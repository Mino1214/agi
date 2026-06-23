"""Read-only Core/Satellite audit for V4H recovery variants.

The script reuses existing backtest helpers and writes research artifacts only.
It does not modify strategy, paper, live, cache, or state logic.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict, deque
import csv
from dataclasses import dataclass
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_4h_regime as short4h  # noqa: E402
import alpha_engine_v1_2_4h_regime_report as comparison  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import v4h_rec92_25_robustness_audit as rec92_audit  # noqa: E402
import v4h_symbol_specific_recovery_audit as symbol_audit  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
CORE_SYMBOLS = tuple(symbol for symbol in SYMBOLS if symbol not in {"SOLUSDT", "BNBUSDT"})
SATELLITE_SYMBOLS = ("SOLUSDT", "BNBUSDT")
BASE_FEE = rec92_audit.BASE_FEE
BASE_SLIPPAGE = rec92_audit.BASE_SLIPPAGE
TOP_SCORE_PCT = rec92_audit.TOP_SCORE_PCT
TARGET_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
CORE_THRESHOLDS = (90, 92, 94)
CORE_SIZES = (0.10, 0.15, 0.25)
SAT_THRESHOLDS = (92, 94, 95)
SAT_SIZES = (0.05, 0.10, 0.15, 0.25)
SAT_COOLDOWNS = (0, 48 * 3600, 72 * 3600)
SAT_ALLOCATIONS = (0.10, 0.15, 0.20, 0.25)
PAUSE_RULES = ("none", "rolling_30d_dd", "monthly_loss")
COST_MULTIPLIERS = (1, 2, 3, 5)
ROLLING_DD_SECONDS = 30 * 86400
ROLLING_DD_PAUSE = -0.10
MONTHLY_LOSS_PAUSE = -0.08

SAT_RUN_CACHE: Dict[Tuple, dict] = {}


@dataclass(frozen=True)
class CoreSpec:
    threshold: int
    size: float

    @property
    def name(self) -> str:
        return f"CORE_NO_SOL_BNB_REC{self.threshold}_{int(round(self.size * 100)):02d}"


@dataclass(frozen=True)
class SatelliteSpec:
    threshold: int
    size: float
    cooldown_seconds: int

    @property
    def cooldown_label(self) -> str:
        return "NONE" if self.cooldown_seconds == 0 else f"{int(self.cooldown_seconds / 3600)}H"

    @property
    def name(self) -> str:
        return f"SAT_SOL_BNB_REC{self.threshold}_{int(round(self.size * 100)):02d}_CD{self.cooldown_label}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "research"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data, short_index, _short_rows, funding_index = rec92_audit.load_context(Path(args.raw_dir))
    market_state_index = rec92_audit.build_market_state_index(data.raw_1d["BTCUSDT"])

    baseline_runs = build_baseline_runs(data, funding_index, short_index)
    baseline_rows = [summary_row_for_run(run, "comparison") for run in baseline_runs.values()]
    v0_metrics = metrics(baseline_runs["V0_BASELINE"], alpha.TEST_START_TS, alpha.TEST_END_TS)
    original_metrics = metrics(baseline_runs["V4H_REC92_25_ORIGINAL"], alpha.TEST_START_TS, alpha.TEST_END_TS)

    core_specs = [CoreSpec(threshold, size) for threshold in CORE_THRESHOLDS for size in CORE_SIZES]
    sat_specs = [SatelliteSpec(threshold, size, cooldown) for threshold in SAT_THRESHOLDS for size in SAT_SIZES for cooldown in SAT_COOLDOWNS]

    core_runs = {
        spec.name: run_core(data, funding_index, short_index, spec, BASE_FEE, BASE_SLIPPAGE)
        for spec in core_specs
    }
    core_rows = build_core_rows(core_specs, core_runs, v0_metrics)
    selected_core_specs = shortlist_core_specs(core_rows, core_specs)
    best_core_row = max(core_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]))
    best_core_run = core_runs[best_core_row["variant"]]

    sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict] = {}
    for index, spec in enumerate(sat_specs, start=1):
        print(f"satellite no-pause full grid {index}/{len(sat_specs)} {spec.name}", file=sys.stderr)
        sat_runs[(spec.name, "none", SATELLITE_SYMBOLS)] = run_satellite(
            data,
            funding_index,
            short_index,
            spec,
            "none",
            SATELLITE_SYMBOLS,
            BASE_FEE,
            BASE_SLIPPAGE,
        )
    satellite_rows = build_satellite_rows(sat_specs, sat_runs, v0_metrics)
    selected_sat_specs = shortlist_satellite_specs(satellite_rows, sat_specs)
    for index, spec in enumerate(selected_sat_specs, start=1):
        print(f"satellite selected pause/leave {index}/{len(selected_sat_specs)} {spec.name}", file=sys.stderr)
        for pause_rule in PAUSE_RULES:
            for universe in (SATELLITE_SYMBOLS, ("SOLUSDT",), ("BNBUSDT",)):
                key = (spec.name, pause_rule, tuple(universe))
                if key not in sat_runs:
                    sat_runs[key] = run_satellite(
                        data,
                        funding_index,
                        short_index,
                        spec,
                        pause_rule,
                        tuple(universe),
                        BASE_FEE,
                        BASE_SLIPPAGE,
                    )
    satellite_rows = build_satellite_rows(sat_specs, sat_runs, v0_metrics)

    original_no_solbnb = run_original_no_solbnb(data, funding_index, short_index)
    original_solbnb_impact = metrics(original_no_solbnb, alpha.TEST_START_TS, alpha.TEST_END_TS)["total_return_pct"] - original_metrics["total_return_pct"]

    combined_rows, combined_context = build_combined_rows(
        selected_core_specs,
        core_runs,
        selected_sat_specs,
        sat_runs,
        v0_metrics,
        original_solbnb_impact,
    )
    shortlisted = shortlist_combined_rows(combined_rows)
    cost_rows = build_cost_rows(
        data,
        funding_index,
        short_index,
        baseline_runs,
        selected_core_specs,
        selected_sat_specs,
        shortlisted,
    )
    cost_lookup = {(row["variant"], row["cost_multiplier"]): row for row in cost_rows}
    yearly_rows = build_yearly_rows(baseline_runs, core_runs, sat_runs, combined_context, shortlisted)
    regime_rows = build_regime_rows(baseline_runs, core_runs, sat_runs, combined_context, shortlisted, market_state_index)
    symbol_rows = build_symbol_rows(baseline_runs, core_runs, sat_runs, combined_context, shortlisted)

    summary_rows = build_summary_rows(
        baseline_rows,
        core_rows,
        satellite_rows,
        combined_rows,
        shortlisted,
        cost_lookup,
        yearly_rows,
        v0_metrics,
        original_metrics,
        original_solbnb_impact,
        best_core_row,
    )

    paths = {
        "report": output_dir / "v4h_core_satellite_report.md",
        "summary": output_dir / "v4h_core_satellite_summary.csv",
        "core": output_dir / "v4h_core_satellite_core_only.csv",
        "satellite": output_dir / "v4h_core_satellite_satellite_only.csv",
        "combined": output_dir / "v4h_core_satellite_combined.csv",
        "cost": output_dir / "v4h_core_satellite_cost_stress.csv",
        "yearly": output_dir / "v4h_core_satellite_oos_yearly.csv",
        "regime": output_dir / "v4h_core_satellite_regime_performance.csv",
        "symbols": output_dir / "v4h_core_satellite_symbol_contribution.csv",
    }
    write_csv(paths["summary"], summary_rows)
    write_csv(paths["core"], core_rows)
    write_csv(paths["satellite"], satellite_rows)
    write_csv(paths["combined"], combined_rows)
    write_csv(paths["cost"], cost_rows)
    write_csv(paths["yearly"], yearly_rows)
    write_csv(paths["regime"], regime_rows)
    write_csv(paths["symbols"], symbol_rows)
    paths["report"].write_text(
        build_report(summary_rows, core_rows, satellite_rows, combined_rows, cost_rows, yearly_rows, regime_rows, symbol_rows, paths),
        encoding="utf-8",
    )
    print(paths["report"])


def build_baseline_runs(data: alpha.AlphaData, funding_index: dict, short_index: dict) -> Dict[str, dict]:
    runs = {}
    runs["V0_BASELINE"] = rec92_audit.run_variant(
        data,
        funding_index,
        short_index,
        rec92_audit.RobustnessVariant("V0_BASELINE", is_v0=True),
        SYMBOLS,
        BASE_FEE,
        BASE_SLIPPAGE,
    )
    strict_base = rec92_audit.RobustnessVariant(
        "V4H_STRICT_BASE",
        gate_config=short4h.GateConfig("V4H_STRICT_BASE", allow_recovery=False, recovery_size_multiplier=0.0, strict_uptrend=True),
    )
    runs["V4H_STRICT_BASE"] = rec92_audit.run_variant(data, funding_index, short_index, strict_base, SYMBOLS, BASE_FEE, BASE_SLIPPAGE)
    runs["V4H_REC92_25_ORIGINAL"] = rec92_audit.run_variant(
        data,
        funding_index,
        short_index,
        rec92_audit.strict_recovery_variant("V4H_REC92_25_ORIGINAL", 92, 0.25),
        SYMBOLS,
        BASE_FEE,
        BASE_SLIPPAGE,
    )
    runs["V4H_REC92_15_ALL"] = rec92_audit.run_variant(
        data,
        funding_index,
        short_index,
        rec92_audit.strict_recovery_variant("V4H_REC92_15_ALL", 92, 0.15),
        SYMBOLS,
        BASE_FEE,
        BASE_SLIPPAGE,
    )
    sym_spec = next(spec for spec in symbol_audit.variant_specs() if spec.name == "V4H_REC92_25_SOLBNB_94_15")
    runs["V4H_REC92_25_SOLBNB_94_15"] = symbol_audit.run_spec(data, funding_index, short_index, sym_spec, (), BASE_FEE, BASE_SLIPPAGE)
    return runs


def run_original_no_solbnb(data: alpha.AlphaData, funding_index: dict, short_index: dict) -> dict:
    return rec92_audit.run_variant(
        data,
        funding_index,
        short_index,
        rec92_audit.strict_recovery_variant("V4H_REC92_25_ORIGINAL_NO_SOL_BNB", 92, 0.25),
        CORE_SYMBOLS,
        BASE_FEE,
        BASE_SLIPPAGE,
    )


def run_core(data: alpha.AlphaData, funding_index: dict, short_index: dict, spec: CoreSpec, fee_rate: float, slippage_rate: float) -> dict:
    variant = rec92_audit.strict_recovery_variant(spec.name, spec.threshold, spec.size)
    return rec92_audit.run_variant(data, funding_index, short_index, variant, CORE_SYMBOLS, fee_rate, slippage_rate)


def run_satellite(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    spec: SatelliteSpec,
    pause_rule: str,
    universe: Tuple[str, ...],
    fee_rate: float,
    slippage_rate: float,
) -> dict:
    key = (spec, pause_rule, tuple(universe), round(fee_rate, 10), round(slippage_rate, 10))
    if key in SAT_RUN_CACHE:
        return SAT_RUN_CACHE[key]
    signal_variant = rec92_audit.strict_recovery_variant(signal_cache_name(spec), spec.threshold, spec.size)
    signals = [dict(signal, variant=spec.name) for signal in rec92_audit.build_strict_recovery_signals(data, short_index, signal_variant, universe)]
    result = run_satellite_engine(data, signals, spec.name, pause_rule, fee_rate, slippage_rate, spec.cooldown_seconds)
    run = rec92_audit.evaluate_result(funding_index, result, spec.name, "base", "4h")
    run["pause_rule"] = pause_rule
    run["satellite_universe"] = "+".join(symbol.replace("USDT", "") for symbol in universe)
    SAT_RUN_CACHE[key] = run
    return run


def signal_cache_name(spec: SatelliteSpec) -> str:
    return f"SAT_SIGNAL_REC{spec.threshold}_{int(round(spec.size * 100)):02d}"


def run_satellite_engine(
    data: alpha.AlphaData,
    signals: List[dict],
    variant_name: str,
    pause_rule: str,
    fee_rate: float,
    slippage_rate: float,
    recovery_cooldown_seconds: int,
) -> rb.RunResult:
    robust_variant = rb.RobustVariant(
        variant_name,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="V4H core/satellite audit",
    )
    config = rb.RunConfig(variant=robust_variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    last_recovery_entry_by_symbol: Dict[str, int] = {}
    signals_by_time = defaultdict(list)
    for signal in signals:
        signals_by_time[int(signal["signal_time"])].append(signal)

    equity_curve = [{"time": alpha.TEST_START_TS, "date": alpha.format_dt(alpha.TEST_START_TS), "equity": 1.0}]
    current_month = ""
    month_start_equity = 1.0
    rolling_window: deque[Tuple[int, float]] = deque()
    rolling_peaks: deque[Tuple[int, float]] = deque()

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

        current_equity = rb.portfolio_equity(cash, positions, data, time)
        month = alpha.format_dt(close_time)[:7]
        if month != current_month:
            current_month = month
            month_start_equity = current_equity
        pause_reason = satellite_pause_reason(
            pause_rule,
            close_time,
            current_equity,
            month_start_equity,
            rolling_window,
            rolling_peaks,
        )

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
        eligible_for_top = [signal for signal in batch if not (config.variant.exclude_doge and f"{signal['symbol']}USDT" == "DOGEUSDT")]
        top_allowed = set()
        if config.variant.top_score_pct:
            top_n = max(1, math.ceil(len(eligible_for_top) * config.variant.top_score_pct))
            top_allowed = {rb.signal_key(signal) for signal in eligible_for_top[:top_n]}

        for signal in batch:
            symbol = f"{signal['symbol']}USDT"
            if pause_reason:
                skip_counter[pause_reason] += 1
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


def satellite_pause_reason(
    pause_rule: str,
    time: int,
    current_equity: float,
    month_start_equity: float,
    rolling_window: deque,
    rolling_peaks: deque,
) -> str:
    if pause_rule == "rolling_30d_dd":
        cutoff = time - ROLLING_DD_SECONDS
        rolling_window.append((time, current_equity))
        while rolling_peaks and rolling_peaks[-1][1] <= current_equity:
            rolling_peaks.pop()
        rolling_peaks.append((time, current_equity))
        while rolling_window and rolling_window[0][0] < cutoff:
            old = rolling_window.popleft()
            if rolling_peaks and rolling_peaks[0] == old:
                rolling_peaks.popleft()
        while rolling_peaks and rolling_peaks[0][0] < cutoff:
            rolling_peaks.popleft()
        peak = rolling_peaks[0][1] if rolling_peaks else current_equity
        if peak > 0 and current_equity / peak - 1 <= ROLLING_DD_PAUSE:
            return "satellite_rolling_30d_dd_pause"
    elif pause_rule == "monthly_loss":
        if month_start_equity > 0 and current_equity / month_start_equity - 1 <= MONTHLY_LOSS_PAUSE:
            return "satellite_monthly_loss_pause"
    return ""


def build_core_rows(core_specs: List[CoreSpec], core_runs: Dict[str, dict], v0_metrics: dict) -> List[dict]:
    rows = []
    for spec in core_specs:
        run = core_runs[spec.name]
        row = summary_row_for_run(run, "core")
        row.update(
            {
                "recovery_threshold": spec.threshold,
                "recovery_size_pct": spec.size * 100,
                "excluded_symbols": "SOL+BNB",
                "return_vs_v0_pct_point": row["total_return_pct"] - v0_metrics["total_return_pct"],
                "calmar_vs_v0": (row.get("calmar") or 0.0) - (v0_metrics.get("calmar") or 0.0),
                "mdd_extra_vs_v0_pct_point": abs(row["mdd_pct"]) - abs(v0_metrics["mdd_pct"]),
                "recovery_pf": recovery_pf(run["trades"]),
            }
        )
        rows.append(row)
    return rows


def build_satellite_rows(sat_specs: List[SatelliteSpec], sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict], v0_metrics: dict) -> List[dict]:
    rows = []
    for spec in sat_specs:
        for pause_rule in PAUSE_RULES:
            if (spec.name, pause_rule, SATELLITE_SYMBOLS) not in sat_runs:
                continue
            run = sat_runs[(spec.name, pause_rule, SATELLITE_SYMBOLS)]
            row = summary_row_for_run(run, "satellite")
            row.update(
                {
                    "recovery_threshold": spec.threshold,
                    "recovery_size_pct": spec.size * 100,
                    "cooldown_hours": spec.cooldown_seconds / 3600,
                    "pause_rule": pause_rule,
                    "satellite_universe": "SOL+BNB",
                    "return_vs_v0_pct_point": row["total_return_pct"] - v0_metrics["total_return_pct"],
                    "calmar_vs_v0": (row.get("calmar") or 0.0) - (v0_metrics.get("calmar") or 0.0),
                    "satellite_max_drawdown_pct": row["mdd_pct"],
                    "recovery_pf": recovery_pf(run["trades"]),
                    "pause_skips": pause_skip_count(run),
                }
            )
            rows.append(row)
    return rows


def build_combined_rows(
    core_specs: List[CoreSpec],
    core_runs: Dict[str, dict],
    sat_specs: List[SatelliteSpec],
    sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict],
    v0_metrics: dict,
    original_solbnb_impact: float,
) -> Tuple[List[dict], Dict[str, dict]]:
    rows = []
    context = {}
    sat_metric_cache: Dict[Tuple[str, str], dict] = {}
    for core_spec in core_specs:
        core_run = core_runs[core_spec.name]
        for sat_spec in sat_specs:
            for pause_rule in PAUSE_RULES:
                required = [
                    (sat_spec.name, pause_rule, SATELLITE_SYMBOLS),
                    (sat_spec.name, pause_rule, ("SOLUSDT",)),
                    (sat_spec.name, pause_rule, ("BNBUSDT",)),
                ]
                if any(key not in sat_runs for key in required):
                    continue
                full_sat = sat_runs[(sat_spec.name, pause_rule, SATELLITE_SYMBOLS)]
                sol_removed_sat = sat_runs[(sat_spec.name, pause_rule, ("BNBUSDT",))]
                bnb_removed_sat = sat_runs[(sat_spec.name, pause_rule, ("SOLUSDT",))]
                for sat_alloc in SAT_ALLOCATIONS:
                    core_alloc = 1.0 - sat_alloc
                    variant = combined_name(core_spec, sat_spec, pause_rule, sat_alloc)
                    run = combine_runs(variant, core_run, full_sat, core_alloc, sat_alloc)
                    row = summary_row_for_run(run, "combined")
                    sol_return = combined_final_return_pct(core_run, sol_removed_sat, core_alloc, sat_alloc)
                    bnb_return = combined_final_return_pct(core_run, bnb_removed_sat, core_alloc, sat_alloc)
                    no_solbnb_return = (core_alloc * float(core_run["curve"][-1]["equity"]) + sat_alloc - 1.0) * 100
                    sat_cache_key = (sat_spec.name, pause_rule)
                    if sat_cache_key not in sat_metric_cache:
                        sat_metric_cache[sat_cache_key] = metrics(full_sat, alpha.TEST_START_TS, alpha.TEST_END_TS)
                    sat_metrics = sat_metric_cache[sat_cache_key]
                    sat_contribution = satellite_return_contribution(run, core_run, full_sat, core_alloc, sat_alloc)
                    mdd_contribution = satellite_mdd_contribution(run, core_run, full_sat, core_alloc, sat_alloc)
                    row.update(
                        {
                            "core_variant": core_spec.name,
                            "core_recovery_threshold": core_spec.threshold,
                            "core_recovery_size_pct": core_spec.size * 100,
                            "satellite_variant": sat_spec.name,
                            "satellite_recovery_threshold": sat_spec.threshold,
                            "satellite_recovery_size_pct": sat_spec.size * 100,
                            "satellite_cooldown_hours": sat_spec.cooldown_seconds / 3600,
                            "pause_rule": pause_rule,
                            "core_allocation_pct": core_alloc * 100,
                            "satellite_allocation_pct": sat_alloc * 100,
                            "return_vs_v0_pct_point": row["total_return_pct"] - v0_metrics["total_return_pct"],
                            "calmar_vs_v0": (row.get("calmar") or 0.0) - (v0_metrics.get("calmar") or 0.0),
                            "mdd_extra_vs_v0_pct_point": abs(row["mdd_pct"]) - abs(v0_metrics["mdd_pct"]),
                            "sol_removed_return_pct": sol_return,
                            "bnb_removed_return_pct": bnb_return,
                            "solbnb_removed_return_pct": no_solbnb_return,
                            "sol_removed_delta_pct_point": sol_return - row["total_return_pct"],
                            "bnb_removed_delta_pct_point": bnb_return - row["total_return_pct"],
                            "solbnb_removed_delta_pct_point": no_solbnb_return - row["total_return_pct"],
                            "solbnb_impact_improvement_pct": impact_improvement(original_solbnb_impact, no_solbnb_return - row["total_return_pct"]),
                            "satellite_standalone_return_pct": sat_metrics["total_return_pct"],
                            "satellite_standalone_calmar": sat_metrics.get("calmar"),
                            "satellite_max_drawdown_pct": sat_metrics["mdd_pct"],
                            "satellite_return_contribution_pct": sat_contribution,
                            "satellite_mdd_contribution_pct": mdd_contribution,
                            "recovery_pf": recovery_pf(run["trades"]),
                            "pause_skips": pause_skip_count(full_sat),
                        }
                    )
                    rows.append(row)
                    context[variant] = {
                        "run": run,
                        "core_spec": core_spec,
                        "sat_spec": sat_spec,
                        "pause_rule": pause_rule,
                        "sat_alloc": sat_alloc,
                        "core_alloc": core_alloc,
                    }
    return rows, context


def build_cost_rows(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    baseline_runs: Dict[str, dict],
    core_specs: List[CoreSpec],
    sat_specs: List[SatelliteSpec],
    shortlisted: List[dict],
) -> List[dict]:
    rows = []
    baseline_variants = {
        "V0_BASELINE": rec92_audit.RobustnessVariant("V0_BASELINE", is_v0=True),
        "V4H_STRICT_BASE": rec92_audit.RobustnessVariant(
            "V4H_STRICT_BASE",
            gate_config=short4h.GateConfig("V4H_STRICT_BASE", allow_recovery=False, recovery_size_multiplier=0.0, strict_uptrend=True),
        ),
        "V4H_REC92_25_ORIGINAL": rec92_audit.strict_recovery_variant("V4H_REC92_25_ORIGINAL", 92, 0.25),
        "V4H_REC92_15_ALL": rec92_audit.strict_recovery_variant("V4H_REC92_15_ALL", 92, 0.15),
    }
    v0_by_cost = {}
    for multiplier in COST_MULTIPLIERS:
        for name, variant in baseline_variants.items():
            run = rec92_audit.run_variant(data, funding_index, short_index, variant, SYMBOLS, BASE_FEE * multiplier, BASE_SLIPPAGE * multiplier)
            row = summary_row_for_run(run, "comparison")
            row.update({"variant": name, "cost_multiplier": multiplier, "fee_rate_pct": BASE_FEE * multiplier * 100, "slippage_rate_pct": BASE_SLIPPAGE * multiplier * 100})
            if name == "V0_BASELINE":
                v0_by_cost[multiplier] = row
            rows.append(row)
    # Symbol-specific comparison is expensive and not part of candidate status, so stress is limited to the original REC92 family plus Core/Satellite shortlist.
    selected = {row["variant"]: row for row in shortlisted}
    core_lookup = {spec.name: spec for spec in core_specs}
    sat_lookup = {spec.name: spec for spec in sat_specs}
    for multiplier in COST_MULTIPLIERS:
        if multiplier == 1:
            continue
        for item in selected.values():
            core_spec = core_lookup[item["core_variant"]]
            sat_spec = sat_lookup[item["satellite_variant"]]
            core_run = run_core(data, funding_index, short_index, core_spec, BASE_FEE * multiplier, BASE_SLIPPAGE * multiplier)
            sat_run = run_satellite(
                data,
                funding_index,
                short_index,
                sat_spec,
                item["pause_rule"],
                SATELLITE_SYMBOLS,
                BASE_FEE * multiplier,
                BASE_SLIPPAGE * multiplier,
            )
            run = combine_runs(item["variant"], core_run, sat_run, item["core_allocation_pct"] / 100, item["satellite_allocation_pct"] / 100)
            row = summary_row_for_run(run, "combined")
            row.update(
                {
                    "cost_multiplier": multiplier,
                    "fee_rate_pct": BASE_FEE * multiplier * 100,
                    "slippage_rate_pct": BASE_SLIPPAGE * multiplier * 100,
                    "core_variant": item["core_variant"],
                    "satellite_variant": item["satellite_variant"],
                    "pause_rule": item["pause_rule"],
                    "satellite_allocation_pct": item["satellite_allocation_pct"],
                }
            )
            rows.append(row)
    for row in rows:
        v0 = v0_by_cost.get(row["cost_multiplier"])
        if v0:
            row["return_vs_v0_pct_point"] = row["total_return_pct"] - v0["total_return_pct"]
            row["calmar_vs_v0"] = (row.get("calmar") or 0.0) - (v0.get("calmar") or 0.0)
            row["mdd_extra_vs_v0_pct_point"] = abs(row["mdd_pct"]) - abs(v0["mdd_pct"])
    return rows


def build_yearly_rows(
    baseline_runs: Dict[str, dict],
    core_runs: Dict[str, dict],
    sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict],
    combined_context: Dict[str, dict],
    shortlisted: List[dict],
) -> List[dict]:
    rows = []
    for run in baseline_runs.values():
        rows.extend(yearly_rows_for_run(run, "comparison"))
    for run in core_runs.values():
        rows.extend(yearly_rows_for_run(run, "core"))
    for key, run in sat_runs.items():
        if key[2] == SATELLITE_SYMBOLS:
            rows.extend(yearly_rows_for_run(run, "satellite", {"pause_rule": key[1], "satellite_universe": "SOL+BNB"}))
    for row in shortlisted:
        run = combined_context[row["variant"]]["run"]
        rows.extend(yearly_rows_for_run(run, "combined", {"pause_rule": row["pause_rule"], "satellite_allocation_pct": row["satellite_allocation_pct"]}))
    return rows


def build_regime_rows(
    baseline_runs: Dict[str, dict],
    core_runs: Dict[str, dict],
    sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict],
    combined_context: Dict[str, dict],
    shortlisted: List[dict],
    market_state_index: Dict[str, str],
) -> List[dict]:
    rows = []
    for run in baseline_runs.values():
        rows.extend(regime_rows_for_run(run, "comparison", market_state_index))
    for run in core_runs.values():
        rows.extend(regime_rows_for_run(run, "core", market_state_index))
    for key, run in sat_runs.items():
        if key[2] == SATELLITE_SYMBOLS:
            rows.extend(regime_rows_for_run(run, "satellite", market_state_index, {"pause_rule": key[1], "satellite_universe": "SOL+BNB"}))
    for row in shortlisted:
        run = combined_context[row["variant"]]["run"]
        rows.extend(regime_rows_for_run(run, "combined", market_state_index, {"pause_rule": row["pause_rule"], "satellite_allocation_pct": row["satellite_allocation_pct"]}))
    return rows


def build_symbol_rows(
    baseline_runs: Dict[str, dict],
    core_runs: Dict[str, dict],
    sat_runs: Dict[Tuple[str, str, Tuple[str, ...]], dict],
    combined_context: Dict[str, dict],
    shortlisted: List[dict],
) -> List[dict]:
    rows = []
    for run in baseline_runs.values():
        rows.extend(symbol_rows_for_run(run, "comparison"))
    for run in core_runs.values():
        rows.extend(symbol_rows_for_run(run, "core"))
    for key, run in sat_runs.items():
        if key[2] == SATELLITE_SYMBOLS:
            rows.extend(symbol_rows_for_run(run, "satellite", {"pause_rule": key[1], "satellite_universe": "SOL+BNB"}))
    for row in shortlisted:
        run = combined_context[row["variant"]]["run"]
        rows.extend(symbol_rows_for_run(run, "combined", {"pause_rule": row["pause_rule"], "satellite_allocation_pct": row["satellite_allocation_pct"]}))
    return rows


def build_summary_rows(
    baseline_rows: List[dict],
    core_rows: List[dict],
    satellite_rows: List[dict],
    combined_rows: List[dict],
    shortlisted: List[dict],
    cost_lookup: Dict[Tuple[str, int], dict],
    yearly_rows: List[dict],
    v0_metrics: dict,
    original_metrics: dict,
    original_solbnb_impact: float,
    best_core_row: dict,
) -> List[dict]:
    rows = []
    for row in baseline_rows:
        out = dict(row)
        out["audit_group"] = "comparison"
        out["audit_status"] = "BASELINE"
        out["audit_reasons"] = "comparison baseline"
        rows.append(out)
    best_core = dict(best_core_row)
    best_core["audit_group"] = "core_best"
    apply_core_status(best_core, v0_metrics)
    rows.append(best_core)
    best_sat = max(satellite_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]))
    best_sat = dict(best_sat)
    best_sat["audit_group"] = "satellite_best"
    best_sat["audit_status"] = "WATCH"
    best_sat["audit_reasons"] = "satellite is evaluated only as capped return engine, not standalone portfolio"
    rows.append(best_sat)

    yearly_lookup = {(row["variant"], row["year"]): row for row in yearly_rows}
    for row in shortlisted:
        out = dict(row)
        out["audit_group"] = "combined_shortlist"
        apply_combined_status(out, cost_lookup, yearly_lookup, v0_metrics, original_metrics, original_solbnb_impact, best_core_row)
        rows.append(out)
    rows.sort(key=lambda row: (status_rank(row.get("audit_status")), -(row.get("calmar") or -999.0), -row.get("total_return_pct", 0.0)))
    return rows


def shortlist_satellite_specs(satellite_rows: List[dict], sat_specs: List[SatelliteSpec]) -> List[SatelliteSpec]:
    spec_by_name = {spec.name: spec for spec in sat_specs}
    selected: Dict[str, SatelliteSpec] = {}
    sorted_by_calmar = sorted(satellite_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]), reverse=True)
    sorted_by_return = sorted(satellite_rows, key=lambda row: row["total_return_pct"], reverse=True)
    sorted_by_mdd = sorted(satellite_rows, key=lambda row: (abs(row["mdd_pct"]), -(row.get("calmar") or -999.0)))
    for row in sorted_by_calmar[:5] + sorted_by_return[:3] + sorted_by_mdd[:2]:
        selected[row["variant"]] = spec_by_name[row["variant"]]
    grouped = defaultdict(list)
    for row in satellite_rows:
        grouped[row["recovery_threshold"]].append(row)
    for group_rows in grouped.values():
        row = max(group_rows, key=lambda item: (item.get("calmar") or -999.0, item["total_return_pct"]))
        selected[row["variant"]] = spec_by_name[row["variant"]]
    return list(selected.values())[:8]


def shortlist_core_specs(core_rows: List[dict], core_specs: List[CoreSpec]) -> List[CoreSpec]:
    spec_by_name = {spec.name: spec for spec in core_specs}
    selected: Dict[str, CoreSpec] = {}
    sorted_by_calmar = sorted(core_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]), reverse=True)
    sorted_by_return = sorted(core_rows, key=lambda row: row["total_return_pct"], reverse=True)
    sorted_by_mdd = sorted(core_rows, key=lambda row: (abs(row["mdd_pct"]), -(row.get("calmar") or -999.0)))
    for row in sorted_by_calmar[:3] + sorted_by_return[:2] + sorted_by_mdd[:2]:
        selected[row["variant"]] = spec_by_name[row["variant"]]
    return list(selected.values())[:4]


def apply_core_status(row: dict, v0_metrics: dict) -> None:
    reasons = []
    if (row.get("calmar") or 0.0) > (v0_metrics.get("calmar") or 0.0):
        row["audit_status"] = "PASS"
        row["audit_reasons"] = "Core Calmar above V0 without SOL/BNB"
        return
    if abs(row["mdd_pct"]) <= abs(v0_metrics["mdd_pct"]) - 3.0 and (row.get("calmar") or 0.0) >= (v0_metrics.get("calmar") or 0.0) * 0.8:
        row["audit_status"] = "WATCH"
        row["audit_reasons"] = "Core MDD materially lower, but Calmar not above V0"
        return
    reasons.append("Core Calmar not above V0")
    if row["total_return_pct"] < v0_metrics["total_return_pct"]:
        reasons.append("Core return below V0")
    row["audit_status"] = "FAIL"
    row["audit_reasons"] = "; ".join(reasons)


def apply_combined_status(
    row: dict,
    cost_lookup: Dict[Tuple[str, int], dict],
    yearly_lookup: Dict[Tuple[str, int], dict],
    v0_metrics: dict,
    original_metrics: dict,
    original_solbnb_impact: float,
    best_core_row: dict,
) -> None:
    fail = []
    watch = []
    if not (row["total_return_pct"] > v0_metrics["total_return_pct"] and (row.get("cagr_pct") or 0.0) > (v0_metrics.get("cagr_pct") or 0.0) and (row.get("calmar") or 0.0) > (v0_metrics.get("calmar") or 0.0)):
        fail.append("Core+Satellite return/CAGR/Calmar not all above V0")
    cost2 = cost_lookup.get((row["variant"], 2))
    if not cost2 or cost2["total_return_pct"] <= v0_metrics["total_return_pct"] or (cost2.get("calmar") or 0.0) <= (v0_metrics.get("calmar") or 0.0):
        fail.append("cost 2x weaker than V0")
    impact_improvement_pct = row.get("solbnb_impact_improvement_pct") or 0.0
    if impact_improvement_pct < 50.0:
        fail.append("SOL+BNB removal impact not sufficiently reduced")
    elif impact_improvement_pct < 70.0:
        watch.append("SOL+BNB impact reduced but still material")
    if row.get("satellite_mdd_contribution_pct") is not None and row["satellite_mdd_contribution_pct"] > 65.0:
        fail.append("satellite drives most account MDD")
    elif row.get("satellite_mdd_contribution_pct") is not None and row["satellite_mdd_contribution_pct"] > 45.0:
        watch.append("satellite MDD contribution material")
    improved_2022 = yearly_lookup.get((row["variant"], 2022), {}).get("total_return_pct", -999.0) > yearly_lookup.get(("V4H_REC92_25_ORIGINAL", 2022), {}).get("total_return_pct", -999.0)
    improved_2025 = yearly_lookup.get((row["variant"], 2025), {}).get("total_return_pct", -999.0) > yearly_lookup.get(("V4H_REC92_25_ORIGINAL", 2025), {}).get("total_return_pct", -999.0)
    if not (improved_2022 or improved_2025):
        fail.append("2022/2025 OOS not improved")
    if (best_core_row.get("calmar") or 0.0) < (v0_metrics.get("calmar") or 0.0) and best_core_row["total_return_pct"] < v0_metrics["total_return_pct"]:
        watch.append("Core remains weaker than V0 without satellite")
    cost3 = cost_lookup.get((row["variant"], 3))
    cost5 = cost_lookup.get((row["variant"], 5))
    if cost3 and cost3["total_return_pct"] < 0:
        watch.append("cost 3x stress weak")
    if cost5 and cost5["total_return_pct"] < 0:
        watch.append("cost 5x stress weak")
    if fail:
        row["audit_status"] = "FAIL"
        row["audit_reasons"] = "; ".join(fail + watch)
    elif watch:
        row["audit_status"] = "WATCH"
        row["audit_reasons"] = "; ".join(watch)
    else:
        row["audit_status"] = "PASS"
        row["audit_reasons"] = "meets Core/Satellite audit thresholds"
    row["original_solbnb_impact_pct_point"] = original_solbnb_impact
    row["rec92_return_pct"] = original_metrics["total_return_pct"]


def shortlist_combined_rows(rows: List[dict]) -> List[dict]:
    selected: Dict[str, dict] = {}
    for row in sorted(rows, key=lambda item: (item.get("calmar") or -999.0, item["total_return_pct"]), reverse=True)[:12]:
        selected[row["variant"]] = row
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["satellite_allocation_pct"], row["pause_rule"])].append(row)
    for group_rows in grouped.values():
        for row in sorted(group_rows, key=lambda item: (item.get("calmar") or -999.0, item["total_return_pct"]), reverse=True)[:1]:
            selected[row["variant"]] = row
        for row in sorted(group_rows, key=lambda item: abs(item.get("solbnb_removed_delta_pct_point") or 0.0))[:1]:
            selected[row["variant"]] = row
    return sorted(selected.values(), key=lambda item: (item.get("calmar") or -999.0, item["total_return_pct"]), reverse=True)[:3]


def combine_runs(variant: str, core_run: dict, satellite_run: dict, core_alloc: float, satellite_alloc: float) -> dict:
    core_times, core_equity = curve_arrays(core_run)
    sat_times, sat_equity = curve_arrays(satellite_run)
    times, equities = combine_curve_arrays(core_times, core_equity, sat_times, sat_equity, core_alloc, satellite_alloc)
    curve = [{"time": time, "date": "", "equity": equity} for time, equity in zip(times, equities)]
    trades = scaled_trades(core_run["trades"], core_alloc, "core") + scaled_trades(satellite_run["trades"], satellite_alloc, "satellite")
    trades.sort(key=lambda trade: int(trade.get("exit_timestamp") or trade.get("entry_timestamp") or 0))
    return {"variant": variant, "scenario": "base", "regime_timeframe": "core_satellite", "curve": curve, "trades": trades, "result": None}


def flat_run_like(template_run: dict) -> dict:
    curve = [{"time": row["time"], "date": "", "equity": 1.0} for row in template_run["curve"]]
    return {"variant": "FLAT_SATELLITE", "scenario": "flat", "regime_timeframe": "flat", "curve": curve, "trades": [], "result": None}


def combined_final_return_pct(core_run: dict, satellite_run: dict, core_alloc: float, satellite_alloc: float) -> float:
    final_equity = core_alloc * float(core_run["curve"][-1]["equity"]) + satellite_alloc * float(satellite_run["curve"][-1]["equity"])
    return (final_equity - 1.0) * 100


def combine_curve_arrays(
    core_times: List[int],
    core_equity: List[float],
    sat_times: List[int],
    sat_equity: List[float],
    core_alloc: float,
    sat_alloc: float,
) -> Tuple[List[int], List[float]]:
    if core_times == sat_times:
        return core_times, [core_alloc * core_equity[index] + sat_alloc * sat_equity[index] for index in range(len(core_times))]
    times = sorted(set(core_times).union(sat_times))
    core_map = forward_fill_map(core_times, core_equity, times)
    sat_map = forward_fill_map(sat_times, sat_equity, times)
    return times, [core_alloc * core_map[index] + sat_alloc * sat_map[index] for index in range(len(times))]


def forward_fill_map(source_times: List[int], source_equity: List[float], target_times: List[int]) -> List[float]:
    values = []
    index = 0
    current = source_equity[0]
    for time in target_times:
        while index + 1 < len(source_times) and source_times[index + 1] <= time:
            index += 1
            current = source_equity[index]
        values.append(current)
    return values


def scaled_trades(trades: List[dict], allocation: float, component: str) -> List[dict]:
    scaled = []
    for trade in trades:
        item = dict(trade)
        item["component"] = component
        item["account_allocation"] = allocation
        for key in ("pnl", "pnl_after_funding", "funding_pnl", "funding_abs_cost"):
            if item.get(key) is not None:
                item[key] = float(item[key]) * allocation
        scaled.append(item)
    return scaled


def summary_row_for_run(run: dict, group: str) -> dict:
    row = metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
    row.update({"variant": run["variant"], "audit_group": group})
    row["calmar"] = calmar(row)
    return row


def metrics(run: dict, start_ts: int, end_ts: int) -> dict:
    row = rec92_audit.run_metrics(run, start_ts, end_ts)
    row["calmar"] = calmar(row)
    return row


def calmar(row: dict) -> Optional[float]:
    cagr = row.get("cagr_pct")
    mdd = row.get("mdd_pct")
    return (cagr / abs(mdd)) if cagr is not None and mdd and mdd < 0 else None


def recovery_pf(trades: List[dict]) -> Optional[float]:
    recovery = [trade for trade in trades if rec92_audit.normalized_regime(trade) == "recovery"]
    losses = [float(trade.get("pnl_after_funding") or 0.0) for trade in recovery if float(trade.get("pnl_after_funding") or 0.0) < 0]
    wins = [float(trade.get("pnl_after_funding") or 0.0) for trade in recovery if float(trade.get("pnl_after_funding") or 0.0) > 0]
    return sum(wins) / abs(sum(losses)) if losses else None


def pause_skip_count(run: dict) -> int:
    result = run.get("result")
    if not result:
        return 0
    return sum(value for key, value in result.skip_counter.items() if "pause" in key)


def yearly_rows_for_run(run: dict, group: str, extras: Optional[dict] = None) -> List[dict]:
    rows = []
    for year in TARGET_YEARS:
        start = rec92_audit.ts(f"{year}-01-01T00:00:00+00:00")
        end = rec92_audit.ts(f"{year + 1}-01-01T00:00:00+00:00")
        row = metrics(run, start, end)
        row.update({"variant": run["variant"], "audit_group": group, "year": year})
        if extras:
            row.update(extras)
        rows.append(row)
    return rows


def regime_rows_for_run(run: dict, group: str, market_state_index: Dict[str, str], extras: Optional[dict] = None) -> List[dict]:
    rows = rec92_audit.market_state_performance_rows(run, market_state_index)
    for row in rows:
        row["audit_group"] = group
        if extras:
            row.update(extras)
    return rows


def symbol_rows_for_run(run: dict, group: str, extras: Optional[dict] = None) -> List[dict]:
    rows = []
    grouped: Dict[str, List[dict]] = defaultdict(list)
    total_positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in run["trades"])
    for trade in run["trades"]:
        grouped[str(trade.get("symbol"))].append(trade)
    for symbol, trades in sorted(grouped.items()):
        row = rec92_audit.group_trade_metrics(trades)
        positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in trades)
        row.update(
            {
                "variant": run["variant"],
                "audit_group": group,
                "symbol": symbol,
                "positive_pnl_share_pct": positive / total_positive * 100 if total_positive else 0.0,
            }
        )
        if extras:
            row.update(extras)
        rows.append(row)
    if rows:
        sorted_rows = sorted(rows, key=lambda item: item["positive_pnl_share_pct"], reverse=True)
        for row in rows:
            row["top1_symbol"] = sorted_rows[0]["symbol"]
            row["top1_positive_pnl_share_pct"] = sorted_rows[0]["positive_pnl_share_pct"]
            row["top2_positive_pnl_share_pct"] = sum(item["positive_pnl_share_pct"] for item in sorted_rows[:2])
    return rows


def curve_arrays(run: dict) -> Tuple[List[int], List[float]]:
    return [int(row["time"]) for row in run["curve"]], [float(row["equity"]) for row in run["curve"]]


def satellite_return_contribution(run: dict, core_run: dict, satellite_run: dict, core_alloc: float, sat_alloc: float) -> Optional[float]:
    total_return = float(run["curve"][-1]["equity"]) - 1.0
    if abs(total_return) < 1e-12:
        return None
    sat_return = sat_alloc * (float(satellite_run["curve"][-1]["equity"]) - 1.0)
    return sat_return / total_return * 100


def satellite_mdd_contribution(run: dict, core_run: dict, satellite_run: dict, core_alloc: float, sat_alloc: float) -> Optional[float]:
    combined = [float(row["equity"]) for row in run["curve"]]
    peak_index = 0
    trough_index = 0
    peak = combined[0]
    max_loss = 0.0
    current_peak_index = 0
    for index, equity in enumerate(combined):
        if equity > peak:
            peak = equity
            current_peak_index = index
        loss = equity - peak
        if loss < max_loss:
            max_loss = loss
            peak_index = current_peak_index
            trough_index = index
    if max_loss >= 0:
        return 0.0
    sat_equity = [float(row["equity"]) for row in satellite_run["curve"]]
    if trough_index >= len(sat_equity) or peak_index >= len(sat_equity):
        return None
    sat_loss = sat_alloc * (sat_equity[trough_index] - sat_equity[peak_index])
    return max(0.0, sat_loss / max_loss * 100)


def impact_improvement(original_impact: float, new_impact: float) -> float:
    original_abs = abs(original_impact)
    if original_abs == 0:
        return 0.0
    return (1 - abs(new_impact) / original_abs) * 100


def combined_name(core_spec: CoreSpec, sat_spec: SatelliteSpec, pause_rule: str, sat_alloc: float) -> str:
    pause = {"none": "NOPAUSE", "rolling_30d_dd": "ROLL30DD", "monthly_loss": "MONTHLOSS"}[pause_rule]
    return f"CS_{core_spec.name}__{sat_spec.name}__SAT{int(round(sat_alloc * 100)):02d}_{pause}"


def status_rank(status: Optional[str]) -> int:
    return {"PASS": 0, "WATCH": 1, "FAIL": 2, "BASELINE": 3}.get(status or "", 4)


def build_report(
    summary_rows: List[dict],
    core_rows: List[dict],
    satellite_rows: List[dict],
    combined_rows: List[dict],
    cost_rows: List[dict],
    yearly_rows: List[dict],
    regime_rows: List[dict],
    symbol_rows: List[dict],
    paths: Dict[str, Path],
) -> str:
    top_combined = [row for row in summary_rows if row.get("audit_group") == "combined_shortlist"][:20]
    best_core = next(row for row in summary_rows if row.get("audit_group") == "core_best")
    best_sat = next(row for row in summary_rows if row.get("audit_group") == "satellite_best")
    status_counts = Counter(row.get("audit_status") for row in top_combined)
    lines = [
        "# V4H Core/Satellite Audit",
        "",
        "## Scope",
        "",
        "- Read-only audit/report only. Strategy, paper engine, live order logic, checkout/merge, commit, and push were not touched.",
        "- Core excludes SOL/BNB; Satellite trades SOL/BNB only; Core+Satellite combines independent equity curves by account allocation.",
        "- Satellite pause rules are audit-only wrappers for new entries: rolling 30D drawdown <= -10% or monthly loss <= -8%.",
        "- Cost stress is run for comparison baselines and the combined shortlist selected from the base Core/Satellite grid.",
        "",
        "## Final Read",
        "",
        f"- Combined shortlist status counts: PASS {status_counts.get('PASS', 0)}, WATCH {status_counts.get('WATCH', 0)}, FAIL {status_counts.get('FAIL', 0)}.",
        f"- Best Core only: `{best_core['variant']}` return {best_core['total_return_pct']:.2f}%, MDD {best_core['mdd_pct']:.2f}%, Calmar {best_core.get('calmar') or 0.0:.2f}, status {best_core['audit_status']}.",
        f"- Best Satellite only: `{best_sat['variant']}` with pause `{best_sat.get('pause_rule')}` return {best_sat['total_return_pct']:.2f}%, MDD {best_sat['mdd_pct']:.2f}%, Calmar {best_sat.get('calmar') or 0.0:.2f}.",
        "",
        "## Summary",
        "",
        markdown_table(
            ["Variant", "Group", "Status", "Reasons", "Return", "CAGR", "MDD", "Calmar", "Trades", "Sat Alloc", "SOL+BNB Impact"],
            summary_rows[:30],
            ["variant", "audit_group", "audit_status", "audit_reasons", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "trade_count", "satellite_allocation_pct", "solbnb_removed_delta_pct_point"],
        ),
        "",
        "## Core Only",
        "",
        markdown_table(
            ["Variant", "Threshold", "Size", "Return", "CAGR", "MDD", "Calmar", "Recovery PF", "Trades"],
            sorted(core_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]), reverse=True),
            ["variant", "recovery_threshold", "recovery_size_pct", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "recovery_pf", "trade_count"],
        ),
        "",
        "## Satellite Only Top 20",
        "",
        markdown_table(
            ["Variant", "Pause", "Return", "CAGR", "MDD", "Calmar", "Recovery PF", "Trades", "Pause Skips"],
            sorted(satellite_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]), reverse=True)[:20],
            ["variant", "pause_rule", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "recovery_pf", "trade_count", "pause_skips"],
        ),
        "",
        "## Combined Top 30",
        "",
        markdown_table(
            ["Variant", "Return", "CAGR", "MDD", "Calmar", "Sat Alloc", "Pause", "SOL+BNB Delta", "Impact Improvement", "Sat MDD Contribution"],
            sorted(combined_rows, key=lambda row: (row.get("calmar") or -999.0, row["total_return_pct"]), reverse=True)[:30],
            ["variant", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "satellite_allocation_pct", "pause_rule", "solbnb_removed_delta_pct_point", "solbnb_impact_improvement_pct", "satellite_mdd_contribution_pct"],
        ),
        "",
        "## Cost Stress",
        "",
        markdown_table(
            ["Variant", "Cost", "Return", "MDD", "Calmar", "Return vs V0", "Calmar vs V0"],
            cost_rows,
            ["variant", "cost_multiplier", "total_return_pct", "mdd_pct", "calmar", "return_vs_v0_pct_point", "calmar_vs_v0"],
        ),
        "",
        "## 2022 / 2025 OOS",
        "",
        markdown_table(
            ["Variant", "Group", "Year", "Return", "CAGR", "MDD", "Calmar", "Trades"],
            [row for row in yearly_rows if row["year"] in {2022, 2025}][:120],
            ["variant", "audit_group", "year", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "trade_count"],
        ),
        "",
        "## Bull / Bear / Sideways",
        "",
        markdown_table(
            ["Variant", "Group", "State", "PnL", "PF", "Win", "Trades"],
            regime_rows[:120],
            ["variant", "audit_group", "market_state", "pnl_pct", "profit_factor", "win_rate_pct", "trade_count"],
        ),
        "",
        "## Output Files",
        "",
    ]
    for key in ("report", "summary", "core", "satellite", "combined", "cost", "yearly", "regime", "symbols"):
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
        lines.append("| " + " | ".join(format_value(row.get(key), key in percent_keys) for key in keys) + " |")
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
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
