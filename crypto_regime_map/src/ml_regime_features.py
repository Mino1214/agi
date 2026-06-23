"""Offline ML regime feature assembly.

The functions in this module are research-only helpers. They only use current
and historical rows for every feature value; forward-looking outcomes live in
``ml_regime_labels``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import pandas as pd


BTC_FEATURES = [
    "return_1d",
    "return_3d",
    "return_7d",
    "return_14d",
    "distance_to_ema20",
    "distance_to_ema50",
    "distance_to_ema200",
    "ema20_slope",
    "ema50_slope",
    "ema200_slope",
    "volatility_7d",
    "volatility_14d",
    "volatility_30d",
    "drawdown_from_30d_high",
    "drawdown_from_90d_high",
    "volume_change_7d",
]

RELATIVE_STRENGTH_FEATURES = [
    "eth_btc_return_spread_7d",
    "sol_btc_return_spread_7d",
    "eth_btc_trend",
    "sol_btc_trend",
]

FUNDING_FEATURES = [
    "btc_funding_rate",
    "btc_funding_rate_7d",
]

OPTIONAL_FEATURES = [
    "btc_open_interest_change_7d",
    "btc_dominance_trend_30d",
    "total_market_trend_30d",
    "total2_market_trend_30d",
    "total3_market_trend_30d",
]


@dataclass(frozen=True)
class FeatureBuildResult:
    frame: pd.DataFrame
    used_features: List[str]
    missing_features: List[str]


def read_json_cache(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_ohlcv_cache(raw_dir: Path, symbols: Iterable[str], interval: str = "1d") -> Dict[str, List[dict]]:
    return {
        symbol: read_json_cache(raw_dir / f"{symbol}_{interval}.json")
        for symbol in symbols
    }


def build_feature_frame(
    raw_ohlcv: Mapping[str, List[dict]],
    funding_rows: Optional[List[dict]] = None,
    optional_ohlcv: Optional[Mapping[str, List[dict]]] = None,
    optional_open_interest_rows: Optional[List[dict]] = None,
) -> FeatureBuildResult:
    if not raw_ohlcv.get("BTCUSDT"):
        raise ValueError("BTCUSDT 1d OHLCV cache is required")

    missing: List[str] = []
    btc = _ohlcv_frame(raw_ohlcv["BTCUSDT"], "BTCUSDT")
    frame = _add_btc_features(btc)
    used = list(BTC_FEATURES)

    frame, relative_used, relative_missing = _add_relative_strength(frame, raw_ohlcv)
    used.extend(relative_used)
    missing.extend(relative_missing)

    frame, funding_used, funding_missing = _add_funding_features(frame, funding_rows or [])
    used.extend(funding_used)
    missing.extend(funding_missing)

    frame, optional_used, optional_missing = _add_optional_features(
        frame=frame,
        optional_ohlcv=optional_ohlcv or {},
        optional_open_interest_rows=optional_open_interest_rows or [],
    )
    used.extend(optional_used)
    missing.extend(optional_missing)

    ordered = ["time", "date", "open", "high", "low", "close", "volume"] + used
    frame = frame[ordered].sort_values("time").reset_index(drop=True)
    return FeatureBuildResult(frame=frame, used_features=used, missing_features=missing)


def _ohlcv_frame(candles: List[dict], symbol: str) -> pd.DataFrame:
    frame = pd.DataFrame(candles)
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{symbol} OHLCV cache is missing columns: {sorted(missing)}")

    frame = frame[list(required)].copy()
    for column in ["time", "open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["time", "close"]).sort_values("time")
    frame = frame.drop_duplicates(subset=["time"], keep="last")
    frame["time"] = frame["time"].astype("int64")
    frame["date"] = pd.to_datetime(frame["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    return frame.reset_index(drop=True)


def _add_btc_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close = out["close"]
    returns = close.pct_change()

    out["return_1d"] = returns
    out["return_3d"] = close.pct_change(3)
    out["return_7d"] = close.pct_change(7)
    out["return_14d"] = close.pct_change(14)

    for period in (20, 50, 200):
        ema = close.ewm(span=period, adjust=False, min_periods=period).mean()
        out[f"distance_to_ema{period}"] = close / ema - 1.0
        out[f"ema{period}_slope"] = ema.pct_change(7)

    out["volatility_7d"] = returns.rolling(7, min_periods=7).std()
    out["volatility_14d"] = returns.rolling(14, min_periods=14).std()
    out["volatility_30d"] = returns.rolling(30, min_periods=30).std()
    out["drawdown_from_30d_high"] = close / close.rolling(30, min_periods=30).max() - 1.0
    out["drawdown_from_90d_high"] = close / close.rolling(90, min_periods=90).max() - 1.0
    out["volume_change_7d"] = out["volume"].pct_change(7)
    return out


def _add_relative_strength(
    frame: pd.DataFrame,
    raw_ohlcv: Mapping[str, List[dict]],
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    out = frame.copy()
    used: List[str] = []
    missing: List[str] = []

    for symbol, prefix in (("ETHUSDT", "eth"), ("SOLUSDT", "sol")):
        spread_feature = f"{prefix}_btc_return_spread_7d"
        trend_feature = f"{prefix}_btc_trend"
        candles = raw_ohlcv.get(symbol) or []
        if not candles:
            missing.extend([spread_feature, trend_feature])
            continue

        asset = _ohlcv_frame(candles, symbol)[["time", "close"]].rename(columns={"close": f"{prefix}_close"})
        out = out.merge(asset, on="time", how="left")
        asset_close = out[f"{prefix}_close"]
        btc_close = out["close"]
        ratio = asset_close / btc_close
        out[spread_feature] = asset_close.pct_change(7) - btc_close.pct_change(7)
        out[trend_feature] = ratio / ratio.ewm(span=20, adjust=False, min_periods=20).mean() - 1.0
        out = out.drop(columns=[f"{prefix}_close"])
        used.extend([spread_feature, trend_feature])

    return out, used, missing


def _add_funding_features(frame: pd.DataFrame, funding_rows: List[dict]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    if not funding_rows:
        return frame, [], list(FUNDING_FEATURES)

    funding = pd.DataFrame(funding_rows)
    if "fundingTime" not in funding.columns or "fundingRate" not in funding.columns:
        return frame, [], list(FUNDING_FEATURES)

    funding["fundingTime"] = pd.to_numeric(funding["fundingTime"], errors="coerce")
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="coerce")
    funding = funding.dropna(subset=["fundingTime", "fundingRate"])
    if funding.empty:
        return frame, [], list(FUNDING_FEATURES)

    funding["date"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    daily = funding.groupby("date", as_index=False)["fundingRate"].mean()
    daily = daily.sort_values("date")
    daily["btc_funding_rate"] = daily["fundingRate"].shift(1)
    daily["btc_funding_rate_7d"] = daily["btc_funding_rate"].rolling(7, min_periods=7).mean()

    out = frame.merge(daily[["date", "btc_funding_rate", "btc_funding_rate_7d"]], on="date", how="left")
    return out, list(FUNDING_FEATURES), []


def _add_optional_features(
    frame: pd.DataFrame,
    optional_ohlcv: Mapping[str, List[dict]],
    optional_open_interest_rows: List[dict],
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    out = frame.copy()
    used: List[str] = []
    missing: List[str] = []

    if optional_open_interest_rows:
        oi = _open_interest_frame(optional_open_interest_rows)
        if oi.empty:
            missing.append("btc_open_interest_change_7d")
        else:
            out = out.merge(oi, on="date", how="left")
            out["btc_open_interest_change_7d"] = out["open_interest"].pct_change(7)
            out = out.drop(columns=["open_interest"])
            used.append("btc_open_interest_change_7d")
    else:
        missing.append("btc_open_interest_change_7d")

    optional_specs = [
        ("BTCDOM", "btc_dominance_trend_30d"),
        ("TOTAL", "total_market_trend_30d"),
        ("TOTAL2", "total2_market_trend_30d"),
        ("TOTAL3", "total3_market_trend_30d"),
    ]
    for key, feature in optional_specs:
        candles = optional_ohlcv.get(key) or []
        if not candles:
            missing.append(feature)
            continue
        market = _ohlcv_frame(candles, key)[["time", "close"]].rename(columns={"close": f"{key}_close"})
        out = out.merge(market, on="time", how="left")
        out[feature] = out[f"{key}_close"].pct_change(30)
        out = out.drop(columns=[f"{key}_close"])
        used.append(feature)

    return out, used, missing


def _open_interest_frame(rows: List[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    time_column = _first_existing_column(frame, ["timestamp", "time", "sumOpenInterestTime"])
    value_column = _first_existing_column(frame, ["sumOpenInterest", "openInterest", "value"])
    if not time_column or not value_column:
        return pd.DataFrame()

    frame[time_column] = pd.to_numeric(frame[time_column], errors="coerce")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna(subset=[time_column, value_column])
    if frame.empty:
        return pd.DataFrame()

    unit = "ms" if frame[time_column].median() > 10_000_000_000 else "s"
    frame["date"] = pd.to_datetime(frame[time_column], unit=unit, utc=True).dt.strftime("%Y-%m-%d")
    daily = frame.groupby("date", as_index=False)[value_column].last()
    return daily.rename(columns={value_column: "open_interest"})


def _first_existing_column(frame: pd.DataFrame, columns: Iterable[str]) -> Optional[str]:
    for column in columns:
        if column in frame.columns:
            return column
    return None
