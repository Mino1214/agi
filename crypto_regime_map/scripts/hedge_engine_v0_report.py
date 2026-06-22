"""Hedge Engine v0 research report.

Standalone BTC-short hedge research for the Alpha Long Engine v1.2 candidate.
This is a defensive overlay study, not a short alpha engine and not live
trading code.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
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

import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


FAPI_BASE_URLS = ("https://fapi.binance.com",)
SYMBOLS = tuple(alpha.UNIVERSE_10)
BTC = "BTCUSDT"
BASE_SLIPPAGE = 0.0020
TAKER_FEE = 0.0005
SLIPPAGE_SENSITIVITY = (0.0010, 0.0020, 0.0030, 0.0050)
BASE_HEDGE_MAX_HOLD_DAYS = 7
INTERVAL_SECONDS = {"1d": 86400, "1h": 3600}
OVERTRADE_WARNING_MONTHLY = 8.0


@dataclass(frozen=True)
class HedgeConfig:
    name: str
    mode: str
    group: str
    ratio_low: float = 0.20
    ratio_high: float = 0.30
    fixed_ratio: Optional[float] = None
    reduce_long_fraction: float = 0.0
    max_hold_days: int = BASE_HEDGE_MAX_HOLD_DAYS
    slippage_rate: float = BASE_SLIPPAGE
    fee_rate: float = TAKER_FEE


@dataclass
class HedgePosition:
    units: float
    entry_price: float
    entry_raw_price: float
    entry_time: int
    signal_time: int
    target_ratio: float
    notional: float
    reason: str
    entry_fee: float
    entry_slippage_cost: float
    funding_pnl: float = 0.0
    funding_events: int = 0


@dataclass
class ReductionLeg:
    symbol: str
    units: float
    entry_price: float
    entry_raw_price: float
    entry_time: int
    signal_time: int
    entry_fee: float
    entry_slippage_cost: float


@dataclass
class HedgeRun:
    config: HedgeConfig
    equity_curve: List[dict]
    trades: List[dict]
    exposure_rows: List[dict]
    hedge_pnl: float
    hedge_funding_pnl: float
    hedge_cost: float
    reduction_pnl: float
    missed_upside: float


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use cached OHLCV/funding data when available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    spot_data = load_long_data(args.use_cache)
    long_result, long_trades, baseline_curve, long_cashflows, funding_index = run_long_baseline(spot_data, args.use_cache)
    btc_futures_1h = load_futures_raw([BTC], "1h", args.use_cache, alpha.FETCH_INTRADAY_START)[BTC]
    btc_futures_1d = load_futures_raw([BTC], "1d", args.use_cache, alpha.FETCH_DAILY_START)[BTC]
    hedge_context = build_hedge_context(spot_data, btc_futures_1h, btc_futures_1d, funding_index[BTC], long_trades, baseline_curve)

    configs = build_configs()
    hedge_runs = [run_hedge_overlay(hedge_context, config) for config in configs]

    no_hedge_summary = no_hedge_summary_row(hedge_context, long_result, long_trades, baseline_curve, long_cashflows)
    summary_rows = [no_hedge_summary]
    monthly_rows = monthly_returns_from_curve(hedge_context, "Alpha Long v1.2 / No Hedge", "No Hedge", "actual", baseline_curve)
    yearly_rows = yearly_rows_from_monthly("Alpha Long v1.2 / No Hedge", "No Hedge", "actual", monthly_rows)
    trade_rows: List[dict] = []

    for run in hedge_runs:
        monthly = monthly_returns_from_curve(hedge_context, run.config.name, run.config.group, "actual", run.equity_curve)
        yearly = yearly_rows_from_monthly(run.config.name, run.config.group, "actual", monthly)
        summary_rows.append(summary_row(hedge_context, run, no_hedge_summary, monthly))
        monthly_rows.extend(monthly)
        yearly_rows.extend(yearly)
        trade_rows.extend(run.trades)

    pass_fail_rows = pass_fail(summary_rows)
    report = build_report(hedge_context, summary_rows, trade_rows, monthly_rows, yearly_rows, pass_fail_rows)

    report_path = output_dir / "hedge_engine_v0_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "hedge_engine_v0_summary.csv", summary_rows)
    write_csv(output_dir / "hedge_engine_v0_trades.csv", trade_rows)
    write_csv(output_dir / "hedge_engine_v0_monthly.csv", monthly_rows)
    write_csv(output_dir / "hedge_engine_v0_yearly.csv", yearly_rows)
    print(report_path)


def load_long_data(use_cache: bool) -> alpha.AlphaData:
    raw_1d = alpha.load_raw(SYMBOLS, "1d", use_cache, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(SYMBOLS, "4h", use_cache, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(SYMBOLS, "1h", use_cache, alpha.FETCH_INTRADAY_START)
    return alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)


def run_long_baseline(spot_data: alpha.AlphaData, use_cache: bool) -> Tuple[rb.RunResult, List[dict], List[dict], List[dict], Dict[str, Tuple[List[int], List[dict]]]]:
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": spot_data})
    variant = rb.RobustVariant(
        "Alpha Long v1.2 candidate / No DOGE + top 20% + liquidation buffer",
        exclude_doge=True,
        top_score_pct=0.20,
        require_liquidation_buffer=True,
        group="No Hedge",
    )
    config = rb.RunConfig(variant=variant, market_data="spot", slippage_rate=BASE_SLIPPAGE, fee_rate=TAKER_FEE)
    result = rb.run_robust_engine(spot_data, config)
    liquidation_trades = rb.annotate_liquidation(result.trades, result)

    funding_info = funding.load_funding_info(use_cache)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }
    funding_index = rb.build_time_index(funding_by_symbol, "funding_time")
    long_trades, long_cashflows = rb.annotate_funding_fast(liquidation_trades, funding_index, "actual_funding", "actual funding", "actual")
    baseline_curve = funding.adjusted_equity_curve(result.equity_curve, long_cashflows)
    return result, long_trades, baseline_curve, long_cashflows, funding_index


def build_configs() -> List[HedgeConfig]:
    configs = [
        HedgeConfig("Defensive Hedge 20%", "defensive", "Regime hedge", fixed_ratio=0.20),
        HedgeConfig("Defensive Hedge 30%", "defensive", "Regime hedge", fixed_ratio=0.30),
        HedgeConfig("Shock Hedge 20% / keep longs", "shock", "Shock hedge", fixed_ratio=0.20),
        HedgeConfig("Shock Hedge 30% / keep longs", "shock", "Shock hedge", fixed_ratio=0.30),
        HedgeConfig("Shock Hedge 20% / reduce longs 50%", "shock", "Shock hedge", fixed_ratio=0.20, reduce_long_fraction=0.50),
        HedgeConfig("Shock Hedge 30% / reduce longs 50%", "shock", "Shock hedge", fixed_ratio=0.30, reduce_long_fraction=0.50),
        HedgeConfig("Drawdown Hedge 20/30%", "drawdown", "Drawdown hedge"),
        HedgeConfig("Volatility Hedge 20/30%", "volatility", "Volatility hedge"),
        HedgeConfig("Composite Hedge 20/30%", "composite", "Composite hedge"),
        HedgeConfig("Defensive Hedge 10%", "defensive", "Hedge ratio sensitivity", fixed_ratio=0.10),
        HedgeConfig("Defensive Hedge 50%", "defensive", "Hedge ratio sensitivity", fixed_ratio=0.50),
        HedgeConfig("Composite Hedge 10%", "composite", "Hedge ratio sensitivity", ratio_low=0.10, ratio_high=0.10),
        HedgeConfig("Composite Hedge 50%", "composite", "Hedge ratio sensitivity", ratio_low=0.50, ratio_high=0.50),
        HedgeConfig("Composite Hedge 20/30% / max hold 14d", "composite", "Hold sensitivity", max_hold_days=14),
    ]
    configs.extend(
        HedgeConfig(
            f"Composite Hedge 20/30% / slippage {slippage * 100:.1f}%",
            "composite",
            "Slippage sensitivity",
            slippage_rate=slippage,
        )
        for slippage in SLIPPAGE_SENSITIVITY
    )
    return dedupe_configs(configs)


def build_hedge_context(
    spot_data: alpha.AlphaData,
    btc_futures_1h: List[dict],
    btc_futures_1d: List[dict],
    btc_funding_index: Tuple[List[int], List[dict]],
    long_trades: List[dict],
    baseline_curve: List[dict],
) -> dict:
    baseline_by_time = {int(row["time"]): float(row["equity"]) for row in baseline_curve}
    baseline_times = sorted(baseline_by_time)
    baseline_peak_by_time = {}
    peak = 0.0
    for timestamp in baseline_times:
        peak = max(peak, baseline_by_time[timestamp])
        baseline_peak_by_time[timestamp] = peak
    btc_1h = alpha.add_1h_features(btc_futures_1h)
    btc_1d = add_daily_vol_features(btc_futures_1d)
    times_1h = [time for time in spot_data.times_1h if alpha.TEST_START_TS <= time < alpha.TEST_END_TS]
    active_map, exposure_open, exposure_close = precompute_long_exposure(spot_data, long_trades, times_1h)
    ctx = {
        "spot_data": spot_data,
        "times_1h": times_1h,
        "btc_futures_1h": btc_1h,
        "btc_futures_by_time": {row["time"]: row for row in btc_1h},
        "btc_daily_features": btc_1d,
        "btc_daily_close_times": [row["close_time"] for row in btc_1d],
        "btc_funding_index": btc_funding_index,
        "long_trades": long_trades,
        "long_trades_by_time": build_active_trade_index(long_trades),
        "active_long_by_time": active_map,
        "long_exposure_open": exposure_open,
        "long_exposure_close": exposure_close,
        "baseline_curve": baseline_curve,
        "baseline_by_time": baseline_by_time,
        "baseline_times": baseline_times,
        "baseline_peak_by_time": baseline_peak_by_time,
        "regime_by_date": spot_data.regime_by_date,
        "months": alpha.MONTHS,
        "test_start_ts": alpha.TEST_START_TS,
        "test_end_ts": alpha.TEST_END_TS,
    }
    return ctx


def precompute_long_exposure(spot_data: alpha.AlphaData, trades: List[dict], times_1h: List[int]) -> Tuple[Dict[int, List[dict]], Dict[int, float], Dict[int, float]]:
    active_map: Dict[int, List[dict]] = defaultdict(list)
    exposure_open = {timestamp: 0.0 for timestamp in times_1h}
    exposure_close = {timestamp: 0.0 for timestamp in times_1h}
    for trade in trades:
        symbol = f"{trade['symbol']}USDT"
        start = int(trade["entry_timestamp"])
        end = int(trade["exit_timestamp"])
        left = bisect_left(times_1h, start)
        right = bisect_left(times_1h, end)
        for timestamp in times_1h[left:right]:
            row = spot_data.by_time_1h.get(symbol, {}).get(timestamp)
            if not row:
                continue
            units = active_trade_units(trade, timestamp)
            active_map[timestamp].append(trade)
            exposure_open[timestamp] += units * row["open"]
            exposure_close[timestamp] += units * row["close"]
    return active_map, exposure_open, exposure_close


def run_hedge_overlay(ctx: dict, config: HedgeConfig) -> HedgeRun:
    cash_adjustment = 0.0
    hedge_position: Optional[HedgePosition] = None
    reduction_legs: List[ReductionLeg] = []
    trades: List[dict] = []
    exposure_rows: List[dict] = []
    equity_curve = [{"time": ctx["test_start_ts"], "date": alpha.format_dt(ctx["test_start_ts"]), "equity": 1.0}]
    hedge_pnl = 0.0
    hedge_funding_pnl = 0.0
    hedge_cost = 0.0
    reduction_pnl = 0.0
    missed_upside = 0.0

    for open_time in ctx["times_1h"]:
        if open_time <= ctx["test_start_ts"]:
            continue
        signal_time = open_time - 3600
        close_time = open_time + 3600
        btc_row = ctx["btc_futures_by_time"].get(open_time)
        if not btc_row:
            continue

        desired = desired_hedge(ctx, config, signal_time)
        long_notional = long_exposure(ctx, open_time, price_key="open")
        desired_notional = long_notional * desired["ratio"]

        if hedge_position:
            cash_delta, funding_delta, funding_events = apply_btc_funding(ctx, hedge_position, min(close_time, ctx["test_end_ts"]))
            cash_adjustment += cash_delta
            hedge_position.funding_pnl += funding_delta
            hedge_position.funding_events += funding_events
            hedge_funding_pnl += funding_delta

        should_close = False
        close_reason = ""
        if hedge_position and desired["ratio"] <= 0:
            should_close = True
            close_reason = "condition_released"
        elif hedge_position and hedge_position.reason != desired["reason"]:
            should_close = True
            close_reason = "condition_changed"
        elif hedge_position and abs(hedge_position.target_ratio - desired["ratio"]) > 0.001:
            should_close = True
            close_reason = "ratio_rebalance"
        elif hedge_position and open_time - hedge_position.entry_time >= config.max_hold_days * 86400:
            should_close = True
            close_reason = "max_hold"

        if should_close and hedge_position:
            trade = close_hedge_trade(ctx, config, hedge_position, btc_row["open"], open_time, close_reason)
            cash_adjustment += trade["_cash_delta"]
            hedge_pnl += trade["pnl"]
            hedge_cost += trade["total_cost"]
            missed_upside += missed_upside_for_trade(ctx, trade)
            trades.append(strip_private(trade))
            hedge_position = None

        if reduction_legs and (desired["ratio"] <= 0 or config.reduce_long_fraction <= 0 or should_close):
            closed, cash_delta = close_reduction_legs(ctx, config, reduction_legs, open_time, "condition_released" if desired["ratio"] <= 0 else "rebalance")
            reduction_legs = []
            cash_adjustment += cash_delta
            reduction_pnl += sum(row["pnl"] for row in closed)
            hedge_cost += sum(row["total_cost"] for row in closed)
            missed_upside += sum(max(-row["pnl"], 0.0) for row in closed if baseline_return(ctx, row["entry_time"], row["exit_time"]) > 0)
            trades.extend(strip_private(row) for row in closed)

        if desired["ratio"] > 0 and long_notional > 0 and hedge_position is None:
            hedge_position = open_hedge_trade(config, btc_row["open"], open_time, signal_time, desired["ratio"], desired_notional, desired["reason"])
            cash_adjustment -= hedge_position.entry_fee
            hedge_cost += hedge_position.entry_fee + hedge_position.entry_slippage_cost
            if config.reduce_long_fraction > 0:
                reduction_legs = open_reduction_legs(ctx, config, open_time, signal_time, config.reduce_long_fraction)
                reduction_open_cost = sum(leg.entry_fee + leg.entry_slippage_cost for leg in reduction_legs)
                cash_adjustment -= sum(leg.entry_fee for leg in reduction_legs)
                hedge_cost += reduction_open_cost

        btc_close = btc_row["close"]
        open_hedge_unrealized = hedge_unrealized(config, hedge_position, btc_close) if hedge_position else 0.0
        open_reduction_unrealized = reduction_unrealized(ctx, reduction_legs, open_time) if reduction_legs else 0.0
        baseline_equity = baseline_equity_at(ctx, close_time)
        equity = baseline_equity + cash_adjustment + open_hedge_unrealized + open_reduction_unrealized
        effective_long_notional = max(0.0, long_notional - current_reduction_notional(ctx, reduction_legs, open_time))
        hedge_notional = hedge_position.units * btc_close if hedge_position else 0.0
        exposure_rows.append(
            {
                "time": close_time,
                "equity": equity,
                "long_notional": long_notional,
                "effective_long_notional": effective_long_notional,
                "hedge_notional": hedge_notional,
                "net_exposure": effective_long_notional - hedge_notional,
                "gross_exposure": effective_long_notional + hedge_notional,
            }
        )
        equity_curve.append({"time": close_time, "date": alpha.format_dt(close_time), "equity": max(1e-9, equity)})

    last_time = ctx["times_1h"][-1]
    last_btc = ctx["btc_futures_by_time"].get(last_time)
    if hedge_position and last_btc:
        trade = close_hedge_trade(ctx, config, hedge_position, last_btc["close"], last_time + 3600, "end_of_test")
        cash_adjustment += trade["_cash_delta"]
        hedge_pnl += trade["pnl"]
        hedge_cost += trade["total_cost"]
        missed_upside += missed_upside_for_trade(ctx, trade)
        trades.append(strip_private(trade))
    if reduction_legs:
        closed, cash_delta = close_reduction_legs(ctx, config, reduction_legs, last_time + 3600, "end_of_test")
        cash_adjustment += cash_delta
        reduction_pnl += sum(row["pnl"] for row in closed)
        hedge_cost += sum(row["total_cost"] for row in closed)
        missed_upside += sum(max(-row["pnl"], 0.0) for row in closed if baseline_return(ctx, row["entry_time"], row["exit_time"]) > 0)
        trades.extend(strip_private(row) for row in closed)

    final_equity = baseline_equity_at(ctx, ctx["test_end_ts"]) + cash_adjustment
    equity_curve.append({"time": ctx["test_end_ts"], "date": alpha.format_dt(ctx["test_end_ts"]), "equity": max(1e-9, final_equity)})
    return HedgeRun(
        config=config,
        equity_curve=equity_curve,
        trades=trades,
        exposure_rows=exposure_rows,
        hedge_pnl=hedge_pnl,
        hedge_funding_pnl=hedge_funding_pnl,
        hedge_cost=hedge_cost,
        reduction_pnl=reduction_pnl,
        missed_upside=missed_upside,
    )


def desired_hedge(ctx: dict, config: HedgeConfig, signal_time: int) -> dict:
    conditions = condition_flags(ctx, signal_time)
    if config.mode == "defensive" and conditions["defensive"]:
        return {"ratio": config.fixed_ratio or config.ratio_low, "reason": "reduce_risk"}
    if config.mode == "shock" and conditions["shock"]:
        return {"ratio": config.fixed_ratio or config.ratio_high, "reason": "shock"}
    if config.mode == "drawdown":
        if conditions["drawdown_10"]:
            return {"ratio": config.ratio_high, "reason": "drawdown_10"}
        if conditions["drawdown_5"]:
            return {"ratio": config.ratio_low, "reason": "drawdown_5"}
        return {"ratio": 0.0, "reason": "drawdown_recovered"}
    if config.mode == "volatility":
        if conditions["volatility_2x"]:
            return {"ratio": config.ratio_high, "reason": "volatility_2x"}
        if conditions["volatility_15x"]:
            return {"ratio": config.ratio_low, "reason": "volatility_15x"}
        return {"ratio": 0.0, "reason": "volatility_normal"}
    if config.mode == "composite":
        count = sum(1 for key in ("defensive", "shock", "drawdown_5", "volatility_15x") if conditions[key])
        if count >= 3:
            return {"ratio": config.ratio_high, "reason": f"composite_{count}_conditions"}
        if count >= 2:
            return {"ratio": config.ratio_low, "reason": f"composite_{count}_conditions"}
        return {"ratio": 0.0, "reason": f"composite_{count}_conditions"}
    return {"ratio": 0.0, "reason": "no_condition"}


def condition_flags(ctx: dict, signal_time: int) -> dict:
    regime = ctx["regime_by_date"].get(alpha.date_from_ts(signal_time), {})
    baseline_equity = baseline_equity_at(ctx, signal_time)
    peak = baseline_peak_at(ctx, signal_time)
    drawdown = baseline_equity / peak - 1 if peak else 0.0
    vol_ratio = btc_vol_ratio(ctx, signal_time)
    return {
        "defensive": regime.get("trade_action_bias") == "reduce_risk",
        "shock": regime.get("trade_action_bias") == "no_new_entry" or regime.get("trade_regime") == "shock",
        "drawdown_5": drawdown <= -0.05,
        "drawdown_10": drawdown <= -0.10,
        "drawdown_recovered": drawdown >= -0.03,
        "volatility_15x": vol_ratio is not None and vol_ratio >= 1.5,
        "volatility_2x": vol_ratio is not None and vol_ratio >= 2.0,
        "vol_ratio": vol_ratio,
        "drawdown": drawdown,
    }


def open_hedge_trade(config: HedgeConfig, raw_price: float, open_time: int, signal_time: int, ratio: float, notional: float, reason: str) -> HedgePosition:
    entry_price = raw_price * (1 - config.slippage_rate)
    units = notional / entry_price if entry_price else 0.0
    entry_fee = notional * config.fee_rate
    return HedgePosition(
        units=units,
        entry_price=entry_price,
        entry_raw_price=raw_price,
        entry_time=open_time,
        signal_time=signal_time,
        target_ratio=ratio,
        notional=notional,
        reason=reason,
        entry_fee=entry_fee,
        entry_slippage_cost=notional * config.slippage_rate,
    )


def close_hedge_trade(ctx: dict, config: HedgeConfig, position: HedgePosition, raw_price: float, exit_time: int, reason: str) -> dict:
    exit_price = raw_price * (1 + config.slippage_rate)
    gross_pnl = position.units * (position.entry_price - exit_price)
    exit_notional = position.units * exit_price
    exit_fee = exit_notional * config.fee_rate
    exit_slippage_cost = position.units * raw_price * config.slippage_rate
    total_cost = position.entry_fee + exit_fee + position.entry_slippage_cost + exit_slippage_cost
    pnl = gross_pnl - exit_fee - position.entry_fee + position.funding_pnl
    return {
        "variant": config.name,
        "group": config.group,
        "event_type": "btc_short_hedge",
        "symbol": "BTC",
        "side": "short",
        "entry_date": alpha.format_dt(position.entry_time),
        "exit_date": alpha.format_dt(exit_time),
        "signal_date": alpha.format_dt(position.signal_time),
        "entry_timestamp": position.entry_time,
        "exit_timestamp": exit_time,
        "signal_time": position.signal_time,
        "available_time": position.signal_time + 3600,
        "execution_time": position.entry_time,
        "lookahead_pass": position.signal_time < position.entry_time,
        "same_candle_signal_execution": False,
        "entry_reason": position.reason,
        "exit_reason": reason,
        "hedge_ratio": position.target_ratio,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "initial_notional": position.notional,
        "units": position.units,
        "gross_pnl": gross_pnl,
        "funding_pnl": position.funding_pnl,
        "pnl": pnl,
        "entry_fee": position.entry_fee,
        "exit_fee": exit_fee,
        "slippage_cost": position.entry_slippage_cost + exit_slippage_cost,
        "total_cost": total_cost,
        "funding_events": position.funding_events,
        "hold_days": (exit_time - position.entry_time) / 86400,
        "baseline_return_during_trade_pct": baseline_return(ctx, position.entry_time, exit_time) * 100,
        "_cash_delta": gross_pnl - exit_fee + position.funding_pnl,
    }


def open_reduction_legs(ctx: dict, config: HedgeConfig, open_time: int, signal_time: int, reduce_fraction: float) -> List[ReductionLeg]:
    legs = []
    for trade in active_long_trades(ctx, open_time):
        symbol = f"{trade['symbol']}USDT"
        row = ctx["spot_data"].by_time_1h.get(symbol, {}).get(open_time)
        if not row:
            continue
        units = active_trade_units(trade, open_time) * reduce_fraction
        if units <= 0:
            continue
        raw_price = row["open"]
        entry_price = raw_price * (1 - config.slippage_rate)
        notional = units * entry_price
        legs.append(
            ReductionLeg(
                symbol=symbol,
                units=units,
                entry_price=entry_price,
                entry_raw_price=raw_price,
                entry_time=open_time,
                signal_time=signal_time,
                entry_fee=notional * config.fee_rate,
                entry_slippage_cost=units * raw_price * config.slippage_rate,
            )
        )
    return legs


def close_reduction_legs(ctx: dict, config: HedgeConfig, legs: List[ReductionLeg], exit_time: int, reason: str) -> Tuple[List[dict], float]:
    rows = []
    cash_delta = 0.0
    for leg in legs:
        row = ctx["spot_data"].by_time_1h.get(leg.symbol, {}).get(exit_time)
        if not row:
            row = latest_row_before(ctx["spot_data"].rows_1h.get(leg.symbol, []), exit_time)
        if not row:
            continue
        raw_price = row.get("open", row["close"])
        exit_price = raw_price * (1 + config.slippage_rate)
        gross_pnl = leg.units * (leg.entry_price - exit_price)
        exit_fee = leg.units * exit_price * config.fee_rate
        exit_slippage_cost = leg.units * raw_price * config.slippage_rate
        pnl = gross_pnl - exit_fee - leg.entry_fee
        total_cost = leg.entry_fee + exit_fee + leg.entry_slippage_cost + exit_slippage_cost
        cash_delta += gross_pnl - exit_fee
        rows.append(
            {
                "variant": config.name,
                "group": config.group,
                "event_type": "long_reduction_overlay",
                "symbol": alpha.v1.short(leg.symbol) if hasattr(alpha, "v1") else leg.symbol.replace("USDT", ""),
                "side": "reduce_long",
                "entry_date": alpha.format_dt(leg.entry_time),
                "exit_date": alpha.format_dt(exit_time),
                "signal_date": alpha.format_dt(leg.signal_time),
                "entry_timestamp": leg.entry_time,
                "exit_timestamp": exit_time,
                "signal_time": leg.signal_time,
                "available_time": leg.signal_time + 3600,
                "execution_time": leg.entry_time,
                "lookahead_pass": leg.signal_time < leg.entry_time,
                "same_candle_signal_execution": False,
                "entry_reason": "shock_reduce_long_50pct",
                "exit_reason": reason,
                "hedge_ratio": config.reduce_long_fraction,
                "entry_price": leg.entry_price,
                "exit_price": exit_price,
                "initial_notional": leg.units * leg.entry_price,
                "units": leg.units,
                "gross_pnl": gross_pnl,
                "funding_pnl": 0.0,
                "pnl": pnl,
                "entry_fee": leg.entry_fee,
                "exit_fee": exit_fee,
                "slippage_cost": leg.entry_slippage_cost + exit_slippage_cost,
                "total_cost": total_cost,
                "funding_events": 0,
                "hold_days": (exit_time - leg.entry_time) / 86400,
                "baseline_return_during_trade_pct": baseline_return(ctx, leg.entry_time, exit_time) * 100,
                "_cash_delta": gross_pnl - exit_fee,
            }
        )
    return rows, cash_delta


def apply_btc_funding(ctx: dict, position: HedgePosition, end_time: int) -> Tuple[float, float, int]:
    times, rows = ctx["btc_funding_index"]
    start = getattr(position, "last_funding_time", position.entry_time)
    left = bisect_right(times, start)
    right = bisect_left(times, end_time)
    funding_pnl = 0.0
    for event in rows[left:right]:
        mark_price = event["mark_price"] or mark_price_for_btc(ctx, event["funding_time"]) or position.entry_price
        notional = position.units * mark_price
        funding_pnl += notional * event["funding_rate"]
        position.last_funding_time = event["funding_time"]
    return funding_pnl, funding_pnl, max(0, right - left)


def hedge_unrealized(config: HedgeConfig, position: Optional[HedgePosition], current_price: float) -> float:
    if not position:
        return 0.0
    exit_price = current_price * (1 + config.slippage_rate)
    return position.units * (position.entry_price - exit_price)


def reduction_unrealized(ctx: dict, legs: List[ReductionLeg], open_time: int) -> float:
    total = 0.0
    for leg in legs:
        row = ctx["spot_data"].by_time_1h.get(leg.symbol, {}).get(open_time)
        if row:
            total += leg.units * (leg.entry_price - row["close"])
    return total


def current_reduction_notional(ctx: dict, legs: List[ReductionLeg], open_time: int) -> float:
    total = 0.0
    for leg in legs:
        row = ctx["spot_data"].by_time_1h.get(leg.symbol, {}).get(open_time)
        if row:
            total += leg.units * row["close"]
    return total


def long_exposure(ctx: dict, timestamp: int, price_key: str = "close") -> float:
    if price_key == "open":
        return ctx["long_exposure_open"].get(timestamp, 0.0)
    return ctx["long_exposure_close"].get(timestamp, 0.0)


def active_long_trades(ctx: dict, timestamp: int) -> List[dict]:
    return ctx["active_long_by_time"].get(timestamp, [])


def active_trade_units(trade: dict, timestamp: int) -> float:
    units = float(trade.get("initial_units") or 0.0)
    partial_time = trade.get("partial_time")
    if partial_time not in {"", None} and timestamp >= int(partial_time):
        units *= 0.5
    return units


def build_active_trade_index(trades: List[dict]) -> Tuple[List[int], List[dict]]:
    ordered = sorted(trades, key=lambda row: int(row["entry_timestamp"]))
    return [int(row["entry_timestamp"]) for row in ordered], ordered


def baseline_equity_at(ctx: dict, timestamp: int) -> float:
    if timestamp in ctx["baseline_by_time"]:
        return ctx["baseline_by_time"][timestamp]
    times = ctx["baseline_times"]
    index = bisect_right(times, timestamp) - 1
    if index >= 0:
        return ctx["baseline_by_time"][times[index]]
    return 1.0


def baseline_peak_at(ctx: dict, timestamp: int) -> float:
    if timestamp in ctx["baseline_peak_by_time"]:
        return ctx["baseline_peak_by_time"][timestamp]
    times = ctx["baseline_times"]
    index = bisect_right(times, timestamp) - 1
    if index >= 0:
        return ctx["baseline_peak_by_time"][times[index]]
    return 1.0


def baseline_return(ctx: dict, start_time: int, end_time: int) -> float:
    start = baseline_equity_at(ctx, start_time)
    end = baseline_equity_at(ctx, end_time)
    return end / start - 1 if start else 0.0


def missed_upside_for_trade(ctx: dict, trade: dict) -> float:
    if baseline_return(ctx, int(trade["entry_timestamp"]), int(trade["exit_timestamp"])) > 0 and trade["pnl"] < 0:
        return -trade["pnl"]
    return 0.0


def btc_vol_ratio(ctx: dict, signal_time: int) -> Optional[float]:
    close_times = ctx["btc_daily_close_times"]
    index = bisect_right(close_times, signal_time) - 1
    if index < 0:
        return None
    row = ctx["btc_daily_features"][index]
    if row.get("atr_pct") is None or row.get("atr_pct_sma30") in {None, 0}:
        return None
    return row["atr_pct"] / row["atr_pct_sma30"]


def add_daily_vol_features(rows: List[dict]) -> List[dict]:
    out = [dict(row) for row in rows]
    atr14 = swing.atr(out, 14)
    atr_pct_values: List[Optional[float]] = []
    for index, row in enumerate(out):
        row["close_time"] = row["time"] + 86400
        row["atr14"] = atr14[index]
        row["atr_pct"] = atr14[index] / row["close"] if atr14[index] is not None and row["close"] else None
        atr_pct_values.append(row["atr_pct"])
    sma30 = rolling_average_optional(atr_pct_values, 30)
    for row, avg in zip(out, sma30):
        row["atr_pct_sma30"] = avg
    return out


def rolling_average_optional(values: Iterable[Optional[float]], period: int) -> List[Optional[float]]:
    out = []
    window: List[float] = []
    for value in values:
        if value is None:
            out.append(None)
            continue
        window.append(float(value))
        out.append(sum(window[-period:]) / period if len(window) >= period else None)
    return out


def mark_price_for_btc(ctx: dict, timestamp: int) -> Optional[float]:
    row = ctx["btc_futures_by_time"].get(timestamp)
    if row:
        return row["close"]
    rows = ctx["btc_futures_1h"]
    times = [row["time"] for row in rows]
    index = bisect_right(times, timestamp) - 1
    return rows[index]["close"] if index >= 0 else None


def latest_row_before(rows: List[dict], timestamp: int) -> Optional[dict]:
    times = [row["time"] for row in rows]
    index = bisect_right(times, timestamp) - 1
    return rows[index] if index >= 0 else None


def no_hedge_summary_row(ctx: dict, long_result: rb.RunResult, trades: List[dict], curve: List[dict], cashflows: List[dict]) -> dict:
    metrics = performance_metrics(ctx, curve, trades, "pnl_after_funding")
    return {
        "name": "Alpha Long v1.2 / No Hedge",
        "group": "No Hedge",
        "hedge_mode": "none",
        "hedge_ratio": 0.0,
        "max_hold_days": "",
        "slippage_rate_pct": BASE_SLIPPAGE * 100,
        "total_return_pct": metrics["total_return_pct"],
        "cagr_pct": metrics["cagr_pct"],
        "mdd_pct": metrics["mdd_pct"],
        "sharpe": metrics["sharpe"],
        "calmar": metrics["calmar"],
        "profit_factor": metrics["profit_factor"],
        "win_rate_pct": metrics["win_rate_pct"],
        "long_pnl": curve[-1]["equity"] - 1 if curve else 0.0,
        "hedge_pnl": 0.0,
        "hedge_funding_pnl": 0.0,
        "hedge_cost": 0.0,
        "hedge_net_benefit": 0.0,
        "reduction_pnl": 0.0,
        "missed_upside": 0.0,
        "hedge_trades": 0,
        "avg_hedge_hold_days": "",
        "mdd_reduction_pct": 0.0,
        "mdd_window_benefit_pct": 0.0,
        "cagr_damage_pct": 0.0,
        "avg_net_exposure_pct": "",
        "max_net_exposure_pct": "",
        "avg_gross_exposure_pct": "",
        "max_gross_exposure_pct": "",
        "skip_or_note": "baseline",
    }


def summary_row(ctx: dict, run: HedgeRun, no_hedge: dict, monthly: List[dict]) -> dict:
    metrics = performance_metrics(ctx, run.equity_curve, run.trades, "pnl")
    hedge_trades = [row for row in run.trades if row["event_type"] == "btc_short_hedge"]
    exposure = exposure_stats(run.exposure_rows)
    baseline_final = 1 + float(no_hedge["long_pnl"])
    final_equity = run.equity_curve[-1]["equity"] if run.equity_curve else 1.0
    no_mdd = abs(float(no_hedge["mdd_pct"]) / 100)
    this_mdd = abs(metrics["mdd_pct"] / 100)
    no_cagr = float(no_hedge["cagr_pct"] or 0.0)
    this_cagr = float(metrics["cagr_pct"] or 0.0)
    mdd_window_benefit = mdd_window_benefit_pct(ctx["baseline_curve"], run.equity_curve)
    return {
        "name": run.config.name,
        "group": run.config.group,
        "hedge_mode": run.config.mode,
        "hedge_ratio": run.config.fixed_ratio if run.config.fixed_ratio is not None else f"{run.config.ratio_low:.2f}/{run.config.ratio_high:.2f}",
        "max_hold_days": run.config.max_hold_days,
        "slippage_rate_pct": run.config.slippage_rate * 100,
        "total_return_pct": metrics["total_return_pct"],
        "cagr_pct": metrics["cagr_pct"],
        "mdd_pct": metrics["mdd_pct"],
        "sharpe": metrics["sharpe"],
        "calmar": metrics["calmar"],
        "profit_factor": metrics["profit_factor"],
        "win_rate_pct": metrics["win_rate_pct"],
        "long_pnl": baseline_final - 1,
        "hedge_pnl": run.hedge_pnl,
        "hedge_funding_pnl": run.hedge_funding_pnl,
        "hedge_cost": run.hedge_cost,
        "hedge_net_benefit": final_equity - baseline_final,
        "reduction_pnl": run.reduction_pnl,
        "missed_upside": run.missed_upside,
        "hedge_trades": len(hedge_trades),
        "avg_hedge_hold_days": mean_present([row["hold_days"] for row in hedge_trades]),
        "mdd_reduction_pct": (no_mdd - this_mdd) / no_mdd * 100 if no_mdd > 0 else 0.0,
        "mdd_window_benefit_pct": mdd_window_benefit,
        "cagr_damage_pct": (no_cagr - this_cagr) / abs(no_cagr) * 100 if no_cagr else 0.0,
        "avg_net_exposure_pct": exposure["avg_net_exposure_pct"],
        "max_net_exposure_pct": exposure["max_net_exposure_pct"],
        "avg_gross_exposure_pct": exposure["avg_gross_exposure_pct"],
        "max_gross_exposure_pct": exposure["max_gross_exposure_pct"],
        "skip_or_note": "",
    }


def performance_metrics(ctx: dict, curve: List[dict], trades: List[dict], pnl_key: str) -> dict:
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = (ctx["test_end_ts"] - ctx["test_start_ts"]) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [curve[index]["equity"] / curve[index - 1]["equity"] - 1 for index in range(1, len(curve)) if curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(curve)
    if trades and all("event_type" not in row for row in trades):
        pnls = [float(row.get(pnl_key, 0.0)) for row in trades]
    else:
        pnls = [float(row.get(pnl_key, 0.0)) for row in trades if row.get("event_type") == "btc_short_hedge"]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    return {
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(pnls) * 100 if pnls else 0.0,
    }


def mdd_window_benefit_pct(baseline_curve: List[dict], hedge_curve: List[dict]) -> float:
    peak_time, trough_time, baseline_return_value = drawdown_window(baseline_curve)
    if peak_time is None or trough_time is None:
        return 0.0
    hedge_start = curve_equity_at(hedge_curve, peak_time)
    hedge_end = curve_equity_at(hedge_curve, trough_time)
    hedge_return = hedge_end / hedge_start - 1 if hedge_start else 0.0
    return (hedge_return - baseline_return_value) * 100


def drawdown_window(curve: List[dict]) -> Tuple[Optional[int], Optional[int], float]:
    peak_equity = None
    peak_time = None
    worst_peak_time = None
    worst_trough_time = None
    worst_drawdown = 0.0
    for point in curve:
        equity = point["equity"]
        if peak_equity is None or equity > peak_equity:
            peak_equity = equity
            peak_time = point["time"]
        if peak_equity and peak_equity > 0:
            drawdown = equity / peak_equity - 1
            if drawdown < worst_drawdown:
                worst_drawdown = drawdown
                worst_peak_time = peak_time
                worst_trough_time = point["time"]
    return worst_peak_time, worst_trough_time, worst_drawdown


def curve_equity_at(curve: List[dict], timestamp: int) -> float:
    times = [row["time"] for row in curve]
    index = bisect_right(times, timestamp) - 1
    if index >= 0:
        return curve[index]["equity"]
    return curve[0]["equity"] if curve else 1.0


def exposure_stats(rows: List[dict]) -> dict:
    net = [abs(row["net_exposure"]) / row["equity"] * 100 for row in rows if row["equity"] > 0]
    gross = [row["gross_exposure"] / row["equity"] * 100 for row in rows if row["equity"] > 0]
    return {
        "avg_net_exposure_pct": mean_present(net),
        "max_net_exposure_pct": max(net) if net else None,
        "avg_gross_exposure_pct": mean_present(gross),
        "max_gross_exposure_pct": max(gross) if gross else None,
    }


def monthly_returns_from_curve(ctx: dict, name: str, group: str, funding_key: str, curve: List[dict]) -> List[dict]:
    month_end: Dict[str, float] = {}
    for point in curve:
        month = alpha.month_from_ts(point["time"])
        if alpha.MONTHS[0] <= month <= alpha.MONTHS[-1]:
            month_end[month] = point["equity"]
    rows = []
    previous = 1.0
    for month in alpha.MONTHS:
        equity = month_end.get(month, previous)
        rows.append({"name": name, "group": group, "funding": funding_key, "month": month, "return_pct": (equity / previous - 1) * 100 if previous else 0.0})
        previous = equity
    return rows


def yearly_rows_from_monthly(name: str, group: str, funding_key: str, monthly: List[dict]) -> List[dict]:
    yearly: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return [{"name": name, "group": group, "funding": funding_key, "year": year, "return_pct": (value - 1) * 100} for year, value in sorted(yearly.items())]


def pass_fail(summary_rows: List[dict]) -> List[dict]:
    no = next(row for row in summary_rows if row["name"] == "Alpha Long v1.2 / No Hedge")
    candidates = [row for row in summary_rows if row["name"] != no["name"] and row["group"] not in {"Slippage sensitivity", "Hedge ratio sensitivity", "Hold sensitivity"}]
    best_mdd = max(candidates, key=lambda row: row["mdd_reduction_pct"], default={})
    best_calmar = max(candidates, key=lambda row: row["calmar"] if row["calmar"] is not None else -999, default={})
    rows = []
    for row in candidates:
        rows.extend(
            [
                {
                    "variant": row["name"],
                    "check": "MDD reduction >= 15%",
                    "result": "PASS" if row["mdd_reduction_pct"] >= 15 else "FAIL",
                    "evidence": f"MDD reduction {row['mdd_reduction_pct']:.1f}%",
                },
                {
                    "variant": row["name"],
                    "check": "CAGR damage <= 20%",
                    "result": "PASS" if row["cagr_damage_pct"] <= 20 else "FAIL",
                    "evidence": f"CAGR damage {row['cagr_damage_pct']:.1f}%",
                },
                {
                    "variant": row["name"],
                    "check": "Calmar higher than No Hedge",
                    "result": "PASS" if (row["calmar"] or -999) > (no["calmar"] or -999) else "FAIL",
                    "evidence": f"Calmar {num(row['calmar'])} vs {num(no['calmar'])}",
                },
                {
                    "variant": row["name"],
                    "check": "Hedge net benefit positive",
                    "result": "PASS" if row["hedge_net_benefit"] > 0 else "FAIL",
                    "evidence": f"Net benefit {num(row['hedge_net_benefit'])}",
                },
                {
                    "variant": row["name"],
                    "check": "Cost-included effect maintained",
                    "result": "PASS" if row["hedge_net_benefit"] > 0 and row["mdd_reduction_pct"] > 0 else "FAIL",
                    "evidence": f"Net benefit {num(row['hedge_net_benefit'])}, cost {num(row['hedge_cost'])}, funding {num(row['hedge_funding_pnl'])}",
                },
                {
                    "variant": row["name"],
                    "check": "Hedge trade count",
                    "result": "WARNING" if row["hedge_trades"] / max(len(alpha.MONTHS), 1) > OVERTRADE_WARNING_MONTHLY else "PASS",
                    "evidence": f"Hedge trades {row['hedge_trades']}, monthly {row['hedge_trades'] / max(len(alpha.MONTHS), 1):.1f}",
                },
                {
                    "variant": row["name"],
                    "check": "Missed upside",
                    "result": "WARNING" if row["missed_upside"] > abs(row["hedge_net_benefit"]) and row["missed_upside"] > 0 else "PASS",
                    "evidence": f"Missed upside {num(row['missed_upside'])}",
                },
            ]
        )
    rows.append({"variant": "Best MDD", "check": "Best MDD reduction", "result": "INFO", "evidence": f"{best_mdd.get('name', '')}: {best_mdd.get('mdd_reduction_pct', 0):.1f}%"})
    rows.append({"variant": "Best Calmar", "check": "Best efficiency", "result": "INFO", "evidence": f"{best_calmar.get('name', '')}: Calmar {num(best_calmar.get('calmar'))}"})
    return rows


def build_report(ctx: dict, summary_rows: List[dict], trades: List[dict], monthly_rows: List[dict], yearly_rows: List[dict], pass_fail_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    primary = [row for row in summary_rows if row["group"] in {"No Hedge", "Regime hedge", "Shock hedge", "Drawdown hedge", "Volatility hedge", "Composite hedge"}]
    sensitivity = [row for row in summary_rows if row["group"] in {"Hedge ratio sensitivity", "Slippage sensitivity", "Hold sensitivity"}]
    lines = [
        "# Hedge Engine v0 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- Hedge Engine v0는 수익 엔진이 아니라 Alpha Long Engine v1.2 후보의 하락 리스크를 줄이는 방어 엔진 연구다.",
        "- Short Engine v0와 다르다. 목적은 BTC 숏으로 돈을 버는 것이 아니라 기존 롱 포지션의 MDD와 폭락 손실을 완화하는 것이다.",
        "- 기존 Alpha Long Engine v1.2 파일, Paper Engine 파일, Short Engine v0 파일은 수정하지 않았다.",
        "- 실제 주문 API 연결은 없고, Binance USD-M Futures BTCUSDT OHLCV/funding 데이터로만 백테스트했다.",
        "- 기준 Long: No DOGE, alpha_score top 20%, liquidation buffer, taker-only 0.05%, slippage 0.2%, actual funding.",
        "",
        "## 해석 메모",
        "",
        interpretation_notes(summary_rows),
        "",
        "## Pass / Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## 핵심 비교",
        "",
        summary_table(primary),
        "",
        "## 민감도",
        "",
        summary_table(sensitivity),
        "",
        "## Hedge Ratio별 성과",
        "",
        ratio_table(summary_rows),
        "",
        "## 진입 / 청산 사유",
        "",
        reason_table(trades),
        "",
        "## 룩어헤드 감사",
        "",
        lookahead_table(trades),
        "",
        "## 최악 월 Top 10",
        "",
        month_rank_table(monthly_rows, reverse=False),
        "",
        "## 최고 월 Top 10",
        "",
        month_rank_table(monthly_rows, reverse=True),
        "",
        "## MDD 방어 효과",
        "",
        drawdown_table(summary_rows),
        "",
        "## Net / Gross Exposure",
        "",
        exposure_table(summary_rows),
        "",
        "## 연도별 수익률",
        "",
        yearly_table(yearly_rows),
        "",
        "## 월별 수익률 최근 12개월",
        "",
        monthly_sample_table(monthly_rows),
        "",
        "## Hedge 거래 Top 20 손실",
        "",
        trade_table(sorted([row for row in trades if row["event_type"] == "btc_short_hedge"], key=lambda row: row["pnl"])[:20]),
        "",
        "## 산출물",
        "",
        "- `hedge_engine_v0_report.md`",
        "- `hedge_engine_v0_summary.csv`",
        "- `hedge_engine_v0_trades.csv`",
        "- `hedge_engine_v0_monthly.csv`",
        "- `hedge_engine_v0_yearly.csv`",
        "",
    ]
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Variant | Check | Result | Evidence |", "|---|---|---|---|"]
    for row in rows[:120]:
        lines.append(f"| {row['variant']} | {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def interpretation_notes(rows: List[dict]) -> str:
    shock_rows = [row for row in rows if row["group"] == "Shock hedge"]
    shock_trades = sum(int(row["hedge_trades"] or 0) for row in shock_rows)
    lines = [
        "- No Hedge 대비 방어 효과가 비용과 funding 반영 후 유지되는지를 기준으로 판단했다.",
        "- Hedge PnL은 BTC 숏 헤지 자체 손익이고, Long PnL은 기준 Alpha Long v1.2 후보의 funding 포함 손익이다.",
    ]
    if shock_trades == 0:
        lines.append("- Shock Hedge는 기존 Long v1.2 후보를 그대로 유지한 조건에서 BTC 헤지 거래가 0회였다. v1.2 기준 Long이 shock/no_new_entry 구간에서 이미 신규/보유 리스크를 크게 줄여, 다음 1H open에 헤지할 long exposure가 없었던 것으로 해석한다.")
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Name", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "Hedge PnL", "Funding", "Cost", "Net benefit", "Trades", "MDD red.", "CAGR damage"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["name"],
                    pct(row["total_return_pct"]),
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    num(row["hedge_pnl"]),
                    num(row["hedge_funding_pnl"]),
                    num(row["hedge_cost"]),
                    num(row["hedge_net_benefit"]),
                    str(row["hedge_trades"]),
                    pct(row["mdd_reduction_pct"]),
                    pct(row["cagr_damage_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def ratio_table(rows: List[dict]) -> str:
    selected = [row for row in rows if row["group"] in {"Regime hedge", "Hedge ratio sensitivity", "Composite hedge"}]
    lines = ["| Name | Ratio | CAGR | MDD | Calmar | Net benefit | Trades |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in selected:
        lines.append(f"| {row['name']} | {row['hedge_ratio']} | {pct(row['cagr_pct'])} | {pct(row['mdd_pct'])} | {num(row['calmar'])} | {num(row['hedge_net_benefit'])} | {row['hedge_trades']} |")
    return "\n".join(lines)


def reason_table(trades: List[dict]) -> str:
    grouped = Counter((row["entry_reason"], row["exit_reason"]) for row in trades if row["event_type"] == "btc_short_hedge")
    lines = ["| Entry reason | Exit reason | Trades |", "|---|---|---:|"]
    for (entry, exit_reason), count in grouped.most_common():
        lines.append(f"| {entry} | {exit_reason} | {count} |")
    return "\n".join(lines)


def lookahead_table(trades: List[dict]) -> str:
    hedge_trades = [row for row in trades if row["event_type"] == "btc_short_hedge"]
    lookahead_fail = sum(1 for row in hedge_trades if str(row.get("lookahead_pass")) not in {"True", "true", "1"})
    same_candle = sum(1 for row in hedge_trades if str(row.get("same_candle_signal_execution")) in {"True", "true", "1"})
    min_lag = min((int(row["execution_time"]) - int(row["signal_time"])) / 3600 for row in hedge_trades) if hedge_trades else 0.0
    return "\n".join(
        [
            "| Check | Value |",
            "|---|---:|",
            f"| Hedge trades | {len(hedge_trades)} |",
            f"| Lookahead failures | {lookahead_fail} |",
            f"| Same candle signal/execution | {same_candle} |",
            f"| Minimum signal-to-execution lag hours | {min_lag:.1f} |",
        ]
    )


def month_rank_table(rows: List[dict], reverse: bool) -> str:
    candidates = [row for row in rows if row["group"] in {"No Hedge", "Composite hedge", "Drawdown hedge", "Shock hedge"}]
    ranked = sorted(candidates, key=lambda row: row["return_pct"], reverse=reverse)[:10]
    lines = ["| Name | Month | Return |", "|---|---|---:|"]
    for row in ranked:
        lines.append(f"| {row['name']} | {row['month']} | {pct(row['return_pct'])} |")
    return "\n".join(lines)


def drawdown_table(rows: List[dict]) -> str:
    lines = ["| Name | MDD | MDD reduction | Baseline MDD window benefit | Hedge net benefit | Missed upside |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        if row["group"] == "No Hedge":
            continue
        lines.append(f"| {row['name']} | {pct(row['mdd_pct'])} | {pct(row['mdd_reduction_pct'])} | {pct(row['mdd_window_benefit_pct'])} | {num(row['hedge_net_benefit'])} | {num(row['missed_upside'])} |")
    return "\n".join(lines)


def exposure_table(rows: List[dict]) -> str:
    lines = ["| Name | Avg net | Max net | Avg gross | Max gross |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        if row["group"] == "No Hedge":
            continue
        lines.append(f"| {row['name']} | {pct(row['avg_net_exposure_pct'])} | {pct(row['max_net_exposure_pct'])} | {pct(row['avg_gross_exposure_pct'])} | {pct(row['max_gross_exposure_pct'])} |")
    return "\n".join(lines)


def yearly_table(rows: List[dict]) -> str:
    names = []
    for row in rows:
        if row["name"] not in names:
            names.append(row["name"])
    years = sorted({row["year"] for row in rows})
    lookup = {(row["name"], row["year"]): row["return_pct"] for row in rows}
    lines = ["| Name | " + " | ".join(years) + " |", "|" + "|".join(["---"] * (len(years) + 1)) + "|"]
    for name in names[:12]:
        lines.append("| " + " | ".join([name] + [pct(lookup.get((name, year))) for year in years]) + " |")
    return "\n".join(lines)


def monthly_sample_table(rows: List[dict]) -> str:
    names = []
    for row in rows:
        if row["name"] not in names:
            names.append(row["name"])
    months = alpha.MONTHS[-12:]
    lookup = {(row["name"], row["month"]): row["return_pct"] for row in rows}
    lines = ["| Name | " + " | ".join(months) + " |", "|" + "|".join(["---"] * (len(months) + 1)) + "|"]
    for name in names[:8]:
        lines.append("| " + " | ".join([name] + [pct(lookup.get((name, month))) for month in months]) + " |")
    return "\n".join(lines)


def trade_table(rows: List[dict]) -> str:
    if not rows:
        return "거래 없음."
    lines = ["| Variant | Entry | Exit | Reason | PnL | Funding | Cost | Hold |", "|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['variant']} | {row['entry_date']} | {row['exit_date']} | {row['entry_reason']}->{row['exit_reason']} | {num(row['pnl'])} | {num(row['funding_pnl'])} | {num(row['total_cost'])} | {num(row['hold_days'])} |")
    return "\n".join(lines)


def load_futures_raw(symbols: Iterable[str], interval: str, use_cache: bool, start: str) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, List[dict]] = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}_futures_{interval}.json"
        cached = read_cache(path) if use_cache else []
        if cached:
            out[symbol] = cached
            continue
        rows = fetch_futures_ohlcv(symbol, interval, start, alpha.FETCH_END)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        out[symbol] = rows
    return out


def fetch_futures_ohlcv(symbol: str, interval: str, start: str, end: str) -> List[dict]:
    if interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported interval: {interval}")
    start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end).timestamp() * 1000)
    cursor = start_ms
    rows: List[dict] = []
    while cursor < end_ms:
        batch = futures_klines_request(symbol, interval, cursor, end_ms)
        if not batch:
            break
        rows.extend(normalize_kline(item) for item in batch)
        next_cursor = int(batch[-1][0]) + INTERVAL_SECONDS[interval] * 1000
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.06)
    deduped = {row["time"]: row for row in rows}
    return [deduped[key] for key in sorted(deduped)]


def futures_klines_request(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    query = urlencode({"symbol": symbol, "interval": interval, "startTime": start_ms, "endTime": end_ms, "limit": 1000})
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
    return {"time": int(item[0]) // 1000, "open": float(item[1]), "high": float(item[2]), "low": float(item[3]), "close": float(item[4]), "volume": float(item[5])}


def read_cache(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def strip_private(row: dict) -> dict:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def dedupe_configs(configs: List[HedgeConfig]) -> List[HedgeConfig]:
    seen = set()
    out = []
    for config in configs:
        if config.name not in seen:
            seen.add(config.name)
            out.append(config)
    return out


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value not in {None, ""}]
    return statistics.mean(clean) if clean else None


def pct(value: Optional[float]) -> str:
    if value in {None, ""}:
        return ""
    return f"{float(value):.1f}%"


def num(value: Optional[float]) -> str:
    if value in {None, ""}:
        return ""
    return f"{float(value):.2f}"


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
