"""Policy backtests for tradeable action-bias regime signals."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional


DEFAULT_FEE_RATE = 0.001
DEFAULT_SLIPPAGE_RATE = 0.0005
TRADING_DAYS = 365
ASSETS = ("btc", "eth", "alt", "cash")
RISK_ASSETS = ("btc", "eth", "alt")
ALT_SYMBOLS = ("SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "ADAUSDT", "TONUSDT")

POLICIES = {
    "policy_a_conservative": {
        "label": "Policy A Conservative",
        "weights": {
            "long_allowed": {"btc": 0.50, "eth": 0.30, "alt": 0.20},
            "btc_eth_preferred": {"btc": 0.70, "eth": 0.30},
            "alt_watch": {"btc": 0.30, "eth": 0.30, "alt": 0.40},
            "reduce_risk": {"cash": 1.00},
            "no_new_entry": {"cash": 1.00},
            "wait": {"cash": 1.00},
            "observe": {"cash": 1.00},
        },
    },
    "policy_b_balanced": {
        "label": "Policy B Balanced",
        "weights": {
            "long_allowed": {"btc": 0.30, "eth": 0.30, "alt": 0.40},
            "btc_eth_preferred": {"btc": 0.60, "eth": 0.40},
            "alt_watch": {"btc": 0.20, "eth": 0.30, "alt": 0.50},
            "reduce_risk": {"cash": 0.70, "btc": 0.30},
            "no_new_entry": {"cash": 1.00},
            "wait": {"cash": 1.00},
            "observe": {"cash": 1.00},
        },
    },
    "policy_c_defensive_carry": {
        "label": "Policy C Defensive Carry",
        "weights": {
            "long_allowed": {"btc": 0.40, "eth": 0.30, "alt": 0.30},
            "btc_eth_preferred": {"btc": 0.60, "eth": 0.30, "cash": 0.10},
            "alt_watch": {"btc": 0.20, "eth": 0.30, "alt": 0.40, "cash": 0.10},
            "reduce_risk": {"cash": 0.80, "btc": 0.20},
            "no_new_entry": {"cash": 1.00},
            "wait": {"cash": 1.00},
            "observe": {"cash": 1.00},
        },
    },
}

BENCHMARKS = {
    "btc_buy_hold": {"label": "BTC Buy & Hold", "weights": {"btc": 1.0}},
    "eth_buy_hold": {"label": "ETH Buy & Hold", "weights": {"eth": 1.0}},
    "alt_equal_weight_buy_hold": {
        "label": "상위 알트 Equal Weight Buy & Hold",
        "weights": {"alt": 1.0},
    },
    "cash_100": {"label": "현금 100%", "weights": {"cash": 1.0}},
    "btc_eth_50_50": {"label": "BTC 50% / ETH 50%", "weights": {"btc": 0.5, "eth": 0.5}},
}

SIMPLE_BASELINES = {
    "btc_ema200_btc": {"label": "BTC EMA200 Risk-On BTC"},
    "btc_ema200_btc_eth": {"label": "BTC EMA200 Risk-On BTC/ETH"},
    "btc_ema200_alt": {"label": "BTC EMA200 Risk-On ALT"},
    "btc_ema50_ema200_trend": {"label": "BTC EMA50/EMA200 Trend"},
    "eth_btc_strength_rotation": {"label": "ETH/BTC Strength Rotation"},
    "momentum_90d_rotation": {"label": "90D Momentum Rotation"},
    "equal_risk_simple": {"label": "Equal Risk Simple"},
}

HYBRID_BASELINE_IDS = (
    "momentum_90d_rotation",
    "eth_btc_strength_rotation",
    "btc_ema200_alt",
    "equal_risk_simple",
    "btc_ema200_btc_eth",
)

OVERLAY_ABLATION_MODES = (
    ("base_only", "base only"),
    ("shock_only", "base + shock only"),
    ("reduce_risk_only", "base + reduce_risk only"),
    ("observe_wait_only", "base + observe/wait only"),
    ("full_v4", "base + full v4 overlay"),
)

REBALANCE_RULES = ("daily", "weekly", "regime_change")
BASELINE_REBALANCE_RULES = ("daily", "weekly", "signal_change")
COST_SENSITIVITY_RATES = (0.0, 0.001, 0.002)


def build_policy_backtest_report(
    payload: dict,
    fee_rate: float = DEFAULT_FEE_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
) -> dict:
    """Build the action-bias policy backtest report.

    The strategy loop only reads trade_regime/trade_action_bias from the signal
    bar and applies the resulting allocation to the next bar's returns.
    """

    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    benchmarks = [
        _run_benchmark(points, benchmark_id, benchmark)
        for benchmark_id, benchmark in BENCHMARKS.items()
    ]
    btc_benchmark = next(row for row in benchmarks if row["id"] == "btc_buy_hold")

    default_rows = [
        _run_policy(
            points,
            regimes,
            policy_id,
            policy,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            rebalance_rule="daily",
            btc_benchmark=btc_benchmark,
            execution_mode="conservative",
        )
        for policy_id, policy in POLICIES.items()
    ]

    return {
        "config": {
            "signal": "trade_action_bias[i] / trade_regime[i]",
            "returnApplication": "weights from signal bar i are applied to returns of bar i+1",
            "stableRegimeDirectUse": False,
            "feeRate": fee_rate,
            "slippageRate": slippage_rate,
            "totalCostRate": fee_rate + slippage_rate,
            "tradingDays": TRADING_DAYS,
            "defaultRebalance": "daily",
        },
        "policies": _policy_definitions(),
        "benchmarks": benchmarks,
        "defaultRun": {
            "rebalance": "daily",
            "feeRate": fee_rate,
            "slippageRate": slippage_rate,
            "totalCostRate": fee_rate + slippage_rate,
            "rows": default_rows,
            "equityCurves": _equity_curves(default_rows, benchmarks),
        },
        "costSensitivity": [
            {
                "label": f"{rate * 100:.1f}%",
                "feeRate": rate,
                "slippageRate": 0.0,
                "totalCostRate": rate,
                "rows": [
                    _run_policy(
                        points,
                        regimes,
                        policy_id,
                        policy,
                        fee_rate=rate,
                        slippage_rate=0.0,
                        rebalance_rule="daily",
                        btc_benchmark=btc_benchmark,
                        execution_mode="conservative",
                        include_curve=False,
                    )
                    for policy_id, policy in POLICIES.items()
                ],
            }
            for rate in COST_SENSITIVITY_RATES
        ],
        "rebalanceComparison": [
            {
                "rebalance": rule,
                "feeRate": fee_rate,
                "slippageRate": slippage_rate,
                "totalCostRate": fee_rate + slippage_rate,
                "rows": [
                    _run_policy(
                        points,
                        regimes,
                        policy_id,
                        policy,
                        fee_rate=fee_rate,
                        slippage_rate=slippage_rate,
                        rebalance_rule=rule,
                        btc_benchmark=btc_benchmark,
                        execution_mode="conservative",
                        include_curve=False,
                    )
                    for policy_id, policy in POLICIES.items()
                ],
            }
            for rule in REBALANCE_RULES
        ],
    }


def build_policy_backtest_audit_report(payload: dict, policy_report: Optional[dict] = None) -> dict:
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    policy_report = policy_report or build_policy_backtest_report(payload)
    return {
        "benchmarkDetailedComparison": _benchmark_detailed_comparison(policy_report),
        "universeAudit": _universe_audit(payload, policy_report),
        "rebalanceComparison": policy_report.get("rebalanceComparison", []),
        "costSensitivity": policy_report.get("costSensitivity", []),
        "executionTiming": _execution_timing_comparison(points, regimes),
        "oos": _oos_report(points, regimes),
        "passFail": _pass_fail_report(policy_report),
    }


def build_simple_baseline_challenge_report(payload: dict, policy_report: Optional[dict] = None) -> dict:
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    policy_report = policy_report or build_policy_backtest_report(payload)
    btc_benchmark = next(row for row in policy_report.get("benchmarks", []) if row["id"] == "btc_buy_hold")
    default_simple_rows = [
        _run_simple_baseline(
            points,
            strategy_id,
            strategy,
            fee_rate=DEFAULT_FEE_RATE,
            slippage_rate=DEFAULT_SLIPPAGE_RATE,
            rebalance_rule="daily",
            btc_benchmark=btc_benchmark,
            include_curve=True,
        )
        for strategy_id, strategy in SIMPLE_BASELINES.items()
    ]
    comparison_rows = _simple_challenge_comparison_rows(policy_report, default_simple_rows)
    return {
        "config": {
            "signal": "simple strategy condition on bar i",
            "returnApplication": "signal bar i is applied to returns of bar i+1",
            "feeRate": DEFAULT_FEE_RATE,
            "slippageRate": DEFAULT_SLIPPAGE_RATE,
            "totalCostRate": DEFAULT_FEE_RATE + DEFAULT_SLIPPAGE_RATE,
            "rebalanceRules": list(BASELINE_REBALANCE_RULES),
        },
        "comparisonRows": comparison_rows,
        "simpleStrategyRows": default_simple_rows,
        "rebalanceComparison": _simple_rebalance_comparison(points, regimes, policy_report),
        "costSensitivity": _simple_cost_sensitivity(points, regimes, policy_report),
        "passFail": _simple_challenge_pass_fail(policy_report, default_simple_rows),
    }


def build_risk_normalized_comparison_report(
    payload: dict,
    policy_report: Optional[dict] = None,
    simple_report: Optional[dict] = None,
) -> dict:
    policy_report = policy_report or build_policy_backtest_report(payload)
    simple_report = simple_report or build_simple_baseline_challenge_report(payload, policy_report)
    rows = simple_report.get("comparisonRows", [])
    same_volatility = _same_volatility_rows(rows, 0.40)
    same_drawdown = _same_drawdown_rows(rows)
    policy_leverage = _policy_leverage_rows(rows, leverage_cap=1.5)
    return {
        "targetVolatility": 0.40,
        "sameVolatilityRows": same_volatility,
        "sameDrawdownRows": same_drawdown,
        "policyLeverageRows": policy_leverage,
        "winners": _risk_normalized_winners(rows, same_volatility, same_drawdown),
    }


def build_hybrid_overlay_challenge_report(
    payload: dict,
    simple_report: Optional[dict] = None,
) -> dict:
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    simple_report = simple_report or build_simple_baseline_challenge_report(payload)
    base_rows = _hybrid_base_rows(points, simple_report)
    best_simple_id = _best_simple_baseline_id(simple_report)
    hybrid_specs = [
        ("hybrid_momentum_v4", "90D Momentum + v4 overlay", "momentum_90d_rotation"),
        ("hybrid_eth_btc_v4", "ETH/BTC Strength + v4 overlay", "eth_btc_strength_rotation"),
        ("hybrid_ema200_alt_v4", "EMA200 ALT + v4 overlay", "btc_ema200_alt"),
        ("hybrid_momentum_eth_btc_50_50_v4", "50% Momentum + 50% ETH/BTC Strength + v4 overlay", "mix_momentum_eth_btc"),
        ("hybrid_best_simple_v4", "Best simple baseline + v4 position sizing overlay", best_simple_id),
    ]
    btc = _run_benchmark(points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
    hybrid_rows = [
        _run_hybrid_overlay(points, regimes, row_id, label, base_id, btc)
        for row_id, label, base_id in hybrid_specs
    ]
    return {
        "config": {
            "overlayRole": "risk overlay only",
            "feeRate": DEFAULT_FEE_RATE,
            "slippageRate": DEFAULT_SLIPPAGE_RATE,
            "rebalance": "daily",
        },
        "baseRows": base_rows,
        "hybridRows": hybrid_rows,
        "comparisonRows": _hybrid_comparison_rows(base_rows, hybrid_rows),
        "passFail": _hybrid_pass_fail_rows(base_rows, hybrid_rows),
    }


def build_overlay_ablation_report(payload: dict) -> dict:
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    btc = _run_benchmark(points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
    rows = []
    for base_id in HYBRID_BASELINE_IDS:
        for mode, label in OVERLAY_ABLATION_MODES:
            if mode == "base_only":
                row = _run_simple_baseline(
                    points,
                    base_id,
                    SIMPLE_BASELINES[base_id],
                    DEFAULT_FEE_RATE,
                    DEFAULT_SLIPPAGE_RATE,
                    "daily",
                    btc,
                    include_curve=False,
                )
            else:
                row = _run_overlay_variant(points, regimes, base_id, mode, f"{SIMPLE_BASELINES[base_id]['label']} · {label}", btc)
            row["baseId"] = base_id
            row["baseLabel"] = SIMPLE_BASELINES[base_id]["label"]
            row["overlayMode"] = mode
            row["overlayLabel"] = label
            rows.append(row)
    return {
        "rows": rows,
        "passFail": _overlay_ablation_pass_fail(rows),
    }


def build_eth_strength_sensitivity_report(payload: dict) -> dict:
    points = payload.get("points", [])
    rows = _eth_strength_condition_rows(points)
    return {
        "rows": rows,
        "passFail": _eth_strength_sensitivity_pass_fail(rows),
    }


def build_alt_universe_robustness_report(payload: dict) -> dict:
    points = payload.get("points", [])
    contribution_rows = _alt_contribution_rows(points)
    default_row = _run_benchmark(points, "alt_equal_weight_buy_hold", BENCHMARKS["alt_equal_weight_buy_hold"])
    leave_one_out = _alt_leave_one_out_rows(points)
    top_cap = _alt_top_cap_row(points, cap=0.25)
    start_years = _alt_start_year_rows(points)
    min_count = _alt_min_count_rows(points)
    return {
        "default": _challenge_row(default_row, "benchmark"),
        "leaveOneOut": leave_one_out,
        "topContributorCap": top_cap,
        "startYearRows": start_years,
        "minCountRows": min_count,
        "contributionRows": contribution_rows,
        "warnings": _alt_universe_robustness_warnings(default_row, leave_one_out, contribution_rows, start_years),
    }


def _benchmark_detailed_comparison(policy_report: dict) -> List[dict]:
    rows = []
    for row in policy_report.get("benchmarks", []):
        rows.append(_comparison_row(row, "benchmark"))
    for row in policy_report.get("defaultRun", {}).get("rows", []):
        rows.append(_comparison_row(row, "policy"))
    return rows


def _comparison_row(row: dict, group: str) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "group": group,
        "totalReturn": row.get("totalReturn"),
        "cagr": row.get("cagr"),
        "maxDrawdown": row.get("maxDrawdown"),
        "sharpe": row.get("sharpe"),
        "calmar": row.get("calmar"),
        "volatility": row.get("volatility"),
        "winRate": row.get("winRate"),
        "maxDrawdownPeriod": row.get("maxDrawdownPeriod"),
        "monthlyReturns": row.get("monthlyReturns", []),
        "yearlyReturns": row.get("yearlyReturns", []),
    }


def _run_simple_baseline(
    points: List[dict],
    strategy_id: str,
    strategy: dict,
    fee_rate: float,
    slippage_rate: float,
    rebalance_rule: str,
    btc_benchmark: dict,
    include_curve: bool = True,
) -> dict:
    current_weights = _cash_weights()
    equity = 1.0
    total_turnover = 0.0
    total_cost = 0.0
    records = []
    equity_curve = _initial_curve(points)
    last_rebalance_week = None
    last_rebalance_signal = None

    for index in range(0, max(0, len(points) - 1)):
        signal_point = points[index]
        return_point = points[index + 1]
        target_weights, signal_marker = _simple_strategy_target(strategy_id, points, index)
        target = _effective_weights(target_weights, signal_point, min_alt_count=3)
        should_rebalance, rebalance_marker = _should_rebalance(
            rebalance_rule,
            signal_point,
            target,
            last_rebalance_week,
            last_rebalance_signal,
            current_weights,
            signal_marker,
        )
        turnover = 0.0
        trading_cost = 0.0
        if should_rebalance:
            turnover = _risk_turnover(current_weights, target)
            trading_cost = turnover * (fee_rate + slippage_rate)
            total_turnover += turnover
            total_cost += equity * trading_cost
            current_weights = dict(target)
            if rebalance_rule == "weekly":
                last_rebalance_week = rebalance_marker
            if rebalance_rule == "signal_change":
                last_rebalance_signal = rebalance_marker

        period_returns = _asset_returns(return_point, "conservative")
        gross_return = _portfolio_return(current_weights, period_returns)
        start_equity = equity
        equity = equity * (1 - trading_cost) * (1 + gross_return)
        net_return = equity / start_equity - 1 if start_equity else 0.0
        records.append(
            {
                "time": return_point["time"],
                "return": net_return,
                "turnover": turnover,
                "tradingCost": start_equity * trading_cost,
                "nonCashWeight": sum(current_weights.get(asset, 0.0) for asset in RISK_ASSETS),
                "actionBias": signal_marker,
                "tradeRegime": signal_marker,
                "weights": dict(current_weights),
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})
        current_weights = _drift_weights(current_weights, period_returns, gross_return)

    row = _metric_row(
        row_id=strategy_id,
        label=strategy["label"],
        kind="simple_baseline",
        rebalance_rule=rebalance_rule,
        records=records,
        equity_curve=equity_curve,
        total_turnover=total_turnover,
        total_cost=total_cost,
        include_curve=include_curve,
        include_daily=False,
    )
    row["excessReturnVsBtc"] = _subtract(row.get("totalReturn"), btc_benchmark.get("totalReturn"))
    row["mddReducedVsBtc"] = _mdd_pass(row.get("maxDrawdown"), btc_benchmark.get("maxDrawdown"))
    row["mddReducedVsBtcStatus"] = "pass" if row["mddReducedVsBtc"] else "fail"
    return row


def _run_custom_weight_strategy(
    points: List[dict],
    row_id: str,
    label: str,
    target_fn,
    fee_rate: float,
    slippage_rate: float,
    rebalance_rule: str,
    btc_benchmark: dict,
    include_curve: bool = False,
) -> dict:
    current_weights = _cash_weights()
    equity = 1.0
    total_turnover = 0.0
    total_cost = 0.0
    records = []
    equity_curve = _initial_curve(points)
    last_rebalance_week = None
    last_rebalance_signal = None

    for index in range(0, max(0, len(points) - 1)):
        signal_point = points[index]
        return_point = points[index + 1]
        target_weights, signal_marker = target_fn(index)
        target = _effective_weights(target_weights, signal_point, min_alt_count=3)
        should_rebalance, rebalance_marker = _should_rebalance(
            rebalance_rule,
            signal_point,
            target,
            last_rebalance_week,
            last_rebalance_signal,
            current_weights,
            signal_marker,
        )
        turnover = 0.0
        trading_cost = 0.0
        if should_rebalance:
            turnover = _risk_turnover(current_weights, target)
            trading_cost = turnover * (fee_rate + slippage_rate)
            total_turnover += turnover
            total_cost += equity * trading_cost
            current_weights = dict(target)
            if rebalance_rule == "weekly":
                last_rebalance_week = rebalance_marker
            if rebalance_rule in {"signal_change", "regime_change"}:
                last_rebalance_signal = rebalance_marker

        period_returns = _asset_returns(return_point, "conservative")
        gross_return = _portfolio_return(current_weights, period_returns)
        start_equity = equity
        equity = equity * (1 - trading_cost) * (1 + gross_return)
        records.append(
            {
                "time": return_point["time"],
                "return": equity / start_equity - 1 if start_equity else 0.0,
                "turnover": turnover,
                "tradingCost": start_equity * trading_cost,
                "nonCashWeight": sum(current_weights.get(asset, 0.0) for asset in RISK_ASSETS),
                "actionBias": signal_marker,
                "tradeRegime": signal_marker,
                "weights": dict(current_weights),
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})
        current_weights = _drift_weights(current_weights, period_returns, gross_return)

    row = _metric_row(
        row_id=row_id,
        label=label,
        kind="hybrid_overlay",
        rebalance_rule=rebalance_rule,
        records=records,
        equity_curve=equity_curve,
        total_turnover=total_turnover,
        total_cost=total_cost,
        include_curve=include_curve,
        include_daily=False,
    )
    row["excessReturnVsBtc"] = _subtract(row.get("totalReturn"), btc_benchmark.get("totalReturn"))
    return row


def _run_hybrid_overlay(points: List[dict], regimes: dict, row_id: str, label: str, base_id: str, btc_benchmark: dict) -> dict:
    def target(index: int):
        base_weights, base_marker = _hybrid_base_target(base_id, points, index)
        overlay_weights, overlay_marker = _apply_v4_overlay(base_weights, points[index], regimes, "full_v4")
        return overlay_weights, f"{base_marker}:{overlay_marker}"

    row = _run_custom_weight_strategy(
        points,
        row_id,
        label,
        target,
        DEFAULT_FEE_RATE,
        DEFAULT_SLIPPAGE_RATE,
        "daily",
        btc_benchmark,
        include_curve=False,
    )
    row["baseId"] = base_id
    row["baseLabel"] = _hybrid_base_label(base_id)
    row["overlayMode"] = "full_v4"
    return row


def _run_overlay_variant(points: List[dict], regimes: dict, base_id: str, mode: str, label: str, btc_benchmark: dict) -> dict:
    def target(index: int):
        base_weights, base_marker = _hybrid_base_target(base_id, points, index)
        overlay_weights, overlay_marker = _apply_v4_overlay(base_weights, points[index], regimes, mode)
        return overlay_weights, f"{base_marker}:{overlay_marker}"

    row = _run_custom_weight_strategy(
        points,
        f"{base_id}_{mode}",
        label,
        target,
        DEFAULT_FEE_RATE,
        DEFAULT_SLIPPAGE_RATE,
        "daily",
        btc_benchmark,
        include_curve=False,
    )
    return row


def _simple_strategy_target(strategy_id: str, points: List[dict], index: int) -> tuple[dict, str]:
    point = points[index]
    risk_on = _btc_above_ema200(point)
    if strategy_id == "btc_ema200_btc":
        return ({"btc": 1.0}, "risk_on_btc") if risk_on else ({"cash": 1.0}, "cash")
    if strategy_id == "btc_ema200_btc_eth":
        return ({"btc": 0.5, "eth": 0.5}, "risk_on_btc_eth") if risk_on else ({"cash": 1.0}, "cash")
    if strategy_id == "btc_ema200_alt":
        return ({"alt": 1.0}, "risk_on_alt") if risk_on else ({"cash": 1.0}, "cash")
    if strategy_id == "btc_ema50_ema200_trend":
        trend_on = _has_value(point.get("ema50")) and _has_value(point.get("ema200")) and point["ema50"] > point["ema200"]
        return ({"btc": 0.5, "eth": 0.3, "alt": 0.2}, "trend_on") if trend_on else ({"cash": 1.0}, "cash")
    if strategy_id == "eth_btc_strength_rotation":
        if not risk_on:
            return {"cash": 1.0}, "cash"
        eth_btc_strong = (
            _has_value(point.get("eth_btc"))
            and _has_value(point.get("eth_btc_ema50"))
            and point["eth_btc"] > point["eth_btc_ema50"]
        )
        if eth_btc_strong:
            return {"alt": 0.5, "eth": 0.3, "btc": 0.2}, "eth_btc_strong"
        return {"btc": 0.7, "eth": 0.3}, "btc_eth_preferred"
    if strategy_id == "momentum_90d_rotation":
        if not risk_on:
            return {"cash": 1.0}, "cash"
        best_asset = _best_momentum_asset(points, index, lookback=90)
        return ({best_asset: 1.0}, f"momentum_{best_asset}") if best_asset else ({"cash": 1.0}, "cash")
    if strategy_id == "equal_risk_simple":
        return ({"btc": 0.4, "eth": 0.3, "alt": 0.3}, "risk_on_equal_risk") if risk_on else ({"cash": 1.0}, "cash")
    raise ValueError(f"Unknown simple baseline: {strategy_id}")


def _simple_challenge_comparison_rows(policy_report: dict, simple_rows: List[dict]) -> List[dict]:
    rows = []
    for row in policy_report.get("benchmarks", []):
        rows.append(_challenge_row(row, "benchmark"))
    for row in policy_report.get("defaultRun", {}).get("rows", []):
        rows.append(_challenge_row(row, "policy"))
    for row in simple_rows:
        rows.append(_challenge_row(row, "simple_baseline"))
    return rows


def _challenge_row(row: dict, group: str) -> dict:
    data = _comparison_row(row, group)
    data.update(
        {
            "rebalance": row.get("rebalance"),
            "turnover": row.get("turnover"),
            "totalTradingCost": row.get("totalTradingCost"),
            "marketParticipation": row.get("marketParticipation"),
            "excessReturnVsBtc": row.get("excessReturnVsBtc"),
            "equityCurve": row.get("equityCurve", []),
        }
    )
    return data


def _simple_rebalance_comparison(points: List[dict], regimes: dict, policy_report: dict) -> List[dict]:
    rows = []
    for rule in BASELINE_REBALANCE_RULES:
        btc = _run_benchmark(points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
        for policy_id, policy in POLICIES.items():
            policy_rule = "signal_change" if rule == "signal_change" else rule
            result = _run_policy(
                points,
                regimes,
                policy_id,
                policy,
                DEFAULT_FEE_RATE,
                DEFAULT_SLIPPAGE_RATE,
                policy_rule,
                btc,
                include_curve=False,
            )
            rows.append({"rebalance": rule, "group": "policy", **_challenge_row(result, "policy")})
        for strategy_id, strategy in SIMPLE_BASELINES.items():
            result = _run_simple_baseline(
                points,
                strategy_id,
                strategy,
                DEFAULT_FEE_RATE,
                DEFAULT_SLIPPAGE_RATE,
                rule,
                btc,
                include_curve=False,
            )
            rows.append({"rebalance": rule, "group": "simple_baseline", **_challenge_row(result, "simple_baseline")})
    return rows


def _simple_cost_sensitivity(points: List[dict], regimes: dict, policy_report: dict) -> List[dict]:
    rows = []
    for rate in COST_SENSITIVITY_RATES:
        btc = _run_benchmark(points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
        label = f"{rate * 100:.1f}%"
        for policy_id, policy in POLICIES.items():
            result = _run_policy(
                points,
                regimes,
                policy_id,
                policy,
                rate,
                0.0,
                "daily",
                btc,
                include_curve=False,
            )
            rows.append({"cost": label, "group": "policy", **_challenge_row(result, "policy")})
        for strategy_id, strategy in SIMPLE_BASELINES.items():
            result = _run_simple_baseline(points, strategy_id, strategy, rate, 0.0, "daily", btc, include_curve=False)
            rows.append({"cost": label, "group": "simple_baseline", **_challenge_row(result, "simple_baseline")})
    return rows


def _simple_challenge_pass_fail(policy_report: dict, simple_rows: List[dict]) -> dict:
    policy_b = next((row for row in policy_report.get("defaultRun", {}).get("rows", []) if row["id"] == "policy_b_balanced"), {})
    simple_calmars = sorted(value for value in (row.get("calmar") for row in simple_rows) if _has_value(value))
    simple_mdds = sorted(value for value in (row.get("maxDrawdown") for row in simple_rows) if _has_value(value))
    simple_returns = sorted(value for value in (row.get("totalReturn") for row in simple_rows) if _has_value(value))
    median_calmar = _median(simple_calmars)
    median_mdd = _median(simple_mdds)
    median_return = _median(simple_returns)
    ema200_alt = next((row for row in simple_rows if row["id"] == "btc_ema200_alt"), {})
    calmar_pass = _has_value(policy_b.get("calmar")) and _has_value(median_calmar) and policy_b["calmar"] > median_calmar
    mdd_pass = _has_value(policy_b.get("maxDrawdown")) and _has_value(median_mdd) and policy_b["maxDrawdown"] <= median_mdd * 1.05
    ema_alt_warning = _has_value(ema200_alt.get("calmar")) and _has_value(policy_b.get("calmar")) and policy_b["calmar"] < ema200_alt["calmar"]
    return_mdd_fail = (
        _has_value(policy_b.get("totalReturn"))
        and _has_value(median_return)
        and _has_value(policy_b.get("maxDrawdown"))
        and _has_value(median_mdd)
        and policy_b["totalReturn"] < median_return
        and policy_b["maxDrawdown"] >= median_mdd * 0.95
    )
    checks = [
        {
            "name": "policy_b_calmar_vs_simple_median",
            "status": _status(calmar_pass),
            "policyValue": policy_b.get("calmar"),
            "baselineValue": median_calmar,
        },
        {
            "name": "policy_b_mdd_vs_simple_median",
            "status": _status(mdd_pass),
            "policyValue": policy_b.get("maxDrawdown"),
            "baselineValue": median_mdd,
        },
        {
            "name": "policy_b_vs_ema200_alt_calmar",
            "status": "warning" if ema_alt_warning else "pass",
            "policyValue": policy_b.get("calmar"),
            "baselineValue": ema200_alt.get("calmar"),
        },
        {
            "name": "policy_b_low_return_similar_mdd",
            "status": "fail" if return_mdd_fail else "pass",
            "policyReturn": policy_b.get("totalReturn"),
            "baselineMedianReturn": median_return,
            "policyMdd": policy_b.get("maxDrawdown"),
            "baselineMedianMdd": median_mdd,
        },
    ]
    return {
        "policy": policy_b.get("label"),
        "medianSimpleCalmar": median_calmar,
        "medianSimpleMdd": median_mdd,
        "medianSimpleReturn": median_return,
        "checks": checks,
        "overall": "fail" if return_mdd_fail else ("warning" if ema_alt_warning else ("pass" if calmar_pass and mdd_pass else "warning")),
    }


def _hybrid_base_rows(points: List[dict], simple_report: dict) -> List[dict]:
    simple_by_id = {row["id"]: row for row in simple_report.get("simpleStrategyRows", [])}
    btc = _run_benchmark(points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
    rows = []
    for base_id in HYBRID_BASELINE_IDS:
        row = simple_by_id.get(base_id)
        if row is None:
            row = _run_simple_baseline(
                points,
                base_id,
                SIMPLE_BASELINES[base_id],
                DEFAULT_FEE_RATE,
                DEFAULT_SLIPPAGE_RATE,
                "daily",
                btc,
                include_curve=False,
            )
        rows.append(row)
    return rows


def _best_simple_baseline_id(simple_report: dict) -> str:
    rows = [row for row in simple_report.get("simpleStrategyRows", []) if _has_value(row.get("calmar"))]
    if not rows:
        return "momentum_90d_rotation"
    return max(rows, key=lambda row: row["calmar"])["id"]


def _hybrid_base_target(base_id: str, points: List[dict], index: int) -> tuple[dict, str]:
    if base_id == "mix_momentum_eth_btc":
        momentum, momentum_marker = _simple_strategy_target("momentum_90d_rotation", points, index)
        eth_btc, eth_btc_marker = _simple_strategy_target("eth_btc_strength_rotation", points, index)
        return _combine_weights([(momentum, 0.5), (eth_btc, 0.5)]), f"mix_{momentum_marker}_{eth_btc_marker}"
    return _simple_strategy_target(base_id, points, index)


def _hybrid_base_label(base_id: str) -> str:
    if base_id == "mix_momentum_eth_btc":
        return "50% Momentum + 50% ETH/BTC Strength"
    return SIMPLE_BASELINES.get(base_id, {}).get("label", base_id)


def _combine_weights(weighted_items: List[tuple[dict, float]]) -> dict:
    combined = {asset: 0.0 for asset in ASSETS}
    for weights, scale in weighted_items:
        normalized = _normalize_weights(weights)
        for asset in ASSETS:
            combined[asset] += normalized.get(asset, 0.0) * scale
    return _normalize_weights(combined)


def _apply_v4_overlay(base_weights: dict, signal_point: dict, regimes: dict, mode: str) -> tuple[dict, str]:
    if mode == "base_only":
        return base_weights, "base_only"
    action_bias = _trade_action_bias(signal_point, regimes)
    trade_regime = signal_point.get("trade_regime")
    if mode == "shock_only":
        if action_bias == "no_new_entry" or trade_regime == "shock":
            return {"cash": 1.0}, "shock_cash"
        return base_weights, "shock_noop"
    if mode == "reduce_risk_only":
        if action_bias == "reduce_risk":
            return _scale_risk_exposure(base_weights, 0.30), "reduce_risk_30"
        return base_weights, "reduce_risk_noop"
    if mode == "observe_wait_only":
        if action_bias == "wait" or trade_regime == "observe":
            return {"cash": 1.0}, "wait_cash"
        return base_weights, "wait_noop"
    if mode != "full_v4":
        raise ValueError(f"Unknown overlay mode: {mode}")

    if action_bias == "long_allowed":
        return base_weights, "long_allowed_100"
    if action_bias == "btc_eth_preferred":
        normalized = _normalize_weights(base_weights)
        if normalized.get("alt", 0.0) >= 0.95:
            return {"btc": 0.50, "eth": 0.30, "alt": 0.20}, "btc_eth_preferred_alt_soften"
        return _scale_risk_exposure(normalized, 0.90), "btc_eth_preferred_90"
    if action_bias == "alt_watch":
        return base_weights, "alt_watch_100"
    if action_bias == "reduce_risk":
        return _scale_risk_exposure(base_weights, 0.30), "reduce_risk_30"
    if action_bias in {"no_new_entry", "wait"} or trade_regime in {"shock", "observe"}:
        return {"cash": 1.0}, "cash"
    return base_weights, "fallback_base"


def _scale_risk_exposure(weights: dict, exposure: float) -> dict:
    normalized = _normalize_weights(weights)
    risk_total = sum(normalized.get(asset, 0.0) for asset in RISK_ASSETS)
    if risk_total <= 0:
        return _cash_weights()
    scaled = {asset: normalized.get(asset, 0.0) * exposure for asset in RISK_ASSETS}
    scaled["cash"] = 1.0 - sum(scaled.values())
    return _normalize_weights(scaled)


def _hybrid_comparison_rows(base_rows: List[dict], hybrid_rows: List[dict]) -> List[dict]:
    rows = []
    for row in base_rows:
        rows.append({"role": "base", **_challenge_row(row, "simple_baseline")})
    for row in hybrid_rows:
        rows.append({"role": "hybrid", **_challenge_row(row, "hybrid_overlay"), "baseId": row.get("baseId"), "baseLabel": row.get("baseLabel")})
    return rows


def _hybrid_pass_fail_rows(base_rows: List[dict], hybrid_rows: List[dict]) -> List[dict]:
    base_by_id = {row["id"]: row for row in base_rows}
    checks = []
    for hybrid in hybrid_rows:
        base = base_by_id.get(hybrid.get("baseId"))
        if not base and hybrid.get("baseId") == "mix_momentum_eth_btc":
            base = _synthetic_mix_reference(base_by_id)
        if not base:
            continue
        calmar_pass = _has_value(hybrid.get("calmar")) and _has_value(base.get("calmar")) and hybrid["calmar"] > base["calmar"]
        risk_pass = _has_value(hybrid.get("maxDrawdown")) and _has_value(base.get("maxDrawdown")) and hybrid["maxDrawdown"] <= base["maxDrawdown"] * 0.80
        cagr_warning = _has_value(hybrid.get("cagr")) and _has_value(base.get("cagr")) and hybrid["cagr"] < base["cagr"] * 0.70
        checks.append(
            {
                "hybridId": hybrid["id"],
                "hybrid": hybrid["label"],
                "baseId": hybrid.get("baseId"),
                "base": hybrid.get("baseLabel") or base.get("label"),
                "calmarPass": _status(calmar_pass),
                "riskPass": _status(risk_pass),
                "cagrStatus": "warning" if cagr_warning else "pass",
                "baseCagr": base.get("cagr"),
                "hybridCagr": hybrid.get("cagr"),
                "baseMdd": base.get("maxDrawdown"),
                "hybridMdd": hybrid.get("maxDrawdown"),
                "baseCalmar": base.get("calmar"),
                "hybridCalmar": hybrid.get("calmar"),
            }
        )
    return checks


def _synthetic_mix_reference(base_by_id: dict) -> Optional[dict]:
    left = base_by_id.get("momentum_90d_rotation")
    right = base_by_id.get("eth_btc_strength_rotation")
    if not left or not right:
        return None
    return {
        "id": "mix_momentum_eth_btc",
        "label": "50% Momentum + 50% ETH/BTC Strength reference",
        "cagr": _mean([value for value in (left.get("cagr"), right.get("cagr")) if _has_value(value)]),
        "calmar": _mean([value for value in (left.get("calmar"), right.get("calmar")) if _has_value(value)]),
        "maxDrawdown": _mean([value for value in (left.get("maxDrawdown"), right.get("maxDrawdown")) if _has_value(value)]),
    }


def _overlay_ablation_pass_fail(rows: List[dict]) -> List[dict]:
    output = []
    by_base = defaultdict(dict)
    for row in rows:
        by_base[row["baseId"]][row["overlayMode"]] = row
    for base_id, variants in by_base.items():
        full = variants.get("full_v4", {})
        shock = variants.get("shock_only", {})
        full_warning = _has_value(full.get("calmar")) and _has_value(shock.get("calmar")) and full["calmar"] < shock["calmar"]
        output.append(
            {
                "baseId": base_id,
                "base": SIMPLE_BASELINES.get(base_id, {}).get("label", base_id),
                "fullOverlayCalmar": full.get("calmar"),
                "shockOnlyCalmar": shock.get("calmar"),
                "status": "warning" if full_warning else "pass",
                "message": "full overlay가 shock-only보다 약함" if full_warning else "full overlay가 shock-only 이상",
            }
        )
    return output


def _universe_audit(payload: dict, policy_report: dict) -> dict:
    points = payload.get("points", [])
    symbol_rows = _symbol_start_rows(payload, points)
    composition = _alt_composition_summary(points)
    contribution = _alt_contribution_rows(points)
    sensitivity = _universe_sensitivity(payload, symbol_rows)
    warnings = _universe_warnings(composition, contribution, sensitivity)
    return {
        "symbolStartRows": symbol_rows,
        "composition": composition,
        "altContributionRows": contribution,
        "sensitivity": sensitivity,
        "warnings": warnings,
        "topContributors": contribution[:3],
        "defaultPolicyTotalReturns": [
            {"id": row["id"], "label": row["label"], "totalReturn": row.get("totalReturn")}
            for row in policy_report.get("defaultRun", {}).get("rows", [])
        ],
    }


def _same_volatility_rows(rows: List[dict], target_volatility: float) -> List[dict]:
    output = []
    for row in rows:
        volatility = row.get("volatility")
        if not _has_value(volatility) or volatility <= 0:
            continue
        returns = _returns_from_equity_curve(row.get("equityCurve", []))
        if not returns:
            continue
        scale = target_volatility / volatility
        metric = _scaled_metrics(row, returns, scale, f"same_vol_{target_volatility:.0%}")
        output.append(metric)
    return output


def _same_drawdown_rows(rows: List[dict]) -> List[dict]:
    policy_b = next((row for row in rows if row.get("id") == "policy_b_balanced"), {})
    target_mdd = policy_b.get("maxDrawdown")
    if not _has_value(target_mdd) or target_mdd <= 0:
        return []
    selected_ids = {"btc_buy_hold", "alt_equal_weight_buy_hold"}
    output = []
    for row in rows:
        if row.get("id") not in selected_ids:
            continue
        mdd = row.get("maxDrawdown")
        returns = _returns_from_equity_curve(row.get("equityCurve", []))
        if not _has_value(mdd) or mdd <= 0 or not returns:
            continue
        scale = min(1.0, target_mdd / mdd)
        metric = _scaled_metrics(row, returns, scale, "same_policy_b_mdd")
        metric["targetMdd"] = target_mdd
        output.append(metric)
    return output


def _policy_leverage_rows(rows: List[dict], leverage_cap: float) -> List[dict]:
    btc = next((row for row in rows if row.get("id") == "btc_buy_hold"), {})
    target_mdd = btc.get("maxDrawdown")
    if not _has_value(target_mdd) or target_mdd <= 0:
        return []
    output = []
    for row in rows:
        if row.get("group") != "policy":
            continue
        mdd = row.get("maxDrawdown")
        returns = _returns_from_equity_curve(row.get("equityCurve", []))
        if not _has_value(mdd) or mdd <= 0 or not returns:
            continue
        scale = min(leverage_cap, target_mdd / mdd)
        metric = _scaled_metrics(row, returns, scale, "policy_to_btc_mdd")
        metric["targetMdd"] = target_mdd
        metric["leverageCap"] = leverage_cap
        output.append(metric)
    return output


def _risk_normalized_winners(rows: List[dict], same_volatility: List[dict], same_drawdown: List[dict]) -> List[dict]:
    return [
        _winner_row("raw_return", rows, "totalReturn"),
        _winner_row("sharpe", rows, "sharpe"),
        _winner_row("calmar", rows, "calmar"),
        _winner_row("same_volatility_cagr", same_volatility, "cagr"),
        _winner_row("same_drawdown_cagr", same_drawdown, "cagr"),
    ]


def _winner_row(name: str, rows: List[dict], key: str) -> dict:
    candidates = [row for row in rows if _has_value(row.get(key))]
    if not candidates:
        return {"name": name, "winner": None, "value": None}
    winner = max(candidates, key=lambda row: row[key])
    return {
        "name": name,
        "winner": winner.get("label"),
        "id": winner.get("id"),
        "group": winner.get("group") or winner.get("kind"),
        "value": winner.get(key),
    }


def _scaled_metrics(row: dict, returns: List[dict], scale: float, mode: str) -> dict:
    records = []
    equity_curve = []
    if returns:
        first_time = returns[0]["previousTime"]
        equity_curve.append({"time": first_time, "value": 1.0})
    equity = 1.0
    for item in returns:
        scaled_return = item["return"] * scale
        equity *= 1 + scaled_return
        records.append(
            {
                "time": item["time"],
                "return": scaled_return,
                "turnover": 0.0,
                "tradingCost": 0.0,
                "nonCashWeight": min(1.0, max(0.0, row.get("marketParticipation") or 0.0) * scale),
            }
        )
        equity_curve.append({"time": item["time"], "value": equity})
    metric = _metric_row(
        row_id=row["id"],
        label=row["label"],
        kind=row.get("group", row.get("kind", "scaled")),
        rebalance_rule=mode,
        records=records,
        equity_curve=equity_curve,
        total_turnover=0.0,
        total_cost=0.0,
        include_curve=False,
        include_daily=False,
    )
    metric["baseTotalReturn"] = row.get("totalReturn")
    metric["baseCagr"] = row.get("cagr")
    metric["baseMaxDrawdown"] = row.get("maxDrawdown")
    metric["scale"] = scale
    metric["mode"] = mode
    metric["group"] = row.get("group")
    return metric


def _returns_from_equity_curve(equity_curve: List[dict]) -> List[dict]:
    rows = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1]
        current = equity_curve[index]
        if not previous.get("value") or current.get("value") is None:
            continue
        rows.append(
            {
                "previousTime": previous.get("time"),
                "time": current.get("time"),
                "return": current["value"] / previous["value"] - 1,
            }
        )
    return rows


def _execution_timing_comparison(points: List[dict], regimes: dict) -> dict:
    modes = [
        {
            "mode": "conservative",
            "label": "conservative",
            "description": "trade_action_bias[i] -> return[i+1]",
        },
        {
            "mode": "practical",
            "label": "practical",
            "description": "trade_action_bias[i] -> return[i]",
        },
        {
            "mode": "next_open",
            "label": "next_open",
            "description": "previous confirmed signal -> same-day open-to-close",
        },
    ]
    rows = []
    checks = []
    for mode in modes:
        check = _execution_lookahead_check(points, regimes, mode["mode"])
        checks.append({**mode, **check})
        benchmarks = [
            _run_benchmark(points, benchmark_id, benchmark, execution_mode=mode["mode"])
            for benchmark_id, benchmark in BENCHMARKS.items()
        ]
        btc_benchmark = next(row for row in benchmarks if row["id"] == "btc_buy_hold")
        for policy_id, policy in POLICIES.items():
            result = _run_policy(
                points,
                regimes,
                policy_id,
                policy,
                fee_rate=DEFAULT_FEE_RATE,
                slippage_rate=DEFAULT_SLIPPAGE_RATE,
                rebalance_rule="daily",
                btc_benchmark=btc_benchmark,
                execution_mode=mode["mode"],
                include_curve=False,
            )
            rows.append(
                {
                    "mode": mode["mode"],
                    "label": mode["label"],
                    "policyId": policy_id,
                    "policy": policy["label"],
                    "totalReturn": result.get("totalReturn"),
                    "cagr": result.get("cagr"),
                    "maxDrawdown": result.get("maxDrawdown"),
                    "turnover": result.get("turnover"),
                    "totalTradingCost": result.get("totalTradingCost"),
                    "lookaheadStatus": check["status"],
                }
            )
    return {"checks": checks, "rows": rows}


def _eth_strength_condition_rows(points: List[dict]) -> List[dict]:
    eth_btc_values = [point.get("eth_btc") for point in points]
    eth_btc_ema100 = _ema_optional(eth_btc_values, 100)
    conditions = [
        ("v4_eth_strength", "현재 v4 eth_strength", lambda i: points[i].get("stable_regime") == "eth_strength"),
        ("eth_btc_gt_ema50", "ETH/BTC > EMA50", lambda i: _gt(points[i].get("eth_btc"), points[i].get("eth_btc_ema50"))),
        ("eth_btc_gt_ema100", "ETH/BTC > EMA100", lambda i: _gt(points[i].get("eth_btc"), eth_btc_ema100[i])),
        ("eth_btc_ema50_slope_up", "ETH/BTC EMA50 slope up", lambda i: i > 0 and _gt(points[i].get("eth_btc_ema50"), points[i - 1].get("eth_btc_ema50"))),
        ("eth_btc_30d_gt_btc_30d", "ETH/BTC 30D return > BTC 30D return", lambda i: _eth_btc_30d_beats_btc(points, i)),
        ("btc_gt_ema200_eth_btc_gt_ema50", "BTC > EMA200 AND ETH/BTC > EMA50", lambda i: _btc_above_ema200(points[i]) and _gt(points[i].get("eth_btc"), points[i].get("eth_btc_ema50"))),
    ]
    return [_eth_strength_condition_row(points, condition_id, label, predicate) for condition_id, label, predicate in conditions]


def _eth_strength_condition_row(points: List[dict], condition_id: str, label: str, predicate) -> dict:
    records = []
    active_alt_returns = []
    active_btc_returns = []
    active_flags = []
    equity = 1.0
    equity_curve = _initial_curve(points)
    for index in range(0, max(0, len(points) - 1)):
        active = bool(predicate(index))
        active_flags.append(active)
        return_point = points[index + 1]
        alt_return = _finite_or_zero(return_point.get("alt_average_return")) if active else 0.0
        btc_return = _finite_or_zero(return_point.get("return")) if active else 0.0
        if active:
            active_alt_returns.append(alt_return)
            active_btc_returns.append(btc_return)
        equity *= 1 + alt_return
        records.append(
            {
                "time": return_point["time"],
                "return": alt_return,
                "turnover": 0.0,
                "tradingCost": 0.0,
                "nonCashWeight": 1.0 if active else 0.0,
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})
    metric = _metric_row(
        row_id=condition_id,
        label=label,
        kind="eth_strength_condition",
        rebalance_rule="condition_active_alt_else_cash",
        records=records,
        equity_curve=equity_curve,
        total_turnover=0.0,
        total_cost=0.0,
        include_curve=False,
        include_daily=False,
    )
    durations = _boolean_duration_stats(active_flags, points)
    metric.update(
        {
            "condition": condition_id,
            "activeDays": sum(1 for active in active_flags if active),
            "occurrences": durations["occurrences"],
            "averageDays": durations["averageDays"],
            "maxDays": durations["maxDays"],
            "altCumulativeReturn": _compound(active_alt_returns) if active_alt_returns else None,
            "btcCumulativeReturn": _compound(active_btc_returns) if active_btc_returns else None,
            "btcExcessReturn": _subtract(
                _compound(active_alt_returns) if active_alt_returns else None,
                _compound(active_btc_returns) if active_btc_returns else None,
            ),
        }
    )
    return metric


def _eth_strength_sensitivity_pass_fail(rows: List[dict]) -> dict:
    current = next((row for row in rows if row["id"] == "v4_eth_strength"), {})
    alternatives = [row for row in rows if row["id"] != "v4_eth_strength" and _has_value(row.get("calmar"))]
    best = max(alternatives, key=lambda row: row["calmar"]) if alternatives else {}
    warning = _has_value(current.get("calmar")) and _has_value(best.get("calmar")) and best["calmar"] > current["calmar"]
    return {
        "status": "warning" if warning else "pass",
        "currentCalmar": current.get("calmar"),
        "bestAlternative": best.get("label"),
        "bestAlternativeCalmar": best.get("calmar"),
        "message": "ETH/BTC 단순 조건이 v4 eth_strength보다 우수" if warning else "v4 eth_strength가 대안 조건 대비 열위 아님",
    }


def _alt_leave_one_out_rows(points: List[dict]) -> List[dict]:
    rows = []
    for excluded in ALT_SYMBOLS:
        symbols = [symbol for symbol in ALT_SYMBOLS if symbol != excluded]
        scenario_points = _points_for_alt_universe(points, symbols, 3)
        row = _run_benchmark(scenario_points, f"alt_without_{excluded.lower()}", {"label": f"{excluded.replace('USDT', '')} 제외 ALT", "weights": {"alt": 1.0}})
        rows.append({"excluded": excluded.replace("USDT", ""), **_challenge_row(row, "alt_universe")})
    return rows


def _alt_top_cap_row(points: List[dict], cap: float) -> dict:
    records = []
    equity = 1.0
    equity_curve = _initial_curve(points)
    for index in range(0, max(0, len(points) - 1)):
        signal_symbols = set(_alt_returns(points[index]).keys())
        return_values = {
            symbol: value
            for symbol, value in _alt_returns(points[index + 1]).items()
            if symbol in signal_symbols
        }
        if not return_values:
            day_return = 0.0
            exposure = 0.0
        else:
            weight = min(1 / len(return_values), cap)
            day_return = sum(value * weight for value in return_values.values())
            exposure = weight * len(return_values)
        equity *= 1 + day_return
        records.append(
            {
                "time": points[index + 1]["time"],
                "return": day_return,
                "turnover": 0.0,
                "tradingCost": 0.0,
                "nonCashWeight": exposure,
            }
        )
        equity_curve.append({"time": points[index + 1]["time"], "value": equity})
    row = _metric_row(
        row_id="alt_top_contributor_cap_25",
        label="ALT basket contributor cap 25%",
        kind="alt_universe",
        rebalance_rule="daily_equal_weight_cap",
        records=records,
        equity_curve=equity_curve,
        total_turnover=0.0,
        total_cost=0.0,
        include_curve=False,
        include_daily=False,
    )
    row["cap"] = cap
    return row


def _alt_start_year_rows(points: List[dict]) -> List[dict]:
    rows = []
    for year in (2020, 2021, 2022, 2023, 2024):
        window = _filter_points(points, f"{year}-01-01", "2026-12-31")
        if len(window) < 2:
            continue
        row = _run_benchmark(window, f"alt_start_{year}", {"label": f"ALT start {year}", "weights": {"alt": 1.0}})
        rows.append({"startYear": year, **_challenge_row(row, "alt_universe")})
    return rows


def _alt_min_count_rows(points: List[dict]) -> List[dict]:
    min3 = _run_benchmark(points, "alt_min3_cash", {"label": "ALT min 3 else cash", "weights": {"alt": 1.0}}, min_alt_count=3)
    min5_cash = _run_benchmark(points, "alt_min5_cash", {"label": "ALT min 5 else cash", "weights": {"alt": 1.0}}, min_alt_count=5)
    min5_sub = _run_alt_min5_btc_eth_substitute(points)
    return [
        _challenge_row(min3, "alt_universe"),
        _challenge_row(min5_cash, "alt_universe"),
        _challenge_row(min5_sub, "alt_universe"),
    ]


def _run_alt_min5_btc_eth_substitute(points: List[dict]) -> dict:
    records = []
    equity = 1.0
    equity_curve = _initial_curve(points)
    for index in range(0, max(0, len(points) - 1)):
        signal_count = _alt_count(points[index])
        return_point = points[index + 1]
        if signal_count >= 5:
            day_return = _finite_or_zero(return_point.get("alt_average_return"))
            exposure = 1.0
        else:
            day_return = 0.5 * _finite_or_zero(return_point.get("return")) + 0.5 * _finite_or_zero(return_point.get("eth_return"))
            exposure = 1.0
        equity *= 1 + day_return
        records.append(
            {
                "time": return_point["time"],
                "return": day_return,
                "turnover": 0.0,
                "tradingCost": 0.0,
                "nonCashWeight": exposure,
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})
    return _metric_row(
        row_id="alt_min5_btc_eth_substitute",
        label="ALT min 5 else BTC/ETH",
        kind="alt_universe",
        rebalance_rule="daily_min_count",
        records=records,
        equity_curve=equity_curve,
        total_turnover=0.0,
        total_cost=0.0,
        include_curve=False,
        include_daily=False,
    )


def _alt_universe_robustness_warnings(default_row: dict, leave_one_out: List[dict], contribution_rows: List[dict], start_year_rows: List[dict]) -> List[dict]:
    warnings = []
    top_share = max((row.get("positiveContributionShare", 0.0) for row in contribution_rows), default=0.0)
    if top_share > 0.25:
        warnings.append({"status": "warning", "name": "top_contributor_dependency", "detail": f"최대 알트 기여 비중 {top_share:.1%}"})
    default_return = default_row.get("totalReturn")
    if _has_value(default_return) and default_return > 0 and leave_one_out:
        worst = min(leave_one_out, key=lambda row: row.get("totalReturn") if _has_value(row.get("totalReturn")) else math.inf)
        if _has_value(worst.get("totalReturn")) and worst["totalReturn"] < default_return * 0.70:
            warnings.append({"status": "warning", "name": "leave_one_out_dependency", "detail": f"{worst.get('excluded')} 제외 시 성과 급감"})
    cagrs = [row.get("cagr") for row in start_year_rows if _has_value(row.get("cagr"))]
    if len(cagrs) >= 2 and min(cagrs) < max(cagrs) * 0.35:
        warnings.append({"status": "warning", "name": "start_year_dependency", "detail": "시작연도별 CAGR 편차 큼"})
    if not warnings:
        warnings.append({"status": "pass", "name": "alt_universe_robustness", "detail": "정의된 robustness warning 조건 없음"})
    return warnings


def _ema_optional(values: List[Optional[float]], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = []
    multiplier = 2 / (period + 1)
    ema_value = None
    seed: List[float] = []
    for value in values:
        if not _has_value(value):
            result.append(None)
            continue
        numeric = float(value)
        if ema_value is None:
            seed.append(numeric)
            if len(seed) < period:
                result.append(None)
                continue
            ema_value = sum(seed[-period:]) / period
        else:
            ema_value = numeric * multiplier + ema_value * (1 - multiplier)
        result.append(ema_value)
    return result


def _gt(left: Optional[float], right: Optional[float]) -> bool:
    return _has_value(left) and _has_value(right) and float(left) > float(right)


def _eth_btc_30d_beats_btc(points: List[dict], index: int) -> bool:
    if index < 30:
        return False
    start = points[index - 30]
    end = points[index]
    if not _has_value(start.get("eth_btc")) or not _has_value(end.get("eth_btc")):
        return False
    if not _has_value(start.get("close")) or not _has_value(end.get("close")):
        return False
    eth_btc_return = end["eth_btc"] / start["eth_btc"] - 1
    btc_return = end["close"] / start["close"] - 1
    return eth_btc_return > btc_return


def _boolean_duration_stats(flags: List[bool], points: List[dict]) -> dict:
    durations = []
    current = 0
    for flag in flags:
        if flag:
            current += 1
        elif current:
            durations.append(current)
            current = 0
    if current:
        durations.append(current)
    return {
        "occurrences": len(durations),
        "averageDays": _mean(durations) or 0.0,
        "maxDays": max(durations) if durations else 0,
    }


def _oos_report(points: List[dict], regimes: dict) -> dict:
    train = _window_backtest(points, regimes, "train_dev", "2020-01-01", "2026-04-30", include_daily=False)
    oos = _window_backtest(points, regimes, "oos", "2026-05-01", "2026-05-31", include_daily=True)
    return {
        "trainDev": train,
        "oos": oos,
        "rollingMonthly": _rolling_oos_months(points, regimes, "2024-01", "2026-05"),
        "note": "OOS results are audit-only and must not be used to tune regime or policy rules.",
    }


def _pass_fail_report(policy_report: dict) -> List[dict]:
    btc = next((row for row in policy_report.get("benchmarks", []) if row["id"] == "btc_buy_hold"), {})
    cost_02 = next((row for row in policy_report.get("costSensitivity", []) if row.get("label") == "0.2%"), {})
    cost_rows = {row["id"]: row for row in cost_02.get("rows", [])}
    regime_change = next(
        (row for row in policy_report.get("rebalanceComparison", []) if row.get("rebalance") == "regime_change"),
        {},
    )
    regime_rows = {row["id"]: row for row in regime_change.get("rows", [])}
    rows = []
    for policy in policy_report.get("defaultRun", {}).get("rows", []):
        cost_row = cost_rows.get(policy["id"], {})
        regime_row = regime_rows.get(policy["id"], {})
        mdd_pass = _has_value(policy.get("maxDrawdown")) and _has_value(btc.get("maxDrawdown")) and (
            policy["maxDrawdown"] <= btc["maxDrawdown"] * 0.70
        )
        efficiency_pass = _has_value(policy.get("calmar")) and _has_value(btc.get("calmar")) and (
            policy["calmar"] > btc["calmar"]
        )
        cost_pass = _has_value(cost_row.get("cagr")) and cost_row["cagr"] > 0 and (
            not _has_value(btc.get("maxDrawdown")) or cost_row.get("maxDrawdown", 1) <= btc["maxDrawdown"]
        )
        robustness_pass = _has_value(regime_row.get("cagr")) and regime_row["cagr"] > 0 and (
            not _has_value(btc.get("maxDrawdown")) or regime_row.get("maxDrawdown", 1) <= btc["maxDrawdown"]
        )
        rows.append(
            {
                "policyId": policy["id"],
                "policy": policy["label"],
                "mddReduction": _safe_div(
                    (btc.get("maxDrawdown") or 0) - (policy.get("maxDrawdown") or 0),
                    btc.get("maxDrawdown"),
                ),
                "mddPass": _status(mdd_pass),
                "efficiencyPass": _status(efficiency_pass),
                "costPass": _status(cost_pass),
                "robustnessPass": _status(robustness_pass),
                "policyCalmar": policy.get("calmar"),
                "btcCalmar": btc.get("calmar"),
                "cost02Cagr": cost_row.get("cagr"),
                "regimeChangeCagr": regime_row.get("cagr"),
            }
        )
    return rows


def _symbol_start_rows(payload: dict, points: List[dict]) -> List[dict]:
    source = payload.get("symbolData") or []
    if source:
        return [
            {
                "symbol": row.get("symbol", "").replace("USDT", ""),
                "rawSymbol": row.get("symbol"),
                "start": _date_label(row.get("start")),
                "end": _date_label(row.get("end")),
                "days": row.get("days", 0),
            }
            for row in source
        ]
    if not points:
        return []
    return [
        {
            "symbol": symbol.replace("USDT", ""),
            "rawSymbol": symbol,
            "start": _date_label(points[0]["time"]),
            "end": _date_label(points[-1]["time"]),
            "days": len(points),
        }
        for symbol in ("BTCUSDT", "ETHUSDT", *ALT_SYMBOLS)
    ]


def _alt_composition_summary(points: List[dict]) -> dict:
    daily = []
    counts = []
    current_below3 = 0
    max_below3_run = 0
    for point in points:
        count = _alt_count(point)
        counts.append(count)
        if count < 3:
            current_below3 += 1
            max_below3_run = max(max_below3_run, current_below3)
        else:
            current_below3 = 0
        daily.append(
            {
                "time": point.get("time"),
                "date": _date_label(point.get("time")),
                "count": count,
                "symbols": sorted(_alt_returns(point).keys()),
            }
        )
    below3_days = sum(1 for count in counts if count < 3)
    return {
        "dailyCounts": daily,
        "averageCount": _mean(counts) or 0.0,
        "minCount": min(counts) if counts else 0,
        "maxCount": max(counts) if counts else 0,
        "below3Days": below3_days,
        "below3Pct": below3_days / len(counts) if counts else 0.0,
        "maxBelow3RunDays": max_below3_run,
        "warningThresholds": {"below3Pct": 0.20, "maxBelow3RunDays": 90},
    }


def _alt_contribution_rows(points: List[dict]) -> List[dict]:
    rows = []
    positive_total = 0.0
    by_symbol = {}
    for symbol in ALT_SYMBOLS:
        own_returns = []
        contribution_returns = []
        total_contribution = 0.0
        first_time = None
        for point in points:
            returns = _alt_returns(point)
            if symbol not in returns:
                contribution_returns.append(0.0)
                continue
            value = returns[symbol]
            count = max(1, len(returns))
            first_time = first_time or point.get("time")
            own_returns.append(value)
            contribution = value / count
            contribution_returns.append(contribution)
            total_contribution += contribution
        positive_total += max(0.0, total_contribution)
        by_symbol[symbol] = {
            "symbol": symbol.replace("USDT", ""),
            "rawSymbol": symbol,
            "firstIncluded": _date_label(first_time),
            "includedDays": len(own_returns),
            "ownCumulativeReturn": _compound(own_returns) if own_returns else None,
            "cumulativeContributionReturn": _compound(contribution_returns) if contribution_returns else None,
            "totalContribution": total_contribution,
        }
    for symbol in ALT_SYMBOLS:
        row = by_symbol[symbol]
        row["positiveContributionShare"] = (
            max(0.0, row["totalContribution"]) / positive_total if positive_total > 0 else 0.0
        )
        rows.append(row)
    return sorted(rows, key=lambda row: row["positiveContributionShare"], reverse=True)


def _universe_sensitivity(payload: dict, symbol_rows: List[dict]) -> dict:
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    start_by_symbol = {row["rawSymbol"]: row.get("start") for row in symbol_rows}
    late_cutoff = "2021-01-01"
    late_excluded = [
        symbol
        for symbol in ALT_SYMBOLS
        if (start_by_symbol.get(symbol) or "9999-12-31") <= late_cutoff
    ]
    scenarios = [
        {"id": "current_fixed_8", "label": "현재 8개 알트 고정", "symbols": list(ALT_SYMBOLS), "minAltCount": 3},
        {"id": "btc_eth_only", "label": "BTC/ETH만 사용", "symbols": [], "minAltCount": 1},
        {
            "id": "btc_eth_sol_bnb",
            "label": "BTC/ETH/SOL/BNB만 사용",
            "symbols": ["SOLUSDT", "BNBUSDT"],
            "minAltCount": 1,
        },
        {
            "id": "exclude_ton",
            "label": "TON 제외",
            "symbols": [symbol for symbol in ALT_SYMBOLS if symbol != "TONUSDT"],
            "minAltCount": 3,
        },
        {
            "id": "exclude_late_after_2021",
            "label": "2021 이후 데이터 시작 코인 제외",
            "symbols": late_excluded,
            "minAltCount": 3,
        },
    ]
    rows = []
    benchmark_rows = []
    for scenario in scenarios:
        scenario_points = _points_for_alt_universe(points, scenario["symbols"], scenario["minAltCount"])
        btc_benchmark = _run_benchmark(scenario_points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
        alt_benchmark = _run_benchmark(
            scenario_points,
            "alt_equal_weight_buy_hold",
            BENCHMARKS["alt_equal_weight_buy_hold"],
            min_alt_count=scenario["minAltCount"],
        )
        benchmark_rows.append(
            {
                "scenario": scenario["id"],
                "label": scenario["label"],
                "symbols": [symbol.replace("USDT", "") for symbol in scenario["symbols"]],
                "altBenchmarkTotalReturn": alt_benchmark.get("totalReturn"),
                "btcBenchmarkTotalReturn": btc_benchmark.get("totalReturn"),
            }
        )
        for policy_id, policy in POLICIES.items():
            result = _run_policy(
                scenario_points,
                regimes,
                policy_id,
                policy,
                fee_rate=DEFAULT_FEE_RATE,
                slippage_rate=DEFAULT_SLIPPAGE_RATE,
                rebalance_rule="daily",
                btc_benchmark=btc_benchmark,
                min_alt_count=scenario["minAltCount"],
                include_curve=False,
            )
            rows.append(
                {
                    "scenario": scenario["id"],
                    "scenarioLabel": scenario["label"],
                    "policyId": policy_id,
                    "policy": policy["label"],
                    "symbols": [symbol.replace("USDT", "") for symbol in scenario["symbols"]],
                    "totalReturn": result.get("totalReturn"),
                    "cagr": result.get("cagr"),
                    "maxDrawdown": result.get("maxDrawdown"),
                    "calmar": result.get("calmar"),
                    "sharpe": result.get("sharpe"),
                    "turnover": result.get("turnover"),
                    "totalTradingCost": result.get("totalTradingCost"),
                    "excessReturnVsBtc": result.get("excessReturnVsBtc"),
                }
            )
    period_effect = _universe_period_effect(points, regimes)
    return {
        "scenarios": scenarios,
        "rows": rows,
        "benchmarkRows": benchmark_rows,
        "lateListingCutoff": late_cutoff,
        "periodEffect2020To2021": period_effect,
    }


def _universe_period_effect(points: List[dict], regimes: dict) -> dict:
    current_points = _filter_points(_points_for_alt_universe(points, ALT_SYMBOLS, 3), "2020-01-01", "2021-12-31")
    sol_bnb_points = _filter_points(_points_for_alt_universe(points, ["SOLUSDT", "BNBUSDT"], 1), "2020-01-01", "2021-12-31")
    if len(current_points) < 2 or len(sol_bnb_points) < 2:
        return {"status": "no_data", "message": "2020~2021 비교 데이터 부족"}
    btc = _run_benchmark(current_points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
    current = _run_policy(
        current_points,
        regimes,
        "policy_b_balanced",
        POLICIES["policy_b_balanced"],
        DEFAULT_FEE_RATE,
        DEFAULT_SLIPPAGE_RATE,
        "daily",
        btc,
        min_alt_count=3,
        include_curve=False,
    )
    subset = _run_policy(
        sol_bnb_points,
        regimes,
        "policy_b_balanced",
        POLICIES["policy_b_balanced"],
        DEFAULT_FEE_RATE,
        DEFAULT_SLIPPAGE_RATE,
        "daily",
        btc,
        min_alt_count=1,
        include_curve=False,
    )
    difference = (current.get("totalReturn") or 0) - (subset.get("totalReturn") or 0)
    return {
        "currentFixed8TotalReturn": current.get("totalReturn"),
        "solBnbTotalReturn": subset.get("totalReturn"),
        "difference": difference,
        "status": "warning" if difference > 0.50 else "pass",
        "message": "2020~2021 현재 고정 알트 유니버스 효과 큼" if difference > 0.50 else "2020~2021 유니버스 차이 제한적",
    }


def _universe_warnings(composition: dict, contribution_rows: List[dict], sensitivity: dict) -> List[dict]:
    warnings = []
    top2_share = sum(row.get("positiveContributionShare", 0.0) for row in contribution_rows[:2])
    if top2_share >= 0.60:
        warnings.append(
            {
                "status": "warning",
                "name": "top_alt_concentration",
                "detail": f"상위 2개 알트 기여 비중 {top2_share:.1%}",
            }
        )
    if composition.get("below3Pct", 0.0) >= 0.20 or composition.get("maxBelow3RunDays", 0) >= 90:
        warnings.append(
            {
                "status": "warning",
                "name": "low_alt_count",
                "detail": f"ALT 3개 미만 {composition.get('below3Pct', 0.0):.1%}, 최대 연속 {composition.get('maxBelow3RunDays', 0)}일",
            }
        )
    period = sensitivity.get("periodEffect2020To2021", {})
    if period.get("status") == "warning":
        warnings.append({"status": "warning", "name": "fixed_universe_2020_2021", "detail": period.get("message")})
    if not warnings:
        warnings.append({"status": "pass", "name": "universe_audit", "detail": "정의된 universe warning 조건 없음"})
    return warnings


def _execution_lookahead_check(points: List[dict], regimes: dict, mode: str) -> dict:
    shift_ok = True
    action_ok = True
    for index in range(1, len(points)):
        previous_regime = points[index - 1].get("stable_regime")
        if points[index].get("trade_regime") != previous_regime:
            shift_ok = False
        expected_action = regimes.get(previous_regime, {}).get("action_bias")
        actual_action = points[index].get("trade_action_bias") or regimes.get(points[index].get("trade_regime"), {}).get("action_bias")
        if expected_action and actual_action != expected_action:
            action_ok = False
    open_data_ok = True
    if mode == "next_open":
        open_data_ok = all(point.get("open") is not None and point.get("close") is not None for point in points[1:])
    status = "pass" if shift_ok and action_ok and open_data_ok else "fail"
    return {
        "status": status,
        "tradeRegimeShiftOk": shift_ok,
        "actionBiasShiftOk": action_ok,
        "openCloseDataOk": open_data_ok,
    }


def _window_backtest(
    points: List[dict],
    regimes: dict,
    scope: str,
    start: str,
    end: str,
    include_daily: bool,
) -> dict:
    window_points = _filter_points(points, start, end)
    benchmarks = [
        _run_benchmark(window_points, benchmark_id, benchmark)
        for benchmark_id, benchmark in BENCHMARKS.items()
    ]
    btc = next((row for row in benchmarks if row["id"] == "btc_buy_hold"), {})
    policy_rows = [
        _run_policy(
            window_points,
            regimes,
            policy_id,
            policy,
            DEFAULT_FEE_RATE,
            DEFAULT_SLIPPAGE_RATE,
            "daily",
            btc,
            include_curve=False,
            include_daily=include_daily,
        )
        for policy_id, policy in POLICIES.items()
    ]
    daily = []
    if include_daily:
        for row in policy_rows:
            for record in row.get("dailyRecords", []):
                daily.append({"policyId": row["id"], "policy": row["label"], **record})
    return {
        "scope": scope,
        "start": start,
        "end": end,
        "days": len(window_points),
        "benchmarks": [_comparison_row(row, "benchmark") for row in benchmarks],
        "policies": [_comparison_row(row, "policy") | {
            "turnover": row.get("turnover"),
            "totalTradingCost": row.get("totalTradingCost"),
            "marketParticipation": row.get("marketParticipation"),
        } for row in policy_rows],
        "daily": daily,
    }


def _rolling_oos_months(points: List[dict], regimes: dict, start_month: str, end_month: str) -> List[dict]:
    rows = []
    for month in _month_range(start_month, end_month):
        start, end = _month_bounds(month)
        window_points = _filter_points(points, start, end)
        if len(window_points) < 2:
            continue
        btc = _run_benchmark(window_points, "btc_buy_hold", BENCHMARKS["btc_buy_hold"])
        for policy_id, policy in POLICIES.items():
            result = _run_policy(
                window_points,
                regimes,
                policy_id,
                policy,
                DEFAULT_FEE_RATE,
                DEFAULT_SLIPPAGE_RATE,
                "daily",
                btc,
                include_curve=False,
            )
            rows.append(
                {
                    "month": month,
                    "policyId": policy_id,
                    "policy": policy["label"],
                    "totalReturn": result.get("totalReturn"),
                    "maxDrawdown": result.get("maxDrawdown"),
                    "turnover": result.get("turnover"),
                    "totalTradingCost": result.get("totalTradingCost"),
                    "btcReturn": btc.get("totalReturn"),
                }
            )
    return rows


def _points_for_alt_universe(points: List[dict], symbols: Iterable[str], min_average_count: int) -> List[dict]:
    allowed = set(symbols)
    rows = []
    for point in points:
        row = dict(point)
        alt_returns = {
            symbol: value
            for symbol, value in _alt_returns(point).items()
            if symbol in allowed and _has_value(value)
        }
        alt_open_close_returns = {
            symbol: value
            for symbol, value in (point.get("alt_open_close_returns") or {}).items()
            if symbol in allowed and _has_value(value)
        }
        count = len(alt_returns)
        row["alt_symbols"] = sorted(alt_returns)
        row["alt_returns"] = alt_returns
        row["alt_open_close_returns"] = alt_open_close_returns
        row["alt_count"] = count
        row["alt_average_return"] = _mean(list(alt_returns.values())) if count >= min_average_count else None
        row["alt_average_open_close_return"] = (
            _mean(list(alt_open_close_returns.values()))
            if len(alt_open_close_returns) >= min_average_count
            else None
        )
        rows.append(row)
    return rows


def _filter_points(points: List[dict], start: str, end: str) -> List[dict]:
    start_ts = _date_to_ts(start)
    end_ts = _date_to_ts(end) + 24 * 60 * 60
    return [point for point in points if start_ts <= point.get("time", 0) < end_ts]


def _month_range(start_month: str, end_month: str) -> List[str]:
    start_year, start_m = [int(value) for value in start_month.split("-")]
    end_year, end_m = [int(value) for value in end_month.split("-")]
    months = []
    year, month = start_year, start_m
    while (year, month) <= (end_year, end_m):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _month_bounds(month: str) -> tuple[str, str]:
    year, month_value = [int(value) for value in month.split("-")]
    if month_value == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month_value + 1
    start = f"{year:04d}-{month_value:02d}-01"
    next_start = datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp()
    end_ts = int(next_start) - 24 * 60 * 60
    return start, _date_label(end_ts)


def _alt_returns(point: dict) -> dict:
    values = point.get("alt_returns") or {}
    return {symbol: float(value) for symbol, value in values.items() if _has_value(value)}


def _alt_count(point: dict) -> int:
    returns = _alt_returns(point)
    if returns:
        return len(returns)
    return int(point.get("alt_count") or 0)


def _btc_above_ema200(point: dict) -> bool:
    return _has_value(point.get("close")) and _has_value(point.get("ema200")) and point["close"] > point["ema200"]


def _best_momentum_asset(points: List[dict], index: int, lookback: int) -> Optional[str]:
    scores = {
        "btc": _asset_momentum(points, index, lookback, "return"),
        "eth": _asset_momentum(points, index, lookback, "eth_return"),
        "alt": _asset_momentum(points, index, lookback, "alt_average_return"),
    }
    available = {asset: value for asset, value in scores.items() if _has_value(value)}
    if not available:
        return None
    return max(available, key=lambda asset: available[asset])


def _asset_momentum(points: List[dict], index: int, lookback: int, key: str) -> Optional[float]:
    if index + 1 < lookback:
        return None
    window = points[index - lookback + 1 : index + 1]
    values = [point.get(key) for point in window]
    if any(not _has_value(value) for value in values):
        return None
    return _compound([float(value) for value in values])


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _status(value: bool) -> str:
    return "pass" if value else "fail"


def _has_value(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(float(value))


def _policy_definitions() -> List[dict]:
    return [
        {
            "id": policy_id,
            "label": policy["label"],
            "weights": policy["weights"],
        }
        for policy_id, policy in POLICIES.items()
    ]


def _run_policy(
    points: List[dict],
    regimes: dict,
    policy_id: str,
    policy: dict,
    fee_rate: float,
    slippage_rate: float,
    rebalance_rule: str,
    btc_benchmark: dict,
    execution_mode: str = "conservative",
    min_alt_count: int = 3,
    include_curve: bool = True,
    include_daily: bool = False,
) -> dict:
    current_weights = _cash_weights()
    equity = 1.0
    total_turnover = 0.0
    total_cost = 0.0
    records = []
    equity_curve = _initial_curve(points)
    last_rebalance_week = None
    last_rebalance_signal = None

    for signal_point, return_point in _execution_periods(points, execution_mode):
        action_bias = _trade_action_bias(signal_point, regimes)
        trade_regime = signal_point.get("trade_regime")
        target = _effective_weights(policy["weights"].get(action_bias, {"cash": 1.0}), signal_point, min_alt_count)

        should_rebalance, rebalance_marker = _should_rebalance(
            rebalance_rule,
            signal_point,
            target,
            last_rebalance_week,
            last_rebalance_signal,
            current_weights,
            action_bias,
        )
        turnover = 0.0
        trading_cost = 0.0
        if should_rebalance:
            turnover = _risk_turnover(current_weights, target)
            trading_cost = turnover * (fee_rate + slippage_rate)
            total_turnover += turnover
            total_cost += equity * trading_cost
            current_weights = dict(target)
            if rebalance_rule == "weekly":
                last_rebalance_week = rebalance_marker
            if rebalance_rule in {"regime_change", "signal_change"}:
                last_rebalance_signal = rebalance_marker

        period_returns = _asset_returns(return_point, execution_mode)
        gross_return = _portfolio_return(current_weights, period_returns)
        start_equity = equity
        equity = equity * (1 - trading_cost) * (1 + gross_return)
        net_return = equity / start_equity - 1 if start_equity else 0.0
        non_cash_weight = sum(current_weights.get(asset, 0.0) for asset in RISK_ASSETS)
        records.append(
            {
                "time": return_point["time"],
                "return": net_return,
                "turnover": turnover,
                "tradingCost": start_equity * trading_cost,
                "nonCashWeight": non_cash_weight,
                "actionBias": action_bias,
                "tradeRegime": trade_regime,
                "weights": dict(current_weights),
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})
        current_weights = _drift_weights(current_weights, period_returns, gross_return)

    row = _metric_row(
        row_id=policy_id,
        label=policy["label"],
        kind="policy",
        rebalance_rule=rebalance_rule,
        records=records,
        equity_curve=equity_curve,
        total_turnover=total_turnover,
        total_cost=total_cost,
        include_curve=include_curve,
        include_daily=include_daily,
    )
    row["excessReturnVsBtc"] = _subtract(row.get("totalReturn"), btc_benchmark.get("totalReturn"))
    row["mddReducedVsBtc"] = _mdd_pass(row.get("maxDrawdown"), btc_benchmark.get("maxDrawdown"))
    row["mddReducedVsBtcStatus"] = "pass" if row["mddReducedVsBtc"] else "fail"
    return row


def _run_benchmark(
    points: List[dict],
    benchmark_id: str,
    benchmark: dict,
    execution_mode: str = "conservative",
    min_alt_count: int = 3,
) -> dict:
    weights = _normalize_weights(benchmark["weights"])
    equity = 1.0
    records = []
    equity_curve = _initial_curve(points)

    for signal_point, return_point in _execution_periods(points, execution_mode):
        effective_weights = _effective_weights(weights, signal_point, min_alt_count)
        period_returns = _asset_returns(return_point, execution_mode)
        period_return = _portfolio_return(effective_weights, period_returns)
        equity *= 1 + period_return
        records.append(
            {
                "time": return_point["time"],
                "return": period_return,
                "turnover": 0.0,
                "tradingCost": 0.0,
                "nonCashWeight": sum(effective_weights.get(asset, 0.0) for asset in RISK_ASSETS),
                "weights": dict(effective_weights),
            }
        )
        equity_curve.append({"time": return_point["time"], "value": equity})

    row = _metric_row(
        row_id=benchmark_id,
        label=benchmark["label"],
        kind="benchmark",
        rebalance_rule="buy_hold",
        records=records,
        equity_curve=equity_curve,
        total_turnover=0.0,
        total_cost=0.0,
        include_curve=True,
        include_daily=False,
    )
    row["excessReturnVsBtc"] = 0.0 if benchmark_id == "btc_buy_hold" else None
    row["mddReducedVsBtc"] = None
    row["mddReducedVsBtcStatus"] = None
    return row


def _metric_row(
    row_id: str,
    label: str,
    kind: str,
    rebalance_rule: str,
    records: List[dict],
    equity_curve: List[dict],
    total_turnover: float,
    total_cost: float,
    include_curve: bool,
    include_daily: bool,
) -> dict:
    returns = [record["return"] for record in records]
    final_equity = equity_curve[-1]["value"] if equity_curve else 1.0
    total_return = final_equity - 1
    max_drawdown, drawdown_period = _max_drawdown_period(equity_curve)
    cagr = _cagr(equity_curve)
    volatility = _volatility(returns)
    sharpe = _safe_div((_mean(returns) or 0.0) * TRADING_DAYS, volatility)
    calmar = _safe_div(cagr, max_drawdown)
    win_rate = _safe_div(sum(1 for value in returns if value > 0), len(returns))
    months = _period_returns(records, "%Y-%m", "month")
    years = _period_returns(records, "%Y", "year")
    return {
        "id": row_id,
        "label": label,
        "kind": kind,
        "rebalance": rebalance_rule,
        "days": len(records),
        "totalReturn": total_return,
        "cagr": cagr,
        "maxDrawdown": max_drawdown,
        "volatility": volatility,
        "sharpe": sharpe,
        "calmar": calmar,
        "winRate": win_rate,
        "monthlyReturns": months,
        "yearlyReturns": years,
        "maxDrawdownPeriod": drawdown_period,
        "turnover": total_turnover,
        "averageDailyTurnover": total_turnover / len(records) if records else 0.0,
        "totalTradingCost": total_cost,
        "totalTradingCostPct": total_cost,
        "marketParticipation": _mean([record["nonCashWeight"] for record in records]) or 0.0,
        "equityCurve": equity_curve if include_curve else [],
        "dailyRecords": _daily_records(records, equity_curve) if include_daily else [],
    }


def _trade_action_bias(point: dict, regimes: dict) -> str:
    action_bias = point.get("trade_action_bias")
    if action_bias:
        return action_bias
    trade_regime = point.get("trade_regime")
    if trade_regime:
        return regimes.get(trade_regime, {}).get("action_bias", "wait")
    return "wait"


def _should_rebalance(
    rule: str,
    signal_point: dict,
    target: dict,
    last_rebalance_week,
    last_rebalance_signal,
    current_weights: dict,
    signal_marker=None,
) -> tuple[bool, object]:
    if rule == "daily":
        return True, None
    if rule == "weekly":
        marker = _iso_week(signal_point["time"])
        return marker != last_rebalance_week, marker
    if rule == "regime_change":
        marker = signal_point.get("trade_regime")
        target_changed = _risk_turnover(current_weights, target) > 1e-12
        return target_changed and marker != last_rebalance_signal, marker
    if rule == "signal_change":
        marker = signal_marker
        target_changed = _risk_turnover(current_weights, target) > 1e-12
        return target_changed and marker != last_rebalance_signal, marker
    raise ValueError(f"Unknown rebalance rule: {rule}")


def _execution_periods(points: List[dict], execution_mode: str):
    if execution_mode == "conservative":
        for index in range(0, max(0, len(points) - 1)):
            yield points[index], points[index + 1]
        return
    if execution_mode in {"practical", "next_open"}:
        for index in range(1, len(points)):
            yield points[index], points[index]
        return
    raise ValueError(f"Unknown execution mode: {execution_mode}")


def _effective_weights(weights: dict, signal_point: dict, min_alt_count: int = 3) -> dict:
    normalized = _normalize_weights(weights)
    effective = {asset: 0.0 for asset in ASSETS}
    for asset in RISK_ASSETS:
        weight = normalized.get(asset, 0.0)
        if weight <= 0:
            continue
        if _asset_available(asset, signal_point, min_alt_count):
            effective[asset] += weight
        else:
            effective["cash"] += weight
    effective["cash"] += normalized.get("cash", 0.0)
    return _normalize_weights(effective)


def _asset_available(asset: str, signal_point: dict, min_alt_count: int) -> bool:
    if asset in {"btc", "eth"}:
        return True
    if asset == "alt":
        return (signal_point.get("alt_count") or 0) >= min_alt_count
    return True


def _asset_returns(point: dict, execution_mode: str = "conservative") -> dict:
    if execution_mode == "next_open":
        btc_return = _open_close_return(point)
        eth_return = point.get("eth_open_close_return")
        alt_return = point.get("alt_average_open_close_return")
    else:
        btc_return = point.get("return")
        eth_return = point.get("eth_return")
        alt_return = point.get("alt_average_return")
    return {
        "btc": _finite_or_zero(btc_return),
        "eth": _finite_or_zero(eth_return),
        "alt": _finite_or_zero(alt_return),
        "cash": 0.0,
    }


def _open_close_return(point: dict) -> Optional[float]:
    open_value = point.get("open")
    close = point.get("close")
    if not open_value or close is None:
        return None
    return close / open_value - 1


def _portfolio_return(weights: dict, period_returns: dict) -> float:
    return sum(weights.get(asset, 0.0) * period_returns.get(asset, 0.0) for asset in ASSETS)


def _drift_weights(weights: dict, period_returns: dict, gross_return: float) -> dict:
    denominator = 1 + gross_return
    if denominator <= 0:
        return _cash_weights()
    drifted = {
        asset: weights.get(asset, 0.0) * (1 + period_returns.get(asset, 0.0)) / denominator
        for asset in ASSETS
    }
    return _normalize_weights(drifted)


def _risk_turnover(current_weights: dict, target_weights: dict) -> float:
    return sum(abs(target_weights.get(asset, 0.0) - current_weights.get(asset, 0.0)) for asset in RISK_ASSETS)


def _normalize_weights(weights: dict) -> dict:
    clean = {asset: max(0.0, float(weights.get(asset, 0.0) or 0.0)) for asset in ASSETS}
    total = sum(clean.values())
    if total <= 0:
        return _cash_weights()
    return {asset: clean[asset] / total for asset in ASSETS}


def _cash_weights() -> dict:
    return {"btc": 0.0, "eth": 0.0, "alt": 0.0, "cash": 1.0}


def _initial_curve(points: List[dict]) -> List[dict]:
    if not points:
        return [{"time": None, "value": 1.0}]
    return [{"time": points[0]["time"], "value": 1.0}]


def _equity_curves(policy_rows: List[dict], benchmark_rows: List[dict]) -> List[dict]:
    btc = next((row for row in benchmark_rows if row["id"] == "btc_buy_hold"), None)
    rows = list(policy_rows)
    if btc:
        rows.append(btc)
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "kind": row["kind"],
            "points": row.get("equityCurve", []),
        }
        for row in rows
    ]


def _daily_records(records: List[dict], equity_curve: List[dict]) -> List[dict]:
    equity_by_time = {point["time"]: point["value"] for point in equity_curve}
    rows = []
    for record in records:
        weights = record.get("weights", {})
        rows.append(
            {
                "time": record["time"],
                "date": _date_label(record["time"]),
                "return": record["return"],
                "turnover": record["turnover"],
                "tradingCost": record["tradingCost"],
                "marketParticipation": record["nonCashWeight"],
                "actionBias": record.get("actionBias"),
                "tradeRegime": record.get("tradeRegime"),
                "btcWeight": weights.get("btc", 0.0),
                "ethWeight": weights.get("eth", 0.0),
                "altWeight": weights.get("alt", 0.0),
                "cashWeight": weights.get("cash", 0.0),
                "equity": equity_by_time.get(record["time"]),
            }
        )
    return rows


def _period_returns(records: List[dict], date_format: str, key: str) -> List[dict]:
    grouped = defaultdict(list)
    for record in records:
        label = datetime.fromtimestamp(record["time"], tz=timezone.utc).strftime(date_format)
        grouped[label].append(record["return"])
    return [
        {key: label, "return": _compound(returns)}
        for label, returns in sorted(grouped.items())
    ]


def _max_drawdown_period(equity_curve: List[dict]) -> tuple[Optional[float], dict]:
    if not equity_curve:
        return None, {"start": None, "end": None, "days": 0}
    peak_value = equity_curve[0]["value"]
    peak_time = equity_curve[0]["time"]
    worst_drawdown = 0.0
    worst_start = peak_time
    worst_end = peak_time
    for point in equity_curve:
        value = point["value"]
        if value > peak_value:
            peak_value = value
            peak_time = point["time"]
        drawdown = value / peak_value - 1 if peak_value else 0.0
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown
            worst_start = peak_time
            worst_end = point["time"]
    return abs(worst_drawdown), {
        "start": _date_label(worst_start),
        "end": _date_label(worst_end),
        "days": _days_between(worst_start, worst_end),
    }


def _cagr(equity_curve: List[dict]) -> Optional[float]:
    if len(equity_curve) < 2:
        return None
    start = equity_curve[0]
    end = equity_curve[-1]
    if not start["time"] or not end["time"] or start["value"] <= 0:
        return None
    years = max((end["time"] - start["time"]) / (365.25 * 24 * 60 * 60), 1 / 365.25)
    return (end["value"] / start["value"]) ** (1 / years) - 1


def _volatility(values: List[float]) -> Optional[float]:
    stdev = _stdev(values)
    return stdev * math.sqrt(TRADING_DAYS) if stdev is not None else None


def _compound(values: Iterable[float]) -> float:
    equity = 1.0
    for value in values:
        equity *= 1 + value
    return equity - 1


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _stdev(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    average = _mean(values) or 0.0
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _subtract(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None or right is None:
        return None
    return left - right


def _mdd_pass(policy_mdd: Optional[float], btc_mdd: Optional[float]) -> bool:
    if policy_mdd is None or btc_mdd is None:
        return False
    return policy_mdd < btc_mdd


def _finite_or_zero(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    value = float(value)
    return value if math.isfinite(value) else 0.0


def _iso_week(timestamp: int) -> tuple[int, int]:
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).isocalendar()
    return date.year, date.week


def _date_label(timestamp: Optional[int]) -> Optional[str]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def _date_to_ts(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def _days_between(start: Optional[int], end: Optional[int]) -> int:
    if start is None or end is None:
        return 0
    return max(0, int((end - start) // (24 * 60 * 60)))
