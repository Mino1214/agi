"""Web control panel for the Alpha Engine v1.2 paper engine.

The panel is paper-only. It never imports or calls a live broker, and the live
trading control remains locked unless a future explicit live configuration is
implemented elsewhere.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
STATIC_DIR = ROOT / "src" / "static"
for path in (SCRIPT_DIR, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402
import alpha_engine_v1_2_health_monitor as health  # noqa: E402


ERROR_LOG_NAME = "paper_control_errors.jsonl"
PANEL_PID_PATH = ROOT / "data" / "paper_control_panel.pid"
PANEL_STATE_PATH = ROOT / "data" / "paper_control_panel_state.json"
LIVE_LOCK_REASON = "paper only mode: live config and password are not configured"
CHART_TIMEFRAMES = {
    "15M": "15m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
}
CHART_LOOKBACK_SECONDS = {
    "15m": 21 * 86400,
    "1h": 120 * 86400,
    "4h": 365 * 86400,
    "1d": 1250 * 86400,
}
CHART_BAR_LIMITS = {
    "15m": 1200,
    "1h": 1500,
    "4h": 1400,
    "1d": 1250,
}
EMA_WINDOWS = (20, 50, 200)

_run_lock = threading.Lock()
_loop_lock = threading.Lock()
_loop_stop = threading.Event()
_loop_thread: Optional[threading.Thread] = None
_loop_state = {
    "running": False,
    "started_at": "",
    "stopped_at": "",
    "last_run_at": "",
    "last_run_timestamp": 0,
    "last_error": "",
    "interval_seconds": 3600,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the paper engine control panel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--state-dir", default=str(paper.STATE_DIR))
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--loop-interval", type=int, default=3600)
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    paper.ensure_state_files(state_dir)
    write_panel_process_state(args.host, args.port)
    print(f"paper_control_panel http://{args.host}:{args.port}", flush=True)
    serve(args.host, args.port, state_dir=state_dir, use_cache=args.use_cache, loop_interval=args.loop_interval)


def serve(host: str, port: int, state_dir: Path, use_cache: bool = True, loop_interval: int = 3600) -> None:
    _loop_state["interval_seconds"] = loop_interval

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/paper_dashboard.html"}:
                self._send_static("paper_dashboard.html")
                return
            if parsed.path == "/api/paper/status":
                self._send_json(build_status(state_dir))
                return
            if parsed.path == "/api/paper/health":
                self._send_json(health.run_check(state_dir=state_dir))
                return
            if parsed.path == "/api/paper/health/flow":
                self._send_json(health.build_health_flow_payload(state_dir=state_dir))
                return
            if parsed.path == "/api/paper/health/events":
                self._send_json({"ok": True, "events": health.read_health_events(state_dir)})
                return
            if parsed.path == "/api/paper/health/report":
                report = health.read_health_report()
                if not report:
                    health.run_check(state_dir=state_dir)
                    report = health.read_health_report()
                self._send_json({"ok": True, "report": report, "path": str(health.REPORT_PATH)})
                return
            if parsed.path == "/api/paper/chart":
                try:
                    params = parse_qs(parsed.query)
                    symbol = first_query_value(params, "symbol", "")
                    timeframe = first_query_value(params, "timeframe", "1H")
                    self._send_json(build_chart_payload(state_dir, symbol, timeframe))
                except Exception as exc:  # pragma: no cover - HTTP boundary
                    log_error(state_dir, str(exc), path=parsed.path)
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
                return
            if parsed.path == "/api/paper/export":
                self._send_export(state_dir)
                return
            if parsed.path == "/health":
                self._send_json(build_dashboard_health(state_dir))
                return
            if parsed.path.startswith("/static/"):
                self._send_static(parsed.path.removeprefix("/static/"))
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/paper/run-once":
                    payload = run_once_action(state_dir, use_cache)
                    self._send_json(payload)
                    return
                if parsed.path == "/api/paper/start-loop":
                    payload = start_loop_action(state_dir, use_cache, loop_interval)
                    self._send_json(payload)
                    return
                if parsed.path == "/api/paper/stop-loop":
                    payload = stop_loop_action()
                    self._send_json(payload)
                    return
                if parsed.path == "/api/paper/force-close":
                    payload = force_close_positions(state_dir)
                    self._send_json(payload)
                    return
                if parsed.path == "/api/paper/clear-state":
                    payload = clear_paper_state(state_dir)
                    self._send_json(payload)
                    return
                if parsed.path == "/api/paper/live-unlock":
                    self._send_json({"ok": False, "error": LIVE_LOCK_REASON, "live_enabled": False}, status=423)
                    return
                if parsed.path == "/api/paper/health/pause":
                    reason = self._read_reason()
                    payload = health.manual_pause(state_dir, reason)
                    self._send_json({"ok": True, "health": payload, "status": build_status(state_dir)})
                    return
                if parsed.path == "/api/paper/health/resume":
                    reason = self._read_reason()
                    payload = health.manual_resume(state_dir, reason)
                    self._send_json({"ok": True, "health": payload, "status": build_status(state_dir)})
                    return
                if parsed.path == "/api/paper/health/repair":
                    repair = health.repair_market_data_gaps(state_dir=state_dir)
                    flow = health.build_health_flow_payload(state_dir=state_dir)
                    self._send_json({"ok": True, "repair": repair, "flow": flow, "status": build_status(state_dir)})
                    return
                if parsed.path == "/api/paper/health/recheck":
                    flow = health.build_health_flow_payload(state_dir=state_dir)
                    self._send_json({"ok": True, "flow": flow, "status": build_status(state_dir)})
                    return
            except Exception as exc:  # pragma: no cover - HTTP boundary
                log_error(state_dir, str(exc), path=parsed.path)
                self._send_json({"ok": False, "error": str(exc), "status": build_status(state_dir)}, status=500)
                return
            self.send_response(404)
            self.end_headers()

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_reason(self) -> str:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return ""
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return ""
            return str(payload.get("reason", "")).strip()

        def _send_export(self, export_state_dir: Path) -> None:
            body = build_export_zip(export_state_dir)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f"attachment; filename=paper_logs_{stamp}.zip")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, asset_name: str) -> None:
            if "/" in asset_name or "\\" in asset_name or asset_name.startswith("."):
                self.send_response(404)
                self.end_headers()
                return
            path = STATIC_DIR / asset_name
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type(path))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        stop_loop_action()
        server.server_close()


def run_once_action(state_dir: Path, use_cache: bool) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "paper engine is already running", "status": build_status(state_dir)}
    try:
        result = paper.run_once(state_dir=state_dir, use_cache=use_cache)
        now_ts = int(time.time())
        _loop_state["last_run_timestamp"] = now_ts
        _loop_state["last_run_at"] = ts_label(now_ts)
        _loop_state["last_error"] = ""
        return {"ok": True, "result": result, "status": build_status(state_dir)}
    except Exception as exc:
        _loop_state["last_error"] = str(exc)
        log_error(state_dir, str(exc), path="run-once")
        raise
    finally:
        _run_lock.release()


def start_loop_action(state_dir: Path, use_cache: bool, interval_seconds: int) -> dict:
    global _loop_thread
    with _loop_lock:
        if _loop_thread and _loop_thread.is_alive():
            return {"ok": True, "message": "loop already running", "status": build_status(state_dir)}
        _loop_stop.clear()
        _loop_state.update(
            {
                "running": True,
                "started_at": now_label(),
                "stopped_at": "",
                "last_error": "",
                "interval_seconds": interval_seconds,
            }
        )
        _loop_thread = threading.Thread(
            target=loop_worker,
            args=(state_dir, use_cache, interval_seconds),
            name="paper-engine-loop",
            daemon=True,
        )
        _loop_thread.start()
    return {"ok": True, "message": "loop started", "status": build_status(state_dir)}


def stop_loop_action() -> dict:
    _loop_stop.set()
    with _loop_lock:
        running = bool(_loop_thread and _loop_thread.is_alive())
        _loop_state["running"] = False
        _loop_state["stopped_at"] = now_label()
    return {"ok": True, "message": "loop stop requested" if running else "loop is not running", "loop": dict(_loop_state)}


def loop_worker(state_dir: Path, use_cache: bool, interval_seconds: int) -> None:
    while not _loop_stop.is_set():
        try:
            run_once_action(state_dir, use_cache)
        except Exception:
            pass
        if _loop_stop.wait(interval_seconds):
            break
    _loop_state["running"] = False
    _loop_state["stopped_at"] = now_label()


def build_status(state_dir: Path) -> dict:
    paper.ensure_state_files(state_dir)
    positions = paper.read_csv_rows(state_dir / paper.STATE_FILES["positions"][0])
    orders = paper.read_csv_rows(state_dir / paper.STATE_FILES["orders"][0])
    trades = paper.read_csv_rows(state_dir / paper.STATE_FILES["trades"][0])
    equity = paper.read_csv_rows(state_dir / paper.STATE_FILES["equity"][0])
    signals = paper.read_csv_rows(state_dir / paper.STATE_FILES["signals"][0])
    errors = read_recent_errors(state_dir, 20)
    health_state = health.load_health_state(state_dir)
    dashboard_state = read_panel_process_state()
    latest_equity = equity[-1] if equity else {}
    current_regime = latest_equity.get("current_regime", "")
    current_action_bias = latest_equity.get("current_action_bias", "")
    strategy_status = latest_equity.get("strategy_status") or "normal"
    health_locked = (
        health_state.get("status") == "paused"
        or health_state.get("new_entry_allowed") is False
        or health_state.get("can_enter") is False
    )
    display_status = "paused" if health_state.get("status") == "paused" else health_state.get("status") or strategy_status
    can_enter = can_enter_now(strategy_status, current_regime, current_action_bias) and not health_locked
    recent_closed = paper.recent_closed_trades(trades, 20)
    recent_pnls = [float(row.get("position_total_pnl") or 0.0) for row in recent_closed]
    latest_signal_batch = latest_signal_rows(signals)
    order_by_signal = latest_order_by_signal(orders)
    enriched_latest_signals = [enrich_signal(row, latest_equity, order_by_signal) for row in latest_signal_batch]

    status = {
        "paper_only": True,
        "symbols": available_symbols(positions, orders, trades, signals),
        "strategy": {
            "status": display_status,
            "current_regime": current_regime,
            "current_action_bias": current_action_bias,
            "can_enter": can_enter,
            "can_enter_label": "진입 가능" if can_enter else "신규 진입 금지 상태입니다",
            "beginner_message": health_state.get("beginner_message") if health_locked else beginner_message(strategy_status, current_regime, current_action_bias, positions, latest_signal_batch),
            "last_run_at": latest_run_at_label(latest_equity),
            "last_data_update_at": last_data_update_label(),
            "pause_reason": health_state.get("pause_reason") or health_state.get("final_block_reason", ""),
            "paper_start_time": health_state.get("paper_start_time", ""),
            "strategy_locked": health_state.get("strategy_locked", False),
            "strategy_lock_time": health_state.get("strategy_lock_time", ""),
            "dashboard": dashboard_state,
            "loop": dict(_loop_state),
            "live_lock": {
                "paper_only": True,
                "live_enabled": False,
                "button_enabled": False,
                "reason": live_lock_reason(current_regime, current_action_bias),
            },
        },
        "metrics": {
            "equity": to_float(latest_equity.get("equity"), paper.INITIAL_CASH),
            "cash": to_float(latest_equity.get("cash"), paper.INITIAL_CASH),
            "unrealized_pnl": sum(to_float(row.get("unrealized_pnl"), 0.0) for row in positions),
            "cumulative_pnl": to_float(latest_equity.get("cumulative_pnl"), 0.0),
            "recent_30d_performance_pct": paper.recent_equity_performance(equity, 30),
            "recent_20_trade_pf": paper.profit_factor(recent_pnls),
            "recent_20_trade_win_rate_pct": paper.win_rate_pct(recent_pnls),
            "max_drawdown_pct": min((to_float(row.get("drawdown_pct"), 0.0) for row in equity), default=0.0),
        },
        "signals": {
            "current": enriched_latest_signals,
            "entry_candidates": [row for row in enriched_latest_signals if row.get("entry_allowed")],
            "top_candidates": [row for row in enriched_latest_signals if row.get("top_20_passed")],
            "scan_summary": signal_scan_summary(enriched_latest_signals),
            "recent": [enrich_signal(row, latest_equity, order_by_signal) for row in signals[-20:]][::-1],
        },
        "positions": [enrich_position(row) for row in positions],
        "logs": {
            "orders": orders[-20:][::-1],
            "trades": trades[-20:][::-1],
            "signals": signals[-20:][::-1],
            "errors": errors,
        },
        "health": health_state,
        "dashboard": dashboard_state,
        "files": {
            key: str(state_dir / value[0])
            for key, value in paper.STATE_FILES.items()
        },
    }
    return status


def build_dashboard_health(state_dir: Path) -> dict:
    health_state = health.load_health_state(state_dir)
    process_state = read_panel_process_state()
    return {
        "ok": True,
        "paper_only": True,
        "dashboard": process_state,
        "loop": dict(_loop_state),
        "health": {
            "status": health_state.get("status", "normal"),
            "new_entry_allowed": health_state.get("new_entry_allowed", True),
            "pause_reason": health_state.get("pause_reason") or health_state.get("final_block_reason", ""),
            "last_check_at": health_state.get("last_check_at", ""),
        },
    }


def build_chart_payload(state_dir: Path, requested_symbol: str = "", requested_timeframe: str = "1H") -> dict:
    paper.ensure_state_files(state_dir)
    status = build_status(state_dir)
    symbol = normalize_chart_symbol(requested_symbol, status.get("symbols", []))
    timeframe = normalize_timeframe(requested_timeframe)
    interval = CHART_TIMEFRAMES[timeframe]
    now_ts = int(datetime.now(timezone.utc).timestamp())
    candles = load_chart_candles(symbol, interval, now_ts)
    candles = attach_ema(candles)
    visible = candles[-CHART_BAR_LIMITS[interval]:]
    events = build_chart_events(state_dir, symbol, interval, visible)
    price_lines = build_chart_price_lines(state_dir, symbol, visible)

    return {
        "ok": True,
        "paper_only": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "interval": interval,
        "generated_at": now_label(),
        "status": {
            "regime": status["strategy"].get("current_regime", ""),
            "action_bias": status["strategy"].get("current_action_bias", ""),
            "strategy_status": status["strategy"].get("status", "normal"),
            "open_positions": len(status.get("positions", [])),
            "last_update": status["strategy"].get("last_data_update_at") or status["strategy"].get("last_run_at") or "",
        },
        "candles": [
            {
                "time": int(row["time"]),
                "open": to_float(row.get("open"), 0.0),
                "high": to_float(row.get("high"), 0.0),
                "low": to_float(row.get("low"), 0.0),
                "close": to_float(row.get("close"), 0.0),
            }
            for row in visible
        ],
        "volume": [
            {
                "time": int(row["time"]),
                "value": to_float(row.get("volume"), 0.0),
                "color": "rgba(22, 163, 74, 0.38)"
                if to_float(row.get("close"), 0.0) >= to_float(row.get("open"), 0.0)
                else "rgba(239, 68, 68, 0.38)",
            }
            for row in visible
        ],
        "ema20": chart_line_values(visible, "ema20"),
        "ema50": chart_line_values(visible, "ema50"),
        "ema200": chart_line_values(visible, "ema200"),
        "events": events,
        "price_lines": price_lines,
    }


def normalize_timeframe(value: str) -> str:
    normalized = (value or "1H").strip().upper()
    return normalized if normalized in CHART_TIMEFRAMES else "1H"


def normalize_chart_symbol(value: str, symbols: List[str]) -> str:
    normalized = (value or "").strip().upper()
    if normalized and normalized in symbols:
        return normalized
    if normalized and normalized.endswith("USDT") and normalized != "DOGEUSDT":
        return normalized
    return symbols[0] if symbols else "BTCUSDT"


def available_symbols(positions: List[dict], orders: List[dict], trades: List[dict], signals: List[dict]) -> List[str]:
    symbols = {symbol for symbol in paper.TRADING_UNIVERSE if symbol != "DOGEUSDT"}
    for row in [*positions, *orders, *trades, *signals]:
        symbol = str(row.get("symbol", "")).upper()
        if symbol.endswith("USDT") and symbol != "DOGEUSDT":
            symbols.add(symbol)
    preferred = list(paper.TRADING_UNIVERSE)
    return sorted(symbols, key=lambda item: (preferred.index(item) if item in preferred else len(preferred), item))


def load_chart_candles(symbol: str, interval: str, now_ts: int) -> List[dict]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{symbol}_{interval}.json"
    cached = paper.read_json_list(path)
    interval_seconds = paper.INTERVAL_SECONDS[interval]
    latest_open = int(cached[-1]["time"]) if cached else 0
    merged = cached

    if not cached or latest_open + interval_seconds <= now_ts:
        warmup_seconds = max(250 * interval_seconds, 3 * 86400)
        earliest_needed = now_ts - CHART_LOOKBACK_SECONDS[interval] - warmup_seconds
        fetch_start_ts = earliest_needed
        if cached:
            fetch_start_ts = max(earliest_needed, latest_open + interval_seconds)
        try:
            fetched = paper.fetch_ohlcv(
                symbol,
                interval,
                paper.ts_to_iso(fetch_start_ts),
                paper.ts_to_iso(now_ts + interval_seconds),
            )
        except RuntimeError:
            if not cached:
                raise
            fetched = []
        merged = paper.merge_candles(cached, fetched)
        if fetched:
            path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")

    cutoff = now_ts - CHART_LOOKBACK_SECONDS[interval] - max(250 * interval_seconds, 3 * 86400)
    return [row for row in merged if int(row.get("time", 0)) >= cutoff]


def attach_ema(candles: List[dict]) -> List[dict]:
    ema_values: Dict[int, Optional[float]] = {window: None for window in EMA_WINDOWS}
    out = []
    for row in candles:
        enriched = dict(row)
        close = to_float(row.get("close"), None)
        if close is not None:
            for window in EMA_WINDOWS:
                multiplier = 2 / (window + 1)
                previous = ema_values[window]
                ema_values[window] = close if previous is None else close * multiplier + previous * (1 - multiplier)
                enriched[f"ema{window}"] = ema_values[window]
        out.append(enriched)
    return out


def chart_line_values(candles: List[dict], key: str) -> List[dict]:
    return [
        {"time": int(row["time"]), "value": to_float(row.get(key), 0.0)}
        for row in candles
        if row.get(key) not in {"", None}
    ]


def build_chart_events(state_dir: Path, symbol: str, interval: str, candles: List[dict]) -> List[dict]:
    if not candles:
        return []
    start_time = int(candles[0]["time"])
    end_time = int(candles[-1]["time"]) + paper.INTERVAL_SECONDS[interval]
    orders = paper.read_csv_rows(state_dir / paper.STATE_FILES["orders"][0])
    trades = paper.read_csv_rows(state_dir / paper.STATE_FILES["trades"][0])
    signals = paper.read_csv_rows(state_dir / paper.STATE_FILES["signals"][0])
    events = []
    signal_price_by_id = {
        row.get("signal_id", ""): to_float(row.get("close"), None)
        for row in signals
        if row.get("signal_id")
    }

    for row in orders:
        if str(row.get("symbol", "")).upper() != symbol:
            continue
        event = chart_event_from_order(row, interval, signal_price_by_id)
        if event and start_time <= int(event["time"]) <= end_time:
            events.append(event)

    for row in trades:
        if str(row.get("symbol", "")).upper() != symbol:
            continue
        event = chart_event_from_trade(row, interval)
        if event and start_time <= int(event["time"]) <= end_time:
            events.append(event)

    for row in signals:
        if str(row.get("symbol", "")).upper() != symbol:
            continue
        event = chart_event_from_signal(row, interval)
        if event and start_time <= int(event["time"]) <= end_time:
            events.append(event)

    return sorted(events, key=lambda item: (int(item["time"]), item["placement"], item["id"]))


def chart_event_from_order(row: dict, interval: str, signal_price_by_id: Dict[str, Optional[float]]) -> Optional[dict]:
    status = str(row.get("status", "")).lower()
    if status not in {"rejected", "canceled", "cancelled", "expired"}:
        return None
    timestamp = int(float(row.get("fill_time") or row.get("signal_time") or row.get("created_time") or 0))
    price = to_float(row.get("entry_price"), None)
    if price is None:
        price = signal_price_by_id.get(row.get("signal_id", ""))
    if not timestamp or price is None:
        return None
    reason = row.get("reason", "") or status
    return {
        "id": row.get("order_id") or f"order_{status}_{timestamp}_{row.get('symbol', '')}",
        "time": marker_candle_time(timestamp, interval, "order"),
        "timestamp": timestamp,
        "date": ts_label(timestamp),
        "price": price,
        "label": "MS",
        "tone": "missed",
        "placement": "above",
        "event": "Missed Signal",
        "reason": reason_label(reason),
        "side": row.get("side", ""),
    }


def chart_event_from_trade(row: dict, interval: str) -> Optional[dict]:
    event_type = row.get("event_type", "")
    if event_type == "funding_fee":
        return None
    timestamp = int(float(row.get("timestamp") or 0))
    price = to_float(row.get("price") or row.get("exit_price") or row.get("entry_price"), None)
    if not timestamp or price is None:
        return None

    label = "C"
    tone = "close"
    placement = "above"
    event_name = "Manual Close"
    reason = row.get("reason", "")
    side = str(row.get("side", "")).lower()

    if event_type == "entry":
        is_short = side in {"sell", "short"}
        label = "S" if is_short else "B"
        tone = "short-entry" if is_short else "long-entry"
        placement = "below"
        event_name = "Short Entry" if is_short else "Long Entry"
    elif event_type == "partial_exit":
        label = "TP"
        tone = "partial-tp"
        event_name = "Partial Take Profit"
    elif event_type == "exit":
        lowered = reason.lower()
        if "liquid" in lowered:
            label = "Liq"
            tone = "liquidation"
            event_name = "Liquidation"
        elif "stop" in lowered:
            label = "SL"
            tone = "stop-loss"
            event_name = "Stop Loss"
        elif "take_profit" in lowered or "target" in lowered or "final" in lowered:
            label = "TP"
            tone = "final-tp"
            event_name = "Final Take Profit"
        elif "force_close" in lowered or "manual" in lowered:
            label = "C"
            tone = "close"
            event_name = "Manual Close"
        else:
            pnl = to_float(row.get("position_total_pnl") or row.get("pnl"), 0.0)
            if pnl and pnl > 0:
                label = "TP"
                tone = "final-tp"
                event_name = "Final Take Profit"

    return {
        "id": row.get("event_id") or f"{event_type}_{timestamp}_{row.get('symbol', '')}",
        "time": marker_candle_time(timestamp, interval, event_type),
        "timestamp": timestamp,
        "date": ts_label(timestamp),
        "price": price,
        "label": label,
        "tone": tone,
        "placement": placement,
        "event": event_name,
        "reason": reason,
        "side": row.get("side", ""),
    }


def chart_event_from_signal(row: dict, interval: str) -> Optional[dict]:
    selected = str(row.get("selected", "")).lower() == "true"
    reason = row.get("rejection_reason", "")
    if selected and not reason:
        return None
    timestamp = int(float(row.get("signal_time") or row.get("fill_time") or 0))
    price = to_float(row.get("close"), None)
    if not timestamp or price is None:
        return None
    return {
        "id": row.get("signal_id") or f"missed_{timestamp}_{row.get('symbol', '')}",
        "time": marker_candle_time(timestamp, interval, "signal"),
        "timestamp": timestamp,
        "date": ts_label(timestamp),
        "price": price,
        "label": "MS",
        "tone": "missed",
        "placement": "above",
        "event": "Missed Signal",
        "reason": reason_label(reason or "후보는 있지만 주문하지 않습니다"),
        "side": "",
    }


def marker_candle_time(timestamp: int, interval: str, event_type: str) -> int:
    seconds = paper.INTERVAL_SECONDS[interval]
    marker_time = timestamp - (timestamp % seconds)
    if event_type in {"exit", "partial_exit"} and timestamp % seconds == 0:
        marker_time -= seconds
    return max(marker_time, 0)


def build_chart_price_lines(state_dir: Path, symbol: str, candles: List[dict]) -> List[dict]:
    positions = paper.read_csv_rows(state_dir / paper.STATE_FILES["positions"][0])
    row = next((item for item in positions if str(item.get("symbol", "")).upper() == symbol), None)
    if not row:
        return []
    entry = to_float(row.get("entry_price"), None)
    stop = to_float(row.get("stop_price"), None)
    risk = to_float(row.get("risk_distance"), None)
    current = to_float(row.get("last_price"), None)
    if current is None and candles:
        current = to_float(candles[-1].get("close"), None)

    side = str(row.get("side", "long")).lower()
    tp = None
    if entry is not None and risk is not None:
        tp = entry - risk if side in {"short", "sell"} else entry + risk

    candidates = [
        ("entry", "Entry", entry, "#22c55e"),
        ("stop", "Stop", stop, "#f97316"),
        ("tp", "TP", tp, "#2563eb"),
        ("current", "Current", current, "#e5e7eb"),
    ]
    return [
        {"id": key, "title": f"{title} {price:.6g}", "price": price, "color": color}
        for key, title, price, color in candidates
        if price is not None
    ]


def first_query_value(params: dict, key: str, default: str) -> str:
    value = params.get(key)
    if not value:
        return default
    return value[0] if value[0] not in {"", None} else default


def latest_order_by_signal(orders: List[dict]) -> Dict[str, dict]:
    out = {}
    for row in orders:
        signal_id = row.get("signal_id")
        if signal_id:
            out[signal_id] = row
    return out


def signal_scan_summary(signals: List[dict]) -> dict:
    total = len(signals)
    top = [row for row in signals if row.get("top_20_passed")]
    entry = [row for row in signals if row.get("entry_allowed")]
    remaining = max(0, total - len(top))
    reason_counts: Dict[str, int] = {}
    for row in signals:
        reason = row.get("rejection_reason") or ""
        if not reason:
            continue
        reason_counts[reason_label(reason)] = reason_counts.get(reason_label(reason), 0) + 1
    top_symbols = [row.get("symbol", "") for row in top]
    if top_symbols:
        top_label = f"상위 20% 조건 통과: {', '.join(top_symbols)}"
    else:
        top_label = "상위 20% 조건 통과 심볼이 없습니다"
    non_top = [row for row in signals if not row.get("top_20_passed")]
    if remaining and all(row.get("rejection_reason") in {"alpha_score_below_min", "alpha_score_not_top_20pct"} for row in non_top):
        remaining_label = f"나머지 {remaining}개는 점수 부족으로 제외"
    elif remaining:
        remaining_label = f"나머지 {remaining}개는 조건 미통과로 제외"
    else:
        remaining_label = "전체 스캔 심볼이 상위 조건을 통과했습니다"
    return {
        "scan_count": total,
        "entry_count": len(entry),
        "top_count": len(top),
        "excluded_count": total - len(entry),
        "top_symbols": top_symbols,
        "top_label": top_label,
        "remaining_label": remaining_label,
        "reason_counts": reason_counts,
    }


def enrich_signal(row: dict, latest_equity: dict, order_by_signal: Optional[Dict[str, dict]] = None) -> dict:
    close = to_float(row.get("close"), None)
    atr = to_float(row.get("atr14"), None)
    equity = to_float(latest_equity.get("equity"), paper.INITIAL_CASH)
    expected_entry = close * (1 + paper.SLIPPAGE_RATE) if close is not None else None
    stop = expected_entry - paper.alpha.STOP_ATR_MULTIPLE * atr if expected_entry is not None and atr is not None else None
    risk_distance = expected_entry - stop if expected_entry is not None and stop is not None else None
    target_risk = equity * paper.alpha.BASE_RISK_PER_SYMBOL
    raw_leverage = None
    applied_leverage = None
    if expected_entry and risk_distance and risk_distance > 0 and equity:
        expected_notional = min(target_risk / risk_distance * expected_entry, equity * paper.PAPER_CONFIG.global_max_leverage)
        raw_leverage = expected_notional / equity
        applied_leverage = paper.applied_leverage_from_raw(raw_leverage)
    order = (order_by_signal or {}).get(row.get("signal_id", ""), {})
    order_reason = order.get("reason") if order.get("status") == "rejected" else ""
    selected = str(row.get("selected", "")).lower() == "true"
    reason = order_reason or row.get("rejection_reason") or ("진입 가능" if selected else "후보는 있지만 주문하지 않습니다")
    entry_allowed = selected and not order_reason
    top_20_passed = str(row.get("top_20_passed", "")).lower() == "true"
    return {
        **row,
        "selected": selected,
        "entry_allowed": entry_allowed,
        "top_20_passed": top_20_passed,
        "order_status": order.get("status", ""),
        "order_reason": order_reason,
        "reason_label": reason_label(reason),
        "expected_entry_price": expected_entry,
        "stop_price": stop,
        "target_risk": target_risk,
        "raw_leverage": raw_leverage,
        "applied_leverage": applied_leverage,
        "expected_leverage": applied_leverage,
    }


def enrich_position(row: dict) -> dict:
    unrealized = to_float(row.get("unrealized_pnl"), 0.0)
    funding_pnl = to_float(row.get("funding_pnl"), 0.0)
    return {
        **row,
        "beginner_message": "포지션 보유 중입니다",
        "unrealized_pnl_number": unrealized,
        "funding_cost": -funding_pnl if funding_pnl < 0 else 0.0,
        "applied_leverage": paper.applied_leverage_from_raw(
            to_float(row.get("applied_leverage"), paper.applied_leverage_from_raw(to_float(row.get("raw_leverage"), 1.0)))
        ),
    }


def force_close_positions(state_dir: Path) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "paper engine is already running", "status": build_status(state_dir)}
    try:
        paper.ensure_state_files(state_dir)
        positions = paper.read_csv_rows(state_dir / paper.STATE_FILES["positions"][0])
        if not positions:
            return {"ok": True, "closed": 0, "status": build_status(state_dir)}

        now_ts = int(datetime.now(timezone.utc).timestamp())
        trades = paper.read_csv_rows(state_dir / paper.STATE_FILES["trades"][0])
        equity_rows = paper.read_csv_rows(state_dir / paper.STATE_FILES["equity"][0])
        latest_equity = equity_rows[-1] if equity_rows else {}
        cash = to_float(latest_equity.get("cash"), paper.INITIAL_CASH)
        new_events = []
        for row in positions:
            event, cash = force_close_event(row, cash, now_ts)
            new_events.append(event)

        trades = paper.merge_unique(trades, new_events, "event_id")
        paper.write_csv_rows(state_dir / paper.STATE_FILES["trades"][0], trades, paper.TRADE_FIELDS)
        paper.write_csv_rows(state_dir / paper.STATE_FILES["positions"][0], [], paper.POSITION_FIELDS)
        equity_rows = paper.merge_unique(equity_rows, [force_close_equity_row(latest_equity, cash, now_ts, equity_rows)], "timestamp")
        paper.write_csv_rows(state_dir / paper.STATE_FILES["equity"][0], equity_rows, paper.EQUITY_FIELDS)
        return {"ok": True, "closed": len(new_events), "status": build_status(state_dir)}
    finally:
        _run_lock.release()


def force_close_event(row: dict, cash: float, timestamp: int) -> tuple[dict, float]:
    position_id = row.get("position_id") or f"manual_{row.get('symbol', 'unknown')}_{timestamp}"
    price = to_float(row.get("last_price"), to_float(row.get("entry_price"), 0.0))
    units = to_float(row.get("units"), 0.0)
    entry = to_float(row.get("entry_price"), price)
    fee = units * price * paper.TAKER_FEE_RATE
    exit_pnl = units * (price - entry) - fee
    funding_pnl = to_float(row.get("funding_pnl"), 0.0)
    realized = to_float(row.get("realized_pnl"), 0.0) + exit_pnl + funding_pnl
    cash += exit_pnl
    opened_at = int(float(row.get("opened_at") or timestamp))
    event = {
        "event_id": f"force_close_{position_id}_{timestamp}",
        "event_type": "exit",
        "position_id": position_id,
        "order_id": row.get("order_id", ""),
        "timestamp": timestamp,
        "date": paper.format_dt(timestamp),
        "symbol": row.get("symbol", ""),
        "side": "sell",
        "price": price,
        "units": units,
        "notional": units * price,
        "fee": fee,
        "raw_leverage": row.get("raw_leverage", ""),
        "applied_leverage": row.get("applied_leverage", ""),
        "funding_rate": "",
        "funding_pnl": funding_pnl,
        "pnl": exit_pnl,
        "cash_delta": exit_pnl,
        "equity_after": cash,
        "reason": "force_close_panel",
        "alpha_score": row.get("alpha_score", ""),
        "trade_regime": row.get("trade_regime", ""),
        "trade_action_bias": row.get("trade_action_bias", ""),
        "entry_price": entry,
        "stop_price": row.get("stop_price", ""),
        "exit_price": price,
        "position_total_pnl": realized,
        "hold_hours": (timestamp - opened_at) / 3600,
    }
    return event, cash


def force_close_equity_row(latest: dict, cash: float, timestamp: int, rows: List[dict]) -> dict:
    previous_equities = [to_float(row.get("equity"), paper.INITIAL_CASH) for row in rows]
    peak = max(previous_equities + [cash]) if previous_equities else cash
    drawdown = (cash / peak - 1) * 100 if peak else 0.0
    return {
        "timestamp": timestamp,
        "date": paper.format_dt(timestamp),
        "equity": cash,
        "cash": cash,
        "open_unrealized": 0.0,
        "cumulative_pnl": cash - paper.INITIAL_CASH,
        "drawdown_pct": drawdown,
        "open_positions": 0,
        "open_notional": 0.0,
        "current_regime": latest.get("current_regime", ""),
        "current_action_bias": latest.get("current_action_bias", ""),
        "strategy_status": latest.get("strategy_status", "normal"),
        "max_drawdown_pct": min([to_float(row.get("drawdown_pct"), 0.0) for row in rows] + [drawdown]),
        "liquidation_risk_count": 0,
    }


def clear_paper_state(state_dir: Path) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "paper engine is already running", "status": build_status(state_dir)}
    try:
        paper.ensure_state_files(state_dir)
        for filename, fields in paper.STATE_FILES.values():
            paper.write_csv_rows(state_dir / filename, [], fields)
        return {"ok": True, "cleared": True, "status": build_status(state_dir)}
    finally:
        _run_lock.release()


def build_export_zip(state_dir: Path) -> bytes:
    paper.ensure_state_files(state_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, _fields in paper.STATE_FILES.values():
            path = state_dir / filename
            if path.exists():
                archive.write(path, arcname=filename)
        for path in sorted(state_dir.glob("paper_daily_report*.md")):
            archive.write(path, arcname=path.name)
        for filename in (health.HEALTH_CSV, health.HEALTH_EVENTS_CSV, health.HEALTH_STATE_JSON, health.HEALTH_REPAIR_STATE_JSON):
            path = state_dir / filename
            if path.exists():
                archive.write(path, arcname=filename)
        if health.REPORT_PATH.exists():
            archive.write(health.REPORT_PATH, arcname=health.REPORT_PATH.name)
        error_path = state_dir / ERROR_LOG_NAME
        if error_path.exists():
            archive.write(error_path, arcname=ERROR_LOG_NAME)
    return buffer.getvalue()


def latest_signal_rows(signals: List[dict]) -> List[dict]:
    if not signals:
        return []
    latest_time = max(int(float(row.get("signal_time") or 0)) for row in signals)
    rows = [row for row in signals if int(float(row.get("signal_time") or 0)) == latest_time]
    preferred = {symbol: index for index, symbol in enumerate(paper.TRADING_UNIVERSE)}
    return sorted(
        rows,
        key=lambda row: (
            not (str(row.get("top_20_passed", "")).lower() == "true"),
            int(float(row.get("rank") or 999)),
            preferred.get(row.get("symbol", ""), len(preferred)),
            row.get("symbol", ""),
        ),
    )


def can_enter_now(status: str, regime: str, action_bias: str) -> bool:
    if status != "normal":
        return False
    if regime in {"shock", "defensive", "observe", "neutral"}:
        return False
    if action_bias in {"no_new_entry", "wait", "reduce_risk"}:
        return False
    return True


def beginner_message(status: str, regime: str, action_bias: str, positions: List[dict], signals: List[dict]) -> str:
    if status == "paused" or regime == "shock" or action_bias == "no_new_entry":
        return "위험 상태라 정지합니다"
    if positions:
        return "포지션 보유 중입니다"
    if regime in {"defensive", "observe", "neutral"} or action_bias in {"wait", "reduce_risk"}:
        return "지금은 쉬는 장입니다"
    if signals and not any(str(row.get("selected", "")).lower() == "true" for row in signals):
        return "후보는 있지만 주문하지 않습니다"
    return "진입 조건을 기다리는 중입니다"


def reason_label(reason: str) -> str:
    labels = {
        "": "진입 가능",
        "doge_excluded": "DOGE는 제외합니다",
        "defensive_no_entry": "reduce_risk로 주문 금지",
        "regime_no_entry": "현재 레짐에서 신규 진입 금지",
        "alpha_score_below_min": "alpha_score 부족",
        "alpha_score_not_top_20pct": "top 20% 미통과",
        "data_missing": "데이터 부족",
        "liquidation_buffer_unavailable": "liquidation buffer 실패",
        "already_open": "이미 포지션이 있습니다",
        "max_positions": "보유 한도에 도달했습니다",
        "missed_signal_before_paper_start": "paper_start_time 이전 신호입니다",
        "applied_leverage_liquidation_buffer": "정수 레버리지 적용 시 청산 안전거리가 부족합니다",
    }
    return labels.get(reason, reason)


def live_lock_reason(regime: str, action_bias: str) -> str:
    if regime in {"shock", "defensive"} or action_bias in {"no_new_entry", "reduce_risk"}:
        return "live disabled by market risk state; paper only"
    return LIVE_LOCK_REASON


def last_data_update_label() -> str:
    raw_dir = ROOT / "data" / "raw"
    mtimes = [path.stat().st_mtime for path in raw_dir.glob("*.json") if path.is_file()]
    return ts_label(max(mtimes)) if mtimes else ""


def write_panel_process_state(host: str, port: int) -> dict:
    PANEL_PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous = read_panel_process_state()
    now = now_label()
    pid = os.getpid()
    state = {
        "pid": pid,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}",
        "started_at": now,
        "last_restart_at": now,
        "restart_count": int(previous.get("restart_count") or 0) + 1,
        "alive": True,
        "pid_path": str(PANEL_PID_PATH),
        "state_path": str(PANEL_STATE_PATH),
        "restart_command": "scripts/manage_paper_control_panel.sh restart",
    }
    PANEL_PID_PATH.write_text(f"{pid}\n", encoding="utf-8")
    PANEL_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return state


def read_panel_process_state() -> dict:
    state = {}
    if PANEL_STATE_PATH.exists():
        try:
            loaded = json.loads(PANEL_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        except json.JSONDecodeError:
            state = {}
    pid = to_int(state.get("pid"), None)
    if pid is None and PANEL_PID_PATH.exists():
        pid = to_int(PANEL_PID_PATH.read_text(encoding="utf-8").strip(), None)
    alive = process_alive(pid)
    return {
        "pid": pid,
        "alive": alive,
        "host": state.get("host", "127.0.0.1"),
        "port": state.get("port", 8790),
        "url": state.get("url", "http://127.0.0.1:8790"),
        "started_at": state.get("started_at", ""),
        "last_restart_at": state.get("last_restart_at", ""),
        "restart_count": state.get("restart_count", 0),
        "pid_path": str(PANEL_PID_PATH),
        "state_path": str(PANEL_STATE_PATH),
        "restart_command": state.get("restart_command", "scripts/manage_paper_control_panel.sh restart"),
    }


def process_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_recent_errors(state_dir: Path, limit: int) -> List[dict]:
    path = state_dir / ERROR_LOG_NAME
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:][::-1]


def log_error(state_dir: Path, message: str, path: str = "") -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": int(datetime.now(timezone.utc).timestamp()), "date": now_label(), "path": path, "message": message}
    with (state_dir / ERROR_LOG_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def content_type(path: Path) -> str:
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    return "application/octet-stream"


def to_float(value, default: Optional[float] = 0.0) -> Optional[float]:
    if value in {"", None}:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def to_int(value, default: Optional[int] = 0) -> Optional[int]:
    if value in {"", None}:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def latest_run_at_label(latest_equity: dict) -> str:
    equity_ts = to_int(latest_equity.get("timestamp"), None)
    loop_ts = to_int(_loop_state.get("last_run_timestamp"), None)
    timestamps = [value for value in (equity_ts, loop_ts) if value is not None]
    if timestamps:
        return ts_label(max(timestamps))
    return _loop_state.get("last_run_at", "")


def ts_label(value) -> str:
    if value in {"", None}:
        return ""
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    main()
