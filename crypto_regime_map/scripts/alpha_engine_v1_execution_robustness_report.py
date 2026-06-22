"""Execution robustness v1.1 report for Alpha Engine v1.

This standalone report keeps Alpha Engine v1 unchanged. It reuses the existing
4H alpha signals, then compares execution-only risk controls: DOGE exclusion,
symbol leverage caps, liquidation safety buffers, score percentile filtering,
and a conservative two-position v1.1 profile.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_2_defensive_probe as defensive_probe_rules  # noqa: E402
import alpha_engine_v1_futures_execution_audit_report as futures_audit  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_report as v1  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
SLIPPAGE_STRESS = (0.0005, 0.0010, 0.0020, 0.0030, 0.0050)
FUNDING_SCENARIOS = (
    ("funding_zero", "funding 0", None),
    ("actual_funding", "actual funding", "actual"),
    ("annual_cost_10", "conservative funding cost -10% annual", 0.10),
)
TAKER_FEE_RATE = 0.0005
MAINTENANCE_MARGIN_RATE = 0.005
LIQUIDATION_FEE_BUFFER = 0.001
LIQUIDATION_BUFFER_MULTIPLE = 0.50
MONTH_COUNT = len(alpha.MONTHS)
MAIN_SLIPPAGE = 0.0020
BASE_SLIPPAGE = 0.0005


SYMBOL_LEVERAGE_CAPS = {
    "BTCUSDT": 3.0,
    "ETHUSDT": 3.0,
    "SOLUSDT": 2.0,
    "BNBUSDT": 2.0,
    "XRPUSDT": 2.0,
    "LINKUSDT": 2.0,
    "AVAXUSDT": 2.0,
    "DOGEUSDT": 1.0,
    "ADAUSDT": 2.0,
    "TONUSDT": 2.0,
}


@dataclass(frozen=True)
class RobustVariant:
    name: str
    exclude_doge: bool = False
    use_symbol_leverage_cap: bool = False
    require_liquidation_buffer: bool = False
    top_score_pct: Optional[float] = None
    max_positions: int = alpha.MAX_POSITIONS
    defensive_probe: bool = False
    group: str = "Robustness"


@dataclass(frozen=True)
class RunConfig:
    variant: RobustVariant
    market_data: str
    slippage_rate: float
    fee_rate: float = TAKER_FEE_RATE
    global_max_leverage: float = 3.0


@dataclass
class RobustPosition:
    symbol: str
    units: float
    initial_units: float
    entry_price: float
    stop_price: float
    risk_distance: float
    risk_amount: float
    entry_time: int
    entry_index_1h: int
    entry_equity: float
    signal_time: int
    signal_score: float
    regime: str
    action_bias: str
    liquidation_leverage_used: float
    liquidation_price_est: float
    symbol_leverage_cap: float
    realized_pnl: float = 0.0
    partial_taken: bool = False
    partial_time: Optional[int] = None
    partial_price: Optional[float] = None


@dataclass
class RunResult:
    config: RunConfig
    trades: List[dict]
    equity_curve: List[dict]
    skip_counter: Counter = field(default_factory=Counter)
    probe_log: List[dict] = field(default_factory=list)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local OHLCV/funding JSON when available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = alpha.load_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    spot_data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)

    futures_raw_1d = futures_audit.load_futures_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    futures_raw_4h = futures_audit.load_futures_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    futures_raw_1h = futures_audit.load_futures_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    futures_data = alpha.AlphaData(raw_1d=futures_raw_1d, raw_4h=futures_raw_4h, raw_1h=futures_raw_1h)
    ACTIVE_DATA_BY_MARKET.update({"spot": spot_data, "futures": futures_data})

    funding_info = funding.load_funding_info(args.use_cache)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, args.use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }
    funding_index = build_time_index(funding_by_symbol, time_key="funding_time")

    variants = build_variants()
    run_results: List[RunResult] = []
    for variant in variants:
        for slippage in SLIPPAGE_STRESS:
            run_results.append(run_robust_engine(spot_data, RunConfig(variant=variant, market_data="spot", slippage_rate=slippage)))

    same_criteria_variants = [variants[0], variants[-1]]
    for variant in same_criteria_variants:
        run_results.append(run_robust_engine(futures_data, RunConfig(variant=variant, market_data="futures", slippage_rate=BASE_SLIPPAGE)))

    summary_rows: List[dict] = []
    trade_rows: List[dict] = []
    for result in run_results:
        liquidation_trades = annotate_liquidation(result.trades, result)
        for scenario_key, scenario_name, scenario_value in FUNDING_SCENARIOS:
            annotated, cashflows = annotate_funding_fast(liquidation_trades, funding_index, scenario_key, scenario_name, scenario_value)
            adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
            row = summary_row(result, annotated, adjusted_curve, scenario_key, scenario_name)
            summary_rows.append(row)
            if scenario_key in {"actual_funding", "annual_cost_10"}:
                trade_rows.extend(add_run_metadata(annotated, result, scenario_key, scenario_name))

    pass_fail_rows = pass_fail(summary_rows)
    report = build_report(summary_rows, trade_rows, pass_fail_rows)

    report_path = output_dir / "alpha_engine_v1_execution_robustness_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_engine_v1_execution_robustness_summary.csv", summary_rows)
    write_csv(output_dir / "alpha_engine_v1_execution_robustness_trades.csv", trade_rows)
    print(report_path)


def build_variants() -> List[RobustVariant]:
    return [
        RobustVariant("Original Alpha Engine v1 / 10 symbols", group="Original"),
        RobustVariant("No DOGE", exclude_doge=True),
        RobustVariant("No DOGE + symbol leverage cap", exclude_doge=True, use_symbol_leverage_cap=True),
        RobustVariant("No DOGE + liquidation safety buffer", exclude_doge=True, require_liquidation_buffer=True),
        RobustVariant("No DOGE + alpha_score top 20%", exclude_doge=True, top_score_pct=0.20),
        RobustVariant("No DOGE + top 20% + symbol leverage cap", exclude_doge=True, top_score_pct=0.20, use_symbol_leverage_cap=True),
        RobustVariant("No DOGE + top 20% + liquidation buffer", exclude_doge=True, top_score_pct=0.20, require_liquidation_buffer=True),
        RobustVariant(
            "Conservative v1.1",
            exclude_doge=True,
            use_symbol_leverage_cap=True,
            require_liquidation_buffer=True,
            top_score_pct=0.20,
            max_positions=2,
            group="Conservative v1.1",
        ),
    ]


def run_robust_engine(data: alpha.AlphaData, config: RunConfig) -> RunResult:
    cash = 1.0
    positions: Dict[str, RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    probe_log: List[dict] = []
    equity_curve = [{"time": alpha.TEST_START_TS, "date": alpha.format_dt(alpha.TEST_START_TS), "equity": 1.0}]

    signals_by_time = defaultdict(list)
    for signal in data.signals_for(SYMBOLS, "next_open"):
        signal = dict(signal)
        signal["variant"] = config.variant.name
        signals_by_time[signal["signal_time"]].append(signal)

    for index, time in enumerate(data.times_1h):
        close_time = time + 3600
        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(time)
            if not row:
                continue
            cash, closed = manage_position(data, config, positions[symbol], row, close_time, index, cash)
            if closed:
                trades.append(closed)
                positions.pop(symbol, None)

        if config.variant.max_positions and alpha.is_shock_date(data, alpha.date_from_ts(close_time)):
            for symbol in list(positions):
                row = data.by_time_1h.get(symbol, {}).get(time)
                if not row:
                    continue
                trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), close_time, index, "shock_exit")
                cash += trade.pop("_cash_delta")
                trades.append(trade)

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
        probe_decisions = defensive_probe_batch_decisions(data, batch, time) if config.variant.defensive_probe else {}
        if probe_decisions:
            for signal in batch:
                key = signal_key(signal)
                if key in probe_decisions:
                    probe_log.append(defensive_probe_log_row(signal, time, probe_decisions[key]))
        eligible_for_top = [
            signal
            for signal in batch
            if signal.get("regime_reason") != "defensive_reduce_risk"
            and not (config.variant.exclude_doge and signal["symbol"] == "DOGE")
        ]
        top_allowed = set()
        if config.variant.top_score_pct:
            top_n = max(1, math.ceil(len(eligible_for_top) * config.variant.top_score_pct))
            top_allowed = {signal_key(signal) for signal in eligible_for_top[:top_n]}

        for signal in batch:
            symbol = f"{signal['symbol']}USDT"
            if signal.get("regime_reason") == "defensive_reduce_risk":
                decision = probe_decisions.get(signal_key(signal))
                if not decision or not decision["probe_can_enter"]:
                    skip_counter[(decision or {}).get("block_reason") or "defensive_no_entry"] += 1
                    continue
            if config.variant.exclude_doge and symbol == "DOGEUSDT":
                skip_counter["doge_excluded"] += 1
                continue
            probe_can_enter = bool(probe_decisions.get(signal_key(signal), {}).get("probe_can_enter"))
            if config.variant.top_score_pct and signal_key(signal) not in top_allowed and not probe_can_enter:
                skip_counter["alpha_score_not_top_20pct"] += 1
                continue
            if symbol in positions or symbol in pending:
                skip_counter["already_open_or_pending"] += 1
                continue
            order = {**signal, "symbol": symbol, "fill_time": time}
            if signal_key(signal) in probe_decisions and probe_decisions[signal_key(signal)]["probe_can_enter"]:
                order["probe_can_enter"] = True
                order["size_multiplier"] = defensive_probe_rules.PROBE_SIZE_MULTIPLIER
                order["stop_atr_multiple"] = defensive_probe_rules.PROBE_STOP_ATR_MULTIPLE
            pending[symbol] = order

        due_orders = [order for order in pending.values() if order["fill_time"] == time]
        for order in sorted(due_orders, key=lambda item: item["alpha_score"], reverse=True):
            pending.pop(order["symbol"], None)
            if order["symbol"] in positions:
                skip_counter["already_open"] += 1
                continue
            if len(positions) >= config.variant.max_positions:
                skip_counter["max_positions"] += 1
                continue
            row = data.by_time_1h.get(order["symbol"], {}).get(time)
            if not row or row.get("atr14") is None:
                skip_counter["missing_1h_execution_data"] += 1
                continue
            equity = portfolio_equity(cash, positions, data, time)
            position, fee, reason = create_position(data, config, order, row, time, index, equity, positions)
            if not position:
                skip_counter[reason or "position_rejected"] += 1
                continue
            cash -= fee
            positions[position.symbol] = position

        equity_curve.append({"time": close_time, "date": alpha.format_dt(close_time), "equity": portfolio_equity(cash, positions, data, time)})

    last_time = data.times_1h[-1]
    last_index = len(data.times_1h) - 1
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(last_time)
        if row:
            trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), last_time + 3600, last_index, "end_of_test")
            cash += trade.pop("_cash_delta")
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": alpha.format_dt(last_time + 3600), "equity": cash})
    return RunResult(config=config, trades=trades, equity_curve=equity_curve, skip_counter=skip_counter, probe_log=probe_log)


def signal_key(signal: dict) -> Tuple[str, int]:
    return signal["symbol"], int(signal["signal_time"])


def defensive_probe_batch_decisions(data: alpha.AlphaData, batch: List[dict], fill_time: int) -> Dict[Tuple[str, int], dict]:
    decisions: Dict[Tuple[str, int], dict] = {}
    health_gate = defensive_probe_rules.health_gate_from_state({})
    defensive_signals = [
        signal
        for signal in batch
        if defensive_probe_rules.is_defensive_state(
            signal.get("trade_regime", ""),
            signal.get("trade_action_bias", ""),
            signal.get("regime_reason", ""),
        )
    ]
    selected_key = None
    for signal in sorted(defensive_signals, key=lambda item: (float(item.get("alpha_score") or 0.0), -int(item.get("rank") or 999)), reverse=True):
        key = signal_key(signal)
        btc = data.by_time_4h.get("BTCUSDT", {}).get(int(signal.get("signal_time") or fill_time) - 4 * 3600)
        decision = defensive_probe_rules.evaluate_candidate(
            signal,
            signal.get("trade_regime", ""),
            signal.get("trade_action_bias", ""),
            signal.get("regime_reason", ""),
            btc,
            health_gate,
            max_slot_available=selected_key is None,
        )
        if decision["probe_can_enter"]:
            selected_key = key
        decisions[key] = decision
    return decisions


def defensive_probe_log_row(signal: dict, timestamp: int, decision: dict) -> dict:
    return defensive_probe_rules.log_row(
        timestamp,
        f"{signal.get('symbol', '')}USDT",
        signal.get("trade_regime", ""),
        signal.get("trade_action_bias", ""),
        False,
        decision,
    )


def manage_position(
    data: alpha.AlphaData,
    config: RunConfig,
    position: RobustPosition,
    row: dict,
    close_time: int,
    index_1h: int,
    cash: float,
) -> Tuple[float, Optional[dict]]:
    if row["low"] <= position.stop_price:
        trade = close_trade(data, config, position, position.stop_price, close_time, index_1h, "stop")
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
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema50_exit")
            return cash + trade.pop("_cash_delta"), trade
        if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] < row_4h["ema20"]:
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema20_trailing_exit")
            return cash + trade.pop("_cash_delta"), trade
    if close_time - position.entry_time >= alpha.MAX_HOLD_HOURS * 3600:
        trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "max_hold")
        return cash + trade.pop("_cash_delta"), trade
    return cash, None


def create_position(
    data: alpha.AlphaData,
    config: RunConfig,
    order: dict,
    row: dict,
    fill_time: int,
    index_1h: int,
    equity: float,
    positions: Dict[str, RobustPosition],
) -> Tuple[Optional[RobustPosition], float, str]:
    raw_price = row["open"]
    entry_price = raw_price * (1 + config.slippage_rate)
    stop_atr_multiple = float(order.get("stop_atr_multiple") or alpha.STOP_ATR_MULTIPLE)
    atr_stop = entry_price - stop_atr_multiple * row["atr14"]
    swing_stop = row.get("swing_low20") or atr_stop
    stop_price = max(atr_stop, swing_stop)
    if stop_price >= entry_price:
        stop_price = atr_stop
    risk_distance = entry_price - stop_price
    if risk_distance <= 0:
        return None, 0.0, "invalid_stop"

    symbol_cap = symbol_leverage_cap(order["symbol"], config)
    liquidation_leverage = symbol_cap
    if config.variant.require_liquidation_buffer:
        safe_leverage = max_safe_liquidation_leverage(entry_price, stop_price)
        if safe_leverage is None or safe_leverage <= 1.0:
            return None, 0.0, "liquidation_buffer_unavailable"
        liquidation_leverage = min(liquidation_leverage, safe_leverage)

    size_multiplier = float(order.get("size_multiplier") or 1.0)
    base_risk = equity * alpha.BASE_RISK_PER_SYMBOL * size_multiplier
    open_risk = sum(position.risk_amount for position in positions.values())
    risk_budget = min(base_risk, max(0.0, equity * alpha.MAX_PORTFOLIO_RISK - open_risk))
    if risk_budget <= 0:
        return None, 0.0, "portfolio_risk_budget"

    risk_units = risk_budget / risk_distance
    risk_notional = risk_units * entry_price
    current_exposure = sum(position.units * position.entry_price for position in positions.values())
    global_notional = max(0.0, equity * config.global_max_leverage - current_exposure)
    symbol_notional = equity * liquidation_leverage
    notional = min(risk_notional, global_notional, symbol_notional)
    if notional <= 1e-12:
        return None, 0.0, "leverage_cap_no_capacity"

    units = notional / entry_price
    risk_amount = units * risk_distance
    fee = notional * config.fee_rate
    liquidation_price = liquidation_price_for(entry_price, liquidation_leverage)
    return (
        RobustPosition(
            symbol=order["symbol"],
            units=units,
            initial_units=units,
            entry_price=entry_price,
            stop_price=stop_price,
            risk_distance=risk_distance,
            risk_amount=risk_amount,
            entry_time=fill_time,
            entry_index_1h=index_1h,
            entry_equity=equity,
            signal_time=order["signal_time"],
            signal_score=order["alpha_score"],
            regime=order["trade_regime"],
            action_bias=order["trade_action_bias"],
            liquidation_leverage_used=liquidation_leverage,
            liquidation_price_est=liquidation_price,
            symbol_leverage_cap=symbol_cap,
        ),
        fee,
        "",
    )


def symbol_leverage_cap(symbol: str, config: RunConfig) -> float:
    if not config.variant.use_symbol_leverage_cap:
        return config.global_max_leverage
    return min(config.global_max_leverage, SYMBOL_LEVERAGE_CAPS.get(symbol, 2.0))


def max_safe_liquidation_leverage(entry_price: float, stop_price: float) -> Optional[float]:
    risk_distance = entry_price - stop_price
    target_liquidation = stop_price - LIQUIDATION_BUFFER_MULTIPLE * risk_distance
    denominator = 1 + MAINTENANCE_MARGIN_RATE + LIQUIDATION_FEE_BUFFER - target_liquidation / entry_price
    if denominator <= 0:
        return None
    return 1 / denominator


def liquidation_price_for(entry_price: float, leverage: float) -> float:
    if leverage <= 1:
        return 0.0
    return max(0.0, entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN_RATE + LIQUIDATION_FEE_BUFFER))


def close_trade(data: alpha.AlphaData, config: RunConfig, position: RobustPosition, exit_price: float, exit_time: int, index_1h: int, reason: str) -> dict:
    gross_pnl = position.units * (exit_price - position.entry_price)
    fee = position.units * exit_price * config.fee_rate
    total_pnl = position.realized_pnl + gross_pnl - fee
    quality = alpha.entry_quality(data, position.symbol, position.entry_time, position.entry_price)
    excursion = alpha.trade_excursion(data, position.symbol, position.entry_time, exit_time, position.entry_price)
    initial_notional = position.initial_units * position.entry_price
    actual_leverage = initial_notional / position.entry_equity if position.entry_equity else 0.0
    return {
        "variant": config.variant.name,
        "market_data": config.market_data,
        "slippage_rate_pct": config.slippage_rate * 100,
        "fee_rate_pct": config.fee_rate * 100,
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
        "alpha_score_bucket": score_bucket(position.signal_score),
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
        "configured_max_leverage": config.global_max_leverage,
        "symbol_leverage_cap": position.symbol_leverage_cap,
        "liquidation_leverage_used": position.liquidation_leverage_used,
        "liquidation_price_est": position.liquidation_price_est,
        "position_margin_at_cap": initial_notional / position.liquidation_leverage_used if position.liquidation_leverage_used else initial_notional,
        "partial_taken": position.partial_taken,
        "partial_time": position.partial_time or "",
        "partial_date": alpha.format_dt(position.partial_time) if position.partial_time else "",
        "partial_price": position.partial_price or "",
        "_cash_delta": total_pnl,
    }


def portfolio_equity(cash: float, positions: Dict[str, RobustPosition], data: alpha.AlphaData, time: int) -> float:
    equity = cash
    for symbol, position in positions.items():
        row = data.by_time_1h.get(symbol, {}).get(time)
        if row:
            equity += position.units * (row["close"] - position.entry_price)
    return equity


def annotate_liquidation(trades: List[dict], result: RunResult) -> List[dict]:
    data = ACTIVE_DATA_BY_MARKET[result.config.market_data]
    rows_1h_index = build_time_index(data.rows_1h)
    rows_4h_index = build_time_index(data.rows_4h)
    out = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        entry_time = int(trade["entry_timestamp"])
        exit_time = int(trade["exit_timestamp"])
        lows_1h = slice_time_index(rows_1h_index, symbol, entry_time, exit_time)
        lows_4h = slice_time_index(rows_4h_index, symbol, entry_time, exit_time)
        min_1h_low = min((row["low"] for row in lows_1h), default=None)
        min_4h_low = min((row["low"] for row in lows_4h), default=None)
        min_1h_open = min((row["open"] for row in lows_1h), default=None)
        liq_price = float(trade["liquidation_price_est"])
        stop_before_liq = float(trade["stop_price"]) > liq_price
        low_touched_1h = min_1h_low is not None and min_1h_low <= liq_price
        low_touched_4h = min_4h_low is not None and min_4h_low <= liq_price
        gap_liq_touch = min_1h_open is not None and min_1h_open <= liq_price
        liquidation_risk = (not stop_before_liq) or gap_liq_touch
        out.append(
            {
                **{key: value for key, value in trade.items() if not key.startswith("_")},
                "trade_index": index,
                "unique_trade_key": trade_key(trade),
                "stop_before_liquidation": stop_before_liq,
                "min_1h_low_during_hold": min_1h_low,
                "min_4h_low_during_hold": min_4h_low,
                "liquidation_low_touched_1h": low_touched_1h,
                "liquidation_low_touched_4h": low_touched_4h,
                "liquidation_gap_touch_1h_open": gap_liq_touch,
                "liquidation_risk": liquidation_risk,
            }
        )
    return out


ACTIVE_DATA_BY_MARKET: Dict[str, alpha.AlphaData] = {}


def build_time_index(rows_by_symbol: Dict[str, List[dict]], time_key: str = "time") -> Dict[str, Tuple[List[int], List[dict]]]:
    return {
        symbol: ([int(row[time_key]) for row in rows], rows)
        for symbol, rows in rows_by_symbol.items()
    }


def slice_time_index(index: Dict[str, Tuple[List[int], List[dict]]], symbol: str, start_time: int, end_time: int) -> List[dict]:
    times, rows = index.get(symbol, ([], []))
    left = bisect_left(times, start_time)
    right = bisect_left(times, end_time)
    return rows[left:right]


def annotate_funding_fast(
    trades: List[dict],
    funding_index: Dict[str, Tuple[List[int], List[dict]]],
    scenario_key: str,
    scenario_name: str,
    scenario_value,
) -> Tuple[List[dict], List[dict]]:
    annotated = []
    cashflows = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        events = slice_time_index(funding_index, symbol, int(trade["entry_timestamp"]), int(trade["exit_timestamp"]))
        funding_pnl = 0.0
        funding_abs_cost = 0.0
        for event in events:
            units = float(trade["initial_units"])
            partial_time = trade.get("partial_time")
            if partial_time not in {"", None} and event["funding_time"] >= int(partial_time):
                units *= 0.5
            mark_price = event["mark_price"] or float(trade["entry_price"])
            notional = units * mark_price
            rate = funding.scenario_rate(event, scenario_value)
            pnl = -notional * rate
            funding_pnl += pnl
            funding_abs_cost += max(-pnl, 0.0)
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
                **trade,
                "scenario": scenario_key,
                "scenario_name": scenario_name,
                "funding_event_count": len(events),
                "funding_pnl": funding_pnl,
                "funding_abs_cost": funding_abs_cost,
                "pnl_after_funding": pnl_after,
                "trade_return_after_funding_pct": pnl_after / entry_equity * 100 if entry_equity else 0.0,
                "pnl_sign_changed_by_funding": sign(float(trade["pnl"])) != sign(pnl_after),
            }
        )
    return annotated, cashflows


def summary_row(result: RunResult, trades: List[dict], equity_curve: List[dict], scenario_key: str, scenario_name: str) -> dict:
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
    pnl_key = "pnl_after_funding" if trades and "pnl_after_funding" in trades[0] else "pnl"
    pnls = [float(trade[pnl_key]) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    leverages = [float(trade["actual_leverage"]) for trade in trades]
    symbol_rows = symbol_stats(trades, pnl_key)
    concentration = max((row["positive_pnl_share_pct"] for row in symbol_rows), default=0.0)
    return {
        "variant": result.config.variant.name,
        "group": result.config.variant.group,
        "market_data": result.config.market_data,
        "slippage_rate_pct": result.config.slippage_rate * 100,
        "fee_rate_pct": result.config.fee_rate * 100,
        "funding_scenario": scenario_key,
        "funding_scenario_name": scenario_name,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trades": len(trades),
        "avg_monthly_trades": len(trades) / MONTH_COUNT,
        "avg_hold_days": mean_present([trade["hold_days"] for trade in trades]),
        "avg_leverage": statistics.mean(leverages) if leverages else None,
        "max_leverage": max(leverages) if leverages else None,
        "trades_gte_3x": sum(1 for value in leverages if value >= 3.0),
        "trades_gte_4x": sum(1 for value in leverages if value >= 4.0),
        "liquidation_risk_trades": sum(1 for trade in trades if truthy(trade.get("liquidation_risk"))),
        "skipped_trades": sum(result.skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(result.skip_counter.items())),
        "max_symbol_positive_pnl_share_pct": concentration,
    }


def add_run_metadata(trades: List[dict], result: RunResult, scenario_key: str, scenario_name: str) -> List[dict]:
    out = []
    for trade in trades:
        out.append(
            {
                **trade,
                "robustness_variant": result.config.variant.name,
                "market_data": result.config.market_data,
                "funding_scenario": scenario_key,
                "funding_scenario_name": scenario_name,
                "run_slippage_rate_pct": result.config.slippage_rate * 100,
                "run_fee_rate_pct": result.config.fee_rate * 100,
            }
        )
    return out


def pass_fail(summary_rows: List[dict]) -> List[dict]:
    lookup = {
        (row["variant"], row["market_data"], round(float(row["slippage_rate_pct"]), 6), row["funding_scenario"]): row
        for row in summary_rows
    }
    original_stress = lookup.get(("Original Alpha Engine v1 / 10 symbols", "spot", round(MAIN_SLIPPAGE * 100, 6), "actual_funding"), {})
    conservative_stress = lookup.get(("Conservative v1.1", "spot", round(MAIN_SLIPPAGE * 100, 6), "actual_funding"), {})
    conservative_base = lookup.get(("Conservative v1.1", "spot", round(BASE_SLIPPAGE * 100, 6), "actual_funding"), {})
    cagr_retention = (
        (conservative_stress.get("cagr_pct") or 0.0) / original_stress["cagr_pct"] * 100
        if original_stress.get("cagr_pct")
        else 0.0
    )
    trade_reduction = (
        (1 - conservative_stress.get("trades", 0) / original_stress["trades"]) * 100
        if original_stress.get("trades")
        else 0.0
    )
    concentration = conservative_stress.get("max_symbol_positive_pnl_share_pct") or 0.0
    return [
        {
            "check": "Slippage 0.2% Calmar >= 1.0",
            "result": "PASS" if (conservative_stress.get("calmar") or 0.0) >= 1.0 else "FAIL",
            "evidence": f"Conservative v1.1 spot actual funding 0.2% slippage Calmar {conservative_stress.get('calmar', 0.0):.2f}",
        },
        {
            "check": "Liquidation risk trades == 0",
            "result": "PASS" if conservative_stress.get("liquidation_risk_trades", 999) == 0 else "FAIL",
            "evidence": f"risk trades {conservative_stress.get('liquidation_risk_trades')}",
        },
        {
            "check": "Taker-only + actual funding Calmar >= 1.2",
            "result": "PASS" if (conservative_base.get("calmar") or 0.0) >= 1.2 else "FAIL",
            "evidence": f"base slippage Calmar {conservative_base.get('calmar', 0.0):.2f}",
        },
        {
            "check": "CAGR retention >= 70% of Original",
            "result": "PASS" if cagr_retention >= 70 else "FAIL",
            "evidence": f"retention {cagr_retention:.1f}% vs Original same stress",
        },
        {
            "check": "MDD within -35%",
            "result": "PASS" if (conservative_stress.get("mdd_pct") or -999) >= -35 else "FAIL",
            "evidence": f"MDD {conservative_stress.get('mdd_pct', 0.0):.1f}%",
        },
        {
            "check": "Trade count reduced by >= 30%",
            "result": "PASS" if trade_reduction >= 30 else "FAIL",
            "evidence": f"trade reduction {trade_reduction:.1f}% ({original_stress.get('trades')} -> {conservative_stress.get('trades')})",
        },
        {
            "check": "Symbol concentration < 50%",
            "result": "PASS" if concentration < 50 else "WARNING",
            "evidence": f"largest positive PnL share {concentration:.1f}%",
        },
    ]


def build_report(summary_rows: List[dict], trade_rows: List[dict], pass_fail_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    main_rows = [
        row
        for row in summary_rows
        if row["market_data"] == "spot" and nearly(row["slippage_rate_pct"], MAIN_SLIPPAGE * 100) and row["funding_scenario"] == "actual_funding"
    ]
    base_rows = [
        row
        for row in summary_rows
        if row["market_data"] == "spot" and nearly(row["slippage_rate_pct"], BASE_SLIPPAGE * 100) and row["funding_scenario"] == "actual_funding"
    ]
    conservative_slip_rows = [
        row
        for row in summary_rows
        if row["variant"] == "Conservative v1.1" and row["market_data"] == "spot" and row["funding_scenario"] == "actual_funding"
    ]
    funding10_rows = [
        row
        for row in summary_rows
        if row["market_data"] == "spot" and nearly(row["slippage_rate_pct"], MAIN_SLIPPAGE * 100) and row["funding_scenario"] == "annual_cost_10"
    ]
    same_criteria_rows = [
        row
        for row in summary_rows
        if row["variant"] in {"Original Alpha Engine v1 / 10 symbols", "Conservative v1.1"}
        and row["funding_scenario"] == "actual_funding"
        and nearly(row["slippage_rate_pct"], BASE_SLIPPAGE * 100)
    ]
    conservative_trades = [
        row
        for row in trade_rows
        if row["robustness_variant"] == "Conservative v1.1"
        and row["funding_scenario"] == "actual_funding"
        and row["market_data"] == "spot"
        and nearly(row["run_slippage_rate_pct"], MAIN_SLIPPAGE * 100)
    ]
    lines = [
        "# Alpha Engine v1 Execution Robustness v1.1 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 기존 Alpha Engine v1, funding audit, futures execution audit 파일은 수정하지 않았다.",
        "- 새 알파 조건은 추가하지 않고 기존 Alpha 신호를 주문 단계에서만 필터링했다.",
        "- 비용 기준은 taker-only 0.05%, funding은 실제 funding과 보수적 연 -10% 비용 시나리오를 비교했다.",
        "- `alpha_score 상위 20%`는 같은 4H 신호 시점의 후보 중 상위 20%만 주문으로 넘기는 방식이다.",
        "- 청산 안전거리는 `stop_price - liquidation_price >= 0.5 * 손절폭`을 만족하도록 isolated leverage를 자동 축소하고, 불가능하면 스킵한다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## Slippage 0.2% + Actual Funding 비교",
        "",
        summary_table(main_rows),
        "",
        "## Base Slippage 0.05% + Actual Funding 비교",
        "",
        summary_table(base_rows),
        "",
        "## Conservative v1.1 Slippage Stress",
        "",
        summary_table(conservative_slip_rows),
        "",
        "## 보수적 Funding 연 -10% 비교",
        "",
        summary_table(funding10_rows),
        "",
        "## Original vs v1.1 동일 기준 Spot/Futures",
        "",
        summary_table(same_criteria_rows),
        "",
        "## Calmar 1.60 vs 2.20 차이 원인",
        "",
        calmar_explanation(),
        "",
        "## Conservative v1.1 스킵 사유",
        "",
        skip_table(summary_rows, "Conservative v1.1"),
        "",
        "## Conservative v1.1 심볼별 성과",
        "",
        symbol_table(symbol_stats(conservative_trades, "pnl_after_funding")),
        "",
        "## Conservative v1.1 Alpha Score 구간별 성과",
        "",
        bucket_table(bucket_stats(conservative_trades, "alpha_score_bucket", "pnl_after_funding")),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_execution_robustness_report.md`",
        "- `alpha_engine_v1_execution_robustness_summary.csv`",
        "- `alpha_engine_v1_execution_robustness_trades.csv`",
        "",
    ]
    return "\n".join(lines)


def calmar_explanation() -> str:
    return "\n".join(
        [
            "| Item | Funding audit Calmar 1.60 | Futures execution audit Calmar 2.20 |",
            "|---|---|---|",
            "| 기준 variant | `Alpha Engine v1 / 10 symbols` actual funding | `Taker only fee 0.05% + actual funding` |",
            "| Trade set | Alpha10 1140 unique trades | 같은 Alpha10 1140 unique trades |",
            "| 비용 가정 | 기존 Alpha 기본 수수료 0.10%, 슬리피지 0.05% | taker-only 0.05%, 슬리피지 0.05% |",
            "| OHLCV 기준 | Spot OHLCV equity curve에 funding overlay | Spot OHLCV, 실행 감사 내 수수료 변경 후 funding overlay |",
            "| 핵심 원인 | funding 비용이 성과를 낮춘 기준선 | 수수료가 0.10%에서 0.05%로 낮아져 CAGR/MDD가 개선됨 |",
        ]
    )


def summary_table(rows: List[dict]) -> str:
    headers = ["Variant", "Market", "Slip", "Funding", "CAGR", "MDD", "Sharpe", "Calmar", "PF", "Trades", "Monthly", "Hold", "Avg lev", "Max lev", ">=3x", ">=4x", "Liq risk", "Skipped", "Max symbol"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["variant"],
            row["market_data"],
            pct_rate(row["slippage_rate_pct"]),
            row["funding_scenario"],
            pct(row["cagr_pct"]),
            pct(row["mdd_pct"]),
            num(row["sharpe"]),
            num(row["calmar"]),
            num(row["profit_factor"]),
            str(row["trades"]),
            num(row["avg_monthly_trades"]),
            num(row["avg_hold_days"]),
            num(row["avg_leverage"]),
            num(row["max_leverage"]),
            str(row["trades_gte_3x"]),
            str(row["trades_gte_4x"]),
            str(row["liquidation_risk_trades"]),
            str(row["skipped_trades"]),
            pct(row["max_symbol_positive_pnl_share_pct"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def skip_table(summary_rows: List[dict], variant: str) -> str:
    rows = [
        row
        for row in summary_rows
        if row["variant"] == variant and row["market_data"] == "spot" and row["funding_scenario"] == "actual_funding"
    ]
    lines = ["| Slip | Skipped | Reasons |", "|---:|---:|---|"]
    for row in rows:
        lines.append(f"| {pct_rate(row['slippage_rate_pct'])} | {row['skipped_trades']} | {row['skip_reasons']} |")
    return "\n".join(lines)


def symbol_stats(trades: List[dict], pnl_key: str) -> List[dict]:
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["symbol"]].append(trade)
    positive_total = sum(max(sum(float(item[pnl_key]) for item in items), 0.0) for items in grouped.values())
    rows = []
    for symbol, items in grouped.items():
        pnls = [float(item[pnl_key]) for item in items]
        rows.append(
            {
                "symbol": symbol,
                "trades": len(items),
                "pnl": sum(pnls),
                "positive_pnl_share_pct": max(sum(pnls), 0.0) / positive_total * 100 if positive_total > 0 else 0.0,
                "mdd_contribution": symbol_mdd_contribution(items, pnl_key),
            }
        )
    return sorted(rows, key=lambda row: row["pnl"], reverse=True)


def symbol_mdd_contribution(trades: List[dict], pnl_key: str) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for trade in sorted(trades, key=lambda item: int(item["exit_timestamp"])):
        cumulative += float(trade[pnl_key])
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def symbol_table(rows: List[dict]) -> str:
    lines = ["| Symbol | Trades | PnL | Positive PnL share | MDD contribution |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['symbol']} | {row['trades']} | {num(row['pnl'])} | {pct(row['positive_pnl_share_pct'])} | {num(row['mdd_contribution'])} |")
    return "\n".join(lines)


def bucket_stats(trades: List[dict], key: str, pnl_key: str) -> List[dict]:
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade[key]].append(trade)
    rows = []
    for bucket, items in grouped.items():
        pnls = [float(item[pnl_key]) for item in items]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        rows.append(
            {
                "bucket": bucket,
                "trades": len(items),
                "pnl": sum(pnls),
                "win_rate_pct": len(wins) / len(items) * 100 if items else 0.0,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            }
        )
    return sorted(rows, key=lambda row: row["bucket"])


def bucket_table(rows: List[dict]) -> str:
    lines = ["| Alpha score bucket | Trades | PnL | Win rate | PF |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['bucket']} | {row['trades']} | {num(row['pnl'])} | {pct(row['win_rate_pct'])} | {num(row['profit_factor'])} |")
    return "\n".join(lines)


def score_bucket(score: float) -> str:
    if score < 6:
        return "5-6"
    if score < 7:
        return "6-7"
    if score < 8:
        return "7-8"
    return "8+"


def trade_key(trade: dict) -> str:
    return "|".join([str(trade.get("symbol", "")), str(trade.get("entry_timestamp", "")), str(trade.get("exit_timestamp", "")), str(trade.get("exit_reason", ""))])


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def nearly(value, target: float) -> bool:
    return abs(float(value) - target) < 1e-9


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and value != ""]
    return statistics.mean(clean) if clean else None


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    text = f"{float(value):.1f}"
    return f"{text}%"


def pct_rate(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


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
