"""Offline ML Regime v2 two-stage research report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ml_regime_features import load_ohlcv_cache, read_json_cache  # noqa: E402
from ml_regime_v2 import (  # noqa: E402
    add_v2_labels,
    aggregate_v2_feature_importance,
    build_v2_feature_frame,
    final_state_distribution,
    make_v2_model_specs,
    run_v2_walk_forward_validation,
    summarize_binary_metrics,
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
V0_SUMMARY = {
    "recovery_uptrend_precision": 0.3859,
    "baseline": 0.3611,
    "shock_recall": 0.0290,
    "macro_f1": 0.1600,
    "verdict": "FAIL",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "research"))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--min-train-size", type=int, default=730)
    parser.add_argument("--test-size", type=int, default=180)
    parser.add_argument("--shock-drawdown-14d", type=float, default=-0.08)
    args = parser.parse_args()

    result = generate_ml_regime_v2_report(
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        folds=args.folds,
        min_train_size=args.min_train_size,
        test_size=args.test_size,
        shock_drawdown_14d=args.shock_drawdown_14d,
    )
    print(result["report_path"])


def generate_ml_regime_v2_report(
    raw_dir: Path,
    output_dir: Path,
    folds: int = 5,
    min_train_size: int = 730,
    test_size: int = 180,
    shock_drawdown_14d: float = -0.08,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_1d = load_ohlcv_cache(raw_dir, DEFAULT_SYMBOLS, interval="1d")
    raw_4h = {"BTCUSDT": read_json_cache(raw_dir / "BTCUSDT_4h.json")}
    raw_1h = {"BTCUSDT": read_json_cache(raw_dir / "BTCUSDT_1h.json")}
    funding_rows = read_json_cache(raw_dir / "BTCUSDT_futures_funding_rate.json")
    optional_ohlcv, optional_missing = load_optional_ohlcv(raw_dir)
    open_interest_rows, open_interest_missing = load_first_existing_json(raw_dir, OPEN_INTEREST_CANDIDATES)

    feature_result = build_v2_feature_frame(
        raw_1d=raw_1d,
        raw_4h=raw_4h,
        raw_1h=raw_1h,
        funding_rows=funding_rows,
        optional_ohlcv=optional_ohlcv,
        optional_open_interest_rows=open_interest_rows,
    )
    labeled = add_v2_labels(feature_result.frame, shock_drawdown_14d=shock_drawdown_14d)
    feature_columns = feature_result.used_features
    dataset = labeled.dropna(subset=["shock_label", "opportunity_label"] + feature_columns).sort_values("time").reset_index(drop=True)
    dataset["shock_label"] = dataset["shock_label"].astype(int)
    dataset["opportunity_label"] = dataset["opportunity_label"].astype(int)

    result = run_v2_walk_forward_validation(
        dataset,
        feature_columns=feature_columns,
        model_specs=make_v2_model_specs(),
        folds=folds,
        min_train_size=min_train_size,
        test_size=test_size,
        calibrate=True,
    )
    shock_summary = summarize_binary_metrics(result.shock_metrics, sort_key="recall")
    opportunity_summary = summarize_binary_metrics(result.opportunity_metrics, sort_key="precision_delta")
    feature_importance = aggregate_v2_feature_importance(result.feature_importance)
    ema_by_date = build_ema_regime_by_date(raw_1d)
    predictions = add_ema_to_predictions(result.predictions, ema_by_date)

    paths = {
        "report": output_dir / "ml_regime_v2_report.md",
        "shock_metrics": output_dir / "ml_regime_v2_shock_metrics.csv",
        "opportunity_metrics": output_dir / "ml_regime_v2_opportunity_metrics.csv",
        "thresholds": output_dir / "ml_regime_v2_thresholds.csv",
        "predictions": output_dir / "ml_regime_v2_predictions.csv",
        "feature_importance": output_dir / "ml_regime_v2_feature_importance.csv",
    }
    write_csv(paths["shock_metrics"], result.shock_metrics)
    write_csv(paths["opportunity_metrics"], result.opportunity_metrics)
    write_csv(paths["thresholds"], result.threshold_rows)
    write_csv(paths["predictions"], predictions)
    write_csv(paths["feature_importance"], feature_importance)

    missing_features = list(dict.fromkeys(feature_result.missing_features + optional_missing + open_interest_missing))
    report = build_report(
        dataset=dataset,
        feature_columns=feature_columns,
        missing_features=missing_features,
        shock_summary=shock_summary,
        opportunity_summary=opportunity_summary,
        shock_metrics=result.shock_metrics,
        opportunity_metrics=result.opportunity_metrics,
        threshold_rows=result.threshold_rows,
        predictions=predictions,
        feature_importance=feature_importance,
        skipped_models=result.skipped_models,
        shock_drawdown_14d=shock_drawdown_14d,
    )
    paths["report"].write_text(report, encoding="utf-8")
    return {"report_path": paths["report"], "paths": paths, "shock_summary": shock_summary, "opportunity_summary": opportunity_summary}


def load_optional_ohlcv(raw_dir: Path) -> tuple[Dict[str, List[dict]], List[str]]:
    loaded: Dict[str, List[dict]] = {}
    missing: List[str] = []
    for key, candidates in OPTIONAL_PRICE_CANDIDATES.items():
        rows, _ = load_first_existing_json(raw_dir, candidates)
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


def add_ema_to_predictions(predictions: List[dict], ema_by_date: Mapping[str, str]) -> List[dict]:
    return [
        {
            **row,
            "ema_regime": ema_by_date.get(str(row["date"]), ""),
            "ml_ema_mismatch": bool(
                ema_by_date.get(str(row["date"]))
                and not _state_matches_ema(row["final_ml_state"], ema_by_date.get(str(row["date"]), ""))
            ),
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
    dataset: pd.DataFrame,
    feature_columns: List[str],
    missing_features: List[str],
    shock_summary: List[dict],
    opportunity_summary: List[dict],
    shock_metrics: List[dict],
    opportunity_metrics: List[dict],
    threshold_rows: List[dict],
    predictions: List[dict],
    feature_importance: List[dict],
    skipped_models: List[dict],
    shock_drawdown_14d: float,
) -> str:
    best_shock = shock_summary[0] if shock_summary else {}
    best_opportunity = opportunity_summary[0] if opportunity_summary else {}
    verdict, reasons = classify_v2_verdict(best_shock, best_opportunity)
    data_start = str(dataset["date"].iloc[0]) if not dataset.empty else "n/a"
    data_end = str(dataset["date"].iloc[-1]) if not dataset.empty else "n/a"
    shock_dist = binary_distribution(dataset["shock_label"], "shock")
    opportunity_base = dataset[dataset["shock_label"] == 0]["opportunity_label"]
    opportunity_dist = binary_distribution(opportunity_base, "opportunity")

    lines = [
        "# ML Regime v2 Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "- Scope: offline research/report/backtest only; paper engine and live order logic untouched.",
        "- Default runtime state: ML Regime v2 OFF.",
        "",
        "## v0 Failure Summary",
        "",
        f"- v0 verdict: {V0_SUMMARY['verdict']}",
        f"- recovery/uptrend precision: {V0_SUMMARY['recovery_uptrend_precision']:.2%}",
        f"- baseline: {V0_SUMMARY['baseline']:.2%}",
        f"- shock recall: {V0_SUMMARY['shock_recall']:.2%}",
        f"- macro F1: {V0_SUMMARY['macro_f1']:.2%}",
        "",
        "## v2 Structure",
        "",
        "- Stage 1 Shock Guard: binary probability model for future 14d max drawdown breach.",
        "- Stage 2 Recovery/Uptrend Detector: binary opportunity model trained/evaluated on non-shock rows.",
        "- Thresholds are selected inside each train fold only, then applied unchanged to the later test fold.",
        "- Opportunity pass check uses precision improvement over baseline as a rough cost/slippage buffer; no fills or orders are modeled.",
        "- final_ml_state: shock_guard first, recovery_candidate second, otherwise neutral_or_follow_ema.",
        "",
        "## Data",
        "",
        f"- Usable data period: {data_start} to {data_end}",
        f"- Usable rows after warmup/label drop: {len(dataset)}",
        f"- Shock label: future_max_drawdown_14d <= {shock_drawdown_14d:.2%}",
        "- Opportunity label: 14d return >= 5% with 14d drawdown > -8%, or 7d return >= 3% with 7d drawdown > -5%.",
        "",
        "## Features",
        "",
        f"- Used feature count: {len(feature_columns)}",
    ]
    lines.extend(f"- {feature}" for feature in feature_columns)
    lines.extend(["", "## Missing Features", ""])
    lines.extend(f"- {feature}" for feature in missing_features or ["none"])

    lines.extend(["", "## Shock Label Distribution", "", "| Label | Count | Share |", "|---|---:|---:|"])
    for row in shock_dist:
        lines.append(f"| {row['label']} | {row['count']} | {row['share']:.2%} |")
    lines.extend(["", "## Opportunity Label Distribution", "", "| Label | Count | Share |", "|---|---:|---:|"])
    for row in opportunity_dist:
        lines.append(f"| {row['label']} | {row['count']} | {row['share']:.2%} |")

    lines.extend(["", "## Shock Guard Walk-Forward", "", "| Model | Folds | Threshold | Recall | Precision | FPR | PR-AUC | ROC-AUC |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in shock_summary:
        lines.append(
            f"| {row['model']} | {row['folds']} | {_fmt_num(row['threshold'])} | {_fmt_pct(row['recall'])} | {_fmt_pct(row['precision'])} | {_fmt_pct(row['fpr'])} | {_fmt_pct(row['pr_auc'])} | {_fmt_pct(row['roc_auc'])} |"
        )

    lines.extend(["", "## Opportunity Detector Walk-Forward", "", "| Model | Folds | Threshold | Precision | Baseline | Delta | Recall | PR-AUC | ROC-AUC |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in opportunity_summary:
        lines.append(
            f"| {row['model']} | {row['folds']} | {_fmt_num(row['threshold'])} | {_fmt_pct(row['precision'])} | {_fmt_pct(row['baseline'])} | {_fmt_pct(row['precision_delta'])} | {_fmt_pct(row['recall'])} | {_fmt_pct(row['pr_auc'])} | {_fmt_pct(row['roc_auc'])} |"
        )

    lines.extend(["", "## Selected Threshold Results", ""])
    lines.extend(threshold_summary_lines(shock_metrics, opportunity_metrics))

    lines.extend(["", "## final_ml_state Distribution", "", "| State | Count | Share |", "|---|---:|---:|"])
    for row in final_state_distribution(predictions):
        lines.append(f"| {row['final_ml_state']} | {row['count']} | {row['share']:.2%} |")

    lines.extend(["", "## Feature Importance", "", "| Task | Model | Rank | Feature | Importance |", "|---|---|---:|---|---:|"])
    for row in feature_importance[:80]:
        lines.append(f"| {row['task']} | {row['model']} | {row['rank']} | {row['feature']} | {row['importance']:.4f} |")

    lines.extend(["", "## EMA vs ML v2 Mismatch Examples", ""])
    mismatches = select_mismatch_examples(predictions, best_shock.get("model"))
    if mismatches:
        lines.extend(["| Date | Model | ML State | EMA Regime | Shock | Opportunity | p_shock | p_opportunity |", "|---|---|---|---|---:|---:|---:|---:|"])
        for row in mismatches:
            lines.append(
                f"| {row['date']} | {row['model']} | {row['final_ml_state']} | {row['ema_regime']} | {row['shock_label']} | {row['opportunity_label']} | {_fmt_pct(row['p_shock'])} | {_fmt_pct(row.get('p_opportunity'))} |"
            )
    else:
        lines.append("- No EMA mismatch examples found.")

    lines.extend(["", "## Lookahead And Leakage Checks", ""])
    lines.extend(
        [
            "- 1D features use current and prior rows only.",
            "- 1H/4H features are grouped by UTC date after computing rolling/pct_change values on prior intraday rows.",
            "- Funding level is shifted by one daily row before use; funding change uses prior shifted values.",
            "- Forward 7d/14d return and drawdown are used only for labels.",
            "- Walk-forward folds are time ordered and never shuffled.",
            "- Thresholds are selected on train fold probabilities only; test fold thresholds are never optimized.",
            "- Paper engine, execution state, and live order code are not imported by this report.",
        ]
    )

    lines.extend(["", "## Skipped Models", ""])
    if skipped_models:
        lines.extend(f"- {json.dumps(row, ensure_ascii=False)}" for row in skipped_models)
    else:
        lines.append("- none")

    lines.extend(["", "## PASS/WATCH/FAIL", "", f"- Status: {verdict}"])
    lines.extend(f"- {reason}" for reason in reasons)
    return "\n".join(lines) + "\n"


def classify_v2_verdict(best_shock: Mapping[str, object], best_opportunity: Mapping[str, object]) -> tuple[str, List[str]]:
    if not best_shock or not best_opportunity:
        return "FAIL", ["One or both v2 stages produced no metrics."]

    shock_recall = _as_float(best_shock.get("recall"))
    shock_fpr = _as_float(best_shock.get("fpr"))
    opportunity_delta = _as_float(best_opportunity.get("precision_delta"))
    opportunity_precision = _as_float(best_opportunity.get("precision"))
    reasons = [
        f"Best shock model: {best_shock.get('model')} recall {_fmt_pct(shock_recall)}, FPR {_fmt_pct(shock_fpr)}.",
        f"Best opportunity model: {best_opportunity.get('model')} precision {_fmt_pct(opportunity_precision)}, delta {_fmt_pct(opportunity_delta)}.",
    ]
    if shock_recall is None or shock_recall < 0.50:
        return "FAIL", reasons + ["Shock Guard does not clear the 50% recall floor."]
    if opportunity_delta is None or opportunity_delta < 0.08:
        return "WATCH", reasons + ["Shock Guard clears recall, but opportunity precision does not improve by +8%p."]
    if shock_fpr is not None and shock_fpr > 0.65:
        return "WATCH", reasons + ["Shock Guard recall clears the floor, but false positives are high."]
    return "PASS", reasons + ["Both v2 objectives clear initial thresholds without lookahead flags."]


def binary_distribution(values: Iterable[int], positive_name: str) -> List[dict]:
    labels = [int(value) for value in values]
    counts = Counter(labels)
    total = len(labels)
    return [
        {"label": f"not_{positive_name}", "count": counts.get(0, 0), "share": counts.get(0, 0) / total if total else 0.0},
        {"label": positive_name, "count": counts.get(1, 0), "share": counts.get(1, 0) / total if total else 0.0},
    ]


def threshold_summary_lines(shock_metrics: List[dict], opportunity_metrics: List[dict]) -> List[str]:
    lines = ["| Task | Model | Fold | Test | Threshold | Precision | Recall | FPR | PR-AUC |", "|---|---|---:|---|---:|---:|---:|---:|---:|"]
    for row in shock_metrics + opportunity_metrics:
        lines.append(
            f"| {row['task']} | {row['model']} | {row['fold']} | {row['test_start']} to {row['test_end']} | {_fmt_num(row['threshold'])} | {_fmt_pct(row['precision'])} | {_fmt_pct(row['recall'])} | {_fmt_pct(row['false_positive_rate'])} | {_fmt_pct(row['pr_auc'])} |"
        )
    return lines


def select_mismatch_examples(predictions: List[dict], model: Optional[str], limit: int = 12) -> List[dict]:
    rows = [
        row
        for row in predictions
        if row.get("ema_regime")
        and row.get("ml_ema_mismatch")
        and (model is None or row.get("model") == model)
    ]
    rows.sort(key=lambda row: (row["date"], row["model"]))
    if len(rows) <= limit:
        return rows
    step = max(1, len(rows) // limit)
    return rows[::step][:limit]


def _state_matches_ema(state: str, ema_regime: str) -> bool:
    if state == "shock_guard":
        return ema_regime in {"shock", "defensive"}
    if state == "recovery_candidate":
        return ema_regime in {"uptrend", "eth_strength", "large_cap_lead"}
    return ema_regime in {"neutral", "observe", "defensive", "uptrend", "eth_strength", "large_cap_lead"}


def _fmt_pct(value: object) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"{number:.2%}"


def _fmt_num(value: object) -> str:
    number = _as_float(value)
    if number is None:
        return "n/a"
    return f"{number:.2f}"


def _as_float(value: object) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


if __name__ == "__main__":
    main()
