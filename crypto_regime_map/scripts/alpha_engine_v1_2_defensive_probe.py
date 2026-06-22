"""Shared defensive-probe rules for Alpha Engine v1.2 test runs."""

from __future__ import annotations

from typing import Optional


PROBE_VARIANT_NAME = "v1_defensive_probe"
PROBE_SCORE_THRESHOLD = 85.0
PROBE_SIZE_MULTIPLIER = 0.25
PROBE_STOP_ATR_MULTIPLE = 1.5

PROBE_LOG_FIELDS = [
    "timestamp",
    "symbol",
    "regime",
    "action_bias",
    "original_can_enter",
    "probe_can_enter",
    "alpha_score",
    "relative_strength_ok",
    "btc_panic_condition",
    "size_multiplier",
    "block_reason",
    "probe_reason",
]


def health_gate_from_state(state: Optional[dict]) -> dict:
    state = state or {}
    status = str(state.get("status") or state.get("status_label") or "normal").lower()
    data_gap_summary = state.get("data_gap_summary") or {}
    trading_gap_count = int(
        data_gap_summary.get("trading_failed_count")
        or data_gap_summary.get("affecting_gap_count")
        or 0
    )
    flow = state.get("flow") or {}
    data_gate = (flow.get("gates") or {}).get("data") or {}
    trading_gap_count = max(trading_gap_count, int(data_gate.get("affecting_gap_count") or 0))

    if state.get("manual_pause") or status in {"critical", "paused"}:
        return {"can_probe": False, "block_reason": f"health_{status}", "status": status, "trading_data_gap_count": trading_gap_count}
    if status not in {"ok", "normal", "warning"}:
        return {"can_probe": False, "block_reason": f"health_{status}", "status": status, "trading_data_gap_count": trading_gap_count}
    if trading_gap_count > 0:
        return {"can_probe": False, "block_reason": "health_trading_data_gap", "status": status, "trading_data_gap_count": trading_gap_count}
    return {"can_probe": True, "block_reason": "", "status": status, "trading_data_gap_count": trading_gap_count}


def evaluate_candidate(
    row: dict,
    regime: str,
    action_bias: str,
    block_reason: str,
    btc: Optional[dict] = None,
    health_gate: Optional[dict] = None,
    max_slot_available: bool = True,
) -> dict:
    health_gate = health_gate or health_gate_from_state({})
    alpha_score = score_value(row, "alpha_score")
    relative_ok = relative_strength_ok(row)
    btc_panic = btc_panic_condition(regime, action_bias, block_reason, btc)
    score_ok = score_percent(row) >= PROBE_SCORE_THRESHOLD

    reason = "passed"
    can_probe = True
    if not is_defensive_state(regime, action_bias, block_reason):
        can_probe = False
        reason = "not_defensive"
    elif hard_risk_block(regime, action_bias, block_reason):
        can_probe = False
        reason = "risk_off_or_panic"
    elif btc_panic:
        can_probe = False
        reason = "btc_panic_condition"
    elif not health_gate.get("can_probe"):
        can_probe = False
        reason = health_gate.get("block_reason") or "health_blocked"
    elif not score_ok:
        can_probe = False
        reason = "score_below_85"
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
        "size_multiplier": PROBE_SIZE_MULTIPLIER if can_probe else 0.0,
        "block_reason": "" if can_probe else reason,
        "probe_reason": reason,
    }


def log_row(timestamp: int, symbol: str, regime: str, action_bias: str, original_can_enter: bool, decision: dict) -> dict:
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "regime": regime,
        "action_bias": action_bias,
        "original_can_enter": bool(original_can_enter),
        "probe_can_enter": bool(decision["probe_can_enter"]),
        "alpha_score": decision["alpha_score"],
        "relative_strength_ok": bool(decision["relative_strength_ok"]),
        "btc_panic_condition": bool(decision["btc_panic_condition"]),
        "size_multiplier": decision["size_multiplier"],
        "block_reason": decision["block_reason"],
        "probe_reason": decision["probe_reason"],
    }


def is_defensive_state(regime: str, action_bias: str, block_reason: str = "") -> bool:
    values = {str(regime or "").lower(), str(action_bias or "").lower(), str(block_reason or "").lower()}
    return "defensive" in values or "reduce_risk" in values or "defensive_reduce_risk" in values


def hard_risk_block(regime: str, action_bias: str, block_reason: str = "") -> bool:
    values = [str(item or "").lower() for item in (regime, action_bias, block_reason)]
    return any(value in {"risk_off", "panic", "shock", "no_new_entry"} for value in values)


def btc_panic_condition(regime: str, action_bias: str, block_reason: str, btc: Optional[dict]) -> bool:
    if hard_risk_block(regime, action_bias, block_reason):
        return True
    btc = btc or {}
    ret_7d = score_value(btc, "ret_7d")
    ret_14d = score_value(btc, "ret_14d")
    return (ret_7d is not None and ret_7d <= -0.10) or (ret_14d is not None and ret_14d <= -0.15)


def relative_strength_ok(row: dict) -> bool:
    explicit = row.get("relative_strength_ok")
    if isinstance(explicit, bool):
        return explicit
    if isinstance(explicit, str) and explicit:
        return explicit.lower() in {"1", "true", "yes", "ok"}

    score = score_value(row, "relative_strength_score")
    if score is not None:
        return score >= 3.0

    btc_excess_7d = score_value(row, "btc_excess_7d_pct")
    btc_excess_14d = score_value(row, "btc_excess_14d_pct")
    ret_7d = score_value(row, "ret_7d_pct")
    ret_14d = score_value(row, "ret_14d_pct")
    has_positive_excess = (btc_excess_7d is not None and btc_excess_7d > 0) or (btc_excess_14d is not None and btc_excess_14d > 0)
    has_positive_return = (ret_7d is not None and ret_7d > 0) or (ret_14d is not None and ret_14d > 0)
    return has_positive_excess and has_positive_return


def score_percent(row: dict) -> float:
    values = [score_value(row, "candidate_score"), score_value(row, "alpha_score")]
    normalized = []
    for value in values:
        if value is None:
            continue
        normalized.append(value * 10 if value <= 10 else value)
    return max(normalized, default=0.0)


def score_value(row: dict, key: str) -> Optional[float]:
    value = row.get(key)
    if value in {"", None}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "ok"}
    return bool(value)
