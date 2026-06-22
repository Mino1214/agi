"""Audit report for BTC/ETH Monthly Strength v1.

This script does not change the strategy rules. It reuses the v1 report
backtest helpers and adds concentration, emergency-defense attribution, OOS,
parameter stability, and benchmark robustness checks.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import btc_eth_monthly_strength_v1_report as v1  # noqa: E402


CONCENTRATION_MDD_WORSEN_LIMIT_PCT = 10.0
OOS_MAX_LOSS_PCT = -20.0
OOS_MDD_LIMIT_PCT = -25.0
PARAMETER_MDD_SPREAD_LIMIT_PCT = 10.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON only if it covers the required window.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = load_latest_raw(v1.SYMBOLS, use_cache=args.use_cache)
    payload = v1.build_payload_from_raw(raw, interval="1d", start=v1.FETCH_START, symbols=v1.SYMBOLS)
    data = v1.BacktestData(raw=raw, payload=payload)

    base = v1.run_strength_strategy(data, v1.base_config())
    no_emergency = v1.run_strength_strategy(
        data,
        v1.StrengthConfig(
            name="v1 without emergency defense",
            emergency_defense=False,
            group="Benchmark",
        ),
    )
    concentration = return_concentration(base)
    emergency_rows = emergency_attribution(data)
    oos = run_oos(data)
    parameter_results = v1.parameter_sensitivity(data)
    benchmarks = benchmark_results(data, base, no_emergency)
    pass_fail = pass_fail_rows(concentration, emergency_rows, oos, parameter_results)

    report = build_report(
        data=data,
        base=base,
        concentration=concentration,
        emergency_rows=emergency_rows,
        oos=oos,
        parameter_results=parameter_results,
        benchmarks=benchmarks,
        pass_fail=pass_fail,
    )

    report_path = output_dir / "btc_eth_monthly_strength_v1_audit_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "btc_eth_monthly_strength_v1_audit_concentration.csv", concentration)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_audit_emergency_attribution.csv", emergency_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_audit_oos_2026.csv", oos["monthly_rows"])
    write_csv(output_dir / "btc_eth_monthly_strength_v1_audit_pass_fail.csv", pass_fail)
    print(report_path)


def load_latest_raw(symbols: Iterable[str], use_cache: bool) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    out = {}
    for symbol in symbols:
        cached = v1.read_cache(raw_dir / f"{symbol}_1d.json") if use_cache else []
        if cached and covers_latest_window(cached):
            out[symbol] = cached
        else:
            out[symbol] = v1.fetch_ohlcv(symbol, "1d", v1.FETCH_START)
    return out


def covers_latest_window(candles: List[dict]) -> bool:
    if not candles:
        return False
    start_ts = int(datetime.fromisoformat(v1.FETCH_START).timestamp())
    latest_month = latest_complete_month_from_clock()
    latest_row = candles[-1]
    return candles[0]["time"] <= start_ts and v1.month_from_ts(latest_row["time"]) >= latest_month


def return_concentration(base: v1.StrategyResult) -> List[dict]:
    rows = base.monthly_rows
    out = [concentration_metric("Base", rows, set())]
    best = sorted(rows, key=lambda row: row["return_pct"], reverse=True)
    worst = sorted(rows, key=lambda row: row["return_pct"])
    for count in (1, 3, 5, 10):
        removed = {row["month"] for row in best[:count]}
        out.append(concentration_metric(f"Best Top {count} removed", rows, removed))
    for count in (1, 3, 5, 10):
        removed = {row["month"] for row in worst[:count]}
        out.append(concentration_metric(f"Worst Top {count} removed", rows, removed))
    return out


def concentration_metric(label: str, rows: List[dict], removed_months: set[str]) -> dict:
    returns = [0.0 if row["month"] in removed_months else row["return_pct"] / 100 for row in rows]
    equity = 1.0
    curve = [equity]
    for value in returns:
        equity *= 1 + value
        curve.append(equity)
    cagr = equity ** (12 / len(returns)) - 1 if returns and equity > 0 else None
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(12) if stdev and stdev > 0 else None
    mdd = monthly_mdd(curve)
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    return {
        "case": label,
        "removed_months": ", ".join(sorted(removed_months)),
        "total_return_pct": (equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
    }


def emergency_attribution(data: v1.BacktestData) -> List[dict]:
    config = v1.base_config()
    equity = 1.0
    current_weights: Dict[str, float] = {"cash": 1.0}
    events: List[dict] = []

    for month in data.months:
        target, _ = v1.strength_target(data, config, month)
        target = v1.normalize_weights(target)
        turnover = v1.risk_turnover(current_weights, target)
        if turnover > 1e-12:
            equity *= 1 - turnover * config.cost_rate
            current_weights = dict(target)
        locked_cash = False
        days = v1.month_days(data, month)

        for index, day in enumerate(days):
            gross_return = v1.portfolio_daily_return(current_weights, day)
            equity *= 1 + gross_return
            current_weights = v1.drift_daily_weights(current_weights, day, gross_return)

            if config.emergency_defense and not locked_cash and v1.should_emergency_exit(data, day["time"], config.ema_period):
                exit_turnover = v1.risk_turnover(current_weights, {"cash": 1.0})
                locked_cash = True
                if exit_turnover <= 1e-12:
                    continue
                exit_cost_rate = exit_turnover * config.cost_rate
                weights_before = dict(current_weights)
                no_defense_return = virtual_rest_of_month_return(weights_before, days[index + 1 :])
                actual_return = -exit_cost_rate
                net_benefit = actual_return - no_defense_return
                events.append(
                    {
                        "month": month,
                        "event_date": day["date"],
                        "held_weights": v1.format_weights(weights_before),
                        "btc_after_event_to_month_end_pct": after_event_return(data, "BTCUSDT", month, day["time"]),
                        "eth_after_event_to_month_end_pct": after_event_return(data, "ETHUSDT", month, day["time"]),
                        "actual_defended_return_pct": actual_return * 100,
                        "virtual_no_defense_return_pct": no_defense_return * 100,
                        "loss_saved_pct": max(net_benefit, 0.0) * 100,
                        "missed_gain_pct": max(-net_benefit, 0.0) * 100,
                        "net_benefit_pct": net_benefit * 100,
                    }
                )
                equity *= 1 - exit_cost_rate
                current_weights = {"cash": 1.0}
    return events


def virtual_rest_of_month_return(weights: Dict[str, float], days: List[dict]) -> float:
    equity = 1.0
    current = dict(weights)
    for day in days:
        gross_return = v1.portfolio_daily_return(current, day)
        equity *= 1 + gross_return
        current = v1.drift_daily_weights(current, day, gross_return)
    return equity - 1


def after_event_return(data: v1.BacktestData, symbol: str, month: str, event_time: int) -> Optional[float]:
    event_row = next((row for row in data.raw[symbol] if row["time"] == event_time), None)
    month_end = data.monthly_closes[symbol].get(month)
    if not event_row or not month_end:
        return None
    return (month_end["close"] / event_row["close"] - 1) * 100


def run_oos(data: v1.BacktestData) -> dict:
    end_month = latest_oos_end(data)
    if not end_month or end_month < "2026-01":
        return {"end_month": "", "result": None, "monthly_rows": []}
    months = v1.month_range("2026-01", end_month)
    result = v1.run_strength_strategy(
        data,
        v1.base_config(name=f"2026 OOS through {end_month}", group="OOS"),
        months=months,
    )
    cumulative = 1.0
    rows = []
    for row in result.monthly_rows:
        cumulative *= 1 + row["return_pct"] / 100
        rows.append(
            {
                "month": row["month"],
                "position": row["target_weights"],
                "return_pct": row["return_pct"],
                "cumulative_return_pct": (cumulative - 1) * 100,
                "emergency_exit": row["emergency_exit"],
                "emergency_exit_date": row["emergency_exit_date"],
            }
        )
    return {"end_month": end_month, "result": result, "monthly_rows": rows}


def latest_oos_end(data: v1.BacktestData) -> str:
    candidate = latest_complete_month_from_clock()
    while candidate >= "2026-01":
        if candidate in data.monthly_closes["BTCUSDT"] and candidate in data.monthly_closes["ETHUSDT"]:
            return candidate
        candidate = v1.previous_month(candidate)
    return ""


def latest_complete_month_from_clock() -> str:
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    return v1.previous_month(current_month)


def benchmark_results(
    data: v1.BacktestData,
    base: v1.StrategyResult,
    no_emergency: v1.StrategyResult,
) -> List[v1.StrategyResult]:
    return [
        v1.run_static_strategy(data, v1.StaticConfig(name="BTC Buy & Hold", weights={"BTCUSDT": 1.0})),
        v1.run_static_strategy(data, v1.StaticConfig(name="ETH Buy & Hold", weights={"ETHUSDT": 1.0})),
        v1.run_static_strategy(
            data,
            v1.StaticConfig(
                name="BTC/ETH 50:50",
                weights={"BTCUSDT": 0.50, "ETHUSDT": 0.50},
                rebalance_monthly=True,
            ),
        ),
        v1.run_strength_strategy(
            data,
            v1.StrengthConfig(
                name="BTC/ETH Top1 100%",
                cash_weight=0.0,
                emergency_defense=False,
                use_ema_filter=False,
                top1_share_of_risk=1.0,
                top2_share_of_risk=0.0,
                group="Benchmark",
            ),
        ),
        no_emergency,
        base,
    ]


def pass_fail_rows(
    concentration: List[dict],
    emergency_rows: List[dict],
    oos: dict,
    parameter_results: List[v1.StrategyResult],
) -> List[dict]:
    lookup = {row["case"]: row for row in concentration}
    base = lookup["Base"]
    top5 = lookup["Best Top 5 removed"]
    concentration_cagr_pass = (top5["cagr_pct"] or -999) > 0
    concentration_mdd_pass = top5["mdd_pct"] >= base["mdd_pct"] - CONCENTRATION_MDD_WORSEN_LIMIT_PCT
    net_benefit = sum(row["net_benefit_pct"] for row in emergency_rows)
    oos_result = oos["result"]
    oos_summary = oos_result.summary if oos_result else {}
    oos_pass = bool(
        oos_result
        and oos_summary["total_return_pct"] >= OOS_MAX_LOSS_PCT
        and oos_summary["mdd_pct"] >= OOS_MDD_LIMIT_PCT
    )
    ema_rows = [result.summary for result in parameter_results if result.name in {"EMA150", "EMA200", "EMA250"}]
    ema_mdds = [row["mdd_pct"] for row in ema_rows]
    parameter_pass = bool(
        ema_rows
        and all((row["cagr_pct"] or -999) > 0 and (row["sharpe"] or -999) > 0 for row in ema_rows)
        and max(ema_mdds) - min(ema_mdds) <= PARAMETER_MDD_SPREAD_LIMIT_PCT
    )
    return [
        {
            "check": "concentration_cagr",
            "result": "PASS" if concentration_cagr_pass else "FAIL",
            "evidence": f"Top 5 profit-month removed CAGR {top5['cagr_pct']:.1f}%",
        },
        {
            "check": "concentration_mdd",
            "result": "PASS" if concentration_mdd_pass else "FAIL",
            "evidence": f"Base monthly MDD {base['mdd_pct']:.1f}%, Top 5 removed MDD {top5['mdd_pct']:.1f}%",
        },
        {
            "check": "emergency_defense",
            "result": "PASS" if net_benefit > 0 else "FAIL",
            "evidence": f"Emergency net benefit sum {net_benefit:.1f}%",
        },
        {
            "check": "2026_oos",
            "result": "PASS" if oos_pass else "FAIL",
            "evidence": (
                f"{oos['end_month']} total {oos_summary.get('total_return_pct', 0.0):.1f}%, "
                f"MDD {oos_summary.get('mdd_pct', 0.0):.1f}%"
            ),
        },
        {
            "check": "parameter_stability",
            "result": "PASS" if parameter_pass else "FAIL",
            "evidence": f"EMA150/200/250 MDD spread {max(ema_mdds) - min(ema_mdds):.1f}%p",
        },
    ]


def build_report(
    data: v1.BacktestData,
    base: v1.StrategyResult,
    concentration: List[dict],
    emergency_rows: List[dict],
    oos: dict,
    parameter_results: List[v1.StrategyResult],
    benchmarks: List[v1.StrategyResult],
    pass_fail: List[dict],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    top5_share = top5_positive_share(base.monthly_rows)
    emergency_net = sum(row["net_benefit_pct"] for row in emergency_rows)
    lines = [
        "# BTC/ETH Monthly Strength v1 감사 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        f"- IS 기간: {v1.TEST_START} ~ {v1.TEST_END}",
        f"- 2026 OOS 기간: 2026-01 ~ {oos['end_month'] or '데이터 없음'}",
        "- 전략 규칙은 기존 `BTC/ETH Monthly Strength v1`과 동일하게 유지했다.",
        "- Return Concentration의 제거 후 성과는 해당 월 수익률을 0%로 중립화하고 전체 72개월 길이를 유지해 계산했다.",
        f"- Concentration MDD pass 기준은 Top 5 수익월 제거 후 월별 MDD 악화가 {CONCENTRATION_MDD_WORSEN_LIMIT_PCT:.0f}%p 이내인 경우다.",
        f"- 2026 OOS pass 기준은 누적수익률 {OOS_MAX_LOSS_PCT:.0f}% 이상, MDD {OOS_MDD_LIMIT_PCT:.0f}% 이상이다.",
        f"- Parameter stability pass 기준은 EMA150/200/250이 모두 양(+) CAGR/Sharpe이고 MDD 범위가 {PARAMETER_MDD_SPREAD_LIMIT_PCT:.0f}%p 이내인 경우다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail),
        "",
        "## 1. Return Concentration",
        "",
        f"- 전체 양(+) 월수익 합계 중 최고 수익월 Top 5 비중: {top5_share:.1f}%",
        "",
        concentration_table(concentration),
        "",
        "## 2. Emergency Defense Attribution",
        "",
        f"- 긴급 방어 발생 건수: {len(emergency_rows)}",
        f"- net benefit 합계: {emergency_net:.1f}%",
        "",
        emergency_table(emergency_rows),
        "",
        "## 3. 2026 OOS",
        "",
        oos_summary_table(base, oos),
        "",
        oos_monthly_table(oos["monthly_rows"]),
        "",
        "## 4. Parameter Stability Summary",
        "",
        compact_metric_table([result.summary for result in parameter_results]),
        "",
        "## 5. Benchmark Robustness",
        "",
        compact_metric_table([result.summary for result in benchmarks]),
        "",
        "## 데이터 커버리지",
        "",
        v1.data_coverage_table(data),
        "",
        "## 산출물",
        "",
        "- `btc_eth_monthly_strength_v1_audit_report.md`",
        "- `btc_eth_monthly_strength_v1_audit_concentration.csv`",
        "- `btc_eth_monthly_strength_v1_audit_emergency_attribution.csv`",
        "- `btc_eth_monthly_strength_v1_audit_oos_2026.csv`",
        "- `btc_eth_monthly_strength_v1_audit_pass_fail.csv`",
        "",
    ]
    return "\n".join(lines)


def top5_positive_share(rows: List[dict]) -> float:
    positives = [row["return_pct"] for row in rows if row["return_pct"] > 0]
    if not positives:
        return 0.0
    return sum(sorted(positives, reverse=True)[:5]) / sum(positives) * 100


def monthly_mdd(curve: List[float]) -> float:
    peak = curve[0] if curve else 1.0
    mdd = 0.0
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, equity / peak - 1)
    return mdd


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def concentration_table(rows: List[dict]) -> str:
    lines = ["| Case | Removed months | Total | CAGR | MDD | Sharpe | Calmar |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["case"],
                    row["removed_months"],
                    pct(row["total_return_pct"]),
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def emergency_table(rows: List[dict]) -> str:
    headers = [
        "Month",
        "Date",
        "Held weights",
        "BTC after",
        "ETH after",
        "Actual",
        "No defense",
        "Loss saved",
        "Missed gain",
        "Net",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["month"],
                    row["event_date"],
                    row["held_weights"],
                    pct(row["btc_after_event_to_month_end_pct"]),
                    pct(row["eth_after_event_to_month_end_pct"]),
                    pct(row["actual_defended_return_pct"]),
                    pct(row["virtual_no_defense_return_pct"]),
                    pct(row["loss_saved_pct"]),
                    pct(row["missed_gain_pct"]),
                    pct(row["net_benefit_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def oos_summary_table(base: v1.StrategyResult, oos: dict) -> str:
    if not oos["result"]:
        return "2026 OOS로 계산할 완결 월 데이터가 없다."
    rows = [
        {"name": "2020-2025 IS", **base.summary},
        {"name": oos["result"].summary["name"], **oos["result"].summary},
    ]
    return compact_metric_table(rows)


def oos_monthly_table(rows: List[dict]) -> str:
    if not rows:
        return ""
    lines = ["| Month | Position | Return | Cumulative | Emergency |", "|---|---|---:|---:|---|"]
    for row in rows:
        emergency = row["emergency_exit_date"] if row["emergency_exit"] else "N"
        lines.append(
            f"| {row['month']} | {row['position']} | {pct(row['return_pct'])} | "
            f"{pct(row['cumulative_return_pct'])} | {emergency} |"
        )
    return "\n".join(lines)


def compact_metric_table(rows: List[dict]) -> str:
    lines = ["| Name | CAGR | MDD | Sharpe | Calmar |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["name"],
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def num(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
