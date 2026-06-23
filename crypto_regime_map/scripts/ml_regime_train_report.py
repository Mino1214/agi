"""Offline ML regime PoC report.

This script reads local raw caches only and writes research artifacts under
reports/research. It is intentionally not connected to the paper engine.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ml_regime_features import build_feature_frame, load_ohlcv_cache, read_json_cache  # noqa: E402
from ml_regime_labels import REGIME_LABELS, add_forward_labels, label_distribution  # noqa: E402
from ml_regime_models import (  # noqa: E402
    aggregate_feature_importance,
    make_model_specs,
    run_walk_forward_validation,
    summarize_metrics,
)
from regime import build_payload_from_raw  # noqa: E402


DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
OPTIONAL_PRICE_CANDIDATES = {
    "BTCDOM": ["BTCDOMUSDT_1d.json", "BTC_D_1d.json", "BTC.D_1d.json", "BTC_DOMINANCE_1d.json"],
    "TOTAL": ["TOTAL_1d.json", "TOTALUSDT_1d.json"],
    "TOTAL2": ["TOTAL2_1d.json", "TOTAL2USDT_1d.json"],
    "TOTAL3": ["TOTAL3_1d.json", "TOTAL3USDT_1d.json"],
}
OPEN_INTEREST_CANDIDATES = [
    "BTCUSDT_futures_open_interest.json",
    "BTCUSDT_open_interest.json",
    "BTCUSDT_futures_open_interest_hist.json",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "research"))
    parser.add_argument("--horizon-days", type=int, default=14)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--min-train-size", type=int, default=730)
    parser.add_argument("--test-size", type=int, default=180)
    args = parser.parse_args()

    result = generate_ml_regime_report(
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        horizon_days=args.horizon_days,
        folds=args.folds,
        min_train_size=args.min_train_size,
        test_size=args.test_size,
    )
    print(result["report_path"])


def generate_ml_regime_report(
    raw_dir: Path,
    output_dir: Path,
    horizon_days: int = 14,
    folds: int = 5,
    min_train_size: int = 730,
    test_size: int = 180,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = load_ohlcv_cache(raw_dir, DEFAULT_SYMBOLS)
    funding_rows = read_json_cache(raw_dir / "BTCUSDT_futures_funding_rate.json")
    optional_ohlcv, optional_missing_files = load_optional_ohlcv(raw_dir)
    open_interest_rows, open_interest_missing = load_first_existing_json(raw_dir, OPEN_INTEREST_CANDIDATES)

    feature_result = build_feature_frame(
        raw_ohlcv=raw,
        funding_rows=funding_rows,
        optional_ohlcv=optional_ohlcv,
        optional_open_interest_rows=open_interest_rows,
    )
    labeled = add_forward_labels(feature_result.frame, horizon_days=horizon_days)
    feature_columns = feature_result.used_features
    dataset = labeled.dropna(subset=["label"] + feature_columns).sort_values("time").reset_index(drop=True)

    model_result = run_walk_forward_validation(
        dataset,
        feature_columns=feature_columns,
        model_specs=make_model_specs(),
        folds=folds,
        min_train_size=min_train_size,
        test_size=test_size,
    )
    metric_summary = summarize_metrics(model_result.metrics)
    feature_importance = aggregate_feature_importance(model_result.feature_importance)
    ema_by_date = build_ema_regime_by_date(raw)
    predictions = add_ema_regime_to_predictions(model_result.predictions, ema_by_date)

    paths = {
        "predictions": output_dir / "ml_regime_predictions.csv",
        "feature_importance": output_dir / "ml_regime_feature_importance.csv",
        "metrics": output_dir / "ml_regime_walk_forward_metrics.csv",
        "confusion": output_dir / "ml_regime_confusion_matrix.csv",
        "report": output_dir / "ml_regime_poc_report.md",
    }
    write_csv(paths["predictions"], predictions)
    write_csv(paths["feature_importance"], feature_importance)
    write_csv(paths["metrics"], model_result.metrics)
    write_csv(paths["confusion"], model_result.confusion_matrix)

    missing_features = list(dict.fromkeys(feature_result.missing_features + optional_missing_files + open_interest_missing))
    report = build_report(
        labeled=labeled,
        dataset=dataset,
        feature_columns=feature_columns,
        missing_features=missing_features,
        metric_summary=metric_summary,
        fold_metrics=model_result.metrics,
        feature_importance=feature_importance,
        skipped_models=model_result.skipped_models,
        predictions=predictions,
        horizon_days=horizon_days,
    )
    paths["report"].write_text(report, encoding="utf-8")
    return {"report_path": paths["report"], "paths": paths, "metrics": metric_summary}


def load_optional_ohlcv(raw_dir: Path) -> tuple[Dict[str, List[dict]], List[str]]:
    loaded: Dict[str, List[dict]] = {}
    missing: List[str] = []
    for key, candidates in OPTIONAL_PRICE_CANDIDATES.items():
        rows, missing_rows = load_first_existing_json(raw_dir, candidates)
        if rows:
            loaded[key] = rows
        else:
            missing.append(f"{key} cache missing ({', '.join(candidates)})")
    return loaded, missing


def load_first_existing_json(raw_dir: Path, candidates: Iterable[str]) -> tuple[List[dict], List[str]]:
    for name in candidates:
        path = raw_dir / name
        if path.exists():
            return read_json_cache(path), []
    return [], [f"cache missing ({', '.join(candidates)})"]


def build_ema_regime_by_date(raw: Mapping[str, List[dict]]) -> Dict[str, str]:
    try:
        payload = build_payload_from_raw(dict(raw), interval="1d", start="2018-01-01", symbols=list(raw.keys()))
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for point in payload.get("points", []):
        date = datetime.fromtimestamp(int(point["time"]), tz=timezone.utc).strftime("%Y-%m-%d")
        out[date] = point.get("stable_regime") or point.get("regime") or ""
    return out


def add_ema_regime_to_predictions(predictions: List[dict], ema_by_date: Mapping[str, str]) -> List[dict]:
    return [
        {
            **row,
            "ema_regime": ema_by_date.get(str(row["date"]), ""),
            "ml_ema_mismatch": bool(ema_by_date.get(str(row["date"])) and ema_by_date.get(str(row["date"])) != row["predicted"]),
        }
        for row in predictions
    ]


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    pd.DataFrame(rows).to_csv(path, index=False)


def build_report(
    labeled: pd.DataFrame,
    dataset: pd.DataFrame,
    feature_columns: List[str],
    missing_features: List[str],
    metric_summary: List[dict],
    fold_metrics: List[dict],
    feature_importance: List[dict],
    skipped_models: List[dict],
    predictions: List[dict],
    horizon_days: int,
) -> str:
    best = metric_summary[0] if metric_summary else {}
    verdict, verdict_reasons = classify_verdict(best, missing_features, fold_metrics)
    distribution = label_distribution(dataset["label"])
    data_start = str(dataset["date"].iloc[0]) if not dataset.empty else "n/a"
    data_end = str(dataset["date"].iloc[-1]) if not dataset.empty else "n/a"

    lines = [
        "# ML Regime PoC Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "- Scope: offline research/report only; paper engine and live order logic untouched.",
        "- Default runtime state: ML Regime OFF.",
        f"- Label horizon: {horizon_days} days.",
        f"- Usable data period: {data_start} to {data_end}.",
        f"- Usable rows after warmup/label drop: {len(dataset)}.",
        "",
        "## Verdict",
        "",
        f"- Status: {verdict}",
    ]
    lines.extend(f"- {reason}" for reason in verdict_reasons)
    lines.extend(
        [
            "",
            "## Features",
            "",
            f"- Used feature count: {len(feature_columns)}",
        ]
    )
    lines.extend(f"- {feature}" for feature in feature_columns)
    lines.extend(["", "## Missing Features", ""])
    if missing_features:
        lines.extend(f"- {feature}" for feature in missing_features)
    else:
        lines.append("- none")

    lines.extend(["", "## Label Distribution", "", "| Label | Count | Share |", "|---|---:|---:|"])
    for row in distribution:
        lines.append(f"| {row['label']} | {row['count']} | {row['share']:.2%} |")

    lines.extend(["", "## Model Performance", "", "| Model | Folds | Accuracy | Balanced Acc | Macro F1 | Recovery/Uptrend Precision | Baseline | Shock Recall |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in metric_summary:
        lines.append(
            "| {model} | {folds} | {accuracy} | {balanced_accuracy} | {macro_f1} | {target_precision} | {baseline} | {shock_recall} |".format(
                model=row["model"],
                folds=row["folds"],
                accuracy=_fmt_pct(row["accuracy"]),
                balanced_accuracy=_fmt_pct(row["balanced_accuracy"]),
                macro_f1=_fmt_pct(row["macro_f1"]),
                target_precision=_fmt_pct(row["recovery_uptrend_precision"]),
                baseline=_fmt_pct(row["target_precision_baseline"]),
                shock_recall=_fmt_pct(row["shock_recall"]),
            )
        )

    lines.extend(["", "## Walk-Forward Folds", "", "| Model | Fold | Train | Test | Macro F1 | Recovery/Uptrend Precision | Shock Recall |", "|---|---:|---|---|---:|---:|---:|"])
    for row in fold_metrics:
        lines.append(
            "| {model} | {fold} | {train_start} to {train_end} | {test_start} to {test_end} | {macro_f1} | {precision} | {shock_recall} |".format(
                model=row["model"],
                fold=row["fold"],
                train_start=row["train_start"],
                train_end=row["train_end"],
                test_start=row["test_start"],
                test_end=row["test_end"],
                macro_f1=_fmt_pct(row["macro_f1"]),
                precision=_fmt_pct(row["recovery_uptrend_precision"]),
                shock_recall=_fmt_pct(row["shock_recall"]),
            )
        )

    lines.extend(["", "## Feature Importance", "", "| Model | Rank | Feature | Importance |", "|---|---:|---|---:|"])
    for row in feature_importance[:60]:
        lines.append(f"| {row['model']} | {row['rank']} | {row['feature']} | {row['importance']:.4f} |")

    lines.extend(["", "## EMA vs ML Mismatch Examples", ""])
    mismatch_rows = select_mismatch_examples(predictions, best.get("model"))
    if mismatch_rows:
        lines.extend(["| Date | Model | ML Regime | EMA Regime | Actual Label | Probability |", "|---|---|---|---|---|---:|"])
        for row in mismatch_rows:
            lines.append(
                f"| {row['date']} | {row['model']} | {row['predicted']} | {row['ema_regime']} | {row['actual']} | {_fmt_pct(row.get('predicted_probability'))} |"
            )
    else:
        lines.append("- No mismatches found in prediction rows with EMA regime coverage.")

    lines.extend(["", "## Lookahead And Leakage Checks", ""])
    lines.extend(
        [
            "- Features use pct_change, rolling, and EMA calculations based on current or prior rows only.",
            "- Funding features are shifted by one daily row before joining.",
            "- Labels use future returns and future low drawdown only after feature generation.",
            "- Walk-forward uses expanding train windows and later test windows; shuffle is not used.",
            "- Paper engine, live execution, state files, and order generation code were not imported or changed.",
        ]
    )

    lines.extend(["", "## Skipped Models", ""])
    if skipped_models:
        lines.extend(f"- {json.dumps(row, ensure_ascii=False)}" for row in skipped_models)
    else:
        lines.append("- none")

    lines.extend(["", "## Next Steps", ""])
    lines.extend(
        [
            "- Tighten label thresholds and test 7d vs 14d horizon side by side.",
            "- Add verified open interest, dominance, and TOTAL/TOTAL2/TOTAL3 caches before making model decisions.",
            "- Keep ML output as a research-only report until shock recall and recovery/uptrend precision are stable across folds.",
            "- If promoted later, add an explicit feature flag and paper-only shadow logging before any execution integration.",
        ]
    )
    return "\n".join(lines) + "\n"


def classify_verdict(best: Mapping[str, object], missing_features: List[str], fold_metrics: List[dict]) -> tuple[str, List[str]]:
    if not best:
        return "FAIL", ["No model produced walk-forward metrics."]

    precision = _as_float(best.get("recovery_uptrend_precision"))
    baseline = _as_float(best.get("target_precision_baseline"))
    shock_recall = _as_float(best.get("shock_recall"))
    macro_f1 = _as_float(best.get("macro_f1"))
    reasons = [
        f"Best model: {best.get('model')}.",
        f"Recovery/uptrend precision delta vs baseline: {_fmt_pct(None if precision is None or baseline is None else precision - baseline)}.",
        f"Shock recall: {_fmt_pct(shock_recall)}.",
    ]

    if precision is None or baseline is None or shock_recall is None:
        return "FAIL", reasons + ["A required precision/recall objective is undefined."]
    if precision <= baseline or shock_recall < 0.30:
        return "FAIL", reasons + ["Core objective is not above baseline or shock recall is too low."]
    if len(missing_features) >= 5:
        return "WATCH", reasons + ["Several optional macro/derivatives features are missing."]
    if precision < baseline + 0.08 or shock_recall < 0.50 or (macro_f1 is not None and macro_f1 < 0.30):
        return "WATCH", reasons + ["Signal exists, but margin is not yet strong enough for PASS."]
    if _fold_concentration_risk(best.get("model"), fold_metrics):
        return "WATCH", reasons + ["Performance is concentrated in too few folds."]
    return "PASS", reasons + ["Objectives clear the initial PoC thresholds without obvious leakage."]


def select_mismatch_examples(predictions: List[dict], model: Optional[str], limit: int = 12) -> List[dict]:
    rows = [
        row
        for row in predictions
        if row.get("ema_regime") and row.get("ml_ema_mismatch") and (model is None or row.get("model") == model)
    ]
    rows.sort(key=lambda row: (row["date"], row["model"]))
    if len(rows) <= limit:
        return rows
    step = max(1, len(rows) // limit)
    return rows[::step][:limit]


def _fold_concentration_risk(model: object, fold_metrics: List[dict]) -> bool:
    rows = [row for row in fold_metrics if row.get("model") == model and row.get("macro_f1") is not None]
    if len(rows) < 3:
        return True
    values = sorted(float(row["macro_f1"]) for row in rows)
    return values[-1] > 2.5 * max(values[0], 0.01)


def _fmt_pct(value: object) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"{number:.2%}"


def _as_float(value: object) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


if __name__ == "__main__":
    main()
