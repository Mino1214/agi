"""Two-stage offline ML regime research helpers.

ML Regime v2 is intentionally report-only. It builds point-in-time features,
creates forward labels, and evaluates binary probabilistic models with
walk-forward validation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml_regime_features import FeatureBuildResult, build_feature_frame
from ml_regime_models import Fold, build_walk_forward_folds


V2_1D_FEATURES = [
    "eth_btc_return_spread_3d",
    "eth_btc_return_spread_14d",
    "sol_btc_return_spread_3d",
    "sol_btc_return_spread_14d",
    "volume_zscore_30d",
    "volatility_compression",
    "drawdown_recovery_ratio",
    "btc_funding_rate_change_7d",
]

V2_INTRADAY_FEATURES = [
    "btc_1h_return_6h",
    "btc_4h_return_12h",
    "btc_4h_return_24h",
    "btc_4h_return_48h",
    "btc_4h_distance_to_ema50",
    "btc_4h_distance_to_ema200",
    "btc_4h_volatility_7d",
]

THRESHOLD_GRID = [round(value / 100, 2) for value in range(5, 96, 5)]


@dataclass(frozen=True)
class V2FeatureBuildResult:
    frame: pd.DataFrame
    used_features: List[str]
    missing_features: List[str]


@dataclass(frozen=True)
class BinaryModelSpec:
    name: str
    factory: Callable[[], object]
    skip_reason: str = ""
    calibrate: bool = False

    @property
    def available(self) -> bool:
        return not self.skip_reason


@dataclass(frozen=True)
class V2WalkForwardResult:
    shock_metrics: List[dict]
    opportunity_metrics: List[dict]
    threshold_rows: List[dict]
    predictions: List[dict]
    feature_importance: List[dict]
    skipped_models: List[dict]
    folds: List[Fold]


def make_v2_model_specs(random_state: int = 42) -> List[BinaryModelSpec]:
    specs = [
        BinaryModelSpec(
            name="Logistic Regression",
            factory=lambda: Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=2000,
                            class_weight="balanced",
                            solver="lbfgs",
                        ),
                    ),
                ]
            ),
            calibrate=True,
        ),
        BinaryModelSpec(
            name="Random Forest",
            factory=lambda: RandomForestClassifier(
                n_estimators=180,
                min_samples_leaf=5,
                class_weight="balanced_subsample",
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
    ]

    try:
        from lightgbm import LGBMClassifier

        specs.append(
            BinaryModelSpec(
                name="LightGBM",
                factory=lambda: LGBMClassifier(
                    objective="binary",
                    n_estimators=180,
                    learning_rate=0.04,
                    num_leaves=15,
                    min_child_samples=20,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    class_weight="balanced",
                    random_state=random_state,
                    verbosity=-1,
                ),
            )
        )
    except Exception as exc:  # pragma: no cover - depends on local environment.
        specs.append(BinaryModelSpec(name="LightGBM", factory=lambda: None, skip_reason=f"unavailable: {exc}"))

    return specs


def build_v2_feature_frame(
    raw_1d: Mapping[str, List[dict]],
    raw_4h: Optional[Mapping[str, List[dict]]] = None,
    raw_1h: Optional[Mapping[str, List[dict]]] = None,
    funding_rows: Optional[List[dict]] = None,
    optional_ohlcv: Optional[Mapping[str, List[dict]]] = None,
    optional_open_interest_rows: Optional[List[dict]] = None,
) -> V2FeatureBuildResult:
    base = build_feature_frame(
        raw_ohlcv=raw_1d,
        funding_rows=funding_rows,
        optional_ohlcv=optional_ohlcv,
        optional_open_interest_rows=optional_open_interest_rows,
    )
    frame = base.frame.copy()
    used = list(base.used_features)
    missing = list(base.missing_features)

    frame, extra_used, extra_missing = _add_daily_v2_features(frame, raw_1d)
    used.extend(extra_used)
    missing.extend(extra_missing)

    frame, intraday_used, intraday_missing = _add_intraday_features(frame, raw_4h or {}, raw_1h or {})
    used.extend(intraday_used)
    missing.extend(intraday_missing)

    used = list(dict.fromkeys(used))
    missing = list(dict.fromkeys(item for item in missing if item not in used))
    ordered = ["time", "date", "open", "high", "low", "close", "volume"] + used
    return V2FeatureBuildResult(frame=frame[ordered].sort_values("time").reset_index(drop=True), used_features=used, missing_features=missing)


def add_v2_labels(
    frame: pd.DataFrame,
    shock_drawdown_14d: float = -0.08,
    opportunity_return_14d: float = 0.05,
    opportunity_drawdown_14d: float = -0.08,
    opportunity_return_7d: float = 0.03,
    opportunity_drawdown_7d: float = -0.05,
) -> pd.DataFrame:
    out = frame.copy()
    out["future_return_7d"] = out["close"].shift(-7) / out["close"] - 1.0
    out["future_return_14d"] = out["close"].shift(-14) / out["close"] - 1.0
    out["future_max_drawdown_7d"] = _future_min_low(out["low"], 7) / out["close"] - 1.0
    out["future_max_drawdown_14d"] = _future_min_low(out["low"], 14) / out["close"] - 1.0

    shock_valid = out["future_max_drawdown_14d"].notna()
    out["shock_label"] = pd.NA
    out.loc[shock_valid, "shock_label"] = (out.loc[shock_valid, "future_max_drawdown_14d"] <= shock_drawdown_14d).astype(int)

    opportunity_14d = (
        (out["future_return_14d"] >= opportunity_return_14d)
        & (out["future_max_drawdown_14d"] > opportunity_drawdown_14d)
    )
    opportunity_7d = (
        (out["future_return_7d"] >= opportunity_return_7d)
        & (out["future_max_drawdown_7d"] > opportunity_drawdown_7d)
    )
    opportunity_valid = (
        out["future_return_14d"].notna()
        & out["future_max_drawdown_14d"].notna()
        & out["future_return_7d"].notna()
        & out["future_max_drawdown_7d"].notna()
    )
    out["opportunity_label"] = pd.NA
    out.loc[opportunity_valid, "opportunity_label"] = (opportunity_14d.loc[opportunity_valid] | opportunity_7d.loc[opportunity_valid]).astype(int)
    return out


def run_v2_walk_forward_validation(
    frame: pd.DataFrame,
    feature_columns: List[str],
    model_specs: Optional[List[BinaryModelSpec]] = None,
    folds: int = 5,
    min_train_size: int = 730,
    test_size: int = 180,
    calibrate: bool = True,
    shock_recall_target: float = 0.50,
    opportunity_precision_delta: float = 0.08,
) -> V2WalkForwardResult:
    required = ["time", "date", "shock_label", "opportunity_label"] + feature_columns
    missing_columns = [column for column in required if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"frame is missing columns: {missing_columns}")

    dataset = frame[required].dropna(subset=["shock_label", "opportunity_label"] + feature_columns)
    dataset = dataset.sort_values("time").reset_index(drop=True)
    dataset["shock_label"] = dataset["shock_label"].astype(int)
    dataset["opportunity_label"] = dataset["opportunity_label"].astype(int)
    fold_defs = build_walk_forward_folds(dataset, folds=folds, min_train_size=min_train_size, test_size=test_size)
    specs = model_specs or make_v2_model_specs()

    shock_metrics: List[dict] = []
    opportunity_metrics: List[dict] = []
    threshold_rows: List[dict] = []
    predictions: List[dict] = []
    importance_rows: List[dict] = []
    skipped: List[dict] = [
        {"model": spec.name, "reason": spec.skip_reason}
        for spec in specs
        if not spec.available
    ]

    for fold in fold_defs:
        train = dataset.iloc[fold.train_indices].copy()
        test = dataset.iloc[fold.test_indices].copy()
        x_train = train[feature_columns]
        x_test = test[feature_columns]
        y_train_shock = train["shock_label"].astype(int)
        y_test_shock = test["shock_label"].astype(int)

        for spec in specs:
            if not spec.available:
                continue
            if y_train_shock.nunique() < 2:
                skipped.append({"model": spec.name, "task": "shock", "fold": fold.fold, "reason": "train fold has fewer than two labels"})
                continue

            try:
                shock_model = _fit_probability_model(spec.factory(), x_train, y_train_shock, calibrate=calibrate and spec.calibrate)
                shock_train_prob = _positive_probability(shock_model, x_train)
                shock_test_prob = _positive_probability(shock_model, x_test)
                importance_model = spec.factory()
                importance_model.fit(x_train, y_train_shock)
                importance_rows.extend(_feature_importance_rows(spec.name, "shock", fold, importance_model, feature_columns))
            except Exception as exc:
                skipped.append({"model": spec.name, "task": "shock", "fold": fold.fold, "reason": str(exc)})
                continue

            shock_threshold = select_shock_threshold(y_train_shock, shock_train_prob, recall_target=shock_recall_target)
            shock_metrics.append(
                _binary_metric_row(
                    task="shock",
                    model_name=spec.name,
                    fold=fold,
                    y_true=y_test_shock,
                    probabilities=shock_test_prob,
                    threshold=shock_threshold,
                    baseline=float(y_test_shock.mean()),
                )
            )
            threshold_rows.extend(
                _threshold_rows("shock", spec.name, fold, "train", y_train_shock, shock_train_prob, shock_threshold)
            )
            threshold_rows.extend(
                _threshold_rows("shock", spec.name, fold, "test", y_test_shock, shock_test_prob, shock_threshold)
            )

            train_non_shock = train[train["shock_label"] == 0]
            test_non_shock = test[test["shock_label"] == 0]
            if train_non_shock["opportunity_label"].nunique() < 2 or test_non_shock.empty:
                skipped.append({"model": spec.name, "task": "opportunity", "fold": fold.fold, "reason": "non-shock train/test fold lacks enough labels"})
                opportunity_test_prob = [None] * len(test)
                opportunity_threshold = None
            else:
                x_train_opp = train_non_shock[feature_columns]
                y_train_opp = train_non_shock["opportunity_label"].astype(int)
                x_test_opp = test_non_shock[feature_columns]
                y_test_opp = test_non_shock["opportunity_label"].astype(int)
                try:
                    opportunity_model = _fit_probability_model(spec.factory(), x_train_opp, y_train_opp, calibrate=calibrate and spec.calibrate)
                    opportunity_train_prob = _positive_probability(opportunity_model, x_train_opp)
                    opportunity_test_prob_non_shock = _positive_probability(opportunity_model, x_test_opp)
                    opportunity_test_prob = _positive_probability(opportunity_model, x_test)
                    opportunity_threshold = select_opportunity_threshold(
                        y_train_opp,
                        opportunity_train_prob,
                        baseline=float(y_train_opp.mean()),
                        precision_delta=opportunity_precision_delta,
                    )
                    opp_importance_model = spec.factory()
                    opp_importance_model.fit(x_train_opp, y_train_opp)
                    importance_rows.extend(_feature_importance_rows(spec.name, "opportunity", fold, opp_importance_model, feature_columns))
                    opportunity_metrics.append(
                        _binary_metric_row(
                            task="opportunity",
                            model_name=spec.name,
                            fold=fold,
                            y_true=y_test_opp,
                            probabilities=opportunity_test_prob_non_shock,
                            threshold=opportunity_threshold,
                            baseline=float(y_test_opp.mean()),
                        )
                    )
                    threshold_rows.extend(
                        _threshold_rows("opportunity", spec.name, fold, "train", y_train_opp, opportunity_train_prob, opportunity_threshold)
                    )
                    threshold_rows.extend(
                        _threshold_rows("opportunity", spec.name, fold, "test", y_test_opp, opportunity_test_prob_non_shock, opportunity_threshold)
                    )
                except Exception as exc:
                    skipped.append({"model": spec.name, "task": "opportunity", "fold": fold.fold, "reason": str(exc)})
                    opportunity_test_prob = [None] * len(test)
                    opportunity_threshold = None

            predictions.extend(
                _prediction_rows(
                    model_name=spec.name,
                    fold=fold,
                    test=test,
                    shock_prob=shock_test_prob,
                    opportunity_prob=opportunity_test_prob,
                    shock_threshold=shock_threshold,
                    opportunity_threshold=opportunity_threshold,
                )
            )

    return V2WalkForwardResult(
        shock_metrics=shock_metrics,
        opportunity_metrics=opportunity_metrics,
        threshold_rows=threshold_rows,
        predictions=predictions,
        feature_importance=importance_rows,
        skipped_models=skipped,
        folds=fold_defs,
    )


def summarize_binary_metrics(rows: Iterable[dict], sort_key: str) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)

    summary: List[dict] = []
    for model, model_rows in grouped.items():
        summary.append(
            {
                "model": model,
                "folds": len(model_rows),
                "threshold": _mean(model_rows, "threshold"),
                "baseline": _mean(model_rows, "baseline"),
                "precision": _mean(model_rows, "precision"),
                "recall": _mean(model_rows, "recall"),
                "fpr": _mean(model_rows, "false_positive_rate"),
                "pr_auc": _mean(model_rows, "pr_auc"),
                "roc_auc": _mean(model_rows, "roc_auc"),
                "precision_delta": _mean(model_rows, "precision_delta"),
                "positive_count": sum(int(row["positive_count"]) for row in model_rows),
            }
        )
    return sorted(summary, key=lambda row: (row.get(sort_key) or 0.0, row.get("precision") or 0.0), reverse=True)


def aggregate_v2_feature_importance(rows: Iterable[dict], top_n: int = 20) -> List[dict]:
    grouped: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["model"], row["feature"])].append(float(row["importance"]))

    aggregated = [
        {
            "task": task,
            "model": model,
            "feature": feature,
            "importance": sum(values) / len(values),
        }
        for (task, model, feature), values in grouped.items()
    ]
    aggregated.sort(key=lambda row: (row["task"], row["model"], -row["importance"], row["feature"]))

    out: List[dict] = []
    ranks: Dict[Tuple[str, str], int] = defaultdict(int)
    for row in aggregated:
        key = (row["task"], row["model"])
        if ranks[key] >= top_n:
            continue
        ranks[key] += 1
        out.append({**row, "rank": ranks[key]})
    return out


def final_state_distribution(predictions: Iterable[dict]) -> List[dict]:
    counts = Counter(row["final_ml_state"] for row in predictions)
    total = sum(counts.values())
    return [
        {"final_ml_state": state, "count": count, "share": count / total if total else 0.0}
        for state, count in sorted(counts.items())
    ]


def select_shock_threshold(y_true: Sequence[int], probabilities: Sequence[float], recall_target: float = 0.50) -> float:
    rows = [_threshold_metric_dict(y_true, probabilities, threshold) for threshold in THRESHOLD_GRID]
    viable = [row for row in rows if row["recall"] is not None and row["recall"] >= recall_target]
    if viable:
        viable.sort(key=lambda row: (row["precision"] or 0.0, -(row["false_positive_rate"] or 1.0), row["threshold"]), reverse=True)
        return float(viable[0]["threshold"])
    rows.sort(key=lambda row: (row["recall"] or 0.0, row["precision"] or 0.0), reverse=True)
    return float(rows[0]["threshold"])


def select_opportunity_threshold(
    y_true: Sequence[int],
    probabilities: Sequence[float],
    baseline: float,
    precision_delta: float = 0.08,
) -> float:
    min_predictions = max(5, int(len(y_true) * 0.03))
    rows = [_threshold_metric_dict(y_true, probabilities, threshold) for threshold in THRESHOLD_GRID]
    viable = [
        row
        for row in rows
        if row["predicted_positive_count"] >= min_predictions
        and row["precision"] is not None
        and row["precision"] >= baseline + precision_delta
    ]
    if viable:
        viable.sort(key=lambda row: (row["precision"] or 0.0, row["recall"] or 0.0, row["threshold"]), reverse=True)
        return float(viable[0]["threshold"])
    fallback = [row for row in rows if row["predicted_positive_count"] >= min_predictions and row["precision"] is not None]
    if fallback:
        fallback.sort(key=lambda row: (row["precision"] or 0.0, row["recall"] or 0.0), reverse=True)
        return float(fallback[0]["threshold"])
    rows.sort(key=lambda row: (row["precision"] or 0.0, row["recall"] or 0.0), reverse=True)
    return float(rows[0]["threshold"])


def _add_daily_v2_features(
    frame: pd.DataFrame,
    raw_1d: Mapping[str, List[dict]],
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    out = frame.copy()
    used: List[str] = []
    missing: List[str] = []
    btc_close = out["close"]

    for symbol, prefix in (("ETHUSDT", "eth"), ("SOLUSDT", "sol")):
        candles = raw_1d.get(symbol) or []
        if not candles:
            missing.extend([f"{prefix}_btc_return_spread_3d", f"{prefix}_btc_return_spread_14d"])
            continue
        asset = _ohlcv_frame(candles, symbol)[["time", "close"]].rename(columns={"close": f"{prefix}_close"})
        out = out.merge(asset, on="time", how="left")
        for days in (3, 14):
            feature = f"{prefix}_btc_return_spread_{days}d"
            out[feature] = out[f"{prefix}_close"].pct_change(days) - btc_close.pct_change(days)
            used.append(feature)
        out = out.drop(columns=[f"{prefix}_close"])

    volume_mean = out["volume"].rolling(30, min_periods=30).mean()
    volume_std = out["volume"].rolling(30, min_periods=30).std()
    out["volume_zscore_30d"] = (out["volume"] - volume_mean) / volume_std.replace(0, pd.NA)
    out["volatility_compression"] = out["volatility_7d"] / out["volatility_30d"].replace(0, pd.NA)
    out["drawdown_recovery_ratio"] = out["return_14d"] / out["drawdown_from_30d_high"].abs().clip(lower=0.001)
    used.extend(["volume_zscore_30d", "volatility_compression", "drawdown_recovery_ratio"])

    if "btc_funding_rate" in out.columns:
        out["btc_funding_rate_change_7d"] = out["btc_funding_rate"] - out["btc_funding_rate"].shift(7)
        used.append("btc_funding_rate_change_7d")
    else:
        missing.append("btc_funding_rate_change_7d")

    return out, used, missing


def _add_intraday_features(
    frame: pd.DataFrame,
    raw_4h: Mapping[str, List[dict]],
    raw_1h: Mapping[str, List[dict]],
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    out = frame.copy()
    used: List[str] = []
    missing: List[str] = []

    candles_1h = raw_1h.get("BTCUSDT") or []
    if candles_1h:
        one_hour = _intraday_daily_features(candles_1h, "1h")
        if "btc_1h_return_6h" in one_hour.columns:
            out = out.merge(one_hour[["date", "btc_1h_return_6h"]], on="date", how="left")
            used.append("btc_1h_return_6h")
        else:
            missing.append("btc_1h_return_6h")
    else:
        missing.append("btc_1h_return_6h")

    candles_4h = raw_4h.get("BTCUSDT") or []
    if candles_4h:
        four_hour = _intraday_daily_features(candles_4h, "4h")
        feature_columns = [column for column in V2_INTRADAY_FEATURES if column != "btc_1h_return_6h" and column in four_hour.columns]
        out = out.merge(four_hour[["date"] + feature_columns], on="date", how="left")
        used.extend(feature_columns)
        missing.extend([column for column in V2_INTRADAY_FEATURES if column not in feature_columns and column != "btc_1h_return_6h"])
    else:
        missing.extend([column for column in V2_INTRADAY_FEATURES if column != "btc_1h_return_6h"])

    return out, used, missing


def _intraday_daily_features(candles: List[dict], interval: str) -> pd.DataFrame:
    frame = _ohlcv_frame(candles, f"BTCUSDT_{interval}")
    close = frame["close"]
    returns = close.pct_change()
    if interval == "1h":
        frame["btc_1h_return_6h"] = close.pct_change(6)
        features = ["btc_1h_return_6h"]
    elif interval == "4h":
        frame["btc_4h_return_12h"] = close.pct_change(3)
        frame["btc_4h_return_24h"] = close.pct_change(6)
        frame["btc_4h_return_48h"] = close.pct_change(12)
        ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
        ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
        frame["btc_4h_distance_to_ema50"] = close / ema50 - 1.0
        frame["btc_4h_distance_to_ema200"] = close / ema200 - 1.0
        frame["btc_4h_volatility_7d"] = returns.rolling(42, min_periods=42).std()
        features = [
            "btc_4h_return_12h",
            "btc_4h_return_24h",
            "btc_4h_return_48h",
            "btc_4h_distance_to_ema50",
            "btc_4h_distance_to_ema200",
            "btc_4h_volatility_7d",
        ]
    else:
        raise ValueError(f"unsupported intraday interval: {interval}")

    daily = frame.groupby("date", as_index=False).tail(1)
    return daily[["date"] + features].sort_values("date").reset_index(drop=True)


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


def _fit_probability_model(model: object, x_train: pd.DataFrame, y_train: pd.Series, calibrate: bool) -> object:
    if not calibrate or len(y_train) < 60 or y_train.value_counts().min() < 3:
        model.fit(x_train, y_train)
        return model
    try:
        calibrated = CalibratedClassifierCV(estimator=model, method="sigmoid", cv=3)
    except TypeError:  # pragma: no cover - for older sklearn versions.
        calibrated = CalibratedClassifierCV(base_estimator=model, method="sigmoid", cv=3)
    calibrated.fit(x_train, y_train)
    return calibrated


def _positive_probability(model: object, x_frame: pd.DataFrame) -> List[float]:
    probabilities = model.predict_proba(x_frame)
    classes = list(getattr(model, "classes_", []))
    positive_index = classes.index(1) if 1 in classes else len(classes) - 1
    return [float(value) for value in probabilities[:, positive_index]]


def _binary_metric_row(
    task: str,
    model_name: str,
    fold: Fold,
    y_true: Sequence[int],
    probabilities: Sequence[float],
    threshold: Optional[float],
    baseline: float,
) -> dict:
    metrics = _threshold_metric_dict(y_true, probabilities, threshold or 1.0)
    return {
        "task": task,
        "model": model_name,
        "fold": fold.fold,
        "train_start": fold.train_start,
        "train_end": fold.train_end,
        "test_start": fold.test_start,
        "test_end": fold.test_end,
        "threshold": threshold,
        "baseline": baseline,
        "precision_delta": (metrics["precision"] - baseline) if metrics["precision"] is not None else None,
        "pr_auc": _safe_pr_auc(y_true, probabilities),
        "roc_auc": _safe_roc_auc(y_true, probabilities),
        "positive_count": int(sum(y_true)),
        **{key: value for key, value in metrics.items() if key != "threshold"},
    }


def _threshold_rows(
    task: str,
    model_name: str,
    fold: Fold,
    sample: str,
    y_true: Sequence[int],
    probabilities: Sequence[float],
    selected_threshold: Optional[float],
) -> List[dict]:
    return [
        {
            "task": task,
            "model": model_name,
            "fold": fold.fold,
            "sample": sample,
            "selected": selected_threshold is not None and abs(threshold - selected_threshold) < 1e-12,
            **_threshold_metric_dict(y_true, probabilities, threshold),
        }
        for threshold in THRESHOLD_GRID
    ]


def _threshold_metric_dict(y_true: Sequence[int], probabilities: Sequence[float], threshold: float) -> dict:
    clean_pairs = [(int(label), float(prob)) for label, prob in zip(y_true, probabilities) if prob is not None and not pd.isna(prob)]
    if not clean_pairs:
        return {
            "threshold": threshold,
            "precision": None,
            "recall": None,
            "false_positive_rate": None,
            "predicted_positive_rate": None,
            "predicted_positive_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "true_negative_count": 0,
            "false_negative_count": 0,
        }
    labels = [label for label, _ in clean_pairs]
    preds = [1 if prob >= threshold else 0 for _, prob in clean_pairs]
    tp = sum(1 for label, pred in zip(labels, preds) if label == 1 and pred == 1)
    fp = sum(1 for label, pred in zip(labels, preds) if label == 0 and pred == 1)
    tn = sum(1 for label, pred in zip(labels, preds) if label == 0 and pred == 0)
    fn = sum(1 for label, pred in zip(labels, preds) if label == 1 and pred == 0)
    return {
        "threshold": threshold,
        "precision": precision_score(labels, preds, zero_division=0),
        "recall": recall_score(labels, preds, zero_division=0),
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "predicted_positive_rate": sum(preds) / len(preds),
        "predicted_positive_count": sum(preds),
        "true_positive_count": tp,
        "false_positive_count": fp,
        "true_negative_count": tn,
        "false_negative_count": fn,
    }


def _prediction_rows(
    model_name: str,
    fold: Fold,
    test: pd.DataFrame,
    shock_prob: Sequence[float],
    opportunity_prob: Sequence[Optional[float]],
    shock_threshold: float,
    opportunity_threshold: Optional[float],
) -> List[dict]:
    rows: List[dict] = []
    for position, (_, row) in enumerate(test.iterrows()):
        p_shock = float(shock_prob[position])
        p_opportunity = opportunity_prob[position]
        p_recovery = (float(p_opportunity) * (1.0 - p_shock)) if p_opportunity is not None and not pd.isna(p_opportunity) else None
        if p_shock >= shock_threshold:
            state = "shock_guard"
        elif opportunity_threshold is not None and p_opportunity is not None and not pd.isna(p_opportunity) and p_opportunity >= opportunity_threshold:
            state = "recovery_candidate"
        else:
            state = "neutral_or_follow_ema"
        rows.append(
            {
                "model": model_name,
                "fold": fold.fold,
                "date": row["date"],
                "time": int(row["time"]),
                "shock_label": int(row["shock_label"]),
                "opportunity_label": int(row["opportunity_label"]),
                "p_shock": p_shock,
                "p_opportunity": p_opportunity,
                "p_recovery": p_recovery,
                "threshold_shock": shock_threshold,
                "threshold_opportunity": opportunity_threshold,
                "final_ml_state": state,
            }
        )
    return rows


def _feature_importance_rows(model_name: str, task: str, fold: Fold, model: object, feature_columns: List[str]) -> List[dict]:
    estimator = model
    if hasattr(model, "named_steps"):
        estimator = model.named_steps.get("model", model)

    values = None
    if hasattr(estimator, "feature_importances_"):
        values = list(estimator.feature_importances_)
    elif hasattr(estimator, "coef_"):
        coef = estimator.coef_
        values = list(abs(coef).mean(axis=0))
    if values is None:
        return []

    total = sum(float(value) for value in values)
    if total > 0:
        values = [float(value) / total for value in values]
    return [
        {
            "task": task,
            "model": model_name,
            "fold": fold.fold,
            "feature": feature,
            "importance": float(value),
        }
        for feature, value in zip(feature_columns, values)
    ]


def _safe_pr_auc(y_true: Sequence[int], probabilities: Sequence[float]) -> Optional[float]:
    if len(set(int(value) for value in y_true)) < 2:
        return None
    return float(average_precision_score(y_true, probabilities))


def _safe_roc_auc(y_true: Sequence[int], probabilities: Sequence[float]) -> Optional[float]:
    if len(set(int(value) for value in y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, probabilities))


def _mean(rows: List[dict], key: str) -> Optional[float]:
    values = [row[key] for row in rows if row.get(key) is not None and not pd.isna(row.get(key))]
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)
