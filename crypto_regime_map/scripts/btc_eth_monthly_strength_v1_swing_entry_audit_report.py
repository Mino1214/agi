"""Swing-entry audit report for BTC/ETH Monthly Strength v1.

The monthly v1 rules are not modified. This script audits the 4H swing-entry
execution layer from the existing swing comparison report, then writes a
separate markdown report and CSV artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import btc_eth_monthly_strength_v1_report as v1  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


MONTHS = v1.month_range("2020-01", "2025-12")
METHOD_NAMES = {
    "immediate": "즉시 진입",
    "ema20_pullback": "EMA20 눌림 진입",
    "ema50_pullback": "EMA50 눌림 진입",
    "split_entry": "분할 진입",
}
TARGET_METHOD_KEYS = ["ema20_pullback", "ema50_pullback", "immediate", "split_entry"]
REENTRY_METHOD_KEYS = ["ema20_pullback", "ema50_pullback"]
RETURN_DAMAGE_FLOOR = 0.80


@dataclass(frozen=True)
class AuditConfig:
    key: str
    name: str
    method_key: str
    fill_mode: str = "next_open"
    cooldown_hours: int = 0
    monthly_candidate_limit: Optional[int] = None
    group: str = "Audit"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON if available and complete.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = load_raw_with_warmup(swing.SYMBOLS, "1d", args.use_cache)
    raw_4h = load_raw_with_warmup(swing.SYMBOLS, "4h", args.use_cache)
    data = swing.SwingData(raw_1d, raw_4h)

    raw_v1 = {symbol: raw_1d[symbol] for symbol in v1.SYMBOLS}
    payload = v1.build_payload_from_raw(raw_v1, interval="1d", start=v1.FETCH_START, symbols=v1.SYMBOLS)
    v1_data = v1.BacktestData(raw=raw_v1, payload=payload)
    monthly_v1 = v1.run_strength_strategy(v1_data, v1.base_config())

    result_cache: Dict[AuditConfig, dict] = {}

    def result(config: AuditConfig) -> dict:
        if config not in result_cache:
            result_cache[config] = run_audit_method(data, config)
        return result_cache[config]

    target_configs = [
        AuditConfig(key=key, name=METHOD_NAMES[key], method_key=key)
        for key in TARGET_METHOD_KEYS
    ]
    timing_configs = target_configs + [
        AuditConfig(
            key=f"{key}_next_close",
            name=METHOD_NAMES[key],
            method_key=key,
            fill_mode="next_close",
            group="Timing",
        )
        for key in TARGET_METHOD_KEYS
    ]
    reentry_configs = [
        config
        for method_key in REENTRY_METHOD_KEYS
        for config in [
            AuditConfig(
                key=f"{method_key}_none",
                name=f"{METHOD_NAMES[method_key]} / 제한 없음",
                method_key=method_key,
                group="Reentry",
            ),
            AuditConfig(
                key=f"{method_key}_cooldown_24h",
                name=f"{METHOD_NAMES[method_key]} / 24h 쿨다운",
                method_key=method_key,
                cooldown_hours=24,
                group="Reentry",
            ),
            AuditConfig(
                key=f"{method_key}_cooldown_48h",
                name=f"{METHOD_NAMES[method_key]} / 48h 쿨다운",
                method_key=method_key,
                cooldown_hours=48,
                group="Reentry",
            ),
            AuditConfig(
                key=f"{method_key}_month_max_1",
                name=f"{METHOD_NAMES[method_key]} / 월 후보당 최대 1회",
                method_key=method_key,
                monthly_candidate_limit=1,
                group="Reentry",
            ),
            AuditConfig(
                key=f"{method_key}_month_max_2",
                name=f"{METHOD_NAMES[method_key]} / 월 후보당 최대 2회",
                method_key=method_key,
                monthly_candidate_limit=2,
                group="Reentry",
            ),
        ]
    ]
    final_configs = [
        AuditConfig("ema20_base", "EMA20 눌림", "ema20_pullback", group="Final"),
        AuditConfig("ema50_base", "EMA50 눌림", "ema50_pullback", group="Final"),
        AuditConfig("ema20_cooldown_48h", "EMA20 눌림 + 48시간 쿨다운", "ema20_pullback", cooldown_hours=48, group="Final"),
        AuditConfig("ema50_cooldown_48h", "EMA50 눌림 + 48시간 쿨다운", "ema50_pullback", cooldown_hours=48, group="Final"),
        AuditConfig("ema20_month_max_1", "EMA20 눌림 + 월 후보당 최대 1회", "ema20_pullback", monthly_candidate_limit=1, group="Final"),
        AuditConfig("ema50_month_max_1", "EMA50 눌림 + 월 후보당 최대 1회", "ema50_pullback", monthly_candidate_limit=1, group="Final"),
    ]

    target_results = [result(config) for config in target_configs]
    timing_results = [result(config) for config in timing_configs]
    reentry_results = [result(config) for config in reentry_configs]
    final_results = [result(config) for config in final_configs]

    state_rows = state_machine_rows(target_results)
    timing_rows = timing_audit_rows(timing_results)
    entry_quality_rows = entry_quality_rows_for(target_results)
    trade_quality_rows = trade_quality_rows_for(target_results)
    reentry_rows = reentry_test_rows(reentry_results)
    final_rows = final_comparison_rows(monthly_v1, final_results)
    monthly_rows = monthly_return_rows(monthly_v1, final_results)
    yearly_rows = yearly_return_rows(monthly_v1, final_results)
    target_trades = [trade for item in target_results for trade in item["trades"]]
    verdict_rows = verdicts(monthly_v1, state_rows, final_rows, reentry_rows)

    report = build_report(
        data=data,
        monthly_v1=monthly_v1,
        state_rows=state_rows,
        timing_rows=timing_rows,
        entry_quality_rows=entry_quality_rows,
        trade_quality_rows=trade_quality_rows,
        reentry_rows=reentry_rows,
        final_rows=final_rows,
        monthly_rows=monthly_rows,
        yearly_rows=yearly_rows,
        verdict_rows=verdict_rows,
        target_trades=target_trades,
    )

    report_path = output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_state_machine.csv", state_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_timing.csv", timing_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_entry_quality.csv", entry_quality_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_trade_quality.csv", trade_quality_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_reentry_tests.csv", reentry_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_final_comparison.csv", final_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_monthly_returns.csv", monthly_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_yearly_returns.csv", yearly_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_trades.csv", target_trades)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_audit_verdicts.csv", verdict_rows)
    print(report_path)


def load_raw_with_warmup(symbols: Iterable[str], interval: str, use_cache: bool) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    out = {}
    for symbol in symbols:
        cached = v1.read_cache(raw_dir / f"{symbol}_{interval}.json") if use_cache else []
        if cached and covers_warmup_window(cached):
            out[symbol] = cached
        else:
            out[symbol] = v1.fetch_ohlcv(symbol, interval, swing.FETCH_START, swing.FETCH_END)
    return out


def covers_warmup_window(candles: List[dict]) -> bool:
    if not candles:
        return False
    start_ts = int(datetime.fromisoformat(swing.FETCH_START).timestamp())
    end_ts = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
    return candles[0]["time"] <= start_ts and candles[-1]["time"] >= end_ts


def run_audit_method(data: swing.SwingData, config: AuditConfig) -> dict:
    cash = 1.0
    units = 0.0
    symbol: Optional[str] = None
    avg_entry_price = 0.0
    entry_equity = 1.0
    entry_time = 0
    entry_index = 0
    entry_atr = 0.0
    entry_parts: List[dict] = []
    pending: Optional[dict] = None
    waiting: Dict[str, object] = {}
    split_state = {"ema20_added": False, "breakout_added": False}
    trades: List[dict] = []
    equity_curve = [{"time": swing.TEST_START_TS, "date": format_dt(swing.TEST_START_TS), "equity": 1.0}]
    last_exit_by_symbol: Dict[str, int] = {}
    monthly_candidate_entries: Counter[Tuple[str, str]] = Counter()

    for index, bar in enumerate(data.bars):
        if pending and pending["index"] == index and pending["fill_mode"] == "next_open":
            cash, units, symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr = execute_entry(
                bar=bar,
                index=index,
                order=pending,
                cash=cash,
                units=units,
                symbol=symbol,
                avg_entry_price=avg_entry_price,
                entry_equity=entry_equity,
                entry_time=entry_time,
                entry_index=entry_index,
                entry_atr=entry_atr,
                entry_parts=entry_parts,
                price_key="open",
                fill_time=bar["time"],
                monthly_candidate_entries=monthly_candidate_entries,
            )
            pending = None

        equity = swing.mark_equity(cash, units, symbol, bar, use_close=True)
        exited = False
        if symbol:
            exit_reason = swing.exit_reason_for(bar, symbol, avg_entry_price, entry_atr, entry_time)
            if exit_reason:
                cash, trade = execute_exit(data, config, bar, index, cash, units, symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_parts, exit_reason)
                trades.append(trade)
                last_exit_by_symbol[symbol] = bar["close_time"]
                units = 0.0
                symbol = None
                avg_entry_price = 0.0
                entry_parts = []
                split_state = {"ema20_added": False, "breakout_added": False}
                waiting = {}
                exited = True
                equity = cash

        if pending and pending["index"] == index and pending["fill_mode"] == "next_close":
            if not exited:
                cash, units, symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr = execute_entry(
                    bar=bar,
                    index=index,
                    order=pending,
                    cash=cash,
                    units=units,
                    symbol=symbol,
                    avg_entry_price=avg_entry_price,
                    entry_equity=entry_equity,
                    entry_time=entry_time,
                    entry_index=entry_index,
                    entry_atr=entry_atr,
                    entry_parts=entry_parts,
                    price_key="close",
                    fill_time=bar["close_time"],
                    monthly_candidate_entries=monthly_candidate_entries,
                )
                equity = swing.mark_equity(cash, units, symbol, bar, use_close=True)
            pending = None

        equity_curve.append({"time": bar["close_time"], "date": format_dt(bar["close_time"]), "equity": equity})
        if index + 1 >= len(data.bars):
            continue

        if symbol and config.method_key == "split_entry" and not exited and pending is None:
            add_order = swing.split_add_order(data, index, bar, symbol, split_state)
            if add_order:
                pending = tag_order(data, config, index, bar, add_order)
                if add_order["part"] == "ema20_recovery":
                    split_state["ema20_added"] = True
                if add_order["part"] == "breakout":
                    split_state["breakout_added"] = True
            continue

        if symbol or exited or pending is not None:
            continue

        candidate = swing.candidate_if_tradeable(bar)
        if not candidate:
            waiting = {}
            continue

        order, waiting = swing.entry_order_for_method(data, swing.Method(config.method_key, METHOD_NAMES[config.method_key]), index, bar, candidate, waiting)
        if order and entry_limit_allows(data, config, order, last_exit_by_symbol, monthly_candidate_entries):
            pending = tag_order(data, config, index, bar, order)

    if symbol:
        last_index = len(data.bars) - 1
        last_bar = data.bars[last_index]
        cash, trade = execute_exit(data, config, last_bar, last_index, cash, units, symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_parts, "end_of_test")
        trades.append(trade)
        equity_curve.append({"time": last_bar["close_time"], "date": format_dt(last_bar["close_time"]), "equity": cash})

    summary = summary_row(config, equity_curve, trades)
    monthly = monthly_returns_from_curve(config.name, equity_curve)
    yearly = yearly_returns_from_monthly(monthly)
    return {"config": config, "summary": summary, "trades": trades, "equity_curve": equity_curve, "monthly": monthly, "yearly": yearly}


def tag_order(data: swing.SwingData, config: AuditConfig, signal_index: int, signal_bar: dict, order: dict) -> dict:
    fill_index = order["index"]
    fill_bar = data.bars[fill_index]
    fill_time = fill_bar["time"] if config.fill_mode == "next_open" else fill_bar["close_time"]
    out = dict(order)
    out.update(
        {
            "signal_index": signal_index,
            "signal_bar_open": signal_bar["time"],
            "signal_bar_close": signal_bar["close_time"],
            "signal_date": signal_bar["date"],
            "fill_index": fill_index,
            "fill_mode": config.fill_mode,
            "expected_fill_time": fill_time,
        }
    )
    return out


def entry_limit_allows(
    data: swing.SwingData,
    config: AuditConfig,
    order: dict,
    last_exit_by_symbol: Dict[str, int],
    monthly_candidate_entries: Counter[Tuple[str, str]],
) -> bool:
    if order["index"] >= len(data.bars):
        return False
    fill_bar = data.bars[order["index"]]
    fill_time = fill_bar["time"] if config.fill_mode == "next_open" else fill_bar["close_time"]
    symbol = order["symbol"]
    if config.cooldown_hours:
        last_exit = last_exit_by_symbol.get(symbol)
        if last_exit is not None and fill_time - last_exit < config.cooldown_hours * 3600:
            return False
    if config.monthly_candidate_limit is not None:
        key = (month_from_ts(fill_time), symbol)
        if monthly_candidate_entries[key] >= config.monthly_candidate_limit:
            return False
    return True


def execute_entry(
    bar: dict,
    index: int,
    order: dict,
    cash: float,
    units: float,
    symbol: Optional[str],
    avg_entry_price: float,
    entry_equity: float,
    entry_time: int,
    entry_index: int,
    entry_atr: float,
    entry_parts: List[dict],
    price_key: str,
    fill_time: int,
    monthly_candidate_entries: Counter[Tuple[str, str]],
) -> Tuple[float, float, str, float, float, int, int, float]:
    fill_symbol = order["symbol"]
    price = bar["assets"][fill_symbol][price_key]
    equity = swing.mark_equity(cash, units, symbol, bar, use_close=price_key == "close")
    current_value = units * price if symbol == fill_symbol else 0.0
    target_value = equity * order["target_weight"]
    notional = max(0.0, target_value - current_value)
    if notional <= 1e-12:
        return cash, units, fill_symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr

    cost = notional * swing.FEE_RATE
    buy_units = notional / price
    is_new_trade = symbol is None
    if is_new_trade:
        entry_equity = equity
        entry_time = fill_time
        entry_index = index
        entry_atr = bar["assets"][fill_symbol]["atr14"] or 0.0
        avg_entry_price = price
        units = 0.0
        monthly_candidate_entries[(month_from_ts(fill_time), fill_symbol)] += 1

    avg_entry_price = ((units * avg_entry_price) + notional) / (units + buy_units) if units + buy_units > 0 else price
    cash -= notional + cost
    units += buy_units
    entry_parts.append(
        {
            "signal_date": format_dt(order["signal_bar_close"]),
            "signal_bar_open": format_dt(order["signal_bar_open"]),
            "fill_date": format_dt(fill_time),
            "part": order["part"],
            "target_weight": order["target_weight"],
            "price": price,
            "price_key": price_key,
            "signal_index": order["signal_index"],
            "fill_index": index,
        }
    )
    return cash, units, fill_symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr


def execute_exit(
    data: swing.SwingData,
    config: AuditConfig,
    bar: dict,
    index: int,
    cash: float,
    units: float,
    symbol: str,
    avg_entry_price: float,
    entry_equity: float,
    entry_time: int,
    entry_index: int,
    entry_parts: List[dict],
    exit_reason: str,
) -> Tuple[float, dict]:
    price = bar["assets"][symbol]["close"]
    proceeds = units * price
    cost = proceeds * swing.FEE_RATE
    cash_after = cash + proceeds - cost
    first_part = entry_parts[0]
    entry_price = first_part["price"]
    hold_days = (bar["close_time"] - entry_time) / 86400
    quality = entry_quality(data, symbol, entry_index, entry_price)
    trade_excursion = excursion(data, symbol, entry_index, index, avg_entry_price)
    fill_lag = first_part["fill_index"] - first_part["signal_index"]
    same_bar_close_signal_fill = bool(first_part["signal_index"] == first_part["fill_index"] and first_part["price_key"] == "close")
    entry_month = month_from_ts(entry_time)
    short_symbol = v1.short(symbol)
    trade = {
        "method": config.name,
        "method_key": config.method_key,
        "fill_mode": config.fill_mode,
        "cooldown_hours": config.cooldown_hours,
        "monthly_candidate_limit": config.monthly_candidate_limit if config.monthly_candidate_limit is not None else "",
        "symbol": short_symbol,
        "candidate_key": f"{entry_month}:{short_symbol}",
        "entry_month": entry_month,
        "entry_date": format_dt(entry_time),
        "exit_date": format_dt(bar["close_time"]),
        "entry_timestamp": entry_time,
        "exit_timestamp": bar["close_time"],
        "signal_date": first_part["signal_date"],
        "signal_bar_open": first_part["signal_bar_open"],
        "signal_index": first_part["signal_index"],
        "fill_index": first_part["fill_index"],
        "fill_lag_bars": fill_lag,
        "same_bar_close_signal_fill": same_bar_close_signal_fill,
        "lookahead_pass": bool(fill_lag >= 1 and not same_bar_close_signal_fill),
        "exit_reason": exit_reason,
        "entry_price": entry_price,
        "avg_entry_price": avg_entry_price,
        "exit_price": price,
        "parts_count": len(entry_parts),
        "parts": json.dumps(entry_parts, ensure_ascii=False),
        "hold_days": hold_days,
        "trade_return_pct": (cash_after / entry_equity - 1) * 100 if entry_equity else 0.0,
        "entry_after_1d_pct": quality["entry_after_1d_pct"],
        "entry_after_3d_pct": quality["entry_after_3d_pct"],
        "entry_after_7d_pct": quality["entry_after_7d_pct"],
        "entry_mae_pct": quality["entry_mae_pct"],
        "entry_mfe_pct": quality["entry_mfe_pct"],
        "trade_mae_pct": trade_excursion["mae_pct"],
        "trade_mfe_pct": trade_excursion["mfe_pct"],
        "stuck_after_1d": quality["stuck_after_1d"],
    }
    return cash_after, trade


def entry_quality(data: swing.SwingData, symbol: str, entry_index: int, entry_price: float) -> dict:
    out = {}
    for days in swing.ENTRY_QUALITY_DAYS:
        offset = days * 6
        if entry_index + offset < len(data.bars):
            close = data.bars[entry_index + offset]["assets"][symbol]["close"]
            out[f"entry_after_{days}d_pct"] = (close / entry_price - 1) * 100
        else:
            out[f"entry_after_{days}d_pct"] = None
    end = min(len(data.bars), entry_index + 7 * 6 + 1)
    lows = [data.bars[item]["assets"][symbol]["low"] for item in range(entry_index, end)]
    highs = [data.bars[item]["assets"][symbol]["high"] for item in range(entry_index, end)]
    out["entry_mae_pct"] = min(0.0, min(lows) / entry_price - 1) * 100 if lows else None
    out["entry_mfe_pct"] = max(0.0, max(highs) / entry_price - 1) * 100 if highs else None
    out["stuck_after_1d"] = bool(out["entry_after_1d_pct"] is not None and out["entry_after_1d_pct"] < 0)
    return out


def excursion(data: swing.SwingData, symbol: str, entry_index: int, exit_index: int, entry_price: float) -> dict:
    if exit_index < entry_index:
        return {"mae_pct": None, "mfe_pct": None}
    lows = [data.bars[item]["assets"][symbol]["low"] for item in range(entry_index, exit_index + 1)]
    highs = [data.bars[item]["assets"][symbol]["high"] for item in range(entry_index, exit_index + 1)]
    return {
        "mae_pct": min(0.0, min(lows) / entry_price - 1) * 100 if lows else None,
        "mfe_pct": max(0.0, max(highs) / entry_price - 1) * 100 if highs else None,
    }


def summary_row(config: AuditConfig, equity_curve: List[dict], trades: List[dict]) -> dict:
    final_equity = equity_curve[-1]["equity"] if equity_curve else 1.0
    years = (swing.TEST_END_TS - swing.TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [
        equity_curve[index]["equity"] / equity_curve[index - 1]["equity"] - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1]["equity"] > 0
    ]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(swing.PERIODS_PER_YEAR) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(equity_curve)
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    trade_returns = [trade["trade_return_pct"] for trade in trades]
    wins = [value for value in trade_returns if value > 0]
    losses = [value for value in trade_returns if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_loss = statistics.mean(losses) if losses else None
    avg_win = statistics.mean(wins) if wins else None
    avg_mae = mean_present([trade["entry_mae_pct"] for trade in trades])
    avg_mfe = mean_present([trade["entry_mfe_pct"] for trade in trades])
    stuck_values = [trade["stuck_after_1d"] for trade in trades if trade["entry_after_1d_pct"] is not None]
    hold_days = [trade["hold_days"] for trade in trades]
    return {
        "strategy": config.name,
        "method_key": config.method_key,
        "fill_mode": config.fill_mode,
        "cooldown_hours": config.cooldown_hours,
        "monthly_candidate_limit": config.monthly_candidate_limit if config.monthly_candidate_limit is not None else "",
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "trades": len(trades),
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "payoff_ratio": avg_win / abs(avg_loss) if avg_win is not None and avg_loss and avg_loss < 0 else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "avg_hold_days": statistics.mean(hold_days) if hold_days else None,
        "median_hold_days": statistics.median(hold_days) if hold_days else None,
        "max_hold_days": max(hold_days) if hold_days else None,
        "entry_after_1d_avg_pct": mean_present([trade["entry_after_1d_pct"] for trade in trades]),
        "entry_after_3d_avg_pct": mean_present([trade["entry_after_3d_pct"] for trade in trades]),
        "entry_after_7d_avg_pct": mean_present([trade["entry_after_7d_pct"] for trade in trades]),
        "avg_mae_pct": avg_mae,
        "avg_mfe_pct": avg_mfe,
        "mae_mfe_ratio": abs(avg_mae) / avg_mfe if avg_mae is not None and avg_mfe and avg_mfe > 0 else None,
        "stuck_after_1d_pct": sum(1 for value in stuck_values if value) / len(stuck_values) * 100 if stuck_values else None,
        "worst_trade_pct": min(trade_returns) if trade_returns else None,
        "best_trade_pct": max(trade_returns) if trade_returns else None,
    }


def state_machine_rows(results: List[dict]) -> List[dict]:
    rows = []
    for result in results:
        trades = result["trades"]
        summary = result["summary"]
        monthly_counts = Counter({month: 0 for month in MONTHS})
        candidate_counts: Counter[str] = Counter()
        for trade in trades:
            monthly_counts[trade["entry_month"]] += 1
            candidate_counts[trade["candidate_key"]] += 1
        monthly_values = [monthly_counts[month] for month in MONTHS]
        candidate_values = list(candidate_counts.values())
        same_candidate_reentries = count_same_candidate_reentries(trades)
        unintended_duplicates = sum(max(int(trade["parts_count"]) - 1, 0) for trade in trades if trade["method_key"] != "split_entry")
        planned_scale_ins = sum(max(int(trade["parts_count"]) - 1, 0) for trade in trades if trade["method_key"] == "split_entry")
        high_months = [month for month in MONTHS if monthly_counts[month] >= 100]
        rows.append(
            {
                "method": summary["strategy"],
                "trades": summary["trades"],
                "unintended_entries_while_position_open": unintended_duplicates,
                "planned_scale_in_entries": planned_scale_ins,
                "same_candidate_reentries_within_4h": same_candidate_reentries,
                "avg_entries_per_month_candidate": statistics.mean(candidate_values) if candidate_values else 0.0,
                "max_entries_per_month_candidate": max(candidate_values) if candidate_values else 0,
                "monthly_trade_min": min(monthly_values) if monthly_values else 0,
                "monthly_trade_p25": percentile(monthly_values, 25),
                "monthly_trade_median": statistics.median(monthly_values) if monthly_values else 0,
                "monthly_trade_p75": percentile(monthly_values, 75),
                "monthly_trade_p90": percentile(monthly_values, 90),
                "monthly_trade_max": max(monthly_values) if monthly_values else 0,
                "months_ge_100_trades": ", ".join(high_months),
                "state_machine_pass": bool(unintended_duplicates == 0),
            }
        )
    return rows


def count_same_candidate_reentries(trades: List[dict]) -> int:
    previous_by_candidate: Dict[str, dict] = {}
    count = 0
    for trade in sorted(trades, key=lambda row: row["entry_timestamp"]):
        previous = previous_by_candidate.get(trade["candidate_key"])
        if previous and trade["entry_timestamp"] - previous["exit_timestamp"] <= swing.INTERVAL_SECONDS:
            count += 1
        previous_by_candidate[trade["candidate_key"]] = trade
    return count


def timing_audit_rows(results: List[dict]) -> List[dict]:
    rows = []
    for result in results:
        trades = result["trades"]
        summary = result["summary"]
        same_bar = sum(1 for trade in trades if trade["same_bar_close_signal_fill"])
        lookahead_fail = sum(1 for trade in trades if not trade["lookahead_pass"])
        lags = [trade["fill_lag_bars"] for trade in trades]
        rows.append(
            {
                "method": summary["strategy"],
                "fill_mode": summary["fill_mode"],
                "cagr_pct": summary["cagr_pct"],
                "mdd_pct": summary["mdd_pct"],
                "trades": summary["trades"],
                "signal_fill_min_lag_bars": min(lags) if lags else "",
                "signal_fill_max_lag_bars": max(lags) if lags else "",
                "same_bar_close_signal_close_fill_count": same_bar,
                "lookahead_fail_count": lookahead_fail,
                "lookahead_result": "PASS" if same_bar == 0 and lookahead_fail == 0 else "FAIL",
            }
        )
    return rows


def entry_quality_rows_for(results: List[dict]) -> List[dict]:
    rows = []
    for result in results:
        summary = result["summary"]
        rows.append(
            {
                "method": summary["strategy"],
                "entry_after_1d_avg_pct": summary["entry_after_1d_avg_pct"],
                "entry_after_3d_avg_pct": summary["entry_after_3d_avg_pct"],
                "entry_after_7d_avg_pct": summary["entry_after_7d_avg_pct"],
                "avg_mae_pct": summary["avg_mae_pct"],
                "avg_mfe_pct": summary["avg_mfe_pct"],
                "mae_mfe_ratio": summary["mae_mfe_ratio"],
                "stuck_after_1d_pct": summary["stuck_after_1d_pct"],
                "stuck_definition": "entry_after_1d_pct < 0, using the first fill price and the close 6 completed 4H bars later",
            }
        )
    return rows


def trade_quality_rows_for(results: List[dict]) -> List[dict]:
    rows = []
    for result in results:
        summary = result["summary"]
        rows.append(
            {
                "method": summary["strategy"],
                "win_rate_pct": summary["win_rate_pct"],
                "avg_win_pct": summary["avg_win_pct"],
                "avg_loss_pct": summary["avg_loss_pct"],
                "payoff_ratio": summary["payoff_ratio"],
                "profit_factor": summary["profit_factor"],
                "avg_hold_days": summary["avg_hold_days"],
                "median_hold_days": summary["median_hold_days"],
                "max_hold_days": summary["max_hold_days"],
                "worst_trade_pct": summary["worst_trade_pct"],
                "best_trade_pct": summary["best_trade_pct"],
            }
        )
    return rows


def reentry_test_rows(results: List[dict]) -> List[dict]:
    baseline_by_method = {}
    for result in results:
        config = result["config"]
        if config.cooldown_hours == 0 and config.monthly_candidate_limit is None:
            baseline_by_method[config.method_key] = result["summary"]
    rows = []
    for result in results:
        summary = result["summary"]
        base = baseline_by_method[result["config"].method_key]
        rows.append(
            {
                "method": summary["strategy"],
                "base_method": METHOD_NAMES[result["config"].method_key],
                "cooldown_hours": summary["cooldown_hours"],
                "monthly_candidate_limit": summary["monthly_candidate_limit"],
                "cagr_pct": summary["cagr_pct"],
                "mdd_pct": summary["mdd_pct"],
                "sharpe": summary["sharpe"],
                "calmar": summary["calmar"],
                "trades": summary["trades"],
                "trade_reduction_pct": (1 - summary["trades"] / base["trades"]) * 100 if base["trades"] else None,
                "mdd_change_pct_point": summary["mdd_pct"] - base["mdd_pct"],
                "cagr_retention_pct": summary["cagr_pct"] / base["cagr_pct"] * 100 if base["cagr_pct"] else None,
                "profit_factor": summary["profit_factor"],
                "avg_hold_days": summary["avg_hold_days"],
                "avg_mae_pct": summary["avg_mae_pct"],
                "avg_mfe_pct": summary["avg_mfe_pct"],
            }
        )
    return rows


def final_comparison_rows(monthly_v1: v1.StrategyResult, results: List[dict]) -> List[dict]:
    rows = [monthly_v1_final_row(monthly_v1)]
    for result in results:
        summary = result["summary"]
        rows.append(
            {
                "strategy": summary["strategy"],
                "cagr_pct": summary["cagr_pct"],
                "mdd_pct": summary["mdd_pct"],
                "sharpe": summary["sharpe"],
                "calmar": summary["calmar"],
                "trades": summary["trades"],
                "avg_hold_days": summary["avg_hold_days"],
                "profit_factor": summary["profit_factor"],
                "avg_mae_pct": summary["avg_mae_pct"],
                "avg_mfe_pct": summary["avg_mfe_pct"],
                "worst_trade_pct": summary["worst_trade_pct"],
            }
        )
    return rows


def monthly_v1_final_row(monthly_v1: v1.StrategyResult) -> dict:
    returns = [row["return_pct"] for row in monthly_v1.monthly_rows]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    gross_loss = abs(sum(losses))
    return {
        "strategy": "기존 Monthly Strength v1",
        "cagr_pct": monthly_v1.summary["cagr_pct"],
        "mdd_pct": monthly_v1.summary["mdd_pct"],
        "sharpe": monthly_v1.summary["sharpe"],
        "calmar": monthly_v1.summary["calmar"],
        "trades": monthly_v1.summary["trades"],
        "avg_hold_days": "",
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "avg_mae_pct": "",
        "avg_mfe_pct": "",
        "worst_trade_pct": min(returns) if returns else None,
    }


def monthly_return_rows(monthly_v1: v1.StrategyResult, results: List[dict]) -> List[dict]:
    rows = [
        {"strategy": "기존 Monthly Strength v1", "month": row["month"], "return_pct": row["return_pct"]}
        for row in monthly_v1.monthly_rows
    ]
    for result in results:
        rows.extend(result["monthly"])
    return rows


def yearly_return_rows(monthly_v1: v1.StrategyResult, results: List[dict]) -> List[dict]:
    rows = [
        {"strategy": "기존 Monthly Strength v1", "year": year, "return_pct": value * 100}
        for year, value in sorted(monthly_v1.yearly_returns.items())
    ]
    for result in results:
        rows.extend({"strategy": result["summary"]["strategy"], "year": year, "return_pct": value} for year, value in sorted(result["yearly"].items()))
    return rows


def verdicts(monthly_v1: v1.StrategyResult, state_rows: List[dict], final_rows: List[dict], reentry_rows: List[dict]) -> List[dict]:
    lookup = {row["strategy"]: row for row in final_rows}
    state_lookup = {row["method"]: row for row in state_rows}
    reentry_lookup = {row["method"]: row for row in reentry_rows}
    v1_mdd = monthly_v1.summary["mdd_pct"]
    immediate_state = state_lookup["즉시 진입"]
    ema20 = lookup["EMA20 눌림"]
    ema50 = lookup["EMA50 눌림"]
    ema20_cd = lookup["EMA20 눌림 + 48시간 쿨다운"]
    ema50_cd = lookup["EMA50 눌림 + 48시간 쿨다운"]
    ema20_reentry_base = reentry_lookup["EMA20 눌림 진입 / 제한 없음"]
    ema50_reentry_base = reentry_lookup["EMA50 눌림 진입 / 제한 없음"]
    ema20_reentry_cd = reentry_lookup["EMA20 눌림 진입 / 48h 쿨다운"]
    ema50_reentry_cd = reentry_lookup["EMA50 눌림 진입 / 48h 쿨다운"]
    return [
        {
            "check": "즉시 진입 1567회가 state-machine 중복 버그인지",
            "result": "POLICY_ISSUE" if immediate_state["state_machine_pass"] and immediate_state["same_candidate_reentries_within_4h"] > 0 else "FAIL",
            "evidence": (
                f"보유 중 비의도 중복진입 {immediate_state['unintended_entries_while_position_open']}회, "
                f"동일 월+후보 4H 이내 재진입 {immediate_state['same_candidate_reentries_within_4h']}회"
            ),
        },
        {
            "check": "EMA20 눌림이 monthly v1 대비 MDD를 악화시키지 않는지",
            "result": "PASS" if ema20["mdd_pct"] >= v1_mdd else "FAIL",
            "evidence": f"Monthly v1 MDD {v1_mdd:.1f}%, EMA20 MDD {ema20['mdd_pct']:.1f}%",
        },
        {
            "check": "EMA50 눌림이 monthly v1 대비 MDD를 악화시키지 않는지",
            "result": "PASS" if ema50["mdd_pct"] >= v1_mdd else "FAIL",
            "evidence": f"Monthly v1 MDD {v1_mdd:.1f}%, EMA50 MDD {ema50['mdd_pct']:.1f}%",
        },
        {
            "check": "EMA20 48h 쿨다운 후 거래 횟수와 MDD가 줄어드는지",
            "result": "PASS" if ema20_reentry_cd["trades"] < ema20_reentry_base["trades"] and ema20_cd["mdd_pct"] >= ema20["mdd_pct"] else "FAIL",
            "evidence": f"거래 {ema20_reentry_base['trades']} -> {ema20_reentry_cd['trades']}, MDD {ema20['mdd_pct']:.1f}% -> {ema20_cd['mdd_pct']:.1f}%",
        },
        {
            "check": "EMA50 48h 쿨다운 후 거래 횟수와 MDD가 줄어드는지",
            "result": "PASS" if ema50_reentry_cd["trades"] < ema50_reentry_base["trades"] and ema50_cd["mdd_pct"] >= ema50["mdd_pct"] else "FAIL",
            "evidence": f"거래 {ema50_reentry_base['trades']} -> {ema50_reentry_cd['trades']}, MDD {ema50['mdd_pct']:.1f}% -> {ema50_cd['mdd_pct']:.1f}%",
        },
        {
            "check": "EMA20 48h 쿨다운 수익률 훼손이 과도하지 않은지",
            "result": "PASS" if ema20_cd["cagr_pct"] >= ema20["cagr_pct"] * RETURN_DAMAGE_FLOOR else "FAIL",
            "evidence": f"CAGR {ema20['cagr_pct']:.1f}% -> {ema20_cd['cagr_pct']:.1f}% / 기준 {RETURN_DAMAGE_FLOOR * 100:.0f}% 유지",
        },
        {
            "check": "EMA50 48h 쿨다운 수익률 훼손이 과도하지 않은지",
            "result": "PASS" if ema50_cd["cagr_pct"] >= ema50["cagr_pct"] * RETURN_DAMAGE_FLOOR else "FAIL",
            "evidence": f"CAGR {ema50['cagr_pct']:.1f}% -> {ema50_cd['cagr_pct']:.1f}% / 기준 {RETURN_DAMAGE_FLOOR * 100:.0f}% 유지",
        },
    ]


def monthly_returns_from_curve(strategy: str, curve: List[dict]) -> List[dict]:
    month_end_equity: Dict[str, float] = {}
    for point in curve:
        month = month_from_ts(point["time"])
        if MONTHS[0] <= month <= MONTHS[-1]:
            month_end_equity[month] = point["equity"]
    rows = []
    previous_equity = 1.0
    for month in MONTHS:
        equity = month_end_equity.get(month, previous_equity)
        monthly_return = equity / previous_equity - 1 if previous_equity else 0.0
        rows.append({"strategy": strategy, "month": month, "return_pct": monthly_return * 100})
        previous_equity = equity
    return rows


def yearly_returns_from_monthly(rows: List[dict]) -> Dict[str, float]:
    yearly: Dict[str, float] = {}
    for row in rows:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return {year: (value - 1) * 100 for year, value in yearly.items()}


def build_report(
    data: swing.SwingData,
    monthly_v1: v1.StrategyResult,
    state_rows: List[dict],
    timing_rows: List[dict],
    entry_quality_rows: List[dict],
    trade_quality_rows: List[dict],
    reentry_rows: List[dict],
    final_rows: List[dict],
    monthly_rows: List[dict],
    yearly_rows: List[dict],
    verdict_rows: List[dict],
    target_trades: List[dict],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# BTC/ETH Monthly Strength v1 Swing Entry Audit 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 데이터: Binance Spot `1d`/`4h` klines, `BTCUSDT`/`ETHUSDT`",
        "- 기존 Monthly Strength v1 규칙은 변경하지 않았다. 이 파일은 별도 감사 산출물이다.",
        "- 스윙 후보는 기존 스윙 비교와 동일하게 직전 완결 1D 기준 최근 14일 수익률이 더 높은 자산으로 둔다.",
        "- `월별 후보`는 감사 목적상 `진입 월 + 진입 심볼`로 정의했다.",
        "- `물린 비율`은 첫 체결가 대비 진입 후 1일, 즉 6개 4H 봉 뒤 종가 수익률이 음수인 거래 비율이다.",
        "- MAE/MFE는 첫 체결 후 7일 동안 저가/고가 기준으로 계산하며, MAE는 0 이하, MFE는 0 이상으로 절단했다.",
        f"- 수익률 훼손 판정은 48h 쿨다운 CAGR이 제한 없음 CAGR의 {RETURN_DAMAGE_FLOOR * 100:.0f}% 이상이면 통과로 둔다.",
        "",
        "## 최종 판정",
        "",
        verdict_table(verdict_rows),
        "",
        "## 1. State Machine 감사",
        "",
        state_table(state_rows),
        "",
        "## 2. 체결 시점 감사",
        "",
        timing_table(timing_rows),
        "",
        "## 3. 진입 품질 지표",
        "",
        entry_quality_table(entry_quality_rows),
        "",
        "## 4. 거래 품질",
        "",
        trade_quality_table(trade_quality_rows),
        "",
        "### 최악 거래 Top 10",
        "",
        trade_rank_table(target_trades, reverse=False),
        "",
        "### 최고 거래 Top 10",
        "",
        trade_rank_table(target_trades, reverse=True),
        "",
        "## 5. 재진입 제한 테스트",
        "",
        reentry_table(reentry_rows),
        "",
        "## 6. 최종 비교",
        "",
        final_table(final_rows),
        "",
        "## 연도별 수익률",
        "",
        yearly_table(yearly_rows),
        "",
        "## 월별 수익률 샘플",
        "",
        monthly_sample_table(monthly_rows),
        "",
        "## 데이터 커버리지",
        "",
        swing.coverage_table(data),
        "",
        "## 산출물",
        "",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_report.md`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_state_machine.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_timing.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_entry_quality.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_trade_quality.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_reentry_tests.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_final_comparison.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_monthly_returns.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_yearly_returns.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_trades.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_audit_verdicts.csv`",
        "",
    ]
    return "\n".join(lines)


def verdict_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def state_table(rows: List[dict]) -> str:
    headers = ["Method", "Trades", "Dup", "Scale-in", "4H re-entry", "Avg/candidate", "Max/candidate", "Monthly median", "Monthly max", ">=100 months", "Pass"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    str(row["trades"]),
                    str(row["unintended_entries_while_position_open"]),
                    str(row["planned_scale_in_entries"]),
                    str(row["same_candidate_reentries_within_4h"]),
                    num(row["avg_entries_per_month_candidate"]),
                    str(row["max_entries_per_month_candidate"]),
                    num(row["monthly_trade_median"]),
                    str(row["monthly_trade_max"]),
                    row["months_ge_100_trades"] or "-",
                    "PASS" if row["state_machine_pass"] else "FAIL",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def timing_table(rows: List[dict]) -> str:
    headers = ["Method", "Fill", "CAGR", "MDD", "Trades", "Lag min", "Lag max", "Same-bar", "Fail", "Result"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    row["fill_mode"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    str(row["trades"]),
                    str(row["signal_fill_min_lag_bars"]),
                    str(row["signal_fill_max_lag_bars"]),
                    str(row["same_bar_close_signal_close_fill_count"]),
                    str(row["lookahead_fail_count"]),
                    row["lookahead_result"],
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def entry_quality_table(rows: List[dict]) -> str:
    headers = ["Method", "1D", "3D", "7D", "Avg MAE", "Avg MFE", "MAE/MFE", "Stuck"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    pct(row["entry_after_1d_avg_pct"]),
                    pct(row["entry_after_3d_avg_pct"]),
                    pct(row["entry_after_7d_avg_pct"]),
                    pct(row["avg_mae_pct"]),
                    pct(row["avg_mfe_pct"]),
                    num(row["mae_mfe_ratio"]),
                    pct(row["stuck_after_1d_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def trade_quality_table(rows: List[dict]) -> str:
    headers = ["Method", "Win", "Avg win", "Avg loss", "Payoff", "PF", "Avg hold", "Median hold", "Max hold", "Worst", "Best"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    pct(row["win_rate_pct"]),
                    pct(row["avg_win_pct"]),
                    pct(row["avg_loss_pct"]),
                    num(row["payoff_ratio"]),
                    num(row["profit_factor"]),
                    num(row["avg_hold_days"]),
                    num(row["median_hold_days"]),
                    num(row["max_hold_days"]),
                    pct(row["worst_trade_pct"]),
                    pct(row["best_trade_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def trade_rank_table(trades: List[dict], reverse: bool) -> str:
    rows = sorted(trades, key=lambda row: row["trade_return_pct"], reverse=reverse)[:10]
    lines = ["| Method | Symbol | Entry | Exit | Reason | Return | Hold | MAE | MFE |", "|---|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    row["symbol"],
                    row["entry_date"],
                    row["exit_date"],
                    row["exit_reason"],
                    pct(row["trade_return_pct"]),
                    num(row["hold_days"]),
                    pct(row["trade_mae_pct"]),
                    pct(row["trade_mfe_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def reentry_table(rows: List[dict]) -> str:
    headers = ["Method", "CAGR", "MDD", "Trades", "Trade red.", "MDD change", "CAGR keep", "PF", "Avg hold", "Avg MAE", "Avg MFE"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    str(row["trades"]),
                    pct(row["trade_reduction_pct"]),
                    pp(row["mdd_change_pct_point"]),
                    pct(row["cagr_retention_pct"]),
                    num(row["profit_factor"]),
                    num(row["avg_hold_days"]),
                    pct(row["avg_mae_pct"]),
                    pct(row["avg_mfe_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def final_table(rows: List[dict]) -> str:
    headers = ["Strategy", "CAGR", "MDD", "Sharpe", "Calmar", "Trades", "Avg hold", "PF", "Avg MAE", "Avg MFE", "Worst"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["strategy"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    str(row["trades"]),
                    num(row["avg_hold_days"]),
                    num(row["profit_factor"]),
                    pct(row["avg_mae_pct"]),
                    pct(row["avg_mfe_pct"]),
                    pct(row["worst_trade_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def yearly_table(rows: List[dict]) -> str:
    strategies = []
    for row in rows:
        if row["strategy"] not in strategies:
            strategies.append(row["strategy"])
    years = sorted({row["year"] for row in rows})
    lookup = {(row["strategy"], row["year"]): row["return_pct"] for row in rows}
    lines = ["| Strategy | " + " | ".join(years) + " |", "|" + "|".join(["---"] * (len(years) + 1)) + "|"]
    for strategy in strategies:
        values = [pct(lookup.get((strategy, year))) for year in years]
        lines.append("| " + " | ".join([strategy] + values) + " |")
    return "\n".join(lines)


def monthly_sample_table(rows: List[dict]) -> str:
    sample_months = MONTHS[-12:]
    strategies = []
    for row in rows:
        if row["strategy"] not in strategies:
            strategies.append(row["strategy"])
    lookup = {(row["strategy"], row["month"]): row["return_pct"] for row in rows}
    lines = ["| Strategy | " + " | ".join(sample_months) + " |", "|" + "|".join(["---"] * (len(sample_months) + 1)) + "|"]
    for strategy in strategies:
        values = [pct(lookup.get((strategy, month))) for month in sample_months]
        lines.append("| " + " | ".join([strategy] + values) + " |")
    return "\n".join(lines)


def percentile(values: List[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile_value / 100
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and value != ""]
    return statistics.mean(clean) if clean else None


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def format_dt(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M")


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def pp(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):+.1f}%p"


def num(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


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
