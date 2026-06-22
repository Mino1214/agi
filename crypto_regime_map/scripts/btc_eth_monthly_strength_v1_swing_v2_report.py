"""Swing v2 timing-filter report for BTC/ETH Monthly Strength v1.

Swing v2 does not use the 4H signal as an independent strategy. It keeps the
Monthly Strength v1 monthly target weights and delays only new buys until each
target asset prints an EMA50 pullback followed by EMA20 recovery.
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
import btc_eth_monthly_strength_v1_swing_entry_audit_report as audit  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


MONTHS = v1.month_range("2020-01", "2025-12")
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
ATR_STOP_MULTIPLE = 2.0
CAGR_RETENTION_FLOOR = 0.80
REENTRY_REDUCTION_FLOOR = 0.50


@dataclass(frozen=True)
class ReentryRule:
    key: str
    name: str
    monthly_candidate_limit: Optional[int] = None
    cooldown_hours: int = 0
    stop_blocks_month: bool = False


@dataclass(frozen=True)
class ExitRule:
    key: str
    name: str


@dataclass(frozen=True)
class V2Config:
    key: str
    name: str
    reentry: ReentryRule
    exit_rule: ExitRule


@dataclass
class Position:
    symbol: str
    units: float
    gross_notional: float
    cost_basis: float
    avg_entry_price: float
    entry_time: int
    entry_index: int
    entry_atr: float
    entry_month: str


REENTRY_RULES = [
    ReentryRule("max1", "월 후보당 최대 1회 진입", monthly_candidate_limit=1),
    ReentryRule("max2", "월 후보당 최대 2회 진입", monthly_candidate_limit=2),
    ReentryRule("cooldown72", "청산 후 72시간 재진입 금지", cooldown_hours=72),
    ReentryRule("stop_block_month", "손절 후 월말까지 재진입 금지", stop_blocks_month=True),
]

EXIT_RULES = [
    ExitRule("ema50_single", "A. 4H EMA50 이탈 청산"),
    ExitRule("ema50_two", "B. 4H EMA50 2캔들 연속 이탈 청산"),
    ExitRule("atr_only", "C. ATR 2.0 손절만, 월말까지 보유"),
    ExitRule("monthly_defense", "D. 월말까지 보유, BTC 1D EMA200/긴급 방어만 청산"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON if it covers the warmup window.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = audit.load_raw_with_warmup(SYMBOLS, "1d", args.use_cache)
    raw_4h = audit.load_raw_with_warmup(SYMBOLS, "4h", args.use_cache)
    swing_data = swing.SwingData(raw_1d, raw_4h)

    raw_v1 = {symbol: raw_1d[symbol] for symbol in v1.SYMBOLS}
    payload = v1.build_payload_from_raw(raw_v1, interval="1d", start=v1.FETCH_START, symbols=v1.SYMBOLS)
    v1_data = v1.BacktestData(raw=raw_v1, payload=payload)
    monthly_v1 = v1.run_strength_strategy(v1_data, v1.base_config())
    monthly_targets = {
        month: v1.normalize_weights(v1.strength_target(v1_data, v1.base_config(), month)[0])
        for month in MONTHS
    }
    daily_defense = build_daily_defense(v1_data)

    baseline_ema50 = audit.run_audit_method(
        swing_data,
        audit.AuditConfig("ema50_base", "EMA50 눌림 기존", "ema50_pullback"),
    )
    baseline_ema50_cd48 = audit.run_audit_method(
        swing_data,
        audit.AuditConfig("ema50_cooldown_48h", "EMA50 눌림 + 48h 쿨다운", "ema50_pullback", cooldown_hours=48),
    )

    configs = [
        V2Config(
            key=f"{exit_rule.key}_{reentry.key}",
            name=f"Swing v2 {exit_rule.key} / {reentry.name}",
            reentry=reentry,
            exit_rule=exit_rule,
        )
        for exit_rule in EXIT_RULES
        for reentry in REENTRY_RULES
    ]
    v2_results = [
        run_swing_v2(swing_data, v1_data, monthly_targets, daily_defense, config)
        for config in configs
    ]

    summary_rows = comparison_rows(monthly_v1, baseline_ema50, baseline_ema50_cd48, v2_results)
    candidate_rows = [candidate_row(result, monthly_v1, baseline_ema50) for result in v2_results]
    verdict_rows = verdict_rows_for(candidate_rows)
    monthly_rows = monthly_return_rows(monthly_v1, baseline_ema50, baseline_ema50_cd48, v2_results)
    yearly_rows = yearly_return_rows(monthly_v1, baseline_ema50, baseline_ema50_cd48, v2_results)
    monthly_rank_rows = monthly_rankings(monthly_rows)
    trade_rows = [trade for result in v2_results for trade in result["trades"]]

    report = build_report(
        swing_data=swing_data,
        monthly_v1=monthly_v1,
        summary_rows=summary_rows,
        candidate_rows=candidate_rows,
        verdict_rows=verdict_rows,
        monthly_rows=monthly_rows,
        yearly_rows=yearly_rows,
        monthly_rank_rows=monthly_rank_rows,
    )

    report_path = output_dir / "btc_eth_monthly_strength_v1_swing_v2_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_summary.csv", summary_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_candidates.csv", candidate_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_verdicts.csv", verdict_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_monthly_returns.csv", monthly_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_yearly_returns.csv", yearly_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_monthly_rankings.csv", monthly_rank_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_v2_trades.csv", trade_rows)
    print(report_path)


def run_swing_v2(
    data: swing.SwingData,
    v1_data: v1.BacktestData,
    monthly_targets: Dict[str, Dict[str, float]],
    daily_defense: Dict[str, bool],
    config: V2Config,
) -> dict:
    cash = 1.0
    positions: Dict[str, Position] = {}
    current_month = ""
    target_weights: Dict[str, float] = {"cash": 1.0}
    waiting: Dict[str, dict] = {}
    pending: List[dict] = []
    last_exit_by_symbol: Dict[str, int] = {}
    stop_block_month_by_symbol: Dict[str, str] = {}
    monthly_candidate_entries: Counter[Tuple[str, str]] = Counter()
    trades: List[dict] = []
    equity_curve = [{"time": swing.TEST_START_TS, "date": format_dt(swing.TEST_START_TS), "equity": 1.0}]
    month_locked = False

    for index, bar in enumerate(data.bars):
        bar_month = month_from_ts(bar["time"])
        if bar_month != current_month:
            current_month = bar_month
            month_locked = False
            pending = []
            waiting = {}
            target_weights = monthly_targets.get(current_month, {"cash": 1.0})
            cash, month_trades = apply_month_rebalance(
                data=data,
                config=config,
                bar=bar,
                index=index,
                cash=cash,
                positions=positions,
                target_weights=target_weights,
                reason="month_rebalance",
            )
            for trade in month_trades:
                trades.append(trade)
                last_exit_by_symbol[f"{trade['symbol']}USDT"] = trade["exit_timestamp"]

        if month_locked:
            pending = []
        else:
            pending_now = [order for order in pending if order["index"] == index]
            pending = [order for order in pending if order["index"] != index]
            for order in pending_now:
                if entry_allowed(config, order["symbol"], bar["time"], current_month, monthly_candidate_entries, last_exit_by_symbol, stop_block_month_by_symbol):
                    cash = execute_buy(
                        data=data,
                        bar=bar,
                        index=index,
                        cash=cash,
                        positions=positions,
                        symbol=order["symbol"],
                        target_weight=target_weights.get(order["symbol"], 0.0),
                        monthly_candidate_entries=monthly_candidate_entries,
                    )

        for symbol in list(positions):
            reason = exit_reason(data, daily_defense, config.exit_rule, index, bar, positions[symbol])
            if reason:
                cash, trade = close_position(data, config, bar, index, cash, positions.pop(symbol), "close", reason)
                trades.append(trade)
                last_exit_by_symbol[symbol] = bar["close_time"]
                if reason == "atr_stop" and config.reentry.stop_blocks_month:
                    stop_block_month_by_symbol[symbol] = current_month
                if reason == "daily_defense_exit":
                    month_locked = True
                    pending = []

        close_equity = portfolio_equity(cash, positions, bar, "close")
        equity_curve.append({"time": bar["close_time"], "date": format_dt(bar["close_time"]), "equity": close_equity})
        if index + 1 >= len(data.bars):
            continue
        if month_locked:
            continue

        for symbol in SYMBOLS:
            if target_weights.get(symbol, 0.0) <= 0:
                continue
            if not has_weight_gap(cash, positions, bar, symbol, target_weights[symbol], "close"):
                continue
            if not entry_allowed(
                config,
                symbol,
                data.bars[index + 1]["time"],
                current_month,
                monthly_candidate_entries,
                last_exit_by_symbol,
                stop_block_month_by_symbol,
            ):
                continue
            order = entry_order_if_recovered(data, index, bar, symbol, waiting)
            if order:
                pending.append(order)

    if positions:
        last_index = len(data.bars) - 1
        last_bar = data.bars[last_index]
        for symbol in list(positions):
            cash, trade = close_position(data, config, last_bar, last_index, cash, positions.pop(symbol), "close", "end_of_test")
            trades.append(trade)
        equity_curve.append({"time": last_bar["close_time"], "date": format_dt(last_bar["close_time"]), "equity": cash})

    monthly = monthly_returns_from_curve(config.name, equity_curve)
    yearly = yearly_returns_from_monthly(monthly)
    summary = summary_row(config, equity_curve, trades)
    return {
        "config": config,
        "summary": summary,
        "trades": trades,
        "equity_curve": equity_curve,
        "monthly": monthly,
        "yearly": yearly,
    }


def apply_month_rebalance(
    data: swing.SwingData,
    config: V2Config,
    bar: dict,
    index: int,
    cash: float,
    positions: Dict[str, Position],
    target_weights: Dict[str, float],
    reason: str,
) -> Tuple[float, List[dict]]:
    trades = []
    equity = portfolio_equity(cash, positions, bar, "open")
    for symbol in list(positions):
        position = positions[symbol]
        price = bar["assets"][symbol]["open"]
        current_value = position.units * price
        target_value = equity * target_weights.get(symbol, 0.0)
        if current_value <= target_value * 1.001:
            continue
        if target_value <= 1e-12:
            cash, trade = close_position(data, config, bar, index, cash, positions.pop(symbol), "open", reason)
            trades.append(trade)
            continue
        sell_value = current_value - target_value
        sell_units = min(position.units, sell_value / price)
        proceeds = sell_units * price
        fee = proceeds * swing.FEE_RATE
        fraction = sell_units / position.units if position.units else 0.0
        position.units -= sell_units
        position.gross_notional *= 1 - fraction
        position.cost_basis *= 1 - fraction
        cash += proceeds - fee
    return cash, trades


def execute_buy(
    data: swing.SwingData,
    bar: dict,
    index: int,
    cash: float,
    positions: Dict[str, Position],
    symbol: str,
    target_weight: float,
    monthly_candidate_entries: Counter[Tuple[str, str]],
) -> float:
    if target_weight <= 0:
        return cash
    price = bar["assets"][symbol]["open"]
    equity = portfolio_equity(cash, positions, bar, "open")
    current_value = positions[symbol].units * price if symbol in positions else 0.0
    notional = max(0.0, equity * target_weight - current_value)
    if notional <= 1e-12:
        return cash
    notional = min(notional, cash / (1 + swing.FEE_RATE))
    if notional <= 1e-12:
        return cash
    fee = notional * swing.FEE_RATE
    buy_units = notional / price
    month = month_from_ts(bar["time"])
    monthly_candidate_entries[(month, symbol)] += 1
    if symbol in positions:
        position = positions[symbol]
        position.units += buy_units
        position.gross_notional += notional
        position.cost_basis += notional + fee
        position.avg_entry_price = position.gross_notional / position.units
    else:
        positions[symbol] = Position(
            symbol=symbol,
            units=buy_units,
            gross_notional=notional,
            cost_basis=notional + fee,
            avg_entry_price=price,
            entry_time=bar["time"],
            entry_index=index,
            entry_atr=bar["assets"][symbol]["atr14"] or 0.0,
            entry_month=month,
        )
    return cash - notional - fee


def close_position(
    data: swing.SwingData,
    config: V2Config,
    bar: dict,
    index: int,
    cash: float,
    position: Position,
    price_key: str,
    reason: str,
) -> Tuple[float, dict]:
    price = bar["assets"][position.symbol][price_key]
    exit_time = bar["time"] if price_key == "open" else bar["close_time"]
    proceeds = position.units * price
    fee = proceeds * swing.FEE_RATE
    cash_after = cash + proceeds - fee
    net_return = (proceeds - fee) / position.cost_basis - 1 if position.cost_basis else 0.0
    excursion = trade_excursion(data, position.symbol, position.entry_index, index, position.avg_entry_price)
    trade = {
        "strategy": config.name,
        "exit_rule": config.exit_rule.name,
        "reentry_rule": config.reentry.name,
        "symbol": v1.short(position.symbol),
        "candidate_key": f"{position.entry_month}:{v1.short(position.symbol)}",
        "entry_month": position.entry_month,
        "entry_date": format_dt(position.entry_time),
        "exit_date": format_dt(exit_time),
        "entry_timestamp": position.entry_time,
        "exit_timestamp": exit_time,
        "exit_reason": reason,
        "entry_price": position.avg_entry_price,
        "exit_price": price,
        "hold_days": (exit_time - position.entry_time) / 86400,
        "trade_return_pct": net_return * 100,
        "trade_mae_pct": excursion["mae_pct"],
        "trade_mfe_pct": excursion["mfe_pct"],
    }
    return cash_after, trade


def exit_reason(
    data: swing.SwingData,
    daily_defense: Dict[str, bool],
    exit_rule: ExitRule,
    index: int,
    bar: dict,
    position: Position,
) -> str:
    asset = bar["assets"][position.symbol]
    if exit_rule.key == "ema50_single":
        if asset["ema50"] is not None and asset["close"] < asset["ema50"]:
            return "ema50_exit"
        return ""
    if exit_rule.key == "ema50_two":
        if index == 0 or asset["ema50"] is None:
            return ""
        previous = data.bars[index - 1]["assets"][position.symbol]
        if previous["ema50"] is not None and previous["close"] < previous["ema50"] and asset["close"] < asset["ema50"]:
            return "ema50_2bar_exit"
        return ""
    if exit_rule.key == "atr_only":
        if position.entry_atr and asset["close"] <= position.avg_entry_price - ATR_STOP_MULTIPLE * position.entry_atr:
            return "atr_stop"
        return ""
    if exit_rule.key == "monthly_defense":
        if daily_defense.get(bar["daily_key"], False):
            return "daily_defense_exit"
        return ""
    raise ValueError(f"Unknown exit rule: {exit_rule.key}")


def entry_order_if_recovered(data: swing.SwingData, index: int, bar: dict, symbol: str, waiting: Dict[str, dict]) -> Optional[dict]:
    asset = bar["assets"][symbol]
    if swing.missing_entry_indicators(asset):
        return None
    month = month_from_ts(bar["time"])
    state = waiting.get(symbol)
    if not state or state.get("month") != month:
        state = {"month": month, "touched": False}
        waiting[symbol] = state
    touched = bool(state["touched"]) or asset["low"] <= asset["ema50"] + swing.PULLBACK_ATR_TOLERANCE * asset["atr14"]
    recovered = touched and asset["close"] > asset["ema20"]
    state["touched"] = touched
    if recovered:
        state["touched"] = False
        return {"index": index + 1, "symbol": symbol}
    return None


def entry_allowed(
    config: V2Config,
    symbol: str,
    fill_time: int,
    month: str,
    monthly_candidate_entries: Counter[Tuple[str, str]],
    last_exit_by_symbol: Dict[str, int],
    stop_block_month_by_symbol: Dict[str, str],
) -> bool:
    limit = config.reentry.monthly_candidate_limit
    if limit is not None and monthly_candidate_entries[(month, symbol)] >= limit:
        return False
    if config.reentry.cooldown_hours:
        last_exit = last_exit_by_symbol.get(symbol)
        if last_exit is not None and fill_time - last_exit < config.reentry.cooldown_hours * 3600:
            return False
    if config.reentry.stop_blocks_month and stop_block_month_by_symbol.get(symbol) == month:
        return False
    return True


def has_weight_gap(
    cash: float,
    positions: Dict[str, Position],
    bar: dict,
    symbol: str,
    target_weight: float,
    price_key: str,
) -> bool:
    equity = portfolio_equity(cash, positions, bar, price_key)
    if equity <= 0:
        return False
    current = positions[symbol].units * bar["assets"][symbol][price_key] if symbol in positions else 0.0
    return current / equity < target_weight - 0.01


def portfolio_equity(cash: float, positions: Dict[str, Position], bar: dict, price_key: str) -> float:
    return cash + sum(position.units * bar["assets"][symbol][price_key] for symbol, position in positions.items())


def trade_excursion(data: swing.SwingData, symbol: str, entry_index: int, exit_index: int, entry_price: float) -> dict:
    if exit_index < entry_index:
        return {"mae_pct": None, "mfe_pct": None}
    lows = [data.bars[item]["assets"][symbol]["low"] for item in range(entry_index, exit_index + 1)]
    highs = [data.bars[item]["assets"][symbol]["high"] for item in range(entry_index, exit_index + 1)]
    return {
        "mae_pct": min(0.0, min(lows) / entry_price - 1) * 100 if lows else None,
        "mfe_pct": max(0.0, max(highs) / entry_price - 1) * 100 if highs else None,
    }


def build_daily_defense(data: v1.BacktestData) -> Dict[str, bool]:
    out = {}
    for row in data.raw["BTCUSDT"]:
        date = v1.date_from_ts(row["time"])
        out[date] = v1.should_emergency_exit(data, row["time"], v1.BASE_EMA_PERIOD)
    return out


def summary_row(config: V2Config, equity_curve: List[dict], trades: List[dict]) -> dict:
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
    gross_loss = abs(sum(losses))
    holds = [trade["hold_days"] for trade in trades]
    monthly_counts = Counter({month: 0 for month in MONTHS})
    for trade in trades:
        monthly_counts[trade["entry_month"]] += 1
    avg_mae = mean_present([trade["trade_mae_pct"] for trade in trades])
    avg_mfe = mean_present([trade["trade_mfe_pct"] for trade in trades])
    return {
        "strategy": config.name,
        "type": "Swing v2",
        "exit_rule": config.exit_rule.name,
        "reentry_rule": config.reentry.name,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "trades": len(trades),
        "avg_monthly_trades": statistics.mean([monthly_counts[month] for month in MONTHS]) if MONTHS else 0.0,
        "avg_hold_days": statistics.mean(holds) if holds else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "avg_mae_pct": avg_mae,
        "avg_mfe_pct": avg_mfe,
        "same_candidate_reentries_within_4h": count_same_candidate_reentries(trades),
        "worst_month_pct": None,
        "best_month_pct": None,
    }


def comparison_rows(
    monthly_v1: v1.StrategyResult,
    baseline_ema50: dict,
    baseline_ema50_cd48: dict,
    v2_results: List[dict],
) -> List[dict]:
    rows = [monthly_v1_row(monthly_v1)]
    rows.append(independent_swing_row("EMA50 눌림 기존", baseline_ema50))
    rows.append(independent_swing_row("EMA50 눌림 + 48h 쿨다운", baseline_ema50_cd48))
    rows.extend(result["summary"] for result in v2_results)
    monthly = monthly_return_rows(monthly_v1, baseline_ema50, baseline_ema50_cd48, v2_results)
    month_lookup: Dict[str, List[float]] = {}
    for row in monthly:
        month_lookup.setdefault(row["strategy"], []).append(row["return_pct"])
    for row in rows:
        values = month_lookup.get(row["strategy"], [])
        row["worst_month_pct"] = min(values) if values else None
        row["best_month_pct"] = max(values) if values else None
    return rows


def monthly_v1_row(monthly_v1: v1.StrategyResult) -> dict:
    returns = [row["return_pct"] for row in monthly_v1.monthly_rows]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    gross_loss = abs(sum(losses))
    return {
        "strategy": "Monthly v1",
        "type": "Benchmark",
        "exit_rule": "",
        "reentry_rule": "",
        "cagr_pct": monthly_v1.summary["cagr_pct"],
        "mdd_pct": monthly_v1.summary["mdd_pct"],
        "sharpe": monthly_v1.summary["sharpe"],
        "calmar": monthly_v1.summary["calmar"],
        "trades": monthly_v1.summary["trades"],
        "avg_monthly_trades": monthly_v1.summary["trades"] / len(MONTHS),
        "avg_hold_days": "",
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "avg_mae_pct": "",
        "avg_mfe_pct": "",
        "same_candidate_reentries_within_4h": "",
        "worst_month_pct": min(returns) if returns else None,
        "best_month_pct": max(returns) if returns else None,
    }


def independent_swing_row(name: str, result: dict) -> dict:
    summary = result["summary"]
    trades = result["trades"]
    return {
        "strategy": name,
        "type": "Independent 4H",
        "exit_rule": "기존 독립 EMA50 눌림",
        "reentry_rule": summary.get("cooldown_hours") and f"{summary['cooldown_hours']}h cooldown" or "제한 없음",
        "cagr_pct": summary["cagr_pct"],
        "mdd_pct": summary["mdd_pct"],
        "sharpe": summary["sharpe"],
        "calmar": summary["calmar"],
        "trades": summary["trades"],
        "avg_monthly_trades": summary["trades"] / len(MONTHS),
        "avg_hold_days": summary["avg_hold_days"],
        "profit_factor": summary["profit_factor"],
        "avg_mae_pct": mean_present([trade.get("trade_mae_pct") for trade in trades]),
        "avg_mfe_pct": mean_present([trade.get("trade_mfe_pct") for trade in trades]),
        "same_candidate_reentries_within_4h": audit.count_same_candidate_reentries(trades),
        "worst_month_pct": None,
        "best_month_pct": None,
    }


def candidate_row(result: dict, monthly_v1: v1.StrategyResult, baseline_ema50: dict) -> dict:
    summary = result["summary"]
    v1_cagr = monthly_v1.summary["cagr_pct"]
    v1_mdd = monthly_v1.summary["mdd_pct"]
    v1_calmar = monthly_v1.summary["calmar"]
    baseline_trades = baseline_ema50["summary"]["trades"]
    baseline_reentries = audit.count_same_candidate_reentries(baseline_ema50["trades"])
    mdd_pass = summary["mdd_pct"] >= v1_mdd
    cagr_pass = bool(summary["cagr_pct"] is not None and summary["cagr_pct"] >= v1_cagr * CAGR_RETENTION_FLOOR)
    trade_pass = summary["trades"] < baseline_trades
    reentry_pass = summary["same_candidate_reentries_within_4h"] <= baseline_reentries * REENTRY_REDUCTION_FLOOR
    calmar_pass = bool(summary["calmar"] is not None and summary["calmar"] > v1_calmar)
    return {
        "strategy": summary["strategy"],
        "exit_rule": summary["exit_rule"],
        "reentry_rule": summary["reentry_rule"],
        "cagr_pct": summary["cagr_pct"],
        "mdd_pct": summary["mdd_pct"],
        "calmar": summary["calmar"],
        "trades": summary["trades"],
        "same_candidate_reentries_within_4h": summary["same_candidate_reentries_within_4h"],
        "cagr_retention_pct": summary["cagr_pct"] / v1_cagr * 100 if v1_cagr and summary["cagr_pct"] is not None else None,
        "trade_reduction_vs_ema50_pct": (1 - summary["trades"] / baseline_trades) * 100 if baseline_trades else None,
        "reentry_reduction_vs_ema50_pct": (1 - summary["same_candidate_reentries_within_4h"] / baseline_reentries) * 100 if baseline_reentries else None,
        "mdd_pass": mdd_pass,
        "cagr_pass": cagr_pass,
        "trade_count_pass": trade_pass,
        "reentry_pass": reentry_pass,
        "calmar_pass": calmar_pass,
        "overall_pass": bool(mdd_pass and cagr_pass and trade_pass and reentry_pass and calmar_pass),
    }


def verdict_rows_for(candidate_rows: List[dict]) -> List[dict]:
    best_calmar = max(candidate_rows, key=lambda row: row["calmar"] if row["calmar"] is not None else -999)
    best_mdd = max(candidate_rows, key=lambda row: row["mdd_pct"])
    passing = [row for row in candidate_rows if row["overall_pass"]]
    return [
        {
            "check": "overall_pass_candidates",
            "result": "PASS" if passing else "FAIL",
            "evidence": f"{len(passing)} / {len(candidate_rows)} candidates passed all criteria",
        },
        {
            "check": "best_calmar_candidate",
            "result": "INFO",
            "evidence": f"{best_calmar['strategy']} Calmar {best_calmar['calmar']:.2f}, MDD {best_calmar['mdd_pct']:.1f}%, CAGR {best_calmar['cagr_pct']:.1f}%",
        },
        {
            "check": "best_mdd_candidate",
            "result": "INFO",
            "evidence": f"{best_mdd['strategy']} MDD {best_mdd['mdd_pct']:.1f}%, CAGR {best_mdd['cagr_pct']:.1f}%",
        },
    ]


def monthly_return_rows(
    monthly_v1: v1.StrategyResult,
    baseline_ema50: dict,
    baseline_ema50_cd48: dict,
    v2_results: List[dict],
) -> List[dict]:
    rows = [
        {"strategy": "Monthly v1", "month": row["month"], "return_pct": row["return_pct"]}
        for row in monthly_v1.monthly_rows
    ]
    rows.extend({**row, "strategy": "EMA50 눌림 기존"} for row in audit.monthly_returns_from_curve("EMA50 눌림 기존", baseline_ema50["equity_curve"]))
    rows.extend({**row, "strategy": "EMA50 눌림 + 48h 쿨다운"} for row in audit.monthly_returns_from_curve("EMA50 눌림 + 48h 쿨다운", baseline_ema50_cd48["equity_curve"]))
    for result in v2_results:
        rows.extend(result["monthly"])
    return rows


def yearly_return_rows(
    monthly_v1: v1.StrategyResult,
    baseline_ema50: dict,
    baseline_ema50_cd48: dict,
    v2_results: List[dict],
) -> List[dict]:
    rows = [
        {"strategy": "Monthly v1", "year": year, "return_pct": value * 100}
        for year, value in sorted(monthly_v1.yearly_returns.items())
    ]
    for name, result in (("EMA50 눌림 기존", baseline_ema50), ("EMA50 눌림 + 48h 쿨다운", baseline_ema50_cd48)):
        monthly = audit.monthly_returns_from_curve(name, result["equity_curve"])
        yearly = yearly_returns_from_monthly(monthly)
        rows.extend({"strategy": name, "year": year, "return_pct": value} for year, value in sorted(yearly.items()))
    for result in v2_results:
        rows.extend({"strategy": result["summary"]["strategy"], "year": year, "return_pct": value} for year, value in sorted(result["yearly"].items()))
    return rows


def monthly_rankings(monthly_rows: List[dict]) -> List[dict]:
    ranked = sorted(monthly_rows, key=lambda row: row["return_pct"])
    rows = []
    for rank, row in enumerate(ranked[:10], start=1):
        rows.append({"side": "worst", "rank": rank, **row})
    for rank, row in enumerate(sorted(monthly_rows, key=lambda row: row["return_pct"], reverse=True)[:10], start=1):
        rows.append({"side": "best", "rank": rank, **row})
    return rows


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
        rows.append({"strategy": strategy, "month": month, "return_pct": (equity / previous_equity - 1) * 100 if previous_equity else 0.0})
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
    swing_data: swing.SwingData,
    monthly_v1: v1.StrategyResult,
    summary_rows: List[dict],
    candidate_rows: List[dict],
    verdict_rows: List[dict],
    monthly_rows: List[dict],
    yearly_rows: List[dict],
    monthly_rank_rows: List[dict],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    passing = [row for row in candidate_rows if row["overall_pass"]]
    top_candidates = sorted(candidate_rows, key=lambda row: row["calmar"] if row["calmar"] is not None else -999, reverse=True)[:8]
    lines = [
        "# BTC/ETH Monthly Strength v1 Swing v2 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 기준 전략: BTC/ETH Monthly Strength v1",
        "- 월별 목표 비중은 v1과 동일하게 `Top1 50% / Top2 30% / Cash 20%`, BTC <= EMA200이면 Cash 100%로 계산했다.",
        "- Swing v2는 4H 신호를 독립 전략으로 쓰지 않고, 월별 목표 비중의 신규 매수 타이밍 필터로만 사용한다.",
        "- 월초 목표 비중이 감소하거나 Cash 전환이면 초과 보유분은 월초 4H open에서 정리하고, 늘려야 하는 비중만 EMA50 눌림 후 EMA20 회복을 기다린다.",
        f"- EMA50 눌림은 기존 비교와 동일하게 `low <= EMA50 + {swing.PULLBACK_ATR_TOLERANCE:.2f} ATR`로 판정했다.",
        "- 손절 후 재진입 금지는 해당 월 종료 전까지 같은 심볼 재진입을 막는 것으로 정의했다.",
        f"- CAGR 유지 pass 기준은 Monthly v1 CAGR의 {CAGR_RETENTION_FLOOR * 100:.0f}% 이상, 재진입 감소 pass 기준은 기존 EMA50 눌림 대비 4H 이내 재진입 {REENTRY_REDUCTION_FLOOR * 100:.0f}% 이하로 둔다.",
        "",
        "## 최종 판정",
        "",
        verdict_table(verdict_rows),
        "",
        f"- 전체 통과 후보: {len(passing)}개",
        "",
        "## Calmar 상위 Swing v2 후보",
        "",
        candidate_table(top_candidates),
        "",
        "## 비교 대상 전체 성과",
        "",
        summary_table(summary_rows),
        "",
        "## Swing v2 후보 판정 매트릭스",
        "",
        candidate_matrix_table(candidate_rows),
        "",
        "## 연도별 수익률",
        "",
        yearly_table(yearly_rows),
        "",
        "## 월별 수익률 샘플",
        "",
        monthly_sample_table(monthly_rows),
        "",
        "## 최악 월 Top 10",
        "",
        monthly_rank_table([row for row in monthly_rank_rows if row["side"] == "worst"]),
        "",
        "## 최고 월 Top 10",
        "",
        monthly_rank_table([row for row in monthly_rank_rows if row["side"] == "best"]),
        "",
        "## 데이터 커버리지",
        "",
        swing.coverage_table(swing_data),
        "",
        "## 산출물",
        "",
        "- `btc_eth_monthly_strength_v1_swing_v2_report.md`",
        "- `btc_eth_monthly_strength_v1_swing_v2_summary.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_candidates.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_verdicts.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_monthly_returns.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_yearly_returns.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_monthly_rankings.csv`",
        "- `btc_eth_monthly_strength_v1_swing_v2_trades.csv`",
        "",
    ]
    return "\n".join(lines)


def verdict_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def candidate_table(rows: List[dict]) -> str:
    headers = ["Strategy", "CAGR", "MDD", "Calmar", "Trades", "Re-entry", "Overall"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["strategy"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["calmar"]),
                    str(row["trades"]),
                    str(row["same_candidate_reentries_within_4h"]),
                    "PASS" if row["overall_pass"] else "FAIL",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Strategy", "Type", "CAGR", "MDD", "Sharpe", "Calmar", "Trades", "Monthly trades", "Avg hold", "PF", "Avg MAE", "Avg MFE", "4H re-entry"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["strategy"],
                    row["type"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    str(row["trades"]),
                    num(row["avg_monthly_trades"]),
                    num(row["avg_hold_days"]),
                    num(row["profit_factor"]),
                    pct(row["avg_mae_pct"]),
                    pct(row["avg_mfe_pct"]),
                    str(row["same_candidate_reentries_within_4h"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def candidate_matrix_table(rows: List[dict]) -> str:
    headers = ["Strategy", "MDD", "CAGR", "Trades", "Re-entry", "Calmar", "Overall"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["strategy"],
                    "PASS" if row["mdd_pass"] else "FAIL",
                    "PASS" if row["cagr_pass"] else "FAIL",
                    "PASS" if row["trade_count_pass"] else "FAIL",
                    "PASS" if row["reentry_pass"] else "FAIL",
                    "PASS" if row["calmar_pass"] else "FAIL",
                    "PASS" if row["overall_pass"] else "FAIL",
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
    for strategy in strategies[:12]:
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
    for strategy in strategies[:12]:
        values = [pct(lookup.get((strategy, month))) for month in sample_months]
        lines.append("| " + " | ".join([strategy] + values) + " |")
    return "\n".join(lines)


def monthly_rank_table(rows: List[dict]) -> str:
    lines = ["| Rank | Strategy | Month | Return |", "|---|---|---|---:|"]
    for row in rows:
        lines.append(f"| {row['rank']} | {row['strategy']} | {row['month']} | {pct(row['return_pct'])} |")
    return "\n".join(lines)


def count_same_candidate_reentries(trades: List[dict]) -> int:
    previous_by_candidate: Dict[str, dict] = {}
    count = 0
    for trade in sorted(trades, key=lambda row: row["entry_timestamp"]):
        previous = previous_by_candidate.get(trade["candidate_key"])
        if previous and trade["entry_timestamp"] - previous["exit_timestamp"] <= swing.INTERVAL_SECONDS:
            count += 1
        previous_by_candidate[trade["candidate_key"]] = trade
    return count


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
