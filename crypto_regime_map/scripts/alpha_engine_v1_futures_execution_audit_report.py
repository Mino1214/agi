"""Futures execution and liquidation audit for Alpha Engine v1.

This is a standalone audit artifact. It does not modify the Alpha Engine v1
or futures funding audit files. The script reuses the Alpha Engine rules,
adds execution metadata at runtime, compares spot and USD-M futures OHLCV,
and stress-tests fees, slippage, stop fills, and liquidation assumptions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_report as v1  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


FAPI_BASE_URLS = ("https://fapi.binance.com",)
SYMBOLS = alpha.UNIVERSE_10
EXPECTED_BASE_UNIQUE_TRADES = 1140
BASE_CONFIG_NAME = "Alpha Engine v1 / 10 symbols"
MAINTENANCE_MARGIN_RATE = 0.005
LIQUIDATION_FEE_BUFFER = 0.001
SPOT_FUTURES_CAGR_DELTA_LIMIT_PCT = 20.0
SPOT_FUTURES_MDD_DELTA_LIMIT_PPT = 5.0
SPOT_FUTURES_TRADE_DELTA_LIMIT_PCT = 10.0
STOP_FILL_MODE = "normal"
ACTIVE_MARKET_DATA = "spot"


@dataclass(frozen=True)
class AuditRun:
    name: str
    group: str
    market_data: str
    config: alpha.AlphaConfig
    result: dict
    funding_included: bool = False
    stop_fill_mode: str = "normal"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local OHLCV/funding JSON when available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    install_execution_metadata_patch()

    spot_raw_1d = alpha.load_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    spot_raw_4h = alpha.load_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    spot_raw_1h = alpha.load_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    spot_data = alpha.AlphaData(raw_1d=spot_raw_1d, raw_4h=spot_raw_4h, raw_1h=spot_raw_1h)

    futures_raw_1d = load_futures_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    futures_raw_4h = load_futures_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    futures_raw_1h = load_futures_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    futures_data = alpha.AlphaData(raw_1d=futures_raw_1d, raw_4h=futures_raw_4h, raw_1h=futures_raw_1h)

    funding_info = funding.load_funding_info(args.use_cache)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, args.use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }

    base_spot = run_alpha(spot_data, "Spot OHLCV base", "Base", "spot", base_config(BASE_CONFIG_NAME))
    base_futures = run_alpha(futures_data, "Futures OHLCV base", "Futures OHLCV", "futures", base_config("Alpha Engine v1 / 10 symbols / futures OHLCV"))

    fee_runs = [
        run_alpha(spot_data, "Maker only fee 0.02%", "Fee model", "spot", base_config("Maker only fee 0.02%", fee_rate=0.0002)),
        run_alpha(spot_data, "Taker only fee 0.05%", "Fee model", "spot", base_config("Taker only fee 0.05%", fee_rate=0.0005)),
        run_alpha(spot_data, "Maker/taker mixed fee 0.035%", "Fee model", "spot", base_config("Maker/taker mixed fee 0.035%", fee_rate=0.00035)),
    ]
    fee_stress_runs = [
        run_alpha(spot_data, f"Fee stress {rate * 100:.2f}%", "Fee stress", "spot", base_config(f"Fee stress {rate * 100:.2f}%", fee_rate=rate))
        for rate in (0.0005, 0.0010, 0.0020, 0.0030, 0.0050)
    ]
    slippage_runs = [
        run_alpha(
            spot_data,
            "Base slippage 0.05%" if rate == alpha.BASE_SLIPPAGE_RATE else f"Slippage stress {rate * 100:.2f}%",
            "Slippage stress",
            "spot",
            base_config(
                "Base slippage 0.05%" if rate == alpha.BASE_SLIPPAGE_RATE else f"Slippage stress {rate * 100:.2f}%",
                slippage_rate=rate,
            ),
        )
        for rate in (alpha.BASE_SLIPPAGE_RATE, 0.0010, 0.0020, 0.0050, 0.0100)
    ]
    gap_stop_run = run_alpha(
        spot_data,
        "Conservative stop gap fill",
        "Stop fill stress",
        "spot",
        base_config("Conservative stop gap fill"),
        stop_fill_mode="gap_conservative",
    )

    taker_run = next(run for run in fee_runs if run.name == "Taker only fee 0.05%")
    taker_funding_run = funding_overlay_run(taker_run, funding_by_symbol)

    all_runs = [base_spot, base_futures, *fee_runs, *fee_stress_runs, *slippage_runs, gap_stop_run, taker_funding_run]

    spot_liq_trades = annotate_liquidation(base_spot.result["trades"], spot_data, base_spot.config, "Spot OHLCV base")
    futures_liq_trades = annotate_liquidation(base_futures.result["trades"], futures_data, base_futures.config, "Futures OHLCV base")
    trade_rows = spot_liq_trades + futures_liq_trades

    liquidation_stress_curve = liquidation_stress_equity_curve(base_spot.result["equity_curve"], spot_liq_trades)
    liquidation_stress_summary = performance_summary(
        "Liquidation stress / spot base",
        "Liquidation stress",
        "spot",
        base_spot.config,
        liquidation_stress_curve,
        stress_trades_from_liquidation(spot_liq_trades),
        funding_included=False,
        stop_fill_mode="normal",
    )

    summary_rows = [summary_from_run(run) for run in all_runs]
    summary_rows.append(liquidation_stress_summary)
    apply_liquidation_counts(summary_rows, "Spot OHLCV base", spot_liq_trades)
    apply_liquidation_counts(summary_rows, "Futures OHLCV base", futures_liq_trades)
    apply_liquidation_counts(summary_rows, "Liquidation stress / spot base", spot_liq_trades)

    unique_audit = unique_trade_audit(base_spot.result["trades"])
    funding_row_audit = funding_audit_row_check(output_dir)
    spot_futures_audit = spot_futures_comparison(base_spot, base_futures)
    ohlcv_diff_rows = ohlcv_diff_summary(
        {"1h": spot_raw_1h, "4h": spot_raw_4h},
        {"1h": futures_raw_1h, "4h": futures_raw_4h},
    )
    leverage_stats = leverage_distribution(spot_liq_trades)
    liquidation_stats = liquidation_summary(spot_liq_trades, liquidation_stress_summary)
    pass_fail_rows = pass_fail(
        summary_rows,
        unique_audit,
        funding_row_audit,
        spot_futures_audit,
        leverage_stats,
        liquidation_stats,
    )

    report = build_report(
        summary_rows=summary_rows,
        trade_rows=trade_rows,
        pass_fail_rows=pass_fail_rows,
        unique_audit=unique_audit,
        funding_row_audit=funding_row_audit,
        spot_futures_audit=spot_futures_audit,
        ohlcv_diff_rows=ohlcv_diff_rows,
        leverage_stats=leverage_stats,
        liquidation_stats=liquidation_stats,
    )

    report_path = output_dir / "alpha_engine_v1_futures_execution_audit_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_engine_v1_futures_execution_audit_summary.csv", summary_rows)
    write_csv(output_dir / "alpha_engine_v1_futures_execution_audit_trades.csv", trade_rows)
    print(report_path)


def base_config(
    name: str,
    fee_rate: float = alpha.BASE_FEE_RATE,
    slippage_rate: float = alpha.BASE_SLIPPAGE_RATE,
) -> alpha.AlphaConfig:
    return alpha.AlphaConfig(
        name=name,
        universe=tuple(SYMBOLS),
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_leverage=3.0,
    )


def run_alpha(
    data: alpha.AlphaData,
    audit_name: str,
    group: str,
    market_data: str,
    config: alpha.AlphaConfig,
    stop_fill_mode: str = "normal",
) -> AuditRun:
    global STOP_FILL_MODE, ACTIVE_MARKET_DATA
    STOP_FILL_MODE = stop_fill_mode
    ACTIVE_MARKET_DATA = market_data
    result = alpha.run_alpha_engine(data, config)
    return AuditRun(audit_name, group, market_data, config, result, funding_included=False, stop_fill_mode=stop_fill_mode)


def funding_overlay_run(run: AuditRun, funding_by_symbol: Dict[str, List[dict]]) -> AuditRun:
    annotated, cashflows = funding.annotate_trades(run.result["trades"], funding_by_symbol, "actual_funding", "실제 funding", "actual")
    adjusted_curve = funding.adjusted_equity_curve(run.result["equity_curve"], cashflows)
    adjusted_result = {
        "summary": {},
        "trades": annotated,
        "equity_curve": adjusted_curve,
    }
    return AuditRun(
        "Taker only fee 0.05% + actual funding",
        "Fee/Funding",
        run.market_data,
        run.config,
        adjusted_result,
        funding_included=True,
        stop_fill_mode=run.stop_fill_mode,
    )


def install_execution_metadata_patch() -> None:
    def patched_manage_position(data, config, position, row, open_time, close_time, index_1h, cash):
        if row["low"] <= position.stop_price:
            exit_price = stop_exit_price(position, row, config)
            trade = patched_close_trade(data, config, position, exit_price, close_time, index_1h, "stop")
            return cash + trade.pop("_cash_delta"), trade
        target_price = position.entry_price + position.risk_distance
        if not position.partial_taken and row["high"] >= target_price:
            close_units = position.units * 0.5
            proceeds = close_units * target_price * (1 - config.slippage_rate)
            pnl = close_units * (target_price * (1 - config.slippage_rate) - position.entry_price) - proceeds * config.fee_rate
            cash += pnl
            position.realized_pnl += pnl
            position.units -= close_units
            position.partial_taken = True
            position.risk_amount *= 0.5
            position.partial_time = close_time
            position.partial_price = target_price * (1 - config.slippage_rate)
        row_4h = data.by_close_4h.get(position.symbol, {}).get(close_time)
        if row_4h:
            if row_4h.get("ema50") is not None and row_4h["close"] < row_4h["ema50"]:
                trade = patched_close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema50_exit")
                return cash + trade.pop("_cash_delta"), trade
            if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] < row_4h["ema20"]:
                trade = patched_close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema20_trailing_exit")
                return cash + trade.pop("_cash_delta"), trade
        if close_time - position.entry_time >= alpha.MAX_HOLD_HOURS * 3600:
            trade = patched_close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "max_hold")
            return cash + trade.pop("_cash_delta"), trade
        return cash, None

    alpha.manage_position = patched_manage_position
    alpha.close_trade = patched_close_trade


def stop_exit_price(position, row: dict, config: alpha.AlphaConfig) -> float:
    if STOP_FILL_MODE == "gap_conservative" and row["open"] < position.stop_price:
        return row["open"] * (1 - config.slippage_rate)
    return position.stop_price


def patched_close_trade(data, config, position, exit_price, exit_time, index_1h, reason) -> dict:
    gross_pnl = position.units * (exit_price - position.entry_price)
    fee = position.units * exit_price * config.fee_rate
    total_pnl = position.realized_pnl + gross_pnl - fee
    quality = alpha.entry_quality(data, position.symbol, position.entry_time, position.entry_price)
    excursion = alpha.trade_excursion(data, position.symbol, position.entry_time, exit_time, position.entry_price)
    partial_time = getattr(position, "partial_time", "")
    initial_notional = position.initial_units * position.entry_price
    actual_leverage = initial_notional / position.entry_equity if position.entry_equity else 0.0
    return {
        "variant": config.name,
        "audit_market_data": ACTIVE_MARKET_DATA,
        "stop_fill_mode": STOP_FILL_MODE,
        "symbol": v1.short(position.symbol),
        "entry_date": alpha.format_dt(position.entry_time),
        "exit_date": alpha.format_dt(exit_time),
        "entry_timestamp": position.entry_time,
        "exit_timestamp": exit_time,
        "signal_date": alpha.format_dt(position.signal_time),
        "lookahead_pass": position.entry_time >= position.signal_time,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "exit_reason": reason,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "stop_price": position.stop_price,
        "risk_distance_pct": position.risk_distance / position.entry_price * 100,
        "alpha_score": position.signal_score,
        "hold_days": (exit_time - position.entry_time) / 86400,
        "trade_return_pct": total_pnl / position.entry_equity * 100 if position.entry_equity else 0.0,
        "pnl": total_pnl,
        "entry_after_1d_pct": quality["entry_after_1d_pct"],
        "entry_after_3d_pct": quality["entry_after_3d_pct"],
        "entry_after_7d_pct": quality["entry_after_7d_pct"],
        "mae_pct": excursion["mae_pct"],
        "mfe_pct": excursion["mfe_pct"],
        "entry_equity": position.entry_equity,
        "initial_units": position.initial_units,
        "remaining_units_at_exit": position.units,
        "initial_notional": initial_notional,
        "actual_leverage": actual_leverage,
        "configured_max_leverage": config.max_leverage,
        "position_margin_at_cap": initial_notional / config.max_leverage if config.max_leverage else initial_notional,
        "partial_taken": position.partial_taken,
        "partial_time": partial_time,
        "partial_date": alpha.format_dt(partial_time) if partial_time else "",
        "partial_price": getattr(position, "partial_price", ""),
        "_cash_delta": total_pnl,
    }


def load_futures_raw(symbols: Iterable[str], interval: str, use_cache: bool, start: str) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, List[dict]] = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}_futures_{interval}.json"
        cached = v1.read_cache(path) if use_cache else []
        if cached and futures_cache_covers(cached):
            out[symbol] = cached
            continue
        rows = fetch_futures_ohlcv(symbol, interval, start, alpha.FETCH_END)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        out[symbol] = rows
    return out


def futures_cache_covers(candles: List[dict]) -> bool:
    if not candles:
        return False
    end_ts = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
    return candles[-1]["time"] >= end_ts - 24 * 3600


def fetch_futures_ohlcv(symbol: str, interval: str, start: str, end: str) -> List[dict]:
    if interval not in {"1d", "4h", "1h"}:
        raise ValueError(f"Unsupported interval: {interval}")
    interval_seconds = {"1d": 86400, "4h": 14400, "1h": 3600}[interval]
    start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end).timestamp() * 1000)
    cursor = start_ms
    rows: List[dict] = []
    while cursor < end_ms:
        batch = futures_klines_request(symbol, interval, cursor, end_ms)
        if not batch:
            break
        rows.extend(normalize_kline(item) for item in batch)
        next_cursor = int(batch[-1][0]) + interval_seconds * 1000
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.06)
    deduped = {row["time"]: row for row in rows}
    return [deduped[key] for key in sorted(deduped)]


def futures_klines_request(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    query = urlencode(
        {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        }
    )
    last_error: Optional[Exception] = None
    for base_url in FAPI_BASE_URLS:
        request = Request(f"{base_url}/fapi/v1/klines?{query}", headers={"User-Agent": "crypto-regime-map/0.1"})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
    raise RuntimeError(f"Binance futures kline request failed for {symbol} {interval}: {last_error}") from last_error


def normalize_kline(item: list) -> dict:
    return {
        "time": int(item[0]) // 1000,
        "open": float(item[1]),
        "high": float(item[2]),
        "low": float(item[3]),
        "close": float(item[4]),
        "volume": float(item[5]),
    }


def annotate_liquidation(trades: List[dict], data: alpha.AlphaData, config: alpha.AlphaConfig, audit_variant: str) -> List[dict]:
    out = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        liq_price = liquidation_price(float(trade["entry_price"]), config.max_leverage)
        lows_1h = rows_in_window(data.rows_1h.get(symbol, []), int(trade["entry_timestamp"]), int(trade["exit_timestamp"]))
        lows_4h = rows_in_window(data.rows_4h.get(symbol, []), int(trade["entry_timestamp"]), int(trade["exit_timestamp"]))
        min_1h_low = min((row["low"] for row in lows_1h), default=None)
        min_4h_low = min((row["low"] for row in lows_4h), default=None)
        min_1h_open = min((row["open"] for row in lows_1h), default=None)
        stop_before_liq = float(trade["stop_price"]) > liq_price
        low_touched_1h = min_1h_low is not None and min_1h_low <= liq_price
        low_touched_4h = min_4h_low is not None and min_4h_low <= liq_price
        gap_liq_touch = min_1h_open is not None and min_1h_open <= liq_price
        liquidation_risk = (not stop_before_liq) or gap_liq_touch
        liquidation_stress_pnl = -float(trade["position_margin_at_cap"]) if liquidation_risk else float(trade["pnl"])
        unique_key = trade_key(trade)
        out.append(
            {
                **{key: value for key, value in trade.items() if not key.startswith("_")},
                "audit_variant": audit_variant,
                "audit_trade_index": index,
                "unique_trade_key": unique_key,
                "liquidation_price_est": liq_price,
                "liquidation_leverage_used": config.max_leverage,
                "maintenance_margin_rate": MAINTENANCE_MARGIN_RATE,
                "stop_before_liquidation": stop_before_liq,
                "min_1h_low_during_hold": min_1h_low,
                "min_4h_low_during_hold": min_4h_low,
                "liquidation_low_touched_1h": low_touched_1h,
                "liquidation_low_touched_4h": low_touched_4h,
                "liquidation_gap_touch_1h_open": gap_liq_touch,
                "liquidation_risk": liquidation_risk,
                "liquidation_stress_pnl": liquidation_stress_pnl,
                "liquidation_stress_delta": liquidation_stress_pnl - float(trade["pnl"]),
            }
        )
    return out


def liquidation_price(entry_price: float, leverage: float) -> float:
    if leverage <= 1:
        return 0.0
    estimate = entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN_RATE + LIQUIDATION_FEE_BUFFER)
    return max(0.0, estimate)


def rows_in_window(rows: List[dict], entry_time: int, exit_time: int) -> List[dict]:
    return [row for row in rows if entry_time <= row["time"] < exit_time]


def liquidation_stress_equity_curve(curve: List[dict], trades: List[dict]) -> List[dict]:
    deltas = sorted(
        (
            {"time": int(trade["exit_timestamp"]), "delta": float(trade["liquidation_stress_delta"])}
            for trade in trades
            if abs(float(trade["liquidation_stress_delta"])) > 1e-15
        ),
        key=lambda row: row["time"],
    )
    out = []
    cumulative = 0.0
    index = 0
    for point in curve:
        while index < len(deltas) and deltas[index]["time"] <= point["time"]:
            cumulative += deltas[index]["delta"]
            index += 1
        out.append({"time": point["time"], "date": point.get("date", alpha.format_dt(point["time"])), "equity": max(1e-9, point["equity"] + cumulative)})
    return out


def stress_trades_from_liquidation(trades: List[dict]) -> List[dict]:
    out = []
    for trade in trades:
        item = dict(trade)
        item["pnl"] = trade["liquidation_stress_pnl"]
        item["trade_return_pct"] = item["pnl"] / item["entry_equity"] * 100 if item["entry_equity"] else 0.0
        out.append(item)
    return out


def unique_trade_audit(trades: List[dict]) -> dict:
    keys = [trade_key(trade) for trade in trades]
    duplicates = len(keys) - len(set(keys))
    return {
        "base_trade_rows": len(trades),
        "base_unique_trades": len(set(keys)),
        "duplicate_trade_rows": duplicates,
        "matches_expected_1140": len(set(keys)) == EXPECTED_BASE_UNIQUE_TRADES,
    }


def funding_audit_row_check(output_dir: Path) -> dict:
    trades_path = output_dir / "alpha_engine_v1_funding_audit_trades.csv"
    summary_path = output_dir / "alpha_engine_v1_funding_audit_summary.csv"
    if not trades_path.exists() or not summary_path.exists():
        return {
            "funding_trades_rows": None,
            "funding_summary_trade_sum": None,
            "funding_rows_explained_by_scenarios": False,
            "funding_variants": None,
            "funding_scenarios": None,
            "alpha10_actual_unique_trades": None,
        }
    with trades_path.open(encoding="utf-8") as handle:
        trade_rows = list(csv.DictReader(handle))
    with summary_path.open(encoding="utf-8") as handle:
        summary_rows = list(csv.DictReader(handle))
    variants = sorted({row["variant"] for row in trade_rows})
    scenarios = sorted({row["scenario"] for row in trade_rows})
    summary_trade_sum = sum(int(float(row["trades"])) for row in summary_rows)
    alpha10_actual = [
        row
        for row in trade_rows
        if row["variant"] == BASE_CONFIG_NAME and row["scenario"] == "actual_funding"
    ]
    alpha10_unique = len({trade_key(row) for row in alpha10_actual})
    return {
        "funding_trades_rows": len(trade_rows),
        "funding_summary_trade_sum": summary_trade_sum,
        "funding_rows_explained_by_scenarios": len(trade_rows) == summary_trade_sum,
        "funding_variants": len(variants),
        "funding_scenarios": len(scenarios),
        "alpha10_actual_unique_trades": alpha10_unique,
    }


def trade_key(trade: dict) -> str:
    return "|".join(
        [
            str(trade.get("symbol", "")),
            str(trade.get("entry_timestamp", "")),
            str(trade.get("exit_timestamp", "")),
            str(trade.get("exit_reason", "")),
        ]
    )


def spot_futures_comparison(spot_run: AuditRun, futures_run: AuditRun) -> dict:
    spot_summary = summary_from_run(spot_run)
    futures_summary = summary_from_run(futures_run)
    spot_keys = {trade_key(trade) for trade in spot_run.result["trades"]}
    futures_keys = {trade_key(trade) for trade in futures_run.result["trades"]}
    cagr_delta_pct = pct_delta(futures_summary["cagr_pct"], spot_summary["cagr_pct"])
    mdd_delta_ppt = futures_summary["mdd_pct"] - spot_summary["mdd_pct"]
    trade_delta_pct = pct_delta(futures_summary["trades"], spot_summary["trades"])
    return {
        "spot_trades": spot_summary["trades"],
        "futures_trades": futures_summary["trades"],
        "common_trades": len(spot_keys & futures_keys),
        "spot_only_trades": len(spot_keys - futures_keys),
        "futures_only_trades": len(futures_keys - spot_keys),
        "spot_cagr_pct": spot_summary["cagr_pct"],
        "futures_cagr_pct": futures_summary["cagr_pct"],
        "cagr_delta_pct": cagr_delta_pct,
        "spot_mdd_pct": spot_summary["mdd_pct"],
        "futures_mdd_pct": futures_summary["mdd_pct"],
        "mdd_delta_ppt": mdd_delta_ppt,
        "spot_calmar": spot_summary["calmar"],
        "futures_calmar": futures_summary["calmar"],
        "trade_delta_pct": trade_delta_pct,
        "not_large_change": abs(cagr_delta_pct or 0.0) <= SPOT_FUTURES_CAGR_DELTA_LIMIT_PCT
        and abs(mdd_delta_ppt) <= SPOT_FUTURES_MDD_DELTA_LIMIT_PPT
        and abs(trade_delta_pct or 0.0) <= SPOT_FUTURES_TRADE_DELTA_LIMIT_PCT,
    }


def ohlcv_diff_summary(spot_raw: Dict[str, Dict[str, List[dict]]], futures_raw: Dict[str, Dict[str, List[dict]]]) -> List[dict]:
    rows = []
    for interval in ("1h", "4h"):
        for symbol in SYMBOLS:
            spot_by_time = {row["time"]: row for row in spot_raw[interval].get(symbol, [])}
            futures_by_time = {row["time"]: row for row in futures_raw[interval].get(symbol, [])}
            common_times = sorted(set(spot_by_time) & set(futures_by_time))
            common_times = [value for value in common_times if alpha.TEST_START_TS <= value < alpha.TEST_END_TS]
            field_stats = {}
            for field in ("close", "high", "low"):
                diffs = [
                    abs(futures_by_time[time][field] / spot_by_time[time][field] - 1) * 100
                    for time in common_times
                    if spot_by_time[time][field]
                ]
                field_stats[f"avg_{field}_abs_diff_pct"] = statistics.mean(diffs) if diffs else None
                field_stats[f"max_{field}_abs_diff_pct"] = max(diffs) if diffs else None
            rows.append(
                {
                    "symbol": v1.short(symbol),
                    "interval": interval,
                    "aligned_candles": len(common_times),
                    **field_stats,
                }
            )
    return rows


def leverage_distribution(trades: List[dict]) -> dict:
    leverages = [float(trade["actual_leverage"]) for trade in trades]
    return {
        "trades": len(leverages),
        "avg_leverage": statistics.mean(leverages) if leverages else None,
        "median_leverage": statistics.median(leverages) if leverages else None,
        "max_leverage": max(leverages) if leverages else None,
        "leverage_lte_1_count": sum(1 for value in leverages if value <= 1.0),
        "leverage_gte_2_count": sum(1 for value in leverages if value >= 2.0),
        "leverage_gte_3_count": sum(1 for value in leverages if value >= 3.0),
        "leverage_gte_4_count": sum(1 for value in leverages if value >= 4.0),
    }


def liquidation_summary(trades: List[dict], stress_summary: dict) -> dict:
    risk_trades = [trade for trade in trades if truthy(trade["liquidation_risk"])]
    low_1h = [trade for trade in trades if truthy(trade["liquidation_low_touched_1h"])]
    low_4h = [trade for trade in trades if truthy(trade["liquidation_low_touched_4h"])]
    stop_not_first = [trade for trade in trades if not truthy(trade["stop_before_liquidation"])]
    return {
        "trades": len(trades),
        "liquidation_risk_trades": len(risk_trades),
        "low_touched_1h_trades": len(low_1h),
        "low_touched_4h_trades": len(low_4h),
        "stop_not_before_liquidation_trades": len(stop_not_first),
        "stress_mdd_pct": stress_summary["mdd_pct"],
        "stress_calmar": stress_summary["calmar"],
    }


def apply_liquidation_counts(summary_rows: List[dict], name: str, trades: List[dict]) -> None:
    risk_count = sum(1 for trade in trades if truthy(trade["liquidation_risk"]))
    for row in summary_rows:
        if row["name"] == name:
            row["liquidation_risk_trades"] = risk_count


def pass_fail(
    summary_rows: List[dict],
    unique_audit: dict,
    funding_row_audit: dict,
    spot_futures_audit: dict,
    leverage_stats: dict,
    liquidation_stats: dict,
) -> List[dict]:
    lookup = {row["name"]: row for row in summary_rows}
    taker_funding = lookup.get("Taker only fee 0.05% + actual funding", {})
    slippage_02 = lookup.get("Slippage stress 0.20%", {})
    return [
        {
            "check": "Unique base trades == 1140",
            "result": "PASS" if unique_audit["matches_expected_1140"] else "FAIL",
            "evidence": f"rows {unique_audit['base_trade_rows']}, unique {unique_audit['base_unique_trades']}, duplicates {unique_audit['duplicate_trade_rows']}",
        },
        {
            "check": "Funding audit row expansion explained",
            "result": "PASS" if funding_row_audit.get("funding_rows_explained_by_scenarios") and funding_row_audit.get("alpha10_actual_unique_trades") == EXPECTED_BASE_UNIQUE_TRADES else "FAIL",
            "evidence": (
                f"funding rows {funding_row_audit.get('funding_trades_rows')}, variants {funding_row_audit.get('funding_variants')}, "
                f"scenarios {funding_row_audit.get('funding_scenarios')}, Alpha10 actual unique {funding_row_audit.get('alpha10_actual_unique_trades')}"
            ),
        },
        {
            "check": "Taker-only + funding Calmar >= 1.2",
            "result": "PASS" if (taker_funding.get("calmar") or 0.0) >= 1.2 else "FAIL",
            "evidence": f"Calmar {taker_funding.get('calmar', 0.0):.2f}",
        },
        {
            "check": "Slippage 0.2% Calmar >= 1.0",
            "result": "PASS" if (slippage_02.get("calmar") or 0.0) >= 1.0 else "FAIL",
            "evidence": f"Calmar {slippage_02.get('calmar', 0.0):.2f}",
        },
        {
            "check": "Liquidation risk trades == 0",
            "result": "PASS" if liquidation_stats["liquidation_risk_trades"] == 0 else "FAIL",
            "evidence": f"risk {liquidation_stats['liquidation_risk_trades']}, 1H low touches {liquidation_stats['low_touched_1h_trades']}, stop not first {liquidation_stats['stop_not_before_liquidation_trades']}",
        },
        {
            "check": "Spot/Futures OHLCV performance not materially changed",
            "result": "PASS" if spot_futures_audit["not_large_change"] else "FAIL",
            "evidence": (
                f"CAGR delta {spot_futures_audit['cagr_delta_pct']:.1f}%, "
                f"MDD delta {spot_futures_audit['mdd_delta_ppt']:.1f}pp, trade delta {spot_futures_audit['trade_delta_pct']:.1f}%"
            ),
        },
        {
            "check": "Liquidation stress MDD within -40%",
            "result": "PASS" if liquidation_stats["stress_mdd_pct"] >= -40 else "FAIL",
            "evidence": f"stress MDD {liquidation_stats['stress_mdd_pct']:.1f}%",
        },
    ]


def summary_from_run(run: AuditRun) -> dict:
    return performance_summary(
        run.name,
        run.group,
        run.market_data,
        run.config,
        run.result["equity_curve"],
        run.result["trades"],
        funding_included=run.funding_included,
        stop_fill_mode=run.stop_fill_mode,
    )


def performance_summary(
    name: str,
    group: str,
    market_data: str,
    config: alpha.AlphaConfig,
    equity_curve: List[dict],
    trades: List[dict],
    funding_included: bool,
    stop_fill_mode: str,
) -> dict:
    final_equity = equity_curve[-1]["equity"] if equity_curve else 1.0
    years = (alpha.TEST_END_TS - alpha.TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [
        equity_curve[index]["equity"] / equity_curve[index - 1]["equity"] - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1]["equity"] > 0
    ]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(equity_curve)
    pnl_key = "pnl_after_funding" if funding_included and trades and "pnl_after_funding" in trades[0] else "pnl"
    pnls = [float(trade[pnl_key]) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    leverages = [float(trade.get("actual_leverage", 0.0)) for trade in trades if trade.get("actual_leverage", "") != ""]
    unique = len({trade_key(trade) for trade in trades})
    return {
        "name": name,
        "group": group,
        "market_data": market_data,
        "fee_rate_pct": config.fee_rate * 100,
        "slippage_rate_pct": config.slippage_rate * 100,
        "configured_max_leverage": config.max_leverage,
        "funding_included": funding_included,
        "stop_fill_mode": stop_fill_mode,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trades": len(trades),
        "unique_trades": unique,
        "avg_leverage": statistics.mean(leverages) if leverages else None,
        "median_leverage": statistics.median(leverages) if leverages else None,
        "max_leverage_observed": max(leverages) if leverages else None,
        "liquidation_risk_trades": sum(1 for trade in trades if truthy(trade.get("liquidation_risk", False))),
    }


def ohlcv_table(rows: List[dict]) -> str:
    lines = [
        "| Symbol | Interval | Candles | Avg close diff | Max close diff | Avg high diff | Avg low diff |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['interval']} | {row['aligned_candles']} | "
            f"{pct(row['avg_close_abs_diff_pct'])} | {pct(row['max_close_abs_diff_pct'])} | "
            f"{pct(row['avg_high_abs_diff_pct'])} | {pct(row['avg_low_abs_diff_pct'])} |"
        )
    return "\n".join(lines)


def build_report(
    summary_rows: List[dict],
    trade_rows: List[dict],
    pass_fail_rows: List[dict],
    unique_audit: dict,
    funding_row_audit: dict,
    spot_futures_audit: dict,
    ohlcv_diff_rows: List[dict],
    leverage_stats: dict,
    liquidation_stats: dict,
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Alpha Engine v1 Futures Execution & Liquidation Audit 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 기존 Alpha Engine v1 및 funding audit 파일은 수정하지 않았다.",
        "- Futures OHLCV는 Binance USD-M `/fapi/v1/klines`에서 별도 캐시로 수집했다.",
        "- 청산가 추정은 isolated long, 설정 레버리지 3x, maintenance margin 0.5%, liquidation fee buffer 0.1% 가정이다.",
        "- 실제 레버리지는 `initial_notional / entry_equity`로 계산했다.",
        "- 청산 위험은 stop price가 liquidation price보다 낮거나 같거나, 보유 중 1H open이 liquidation price 이하로 갭다운한 경우로 정의했다.",
        "- Spot/Futures 성과 차이 PASS 기준은 CAGR 변화 20% 이내, MDD 변화 5%p 이내, 거래 수 변화 10% 이내다.",
        "- Funding audit의 40,260 trade rows는 8개 변형과 5개 funding 시나리오를 펼친 결과이며, 성과는 summary row별로 분리 계산했다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## Unique Trade Count 감사",
        "",
        unique_audit_table(unique_audit, funding_row_audit),
        "",
        "## Spot/Futures OHLCV 성과 비교",
        "",
        spot_futures_table(spot_futures_audit),
        "",
        "## Futures OHLCV 가격 차이",
        "",
        ohlcv_table(ohlcv_diff_rows),
        "",
        "## 수수료 현실성",
        "",
        summary_table([row for row in summary_rows if row["group"] in {"Fee model", "Fee stress", "Fee/Funding"}]),
        "",
        "## 슬리피지 스트레스",
        "",
        summary_table([row for row in summary_rows if row["group"] == "Slippage stress"]),
        "",
        "## 손절 체결 현실성",
        "",
        summary_table([row for row in summary_rows if row["name"] in {"Spot OHLCV base", "Conservative stop gap fill"}]),
        "",
        "## 전체 실행 감사 요약",
        "",
        summary_table(summary_rows),
        "",
        "## 레버리지 분포",
        "",
        leverage_table(leverage_stats),
        "",
        "## 청산 위험 감사",
        "",
        liquidation_table(liquidation_stats),
        "",
        "## Base Spot 청산 위험 거래",
        "",
        liquidation_risk_table([row for row in trade_rows if row["audit_variant"] == "Spot OHLCV base" and truthy(row["liquidation_risk"])]),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_futures_execution_audit_report.md`",
        "- `alpha_engine_v1_futures_execution_audit_summary.csv`",
        "- `alpha_engine_v1_futures_execution_audit_trades.csv`",
        "",
    ]
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def unique_audit_table(unique_audit: dict, funding_row_audit: dict) -> str:
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Base Alpha10 trade rows | {unique_audit['base_trade_rows']} |",
            f"| Base Alpha10 unique trades | {unique_audit['base_unique_trades']} |",
            f"| Base duplicate rows | {unique_audit['duplicate_trade_rows']} |",
            f"| Funding audit trade rows | {funding_row_audit.get('funding_trades_rows')} |",
            f"| Funding variants | {funding_row_audit.get('funding_variants')} |",
            f"| Funding scenarios | {funding_row_audit.get('funding_scenarios')} |",
            f"| Funding summary trade sum | {funding_row_audit.get('funding_summary_trade_sum')} |",
            f"| Funding Alpha10 actual unique trades | {funding_row_audit.get('alpha10_actual_unique_trades')} |",
            f"| Funding rows explained by variant/scenario summaries | {funding_row_audit.get('funding_rows_explained_by_scenarios')} |",
        ]
    )


def spot_futures_table(row: dict) -> str:
    return "\n".join(
        [
            "| Metric | Spot | Futures | Delta |",
            "|---|---:|---:|---:|",
            f"| Trades | {row['spot_trades']} | {row['futures_trades']} | {pct(row['trade_delta_pct'])} |",
            f"| CAGR | {pct(row['spot_cagr_pct'])} | {pct(row['futures_cagr_pct'])} | {pct(row['cagr_delta_pct'])} |",
            f"| MDD | {pct(row['spot_mdd_pct'])} | {pct(row['futures_mdd_pct'])} | {pct(row['mdd_delta_ppt'])}p |",
            f"| Calmar | {num(row['spot_calmar'])} | {num(row['futures_calmar'])} |  |",
            f"| Common unique trades | {row['common_trades']} |  |  |",
            f"| Spot-only unique trades | {row['spot_only_trades']} |  |  |",
            f"| Futures-only unique trades | {row['futures_only_trades']} |  |  |",
        ]
    )


def summary_table(rows: List[dict]) -> str:
    headers = ["Name", "Group", "Market", "Fee", "Slip", "Funding", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "PF", "Trades", "Unique", "Avg lev", "Max lev", "Liq risk"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["name"],
            row["group"],
            row["market_data"],
            pct_cost(row["fee_rate_pct"]),
            pct_cost(row["slippage_rate_pct"]),
            str(row["funding_included"]),
            pct(row["total_return_pct"]),
            pct(row["cagr_pct"]),
            pct(row["mdd_pct"]),
            num(row["sharpe"]),
            num(row["calmar"]),
            num(row["profit_factor"]),
            str(row["trades"]),
            str(row["unique_trades"]),
            num(row["avg_leverage"]),
            num(row["max_leverage_observed"]),
            str(row["liquidation_risk_trades"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def leverage_table(row: dict) -> str:
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Trades | {row['trades']} |",
            f"| Average leverage | {num(row['avg_leverage'])} |",
            f"| Median leverage | {num(row['median_leverage'])} |",
            f"| Max leverage | {num(row['max_leverage'])} |",
            f"| <= 1x trades | {row['leverage_lte_1_count']} |",
            f"| >= 2x trades | {row['leverage_gte_2_count']} |",
            f"| >= 3x trades | {row['leverage_gte_3_count']} |",
            f"| >= 4x trades | {row['leverage_gte_4_count']} |",
        ]
    )


def liquidation_table(row: dict) -> str:
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Trades | {row['trades']} |",
            f"| Liquidation risk trades | {row['liquidation_risk_trades']} |",
            f"| 1H low touched liquidation price | {row['low_touched_1h_trades']} |",
            f"| 4H low touched liquidation price | {row['low_touched_4h_trades']} |",
            f"| Stop not before liquidation | {row['stop_not_before_liquidation_trades']} |",
            f"| Liquidation stress MDD | {pct(row['stress_mdd_pct'])} |",
            f"| Liquidation stress Calmar | {num(row['stress_calmar'])} |",
        ]
    )


def liquidation_risk_table(rows: List[dict]) -> str:
    if not rows:
        return "청산 위험 거래 없음."
    lines = [
        "| Symbol | Entry | Exit | Entry | Stop | Liq | Min 1H low | PnL | Stress PnL |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:20]:
        lines.append(
            f"| {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {num(row['entry_price'])} | "
            f"{num(row['stop_price'])} | {num(row['liquidation_price_est'])} | {num(row['min_1h_low_during_hold'])} | "
            f"{num(row['pnl'])} | {num(row['liquidation_stress_pnl'])} |"
        )
    return "\n".join(lines)


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def pct_delta(value: Optional[float], base: Optional[float]) -> Optional[float]:
    if value is None or base in {None, 0}:
        return None
    return (float(value) - float(base)) / abs(float(base)) * 100


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def pct_cost(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return f"{text}%"


def num(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.4f}"


if __name__ == "__main__":
    main()
