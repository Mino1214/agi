"""Daily OOS/Paper report for Alpha Long Engine v1.2 No Hedge.

The report is read-only with respect to strategy state. It reads paper ledgers
and health snapshots, then writes summary artifacts for operations review.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402


STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2"
REPORT_PATH = ROOT / "reports" / "daily_oos_report.md"
SUMMARY_NAME = "daily_oos_summary.csv"
SUMMARY_PATH = STATE_DIR / SUMMARY_NAME

STRATEGY_NAME = "Alpha Long Engine v1.2 No Hedge"
STRATEGY_LOCK_TIME = "2026-06-21 14:13 UTC"
PAPER_START_TIME = "2026-06-21 14:13 UTC"
OOS_START_TIME = "2026-06-21 14:13 UTC"
OOS_START_TS = int(datetime(2026, 6, 21, 14, 13, tzinfo=timezone.utc).timestamp())

SUMMARY_FIELDS = [
    "date",
    "health_status",
    "last_loop_run_at",
    "last_data_update_at",
    "current_regime",
    "current_action_bias",
    "signal_count",
    "entry_candidate_count",
    "order_created_count",
    "order_blocked_count",
    "block_reduce_risk",
    "block_shock",
    "block_alpha_score_below_min",
    "block_liquidation_buffer",
    "block_top20_failed",
    "block_data_missing",
    "block_other",
    "normal_reduce_risk_block",
    "position_count",
    "unrealized_pnl",
    "realized_pnl",
    "funding_fee",
    "recent_7d_trade_count",
    "recent_30d_trade_count",
    "recent_30d_mdd_pct",
    "health_warning_critical_reasons",
    "trade_sample_count",
    "performance_judgement",
    "strategy_lock_time",
    "paper_start_time",
    "oos_start_time",
    "generated_at",
]

BLOCK_FIELD_BY_CATEGORY = {
    "reduce_risk": "block_reduce_risk",
    "shock": "block_shock",
    "alpha_score_below_min": "block_alpha_score_below_min",
    "liquidation_buffer": "block_liquidation_buffer",
    "top20_failed": "block_top20_failed",
    "data_missing": "block_data_missing",
    "other": "block_other",
}


@dataclass
class ReportResult:
    today: dict
    cumulative: dict
    daily_rows: List[dict]
    report_text: str
    report_path: Path
    summary_path: Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Alpha Long v1.2 daily OOS/Paper report")
    parser.add_argument("--state-dir", default=str(STATE_DIR))
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--summary-path", default=str(SUMMARY_PATH))
    parser.add_argument("--now-ts", type=int, default=0)
    args = parser.parse_args()

    result = generate_daily_oos_report(
        state_dir=Path(args.state_dir),
        report_path=Path(args.report_path),
        summary_path=Path(args.summary_path),
        now_ts=args.now_ts or None,
    )
    print(result.report_text)


def generate_daily_oos_report(
    state_dir: Path = STATE_DIR,
    report_path: Path = REPORT_PATH,
    summary_path: Path = SUMMARY_PATH,
    now_ts: Optional[int] = None,
) -> ReportResult:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    state = load_inputs(state_dir)
    daily_rows = build_daily_rows(state, now_ts)
    cumulative = build_cumulative_summary(state, daily_rows, now_ts)
    today_key = utc_date(now_ts)
    today = next((row for row in daily_rows if row["date"] == today_key), daily_rows[-1])
    report_text = build_markdown(today, cumulative, daily_rows, now_ts)

    write_summary_csv(summary_path, daily_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    return ReportResult(today, cumulative, daily_rows, report_text, report_path, summary_path)


def load_inputs(state_dir: Path) -> dict:
    paper.ensure_state_files(state_dir)
    return {
        "signals": paper.read_csv_rows(state_dir / paper.STATE_FILES["signals"][0]),
        "orders": paper.read_csv_rows(state_dir / paper.STATE_FILES["orders"][0]),
        "trades": paper.read_csv_rows(state_dir / paper.STATE_FILES["trades"][0]),
        "positions": paper.read_csv_rows(state_dir / paper.STATE_FILES["positions"][0]),
        "equity": paper.read_csv_rows(state_dir / paper.STATE_FILES["equity"][0]),
        "health_rows": read_csv_rows(state_dir / "paper_health.csv"),
        "health_state": read_json(state_dir / paper.HEALTH_STATE_NAME),
    }


def build_daily_rows(state: dict, now_ts: int) -> List[dict]:
    rows = []
    start_date = datetime.fromtimestamp(OOS_START_TS, timezone.utc).date()
    end_date = datetime.fromtimestamp(now_ts, timezone.utc).date()
    current = start_date
    while current <= end_date:
        rows.append(build_day_row(state, current.isoformat(), now_ts))
        current += timedelta(days=1)
    return rows


def build_day_row(state: dict, day: str, now_ts: int) -> dict:
    start_ts, end_ts = day_bounds(day)
    start_ts = max(start_ts, OOS_START_TS)
    signals = rows_in_range(state["signals"], "signal_time", start_ts, end_ts)
    orders = rows_in_range(state["orders"], "created_time", start_ts, end_ts)
    trades = rows_in_range(state["trades"], "timestamp", start_ts, end_ts)
    equity_rows = rows_in_range(state["equity"], "timestamp", start_ts, end_ts)
    health_rows = rows_in_range(state["health_rows"], "timestamp", start_ts, end_ts)

    latest_equity = latest_row(equity_rows) or latest_row(rows_before(state["equity"], "timestamp", end_ts)) or {}
    latest_health_row = latest_row(health_rows) or latest_row(rows_before(state["health_rows"], "timestamp", end_ts)) or {}
    health_state = state["health_state"]
    health_status = latest_health_row.get("status") or health_state.get("status") or "unknown"
    block_counts = count_blocks(signals, orders, health_rows)
    trade_sample_count = count_closed_trades(trades)
    realized_pnl = realized_pnl_sum(trades)
    funding_fee = funding_fee_sum(trades)
    warning_critical = health_reason_text(health_state)
    generated_at = ts_label(now_ts)

    row = {
        "date": day,
        "health_status": health_status,
        "last_loop_run_at": latest_health_row.get("last_run_at") or ts_label(to_int(latest_equity.get("timestamp"), 0)),
        "last_data_update_at": latest_health_row.get("last_data_update_at") or "",
        "current_regime": latest_equity.get("current_regime") or "",
        "current_action_bias": latest_equity.get("current_action_bias") or "",
        "signal_count": len(signals),
        "entry_candidate_count": sum(1 for row in signals if is_entry_candidate(row)),
        "order_created_count": len(orders),
        "order_blocked_count": sum(block_counts.values()),
        "normal_reduce_risk_block": "yes" if block_counts["reduce_risk"] else "no",
        "position_count": latest_equity.get("open_positions") or len(state["positions"]),
        "unrealized_pnl": format_float(to_float(latest_equity.get("open_unrealized"), 0.0)),
        "realized_pnl": format_float(realized_pnl),
        "funding_fee": format_float(funding_fee),
        "recent_7d_trade_count": latest_health_row.get("recent_7d_trade_count") or count_recent_closed_trades(state["trades"], now_ts, 7),
        "recent_30d_trade_count": latest_health_row.get("recent_30d_trade_count") or count_recent_closed_trades(state["trades"], now_ts, 30),
        "recent_30d_mdd_pct": latest_health_row.get("recent_30d_mdd_pct")
        or format_float(recent_mdd_pct(state["equity"], now_ts, 30)),
        "health_warning_critical_reasons": warning_critical,
        "trade_sample_count": trade_sample_count,
        "performance_judgement": performance_judgement(count_closed_trades(rows_after(state["trades"], "timestamp", OOS_START_TS))),
        "strategy_lock_time": STRATEGY_LOCK_TIME,
        "paper_start_time": PAPER_START_TIME,
        "oos_start_time": OOS_START_TIME,
        "generated_at": generated_at,
    }
    for category, field in BLOCK_FIELD_BY_CATEGORY.items():
        row[field] = block_counts[category]
    return {field: csv_value(row.get(field, "")) for field in SUMMARY_FIELDS}


def build_cumulative_summary(state: dict, daily_rows: List[dict], now_ts: int) -> dict:
    oos_signals = rows_after(state["signals"], "signal_time", OOS_START_TS)
    oos_orders = rows_after(state["orders"], "created_time", OOS_START_TS)
    oos_trades = rows_after(state["trades"], "timestamp", OOS_START_TS)
    oos_health = rows_after(state["health_rows"], "timestamp", OOS_START_TS)
    latest_equity = latest_row(rows_after(state["equity"], "timestamp", OOS_START_TS)) or latest_row(state["equity"]) or {}
    block_counts = Counter()
    for row in daily_rows:
        for category, field in BLOCK_FIELD_BY_CATEGORY.items():
            block_counts[category] += to_int(row.get(field), 0)
    trade_sample_count = count_closed_trades(oos_trades)
    return {
        "oos_days": len(daily_rows),
        "signal_count": len(oos_signals),
        "entry_candidate_count": sum(1 for row in oos_signals if is_entry_candidate(row)),
        "order_created_count": len(oos_orders),
        "order_blocked_count": sum(block_counts.values()),
        "block_counts": block_counts,
        "position_count": latest_equity.get("open_positions") or len(state["positions"]),
        "unrealized_pnl": format_float(to_float(latest_equity.get("open_unrealized"), 0.0)),
        "realized_pnl": format_float(realized_pnl_sum(oos_trades)),
        "funding_fee": format_float(funding_fee_sum(oos_trades)),
        "trade_sample_count": trade_sample_count,
        "performance_judgement": performance_judgement(trade_sample_count),
        "health_rows": len(oos_health),
        "generated_at": ts_label(now_ts),
    }


def count_blocks(signals: List[dict], orders: List[dict], health_rows: List[dict]) -> Counter:
    counts: Counter = Counter()
    for signal in signals:
        if is_entry_candidate(signal):
            continue
        counts[block_category(signal_block_reason(signal), signal)] += 1

    for order in orders:
        status = str(order.get("status", "")).lower()
        reason = str(order.get("reason", ""))
        if status == "rejected" or reason in {"missing_1h_execution_data", "applied_leverage_liquidation_buffer"}:
            counts[block_category(reason, order)] += 1

    seen_runtime_blocks = set()
    for row in health_rows:
        if str(row.get("can_enter", "")).lower() not in {"false", "0", "no"}:
            continue
        reason = row.get("pause_reason", "")
        if not reason:
            continue
        key = (row.get("last_run_at") or row.get("timestamp"), reason)
        if key in seen_runtime_blocks:
            continue
        seen_runtime_blocks.add(key)
        counts[block_category(reason, row)] += 1
    return counts


def signal_block_reason(row: dict) -> str:
    reason = str(row.get("rejection_reason") or row.get("entry_block_reason") or "")
    if reason:
        return reason
    if str(row.get("top_20_passed", "")).lower() == "false":
        return "alpha_score_not_top_20pct"
    if str(row.get("trade_action_bias", "")).lower() in {"reduce_risk", "shock", "no_new_entry"}:
        return str(row.get("trade_action_bias", ""))
    return "not_entry_candidate"


def block_category(reason: str, row: Optional[dict] = None) -> str:
    lowered = str(reason or "").lower()
    row = row or {}
    action_bias = str(row.get("trade_action_bias") or row.get("pause_reason") or "").lower()
    regime = str(row.get("trade_regime") or "").lower()
    if "reduce_risk" in lowered or lowered == "defensive_no_entry" or action_bias == "reduce_risk":
        return "reduce_risk"
    if "shock" in lowered or action_bias == "shock" or regime == "shock":
        return "shock"
    if lowered == "alpha_score_below_min":
        return "alpha_score_below_min"
    if "liquidation" in lowered:
        return "liquidation_buffer"
    if lowered in {"alpha_score_not_top_20pct", "top20_failed"}:
        return "top20_failed"
    if "data_missing" in lowered or "missing_1h" in lowered:
        return "data_missing"
    return "other"


def is_entry_candidate(row: dict) -> bool:
    selected = str(row.get("selected", "")).lower() == "true"
    return selected and not row.get("rejection_reason") and not row.get("entry_block_reason")


def build_markdown(today: dict, cumulative: dict, daily_rows: List[dict], now_ts: int) -> str:
    block_counts = cumulative["block_counts"]
    today_normal_block = today.get("normal_reduce_risk_block") == "yes"
    lines = [
        "# Alpha Long v1.2 Daily OOS/Paper Report",
        "",
        f"- generated_at: {ts_label(now_ts)}",
        f"- strategy: {STRATEGY_NAME}",
        f"- strategy_lock_time: {STRATEGY_LOCK_TIME}",
        f"- paper_start_time: {PAPER_START_TIME}",
        f"- oos_start_time: {OOS_START_TIME}",
        "",
        "## 오늘 요약",
        "",
        markdown_table(
            [
                ("date", today["date"]),
                ("health_status", today["health_status"]),
                ("last_loop_run_at", today["last_loop_run_at"]),
                ("last_data_update_at", today["last_data_update_at"]),
                ("current_regime/action_bias", f"{today['current_regime']} / {today['current_action_bias']}"),
                ("signal_count", today["signal_count"]),
                ("entry_candidate_count", today["entry_candidate_count"]),
                ("order_created_count", today["order_created_count"]),
                ("order_blocked_count", today["order_blocked_count"]),
                ("position_count", today["position_count"]),
                ("unrealized_pnl", today["unrealized_pnl"]),
                ("realized_pnl", today["realized_pnl"]),
                ("funding_fee", today["funding_fee"]),
                ("recent_7d_trade_count", today["recent_7d_trade_count"]),
                ("recent_30d_trade_count", today["recent_30d_trade_count"]),
                ("recent_30d_mdd_pct", today["recent_30d_mdd_pct"]),
            ]
        ),
        "",
        "## 오늘 차단 사유",
        "",
        markdown_table(
            [
                ("reduce_risk", normal_block_label(today["block_reduce_risk"], today_normal_block)),
                ("shock", today["block_shock"]),
                ("alpha_score 부족", today["block_alpha_score_below_min"]),
                ("liquidation buffer 실패", today["block_liquidation_buffer"]),
                ("top20 미통과", today["block_top20_failed"]),
                ("데이터 부족", today["block_data_missing"]),
                ("기타", today["block_other"]),
            ]
        ),
        "",
        "## 누적 OOS 요약",
        "",
        markdown_table(
            [
                ("oos_days", cumulative["oos_days"]),
                ("signal_count", cumulative["signal_count"]),
                ("entry_candidate_count", cumulative["entry_candidate_count"]),
                ("order_created_count", cumulative["order_created_count"]),
                ("order_blocked_count", cumulative["order_blocked_count"]),
                ("position_count", cumulative["position_count"]),
                ("unrealized_pnl", cumulative["unrealized_pnl"]),
                ("realized_pnl", cumulative["realized_pnl"]),
                ("funding_fee", cumulative["funding_fee"]),
                ("health_snapshot_count", cumulative["health_rows"]),
            ]
        ),
        "",
        "## 누적 차단 사유",
        "",
        markdown_table(
            [
                ("reduce_risk", normal_block_label(block_counts["reduce_risk"], block_counts["reduce_risk"] > 0)),
                ("shock", block_counts["shock"]),
                ("alpha_score 부족", block_counts["alpha_score_below_min"]),
                ("liquidation buffer 실패", block_counts["liquidation_buffer"]),
                ("top20 미통과", block_counts["top20_failed"]),
                ("데이터 부족", block_counts["data_missing"]),
                ("기타", block_counts["other"]),
            ]
        ),
        "",
        "## 성과 판단",
        "",
        f"- current_trade_sample_count: {cumulative['trade_sample_count']}",
        f"- performance_judgement: {cumulative['performance_judgement']}",
        "",
        "## Health Warning/Critical 사유",
        "",
        today["health_warning_critical_reasons"] or "-",
        "",
        "## Daily Rows",
        "",
        markdown_daily_rows(daily_rows),
        "",
    ]
    return "\n".join(lines)


def normal_block_label(value: object, is_normal: bool) -> str:
    suffix = " (정상 차단)" if is_normal and to_int(value, 0) > 0 else ""
    return f"{value}{suffix}"


def markdown_table(rows: Iterable[tuple]) -> str:
    lines = ["| item | value |", "| --- | --- |"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def markdown_daily_rows(rows: List[dict]) -> str:
    fields = [
        "date",
        "health_status",
        "current_regime",
        "current_action_bias",
        "signal_count",
        "entry_candidate_count",
        "order_created_count",
        "order_blocked_count",
        "trade_sample_count",
    ]
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    return "\n".join(lines)


def write_summary_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in SUMMARY_FIELDS})


def performance_judgement(trade_sample_count: int) -> str:
    if trade_sample_count >= 30:
        return "성과 판단 가능"
    if trade_sample_count > 0:
        return "성과 판단 보류: closed trade sample 30건 미만"
    return "성과 판단 불가: closed trade sample 0건"


def health_reason_text(health_state: dict) -> str:
    reasons = []
    for key in ("critical_reasons", "warning_reasons"):
        for item in health_state.get(key) or []:
            status = item.get("status") or key.replace("_reasons", "")
            section = item.get("section") or ""
            code = item.get("code") or ""
            message = item.get("message") or ""
            reasons.append(f"{status}.{section}.{code}: {message}".strip(": "))
    return "; ".join(reasons)


def rows_in_range(rows: List[dict], field: str, start_ts: int, end_ts: int) -> List[dict]:
    return [row for row in rows if start_ts <= to_int(row.get(field), 0) < end_ts]


def rows_after(rows: List[dict], field: str, start_ts: int) -> List[dict]:
    return [row for row in rows if to_int(row.get(field), 0) >= start_ts]


def rows_before(rows: List[dict], field: str, end_ts: int) -> List[dict]:
    return [row for row in rows if 0 < to_int(row.get(field), 0) < end_ts]


def latest_row(rows: List[dict]) -> dict:
    return rows[-1] if rows else {}


def realized_pnl_sum(trades: List[dict]) -> float:
    total = 0.0
    for row in trades:
        event_type = row.get("event_type")
        if event_type == "exit":
            total += to_float(row.get("position_total_pnl"), to_float(row.get("pnl"), 0.0))
        elif event_type == "partial_exit":
            total += to_float(row.get("pnl"), 0.0)
    return total


def funding_fee_sum(trades: List[dict]) -> float:
    return sum(to_float(row.get("funding_pnl"), 0.0) for row in trades if row.get("event_type") == "funding_fee")


def count_closed_trades(trades: List[dict]) -> int:
    return sum(1 for row in trades if row.get("event_type") == "exit")


def count_recent_closed_trades(trades: List[dict], now_ts: int, days: int) -> int:
    start_ts = now_ts - days * 86400
    return count_closed_trades(rows_in_range(trades, "timestamp", start_ts, now_ts + 1))


def recent_mdd_pct(equity_rows: List[dict], now_ts: int, days: int) -> float:
    start_ts = now_ts - days * 86400
    rows = rows_in_range(equity_rows, "timestamp", start_ts, now_ts + 1)
    return min((to_float(row.get("drawdown_pct"), 0.0) for row in rows), default=0.0)


def day_bounds(day: str) -> tuple[int, int]:
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def utc_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


def ts_label(timestamp: int) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def to_int(value, default: int = 0) -> int:
    if value in {"", None}:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default: float = 0.0) -> float:
    if value in {"", None}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_float(value: float) -> str:
    return f"{value:.6f}"


def csv_value(value) -> str:
    if value is None:
        return ""
    return str(value)


if __name__ == "__main__":
    main()
