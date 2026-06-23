"""Offline ML Opportunity hybrid backtest for Alpha Engine v1.2 Candidate.

This report keeps ML disabled for runtime and does not touch paper/live order
paths. It reuses the Candidate v1.2 execution logic, then applies walk-forward
ML Opportunity probabilities at the entry gate only.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_report as v1  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


PREDICTION_PATH = ROOT / "reports" / "research" / "ml_regime_v2_predictions.csv"
OUTPUT_DIR = ROOT / "reports" / "research"
OPPORTUNITY_MODEL = "Random Forest"
SHOCK_MODEL = "Logistic Regression"
BASE_FEE = candidate.BASE_FEE
BASE_SLIPPAGE = candidate.BASE_SLIPPAGE
ACTUAL_FUNDING = candidate.ACTUAL_FUNDING
EQUITY_BASE_USD = 1000.0


@dataclass(frozen=True)
class MlPrediction:
    date: str
    p_opportunity: Optional[float]
    p_shock: Optional[float]
    opportunity_model: str = OPPORTUNITY_MODEL
    shock_model: str = SHOCK_MODEL


@dataclass(frozen=True)
class HybridPolicy:
    name: str
    opportunity_threshold: Optional[float] = None
    size_adjust: bool = False
    shock_soft: bool = False


@dataclass(frozen=True)
class CostScenario:
    name: str
    fee_multiplier: float
    slippage_multiplier: float


@dataclass
class HybridRun:
    policy: HybridPolicy
    scenario: CostScenario
    result: rb.RunResult
    trades: List[dict]
    curve: List[dict]
    monthly: List[dict]
    yearly: List[dict]
    summary: dict


POLICIES = [
    HybridPolicy("V0_EMA_BASELINE"),
    HybridPolicy("ML_OPP_FILTER_60", opportunity_threshold=0.60),
    HybridPolicy("ML_OPP_FILTER_65", opportunity_threshold=0.65),
    HybridPolicy("ML_OPP_FILTER_70", opportunity_threshold=0.70),
    HybridPolicy("ML_OPP_SIZE_ADJUST", size_adjust=True),
    HybridPolicy("ML_OPP_WITH_SHOCK_SOFT", size_adjust=True, shock_soft=True),
]

COST_SCENARIOS = [
    CostScenario("base", 1.0, 1.0),
    CostScenario("cost_2x", 2.0, 1.0),
    CostScenario("slippage_2x", 1.0, 2.0),
    CostScenario("cost_2x_slippage_2x", 2.0, 2.0),
    CostScenario("cost_3x_slippage_3x", 3.0, 3.0),
]

OPPORTUNITY_BINS = [
    ("lt_0_50", None, 0.50),
    ("0_50_0_60", 0.50, 0.60),
    ("0_60_0_65", 0.60, 0.65),
    ("0_65_0_70", 0.65, 0.70),
    ("0_70_0_80", 0.70, 0.80),
    ("0_80_plus", 0.80, None),
]

SHOCK_BINS = [
    ("lt_0_30", None, 0.30),
    ("0_30_0_50", 0.30, 0.50),
    ("0_50_0_70", 0.50, 0.70),
    ("0_70_0_85", 0.70, 0.85),
    ("0_85_plus", 0.85, None),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-path", default=str(PREDICTION_PATH))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    result = generate_report(Path(args.prediction_path), Path(args.output_dir))
    print(result["report_path"])


def generate_report(prediction_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = load_ml_predictions(prediction_path)
    start_time, end_time = prediction_backtest_window(predictions)

    raw_1d = alpha.load_raw(candidate.SYMBOLS, "1d", True, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(candidate.SYMBOLS, "4h", True, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(candidate.SYMBOLS, "1h", True, alpha.FETCH_INTRADAY_START)
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})

    funding_info = funding.load_funding_info(True)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, True, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in candidate.SYMBOLS
    }
    funding_index = rb.build_time_index(funding_by_symbol, time_key="funding_time")

    runs = [
        run_policy(data, funding_index, predictions, policy, scenario, start_time, end_time)
        for scenario in COST_SCENARIOS
        for policy in POLICIES
    ]
    base_runs = [run for run in runs if run.scenario.name == "base"]
    v0 = next(run for run in base_runs if run.policy.name == "V0_EMA_BASELINE")
    trade_attribution = build_trade_attribution(v0.trades)
    probability_bins = build_probability_bins(v0.trades)
    summary_rows = with_v0_deltas([run.summary for run in runs])
    equity_rows = equity_curve_rows(runs)
    cost_stress_rows = cost_stress_rows_from_runs(runs)

    paths = {
        "report": output_dir / "ml_regime_v3_hybrid_backtest_report.md",
        "summary": output_dir / "ml_regime_v3_hybrid_summary.csv",
        "equity": output_dir / "ml_regime_v3_equity_curves.csv",
        "attribution": output_dir / "ml_regime_v3_trade_attribution.csv",
        "cost": output_dir / "ml_regime_v3_cost_stress.csv",
        "bins": output_dir / "ml_regime_v3_probability_bins.csv",
    }
    write_csv(paths["summary"], summary_rows)
    write_csv(paths["equity"], equity_rows)
    write_csv(paths["attribution"], trade_attribution)
    write_csv(paths["cost"], cost_stress_rows)
    write_csv(paths["bins"], probability_bins)

    report = build_report(
        runs=runs,
        summary_rows=summary_rows,
        trade_attribution=trade_attribution,
        probability_bins=probability_bins,
        start_time=start_time,
        end_time=end_time,
        prediction_path=prediction_path,
    )
    paths["report"].write_text(report, encoding="utf-8")
    return {"report_path": paths["report"], "paths": paths, "summary": summary_rows}


def run_policy(
    data: alpha.AlphaData,
    funding_index: Dict[str, Tuple[List[int], List[dict]]],
    predictions: Mapping[str, MlPrediction],
    policy: HybridPolicy,
    scenario: CostScenario,
    start_time: int,
    end_time: int,
) -> HybridRun:
    variant = rb.RobustVariant(
        "Candidate v1.2 / no leverage cap",
        exclude_doge=True,
        top_score_pct=0.20,
        require_liquidation_buffer=True,
        group="Candidate",
    )
    config = rb.RunConfig(
        variant=variant,
        market_data="spot",
        slippage_rate=BASE_SLIPPAGE * scenario.slippage_multiplier,
        fee_rate=BASE_FEE * scenario.fee_multiplier,
    )
    result = run_hybrid_engine(data, config, predictions, policy, start_time, end_time)
    liq_trades = rb.annotate_liquidation(result.trades, result)
    scenario_key, scenario_name, scenario_value = ACTUAL_FUNDING
    trades, cashflows = rb.annotate_funding_fast(liq_trades, funding_index, scenario_key, scenario_name, scenario_value)
    trades = add_trade_metrics(trades, policy, scenario)
    adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    monthly = monthly_returns(policy.name, scenario.name, adjusted_curve, start_time, end_time)
    yearly = yearly_returns(policy.name, scenario.name, monthly)
    summary = make_summary(policy, scenario, config, result, trades, adjusted_curve, start_time, end_time)
    return HybridRun(policy=policy, scenario=scenario, result=result, trades=trades, curve=adjusted_curve, monthly=monthly, yearly=yearly, summary=summary)


def run_hybrid_engine(
    data: alpha.AlphaData,
    config: rb.RunConfig,
    predictions: Mapping[str, MlPrediction],
    policy: HybridPolicy,
    start_time: int,
    end_time: int,
) -> rb.RunResult:
    cash = 1.0
    positions: Dict[str, rb.RobustPosition] = {}
    trades: List[dict] = []
    pending: Dict[str, dict] = {}
    skip_counter: Counter = Counter()
    equity_curve = [{"time": start_time, "date": alpha.format_dt(start_time), "equity": 1.0}]

    signals_by_time = defaultdict(list)
    for signal in data.signals_for(candidate.SYMBOLS, "next_open"):
        if start_time <= int(signal["signal_time"]) < end_time:
            signals_by_time[int(signal["signal_time"])].append({**signal, "variant": config.variant.name})

    times = [time for time in data.times_1h if start_time <= time < end_time]
    for index, time in enumerate(times):
        close_time = time + 3600
        for symbol in list(positions):
            row = data.by_time_1h.get(symbol, {}).get(time)
            if not row:
                continue
            cash, closed = manage_position(data, config, positions[symbol], row, close_time, index, cash)
            if closed:
                trades.append(closed)
                positions.pop(symbol, None)

        if config.variant.max_positions and alpha.is_shock_date(data, alpha.date_from_ts(close_time)):
            for symbol in list(positions):
                row = data.by_time_1h.get(symbol, {}).get(time)
                if not row:
                    continue
                trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), close_time, index, "shock_exit")
                cash += trade.pop("_cash_delta")
                trades.append(trade)

        batch = sorted(signals_by_time.get(time, []), key=lambda item: item["alpha_score"], reverse=True)
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
            if signal.get("regime_reason") == "defensive_reduce_risk":
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
            prediction = prediction_for_fill_time(predictions, time)
            decision = ml_policy_decision(policy, prediction)
            if not decision["allow_entry"]:
                skip_counter[decision["block_reason"]] += 1
                continue
            order = {
                **signal,
                "symbol": symbol,
                "fill_time": time,
                "size_multiplier": decision["size_multiplier"],
                "ml_prediction_date": decision["prediction_date"],
                "ml_p_opportunity": decision["p_opportunity"],
                "ml_p_shock": decision["p_shock"],
                "ml_policy": policy.name,
                "ml_size_multiplier": decision["size_multiplier"],
                "ml_block_reason": "",
                "ml_opportunity_model": OPPORTUNITY_MODEL,
                "ml_shock_model": SHOCK_MODEL,
            }
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
            position.ml_meta = {
                "ml_policy": order["ml_policy"],
                "ml_prediction_date": order["ml_prediction_date"],
                "ml_p_opportunity": order["ml_p_opportunity"],
                "ml_p_shock": order["ml_p_shock"],
                "ml_size_multiplier": order["ml_size_multiplier"],
                "ml_opportunity_model": order["ml_opportunity_model"],
                "ml_shock_model": order["ml_shock_model"],
            }
            cash -= fee
            positions[position.symbol] = position

        equity_curve.append({"time": close_time, "date": alpha.format_dt(close_time), "equity": rb.portfolio_equity(cash, positions, data, time)})

    last_time = times[-1] if times else start_time
    last_index = len(times) - 1
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(last_time)
        if row:
            trade = close_trade(data, config, positions.pop(symbol), row["close"] * (1 - config.slippage_rate), last_time + 3600, last_index, "end_of_test")
            cash += trade.pop("_cash_delta")
            trades.append(trade)
    equity_curve.append({"time": last_time + 3600, "date": alpha.format_dt(last_time + 3600), "equity": cash})
    return rb.RunResult(config=config, trades=trades, equity_curve=equity_curve, skip_counter=skip_counter, probe_log=[])


def manage_position(
    data: alpha.AlphaData,
    config: rb.RunConfig,
    position: rb.RobustPosition,
    row: dict,
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
        position.partial_time = close_time
        position.partial_price = target_price * (1 - config.slippage_rate)
    row_4h = data.by_close_4h.get(position.symbol, {}).get(close_time)
    if row_4h:
        if row_4h.get("ema50") is not None and row_4h["close"] < row_4h["ema50"]:
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema50_exit")
            return cash + trade.pop("_cash_delta"), trade
        if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] < row_4h["ema20"]:
            trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "ema20_trailing_exit")
            return cash + trade.pop("_cash_delta"), trade
    if close_time - position.entry_time >= alpha.MAX_HOLD_HOURS * 3600:
        trade = close_trade(data, config, position, row["close"] * (1 - config.slippage_rate), close_time, index_1h, "max_hold")
        return cash + trade.pop("_cash_delta"), trade
    return cash, None


def close_trade(data: alpha.AlphaData, config: rb.RunConfig, position: rb.RobustPosition, exit_price: float, exit_time: int, index_1h: int, reason: str) -> dict:
    trade = rb.close_trade(data, config, position, exit_price, exit_time, index_1h, reason)
    meta = getattr(position, "ml_meta", {})
    return {
        **trade,
        "ml_policy": meta.get("ml_policy", ""),
        "ml_prediction_date": meta.get("ml_prediction_date", ""),
        "ml_p_opportunity": meta.get("ml_p_opportunity", ""),
        "ml_p_shock": meta.get("ml_p_shock", ""),
        "ml_size_multiplier": meta.get("ml_size_multiplier", ""),
        "ml_opportunity_model": meta.get("ml_opportunity_model", ""),
        "ml_shock_model": meta.get("ml_shock_model", ""),
    }


def load_ml_predictions(path: Path) -> Dict[str, MlPrediction]:
    opportunity: Dict[str, float] = {}
    shock: Dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date = row["date"]
            if row["model"] == OPPORTUNITY_MODEL:
                opportunity[date] = float(row["p_opportunity"]) if row.get("p_opportunity") else None
            if row["model"] == SHOCK_MODEL:
                shock[date] = float(row["p_shock"]) if row.get("p_shock") else None
    dates = sorted(set(opportunity) & set(shock))
    return {date: MlPrediction(date=date, p_opportunity=opportunity[date], p_shock=shock[date]) for date in dates}


def prediction_backtest_window(predictions: Mapping[str, MlPrediction]) -> Tuple[int, int]:
    dates = sorted(predictions)
    if not dates:
        raise RuntimeError("No ML prediction rows found")
    first = datetime.fromisoformat(dates[0]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    last = datetime.fromisoformat(dates[-1]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    start_time = int(first.timestamp())
    end_time = min(alpha.TEST_END_TS, int(last.timestamp()))
    return start_time, end_time


def prediction_for_fill_time(predictions: Mapping[str, MlPrediction], fill_time: int) -> Optional[MlPrediction]:
    prediction_date = datetime.fromtimestamp(fill_time, tz=timezone.utc).date() - timedelta(days=1)
    return predictions.get(prediction_date.isoformat())


def ml_policy_decision(policy: HybridPolicy, prediction: Optional[MlPrediction]) -> dict:
    if prediction is None:
        return {
            "allow_entry": policy.name == "V0_EMA_BASELINE",
            "block_reason": "ml_missing_prediction",
            "size_multiplier": 1.0,
            "prediction_date": "",
            "p_opportunity": "",
            "p_shock": "",
        }

    p_opp = prediction.p_opportunity
    p_shock = prediction.p_shock
    if policy.opportunity_threshold is not None and (p_opp is None or p_opp < policy.opportunity_threshold):
        return _decision(False, "ml_opportunity_below_threshold", 0.0, prediction)

    size = 1.0
    if policy.size_adjust:
        if p_opp is None:
            return _decision(False, "ml_missing_opportunity", 0.0, prediction)
        if p_opp >= 0.70:
            size = 1.0
        elif p_opp >= 0.60:
            size = 0.5
        else:
            size = 0.25
    if policy.shock_soft and p_shock is not None:
        if p_shock >= 0.85:
            size *= 0.25
        elif p_shock >= 0.70:
            size *= 0.5
    return _decision(True, "", size, prediction)


def _decision(allow: bool, reason: str, size: float, prediction: MlPrediction) -> dict:
    return {
        "allow_entry": allow,
        "block_reason": reason,
        "size_multiplier": size,
        "prediction_date": prediction.date,
        "p_opportunity": prediction.p_opportunity if prediction.p_opportunity is not None else "",
        "p_shock": prediction.p_shock if prediction.p_shock is not None else "",
    }


def make_summary(
    policy: HybridPolicy,
    scenario: CostScenario,
    config: rb.RunConfig,
    result: rb.RunResult,
    trades: List[dict],
    curve: List[dict],
    start_time: int,
    end_time: int,
) -> dict:
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = (end_time - start_time) / (365.25 * 86400)
    returns = [curve[index]["equity"] / curve[index - 1]["equity"] - 1 for index in range(1, len(curve)) if curve[index - 1]["equity"] > 0]
    mean_return = statistics.mean(returns) if returns else 0.0
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    downside = [value for value in returns if value < 0]
    downside_stdev = statistics.stdev(downside) if len(downside) > 1 else None
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 and years > 0 else None
    mdd = swing.max_drawdown(curve)
    pnl_values = [float(trade["pnl_after_funding"]) for trade in trades]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    trade_returns = [float(trade["trade_return_after_funding_pct"]) for trade in trades]
    r_values = [trade_r_multiple(trade) for trade in trades]
    r_clean = [value for value in r_values if value is not None]
    return {
        "policy": policy.name,
        "cost_scenario": scenario.name,
        "fee_rate_pct": config.fee_rate * 100,
        "slippage_rate_pct": config.slippage_rate * 100,
        "start_date": alpha.date_from_ts(start_time),
        "end_date": alpha.date_from_ts(end_time),
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": mean_return / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None,
        "sortino": mean_return / downside_stdev * math.sqrt(365 * 24) if downside_stdev and downside_stdev > 0 else None,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "trade_count": len(trades),
        "average_r": statistics.mean(r_clean) if r_clean else None,
        "median_trade_return_pct": statistics.median(trade_returns) if trade_returns else None,
        "max_consecutive_losses": max_consecutive_losses(trades),
        "skipped_trades": sum(result.skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(result.skip_counter.items())),
    }


def add_trade_metrics(trades: List[dict], policy: HybridPolicy, scenario: CostScenario) -> List[dict]:
    out = []
    for trade in trades:
        row = {
            **trade,
            "policy": policy.name,
            "cost_scenario": scenario.name,
            "entry_month": month_from_ts(int(trade["entry_timestamp"])),
            "entry_year": str(datetime.fromtimestamp(int(trade["entry_timestamp"]), tz=timezone.utc).year),
            "ml_opportunity_bin": probability_bin(float_or_none(trade.get("ml_p_opportunity")), OPPORTUNITY_BINS),
            "ml_shock_bin": probability_bin(float_or_none(trade.get("ml_p_shock")), SHOCK_BINS),
            "r_multiple": trade_r_multiple(trade),
        }
        out.append(row)
    return out


def with_v0_deltas(summary_rows: List[dict]) -> List[dict]:
    baselines = {row["cost_scenario"]: row for row in summary_rows if row["policy"] == "V0_EMA_BASELINE"}
    out = []
    for row in summary_rows:
        base = baselines.get(row["cost_scenario"], {})
        out.append(
            {
                **row,
                "v0_total_return_delta_pct": (row["total_return_pct"] - base.get("total_return_pct", 0.0)) if row["policy"] != "V0_EMA_BASELINE" else 0.0,
                "v0_mdd_delta_pct": (row["mdd_pct"] - base.get("mdd_pct", 0.0)) if row["policy"] != "V0_EMA_BASELINE" else 0.0,
                "v0_calmar_delta": ((row["calmar"] or 0.0) - (base.get("calmar") or 0.0)) if row["policy"] != "V0_EMA_BASELINE" else 0.0,
                "v0_trade_count_delta": (row["trade_count"] - base.get("trade_count", 0)) if row["policy"] != "V0_EMA_BASELINE" else 0,
            }
        )
    return out


def build_trade_attribution(v0_trades: List[dict]) -> List[dict]:
    rows = []
    groups = []
    for threshold in (0.60, 0.65, 0.70):
        allowed = [trade for trade in v0_trades if (float_or_none(trade.get("ml_p_opportunity")) or -1.0) >= threshold]
        blocked = [trade for trade in v0_trades if (float_or_none(trade.get("ml_p_opportunity")) or -1.0) < threshold]
        groups.append((f"allowed_by_opp_{threshold:.2f}", allowed))
        groups.append((f"blocked_by_opp_{threshold:.2f}", blocked))
    groups.append(("ema_defensive_high_opportunity", [trade for trade in v0_trades if trade.get("trade_regime") == "defensive" and (float_or_none(trade.get("ml_p_opportunity")) or 0.0) >= 0.60]))
    groups.append(("ema_uptrend_low_opportunity", [trade for trade in v0_trades if trade.get("trade_regime") == "uptrend" and (float_or_none(trade.get("ml_p_opportunity")) or 1.0) < 0.60]))
    for name, trades in groups:
        rows.append(trade_group_stats(name, trades))
    return rows


def build_probability_bins(v0_trades: List[dict]) -> List[dict]:
    rows = []
    for bin_name, low, high in OPPORTUNITY_BINS:
        trades = [trade for trade in v0_trades if in_bin(float_or_none(trade.get("ml_p_opportunity")), low, high)]
        rows.append({**trade_group_stats(f"p_opportunity_{bin_name}", trades), "dimension": "p_opportunity", "bin": bin_name})
    for bin_name, low, high in SHOCK_BINS:
        trades = [trade for trade in v0_trades if in_bin(float_or_none(trade.get("ml_p_shock")), low, high)]
        rows.append({**trade_group_stats(f"p_shock_{bin_name}", trades), "dimension": "p_shock", "bin": bin_name})
    return rows


def trade_group_stats(group: str, trades: List[dict]) -> dict:
    pnls = [float(trade["pnl_after_funding"]) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    returns = [float(trade["trade_return_after_funding_pct"]) for trade in trades]
    return {
        "group": group,
        "trade_count": len(trades),
        "total_pnl": sum(pnls),
        "avg_pnl": statistics.mean(pnls) if pnls else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "median_trade_return_pct": statistics.median(returns) if returns else None,
        "avg_r": statistics.mean([value for value in (trade_r_multiple(trade) for trade in trades) if value is not None]) if trades else None,
    }


def equity_curve_rows(runs: List[HybridRun]) -> List[dict]:
    rows = []
    for run in runs:
        if run.scenario.name != "base":
            continue
        for point in run.curve:
            rows.append(
                {
                    "policy": run.policy.name,
                    "cost_scenario": run.scenario.name,
                    "time": point["time"],
                    "date": point["date"],
                    "equity": point["equity"],
                    "equity_1000_usd": point["equity"] * EQUITY_BASE_USD,
                }
            )
    return rows


def cost_stress_rows_from_runs(runs: List[HybridRun]) -> List[dict]:
    return [run.summary for run in runs]


def monthly_returns(policy: str, scenario: str, curve: List[dict], start_time: int, end_time: int) -> List[dict]:
    month_end: Dict[str, float] = {}
    for point in curve:
        if start_time <= int(point["time"]) <= end_time:
            month_end[month_from_ts(int(point["time"]))] = float(point["equity"])
    months = month_range(month_from_ts(start_time), month_from_ts(end_time - 1))
    rows = []
    previous = 1.0
    for month in months:
        equity = month_end.get(month, previous)
        rows.append({"policy": policy, "cost_scenario": scenario, "month": month, "return_pct": (equity / previous - 1) * 100 if previous else 0.0})
        previous = equity
    return rows


def yearly_returns(policy: str, scenario: str, monthly: List[dict]) -> List[dict]:
    yearly: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + float(row["return_pct"]) / 100
    return [
        {"policy": policy, "cost_scenario": scenario, "year": year, "return_pct": (value - 1) * 100}
        for year, value in sorted(yearly.items())
    ]


def build_report(
    runs: List[HybridRun],
    summary_rows: List[dict],
    trade_attribution: List[dict],
    probability_bins: List[dict],
    start_time: int,
    end_time: int,
    prediction_path: Path,
) -> str:
    base_rows = [row for row in summary_rows if row["cost_scenario"] == "base"]
    stress_rows = [row for row in summary_rows if row["cost_scenario"] in {"cost_2x_slippage_2x", "cost_3x_slippage_3x"}]
    verdict, reasons = pass_watch_fail(base_rows, summary_rows, trade_attribution)
    best_hybrid = best_hybrid_row(base_rows)
    v0 = next(row for row in base_rows if row["policy"] == "V0_EMA_BASELINE")
    lines = [
        "# ML Regime v3 Hybrid Backtest Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "- Scope: offline backtest/report only; ML remains OFF by default.",
        "- Runtime paper engine and live order logic were not modified.",
        f"- V2 preserved as WATCH: Shock recall 94.46%, FPR 88.87%, Opportunity precision 70.80%, baseline 59.60%, delta +11.20%p.",
        f"- Prediction source: `{prediction_path}`",
        f"- Backtest window: {alpha.date_from_ts(start_time)} to {alpha.date_from_ts(end_time)} UTC, restricted to walk-forward prediction coverage.",
        "- Trade-time ML lookup uses the previous UTC daily prediction only, so daily close features are never used on the same intraday trade date.",
        "- Shock Guard is reference-only; p_shock never hard-blocks an entry.",
        "",
        "## PASS/WATCH/FAIL",
        "",
        f"- Status: {verdict}",
    ]
    lines.extend(f"- {reason}" for reason in reasons)
    lines.extend(
        [
            "",
            "## Base Comparison",
            "",
            summary_table(base_rows),
            "",
            "## Cost Stress",
            "",
            summary_table(stress_rows),
            "",
            "## V0 vs Best Hybrid",
            "",
            f"- Best hybrid by Calmar: {best_hybrid['policy']}",
            f"- Total return delta vs V0: {fmt_pct(best_hybrid['v0_total_return_delta_pct'])}",
            f"- MDD delta vs V0: {fmt_pct(best_hybrid['v0_mdd_delta_pct'])}",
            f"- Calmar delta vs V0: {fmt_num(best_hybrid['v0_calmar_delta'])}",
            f"- Trade count delta vs V0: {best_hybrid['v0_trade_count_delta']}",
            f"- V0 total return / MDD / Calmar: {fmt_pct(v0['total_return_pct'])} / {fmt_pct(v0['mdd_pct'])} / {fmt_num(v0['calmar'])}",
            "",
            "## Trade Attribution",
            "",
            attribution_table(trade_attribution),
            "",
            "## Probability Bins",
            "",
            attribution_table(probability_bins),
            "",
            "## Monthly Returns",
            "",
            monthly_report_table(runs),
            "",
            "## Yearly Returns",
            "",
            yearly_report_table(runs),
            "",
            "## Lookahead / Leakage Audit",
            "",
            "- Only v2 walk-forward predictions are used.",
            "- Entry decisions use prediction date = fill UTC date minus one day.",
            "- V0 and ML variants share the same data, fees, slippage, actual funding, top-score rule, liquidation buffer, and exits.",
            "- Thresholds are fixed experiment constants: 0.60, 0.65, 0.70. They are not optimized on the test period.",
            "- p_shock is used only for size reduction in `ML_OPP_WITH_SHOCK_SOFT`; it never blocks entries.",
            "- Existing Alpha Engine v1.2 Candidate baseline code path remains unchanged; this script is standalone offline research.",
            "",
            "## Decomposition",
            "",
        ]
    )
    lines.extend(decomposition_lines(base_rows))
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `ml_regime_v3_hybrid_backtest_report.md`",
            "- `ml_regime_v3_hybrid_summary.csv`",
            "- `ml_regime_v3_equity_curves.csv`",
            "- `ml_regime_v3_trade_attribution.csv`",
            "- `ml_regime_v3_cost_stress.csv`",
            "- `ml_regime_v3_probability_bins.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def pass_watch_fail(base_rows: List[dict], all_rows: List[dict], trade_attribution: List[dict]) -> Tuple[str, List[str]]:
    v0 = next(row for row in base_rows if row["policy"] == "V0_EMA_BASELINE")
    hybrids = [row for row in base_rows if row["policy"] != "V0_EMA_BASELINE"]
    best = best_hybrid_row(base_rows)
    stress_lookup = {(row["policy"], row["cost_scenario"]): row for row in all_rows}
    stress = stress_lookup.get((best["policy"], "cost_2x_slippage_2x"), {})
    v0_stress = stress_lookup.get(("V0_EMA_BASELINE", "cost_2x_slippage_2x"), {})
    reasons = [
        f"Best base hybrid: {best['policy']} total return {fmt_pct(best['total_return_pct'])}, Calmar {fmt_num(best['calmar'])}.",
        f"V0 base: total return {fmt_pct(v0['total_return_pct'])}, MDD {fmt_pct(v0['mdd_pct'])}, Calmar {fmt_num(v0['calmar'])}.",
        f"2x fee+slippage delta for best hybrid vs V0: return {fmt_pct((stress.get('total_return_pct') or 0.0) - (v0_stress.get('total_return_pct') or 0.0))}, Calmar {fmt_num((stress.get('calmar') or 0.0) - (v0_stress.get('calmar') or 0.0))}.",
    ]
    attribution = {row["group"]: row for row in trade_attribution}
    allowed_60 = attribution.get("allowed_by_opp_0.60", {})
    blocked_60 = attribution.get("blocked_by_opp_0.60", {})
    allowed_worse_than_blocked = (allowed_60.get("profit_factor") or 0.0) < (blocked_60.get("profit_factor") or 0.0)
    improves_return_or_calmar = best["total_return_pct"] > v0["total_return_pct"] or (best["calmar"] or 0.0) > (v0["calmar"] or 0.0)
    mdd_ok = best["mdd_pct"] >= v0["mdd_pct"] - 3.0
    stress_ok = (stress.get("total_return_pct") or -999.0) > (v0_stress.get("total_return_pct") or 999.0) or (stress.get("calmar") or -999.0) > (v0_stress.get("calmar") or 999.0)
    pf_ok = (best.get("profit_factor") or 0.0) > (v0.get("profit_factor") or 0.0)
    trade_retention = best["trade_count"] / v0["trade_count"] if v0["trade_count"] else 0.0
    if not improves_return_or_calmar:
        extra = ["No base hybrid improves total return or Calmar versus V0."]
        if allowed_worse_than_blocked:
            extra.append("V0 trades allowed by p_opportunity >= 0.60 have weaker PF than blocked trades, so ML is not selecting better entries.")
        return "FAIL", reasons + extra
    if improves_return_or_calmar and mdd_ok and stress_ok and pf_ok and trade_retention >= 0.35:
        return "PASS", reasons + ["Best hybrid clears return/Calmar, MDD, stress, PF, and trade-retention checks."]
    if improves_return_or_calmar or mdd_ok:
        return "WATCH", reasons + ["Improvement is incomplete; not all stress/PF/trade-retention checks clear."]
    return "FAIL", reasons + ["ML hybrids do not improve the base V0 tradeoff."]


def best_hybrid_row(base_rows: List[dict]) -> dict:
    hybrids = [row for row in base_rows if row["policy"] != "V0_EMA_BASELINE"]
    return max(hybrids, key=lambda row: (row.get("calmar") or -999.0, row.get("total_return_pct") or -999.0))


def decomposition_lines(base_rows: List[dict]) -> List[str]:
    v0 = next(row for row in base_rows if row["policy"] == "V0_EMA_BASELINE")
    lines = ["| Policy | Return Delta | MDD Delta | Trade Delta | Interpretation |", "|---|---:|---:|---:|---|"]
    for row in base_rows:
        if row["policy"] == "V0_EMA_BASELINE":
            continue
        if row["v0_total_return_delta_pct"] > 0:
            interpretation = "return improvement"
        elif row["mdd_pct"] > v0["mdd_pct"]:
            interpretation = "drawdown improvement only"
        else:
            interpretation = "weaker than V0"
        lines.append(
            f"| {row['policy']} | {fmt_pct(row['v0_total_return_delta_pct'])} | {fmt_pct(row['v0_mdd_delta_pct'])} | {row['v0_trade_count_delta']} | {interpretation} |"
        )
    return lines


def summary_table(rows: List[dict]) -> str:
    headers = ["Policy", "Scenario", "Return", "CAGR", "MDD", "Calmar", "Sharpe", "Sortino", "PF", "Win", "Trades", "Avg R", "Median Trade", "Max Losses", "Ret Δ", "MDD Δ", "Trades Δ"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["policy"],
            row["cost_scenario"],
            fmt_pct(row["total_return_pct"]),
            fmt_pct(row["cagr_pct"]),
            fmt_pct(row["mdd_pct"]),
            fmt_num(row["calmar"]),
            fmt_num(row["sharpe"]),
            fmt_num(row["sortino"]),
            fmt_num(row["profit_factor"]),
            fmt_pct(row["win_rate_pct"]),
            str(row["trade_count"]),
            fmt_num(row["average_r"]),
            fmt_pct(row["median_trade_return_pct"]),
            str(row["max_consecutive_losses"]),
            fmt_pct(row["v0_total_return_delta_pct"]),
            fmt_pct(row["v0_mdd_delta_pct"]),
            str(row["v0_trade_count_delta"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def attribution_table(rows: List[dict]) -> str:
    lines = ["| Group | Trades | Total PnL | Avg PnL | Win | PF | Median Return | Avg R |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['group']} | {row['trade_count']} | {fmt_num(row['total_pnl'])} | {fmt_num(row['avg_pnl'])} | {fmt_pct(row['win_rate_pct'])} | {fmt_num(row['profit_factor'])} | {fmt_pct(row['median_trade_return_pct'])} | {fmt_num(row['avg_r'])} |"
        )
    return "\n".join(lines)


def monthly_report_table(runs: List[HybridRun]) -> str:
    base_runs = [run for run in runs if run.scenario.name == "base"]
    months = sorted({row["month"] for run in base_runs for row in run.monthly})
    headers = ["Month"] + [run.policy.name for run in base_runs]
    lookup = {(run.policy.name, row["month"]): row["return_pct"] for run in base_runs for row in run.monthly}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for month in months:
        lines.append("| " + " | ".join([month] + [fmt_pct(lookup.get((run.policy.name, month))) for run in base_runs]) + " |")
    return "\n".join(lines)


def yearly_report_table(runs: List[HybridRun]) -> str:
    base_runs = [run for run in runs if run.scenario.name == "base"]
    years = sorted({row["year"] for run in base_runs for row in run.yearly})
    headers = ["Year"] + [run.policy.name for run in base_runs]
    lookup = {(run.policy.name, row["year"]): row["return_pct"] for run in base_runs for row in run.yearly}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for year in years:
        lines.append("| " + " | ".join([year] + [fmt_pct(lookup.get((run.policy.name, year))) for run in base_runs]) + " |")
    return "\n".join(lines)


def trade_r_multiple(trade: Mapping[str, object]) -> Optional[float]:
    risk = float(trade["initial_units"]) * max(float(trade["entry_price"]) - float(trade["stop_price"]), 0.0)
    if risk <= 0:
        return None
    return float(trade["pnl_after_funding"]) / risk if "pnl_after_funding" in trade else float(trade["pnl"]) / risk


def max_consecutive_losses(trades: List[dict]) -> int:
    current = 0
    worst = 0
    for trade in sorted(trades, key=lambda row: int(row["exit_timestamp"])):
        if float(trade["pnl_after_funding"]) < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def probability_bin(value: Optional[float], bins: List[Tuple[str, Optional[float], Optional[float]]]) -> str:
    for name, low, high in bins:
        if in_bin(value, low, high):
            return name
    return "missing"


def in_bin(value: Optional[float], low: Optional[float], high: Optional[float]) -> bool:
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value >= high:
        return False
    return True


def float_or_none(value: object) -> Optional[float]:
    if value in {"", None}:
        return None
    return float(value)


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m")


def month_range(start: str, end: str) -> List[str]:
    year, month = [int(part) for part in start.split("-")]
    end_year, end_month = [int(part) for part in end.split("-")]
    out = []
    while (year, month) <= (end_year, end_month):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return out


def fmt_pct(value: object) -> str:
    if value in {"", None}:
        return ""
    return f"{float(value):.2f}%"


def fmt_num(value: object) -> str:
    if value in {"", None}:
        return ""
    return f"{float(value):.4f}"


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
