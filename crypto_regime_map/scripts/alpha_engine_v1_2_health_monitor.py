"""Health monitor for the Alpha Engine v1.2 paper engine.

The monitor is paper-only. It reads CSV ledgers and cached OHLCV files,
records health snapshots/events, writes a markdown report, and controls only
the paper engine's new-entry pause state.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
SRC = ROOT / "src"
STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2"
RAW_DIR = ROOT / "data" / "raw"
REPORT_PATH = ROOT / "reports" / "alpha_engine_v1_2_health_report.md"
for path in (SCRIPT_DIR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

PAPER_FILES = {
    "positions": "paper_positions.csv",
    "orders": "paper_orders.csv",
    "trades": "paper_trades.csv",
    "equity": "paper_equity.csv",
    "signals": "paper_signals.csv",
}

HEALTH_CSV = "paper_health.csv"
HEALTH_EVENTS_CSV = "health_events.csv"
HEALTH_STATE_JSON = "health_state.json"
HEALTH_REPAIR_STATE_JSON = "health_repair_state.json"
ERROR_LOG_NAME = "paper_control_errors.jsonl"
STRATEGY_LOCK_NAME = "Alpha Long Engine v1.2 No Hedge"
STRATEGY_LOCK_VERSION = "v1.2-no-hedge"

UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "TONUSDT",
    "DOGEUSDT",
)
TRADING_UNIVERSE = tuple(symbol for symbol in UNIVERSE if symbol != "DOGEUSDT")
EXPECTED_SCAN_SYMBOLS = len(TRADING_UNIVERSE)
INTERVAL_SECONDS = {"1h": 3600, "4h": 4 * 3600, "1d": 24 * 3600}
VALID_LEVERAGE_STEPS = {1, 2, 3, 4}

STATUS_RANK = {"normal": 0, "warning": 1, "critical": 2, "paused": 3}
RANK_STATUS = {value: key for key, value in STATUS_RANK.items()}
BEGINNER_MESSAGES = {
    "normal": "정상입니다. 봇이 잘 작동 중입니다.",
    "warning": "주의가 필요합니다. 확인 후 계속 진행하세요.",
    "critical": "심각한 문제가 있습니다. 새 진입을 막는 것이 좋습니다.",
    "paused": "정지 상태입니다. 사람이 확인해야 합니다.",
}

HEALTH_FIELDS = [
    "timestamp",
    "date",
    "status",
    "can_enter",
    "pause_reason",
    "system_status",
    "data_status",
    "signal_status",
    "order_position_status",
    "risk_status",
    "performance_status",
    "frequency_status",
    "last_run_at",
    "last_data_update_at",
    "last_1h_candle_at",
    "last_4h_signal_at",
    "open_positions",
    "liquidation_risk_count",
    "recent_20_trade_pf",
    "recent_50_trade_pf",
    "recent_20_trade_win_rate_pct",
    "recent_50_trade_win_rate_pct",
    "recent_30d_return_pct",
    "recent_30d_mdd_pct",
    "recent_7d_trade_count",
    "recent_30d_trade_count",
    "issue_count",
    "paused_issue_count",
]

EVENT_FIELDS = [
    "event_id",
    "timestamp",
    "date",
    "status",
    "section",
    "code",
    "message",
    "details_json",
]


@dataclass
class Finding:
    section: str
    status: str
    code: str
    message: str
    details: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "section": self.section,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha Engine v1.2 paper health monitor")
    parser.add_argument("command", choices=["check", "report", "repair", "pause", "resume"])
    parser.add_argument("--state-dir", default=str(STATE_DIR))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    raw_dir = Path(args.raw_dir)
    report_path = Path(args.report_path)

    if args.command == "pause":
        try:
            state = manual_pause(state_dir, args.reason)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    if args.command == "resume":
        try:
            state = manual_resume(state_dir, args.reason)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    if args.command == "repair":
        result = repair_market_data_gaps(state_dir=state_dir, raw_dir=raw_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    result = run_check(state_dir=state_dir, raw_dir=raw_dir, report_path=report_path)
    if args.command == "report":
        print(str(report_path))
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_check(
    state_dir: Path = STATE_DIR,
    raw_dir: Path = RAW_DIR,
    report_path: Path = REPORT_PATH,
    now_ts: Optional[int] = None,
    write_outputs: bool = True,
) -> dict:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    state_dir = Path(state_dir)
    raw_dir = Path(raw_dir)
    report_path = Path(report_path)
    if write_outputs:
        ensure_output_files(state_dir)

    previous_state = load_health_state(state_dir)
    rows_by_file, csv_errors = load_paper_csvs(state_dir)
    findings: List[Finding] = []
    for error in csv_errors:
        add_finding(
            findings,
            "system",
            "critical",
            "csv_read_error",
            error["message"],
            filename=error.get("filename", ""),
        )

    position_symbols = {
        str(row.get("symbol", "")).upper()
        for row in open_position_rows(rows_by_file.get("positions", []))
        if row.get("symbol")
    }
    market = inspect_market_data(raw_dir, now_ts, findings, position_symbols=position_symbols)
    system = check_system_health(rows_by_file, market, state_dir, csv_errors, now_ts, findings)
    data = check_data_health(market, now_ts, findings)
    signals = check_signal_health(rows_by_file, market, now_ts, findings)
    order_position = check_order_position_health(rows_by_file, now_ts, findings)
    risk = check_risk_health(rows_by_file, now_ts, findings)
    performance = check_performance_health(rows_by_file, now_ts, findings)
    frequency = check_trade_frequency_health(rows_by_file, now_ts, findings)

    component_status = {
        "system": section_status(findings, "system"),
        "data": section_status(findings, "data"),
        "signal": section_status(findings, "signal"),
        "order_position": section_status(findings, "order_position"),
        "risk": section_status(findings, "risk"),
        "performance": section_status(findings, "performance"),
        "frequency": section_status(findings, "frequency"),
    }
    aggregate = worst_status(component_status.values())
    pause_findings = [finding for finding in findings if finding.status == "paused"]

    manual_paused = bool(previous_state.get("manual_pause")) and previous_state.get("status") == "paused"
    if manual_paused:
        status = "paused"
        pause_reason = previous_state.get("pause_reason", "manual pause")
    elif pause_findings:
        status = "paused"
        pause_reason = pause_findings[0].message
    else:
        status = aggregate
        pause_reason = ""

    can_enter = status != "paused"
    last_normal_run_at = previous_state.get("last_normal_run_at", "")
    if status == "normal":
        last_normal_run_at = format_dt(now_ts)

    metrics = {
        "open_positions": risk["open_positions"],
        "liquidation_risk_count": risk["liquidation_risk_count"],
        "recent_20_trade_pf": performance["recent_20_trade_pf"],
        "recent_50_trade_pf": performance["recent_50_trade_pf"],
        "recent_20_trade_win_rate_pct": performance["recent_20_trade_win_rate_pct"],
        "recent_50_trade_win_rate_pct": performance["recent_50_trade_win_rate_pct"],
        "recent_30d_return_pct": performance["recent_30d_return_pct"],
        "recent_30d_mdd_pct": performance["recent_30d_mdd_pct"],
        "recent_7d_trade_count": frequency["recent_7d_trade_count"],
        "recent_30d_trade_count": frequency["recent_30d_trade_count"],
        "daily_loss_pct": risk["daily_loss_pct"],
        "recent_7d_loss_pct": risk["recent_7d_loss_pct"],
        "total_portfolio_risk_pct": risk["total_portfolio_risk_pct"],
        "actual_slippage_avg_pct": performance["actual_slippage_avg_pct"],
        "funding_cost_to_pnl_pct": performance["funding_cost_to_pnl_pct"],
    }

    result = {
        "ok": True,
        "generated_at": format_dt(now_ts),
        "timestamp": now_ts,
        "status": status,
        "can_enter": can_enter,
        "new_entry_allowed": can_enter,
        "pause_reason": pause_reason,
        "beginner_message": BEGINNER_MESSAGES[status],
        "last_normal_run_at": last_normal_run_at,
        "component_status": component_status,
        "metrics": metrics,
        "system": system,
        "data": data,
        "signals": signals,
        "order_position": order_position,
        "risk": risk,
        "performance": performance,
        "trade_frequency": frequency,
        "findings": [finding.as_dict() for finding in findings],
        "files": {
            "paper_health": str(state_dir / HEALTH_CSV),
            "health_events": str(state_dir / HEALTH_EVENTS_CSV),
            "health_state": str(state_dir / HEALTH_STATE_JSON),
            "health_report": str(report_path),
        },
    }
    flow = build_flow(result, rows_by_file, previous_state)
    result["flow"] = flow
    result["can_enter"] = flow["new_entry_allowed"]
    result["new_entry_allowed"] = flow["new_entry_allowed"]
    result["pause_reason"] = pause_reason or flow["final_block_reason"]
    result["beginner_message"] = flow["beginner_message"]

    state = build_state(previous_state, result, now_ts)
    if write_outputs:
        write_health_state(state_dir, state)
        append_health_row(state_dir, result)
        append_findings(state_dir, findings, now_ts)
        if status == "paused" and previous_state.get("status") != "paused":
            append_event(
                state_dir,
                now_ts,
                "paused",
                "auto_pause",
                "auto_pause",
                pause_reason,
                {"source": "health_monitor"},
            )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_report(result), encoding="utf-8")

    return result


def build_state(previous_state: dict, result: dict, now_ts: int) -> dict:
    state = dict(previous_state)
    critical_reasons = readable_reasons(result, {"critical"})
    warning_reasons = readable_reasons(result, {"warning"})
    paused_reasons = readable_reasons(result, {"paused"})
    data_gap_summary = summarize_data_gaps(result.get("data", {}).get("data_gaps", []))
    state.update(
        {
            "status": result["status"],
            "status_label": result["status"],
            "can_enter": result["can_enter"],
            "new_entry_allowed": result["new_entry_allowed"],
            "pause_reason": result["pause_reason"],
            "final_block_reason": result.get("flow", {}).get("final_block_reason", ""),
            "beginner_message": result["beginner_message"],
            "last_check_at": result["generated_at"],
            "last_check_timestamp": now_ts,
            "last_normal_run_at": result["last_normal_run_at"],
            "component_status": result["component_status"],
            "metrics": result["metrics"],
            "resume_required": result["status"] == "paused",
            "status_reasons": readable_reasons(result, {"warning", "critical", "paused"}),
            "critical_reasons": critical_reasons,
            "warning_reasons": warning_reasons,
            "paused_reasons": paused_reasons,
            "human_summary": human_status_summary(result, data_gap_summary, critical_reasons, warning_reasons, paused_reasons),
            "data_gap_summary": data_gap_summary,
            "repairable_gap_count": data_gap_summary["repairable_count"],
            "unrepairable_gap_count": data_gap_summary["unrepairable_count"],
        }
    )
    apply_strategy_lock_metadata(state, now_ts)
    if result["status"] == "paused" and not state.get("manual_pause"):
        state["auto_paused_at"] = state.get("auto_paused_at") or result["generated_at"]
    if result["status"] != "paused":
        state["manual_pause"] = False
        state["auto_paused_at"] = ""
    return state


def apply_strategy_lock_metadata(state: dict, now_ts: int) -> None:
    existing_name = state.get("strategy_lock_name") or state.get("strategy_name")
    if existing_name and existing_name != STRATEGY_LOCK_NAME:
        state["oos_reset_required"] = True
        state["oos_reset_reason"] = f"strategy changed from {existing_name} to {STRATEGY_LOCK_NAME}"
    state["strategy_locked"] = True
    state["strategy_lock_name"] = STRATEGY_LOCK_NAME
    state["strategy_name"] = STRATEGY_LOCK_NAME
    state["strategy_lock_version"] = STRATEGY_LOCK_VERSION
    state["strategy_change_requires_oos_reset"] = True
    if not state.get("strategy_lock_timestamp"):
        state["strategy_lock_timestamp"] = now_ts
    if not state.get("strategy_lock_time"):
        state["strategy_lock_time"] = format_dt(state["strategy_lock_timestamp"])
    if not state.get("paper_start_timestamp"):
        state["paper_start_timestamp"] = now_ts
    if not state.get("paper_start_time"):
        state["paper_start_time"] = format_dt(state["paper_start_timestamp"])
    state["oos_start_timestamp"] = state.get("paper_start_timestamp")
    state["oos_start_time"] = state.get("paper_start_time")
    state["oos_classification_rule"] = "Only signals, orders, trades, and health snapshots at or after paper_start_time are OOS."
    state.setdefault("oos_reset_required", False)


def readable_reasons(result: dict, statuses: set) -> List[dict]:
    rows = []
    for finding in result.get("findings", []):
        if finding.get("status") not in statuses:
            continue
        rows.append(
            {
                "status": finding.get("status", ""),
                "section": finding.get("section", ""),
                "code": finding.get("code", ""),
                "message": finding.get("message", ""),
                "details": finding.get("details", {}),
            }
        )
    final_block = result.get("flow", {}).get("final_block_reason", "")
    if final_block and "paused" in statuses:
        rows.append(
            {
                "status": "paused",
                "section": "final_gate",
                "code": final_block,
                "message": f"신규 진입 최종 차단 사유: {final_block}",
                "details": {},
            }
        )
    return rows


def summarize_data_gaps(data_gaps: List[dict]) -> dict:
    failed = [row for row in data_gaps if row.get("status") == "fail"]
    trading_failed = [row for row in failed if row.get("affects_trading")]
    unrepairable = [row for row in failed if not row.get("repairable")]
    repairable = [row for row in failed if row.get("repairable")]
    return {
        "total_count": len(data_gaps),
        "failed_count": len(failed),
        "trading_failed_count": len(trading_failed),
        "repairable_count": len(repairable),
        "unrepairable_count": len(unrepairable),
        "affected_symbols": sorted({row.get("symbol", "") for row in trading_failed if row.get("symbol")}),
        "affected_timeframes": sorted({row.get("timeframe", "") for row in trading_failed if row.get("timeframe")}),
        "unrepairable": [
            {
                "symbol": row.get("symbol", ""),
                "timeframe": row.get("timeframe", ""),
                "gap_type": row.get("gap_type", ""),
                "failure_reason": row.get("failure_reason", ""),
            }
            for row in unrepairable[:20]
        ],
    }


def human_status_summary(
    result: dict,
    data_gap_summary: dict,
    critical_reasons: List[dict],
    warning_reasons: List[dict],
    paused_reasons: List[dict],
) -> str:
    status = result.get("status", "normal")
    if status == "critical" and critical_reasons:
        first = critical_reasons[0]
        return f"critical: {first['section']}.{first['code']} - {first['message']}"
    if status == "paused" and paused_reasons:
        first = paused_reasons[0]
        return f"paused: {first['section']}.{first['code']} - {first['message']}"
    if data_gap_summary["trading_failed_count"]:
        symbols = ", ".join(data_gap_summary["affected_symbols"]) or "unknown"
        timeframes = ", ".join(data_gap_summary["affected_timeframes"]) or "unknown"
        return f"{status}: trading data gaps remain in {symbols} {timeframes}"
    if status == "warning" and warning_reasons:
        first = warning_reasons[0]
        return f"warning: {first['section']}.{first['code']} - {first['message']}"
    return f"{status}: {BEGINNER_MESSAGES.get(status, '')}"


def check_system_health(
    rows_by_file: Dict[str, List[dict]],
    market: dict,
    state_dir: Path,
    csv_errors: List[dict],
    now_ts: int,
    findings: List[Finding],
) -> dict:
    latest_run_ts = latest_engine_timestamp(rows_by_file)
    latest_data_ts = market.get("latest_data_ts")
    latest_1h = market.get("latest_by_interval", {}).get("1h")
    latest_4h_signal = max_ts(rows_by_file.get("signals", []), ("signal_time", "fill_time"))
    api_errors = read_api_errors(state_dir, now_ts)

    if latest_run_ts is None:
        add_finding(findings, "system", "warning", "last_run_missing", "마지막 실행 시각을 찾을 수 없습니다.")
    else:
        age = now_ts - latest_run_ts
        if age >= 6 * 3600:
            add_finding(
                findings,
                "system",
                "critical",
                "last_run_critical_delay",
                "마지막 실행이 6시간 이상 지연됐습니다.",
                age_hours=round(age / 3600, 2),
            )
        elif age >= 3 * 3600:
            add_finding(
                findings,
                "system",
                "warning",
                "last_run_warning_delay",
                "마지막 실행이 3시간 이상 지연됐습니다.",
                age_hours=round(age / 3600, 2),
            )

    if latest_data_ts is None:
        add_finding(findings, "system", "critical", "data_update_missing", "마지막 데이터 업데이트 시각을 찾을 수 없습니다.")
    else:
        data_age = now_ts - latest_data_ts
        if data_age >= 6 * 3600:
            add_finding(
                findings,
                "system",
                "paused",
                "data_update_paused_delay",
                "데이터 업데이트가 6시간 이상 지연돼 신규 진입을 정지합니다.",
                age_hours=round(data_age / 3600, 2),
            )

    if len(api_errors) >= 5:
        add_finding(
            findings,
            "system",
            "critical",
            "api_errors_critical",
            "최근 24시간 API 오류가 5회 이상입니다.",
            count=len(api_errors),
        )
    elif api_errors:
        add_finding(
            findings,
            "system",
            "warning",
            "api_errors_warning",
            "최근 24시간 API 오류가 기록됐습니다.",
            count=len(api_errors),
        )

    return {
        "last_run_at": format_dt(latest_run_ts),
        "last_run_age_hours": age_hours(now_ts, latest_run_ts),
        "last_data_update_at": format_dt(latest_data_ts),
        "last_data_update_age_hours": age_hours(now_ts, latest_data_ts),
        "last_1h_candle_at": format_dt(latest_1h),
        "last_4h_signal_at": format_dt(latest_4h_signal),
        "loop_running": None,
        "loop_interrupted": latest_run_ts is not None and now_ts - latest_run_ts >= 3 * 3600,
        "api_error_count_24h": len(api_errors),
        "csv_error_count": len(csv_errors),
    }


def inspect_market_data(
    raw_dir: Path,
    now_ts: int,
    findings: List[Finding],
    position_symbols: Optional[set] = None,
) -> dict:
    latest_by_interval: Dict[str, int] = {}
    latest_file_mtime = None
    summaries = {}
    gap_details: List[dict] = []
    position_symbols = position_symbols or set()
    issue_counts = {"missing_files": 0, "duplicate_timestamps": 0, "reversed_timestamps": 0, "ohlc_invalid": 0, "missing_candles": 0}

    for interval, seconds in INTERVAL_SECONDS.items():
        interval_summary = {
            "symbols_checked": 0,
            "missing_files": [],
            "latest_candle_at": "",
            "missing_candle_count": 0,
            "duplicate_timestamp_count": 0,
            "reversed_timestamp_count": 0,
            "ohlc_issue_count": 0,
        }
        for symbol in UNIVERSE:
            path = candle_path(raw_dir, symbol, interval)
            if path is None:
                interval_summary["missing_files"].append(symbol)
                issue_counts["missing_files"] += 1
                affects_trading = symbol in TRADING_UNIVERSE and interval in {"1h", "4h"}
                gap_details.append(
                    data_gap_row(
                        symbol,
                        interval,
                        "active_symbol_gap" if affects_trading else "old_historical_gap",
                        0,
                        None,
                        None,
                        affects_trading,
                        False,
                        "fail" if affects_trading else "warning",
                        "missing candle file has no repair time range",
                    )
                )
                continue
            interval_summary["symbols_checked"] += 1
            latest_file_mtime = max(latest_file_mtime or 0, int(path.stat().st_mtime))
            rows = read_json_rows(path)
            if not rows:
                add_finding(
                    findings,
                    "data",
                    "critical",
                    "empty_candle_file",
                    f"{symbol} {interval} 캔들 파일이 비어 있습니다.",
                    path=str(path),
                )
                continue
            candle_result = inspect_candles(symbol, interval, rows, seconds, now_ts, position_symbols)
            gap_details.extend(candle_result["gap_details"])
            issue_counts["duplicate_timestamps"] += candle_result["duplicate_timestamp_count"]
            issue_counts["reversed_timestamps"] += candle_result["reversed_timestamp_count"]
            issue_counts["ohlc_invalid"] += candle_result["ohlc_issue_count"]
            issue_counts["missing_candles"] += candle_result["missing_candle_count"]
            interval_summary["missing_candle_count"] += candle_result["missing_candle_count"]
            interval_summary["duplicate_timestamp_count"] += candle_result["duplicate_timestamp_count"]
            interval_summary["reversed_timestamp_count"] += candle_result["reversed_timestamp_count"]
            interval_summary["ohlc_issue_count"] += candle_result["ohlc_issue_count"]

            latest_close = candle_result["latest_close_ts"]
            if latest_close is not None:
                latest_by_interval[interval] = max(latest_by_interval.get(interval, 0), latest_close)
                latest_gap = latest_gap_detail(symbol, interval, latest_close, seconds, now_ts)
                if latest_gap:
                    gap_details.append(latest_gap)
                    candle_result["gap_details"].append(latest_gap)

            if candle_result["duplicate_timestamp_count"]:
                add_finding(
                    findings,
                    "data",
                    "warning",
                    "duplicate_candle_timestamp",
                    f"{symbol} {interval} 캔들에 중복 timestamp가 있습니다.",
                    count=candle_result["duplicate_timestamp_count"],
                )
            if candle_result["reversed_timestamp_count"]:
                add_finding(
                    findings,
                    "data",
                    "critical",
                    "reversed_candle_timestamp",
                    f"{symbol} {interval} 캔들 timestamp가 역순입니다.",
                    count=candle_result["reversed_timestamp_count"],
                )
            if candle_result["ohlc_issue_count"]:
                add_finding(
                    findings,
                    "data",
                    "critical",
                    "ohlc_invalid",
                    f"{symbol} {interval} 캔들 OHLC 이상값이 있습니다.",
                    count=candle_result["ohlc_issue_count"],
                    examples=candle_result["ohlc_examples"],
                )
            if candle_result["missing_candle_count"]:
                blocking_gap = any(row.get("affects_trading") and row.get("status") == "fail" for row in candle_result["gap_details"])
                status = "critical" if blocking_gap else "warning"
                add_finding(
                    findings,
                    "data",
                    status,
                    "missing_candles",
                    f"{symbol} {interval} 캔들 누락이 감지됐습니다.",
                    missing_count=candle_result["missing_candle_count"],
                    max_gap_hours=round(candle_result["max_gap_seconds"] / 3600, 2),
                    gap_types=sorted({row["gap_type"] for row in candle_result["gap_details"]}),
                )
            blocking_latest_gaps = [
                row
                for row in candle_result["gap_details"]
                if row.get("gap_type") == "latest_incomplete_candle" and row.get("affects_trading") and row.get("status") == "fail"
            ]
            for gap in blocking_latest_gaps:
                add_finding(
                    findings,
                    "data",
                    "critical",
                    "latest_symbol_candle_gap",
                    f"{symbol} {interval} 최신 캔들이 누락돼 운영 데이터가 멈춰 있습니다.",
                    symbol=symbol,
                    timeframe=interval,
                    missing_count=gap.get("missing_count"),
                    start_time=gap.get("start_time"),
                    end_time=gap.get("end_time"),
                    repairable=gap.get("repairable"),
                )

        if interval_summary["missing_files"]:
            status = "critical" if interval_summary["symbols_checked"] == 0 else "warning"
            add_finding(
                findings,
                "data",
                status,
                f"missing_{interval}_candle_files",
                f"{interval.upper()} 캔들 파일 누락이 있습니다.",
                symbols=interval_summary["missing_files"],
            )
        latest_at = latest_by_interval.get(interval)
        interval_summary["latest_candle_at"] = format_dt(latest_at)
        interval_summary["latest_candle_age_hours"] = age_hours(now_ts, latest_at)
        summaries[interval] = interval_summary

    latest_data_ts = max(latest_by_interval.values()) if latest_by_interval else latest_file_mtime
    return {
        "raw_dir": str(raw_dir),
        "latest_data_ts": latest_data_ts,
        "latest_file_mtime": latest_file_mtime,
        "latest_by_interval": latest_by_interval,
        "summaries": summaries,
        "gap_details": gap_details,
        "issue_counts": issue_counts,
    }


def check_data_health(market: dict, now_ts: int, findings: List[Finding]) -> dict:
    latest_by_interval = market.get("latest_by_interval", {})
    for interval, warn_hours, critical_hours in (("1h", 3, 6), ("4h", 8, 16), ("1d", 48, 72)):
        latest_ts = latest_by_interval.get(interval)
        if latest_ts is None:
            continue
        age = now_ts - latest_ts
        if interval == "1h" and age >= critical_hours * 3600:
            add_finding(
                findings,
                "data",
                "paused",
                "latest_1h_candle_stale",
                "마지막 1H 캔들이 6시간 이상 오래돼 신규 진입을 정지합니다.",
                age_hours=round(age / 3600, 2),
            )
        elif age >= critical_hours * 3600:
            add_finding(
                findings,
                "data",
                "critical",
                f"latest_{interval}_candle_critical_stale",
                f"마지막 {interval.upper()} 캔들이 오래됐습니다.",
                age_hours=round(age / 3600, 2),
            )
        elif age >= warn_hours * 3600:
            add_finding(
                findings,
                "data",
                "warning",
                f"latest_{interval}_candle_warning_stale",
                f"마지막 {interval.upper()} 캔들 업데이트가 지연됐습니다.",
                age_hours=round(age / 3600, 2),
            )

    return {
        "latest_data_update_at": format_dt(market.get("latest_data_ts")),
        "latest_by_interval": {key: format_dt(value) for key, value in latest_by_interval.items()},
        "intervals": market.get("summaries", {}),
        "data_gaps": market.get("gap_details", []),
        "issue_counts": market.get("issue_counts", {}),
    }


def check_signal_health(rows_by_file: Dict[str, List[dict]], market: dict, now_ts: int, findings: List[Finding]) -> dict:
    signals = rows_by_file.get("signals", [])
    orders = rows_by_file.get("orders", [])
    latest_signal_time = max_ts(signals, ("signal_time", "fill_time"))
    latest_batch = latest_rows_by_timestamp(signals, "signal_time")
    latest_4h_close = market.get("latest_by_interval", {}).get("4h")
    if latest_4h_close and latest_4h_close > now_ts:
        latest_4h_close -= INTERVAL_SECONDS["4h"]

    if latest_4h_close and (latest_signal_time is None or latest_signal_time < latest_4h_close):
        delay = now_ts - latest_4h_close
        status = "critical" if delay >= 8 * 3600 else "warning"
        add_finding(
            findings,
            "signal",
            status,
            "missing_signal_after_4h_close",
            "마지막 4H 봉 마감 후 신호가 생성되지 않았습니다.",
            latest_4h_close=format_dt(latest_4h_close),
            latest_signal_time=format_dt(latest_signal_time),
        )

    doge_selected = [
        row
        for row in signals
        if str(row.get("symbol", "")).upper() == "DOGEUSDT" and truthy(row.get("selected"))
    ]
    if doge_selected:
        add_finding(
            findings,
            "signal",
            "critical",
            "doge_selected",
            "DOGEUSDT가 진입 후보로 선택됐습니다.",
            count=len(doge_selected),
        )
    elif any(str(row.get("symbol", "")).upper() == "DOGEUSDT" for row in latest_batch):
        add_finding(
            findings,
            "signal",
            "warning",
            "doge_scanned",
            "최신 신호 스캔에 DOGEUSDT가 포함됐습니다.",
        )

    scan_count = len(latest_batch)
    if scan_count and scan_count < EXPECTED_SCAN_SYMBOLS:
        add_finding(
            findings,
            "signal",
            "warning",
            "scan_symbol_count_low",
            "전체 스캔 심볼 수가 기대값보다 적습니다.",
            expected=EXPECTED_SCAN_SYMBOLS,
            actual=scan_count,
        )
    if latest_batch and not any("top_20_passed" in row for row in latest_batch):
        add_finding(
            findings,
            "signal",
            "warning",
            "top_20_filter_missing",
            "신호 CSV에서 alpha_score top 20% 필터 적용 여부를 확인할 수 없습니다.",
        )
    selected_not_top = [
        row
        for row in latest_batch
        if truthy(row.get("selected")) and not truthy(row.get("top_20_passed"))
    ]
    if selected_not_top:
        add_finding(
            findings,
            "signal",
            "critical",
            "selected_signal_not_top_20",
            "top 20% 필터를 통과하지 않은 신호가 선택됐습니다.",
            symbols=[row.get("symbol", "") for row in selected_not_top],
        )

    blocked_regime_selected = [
        row
        for row in latest_batch
        if truthy(row.get("selected")) and is_blocked_regime(row.get("trade_regime", ""), row.get("trade_action_bias", ""))
    ]
    if blocked_regime_selected:
        add_finding(
            findings,
            "signal",
            "critical",
            "signal_selected_in_blocked_regime",
            "reduce_risk/shock 상태에서 선택된 신호가 있습니다.",
            symbols=[row.get("symbol", "") for row in blocked_regime_selected],
        )

    order_by_signal = {row.get("signal_id", ""): row for row in orders if row.get("signal_id")}
    scan_results = []
    for row in latest_batch:
        order = order_by_signal.get(row.get("signal_id", ""), {})
        block_reason = order.get("reason") or row.get("entry_block_reason") or row.get("rejection_reason") or ""
        scan_results.append(
            {
                "signal_id": row.get("signal_id", ""),
                "symbol": row.get("symbol", ""),
                "alpha_score": number_or_none(row.get("alpha_score")),
                "rank": number_or_none(row.get("rank")),
                "universe_size": int_or_none(row.get("universe_size")),
                "selected": truthy(row.get("selected")),
                "top_20_passed": truthy(row.get("top_20_passed")),
                "trade_regime": row.get("trade_regime", ""),
                "trade_action_bias": row.get("trade_action_bias", ""),
                "block_reason": block_reason,
            }
        )

    entry_candidates = [row for row in scan_results if row["selected"] and not row["block_reason"]]
    top_passed = [row for row in scan_results if row["top_20_passed"]]
    return {
        "last_4h_signal_at": format_dt(latest_signal_time),
        "latest_scan_time": format_dt(max_ts(latest_batch, ("signal_time",))),
        "scan_count": scan_count,
        "expected_scan_count": EXPECTED_SCAN_SYMBOLS,
        "doge_excluded": not bool(doge_selected) and not any(row.get("symbol") == "DOGEUSDT" for row in scan_results),
        "top_20_filter_applied": any(row["top_20_passed"] for row in scan_results) if scan_results else False,
        "liquidation_buffer_applied": liquidation_buffer_is_recorded(rows_by_file),
        "blocked_regime_orders_blocked": not bool(blocked_regime_selected),
        "entry_candidates": entry_candidates,
        "top_20_candidates": top_passed,
        "scan_results": scan_results,
        "block_reasons": {row["symbol"]: row["block_reason"] for row in scan_results},
    }


def check_order_position_health(rows_by_file: Dict[str, List[dict]], now_ts: int, findings: List[Finding]) -> dict:
    positions = open_position_rows(rows_by_file.get("positions", []))
    orders = rows_by_file.get("orders", [])
    trades = rows_by_file.get("trades", [])
    equity = rows_by_file.get("equity", [])

    positions_by_symbol: Dict[str, List[dict]] = {}
    for row in positions:
        positions_by_symbol.setdefault(str(row.get("symbol", "")).upper(), []).append(row)
    duplicate_symbols = {symbol: rows for symbol, rows in positions_by_symbol.items() if symbol and len(rows) > 1}
    if duplicate_symbols:
        add_finding(
            findings,
            "order_position",
            "paused",
            "duplicate_open_positions",
            "동일 심볼 중복 포지션이 있어 신규 진입을 정지합니다.",
            symbols=sorted(duplicate_symbols),
        )

    position_ids = {row.get("position_id", "") for row in positions if row.get("position_id")}
    entry_position_ids = {
        row.get("position_id", "")
        for row in trades
        if row.get("event_type") == "entry" and row.get("position_id")
    }
    filled_order_position_ids = {
        row.get("position_id", "")
        for row in orders
        if row.get("status") == "filled" and row.get("position_id")
    }
    known_position_ids = position_ids | entry_position_ids | filled_order_position_ids

    positionless_exits = [
        row
        for row in trades
        if row.get("event_type") in {"exit", "partial_exit"} and row.get("position_id") not in known_position_ids
    ]
    if positionless_exits:
        add_finding(
            findings,
            "order_position",
            "critical",
            "positionless_exit_event",
            "포지션 없는 청산 이벤트가 있습니다.",
            count=len(positionless_exits),
        )

    funding_without_entry = [
        row
        for row in trades
        if row.get("event_type") == "funding_fee"
        and row.get("position_id") not in entry_position_ids
        and row.get("position_id") not in position_ids
    ]
    if funding_without_entry:
        add_finding(
            findings,
            "order_position",
            "critical",
            "funding_without_entry",
            "진입 없는 funding_fee 이벤트가 있습니다.",
            count=len(funding_without_entry),
        )

    entry_event_order_ids = {row.get("order_id", "") for row in trades if row.get("event_type") == "entry"}
    filled_without_position = [
        row
        for row in orders
        if row.get("status") == "filled"
        and row.get("order_id") not in entry_event_order_ids
        and row.get("position_id") not in position_ids
    ]
    if filled_without_position:
        add_finding(
            findings,
            "order_position",
            "critical",
            "filled_order_without_position",
            "주문 체결 후 포지션/진입 이벤트가 생성되지 않았습니다.",
            count=len(filled_without_position),
        )

    pending_stale = [
        row
        for row in orders
        if row.get("status") == "pending"
        and (now_ts - (parse_ts(row.get("created_time")) or now_ts)) >= 6 * 3600
    ]
    if pending_stale:
        add_finding(
            findings,
            "order_position",
            "warning",
            "stale_pending_orders",
            "오래된 pending 주문이 있습니다.",
            count=len(pending_stale),
        )

    if positions and not equity:
        add_finding(
            findings,
            "order_position",
            "critical",
            "position_without_equity",
            "포지션이 있는데 equity 기록이 없습니다.",
        )

    exited_position_ids = {
        row.get("position_id", "")
        for row in trades
        if row.get("event_type") == "exit" and row.get("position_id")
    }
    closed_still_open = sorted(position_ids & exited_position_ids)
    if closed_still_open:
        add_finding(
            findings,
            "order_position",
            "paused",
            "closed_position_still_open",
            "청산 후 포지션이 잔존해 신규 진입을 정지합니다.",
            position_ids=closed_still_open,
        )

    blocked_orders = [
        row
        for row in orders
        if row.get("status") not in {"rejected", "canceled", "cancelled", "expired"}
        and is_blocked_regime(row.get("trade_regime", ""), row.get("trade_action_bias", ""))
    ]
    if blocked_orders:
        add_finding(
            findings,
            "order_position",
            "paused",
            "order_created_in_blocked_regime",
            "reduce_risk/shock 상태에서 주문이 생성돼 신규 진입을 정지합니다.",
            count=len(blocked_orders),
        )

    return {
        "open_position_count": len(positions),
        "duplicate_position_symbols": sorted(duplicate_symbols),
        "positionless_exit_count": len(positionless_exits),
        "funding_without_entry_count": len(funding_without_entry),
        "filled_order_without_position_count": len(filled_without_position),
        "stale_pending_order_count": len(pending_stale),
        "closed_position_still_open_ids": closed_still_open,
        "blocked_regime_order_count": len(blocked_orders),
    }


def check_risk_health(rows_by_file: Dict[str, List[dict]], now_ts: int, findings: List[Finding]) -> dict:
    positions = open_position_rows(rows_by_file.get("positions", []))
    orders = rows_by_file.get("orders", [])
    equity = rows_by_file.get("equity", [])
    latest_equity = latest_equity_value(equity)
    open_positions = len(positions)

    if open_positions > 3:
        add_finding(
            findings,
            "risk",
            "critical",
            "max_positions_exceeded",
            "동시 보유 포지션이 최대 3개를 초과했습니다.",
            open_positions=open_positions,
        )

    invalid_leverage_rows = []
    for source, rows in (("positions", positions), ("orders", orders)):
        for row in rows:
            leverage = number_or_none(row.get("applied_leverage"))
            if leverage is None:
                continue
            if int(leverage) != leverage or int(leverage) not in VALID_LEVERAGE_STEPS:
                invalid_leverage_rows.append({"source": source, "id": row.get("position_id") or row.get("order_id"), "applied_leverage": leverage})
    if invalid_leverage_rows:
        add_finding(
            findings,
            "risk",
            "critical",
            "invalid_applied_leverage",
            "applied_leverage가 1/2/3/4 외 값입니다.",
            rows=invalid_leverage_rows[:10],
        )

    liquidation_risk_positions = [row for row in positions if has_liquidation_risk(row)]
    if liquidation_risk_positions:
        add_finding(
            findings,
            "risk",
            "paused",
            "liquidation_risk",
            "청산 위험 거래가 있어 신규 진입을 정지합니다.",
            symbols=[row.get("symbol", "") for row in liquidation_risk_positions],
        )

    symbol_risks = []
    total_risk = 0.0
    for row in positions:
        risk_amount = number_or_none(row.get("risk_amount")) or 0.0
        total_risk += risk_amount
        symbol_risks.append(
            {
                "symbol": row.get("symbol", ""),
                "risk_amount": risk_amount,
                "risk_pct": (risk_amount / latest_equity * 100) if latest_equity else None,
                "raw_leverage": number_or_none(row.get("raw_leverage")),
                "applied_leverage": number_or_none(row.get("applied_leverage")),
                "liquidation_buffer_pct": number_or_none(row.get("liquidation_buffer_pct")),
                "liquidation_risk": has_liquidation_risk(row),
            }
        )
    total_risk_pct = (total_risk / latest_equity * 100) if latest_equity else 0.0
    if total_risk_pct > 6.0:
        add_finding(
            findings,
            "risk",
            "warning",
            "portfolio_risk_high",
            "총 포트폴리오 리스크가 6%를 초과했습니다.",
            total_portfolio_risk_pct=round(total_risk_pct, 2),
        )

    recent_30d_mdd = rolling_mdd_pct(equity, now_ts, 30)
    if recent_30d_mdd is not None and recent_30d_mdd <= -10.0:
        add_finding(
            findings,
            "risk",
            "paused",
            "recent_30d_mdd_exceeded",
            "최근 30일 MDD가 -10%를 초과해 신규 진입을 정지합니다.",
            recent_30d_mdd_pct=round(recent_30d_mdd, 2),
        )

    return {
        "open_positions": open_positions,
        "max_positions": 3,
        "symbol_risks": symbol_risks,
        "total_portfolio_risk": total_risk,
        "total_portfolio_risk_pct": total_risk_pct,
        "liquidation_risk_count": len(liquidation_risk_positions),
        "daily_loss_pct": period_return_pct(equity, now_ts, 1),
        "recent_7d_loss_pct": period_return_pct(equity, now_ts, 7),
        "recent_30d_mdd_pct": recent_30d_mdd,
        "invalid_applied_leverage_count": len(invalid_leverage_rows),
    }


def check_performance_health(rows_by_file: Dict[str, List[dict]], now_ts: int, findings: List[Finding]) -> dict:
    trades = rows_by_file.get("trades", [])
    equity = rows_by_file.get("equity", [])
    signals = rows_by_file.get("signals", [])
    orders = rows_by_file.get("orders", [])
    closed = closed_trade_rows(trades)
    pnl_values = [trade_pnl(row) for row in closed]

    recent_20 = pnl_values[-20:]
    recent_50 = pnl_values[-50:]
    pf20 = profit_factor(recent_20)
    pf50 = profit_factor(recent_50)
    win20 = win_rate_pct(recent_20)
    win50 = win_rate_pct(recent_50)

    if len(recent_20) >= 20 and pf20 is not None and pf20 < 1.0:
        add_finding(
            findings,
            "performance",
            "warning",
            "recent_20_pf_below_one",
            "최근 20거래 PF가 1.0 미만입니다.",
            pf=round(pf20, 4),
        )
    if len(recent_50) >= 50 and pf50 is not None and pf50 < 1.0:
        add_finding(
            findings,
            "performance",
            "paused",
            "recent_50_pf_below_one",
            "최근 50거래 PF가 1.0 미만이라 신규 진입을 정지합니다.",
            pf=round(pf50, 4),
        )

    recent_30d_return = period_return_pct(equity, now_ts, 30)
    recent_30d_mdd = rolling_mdd_pct(equity, now_ts, 30)
    if recent_30d_mdd is not None and recent_30d_mdd <= -10.0:
        add_finding(
            findings,
            "performance",
            "paused",
            "performance_30d_mdd_exceeded",
            "최근 30일 MDD가 -10%를 초과해 신규 진입을 정지합니다.",
            recent_30d_mdd_pct=round(recent_30d_mdd, 2),
        )

    slippages = actual_slippage_pct(orders, signals)
    recent_slippages = slippages[-5:]
    avg_slippage = sum(recent_slippages) / len(recent_slippages) if recent_slippages else None
    if avg_slippage is not None and len(recent_slippages) >= 3 and avg_slippage > 0.2:
        add_finding(
            findings,
            "performance",
            "warning",
            "actual_slippage_high",
            "실제 slippage가 0.2%를 지속 초과합니다.",
            average_slippage_pct=round(avg_slippage, 4),
        )

    funding_cost = sum(abs(number_or_none(row.get("funding_pnl")) or 0.0) for row in trades if row.get("event_type") == "funding_fee" and (number_or_none(row.get("funding_pnl")) or 0.0) < 0)
    total_pnl = sum(pnl_values)
    funding_ratio = None
    if funding_cost > 0:
        funding_ratio = (funding_cost / abs(total_pnl) * 100) if total_pnl else math.inf
        if funding_ratio > 15:
            add_finding(
                findings,
                "performance",
                "warning",
                "funding_cost_high",
                "funding 비용이 총 PnL의 15%를 초과합니다.",
                funding_cost_to_pnl_pct=funding_ratio,
            )

    recent_20_r = trade_r_values(closed[-20:])
    recent_20_losses = [value for value in recent_20 if value < 0]
    recent_20_profits = [value for value in recent_20 if value > 0]
    return {
        "closed_trade_count": len(closed),
        "recent_20_trade_pf": pf20,
        "recent_50_trade_pf": pf50,
        "recent_20_trade_win_rate_pct": win20,
        "recent_50_trade_win_rate_pct": win50,
        "recent_20_avg_r": avg(recent_20_r),
        "recent_20_avg_loss": avg(recent_20_losses),
        "recent_20_avg_profit": avg(recent_20_profits),
        "recent_30d_return_pct": recent_30d_return,
        "recent_30d_mdd_pct": recent_30d_mdd,
        "actual_slippage_avg_pct": avg_slippage,
        "actual_slippage_samples": slippages[-20:],
        "funding_cost": funding_cost,
        "funding_cost_to_pnl_pct": funding_ratio,
    }


def check_trade_frequency_health(rows_by_file: Dict[str, List[dict]], now_ts: int, findings: List[Finding]) -> dict:
    entries = [
        row
        for row in rows_by_file.get("trades", [])
        if row.get("event_type") == "entry" and parse_ts(row.get("timestamp")) is not None
    ]
    recent_7d = [row for row in entries if (parse_ts(row.get("timestamp")) or 0) >= now_ts - 7 * 86400]
    recent_30d = [row for row in entries if (parse_ts(row.get("timestamp")) or 0) >= now_ts - 30 * 86400]

    if len(recent_7d) > 10:
        add_finding(
            findings,
            "frequency",
            "warning",
            "recent_7d_trade_count_high",
            "최근 7일 거래 수가 10회를 초과했습니다.",
            count=len(recent_7d),
        )
    if len(recent_30d) > 45:
        add_finding(
            findings,
            "frequency",
            "paused",
            "recent_30d_trade_count_paused",
            "최근 30일 거래 수가 45회를 초과해 신규 진입을 정지합니다.",
            count=len(recent_30d),
        )
    elif len(recent_30d) > 30:
        add_finding(
            findings,
            "frequency",
            "warning",
            "recent_30d_trade_count_high",
            "최근 30일 거래 수가 30회를 초과했습니다.",
            count=len(recent_30d),
        )

    reentry_symbols = same_symbol_reentries(entries)
    if reentry_symbols:
        add_finding(
            findings,
            "frequency",
            "warning",
            "same_symbol_reentry_high",
            "동일 심볼이 24시간 내 3회 이상 재진입했습니다.",
            symbols=sorted(reentry_symbols),
        )

    return {
        "recent_7d_trade_count": len(recent_7d),
        "recent_30d_trade_count": len(recent_30d),
        "same_symbol_24h_reentry_symbols": sorted(reentry_symbols),
    }


def build_flow(result: dict, rows_by_file: Dict[str, List[dict]], previous_state: dict) -> dict:
    data_gate = build_data_gate(result)
    regime_gate = build_regime_gate(rows_by_file)
    risk_gate = build_risk_gate(result)
    final_block_reason = final_gate_block_reason(result, data_gate, regime_gate, risk_gate)
    new_entry_allowed = final_block_reason == ""
    repair_state = previous_state.get("last_repair", {})
    flow_steps = build_flow_steps(data_gate, repair_state, new_entry_allowed)
    signal_order = build_signal_order_flow(result, data_gate, regime_gate, risk_gate, final_block_reason)
    beginner_message = flow_beginner_message(data_gate, regime_gate, risk_gate, new_entry_allowed, repair_state)
    return {
        "health_status": result["status"],
        "new_entry_allowed": new_entry_allowed,
        "trading_ready": new_entry_allowed,
        "final_block_reason": final_block_reason,
        "beginner_message": beginner_message,
        "gates": {
            "data": data_gate,
            "regime": regime_gate,
            "risk": risk_gate,
            "final": {
                "status": "pass" if new_entry_allowed else "blocked",
                "new_entry_allowed": new_entry_allowed,
                "reason": final_block_reason,
            },
        },
        "flow_steps": flow_steps,
        "data_gaps": result.get("data", {}).get("data_gaps", []),
        "signals": signal_order,
        "repair": repair_state,
    }


def build_data_gate(result: dict) -> dict:
    data_gaps = result.get("data", {}).get("data_gaps", [])
    affected = [row for row in data_gaps if row.get("affects_trading") and row.get("status") == "fail"]
    data_status = result.get("component_status", {}).get("data", "normal")
    data_findings = [row for row in result.get("findings", []) if row.get("section") == "data" and row.get("status") in {"critical", "paused"}]
    blocking_codes = {
        "latest_1h_candle_stale",
        "empty_candle_file",
        "ohlc_invalid",
        "reversed_candle_timestamp",
        "data_update_missing",
    }
    blocking_findings = [
        row
        for row in data_findings
        if row.get("status") == "paused"
        or row.get("code") in blocking_codes
        or (str(row.get("code", "")).startswith("missing_") and row.get("code") != "missing_candles")
    ]
    status = "fail" if affected or blocking_findings or data_status == "paused" else "pass"
    first_gap = affected[0] if affected else {}
    reason = first_gap.get("gap_type") or (blocking_findings[0]["code"] if blocking_findings else "")
    if status == "pass":
        reason = ""
    return {
        "status": status,
        "reason": reason,
        "failed_reason": reason,
        "affected_symbols": sorted({row.get("symbol", "") for row in affected if row.get("symbol")}),
        "affected_timeframes": sorted({row.get("timeframe", "") for row in affected if row.get("timeframe")}),
        "gap_count": len(data_gaps),
        "affecting_gap_count": len(affected),
        "repairable_gap_count": len([row for row in affected if row.get("repairable")]),
        "unrepairable_gap_count": len([row for row in affected if not row.get("repairable")]),
        "unrepairable_gaps": [
            {
                "symbol": row.get("symbol", ""),
                "timeframe": row.get("timeframe", ""),
                "gap_type": row.get("gap_type", ""),
                "failure_reason": row.get("failure_reason", ""),
            }
            for row in affected
            if not row.get("repairable")
        ],
        "data_gaps": data_gaps,
    }


def build_regime_gate(rows_by_file: Dict[str, List[dict]]) -> dict:
    regime, action_bias = latest_regime_state(rows_by_file)
    reason = ""
    if str(regime).lower() == "shock" or str(action_bias).lower() == "shock":
        reason = "regime_shock"
    elif str(action_bias).lower() == "reduce_risk":
        reason = "regime_reduce_risk"
    elif str(action_bias).lower() == "no_new_entry":
        reason = "regime_no_new_entry"
    elif str(action_bias).lower() == "wait":
        reason = "regime_wait"
    elif str(regime).lower() in {"defensive", "observe", "neutral"}:
        reason = f"regime_{str(regime).lower()}"
    return {
        "status": "blocked" if reason else "pass",
        "regime": regime,
        "action_bias": action_bias,
        "reason": reason,
    }


def latest_regime_state(rows_by_file: Dict[str, List[dict]]) -> Tuple[str, str]:
    equity = rows_by_file.get("equity", [])
    if equity:
        latest = equity[-1]
        regime = latest.get("current_regime", "")
        action = latest.get("current_action_bias", "")
        if regime or action:
            return regime, action
    signals = rows_by_file.get("signals", [])
    latest_signal_rows = latest_rows_by_timestamp(signals, "signal_time")
    if latest_signal_rows:
        row = latest_signal_rows[0]
        return row.get("trade_regime", ""), row.get("trade_action_bias", "")
    return "", ""


def build_risk_gate(result: dict) -> dict:
    risk = result.get("risk", {})
    symbol_risks = risk.get("symbol_risks", [])
    liquidation_count = risk.get("liquidation_risk_count", 0) or 0
    invalid_leverage_count = risk.get("invalid_applied_leverage_count", 0) or 0
    open_positions = risk.get("open_positions", 0) or 0
    fail = liquidation_count > 0 or invalid_leverage_count > 0 or open_positions > risk.get("max_positions", 3)
    applied = [row.get("applied_leverage") for row in symbol_risks if row.get("applied_leverage") is not None]
    buffers = [row.get("liquidation_buffer_pct") for row in symbol_risks if row.get("liquidation_buffer_pct") is not None]
    return {
        "status": "fail" if fail else "pass",
        "reason": "liquidation_risk" if liquidation_count else "invalid_applied_leverage" if invalid_leverage_count else "max_positions_exceeded" if fail else "",
        "liquidation_buffer": min(buffers) if buffers else None,
        "applied_leverage": applied,
        "position_count": open_positions,
        "liquidation_risk": liquidation_count > 0,
        "liquidation_risk_count": liquidation_count,
        "invalid_applied_leverage_count": invalid_leverage_count,
    }


def final_gate_block_reason(result: dict, data_gate: dict, regime_gate: dict, risk_gate: dict) -> str:
    if data_gate["status"] == "fail":
        return "health_data_gap"
    if regime_gate["status"] == "blocked":
        return regime_gate.get("reason") or "regime_blocked"
    if risk_gate["status"] == "fail":
        return risk_gate.get("reason") or "risk_gate_fail"
    if result.get("status") == "paused":
        return result.get("pause_reason") or "health_paused"
    return ""


def build_flow_steps(data_gate: dict, repair_state: dict, new_entry_allowed: bool) -> List[dict]:
    data_failed = data_gate["status"] == "fail"
    repair_status = repair_state.get("status", "")
    if data_failed:
        repair_step = "ready"
    elif repair_status == "complete":
        repair_step = "pass"
    else:
        repair_step = "pending"
    return [
        {"name": "data_check", "label": "데이터 검사", "status": "fail" if data_failed else "pass"},
        {
            "name": "new_entry_lock",
            "label": "신규 진입 잠금",
            "status": "pass" if data_failed and not new_entry_allowed else "pending" if not data_failed else "fail",
        },
        {"name": "repair_data", "label": "데이터 복구", "status": repair_step},
        {"name": "recheck_health", "label": "Health 재검사", "status": "pending" if data_failed else "pass"},
        {"name": "allow_new_entry", "label": "신규 진입 허용 여부", "status": "pass" if new_entry_allowed else "blocked"},
    ]


def build_signal_order_flow(result: dict, data_gate: dict, regime_gate: dict, risk_gate: dict, final_block_reason: str) -> List[dict]:
    out = []
    for row in result.get("signals", {}).get("scan_results", []):
        signal_status = "candidate_pass" if row.get("top_20_passed") else "filtered"
        if row.get("selected"):
            signal_status = "candidate_pass"
        elif row.get("block_reason") and not row.get("top_20_passed"):
            signal_status = "candidate_fail"

        order_status = "ready" if row.get("selected") and not final_block_reason else "not_created"
        block_reason = row.get("block_reason") or ""
        if row.get("selected") or row.get("top_20_passed"):
            if data_gate["status"] == "fail":
                order_status = "blocked"
                block_reason = "health_data_gap"
            elif regime_gate["status"] == "blocked":
                order_status = "blocked"
                block_reason = regime_gate.get("reason") or "regime_blocked"
            elif risk_gate["status"] == "fail":
                order_status = "blocked"
                block_reason = risk_gate.get("reason") or "risk_gate_fail"
            elif final_block_reason:
                order_status = "blocked"
                block_reason = final_block_reason
            elif row.get("selected"):
                order_status = "ready"

        out.append(
            {
                "symbol": row.get("symbol", ""),
                "alpha_score": row.get("alpha_score"),
                "signal_status": signal_status,
                "order_status": order_status,
                "block_reason": block_reason,
            }
        )
    return out


def flow_beginner_message(data_gate: dict, regime_gate: dict, risk_gate: dict, new_entry_allowed: bool, repair_state: dict) -> str:
    if data_gate["status"] == "fail":
        if repair_state.get("status") == "complete":
            return "데이터 복구가 끝났습니다. 다시 검사를 실행하세요."
        return "데이터가 비어 있어서 새 주문을 막았습니다."
    if repair_state.get("status") == "ready":
        return "복구 버튼을 누르면 누락된 캔들을 다시 받아옵니다."
    if regime_gate["status"] == "blocked":
        return "데이터는 정상입니다. 하지만 현재 시장 상태가 방어 모드라 주문하지 않습니다."
    if risk_gate["status"] == "fail":
        return "리스크 조건이 맞지 않아 새 주문을 막았습니다."
    if new_entry_allowed:
        return "모든 조건이 정상입니다. 다음 신호부터 페이퍼 주문이 생성됩니다."
    return BEGINNER_MESSAGES["paused"]


def build_health_flow_payload(
    state_dir: Path = STATE_DIR,
    raw_dir: Path = RAW_DIR,
    report_path: Path = REPORT_PATH,
    now_ts: Optional[int] = None,
    write_outputs: bool = True,
) -> dict:
    health_result = run_check(state_dir=state_dir, raw_dir=raw_dir, report_path=report_path, now_ts=now_ts, write_outputs=write_outputs)
    flow = health_result["flow"]
    return {
        "ok": True,
        "health_status": flow["health_status"],
        "new_entry_allowed": flow["new_entry_allowed"],
        "trading_ready": flow["trading_ready"],
        "final_block_reason": flow["final_block_reason"],
        "beginner_message": flow["beginner_message"],
        "gates": flow["gates"],
        "flow_steps": flow["flow_steps"],
        "data_gaps": flow["data_gaps"],
        "signals": flow["signals"],
        "repair": flow["repair"],
        "health": health_result,
    }


def repair_market_data_gaps(
    state_dir: Path = STATE_DIR,
    raw_dir: Path = RAW_DIR,
    now_ts: Optional[int] = None,
    fetcher=None,
) -> dict:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    state_dir = Path(state_dir)
    raw_dir = Path(raw_dir)
    state = load_health_state(state_dir)
    state["last_repair"] = {"status": "repairing", "started_at": format_dt(now_ts)}
    write_health_state(state_dir, state)

    check = run_check(state_dir=state_dir, raw_dir=raw_dir, now_ts=now_ts, write_outputs=False)
    failed_gaps = [
        row
        for row in check.get("flow", {}).get("data_gaps", [])
        if row.get("affects_trading") and row.get("status") == "fail"
    ]
    unrepairable = [
        row
        for row in failed_gaps
        if not row.get("repairable") or not row.get("start_ts") or not row.get("end_ts")
    ]
    repairable = [
        row
        for row in failed_gaps
        if row.get("repairable") and row.get("status") == "fail" and row.get("start_ts") and row.get("end_ts")
    ]
    repaired_candles = 0
    duplicates_removed = 0
    errors = []
    for gap in repairable:
        symbol = gap["symbol"]
        interval = gap["timeframe"]
        path = candle_path(raw_dir, symbol, interval)
        if path is None:
            path = raw_dir / f"{symbol}_{interval}.json"
        raw_dir.mkdir(parents=True, exist_ok=True)
        existing = read_json_rows(path) if path.exists() else []
        before_count = len(existing)
        before_unique = len({parse_ts(row.get("time") or row.get("timestamp") or row.get("open_time")) for row in existing})
        try:
            fetched = fetch_gap_candles(symbol, interval, int(gap["start_ts"]), int(gap["end_ts"]), fetcher)
        except Exception as exc:  # pragma: no cover - network boundary
            errors.append({"symbol": symbol, "timeframe": interval, "error": str(exc)})
            continue
        merged = merge_candle_rows(existing, fetched)
        after_times = {parse_ts(row.get("time") or row.get("timestamp") or row.get("open_time")) for row in merged}
        repaired_candles += max(0, len(after_times) - before_unique)
        duplicates_removed += max(0, before_count + len(fetched) - len(merged))
        path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")

    validation = run_check(state_dir=state_dir, raw_dir=raw_dir, now_ts=now_ts, write_outputs=False)
    validation_result = "pass" if validation.get("flow", {}).get("gates", {}).get("data", {}).get("status") == "pass" else "fail"
    result = {
        "status": "complete",
        "started_at": state.get("last_repair", {}).get("started_at", format_dt(now_ts)),
        "completed_at": format_dt(now_ts),
        "repaired_candle_count": repaired_candles,
        "duplicate_removed_count": duplicates_removed,
        "validation_result": validation_result,
        "errors": errors,
        "unrepairable_gaps": [
            {
                "symbol": row.get("symbol", ""),
                "timeframe": row.get("timeframe", ""),
                "gap_type": row.get("gap_type", ""),
                "failure_reason": row.get("failure_reason", "missing repair window"),
            }
            for row in unrepairable
        ],
    }
    state = load_health_state(state_dir)
    state["last_repair"] = result
    write_health_state(state_dir, state)
    (state_dir / HEALTH_REPAIR_STATE_JSON).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    append_event(state_dir, now_ts, "normal" if validation_result == "pass" else "warning", "repair", "data_repair", "data repair finished", result)
    return result


def fetch_gap_candles(symbol: str, interval: str, start_ts: int, end_ts: int, fetcher=None) -> List[dict]:
    if fetcher is None:
        from collector import fetch_ohlcv  # noqa: WPS433

        fetcher = fetch_ohlcv
    if end_ts < start_ts:
        return []
    return fetcher(symbol, interval, ts_to_iso(start_ts), ts_to_iso(end_ts + INTERVAL_SECONDS[interval]))


def merge_candle_rows(existing: List[dict], fetched: List[dict]) -> List[dict]:
    by_time = {}
    for row in [*existing, *fetched]:
        timestamp = parse_ts(row.get("time") or row.get("timestamp") or row.get("open_time"))
        if timestamp is None:
            continue
        normalized = dict(row)
        normalized["time"] = timestamp
        by_time[timestamp] = normalized
    return [by_time[key] for key in sorted(by_time)]


def manual_pause(state_dir: Path = STATE_DIR, reason: str = "", now_ts: Optional[int] = None) -> dict:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    reason = reason.strip()
    if not reason:
        raise ValueError("pause reason is required")
    ensure_output_files(state_dir)
    previous = load_health_state(state_dir)
    previous.update(
        {
            "status": "paused",
            "can_enter": False,
            "new_entry_allowed": False,
            "pause_reason": reason,
            "manual_pause": True,
            "manual_paused_at": format_dt(now_ts),
            "last_check_at": format_dt(now_ts),
            "resume_required": True,
            "beginner_message": BEGINNER_MESSAGES["paused"],
        }
    )
    write_health_state(state_dir, previous)
    append_event(state_dir, now_ts, "paused", "manual", "manual_pause", reason, {"source": "cli_or_dashboard"})
    return previous


def manual_resume(state_dir: Path = STATE_DIR, reason: str = "", now_ts: Optional[int] = None) -> dict:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    reason = reason.strip()
    if not reason:
        raise ValueError("resume reason is required")
    ensure_output_files(state_dir)
    previous = load_health_state(state_dir)
    previous.update(
        {
            "status": "normal",
            "can_enter": True,
            "new_entry_allowed": True,
            "pause_reason": "",
            "manual_pause": False,
            "auto_paused_at": "",
            "manual_resumed_at": format_dt(now_ts),
            "manual_resume_reason": reason,
            "last_check_at": format_dt(now_ts),
            "resume_required": False,
            "beginner_message": BEGINNER_MESSAGES["normal"],
        }
    )
    write_health_state(state_dir, previous)
    append_event(state_dir, now_ts, "normal", "manual", "manual_resume", reason, {"source": "cli_or_dashboard"})
    return previous


def load_health_state(state_dir: Path = STATE_DIR) -> dict:
    path = Path(state_dir) / HEALTH_STATE_JSON
    default = {
        "status": "normal",
        "can_enter": True,
        "new_entry_allowed": True,
        "pause_reason": "",
        "manual_pause": False,
        "resume_required": False,
        "beginner_message": BEGINNER_MESSAGES["normal"],
        "last_check_at": "",
        "last_check_timestamp": None,
        "last_normal_run_at": "",
        "component_status": {},
        "metrics": {},
        "final_block_reason": "",
        "last_repair": {},
        "status_label": "normal",
        "status_reasons": [],
        "critical_reasons": [],
        "warning_reasons": [],
        "paused_reasons": [],
        "human_summary": BEGINNER_MESSAGES["normal"],
        "data_gap_summary": {},
        "repairable_gap_count": 0,
        "unrepairable_gap_count": 0,
        "strategy_locked": False,
        "strategy_lock_name": "",
        "strategy_name": "",
        "strategy_lock_version": "",
        "strategy_lock_time": "",
        "strategy_lock_timestamp": None,
        "paper_start_time": "",
        "paper_start_timestamp": None,
        "oos_start_time": "",
        "oos_start_timestamp": None,
        "oos_classification_rule": "",
        "strategy_change_requires_oos_reset": True,
        "oos_reset_required": False,
        "oos_reset_reason": "",
    }
    if not path.exists():
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return {**default, **loaded}


def read_health_events(state_dir: Path = STATE_DIR, limit: int = 100) -> List[dict]:
    path = Path(state_dir) / HEALTH_EVENTS_CSV
    if not path.exists():
        return []
    rows = read_csv_rows(path)
    return rows[-limit:][::-1]


def read_health_report(report_path: Path = REPORT_PATH) -> str:
    path = Path(report_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def ensure_output_files(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    ensure_csv_file(state_dir / HEALTH_CSV, HEALTH_FIELDS)
    ensure_csv_file(state_dir / HEALTH_EVENTS_CSV, EVENT_FIELDS)


def load_paper_csvs(state_dir: Path) -> Tuple[Dict[str, List[dict]], List[dict]]:
    rows_by_file: Dict[str, List[dict]] = {}
    errors: List[dict] = []
    for key, filename in PAPER_FILES.items():
        path = state_dir / filename
        if not path.exists():
            rows_by_file[key] = []
            errors.append({"filename": filename, "message": f"필수 CSV가 없습니다: {filename}"})
            continue
        try:
            rows_by_file[key] = read_csv_rows(path)
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            rows_by_file[key] = []
            errors.append({"filename": filename, "message": f"CSV 읽기 오류: {filename}: {exc}"})
    return rows_by_file, errors


def read_csv_rows(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        return list(reader)


def ensure_csv_file(path: Path, fields: List[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()


def append_health_row(state_dir: Path, result: dict) -> None:
    row = {
        "timestamp": result["timestamp"],
        "date": result["generated_at"],
        "status": result["status"],
        "can_enter": result["can_enter"],
        "pause_reason": result["pause_reason"],
        "system_status": result["component_status"]["system"],
        "data_status": result["component_status"]["data"],
        "signal_status": result["component_status"]["signal"],
        "order_position_status": result["component_status"]["order_position"],
        "risk_status": result["component_status"]["risk"],
        "performance_status": result["component_status"]["performance"],
        "frequency_status": result["component_status"]["frequency"],
        "last_run_at": result["system"]["last_run_at"],
        "last_data_update_at": result["system"]["last_data_update_at"],
        "last_1h_candle_at": result["system"]["last_1h_candle_at"],
        "last_4h_signal_at": result["system"]["last_4h_signal_at"],
        "open_positions": result["metrics"]["open_positions"],
        "liquidation_risk_count": result["metrics"]["liquidation_risk_count"],
        "recent_20_trade_pf": format_optional_number(result["metrics"]["recent_20_trade_pf"]),
        "recent_50_trade_pf": format_optional_number(result["metrics"]["recent_50_trade_pf"]),
        "recent_20_trade_win_rate_pct": format_optional_number(result["metrics"]["recent_20_trade_win_rate_pct"]),
        "recent_50_trade_win_rate_pct": format_optional_number(result["metrics"]["recent_50_trade_win_rate_pct"]),
        "recent_30d_return_pct": format_optional_number(result["metrics"]["recent_30d_return_pct"]),
        "recent_30d_mdd_pct": format_optional_number(result["metrics"]["recent_30d_mdd_pct"]),
        "recent_7d_trade_count": result["metrics"]["recent_7d_trade_count"],
        "recent_30d_trade_count": result["metrics"]["recent_30d_trade_count"],
        "issue_count": len(result["findings"]),
        "paused_issue_count": len([row for row in result["findings"] if row["status"] == "paused"]),
    }
    append_csv_row(state_dir / HEALTH_CSV, HEALTH_FIELDS, row)


def append_findings(state_dir: Path, findings: List[Finding], now_ts: int) -> None:
    for index, finding in enumerate(findings):
        if finding.status == "normal":
            continue
        append_event(
            state_dir,
            now_ts,
            finding.status,
            finding.section,
            finding.code,
            finding.message,
            finding.details,
            suffix=str(index),
        )


def append_event(
    state_dir: Path,
    timestamp: int,
    status: str,
    section: str,
    code: str,
    message: str,
    details: dict,
    suffix: str = "",
) -> None:
    ensure_output_files(state_dir)
    event_id = f"health_{timestamp}_{code}"
    if suffix:
        event_id = f"{event_id}_{suffix}"
    row = {
        "event_id": event_id,
        "timestamp": timestamp,
        "date": format_dt(timestamp),
        "status": status,
        "section": section,
        "code": code,
        "message": message,
        "details_json": json.dumps(details, ensure_ascii=False, separators=(",", ":")),
    }
    append_csv_row(state_dir / HEALTH_EVENTS_CSV, EVENT_FIELDS, row)


def append_csv_row(path: Path, fields: List[str], row: dict) -> None:
    ensure_csv_file(path, fields)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writerow(row)


def write_health_state(state_dir: Path, state: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / HEALTH_STATE_JSON).write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_report(result: dict) -> str:
    metrics = result["metrics"]
    lines = [
        "# Alpha Engine v1.2 Health Report",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- status: {result['status']}",
        f"- beginner_message: {result['beginner_message']}",
        f"- new_entry_allowed: {result['new_entry_allowed']}",
        f"- pause_reason: {result['pause_reason'] or '-'}",
        f"- last_normal_run_at: {result['last_normal_run_at'] or '-'}",
        f"- human_summary: {human_status_summary(result, summarize_data_gaps(result.get('data', {}).get('data_gaps', [])), readable_reasons(result, {'critical'}), readable_reasons(result, {'warning'}), readable_reasons(result, {'paused'}))}",
        f"- strategy_locked: {STRATEGY_LOCK_NAME}",
        f"- oos_rule: paper_start_time 이후 데이터만 OOS로 분류하며 전략 변경 시 OOS reset 필요",
        "",
        "## Dashboard Metrics",
        "",
        f"- recent_20_trade_pf: {format_optional_number(metrics['recent_20_trade_pf'])}",
        f"- recent_50_trade_pf: {format_optional_number(metrics['recent_50_trade_pf'])}",
        f"- recent_30d_mdd_pct: {format_optional_number(metrics['recent_30d_mdd_pct'])}",
        f"- recent_7d_trade_count: {metrics['recent_7d_trade_count']}",
        f"- recent_30d_trade_count: {metrics['recent_30d_trade_count']}",
        "",
        "## Component Status",
        "",
    ]
    for key, value in result["component_status"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Signal Scan",
            "",
            f"- scan_count: {result['signals']['scan_count']}",
            f"- entry_candidates: {len(result['signals']['entry_candidates'])}",
            "",
            "| symbol | alpha_score | top_20 | selected | block_reason |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in result["signals"]["scan_results"]:
        lines.append(
            f"| {row['symbol']} | {format_optional_number(row['alpha_score'])} | {row['top_20_passed']} | {row['selected']} | {row['block_reason'] or '-'} |"
        )

    lines.extend(["", "## Findings", ""])
    if result["findings"]:
        for finding in result["findings"]:
            lines.append(f"- [{finding['status']}] {finding['section']}.{finding['code']}: {finding['message']}")
    else:
        lines.append("- no findings")
    lines.append("")
    return "\n".join(lines)


def read_api_errors(state_dir: Path, now_ts: int) -> List[dict]:
    path = state_dir / ERROR_LOG_NAME
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(row.get("timestamp"))
        if ts is not None and ts >= now_ts - 86400:
            rows.append(row)
    return rows


def candle_path(raw_dir: Path, symbol: str, interval: str) -> Optional[Path]:
    candidates = [
        raw_dir / f"{symbol}_{interval}.json",
        raw_dir / f"{symbol}_futures_{interval}.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def read_json_rows(path: Path) -> List[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "candles"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def inspect_candles(
    symbol: str,
    interval: str,
    rows: List[dict],
    seconds: int,
    now_ts: int,
    position_symbols: set,
) -> dict:
    times = [parse_ts(row.get("time") or row.get("timestamp") or row.get("open_time")) for row in rows]
    times = [value for value in times if value is not None]
    duplicate_count = len(times) - len(set(times))
    reversed_count = sum(1 for previous, current in zip(times, times[1:]) if current < previous)
    missing_count = 0
    max_gap = 0
    gap_details = []
    sorted_times = sorted(set(times))
    for previous, current in zip(sorted_times, sorted_times[1:]):
        gap = current - previous
        max_gap = max(max_gap, gap)
        if gap > seconds * 1.5:
            count = max(1, round(gap / seconds) - 1)
            missing_count += count
            gap_type = classify_gap(symbol, interval, previous, current, seconds, now_ts, position_symbols)
            affects_trading = gap_affects_trading(symbol, interval, gap_type)
            gap_details.append(
                data_gap_row(
                    symbol,
                    interval,
                    gap_type,
                    count,
                    previous + seconds,
                    current - seconds,
                    affects_trading,
                    True,
                    "fail" if affects_trading else "warning",
                )
            )

    ohlc_issues = []
    for row in rows:
        ts = parse_ts(row.get("time") or row.get("timestamp") or row.get("open_time"))
        open_price = number_or_none(row.get("open"))
        high = number_or_none(row.get("high"))
        low = number_or_none(row.get("low"))
        close = number_or_none(row.get("close"))
        if close is None or high is None or low is None:
            ohlc_issues.append({"time": ts, "reason": "missing_ohlc"})
            continue
        if close <= 0:
            ohlc_issues.append({"time": ts, "reason": "close_le_zero", "close": close})
        if high < low:
            ohlc_issues.append({"time": ts, "reason": "high_lt_low", "high": high, "low": low})
        if close > high or close < low:
            ohlc_issues.append({"time": ts, "reason": "close_outside_range", "close": close, "high": high, "low": low})
        if open_price is not None and open_price <= 0:
            ohlc_issues.append({"time": ts, "reason": "open_le_zero", "open": open_price})

    latest_open = max(sorted_times) if sorted_times else None
    latest_close_ts = latest_open + seconds if latest_open is not None else None
    return {
        "symbol": symbol,
        "interval": interval,
        "latest_close_ts": latest_close_ts,
        "duplicate_timestamp_count": duplicate_count,
        "reversed_timestamp_count": reversed_count,
        "missing_candle_count": missing_count,
        "max_gap_seconds": max_gap,
        "gap_details": gap_details,
        "ohlc_issue_count": len(ohlc_issues),
        "ohlc_examples": ohlc_issues[:5],
    }


def classify_gap(
    symbol: str,
    interval: str,
    previous: int,
    current: int,
    seconds: int,
    now_ts: int,
    position_symbols: set,
) -> str:
    if symbol in position_symbols:
        return "position_symbol_gap"
    gap_end = current - seconds
    if gap_end >= now_ts - 7 * 86400:
        return "recent_middle_gap"
    if symbol in TRADING_UNIVERSE and interval in {"1h", "4h"} and gap_end >= now_ts - 30 * 86400:
        return "active_symbol_gap"
    return "old_historical_gap"


def gap_affects_trading(symbol: str, interval: str, gap_type: str) -> bool:
    if interval not in {"1h", "4h"}:
        return False
    if symbol not in TRADING_UNIVERSE:
        return False
    return gap_type in {"recent_middle_gap", "active_symbol_gap", "position_symbol_gap"}


def data_gap_row(
    symbol: str,
    timeframe: str,
    gap_type: str,
    missing_count: int,
    start_time: Optional[int],
    end_time: Optional[int],
    affects_trading: bool,
    repairable: bool,
    status: str,
    failure_reason: str = "",
) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "gap_type": gap_type,
        "missing_count": missing_count,
        "start_time": format_dt(start_time),
        "end_time": format_dt(end_time),
        "start_ts": start_time,
        "end_ts": end_time,
        "affects_trading": affects_trading,
        "repairable": repairable,
        "status": status,
        "failure_reason": failure_reason,
    }


def latest_gap_detail(symbol: str, interval: str, latest_close: int, seconds: int, now_ts: int) -> Optional[dict]:
    age = now_ts - latest_close
    if age <= seconds * 1.5:
        return None
    missing_count = max(1, int(age // seconds))
    affects = symbol in TRADING_UNIVERSE and interval in {"1h", "4h"}
    return data_gap_row(
        symbol,
        interval,
        "latest_incomplete_candle",
        missing_count,
        latest_close,
        now_ts - seconds,
        affects,
        True,
        "fail" if affects else "warning",
    )


def latest_engine_timestamp(rows_by_file: Dict[str, List[dict]]) -> Optional[int]:
    candidates: List[int] = []
    fields_by_file = {
        "positions": ("last_update_time", "opened_at", "signal_time"),
        "orders": ("updated_time", "created_time", "fill_time", "signal_time"),
        "trades": ("timestamp",),
        "equity": ("timestamp",),
        "signals": ("signal_time", "fill_time"),
    }
    for key, fields in fields_by_file.items():
        timestamp = max_ts(rows_by_file.get(key, []), fields)
        if timestamp is not None:
            candidates.append(timestamp)
    return max(candidates) if candidates else None


def latest_rows_by_timestamp(rows: List[dict], field: str) -> List[dict]:
    latest = max_ts(rows, (field,))
    if latest is None:
        return []
    return [row for row in rows if parse_ts(row.get(field)) == latest]


def max_ts(rows: Iterable[dict], fields: Iterable[str]) -> Optional[int]:
    values: List[int] = []
    for row in rows:
        for field in fields:
            value = parse_ts(row.get(field))
            if value is not None:
                values.append(value)
    return max(values) if values else None


def parse_ts(value) -> Optional[int]:
    if value in {"", None}:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = float(text)
        except ValueError:
            try:
                return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
            except ValueError:
                return None
    if not math.isfinite(parsed):
        return None
    if parsed > 10_000_000_000:
        parsed = parsed / 1000
    return int(parsed)


def number_or_none(value) -> Optional[float]:
    if value in {"", None}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def int_or_none(value) -> Optional[int]:
    parsed = number_or_none(value)
    return int(parsed) if parsed is not None else None


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def is_blocked_regime(regime: str, action_bias: str) -> bool:
    regime_value = str(regime or "").lower()
    action_value = str(action_bias or "").lower()
    return regime_value == "shock" or action_value in {"reduce_risk", "shock", "no_new_entry"}


def liquidation_buffer_is_recorded(rows_by_file: Dict[str, List[dict]]) -> bool:
    positions = rows_by_file.get("positions", [])
    orders = rows_by_file.get("orders", [])
    if any(row.get("liquidation_buffer_pct") not in {"", None} for row in positions):
        return True
    return any(row.get("reason") == "applied_leverage_liquidation_buffer" for row in orders)


def open_position_rows(rows: List[dict]) -> List[dict]:
    return [row for row in rows if str(row.get("status") or "open").lower() == "open"]


def has_liquidation_risk(row: dict) -> bool:
    if truthy(row.get("liquidation_risk")):
        return True
    stop = number_or_none(row.get("stop_price"))
    liquidation = number_or_none(row.get("liquidation_price_est"))
    buffer_pct = number_or_none(row.get("liquidation_buffer_pct"))
    if buffer_pct is not None and buffer_pct <= 0:
        return True
    if stop is not None and liquidation is not None and stop <= liquidation:
        return True
    return False


def latest_equity_value(equity_rows: List[dict]) -> float:
    if not equity_rows:
        return 1.0
    value = number_or_none(equity_rows[-1].get("equity"))
    return value if value is not None and value > 0 else 1.0


def period_return_pct(equity_rows: List[dict], now_ts: int, days: int) -> Optional[float]:
    if not equity_rows:
        return None
    rows = sorted(
        [(parse_ts(row.get("timestamp")), number_or_none(row.get("equity"))) for row in equity_rows],
        key=lambda item: item[0] or 0,
    )
    rows = [(ts, value) for ts, value in rows if ts is not None and value is not None and value > 0]
    if not rows:
        return None
    current = rows[-1][1]
    cutoff = now_ts - days * 86400
    baseline = rows[0][1]
    for ts, value in rows:
        if ts >= cutoff:
            baseline = value
            break
    return (current / baseline - 1) * 100 if baseline else None


def rolling_mdd_pct(equity_rows: List[dict], now_ts: int, days: int) -> Optional[float]:
    rows = sorted(
        [(parse_ts(row.get("timestamp")), number_or_none(row.get("equity"))) for row in equity_rows],
        key=lambda item: item[0] or 0,
    )
    rows = [(ts, value) for ts, value in rows if ts is not None and value is not None and ts >= now_ts - days * 86400]
    if not rows:
        return None
    peak = rows[0][1]
    max_drawdown = 0.0
    for _ts, value in rows:
        peak = max(peak, value)
        if peak:
            max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return max_drawdown


def closed_trade_rows(trades: List[dict]) -> List[dict]:
    return [row for row in trades if row.get("event_type") == "exit"]


def trade_pnl(row: dict) -> float:
    value = number_or_none(row.get("position_total_pnl"))
    if value is not None:
        return value
    return number_or_none(row.get("pnl")) or 0.0


def profit_factor(values: List[float]) -> Optional[float]:
    if not values:
        return None
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else None
    return gross_profit / gross_loss


def win_rate_pct(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values) * 100


def trade_r_values(trades: List[dict]) -> List[float]:
    out = []
    for row in trades:
        entry = number_or_none(row.get("entry_price"))
        stop = number_or_none(row.get("stop_price"))
        exit_price = number_or_none(row.get("exit_price") or row.get("price"))
        if entry is None or stop is None or exit_price is None or entry == stop:
            continue
        out.append((exit_price - entry) / abs(entry - stop))
    return out


def actual_slippage_pct(orders: List[dict], signals: List[dict]) -> List[float]:
    signal_close_by_id = {
        row.get("signal_id", ""): number_or_none(row.get("close"))
        for row in signals
        if row.get("signal_id")
    }
    out = []
    for order in orders:
        if order.get("status") != "filled":
            continue
        entry = number_or_none(order.get("entry_price"))
        signal_close = signal_close_by_id.get(order.get("signal_id", ""))
        if entry is None or signal_close is None or signal_close <= 0:
            continue
        out.append(abs(entry / signal_close - 1) * 100)
    return out


def same_symbol_reentries(entries: List[dict]) -> set:
    by_symbol: Dict[str, List[int]] = {}
    for row in entries:
        ts = parse_ts(row.get("timestamp"))
        symbol = str(row.get("symbol", "")).upper()
        if ts is not None and symbol:
            by_symbol.setdefault(symbol, []).append(ts)
    flagged = set()
    for symbol, times in by_symbol.items():
        sorted_times = sorted(times)
        for index, start in enumerate(sorted_times):
            count = sum(1 for ts in sorted_times[index:] if ts - start <= 86400)
            if count >= 3:
                flagged.add(symbol)
                break
    return flagged


def add_finding(findings: List[Finding], section: str, status: str, code: str, message: str, **details) -> None:
    findings.append(Finding(section=section, status=status, code=code, message=message, details=details))


def section_status(findings: List[Finding], section: str) -> str:
    return worst_status(finding.status for finding in findings if finding.section == section)


def worst_status(statuses: Iterable[str]) -> str:
    rank = 0
    for status in statuses:
        rank = max(rank, STATUS_RANK.get(status, 0))
    return RANK_STATUS[rank]


def format_dt(timestamp) -> str:
    if timestamp in {"", None}:
        return ""
    try:
        return datetime.fromtimestamp(int(float(timestamp)), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return ""


def ts_to_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def age_hours(now_ts: int, timestamp: Optional[int]) -> Optional[float]:
    if timestamp is None:
        return None
    return round((now_ts - timestamp) / 3600, 2)


def avg(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def format_optional_number(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


if __name__ == "__main__":
    main()
