"""Alpha Short Engine v0 research report.

Standalone short-only research module. It does not import or modify the
Alpha Long Engine v1.2 or Paper Engine files, and it does not place orders.
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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from indicators import ema  # noqa: E402
from regime import build_payload_from_raw  # noqa: E402


FAPI_BASE_URLS = ("https://fapi.binance.com",)
FETCH_DAILY_START = "2018-01-01T00:00:00+00:00"
FETCH_INTRADAY_START = "2019-01-01T00:00:00+00:00"
TEST_START = "2020-01-01T00:00:00+00:00"
TEST_START_TS = int(datetime.fromisoformat(TEST_START).timestamp())
BASE_UNIVERSE_4 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
BASE_UNIVERSE_9 = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "ADAUSDT",
    "TONUSDT",
)
INTERVAL_SECONDS = {"1d": 86400, "4h": 14400, "1h": 3600}

TAKER_FEE_RATE = 0.0005
BASE_SLIPPAGE = 0.0020
SLIPPAGE_SENSITIVITY = (0.0010, 0.0020, 0.0030, 0.0050)
RISK_PER_SYMBOL = 0.005
MAX_PORTFOLIO_RISK = 0.010
MAX_POSITIONS = 2
MAX_APPLIED_LEVERAGE = 4
MIN_SHORT_ALPHA_SCORE = 6.0
TOP_SCORE_PCT = 0.20
OVEREXTENSION_ATR_MULTIPLE = 2.0
STOP_ATR_MULTIPLE = 2.0
SWING_HIGH_LOOKBACK = 20
BOUNCE_LOOKBACK_4H = 10
BOUNCE_ATR_TOLERANCE = 0.25
MAINTENANCE_MARGIN_RATE = 0.005
LIQUIDATION_FEE_BUFFER = 0.001
LIQUIDATION_BUFFER_MULTIPLE = 0.50
MIN_TRADES_FOR_DATA = 20


@dataclass(frozen=True)
class ShortConfig:
    name: str
    universe: Tuple[str, ...]
    group: str = "Short Engine v0"
    fill_mode: str = "next_open"
    shock_mode: str = "forbid_new"
    max_hold_days: int = 7
    slippage_rate: float = BASE_SLIPPAGE
    fee_rate: float = TAKER_FEE_RATE


@dataclass
class Position:
    symbol: str
    units: float
    initial_units: float
    entry_price: float
    stop_price: float
    risk_distance: float
    risk_amount: float
    entry_time: int
    entry_candle_time: int
    entry_index_1h: int
    entry_equity: float
    signal_id: str
    signal_time: int
    signal_candle_time: int
    available_time: int
    four_h_signal_time: int
    short_alpha_score: float
    trade_regime: str
    trade_action_bias: str
    downtrend_score: float
    relative_weakness_score: float
    rejection_score: float
    volume_score: float
    risk_distance_score: float
    raw_leverage: float
    applied_leverage: int
    initial_notional: float
    entry_fee: float
    liquidation_price_est: float
    realized_pnl: float = 0.0
    partial_taken: bool = False
    partial_time: Optional[int] = None
    partial_price: Optional[float] = None


@dataclass
class RunResult:
    config: ShortConfig
    trades: List[dict]
    equity_curve: List[dict]
    signals: List[dict]
    skip_counter: Counter = field(default_factory=Counter)


class ShortData:
    def __init__(self, raw_1d: Dict[str, List[dict]], raw_4h: Dict[str, List[dict]], raw_1h: Dict[str, List[dict]]):
        self.raw_1d = raw_1d
        self.raw_4h = raw_4h
        self.raw_1h = raw_1h
        self.rows_4h = {symbol: add_4h_features(rows) for symbol, rows in raw_4h.items()}
        self.rows_1h = {symbol: add_1h_features(rows) for symbol, rows in raw_1h.items()}
        self.by_time_1h = {symbol: {row["time"]: row for row in rows} for symbol, rows in self.rows_1h.items()}
        self.by_close_4h = {symbol: {row["close_time"]: row for row in rows} for symbol, rows in self.rows_4h.items()}
        self.close_times_4h = sorted({row["close_time"] for row in self.rows_4h.get("BTCUSDT", [])})
        self.times_1h = self._common_1h_times()
        self.test_end_ts = (self.times_1h[-1] + 3600) if self.times_1h else TEST_START_TS
        self.months = month_range(month_from_ts(TEST_START_TS), month_from_ts(max(TEST_START_TS, self.test_end_ts - 1)))
        self.regime_by_date = build_trade_regime(raw_1d)
        self.signal_cache: Dict[Tuple[Tuple[str, ...], str, str], List[dict]] = {}

    def _common_1h_times(self) -> List[int]:
        base = [row["time"] for row in self.rows_1h.get("BTCUSDT", []) if row["time"] >= TEST_START_TS]
        available = {symbol: set(rows_by_time) for symbol, rows_by_time in self.by_time_1h.items()}
        out = []
        for timestamp in base:
            if all(timestamp in available.get(symbol, set()) for symbol in BASE_UNIVERSE_9 if symbol in self.by_time_1h):
                out.append(timestamp)
        return out

    def latest_4h_rows(self, close_time: int, universe: Tuple[str, ...]) -> Tuple[Optional[int], Dict[str, dict]]:
        index = bisect_right(self.close_times_4h, close_time) - 1
        if index < 0:
            return None, {}
        four_h_close = self.close_times_4h[index]
        return four_h_close, {
            symbol: self.by_close_4h.get(symbol, {}).get(four_h_close)
            for symbol in universe
            if self.by_close_4h.get(symbol, {}).get(four_h_close)
        }

    def signals_for(self, config: ShortConfig) -> List[dict]:
        key = (config.universe, config.fill_mode, config.shock_mode)
        if key not in self.signal_cache:
            self.signal_cache[key] = build_signals(self, config)
        return [dict(row) for row in self.signal_cache[key]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use cached USD-M futures OHLCV/funding data when available.")
    parser.add_argument("--end", default=None, help="Optional ISO UTC end time for fresh Binance downloads.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_end = args.end or (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00+00:00")
    raw_1d = load_futures_raw(BASE_UNIVERSE_9, "1d", args.use_cache, FETCH_DAILY_START, fetch_end)
    raw_4h = load_futures_raw(BASE_UNIVERSE_9, "4h", args.use_cache, FETCH_INTRADAY_START, fetch_end)
    raw_1h = load_futures_raw(BASE_UNIVERSE_9, "1h", args.use_cache, FETCH_INTRADAY_START, fetch_end)
    data = ShortData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)

    funding_info = load_funding_info(args.use_cache)
    funding_by_symbol = {
        symbol: load_funding_history(symbol, args.use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"), data.test_end_ts)
        for symbol in BASE_UNIVERSE_9
    }
    funding_index = build_time_index(funding_by_symbol, "funding_time")

    configs = build_configs()
    run_results = [run_short_engine(data, config) for config in configs]

    summary_rows: List[dict] = []
    trade_rows: List[dict] = []
    monthly_rows: List[dict] = []
    yearly_rows: List[dict] = []
    signal_rows: List[dict] = []
    for result in run_results:
        liquidated = annotate_liquidation(data, result.trades)
        for funding_key, funding_name, include_funding in (("excluded", "funding excluded", False), ("actual", "actual funding", True)):
            annotated, cashflows = annotate_funding(data, liquidated, funding_index, include_funding)
            curve = adjusted_equity_curve(result.equity_curve, cashflows)
            summary_rows.append(summary_row(data, result, annotated, curve, funding_key, funding_name))
            monthly = monthly_returns_from_curve(data, result.config.name, result.config.group, funding_key, curve)
            yearly = yearly_rows_from_monthly(result.config.name, result.config.group, funding_key, monthly)
            monthly_rows.extend(monthly)
            yearly_rows.extend(yearly)
            if include_funding and should_export_trades(result.config):
                trade_rows.extend(add_trade_run_metadata(annotated, result.config, funding_key, funding_name))
        if should_export_signals(result.config):
            signal_rows.extend(result.signals)

    benchmark_runs = build_benchmarks(data)
    summary_rows.extend(row["summary"] for row in benchmark_runs)
    monthly_rows.extend(row for item in benchmark_runs for row in item["monthly"])
    yearly_rows.extend(row for item in benchmark_runs for row in item["yearly"])

    reference_rows = load_alpha_long_reference(output_dir)
    pass_fail_rows = pass_fail(summary_rows, yearly_rows)
    report = build_report(data, summary_rows, trade_rows, signal_rows, monthly_rows, yearly_rows, pass_fail_rows, reference_rows, funding_by_symbol)

    report_path = output_dir / "alpha_short_engine_v0_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_short_engine_v0_summary.csv", summary_rows + reference_rows)
    write_csv(output_dir / "alpha_short_engine_v0_trades.csv", trade_rows)
    write_csv(output_dir / "alpha_short_engine_v0_signals.csv", signal_rows)
    write_csv(output_dir / "alpha_short_engine_v0_monthly.csv", monthly_rows)
    write_csv(output_dir / "alpha_short_engine_v0_yearly.csv", yearly_rows)
    print(report_path)


def build_configs() -> List[ShortConfig]:
    base = [
        ShortConfig("Short Engine v0 / 4 symbols", BASE_UNIVERSE_4),
        ShortConfig("Short Engine v0 / 9 symbols", BASE_UNIVERSE_9),
        ShortConfig("Short Engine v0 / 4 symbols / shock forced flat", BASE_UNIVERSE_4, group="Shock comparison", shock_mode="force_flat"),
        ShortConfig("Short Engine v0 / 9 symbols / shock forced flat", BASE_UNIVERSE_9, group="Shock comparison", shock_mode="force_flat"),
        ShortConfig("Short Engine v0 / 4 symbols / shock allow comparison", BASE_UNIVERSE_4, group="Shock comparison", shock_mode="allow_new"),
        ShortConfig("Short Engine v0 / 9 symbols / shock allow comparison", BASE_UNIVERSE_9, group="Shock comparison", shock_mode="allow_new"),
        ShortConfig("Short Engine v0 / 4 symbols / next 1H close", BASE_UNIVERSE_4, group="Timing comparison", fill_mode="next_close"),
        ShortConfig("Short Engine v0 / 9 symbols / next 1H close", BASE_UNIVERSE_9, group="Timing comparison", fill_mode="next_close"),
        ShortConfig("Short Engine v0 / 4 symbols / max hold 10d", BASE_UNIVERSE_4, group="Hold comparison", max_hold_days=10),
        ShortConfig("Short Engine v0 / 9 symbols / max hold 10d", BASE_UNIVERSE_9, group="Hold comparison", max_hold_days=10),
    ]
    cost = [
        ShortConfig(
            f"Short Engine v0 / 4 symbols / slippage {slippage * 100:.1f}%",
            BASE_UNIVERSE_4,
            group="Slippage sensitivity",
            slippage_rate=slippage,
        )
        for slippage in SLIPPAGE_SENSITIVITY
    ] + [
        ShortConfig(
            f"Short Engine v0 / 9 symbols / slippage {slippage * 100:.1f}%",
            BASE_UNIVERSE_9,
            group="Slippage sensitivity",
            slippage_rate=slippage,
        )
        for slippage in SLIPPAGE_SENSITIVITY
    ]
    return dedupe_configs(base + cost)


def should_export_trades(config: ShortConfig) -> bool:
    return (
        config.name in {"Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols"}
        or config.group in {"Shock comparison", "Timing comparison", "Hold comparison"}
    )


def should_export_signals(config: ShortConfig) -> bool:
    return config.name in {"Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols"} or config.group == "Shock comparison"


def run_short_engine(data: ShortData, config: ShortConfig) -> RunResult:
    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[dict] = []
    skip_counter: Counter = Counter()
    signals = data.signals_for(config)
    signals_by_execution = defaultdict(list)
    signal_status = {}
    for signal in signals:
        signal["run_name"] = config.name
        signal["run_group"] = config.group
        signal["entered"] = False
        signal["skip_reason"] = signal.get("pre_trade_skip_reason", "")
        signal_status[signal["signal_id"]] = signal
        signals_by_execution[signal["execution_candle_time"]].append(signal)
        if signal["skip_reason"]:
            skip_counter[signal["skip_reason"]] += 1

    equity_curve = [{"time": TEST_START_TS, "date": format_dt(TEST_START_TS), "equity": 1.0}]
    index_by_time = {timestamp: index for index, timestamp in enumerate(data.times_1h)}

    for open_time in data.times_1h:
        index_1h = index_by_time[open_time]
        close_time = open_time + 3600

        due_open = [signal for signal in signals_by_execution.get(open_time, []) if signal["fill_mode"] == "next_open"]
        cash = process_entries(data, config, due_open, positions, cash, open_time, index_1h, skip_counter, signal_status)

        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(open_time)
            if not row:
                continue
            cash, closed = manage_position(data, config, positions[symbol], row, open_time, close_time, index_1h, cash)
            if closed:
                trades.append(closed)
                positions.pop(symbol, None)

        cash = apply_regime_exits(data, config, positions, trades, cash, open_time, close_time, index_1h)

        due_close = [signal for signal in signals_by_execution.get(open_time, []) if signal["fill_mode"] == "next_close"]
        cash = process_entries(data, config, due_close, positions, cash, open_time, index_1h, skip_counter, signal_status)

        equity_curve.append({"time": close_time, "date": format_dt(close_time), "equity": portfolio_equity(cash, positions, data, open_time)})

    if data.times_1h:
        last_open = data.times_1h[-1]
        last_close = last_open + 3600
        last_index = len(data.times_1h) - 1
        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(last_open)
            if row:
                trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 + config.slippage_rate), last_close, last_open, last_index, "end_of_test")
                cash += trade.pop("_cash_delta")
                trades.append(trade)
        equity_curve.append({"time": last_close, "date": format_dt(last_close), "equity": cash})

    for trade in trades:
        signal = signal_status.get(trade["signal_id"])
        if signal:
            signal["entered"] = True
            signal["skip_reason"] = ""
            signal["entry_time"] = trade["entry_timestamp"]
            signal["entry_date"] = trade["entry_date"]

    return RunResult(config=config, trades=trades, equity_curve=equity_curve, signals=list(signal_status.values()), skip_counter=skip_counter)


def process_entries(
    data: ShortData,
    config: ShortConfig,
    due_signals: List[dict],
    positions: Dict[str, Position],
    cash: float,
    open_time: int,
    index_1h: int,
    skip_counter: Counter,
    signal_status: Dict[str, dict],
) -> float:
    for signal in sorted(due_signals, key=lambda row: row["short_alpha_score"], reverse=True):
        status = signal_status[signal["signal_id"]]
        if status.get("skip_reason"):
            continue
        symbol = signal["symbol"]
        if symbol in positions:
            status["skip_reason"] = "already_open"
            skip_counter["already_open"] += 1
            continue
        if len(positions) >= MAX_POSITIONS:
            status["skip_reason"] = "max_positions"
            skip_counter["max_positions"] += 1
            continue
        row = data.by_time_1h.get(symbol, {}).get(open_time)
        if not row:
            status["skip_reason"] = "missing_execution_1h"
            skip_counter["missing_execution_1h"] += 1
            continue
        equity = portfolio_equity(cash, positions, data, open_time)
        position, fee, reason = create_position(data, config, signal, row, open_time, index_1h, equity, positions)
        if not position:
            status["skip_reason"] = reason
            skip_counter[reason] += 1
            continue
        cash -= fee
        positions[symbol] = position
    return cash


def create_position(
    data: ShortData,
    config: ShortConfig,
    signal: dict,
    row: dict,
    open_time: int,
    index_1h: int,
    equity: float,
    positions: Dict[str, Position],
) -> Tuple[Optional[Position], float, str]:
    if row.get("atr14") is None:
        return None, 0.0, "missing_atr"
    raw_price = row["open"] if signal["fill_mode"] == "next_open" else row["close"]
    entry_time = open_time if signal["fill_mode"] == "next_open" else open_time + 3600
    entry_price = raw_price * (1 - config.slippage_rate)
    swing_stop = row.get("swing_high20") or (entry_price + STOP_ATR_MULTIPLE * row["atr14"])
    stop_trigger = max(swing_stop, entry_price + STOP_ATR_MULTIPLE * row["atr14"])
    stop_fill_price = stop_trigger * (1 + config.slippage_rate)
    risk_distance = stop_fill_price - entry_price
    if risk_distance <= 0:
        return None, 0.0, "invalid_stop"

    base_risk = equity * RISK_PER_SYMBOL
    open_risk = sum(position.risk_amount for position in positions.values())
    risk_budget = min(base_risk, max(0.0, equity * MAX_PORTFOLIO_RISK - open_risk))
    if risk_budget <= 0:
        return None, 0.0, "portfolio_risk_budget"

    risk_notional = risk_budget / risk_distance * entry_price
    raw_leverage = risk_notional / equity if equity else MAX_APPLIED_LEVERAGE
    applied_leverage = int(max(1, min(MAX_APPLIED_LEVERAGE, math.ceil(raw_leverage))))
    current_notional = sum(position.initial_notional for position in positions.values())
    notional = min(risk_notional, max(0.0, equity * applied_leverage - current_notional))
    if notional <= 1e-12:
        return None, 0.0, "leverage_capacity"

    liquidation_price = short_liquidation_price(entry_price, applied_leverage)
    required_liq = stop_fill_price + LIQUIDATION_BUFFER_MULTIPLE * risk_distance
    if liquidation_price <= required_liq:
        return None, 0.0, "liquidation_buffer_failed"

    units = notional / entry_price
    risk_amount = units * risk_distance
    fee = notional * config.fee_rate
    return (
        Position(
            symbol=signal["symbol"],
            units=units,
            initial_units=units,
            entry_price=entry_price,
            stop_price=stop_fill_price,
            risk_distance=risk_distance,
            risk_amount=risk_amount,
            entry_time=entry_time,
            entry_candle_time=open_time,
            entry_index_1h=index_1h,
            entry_equity=equity,
            signal_id=signal["signal_id"],
            signal_time=signal["signal_time"],
            signal_candle_time=signal["signal_candle_time"],
            available_time=signal["available_time"],
            four_h_signal_time=signal["four_h_signal_time"],
            short_alpha_score=signal["short_alpha_score"],
            trade_regime=signal["trade_regime"],
            trade_action_bias=signal["trade_action_bias"],
            downtrend_score=signal["downtrend_score"],
            relative_weakness_score=signal["relative_weakness_score"],
            rejection_score=signal["rejection_score"],
            volume_score=signal["volume_score"],
            risk_distance_score=signal["risk_distance_score"],
            raw_leverage=raw_leverage,
            applied_leverage=applied_leverage,
            initial_notional=notional,
            entry_fee=fee,
            liquidation_price_est=liquidation_price,
        ),
        fee,
        "",
    )


def manage_position(
    data: ShortData,
    config: ShortConfig,
    position: Position,
    row: dict,
    open_time: int,
    close_time: int,
    index_1h: int,
    cash: float,
) -> Tuple[float, Optional[dict]]:
    if row["high"] >= position.stop_price:
        trade = close_trade(data, config, position, position.stop_price, close_time, open_time, index_1h, "stop")
        return cash + trade.pop("_cash_delta"), trade

    target_price = position.entry_price - position.risk_distance
    if not position.partial_taken and row["low"] <= target_price:
        partial_exit = target_price * (1 + config.slippage_rate)
        close_units = position.units * 0.5
        pnl = close_units * (position.entry_price - partial_exit) - close_units * partial_exit * config.fee_rate
        cash += pnl
        position.realized_pnl += pnl
        position.units -= close_units
        position.risk_amount *= 0.5
        position.partial_taken = True
        position.partial_time = close_time
        position.partial_price = partial_exit

    row_4h = data.by_close_4h.get(position.symbol, {}).get(close_time)
    if row_4h:
        if row_4h.get("ema50") is not None and row_4h["close"] > row_4h["ema50"]:
            trade = close_trade(data, config, position, row["close"] * (1 + config.slippage_rate), close_time, open_time, index_1h, "ema50_recovery_exit")
            return cash + trade.pop("_cash_delta"), trade
        if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] > row_4h["ema20"]:
            trade = close_trade(data, config, position, row["close"] * (1 + config.slippage_rate), close_time, open_time, index_1h, "ema20_recovery_trailing_exit")
            return cash + trade.pop("_cash_delta"), trade

    if close_time - position.entry_time >= config.max_hold_days * 86400:
        trade = close_trade(data, config, position, row["close"] * (1 + config.slippage_rate), close_time, open_time, index_1h, "max_hold")
        return cash + trade.pop("_cash_delta"), trade
    return cash, None


def apply_regime_exits(
    data: ShortData,
    config: ShortConfig,
    positions: Dict[str, Position],
    trades: List[dict],
    cash: float,
    open_time: int,
    close_time: int,
    index_1h: int,
) -> float:
    regime = data.regime_by_date.get(date_from_ts(close_time), {})
    exit_for_uptrend = regime.get("trade_regime") == "uptrend" or regime.get("trade_action_bias") == "long_allowed"
    exit_for_shock = config.shock_mode == "force_flat" and (
        regime.get("trade_regime") == "shock" or regime.get("trade_action_bias") == "no_new_entry"
    )
    if not exit_for_uptrend and not exit_for_shock:
        return cash
    reason = "regime_uptrend_exit" if exit_for_uptrend else "shock_forced_flat_exit"
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(open_time)
        if not row:
            continue
        trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 + config.slippage_rate), close_time, open_time, index_1h, reason)
        cash += trade.pop("_cash_delta")
        trades.append(trade)
    return cash


def close_trade(
    data: ShortData,
    config: ShortConfig,
    position: Position,
    exit_price: float,
    exit_time: int,
    exit_candle_time: int,
    index_1h: int,
    reason: str,
) -> dict:
    remaining_gross_pnl = position.units * (position.entry_price - exit_price)
    exit_fee = position.units * exit_price * config.fee_rate
    close_cash_delta = remaining_gross_pnl - exit_fee
    total_pnl = position.realized_pnl + close_cash_delta - position.entry_fee
    quality = short_entry_quality(data, position.symbol, position.entry_time, position.entry_price)
    excursion = short_trade_excursion(data, position.symbol, position.entry_time, exit_time, position.entry_price)
    return {
        "variant": config.name,
        "run_group": config.group,
        "universe_size": len(config.universe),
        "fill_mode": config.fill_mode,
        "shock_mode": config.shock_mode,
        "max_hold_days": config.max_hold_days,
        "slippage_rate_pct": config.slippage_rate * 100,
        "fee_rate_pct": config.fee_rate * 100,
        "symbol": short_symbol(position.symbol),
        "side": "short",
        "entry_date": format_dt(position.entry_time),
        "exit_date": format_dt(exit_time),
        "signal_date": format_dt(position.signal_time),
        "available_date": format_dt(position.available_time),
        "entry_timestamp": position.entry_time,
        "exit_timestamp": exit_time,
        "signal_time": position.signal_time,
        "signal_candle_time": position.signal_candle_time,
        "available_time": position.available_time,
        "execution_time": position.entry_time,
        "execution_candle_time": position.entry_candle_time,
        "four_h_signal_time": position.four_h_signal_time,
        "lookahead_pass": position.available_time <= position.entry_time and position.signal_candle_time < position.entry_candle_time,
        "same_candle_signal_execution": position.signal_candle_time == position.entry_candle_time,
        "trade_regime": position.trade_regime,
        "trade_action_bias": position.trade_action_bias,
        "exit_reason": reason,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "stop_price": position.stop_price,
        "risk_distance_pct": position.risk_distance / position.entry_price * 100,
        "short_alpha_score": position.short_alpha_score,
        "downtrend_score": position.downtrend_score,
        "relative_weakness_score": position.relative_weakness_score,
        "rejection_score": position.rejection_score,
        "volume_score": position.volume_score,
        "risk_distance_score": position.risk_distance_score,
        "hold_days": (exit_time - position.entry_time) / 86400,
        "trade_return_pct": total_pnl / position.entry_equity * 100 if position.entry_equity else 0.0,
        "pnl": total_pnl,
        "entry_after_1d_pct": quality["entry_after_1d_pct"],
        "entry_after_3d_pct": quality["entry_after_3d_pct"],
        "entry_after_7d_pct": quality["entry_after_7d_pct"],
        "mae_pct": excursion["mae_pct"],
        "mfe_pct": excursion["mfe_pct"],
        "mae_mfe_ratio": abs(excursion["mae_pct"]) / excursion["mfe_pct"] if excursion["mfe_pct"] and excursion["mfe_pct"] > 0 else None,
        "entry_equity": position.entry_equity,
        "initial_units": position.initial_units,
        "remaining_units_at_exit": position.units,
        "initial_notional": position.initial_notional,
        "entry_fee": position.entry_fee,
        "exit_fee": exit_fee,
        "raw_leverage": position.raw_leverage,
        "applied_leverage": position.applied_leverage,
        "liquidation_price_est": position.liquidation_price_est,
        "position_margin_at_applied_leverage": position.initial_notional / position.applied_leverage if position.applied_leverage else position.initial_notional,
        "partial_taken": position.partial_taken,
        "partial_time": position.partial_time or "",
        "partial_date": format_dt(position.partial_time) if position.partial_time else "",
        "partial_price": position.partial_price or "",
        "signal_id": position.signal_id,
        "_cash_delta": close_cash_delta,
    }


def build_signals(data: ShortData, config: ShortConfig) -> List[dict]:
    signals: List[dict] = []
    by_time_1h = data.by_time_1h
    for open_time in data.times_1h:
        close_time = open_time + 3600
        if close_time < TEST_START_TS or close_time >= data.test_end_ts:
            continue
        four_h_close, rows_4h = data.latest_4h_rows(close_time, config.universe)
        if four_h_close is None or not rows_4h:
            continue
        btc = rows_4h.get("BTCUSDT")
        if not btc or btc.get("ret_7d") is None or btc.get("ret_14d") is None:
            continue
        regime = data.regime_by_date.get(date_from_ts(close_time), {})
        policy = short_regime_policy(regime, config.shock_mode)
        ret14_values = {
            symbol: row["ret_14d"]
            for symbol, row in rows_4h.items()
            if row.get("ret_14d") is not None
        }
        ranked = sorted(ret14_values, key=ret14_values.get)
        rank_lookup = {symbol: rank + 1 for rank, symbol in enumerate(ranked)}
        batch: List[dict] = []
        for symbol in config.universe:
            row_4h = rows_4h.get(symbol)
            row_1h = by_time_1h.get(symbol, {}).get(open_time)
            prev_1h = by_time_1h.get(symbol, {}).get(open_time - 3600)
            if not row_4h or not row_1h or not prev_1h:
                continue
            signal = score_short_signal(
                symbol=symbol,
                row_4h=row_4h,
                row_1h=row_1h,
                prev_1h=prev_1h,
                btc_4h=btc,
                rank=rank_lookup.get(symbol),
                universe_size=len(ranked),
                regime=regime,
                policy=policy,
                config=config,
                signal_candle_time=open_time,
                signal_time=close_time,
                four_h_signal_time=four_h_close,
            )
            if signal:
                batch.append(signal)
        eligible = [
            signal for signal in batch
            if signal["regime_entry_allowed"] and signal["short_alpha_score"] >= MIN_SHORT_ALPHA_SCORE
        ]
        top_n = max(1, math.ceil(len(eligible) * TOP_SCORE_PCT)) if eligible else 0
        top_ids = {signal["signal_id"] for signal in sorted(eligible, key=lambda row: row["short_alpha_score"], reverse=True)[:top_n]}
        for signal in sorted(batch, key=lambda row: row["short_alpha_score"], reverse=True):
            if not signal["regime_entry_allowed"]:
                signal["pre_trade_skip_reason"] = signal["regime_policy"]
            elif signal["short_alpha_score"] < MIN_SHORT_ALPHA_SCORE:
                signal["pre_trade_skip_reason"] = "score_below_min"
            elif signal["signal_id"] not in top_ids:
                signal["pre_trade_skip_reason"] = "score_not_top_20pct"
            else:
                signal["pre_trade_skip_reason"] = ""
            signal["selected_by_score"] = signal["signal_id"] in top_ids
            signals.append(signal)
    return signals


def score_short_signal(
    symbol: str,
    row_4h: dict,
    row_1h: dict,
    prev_1h: dict,
    btc_4h: dict,
    rank: Optional[int],
    universe_size: int,
    regime: dict,
    policy: dict,
    config: ShortConfig,
    signal_candle_time: int,
    signal_time: int,
    four_h_signal_time: int,
) -> Optional[dict]:
    required = {row_4h.get("ema20"), row_4h.get("ema50"), row_4h.get("atr14"), row_4h.get("volume20"), row_1h.get("ema20"), row_1h.get("atr14")}
    if None in required or rank is None or not universe_size:
        return None
    downtrend_ok = row_4h["close"] < row_4h["ema50"] and row_4h["ema20"] < row_4h["ema50"]
    if not downtrend_ok:
        return None
    overextended = row_4h["close"] < row_4h["ema20"] - OVEREXTENSION_ATR_MULTIPLE * row_4h["atr14"]
    if overextended:
        return None

    ret_7d = row_4h.get("ret_7d")
    ret_14d = row_4h.get("ret_14d")
    btc_excess_7d = ret_7d - btc_4h["ret_7d"] if ret_7d is not None else None
    btc_excess_14d = ret_14d - btc_4h["ret_14d"] if ret_14d is not None else None
    bottom_n = max(1, math.ceil(universe_size * 0.20))
    ret7_weaker = btc_excess_7d is not None and btc_excess_7d < 0
    ret14_bottom = rank <= bottom_n
    btc_excess_negative = btc_excess_14d is not None and btc_excess_14d < 0
    if not (ret7_weaker and ret14_bottom and btc_excess_negative):
        return None

    rebreak_below_ema20 = (
        row_1h["close"] < row_1h["ema20"]
        and (
            (prev_1h.get("ema20") is not None and prev_1h["close"] >= prev_1h["ema20"])
            or row_1h["high"] >= row_1h["ema20"]
        )
    )
    if not (rebreak_below_ema20 and (row_4h.get("recent_ema20_bounce") or row_4h.get("recent_ema50_bounce"))):
        return None

    downtrend_score = 2.0
    relative_weakness_score = float(ret7_weaker) + float(ret14_bottom) + float(btc_excess_negative)
    rejection_score = 1.0 + (2.0 if row_4h.get("recent_ema50_bounce") else 1.5)
    volume_score = 1.0 if row_4h["volume"] > row_4h["volume20"] * 1.2 else 0.0
    stop_estimate = max(row_1h.get("swing_high20") or row_1h["close"], row_1h["close"] + STOP_ATR_MULTIPLE * row_1h["atr14"])
    risk_pct = (stop_estimate - row_1h["close"]) / row_1h["close"] if row_1h["close"] else 999
    risk_distance_score = 1.5 if risk_pct <= 0.04 else 1.0 if risk_pct <= 0.07 else 0.5
    short_alpha_score = downtrend_score + relative_weakness_score + rejection_score + volume_score + risk_distance_score
    execution_candle_time = signal_time
    execution_time = signal_time if config.fill_mode == "next_open" else signal_time + 3600
    signal_id = "|".join([config.name, symbol, str(signal_time), str(four_h_signal_time), config.fill_mode, config.shock_mode])
    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "symbol_short": short_symbol(symbol),
        "side": "short",
        "fill_mode": config.fill_mode,
        "shock_mode": config.shock_mode,
        "signal_candle_time": signal_candle_time,
        "signal_candle_date": format_dt(signal_candle_time),
        "signal_time": signal_time,
        "signal_date": format_dt(signal_time),
        "available_time": signal_time,
        "available_date": format_dt(signal_time),
        "execution_candle_time": execution_candle_time,
        "execution_candle_date": format_dt(execution_candle_time),
        "execution_time": execution_time,
        "execution_date": format_dt(execution_time),
        "four_h_signal_time": four_h_signal_time,
        "four_h_signal_date": format_dt(four_h_signal_time),
        "trade_regime": regime.get("trade_regime"),
        "trade_action_bias": regime.get("trade_action_bias"),
        "regime_policy": policy["reason"],
        "regime_entry_allowed": policy["allow_new"],
        "downtrend_score": downtrend_score,
        "relative_weakness_score": relative_weakness_score,
        "rejection_score": rejection_score,
        "volume_score": volume_score,
        "risk_distance_score": risk_distance_score,
        "short_alpha_score": short_alpha_score,
        "rank_14d_weakness": rank,
        "universe_size": universe_size,
        "bottom_20pct_cutoff": bottom_n,
        "ret_7d_pct": ret_7d * 100 if ret_7d is not None else None,
        "ret_14d_pct": ret_14d * 100 if ret_14d is not None else None,
        "btc_excess_7d_pct": btc_excess_7d * 100 if btc_excess_7d is not None else None,
        "btc_excess_14d_pct": btc_excess_14d * 100 if btc_excess_14d is not None else None,
        "downtrend_ok": downtrend_ok,
        "ret7_weaker_than_btc": ret7_weaker,
        "ret14_bottom_20pct": ret14_bottom,
        "btc_excess_negative": btc_excess_negative,
        "recent_ema20_bounce": bool(row_4h.get("recent_ema20_bounce")),
        "recent_ema50_bounce": bool(row_4h.get("recent_ema50_bounce")),
        "rebreak_below_1h_ema20": rebreak_below_ema20,
        "overextension_blocked": overextended,
        "volume_boost": volume_score > 0,
        "close_4h": row_4h["close"],
        "ema20_4h": row_4h["ema20"],
        "ema50_4h": row_4h["ema50"],
        "atr14_4h": row_4h["atr14"],
        "close_1h": row_1h["close"],
        "ema20_1h": row_1h["ema20"],
        "atr14_1h": row_1h["atr14"],
        "risk_distance_est_pct": risk_pct * 100,
        "lookahead_rule_pass": four_h_signal_time <= signal_time and signal_candle_time < execution_candle_time,
    }


def short_regime_policy(regime: dict, shock_mode: str) -> dict:
    trade_regime = regime.get("trade_regime")
    action_bias = regime.get("trade_action_bias")
    if trade_regime == "defensive" or action_bias == "reduce_risk":
        return {"allow_new": True, "reason": "defensive_reduce_risk_allowed"}
    if trade_regime == "shock" or action_bias == "no_new_entry":
        if shock_mode == "allow_new":
            return {"allow_new": True, "reason": "shock_allow_comparison"}
        return {"allow_new": False, "reason": "shock_no_new_entry"}
    if trade_regime == "uptrend" or action_bias == "long_allowed":
        return {"allow_new": False, "reason": "uptrend_long_allowed_block"}
    if trade_regime == "eth_strength" or action_bias == "alt_watch":
        return {"allow_new": False, "reason": "eth_strength_alt_watch_block"}
    if trade_regime == "large_cap_lead":
        return {"allow_new": False, "reason": "large_cap_lead_block"}
    if trade_regime in {"neutral", "observe"} or action_bias == "wait":
        return {"allow_new": False, "reason": "neutral_observe_wait"}
    return {"allow_new": False, "reason": str(action_bias or trade_regime or "missing_regime")}


def add_4h_features(candles: List[dict]) -> List[dict]:
    rows = [dict(row) for row in candles]
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    atr14 = atr(rows, 14)
    volume20 = rolling_average(volumes, 20)
    for index, row in enumerate(rows):
        row["close_time"] = row["time"] + 4 * 3600
        row["ema20"] = ema20[index]
        row["ema50"] = ema50[index]
        row["atr14"] = atr14[index]
        row["volume20"] = volume20[index]
        row["ret_7d"] = row["close"] / rows[index - 42]["close"] - 1 if index >= 42 and rows[index - 42]["close"] else None
        row["ret_14d"] = row["close"] / rows[index - 84]["close"] - 1 if index >= 84 and rows[index - 84]["close"] else None
        recent = rows[max(0, index - BOUNCE_LOOKBACK_4H + 1) : index + 1]
        row["recent_ema20_bounce"] = any(touched_short_bounce(item, "ema20") for item in recent)
        row["recent_ema50_bounce"] = any(touched_short_bounce(item, "ema50") for item in recent)
    return rows


def touched_short_bounce(row: dict, key: str) -> bool:
    if row.get(key) is None or row.get("atr14") is None:
        return False
    tolerance = BOUNCE_ATR_TOLERANCE * row["atr14"]
    return row["high"] >= row[key] - tolerance


def add_1h_features(candles: List[dict]) -> List[dict]:
    rows = [dict(row) for row in candles]
    closes = [row["close"] for row in rows]
    ema20 = ema(closes, 20)
    atr14 = atr(rows, 14)
    for index, row in enumerate(rows):
        row["close_time"] = row["time"] + 3600
        row["ema20"] = ema20[index]
        row["atr14"] = atr14[index]
        highs = [rows[item]["high"] for item in range(max(0, index - SWING_HIGH_LOOKBACK), index + 1)]
        row["swing_high20"] = max(highs) if highs else None
    return rows


def atr(rows: List[dict], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    true_ranges = []
    previous_close = None
    for row in rows:
        if previous_close is None:
            tr = row["high"] - row["low"]
        else:
            tr = max(row["high"] - row["low"], abs(row["high"] - previous_close), abs(row["low"] - previous_close))
        true_ranges.append(tr)
        previous_close = row["close"]
        if len(true_ranges) < period:
            out.append(None)
        else:
            out.append(sum(true_ranges[-period:]) / period)
    return out


def rolling_average(values: Iterable[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    window: List[float] = []
    for value in values:
        window.append(float(value))
        if len(window) < period:
            out.append(None)
        else:
            out.append(sum(window[-period:]) / period)
    return out


def build_trade_regime(raw_1d: Dict[str, List[dict]]) -> Dict[str, dict]:
    payload = build_payload_from_raw(raw_1d, interval="1d", start=FETCH_DAILY_START, symbols=BASE_UNIVERSE_9)
    out = {}
    for point in payload["points"]:
        out[date_from_ts(point["time"])] = {
            "trade_regime": point.get("trade_regime"),
            "trade_action_bias": point.get("trade_action_bias"),
        }
    return out


def annotate_funding(
    data: ShortData,
    trades: List[dict],
    funding_index: Dict[str, Tuple[List[int], List[dict]]],
    include_funding: bool,
) -> Tuple[List[dict], List[dict]]:
    annotated = []
    cashflows = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        events = slice_time_index(funding_index, symbol, int(trade["entry_timestamp"]), int(trade["exit_timestamp"])) if include_funding else []
        funding_pnl = 0.0
        funding_cost = 0.0
        funding_income = 0.0
        for event in events:
            units = float(trade["initial_units"])
            partial_time = trade.get("partial_time")
            if partial_time not in {"", None} and event["funding_time"] >= int(partial_time):
                units *= 0.5
            mark_price = event["mark_price"] or mark_price_for(data, symbol, event["funding_time"]) or float(trade["entry_price"])
            notional = units * mark_price
            pnl = notional * event["funding_rate"]
            funding_pnl += pnl
            funding_cost += max(-pnl, 0.0)
            funding_income += max(pnl, 0.0)
            cashflows.append(
                {
                    "variant": trade["variant"],
                    "symbol": trade["symbol"],
                    "trade_index": index,
                    "funding_time": event["funding_time"],
                    "funding_date": event["funding_date"],
                    "funding_rate": event["funding_rate"],
                    "mark_price": mark_price,
                    "notional": notional,
                    "funding_pnl": pnl,
                }
            )
        pnl_after = float(trade["pnl"]) + funding_pnl
        entry_equity = float(trade["entry_equity"]) if trade.get("entry_equity") else 1.0
        annotated.append(
            {
                **trade,
                "funding_event_count": len(events),
                "funding_pnl": funding_pnl,
                "funding_cost": funding_cost,
                "funding_income": funding_income,
                "funding_cost_income_ratio": funding_cost / funding_income if funding_income > 0 else None,
                "pnl_after_funding": pnl_after,
                "trade_return_after_funding_pct": pnl_after / entry_equity * 100 if entry_equity else 0.0,
            }
        )
    return annotated, cashflows


def adjusted_equity_curve(curve: List[dict], cashflows: List[dict]) -> List[dict]:
    events = sorted(cashflows, key=lambda row: row["funding_time"])
    out = []
    cumulative = 0.0
    index = 0
    for point in curve:
        while index < len(events) and events[index]["funding_time"] <= point["time"]:
            cumulative += events[index]["funding_pnl"]
            index += 1
        out.append({"time": point["time"], "date": point.get("date", format_dt(point["time"])), "equity": max(1e-9, point["equity"] + cumulative)})
    return out


def annotate_liquidation(data: ShortData, trades: List[dict]) -> List[dict]:
    rows_index = build_time_index(data.rows_1h)
    out = []
    for index, trade in enumerate(trades):
        symbol = f"{trade['symbol']}USDT"
        rows = slice_time_index(rows_index, symbol, int(trade["entry_timestamp"]), int(trade["exit_timestamp"]))
        max_high = max((row["high"] for row in rows), default=None)
        max_open = max((row["open"] for row in rows), default=None)
        liquidation_price = float(trade["liquidation_price_est"])
        stop_before_liq = float(trade["stop_price"]) < liquidation_price
        high_touched = max_high is not None and max_high >= liquidation_price
        gap_touch = max_open is not None and max_open >= liquidation_price
        out.append(
            {
                **trade,
                "trade_index": index,
                "max_1h_high_during_hold": max_high,
                "max_1h_open_during_hold": max_open,
                "stop_before_liquidation": stop_before_liq,
                "liquidation_high_touched_1h": high_touched,
                "liquidation_gap_touch_1h_open": gap_touch,
                "liquidation_risk": (not stop_before_liq) or gap_touch,
            }
        )
    return out


def summary_row(data: ShortData, result: RunResult, trades: List[dict], curve: List[dict], funding_key: str, funding_name: str) -> dict:
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = max((data.test_end_ts - TEST_START_TS) / (365.25 * 86400), 1 / 365.25)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [curve[index]["equity"] / curve[index - 1]["equity"] - 1 for index in range(1, len(curve)) if curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = max_drawdown(curve)
    pnl_key = "pnl_after_funding" if funding_key == "actual" else "pnl"
    pnls = [float(trade[pnl_key]) for trade in trades]
    returns_pct = [float(trade["trade_return_after_funding_pct"] if funding_key == "actual" else trade["trade_return_pct"]) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    win_returns = [value for value in returns_pct if value > 0]
    loss_returns = [value for value in returns_pct if value < 0]
    holds = [float(trade["hold_days"]) for trade in trades]
    symbol_rows = group_trade_stats(trades, "symbol", pnl_key)
    positive_total = sum(row["pnl"] for row in symbol_rows if row["pnl"] > 0)
    max_symbol_share = max((row["pnl"] / positive_total * 100 for row in symbol_rows if row["pnl"] > 0), default=0.0) if positive_total > 0 else 0.0
    funding_pnl = sum(float(trade.get("funding_pnl", 0.0)) for trade in trades)
    funding_cost = sum(float(trade.get("funding_cost", 0.0)) for trade in trades)
    funding_income = sum(float(trade.get("funding_income", 0.0)) for trade in trades)
    return {
        "name": result.config.name,
        "group": result.config.group,
        "funding": funding_name,
        "universe_size": len(result.config.universe),
        "fill_mode": result.config.fill_mode,
        "shock_mode": result.config.shock_mode,
        "max_hold_days": result.config.max_hold_days,
        "slippage_rate_pct": result.config.slippage_rate * 100,
        "fee_rate_pct": result.config.fee_rate * 100,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "avg_payoff_ratio": statistics.mean(win_returns) / abs(statistics.mean(loss_returns)) if win_returns and loss_returns else None,
        "trades": len(trades),
        "avg_monthly_trades": len(trades) / max(len(data.months), 1),
        "avg_hold_days": mean_present(holds),
        "median_hold_days": statistics.median(holds) if holds else None,
        "max_hold_days_actual": max(holds) if holds else None,
        "avg_entry_after_1d_pct": mean_present([trade["entry_after_1d_pct"] for trade in trades]),
        "avg_entry_after_3d_pct": mean_present([trade["entry_after_3d_pct"] for trade in trades]),
        "avg_entry_after_7d_pct": mean_present([trade["entry_after_7d_pct"] for trade in trades]),
        "avg_mae_pct": mean_present([trade["mae_pct"] for trade in trades]),
        "avg_mfe_pct": mean_present([trade["mfe_pct"] for trade in trades]),
        "avg_mae_mfe_ratio": mean_present([trade["mae_mfe_ratio"] for trade in trades]),
        "avg_winning_trade_pct": statistics.mean(win_returns) if win_returns else None,
        "avg_losing_trade_pct": statistics.mean(loss_returns) if loss_returns else None,
        "funding_pnl": funding_pnl,
        "funding_cost": funding_cost,
        "funding_income": funding_income,
        "funding_cost_income_ratio": funding_cost / funding_income if funding_income > 0 else None,
        "liquidation_risk_trades": sum(1 for trade in trades if truthy(trade.get("liquidation_risk"))),
        "liquidation_buffer_failed_skips": result.skip_counter.get("liquidation_buffer_failed", 0),
        "signal_count": len(result.signals),
        "entry_count": len(trades),
        "skip_total": sum(result.skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(result.skip_counter.items())),
        "max_symbol_positive_pnl_share_pct": max_symbol_share,
    }


def monthly_returns_from_curve(data: ShortData, name: str, group: str, funding_key: str, curve: List[dict]) -> List[dict]:
    month_end: Dict[str, float] = {}
    for point in curve:
        month = month_from_ts(point["time"])
        if data.months[0] <= month <= data.months[-1]:
            month_end[month] = point["equity"]
    rows = []
    previous = 1.0
    for month in data.months:
        equity = month_end.get(month, previous)
        rows.append(
            {
                "name": name,
                "group": group,
                "funding": funding_key,
                "month": month,
                "return_pct": (equity / previous - 1) * 100 if previous else 0.0,
                "equity": equity,
            }
        )
        previous = equity
    return rows


def yearly_rows_from_monthly(name: str, group: str, funding_key: str, monthly: List[dict]) -> List[dict]:
    yearly: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return [
        {
            "name": name,
            "group": group,
            "funding": funding_key,
            "year": year,
            "return_pct": (value - 1) * 100,
        }
        for year, value in sorted(yearly.items())
    ]


def build_benchmarks(data: ShortData) -> List[dict]:
    return [cash_benchmark(data), btc_buy_hold(data)]


def cash_benchmark(data: ShortData) -> dict:
    curve = [{"time": TEST_START_TS, "date": format_dt(TEST_START_TS), "equity": 1.0}]
    for timestamp in data.times_1h:
        curve.append({"time": timestamp + 3600, "date": format_dt(timestamp + 3600), "equity": 1.0})
    monthly = monthly_returns_from_curve(data, "Cash 100%", "Benchmark", "excluded", curve)
    yearly = yearly_rows_from_monthly("Cash 100%", "Benchmark", "excluded", monthly)
    return {
        "summary": benchmark_summary(data, "Cash 100%", "Benchmark", curve, monthly),
        "monthly": monthly,
        "yearly": yearly,
    }


def btc_buy_hold(data: ShortData) -> dict:
    rows = [row for row in data.raw_1d.get("BTCUSDT", []) if TEST_START_TS <= row["time"] < data.test_end_ts]
    if not rows:
        return cash_benchmark(data)
    start = rows[0]["open"]
    curve = [{"time": rows[0]["time"], "date": format_dt(rows[0]["time"]), "equity": 1.0}]
    for row in rows:
        curve.append({"time": row["time"] + 86400, "date": format_dt(row["time"] + 86400), "equity": row["close"] / start if start else 1.0})
    monthly = monthly_returns_from_curve(data, "BTC Buy & Hold", "Benchmark", "excluded", curve)
    yearly = yearly_rows_from_monthly("BTC Buy & Hold", "Benchmark", "excluded", monthly)
    return {
        "summary": benchmark_summary(data, "BTC Buy & Hold", "Benchmark", curve, monthly),
        "monthly": monthly,
        "yearly": yearly,
    }


def benchmark_summary(data: ShortData, name: str, group: str, curve: List[dict], monthly: List[dict]) -> dict:
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = max((data.test_end_ts - TEST_START_TS) / (365.25 * 86400), 1 / 365.25)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [curve[index]["equity"] / curve[index - 1]["equity"] - 1 for index in range(1, len(curve)) if curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 if name != "Cash 100%" else 1) if stdev and stdev > 0 else None
    mdd = max_drawdown(curve)
    return {
        "name": name,
        "group": group,
        "funding": "excluded",
        "universe_size": "",
        "fill_mode": "",
        "shock_mode": "",
        "max_hold_days": "",
        "slippage_rate_pct": "",
        "fee_rate_pct": "",
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": "",
        "win_rate_pct": "",
        "avg_payoff_ratio": "",
        "trades": 0,
        "avg_monthly_trades": 0,
        "avg_hold_days": "",
        "median_hold_days": "",
        "max_hold_days_actual": "",
        "avg_entry_after_1d_pct": "",
        "avg_entry_after_3d_pct": "",
        "avg_entry_after_7d_pct": "",
        "avg_mae_pct": "",
        "avg_mfe_pct": "",
        "avg_mae_mfe_ratio": "",
        "avg_winning_trade_pct": "",
        "avg_losing_trade_pct": "",
        "funding_pnl": 0.0,
        "funding_cost": 0.0,
        "funding_income": 0.0,
        "funding_cost_income_ratio": "",
        "liquidation_risk_trades": "",
        "liquidation_buffer_failed_skips": "",
        "signal_count": "",
        "entry_count": "",
        "skip_total": "",
        "skip_reasons": "",
        "max_symbol_positive_pnl_share_pct": "",
    }


def pass_fail(summary_rows: List[dict], yearly_rows: List[dict]) -> List[dict]:
    lookup = {(row["name"], row["funding"]): row for row in summary_rows}
    base4 = lookup.get(("Short Engine v0 / 4 symbols", "actual funding"), {})
    base9 = lookup.get(("Short Engine v0 / 9 symbols", "actual funding"), {})
    shock4 = lookup.get(("Short Engine v0 / 4 symbols / shock allow comparison", "actual funding"), {})
    shock9 = lookup.get(("Short Engine v0 / 9 symbols / shock allow comparison", "actual funding"), {})
    rows = []
    for label, row in (("4 symbols", base4), ("9 symbols", base9)):
        calmar = row.get("calmar")
        mdd = row.get("mdd_pct")
        rows.append(
            {
                "check": f"{label} Calmar >= 1.0 at 0.2% slippage",
                "result": "PASS" if row and calmar is not None and calmar >= 1.0 else "FAIL",
                "evidence": f"Calmar {num(calmar)}",
            }
        )
        rows.append(
            {
                "check": f"{label} MDD within -35%",
                "result": "PASS" if row and mdd is not None and mdd >= -35.0 else "FAIL",
                "evidence": f"MDD {pct(mdd)}",
            }
        )
        rows.append(
            {
                "check": f"{label} liquidation risk 0",
                "result": "PASS" if row and int(row.get("liquidation_risk_trades") or 0) == 0 else "FAIL",
                "evidence": f"Liquidation risk trades {row.get('liquidation_risk_trades', '')}",
            }
        )
        rows.append(
            {
                "check": f"{label} actual funding Calmar >= 0.8 minimum",
                "result": "PASS" if row and calmar is not None and calmar >= 0.8 else "FAIL",
                "evidence": f"Funding-included Calmar {num(calmar)}",
            }
        )
        concentration = row.get("max_symbol_positive_pnl_share_pct")
        rows.append(
            {
                "check": f"{label} symbol PnL concentration",
                "result": "WARNING" if concentration not in {None, ""} and float(concentration) >= 50.0 else "PASS",
                "evidence": f"Max positive PnL share {pct(concentration)}",
            }
        )
        rows.append(
            {
                "check": f"{label} trade count",
                "result": "NO_DATA" if int(row.get("trades") or 0) < MIN_TRADES_FOR_DATA else "PASS",
                "evidence": f"Trades {row.get('trades', 0)}",
            }
        )
        rows.append(annual_dependency_check(label, row, yearly_rows))
    if base4 and shock4:
        rows.append(
            {
                "check": "4 symbols shock chasing comparison",
                "result": "KEEP_SHOCK_FORBID" if (shock4.get("calmar") or -999) < (base4.get("calmar") or -999) else "REVIEW",
                "evidence": f"Base Calmar {num(base4.get('calmar'))}, shock-allow Calmar {num(shock4.get('calmar'))}",
            }
        )
    if base9 and shock9:
        rows.append(
            {
                "check": "9 symbols shock chasing comparison",
                "result": "KEEP_SHOCK_FORBID" if (shock9.get("calmar") or -999) < (base9.get("calmar") or -999) else "REVIEW",
                "evidence": f"Base Calmar {num(base9.get('calmar'))}, shock-allow Calmar {num(shock9.get('calmar'))}",
            }
        )
    if base4 and base9:
        stable4 = (base4.get("calmar") or -999) >= (base9.get("calmar") or -999) and (base4.get("mdd_pct") or -999) >= (base9.get("mdd_pct") or -999)
        rows.append(
            {
                "check": "4 symbols vs 9 symbols stability",
                "result": "PREFER_4_SYMBOLS" if stable4 else "PREFER_9_SYMBOLS_OR_REVIEW",
                "evidence": f"4 Calmar {num(base4.get('calmar'))}, MDD {pct(base4.get('mdd_pct'))}; 9 Calmar {num(base9.get('calmar'))}, MDD {pct(base9.get('mdd_pct'))}",
            }
        )
    return rows


def annual_dependency_check(label: str, row: dict, yearly_rows: List[dict]) -> dict:
    rows = [
        item for item in yearly_rows
        if item["name"] == row.get("name") and item["funding"] == "actual"
    ]
    positives = [item["return_pct"] for item in rows if item["return_pct"] > 0]
    total_positive = sum(positives)
    largest = max(positives, default=0.0)
    share = largest / total_positive * 100 if total_positive > 0 else 0.0
    only_one = len(positives) <= 1 and len(rows) > 1
    return {
        "check": f"{label} annual dependency",
        "result": "WARNING" if share >= 70.0 or only_one else "PASS",
        "evidence": f"Largest positive year share {share:.1f}%, positive years {len(positives)}",
    }


def build_report(
    data: ShortData,
    summary_rows: List[dict],
    trade_rows: List[dict],
    signal_rows: List[dict],
    monthly_rows: List[dict],
    yearly_rows: List[dict],
    pass_fail_rows: List[dict],
    reference_rows: List[dict],
    funding_by_symbol: Dict[str, List[dict]],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base_rows = [
        row for row in summary_rows
        if row["funding"] == "actual funding" and row["group"] in {"Short Engine v0", "Benchmark"}
    ]
    comparison_rows = [row for row in summary_rows if row["funding"] == "actual funding" and row["group"] not in {"Short Engine v0", "Benchmark"}]
    base_trades = [row for row in trade_rows if row["variant"] in {"Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols"}]
    lines = [
        "# Alpha Short Engine v0 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        f"- 기간: {format_dt(TEST_START_TS)} ~ {format_dt(data.test_end_ts)} UTC",
        "- Short Engine v0는 실전 투입용이 아니라 연구/백테스트 전용이다.",
        "- Alpha Long Engine v1.2와 통합하지 않았고, 기존 `alpha_engine_v1_2` 관련 파일도 수정하지 않았다.",
        "- Paper Trading 연결 전 별도 감사가 필요하다.",
        "- 통과하더라도 최소 3개월 별도 Paper Trading 검증이 필요하다.",
        "- 실제 주문 API 연결은 없다. 데이터 조회는 Binance USD-M Futures OHLCV/funding history만 사용한다.",
        "- DOGE는 v0 유니버스에서 제외했다.",
        "",
        "## Pass / Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## 핵심 성과",
        "",
        summary_table(base_rows),
        "",
        "## 비교 및 민감도",
        "",
        summary_table(comparison_rows),
        "",
        "## Funding 포함 / 제외 비교",
        "",
        summary_table([row for row in summary_rows if row["group"] == "Short Engine v0"]),
        "",
        "## Alpha Long Engine v1.2 참고값",
        "",
        reference_table(reference_rows),
        "",
        "## 룩어헤드 감사",
        "",
        lookahead_table(base_trades, signal_rows),
        "",
        "## OOS / Walk-forward",
        "",
        oos_table(monthly_rows),
        "",
        "## 분기별 Rolling 성과",
        "",
        quarterly_table(monthly_rows),
        "",
        "## 심볼별 성과",
        "",
        grouped_table(group_trade_stats(base_trades, "symbol", "pnl_after_funding"), "symbol"),
        "",
        "## 레짐별 성과",
        "",
        grouped_table(group_trade_stats(base_trades, "trade_regime", "pnl_after_funding"), "trade_regime"),
        "",
        "## Action Bias별 성과",
        "",
        grouped_table(group_trade_stats(base_trades, "trade_action_bias", "pnl_after_funding"), "trade_action_bias"),
        "",
        "## 진입 품질",
        "",
        entry_quality_table(base_trades),
        "",
        "## 신호 / 스킵 통계",
        "",
        skip_table(signal_rows),
        "",
        "## Funding 요약",
        "",
        funding_table(base_trades),
        "",
        "## 최악 거래 Top 20",
        "",
        trade_rank_table(base_trades, reverse=False),
        "",
        "## 최고 거래 Top 20",
        "",
        trade_rank_table(base_trades, reverse=True),
        "",
        "## 연도별 수익률",
        "",
        yearly_table(yearly_rows),
        "",
        "## 월별 수익률 최근 12개월",
        "",
        monthly_sample_table(data, monthly_rows),
        "",
        "## 데이터 커버리지",
        "",
        coverage_table(data, funding_by_symbol),
        "",
        "## 산출물",
        "",
        "- `alpha_short_engine_v0_report.md`",
        "- `alpha_short_engine_v0_summary.csv`",
        "- `alpha_short_engine_v0_trades.csv`",
        "- `alpha_short_engine_v0_signals.csv`",
        "- `alpha_short_engine_v0_monthly.csv`",
        "- `alpha_short_engine_v0_yearly.csv`",
        "",
    ]
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Name", "Funding", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "PF", "Win", "Trades", "Monthly", "Funding PnL", "Liq risk"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["name"]),
                    str(row["funding"]),
                    pct(row["total_return_pct"]),
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    num(row["profit_factor"]),
                    pct(row["win_rate_pct"]),
                    str(row["trades"]),
                    num(row["avg_monthly_trades"]),
                    num(row["funding_pnl"]),
                    str(row["liquidation_risk_trades"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def reference_table(rows: List[dict]) -> str:
    if not rows:
        return "기존 `alpha_engine_v1_2_candidate_summary.csv` 참고값을 찾지 못했다."
    return summary_table(rows)


def lookahead_table(trades: List[dict], signals: List[dict]) -> str:
    same_candle_trades = sum(1 for trade in trades if truthy(trade.get("same_candle_signal_execution")))
    lookahead_fail = sum(1 for trade in trades if not truthy(trade.get("lookahead_pass")))
    signal_rule_fail = sum(1 for row in signals if not truthy(row.get("lookahead_rule_pass")))
    min_lag = min((float(trade["execution_time"]) - float(trade["available_time"])) / 3600 for trade in trades) if trades else 0.0
    return "\n".join(
        [
            "| Check | Value |",
            "|---|---:|",
            f"| 1D regime source | trade_regime / trade_action_bias only |",
            f"| stable_regime same-day direct use | 0 |",
            f"| Trade lookahead failures | {lookahead_fail} |",
            f"| Signal rule failures | {signal_rule_fail} |",
            f"| Same candle signal/execution trades | {same_candle_trades} |",
            f"| Minimum available-to-execution lag hours | {min_lag:.1f} |",
        ]
    )


def oos_table(monthly_rows: List[dict]) -> str:
    names = ["Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols"]
    windows = [
        ("2020-2023 train", "2020-01", "2023-12"),
        ("2024 test", "2024-01", "2024-12"),
        ("2020-2024 train", "2020-01", "2024-12"),
        ("2025 test", "2025-01", "2025-12"),
        ("2026 OOS", "2026-01", "2026-12"),
    ]
    lines = ["| Name | Window | Months | Return | Result |", "|---|---|---:|---:|---|"]
    for name in names:
        rows = [row for row in monthly_rows if row["name"] == name and row["funding"] == "actual"]
        for label, start, end in windows:
            subset = [row for row in rows if start <= row["month"] <= end]
            if not subset:
                lines.append(f"| {name} | {label} | 0 |  | no_data |")
                continue
            value = 1.0
            for row in subset:
                value *= 1 + row["return_pct"] / 100
            lines.append(f"| {name} | {label} | {len(subset)} | {pct((value - 1) * 100)} | {'no_data' if label == '2026 OOS' and len(subset) < 3 else 'ok'} |")
    return "\n".join(lines)


def quarterly_table(monthly_rows: List[dict]) -> str:
    names = ["Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols"]
    grouped: Dict[Tuple[str, str], float] = {}
    for row in monthly_rows:
        if row["name"] not in names or row["funding"] != "actual":
            continue
        year, month = row["month"].split("-")
        quarter = f"{year}-Q{(int(month) - 1) // 3 + 1}"
        grouped.setdefault((row["name"], quarter), 1.0)
        grouped[(row["name"], quarter)] *= 1 + row["return_pct"] / 100
    quarters = sorted({quarter for _, quarter in grouped})[-12:]
    lines = ["| Name | " + " | ".join(quarters) + " |", "|" + "|".join(["---"] * (len(quarters) + 1)) + "|"]
    for name in names:
        lines.append("| " + " | ".join([name] + [pct((grouped.get((name, quarter), 1.0) - 1) * 100) for quarter in quarters]) + " |")
    return "\n".join(lines)


def group_trade_stats(trades: List[dict], key: str, pnl_key: str) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key, ""))].append(trade)
    out = []
    for value, items in grouped.items():
        pnls = [float(item[pnl_key]) for item in items]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        out.append(
            {
                key: value,
                "trades": len(items),
                "pnl": sum(pnls),
                "win_rate_pct": len(wins) / len(items) * 100 if items else 0.0,
                "avg_return_pct": mean_present([item["trade_return_after_funding_pct"] for item in items]),
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            }
        )
    return sorted(out, key=lambda row: row["pnl"], reverse=True)


def grouped_table(rows: List[dict], key: str) -> str:
    if not rows:
        return "거래 없음."
    lines = [f"| {key} | Trades | PnL | Win | Avg return | PF |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row[key]} | {row['trades']} | {num(row['pnl'])} | {pct(row['win_rate_pct'])} | {pct(row['avg_return_pct'])} | {num(row['profit_factor'])} |")
    return "\n".join(lines)


def entry_quality_table(trades: List[dict]) -> str:
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Entry +1D avg | {pct(mean_present([trade['entry_after_1d_pct'] for trade in trades]))} |",
            f"| Entry +3D avg | {pct(mean_present([trade['entry_after_3d_pct'] for trade in trades]))} |",
            f"| Entry +7D avg | {pct(mean_present([trade['entry_after_7d_pct'] for trade in trades]))} |",
            f"| Avg MAE | {pct(mean_present([trade['mae_pct'] for trade in trades]))} |",
            f"| Avg MFE | {pct(mean_present([trade['mfe_pct'] for trade in trades]))} |",
            f"| Avg MAE/MFE | {num(mean_present([trade['mae_mfe_ratio'] for trade in trades]))} |",
            f"| Avg winning trade | {pct(mean_present([trade['trade_return_after_funding_pct'] for trade in trades if trade['trade_return_after_funding_pct'] > 0]))} |",
            f"| Avg losing trade | {pct(mean_present([trade['trade_return_after_funding_pct'] for trade in trades if trade['trade_return_after_funding_pct'] < 0]))} |",
        ]
    )


def skip_table(signals: List[dict]) -> str:
    counter = Counter(row.get("skip_reason") or "entered" for row in signals)
    lines = ["| Reason | Count |", "|---|---:|"]
    for reason, count in sorted(counter.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| {reason} | {count} |")
    return "\n".join(lines)


def funding_table(trades: List[dict]) -> str:
    funding_pnl = sum(float(trade.get("funding_pnl", 0.0)) for trade in trades)
    funding_cost = sum(float(trade.get("funding_cost", 0.0)) for trade in trades)
    funding_income = sum(float(trade.get("funding_income", 0.0)) for trade in trades)
    ratio = funding_cost / funding_income if funding_income > 0 else None
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Funding PnL | {num(funding_pnl)} |",
            f"| Funding income | {num(funding_income)} |",
            f"| Funding cost | {num(funding_cost)} |",
            f"| Funding cost / income | {num(ratio)} |",
            f"| Funding events | {sum(int(trade.get('funding_event_count') or 0) for trade in trades)} |",
        ]
    )


def trade_rank_table(trades: List[dict], reverse: bool) -> str:
    if not trades:
        return "거래 없음."
    rows = sorted(trades, key=lambda row: row["trade_return_after_funding_pct"], reverse=reverse)[:20]
    lines = ["| Variant | Symbol | Entry | Exit | Reason | Return | Funding | Hold | MAE | MFE |", "|---|---|---|---|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['variant']} | {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['exit_reason']} | "
            f"{pct(row['trade_return_after_funding_pct'])} | {num(row['funding_pnl'])} | {num(row['hold_days'])} | {pct(row['mae_pct'])} | {pct(row['mfe_pct'])} |"
        )
    return "\n".join(lines)


def yearly_table(rows: List[dict]) -> str:
    names = []
    for row in rows:
        if row["funding"] == "actual" and row["name"] not in names:
            names.append(row["name"])
    years = sorted({row["year"] for row in rows})
    lookup = {(row["name"], row["funding"], row["year"]): row["return_pct"] for row in rows}
    lines = ["| Name | " + " | ".join(years) + " |", "|" + "|".join(["---"] * (len(years) + 1)) + "|"]
    for name in names[:14]:
        lines.append("| " + " | ".join([name] + [pct(lookup.get((name, "actual", year), lookup.get((name, "excluded", year)))) for year in years]) + " |")
    return "\n".join(lines)


def monthly_sample_table(data: ShortData, rows: List[dict]) -> str:
    names = ["Short Engine v0 / 4 symbols", "Short Engine v0 / 9 symbols", "BTC Buy & Hold"]
    sample_months = data.months[-12:]
    lookup = {(row["name"], row["funding"], row["month"]): row["return_pct"] for row in rows}
    lines = ["| Name | " + " | ".join(sample_months) + " |", "|" + "|".join(["---"] * (len(sample_months) + 1)) + "|"]
    for name in names:
        funding = "actual" if name.startswith("Short") else "excluded"
        lines.append("| " + " | ".join([name] + [pct(lookup.get((name, funding, month))) for month in sample_months]) + " |")
    return "\n".join(lines)


def coverage_table(data: ShortData, funding_by_symbol: Dict[str, List[dict]]) -> str:
    lines = ["| Symbol | 1D | 4H | 1H | Funding | 1H first | 1H last |", "|---|---:|---:|---:|---:|---|---|"]
    for symbol in BASE_UNIVERSE_9:
        rows_1h = data.raw_1h.get(symbol, [])
        funding_rows = funding_by_symbol.get(symbol, [])
        lines.append(
            f"| {short_symbol(symbol)} | {len(data.raw_1d.get(symbol, []))} | {len(data.raw_4h.get(symbol, []))} | "
            f"{len(rows_1h)} | {len(funding_rows)} | {format_dt(rows_1h[0]['time']) if rows_1h else ''} | {format_dt(rows_1h[-1]['time']) if rows_1h else ''} |"
        )
    return "\n".join(lines)


def load_alpha_long_reference(output_dir: Path) -> List[dict]:
    path = output_dir / "alpha_engine_v1_2_candidate_summary.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        row for row in rows
        if row.get("variant") == "Candidate v1.2 / leverage cap" and row.get("run_group") == "default"
    ] or rows[:1]
    out = []
    for row in selected[:2]:
        out.append(
            {
                "name": f"Reference only / Alpha Long Engine v1.2 / {row.get('variant', '')}",
                "group": "Reference",
                "funding": row.get("funding", "actual"),
                "universe_size": "",
                "fill_mode": "",
                "shock_mode": "",
                "max_hold_days": "",
                "slippage_rate_pct": row.get("slippage_rate_pct", ""),
                "fee_rate_pct": row.get("fee_rate_pct", ""),
                "total_return_pct": to_float(row.get("total_return_pct")),
                "cagr_pct": to_float(row.get("cagr_pct")),
                "mdd_pct": to_float(row.get("mdd_pct")),
                "sharpe": to_float(row.get("sharpe")),
                "calmar": to_float(row.get("calmar")),
                "profit_factor": to_float(row.get("profit_factor")),
                "win_rate_pct": "",
                "avg_payoff_ratio": "",
                "trades": row.get("trades", ""),
                "avg_monthly_trades": row.get("avg_monthly_trades", ""),
                "avg_hold_days": row.get("avg_hold_days", ""),
                "median_hold_days": row.get("median_hold_days", ""),
                "max_hold_days_actual": "",
                "avg_entry_after_1d_pct": "",
                "avg_entry_after_3d_pct": "",
                "avg_entry_after_7d_pct": "",
                "avg_mae_pct": "",
                "avg_mfe_pct": "",
                "avg_mae_mfe_ratio": "",
                "avg_winning_trade_pct": "",
                "avg_losing_trade_pct": "",
                "funding_pnl": "",
                "funding_cost": "",
                "funding_income": "",
                "funding_cost_income_ratio": "",
                "liquidation_risk_trades": row.get("liquidation_risk_trades", ""),
                "liquidation_buffer_failed_skips": "",
                "signal_count": "",
                "entry_count": "",
                "skip_total": row.get("skipped_trades", ""),
                "skip_reasons": row.get("skip_reasons", ""),
                "max_symbol_positive_pnl_share_pct": row.get("max_symbol_positive_pnl_share_pct", ""),
            }
        )
    return out


def load_futures_raw(symbols: Iterable[str], interval: str, use_cache: bool, start: str, end: str) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, List[dict]] = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}_futures_{interval}.json"
        cached = read_cache(path) if use_cache else []
        if cached:
            out[symbol] = cached
            continue
        rows = fetch_futures_ohlcv(symbol, interval, start, end)
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
    return {
        "time": int(item[0]) // 1000,
        "open": float(item[1]),
        "high": float(item[2]),
        "low": float(item[3]),
        "close": float(item[4]),
        "volume": float(item[5]),
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


def load_funding_history(symbol: str, use_cache: bool, interval_hours: Optional[float], end_ts: int) -> List[dict]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{symbol}_futures_funding_rate.json"
    cached = read_cache(path) if use_cache else []
    if cached:
        return normalize_funding_rows(symbol, cached, interval_hours, end_ts)
    rows: List[dict] = []
    cursor_ms = TEST_START_TS * 1000
    end_ms = end_ts * 1000
    while cursor_ms < end_ms:
        batch = request_json("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": cursor_ms, "endTime": end_ms, "limit": 1000})
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
    return normalize_funding_rows(symbol, rows, interval_hours, end_ts)


def normalize_funding_rows(symbol: str, rows: List[dict], interval_hours: Optional[float], end_ts: int) -> List[dict]:
    out = []
    sorted_rows = sorted(rows, key=lambda row: int(row["fundingTime"]))
    for index, row in enumerate(sorted_rows):
        funding_time = int(row["fundingTime"]) // 1000
        if funding_time < TEST_START_TS or funding_time >= end_ts:
            continue
        inferred_hours = interval_hours
        if inferred_hours is None and index > 0:
            inferred_hours = (int(row["fundingTime"]) - int(sorted_rows[index - 1]["fundingTime"])) / 3600000
        out.append(
            {
                "symbol": symbol,
                "funding_time": funding_time,
                "funding_date": format_dt(funding_time),
                "funding_rate": float(row.get("fundingRate", 0.0)),
                "mark_price": float(row.get("markPrice") or 0.0),
                "funding_interval_hours": float(inferred_hours or 8.0),
            }
        )
    return out


def request_json(path: str, params: dict) -> list:
    query = urlencode(params)
    last_error: Optional[Exception] = None
    for base_url in FAPI_BASE_URLS:
        request = Request(f"{base_url}{path}" + (f"?{query}" if query else ""), headers={"User-Agent": "crypto-regime-map/0.1"})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
    raise RuntimeError(f"Binance futures request failed for {path}: {last_error}") from last_error


def portfolio_equity(cash: float, positions: Dict[str, Position], data: ShortData, open_time: int) -> float:
    equity = cash
    for symbol, position in positions.items():
        row = data.by_time_1h.get(symbol, {}).get(open_time)
        if row:
            equity += position.units * (position.entry_price - row["close"])
    return equity


def short_entry_quality(data: ShortData, symbol: str, entry_time: int, entry_price: float) -> dict:
    by_time = data.by_time_1h.get(symbol, {})
    out = {}
    for days in (1, 3, 7):
        row = by_time.get(entry_time + days * 86400)
        out[f"entry_after_{days}d_pct"] = (entry_price / row["close"] - 1) * 100 if row and row["close"] else None
    return out


def short_trade_excursion(data: ShortData, symbol: str, entry_time: int, exit_time: int, entry_price: float) -> dict:
    rows = [row for row in data.rows_1h.get(symbol, []) if entry_time <= row["time"] <= exit_time]
    if not rows:
        return {"mae_pct": None, "mfe_pct": None}
    adverse = max(row["high"] for row in rows) / entry_price - 1
    favorable = entry_price / min(row["low"] for row in rows) - 1
    return {
        "mae_pct": min(0.0, -adverse) * 100 if adverse > 0 else 0.0,
        "mfe_pct": max(0.0, favorable) * 100,
    }


def mark_price_for(data: ShortData, symbol: str, timestamp: int) -> Optional[float]:
    row = data.by_time_1h.get(symbol, {}).get(timestamp)
    if row:
        return row["close"]
    rows = data.rows_1h.get(symbol, [])
    times = [row["time"] for row in rows]
    index = bisect_right(times, timestamp) - 1
    if index >= 0:
        return rows[index]["close"]
    return None


def short_liquidation_price(entry_price: float, leverage: int) -> float:
    if leverage <= 0:
        return entry_price
    return entry_price * (1 + 1 / leverage - MAINTENANCE_MARGIN_RATE - LIQUIDATION_FEE_BUFFER)


def max_drawdown(curve: List[dict]) -> float:
    peak = None
    worst = 0.0
    for point in curve:
        equity = point["equity"]
        peak = equity if peak is None else max(peak, equity)
        if peak and peak > 0:
            worst = min(worst, equity / peak - 1)
    return worst


def build_time_index(rows_by_symbol: Dict[str, List[dict]], time_key: str = "time") -> Dict[str, Tuple[List[int], List[dict]]]:
    return {symbol: ([int(row[time_key]) for row in rows], rows) for symbol, rows in rows_by_symbol.items()}


def slice_time_index(index: Dict[str, Tuple[List[int], List[dict]]], symbol: str, start_time: int, end_time: int) -> List[dict]:
    times, rows = index.get(symbol, ([], []))
    left = bisect_left(times, start_time)
    right = bisect_left(times, end_time)
    return rows[left:right]


def add_trade_run_metadata(trades: List[dict], config: ShortConfig, funding_key: str, funding_name: str) -> List[dict]:
    return [{**trade, "funding": funding_name, "funding_key": funding_key} for trade in trades]


def month_range(start: str, end: str) -> List[str]:
    start_year, start_month = [int(part) for part in start.split("-")]
    end_year, end_month = [int(part) for part in end.split("-")]
    year, month = start_year, start_month
    out = []
    while (year, month) <= (end_year, end_month):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return out


def read_cache(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe_configs(configs: List[ShortConfig]) -> List[ShortConfig]:
    seen = set()
    out = []
    for config in configs:
        key = config.name
        if key not in seen:
            seen.add(key)
            out.append(config)
    return out


def short_symbol(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def date_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def format_dt(timestamp: Optional[int]) -> str:
    if timestamp in {None, ""}:
        return ""
    return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y-%m-%d %H:%M")


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


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, "", 0, 0.0, "0", "false", "False"}:
        return False
    return bool(value)


def to_float(value) -> Optional[float]:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen and not key.startswith("_"):
                seen.add(key)
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{key: value for key, value in row.items() if not key.startswith("_")} for row in rows])


if __name__ == "__main__":
    main()
