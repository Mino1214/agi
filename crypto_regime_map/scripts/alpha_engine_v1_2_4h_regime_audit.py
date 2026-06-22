"""Read-only focused audit for Alpha Engine v1.2 BTC 4H regime variants."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_4h_regime as short4h  # noqa: E402
import alpha_engine_v1_2_4h_regime_report as comparison  # noqa: E402
import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
BASE_FEE = candidate.BASE_FEE
BASE_SLIPPAGE = candidate.BASE_SLIPPAGE
TOP_SCORE_PCT = candidate.TOP_SCORE_PCT if hasattr(candidate, "TOP_SCORE_PCT") else 0.20
COST_SCENARIOS = [
    ("base", BASE_FEE, BASE_SLIPPAGE),
    ("cost_2x", BASE_FEE * 2, BASE_SLIPPAGE),
    ("slippage_2x", BASE_FEE, BASE_SLIPPAGE * 2),
    ("cost_2x_slippage_2x", BASE_FEE * 2, BASE_SLIPPAGE * 2),
    ("cost_3x_slippage_3x", BASE_FEE * 3, BASE_SLIPPAGE * 3),
]


@dataclass(frozen=True)
class AuditVariant:
    name: str
    gate_config: short4h.GateConfig
    recovery_score_min_pct: Optional[float] = None
    recovery_only_if_1d_not_defensive: bool = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir)

    raw_1d = comparison.load_cached_raw(raw_dir, SYMBOLS, "1d")
    raw_4h = comparison.load_cached_raw(raw_dir, SYMBOLS, "4h")
    raw_1h = comparison.load_cached_raw(raw_dir, SYMBOLS, "1h")
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})

    short_index = short4h.build_regime_indexes(raw_4h["BTCUSDT"])
    short_rows = [
        row
        for row in short_index["rows"]
        if alpha.TEST_START_TS <= int(row["close_time"]) < alpha.TEST_END_TS
    ]
    transitions = short4h.transition_rows(short_rows)
    funding_index = comparison.load_cached_funding_index(raw_dir, SYMBOLS)
    variants = audit_variants()
    signals_by_variant = {
        variant.name: build_audit_signals(data, short_index, variant)
        for variant in variants
    }

    runs = []
    for scenario, fee_rate, slippage_rate in COST_SCENARIOS:
        runs.append(run_v0(data, funding_index, scenario, fee_rate, slippage_rate))
        for variant in variants:
            runs.append(
                run_audit_variant(
                    data,
                    funding_index,
                    variant,
                    signals_by_variant[variant.name],
                    scenario,
                    fee_rate,
                    slippage_rate,
                )
            )

    variant_rows = [metrics(run) for run in runs]
    base_runs = [run for run in runs if run["scenario"] == "base"]
    summary_rows = build_summary_rows(base_runs, runs, transitions)
    regime_rows = [row for run in base_runs for row in regime_performance_rows(run)]
    recovery_rows = recovery_analysis_rows(base_runs)
    whipsaw_rows = whipsaw_analysis_rows(base_runs, transitions)
    report = build_report(summary_rows, variant_rows, recovery_rows, whipsaw_rows, regime_rows)

    write_csv(output_dir / "alpha_engine_v1_2_4h_regime_audit_summary.csv", summary_rows)
    write_csv(output_dir / "alpha_engine_v1_2_4h_regime_audit_variant_comparison.csv", variant_rows)
    write_csv(output_dir / "alpha_engine_v1_2_4h_regime_audit_recovery_analysis.csv", recovery_rows)
    write_csv(output_dir / "alpha_engine_v1_2_4h_regime_audit_whipsaw_analysis.csv", whipsaw_rows)
    write_csv(output_dir / "alpha_engine_v1_2_4h_regime_audit_regime_performance.csv", regime_rows)
    report_path = output_dir / "alpha_engine_v1_2_4h_regime_audit.md"
    report_path.write_text(report, encoding="utf-8")
    print(report_path)


def audit_variants() -> List[AuditVariant]:
    return [
        AuditVariant("V4H_strict", short4h.V4H_STRICT),
        AuditVariant("V4H_recovery_size_25", short4h.V4H_RECOVERY_25),
        AuditVariant("V4H_recovery_size_50", short4h.V4H_RECOVERY_50),
        AuditVariant("V4H_no_recovery", short4h.GateConfig("V4H_no_recovery", allow_recovery=False)),
        AuditVariant(
            "V4H_recovery_only_if_1D_not_defensive",
            short4h.GateConfig("V4H_recovery_only_if_1D_not_defensive", allow_recovery=True, recovery_size_multiplier=0.5),
            recovery_only_if_1d_not_defensive=True,
        ),
        AuditVariant(
            "V4H_recovery_score_90",
            short4h.GateConfig("V4H_recovery_score_90", allow_recovery=True, recovery_size_multiplier=0.5),
            recovery_score_min_pct=90.0,
        ),
        AuditVariant(
            "V4H_recovery_score_90_size_25",
            short4h.GateConfig("V4H_recovery_score_90_size_25", allow_recovery=True, recovery_size_multiplier=0.25),
            recovery_score_min_pct=90.0,
        ),
    ]


def run_v0(data: alpha.AlphaData, funding_index: dict, scenario: str, fee_rate: float, slippage_rate: float) -> dict:
    variant = rb.RobustVariant(
        "V0_1D",
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="V0",
    )
    config = rb.RunConfig(variant=variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    result = rb.run_robust_engine(data, config)
    return evaluate_result(funding_index, result, variant.name, scenario, "1d")


def run_audit_variant(
    data: alpha.AlphaData,
    funding_index: dict,
    variant: AuditVariant,
    signals: List[dict],
    scenario: str,
    fee_rate: float,
    slippage_rate: float,
) -> dict:
    robust_variant = rb.RobustVariant(
        variant.name,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="4H audit",
    )
    config = rb.RunConfig(variant=robust_variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    result = run_engine_with_signals(data, signals, config)
    return evaluate_result(funding_index, result, variant.name, scenario, "4h")


def evaluate_result(funding_index: dict, result: rb.RunResult, variant_name: str, scenario: str, regime_timeframe: str) -> dict:
    liq_trades = rb.annotate_liquidation(result.trades, result)
    trades, cashflows = rb.annotate_funding_fast(liq_trades, funding_index, "actual_funding", "actual funding", "actual")
    adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    return {
        "variant": variant_name,
        "scenario": scenario,
        "regime_timeframe": regime_timeframe,
        "config": result.config,
        "result": result,
        "trades": trades,
        "curve": adjusted_curve,
    }


def build_audit_signals(data: alpha.AlphaData, short_index: dict, variant: AuditVariant) -> List[dict]:
    signals = []
    btc_by_time = data.by_time_4h["BTCUSDT"]
    all_times = sorted(set().union(*(set(data.by_time_4h[symbol].keys()) for symbol in SYMBOLS if symbol in data.by_time_4h)))
    for time in all_times:
        if time < alpha.TEST_START_TS - 14 * 86400 or time >= alpha.TEST_END_TS:
            continue
        rows = {symbol: data.by_time_4h.get(symbol, {}).get(time) for symbol in SYMBOLS}
        rows = {symbol: row for symbol, row in rows.items() if row}
        if not rows:
            continue
        btc = btc_by_time.get(time)
        if not btc or btc.get("ret_7d") is None or btc.get("ret_14d") is None:
            continue
        close_time = time + 4 * 3600
        if close_time < alpha.TEST_START_TS:
            continue
        daily_regime = data.regime_by_date.get(alpha.date_from_ts(close_time), {})
        short_row = (short_index.get("by_close_time") or {}).get(close_time)
        allowed_symbols, size_multiplier, block_reason, gate_regime = short4h.gate_for_signal(
            SYMBOLS,
            short_row,
            config=variant.gate_config,
            daily_regime=daily_regime,
            health_gate={"can_probe": True, "block_reason": ""},
        )
        if not allowed_symbols:
            continue
        short_regime = str(gate_regime.get("short_regime_4h") or "")
        if (
            short_regime == "recovery"
            and variant.recovery_only_if_1d_not_defensive
            and (daily_regime.get("trade_regime") == "defensive" or daily_regime.get("trade_action_bias") == "reduce_risk")
        ):
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
            signal = alpha.score_signal(symbol, row, btc, rank_lookup[symbol], len(ranked), gate_regime, size_multiplier, block_reason)
            if not signal or signal["alpha_score"] < alpha.MIN_ALPHA_SCORE:
                continue
            if short_regime == "recovery" and variant.recovery_score_min_pct is not None and score_percent(signal) < variant.recovery_score_min_pct:
                continue
            signal.update(
                {
                    "variant": variant.name,
                    "signal_time": close_time,
                    "signal_date": alpha.format_dt(close_time),
                    "fill_mode": "next_open",
                    "lookahead_pass": True,
                    "regime_timeframe": "4h",
                    "size_multiplier": size_multiplier,
                    "daily_trade_regime": daily_regime.get("trade_regime", ""),
                    "daily_trade_action_bias": daily_regime.get("trade_action_bias", ""),
                    "short_regime_4h": gate_regime.get("short_regime_4h", ""),
                    "short_action_bias_4h": gate_regime.get("short_action_bias_4h", ""),
                    "short_regime_close_time": gate_regime.get("short_regime_close_time", close_time),
                    "hybrid_override": False,
                }
            )
            candidates.append(signal)
        candidates.sort(key=lambda item: (item["alpha_score"], -item["rank"]), reverse=True)
        signals.extend(candidates)
    return signals


def run_engine_with_signals(data: alpha.AlphaData, signals: List[dict], config: rb.RunConfig) -> rb.RunResult:
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    equity_curve = [{"time": alpha.TEST_START_TS, "date": alpha.format_dt(alpha.TEST_START_TS), "equity": 1.0}]
    signals_by_time = defaultdict(list)
    for signal in signals:
        signals_by_time[signal["signal_time"]].append(signal)

    for index, time in enumerate(data.times_1h):
        close_time = time + 3600
        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(time)
            if not row:
                continue
            position = positions[symbol]
            cash, closed = rb.manage_position(data, config, position, row, close_time, index, cash)
            if closed:
                comparison.enrich_trade(closed, position)
                trades.append(closed)
                positions.pop(symbol, None)

        if alpha.is_shock_date(data, alpha.date_from_ts(close_time)):
            for symbol in list(positions):
                row = data.by_time_1h.get(symbol, {}).get(time)
                if not row:
                    continue
                position = positions.pop(symbol)
                trade = rb.close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index, "shock_exit")
                cash += trade.pop("_cash_delta")
                comparison.enrich_trade(trade, position)
                trades.append(trade)

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
        eligible_for_top = [signal for signal in batch if not (config.variant.exclude_doge and signal["symbol"] == "DOGE")]
        top_allowed = set()
        if config.variant.top_score_pct:
            top_n = max(1, math.ceil(len(eligible_for_top) * config.variant.top_score_pct))
            top_allowed = {rb.signal_key(signal) for signal in eligible_for_top[:top_n]}

        for signal in batch:
            symbol = f"{signal['symbol']}USDT"
            if config.variant.exclude_doge and symbol == "DOGEUSDT":
                skip_counter["doge_excluded"] += 1
                continue
            if config.variant.top_score_pct and rb.signal_key(signal) not in top_allowed:
                skip_counter["alpha_score_not_top_20pct"] += 1
                continue
            if symbol in positions or symbol in pending:
                skip_counter["already_open_or_pending"] += 1
                continue
            pending[symbol] = {**signal, "symbol": symbol, "fill_time": time}

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
            comparison.attach_position_metadata(position, order)
            cash -= fee
            positions[position.symbol] = position

        equity_curve.append({"time": close_time, "date": alpha.format_dt(close_time), "equity": rb.portfolio_equity(cash, positions, data, time)})

    last_time = data.times_1h[-1]
    last_index = len(data.times_1h) - 1
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(last_time)
        if row:
            position = positions.pop(symbol)
            trade = rb.close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), last_time + 3600, last_index, "end_of_test")
            cash += trade.pop("_cash_delta")
            comparison.enrich_trade(trade, position)
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": alpha.format_dt(last_time + 3600), "equity": cash})
    return rb.RunResult(config=config, trades=trades, equity_curve=equity_curve, skip_counter=skip_counter)


def metrics(run: dict) -> dict:
    trades = run["trades"]
    curve = run["curve"]
    returns = equity_returns(curve)
    downside = [value for value in returns if value < 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    downside_stdev = statistics.stdev(downside) if len(downside) > 1 else None
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = (alpha.TEST_END_TS - alpha.TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    mdd = swing.max_drawdown(curve)
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "variant": run["variant"],
        "scenario": run["scenario"],
        "regime_timeframe": run["regime_timeframe"],
        "fee_rate_pct": run["config"].fee_rate * 100,
        "slippage_rate_pct": run["config"].slippage_rate * 100,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None,
        "sortino": statistics.mean(returns) / downside_stdev * math.sqrt(365 * 24) if downside_stdev and downside_stdev > 0 else None,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "trade_count": len(trades),
        "max_consecutive_losses": max_consecutive_losses(trades),
        "average_r": mean_present(r_multiple(trade) for trade in trades),
        "median_trade_return_pct": statistics.median([float(trade.get("trade_return_after_funding_pct") or 0.0) for trade in trades]) if trades else None,
        "skipped_trades": sum(run["result"].skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(run["result"].skip_counter.items())),
    }


def build_summary_rows(base_runs: List[dict], all_runs: List[dict], transitions: List[dict]) -> List[dict]:
    base_metrics = {run["variant"]: metrics(run) for run in base_runs}
    scenario_metrics = {(run["variant"], run["scenario"]): metrics(run) for run in all_runs}
    v0 = base_metrics["V0_1D"]
    rows = []
    for run in base_runs:
        row = dict(base_metrics[run["variant"]])
        row["total_return_vs_v0_pct_point"] = row["total_return_pct"] - v0["total_return_pct"]
        row["cagr_vs_v0_pct_point"] = row["cagr_pct"] - v0["cagr_pct"]
        row["mdd_extra_pct_point"] = abs(row["mdd_pct"]) - abs(v0["mdd_pct"])
        for scenario in ("cost_2x", "slippage_2x", "cost_2x_slippage_2x", "cost_3x_slippage_3x"):
            stress = scenario_metrics.get((run["variant"], scenario), {})
            v0_stress = scenario_metrics.get(("V0_1D", scenario), {})
            row[f"{scenario}_total_return_pct"] = stress.get("total_return_pct")
            row[f"{scenario}_return_vs_v0_pct_point"] = (
                stress.get("total_return_pct") - v0_stress.get("total_return_pct")
                if stress and v0_stress
                else None
            )
        whipsaw = whipsaw_summary_for_run(run, transitions)
        row.update(
            {
                "transition_count": whipsaw["transition_count"],
                "whipsaw_pnl_pct": whipsaw["whipsaw_pnl_pct"],
                "whipsaw_pnl_share_of_total_pct": whipsaw["whipsaw_pnl_share_of_total_pct"],
            }
        )
        row.update(verdict(row, recovery_summary(run), whipsaw))
        rows.append(row)
    return rows


def verdict(row: dict, recovery: dict, whipsaw: dict) -> dict:
    reasons = []
    status = "PASS"
    if row["variant"] == "V0_1D":
        return {"audit_status": "BASELINE", "audit_reasons": "baseline"}
    if row["total_return_vs_v0_pct_point"] <= 0 or row["cagr_vs_v0_pct_point"] <= 0:
        status = "FAIL"
        reasons.append("base return/CAGR not above V0")
    if row["mdd_extra_pct_point"] > 5:
        status = "FAIL"
        reasons.append("additional MDD > 5pp")
    elif row["mdd_extra_pct_point"] > 3 and status != "FAIL":
        status = "WATCH"
        reasons.append("additional MDD > 3pp")
    if (row.get("cost_2x_slippage_2x_return_vs_v0_pct_point") or 0.0) <= 0:
        status = "FAIL"
        reasons.append("cost 2x + slippage 2x under V0")
    if recovery["trade_count"] > 0 and recovery.get("profit_factor") is not None and recovery["profit_factor"] <= 1.0:
        status = "FAIL"
        reasons.append("recovery PF <= 1.0")
    if abs(whipsaw.get("whipsaw_pnl_share_of_total_pct") or 0.0) >= 50 and (whipsaw.get("whipsaw_pnl_pct") or 0.0) < 0:
        status = "FAIL"
        reasons.append("whipsaw losses consume most profit")
    if not reasons:
        reasons.append("meets audit thresholds")
    return {"audit_status": status, "audit_reasons": "; ".join(reasons)}


def regime_performance_rows(run: dict) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in run["trades"]:
        regime = normalized_trade_regime(trade)
        grouped[regime].append(trade)
    rows = []
    for regime in ["uptrend", "recovery", "defensive", "risk_off", "shock", "large_cap_lead", "eth_strength"]:
        trades = grouped.get(regime, [])
        if not trades:
            rows.append(empty_group_row(run["variant"], regime))
            continue
        pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        rows.append(
            {
                "variant": run["variant"],
                "regime": regime,
                "trade_count": len(trades),
                "pnl": sum(pnls),
                "pnl_pct": sum(pnls) * 100,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
                "average_r": mean_present(r_multiple(trade) for trade in trades),
                "mdd_contribution": group_mdd_contribution(trades),
                "mdd_contribution_pct": group_mdd_contribution(trades) * 100,
            }
        )
    return rows


def recovery_analysis_rows(base_runs: List[dict]) -> List[dict]:
    rows = []
    for run in base_runs:
        recovery_trades = [trade for trade in run["trades"] if normalized_trade_regime(trade) == "recovery"]
        summary = recovery_summary(run)
        rows.append({"analysis_type": "summary", "variant": run["variant"], **summary})
        if recovery_trades:
            best = max(recovery_trades, key=lambda item: float(item.get("pnl_after_funding") or 0.0))
            worst = min(recovery_trades, key=lambda item: float(item.get("pnl_after_funding") or 0.0))
            rows.append(trade_extreme_row(run["variant"], "best_trade", best))
            rows.append(trade_extreme_row(run["variant"], "worst_trade", worst))
        for row in top_recovery_symbol_losses(run["variant"], recovery_trades):
            rows.append(row)
        for row in top_recovery_period_losses(run["variant"], recovery_trades):
            rows.append(row)
    return rows


def recovery_summary(run: dict) -> dict:
    recovery_trades = [trade for trade in run["trades"] if normalized_trade_regime(trade) == "recovery"]
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in recovery_trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "trade_count": len(recovery_trades),
        "pnl": sum(pnls),
        "pnl_pct": sum(pnls) * 100,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(recovery_trades) * 100 if recovery_trades else 0.0,
        "max_consecutive_losses": max_consecutive_losses(recovery_trades),
        "average_r": mean_present(r_multiple(trade) for trade in recovery_trades),
        "mdd_contribution": group_mdd_contribution(recovery_trades),
        "mdd_contribution_pct": group_mdd_contribution(recovery_trades) * 100,
    }


def whipsaw_analysis_rows(base_runs: List[dict], transitions: List[dict]) -> List[dict]:
    pattern_count = up_def_up_count(transitions)
    rows = []
    for run in base_runs:
        summary = whipsaw_summary_for_run(run, transitions)
        summary["stop_within_1_candles"] = stop_count_after_transitions(run["trades"], transitions, 1)
        summary["stop_within_3_candles"] = stop_count_after_transitions(run["trades"], transitions, 3)
        summary["stop_within_5_candles"] = stop_count_after_transitions(run["trades"], transitions, 5)
        rows.append(
            {
                "analysis_type": "summary",
                "variant": run["variant"],
                "transition_count": len(transitions),
                "uptrend_defensive_uptrend_count": pattern_count,
                **summary,
            }
        )
        for candles in (1, 3, 5):
            rows.append(
                {
                    "analysis_type": f"stop_within_{candles}_candles",
                    "variant": run["variant"],
                    "stop_count": stop_count_after_transitions(run["trades"], transitions, candles),
                }
            )
    return rows


def whipsaw_summary_for_run(run: dict, transitions: List[dict]) -> dict:
    total_pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in run["trades"])
    whipsaw_trades = trades_after_flagged_transitions(run["trades"], transitions, whipsaw_only=True)
    whipsaw_pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in whipsaw_trades)
    transition_trades = trades_after_flagged_transitions(run["trades"], transitions, whipsaw_only=False)
    transition_pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in transition_trades)
    rec_def_loss_count = recovery_defensive_loss_count(run["trades"], transitions)
    return {
        "transition_count": len(transitions),
        "whipsaw_transition_count": sum(1 for row in transitions if row.get("whipsaw")),
        "recovery_to_defensive_loss_count": rec_def_loss_count,
        "transition_trade_count": len(transition_trades),
        "transition_pnl_pct": transition_pnl * 100,
        "average_pnl_per_transition_pct": transition_pnl / len(transitions) * 100 if transitions else 0.0,
        "whipsaw_trade_count": len(whipsaw_trades),
        "whipsaw_pnl_pct": whipsaw_pnl * 100,
        "whipsaw_pnl_share_of_total_pct": whipsaw_pnl / total_pnl * 100 if total_pnl else 0.0,
    }


def build_report(summary_rows: List[dict], variant_rows: List[dict], recovery_rows: List[dict], whipsaw_rows: List[dict], regime_rows: List[dict]) -> str:
    base_variant_rows = [row for row in variant_rows if row["scenario"] == "base"]
    stress_rows = [row for row in variant_rows if row["scenario"] != "base"]
    lines = [
        "# Alpha Engine v1.2 4H Regime Focused Audit",
        "",
        "- 기존 V0/V4H comparison 로직은 수정하지 않고 별도 read-only audit 스크립트로 재계산했다.",
        "- 감사 대상: V4H_strict, recovery size 25/50, recovery 제거/제한 변형.",
        "- 비용 stress: fee 2x, slippage 2x, fee+slippage 2x, fee+slippage 3x.",
        "",
        "## PASS/WATCH/FAIL",
        "",
        markdown_table(
            ["Variant", "Status", "Reasons", "Return vs V0", "MDD extra", "2x cost+slip vs V0", "Whipsaw PnL"],
            summary_rows,
            ["variant", "audit_status", "audit_reasons", "total_return_vs_v0_pct_point", "mdd_extra_pct_point", "cost_2x_slippage_2x_return_vs_v0_pct_point", "whipsaw_pnl_pct"],
        ),
        "",
        "## Base Metrics",
        "",
        markdown_table(
            ["Variant", "Return", "CAGR", "MDD", "Sharpe", "Sortino", "Calmar", "PF", "Win", "Trades", "Max losses", "Avg R", "Median trade"],
            base_variant_rows,
            ["variant", "total_return_pct", "cagr_pct", "mdd_pct", "sharpe", "sortino", "calmar", "profit_factor", "win_rate_pct", "trade_count", "max_consecutive_losses", "average_r", "median_trade_return_pct"],
        ),
        "",
        "## Cost Stress",
        "",
        markdown_table(
            ["Variant", "Scenario", "Return", "CAGR", "MDD", "PF", "Trades"],
            stress_rows,
            ["variant", "scenario", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "trade_count"],
        ),
        "",
        "## Recovery Summary",
        "",
        markdown_table(
            ["Variant", "Trades", "PnL", "PF", "Win", "Max losses", "MDD contrib"],
            [row for row in recovery_rows if row.get("analysis_type") == "summary"],
            ["variant", "trade_count", "pnl_pct", "profit_factor", "win_rate_pct", "max_consecutive_losses", "mdd_contribution_pct"],
        ),
        "",
        "## Whipsaw Summary",
        "",
        markdown_table(
            ["Variant", "Transitions", "Whipsaw", "Rec->Def losses", "Stop 1", "Stop 3", "Stop 5", "Whipsaw PnL", "Whipsaw share"],
            [row for row in whipsaw_rows if row.get("analysis_type") == "summary"],
            ["variant", "transition_count", "whipsaw_transition_count", "recovery_to_defensive_loss_count", "stop_within_1_candles", "stop_within_3_candles", "stop_within_5_candles", "whipsaw_pnl_pct", "whipsaw_pnl_share_of_total_pct"],
        ),
        "",
        "## Regime Performance",
        "",
        markdown_table(
            ["Variant", "Regime", "Trades", "PnL", "PF", "Avg R", "MDD contrib"],
            [row for row in regime_rows if row["trade_count"]],
            ["variant", "regime", "trade_count", "pnl_pct", "profit_factor", "average_r", "mdd_contribution_pct"],
        ),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_2_4h_regime_audit.md`",
        "- `alpha_engine_v1_2_4h_regime_audit_summary.csv`",
        "- `alpha_engine_v1_2_4h_regime_audit_recovery_analysis.csv`",
        "- `alpha_engine_v1_2_4h_regime_audit_whipsaw_analysis.csv`",
        "- `alpha_engine_v1_2_4h_regime_audit_regime_performance.csv`",
        "- `alpha_engine_v1_2_4h_regime_audit_variant_comparison.csv`",
        "",
    ]
    return "\n".join(lines)


def score_percent(signal: dict) -> float:
    score = float(signal.get("alpha_score") or 0.0)
    return score * 10 if score <= 10 else score


def normalized_trade_regime(trade: dict) -> str:
    regime = str(trade.get("short_regime_4h") or trade.get("trade_regime") or "")
    if regime == "risk_off":
        return "risk_off"
    return regime


def empty_group_row(variant: str, regime: str) -> dict:
    return {
        "variant": variant,
        "regime": regime,
        "trade_count": 0,
        "pnl": 0.0,
        "pnl_pct": 0.0,
        "profit_factor": None,
        "average_r": None,
        "mdd_contribution": 0.0,
        "mdd_contribution_pct": 0.0,
    }


def trade_extreme_row(variant: str, analysis_type: str, trade: dict) -> dict:
    return {
        "analysis_type": analysis_type,
        "variant": variant,
        "symbol": trade.get("symbol"),
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "exit_reason": trade.get("exit_reason"),
        "pnl": trade.get("pnl_after_funding"),
        "trade_return_pct": trade.get("trade_return_after_funding_pct"),
        "alpha_score": trade.get("alpha_score"),
    }


def top_recovery_symbol_losses(variant: str, trades: List[dict], limit: int = 10) -> List[dict]:
    grouped: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for trade in trades:
        pnl = float(trade.get("pnl_after_funding") or 0.0)
        if pnl < 0:
            grouped[str(trade.get("symbol"))] += pnl
            counts[str(trade.get("symbol"))] += 1
    rows = []
    for symbol, pnl in sorted(grouped.items(), key=lambda item: item[1])[:limit]:
        rows.append({"analysis_type": "symbol_loss", "variant": variant, "symbol": symbol, "loss_count": counts[symbol], "pnl": pnl, "pnl_pct": pnl * 100})
    return rows


def top_recovery_period_losses(variant: str, trades: List[dict], limit: int = 10) -> List[dict]:
    grouped: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for trade in trades:
        pnl = float(trade.get("pnl_after_funding") or 0.0)
        if pnl < 0:
            period = str(trade.get("entry_date", ""))[:7]
            grouped[period] += pnl
            counts[period] += 1
    rows = []
    for period, pnl in sorted(grouped.items(), key=lambda item: item[1])[:limit]:
        rows.append({"analysis_type": "period_loss", "variant": variant, "period": period, "loss_count": counts[period], "pnl": pnl, "pnl_pct": pnl * 100})
    return rows


def group_mdd_contribution(trades: List[dict]) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for trade in sorted(trades, key=lambda item: int(item.get("exit_timestamp") or 0)):
        cumulative += float(trade.get("pnl_after_funding") or 0.0)
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def up_def_up_count(transitions: List[dict]) -> int:
    count = 0
    for index in range(len(transitions) - 1):
        current = transitions[index]
        nxt = transitions[index + 1]
        if current.get("from_regime") == "uptrend" and current.get("to_regime") == "defensive" and nxt.get("from_regime") == "defensive" and nxt.get("to_regime") == "uptrend":
            count += 1
    return count


def trades_after_flagged_transitions(trades: List[dict], transitions: List[dict], whipsaw_only: bool) -> List[dict]:
    windows = transition_windows(transitions, whipsaw_only=whipsaw_only)
    selected = []
    seen = set()
    for trade in trades:
        entry = int(trade.get("entry_timestamp") or 0)
        key = trade_key(trade)
        for start, end in windows:
            if start <= entry < end and key not in seen:
                selected.append(trade)
                seen.add(key)
                break
    return selected


def transition_windows(transitions: List[dict], whipsaw_only: bool = False) -> List[Tuple[int, int]]:
    rows = [row for row in transitions if row.get("whipsaw") or not whipsaw_only]
    windows = []
    for index, row in enumerate(rows):
        start = int(row.get("transition_time") or 0)
        end = int(rows[index + 1].get("transition_time") or start + 24 * 3600) if index + 1 < len(rows) else start + 24 * 3600
        windows.append((start, end))
    return windows


def recovery_defensive_loss_count(trades: List[dict], transitions: List[dict]) -> int:
    rec_def_times = [
        int(row.get("transition_time") or 0)
        for row in transitions
        if row.get("from_regime") == "recovery" and row.get("to_regime") == "defensive"
    ]
    count = 0
    for trade in trades:
        if normalized_trade_regime(trade) != "recovery" or float(trade.get("pnl_after_funding") or 0.0) >= 0:
            continue
        entry = int(trade.get("entry_timestamp") or 0)
        exit_time = int(trade.get("exit_timestamp") or 0)
        if any(entry <= transition_time <= exit_time for transition_time in rec_def_times):
            count += 1
    return count


def stop_count_after_transitions(trades: List[dict], transitions: List[dict], candles: int) -> int:
    window_seconds = candles * 4 * 3600
    seen = set()
    for transition in transitions:
        start = int(transition.get("transition_time") or 0)
        end = start + window_seconds
        for trade in trades:
            if trade.get("exit_reason") != "stop":
                continue
            entry = int(trade.get("entry_timestamp") or 0)
            if start <= entry <= end:
                seen.add(trade_key(trade))
    return len(seen)


def trade_key(trade: dict) -> str:
    return "|".join([str(trade.get("symbol", "")), str(trade.get("entry_timestamp", "")), str(trade.get("exit_timestamp", "")), str(trade.get("exit_reason", ""))])


def equity_returns(curve: List[dict]) -> List[float]:
    return [
        curve[index]["equity"] / curve[index - 1]["equity"] - 1
        for index in range(1, len(curve))
        if curve[index - 1]["equity"] > 0
    ]


def max_consecutive_losses(trades: List[dict]) -> int:
    max_count = 0
    current = 0
    for trade in sorted(trades, key=lambda item: int(item.get("exit_timestamp") or 0)):
        if float(trade.get("pnl_after_funding") or 0.0) < 0:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def r_multiple(trade: dict) -> Optional[float]:
    risk_pct = float(trade.get("risk_distance_pct") or 0.0) / 100
    initial_risk = float(trade.get("initial_units") or 0.0) * float(trade.get("entry_price") or 0.0) * risk_pct
    if initial_risk <= 0:
        return None
    return float(trade.get("pnl_after_funding") or 0.0) / initial_risk


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    return statistics.mean(clean) if clean else None


def markdown_table(headers: List[str], rows: List[dict], keys: List[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    percent_keys = {key for key in keys if key.endswith("_pct") or key.endswith("_pct_point") or "return" in key or "pnl" in key or "mdd" in key or "share" in key}
    for row in rows:
        lines.append("| " + " | ".join(format_value(row.get(key), percent=key in percent_keys) for key in keys) + " |")
    return "\n".join(lines)


def format_value(value, percent: bool = False) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    suffix = "%" if percent else ""
    return f"{float(value):.2f}{suffix}"


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
