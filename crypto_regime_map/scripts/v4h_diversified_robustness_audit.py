"""Read-only diversified V4H robustness audit.

This script adds audit-only diversified variants. It does not change the
strategy modules, paper engine, live order logic, or existing report files.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
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
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import v4h_rec92_25_robustness_audit as rec92_audit  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
NON_DOGE_SYMBOLS = tuple(symbol for symbol in SYMBOLS if symbol != "DOGEUSDT")
BASE_FEE = rec92_audit.BASE_FEE
BASE_SLIPPAGE = rec92_audit.BASE_SLIPPAGE
TOP_SCORE_PCT = rec92_audit.TOP_SCORE_PCT
ROLLING_WINDOW_SECONDS = 30 * 86400
DIVERSIFIED_MAX_ENTRIES_30D = 2
RECOVERY_COOLDOWN_SECONDS = 24 * 3600
COST_MULTIPLIERS = (1, 2, 3, 5)
TARGET_YEARS = rec92_audit.TARGET_YEARS
LEAVE_OUT_SETS = [(symbol.replace("USDT", ""),) for symbol in NON_DOGE_SYMBOLS] + [("SOL", "BNB")]

RUN_CACHE: Dict[Tuple, dict] = {}
SIGNAL_CACHE: Dict[Tuple, List[dict]] = {}


@dataclass(frozen=True)
class VariantSpec:
    name: str
    is_v0: bool = False
    allow_recovery: bool = True
    recovery_score_min_pct: Optional[float] = None
    recovery_size: float = 0.25
    strict_uptrend: bool = True
    recovery_cooldown_seconds: int = 0
    diversified: bool = False
    rolling_cap_scope: str = "all"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "research"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir)

    data, short_index, _short_rows, funding_index = rec92_audit.load_context(raw_dir)
    specs = variant_specs()
    base_runs = {spec.name: run_spec(data, funding_index, short_index, spec, (), BASE_FEE, BASE_SLIPPAGE) for spec in specs}

    summary_rows = build_summary_rows(base_runs, specs)
    leave_rows = build_leave_one_rows(data, funding_index, short_index, specs, base_runs)
    concentration_rows = build_symbol_concentration_rows(base_runs)
    cost_rows = build_cost_rows(data, funding_index, short_index, specs)
    yearly_rows = [row for run in base_runs.values() for row in yearly_rows_for_run(run)]
    market_index = rec92_audit.build_market_state_index(data.raw_1d["BTCUSDT"])
    regime_rows = [row for run in base_runs.values() for row in rec92_audit.market_state_performance_rows(run, market_index)]
    apply_status(summary_rows, leave_rows, concentration_rows, cost_rows, regime_rows)

    paths = {
        "report": output_dir / "v4h_diversified_robustness_report.md",
        "summary": output_dir / "v4h_diversified_summary.csv",
        "leave": output_dir / "v4h_diversified_leave_one_symbol.csv",
        "concentration": output_dir / "v4h_diversified_symbol_concentration.csv",
        "cost": output_dir / "v4h_diversified_cost_stress.csv",
        "yearly": output_dir / "v4h_diversified_oos_yearly.csv",
        "regime": output_dir / "v4h_diversified_regime_performance.csv",
    }
    write_csv(paths["summary"], summary_rows)
    write_csv(paths["leave"], leave_rows)
    write_csv(paths["concentration"], concentration_rows)
    write_csv(paths["cost"], cost_rows)
    write_csv(paths["yearly"], yearly_rows)
    write_csv(paths["regime"], regime_rows)
    paths["report"].write_text(
        build_report(summary_rows, leave_rows, concentration_rows, cost_rows, yearly_rows, regime_rows, paths),
        encoding="utf-8",
    )
    print(paths["report"])


def variant_specs() -> List[VariantSpec]:
    return [
        VariantSpec("V0_BASELINE", is_v0=True),
        VariantSpec("V4H_STRICT_BASE", allow_recovery=False, recovery_score_min_pct=None, recovery_size=0.0),
        VariantSpec("V4H_STRICT_REC92_25", recovery_score_min_pct=92.0, recovery_size=0.25),
        VariantSpec("V4H_STRICT_REC92_15", recovery_score_min_pct=92.0, recovery_size=0.15),
        VariantSpec(
            "V4H_STRICT_REC90_25_COOLDOWN",
            recovery_score_min_pct=90.0,
            recovery_size=0.25,
            recovery_cooldown_seconds=RECOVERY_COOLDOWN_SECONDS,
        ),
        VariantSpec("V4H_REC92_15_DIVERSIFIED", recovery_score_min_pct=92.0, recovery_size=0.15, diversified=True),
        VariantSpec("V4H_REC92_10_DIVERSIFIED", recovery_score_min_pct=92.0, recovery_size=0.10, diversified=True),
        VariantSpec(
            "V4H_REC90_25_COOLDOWN_DIVERSIFIED",
            recovery_score_min_pct=90.0,
            recovery_size=0.25,
            recovery_cooldown_seconds=RECOVERY_COOLDOWN_SECONDS,
            diversified=True,
        ),
        VariantSpec(
            "V4H_STRICT_NO_RECOVERY_DIVERSIFIED",
            allow_recovery=False,
            recovery_score_min_pct=None,
            recovery_size=0.0,
            diversified=True,
        ),
    ]


def run_spec(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    spec: VariantSpec,
    excluded_symbols: Tuple[str, ...],
    fee_rate: float,
    slippage_rate: float,
) -> dict:
    excluded_usdt = {symbol if symbol.endswith("USDT") else f"{symbol}USDT" for symbol in excluded_symbols}
    universe = tuple(symbol for symbol in SYMBOLS if symbol not in excluded_usdt)
    cache_key = (
        spec.name,
        tuple(sorted(excluded_usdt)),
        round(fee_rate, 10),
        round(slippage_rate, 10),
        spec.diversified,
        DIVERSIFIED_MAX_ENTRIES_30D if spec.diversified else 0,
    )
    if cache_key in RUN_CACHE:
        return RUN_CACHE[cache_key]

    base_variant = base_variant_from_spec(spec)
    if not spec.diversified:
        run = rec92_audit.run_variant(data, funding_index, short_index, base_variant, universe, fee_rate, slippage_rate)
        RUN_CACHE[cache_key] = run
        return run

    signals = signals_for_spec(data, short_index, spec, universe)
    result = run_engine_with_symbol_cap(data, signals, spec, fee_rate, slippage_rate)
    run = rec92_audit.evaluate_result(funding_index, result, spec.name, "base", "4h")
    RUN_CACHE[cache_key] = run
    return run


def base_variant_from_spec(spec: VariantSpec) -> rec92_audit.RobustnessVariant:
    if spec.is_v0:
        return rec92_audit.RobustnessVariant(spec.name, is_v0=True)
    return rec92_audit.RobustnessVariant(
        name=spec.name,
        gate_config=short4h.GateConfig(
            spec.name,
            allow_recovery=spec.allow_recovery,
            recovery_size_multiplier=spec.recovery_size,
            strict_uptrend=spec.strict_uptrend,
        ),
        recovery_score_min_pct=spec.recovery_score_min_pct,
        recovery_cooldown_seconds=spec.recovery_cooldown_seconds,
    )


def signals_for_spec(data: alpha.AlphaData, short_index: dict, spec: VariantSpec, universe: Tuple[str, ...]) -> List[dict]:
    key = (spec.name, tuple(universe))
    if key not in SIGNAL_CACHE:
        SIGNAL_CACHE[key] = rec92_audit.build_strict_recovery_signals(data, short_index, base_variant_from_spec(spec), universe)
    return SIGNAL_CACHE[key]


def run_engine_with_symbol_cap(
    data: alpha.AlphaData,
    signals: List[dict],
    spec: VariantSpec,
    fee_rate: float,
    slippage_rate: float,
) -> rb.RunResult:
    robust_variant = rb.RobustVariant(
        spec.name,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="V4H diversified audit",
    )
    config = rb.RunConfig(variant=robust_variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    entry_history: Dict[str, deque] = defaultdict(deque)
    recovery_entry_history: Dict[str, int] = {}
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
        eligible_for_top = [signal for signal in batch if not (config.variant.exclude_doge and f"{signal['symbol']}USDT" == "DOGEUSDT")]
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
            if spec.recovery_cooldown_seconds and signal.get("short_regime_4h") == "recovery":
                previous = recovery_entry_history.get(symbol)
                if previous is not None and time - previous < spec.recovery_cooldown_seconds:
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
            if not rolling_cap_allows(entry_history[order["symbol"]], time, spec, order):
                skip_counter["rolling_30d_symbol_cap"] += 1
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
            entry_history[position.symbol].append(time)
            if order.get("short_regime_4h") == "recovery":
                recovery_entry_history[position.symbol] = time

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


def rolling_cap_allows(history: deque, timestamp: int, spec: VariantSpec, order: dict) -> bool:
    while history and timestamp - history[0] >= ROLLING_WINDOW_SECONDS:
        history.popleft()
    if spec.rolling_cap_scope == "recovery" and order.get("short_regime_4h") != "recovery":
        return True
    return len(history) < DIVERSIFIED_MAX_ENTRIES_30D


def build_summary_rows(base_runs: Dict[str, dict], specs: List[VariantSpec]) -> List[dict]:
    v0 = metrics(base_runs["V0_BASELINE"], alpha.TEST_START_TS, alpha.TEST_END_TS)
    rec92 = metrics(base_runs["V4H_STRICT_REC92_25"], alpha.TEST_START_TS, alpha.TEST_END_TS)
    rows = []
    for spec in specs:
        run = base_runs[spec.name]
        row = metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
        row.update(
            {
                "variant": spec.name,
                "group": "diversified" if spec.diversified else "baseline",
                "rolling_30d_symbol_entry_cap": DIVERSIFIED_MAX_ENTRIES_30D if spec.diversified else "",
                "recovery_score_min_pct": spec.recovery_score_min_pct,
                "recovery_size_pct": spec.recovery_size * 100 if spec.allow_recovery else 0.0,
                "return_vs_v0_pct_point": row["total_return_pct"] - v0["total_return_pct"],
                "cagr_vs_v0_pct_point": (row.get("cagr_pct") or 0.0) - (v0.get("cagr_pct") or 0.0),
                "mdd_extra_vs_v0_pct_point": abs(row["mdd_pct"]) - abs(v0["mdd_pct"]),
                "calmar_vs_v0": (row.get("calmar") or 0.0) - (v0.get("calmar") or 0.0),
                "trade_count_vs_rec92_25": row["trade_count"] - rec92["trade_count"],
                "mdd_change_vs_rec92_25_pct_point": row["mdd_pct"] - rec92["mdd_pct"],
                "calmar_change_vs_rec92_25": (row.get("calmar") or 0.0) - (rec92.get("calmar") or 0.0),
                "skipped_trades": sum(run["result"].skip_counter.values()),
                "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(run["result"].skip_counter.items())),
            }
        )
        rows.append(row)
    return rows


def metrics(run: dict, start_ts: int, end_ts: int) -> dict:
    row = rec92_audit.run_metrics(run, start_ts, end_ts)
    cagr = row.get("cagr_pct")
    mdd = row.get("mdd_pct")
    row["calmar"] = (cagr / abs(mdd)) if cagr is not None and mdd and mdd < 0 else None
    return row


def build_leave_one_rows(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    specs: List[VariantSpec],
    base_runs: Dict[str, dict],
) -> List[dict]:
    base_metrics = {name: metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS) for name, run in base_runs.items()}
    rows = []
    for excluded in LEAVE_OUT_SETS:
        v0_run = run_spec(data, funding_index, short_index, specs[0], excluded, BASE_FEE, BASE_SLIPPAGE)
        v0_metric = metrics(v0_run, alpha.TEST_START_TS, alpha.TEST_END_TS)
        for spec in specs:
            run = run_spec(data, funding_index, short_index, spec, excluded, BASE_FEE, BASE_SLIPPAGE)
            row = metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
            base = base_metrics[spec.name]
            row.update(
                {
                    "variant": spec.name,
                    "excluded_symbols": "+".join(excluded),
                    "return_delta_vs_full_pct_point": row["total_return_pct"] - base["total_return_pct"],
                    "calmar_delta_vs_full": (row.get("calmar") or 0.0) - (base.get("calmar") or 0.0),
                    "return_vs_v0_same_exclusion_pct_point": row["total_return_pct"] - v0_metric["total_return_pct"],
                    "calmar_vs_v0_same_exclusion": (row.get("calmar") or 0.0) - (v0_metric.get("calmar") or 0.0),
                }
            )
            rows.append(row)
    return rows


def build_symbol_concentration_rows(base_runs: Dict[str, dict]) -> List[dict]:
    rows = []
    for variant, run in base_runs.items():
        symbol_rows = concentration_symbol_rows(variant, run["trades"])
        rows.append(concentration_summary_row(variant, symbol_rows))
        rows.extend(symbol_rows)
    return rows


def concentration_symbol_rows(variant: str, trades: List[dict]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("symbol"))].append(trade)
    total_positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in trades)
    recovery_trades = [trade for trade in trades if rec92_audit.normalized_regime(trade) == "recovery"]
    total_recovery_positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in recovery_trades)
    rows = []
    for symbol in sorted(grouped):
        symbol_trades = grouped[symbol]
        pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in symbol_trades)
        positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in symbol_trades)
        symbol_recovery = [trade for trade in symbol_trades if rec92_audit.normalized_regime(trade) == "recovery"]
        recovery_positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in symbol_recovery)
        rows.append(
            {
                "analysis_type": "symbol",
                "variant": variant,
                "symbol": symbol,
                "trade_count": len(symbol_trades),
                "pnl_pct": pnl * 100,
                "positive_pnl_share_pct": positive / total_positive * 100 if total_positive else 0.0,
                "recovery_trade_count": len(symbol_recovery),
                "recovery_positive_pnl_share_pct": recovery_positive / total_recovery_positive * 100 if total_recovery_positive else 0.0,
            }
        )
    return rows


def concentration_summary_row(variant: str, symbol_rows: List[dict]) -> dict:
    sorted_all = sorted(symbol_rows, key=lambda row: row["positive_pnl_share_pct"], reverse=True)
    sorted_recovery = sorted(symbol_rows, key=lambda row: row["recovery_positive_pnl_share_pct"], reverse=True)
    top1 = sorted_all[0] if sorted_all else {}
    top2_share = sum(row["positive_pnl_share_pct"] for row in sorted_all[:2])
    recovery_top1 = sorted_recovery[0] if sorted_recovery else {}
    return {
        "analysis_type": "summary",
        "variant": variant,
        "top1_symbol": top1.get("symbol", ""),
        "top1_positive_pnl_share_pct": top1.get("positive_pnl_share_pct", 0.0),
        "top2_positive_pnl_share_pct": top2_share,
        "recovery_top1_symbol": recovery_top1.get("symbol", ""),
        "recovery_top1_positive_pnl_share_pct": recovery_top1.get("recovery_positive_pnl_share_pct", 0.0),
        "concentration_fail": bool(
            (top1.get("positive_pnl_share_pct", 0.0) > 35.0)
            or top2_share > 55.0
            or recovery_top1.get("recovery_positive_pnl_share_pct", 0.0) > 40.0
        ),
    }


def build_cost_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict, specs: List[VariantSpec]) -> List[dict]:
    rows = []
    by_multiplier_v0 = {}
    for multiplier in COST_MULTIPLIERS:
        for spec in specs:
            run = run_spec(data, funding_index, short_index, spec, (), BASE_FEE * multiplier, BASE_SLIPPAGE * multiplier)
            row = metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
            row.update(
                {
                    "variant": spec.name,
                    "cost_multiplier": multiplier,
                    "fee_rate_pct": BASE_FEE * multiplier * 100,
                    "slippage_rate_pct": BASE_SLIPPAGE * multiplier * 100,
                }
            )
            if spec.is_v0:
                by_multiplier_v0[multiplier] = row
            rows.append(row)
    for row in rows:
        v0 = by_multiplier_v0[row["cost_multiplier"]]
        row["return_vs_v0_pct_point"] = row["total_return_pct"] - v0["total_return_pct"]
        row["calmar_vs_v0"] = (row.get("calmar") or 0.0) - (v0.get("calmar") or 0.0)
        row["mdd_extra_vs_v0_pct_point"] = abs(row["mdd_pct"]) - abs(v0["mdd_pct"])
    return rows


def yearly_rows_for_run(run: dict) -> List[dict]:
    rows = []
    for year in TARGET_YEARS:
        start = rec92_audit.ts(f"{year}-01-01T00:00:00+00:00")
        end = rec92_audit.ts(f"{year + 1}-01-01T00:00:00+00:00")
        row = metrics(run, start, end)
        row.update({"variant": run["variant"], "year": year})
        rows.append(row)
    return rows


def apply_status(
    summary_rows: List[dict],
    leave_rows: List[dict],
    concentration_rows: List[dict],
    cost_rows: List[dict],
    regime_rows: List[dict],
) -> None:
    summary_by_variant = {row["variant"]: row for row in summary_rows}
    v0 = summary_by_variant["V0_BASELINE"]
    concentration = {row["variant"]: row for row in concentration_rows if row.get("analysis_type") == "summary"}
    cost_lookup = {(row["variant"], row["cost_multiplier"]): row for row in cost_rows}
    regime_lookup = {(row["variant"], row["market_state"]): row for row in regime_rows}
    leave_lookup = {(row["variant"], row["excluded_symbols"]): row for row in leave_rows}

    for row in summary_rows:
        variant = row["variant"]
        if variant == "V0_BASELINE":
            row["audit_status"] = "BASELINE"
            row["audit_reasons"] = "baseline"
            continue
        fail = []
        watch = []
        if row["total_return_pct"] <= v0["total_return_pct"] or (row.get("cagr_pct") or 0.0) <= (v0.get("cagr_pct") or 0.0):
            fail.append("base return/CAGR not above V0")
        if row["mdd_extra_vs_v0_pct_point"] > 3.0:
            fail.append("MDD worse than V0 by >3pp")
        for excluded in ("SOL", "BNB"):
            leave = leave_lookup.get((variant, excluded), {})
            if (leave.get("calmar_vs_v0_same_exclusion") or -999.0) <= 0:
                fail.append(f"{excluded} removal Calmar <= V0")
            elif (leave.get("return_vs_v0_same_exclusion_pct_point") or 0.0) < 100:
                watch.append(f"{excluded} removal edge weakened")
        pair = leave_lookup.get((variant, "SOL+BNB"), {})
        if pair and (pair.get("return_vs_v0_same_exclusion_pct_point") or 0.0) <= 0:
            fail.append("SOL+BNB removal return <= V0")
        for state in ("bear", "sideways"):
            state_row = regime_lookup.get((variant, state), {})
            v0_state = regime_lookup.get(("V0_BASELINE", state), {})
            if state_row.get("pnl_pct", 0.0) < v0_state.get("pnl_pct", 0.0):
                fail.append(f"{state} PnL worse than V0")
        cost_2x = cost_lookup.get((variant, 2), {})
        if (cost_2x.get("return_vs_v0_pct_point") or -999.0) <= 0 or (cost_2x.get("calmar_vs_v0") or -999.0) <= 0:
            fail.append("2x fee/slippage <= V0")
        if concentration.get(variant, {}).get("concentration_fail"):
            fail.append("symbol contribution over concentration limit")
        for multiplier in (3, 5):
            stress = cost_lookup.get((variant, multiplier), {})
            if stress and stress.get("total_return_pct", 0.0) < 0:
                watch.append(f"{multiplier}x cost stress weak")
        if fail:
            row["audit_status"] = "FAIL"
            row["audit_reasons"] = "; ".join(fail + watch)
        elif watch:
            row["audit_status"] = "WATCH"
            row["audit_reasons"] = "; ".join(watch)
        else:
            row["audit_status"] = "PASS"
            row["audit_reasons"] = "meets diversified robustness thresholds"


def build_report(
    summary_rows: List[dict],
    leave_rows: List[dict],
    concentration_rows: List[dict],
    cost_rows: List[dict],
    yearly_rows: List[dict],
    regime_rows: List[dict],
    paths: Dict[str, Path],
) -> str:
    diversified_summary = [row for row in summary_rows if row["group"] == "diversified"]
    focus_leave = [row for row in leave_rows if row["variant"] in {item["variant"] for item in diversified_summary} and row["excluded_symbols"] in {"SOL", "BNB", "SOL+BNB"}]
    concentration_summary = [row for row in concentration_rows if row.get("analysis_type") == "summary"]
    lines = [
        "# V4H Diversified Robustness Report",
        "",
        "## Scope",
        "",
        "- Read-only audit/report only. Strategy modules, paper engine, live order logic, main checkout/merge, commit, and push were not touched.",
        "- Existing `V4H_STRICT_REC92_25` robustness FAIL is preserved as-is; this audit writes only `v4h_diversified_*` outputs.",
        f"- Diversification cap used in this audit: existing same-symbol simultaneous position limit = 1, plus rolling 30D max {DIVERSIFIED_MAX_ENTRIES_30D} new entries per symbol for diversified variants.",
        "- Concentration failure thresholds: top1 positive PnL share > 35%, top2 positive PnL share > 55%, or recovery top1 positive PnL share > 40%.",
        "",
        "## PASS/WATCH/FAIL",
        "",
        markdown_table(
            ["Variant", "Status", "Reasons", "Return", "CAGR", "MDD", "Calmar", "PF", "Trades", "Top1", "Top2", "Recovery top1"],
            [
                {
                    **row,
                    **concentration_summary_for(row["variant"], concentration_summary),
                }
                for row in summary_rows
            ],
            ["variant", "audit_status", "audit_reasons", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "profit_factor", "trade_count", "top1_positive_pnl_share_pct", "top2_positive_pnl_share_pct", "recovery_top1_positive_pnl_share_pct"],
        ),
        "",
        "## Diversified Candidates",
        "",
        markdown_table(
            ["Variant", "Return vs V0", "MDD extra vs V0", "Calmar vs V0", "Trades vs REC92_25", "MDD vs REC92_25", "Calmar vs REC92_25"],
            diversified_summary,
            ["variant", "return_vs_v0_pct_point", "mdd_extra_vs_v0_pct_point", "calmar_vs_v0", "trade_count_vs_rec92_25", "mdd_change_vs_rec92_25_pct_point", "calmar_change_vs_rec92_25"],
        ),
        "",
        "## Leave-SOL/BNB-Out",
        "",
        markdown_table(
            ["Variant", "Excluded", "Return", "Calmar", "Return vs V0 same exclusion", "Calmar vs V0 same exclusion", "Return delta vs full"],
            focus_leave,
            ["variant", "excluded_symbols", "total_return_pct", "calmar", "return_vs_v0_same_exclusion_pct_point", "calmar_vs_v0_same_exclusion", "return_delta_vs_full_pct_point"],
        ),
        "",
        "## Symbol Concentration",
        "",
        markdown_table(
            ["Variant", "Top1 symbol", "Top1 share", "Top2 share", "Recovery top1 symbol", "Recovery top1 share", "Fail"],
            concentration_summary,
            ["variant", "top1_symbol", "top1_positive_pnl_share_pct", "top2_positive_pnl_share_pct", "recovery_top1_symbol", "recovery_top1_positive_pnl_share_pct", "concentration_fail"],
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
        "## Yearly OOS",
        "",
        markdown_table(
            ["Variant", "Year", "Return", "CAGR", "MDD", "Calmar", "PF", "Win", "Trades"],
            yearly_rows,
            ["variant", "year", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "profit_factor", "win_rate_pct", "trade_count"],
        ),
        "",
        "## Bull / Bear / Sideways",
        "",
        markdown_table(
            ["Variant", "State", "PnL", "PF", "Win", "Trades", "Avg R"],
            regime_rows,
            ["variant", "market_state", "pnl_pct", "profit_factor", "win_rate_pct", "trade_count", "average_r"],
        ),
        "",
        "## Output Files",
        "",
    ]
    for key in ("report", "summary", "leave", "concentration", "cost", "yearly", "regime"):
        lines.append(f"- `{paths[key].relative_to(ROOT)}`")
    lines.append("")
    return "\n".join(lines)


def concentration_summary_for(variant: str, rows: List[dict]) -> dict:
    for row in rows:
        if row["variant"] == variant:
            return row
    return {}


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
    if isinstance(value, bool):
        return "true" if value else "false"
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
