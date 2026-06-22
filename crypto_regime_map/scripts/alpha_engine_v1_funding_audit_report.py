"""Futures funding audit for Alpha Engine v1.

This script does not modify Alpha Engine v1. It re-runs selected Alpha Engine
variants with extra trade metadata, downloads Binance USD-M funding history,
and overlays funding cashflows on top of the spot-OHLCV backtest.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from collections import defaultdict
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

import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_report as v1  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


FAPI_BASE_URLS = ("https://fapi.binance.com",)
FUNDING_START = "2020-01-01T00:00:00+00:00"
FUNDING_END = "2026-01-01T00:00:00+00:00"
START_TS = int(datetime.fromisoformat(FUNDING_START).timestamp())
END_TS = int(datetime.fromisoformat(FUNDING_END).timestamp())
SYMBOLS = alpha.UNIVERSE_10
SCENARIOS = [
    ("funding_zero", "funding 0", None),
    ("actual_funding", "실제 funding", "actual"),
    ("annual_cost_5", "보수적 funding 비용 연 -5%", 0.05),
    ("annual_cost_10", "보수적 funding 비용 연 -10%", 0.10),
    ("annual_cost_20", "보수적 funding 비용 연 -20%", 0.20),
]


@dataclass(frozen=True)
class AuditRun:
    config: alpha.AlphaConfig
    result: dict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw/funding JSON if available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    install_alpha_trade_metadata_patch()

    raw_1d = alpha.load_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)

    funding_info = load_funding_info(args.use_cache)
    funding_by_symbol = {
        symbol: load_funding_history(symbol, args.use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }
    funding_event_rows = flatten_funding_events(funding_by_symbol, funding_info)

    configs = [
        alpha.AlphaConfig("Alpha Engine v1 / 4 symbols", tuple(alpha.UNIVERSE_4)),
        alpha.AlphaConfig("Alpha Engine v1 / 10 symbols", tuple(alpha.UNIVERSE_10)),
        alpha.AlphaConfig("Alpha Engine v1 / 4 symbols / 2x", tuple(alpha.UNIVERSE_4), max_leverage=2.0, group="Leverage sensitivity"),
        alpha.AlphaConfig("Alpha Engine v1 / 4 symbols / 3x", tuple(alpha.UNIVERSE_4), max_leverage=3.0, group="Leverage sensitivity"),
        alpha.AlphaConfig("Alpha Engine v1 / 4 symbols / 4x", tuple(alpha.UNIVERSE_4), max_leverage=4.0, group="Leverage sensitivity"),
        alpha.AlphaConfig("Alpha Engine v1 / 10 symbols / 2x", tuple(alpha.UNIVERSE_10), max_leverage=2.0, group="Leverage sensitivity"),
        alpha.AlphaConfig("Alpha Engine v1 / 10 symbols / 3x", tuple(alpha.UNIVERSE_10), max_leverage=3.0, group="Leverage sensitivity"),
        alpha.AlphaConfig("Alpha Engine v1 / 10 symbols / 4x", tuple(alpha.UNIVERSE_10), max_leverage=4.0, group="Leverage sensitivity"),
    ]
    runs = [AuditRun(config, alpha.run_alpha_engine(data, config)) for config in configs]

    summary_rows: List[dict] = []
    trade_rows: List[dict] = []
    cashflow_by_run_scenario: Dict[Tuple[str, str], List[dict]] = {}
    for run in runs:
        for scenario_key, scenario_name, scenario_value in SCENARIOS:
            annotated, cashflows = annotate_trades(run.result["trades"], funding_by_symbol, scenario_key, scenario_name, scenario_value)
            cashflow_by_run_scenario[(run.config.name, scenario_key)] = cashflows
            summary_rows.append(summary_row(run, annotated, cashflows, scenario_key, scenario_name))
            trade_rows.extend(annotated)

    pass_fail_rows = pass_fail(summary_rows, trade_rows)
    report = build_report(summary_rows, trade_rows, funding_event_rows, pass_fail_rows)

    report_path = output_dir / "alpha_engine_v1_funding_audit_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_engine_v1_funding_audit_summary.csv", summary_rows)
    write_csv(output_dir / "alpha_engine_v1_funding_audit_trades.csv", trade_rows)
    write_csv(output_dir / "alpha_engine_v1_funding_events.csv", funding_event_rows)
    print(report_path)


def install_alpha_trade_metadata_patch() -> None:
    def patched_manage_position(data, config, position, row, open_time, close_time, index_1h, cash):
        if row["low"] <= position.stop_price:
            trade = patched_close_trade(data, config, position, position.stop_price, close_time, index_1h, "stop")
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


def patched_close_trade(data, config, position, exit_price, exit_time, index_1h, reason) -> dict:
    gross_pnl = position.units * (exit_price - position.entry_price)
    fee = position.units * exit_price * config.fee_rate
    total_pnl = position.realized_pnl + gross_pnl - fee
    quality = alpha.entry_quality(data, position.symbol, position.entry_time, position.entry_price)
    excursion = alpha.trade_excursion(data, position.symbol, position.entry_time, exit_time, position.entry_price)
    partial_time = getattr(position, "partial_time", "")
    return {
        "variant": config.name,
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
        "initial_notional": position.initial_units * position.entry_price,
        "partial_taken": position.partial_taken,
        "partial_time": partial_time,
        "partial_date": alpha.format_dt(partial_time) if partial_time else "",
        "partial_price": getattr(position, "partial_price", ""),
        "max_leverage": config.max_leverage,
        "_cash_delta": total_pnl,
    }


def load_funding_info(use_cache: bool) -> Dict[str, dict]:
    path = ROOT / "data" / "raw" / "futures_funding_info.json"
    if use_cache and path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            return {row.get("symbol"): row for row in rows if row.get("symbol")}
        except json.JSONDecodeError:
            pass
    try:
        rows = request_json("/fapi/v1/fundingInfo", {})
    except RuntimeError:
        rows = []
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return {row.get("symbol"): row for row in rows if row.get("symbol")}


def load_funding_history(symbol: str, use_cache: bool, interval_hours: Optional[float]) -> List[dict]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{symbol}_futures_funding_rate.json"
    if use_cache and path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            if rows and int(rows[0]["fundingTime"]) <= START_TS * 1000 and int(rows[-1]["fundingTime"]) >= (END_TS - 8 * 3600) * 1000:
                return normalize_funding_rows(symbol, rows, interval_hours)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    rows: List[dict] = []
    cursor_ms = START_TS * 1000
    end_ms = END_TS * 1000
    while cursor_ms < end_ms:
        batch = request_json(
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "startTime": cursor_ms, "endTime": end_ms, "limit": 1000},
        )
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1]["fundingTime"]) + 1
        if next_cursor <= cursor_ms:
            break
        cursor_ms = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.08)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return normalize_funding_rows(symbol, rows, interval_hours)


def request_json(path: str, params: dict) -> list:
    query = urlencode(params)
    last_error: Optional[Exception] = None
    for base in FAPI_BASE_URLS:
        url = f"{base}{path}" + (f"?{query}" if query else "")
        request = Request(url, headers={"User-Agent": "crypto-regime-map/0.1"})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
    raise RuntimeError(f"Funding request failed for {path}: {last_error}") from last_error


def normalize_funding_rows(symbol: str, rows: List[dict], interval_hours: Optional[float]) -> List[dict]:
    out = []
    sorted_rows = sorted(rows, key=lambda row: int(row["fundingTime"]))
    for index, row in enumerate(sorted_rows):
        funding_time = int(row["fundingTime"]) // 1000
        if funding_time < START_TS or funding_time >= END_TS:
            continue
        inferred_hours = interval_hours
        if inferred_hours is None and index > 0:
            inferred_hours = (int(row["fundingTime"]) - int(sorted_rows[index - 1]["fundingTime"])) / 3600000
        if inferred_hours is None:
            inferred_hours = 8.0
        out.append(
            {
                "symbol": symbol,
                "funding_time": funding_time,
                "funding_date": alpha.format_dt(funding_time),
                "funding_rate": float(row.get("fundingRate", 0.0)),
                "mark_price": float(row.get("markPrice") or 0.0),
                "funding_interval_hours": float(inferred_hours),
            }
        )
    return out


def flatten_funding_events(funding_by_symbol: Dict[str, List[dict]], funding_info: Dict[str, dict]) -> List[dict]:
    rows = []
    for symbol, events in funding_by_symbol.items():
        info = funding_info.get(symbol, {})
        for event in events:
            rows.append(
                {
                    **event,
                    "funding_interval_hours_info": info.get("fundingIntervalHours", ""),
                    "adjusted_funding_rate_cap": info.get("adjustedFundingRateCap", ""),
                    "adjusted_funding_rate_floor": info.get("adjustedFundingRateFloor", ""),
                }
            )
    return sorted(rows, key=lambda row: (row["symbol"], row["funding_time"]))


def annotate_trades(
    trades: List[dict],
    funding_by_symbol: Dict[str, List[dict]],
    scenario_key: str,
    scenario_name: str,
    scenario_value,
) -> Tuple[List[dict], List[dict]]:
    annotated = []
    cashflows = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        funding_pnl = 0.0
        funding_abs_cost = 0.0
        funding_event_count = 0
        for event in funding_by_symbol.get(symbol, []):
            if not (int(trade["entry_timestamp"]) <= event["funding_time"] < int(trade["exit_timestamp"])):
                continue
            units = float(trade["initial_units"])
            partial_time = trade.get("partial_time")
            if partial_time not in {"", None} and event["funding_time"] >= int(partial_time):
                units *= 0.5
            mark_price = event["mark_price"] or float(trade["entry_price"])
            notional = units * mark_price
            rate = scenario_rate(event, scenario_value)
            pnl = -notional * rate
            funding_pnl += pnl
            funding_abs_cost += max(-pnl, 0.0)
            funding_event_count += 1
            cashflows.append(
                {
                    "variant": trade["variant"],
                    "scenario": scenario_key,
                    "trade_index": index,
                    "symbol": trade["symbol"],
                    "funding_time": event["funding_time"],
                    "funding_date": event["funding_date"],
                    "funding_rate_used": rate,
                    "actual_funding_rate": event["funding_rate"],
                    "mark_price": mark_price,
                    "notional": notional,
                    "funding_pnl": pnl,
                }
            )
        pnl_after = float(trade["pnl"]) + funding_pnl
        entry_equity = float(trade["entry_equity"]) if trade["entry_equity"] else 1.0
        annotated.append(
            {
                **{key: value for key, value in trade.items() if not key.startswith("_")},
                "scenario": scenario_key,
                "scenario_name": scenario_name,
                "funding_event_count": funding_event_count,
                "funding_pnl": funding_pnl,
                "funding_abs_cost": funding_abs_cost,
                "pnl_after_funding": pnl_after,
                "trade_return_after_funding_pct": pnl_after / entry_equity * 100 if entry_equity else 0.0,
                "pnl_sign_changed_by_funding": sign(float(trade["pnl"])) != sign(pnl_after),
            }
        )
    return annotated, cashflows


def scenario_rate(event: dict, scenario_value) -> float:
    if scenario_value is None:
        return 0.0
    if scenario_value == "actual":
        return event["funding_rate"]
    return float(scenario_value) * event["funding_interval_hours"] / (365 * 24)


def summary_row(run: AuditRun, trades: List[dict], cashflows: List[dict], scenario_key: str, scenario_name: str) -> dict:
    base = run.result["summary"]
    adjusted_curve = adjusted_equity_curve(run.result["equity_curve"], cashflows)
    final_equity = adjusted_curve[-1]["equity"] if adjusted_curve else 1.0
    years = (alpha.TEST_END_TS - alpha.TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [adjusted_curve[index]["equity"] / adjusted_curve[index - 1]["equity"] - 1 for index in range(1, len(adjusted_curve)) if adjusted_curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(adjusted_curve)
    adjusted_returns = [row["trade_return_after_funding_pct"] for row in trades]
    adjusted_pnls = [row["pnl_after_funding"] for row in trades]
    wins = [value for value in adjusted_pnls if value > 0]
    losses = [value for value in adjusted_pnls if value < 0]
    funding_total = sum(row["funding_pnl"] for row in trades)
    funding_cost = sum(row["funding_abs_cost"] for row in trades)
    total_profit = final_equity - 1
    return {
        "variant": run.config.name,
        "universe_size": len(run.config.universe),
        "max_leverage": run.config.max_leverage,
        "scenario": scenario_key,
        "scenario_name": scenario_name,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trades": len(trades),
        "base_total_return_pct": base["total_return_pct"],
        "base_cagr_pct": base["cagr_pct"],
        "base_mdd_pct": base["mdd_pct"],
        "base_calmar": base["calmar"],
        "cagr_delta_pct_point": (cagr * 100 - base["cagr_pct"]) if cagr is not None else None,
        "cagr_decrease_pct": ((base["cagr_pct"] - cagr * 100) / base["cagr_pct"] * 100) if cagr is not None and base["cagr_pct"] else None,
        "funding_total_pnl": funding_total,
        "funding_total_cost": funding_cost,
        "avg_trade_funding_pnl": funding_total / len(trades) if trades else 0.0,
        "funding_cost_to_total_pnl_pct": funding_cost / total_profit * 100 if total_profit > 0 else None,
        "pnl_sign_changed_trades": sum(1 for row in trades if row["pnl_sign_changed_by_funding"]),
    }


def adjusted_equity_curve(curve: List[dict], cashflows: List[dict]) -> List[dict]:
    events = sorted(cashflows, key=lambda row: row["funding_time"])
    out = []
    cumulative = 0.0
    index = 0
    for point in curve:
        while index < len(events) and events[index]["funding_time"] <= point["time"]:
            cumulative += events[index]["funding_pnl"]
            index += 1
        out.append({"time": point["time"], "date": point.get("date", alpha.format_dt(point["time"])), "equity": max(1e-9, point["equity"] + cumulative)})
    return out


def pass_fail(summary_rows: List[dict], trade_rows: List[dict]) -> List[dict]:
    lookup = {(row["variant"], row["scenario"]): row for row in summary_rows}
    alpha10_actual = lookup.get(("Alpha Engine v1 / 10 symbols", "actual_funding"), {})
    alpha10_zero = lookup.get(("Alpha Engine v1 / 10 symbols", "funding_zero"), {})
    alpha10_minus10 = lookup.get(("Alpha Engine v1 / 10 symbols", "annual_cost_10"), {})
    actual_trades = [row for row in trade_rows if row["variant"] == "Alpha Engine v1 / 10 symbols" and row["scenario"] == "actual_funding"]
    symbol_costs = defaultdict(float)
    for row in actual_trades:
        symbol_costs[row["symbol"]] += row["funding_abs_cost"]
    total_cost = sum(symbol_costs.values())
    largest_symbol = max(symbol_costs, key=symbol_costs.get) if symbol_costs else ""
    largest_share = symbol_costs[largest_symbol] / total_cost * 100 if total_cost else 0.0
    cagr_decrease = alpha10_actual.get("cagr_decrease_pct", 0.0) or 0.0
    cost_ratio = alpha10_actual.get("funding_cost_to_total_pnl_pct", 0.0) or 0.0
    return [
        {
            "check": "Actual funding Calmar >= 1.2",
            "result": "PASS" if (alpha10_actual.get("calmar") or 0.0) >= 1.2 else "FAIL",
            "evidence": f"Actual funding Calmar {alpha10_actual.get('calmar', 0.0):.2f}",
        },
        {
            "check": "CAGR decrease <= 20%",
            "result": "PASS" if cagr_decrease <= 20 else "FAIL",
            "evidence": f"Base CAGR {alpha10_zero.get('cagr_pct', 0.0):.1f}%, actual funding CAGR {alpha10_actual.get('cagr_pct', 0.0):.1f}%, decrease {cagr_decrease:.1f}%",
        },
        {
            "check": "Funding cost / total PnL <= 15%",
            "result": "PASS" if cost_ratio <= 15 else "FAIL",
            "evidence": f"Funding cost / total PnL {cost_ratio:.1f}%",
        },
        {
            "check": "Annual -10% funding MDD within -40%",
            "result": "PASS" if (alpha10_minus10.get("mdd_pct") or -999) >= -40 else "FAIL",
            "evidence": f"Annual -10% scenario MDD {alpha10_minus10.get('mdd_pct', 0.0):.1f}%",
        },
        {
            "check": "Symbol funding concentration",
            "result": "WARNING" if largest_share >= 50 else "PASS",
            "evidence": f"{largest_symbol or 'N/A'} funding cost share {largest_share:.1f}%",
        },
    ]


def build_report(summary_rows: List[dict], trade_rows: List[dict], funding_events: List[dict], pass_fail_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alpha10_rows = [row for row in summary_rows if row["variant"] == "Alpha Engine v1 / 10 symbols"]
    actual_alpha10_trades = [row for row in trade_rows if row["variant"] == "Alpha Engine v1 / 10 symbols" and row["scenario"] == "actual_funding"]
    lines = [
        "# Alpha Engine v1 Futures Funding Audit 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- Funding 데이터: Binance USD-M Futures `/fapi/v1/fundingRate`",
        "- Funding event 포함 조건: `entry_time <= funding_time < exit_time`",
        "- Long 기준 funding_rate > 0은 비용, funding_rate < 0은 수익으로 계산했다.",
        "- 부분익절 이후 funding event는 최초 수량의 50% 잔여 명목금액으로 계산했다.",
        "- 성과 조정은 기존 Alpha Engine v1 spot backtest equity curve에 funding cashflow를 overlay한 감사 계산이다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## Alpha10 Funding 시나리오 비교",
        "",
        summary_table(alpha10_rows),
        "",
        "## 전체 Funding 감사 요약",
        "",
        summary_table(summary_rows),
        "",
        "## 심볼별 Funding 비용",
        "",
        funding_group_table(group_funding(actual_alpha10_trades, "symbol"), "symbol"),
        "",
        "## 연도별 Funding 비용",
        "",
        funding_group_table(group_funding_by_year(actual_alpha10_trades), "year"),
        "",
        "## 레짐별 Funding 비용",
        "",
        funding_group_table(group_funding(actual_alpha10_trades, "trade_regime"), "trade_regime"),
        "",
        "## Action Bias별 Funding 비용",
        "",
        funding_group_table(group_funding(actual_alpha10_trades, "trade_action_bias"), "trade_action_bias"),
        "",
        "## Funding 비용 상위 거래 Top 20",
        "",
        trade_funding_table(sorted(actual_alpha10_trades, key=lambda row: row["funding_pnl"])[:20]),
        "",
        "## Funding 수익 상위 거래 Top 20",
        "",
        trade_funding_table(sorted(actual_alpha10_trades, key=lambda row: row["funding_pnl"], reverse=True)[:20]),
        "",
        "## Funding 데이터 커버리지",
        "",
        funding_coverage_table(funding_events),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_funding_audit_report.md`",
        "- `alpha_engine_v1_funding_audit_summary.csv`",
        "- `alpha_engine_v1_funding_audit_trades.csv`",
        "- `alpha_engine_v1_funding_events.csv`",
        "",
    ]
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Variant", "Scenario", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "PF", "Funding PnL", "Funding cost", "Avg/trade", "Cost/PnL", "Sign flips"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["variant"],
            row["scenario_name"],
            pct(row["total_return_pct"]),
            pct(row["cagr_pct"]),
            pct(row["mdd_pct"]),
            num(row["sharpe"]),
            num(row["calmar"]),
            num(row["profit_factor"]),
            num(row["funding_total_pnl"]),
            num(row["funding_total_cost"]),
            num(row["avg_trade_funding_pnl"]),
            pct(row["funding_cost_to_total_pnl_pct"]),
            str(row["pnl_sign_changed_trades"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def group_funding(rows: List[dict], key: str) -> List[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key, ""))].append(row)
    out = []
    for value, items in grouped.items():
        out.append(
            {
                key: value,
                "trades": len(items),
                "funding_pnl": sum(item["funding_pnl"] for item in items),
                "funding_cost": sum(item["funding_abs_cost"] for item in items),
                "avg_trade_funding": statistics.mean([item["funding_pnl"] for item in items]) if items else 0.0,
            }
        )
    return sorted(out, key=lambda row: row["funding_cost"], reverse=True)


def group_funding_by_year(rows: List[dict]) -> List[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["entry_date"][:4]].append(row)
    out = []
    for year, items in grouped.items():
        out.append(
            {
                "year": year,
                "trades": len(items),
                "funding_pnl": sum(item["funding_pnl"] for item in items),
                "funding_cost": sum(item["funding_abs_cost"] for item in items),
                "avg_trade_funding": statistics.mean([item["funding_pnl"] for item in items]) if items else 0.0,
            }
        )
    return sorted(out, key=lambda row: row["year"])


def funding_group_table(rows: List[dict], key: str) -> str:
    lines = [f"| {key} | Trades | Funding PnL | Funding cost | Avg/trade |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row[key]} | {row['trades']} | {num(row['funding_pnl'])} | {num(row['funding_cost'])} | {num(row['avg_trade_funding'])} |")
    return "\n".join(lines)


def trade_funding_table(rows: List[dict]) -> str:
    lines = ["| Symbol | Entry | Exit | Regime | PnL before | Funding PnL | PnL after | Events |", "|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['trade_regime']} | "
            f"{num(row['pnl'])} | {num(row['funding_pnl'])} | {num(row['pnl_after_funding'])} | {row['funding_event_count']} |"
        )
    return "\n".join(lines)


def funding_coverage_table(rows: List[dict]) -> str:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["symbol"]].append(row)
    lines = ["| Symbol | Events | First | Last | Avg rate |", "|---|---:|---|---|---:|"]
    for symbol in SYMBOLS:
        items = grouped.get(symbol, [])
        lines.append(
            f"| {v1.short(symbol)} | {len(items)} | {items[0]['funding_date'] if items else ''} | "
            f"{items[-1]['funding_date'] if items else ''} | {pct(statistics.mean([item['funding_rate'] for item in items]) * 100 if items else None)} |"
        )
    return "\n".join(lines)


def sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def num(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.4f}"


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
