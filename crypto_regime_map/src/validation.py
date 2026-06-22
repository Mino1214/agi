"""Validation report generation for regime stability and performance."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from policy_backtest import (
    build_alt_universe_robustness_report,
    build_eth_strength_sensitivity_report,
    build_hybrid_overlay_challenge_report,
    build_overlay_ablation_report,
    build_policy_backtest_audit_report,
    build_policy_backtest_report,
    build_risk_normalized_comparison_report,
    build_simple_baseline_challenge_report,
)


EVENT_WINDOWS = [
    {"event": "2020-03 코로나 폭락", "start": "2020-03-01", "end": "2020-03-31"},
    {"event": "2021-05 폭락", "start": "2021-05-01", "end": "2021-05-31"},
    {"event": "2022-05 루나", "start": "2022-05-01", "end": "2022-05-31"},
    {"event": "2022-11 FTX", "start": "2022-11-01", "end": "2022-11-30"},
    {"event": "2024-01 BTC ETF", "start": "2024-01-01", "end": "2024-01-31"},
]

OBSERVE_LIMIT_DAYS_V3 = 7
OBSERVE_LIMIT_CHECK_WINDOW = {
    "name": "2021-02-26 ~ 2021-04-22",
    "start": "2021-02-26",
    "end": "2021-04-22",
}

UPTREND = "uptrend"
LARGE_CAP_LEAD = "large_cap_lead"
ETH_STRENGTH = "eth_strength"
DEFENSIVE = "defensive"
SHOCK = "shock"
NEUTRAL = "neutral"
OBSERVE = "observe"


def build_validation_report(payload: dict) -> dict:
    points = payload.get("points", [])
    policy_backtest_report = build_policy_backtest_report(payload)
    simple_baseline_report = build_simple_baseline_challenge_report(payload, policy_backtest_report)
    return {
        "durationSummary": _duration_summary(payload, "stable_regime"),
        "performanceSummary": _performance_summary(payload, "stable_regime"),
        "rawDurationSummary": _duration_summary(payload, "raw_regime"),
        "rawPerformanceSummary": _performance_summary(payload, "raw_regime"),
        "stabilityComparison": _stability_comparison(payload),
        "returnComparison": _return_comparison(payload),
        "eventChecks": _event_checks(payload),
        "observe": _observe_report(payload),
        "v2v3Comparison": _v2_v3_comparison(payload),
        "benchmarkReport": _benchmark_report(payload),
        "labelRevalidationReport": _label_revalidation_report(payload),
        "labelMigrationReport": _label_migration_report(payload),
        "actionBiasPerformance": _action_bias_performance_report(payload),
        "policyBacktestReport": policy_backtest_report,
        "policyBacktestAuditReport": build_policy_backtest_audit_report(payload, policy_backtest_report),
        "simpleBaselineChallengeReport": simple_baseline_report,
        "riskNormalizedComparisonReport": build_risk_normalized_comparison_report(
            payload,
            policy_backtest_report,
            simple_baseline_report,
        ),
        "hybridOverlayChallengeReport": build_hybrid_overlay_challenge_report(payload, simple_baseline_report),
        "overlayAblationReport": build_overlay_ablation_report(payload),
        "ethStrengthSensitivityReport": build_eth_strength_sensitivity_report(payload),
        "altUniverseRobustnessReport": build_alt_universe_robustness_report(payload),
        "lookahead": _lookahead_report(points),
    }


def _duration_summary(payload: dict, regime_key: str) -> List[dict]:
    regimes = payload.get("regimes", {})
    grouped = defaultdict(list)
    for segment in _segments(payload.get("points", []), regime_key):
        grouped[segment["regime"]].append(segment["count"])

    rows = []
    for regime, meta in regimes.items():
        durations = grouped.get(regime, [])
        total = sum(durations)
        rows.append(
            {
                "regime": regime,
                "label": meta["label"],
                "color": meta["color"],
                "occurrences": len(durations),
                "totalDays": total,
                "averageDays": total / len(durations) if durations else 0,
                "minDays": min(durations) if durations else 0,
                "maxDays": max(durations) if durations else 0,
            }
        )
    return rows


def _performance_summary(payload: dict, regime_key: str) -> List[dict]:
    regimes = payload.get("regimes", {})
    grouped = defaultdict(list)
    points = payload.get("points", [])
    for index in range(1, len(points)):
        applied_regime = points[index - 1].get(regime_key)
        if applied_regime:
            grouped[applied_regime].append(points[index])

    rows = []
    for regime, meta in regimes.items():
        points = grouped.get(regime, [])
        btc_returns = _values(point.get("return") for point in points)
        eth_returns = _values(point.get("eth_return") for point in points)
        alt_returns = _values(point.get("alt_average_return") for point in points)
        rows.append(
            {
                "regime": regime,
                "label": meta["label"],
                "color": meta["color"],
                "days": len(points),
                "btcAverageDailyReturn": _mean(btc_returns),
                "btcCumulativeReturn": _compound(btc_returns),
                "ethAverageDailyReturn": _mean(eth_returns),
                "altAverageDailyReturn": _mean(alt_returns),
                "volatility": _stdev(btc_returns),
                "maxDrawdown": _max_drawdown(btc_returns),
            }
        )
    return rows


def _benchmark_report(payload: dict) -> dict:
    return {
        "stable": _benchmark_scope(payload, "stable", "stable_regime", shifted=True),
        "trade": _benchmark_scope(payload, "trade", "trade_regime", shifted=False),
    }


def _label_migration_report(payload: dict) -> dict:
    rows = []
    regimes = payload.get("regimes", {})
    for row in payload.get("regimeLabelMigration", []):
        regime = row["regime"]
        meta = regimes.get(regime, {})
        rows.append(
            {
                "legacy": row["legacy"],
                "legacyLabel": row["legacyLabel"],
                "regime": regime,
                "label": row["label"],
                "actionBias": meta.get("action_bias"),
                "color": meta.get("color"),
            }
        )
    return {"version": "v4", "rows": rows}


def _action_bias_performance_report(payload: dict) -> dict:
    return {
        "stable": _action_bias_scope(payload, "stable", "stable_regime", shifted=True),
        "trade": _action_bias_scope(payload, "trade", "trade_regime", shifted=False),
    }


def _action_bias_scope(payload: dict, scope: str, regime_key: str, shifted: bool) -> dict:
    grouped = defaultdict(list)
    regimes_by_bias = defaultdict(set)
    points = payload.get("points", [])
    regimes = payload.get("regimes", {})
    if shifted:
        for index in range(1, len(points)):
            regime = points[index - 1].get(regime_key)
            action_bias = regimes.get(regime, {}).get("action_bias")
            if action_bias:
                grouped[action_bias].append(points[index])
                regimes_by_bias[action_bias].add(regime)
    else:
        for point in points:
            regime = point.get(regime_key)
            action_bias = regimes.get(regime, {}).get("action_bias")
            if action_bias:
                grouped[action_bias].append(point)
                regimes_by_bias[action_bias].add(regime)

    rows = []
    for action_bias in sorted(grouped):
        rows.append(_action_bias_row(action_bias, sorted(regimes_by_bias[action_bias]), grouped[action_bias]))
    return {
        "scope": scope,
        "basis": "previous_stable_regime" if shifted else "same_bar_trade_regime",
        "rows": rows,
    }


def _action_bias_row(action_bias: str, regimes: List[str], points: List[dict]) -> dict:
    btc_returns = _values(point.get("return") for point in points)
    eth_returns = _values(point.get("eth_return") for point in points)
    alt_returns = _values(point.get("alt_average_return") for point in points)
    assets = {
        "btc": _compound(btc_returns),
        "eth": _compound(eth_returns),
        "alt": _compound(alt_returns),
        "cash": 0.0,
    }
    best_asset = _best_asset(assets)
    return {
        "actionBias": action_bias,
        "regimes": regimes,
        "days": len(points),
        "btcAverageDailyReturn": _mean(btc_returns),
        "btcCumulativeReturn": assets["btc"],
        "ethAverageDailyReturn": _mean(eth_returns),
        "ethCumulativeReturn": assets["eth"],
        "altAverageDailyReturn": _mean(alt_returns),
        "altCumulativeReturn": assets["alt"],
        "cashCumulativeReturn": assets["cash"],
        "bestAsset": best_asset,
        "bestAssetReturn": assets.get(best_asset) if best_asset else None,
    }


def _benchmark_scope(payload: dict, scope: str, regime_key: str, shifted: bool) -> dict:
    grouped = defaultdict(list)
    points = payload.get("points", [])
    if shifted:
        for index in range(1, len(points)):
            applied_regime = points[index - 1].get(regime_key)
            if applied_regime:
                grouped[applied_regime].append(points[index])
    else:
        for point in points:
            applied_regime = point.get(regime_key)
            if applied_regime:
                grouped[applied_regime].append(point)

    rows = []
    for regime, meta in payload.get("regimes", {}).items():
        regime_points = grouped.get(regime, [])
        row = _benchmark_row(regime, meta, regime_points)
        rows.append(row)
    return {
        "scope": scope,
        "basis": "previous_stable_regime" if shifted else "same_bar_trade_regime",
        "rows": rows,
    }


def _label_revalidation_report(payload: dict) -> dict:
    benchmark = _benchmark_report(payload)
    return {
        "stable": _label_revalidation_scope(
            payload,
            "stable",
            "stable_regime",
            shifted=True,
            benchmark_scope=benchmark["stable"],
        ),
        "trade": _label_revalidation_scope(
            payload,
            "trade",
            "trade_regime",
            shifted=False,
            benchmark_scope=benchmark["trade"],
        ),
    }


def _label_revalidation_scope(
    payload: dict,
    scope: str,
    regime_key: str,
    shifted: bool,
    benchmark_scope: dict,
) -> dict:
    benchmark_rows = {row["regime"]: row for row in benchmark_scope["rows"]}
    large_cap_points = _applied_points_for_regime(payload, regime_key, shifted, LARGE_CAP_LEAD)
    eth_strength_points = _applied_points_for_regime(payload, regime_key, shifted, ETH_STRENGTH)
    defensive_points = _applied_points_for_regime(payload, regime_key, shifted, DEFENSIVE)
    shock_points = _applied_points_for_regime(payload, regime_key, shifted, SHOCK)

    large_cap_analysis = _large_cap_label_analysis(large_cap_points, benchmark_rows.get(LARGE_CAP_LEAD, {}))
    eth_strength_analysis = _eth_strength_label_analysis(eth_strength_points, benchmark_rows.get(ETH_STRENGTH, {}))
    defensive_analysis = _defensive_label_analysis(DEFENSIVE, defensive_points, benchmark_rows.get(DEFENSIVE, {}))
    shock_analysis = _defensive_label_analysis(SHOCK, shock_points, benchmark_rows.get(SHOCK, {}))
    candidates = _label_candidates(
        payload,
        benchmark_rows,
        large_cap_analysis,
        eth_strength_analysis,
        defensive_analysis,
        shock_analysis,
    )
    return {
        "scope": scope,
        "basis": benchmark_scope["basis"],
        "largeCapLead": large_cap_analysis,
        "ethStrength": eth_strength_analysis,
        "defensive": defensive_analysis,
        "shock": shock_analysis,
        "candidates": candidates,
    }


def _applied_points_for_regime(payload: dict, regime_key: str, shifted: bool, regime: str) -> List[dict]:
    points = payload.get("points", [])
    rows = []
    if shifted:
        for index in range(1, len(points)):
            if points[index - 1].get(regime_key) == regime:
                rows.append(points[index])
    else:
        for point in points:
            if point.get(regime_key) == regime:
                rows.append(point)
    return rows


def _large_cap_label_analysis(points: List[dict], benchmark_row: dict) -> dict:
    non_winning_segments = _condition_segments(
        points,
        lambda point: _best_daily_risk_asset(point) not in {None, "btc"},
        "BTC가 ETH/알트보다 약함",
    )
    return {
        "days": len(points),
        "bestAsset": benchmark_row.get("bestRiskAsset"),
        "bestAssetReturn": benchmark_row.get("bestRiskAssetReturn"),
        "btcCumulativeReturn": benchmark_row.get("btcCumulativeReturn"),
        "ethCumulativeReturn": benchmark_row.get("ethCumulativeReturn"),
        "altCumulativeReturn": benchmark_row.get("altCumulativeReturn"),
        "nonWinningDays": sum(segment["days"] for segment in non_winning_segments),
        "nonWinningSegments": non_winning_segments,
    }


def _eth_strength_label_analysis(points: List[dict], benchmark_row: dict) -> dict:
    weaker_segments = _condition_segments(
        points,
        lambda point: _daily_return(point, "alt") is not None
        and _daily_return(point, "btc") is not None
        and _daily_return(point, "alt") <= _daily_return(point, "btc"),
        "알트 평균이 BTC보다 약함",
    )
    eth_btc_check = _eth_btc_strength_check(points)
    return {
        "days": len(points),
        "bestAsset": benchmark_row.get("bestRiskAsset"),
        "bestAssetReturn": benchmark_row.get("bestRiskAssetReturn"),
        "btcCumulativeReturn": benchmark_row.get("btcCumulativeReturn"),
        "ethCumulativeReturn": benchmark_row.get("ethCumulativeReturn"),
        "altCumulativeReturn": benchmark_row.get("altCumulativeReturn"),
        "weakerThanBtcDays": sum(segment["days"] for segment in weaker_segments),
        "weakerThanBtcSegments": weaker_segments,
        "ethBtcStrengthCheck": eth_btc_check,
    }


def _defensive_label_analysis(regime: str, points: List[dict], benchmark_row: dict) -> dict:
    holding_advantage_segments = _condition_segments(
        points,
        lambda point: (_best_daily_risk_return(point) or 0) > 0,
        "보유가 현금보다 유리",
    )
    rebound_segments = _condition_segments(
        points,
        _is_rebound_candidate,
        "BTC 반등 후보",
    )
    return {
        "regime": regime,
        "days": len(points),
        "bestAsset": benchmark_row.get("bestAsset"),
        "bestAssetReturn": benchmark_row.get("bestAssetReturn"),
        "btcCumulativeReturn": benchmark_row.get("btcCumulativeReturn"),
        "ethCumulativeReturn": benchmark_row.get("ethCumulativeReturn"),
        "altCumulativeReturn": benchmark_row.get("altCumulativeReturn"),
        "cashCumulativeReturn": benchmark_row.get("cashCumulativeReturn"),
        "holdingAdvantageDays": sum(segment["days"] for segment in holding_advantage_segments),
        "holdingAdvantageSegments": holding_advantage_segments,
        "reboundDays": sum(segment["days"] for segment in rebound_segments),
        "reboundSegments": rebound_segments,
    }


def _eth_btc_strength_check(points: List[dict]) -> dict:
    valid_points = [
        point
        for point in points
        if _daily_return(point, "btc") is not None and _daily_return(point, "alt") is not None
    ]
    rising_points = [point for point in valid_points if _eth_btc_rising(point)]
    confirmed_points = [point for point in valid_points if _eth_btc_confirmed_rising(point)]
    alt_beats_btc = [point for point in valid_points if _daily_return(point, "alt") > _daily_return(point, "btc")]
    rising_and_alt_beats = [
        point
        for point in rising_points
        if _daily_return(point, "alt") > _daily_return(point, "btc")
    ]
    confirmed_and_alt_beats = [
        point
        for point in confirmed_points
        if _daily_return(point, "alt") > _daily_return(point, "btc")
    ]
    hit_rate = len(confirmed_and_alt_beats) / len(confirmed_points) if confirmed_points else None
    coverage = len(confirmed_and_alt_beats) / len(alt_beats_btc) if alt_beats_btc else None
    status = _eth_btc_strength_status(hit_rate)
    return {
        "days": len(valid_points),
        "ethBtcRisingDays": len(rising_points),
        "ethBtcConfirmedDays": len(confirmed_points),
        "altBeatsBtcDays": len(alt_beats_btc),
        "risingAndAltBeatsDays": len(rising_and_alt_beats),
        "confirmedAndAltBeatsDays": len(confirmed_and_alt_beats),
        "confirmedHitRate": hit_rate,
        "confirmedCoverage": coverage,
        "status": status["status"],
        "message": status["message"],
    }


def _eth_btc_strength_status(hit_rate: Optional[float]) -> dict:
    if hit_rate is None:
        return {"status": "no_data", "message": "ETH/BTC 확인 데이터 부족"}
    if hit_rate >= 0.55:
        return {"status": "pass", "message": "ETH/BTC 상승 조건이 알트 강세를 충분히 설명"}
    if hit_rate >= 0.45:
        return {"status": "warning", "message": "ETH/BTC 상승 조건 설명력이 약함"}
    return {"status": "fail", "message": "ETH/BTC 상승 조건이 알트 강세를 설명하지 못함"}


def _label_candidates(
    payload: dict,
    benchmark_rows: dict,
    large_cap_analysis: dict,
    eth_strength_analysis: dict,
    defensive_analysis: dict,
    shock_analysis: dict,
) -> List[dict]:
    regimes = payload.get("regimes", {})
    rows = [
        _label_candidate_row(
            regimes,
            LARGE_CAP_LEAD,
            "large_cap_lead",
            benchmark_rows.get(LARGE_CAP_LEAD, {}),
            "v4에서 BTC 단독 주도가 아니라 BTC/ETH 대형주 주도 상태로 명명",
            True,
        ),
        _label_candidate_row(
            regimes,
            ETH_STRENGTH,
            "eth_strength",
            benchmark_rows.get(ETH_STRENGTH, {}),
            "v4에서 알트 수익률 예측이 아니라 ETH/BTC 강세 관측 상태로 명명",
            True,
        ),
        _label_candidate_row(
            regimes,
            DEFENSIVE,
            "defensive",
            benchmark_rows.get(DEFENSIVE, {}),
            "v4에서 하락 예측이 아니라 리스크 축소가 필요한 방어 상태로 명명",
            True,
        ),
        _label_candidate_row(
            regimes,
            SHOCK,
            "shock",
            benchmark_rows.get(SHOCK, {}),
            "v4에서 지속 위험 예측이 아니라 급격한 충격 상태로 명명",
            True,
        ),
    ]
    return rows


def _label_candidate_row(
    regimes: dict,
    regime: str,
    candidate: str,
    benchmark_row: dict,
    reason: str,
    recommended: bool,
) -> dict:
    meta = regimes.get(regime, {})
    return {
        "regime": regime,
        "currentLabel": meta.get("label", regime),
        "candidate": candidate,
        "recommendation": "recommended" if recommended else "monitor",
        "benchmarkStatus": benchmark_row.get("validationStatus"),
        "bestAsset": benchmark_row.get("bestAsset"),
        "reason": reason,
    }


def _condition_segments(points: List[dict], predicate, reason: str) -> List[dict]:
    segments = []
    current = []
    for point in points:
        matches = predicate(point)
        contiguous = not current or point["time"] - current[-1]["time"] <= 24 * 60 * 60
        if matches and contiguous:
            current.append(point)
            continue
        if current:
            segments.append(_asset_segment_row(current, reason))
            current = []
        if matches:
            current.append(point)
    if current:
        segments.append(_asset_segment_row(current, reason))
    return segments


def _asset_segment_row(points: List[dict], reason: str) -> dict:
    btc_returns = _values(point.get("return") for point in points)
    eth_returns = _values(point.get("eth_return") for point in points)
    alt_returns = _values(point.get("alt_average_return") for point in points)
    assets = {
        "btc": _compound(btc_returns),
        "eth": _compound(eth_returns),
        "alt": _compound(alt_returns),
        "cash": 0.0,
    }
    best_risk_asset = _best_asset({key: assets[key] for key in ("btc", "eth", "alt")})
    best_asset = _best_asset(assets)
    return {
        "start": _date_label(points[0]["time"]),
        "end": _date_label(points[-1]["time"]),
        "days": len(points),
        "btcCumulativeReturn": assets["btc"],
        "ethCumulativeReturn": assets["eth"],
        "altCumulativeReturn": assets["alt"],
        "cashCumulativeReturn": assets["cash"],
        "bestRiskAsset": best_risk_asset,
        "bestRiskAssetReturn": assets.get(best_risk_asset) if best_risk_asset else None,
        "bestAsset": best_asset,
        "bestAssetReturn": assets.get(best_asset) if best_asset else None,
        "reason": reason,
        "reboundCandidate": any(_is_rebound_candidate(point) for point in points),
    }


def _daily_return(point: dict, asset: str) -> Optional[float]:
    key = {
        "btc": "return",
        "eth": "eth_return",
        "alt": "alt_average_return",
    }[asset]
    value = point.get(key)
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _best_daily_risk_asset(point: dict) -> Optional[str]:
    return _best_asset(
        {
            "btc": _daily_return(point, "btc"),
            "eth": _daily_return(point, "eth"),
            "alt": _daily_return(point, "alt"),
        }
    )


def _best_daily_risk_return(point: dict) -> Optional[float]:
    asset = _best_daily_risk_asset(point)
    if not asset:
        return None
    return _daily_return(point, asset)


def _eth_btc_rising(point: dict) -> bool:
    eth_btc = point.get("eth_btc")
    eth_ema50 = point.get("eth_btc_ema50")
    return bool(eth_btc is not None and eth_ema50 is not None and eth_btc > eth_ema50)


def _eth_btc_confirmed_rising(point: dict) -> bool:
    eth_btc = point.get("eth_btc")
    eth_ema50 = point.get("eth_btc_ema50")
    eth_ema200 = point.get("eth_btc_ema200")
    return bool(
        eth_btc is not None
        and eth_ema50 is not None
        and eth_ema200 is not None
        and eth_btc > eth_ema50
        and eth_ema50 >= eth_ema200
    )


def _is_rebound_candidate(point: dict) -> bool:
    btc_return = _daily_return(point, "btc")
    close = point.get("close")
    ema50 = point.get("ema50")
    return bool(
        btc_return is not None
        and btc_return > 0
        and close is not None
        and ema50 is not None
        and close > ema50
    )


def _benchmark_row(regime: str, meta: dict, points: List[dict]) -> dict:
    btc_returns = _values(point.get("return") for point in points)
    eth_returns = _values(point.get("eth_return") for point in points)
    alt_returns = _values(point.get("alt_average_return") for point in points)
    assets = {
        "btc": _compound(btc_returns),
        "eth": _compound(eth_returns),
        "alt": _compound(alt_returns),
        "cash": 0.0,
    }
    has_long_data = any(_has_value(assets.get(asset)) for asset in ("btc", "eth", "alt"))
    best_asset = _best_asset(assets) if has_long_data else None
    best_risk_asset = _best_asset({key: assets[key] for key in ("btc", "eth", "alt")})
    validation = _benchmark_validation(regime, assets, best_risk_asset)
    return {
        "regime": regime,
        "label": meta["label"],
        "color": meta["color"],
        "days": len(points),
        "btcAverageDailyReturn": _mean(btc_returns),
        "btcCumulativeReturn": assets["btc"],
        "ethAverageDailyReturn": _mean(eth_returns),
        "ethCumulativeReturn": assets["eth"],
        "altAverageDailyReturn": _mean(alt_returns),
        "altCumulativeReturn": assets["alt"],
        "cashCumulativeReturn": assets["cash"],
        "bestAsset": best_asset,
        "bestAssetReturn": assets.get(best_asset) if best_asset else None,
        "bestRiskAsset": best_risk_asset,
        "bestRiskAssetReturn": assets.get(best_risk_asset) if best_risk_asset else None,
        "cashWasBest": best_asset == "cash",
        "shortNeeded": regime == DEFENSIVE and _all_long_assets_below_cash(assets),
        "validationStatus": validation["status"],
        "validationMessage": validation["message"],
    }


def _best_asset(assets: dict) -> Optional[str]:
    available = {
        asset: value
        for asset, value in assets.items()
        if value is not None and math.isfinite(float(value))
    }
    if not available:
        return None
    priority = {"btc": 0, "eth": 1, "alt": 2, "cash": 3}
    return max(available, key=lambda asset: (available[asset], -priority.get(asset, 99)))


def _benchmark_validation(regime: str, assets: dict, best_risk_asset: Optional[str]) -> dict:
    btc = assets.get("btc")
    eth = assets.get("eth")
    alt = assets.get("alt")
    cash = assets.get("cash", 0.0)
    if not _has_value(btc) or not _has_value(eth) or not _has_value(alt):
        return {"status": "no_data", "message": "데이터 부족"}

    if regime == ETH_STRENGTH:
        if eth <= btc:
            return {"status": "warning", "message": "ETH strength인데 ETH가 BTC보다 약함"}
        return {"status": "pass", "message": "ETH가 BTC보다 강함"}
    if regime == LARGE_CAP_LEAD:
        if alt > max(btc, eth):
            return {"status": "fail", "message": "대형주 주도인데 알트 평균이 더 강함"}
        return {"status": "pass", "message": "BTC/ETH가 알트보다 강함"}
    if regime == DEFENSIVE:
        if btc > 0:
            return {"status": "warning", "message": "defensive인데 BTC 수익률이 양수"}
        if _all_long_assets_below_cash(assets):
            return {"status": "pass", "message": "현금 우위, 숏 검토 구간"}
        return {"status": "pass", "message": "현금보다 나은 보유 자산 존재"}
    if regime == SHOCK:
        if max(btc, eth, alt) > cash:
            return {"status": "warning", "message": "shock인데 보유가 현금보다 나음"}
        return {"status": "pass", "message": "현금 방어 우위"}
    if regime == UPTREND:
        return {"status": "pass", "message": f"{_asset_label(best_risk_asset)} 우위"}
    if regime == OBSERVE:
        return {"status": "pass", "message": "임시 대기 구간"}
    return {"status": "pass", "message": f"{_asset_label(best_risk_asset)} 우위"}


def _all_long_assets_below_cash(assets: dict) -> bool:
    return all(
        _has_value(assets.get(asset)) and assets[asset] < 0
        for asset in ("btc", "eth", "alt")
    )


def _has_value(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(float(value))


def _asset_label(asset: Optional[str]) -> str:
    labels = {
        "btc": "BTC",
        "eth": "ETH",
        "alt": "상위 알트",
        "cash": "현금",
    }
    return labels.get(asset or "", "-")


def _stability_comparison(payload: dict) -> List[dict]:
    return [
        _stability_row(payload, "raw", "raw_regime"),
        _stability_row(payload, "stable", "stable_regime"),
    ]


def _stability_row(payload: dict, scope: str, regime_key: str) -> dict:
    segments = _segments(payload.get("points", []), regime_key)
    durations = [segment["count"] for segment in segments]
    by_regime = defaultdict(list)
    for segment in segments:
        by_regime[segment["regime"]].append(segment["count"])
    return {
        "scope": scope,
        "changeCount": max(0, len(segments) - 1),
        "averageDays": _mean(durations) or 0,
        "minDays": min(durations) if durations else 0,
        "maxDays": max(durations) if durations else 0,
        "bullAverageDays": _mean(by_regime.get(UPTREND, [])) or 0,
        "bearAverageDays": _mean(by_regime.get(DEFENSIVE, [])) or 0,
        "btcAverageDays": _mean(by_regime.get(LARGE_CAP_LEAD, [])) or 0,
        "altAverageDays": _mean(by_regime.get(ETH_STRENGTH, [])) or 0,
    }


def _return_comparison(payload: dict) -> List[dict]:
    raw = {row["regime"]: row for row in _performance_summary(payload, "raw_regime")}
    stable = {row["regime"]: row for row in _performance_summary(payload, "stable_regime")}
    rows = []
    for regime, meta in payload.get("regimes", {}).items():
        raw_row = raw.get(regime, {})
        stable_row = stable.get(regime, {})
        rows.append(
            {
                "regime": regime,
                "label": meta["label"],
                "color": meta["color"],
                "rawDays": raw_row.get("days", 0),
                "rawBtcAverageDailyReturn": raw_row.get("btcAverageDailyReturn"),
                "rawBtcCumulativeReturn": raw_row.get("btcCumulativeReturn"),
                "stableDays": stable_row.get("days", 0),
                "stableBtcAverageDailyReturn": stable_row.get("btcAverageDailyReturn"),
                "stableBtcCumulativeReturn": stable_row.get("btcCumulativeReturn"),
            }
        )
    return rows


def _v2_v3_comparison(payload: dict) -> Optional[dict]:
    points = payload.get("points", [])
    if not _has_regime_key(points, "v2_stable_regime"):
        return None

    event_risk_delay = _v2_v3_event_risk_delay(points)
    return {
        "summary": _v2_v3_summary(payload, event_risk_delay),
        "eventRiskDelay": event_risk_delay,
        "regimeReturns": _v2_v3_regime_returns(payload),
        "observeLimitCheck": _observe_limit_check(payload),
    }


def _v2_v3_summary(payload: dict, event_risk_delay: List[dict]) -> List[dict]:
    rows = []
    for version, key in (("v2", "v2_stable_regime"), ("v3", "stable_regime")):
        stability = _stability_row(payload, version, key)
        observe = _observe_stats(payload.get("points", []), key)
        delays = _values(row.get(f"{version}RiskDelayDays") for row in event_risk_delay)
        rows.append(
            {
                "version": version,
                "stableChangeCount": stability["changeCount"],
                "averageDays": stability["averageDays"],
                "observeTotalDays": observe["totalDays"],
                "observeMaxDays": observe["maxDays"],
                "averageEventRiskDelayDays": _mean(delays),
            }
        )
    return rows


def _observe_stats(points: List[dict], regime_key: str) -> dict:
    observe_segments = [
        segment
        for segment in _segments(points, regime_key)
        if segment["regime"] == "observe"
    ]
    durations = [segment["count"] for segment in observe_segments]
    return {
        "totalDays": sum(durations),
        "maxDays": max(durations) if durations else 0,
    }


def _v2_v3_event_risk_delay(points: List[dict]) -> List[dict]:
    rows = []
    for event in EVENT_WINDOWS:
        start = _date_to_ts(event["start"])
        end = _date_to_ts(event["end"]) + 24 * 60 * 60
        window_points = [point for point in points if start <= point["time"] < end]
        rows.append(
            {
                "event": event["event"],
                "start": event["start"],
                "end": event["end"],
                "v2RiskDelayDays": _risk_delay(window_points, "v2_stable_regime", start),
                "v3RiskDelayDays": _risk_delay(window_points, "stable_regime", start),
            }
        )
    return rows


def _v2_v3_regime_returns(payload: dict) -> List[dict]:
    v2 = {row["regime"]: row for row in _performance_summary(payload, "v2_stable_regime")}
    v3 = {row["regime"]: row for row in _performance_summary(payload, "stable_regime")}
    rows = []
    for regime, meta in payload.get("regimes", {}).items():
        v2_row = v2.get(regime, {})
        v3_row = v3.get(regime, {})
        rows.append(
            {
                "regime": regime,
                "label": meta["label"],
                "color": meta["color"],
                "v2Days": v2_row.get("days", 0),
                "v2BtcAverageDailyReturn": v2_row.get("btcAverageDailyReturn"),
                "v2BtcCumulativeReturn": v2_row.get("btcCumulativeReturn"),
                "v2EthAverageDailyReturn": v2_row.get("ethAverageDailyReturn"),
                "v2AltAverageDailyReturn": v2_row.get("altAverageDailyReturn"),
                "v3Days": v3_row.get("days", 0),
                "v3BtcAverageDailyReturn": v3_row.get("btcAverageDailyReturn"),
                "v3BtcCumulativeReturn": v3_row.get("btcCumulativeReturn"),
                "v3EthAverageDailyReturn": v3_row.get("ethAverageDailyReturn"),
                "v3AltAverageDailyReturn": v3_row.get("altAverageDailyReturn"),
            }
        )
    return rows


def _observe_limit_check(payload: dict) -> dict:
    points = payload.get("points", [])
    start = _date_to_ts(OBSERVE_LIMIT_CHECK_WINDOW["start"])
    end = _date_to_ts(OBSERVE_LIMIT_CHECK_WINDOW["end"]) + 24 * 60 * 60
    window_points = [point for point in points if start <= point["time"] < end]
    v2_segments = _segments(window_points, "v2_stable_regime")
    v3_segments = _segments(window_points, "stable_regime")
    v2_observe = [segment for segment in v2_segments if segment["regime"] == "observe"]
    v3_observe = [segment for segment in v3_segments if segment["regime"] == "observe"]
    v3_max_days = max((segment["count"] for segment in v3_observe), default=0)
    return {
        "name": OBSERVE_LIMIT_CHECK_WINDOW["name"],
        "start": OBSERVE_LIMIT_CHECK_WINDOW["start"],
        "end": OBSERVE_LIMIT_CHECK_WINDOW["end"],
        "limitDays": OBSERVE_LIMIT_DAYS_V3,
        "v2ObserveTotalDays": sum(segment["count"] for segment in v2_observe),
        "v2ObserveMaxDays": max((segment["count"] for segment in v2_observe), default=0),
        "v3ObserveTotalDays": sum(segment["count"] for segment in v3_observe),
        "v3ObserveMaxDays": v3_max_days,
        "v3Pass": v3_max_days <= OBSERVE_LIMIT_DAYS_V3,
        "v3ObserveSegments": [
            _observe_segment_row(segment, v3_segments, index)
            for index, segment in enumerate(v3_segments)
            if segment["regime"] == "observe"
        ],
    }


def _event_checks(payload: dict) -> List[dict]:
    points = payload.get("points", [])
    rows = []
    for event in EVENT_WINDOWS:
        start = _date_to_ts(event["start"])
        end = _date_to_ts(event["end"]) + 24 * 60 * 60
        window_points = [point for point in points if start <= point["time"] < end]
        btc_returns = _values(point.get("return") for point in window_points)
        eth_returns = _values(point.get("eth_return") for point in window_points)
        alt_returns = _values(point.get("alt_average_return") for point in window_points)
        rows.append(
            {
                "event": event["event"],
                "start": event["start"],
                "end": event["end"],
                "days": len(window_points),
                "rawDominantRegime": _dominant(window_points, "raw_regime"),
                "stableDominantRegime": _dominant(window_points, "stable_regime"),
                "tradeDominantRegime": _dominant(window_points, "trade_regime"),
                "rawRiskDelayDays": _risk_delay(window_points, "raw_regime", start),
                "stableRiskDelayDays": _risk_delay(window_points, "stable_regime", start),
                "tradeRiskDelayDays": _risk_delay(window_points, "trade_regime", start),
                "rawMix": _mix(window_points, "raw_regime"),
                "stableMix": _mix(window_points, "stable_regime"),
                "tradeMix": _mix(window_points, "trade_regime"),
                "btcCumulativeReturn": _compound(btc_returns),
                "ethCumulativeReturn": _compound(eth_returns),
                "altCumulativeReturn": _compound(alt_returns),
            }
        )
    return rows


def _risk_delay(points: List[dict], key: str, start_ts: int) -> Optional[int]:
    for point in points:
        if point.get(key) == SHOCK:
            return int((point["time"] - start_ts) // (24 * 60 * 60))
    return None


def _observe_report(payload: dict) -> dict:
    points = payload.get("points", [])
    segments = _segments(points, "stable_regime")
    observe_segments = [segment for segment in segments if segment["regime"] == "observe"]
    durations = [segment["count"] for segment in observe_segments]
    observe_points = [point for point in points if point.get("stable_regime") == "observe"]
    btc_returns = _values(point.get("return") for point in observe_points)
    eth_returns = _values(point.get("eth_return") for point in observe_points)
    alt_returns = _values(point.get("alt_average_return") for point in observe_points)

    transition_rows = _observe_transition_rows(segments)
    transition_counts = Counter(row["category"] for row in transition_rows)
    return {
        "summary": {
            "occurrences": len(observe_segments),
            "totalDays": sum(durations),
            "averageDays": _mean(durations) or 0,
            "maxDays": max(durations) if durations else 0,
            "longSegments": [
                _observe_segment_row(segment, segments, index)
                for index, segment in enumerate(segments)
                if segment["regime"] == "observe"
                if segment["count"] >= 10
            ],
        },
        "transitions": {
            "returnToPrevious": transition_counts.get("return_to_previous", 0),
            "toBear": transition_counts.get("to_bear", 0),
            "toGrowth": transition_counts.get("to_growth", 0),
            "toRisk": transition_counts.get("to_risk", 0),
            "toOther": transition_counts.get("to_other", 0),
            "rows": transition_rows,
        },
        "performance": {
            "btcAverageDailyReturn": _mean(btc_returns),
            "ethAverageDailyReturn": _mean(eth_returns),
            "altAverageDailyReturn": _mean(alt_returns),
            "maxDrawdown": _max_drawdown(btc_returns),
        },
        "eventObserve": _observe_event_rows(segments),
    }


def _observe_transition_rows(segments: List[dict]) -> List[dict]:
    rows = []
    for index, segment in enumerate(segments):
        if segment["regime"] != "observe":
            continue
        previous = _previous_non_risk_regime(segments, index)
        next_regime = segments[index + 1]["regime"] if index + 1 < len(segments) else None
        category = _observe_transition_category(previous, next_regime)
        rows.append(
            {
                "start": _date_label(segment["startTime"]),
                "end": _date_label(segment["endTime"]),
                "days": segment["count"],
                "previousRegime": previous,
                "nextRegime": next_regime,
                "category": category,
            }
        )
    return rows


def _observe_transition_category(previous: Optional[str], next_regime: Optional[str]) -> str:
    if next_regime is None:
        return "to_other"
    if previous and next_regime == previous:
        return "return_to_previous"
    if next_regime == DEFENSIVE:
        return "to_bear"
    if next_regime in {UPTREND, ETH_STRENGTH, LARGE_CAP_LEAD}:
        return "to_growth"
    if next_regime == SHOCK:
        return "to_risk"
    return "to_other"


def _observe_segment_row(segment: dict, segments: List[dict], index: int) -> dict:
    return {
        "start": _date_label(segment["startTime"]),
        "end": _date_label(segment["endTime"]),
        "days": segment["count"],
        "previousRegime": _previous_non_risk_regime(segments, index),
        "nextRegime": segments[index + 1]["regime"] if index + 1 < len(segments) else None,
    }


def _previous_non_risk_regime(segments: List[dict], index: int) -> Optional[str]:
    for segment in reversed(segments[:index]):
        if segment["regime"] not in {SHOCK, OBSERVE}:
            return segment["regime"]
    return None


def _observe_event_rows(segments: List[dict]) -> List[dict]:
    rows = []
    for event in EVENT_WINDOWS[:4]:
        start = _date_to_ts(event["start"])
        end = _date_to_ts(event["end"]) + 24 * 60 * 60
        observe = _event_observe_segment(segments, start, end)
        rows.append(
            {
                "event": event["event"],
                "start": event["start"],
                "end": event["end"],
                "observeDays": observe["count"] if observe else 0,
                "observeStart": _date_label(observe["startTime"]) if observe else None,
                "observeEnd": _date_label(observe["endTime"]) if observe else None,
            }
        )
    return rows


def _event_observe_segment(segments: List[dict], start: int, end: int) -> Optional[dict]:
    for index, segment in enumerate(segments):
        if segment["regime"] != SHOCK:
            continue
        if not (start <= segment["startTime"] < end):
            continue
        if index + 1 < len(segments) and segments[index + 1]["regime"] == "observe":
            return segments[index + 1]
    for segment in segments:
        if segment["regime"] == "observe" and start <= segment["startTime"] < end:
            return segment
    return None


def _lookahead_report(points: List[dict]) -> dict:
    shift_ok = True
    for index in range(1, len(points)):
        if points[index].get("trade_regime") != points[index - 1].get("stable_regime"):
            shift_ok = False
            break
    first_empty = not points or points[0].get("trade_regime") is None
    return {
        "status": "pass" if shift_ok and first_empty else "fail",
        "checks": [
            {
                "name": "live_regime_shifted_one_bar",
                "status": "pass" if shift_ok else "fail",
                "detail": "trade_regime[i] == stable_regime[i-1]",
            },
            {
                "name": "first_bar_has_no_live_regime",
                "status": "pass" if first_empty else "fail",
                "detail": "첫 봉은 이전 확정 레짐이 없어서 적용 레짐을 비워둠",
            },
            {
                "name": "same_bar_regime_after_close",
                "status": "info",
                "detail": "raw/stable_regime은 해당 봉 종가 확정 후 알 수 있고, 실전 판단은 trade_regime을 사용",
            },
        ],
    }


def _segments(points: List[dict], regime_key: str) -> List[dict]:
    segments = []
    current = None
    for index, point in enumerate(points):
        regime = point.get(regime_key)
        if not regime:
            continue
        if current is None or current["regime"] != regime:
            if current is not None:
                current["endIndex"] = index - 1
                current["endTime"] = points[index - 1]["time"]
                segments.append(current)
            current = {"regime": regime, "count": 1, "startIndex": index, "startTime": point["time"]}
        else:
            current["count"] += 1
    if current is not None:
        current["endIndex"] = len(points) - 1
        current["endTime"] = points[-1]["time"]
        segments.append(current)
    return segments


def _dominant(points: List[dict], key: str) -> Optional[str]:
    counts = Counter(point.get(key) for point in points if point.get(key))
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _mix(points: List[dict], key: str) -> List[dict]:
    counts = Counter(point.get(key) for point in points if point.get(key))
    total = sum(counts.values()) or 1
    return [
        {"regime": regime, "days": days, "pct": days / total}
        for regime, days in counts.most_common()
    ]


def _has_regime_key(points: List[dict], key: str) -> bool:
    return any(point.get(key) for point in points)


def _values(values: Iterable[Optional[float]]) -> List[float]:
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _stdev(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    average = _mean(values) or 0.0
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _compound(values: List[float]) -> Optional[float]:
    if not values:
        return None
    equity = 1.0
    for value in values:
        equity *= 1 + value
    return equity - 1


def _max_drawdown(values: List[float]) -> Optional[float]:
    if not values:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    return abs(max_drawdown)


def _date_to_ts(value: str) -> int:
    parsed = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _date_label(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
