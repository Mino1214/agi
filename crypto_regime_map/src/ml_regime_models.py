"""Model comparison utilities for the offline ML regime PoC."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml_regime_labels import REGIME_LABELS


TARGET_LABELS = {"recovery", "uptrend"}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    factory: Callable[[], object]
    skip_reason: str = ""

    @property
    def available(self) -> bool:
        return not self.skip_reason


@dataclass(frozen=True)
class Fold:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_indices: List[int]
    test_indices: List[int]


@dataclass(frozen=True)
class WalkForwardResult:
    metrics: List[dict]
    predictions: List[dict]
    confusion_matrix: List[dict]
    feature_importance: List[dict]
    skipped_models: List[dict]
    folds: List[Fold]


def make_model_specs(random_state: int = 42) -> List[ModelSpec]:
    specs = [
        ModelSpec(
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
        ),
        ModelSpec(
            name="Random Forest",
            factory=lambda: RandomForestClassifier(
                n_estimators=350,
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
            ModelSpec(
                name="LightGBM",
                factory=lambda: LGBMClassifier(
                    objective="multiclass",
                    n_estimators=240,
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
        specs.append(ModelSpec(name="LightGBM", factory=lambda: None, skip_reason=f"unavailable: {exc}"))

    return specs


def build_walk_forward_folds(
    frame: pd.DataFrame,
    folds: int = 5,
    min_train_size: int = 730,
    test_size: int = 180,
) -> List[Fold]:
    if folds <= 0:
        raise ValueError("folds must be positive")
    if min_train_size <= 0 or test_size <= 0:
        raise ValueError("min_train_size and test_size must be positive")

    ordered = frame.sort_values("time").reset_index(drop=True)
    row_count = len(ordered)
    if row_count <= min_train_size:
        return []

    max_test_size = max(30, (row_count - min_train_size) // folds)
    actual_test_size = min(test_size, max_test_size)
    actual_folds = min(folds, max(1, (row_count - min_train_size) // actual_test_size))
    first_test_start = row_count - actual_folds * actual_test_size
    first_test_start = max(min_train_size, first_test_start)

    out: List[Fold] = []
    test_start = first_test_start
    fold_number = 1
    while test_start < row_count and fold_number <= folds:
        test_end = min(row_count, test_start + actual_test_size)
        if test_end <= test_start:
            break
        train_indices = list(range(0, test_start))
        test_indices = list(range(test_start, test_end))
        train_dates = ordered.iloc[train_indices]["date"]
        test_dates = ordered.iloc[test_indices]["date"]
        out.append(
            Fold(
                fold=fold_number,
                train_start=str(train_dates.iloc[0]),
                train_end=str(train_dates.iloc[-1]),
                test_start=str(test_dates.iloc[0]),
                test_end=str(test_dates.iloc[-1]),
                train_indices=train_indices,
                test_indices=test_indices,
            )
        )
        fold_number += 1
        test_start = test_end

    return out


def run_walk_forward_validation(
    frame: pd.DataFrame,
    feature_columns: List[str],
    label_column: str = "label",
    model_specs: Optional[List[ModelSpec]] = None,
    folds: int = 5,
    min_train_size: int = 730,
    test_size: int = 180,
) -> WalkForwardResult:
    required = ["time", "date", label_column] + feature_columns
    missing_columns = [column for column in required if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"frame is missing columns: {missing_columns}")

    dataset = frame[required].dropna(subset=[label_column] + feature_columns)
    dataset = dataset.sort_values("time").reset_index(drop=True)
    fold_defs = build_walk_forward_folds(dataset, folds=folds, min_train_size=min_train_size, test_size=test_size)
    specs = model_specs or make_model_specs()

    metrics: List[dict] = []
    predictions: List[dict] = []
    confusion_rows: List[dict] = []
    importance_rows: List[dict] = []
    skipped_models: List[dict] = [
        {"model": spec.name, "reason": spec.skip_reason}
        for spec in specs
        if not spec.available
    ]

    for fold in fold_defs:
        train = dataset.iloc[fold.train_indices]
        test = dataset.iloc[fold.test_indices]
        x_train = train[feature_columns]
        y_train = train[label_column].astype(str)
        x_test = test[feature_columns]
        y_test = test[label_column].astype(str)

        if y_train.nunique() < 2:
            skipped_models.extend(
                {"model": spec.name, "fold": fold.fold, "reason": "train fold has fewer than two labels"}
                for spec in specs
                if spec.available
            )
            continue

        for spec in specs:
            if not spec.available:
                continue
            model = spec.factory()
            try:
                model.fit(x_train, y_train)
                y_pred = pd.Series(model.predict(x_test), index=test.index, dtype="object")
                probabilities = _predict_probabilities(model, x_test)
            except Exception as exc:
                skipped_models.append({"model": spec.name, "fold": fold.fold, "reason": str(exc)})
                continue

            metrics.append(_metrics_row(spec.name, fold, y_test, y_pred))
            predictions.extend(_prediction_rows(spec.name, fold, test, y_test, y_pred, probabilities))
            confusion_rows.extend(_confusion_rows(spec.name, fold, y_test, y_pred))
            importance_rows.extend(_feature_importance_rows(spec.name, fold, model, feature_columns))

    return WalkForwardResult(
        metrics=metrics,
        predictions=predictions,
        confusion_matrix=confusion_rows,
        feature_importance=importance_rows,
        skipped_models=skipped_models,
        folds=fold_defs,
    )


def summarize_metrics(metrics: Iterable[dict]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in metrics:
        grouped[row["model"]].append(row)

    summary: List[dict] = []
    for model, rows in grouped.items():
        summary.append(
            {
                "model": model,
                "folds": len(rows),
                "accuracy": _mean(rows, "accuracy"),
                "balanced_accuracy": _mean(rows, "balanced_accuracy"),
                "macro_f1": _mean(rows, "macro_f1"),
                "recovery_uptrend_precision": _mean(rows, "recovery_uptrend_precision"),
                "target_precision_baseline": _mean(rows, "target_precision_baseline"),
                "shock_recall": _mean(rows, "shock_recall"),
                "shock_count": sum(int(row["shock_count"]) for row in rows),
            }
        )
    return sorted(summary, key=lambda row: (row["macro_f1"] or 0.0, row["balanced_accuracy"] or 0.0), reverse=True)


def aggregate_feature_importance(rows: Iterable[dict], top_n: int = 20) -> List[dict]:
    grouped: Dict[tuple, List[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["model"], row["feature"])].append(float(row["importance"]))

    aggregated = [
        {
            "model": model,
            "feature": feature,
            "importance": sum(values) / len(values),
        }
        for (model, feature), values in grouped.items()
    ]
    aggregated.sort(key=lambda row: (row["model"], -row["importance"], row["feature"]))

    out: List[dict] = []
    by_model: Dict[str, int] = defaultdict(int)
    for row in aggregated:
        if by_model[row["model"]] >= top_n:
            continue
        by_model[row["model"]] += 1
        out.append({**row, "rank": by_model[row["model"]]})
    return out


def _metrics_row(model_name: str, fold: Fold, y_true: pd.Series, y_pred: pd.Series) -> dict:
    y_true_list = list(y_true)
    y_pred_list = list(y_pred)
    target_precision = _combined_precision(y_true_list, y_pred_list, TARGET_LABELS)
    shock_recall = _recall_for_label(y_true_list, y_pred_list, "shock")
    target_baseline = sum(1 for value in y_true_list if value in TARGET_LABELS) / len(y_true_list) if y_true_list else 0.0
    return {
        "model": model_name,
        "fold": fold.fold,
        "train_start": fold.train_start,
        "train_end": fold.train_end,
        "test_start": fold.test_start,
        "test_end": fold.test_end,
        "train_rows": len(fold.train_indices),
        "test_rows": len(fold.test_indices),
        "accuracy": accuracy_score(y_true_list, y_pred_list),
        "balanced_accuracy": balanced_accuracy_score(y_true_list, y_pred_list),
        "macro_f1": f1_score(y_true_list, y_pred_list, labels=REGIME_LABELS, average="macro", zero_division=0),
        "recovery_uptrend_precision": target_precision,
        "target_precision_baseline": target_baseline,
        "shock_recall": shock_recall,
        "shock_count": sum(1 for value in y_true_list if value == "shock"),
    }


def _prediction_rows(
    model_name: str,
    fold: Fold,
    test: pd.DataFrame,
    y_true: pd.Series,
    y_pred: pd.Series,
    probabilities: Dict[str, List[float]],
) -> List[dict]:
    out: List[dict] = []
    for position, (_, row) in enumerate(test.iterrows()):
        predicted = str(y_pred.iloc[position])
        result = {
            "model": model_name,
            "fold": fold.fold,
            "date": row["date"],
            "time": int(row["time"]),
            "actual": str(y_true.iloc[position]),
            "predicted": predicted,
            "predicted_probability": probabilities.get(predicted, [None] * len(test))[position],
        }
        for label in REGIME_LABELS:
            result[f"prob_{label}"] = probabilities.get(label, [None] * len(test))[position]
        out.append(result)
    return out


def _predict_probabilities(model: object, x_test: pd.DataFrame) -> Dict[str, List[float]]:
    if not hasattr(model, "predict_proba"):
        return {}
    probabilities = model.predict_proba(x_test)
    classes = list(getattr(model, "classes_", []))
    return {
        str(label): [float(value) for value in probabilities[:, index]]
        for index, label in enumerate(classes)
    }


def _confusion_rows(model_name: str, fold: Fold, y_true: pd.Series, y_pred: pd.Series) -> List[dict]:
    counts = Counter(zip(y_true.astype(str), y_pred.astype(str)))
    return [
        {
            "model": model_name,
            "fold": fold.fold,
            "actual": actual,
            "predicted": predicted,
            "count": count,
        }
        for (actual, predicted), count in sorted(counts.items())
    ]


def _feature_importance_rows(model_name: str, fold: Fold, model: object, feature_columns: List[str]) -> List[dict]:
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
            "model": model_name,
            "fold": fold.fold,
            "feature": feature,
            "importance": float(value),
        }
        for feature, value in zip(feature_columns, values)
    ]


def _combined_precision(y_true: List[str], y_pred: List[str], positive_labels: set[str]) -> Optional[float]:
    predicted_positive = [index for index, value in enumerate(y_pred) if value in positive_labels]
    if not predicted_positive:
        return None
    true_positive = sum(1 for index in predicted_positive if y_true[index] in positive_labels)
    return true_positive / len(predicted_positive)


def _recall_for_label(y_true: List[str], y_pred: List[str], label: str) -> Optional[float]:
    actual = [index for index, value in enumerate(y_true) if value == label]
    if not actual:
        return None
    hits = sum(1 for index in actual if y_pred[index] == label)
    return hits / len(actual)


def _mean(rows: List[dict], key: str) -> Optional[float]:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)
