"""Market regime dataset assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from collector import INTERVAL_SECONDS, load_or_fetch_many
from indicators import add_indicators, ema
from validation import build_validation_report


DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "ADAUSDT",
    "TONUSDT",
]

ALT_SYMBOLS = [symbol for symbol in DEFAULT_SYMBOLS if symbol not in {"BTCUSDT", "ETHUSDT"}]

REGIME_LABEL_MIGRATION = [
    {"legacy": "bull", "legacyLabel": "상승장", "regime": "uptrend", "label": "uptrend"},
    {"legacy": "btc", "legacyLabel": "BTC 중심장", "regime": "large_cap_lead", "label": "large_cap_lead"},
    {"legacy": "alt", "legacyLabel": "알트장", "regime": "eth_strength", "label": "eth_strength"},
    {"legacy": "bear", "legacyLabel": "하락장", "regime": "defensive", "label": "defensive"},
    {"legacy": "risk", "legacyLabel": "위험장", "regime": "shock", "label": "shock"},
    {"legacy": "sideways", "legacyLabel": "횡보장", "regime": "neutral", "label": "neutral"},
    {"legacy": "observe", "legacyLabel": "관찰장", "regime": "observe", "label": "observe"},
]

REGIMES = {
    "uptrend": {"label": "uptrend", "color": "#18b66a", "action_bias": "long_allowed"},
    "large_cap_lead": {"label": "large_cap_lead", "color": "#2f80ed", "action_bias": "btc_eth_preferred"},
    "eth_strength": {"label": "eth_strength", "color": "#9b5cf6", "action_bias": "alt_watch"},
    "defensive": {"label": "defensive", "color": "#ef4444", "action_bias": "reduce_risk"},
    "shock": {"label": "shock", "color": "#f97316", "action_bias": "no_new_entry"},
    "neutral": {"label": "neutral", "color": "#8b949e", "action_bias": "wait"},
    "observe": {"label": "observe", "color": "#f2c94c", "action_bias": "wait"},
}

MIN_STABLE_DAYS = 5
RISK_OBSERVE_DAYS = 3
OBSERVE_MAX_DAYS_V3 = 7


def build_regime_payload(
    data_dir: Path,
    interval: str = "1d",
    start: str = "2020-01-01",
    symbols: Optional[Iterable[str]] = None,
    refresh: bool = False,
) -> dict:
    if interval != "1d":
        raise ValueError("Initial regime map supports 1d only")

    selected_symbols = list(symbols or DEFAULT_SYMBOLS)
    raw = load_or_fetch_many(selected_symbols, interval, start, data_dir / "raw", refresh=refresh)
    payload = build_payload_from_raw(raw, interval=interval, start=start, symbols=selected_symbols)
    _write_processed(data_dir, payload)
    return payload


def build_payload_from_raw(
    raw: Dict[str, List[dict]],
    interval: str = "1d",
    start: str = "2020-01-01",
    symbols: Optional[Iterable[str]] = None,
) -> dict:
    selected_symbols = list(symbols or raw.keys())
    symbol_rows = {symbol: add_indicators(candles) for symbol, candles in raw.items() if candles}
    if "BTCUSDT" not in symbol_rows:
        raise RuntimeError("BTCUSDT data is required")

    btc_rows = symbol_rows["BTCUSDT"]
    indexes = {
        symbol: {row["time"]: row for row in rows}
        for symbol, rows in symbol_rows.items()
    }
    eth_btc = _eth_btc_series(btc_rows, indexes.get("ETHUSDT", {}))
    eth_ema50 = ema(eth_btc, 50)
    eth_ema200 = ema(eth_btc, 200)

    points: List[dict] = []
    for index, btc in enumerate(btc_rows):
        point = dict(btc)
        point["eth_btc"] = eth_btc[index]
        point["eth_btc_ema50"] = eth_ema50[index]
        point["eth_btc_ema200"] = eth_ema200[index]
        eth_row = indexes.get("ETHUSDT", {}).get(point["time"])
        point["eth_return"] = eth_row.get("return") if eth_row else None
        point["eth_open_close_return"] = _open_close_return(eth_row) if eth_row else None
        point.update(_alt_snapshot(point["time"], indexes))
        point["raw_regime"] = classify(point)
        _apply_regime_meta(point, "raw_regime", "raw")
        points.append(point)

    stabilize_regimes(
        points,
        observe_limit_days=None,
        regime_key="v2_stable_regime",
        stable_prefix="v2_stable",
        trade_key="v2_trade_regime",
        trade_prefix="v2_trade",
        set_primary=False,
        allow_observe_last_non_risk=True,
    )
    stabilize_regimes(points)
    stable_segments = _segments(points, INTERVAL_SECONDS[interval], "stable_regime")
    v2_stable_segments = _segments(points, INTERVAL_SECONDS[interval], "v2_stable_regime")
    raw_segments = _segments(points, INTERVAL_SECONDS[interval], "raw_regime")
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "start": start,
        "interval": interval,
        "stabilization": {
            "version": "v4",
            "previousVersion": "v3",
            "regimeLabelVersion": "v4",
            "minStableDays": MIN_STABLE_DAYS,
            "riskVersion": "v2",
            "riskObserveDays": RISK_OBSERVE_DAYS,
            "observeMaxDays": OBSERVE_MAX_DAYS_V3,
            "riskImmediate": True,
            "riskConditionsRequired": 2,
            "bullEntry": "close > EMA200 * 1.02",
            "bullExit": "close < EMA200 * 0.99",
            "observeForcedReclassification": [
                "BTC < EMA200 -> defensive",
                "BTC > EMA200 * 1.02 and ETH/BTC rising -> eth_strength",
                "BTC > EMA200 * 1.02 and ETH/BTC falling -> large_cap_lead",
                "BTC > EMA200 -> uptrend",
                "otherwise -> neutral",
            ],
        },
        "symbols": selected_symbols,
        "symbolData": _symbol_data_summary(symbol_rows, selected_symbols),
        "regimes": REGIMES,
        "regimeLabelMigration": REGIME_LABEL_MIGRATION,
        "candles": _series(points, ["time", "open", "high", "low", "close"]),
        "ema50": _line(points, "ema50"),
        "ema200": _line(points, "ema200"),
        "points": _points(points),
        "rawSegments": raw_segments,
        "v2StableSegments": v2_stable_segments,
        "stableSegments": stable_segments,
        "segments": stable_segments,
        "rawStats": _stats(points, "raw_regime"),
        "v2StableStats": _stats(points, "v2_stable_regime"),
        "stableStats": _stats(points, "stable_regime"),
        "stats": _stats(points, "stable_regime"),
        "latest": _latest(points),
    }
    payload["report"] = build_validation_report(payload)
    return payload


def classify(row: dict) -> str:
    close = row.get("close")
    ema50_value = row.get("ema50")
    ema200_value = row.get("ema200")
    atr_pct = row.get("atr_pct")
    atr_avg = row.get("atr_pct_sma50")

    if _is_risk_v2(row):
        return "shock"
    if close and ema200_value and ema50_value and close < ema200_value and ema50_value < ema200_value:
        return "defensive"
    if _is_alt_regime(row):
        return "eth_strength"
    if _is_btc_regime(row):
        return "large_cap_lead"
    if close and ema200_value and ema50_value and close > ema200_value and ema50_value > ema200_value:
        if atr_pct is None or atr_avg is None or atr_pct <= atr_avg * 1.8:
            return "uptrend"
    if _is_sideways(row):
        return "neutral"
    if close and ema200_value and close < ema200_value:
        return "defensive"
    if close and ema200_value and close > ema200_value:
        return "uptrend"
    return "neutral"


def stabilize_regimes(
    points: List[dict],
    min_days: int = MIN_STABLE_DAYS,
    observe_limit_days: Optional[int] = OBSERVE_MAX_DAYS_V3,
    regime_key: str = "stable_regime",
    stable_prefix: str = "stable",
    trade_key: str = "trade_regime",
    trade_prefix: str = "trade",
    set_primary: bool = True,
    allow_observe_last_non_risk: bool = False,
) -> None:
    current: Optional[str] = None
    pending: Optional[str] = None
    pending_days = 0
    last_non_risk: Optional[str] = None
    observe_days = 0

    for index, point in enumerate(points):
        candidate = _stable_candidate(point, current)
        if current is None:
            current = candidate
        elif candidate == "shock":
            if current != "shock" and (allow_observe_last_non_risk or current != "observe"):
                last_non_risk = current
            current = "shock"
            pending = None
            pending_days = 0
            observe_days = 0
        elif current == "shock":
            current = "observe"
            observe_days = 1
            pending = None
            pending_days = 0
        elif current == "observe":
            observe_days += 1
            if observe_limit_days is not None and observe_days > observe_limit_days:
                current = _forced_observe_regime(point)
                observe_days = 0
            elif observe_days >= RISK_OBSERVE_DAYS and _risk_recovered(point):
                current = last_non_risk or candidate
                observe_days = 0
            elif observe_days >= RISK_OBSERVE_DAYS and _risk_breakdown(point):
                current = "defensive"
                observe_days = 0
            else:
                current = "observe"
            pending = None
            pending_days = 0
        elif candidate == current:
            pending = None
            pending_days = 0
        else:
            if pending == candidate:
                pending_days += 1
            else:
                pending = candidate
                pending_days = 1
            if pending_days >= min_days:
                current = candidate
                pending = None
                pending_days = 0

        if current not in {"shock", "observe"}:
            last_non_risk = current
        point[regime_key] = current
        _apply_regime_meta(point, regime_key, stable_prefix)
        if set_primary:
            point["regime"] = point[regime_key]
            point["regime_label"] = point[f"{stable_prefix}_regime_label"]
            point["regime_color"] = point[f"{stable_prefix}_regime_color"]
            point["action_bias"] = point[f"{stable_prefix}_action_bias"]
        if index == 0:
            point[trade_key] = None
            point[f"{trade_prefix}_regime_label"] = None
            point[f"{trade_prefix}_regime_color"] = None
            point[f"{trade_prefix}_action_bias"] = None
        else:
            previous = points[index - 1]
            point[trade_key] = previous[regime_key]
            point[f"{trade_prefix}_regime_label"] = previous[f"{stable_prefix}_regime_label"]
            point[f"{trade_prefix}_regime_color"] = previous[f"{stable_prefix}_regime_color"]
            point[f"{trade_prefix}_action_bias"] = previous[f"{stable_prefix}_action_bias"]


def _stable_candidate(row: dict, current: Optional[str]) -> str:
    raw = row["raw_regime"]
    if raw == "shock":
        return "shock"
    if current == "uptrend" and raw in {"defensive", "neutral"} and not _bull_exit(row):
        return "uptrend"
    if raw == "uptrend" and not _bull_entry(row):
        return current or "neutral"
    return raw


def _risk_recovered(row: dict) -> bool:
    close = row.get("close")
    ema50_value = row.get("ema50")
    return bool(close and ema50_value and close > ema50_value)


def _risk_breakdown(row: dict) -> bool:
    close = row.get("close")
    ema50_value = row.get("ema50")
    ema50_slope = row.get("ema50_slope")
    return bool(close and ema50_value and ema50_slope is not None and close < ema50_value and ema50_slope < 0)


def _forced_observe_regime(row: dict) -> str:
    close = row.get("close")
    ema200_value = row.get("ema200")
    if close is None or ema200_value is None:
        return "neutral"
    if close < ema200_value:
        return "defensive"
    if close > ema200_value * 1.02:
        if _eth_btc_rising(row):
            return "eth_strength"
        if _eth_btc_falling(row):
            return "large_cap_lead"
    if close > ema200_value:
        return "uptrend"
    return "neutral"


def _eth_btc_rising(row: dict) -> bool:
    eth_btc = row.get("eth_btc")
    eth_ema50 = row.get("eth_btc_ema50")
    return bool(eth_btc is not None and eth_ema50 is not None and eth_btc > eth_ema50)


def _eth_btc_falling(row: dict) -> bool:
    eth_btc = row.get("eth_btc")
    eth_ema50 = row.get("eth_btc_ema50")
    return bool(eth_btc is not None and eth_ema50 is not None and eth_btc < eth_ema50)


def _bull_entry(row: dict) -> bool:
    close = row.get("close")
    ema200_value = row.get("ema200")
    ema50_value = row.get("ema50")
    return bool(close and ema200_value and ema50_value and close > ema200_value * 1.02 and ema50_value > ema200_value)


def _bull_exit(row: dict) -> bool:
    close = row.get("close")
    ema200_value = row.get("ema200")
    return bool(close and ema200_value and close < ema200_value * 0.99)


def _apply_regime_meta(row: dict, key: str, prefix: str) -> None:
    regime = row[key]
    row[f"{prefix}_regime_label"] = REGIMES[regime]["label"]
    row[f"{prefix}_regime_color"] = REGIMES[regime]["color"]
    row[f"{prefix}_action_bias"] = REGIMES[regime]["action_bias"]


def _is_risk_v2(row: dict) -> bool:
    conditions = 0
    day_return = row.get("return")
    return_3d = row.get("return_3d")
    atr_pct = row.get("atr_pct")
    atr_avg = row.get("atr_pct_sma20")
    volume = row.get("volume")
    volume_avg = row.get("volume_sma20")
    alt_up_ratio = row.get("alt_up_ratio")

    if day_return is not None and day_return <= -0.07:
        conditions += 1
    if return_3d is not None and return_3d <= -0.12:
        conditions += 1
    if atr_pct is not None and atr_avg and atr_pct / atr_avg >= 1.8:
        conditions += 1
    if volume is not None and volume_avg and volume / volume_avg >= 1.8:
        conditions += 1
    if alt_up_ratio is not None and alt_up_ratio <= 0.25:
        conditions += 1
    return conditions >= 2


def _is_alt_regime(row: dict) -> bool:
    close = row.get("close")
    ema50_value = row.get("ema50")
    eth_btc = row.get("eth_btc")
    eth_ema50 = row.get("eth_btc_ema50")
    eth_ema200 = row.get("eth_btc_ema200")
    alt_up_ratio = row.get("alt_up_ratio")
    if None in {close, ema50_value, eth_btc, eth_ema50, eth_ema200, alt_up_ratio}:
        return False
    btc_not_breaking = close >= ema50_value * 0.96 or (row.get("return") or 0) >= -0.02
    eth_btc_rising = eth_btc > eth_ema50 and eth_ema50 >= eth_ema200
    return btc_not_breaking and eth_btc_rising and alt_up_ratio >= 0.60


def _is_btc_regime(row: dict) -> bool:
    close = row.get("close")
    ema50_value = row.get("ema50")
    eth_btc = row.get("eth_btc")
    eth_ema50 = row.get("eth_btc_ema50")
    alt_up_ratio = row.get("alt_up_ratio")
    if None in {close, ema50_value, eth_btc, eth_ema50, alt_up_ratio}:
        return False
    btc_rising = close > ema50_value or (row.get("return") or 0) > 0.018
    eth_btc_weak = eth_btc < eth_ema50
    return btc_rising and eth_btc_weak and alt_up_ratio < 0.50


def _is_sideways(row: dict) -> bool:
    close = row.get("close")
    ema50_value = row.get("ema50")
    atr_pct = row.get("atr_pct")
    atr_avg = row.get("atr_pct_sma50")
    if None in {close, ema50_value, atr_pct, atr_avg}:
        return False
    near_ema50 = abs(close / ema50_value - 1) <= 0.035
    low_volatility = atr_pct <= atr_avg * 0.92
    return near_ema50 and low_volatility


def _eth_btc_series(btc_rows: List[dict], eth_index: Dict[int, dict]) -> List[Optional[float]]:
    values: List[Optional[float]] = []
    for btc in btc_rows:
        eth = eth_index.get(btc["time"])
        if eth and btc["close"]:
            values.append(eth["close"] / btc["close"])
        else:
            values.append(None)
    return values


def _alt_snapshot(timestamp: int, indexes: Dict[str, Dict[int, dict]]) -> dict:
    present = []
    returns = {}
    open_close_returns = {}
    up = 0
    above_ema200 = 0
    volume_expansion = 0
    for symbol in ALT_SYMBOLS:
        row = indexes.get(symbol, {}).get(timestamp)
        if not row or row.get("return") is None:
            continue
        present.append(symbol)
        returns[symbol] = row["return"]
        open_close_returns[symbol] = _open_close_return(row)
        if row["return"] > 0:
            up += 1
        if row.get("ema200") and row["close"] > row["ema200"]:
            above_ema200 += 1
        if row.get("volume_sma20") and row["volume"] > row["volume_sma20"] * 1.2:
            volume_expansion += 1

    count = len(present)
    if count < 3:
        return {
            "alt_count": count,
            "alt_symbols": present,
            "alt_returns": returns,
            "alt_open_close_returns": open_close_returns,
            "alt_up_ratio": None,
            "alt_above_ema200_ratio": None,
            "alt_volume_expansion_ratio": None,
            "alt_average_return": None,
            "alt_average_open_close_return": None,
        }
    return {
        "alt_count": count,
        "alt_symbols": present,
        "alt_returns": returns,
        "alt_open_close_returns": open_close_returns,
        "alt_up_ratio": up / count,
        "alt_above_ema200_ratio": above_ema200 / count,
        "alt_volume_expansion_ratio": volume_expansion / count,
        "alt_average_return": sum(returns.values()) / count,
        "alt_average_open_close_return": _average(open_close_returns.values()),
    }


def _open_close_return(row: Optional[dict]) -> Optional[float]:
    if not row or not row.get("open"):
        return None
    return row["close"] / row["open"] - 1


def _average(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _symbol_data_summary(symbol_rows: Dict[str, List[dict]], symbols: List[str]) -> List[dict]:
    rows = []
    for symbol in symbols:
        candles = symbol_rows.get(symbol, [])
        rows.append(
            {
                "symbol": symbol,
                "start": candles[0]["time"] if candles else None,
                "end": candles[-1]["time"] if candles else None,
                "days": len(candles),
            }
        )
    return rows


def _segments(points: List[dict], interval_seconds: int, regime_key: str) -> List[dict]:
    segments: List[dict] = []
    current: Optional[dict] = None

    for index, point in enumerate(points):
        next_time = points[index + 1]["time"] if index + 1 < len(points) else point["time"] + interval_seconds
        regime = point[regime_key]
        if current is None or current["regime"] != regime:
            if current is not None:
                segments.append(current)
            current = {
                "from": point["time"],
                "to": next_time,
                "regime": regime,
                "label": REGIMES[regime]["label"],
                "color": REGIMES[regime]["color"],
                "action_bias": REGIMES[regime]["action_bias"],
                "count": 1,
            }
        else:
            current["to"] = next_time
            current["count"] += 1
    if current is not None:
        segments.append(current)
    return segments


def _stats(points: List[dict], regime_key: str) -> List[dict]:
    total = len(points) or 1
    stats = []
    for key, meta in REGIMES.items():
        count = sum(1 for point in points if point[regime_key] == key)
        stats.append(
            {
                "regime": key,
                "label": meta["label"],
                "color": meta["color"],
                "action_bias": meta["action_bias"],
                "count": count,
                "pct": count / total,
            }
        )
    return stats


def _latest(points: List[dict]) -> dict:
    if not points:
        return {}
    point = points[-1]
    return {
        "time": point["time"],
        "close": point["close"],
        "regime": point["regime"],
        "regime_label": point["regime_label"],
        "regime_color": point["regime_color"],
        "action_bias": point.get("action_bias"),
        "raw_regime": point.get("raw_regime"),
        "raw_regime_label": point.get("raw_regime_label"),
        "raw_regime_color": point.get("raw_regime_color"),
        "raw_action_bias": point.get("raw_action_bias"),
        "v2_stable_regime": point.get("v2_stable_regime"),
        "v2_stable_regime_label": point.get("v2_stable_regime_label"),
        "v2_stable_regime_color": point.get("v2_stable_regime_color"),
        "v2_stable_action_bias": point.get("v2_stable_action_bias"),
        "v2_trade_regime": point.get("v2_trade_regime"),
        "v2_trade_regime_label": point.get("v2_trade_regime_label"),
        "v2_trade_regime_color": point.get("v2_trade_regime_color"),
        "v2_trade_action_bias": point.get("v2_trade_action_bias"),
        "stable_regime": point.get("stable_regime"),
        "stable_regime_label": point.get("stable_regime_label"),
        "stable_regime_color": point.get("stable_regime_color"),
        "stable_action_bias": point.get("stable_action_bias"),
        "trade_regime": point.get("trade_regime"),
        "trade_regime_label": point.get("trade_regime_label"),
        "trade_regime_color": point.get("trade_regime_color"),
        "trade_action_bias": point.get("trade_action_bias"),
        "ema50": point.get("ema50"),
        "ema200": point.get("ema200"),
        "atr_pct": point.get("atr_pct"),
        "atr_pct_sma20": point.get("atr_pct_sma20"),
        "eth_btc": point.get("eth_btc"),
        "eth_return": point.get("eth_return"),
        "return_3d": point.get("return_3d"),
        "ema50_slope": point.get("ema50_slope"),
        "alt_up_ratio": point.get("alt_up_ratio"),
        "alt_above_ema200_ratio": point.get("alt_above_ema200_ratio"),
        "alt_average_return": point.get("alt_average_return"),
        "alt_count": point.get("alt_count"),
    }


def _points(points: List[dict]) -> List[dict]:
    keys = [
        "time",
        "open",
        "close",
        "return",
        "return_3d",
        "ema50",
        "ema50_slope",
        "ema200",
        "atr_pct",
        "atr_pct_sma20",
        "atr_pct_sma50",
        "volume",
        "volume_sma20",
        "eth_btc",
        "eth_btc_ema50",
        "eth_btc_ema200",
        "alt_count",
        "alt_up_ratio",
        "alt_above_ema200_ratio",
        "alt_volume_expansion_ratio",
        "raw_regime",
        "raw_regime_label",
        "raw_regime_color",
        "raw_action_bias",
        "v2_stable_regime",
        "v2_stable_regime_label",
        "v2_stable_regime_color",
        "v2_stable_action_bias",
        "v2_trade_regime",
        "v2_trade_regime_label",
        "v2_trade_regime_color",
        "v2_trade_action_bias",
        "stable_regime",
        "stable_regime_label",
        "stable_regime_color",
        "stable_action_bias",
        "regime",
        "regime_label",
        "regime_color",
        "action_bias",
        "trade_regime",
        "trade_regime_label",
        "trade_regime_color",
        "trade_action_bias",
        "eth_return",
        "eth_open_close_return",
        "alt_symbols",
        "alt_returns",
        "alt_average_return",
        "alt_open_close_returns",
        "alt_average_open_close_return",
    ]
    return [_select(point, keys) for point in points]


def _series(points: List[dict], keys: List[str]) -> List[dict]:
    return [_select(point, keys) for point in points]


def _line(points: List[dict], key: str) -> List[dict]:
    return [
        {"time": point["time"], "value": point[key]}
        for point in points
        if point.get(key) is not None
    ]


def _select(row: dict, keys: List[str]) -> dict:
    return {key: row.get(key) for key in keys}


def _write_processed(data_dir: Path, payload: dict) -> None:
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / "regime_1d_latest.json"
    import json

    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
