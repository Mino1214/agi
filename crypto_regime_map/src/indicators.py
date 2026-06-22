"""Indicator calculations for regime classification."""

from __future__ import annotations

from typing import Iterable, List, Optional


Number = Optional[float]


def add_indicators(candles: Iterable[dict]) -> List[dict]:
    rows = [dict(item) for item in candles]
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]

    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    atr14 = atr(rows, 14)
    atr_pct = [value / close if value is not None and close else None for value, close in zip(atr14, closes)]
    atr_pct_sma20 = rolling_average(atr_pct, 20)
    atr_pct_sma50 = rolling_average(atr_pct, 50)
    volume_sma20 = rolling_average(volumes, 20)

    previous_close: Number = None
    for index, row in enumerate(rows):
        close = row["close"]
        row["return"] = close / previous_close - 1 if previous_close else None
        row["return_3d"] = close / rows[index - 3]["close"] - 1 if index >= 3 else None
        row["ema50"] = ema50[index]
        row["ema200"] = ema200[index]
        row["ema50_slope"] = (
            ema50[index] / ema50[index - 3] - 1
            if index >= 3 and ema50[index] is not None and ema50[index - 3] is not None
            else None
        )
        row["atr"] = atr14[index]
        row["atr_pct"] = atr_pct[index]
        row["atr_pct_sma20"] = atr_pct_sma20[index]
        row["atr_pct_sma50"] = atr_pct_sma50[index]
        row["volume_sma20"] = volume_sma20[index]
        previous_close = close
    return rows


def ema(values: Iterable[Number], period: int) -> List[Number]:
    multiplier = 2 / (period + 1)
    result: List[Number] = []
    window: List[float] = []
    previous: Number = None

    for value in values:
        if value is None:
            result.append(None)
            continue
        number = float(value)
        window.append(number)
        if len(window) < period:
            result.append(None)
            continue
        if previous is None:
            previous = sum(window[-period:]) / period
        else:
            previous = number * multiplier + previous * (1 - multiplier)
        result.append(previous)
    return result


def rolling_average(values: Iterable[Number], period: int) -> List[Number]:
    result: List[Number] = []
    window: List[float] = []
    for value in values:
        if value is not None:
            window.append(float(value))
        if len(window) < period:
            result.append(None)
        else:
            result.append(sum(window[-period:]) / period)
    return result


def atr(candles: List[dict], period: int) -> List[Number]:
    true_ranges: List[float] = []
    previous_close: Number = None
    for row in candles:
        high = row["high"]
        low = row["low"]
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = row["close"]
    return rolling_average(true_ranges, period)
