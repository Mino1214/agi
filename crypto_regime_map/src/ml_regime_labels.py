"""Forward label generation for the offline ML regime PoC."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List

import pandas as pd


REGIME_LABELS = ["shock", "defensive", "chop", "recovery", "uptrend"]


def add_forward_labels(frame: pd.DataFrame, horizon_days: int = 14) -> pd.DataFrame:
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    for column in ("close", "low"):
        if column not in frame.columns:
            raise ValueError(f"frame is missing required column: {column}")

    out = frame.copy()
    out[f"future_return_{horizon_days}d"] = out["close"].shift(-horizon_days) / out["close"] - 1.0
    out[f"future_max_drawdown_{horizon_days}d"] = _future_min_low(out["low"], horizon_days) / out["close"] - 1.0
    out["label"] = [
        classify_forward_label(future_return, future_drawdown)
        for future_return, future_drawdown in zip(
            out[f"future_return_{horizon_days}d"],
            out[f"future_max_drawdown_{horizon_days}d"],
        )
    ]
    return out


def classify_forward_label(future_return: float, future_max_drawdown: float) -> str | None:
    if pd.isna(future_return) or pd.isna(future_max_drawdown):
        return None
    if future_max_drawdown <= -0.10:
        return "shock"
    if future_return >= 0.08 and future_max_drawdown > -0.06:
        return "uptrend"
    if future_return >= 0.03 and future_max_drawdown > -0.08:
        return "recovery"
    if future_return <= -0.05:
        return "defensive"
    return "chop"


def label_distribution(labels: Iterable[str]) -> List[Dict[str, object]]:
    counts = Counter(label for label in labels if label)
    total = sum(counts.values())
    return [
        {
            "label": label,
            "count": counts.get(label, 0),
            "share": counts.get(label, 0) / total if total else 0.0,
        }
        for label in REGIME_LABELS
    ]


def _future_min_low(values: pd.Series, horizon_days: int) -> pd.Series:
    return pd.Series(
        [
            values.iloc[index + 1 : index + horizon_days + 1].min()
            if index + horizon_days < len(values)
            else None
            for index in range(len(values))
        ],
        index=values.index,
    )
