"""Robustness audit for Alpha Engine v1.2 defensive_probe.

This is a read-only analysis script. It does not touch paper state, live order
code, or the existing V0/V1 comparison report.
"""

from __future__ import annotations

import argparse
import csv
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

import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_2_defensive_probe as defensive_probe_rules  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
BASE_FEE = candidate.BASE_FEE
BASE_SLIPPAGE = candidate.BASE_SLIPPAGE
TOP_SCORE_PCT = 0.20
COOLDOWN_SECONDS = max(24 * 3600, 3 * 4 * 3600)

AUDIT_MD = "alpha_engine_v1_2_defensive_probe_audit.md"
AUDIT_CSV = "alpha_engine_v1_2_defensive_probe_audit.csv"
PARAM_CSV = "alpha_engine_v1_2_defensive_probe_audit_params.csv"
COST_CSV = "alpha_engine_v1_2_defensive_probe_audit_costs.csv"
SYMBOL_CSV = "alpha_engine_v1_2_defensive_probe_audit_symbols.csv"
PERIOD_CSV = "alpha_engine_v1_2_defensive_probe_audit_periods.csv"


@dataclass(frozen=True)
class AuditVariant:
    name: str
    defensive_probe: bool = False
    score_threshold: float = 85.0
    size_multiplier: float = 0.25
    same_symbol_cooldown: bool = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local OHLCV/funding JSON when available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_alpha_data(args.use_cache)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})
    funding_index = load_funding_index(args.use_cache)

    v0 = run_and_adjust(data, funding_index, AuditVariant("V0"), BASE_FEE, BASE_SLIPPAGE)
    v1 = run_and_adjust(data, funding_index, AuditVariant("V1_85_25", defensive_probe=True), BASE_FEE, BASE_SLIPPAGE)

    defensive_quality = defensive_quality_row(v1)
    symbol_rows = symbol_rows_for(v0, v1)
    period_rows = period_rows_for(v0, v1, data)
    cost_rows = cost_stress_rows(data, funding_index)
    param_rows = parameter_rows(data, funding_index, v0)
    leakage = leakage_row(v0, v1)
    verdict = verdict_row(v0, v1, defensive_quality, symbol_rows, period_rows, cost_rows, leakage)
    audit_rows = [summary_row(v0, v1, defensive_quality, symbol_rows, period_rows, leakage, verdict)]

    report = build_report(audit_rows[0], defensive_quality, symbol_rows, period_rows, cost_rows, param_rows, leakage, verdict)

    write_csv(output_dir / AUDIT_CSV, audit_rows)
    write_csv(output_dir / PARAM_CSV, param_rows)
    write_csv(output_dir / COST_CSV, cost_rows)
    write_csv(output_dir / SYMBOL_CSV, symbol_rows)
    write_csv(output_dir / PERIOD_CSV, period_rows)
    (output_dir / AUDIT_MD).write_text(report, encoding="utf-8")
    print(output_dir / AUDIT_MD)


def load_alpha_data(use_cache: bool) -> alpha.AlphaData:
    raw_1d = alpha.load_raw(SYMBOLS, "1d", use_cache, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(SYMBOLS, "4h", use_cache, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(SYMBOLS, "1h", use_cache, alpha.FETCH_INTRADAY_START)
    return alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)


def load_funding_index(use_cache: bool) -> dict:
    funding_info = funding.load_funding_info(use_cache)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }
    return rb.build_time_index(funding_by_symbol, time_key="funding_time")


def run_and_adjust(data: alpha.AlphaData, funding_index: dict, variant: AuditVariant, fee_rate: float, slippage_rate: float) -> dict:
    config = rb.RunConfig(
        variant=rb.RobustVariant(
            variant.name,
            exclude_doge=True,
            top_score_pct=TOP_SCORE_PCT,
            require_liquidation_buffer=True,
            defensive_probe=variant.defensive_probe,
            group="Audit",
        ),
        market_data="spot",
        slippage_rate=slippage_rate,
        fee_rate=fee_rate,
    )
    result = run_audit_engine(data, config, variant)
    trades, cashflows = rb.annotate_funding_fast(result.trades, funding_index, "actual_funding", "actual funding", "actual")
    curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    return {"name": variant.name, "variant": variant, "config": config, "result": result, "trades": trades, "curve": curve}


def run_audit_engine(data: alpha.AlphaData, config: rb.RunConfig, audit_variant: AuditVariant) -> rb.RunResult:
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    probe_log: List[dict] = []
    last_probe_entry_by_symbol: Dict[str, int] = {}
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
            cash, closed = rb.manage_position(data, config, positions[symbol], row, close_time, index, cash)
            if closed:
                trades.append(closed)
                positions.pop(symbol, None)

        if config.variant.max_positions and alpha.is_shock_date(data, alpha.date_from_ts(close_time)):
            for symbol in list(positions):
                row = data.by_time_1h.get(symbol, {}).get(time)
                if not row:
                    continue
                trade = rb.close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), close_time, index, "shock_exit")
                cash += trade.pop("_cash_delta")
                trades.append(trade)

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
        probe_decisions = audit_probe_decisions(data, batch, time, audit_variant, last_probe_entry_by_symbol) if audit_variant.defensive_probe else {}
        for signal in batch:
            key = rb.signal_key(signal)
            if key in probe_decisions:
                probe_log.append(defensive_probe_log_row(signal, time, probe_decisions[key], audit_variant))

        eligible_for_top = [
            signal
            for signal in batch
            if signal.get("regime_reason") != "defensive_reduce_risk"
            and not (config.variant.exclude_doge and signal["symbol"] == "DOGE")
        ]
        top_allowed = set()
        if config.variant.top_score_pct:
            top_n = max(1, math.ceil(len(eligible_for_top) * config.variant.top_score_pct))
            top_allowed = {rb.signal_key(signal) for signal in eligible_for_top[:top_n]}

        for signal in batch:
            symbol = f"{signal['symbol']}USDT"
            key = rb.signal_key(signal)
            probe_can_enter = bool(probe_decisions.get(key, {}).get("probe_can_enter"))
            if signal.get("regime_reason") == "defensive_reduce_risk" and not probe_can_enter:
                skip_counter[probe_decisions.get(key, {}).get("block_reason") or "defensive_no_entry"] += 1
                continue
            if config.variant.exclude_doge and symbol == "DOGEUSDT":
                skip_counter["doge_excluded"] += 1
                continue
            if config.variant.top_score_pct and key not in top_allowed and not probe_can_enter:
                skip_counter["alpha_score_not_top_20pct"] += 1
                continue
            if symbol in positions or symbol in pending:
                skip_counter["already_open_or_pending"] += 1
                continue
            order = {**signal, "symbol": symbol, "fill_time": time}
            if probe_can_enter:
                order["probe_can_enter"] = True
                order["size_multiplier"] = audit_variant.size_multiplier
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
            equity = rb.portfolio_equity(cash, positions, data, time)
            position, fee, reason = rb.create_position(data, config, order, row, time, index, equity, positions)
            if not position:
                skip_counter[reason or "position_rejected"] += 1
                continue
            cash -= fee
            positions[position.symbol] = position
            if order.get("probe_can_enter"):
                last_probe_entry_by_symbol[order["symbol"]] = time

        equity_curve.append({"time": close_time, "date": alpha.format_dt(close_time), "equity": rb.portfolio_equity(cash, positions, data, time)})

    last_time = data.times_1h[-1]
    last_index = len(data.times_1h) - 1
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(last_time)
        if row:
            trade = rb.close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), last_time + 3600, last_index, "end_of_test")
            cash += trade.pop("_cash_delta")
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": alpha.format_dt(last_time + 3600), "equity": cash})
    return rb.RunResult(config=config, trades=trades, equity_curve=equity_curve, skip_counter=skip_counter, probe_log=probe_log)


def audit_probe_decisions(
    data: alpha.AlphaData,
    batch: List[dict],
    fill_time: int,
    variant: AuditVariant,
    last_probe_entry_by_symbol: Dict[str, int],
) -> Dict[Tuple[str, int], dict]:
    decisions: Dict[Tuple[str, int], dict] = {}
    selected_key = None
    defensive_signals = [
        signal
        for signal in batch
        if defensive_probe_rules.is_defensive_state(signal.get("trade_regime", ""), signal.get("trade_action_bias", ""), signal.get("regime_reason", ""))
    ]
    for signal in sorted(defensive_signals, key=lambda item: (float(item.get("alpha_score") or 0.0), -int(item.get("rank") or 999)), reverse=True):
        symbol = f"{signal['symbol']}USDT"
        cooldown_ok = True
        if variant.same_symbol_cooldown:
            last_entry = last_probe_entry_by_symbol.get(symbol)
            cooldown_ok = last_entry is None or fill_time - last_entry >= COOLDOWN_SECONDS
        decision = audit_probe_decision(data, signal, fill_time, variant, selected_key is None and cooldown_ok)
        if decision["probe_can_enter"]:
            selected_key = rb.signal_key(signal)
        elif not cooldown_ok and decision["block_reason"] in {"", "probe_max_one_per_batch"}:
            decision = {**decision, "block_reason": "same_symbol_cooldown", "probe_reason": "same_symbol_cooldown"}
        decisions[rb.signal_key(signal)] = decision
    return decisions


def audit_probe_decision(data: alpha.AlphaData, signal: dict, fill_time: int, variant: AuditVariant, max_slot_available: bool) -> dict:
    btc = data.by_time_4h.get("BTCUSDT", {}).get(int(signal.get("signal_time") or fill_time) - 4 * 3600)
    alpha_score = defensive_probe_rules.score_value(signal, "alpha_score")
    relative_ok = defensive_probe_rules.relative_strength_ok(signal)
    btc_panic = defensive_probe_rules.btc_panic_condition(
        signal.get("trade_regime", ""),
        signal.get("trade_action_bias", ""),
        signal.get("regime_reason", ""),
        btc,
    )
    score_ok = defensive_probe_rules.score_percent(signal) >= variant.score_threshold
    can_probe = True
    reason = "passed"
    if defensive_probe_rules.hard_risk_block(signal.get("trade_regime", ""), signal.get("trade_action_bias", ""), signal.get("regime_reason", "")):
        can_probe = False
        reason = "risk_off_or_panic"
    elif btc_panic:
        can_probe = False
        reason = "btc_panic_condition"
    elif not score_ok:
        can_probe = False
        reason = "score_below_threshold"
    elif not relative_ok:
        can_probe = False
        reason = "relative_strength_failed"
    elif not max_slot_available:
        can_probe = False
        reason = "probe_max_one_per_batch"
    return {
        "probe_can_enter": can_probe,
        "alpha_score": alpha_score,
        "relative_strength_ok": relative_ok,
        "btc_panic_condition": btc_panic,
        "size_multiplier": variant.size_multiplier if can_probe else 0.0,
        "block_reason": "" if can_probe else reason,
        "probe_reason": reason,
    }


def defensive_probe_log_row(signal: dict, timestamp: int, decision: dict, variant: AuditVariant) -> dict:
    row = defensive_probe_rules.log_row(
        timestamp,
        f"{signal.get('symbol', '')}USDT",
        signal.get("trade_regime", ""),
        signal.get("trade_action_bias", ""),
        False,
        decision,
    )
    row["variant"] = variant.name
    return row


def defensive_quality_row(run: dict) -> dict:
    trades = defensive_trades(run["trades"])
    returns = [float(trade.get("trade_return_after_funding_pct") or 0.0) for trade in trades]
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    positive_returns = [value for value in returns if value > 0]
    negative_returns = [value for value in returns if value < 0]
    r_values = [value for value in (r_multiple(trade) for trade in trades) if value is not None]
    best = max(trades, key=lambda trade: float(trade.get("pnl_after_funding") or 0.0), default={})
    worst = min(trades, key=lambda trade: float(trade.get("pnl_after_funding") or 0.0), default={})
    return {
        "defensive_trade_count": len(trades),
        "defensive_win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "defensive_profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "defensive_avg_gain_pct": statistics.mean(positive_returns) if positive_returns else 0.0,
        "defensive_avg_loss_pct": statistics.mean(negative_returns) if negative_returns else 0.0,
        "defensive_average_r": statistics.mean(r_values) if r_values else None,
        "defensive_max_consecutive_losses": max_consecutive_losses(trades),
        "defensive_expectancy_pct": statistics.mean(returns) if returns else 0.0,
        "defensive_median_trade_return_pct": statistics.median(returns) if returns else 0.0,
        "defensive_best_trade_symbol": best.get("symbol", ""),
        "defensive_best_trade_return_pct": best.get("trade_return_after_funding_pct", ""),
        "defensive_worst_trade_symbol": worst.get("symbol", ""),
        "defensive_worst_trade_return_pct": worst.get("trade_return_after_funding_pct", ""),
    }


def symbol_rows_for(v0: dict, v1: dict) -> List[dict]:
    trades = defensive_trades(v1["trades"])
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["symbol"]].append(trade)
    additional_pnl = max(1e-12, final_equity(v1) - final_equity(v0))
    rows = []
    for symbol, items in sorted(grouped.items()):
        pnls = [float(item.get("pnl_after_funding") or 0.0) for item in items]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        rows.append(
            {
                "symbol": symbol,
                "trade_count": len(items),
                "total_pnl": sum(pnls),
                "win_rate_pct": len(wins) / len(items) * 100 if items else 0.0,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
                "average_r": mean_present(r_multiple(item) for item in items),
                "mdd_contribution_pct": pnl_curve_mdd_pct(items),
                "additional_return_contribution_pct": sum(pnls) / additional_pnl * 100,
            }
        )
    return sorted(rows, key=lambda row: row["total_pnl"], reverse=True)


def period_rows_for(v0: dict, v1: dict, data: alpha.AlphaData) -> List[dict]:
    v0_periods = period_stats(v0["curve"])
    v1_periods = period_stats(v1["curve"])
    trades_by_month = defaultdict(list)
    for trade in defensive_trades(v1["trades"]):
        trades_by_month[alpha.month_from_ts(int(trade["entry_timestamp"]))].append(trade)
    btc_month_returns = btc_monthly_returns(data)
    rows = []
    for month in sorted(set(v0_periods) | set(v1_periods)):
        defensive_pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in trades_by_month.get(month, []))
        v0_return = v0_periods.get(month, {}).get("return_pct")
        v1_return = v1_periods.get(month, {}).get("return_pct")
        rows.append(
            {
                "period": month,
                "market_state": market_state(btc_month_returns.get(month)),
                "btc_return_pct": btc_month_returns.get(month),
                "v0_return_pct": v0_return,
                "v1_return_pct": v1_return,
                "v1_minus_v0_pct": (v1_return - v0_return) if v0_return is not None and v1_return is not None else None,
                "v0_mdd_pct": v0_periods.get(month, {}).get("mdd_pct"),
                "v1_mdd_pct": v1_periods.get(month, {}).get("mdd_pct"),
                "defensive_probe_trade_count": len(trades_by_month.get(month, [])),
                "defensive_probe_pnl": defensive_pnl,
            }
        )
    return rows


def cost_stress_rows(data: alpha.AlphaData, funding_index: dict) -> List[dict]:
    cases = [
        ("base", 1, 1),
        ("fee_2x", 2, 1),
        ("fee_3x", 3, 1),
        ("slippage_2x", 1, 2),
        ("slippage_3x", 1, 3),
        ("fee_2x_slippage_2x", 2, 2),
        ("fee_3x_slippage_3x", 3, 3),
    ]
    rows = []
    for name, fee_mult, slip_mult in cases:
        v0 = run_and_adjust(data, funding_index, AuditVariant("V0"), BASE_FEE * fee_mult, BASE_SLIPPAGE * slip_mult)
        v1 = run_and_adjust(data, funding_index, AuditVariant("V1_85_25", defensive_probe=True), BASE_FEE * fee_mult, BASE_SLIPPAGE * slip_mult)
        v0_metrics = run_metrics(v0)
        v1_metrics = run_metrics(v1)
        rows.append(
            {
                "case": name,
                "fee_multiplier": fee_mult,
                "slippage_multiplier": slip_mult,
                "v0_total_return_pct": v0_metrics["total_return_pct"],
                "v1_total_return_pct": v1_metrics["total_return_pct"],
                "v1_additional_return_pct": v1_metrics["total_return_pct"] - v0_metrics["total_return_pct"],
                "v0_mdd_pct": v0_metrics["mdd_pct"],
                "v1_mdd_pct": v1_metrics["mdd_pct"],
                "v1_additional_mdd_pct": mdd_worsening(v0_metrics["mdd_pct"], v1_metrics["mdd_pct"]),
                "v0_profit_factor": v0_metrics["profit_factor"],
                "v1_profit_factor": v1_metrics["profit_factor"],
                "v0_trade_count": v0_metrics["trade_count"],
                "v1_trade_count": v1_metrics["trade_count"],
            }
        )
    return rows


def parameter_rows(data: alpha.AlphaData, funding_index: dict, v0: dict) -> List[dict]:
    variants = [
        AuditVariant("V1_85_25", defensive_probe=True, score_threshold=85, size_multiplier=0.25),
        AuditVariant("V1_90_25", defensive_probe=True, score_threshold=90, size_multiplier=0.25),
        AuditVariant("V1_90_15", defensive_probe=True, score_threshold=90, size_multiplier=0.15),
        AuditVariant("V1_85_15", defensive_probe=True, score_threshold=85, size_multiplier=0.15),
        AuditVariant("V1_90_25_cooldown", defensive_probe=True, score_threshold=90, size_multiplier=0.25, same_symbol_cooldown=True),
        AuditVariant("V1_85_25_cooldown", defensive_probe=True, score_threshold=85, size_multiplier=0.25, same_symbol_cooldown=True),
    ]
    v0_metrics = run_metrics(v0)
    rows = []
    for variant in variants:
        run = run_and_adjust(data, funding_index, variant, BASE_FEE, BASE_SLIPPAGE)
        metrics = run_metrics(run)
        rows.append(
            {
                "variant": variant.name,
                "score_threshold": variant.score_threshold,
                "size_multiplier": variant.size_multiplier,
                "same_symbol_cooldown": variant.same_symbol_cooldown,
                "total_return_pct": metrics["total_return_pct"],
                "mdd_pct": metrics["mdd_pct"],
                "profit_factor": metrics["profit_factor"],
                "trade_count": metrics["trade_count"],
                "defensive_trade_count": len(defensive_trades(run["trades"])),
                "average_r": metrics["average_r"],
                "max_consecutive_losses": metrics["max_consecutive_losses"],
                "additional_return_vs_v0_pct": metrics["total_return_pct"] - v0_metrics["total_return_pct"],
                "additional_mdd_vs_v0_pct": mdd_worsening(v0_metrics["mdd_pct"], metrics["mdd_pct"]),
            }
        )
    return rows


def leakage_row(v0: dict, v1: dict) -> dict:
    trades = v0["trades"] + v1["trades"]
    lookahead_failures = [trade for trade in trades if not defensive_probe_rules.truthy(trade.get("lookahead_pass"))]
    execution_before_signal = [
        trade
        for trade in trades
        if int(trade.get("entry_timestamp") or 0) < int(trade.get("signal_date") and trade.get("entry_timestamp") or trade.get("entry_timestamp") or 0)
    ]
    entry_before_signal = [
        trade
        for trade in trades
        if int(trade.get("entry_timestamp") or 0) < int(trade.get("signal_timestamp") or trade.get("entry_timestamp") or 0)
    ]
    return {
        "lookahead_failure_count": len(lookahead_failures),
        "entry_before_signal_count": len(entry_before_signal or execution_before_signal),
        "same_loaded_data_object": True,
        "same_fee_slippage_for_v0_v1": v0["config"].fee_rate == v1["config"].fee_rate and v0["config"].slippage_rate == v1["config"].slippage_rate,
        "same_market_data_path": v0["config"].market_data == v1["config"].market_data == "spot",
        "suspected_leakage": bool(lookahead_failures or entry_before_signal or execution_before_signal),
    }


def verdict_row(v0: dict, v1: dict, quality: dict, symbol_rows: List[dict], period_rows: List[dict], cost_rows: List[dict], leakage: dict) -> dict:
    v0_metrics = run_metrics(v0)
    v1_metrics = run_metrics(v1)
    combined_2x = next(row for row in cost_rows if row["case"] == "fee_2x_slippage_2x")
    any_2x_lost = any(
        row["v1_additional_return_pct"] <= 0
        for row in cost_rows
        if row["case"] in {"fee_2x", "slippage_2x", "fee_2x_slippage_2x"}
    )
    mdd_extra = mdd_worsening(v0_metrics["mdd_pct"], v1_metrics["mdd_pct"])
    concentration = concentration_summary(symbol_rows, period_rows)
    fail_reasons = []
    watch_reasons = []
    if any_2x_lost:
        fail_reasons.append("cost_2x_advantage_lost")
    if mdd_extra >= 5:
        fail_reasons.append("additional_mdd_gte_5pp")
    if (quality.get("defensive_profit_factor") or 0.0) <= 1.0:
        fail_reasons.append("defensive_pf_lte_1")
    if leakage.get("suspected_leakage"):
        fail_reasons.append("lookahead_or_data_leakage_possible")

    if not fail_reasons:
        if combined_2x["v1_additional_return_pct"] <= 0:
            watch_reasons.append("cost_stress_edge_weak")
        if mdd_extra > 3:
            watch_reasons.append("additional_mdd_gt_3pp")
        if (quality.get("defensive_profit_factor") or 0.0) <= 1.15:
            watch_reasons.append("defensive_pf_lte_1_15")
        if concentration["symbol_concentration_watch"] or concentration["period_concentration_watch"]:
            watch_reasons.append("concentration_watch")
        if v1_metrics["trade_count"] > v0_metrics["trade_count"] * 1.75:
            watch_reasons.append("trade_count_high")

    if fail_reasons:
        verdict = "FAIL"
        reasons = fail_reasons
    elif watch_reasons:
        verdict = "WATCH"
        reasons = watch_reasons
    else:
        verdict = "PASS"
        reasons = ["all_pass_conditions_met"]
    return {
        "verdict": verdict,
        "reasons": ";".join(reasons),
        "cost_2x_additional_return_pct": combined_2x["v1_additional_return_pct"],
        "additional_mdd_worsening_pct": mdd_extra,
        "defensive_profit_factor": quality.get("defensive_profit_factor"),
        **concentration,
        "suspected_leakage": leakage.get("suspected_leakage"),
    }


def summary_row(v0: dict, v1: dict, quality: dict, symbol_rows: List[dict], period_rows: List[dict], leakage: dict, verdict: dict) -> dict:
    v0_metrics = run_metrics(v0)
    v1_metrics = run_metrics(v1)
    concentration = concentration_summary(symbol_rows, period_rows)
    return {
        "verdict": verdict["verdict"],
        "verdict_reasons": verdict["reasons"],
        "v0_total_return_pct": v0_metrics["total_return_pct"],
        "v1_total_return_pct": v1_metrics["total_return_pct"],
        "v1_additional_return_pct": v1_metrics["total_return_pct"] - v0_metrics["total_return_pct"],
        "v0_mdd_pct": v0_metrics["mdd_pct"],
        "v1_mdd_pct": v1_metrics["mdd_pct"],
        "v1_additional_mdd_worsening_pct": mdd_worsening(v0_metrics["mdd_pct"], v1_metrics["mdd_pct"]),
        **quality,
        **concentration,
        **leakage,
    }


def run_metrics(run: dict) -> dict:
    trades = run["trades"]
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    return {
        "total_return_pct": (final_equity(run) - 1) * 100,
        "mdd_pct": swing.max_drawdown(run["curve"]) * 100,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trade_count": len(trades),
        "average_r": mean_present(r_multiple(trade) for trade in trades),
        "max_consecutive_losses": max_consecutive_losses(trades),
    }


def defensive_trades(trades: List[dict]) -> List[dict]:
    return [
        trade
        for trade in trades
        if str(trade.get("trade_regime", "")).lower() == "defensive"
        or str(trade.get("trade_action_bias", "")).lower() == "reduce_risk"
    ]


def final_equity(run: dict) -> float:
    return run["curve"][-1]["equity"] if run["curve"] else 1.0


def r_multiple(trade: dict) -> Optional[float]:
    risk_pct = float(trade.get("risk_distance_pct") or 0.0) / 100
    initial_risk = float(trade.get("initial_units") or 0.0) * float(trade.get("entry_price") or 0.0) * risk_pct
    if initial_risk <= 0:
        return None
    return float(trade.get("pnl_after_funding") or 0.0) / initial_risk


def max_consecutive_losses(trades: List[dict]) -> int:
    max_count = 0
    current = 0
    for trade in sorted(trades, key=lambda row: int(row.get("exit_timestamp") or 0)):
        if float(trade.get("pnl_after_funding") or 0.0) < 0:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    return statistics.mean(clean) if clean else None


def pnl_curve_mdd_pct(trades: List[dict]) -> float:
    cumulative = 0.0
    peak = 0.0
    mdd = 0.0
    for trade in sorted(trades, key=lambda row: int(row.get("exit_timestamp") or 0)):
        cumulative += float(trade.get("pnl_after_funding") or 0.0)
        peak = max(peak, cumulative)
        mdd = min(mdd, cumulative - peak)
    return mdd * 100


def period_stats(curve: List[dict]) -> Dict[str, dict]:
    grouped = defaultdict(list)
    for point in curve:
        grouped[alpha.month_from_ts(int(point["time"]))].append(point)
    out = {}
    previous_equity = 1.0
    for month in sorted(grouped):
        points = sorted(grouped[month], key=lambda row: row["time"])
        start_equity = previous_equity
        end_equity = points[-1]["equity"]
        previous_equity = end_equity
        scoped = [{"time": points[0]["time"] - 1, "equity": start_equity}] + points
        out[month] = {
            "return_pct": (end_equity / start_equity - 1) * 100 if start_equity > 0 else None,
            "mdd_pct": swing.max_drawdown(scoped) * 100,
        }
    return out


def btc_monthly_returns(data: alpha.AlphaData) -> Dict[str, float]:
    month_rows = defaultdict(list)
    for row in data.rows_1h["BTCUSDT"]:
        if alpha.TEST_START_TS <= row["time"] < alpha.TEST_END_TS:
            month_rows[alpha.month_from_ts(row["time"])].append(row)
    out = {}
    for month, rows in month_rows.items():
        sorted_rows = sorted(rows, key=lambda row: row["time"])
        if sorted_rows[0]["open"]:
            out[month] = (sorted_rows[-1]["close"] / sorted_rows[0]["open"] - 1) * 100
    return out


def market_state(btc_return_pct: Optional[float]) -> str:
    if btc_return_pct is None:
        return "unknown"
    if btc_return_pct <= -5:
        return "downtrend"
    if btc_return_pct >= 5:
        return "rebound"
    return "range"


def concentration_summary(symbol_rows: List[dict], period_rows: List[dict]) -> dict:
    positive_symbols = [row for row in symbol_rows if row["total_pnl"] > 0]
    negative_symbols = [row for row in symbol_rows if row["total_pnl"] < 0]
    positive_total = sum(row["total_pnl"] for row in positive_symbols)
    negative_total = abs(sum(row["total_pnl"] for row in negative_symbols))
    top2_profit_share = sum(row["total_pnl"] for row in sorted(positive_symbols, key=lambda row: row["total_pnl"], reverse=True)[:2]) / positive_total * 100 if positive_total else 0.0
    top2_loss_share = abs(sum(row["total_pnl"] for row in sorted(negative_symbols, key=lambda row: row["total_pnl"])[:2])) / negative_total * 100 if negative_total else 0.0
    positive_periods = [row for row in period_rows if (row.get("defensive_probe_pnl") or 0.0) > 0]
    positive_period_total = sum(row["defensive_probe_pnl"] for row in positive_periods)
    top_period_share = max((row["defensive_probe_pnl"] for row in positive_periods), default=0.0) / positive_period_total * 100 if positive_period_total else 0.0
    return {
        "top2_profit_symbol_share_pct": top2_profit_share,
        "top2_loss_symbol_share_pct": top2_loss_share,
        "top_positive_period_share_pct": top_period_share,
        "symbol_concentration_watch": top2_profit_share > 70 or top2_loss_share > 70,
        "period_concentration_watch": top_period_share > 50,
    }


def mdd_worsening(v0_mdd_pct: float, v1_mdd_pct: float) -> float:
    return max(0.0, abs(v1_mdd_pct) - abs(v0_mdd_pct))


def build_report(
    summary: dict,
    quality: dict,
    symbol_rows: List[dict],
    period_rows: List[dict],
    cost_rows: List[dict],
    param_rows: List[dict],
    leakage: dict,
    verdict: dict,
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state_rows = market_state_rows(period_rows)
    lines = [
        "# Alpha Engine v1.2 Defensive Probe Audit",
        "",
        f"- 생성 시각: {generated_at}",
        "- 분석 범위: 2020-01-01 ~ 2025-12-31 UTC",
        "- 원칙: 기존 V0/V1 전략 소스와 paper/probe state는 변경하지 않고, reports 산출물만 생성했다.",
        "- score 85는 기존 0~10 alpha_score 스케일에서 8.5 이상으로 환산했다.",
        "",
        "## Final Verdict",
        "",
        f"- 판정: **{verdict['verdict']}**",
        f"- 사유: {verdict['reasons']}",
        f"- 비용 2배 추가 수익: {fmt(verdict['cost_2x_additional_return_pct'], True)}",
        f"- 추가 MDD 악화폭: {fmt(verdict['additional_mdd_worsening_pct'], True)}",
        f"- defensive PF: {fmt(verdict['defensive_profit_factor'])}",
        f"- lookahead/data leakage 의심: {verdict['suspected_leakage']}",
        "",
        "## Defensive Entry Quality",
        "",
        key_value_table(quality),
        "",
        "## Symbol Concentration",
        "",
        table(symbol_rows[:12], ["symbol", "trade_count", "total_pnl", "win_rate_pct", "profit_factor", "average_r", "mdd_contribution_pct", "additional_return_contribution_pct"]),
        "",
        f"- top 2 profit symbol share: {fmt(summary['top2_profit_symbol_share_pct'], True)}",
        f"- top 2 loss symbol share: {fmt(summary['top2_loss_symbol_share_pct'], True)}",
        "",
        "## Period / Market State",
        "",
        table(period_rows[:18], ["period", "market_state", "v0_return_pct", "v1_return_pct", "v1_minus_v0_pct", "v0_mdd_pct", "v1_mdd_pct", "defensive_probe_trade_count", "defensive_probe_pnl"]),
        "",
        "### Market State Aggregate",
        "",
        table(state_rows, ["market_state", "period_count", "avg_v1_minus_v0_pct", "defensive_probe_trade_count", "defensive_probe_pnl"]),
        "",
        "## Cost Stress",
        "",
        table(cost_rows, ["case", "v0_total_return_pct", "v1_total_return_pct", "v1_additional_return_pct", "v0_mdd_pct", "v1_mdd_pct", "v1_additional_mdd_pct", "v1_profit_factor", "v1_trade_count"]),
        "",
        "## Parameter Sensitivity",
        "",
        table(param_rows, ["variant", "total_return_pct", "mdd_pct", "profit_factor", "trade_count", "defensive_trade_count", "average_r", "max_consecutive_losses", "additional_return_vs_v0_pct", "additional_mdd_vs_v0_pct"]),
        "",
        "## Lookahead / Data Leakage Check",
        "",
        "- 진입 판단은 4H 신호 close timestamp 이후 `next_open` 실행 timestamp에서 이루어지는 기존 경로를 재사용했다.",
        "- `lookahead_pass` 실패 수: " + str(leakage["lookahead_failure_count"]),
        "- V0/V1은 스크립트에서 같은 `AlphaData` 객체와 같은 funding index를 공유한다.",
        "- `--use-cache` 사용 시 raw OHLCV/funding 캐시를 한 번 로드한 뒤 모든 변형에 동일하게 주입한다.",
        "- V1은 V0보다 유리한 별도 데이터 경로를 쓰지 않는다.",
        "",
        "## CSV Outputs",
        "",
        f"- `{AUDIT_CSV}`",
        f"- `{PARAM_CSV}`",
        f"- `{COST_CSV}`",
        f"- `{SYMBOL_CSV}`",
        f"- `{PERIOD_CSV}`",
        "",
    ]
    return "\n".join(lines)


def market_state_rows(period_rows: List[dict]) -> List[dict]:
    grouped = defaultdict(list)
    for row in period_rows:
        grouped[row["market_state"]].append(row)
    out = []
    for state, rows in sorted(grouped.items()):
        out.append(
            {
                "market_state": state,
                "period_count": len(rows),
                "avg_v1_minus_v0_pct": mean_present(row.get("v1_minus_v0_pct") for row in rows),
                "defensive_probe_trade_count": sum(row.get("defensive_probe_trade_count") or 0 for row in rows),
                "defensive_probe_pnl": sum(row.get("defensive_probe_pnl") or 0.0 for row in rows),
            }
        )
    return out


def key_value_table(row: dict) -> str:
    lines = ["| Metric | Value |", "|---|---:|"]
    for key, value in row.items():
        lines.append(f"| {key} | {fmt(value, key.endswith('_pct'))} |")
    return "\n".join(lines)


def table(rows: List[dict], keys: List[str]) -> str:
    lines = ["| " + " | ".join(keys) + " |", "|" + "|".join(["---"] * len(keys)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(key), key.endswith("_pct")) for key in keys) + " |")
    return "\n".join(lines)


def fmt(value, percent: bool = False) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    suffix = "%" if percent else ""
    return f"{float(value):.2f}{suffix}"


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if fieldnames:
            writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
