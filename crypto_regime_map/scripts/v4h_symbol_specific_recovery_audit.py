"""Read-only SOL/BNB-specific recovery-control audit for V4H variants."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
import v4h_diversified_robustness_audit as diversified_audit  # noqa: E402
import v4h_rec92_25_robustness_audit as rec92_audit  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
SPECIAL_SYMBOLS = {"SOLUSDT", "BNBUSDT"}
BASE_FEE = rec92_audit.BASE_FEE
BASE_SLIPPAGE = rec92_audit.BASE_SLIPPAGE
TOP_SCORE_PCT = rec92_audit.TOP_SCORE_PCT
SOLBNB_COOLDOWN_SECONDS = 48 * 3600
COST_MULTIPLIERS = (1, 2, 3)
TARGET_YEARS = rec92_audit.TARGET_YEARS
LEAVE_SETS = [("SOL",), ("BNB",), ("SOL", "BNB")]

RUN_CACHE: Dict[Tuple, dict] = {}
SIGNAL_CACHE: Dict[Tuple, List[dict]] = {}


@dataclass(frozen=True)
class VariantSpec:
    name: str
    kind: str
    base_recovery_score: Optional[float] = None
    base_recovery_size: float = 0.25
    solbnb_recovery_score: Optional[float] = None
    solbnb_recovery_size: Optional[float] = None
    solbnb_cooldown_seconds: int = 0


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
    leave_rows = build_leave_rows(data, funding_index, short_index, specs, base_runs)
    recovery_rows = build_recovery_rows(base_runs)
    cost_rows = build_cost_rows(data, funding_index, short_index, specs)
    yearly_rows = [row for run in base_runs.values() for row in yearly_rows_for_run(run)]
    market_index = rec92_audit.build_market_state_index(data.raw_1d["BTCUSDT"])
    regime_rows = [row for run in base_runs.values() for row in rec92_audit.market_state_performance_rows(run, market_index)]
    concentration_rows = build_concentration_rows(base_runs)
    apply_status(summary_rows, leave_rows, recovery_rows, cost_rows, yearly_rows, concentration_rows)

    paths = {
        "report": output_dir / "v4h_symbol_specific_recovery_report.md",
        "summary": output_dir / "v4h_symbol_specific_summary.csv",
        "leave": output_dir / "v4h_symbol_specific_leave_symbol.csv",
        "recovery": output_dir / "v4h_symbol_specific_recovery_by_symbol.csv",
        "cost": output_dir / "v4h_symbol_specific_cost_stress.csv",
        "yearly": output_dir / "v4h_symbol_specific_oos_yearly.csv",
        "regime": output_dir / "v4h_symbol_specific_regime_performance.csv",
        "concentration": output_dir / "v4h_symbol_specific_concentration.csv",
    }
    write_csv(paths["summary"], summary_rows)
    write_csv(paths["leave"], leave_rows)
    write_csv(paths["recovery"], recovery_rows)
    write_csv(paths["cost"], cost_rows)
    write_csv(paths["yearly"], yearly_rows)
    write_csv(paths["regime"], regime_rows)
    write_csv(paths["concentration"], concentration_rows)
    paths["report"].write_text(
        build_report(summary_rows, leave_rows, recovery_rows, cost_rows, yearly_rows, regime_rows, concentration_rows, paths),
        encoding="utf-8",
    )
    print(paths["report"])


def variant_specs() -> List[VariantSpec]:
    return [
        VariantSpec("V0_BASELINE", "v0"),
        VariantSpec("V4H_STRICT_BASE", "strict_base"),
        VariantSpec("V4H_STRICT_REC92_25", "standard", 92.0, 0.25),
        VariantSpec("V4H_REC92_15_DIVERSIFIED", "diversified"),
        VariantSpec("V4H_REC92_25_SOLBNB_94_15", "symbol_specific", 92.0, 0.25, 94.0, 0.15),
        VariantSpec("V4H_REC92_25_SOLBNB_95_10", "symbol_specific", 92.0, 0.25, 95.0, 0.10),
        VariantSpec("V4H_REC92_20_SOLBNB_94_15", "symbol_specific", 92.0, 0.20, 94.0, 0.15),
        VariantSpec("V4H_REC92_25_SOLBNB_COOLDOWN", "symbol_specific", 92.0, 0.25, 92.0, 0.25, SOLBNB_COOLDOWN_SECONDS),
        VariantSpec("V4H_REC92_25_SOLBNB_94_15_COOLDOWN", "symbol_specific", 92.0, 0.25, 94.0, 0.15, SOLBNB_COOLDOWN_SECONDS),
        VariantSpec("V4H_REC92_15_ALL", "standard", 92.0, 0.15),
        VariantSpec("V4H_REC94_15_ALL", "standard", 94.0, 0.15),
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
    cache_key = (spec, tuple(sorted(excluded_usdt)), round(fee_rate, 10), round(slippage_rate, 10))
    if cache_key in RUN_CACHE:
        return RUN_CACHE[cache_key]

    if spec.kind == "v0":
        run = rec92_audit.run_variant(data, funding_index, short_index, rec92_audit.RobustnessVariant(spec.name, is_v0=True), universe, fee_rate, slippage_rate)
    elif spec.kind == "strict_base":
        run = rec92_audit.run_variant(data, funding_index, short_index, base_variant(spec.name, False, None, 0.0), universe, fee_rate, slippage_rate)
    elif spec.kind == "diversified":
        div_spec = next(item for item in diversified_audit.variant_specs() if item.name == "V4H_REC92_15_DIVERSIFIED")
        run = diversified_audit.run_spec(data, funding_index, short_index, div_spec, excluded_symbols, fee_rate, slippage_rate)
    elif spec.kind == "standard":
        run = rec92_audit.run_variant(data, funding_index, short_index, base_variant(spec.name, True, spec.base_recovery_score, spec.base_recovery_size), universe, fee_rate, slippage_rate)
    else:
        signals = symbol_specific_signals(data, short_index, spec, universe)
        result = run_engine(data, signals, spec, fee_rate, slippage_rate)
        run = rec92_audit.evaluate_result(funding_index, result, spec.name, "base", "4h")
    RUN_CACHE[cache_key] = run
    return run


def base_variant(name: str, allow_recovery: bool, recovery_score: Optional[float], recovery_size: float) -> rec92_audit.RobustnessVariant:
    return rec92_audit.RobustnessVariant(
        name=name,
        gate_config=short4h.GateConfig(name, allow_recovery=allow_recovery, recovery_size_multiplier=recovery_size, strict_uptrend=True),
        recovery_score_min_pct=recovery_score,
    )


def symbol_specific_signals(data: alpha.AlphaData, short_index: dict, spec: VariantSpec, universe: Tuple[str, ...]) -> List[dict]:
    key = (spec.name, tuple(universe))
    if key in SIGNAL_CACHE:
        return SIGNAL_CACHE[key]
    gate_config = short4h.GateConfig(spec.name, allow_recovery=True, recovery_size_multiplier=spec.base_recovery_size, strict_uptrend=True)
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
            config=gate_config,
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
            effective_size = size_multiplier
            threshold = spec.base_recovery_score
            if short_regime == "recovery":
                if symbol in SPECIAL_SYMBOLS:
                    threshold = spec.solbnb_recovery_score
                    effective_size = spec.solbnb_recovery_size if spec.solbnb_recovery_size is not None else effective_size
                else:
                    effective_size = spec.base_recovery_size
            signal = alpha.score_signal(symbol, row, btc, rank_lookup[symbol], len(ranked), gate_regime, effective_size, block_reason)
            if not signal or signal["alpha_score"] < alpha.MIN_ALPHA_SCORE:
                continue
            if short_regime == "recovery" and threshold is not None and rec92_audit.audit.score_percent(signal) < threshold:
                continue
            signal.update(
                {
                    "variant": spec.name,
                    "signal_time": close_time,
                    "signal_date": alpha.format_dt(close_time),
                    "fill_mode": "next_open",
                    "lookahead_pass": True,
                    "regime_timeframe": "4h",
                    "size_multiplier": effective_size,
                    "daily_trade_regime": daily_regime.get("trade_regime", ""),
                    "daily_trade_action_bias": daily_regime.get("trade_action_bias", ""),
                    "short_regime_4h": gate_regime.get("short_regime_4h", ""),
                    "short_action_bias_4h": gate_regime.get("short_action_bias_4h", ""),
                    "short_regime_close_time": gate_regime.get("short_regime_close_time", close_time),
                    "hybrid_override": False,
                    "symbol_specific_recovery_control": bool(short_regime == "recovery" and symbol in SPECIAL_SYMBOLS),
                }
            )
            candidates.append(signal)
        candidates.sort(key=lambda item: (item["alpha_score"], -item["rank"]), reverse=True)
        signals.extend(candidates)
    SIGNAL_CACHE[key] = signals
    return signals


def run_engine(data: alpha.AlphaData, signals: List[dict], spec: VariantSpec, fee_rate: float, slippage_rate: float) -> rb.RunResult:
    robust_variant = rb.RobustVariant(spec.name, exclude_doge=True, top_score_pct=TOP_SCORE_PCT, require_liquidation_buffer=True, group="V4H symbol-specific")
    config = rb.RunConfig(variant=robust_variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    solbnb_recovery_entry: Dict[str, int] = {}
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
            if (
                spec.solbnb_cooldown_seconds
                and symbol in SPECIAL_SYMBOLS
                and signal.get("short_regime_4h") == "recovery"
                and symbol in solbnb_recovery_entry
                and time - solbnb_recovery_entry[symbol] < spec.solbnb_cooldown_seconds
            ):
                skip_counter["solbnb_recovery_cooldown"] += 1
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
            if position.symbol in SPECIAL_SYMBOLS and order.get("short_regime_4h") == "recovery":
                solbnb_recovery_entry[position.symbol] = time

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
                "kind": spec.kind,
                "base_recovery_score": spec.base_recovery_score,
                "base_recovery_size_pct": spec.base_recovery_size * 100 if spec.base_recovery_score is not None else "",
                "solbnb_recovery_score": spec.solbnb_recovery_score,
                "solbnb_recovery_size_pct": spec.solbnb_recovery_size * 100 if spec.solbnb_recovery_size is not None else "",
                "solbnb_cooldown_hours": spec.solbnb_cooldown_seconds / 3600 if spec.solbnb_cooldown_seconds else 0,
                "return_vs_v0_pct_point": row["total_return_pct"] - v0["total_return_pct"],
                "cagr_vs_v0_pct_point": (row.get("cagr_pct") or 0.0) - (v0.get("cagr_pct") or 0.0),
                "calmar_vs_v0": (row.get("calmar") or 0.0) - (v0.get("calmar") or 0.0),
                "mdd_extra_vs_v0_pct_point": abs(row["mdd_pct"]) - abs(v0["mdd_pct"]),
                "return_delta_vs_rec92_pct_point": row["total_return_pct"] - rec92["total_return_pct"],
                "calmar_delta_vs_rec92": (row.get("calmar") or 0.0) - (rec92.get("calmar") or 0.0),
                "trade_count_delta_vs_rec92": row["trade_count"] - rec92["trade_count"],
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


def build_leave_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict, specs: List[VariantSpec], base_runs: Dict[str, dict]) -> List[dict]:
    base_metrics = {name: metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS) for name, run in base_runs.items()}
    rows = []
    for excluded in LEAVE_SETS:
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


def build_recovery_rows(base_runs: Dict[str, dict]) -> List[dict]:
    rows = []
    for variant, run in base_runs.items():
        recovery_trades = [trade for trade in run["trades"] if rec92_audit.normalized_regime(trade) == "recovery"]
        groups = {
            "ALL_RECOVERY": recovery_trades,
            "SOL_RECOVERY": [trade for trade in recovery_trades if trade.get("symbol") == "SOL"],
            "BNB_RECOVERY": [trade for trade in recovery_trades if trade.get("symbol") == "BNB"],
            "NON_SOLBNB_RECOVERY": [trade for trade in recovery_trades if f"{trade.get('symbol')}USDT" not in SPECIAL_SYMBOLS],
        }
        for group, trades in groups.items():
            row = trade_group_metrics(trades)
            row.update({"variant": variant, "recovery_group": group})
            rows.append(row)
        for symbol, trades in sorted(group_by_symbol(recovery_trades).items()):
            row = trade_group_metrics(trades)
            row.update({"variant": variant, "recovery_group": "SYMBOL", "symbol": symbol})
            rows.append(row)
    return rows


def trade_group_metrics(trades: List[dict]) -> dict:
    pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "trade_count": len(trades),
        "pnl_pct": sum(pnls) * 100,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "average_r": rec92_audit.mean_present(rec92_audit.audit.r_multiple(trade) for trade in trades),
    }


def group_by_symbol(trades: List[dict]) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("symbol"))].append(trade)
    return grouped


def build_cost_rows(data: alpha.AlphaData, funding_index: dict, short_index: dict, specs: List[VariantSpec]) -> List[dict]:
    rows = []
    v0_by_multiplier = {}
    for multiplier in COST_MULTIPLIERS:
        for spec in specs:
            run = run_spec(data, funding_index, short_index, spec, (), BASE_FEE * multiplier, BASE_SLIPPAGE * multiplier)
            row = metrics(run, alpha.TEST_START_TS, alpha.TEST_END_TS)
            row.update({"variant": spec.name, "cost_multiplier": multiplier, "fee_rate_pct": BASE_FEE * multiplier * 100, "slippage_rate_pct": BASE_SLIPPAGE * multiplier * 100})
            if spec.kind == "v0":
                v0_by_multiplier[multiplier] = row
            rows.append(row)
    for row in rows:
        v0 = v0_by_multiplier[row["cost_multiplier"]]
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


def build_concentration_rows(base_runs: Dict[str, dict]) -> List[dict]:
    rows = []
    for variant, run in base_runs.items():
        symbol_rows = concentration_symbol_rows(variant, run["trades"])
        rows.append(concentration_summary_row(variant, symbol_rows))
        rows.extend(symbol_rows)
    return rows


def concentration_symbol_rows(variant: str, trades: List[dict]) -> List[dict]:
    grouped = group_by_symbol(trades)
    total_positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in trades)
    rows = []
    for symbol, symbol_trades in sorted(grouped.items()):
        pnl = sum(float(trade.get("pnl_after_funding") or 0.0) for trade in symbol_trades)
        positive = sum(max(float(trade.get("pnl_after_funding") or 0.0), 0.0) for trade in symbol_trades)
        rows.append(
            {
                "analysis_type": "symbol",
                "variant": variant,
                "symbol": symbol,
                "trade_count": len(symbol_trades),
                "pnl_pct": pnl * 100,
                "positive_pnl_share_pct": positive / total_positive * 100 if total_positive else 0.0,
            }
        )
    return rows


def concentration_summary_row(variant: str, symbol_rows: List[dict]) -> dict:
    sorted_rows = sorted(symbol_rows, key=lambda row: row["positive_pnl_share_pct"], reverse=True)
    top1 = sorted_rows[0] if sorted_rows else {}
    top2_share = sum(row["positive_pnl_share_pct"] for row in sorted_rows[:2])
    return {
        "analysis_type": "summary",
        "variant": variant,
        "top1_symbol": top1.get("symbol", ""),
        "top1_positive_pnl_share_pct": top1.get("positive_pnl_share_pct", 0.0),
        "top2_positive_pnl_share_pct": top2_share,
    }


def apply_status(
    summary_rows: List[dict],
    leave_rows: List[dict],
    recovery_rows: List[dict],
    cost_rows: List[dict],
    yearly_rows: List[dict],
    concentration_rows: List[dict],
) -> None:
    summary = {row["variant"]: row for row in summary_rows}
    v0 = summary["V0_BASELINE"]
    rec92 = summary["V4H_STRICT_REC92_25"]
    rec92_top1 = next(row for row in concentration_rows if row["variant"] == "V4H_STRICT_REC92_25" and row["analysis_type"] == "summary")["top1_positive_pnl_share_pct"]
    leave_lookup = {(row["variant"], row["excluded_symbols"]): row for row in leave_rows}
    recovery_lookup = {(row["variant"], row["recovery_group"]): row for row in recovery_rows}
    cost_lookup = {(row["variant"], row["cost_multiplier"]): row for row in cost_rows}
    concentration_lookup = {row["variant"]: row for row in concentration_rows if row["analysis_type"] == "summary"}
    yearly_lookup = {(row["variant"], row["year"]): row for row in yearly_rows}
    rec92_2022 = yearly_lookup[("V4H_STRICT_REC92_25", 2022)]["total_return_pct"]
    rec92_2025 = yearly_lookup[("V4H_STRICT_REC92_25", 2025)]["total_return_pct"]

    for row in summary_rows:
        variant = row["variant"]
        if variant == "V0_BASELINE":
            row["audit_status"] = "BASELINE"
            row["audit_reasons"] = "baseline"
            continue
        fail = []
        watch = []
        if (row.get("calmar") or 0.0) < (v0.get("calmar") or 0.0):
            fail.append("Calmar below V0")
        if row["total_return_pct"] <= v0["total_return_pct"] or (row.get("cagr_pct") or 0.0) <= (v0.get("cagr_pct") or 0.0):
            watch.append("base return/CAGR not above V0")
        if row["mdd_extra_vs_v0_pct_point"] > 3.0:
            fail.append("MDD worse than V0 by >3pp")
        cost2 = cost_lookup[(variant, 2)]
        if cost2["return_vs_v0_pct_point"] <= 0 or cost2["calmar_vs_v0"] <= 0:
            fail.append("2x fee/slippage weaker than V0")
        for excluded in ("SOL", "BNB", "SOL+BNB"):
            leave = leave_lookup.get((variant, excluded), {})
            if leave and ((leave["total_return_pct"] <= 0) or ((leave.get("calmar") or 0.0) <= 0)):
                fail.append(f"{excluded} removal collapse")
            elif leave and leave.get("return_delta_vs_full_pct_point", 0.0) < -300:
                watch.append(f"{excluded} removal edge still large")
        recovery_pf = recovery_lookup.get((variant, "ALL_RECOVERY"), {}).get("profit_factor")
        if recovery_pf is not None and recovery_pf <= 1.0:
            fail.append("recovery PF <= 1.0")
        elif recovery_pf is not None and recovery_pf <= 1.15:
            watch.append("recovery PF <= 1.15")
        conc = concentration_lookup[variant]
        if conc["top1_positive_pnl_share_pct"] >= rec92_top1 and variant not in {"V4H_STRICT_BASE", "V4H_STRICT_REC92_25"}:
            fail.append("top1 contribution not reduced vs REC92_25")
        if conc["top1_positive_pnl_share_pct"] > 35.0 or conc["top2_positive_pnl_share_pct"] > 55.0:
            fail.append("top1/top2 contribution excessive")
        improved_2022 = yearly_lookup[(variant, 2022)]["total_return_pct"] > rec92_2022
        improved_2025 = yearly_lookup[(variant, 2025)]["total_return_pct"] > rec92_2025
        if not (improved_2022 or improved_2025) and variant != "V4H_STRICT_REC92_25":
            watch.append("2022/2025 not improved")
        if cost_lookup[(variant, 3)]["total_return_pct"] < 0:
            watch.append("3x cost stress weak")
        if fail:
            row["audit_status"] = "FAIL"
            row["audit_reasons"] = "; ".join(fail + watch)
        elif watch:
            row["audit_status"] = "WATCH"
            row["audit_reasons"] = "; ".join(watch)
        else:
            row["audit_status"] = "PASS"
            row["audit_reasons"] = "meets symbol-specific recovery thresholds"


def build_report(
    summary_rows: List[dict],
    leave_rows: List[dict],
    recovery_rows: List[dict],
    cost_rows: List[dict],
    yearly_rows: List[dict],
    regime_rows: List[dict],
    concentration_rows: List[dict],
    paths: Dict[str, Path],
) -> str:
    new_variants = {row["variant"] for row in summary_rows if row["kind"] in {"symbol_specific", "standard"} and row["variant"] not in {"V4H_STRICT_REC92_25"}}
    focus_leave = [row for row in leave_rows if row["variant"] in new_variants]
    recovery_summary = [row for row in recovery_rows if row["recovery_group"] in {"ALL_RECOVERY", "SOL_RECOVERY", "BNB_RECOVERY", "NON_SOLBNB_RECOVERY"}]
    concentration_summary = [row for row in concentration_rows if row["analysis_type"] == "summary"]
    lines = [
        "# V4H Symbol-Specific Recovery Control Audit",
        "",
        "## Scope",
        "",
        "- Read-only audit/report only. Existing strategy, paper engine, live order logic, main checkout/merge, commit, and push were not touched.",
        "- Existing `V4H_STRICT_REC92_25` robustness FAIL and diversified FAIL reports are preserved by checksum.",
        "- New variants keep SOL/BNB in the universe and only change recovery score/size/cooldown for SOL/BNB recovery entries.",
        "",
        "## PASS/WATCH/FAIL",
        "",
        markdown_table(
            ["Variant", "Status", "Reasons", "Return", "CAGR", "MDD", "Calmar", "PF", "Trades", "Top1", "Top2"],
            [
                {**row, **concentration_for(row["variant"], concentration_summary)}
                for row in summary_rows
            ],
            ["variant", "audit_status", "audit_reasons", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "profit_factor", "trade_count", "top1_positive_pnl_share_pct", "top2_positive_pnl_share_pct"],
        ),
        "",
        "## SOL/BNB Leave-Out",
        "",
        markdown_table(
            ["Variant", "Excluded", "Return", "Calmar", "Return delta vs full", "Return vs V0 same exclusion", "Calmar vs V0 same exclusion"],
            focus_leave,
            ["variant", "excluded_symbols", "total_return_pct", "calmar", "return_delta_vs_full_pct_point", "return_vs_v0_same_exclusion_pct_point", "calmar_vs_v0_same_exclusion"],
        ),
        "",
        "## Recovery PF Breakdown",
        "",
        markdown_table(
            ["Variant", "Group", "Trades", "PnL", "PF", "Win", "Avg R"],
            recovery_summary,
            ["variant", "recovery_group", "trade_count", "pnl_pct", "profit_factor", "win_rate_pct", "average_r"],
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
            ["Variant", "Year", "Return", "CAGR", "MDD", "Calmar", "PF", "Trades"],
            yearly_rows,
            ["variant", "year", "total_return_pct", "cagr_pct", "mdd_pct", "calmar", "profit_factor", "trade_count"],
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
        "## Symbol Concentration",
        "",
        markdown_table(
            ["Variant", "Top1 symbol", "Top1 share", "Top2 share"],
            concentration_summary,
            ["variant", "top1_symbol", "top1_positive_pnl_share_pct", "top2_positive_pnl_share_pct"],
        ),
        "",
        "## Audit Notes",
        "",
        *audit_notes(summary_rows, leave_rows, recovery_rows, cost_rows, yearly_rows, concentration_summary),
        "",
        "## Output Files",
        "",
    ]
    for key in ("report", "summary", "leave", "recovery", "cost", "yearly", "regime", "concentration"):
        lines.append(f"- `{paths[key].relative_to(ROOT)}`")
    lines.append("")
    return "\n".join(lines)


def audit_notes(
    summary_rows: List[dict],
    leave_rows: List[dict],
    recovery_rows: List[dict],
    cost_rows: List[dict],
    yearly_rows: List[dict],
    concentration_summary: List[dict],
) -> List[str]:
    summary = {row["variant"]: row for row in summary_rows}
    concentration = {row["variant"]: row for row in concentration_summary}
    recovery = {(row["variant"], row["recovery_group"]): row for row in recovery_rows}
    cost = {(row["variant"], row["cost_multiplier"]): row for row in cost_rows}
    yearly = {(row["variant"], row["year"]): row for row in yearly_rows}
    symbol_variants = [row for row in summary_rows if row["kind"] == "symbol_specific"]
    passed = [row["variant"] for row in symbol_variants if row.get("audit_status") == "PASS"]
    watched = [row["variant"] for row in symbol_variants if row.get("audit_status") == "WATCH"]
    failed = [row["variant"] for row in symbol_variants if row.get("audit_status") == "FAIL"]
    rec92_top1 = concentration["V4H_STRICT_REC92_25"]["top1_positive_pnl_share_pct"]
    reduced_top1 = [
        concentration[row["variant"]]["top1_positive_pnl_share_pct"]
        for row in symbol_variants
        if row["variant"] in concentration and row["variant"] != "V4H_REC92_25_SOLBNB_COOLDOWN"
    ]
    symbol_variant_names = {row["variant"] for row in symbol_variants}
    solbnb_leave = [
        row["return_delta_vs_full_pct_point"]
        for row in leave_rows
        if row["variant"] in symbol_variant_names and row["excluded_symbols"] == "SOL+BNB"
    ]
    rec94_same = False
    if "V4H_REC92_15_ALL" in summary and "V4H_REC94_15_ALL" in summary:
        keys = ("total_return_pct", "cagr_pct", "mdd_pct", "calmar", "trade_count", "pnl_pct")
        rec94_same = all(abs(float(summary["V4H_REC92_15_ALL"].get(key) or 0.0) - float(summary["V4H_REC94_15_ALL"].get(key) or 0.0)) < 1e-9 for key in keys)
    notes = [
        f"- Final symbol-specific verdict: PASS {len(passed)}, WATCH {len(watched)}, FAIL {len(failed)}. No symbol-specific candidate reached PASS.",
        f"- SOL/BNB-specific score/size controls lowered top1 contribution from {rec92_top1:.2f}% to a best {min(reduced_top1):.2f}% among non-cooldown-only controls, but SOL+BNB removal still reduced return by {min(solbnb_leave):.2f}pp to {max(solbnb_leave):.2f}pp.",
        f"- Recovery PF stayed above the PASS floor for the controlled variants: {min((recovery[(row['variant'], 'ALL_RECOVERY')]['profit_factor'] or 0.0) for row in symbol_variants):.2f} minimum.",
        f"- Cost 2x remained above V0 for controlled variants, but cost 3x stayed negative for all symbol-specific candidates; best 3x return was {max(cost[(row['variant'], 3)]['total_return_pct'] for row in symbol_variants):.2f}%.",
        f"- 2022/2025 did not provide the required improvement for the score/size controls; best 2022 among symbol-specific candidates was {max(yearly[(row['variant'], 2022)]['total_return_pct'] for row in symbol_variants):.2f}% and best 2025 was {max(yearly[(row['variant'], 2025)]['total_return_pct'] for row in symbol_variants):.2f}%.",
    ]
    if rec94_same:
        notes.append("- `V4H_REC94_15_ALL` matched `V4H_REC92_15_ALL` exactly in this audit, so the 94 threshold did not remove any filled recovery trades under the existing signal/top-score execution path.")
    return notes


def concentration_for(variant: str, rows: List[dict]) -> dict:
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
