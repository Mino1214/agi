"""Short-term 4H BTC regime rules for Alpha Engine v1.2 experiments.

This module is intentionally separate from the production 1D regime engine.
It classifies BTC 4H candles and returns entry-gate decisions for experiment
runs only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple


UPTREND = "uptrend"
RECOVERY = "recovery"
DEFENSIVE = "defensive"
RISK_OFF = "risk_off"
UNKNOWN = "unknown"

ALLOW_RISK = "allow_risk"
SELECTIVE_ENTER = "selective_enter"
REDUCE_RISK = "reduce_risk"
BLOCK_ENTRY = "block_entry"

DEFAULT_RECOVERY_SIZE = 0.5
SHOCK_RETURN_4H = -0.055
SHOCK_DRAWDOWN_24H = -0.10
SHOCK_DRAWDOWN_72H = -0.16
VOLATILITY_SPIKE_MULTIPLE = 1.8


@dataclass(frozen=True)
class GateConfig:
    name: str
    allow_recovery: bool = True
    recovery_size_multiplier: float = DEFAULT_RECOVERY_SIZE
    strict_uptrend: bool = False
    hybrid_daily_override: bool = False
    hybrid_override_size_multiplier: float = 0.25


PAPER_4H_CONFIG = GateConfig("paper_short_regime_4h", allow_recovery=True, recovery_size_multiplier=0.5)
V4H_BASIC = GateConfig("V4H_basic", allow_recovery=False)
V4H_RECOVERY_50 = GateConfig("V4H_recovery_size_50", allow_recovery=True, recovery_size_multiplier=0.5)
V4H_RECOVERY_25 = GateConfig("V4H_recovery_size_25", allow_recovery=True, recovery_size_multiplier=0.25)
V4H_STRICT = GateConfig("V4H_strict", allow_recovery=False, strict_uptrend=True)
V4H_HYBRID = GateConfig(
    "V4H_hybrid",
    allow_recovery=True,
    recovery_size_multiplier=0.5,
    hybrid_daily_override=True,
    hybrid_override_size_multiplier=0.25,
)

COMPARISON_CONFIGS = [V4H_BASIC, V4H_RECOVERY_50, V4H_RECOVERY_25, V4H_STRICT, V4H_HYBRID]


def build_btc_4h_regime_rows(raw_btc_4h: List[dict]) -> List[dict]:
    rows = [dict(row) for row in sorted(raw_btc_4h, key=lambda item: int(item["time"]))]
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    atr14 = atr(rows, 14)
    atr_pct_values = [
        atr14[index] / closes[index] if atr14[index] is not None and closes[index] else None
        for index in range(len(rows))
    ]
    atr_pct_sma50 = rolling_average(atr_pct_values, 50)

    for index, row in enumerate(rows):
        close = closes[index]
        row["close_time"] = int(row["time"]) + 4 * 3600
        row["ema20"] = ema20[index]
        row["ema50"] = ema50[index]
        row["ema200"] = ema200[index]
        row["atr14"] = atr14[index]
        row["atr_pct"] = atr_pct_values[index]
        row["atr_pct_sma50"] = atr_pct_sma50[index]
        row["ret_4h"] = close / closes[index - 1] - 1 if index >= 1 and closes[index - 1] else None
        row["drawdown_24h"] = close / max(highs[max(0, index - 5) : index + 1]) - 1 if index >= 1 else None
        row["drawdown_72h"] = close / max(highs[max(0, index - 17) : index + 1]) - 1 if index >= 1 else None
        row["short_regime"] = classify_4h_row(row, strict_uptrend=False)
        row["strict_short_regime"] = classify_4h_row(row, strict_uptrend=True)
        row["short_action_bias"] = action_bias_for_regime(row["short_regime"])
        row["strict_short_action_bias"] = action_bias_for_regime(row["strict_short_regime"])
    return rows


def build_regime_indexes(raw_btc_4h: List[dict]) -> dict:
    rows = build_btc_4h_regime_rows(raw_btc_4h)
    return {
        "rows": rows,
        "by_close_time": {int(row["close_time"]): row for row in rows},
        "by_open_time": {int(row["time"]): row for row in rows},
    }


def classify_4h_row(row: dict, strict_uptrend: bool = False) -> str:
    close = number_or_none(row.get("close"))
    ema20_value = number_or_none(row.get("ema20"))
    ema50_value = number_or_none(row.get("ema50"))
    ema200_value = number_or_none(row.get("ema200"))
    if None in {close, ema20_value, ema50_value, ema200_value}:
        return UNKNOWN
    if shock_condition(row):
        return RISK_OFF
    if close > ema50_value and ema20_value > ema50_value and ema50_value < ema200_value:
        return RECOVERY
    if close < ema200_value and ema50_value < ema200_value:
        return DEFENSIVE
    if strict_uptrend:
        if close > ema200_value and ema50_value > ema200_value:
            return UPTREND
    elif close > ema200_value and ema50_value > ema200_value and ema20_value > ema50_value:
        return UPTREND
    if close < ema200_value:
        return DEFENSIVE
    return DEFENSIVE


def shock_condition(row: dict) -> bool:
    close = number_or_none(row.get("close"))
    ema200_value = number_or_none(row.get("ema200"))
    ret_4h = number_or_none(row.get("ret_4h"))
    drawdown_24h = number_or_none(row.get("drawdown_24h"))
    drawdown_72h = number_or_none(row.get("drawdown_72h"))
    atr_pct = number_or_none(row.get("atr_pct"))
    atr_pct_sma50 = number_or_none(row.get("atr_pct_sma50"))
    volatility_spike = atr_pct is not None and atr_pct_sma50 is not None and atr_pct > atr_pct_sma50 * VOLATILITY_SPIKE_MULTIPLE
    sharp_drop = (ret_4h is not None and ret_4h <= SHOCK_RETURN_4H) or (drawdown_24h is not None and drawdown_24h <= SHOCK_DRAWDOWN_24H)
    extreme_drawdown = drawdown_72h is not None and drawdown_72h <= SHOCK_DRAWDOWN_72H
    under_ema200 = close is not None and ema200_value is not None and close < ema200_value
    return bool(sharp_drop and (volatility_spike or (under_ema200 and extreme_drawdown)))


def action_bias_for_regime(regime: str) -> str:
    if regime == UPTREND:
        return ALLOW_RISK
    if regime == RECOVERY:
        return SELECTIVE_ENTER
    if regime == DEFENSIVE:
        return REDUCE_RISK
    if regime == RISK_OFF:
        return BLOCK_ENTRY
    return BLOCK_ENTRY


def gate_for_signal(
    universe: Iterable[str],
    short_row: Optional[dict],
    config: GateConfig = PAPER_4H_CONFIG,
    daily_regime: Optional[dict] = None,
    health_gate: Optional[dict] = None,
) -> Tuple[List[str], float, str, dict]:
    symbols = list(universe)
    health_gate = health_gate or {"can_probe": True, "block_reason": ""}
    if not health_gate.get("can_probe", True):
        reason = str(health_gate.get("block_reason") or "health_blocked")
        return [], 0.0, reason, gate_regime_row(UNKNOWN, BLOCK_ENTRY, short_row, daily_regime)

    short_regime = regime_from_row(short_row, config)
    short_action = action_bias_for_regime(short_regime)
    daily_regime = daily_regime or {}
    daily_trade_regime = str(daily_regime.get("trade_regime") or "")
    daily_action = str(daily_regime.get("trade_action_bias") or "")
    if config.hybrid_daily_override:
        if daily_trade_regime in {"shock", "risk_off"} or daily_action in {"no_new_entry", "shock", "block_entry"}:
            return [], 0.0, "daily_risk_off", gate_regime_row(short_regime, BLOCK_ENTRY, short_row, daily_regime)
        if daily_trade_regime == "defensive" or daily_action == "reduce_risk":
            if short_regime in {UPTREND, RECOVERY}:
                regime = gate_regime_row(short_regime, SELECTIVE_ENTER, short_row, daily_regime)
                regime["hybrid_override"] = True
                return symbols, config.hybrid_override_size_multiplier, "hybrid_1d_defensive_4h_recovery", regime
            return [], 0.0, f"short_{short_regime}", gate_regime_row(short_regime, short_action, short_row, daily_regime)

    if short_regime == UPTREND:
        return symbols, 1.0, "short_4h_uptrend", gate_regime_row(short_regime, ALLOW_RISK, short_row, daily_regime)
    if short_regime == RECOVERY and config.allow_recovery:
        return symbols, config.recovery_size_multiplier, "short_4h_recovery", gate_regime_row(short_regime, SELECTIVE_ENTER, short_row, daily_regime)
    if short_regime == RECOVERY:
        return [], 0.0, "short_4h_recovery_blocked", gate_regime_row(short_regime, SELECTIVE_ENTER, short_row, daily_regime)
    if short_regime == DEFENSIVE:
        return [], 0.0, "short_4h_defensive", gate_regime_row(short_regime, REDUCE_RISK, short_row, daily_regime)
    return [], 0.0, f"short_4h_{short_regime}", gate_regime_row(short_regime, BLOCK_ENTRY, short_row, daily_regime)


def regime_from_row(short_row: Optional[dict], config: GateConfig) -> str:
    if not short_row:
        return UNKNOWN
    key = "strict_short_regime" if config.strict_uptrend else "short_regime"
    return str(short_row.get(key) or UNKNOWN)


def gate_regime_row(short_regime: str, action_bias: str, short_row: Optional[dict], daily_regime: Optional[dict]) -> dict:
    row = {
        "trade_regime": short_regime,
        "trade_action_bias": action_bias,
        "regime_timeframe": "4h",
        "short_regime_4h": short_regime,
        "short_action_bias_4h": action_bias,
        "daily_trade_regime": (daily_regime or {}).get("trade_regime", ""),
        "daily_trade_action_bias": (daily_regime or {}).get("trade_action_bias", ""),
    }
    if short_row:
        row.update(
            {
                "short_regime_open_time": int(short_row.get("time") or 0),
                "short_regime_close_time": int(short_row.get("close_time") or 0),
                "btc_4h_close": short_row.get("close", ""),
                "btc_4h_ema20": short_row.get("ema20", ""),
                "btc_4h_ema50": short_row.get("ema50", ""),
                "btc_4h_ema200": short_row.get("ema200", ""),
                "btc_4h_ret_pct": percent(short_row.get("ret_4h")),
                "btc_4h_drawdown_24h_pct": percent(short_row.get("drawdown_24h")),
                "btc_4h_drawdown_72h_pct": percent(short_row.get("drawdown_72h")),
                "btc_4h_atr_pct": percent(short_row.get("atr_pct")),
                "btc_4h_atr_pct_sma50": percent(short_row.get("atr_pct_sma50")),
            }
        )
    return row


def regime_log_rows(rows: List[dict]) -> List[dict]:
    out = []
    for row in rows:
        regime = row.get("short_regime", UNKNOWN)
        out.append(
            {
                "open_time": row.get("time"),
                "close_time": row.get("close_time"),
                "close_date": fmt(row.get("close_time")),
                "short_regime": regime,
                "short_action_bias": action_bias_for_regime(regime),
                "close": row.get("close"),
                "ema20": row.get("ema20"),
                "ema50": row.get("ema50"),
                "ema200": row.get("ema200"),
                "ret_4h_pct": percent(row.get("ret_4h")),
                "drawdown_24h_pct": percent(row.get("drawdown_24h")),
                "drawdown_72h_pct": percent(row.get("drawdown_72h")),
                "atr_pct": percent(row.get("atr_pct")),
                "atr_pct_sma50": percent(row.get("atr_pct_sma50")),
            }
        )
    return out


def transition_rows(rows: List[dict], whipsaw_hours: int = 24) -> List[dict]:
    transitions = []
    previous = None
    previous_time = None
    for row in rows:
        regime = row.get("short_regime", UNKNOWN)
        close_time = int(row.get("close_time") or 0)
        if previous is None:
            previous = regime
            previous_time = close_time
            continue
        if regime != previous:
            transitions.append(
                {
                    "transition_time": close_time,
                    "transition_date": fmt(close_time),
                    "from_regime": previous,
                    "to_regime": regime,
                    "hours_since_previous_transition": (close_time - previous_time) / 3600 if previous_time else "",
                    "whipsaw": bool(previous_time and close_time - previous_time <= whipsaw_hours * 3600),
                }
            )
            previous = regime
            previous_time = close_time
    return transitions


def regime_state_ratios(rows: List[dict]) -> List[dict]:
    counts = Counter(row.get("short_regime", UNKNOWN) for row in rows)
    total = sum(counts.values()) or 1
    return [{"short_regime": regime, "bars": count, "state_ratio_pct": count / total * 100} for regime, count in sorted(counts.items())]


def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    multiplier = 2 / (period + 1)
    current: Optional[float] = None
    for index, value in enumerate(values):
        value = float(value)
        if index + 1 < period:
            out.append(None)
            continue
        if current is None:
            current = sum(values[index + 1 - period : index + 1]) / period
        else:
            current = value * multiplier + current * (1 - multiplier)
        out.append(current)
    return out


def atr(rows: List[dict], period: int) -> List[Optional[float]]:
    true_ranges: List[float] = []
    out: List[Optional[float]] = []
    previous_close: Optional[float] = None
    for row in rows:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        if previous_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)
        if len(true_ranges) < period:
            out.append(None)
        else:
            out.append(sum(true_ranges[-period:]) / period)
        previous_close = close
    return out


def rolling_average(values: List[Optional[float]], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    window: List[float] = []
    for value in values:
        if value is not None:
            window.append(value)
        if len(window) < period:
            out.append(None)
        else:
            out.append(sum(window[-period:]) / period)
    return out


def number_or_none(value) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent(value) -> Optional[float]:
    number = number_or_none(value)
    return number * 100 if number is not None else None


def fmt(timestamp) -> str:
    if timestamp in {None, ""}:
        return ""
    return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y-%m-%d %H:%M")
