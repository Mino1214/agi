"""Alpha Engine v1 research report.

This script leaves the BTC/ETH Monthly Strength v1 files unchanged. It uses the
existing regime engine only as a trade permission filter, then tests 4H alpha
signals with 1H execution and risk-based sizing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
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


FETCH_DAILY_START = "2018-01-01T00:00:00+00:00"
FETCH_INTRADAY_START = "2019-01-01T00:00:00+00:00"
FETCH_END = "2026-01-02T00:00:00+00:00"
TEST_START_TS = int(datetime.fromisoformat("2020-01-01T00:00:00+00:00").timestamp())
TEST_END_TS = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
MONTHS = v1.month_range("2020-01", "2025-12")
UNIVERSE_4 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
UNIVERSE_10 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "DOGEUSDT", "ADAUSDT", "TONUSDT"]
BASE_FEE_RATE = 0.001
BASE_SLIPPAGE_RATE = 0.0005
BASE_RISK_PER_SYMBOL = 0.005
MAX_PORTFOLIO_RISK = 0.015
MAX_POSITIONS = 3
MAX_HOLD_HOURS = 14 * 24
MIN_ALPHA_SCORE = 5.0
OVEREXTENSION_ATR_MULTIPLE = 2.0
PULLBACK_ATR_TOLERANCE = 0.25
STOP_ATR_MULTIPLE = 2.0
SWING_LOW_LOOKBACK_HOURS = 20
TOO_MANY_TRADES_PER_MONTH = 20.0
SYMBOL_CONCENTRATION_WARNING = 0.60


@dataclass(frozen=True)
class AlphaConfig:
    name: str
    universe: Tuple[str, ...]
    fill_mode: str = "next_open"
    defensive_mode: str = "no_entry"
    max_leverage: float = 3.0
    shock_exit: bool = True
    fee_rate: float = BASE_FEE_RATE
    slippage_rate: float = BASE_SLIPPAGE_RATE
    group: str = "Alpha"


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
    entry_index_1h: int
    entry_equity: float
    signal_time: int
    signal_score: float
    regime: str
    action_bias: str
    realized_pnl: float = 0.0
    partial_taken: bool = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use cached raw JSON if it covers the required window.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = load_raw(UNIVERSE_10, "1d", args.use_cache, FETCH_DAILY_START)
    raw_4h = load_raw(UNIVERSE_10, "4h", args.use_cache, FETCH_INTRADAY_START)
    raw_1h = load_raw(UNIVERSE_10, "1h", args.use_cache, FETCH_INTRADAY_START)

    data = AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    monthly_v1, buy_hold_btc, buy_hold_eth = benchmark_results(raw_1d)

    base_configs = [
        AlphaConfig("Alpha Engine v1 / 4 symbols", tuple(UNIVERSE_4)),
        AlphaConfig("Alpha Engine v1 / 10 symbols", tuple(UNIVERSE_10)),
        AlphaConfig("Alpha Engine v1 / BTC only", ("BTCUSDT",)),
        AlphaConfig("Alpha Engine v1 / ETH only", ("ETHUSDT",)),
        AlphaConfig("Alpha Engine v1 / BTC/ETH only", ("BTCUSDT", "ETHUSDT")),
    ]
    sensitivity_configs = [
        AlphaConfig("Alpha Engine v1 / 4 symbols / defensive 50%", tuple(UNIVERSE_4), defensive_mode="half_size", group="Regime sensitivity"),
        AlphaConfig("Alpha Engine v1 / 10 symbols / defensive 50%", tuple(UNIVERSE_10), defensive_mode="half_size", group="Regime sensitivity"),
        AlphaConfig("Alpha Engine v1 / 4 symbols / next 1H close", tuple(UNIVERSE_4), fill_mode="next_close", group="Timing sensitivity"),
        AlphaConfig("Alpha Engine v1 / 10 symbols / next 1H close", tuple(UNIVERSE_10), fill_mode="next_close", group="Timing sensitivity"),
        AlphaConfig("Alpha Engine v1 / 4 symbols / no shock exit", tuple(UNIVERSE_4), shock_exit=False, group="Exit sensitivity"),
        AlphaConfig("Alpha Engine v1 / 10 symbols / no shock exit", tuple(UNIVERSE_10), shock_exit=False, group="Exit sensitivity"),
    ]
    leverage_configs = [
        AlphaConfig(f"Alpha Engine v1 / 4 symbols / {lev:.0f}x", tuple(UNIVERSE_4), max_leverage=lev, group="Leverage sensitivity")
        for lev in (2.0, 3.0, 4.0)
    ] + [
        AlphaConfig(f"Alpha Engine v1 / 10 symbols / {lev:.0f}x", tuple(UNIVERSE_10), max_leverage=lev, group="Leverage sensitivity")
        for lev in (2.0, 3.0, 4.0)
    ]
    cost_configs = [
        AlphaConfig("Alpha Engine v1 / 4 symbols / low cost", tuple(UNIVERSE_4), fee_rate=0.0005, slippage_rate=0.0002, group="Cost sensitivity"),
        AlphaConfig("Alpha Engine v1 / 4 symbols / base cost", tuple(UNIVERSE_4), fee_rate=BASE_FEE_RATE, slippage_rate=BASE_SLIPPAGE_RATE, group="Cost sensitivity"),
        AlphaConfig("Alpha Engine v1 / 4 symbols / high cost", tuple(UNIVERSE_4), fee_rate=0.0020, slippage_rate=0.0010, group="Cost sensitivity"),
    ]
    configs = dedupe_configs(base_configs + sensitivity_configs + leverage_configs + cost_configs)

    results = [run_alpha_engine(data, config) for config in configs]
    benchmark_rows = [
        benchmark_summary_row("BTC/ETH Monthly Strength v1", "Benchmark", monthly_v1.summary, monthly_v1.monthly_rows),
        benchmark_summary_row("Buy & Hold BTC", "Benchmark", buy_hold_btc.summary, buy_hold_btc.monthly_rows),
        benchmark_summary_row("Buy & Hold ETH", "Benchmark", buy_hold_eth.summary, buy_hold_eth.monthly_rows),
    ]
    summary_rows = benchmark_rows + [result["summary"] for result in results]
    monthly_rows = benchmark_monthly_rows(monthly_v1, buy_hold_btc, buy_hold_eth) + [row for result in results for row in result["monthly"]]
    yearly_rows = benchmark_yearly_rows(monthly_v1, buy_hold_btc, buy_hold_eth) + [row for result in results for row in result["yearly"]]
    trades = [trade for result in results for trade in result["trades"]]
    signals = data.signal_rows
    pass_fail_rows = pass_fail(summary_rows)

    report = build_report(
        data=data,
        summary_rows=summary_rows,
        monthly_rows=monthly_rows,
        yearly_rows=yearly_rows,
        trades=trades,
        signals=signals,
        pass_fail_rows=pass_fail_rows,
    )

    report_path = output_dir / "alpha_engine_v1_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_engine_v1_summary.csv", summary_rows)
    write_csv(output_dir / "alpha_engine_v1_trades.csv", trades)
    write_csv(output_dir / "alpha_engine_v1_signals.csv", signals)
    print(report_path)


class AlphaData:
    def __init__(self, raw_1d: Dict[str, List[dict]], raw_4h: Dict[str, List[dict]], raw_1h: Dict[str, List[dict]]):
        self.raw_1d = raw_1d
        self.raw_4h = raw_4h
        self.raw_1h = raw_1h
        self.rows_4h = {symbol: add_4h_features(rows) for symbol, rows in raw_4h.items()}
        self.rows_1h = {symbol: add_1h_features(rows) for symbol, rows in raw_1h.items()}
        self.by_time_4h = {symbol: {row["time"]: row for row in rows} for symbol, rows in self.rows_4h.items()}
        self.by_close_4h = {symbol: {row["close_time"]: row for row in rows} for symbol, rows in self.rows_4h.items()}
        self.by_time_1h = {symbol: {row["time"]: row for row in rows} for symbol, rows in self.rows_1h.items()}
        self.times_1h = [row["time"] for row in self.rows_1h["BTCUSDT"] if TEST_START_TS <= row["time"] < TEST_END_TS]
        self.index_1h = {time: index for index, time in enumerate(self.times_1h)}
        self.regime_by_date = build_trade_regime(raw_1d)
        self.signal_cache: Dict[Tuple[Tuple[str, ...], str], List[dict]] = {}
        self.signal_rows: List[dict] = []

    def signals_for(self, universe: Tuple[str, ...], fill_mode: str) -> List[dict]:
        key = (universe, fill_mode)
        if key not in self.signal_cache:
            self.signal_cache[key] = build_signals(self, list(universe), fill_mode)
            self.signal_rows.extend(self.signal_cache[key])
        return self.signal_cache[key]


def load_raw(symbols: Iterable[str], interval: str, use_cache: bool, start: str) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for symbol in symbols:
        cache_path = raw_dir / f"{symbol}_{interval}.json"
        cached = v1.read_cache(cache_path) if use_cache else []
        if cached and covers_window(cached, start):
            out[symbol] = cached
        else:
            candles = v1.fetch_ohlcv(symbol, interval, start, FETCH_END)
            cache_path.write_text(json.dumps(candles, ensure_ascii=False), encoding="utf-8")
            out[symbol] = candles
    return out


def covers_window(candles: List[dict], start: str) -> bool:
    if not candles:
        return False
    start_ts = int(datetime.fromisoformat(start).timestamp())
    end_ts = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
    return candles[0]["time"] <= start_ts and candles[-1]["time"] >= end_ts


def add_4h_features(candles: List[dict]) -> List[dict]:
    rows = [dict(row) for row in candles]
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    ema20 = v1.ema(closes, 20)
    ema50 = v1.ema(closes, 50)
    atr14 = swing.atr(rows, 14)
    volume20 = rolling_average(volumes, 20)
    for index, row in enumerate(rows):
        row["close_time"] = row["time"] + 4 * 3600
        row["ema20"] = ema20[index]
        row["ema50"] = ema50[index]
        row["atr14"] = atr14[index]
        row["volume20"] = volume20[index]
        row["ret_7d"] = row["close"] / rows[index - 42]["close"] - 1 if index >= 42 and rows[index - 42]["close"] else None
        row["ret_14d"] = row["close"] / rows[index - 84]["close"] - 1 if index >= 84 and rows[index - 84]["close"] else None
        recent = rows[max(0, index - 9) : index + 1]
        row["recent_ema20_pullback"] = any(
            item.get("ema20") is not None
            and item.get("atr14") is not None
            and item["low"] <= item["ema20"] + PULLBACK_ATR_TOLERANCE * item["atr14"]
            for item in recent
        )
        row["recent_ema50_pullback"] = any(
            item.get("ema50") is not None
            and item.get("atr14") is not None
            and item["low"] <= item["ema50"] + PULLBACK_ATR_TOLERANCE * item["atr14"]
            for item in recent
        )
    return rows


def add_1h_features(candles: List[dict]) -> List[dict]:
    rows = [dict(row) for row in candles]
    atr14 = swing.atr(rows, 14)
    for index, row in enumerate(rows):
        row["close_time"] = row["time"] + 3600
        row["atr14"] = atr14[index]
        lows = [rows[item]["low"] for item in range(max(0, index - SWING_LOW_LOOKBACK_HOURS), index + 1)]
        row["swing_low20"] = min(lows) if lows else None
    return rows


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
    payload = v1.build_payload_from_raw(raw_1d, interval="1d", start=FETCH_DAILY_START, symbols=UNIVERSE_10)
    out = {}
    for point in payload["points"]:
        date = date_from_ts(point["time"])
        out[date] = {
            "trade_regime": point.get("trade_regime"),
            "trade_action_bias": point.get("trade_action_bias"),
        }
    return out


def build_signals(data: AlphaData, universe: List[str], fill_mode: str) -> List[dict]:
    signals = []
    btc_by_time = data.by_time_4h["BTCUSDT"]
    all_times = sorted(set().union(*(set(data.by_time_4h[symbol].keys()) for symbol in universe if symbol in data.by_time_4h)))
    for time in all_times:
        if time < TEST_START_TS - 14 * 86400 or time >= TEST_END_TS:
            continue
        rows = {symbol: data.by_time_4h.get(symbol, {}).get(time) for symbol in universe}
        rows = {symbol: row for symbol, row in rows.items() if row}
        if not rows:
            continue
        btc = btc_by_time.get(time)
        if not btc or btc.get("ret_7d") is None or btc.get("ret_14d") is None:
            continue
        close_time = time + 4 * 3600
        if close_time < TEST_START_TS:
            continue
        regime_date = date_from_ts(close_time)
        regime = data.regime_by_date.get(regime_date, {})
        allowed_symbols, size_multiplier, block_reason = allowed_by_regime(universe, regime)
        if not allowed_symbols:
            continue
        rank_values = {
            symbol: 0.5 * (row.get("ret_7d") or -999) + 0.5 * (row.get("ret_14d") or -999)
            for symbol, row in rows.items()
            if row.get("ret_7d") is not None and row.get("ret_14d") is not None
        }
        ranked = sorted(rank_values, key=rank_values.get, reverse=True)
        rank_lookup = {symbol: rank + 1 for rank, symbol in enumerate(ranked)}
        candidates = []
        for symbol in allowed_symbols:
            row = rows.get(symbol)
            if not row or symbol not in rank_lookup:
                continue
            signal = score_signal(symbol, row, btc, rank_lookup[symbol], len(ranked), regime, size_multiplier, block_reason)
            if signal and signal["alpha_score"] >= MIN_ALPHA_SCORE:
                candidates.append(signal)
        candidates.sort(key=lambda item: (item["alpha_score"], -item["rank"]), reverse=True)
        for signal in candidates:
            signal["variant"] = f"universe_{len(universe)}_{fill_mode}"
            signal["signal_time"] = close_time
            signal["signal_date"] = format_dt(close_time)
            signal["fill_mode"] = fill_mode
            signal["lookahead_pass"] = True
            signals.append(signal)
    return signals


def allowed_by_regime(universe: List[str], regime: dict) -> Tuple[List[str], float, str]:
    trade_regime = regime.get("trade_regime")
    action_bias = regime.get("trade_action_bias")
    if trade_regime in {None, "shock", "observe", "neutral"} or action_bias in {None, "no_new_entry", "wait"}:
        return [], 0.0, str(action_bias or trade_regime)
    if trade_regime == "defensive" or action_bias == "reduce_risk":
        return list(universe), 0.5, "defensive_reduce_risk"
    if trade_regime == "large_cap_lead" or action_bias == "btc_eth_preferred":
        return [symbol for symbol in universe if symbol in {"BTCUSDT", "ETHUSDT"}], 1.0, "large_cap_lead"
    if trade_regime == "eth_strength" or action_bias == "alt_watch":
        return [symbol for symbol in universe if symbol != "BTCUSDT"], 1.0, "eth_strength"
    if trade_regime == "uptrend" or action_bias == "long_allowed":
        return list(universe), 1.0, "uptrend"
    return [], 0.0, str(action_bias or trade_regime)


def score_signal(symbol: str, row: dict, btc: dict, rank: int, universe_size: int, regime: dict, size_multiplier: float, block_reason: str) -> Optional[dict]:
    if None in {row.get("ema20"), row.get("ema50"), row.get("atr14"), row.get("volume20")}:
        return None
    close = row["close"]
    atr = row["atr14"]
    trend_ok = close > row["ema50"] and row["ema20"] > row["ema50"]
    if not trend_ok:
        return None
    overextended = close > row["ema20"] + OVEREXTENSION_ATR_MULTIPLE * atr
    if overextended:
        return None
    pullback = recent_pullback(row)
    if pullback <= 0:
        return None
    recovered = close > row["ema20"]
    if not recovered:
        return None
    ret_7d = row["ret_7d"]
    ret_14d = row["ret_14d"]
    btc_excess_7d = ret_7d - btc["ret_7d"] if ret_7d is not None else None
    btc_excess_14d = ret_14d - btc["ret_14d"] if ret_14d is not None else None
    trend_score = 2.0
    relative_strength_score = 0.0
    if ret_7d and ret_7d > 0:
        relative_strength_score += 1.0
    if ret_14d and ret_14d > 0:
        relative_strength_score += 1.0
    if btc_excess_7d and btc_excess_7d > 0:
        relative_strength_score += 1.0
    if rank <= max(1, math.ceil(universe_size * 0.30)):
        relative_strength_score += 1.0
    pullback_score = pullback
    volume_score = 1.0 if row["volume"] > row["volume20"] * 1.2 else 0.0
    atr_pct = atr / close if close else 999
    risk_distance_score = 1.5 if atr_pct <= 0.035 else 1.0 if atr_pct <= 0.06 else 0.5
    alpha_score = trend_score + relative_strength_score + pullback_score + volume_score + risk_distance_score
    return {
        "variant": "",
        "symbol": v1.short(symbol),
        "signal_date": "",
        "signal_time": 0,
        "trade_regime": regime.get("trade_regime"),
        "trade_action_bias": regime.get("trade_action_bias"),
        "regime_size_multiplier": size_multiplier,
        "regime_reason": block_reason,
        "rank": rank,
        "universe_size": universe_size,
        "trend_score": trend_score,
        "relative_strength_score": relative_strength_score,
        "pullback_score": pullback_score,
        "volume_score": volume_score,
        "risk_distance_score": risk_distance_score,
        "alpha_score": alpha_score,
        "ret_7d_pct": ret_7d * 100 if ret_7d is not None else None,
        "ret_14d_pct": ret_14d * 100 if ret_14d is not None else None,
        "btc_excess_7d_pct": btc_excess_7d * 100 if btc_excess_7d is not None else None,
        "btc_excess_14d_pct": btc_excess_14d * 100 if btc_excess_14d is not None else None,
        "close": close,
        "ema20": row["ema20"],
        "ema50": row["ema50"],
        "atr14": atr,
    }


def recent_pullback(row: dict) -> float:
    if row.get("recent_ema50_pullback"):
        return 2.0
    if row.get("recent_ema20_pullback"):
        return 1.5
    return 0.0


def run_alpha_engine(data: AlphaData, config: AlphaConfig) -> dict:
    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    equity_curve = [{"time": TEST_START_TS, "date": format_dt(TEST_START_TS), "equity": 1.0}]
    signals_by_time = defaultdict(list)
    for signal in data.signals_for(config.universe, config.fill_mode):
        if config.defensive_mode == "no_entry" and signal["regime_reason"] == "defensive_reduce_risk":
            continue
        signal = dict(signal)
        signal["variant"] = config.name
        signals_by_time[signal["signal_time"]].append(signal)

    for index, time in enumerate(data.times_1h):
        row_btc = data.by_time_1h["BTCUSDT"].get(time)
        if not row_btc:
            continue
        close_time = time + 3600

        for symbol in list(positions):
            position = positions[symbol]
            row = data.by_time_1h.get(symbol, {}).get(time)
            if not row:
                continue
            cash, closed = manage_position(data, config, position, row, time, close_time, index, cash)
            if closed:
                trades.append(closed)
                positions.pop(symbol, None)

        if config.shock_exit and is_shock_date(data, date_from_ts(close_time)):
            for symbol in list(positions):
                row = data.by_time_1h.get(symbol, {}).get(time)
                if row:
                    trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), close_time, index, "shock_exit")
                    cash += trade.pop("_cash_delta")
                    trades.append(trade)

        for signal in sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True):
            symbol = f"{signal['symbol']}USDT"
            if symbol in positions or symbol in pending:
                continue
            pending[symbol] = {**signal, "symbol": symbol, "fill_time": time}

        due_orders = [order for order in pending.values() if order["fill_time"] == time]
        for order in sorted(due_orders, key=lambda item: item["alpha_score"], reverse=True):
            pending.pop(order["symbol"], None)
            if order["symbol"] in positions:
                continue
            if len(positions) >= MAX_POSITIONS:
                continue
            row = data.by_time_1h.get(order["symbol"], {}).get(time)
            if not row or row.get("atr14") is None:
                continue
            fill_price_key = "open" if config.fill_mode == "next_open" else "close"
            fill_time = time if config.fill_mode == "next_open" else close_time
            if fill_time <= order["signal_time"] and config.fill_mode == "next_close":
                continue
            equity = portfolio_equity(cash, positions, data, time)
            position, fee = create_position(data, config, order, row, fill_price_key, fill_time, index, equity, positions)
            if position:
                cash -= fee
                positions[position.symbol] = position

        equity_curve.append({"time": close_time, "date": format_dt(close_time), "equity": portfolio_equity(cash, positions, data, time)})

    last_time = data.times_1h[-1]
    last_index = len(data.times_1h) - 1
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(last_time)
        if row:
            trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), last_time + 3600, last_index, "end_of_test")
            cash += trade.pop("_cash_delta")
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": format_dt(last_time + 3600), "equity": cash})

    monthly = monthly_returns_from_curve(config.name, equity_curve)
    yearly = yearly_rows_from_monthly(config.name, monthly)
    summary = summary_row(config, equity_curve, trades, monthly)
    return {"summary": summary, "trades": trades, "monthly": monthly, "yearly": yearly, "equity_curve": equity_curve}


def create_position(
    data: AlphaData,
    config: AlphaConfig,
    order: dict,
    row: dict,
    price_key: str,
    fill_time: int,
    index_1h: int,
    equity: float,
    positions: Dict[str, Position],
) -> Tuple[Optional[Position], float]:
    raw_price = row[price_key]
    entry_price = raw_price * (1 + config.slippage_rate)
    atr_stop = entry_price - STOP_ATR_MULTIPLE * row["atr14"]
    swing_stop = row.get("swing_low20") or atr_stop
    stop_price = max(atr_stop, swing_stop)
    if stop_price >= entry_price:
        stop_price = atr_stop
    risk_distance = entry_price - stop_price
    if risk_distance <= 0:
        return None, 0.0
    size_multiplier = order["regime_size_multiplier"] if config.defensive_mode == "half_size" else 1.0
    base_risk = equity * BASE_RISK_PER_SYMBOL * size_multiplier
    open_risk = sum(position.risk_amount for position in positions.values())
    risk_budget = min(base_risk, max(0.0, equity * MAX_PORTFOLIO_RISK - open_risk))
    if risk_budget <= 0:
        return None, 0.0
    units = risk_budget / risk_distance
    max_exposure = equity * config.max_leverage
    current_exposure = sum(position.units * position.entry_price for position in positions.values())
    max_notional = max(0.0, max_exposure - current_exposure)
    notional = min(units * entry_price, max_notional)
    if notional <= 1e-12:
        return None, 0.0
    units = notional / entry_price
    risk_amount = units * risk_distance
    fee = notional * config.fee_rate
    return (
        Position(
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
        ),
        fee,
    )


def manage_position(
    data: AlphaData,
    config: AlphaConfig,
    position: Position,
    row: dict,
    open_time: int,
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
    row_4h = data.by_close_4h.get(position.symbol, {}).get(close_time)
    if row_4h:
        if row_4h.get("ema50") is not None and row_4h["close"] < row_4h["ema50"]:
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema50_exit")
            return cash + trade.pop("_cash_delta"), trade
        if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] < row_4h["ema20"]:
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema20_trailing_exit")
            return cash + trade.pop("_cash_delta"), trade
    if close_time - position.entry_time >= MAX_HOLD_HOURS * 3600:
        trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "max_hold")
        return cash + trade.pop("_cash_delta"), trade
    return cash, None


def close_trade(data: AlphaData, config: AlphaConfig, position: Position, exit_price: float, exit_time: int, index_1h: int, reason: str) -> dict:
    gross_pnl = position.units * (exit_price - position.entry_price)
    fee = position.units * exit_price * config.fee_rate
    total_pnl = position.realized_pnl + gross_pnl - fee
    quality = entry_quality(data, position.symbol, position.entry_time, position.entry_price)
    excursion = trade_excursion(data, position.symbol, position.entry_time, exit_time, position.entry_price)
    return {
        "variant": config.name,
        "symbol": v1.short(position.symbol),
        "entry_date": format_dt(position.entry_time),
        "exit_date": format_dt(exit_time),
        "entry_timestamp": position.entry_time,
        "exit_timestamp": exit_time,
        "signal_date": format_dt(position.signal_time),
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
        "_cash_delta": total_pnl,
    }


def portfolio_equity(cash: float, positions: Dict[str, Position], data: AlphaData, time: int) -> float:
    equity = cash
    for symbol, position in positions.items():
        row = data.by_time_1h.get(symbol, {}).get(time)
        if row:
            equity += position.units * (row["close"] - position.entry_price)
    return equity


def is_shock_date(data: AlphaData, date: str) -> bool:
    regime = data.regime_by_date.get(date, {})
    return regime.get("trade_regime") == "shock" or regime.get("trade_action_bias") == "no_new_entry"


def entry_quality(data: AlphaData, symbol: str, entry_time: int, entry_price: float) -> dict:
    by_time = data.by_time_1h[symbol]
    out = {}
    for days in (1, 3, 7):
        row = by_time.get(entry_time + days * 86400)
        out[f"entry_after_{days}d_pct"] = (row["close"] / entry_price - 1) * 100 if row else None
    return out


def trade_excursion(data: AlphaData, symbol: str, entry_time: int, exit_time: int, entry_price: float) -> dict:
    rows = [row for row in data.rows_1h[symbol] if entry_time <= row["time"] <= exit_time]
    if not rows:
        return {"mae_pct": None, "mfe_pct": None}
    return {
        "mae_pct": min(0.0, min(row["low"] for row in rows) / entry_price - 1) * 100,
        "mfe_pct": max(0.0, max(row["high"] for row in rows) / entry_price - 1) * 100,
    }


def benchmark_results(raw_1d: Dict[str, List[dict]]) -> Tuple[v1.StrategyResult, v1.StrategyResult, v1.StrategyResult]:
    raw = {symbol: raw_1d[symbol] for symbol in ["BTCUSDT", "ETHUSDT"]}
    payload = v1.build_payload_from_raw(raw, interval="1d", start=FETCH_DAILY_START, symbols=["BTCUSDT", "ETHUSDT"])
    data = v1.BacktestData(raw=raw, payload=payload)
    return (
        v1.run_strength_strategy(data, v1.base_config()),
        v1.run_static_strategy(data, v1.StaticConfig(name="Buy & Hold BTC", weights={"BTCUSDT": 1.0})),
        v1.run_static_strategy(data, v1.StaticConfig(name="Buy & Hold ETH", weights={"ETHUSDT": 1.0})),
    )


def summary_row(config: AlphaConfig, equity_curve: List[dict], trades: List[dict], monthly: List[dict]) -> dict:
    final_equity = equity_curve[-1]["equity"] if equity_curve else 1.0
    years = (TEST_END_TS - TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [equity_curve[index]["equity"] / equity_curve[index - 1]["equity"] - 1 for index in range(1, len(equity_curve)) if equity_curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(equity_curve)
    trade_returns = [trade["trade_return_pct"] for trade in trades]
    wins = [value for value in trade_returns if value > 0]
    losses = [value for value in trade_returns if value < 0]
    gross_loss = abs(sum(losses))
    avg_win = statistics.mean(wins) if wins else None
    avg_loss = statistics.mean(losses) if losses else None
    by_symbol = symbol_performance(trades)
    best_symbol_share = max((row["pnl"] for row in by_symbol), default=0.0) / sum((row["pnl"] for row in by_symbol if row["pnl"] > 0), 1e-12)
    return {
        "name": config.name,
        "group": config.group,
        "universe_size": len(config.universe),
        "fill_mode": config.fill_mode,
        "defensive_mode": config.defensive_mode,
        "max_leverage": config.max_leverage,
        "shock_exit": config.shock_exit,
        "fee_rate_pct": config.fee_rate * 100,
        "slippage_rate_pct": config.slippage_rate * 100,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "payoff_ratio": avg_win / abs(avg_loss) if avg_win is not None and avg_loss and avg_loss < 0 else None,
        "avg_hold_days": mean_present([trade["hold_days"] for trade in trades]),
        "trades": len(trades),
        "avg_monthly_trades": len(trades) / len(MONTHS),
        "avg_entry_after_1d_pct": mean_present([trade["entry_after_1d_pct"] for trade in trades]),
        "avg_entry_after_3d_pct": mean_present([trade["entry_after_3d_pct"] for trade in trades]),
        "avg_entry_after_7d_pct": mean_present([trade["entry_after_7d_pct"] for trade in trades]),
        "avg_mae_pct": mean_present([trade["mae_pct"] for trade in trades]),
        "avg_mfe_pct": mean_present([trade["mfe_pct"] for trade in trades]),
        "worst_month_pct": min((row["return_pct"] for row in monthly), default=None),
        "best_month_pct": max((row["return_pct"] for row in monthly), default=None),
        "best_symbol_positive_pnl_share_pct": best_symbol_share * 100 if by_symbol else None,
    }


def benchmark_summary_row(name: str, group: str, summary: dict, monthly_rows: List[dict]) -> dict:
    return {
        "name": name,
        "group": group,
        "universe_size": "",
        "fill_mode": "",
        "defensive_mode": "",
        "max_leverage": "",
        "shock_exit": "",
        "fee_rate_pct": "",
        "slippage_rate_pct": "",
        "total_return_pct": summary["total_return_pct"],
        "cagr_pct": summary["cagr_pct"],
        "mdd_pct": summary["mdd_pct"],
        "sharpe": summary["sharpe"],
        "calmar": summary["calmar"],
        "profit_factor": "",
        "win_rate_pct": summary["win_rate_pct"],
        "payoff_ratio": "",
        "avg_hold_days": "",
        "trades": summary["trades"],
        "avg_monthly_trades": summary["trades"] / len(MONTHS),
        "avg_entry_after_1d_pct": "",
        "avg_entry_after_3d_pct": "",
        "avg_entry_after_7d_pct": "",
        "avg_mae_pct": "",
        "avg_mfe_pct": "",
        "worst_month_pct": min(row["return_pct"] for row in monthly_rows),
        "best_month_pct": max(row["return_pct"] for row in monthly_rows),
        "best_symbol_positive_pnl_share_pct": "",
    }


def monthly_returns_from_curve(name: str, curve: List[dict]) -> List[dict]:
    month_end: Dict[str, float] = {}
    for point in curve:
        month = month_from_ts(point["time"])
        if MONTHS[0] <= month <= MONTHS[-1]:
            month_end[month] = point["equity"]
    rows = []
    previous = 1.0
    for month in MONTHS:
        equity = month_end.get(month, previous)
        rows.append({"name": name, "month": month, "return_pct": (equity / previous - 1) * 100 if previous else 0.0})
        previous = equity
    return rows


def yearly_rows_from_monthly(name: str, monthly: List[dict]) -> List[dict]:
    yearly: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return [{"name": name, "year": year, "return_pct": (value - 1) * 100} for year, value in sorted(yearly.items())]


def benchmark_monthly_rows(monthly_v1: v1.StrategyResult, btc: v1.StrategyResult, eth: v1.StrategyResult) -> List[dict]:
    out = []
    for name, result in (("BTC/ETH Monthly Strength v1", monthly_v1), ("Buy & Hold BTC", btc), ("Buy & Hold ETH", eth)):
        out.extend({"name": name, "month": row["month"], "return_pct": row["return_pct"]} for row in result.monthly_rows)
    return out


def benchmark_yearly_rows(monthly_v1: v1.StrategyResult, btc: v1.StrategyResult, eth: v1.StrategyResult) -> List[dict]:
    out = []
    for name, result in (("BTC/ETH Monthly Strength v1", monthly_v1), ("Buy & Hold BTC", btc), ("Buy & Hold ETH", eth)):
        out.extend({"name": name, "year": year, "return_pct": value * 100} for year, value in sorted(result.yearly_returns.items()))
    return out


def symbol_performance(trades: List[dict]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[trade["symbol"]].append(trade)
    rows = []
    for symbol, items in grouped.items():
        rows.append({"symbol": symbol, "trades": len(items), "pnl": sum(item["pnl"] for item in items), "avg_return_pct": mean_present([item["trade_return_pct"] for item in items])})
    return sorted(rows, key=lambda row: row["pnl"], reverse=True)


def grouped_trade_stats(trades: List[dict], key: str) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key, ""))].append(trade)
    rows = []
    for value, items in grouped.items():
        wins = [item["trade_return_pct"] for item in items if item["trade_return_pct"] > 0]
        losses = [item["trade_return_pct"] for item in items if item["trade_return_pct"] < 0]
        rows.append(
            {
                key: value,
                "trades": len(items),
                "pnl": sum(item["pnl"] for item in items),
                "win_rate_pct": len(wins) / len(items) * 100 if items else 0.0,
                "avg_return_pct": mean_present([item["trade_return_pct"] for item in items]),
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            }
        )
    return sorted(rows, key=lambda row: row["pnl"], reverse=True)


def pass_fail(summary_rows: List[dict]) -> List[dict]:
    lookup = {row["name"]: row for row in summary_rows}
    alpha4 = lookup.get("Alpha Engine v1 / 4 symbols", {})
    alpha10 = lookup.get("Alpha Engine v1 / 10 symbols", {})
    btc = lookup.get("Buy & Hold BTC", {})
    monthly = lookup.get("BTC/ETH Monthly Strength v1", {})
    lev4 = lookup.get("Alpha Engine v1 / 4 symbols / 4x", {})
    concentration = alpha10.get("best_symbol_positive_pnl_share_pct")
    return [
        {
            "check": "MDD lower than BTC buy-and-hold",
            "result": "PASS" if alpha10 and btc and alpha10["mdd_pct"] > btc["mdd_pct"] else "FAIL",
            "evidence": f"Alpha10 MDD {alpha10.get('mdd_pct', 0):.1f}%, BTC B&H MDD {btc.get('mdd_pct', 0):.1f}%",
        },
        {
            "check": "Calmar better than Monthly v1",
            "result": "PASS" if alpha10 and monthly and (alpha10["calmar"] or -999) > (monthly["calmar"] or -999) else "FAIL",
            "evidence": f"Alpha10 Calmar {alpha10.get('calmar', 0):.2f}, Monthly v1 Calmar {monthly.get('calmar', 0):.2f}",
        },
        {
            "check": "Trade count not excessive",
            "result": "PASS" if alpha10 and alpha10["avg_monthly_trades"] <= TOO_MANY_TRADES_PER_MONTH else "FAIL",
            "evidence": f"Alpha10 average monthly trades {alpha10.get('avg_monthly_trades', 0):.1f}",
        },
        {
            "check": "Symbol concentration",
            "result": "WARNING" if concentration is not None and concentration >= SYMBOL_CONCENTRATION_WARNING * 100 else "PASS",
            "evidence": f"Best symbol positive PnL share {concentration or 0:.1f}%",
        },
        {
            "check": "10-symbol expansion",
            "result": "PASS" if alpha10 and alpha4 and (alpha10["calmar"] or -999) >= (alpha4["calmar"] or -999) else "HOLD",
            "evidence": f"Alpha10 Calmar {alpha10.get('calmar', 0):.2f}, Alpha4 Calmar {alpha4.get('calmar', 0):.2f}",
        },
        {
            "check": "4x leverage",
            "result": "HOLD" if lev4 and lev4["mdd_pct"] <= -50 else "PASS",
            "evidence": f"4x MDD {lev4.get('mdd_pct', 0):.1f}%",
        },
    ]


def build_report(data: AlphaData, summary_rows: List[dict], monthly_rows: List[dict], yearly_rows: List[dict], trades: List[dict], signals: List[dict], pass_fail_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alpha_trades = [trade for trade in trades if trade["variant"] == "Alpha Engine v1 / 10 symbols"]
    lines = [
        "# Alpha Engine v1 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 데이터: Binance Spot 1D/4H/1H OHLCV. Futures funding fee는 optional 항목으로 이번 리포트에는 반영하지 않았다.",
        "- 레짐은 `trade_regime` / `trade_action_bias`만 사용했다. `stable_regime` 당일 값은 매매 필터에 직접 사용하지 않았다.",
        f"- 기본 비용은 진입/청산 각각 수수료 {BASE_FEE_RATE * 100:.2f}%, 슬리피지 {BASE_SLIPPAGE_RATE * 100:.2f}%로 반영했다.",
        "- 기본 리스크는 심볼당 0.5%, 포트폴리오 전체 1.5%, 동시 보유 3개로 제한했다.",
        "- `next_open`은 4H 신호 봉이 닫힌 직후 새 1H 봉 open 체결로 처리한다. 타임스탬프는 같을 수 있지만 같은 4H 봉 내부 체결은 아니다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## 룩어헤드 감사",
        "",
        lookahead_table(trades),
        "",
        "## 전체 성과",
        "",
        summary_table([row for row in summary_rows if row["group"] in {"Benchmark", "Alpha"}]),
        "",
        "## 레버리지별 성과",
        "",
        summary_table([row for row in summary_rows if row["group"] == "Leverage sensitivity"]),
        "",
        "## 수수료/슬리피지 민감도",
        "",
        summary_table([row for row in summary_rows if row["group"] == "Cost sensitivity"]),
        "",
        "## 타이밍/레짐/청산 민감도",
        "",
        summary_table([row for row in summary_rows if row["group"] in {"Regime sensitivity", "Timing sensitivity", "Exit sensitivity"}]),
        "",
        "## 심볼별 성과",
        "",
        symbol_table(symbol_performance(alpha_trades)),
        "",
        "## 레짐별 성과",
        "",
        grouped_table(grouped_trade_stats(alpha_trades, "trade_regime"), "trade_regime"),
        "",
        "## Action Bias별 성과",
        "",
        grouped_table(grouped_trade_stats(alpha_trades, "trade_action_bias"), "trade_action_bias"),
        "",
        "## 청산 사유별 통계",
        "",
        grouped_table(grouped_trade_stats(alpha_trades, "exit_reason"), "exit_reason"),
        "",
        "## 진입 품질",
        "",
        entry_quality_table(alpha_trades),
        "",
        "## 최악 거래 Top 20",
        "",
        trade_rank_table(alpha_trades, reverse=False),
        "",
        "## 최고 거래 Top 20",
        "",
        trade_rank_table(alpha_trades, reverse=True),
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
        coverage_table(data),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_report.md`",
        "- `alpha_engine_v1_summary.csv`",
        "- `alpha_engine_v1_trades.csv`",
        "- `alpha_engine_v1_signals.csv`",
        "",
    ]
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def lookahead_table(trades: List[dict]) -> str:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[trade["variant"]].append(trade)
    lines = ["| Variant | Trades | Lookahead fail | Min lag hours | Same timestamp fills |", "|---|---:|---:|---:|---:|"]
    for variant, items in sorted(grouped.items()):
        lags = [(trade["entry_timestamp"] - datetime.strptime(trade["signal_date"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()) / 3600 for trade in items]
        lines.append(
            f"| {variant} | {len(items)} | {sum(1 for trade in items if not trade['lookahead_pass'])} | "
            f"{min(lags) if lags else 0:.1f} | {sum(1 for lag in lags if lag == 0)} |"
        )
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Name", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "PF", "Win", "Payoff", "Trades", "Monthly trades", "Avg hold", "MAE", "MFE"]
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
                    num(row["profit_factor"]),
                    pct(row["win_rate_pct"]),
                    num(row["payoff_ratio"]),
                    str(row["trades"]),
                    num(row["avg_monthly_trades"]),
                    num(row["avg_hold_days"]),
                    pct(row["avg_mae_pct"]),
                    pct(row["avg_mfe_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def symbol_table(rows: List[dict]) -> str:
    lines = ["| Symbol | Trades | PnL | Avg return |", "|---|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['symbol']} | {row['trades']} | {num(row['pnl'])} | {pct(row['avg_return_pct'])} |")
    return "\n".join(lines)


def grouped_table(rows: List[dict], key: str) -> str:
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
        ]
    )


def trade_rank_table(trades: List[dict], reverse: bool) -> str:
    rows = sorted(trades, key=lambda row: row["trade_return_pct"], reverse=reverse)[:20]
    lines = ["| Variant | Symbol | Entry | Exit | Reason | Return | Hold | MAE | MFE |", "|---|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['variant']} | {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['exit_reason']} | {pct(row['trade_return_pct'])} | {num(row['hold_days'])} | {pct(row['mae_pct'])} | {pct(row['mfe_pct'])} |")
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
    sample_months = MONTHS[-12:]
    lookup = {(row["name"], row["month"]): row["return_pct"] for row in rows}
    lines = ["| Name | " + " | ".join(sample_months) + " |", "|" + "|".join(["---"] * (len(sample_months) + 1)) + "|"]
    for name in names[:12]:
        lines.append("| " + " | ".join([name] + [pct(lookup.get((name, month))) for month in sample_months]) + " |")
    return "\n".join(lines)


def coverage_table(data: AlphaData) -> str:
    lines = ["| Symbol | 1D | 4H | 1H |", "|---|---:|---:|---:|"]
    for symbol in UNIVERSE_10:
        lines.append(f"| {v1.short(symbol)} | {len(data.raw_1d.get(symbol, []))} | {len(data.raw_4h.get(symbol, []))} | {len(data.raw_1h.get(symbol, []))} |")
    return "\n".join(lines)


def dedupe_configs(configs: List[AlphaConfig]) -> List[AlphaConfig]:
    seen = set()
    out = []
    for config in configs:
        key = config.name
        if key not in seen:
            seen.add(key)
            out.append(config)
    return out


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def date_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def format_dt(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M")


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and value != ""]
    return statistics.mean(clean) if clean else None


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


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
