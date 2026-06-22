"""V0 1D regime vs experimental BTC 4H short-regime comparison.

The script is read-only with respect to market data and paper state. It reads
existing cached OHLCV/funding JSON files and writes report artifacts only.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_4h_regime as short4h  # noqa: E402
import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
BASE_FEE = candidate.BASE_FEE
BASE_SLIPPAGE = candidate.BASE_SLIPPAGE
TOP_SCORE_PCT = candidate.TOP_SCORE_PCT if hasattr(candidate, "TOP_SCORE_PCT") else 0.20
ACTUAL_FUNDING = ("actual_funding", "actual funding", "actual")
COST_SCENARIOS = [
    ("base", BASE_FEE, BASE_SLIPPAGE),
    ("fee_2x", BASE_FEE * 2, BASE_SLIPPAGE),
    ("slippage_2x", BASE_FEE, BASE_SLIPPAGE * 2),
    ("fee_2x_slippage_2x", BASE_FEE * 2, BASE_SLIPPAGE * 2),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir)

    raw_1d = load_cached_raw(raw_dir, SYMBOLS, "1d")
    raw_4h = load_cached_raw(raw_dir, SYMBOLS, "4h")
    raw_1h = load_cached_raw(raw_dir, SYMBOLS, "1h")
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})

    short_index = short4h.build_regime_indexes(raw_4h["BTCUSDT"])
    short_rows = [
        row
        for row in short_index["rows"]
        if alpha.TEST_START_TS <= int(row["close_time"]) < alpha.TEST_END_TS
    ]
    funding_index = load_cached_funding_index(raw_dir, SYMBOLS)

    base_runs = [run_v0(data, funding_index, "base", BASE_FEE, BASE_SLIPPAGE)]
    base_runs.extend(
        run_short_variant(data, funding_index, short_index, config, "base", BASE_FEE, BASE_SLIPPAGE)
        for config in short4h.COMPARISON_CONFIGS
    )
    stress_runs = [
        run_v0(data, funding_index, scenario, fee_rate, slippage_rate)
        for scenario, fee_rate, slippage_rate in COST_SCENARIOS
        if scenario != "base"
    ]
    for scenario, fee_rate, slippage_rate in COST_SCENARIOS:
        if scenario == "base":
            continue
        stress_runs.extend(
            run_short_variant(data, funding_index, short_index, config, scenario, fee_rate, slippage_rate)
            for config in short4h.COMPARISON_CONFIGS
        )

    summary_rows = build_summary_rows(base_runs, short_rows)
    monthly_rows = [row for run in base_runs for row in monthly_returns(run)]
    yearly_rows = [row for run in base_runs for row in yearly_returns(run, monthly_returns(run))]
    equity_rows = [row for run in base_runs for row in equity_curve_rows(run)]
    cost_rows = [cost_summary_row(run, short_rows) for run in base_runs + stress_runs]
    regime_stats_rows = [row for run in base_runs for row in regime_trade_stats(run)]
    additional_rows = additional_analysis_rows(base_runs, data, short_rows)

    report_path = output_dir / "alpha_engine_v1_2_4h_regime_comparison.md"
    comparison_path = output_dir / "alpha_engine_v1_2_4h_regime_comparison.csv"
    log_path = output_dir / "alpha_engine_v1_2_4h_regime_log.csv"
    transitions_path = output_dir / "alpha_engine_v1_2_4h_regime_transitions.csv"
    equity_path = output_dir / "alpha_engine_v1_2_4h_regime_equity_1000.csv"
    cost_path = output_dir / "alpha_engine_v1_2_4h_regime_cost_stress.csv"
    monthly_path = output_dir / "alpha_engine_v1_2_4h_regime_monthly_returns.csv"
    yearly_path = output_dir / "alpha_engine_v1_2_4h_regime_yearly_returns.csv"
    regime_stats_path = output_dir / "alpha_engine_v1_2_4h_regime_regime_stats.csv"

    report_path.write_text(build_report(summary_rows, additional_rows, regime_stats_rows), encoding="utf-8")
    write_csv(comparison_path, summary_rows)
    write_csv(log_path, short4h.regime_log_rows(short_rows))
    write_csv(transitions_path, short4h.transition_rows(short_rows))
    write_csv(equity_path, equity_rows)
    write_csv(cost_path, cost_rows)
    write_csv(monthly_path, monthly_rows)
    write_csv(yearly_path, yearly_rows)
    write_csv(regime_stats_path, regime_stats_rows)
    print(report_path)


def load_cached_raw(raw_dir: Path, symbols: Iterable[str], interval: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    missing = []
    for symbol in symbols:
        path = raw_dir / f"{symbol}_{interval}.json"
        if not path.exists():
            missing.append(str(path))
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not rows:
            missing.append(str(path))
            continue
        out[symbol] = rows
    if missing:
        raise FileNotFoundError("missing cached raw data: " + ", ".join(missing[:5]))
    return out


def load_cached_funding_index(raw_dir: Path, symbols: Iterable[str]) -> Dict[str, Tuple[List[int], List[dict]]]:
    info_path = raw_dir / "futures_funding_info.json"
    info_rows = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else []
    info = {row.get("symbol"): row for row in info_rows if row.get("symbol")}
    funding_by_symbol = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}_futures_funding_rate.json"
        if not path.exists():
            funding_by_symbol[symbol] = []
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        interval_hours = info.get(symbol, {}).get("fundingIntervalHours")
        funding_by_symbol[symbol] = funding.normalize_funding_rows(symbol, rows, interval_hours)
    return rb.build_time_index(funding_by_symbol, time_key="funding_time")


def v0_variant() -> rb.RobustVariant:
    return rb.RobustVariant(
        "V0_1D_regime",
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="V0",
    )


def run_v0(data: alpha.AlphaData, funding_index: dict, scenario: str, fee_rate: float, slippage_rate: float) -> dict:
    variant = v0_variant()
    config = rb.RunConfig(variant=variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    result = rb.run_robust_engine(data, config)
    return evaluate_run(data, funding_index, result, variant.name, scenario, "1d")


def run_short_variant(
    data: alpha.AlphaData,
    funding_index: dict,
    short_index: dict,
    gate_config: short4h.GateConfig,
    scenario: str,
    fee_rate: float,
    slippage_rate: float,
) -> dict:
    variant = rb.RobustVariant(
        gate_config.name,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=True,
        group="4H",
    )
    config = rb.RunConfig(variant=variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    result = run_short_regime_engine(data, short_index, gate_config, config)
    return evaluate_run(data, funding_index, result, variant.name, scenario, "4h", gate_config)


def evaluate_run(
    data: alpha.AlphaData,
    funding_index: dict,
    result: rb.RunResult,
    variant_name: str,
    scenario: str,
    regime_timeframe: str,
    gate_config: Optional[short4h.GateConfig] = None,
) -> dict:
    liq_trades = rb.annotate_liquidation(result.trades, result)
    scenario_key, scenario_name, scenario_value = ACTUAL_FUNDING
    trades, cashflows = rb.annotate_funding_fast(liq_trades, funding_index, scenario_key, scenario_name, scenario_value)
    adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    return {
        "variant": variant_name,
        "scenario": scenario,
        "regime_timeframe": regime_timeframe,
        "gate_config": gate_config,
        "config": result.config,
        "result": result,
        "trades": trades,
        "curve": adjusted_curve,
    }


def run_short_regime_engine(
    data: alpha.AlphaData,
    short_index: dict,
    gate_config: short4h.GateConfig,
    config: rb.RunConfig,
) -> rb.RunResult:
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    equity_curve = [{"time": alpha.TEST_START_TS, "date": alpha.format_dt(alpha.TEST_START_TS), "equity": 1.0}]

    signals_by_time = defaultdict(list)
    for signal in build_short_regime_signals(data, short_index, gate_config):
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
                enrich_trade(closed, position)
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
                enrich_trade(trade, position)
                trades.append(trade)

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
        eligible_for_top = [
            signal
            for signal in batch
            if not (config.variant.exclude_doge and signal["symbol"] == "DOGE")
        ]
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
            attach_position_metadata(position, order)
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
            enrich_trade(trade, position)
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": alpha.format_dt(last_time + 3600), "equity": cash})
    return rb.RunResult(config=config, trades=trades, equity_curve=equity_curve, skip_counter=skip_counter)


def build_short_regime_signals(data: alpha.AlphaData, short_index: dict, gate_config: short4h.GateConfig) -> List[dict]:
    if not short_index or not gate_config:
        return []
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
            config=gate_config,
            daily_regime=daily_regime,
            health_gate={"can_probe": True, "block_reason": ""},
        )
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
            signal = alpha.score_signal(symbol, row, btc, rank_lookup[symbol], len(ranked), gate_regime, size_multiplier, block_reason)
            if signal and signal["alpha_score"] >= alpha.MIN_ALPHA_SCORE:
                signal.update(
                    {
                        "variant": gate_config.name,
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
                        "hybrid_override": bool(gate_regime.get("hybrid_override")),
                    }
                )
                candidates.append(signal)
        candidates.sort(key=lambda item: (item["alpha_score"], -item["rank"]), reverse=True)
        signals.extend(candidates)
    return signals


def attach_position_metadata(position: rb.RobustPosition, order: dict) -> None:
    for key in [
        "regime_timeframe",
        "daily_trade_regime",
        "daily_trade_action_bias",
        "short_regime_4h",
        "short_action_bias_4h",
        "short_regime_close_time",
        "hybrid_override",
    ]:
        setattr(position, key, order.get(key, ""))


def enrich_trade(trade: dict, position: rb.RobustPosition) -> None:
    for key in [
        "regime_timeframe",
        "daily_trade_regime",
        "daily_trade_action_bias",
        "short_regime_4h",
        "short_action_bias_4h",
        "short_regime_close_time",
        "hybrid_override",
    ]:
        trade[key] = getattr(position, key, "")


def build_summary_rows(runs: List[dict], short_rows: List[dict]) -> List[dict]:
    base = metrics(runs[0], short_rows)
    rows = []
    for run in runs:
        row = metrics(run, short_rows)
        row["return_vs_v0_pct_point"] = row["total_return_pct"] - base["total_return_pct"]
        row["mdd_vs_v0_pct_point"] = row["mdd_pct"] - base["mdd_pct"]
        rows.append(row)
    return rows


def metrics(run: dict, short_rows: List[dict]) -> dict:
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
    pnls = [float(trade["pnl_after_funding"]) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    state_ratios = {row["short_regime"]: row["state_ratio_pct"] for row in short4h.regime_state_ratios(short_rows)}
    by_regime = trade_counts_by_regime(trades)
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
        "average_r": mean_present(r_multiple(trade) for trade in trades),
        "max_consecutive_losses": max_consecutive_losses(trades),
        "uptrend_entry_count": by_regime.get("uptrend", 0),
        "recovery_entry_count": by_regime.get("recovery", 0),
        "defensive_entry_count": by_regime.get("defensive", 0),
        "risk_off_entry_count": by_regime.get("risk_off", 0),
        "uptrend_state_ratio_pct": state_ratios.get("uptrend", 0.0),
        "recovery_state_ratio_pct": state_ratios.get("recovery", 0.0),
        "defensive_state_ratio_pct": state_ratios.get("defensive", 0.0),
        "risk_off_state_ratio_pct": state_ratios.get("risk_off", 0.0),
        "skipped_trades": sum(run["result"].skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(run["result"].skip_counter.items())),
    }


def cost_summary_row(run: dict, short_rows: List[dict]) -> dict:
    return metrics(run, short_rows)


def monthly_returns(run: dict) -> List[dict]:
    rows = []
    for row in alpha.monthly_returns_from_curve(run["variant"], run["curve"]):
        rows.append(
            {
                "variant": run["variant"],
                "scenario": run["scenario"],
                "month": row["month"],
                "return_pct": row["return_pct"],
            }
        )
    return rows


def yearly_returns(run: dict, monthly: List[dict]) -> List[dict]:
    by_year: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        by_year.setdefault(year, 1.0)
        by_year[year] *= 1 + float(row["return_pct"]) / 100
    return [
        {
            "variant": run["variant"],
            "scenario": run["scenario"],
            "year": year,
            "return_pct": (value - 1) * 100,
        }
        for year, value in sorted(by_year.items())
    ]


def equity_curve_rows(run: dict) -> List[dict]:
    rows = []
    peak = 1000.0
    for point in run["curve"]:
        equity_usd = point["equity"] * 1000
        peak = max(peak, equity_usd)
        rows.append(
            {
                "variant": run["variant"],
                "scenario": run["scenario"],
                "time": point["time"],
                "date": point["date"],
                "equity": point["equity"],
                "equity_usd": equity_usd,
                "drawdown_pct": (equity_usd / peak - 1) * 100 if peak else 0.0,
            }
        )
    return rows


def regime_trade_stats(run: dict) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for trade in run["trades"]:
        regime = str(trade.get("short_regime_4h") or trade.get("trade_regime") or "")
        grouped[regime].append(trade)
    rows = []
    for regime, trades in sorted(grouped.items()):
        pnls = [float(trade.get("pnl_after_funding") or 0.0) for trade in trades]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        rows.append(
            {
                "variant": run["variant"],
                "scenario": run["scenario"],
                "regime": regime,
                "entry_count": len(trades),
                "return_pct": sum(pnls) * 100,
                "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
                "average_r": mean_present(r_multiple(trade) for trade in trades),
            }
        )
    return rows


def additional_analysis_rows(runs: List[dict], data: alpha.AlphaData, short_rows: List[dict]) -> List[dict]:
    transitions = short4h.transition_rows(short_rows)
    defensive_bars = daily_defensive_short_recovery_count(data, short_rows)
    avg_lead = average_4h_lead_hours(data, transitions)
    rows = []
    for run in runs:
        defensive_override_trades = [
            trade
            for trade in run["trades"]
            if str(trade.get("daily_trade_regime")) == "defensive" and str(trade.get("short_regime_4h")) in {"uptrend", "recovery"}
        ]
        fake_recovery_losses = [
            trade
            for trade in run["trades"]
            if str(trade.get("short_regime_4h")) == "recovery" and float(trade.get("pnl_after_funding") or 0.0) < 0
        ]
        rows.append(
            {
                "variant": run["variant"],
                "daily_defensive_short_recovery_or_uptrend_bars": defensive_bars,
                "entries_in_daily_defensive_short_recovery_or_uptrend": len(defensive_override_trades),
                "return_in_daily_defensive_short_recovery_or_uptrend_pct": sum(float(trade.get("pnl_after_funding") or 0.0) for trade in defensive_override_trades) * 100,
                "avg_4h_lead_hours_before_1d_uptrend": avg_lead,
                "fake_recovery_loss_count": len(fake_recovery_losses),
                "short_regime_transition_count": len(transitions),
                "short_regime_whipsaw_count": sum(1 for row in transitions if row.get("whipsaw")),
            }
        )
    return rows


def daily_defensive_short_recovery_count(data: alpha.AlphaData, short_rows: List[dict]) -> int:
    count = 0
    for row in short_rows:
        daily = data.regime_by_date.get(alpha.date_from_ts(int(row["close_time"])), {})
        if daily.get("trade_regime") == "defensive" and row.get("short_regime") in {"uptrend", "recovery"}:
            count += 1
    return count


def average_4h_lead_hours(data: alpha.AlphaData, transitions: List[dict]) -> Optional[float]:
    short_up_times = [
        int(row["transition_time"])
        for row in transitions
        if row.get("to_regime") in {"uptrend", "recovery"}
    ]
    if not short_up_times:
        return None
    daily_items = sorted(data.regime_by_date.items())
    previous = None
    leads = []
    for date, regime in daily_items:
        current = regime.get("trade_regime")
        if current == "uptrend" and previous != "uptrend":
            daily_ts = int(datetime.fromisoformat(f"{date}T00:00:00+00:00").timestamp())
            prior = [time for time in short_up_times if time <= daily_ts]
            if prior:
                leads.append((daily_ts - max(prior)) / 3600)
        previous = current
    return statistics.mean(leads) if leads else None


def trade_counts_by_regime(trades: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for trade in trades:
        regime = str(trade.get("short_regime_4h") or trade.get("trade_regime") or "")
        counts[regime] += 1
    return counts


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


def build_report(summary_rows: List[dict], additional_rows: List[dict], regime_stats_rows: List[dict]) -> str:
    lines = [
        "# Alpha Engine v1.2 4H Regime 비교 리포트",
        "",
        "- V0_1D_regime: 기존 1D trade_regime gate + v1.2 조건(DOGE 제외, alpha_score top 20%, liquidation buffer).",
        "- V4H 계열: BTC 4H close/EMA20/EMA50/EMA200 + volatility shock filter로 신규 진입 gate만 실험.",
        "- 분석 스크립트는 cached raw/funding JSON을 읽고 reports 산출물만 쓴다.",
        "",
        "## Summary",
        "",
        summary_table(summary_rows),
        "",
        "## 추가 분석",
        "",
        additional_table(additional_rows),
        "",
        "## Regime별 성과",
        "",
        regime_table(regime_stats_rows),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_2_4h_regime_comparison.md`",
        "- `alpha_engine_v1_2_4h_regime_comparison.csv`",
        "- `alpha_engine_v1_2_4h_regime_log.csv`",
        "- `alpha_engine_v1_2_4h_regime_transitions.csv`",
        "- `alpha_engine_v1_2_4h_regime_equity_1000.csv`",
        "- `alpha_engine_v1_2_4h_regime_cost_stress.csv`",
        "- `alpha_engine_v1_2_4h_regime_monthly_returns.csv`",
        "- `alpha_engine_v1_2_4h_regime_yearly_returns.csv`",
        "",
    ]
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Variant", "Return", "CAGR", "MDD", "Sharpe", "Sortino", "Calmar", "PF", "Win", "Trades", "Avg R", "Max losses", "Recovery entries", "Return vs V0"]
    keys = [
        "variant",
        "total_return_pct",
        "cagr_pct",
        "mdd_pct",
        "sharpe",
        "sortino",
        "calmar",
        "profit_factor",
        "win_rate_pct",
        "trade_count",
        "average_r",
        "max_consecutive_losses",
        "recovery_entry_count",
        "return_vs_v0_pct_point",
    ]
    return markdown_table(headers, rows, keys)


def additional_table(rows: List[dict]) -> str:
    headers = ["Variant", "1D def + 4H rec/up bars", "Entries", "Return", "Avg lead h", "Fake recovery losses", "Transitions", "Whipsaw"]
    keys = [
        "variant",
        "daily_defensive_short_recovery_or_uptrend_bars",
        "entries_in_daily_defensive_short_recovery_or_uptrend",
        "return_in_daily_defensive_short_recovery_or_uptrend_pct",
        "avg_4h_lead_hours_before_1d_uptrend",
        "fake_recovery_loss_count",
        "short_regime_transition_count",
        "short_regime_whipsaw_count",
    ]
    return markdown_table(headers, rows, keys)


def regime_table(rows: List[dict]) -> str:
    headers = ["Variant", "Regime", "Entries", "Return", "Win", "PF", "Avg R"]
    keys = ["variant", "regime", "entry_count", "return_pct", "win_rate_pct", "profit_factor", "average_r"]
    return markdown_table(headers, rows, keys)


def markdown_table(headers: List[str], rows: List[dict], keys: List[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    percent_keys = {key for key in keys if key.endswith("_pct") or "return" in key or key in {"mdd_pct", "cagr_pct", "win_rate_pct"}}
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
