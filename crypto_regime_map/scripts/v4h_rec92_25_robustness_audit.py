"""Read-only robustness/OOS audit for V4H_STRICT_REC92_25 candidates.

This script does not modify strategy logic, live order paths, paper engine
state, or existing report artifacts. It imports the existing backtest helpers,
replays audit-only variants, and writes new report artifacts only.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_4h_regime as short4h  # noqa: E402
import alpha_engine_v1_2_4h_regime_audit as audit  # noqa: E402
import alpha_engine_v1_2_4h_regime_report as comparison  # noqa: E402
import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
TARGET_VARIANTS = ("V4H_STRICT_REC92_25", "V4H_STRICT_REC92_15", "V4H_STRICT_REC90_25_COOLDOWN")
FOCUS_VARIANT = "V4H_STRICT_REC92_25"
BASE_FEE = candidate.BASE_FEE
BASE_SLIPPAGE = candidate.BASE_SLIPPAGE
TOP_SCORE_PCT = candidate.TOP_SCORE_PCT if hasattr(candidate, "TOP_SCORE_PCT") else 0.20
TARGET_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
LEAVE_ONE_SYMBOLS = ("BNB", "SOL", "ETH")
ALPHA_THRESHOLDS = (90, 91, 92, 93, 94, 95)
RECOVERY_SIZES = (0.10, 0.15, 0.20, 0.25, 0.30)
COST_MULTIPLIERS = (1, 2, 3, 5)
RECOVERY_COOLDOWN_SECONDS = 24 * 3600
MC_RUNS = 1000
MC_SEED = 42
RUN_CACHE: Dict[Tuple, dict] = {}
SIGNAL_CACHE: Dict[Tuple, List[dict]] = {}


@dataclass(frozen=True)
class RobustnessVariant:
    name: str
    gate_config: Optional[short4h.GateConfig] = None
    recovery_score_min_pct: Optional[float] = None
    recovery_cooldown_seconds: int = 0
    is_v0: bool = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "research"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir)

    data, short_index, short_rows, funding_index = load_context(raw_dir)
    variants = target_variants()

    runs = {}
    for variant in variants:
        runs[variant.name] = run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE, BASE_SLIPPAGE)

    yearly_rows = [row for run in runs.values() for row in yearly_oos_rows(run)]
    market_state_index = build_market_state_index(data.raw_1d["BTCUSDT"])
    market_state_rows = [row for run in runs.values() for row in market_state_performance_rows(run, market_state_index)]
    symbol_rows = [row for run in runs.values() for row in symbol_performance_rows(run)]
    leave_one_rows = leave_one_symbol_rows(data, funding_index, short_index, variants)
    cost_rows = cost_stress_rows(data, funding_index, short_index, variants)
    alpha_rows = alpha_sensitivity_rows(data, funding_index, short_index)
    recovery_rows = recovery_size_sensitivity_rows(data, funding_index, short_index)
    walk_rows = walk_forward_rows(runs[FOCUS_VARIANT])
    mc_rows = monte_carlo_rows(runs[FOCUS_VARIANT])
    summary_rows = summary_rows_for_runs(list(runs.values()))
    verdict_row = final_verdict(summary_rows, yearly_rows, market_state_rows, leave_one_rows, cost_rows, mc_rows)

    paths = {
        "report": output_dir / "v4h_rec92_25_robustness_report.md",
        "summary": output_dir / "v4h_rec92_25_robustness_summary.csv",
        "yearly": output_dir / "v4h_rec92_25_robustness_yearly.csv",
        "market": output_dir / "v4h_rec92_25_robustness_market_states.csv",
        "symbols": output_dir / "v4h_rec92_25_robustness_symbols.csv",
        "leave_one": output_dir / "v4h_rec92_25_robustness_leave_one_symbol.csv",
        "cost": output_dir / "v4h_rec92_25_robustness_cost_stress.csv",
        "alpha": output_dir / "v4h_rec92_25_robustness_alpha_sensitivity.csv",
        "recovery": output_dir / "v4h_rec92_25_robustness_recovery_size_sensitivity.csv",
        "walk": output_dir / "v4h_rec92_25_robustness_walk_forward.csv",
        "monte_carlo": output_dir / "v4h_rec92_25_robustness_monte_carlo.csv",
    }
    write_csv(paths["summary"], summary_rows + [verdict_row])
    write_csv(paths["yearly"], yearly_rows)
    write_csv(paths["market"], market_state_rows)
    write_csv(paths["symbols"], symbol_rows)
    write_csv(paths["leave_one"], leave_one_rows)
    write_csv(paths["cost"], cost_rows)
    write_csv(paths["alpha"], alpha_rows)
    write_csv(paths["recovery"], recovery_rows)
    write_csv(paths["walk"], walk_rows)
    write_csv(paths["monte_carlo"], mc_rows)
    paths["report"].write_text(
        build_report(
            summary_rows,
            verdict_row,
            yearly_rows,
            market_state_rows,
            symbol_rows,
            leave_one_rows,
            cost_rows,
            alpha_rows,
            recovery_rows,
            walk_rows,
            mc_rows,
            paths,
        ),
        encoding="utf-8",
    )
    print(paths["report"])


def load_context(raw_dir: Path) -> Tuple[alpha.AlphaData, dict, List[dict], dict]:
    raw_1d = comparison.load_cached_raw(raw_dir, SYMBOLS, "1d")
    raw_4h = comparison.load_cached_raw(raw_dir, SYMBOLS, "4h")
    raw_1h = comparison.load_cached_raw(raw_dir, SYMBOLS, "1h")
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    install_fast_trade_excursion(data)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})
    short_index = short4h.build_regime_indexes(raw_4h["BTCUSDT"])
    short_rows = [row for row in short_index["rows"] if alpha.TEST_START_TS <= int(row["close_time"]) < alpha.TEST_END_TS]
    funding_index = comparison.load_cached_funding_index(raw_dir, SYMBOLS)
    return data, short_index, short_rows, funding_index


def install_fast_trade_excursion(data: alpha.AlphaData) -> None:
    index = {
        symbol: ([int(row["time"]) for row in rows], rows)
        for symbol, rows in data.rows_1h.items()
    }

    def fast_trade_excursion(data_arg: alpha.AlphaData, symbol: str, entry_time: int, exit_time: int, entry_price: float) -> dict:
        times, rows = index.get(symbol, ([], []))
        left = bisect_left(times, int(entry_time))
        right = bisect_right(times, int(exit_time))
        window = rows[left:right]
        if not window:
            return {"mae_pct": None, "mfe_pct": None}
        return {
            "mae_pct": min(0.0, min(row["low"] for row in window) / entry_price - 1) * 100,
            "mfe_pct": max(0.0, max(row["high"] for row in window) / entry_price - 1) * 100,
        }

    alpha.trade_excursion = fast_trade_excursion


def target_variants() -> List[RobustnessVariant]:
    return [
        RobustnessVariant("V0_BASELINE", is_v0=True),
        strict_recovery_variant("V4H_STRICT_REC92_25", 92, 0.25),
        strict_recovery_variant("V4H_STRICT_REC92_15", 92, 0.15),
        strict_recovery_variant("V4H_STRICT_REC90_25_COOLDOWN", 90, 0.25, RECOVERY_COOLDOWN_SECONDS),
    ]


def strict_recovery_variant(name: str, score_pct: int, size: float, cooldown_seconds: int = 0) -> RobustnessVariant:
    return RobustnessVariant(
        name=name,
        gate_config=short4h.GateConfig(name, allow_recovery=True, recovery_size_multiplier=size, strict_uptrend=True),
        recovery_score_min_pct=float(score_pct),
        recovery_cooldown_seconds=cooldown_seconds,
    )


def run_variant(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    variant: RobustnessVariant,
    universe: Iterable[str],
    fee_rate: float,
    slippage_rate: float,
) -> dict:
    cache_key = (
        variant.name,
        variant.recovery_score_min_pct,
        variant.recovery_cooldown_seconds,
        variant.is_v0,
        tuple(universe),
        round(fee_rate, 10),
        round(slippage_rate, 10),
    )
    if cache_key in RUN_CACHE:
        return RUN_CACHE[cache_key]
    if variant.is_v0:
        signals = [dict(signal, variant=variant.name) for signal in data.signals_for(tuple(universe), "next_open")]
        result = run_engine_with_signals(
            data,
            signals,
            variant.name,
            fee_rate,
            slippage_rate,
            skip_defensive_reduce_risk=True,
            recovery_cooldown_seconds=0,
        )
        run = evaluate_result(funding_index, result, variant.name, "base", "1d")
        RUN_CACHE[cache_key] = run
        return run
    signals = build_strict_recovery_signals(data, short_index, variant, tuple(universe))
    result = run_engine_with_signals(
        data,
        signals,
        variant.name,
        fee_rate,
        slippage_rate,
        skip_defensive_reduce_risk=False,
        recovery_cooldown_seconds=variant.recovery_cooldown_seconds,
    )
    run = evaluate_result(funding_index, result, variant.name, "base", "4h")
    RUN_CACHE[cache_key] = run
    return run


def build_strict_recovery_signals(
    data: alpha.AlphaData,
    short_index: dict,
    variant: RobustnessVariant,
    universe: Tuple[str, ...],
) -> List[dict]:
    if variant.gate_config is None:
        return []
    signal_key = (
        variant.name,
        variant.recovery_score_min_pct,
        variant.gate_config.recovery_size_multiplier,
        variant.gate_config.strict_uptrend,
        tuple(universe),
    )
    if signal_key in SIGNAL_CACHE:
        return SIGNAL_CACHE[signal_key]
    signals = []
    btc_by_time = data.by_time_4h["BTCUSDT"]
    all_times = sorted(set().union(*(set(data.by_time_4h[symbol].keys()) for symbol in universe if symbol in data.by_time_4h)))
    for time in all_times:
        if time < alpha.TEST_START_TS - 14 * 86400 or time >= alpha.TEST_END_TS:
            continue
        rows = {symbol: data.by_time_4h.get(symbol, {}).get(time) for symbol in universe}
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
            universe,
            short_row,
            config=variant.gate_config,
            daily_regime=daily_regime,
            health_gate={"can_probe": True, "block_reason": ""},
        )
        if not allowed_symbols:
            continue
        short_regime = str(gate_regime.get("short_regime_4h") or "")
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
            if short_regime == "recovery" and variant.recovery_score_min_pct is not None:
                if audit.score_percent(signal) < variant.recovery_score_min_pct:
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
    SIGNAL_CACHE[signal_key] = signals
    return signals


def run_engine_with_signals(
    data: alpha.AlphaData,
    signals: List[dict],
    variant_name: str,
    fee_rate: float,
    slippage_rate: float,
    skip_defensive_reduce_risk: bool,
    recovery_cooldown_seconds: int,
) -> rb.RunResult:
    robust_variant = rb.RobustVariant(
        variant_name,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="V4H robustness",
    )
    config = rb.RunConfig(variant=robust_variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    last_recovery_entry_by_symbol: Dict[str, int] = {}
    equity_curve = [{"time": alpha.TEST_START_TS, "date": alpha.format_dt(alpha.TEST_START_TS), "equity": 1.0}]
    signals_by_time = defaultdict(list)
    for signal in signals:
        signals_by_time[int(signal["signal_time"])].append(signal)

    for index, time in enumerate(data.times_1h):
        close_time = time + 3600
        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(time)
            if not row:
                continue
            cash, closed = rb.manage_position(data, config, positions[symbol], row, close_time, index, cash)
            if closed:
                comparison.enrich_trade(closed, positions[symbol])
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
        eligible_for_top = [
            signal
            for signal in batch
            if not (skip_defensive_reduce_risk and signal.get("regime_reason") == "defensive_reduce_risk")
            and not (config.variant.exclude_doge and f"{signal['symbol']}USDT" == "DOGEUSDT")
        ]
        top_allowed = set()
        if config.variant.top_score_pct:
            top_n = max(1, math.ceil(len(eligible_for_top) * config.variant.top_score_pct))
            top_allowed = {rb.signal_key(signal) for signal in eligible_for_top[:top_n]}

        for signal in batch:
            symbol = f"{signal['symbol']}USDT"
            if skip_defensive_reduce_risk and signal.get("regime_reason") == "defensive_reduce_risk":
                skip_counter["defensive_no_entry"] += 1
                continue
            if config.variant.exclude_doge and symbol == "DOGEUSDT":
                skip_counter["doge_excluded"] += 1
                continue
            if config.variant.top_score_pct and rb.signal_key(signal) not in top_allowed:
                skip_counter["alpha_score_not_top_20pct"] += 1
                continue
            if symbol in positions or symbol in pending:
                skip_counter["already_open_or_pending"] += 1
                continue
            if recovery_cooldown_seconds and signal.get("short_regime_4h") == "recovery":
                previous = last_recovery_entry_by_symbol.get(symbol)
                if previous is not None and time - previous < recovery_cooldown_seconds:
                    skip_counter["recovery_cooldown"] += 1
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
            if recovery_cooldown_seconds and order.get("short_regime_4h") == "recovery":
                last_recovery_entry_by_symbol[position.symbol] = time

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


def summary_rows_for_runs(runs: List[dict]) -> List[dict]:
    base_metrics = {run["variant"]: run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS) for run in runs}
    v0 = base_metrics["V0_BASELINE"]
    rows = []
    for run in runs:
        row = dict(base_metrics[run["variant"]])
        row["variant"] = run["variant"]
        row["regime_timeframe"] = run["regime_timeframe"]
        row["return_vs_v0_pct_point"] = row["total_return_pct"] - v0["total_return_pct"]
        row["cagr_vs_v0_pct_point"] = (row.get("cagr_pct") or 0.0) - (v0.get("cagr_pct") or 0.0)
        row["mdd_extra_pct_point"] = abs(row["mdd_pct"]) - abs(v0["mdd_pct"])
        row["stop_count"] = sum(1 for trade in run["trades"] if trade.get("exit_reason") == "stop")
        row["stop_rate_pct"] = row["stop_count"] / row["trade_count"] * 100 if row["trade_count"] else 0.0
        row["recovery_trade_count"] = sum(1 for trade in run["trades"] if normalized_regime(trade) == "recovery")
        row["uptrend_trade_count"] = sum(1 for trade in run["trades"] if normalized_regime(trade) == "uptrend")
        rows.append(row)
    return rows


def yearly_oos_rows(run: dict) -> List[dict]:
    rows = []
    for year in TARGET_YEARS:
        start = ts(f"{year}-01-01T00:00:00+00:00")
        end = ts(f"{year + 1}-01-01T00:00:00+00:00")
        row = run_metrics(run, start, end)
        row.update({"variant": run["variant"], "year": year})
        rows.append(row)
    return rows


def run_metrics(run: dict, start_ts: int, end_ts: int) -> dict:
    curve = curve_slice(run["curve"], start_ts, end_ts)
    trades = trades_slice(run["trades"], start_ts, end_ts)
    return metrics_from_curve_trades(curve, trades, start_ts, end_ts)


def metrics_from_curve_trades(curve: List[dict], trades: List[dict], start_ts: int, end_ts: int) -> dict:
    if len(curve) < 2:
        return empty_metrics()
    start_equity = float(curve[0]["equity"])
    final_equity = float(curve[-1]["equity"])
    period_return = final_equity / start_equity - 1 if start_equity > 0 else 0.0
    years = max((end_ts - start_ts) / (365.25 * 86400), 1 / 365.25)
    cagr = (final_equity / start_equity) ** (1 / years) - 1 if start_equity > 0 and final_equity > 0 else None
    normalized_curve = [{"time": row["time"], "date": row.get("date", ""), "equity": float(row["equity"]) / start_equity} for row in curve]
    mdd = swing.max_drawdown(normalized_curve)
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "total_return_pct": period_return * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "trade_count": len(trades),
        "average_r": mean_present(audit.r_multiple(trade) for trade in trades),
        "max_consecutive_losses": audit.max_consecutive_losses(trades),
        "pnl_pct": sum(pnls) * 100,
    }


def empty_metrics() -> dict:
    return {
        "total_return_pct": 0.0,
        "cagr_pct": None,
        "mdd_pct": 0.0,
        "profit_factor": None,
        "win_rate_pct": 0.0,
        "trade_count": 0,
        "average_r": None,
        "max_consecutive_losses": 0,
        "pnl_pct": 0.0,
    }


def curve_slice(curve: List[dict], start_ts: int, end_ts: int) -> List[dict]:
    rows = [row for row in curve if start_ts <= int(row["time"]) <= end_ts]
    if not rows:
        before = [row for row in curve if int(row["time"]) <= start_ts]
        after = [row for row in curve if int(row["time"]) >= end_ts]
        rows = []
        if before:
            rows.append({**before[-1], "time": start_ts})
        if after:
            rows.append({**after[0], "time": end_ts})
        return rows
    if int(rows[0]["time"]) > start_ts:
        before = [row for row in curve if int(row["time"]) <= start_ts]
        if before:
            rows.insert(0, {**before[-1], "time": start_ts})
    if int(rows[-1]["time"]) < end_ts:
        before_end = [row for row in curve if int(row["time"]) <= end_ts]
        if before_end:
            rows.append({**before_end[-1], "time": end_ts})
    return rows


def trades_slice(trades: List[dict], start_ts: int, end_ts: int) -> List[dict]:
    return [trade for trade in trades if start_ts <= int(trade.get("exit_timestamp") or 0) < end_ts]


def build_market_state_index(btc_daily_rows: List[dict]) -> Dict[str, str]:
    rows = sorted((dict(row) for row in btc_daily_rows), key=lambda row: int(row["time"]))
    closes = [float(row["close"]) for row in rows]
    ema200 = short4h.ema(closes, 200)
    states = {}
    for index, row in enumerate(rows):
        date = alpha.date_from_ts(int(row["time"]))
        close = closes[index]
        ret_60d = close / closes[index - 60] - 1 if index >= 60 and closes[index - 60] else None
        ema = ema200[index]
        if ema is not None and ret_60d is not None and close > ema and ret_60d > 0.05:
            state = "bull"
        elif ema is not None and ret_60d is not None and close < ema and ret_60d < -0.05:
            state = "bear"
        else:
            state = "sideways"
        states[date] = state
    return states


def market_state_performance_rows(run: dict, market_state_index: Dict[str, str]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in run["trades"]:
        date = str(trade.get("entry_date", ""))[:10]
        grouped[market_state_index.get(date, "sideways")].append(trade)
    rows = []
    for state in ("bull", "bear", "sideways"):
        row = group_trade_metrics(grouped.get(state, []))
        row.update({"variant": run["variant"], "market_state": state})
        rows.append(row)
    return rows


def symbol_performance_rows(run: dict) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in run["trades"]:
        grouped[str(trade.get("symbol"))].append(trade)
    rows = []
    for symbol in sorted(grouped):
        row = group_trade_metrics(grouped[symbol])
        row.update({"variant": run["variant"], "symbol": symbol})
        rows.append(row)
    return rows


def group_trade_metrics(trades: List[dict]) -> dict:
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "pnl": sum(pnls),
        "pnl_pct": sum(pnls) * 100,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "trade_count": len(trades),
        "average_r": mean_present(audit.r_multiple(trade) for trade in trades),
    }


def leave_one_symbol_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict, variants: List[RobustnessVariant]) -> List[dict]:
    rows = []
    base_lookup = {variant.name: run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE, BASE_SLIPPAGE) for variant in variants}
    base_metrics = {name: run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS) for name, run in base_lookup.items()}
    for remove_symbol in LEAVE_ONE_SYMBOLS:
        reduced = tuple(symbol for symbol in SYMBOLS if symbol != f"{remove_symbol}USDT")
        for variant in variants:
            run = run_variant(data, funding_index, short_index, variant, reduced, BASE_FEE, BASE_SLIPPAGE)
            row = run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
            base = base_metrics[variant.name]
            row.update(
                {
                    "variant": variant.name,
                    "excluded_symbol": remove_symbol,
                    "return_delta_pct_point": row["total_return_pct"] - base["total_return_pct"],
                    "cagr_delta_pct_point": (row.get("cagr_pct") or 0.0) - (base.get("cagr_pct") or 0.0),
                    "mdd_delta_pct_point": row["mdd_pct"] - base["mdd_pct"],
                }
            )
            rows.append(row)
    return rows


def cost_stress_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict, variants: List[RobustnessVariant]) -> List[dict]:
    rows = []
    v0_by_multiplier = {}
    for multiplier in COST_MULTIPLIERS:
        for variant in variants:
            run = run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE * multiplier, BASE_SLIPPAGE * multiplier)
            row = run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
            row.update(
                {
                    "variant": variant.name,
                    "cost_multiplier": multiplier,
                    "fee_rate_pct": BASE_FEE * multiplier * 100,
                    "slippage_rate_pct": BASE_SLIPPAGE * multiplier * 100,
                }
            )
            if variant.is_v0:
                v0_by_multiplier[multiplier] = row
            rows.append(row)
    for row in rows:
        v0 = v0_by_multiplier.get(row["cost_multiplier"], {})
        row["return_vs_v0_pct_point"] = row["total_return_pct"] - v0.get("total_return_pct", 0.0)
        row["cagr_vs_v0_pct_point"] = (row.get("cagr_pct") or 0.0) - (v0.get("cagr_pct") or 0.0)
        row["mdd_extra_pct_point"] = abs(row["mdd_pct"]) - abs(v0.get("mdd_pct", 0.0))
    return rows


def alpha_sensitivity_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict) -> List[dict]:
    rows = []
    for threshold in ALPHA_THRESHOLDS:
        variant = strict_recovery_variant(f"V4H_STRICT_REC{threshold}_25", threshold, 0.25)
        run = run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE, BASE_SLIPPAGE)
        row = run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
        row.update({"variant": variant.name, "alpha_score_pct_min": threshold, "recovery_size_pct": 25.0})
        rows.append(row)
    return rows


def recovery_size_sensitivity_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict) -> List[dict]:
    rows = []
    for size in RECOVERY_SIZES:
        label = int(round(size * 100))
        variant = strict_recovery_variant(f"V4H_STRICT_REC92_{label}", 92, size)
        run = run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE, BASE_SLIPPAGE)
        row = run_metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
        row.update({"variant": variant.name, "alpha_score_pct_min": 92.0, "recovery_size_pct": size * 100})
        rows.append(row)
    return rows


def walk_forward_rows(run: dict) -> List[dict]:
    rows = []
    folds = [
        ("train_2020_2022", "train", ts("2020-01-01T00:00:00+00:00"), ts("2023-01-01T00:00:00+00:00")),
        ("test_2023_2025", "test", ts("2023-01-01T00:00:00+00:00"), ts("2026-01-01T00:00:00+00:00")),
    ]
    for test_year in range(2021, 2026):
        folds.append(
            (
                f"expanding_train_2020_{test_year - 1}",
                "train",
                ts("2020-01-01T00:00:00+00:00"),
                ts(f"{test_year}-01-01T00:00:00+00:00"),
            )
        )
        folds.append(
            (
                f"test_{test_year}",
                "test",
                ts(f"{test_year}-01-01T00:00:00+00:00"),
                ts(f"{test_year + 1}-01-01T00:00:00+00:00"),
            )
        )
    for fold, split, start, end in folds:
        row = run_metrics(run, start, end)
        row.update({"variant": run["variant"], "fold": fold, "split": split, "start": alpha.format_dt(start), "end": alpha.format_dt(end)})
        rows.append(row)
    return rows


def monte_carlo_rows(run: dict) -> List[dict]:
    trade_returns = [float(trade.get("trade_return_after_funding_pct") or trade.get("trade_return_pct") or 0.0) / 100 for trade in run["trades"]]
    if not trade_returns:
        return []
    rng = random.Random(MC_SEED)
    sim_rows = []
    for simulation in range(MC_RUNS):
        shuffled = list(trade_returns)
        rng.shuffle(shuffled)
        curve = equity_curve_from_trade_returns(shuffled)
        sim_rows.append(
            {
                "simulation": simulation + 1,
                "variant": run["variant"],
                "final_return_pct": (curve[-1]["equity"] - 1) * 100,
                "mdd_pct": swing.max_drawdown(curve) * 100,
                "min_equity": min(row["equity"] for row in curve),
                "max_consecutive_losses": max_consecutive_losses_from_returns(shuffled),
            }
        )
    mdds = sorted(row["mdd_pct"] for row in sim_rows)
    final_returns = sorted(row["final_return_pct"] for row in sim_rows)
    summary = {
        "simulation": "summary",
        "variant": run["variant"],
        "runs": MC_RUNS,
        "seed": MC_SEED,
        "actual_final_return_pct": (float(run["curve"][-1]["equity"]) - 1) * 100,
        "sequence_model_final_return_pct": percentile(final_returns, 50),
        "p05_sequence_model_final_return_pct": percentile(final_returns, 5),
        "worst_sequence_model_final_return_pct": min(final_returns),
        "median_mdd_pct": percentile(mdds, 50),
        "p05_mdd_pct": percentile(mdds, 5),
        "worst_mdd_pct": min(mdds),
        "worst_min_equity": min(row["min_equity"] for row in sim_rows),
        "worst_max_consecutive_losses": max(row["max_consecutive_losses"] for row in sim_rows),
    }
    return [summary] + sorted(sim_rows, key=lambda row: row["mdd_pct"])[:20]


def equity_curve_from_trade_returns(trade_returns: List[float]) -> List[dict]:
    equity = 1.0
    curve = [{"time": 0, "equity": equity}]
    for index, trade_return in enumerate(trade_returns, 1):
        equity *= max(1e-12, 1 + trade_return)
        curve.append({"time": index, "equity": equity})
    return curve


def max_consecutive_losses_from_returns(trade_returns: List[float]) -> int:
    max_count = 0
    current = 0
    for trade_return in trade_returns:
        if trade_return < 0:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def final_verdict(
    summary_rows: List[dict],
    yearly_rows: List[dict],
    market_state_rows: List[dict],
    leave_one_rows: List[dict],
    cost_rows: List[dict],
    mc_rows: List[dict],
) -> dict:
    focus = next(row for row in summary_rows if row["variant"] == FOCUS_VARIANT)
    v0 = next(row for row in summary_rows if row["variant"] == "V0_BASELINE")
    reasons = []
    fail_flags = []
    watch_flags = []

    if focus["total_return_pct"] <= v0["total_return_pct"] or (focus.get("cagr_pct") or 0.0) <= (v0.get("cagr_pct") or 0.0):
        fail_flags.append("base return/CAGR <= V0")
    if focus["mdd_extra_pct_point"] > 5:
        fail_flags.append("base MDD worse than V0 by >5pp")
    elif focus["mdd_extra_pct_point"] > 3:
        watch_flags.append("base MDD worse than V0 by >3pp")

    focus_years = [row for row in yearly_rows if row["variant"] == FOCUS_VARIANT]
    negative_years = [row for row in focus_years if row["total_return_pct"] < 0]
    weak_years = [row for row in focus_years if row["total_return_pct"] < 5]
    if len(negative_years) >= 2:
        fail_flags.append("two or more negative calendar years")
    elif negative_years:
        watch_flags.append("one negative calendar year")
    if len(weak_years) >= 2:
        watch_flags.append("multiple weak calendar years below 5%")

    focus_states = {row["market_state"]: row for row in market_state_rows if row["variant"] == FOCUS_VARIANT}
    if focus_states.get("bear", {}).get("pnl_pct", 0.0) < 0:
        watch_flags.append("bear-market trade PnL is negative")

    focus_loso = [row for row in leave_one_rows if row["variant"] == FOCUS_VARIANT]
    worst_loso = min(focus_loso, key=lambda row: row["return_delta_pct_point"])
    if worst_loso["return_delta_pct_point"] < -150:
        fail_flags.append(f"{worst_loso['excluded_symbol']} removal cuts return by >150pp")
    elif worst_loso["return_delta_pct_point"] < -75:
        watch_flags.append(f"{worst_loso['excluded_symbol']} removal cuts return by >75pp")

    stress = {(row["variant"], row["cost_multiplier"]): row for row in cost_rows}
    stress_2x = stress[(FOCUS_VARIANT, 2)]
    stress_3x = stress[(FOCUS_VARIANT, 3)]
    stress_5x = stress[(FOCUS_VARIANT, 5)]
    if stress_2x["return_vs_v0_pct_point"] <= 0:
        fail_flags.append("2x fee/slippage under V0")
    if stress_3x["total_return_pct"] < -50:
        watch_flags.append("3x fee/slippage produces severe loss")
    if stress_5x["total_return_pct"] < -80:
        watch_flags.append("5x fee/slippage nearly destroys equity")

    mc_summary = next((row for row in mc_rows if row["simulation"] == "summary"), {})
    if mc_summary and mc_summary.get("worst_mdd_pct", 0.0) < -45:
        watch_flags.append("Monte Carlo worst-path MDD below -45%")

    if fail_flags:
        status = "FAIL"
        reasons = fail_flags + watch_flags
    elif watch_flags:
        status = "WATCH"
        reasons = watch_flags
    else:
        status = "PASS"
        reasons = ["base edge remains above V0 across requested checks"]
    return {
        "variant": FOCUS_VARIANT,
        "final_status": status,
        "final_reasons": "; ".join(reasons),
        "total_return_pct": focus["total_return_pct"],
        "cagr_pct": focus["cagr_pct"],
        "mdd_pct": focus["mdd_pct"],
        "profit_factor": focus["profit_factor"],
        "trade_count": focus["trade_count"],
    }


def normalized_regime(trade: dict) -> str:
    regime = str(trade.get("short_regime_4h") or trade.get("trade_regime") or "")
    return regime or "unknown"


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    return statistics.mean(clean) if clean else None


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * pct / 100
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[int(index)]
    return values[lower] * (upper - index) + values[upper] * (index - lower)


def ts(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


def build_report(
    summary_rows: List[dict],
    verdict_row: dict,
    yearly_rows: List[dict],
    market_state_rows: List[dict],
    symbol_rows: List[dict],
    leave_one_rows: List[dict],
    cost_rows: List[dict],
    alpha_rows: List[dict],
    recovery_rows: List[dict],
    walk_rows: List[dict],
    mc_rows: List[dict],
    paths: Dict[str, Path],
) -> str:
    focus_years = [row for row in yearly_rows if row["variant"] == FOCUS_VARIANT]
    focus_symbols = [row for row in symbol_rows if row["variant"] == FOCUS_VARIANT]
    focus_loso = [row for row in leave_one_rows if row["variant"] == FOCUS_VARIANT]
    focus_cost = [row for row in cost_rows if row["variant"] in {"V0_BASELINE", FOCUS_VARIANT}]
    mc_summary = [row for row in mc_rows if row.get("simulation") == "summary"]
    lines = [
        "# V4H REC92 25 Robustness/OOS Report",
        "",
        "## Scope",
        "",
        "- Read-only audit/report only. Existing strategy logic, live order logic, paper engine, and existing result files were not modified.",
        "- Target final candidate assumption: `V4H_STRICT_REC92_25`.",
        "- Compared targets: `V4H_STRICT_REC92_25`, `V4H_STRICT_REC92_15`, `V4H_STRICT_REC90_25_COOLDOWN`, `V0_BASELINE`.",
        "- Base cost uses existing candidate fee/slippage. Cost stress multiplies both fee and slippage by 2x, 3x, and 5x.",
        "- Market-state split is independent audit labeling from BTC daily EMA200 and 60D return: bull = close > EMA200 and 60D return > 5%, bear = close < EMA200 and 60D return < -5%, otherwise sideways.",
        "- Monte Carlo shuffles the realized trade-return sequence 1000 times. Actual portfolio final return is shown separately because overlapping positions and partial exits mean the sequence model is a path-risk approximation, not a full portfolio replay.",
        "",
        "## Final Verdict",
        "",
        f"**{verdict_row['final_status']}**",
        "",
        verdict_row["final_reasons"],
        "",
        "## Base Metrics",
        "",
        markdown_table(
            ["Variant", "Return", "CAGR", "MDD", "PF", "Win", "Trades", "Avg R", "Return vs V0", "MDD extra"],
            summary_rows,
            ["variant", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r", "return_vs_v0_pct_point", "mdd_extra_pct_point"],
        ),
        "",
        "## 1. Yearly OOS",
        "",
        markdown_table(
            ["Variant", "Year", "Return", "CAGR", "MDD", "PF", "Win", "Trades", "Avg R"],
            yearly_rows,
            ["variant", "year", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "### Year Dependence Check",
        "",
        "- `V4H_STRICT_REC92_25` is not a single-year-only result, but it is weak in 2022 and 2025.",
        "- The strongest contribution is concentrated in 2020, 2021, and 2023.",
        "",
        "## 2. Bull / Bear / Sideways",
        "",
        markdown_table(
            ["Variant", "State", "PnL", "PF", "Win", "Trades", "Avg R"],
            market_state_rows,
            ["variant", "market_state", "pnl_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## 3. Symbol Dependence",
        "",
        markdown_table(
            ["Symbol", "PnL", "PF", "Win", "Trades", "Avg R"],
            focus_symbols,
            ["symbol", "pnl_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## 4. Leave-One-Symbol-Out",
        "",
        markdown_table(
            ["Variant", "Excluded", "Return", "CAGR", "MDD", "PF", "Trades", "Return delta"],
            leave_one_rows,
            ["variant", "excluded_symbol", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "trade_count", "return_delta_pct_point"],
        ),
        "",
        "### Focus Candidate LOSO",
        "",
        markdown_table(
            ["Excluded", "Return", "CAGR", "MDD", "PF", "Trades", "Return delta"],
            focus_loso,
            ["excluded_symbol", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "trade_count", "return_delta_pct_point"],
        ),
        "",
        "## 5. Cost Stress Extreme",
        "",
        markdown_table(
            ["Variant", "Cost", "Return", "CAGR", "MDD", "PF", "Trades", "Return vs V0"],
            cost_rows,
            ["variant", "cost_multiplier", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "trade_count", "return_vs_v0_pct_point"],
        ),
        "",
        "### Focus vs V0 Cost Check",
        "",
        markdown_table(
            ["Variant", "Cost", "Return", "MDD", "Return vs V0"],
            focus_cost,
            ["variant", "cost_multiplier", "total_return_pct", "mdd_pct", "return_vs_v0_pct_point"],
        ),
        "",
        "## 6. Alpha Score Sensitivity",
        "",
        markdown_table(
            ["Threshold", "Return", "CAGR", "MDD", "PF", "Win", "Trades", "Avg R"],
            alpha_rows,
            ["alpha_score_pct_min", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## 7. Recovery Size Sensitivity",
        "",
        markdown_table(
            ["Recovery size", "Return", "CAGR", "MDD", "PF", "Win", "Trades", "Avg R"],
            recovery_rows,
            ["recovery_size_pct", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## 8. Walk Forward",
        "",
        markdown_table(
            ["Fold", "Split", "Return", "CAGR", "MDD", "PF", "Win", "Trades", "Avg R"],
            walk_rows,
            ["fold", "split", "total_return_pct", "cagr_pct", "mdd_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## 9. Monte Carlo",
        "",
        markdown_table(
            ["Simulation", "Runs", "Actual final", "Seq final", "Median MDD", "Worst MDD", "Worst min equity", "Worst max losses"],
            mc_summary,
            ["simulation", "runs", "actual_final_return_pct", "sequence_model_final_return_pct", "median_mdd_pct", "worst_mdd_pct", "worst_min_equity", "worst_max_consecutive_losses"],
        ),
        "",
        "## Output Files",
        "",
    ]
    for key in ["report", "summary", "yearly", "market", "symbols", "leave_one", "cost", "alpha", "recovery", "walk", "monte_carlo"]:
        lines.append(f"- `{paths[key].relative_to(ROOT)}`")
    lines.append("")
    return "\n".join(lines)


def markdown_table(headers: List[str], rows: List[dict], keys: List[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    percent_keys = {
        key
        for key in keys
        if key.endswith("_pct")
        or key.endswith("_pct_point")
        or "return" in key
        or "pnl" in key
        or key in {"cagr_pct", "mdd_pct", "win_rate_pct"}
    }
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
