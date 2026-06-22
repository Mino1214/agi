"""Position sizing study for monthly strength rotation.

This builds on ``strength_rotation_defense_report.py`` and compares smaller
position sizes against the same monthly defensive filters, plus an optional
daily emergency exit that stays in cash until the next month-end signal.
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
from typing import Callable, Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strength_rotation_defense_report import (  # noqa: E402
    BacktestData,
    FEE_RATE,
    FETCH_END,
    FETCH_START,
    REGIMES,
    SLIPPAGE_RATE,
    TEST_END,
    TEST_START,
    build_payload_from_raw,
    eligible_candidates,
    load_raw,
    month_from_ts,
    month_range,
    normalize_weights,
    previous_month,
    risk_turnover,
    short,
    signal_state,
)


TOTAL_COST_RATE = FEE_RATE + SLIPPAGE_RATE
UNIVERSES = {
    "BTC/ETH/DOGE": ["BTCUSDT", "ETHUSDT", "DOGEUSDT"],
    "BTC/ETH only": ["BTCUSDT", "ETHUSDT"],
}
FILTERS = {
    "BTC_EMA200": "BTC EMA200 필터",
    "All_Negative": "전체 약세 필터",
    "Composite": "복합 필터",
}
SIZING_MODES = {
    "Top1_100": "Top1 100%",
    "Top1_70_Cash_30": "Top1 70% / Cash 30%",
    "Top1_50_Cash_50": "Top1 50% / Cash 50%",
    "Top1_70_Top2_30": "Top1 70% / Top2 30%",
    "Top1_50_Top2_50": "Top1 50% / Top2 50%",
    "Top1_50_Top2_30_Cash_20": "Top1 50% / Top2 30% / Cash 20%",
    "DOGE_Cap_50": "DOGE max 50%",
    "DOGE_Cap_30": "DOGE max 30%",
}
EXIT_MODES = {
    "Monthly": "월말 필터만",
    "Emergency": "월중 긴급 방어",
}
PASS_CAGR = 40.0
PASS_MDD = -40.0
PASS_2022 = -25.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON if it covers the required window.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols = sorted({symbol for values in UNIVERSES.values() for symbol in values})
    raw = load_raw(symbols, use_cache=args.use_cache)
    payload = build_payload_from_raw(raw, interval="1d", start=FETCH_START, symbols=symbols)
    data = PositionData(raw=raw, payload=payload)

    results: List[Result] = []
    for universe_name, universe_symbols in UNIVERSES.items():
        for filter_id, filter_label in FILTERS.items():
            for sizing_id, sizing_label in SIZING_MODES.items():
                for exit_id, exit_label in EXIT_MODES.items():
                    results.append(
                        run_position_strategy(
                            data,
                            universe_name,
                            universe_symbols,
                            filter_id,
                            filter_label,
                            sizing_id,
                            sizing_label,
                            exit_id,
                            exit_label,
                        )
                    )

    baseline_2025 = {
        (row.summary["universe"], row.summary["filter"], row.summary["exit_mode"]): row.yearly.get("2025", 0.0)
        for row in results
        if row.summary["sizing"] == "Top1 100%"
    }
    for result in results:
        result.apply_pass_fail(baseline_2025)

    write_csv(output_dir / "strength_rotation_position_sizing_summary.csv", [result.summary for result in results])
    write_csv(output_dir / "strength_rotation_position_sizing_yearly.csv", [result.yearly_row for result in results])
    monthly_rows: List[dict] = []
    for result in results:
        monthly_rows.extend(result.monthly_rows)
    write_csv(output_dir / "strength_rotation_position_sizing_monthly.csv", monthly_rows)

    report = build_report(data, results)
    report_path = output_dir / "strength_rotation_position_sizing_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report_path)


class PositionData(BacktestData):
    def __init__(self, raw: Dict[str, List[dict]], payload: dict):
        super().__init__(raw, payload)
        self.daily_rows = build_daily_rows(raw)
        self.points_by_time = {point["time"]: point for point in payload["points"]}


class Result:
    def __init__(self, summary: dict, monthly_rows: List[dict], yearly: Dict[str, float]):
        self.summary = summary
        self.monthly_rows = monthly_rows
        self.yearly = yearly
        self.yearly_row = {"universe": summary["universe"], "filter": summary["filter"], "sizing": summary["sizing"], "exit_mode": summary["exit_mode"]}
        self.yearly_row.update({str(year): yearly.get(str(year), 0.0) * 100 for year in range(2020, 2026)})

    def apply_pass_fail(self, baseline_2025: Dict[Tuple[str, str, str], float]) -> None:
        baseline = baseline_2025.get((self.summary["universe"], self.summary["filter"], self.summary["exit_mode"]))
        year_2025 = self.yearly.get("2025", 0.0)
        cagr_pass = self.summary["cagr_pct"] >= PASS_CAGR
        mdd_pass = self.summary["mdd_pct"] >= PASS_MDD
        y2022_pass = self.yearly.get("2022", 0.0) * 100 >= PASS_2022
        y2025_improved = baseline is None or year_2025 >= baseline
        self.summary.update(
            {
                "pass_cagr_40": cagr_pass,
                "pass_mdd_40": mdd_pass,
                "pass_2022_minus_25": y2022_pass,
                "pass_2025_improved": y2025_improved,
                "overall_pass": cagr_pass and mdd_pass and y2022_pass and y2025_improved,
                "baseline_2025_pct": baseline * 100 if baseline is not None else None,
            }
        )


def build_daily_rows(raw: Dict[str, List[dict]]) -> Dict[str, Dict[str, List[dict]]]:
    by_symbol: Dict[str, Dict[str, List[dict]]] = {}
    for symbol, candles in raw.items():
        months: Dict[str, List[dict]] = {}
        previous_close = None
        for row in candles:
            daily_return = row["close"] / previous_close - 1 if previous_close else None
            previous_close = row["close"]
            month = month_from_ts(row["time"])
            if TEST_START <= month <= TEST_END and daily_return is not None:
                months.setdefault(month, []).append({**row, "return": daily_return, "month": month})
        by_symbol[symbol] = months
    return by_symbol


def run_position_strategy(
    data: PositionData,
    universe_name: str,
    universe_symbols: List[str],
    filter_id: str,
    filter_label: str,
    sizing_id: str,
    sizing_label: str,
    exit_id: str,
    exit_label: str,
) -> Result:
    equity = 1.0
    current_weights: Dict[str, float] = {"cash": 1.0}
    daily_equity = [{"time": None, "equity": equity}]
    month_end_equity = [{"month": previous_month(data.months[0]), "equity": equity}]
    monthly_rows = []
    total_turnover = 0.0
    total_cost = 0.0
    trades = 0
    emergency_exits = 0

    for month in data.months:
        start_equity = equity
        target, target_meta = monthly_target(data, universe_symbols, month, filter_id, sizing_id)
        target = normalize_weights(target)
        turnover = risk_turnover(current_weights, target)
        if turnover > 1e-12:
            trades += 1
            cost = turnover * TOTAL_COST_RATE
            total_turnover += turnover
            total_cost += equity * cost
            equity *= 1 - cost
            current_weights = dict(target)
        else:
            cost = 0.0

        month_turnover = turnover
        month_cost = cost
        month_emergency = False
        month_active = any(key != "cash" and value > 1e-12 for key, value in current_weights.items())
        locked_cash = False

        for day in month_days(data, universe_symbols, month):
            gross_return = portfolio_daily_return(current_weights, day)
            equity *= 1 + gross_return
            if equity <= 0:
                equity = 0.0
            current_weights = drift_daily_weights(current_weights, day, gross_return)
            daily_equity.append({"time": day["time"], "equity": equity})

            if exit_id == "Emergency" and not locked_cash and should_emergency_exit(data, day["time"]):
                exit_turnover = risk_turnover(current_weights, {"cash": 1.0})
                if exit_turnover > 1e-12:
                    exit_cost = exit_turnover * TOTAL_COST_RATE
                    total_turnover += exit_turnover
                    total_cost += equity * exit_cost
                    month_turnover += exit_turnover
                    month_cost += exit_cost
                    trades += 1
                    emergency_exits += 1
                    month_emergency = True
                    equity *= 1 - exit_cost
                    current_weights = {"cash": 1.0}
                    daily_equity[-1]["equity"] = equity
                locked_cash = True

        month_return = equity / start_equity - 1 if start_equity else 0.0
        month_end_equity.append({"month": month, "equity": equity})
        monthly_rows.append(
            {
                "universe": universe_name,
                "filter": filter_label,
                "sizing": sizing_label,
                "exit_mode": exit_label,
                "month": month,
                "return_pct": month_return * 100,
                "equity": equity,
                "turnover": month_turnover,
                "cost_pct": month_cost * 100,
                "selected": target_meta["selected"],
                "reason": target_meta["reason"],
                "emergency_exit": month_emergency,
                "trade_regime": target_meta.get("trade_regime"),
                "trade_action_bias": target_meta.get("trade_action_bias"),
                "weights": json.dumps({short(k): v for k, v in sorted(target.items()) if abs(v) > 1e-12}, sort_keys=True),
            }
        )
        if not month_active and target_meta["selected"] == "cash":
            current_weights = {"cash": 1.0}

    monthly_returns = [row["return_pct"] / 100 for row in monthly_rows]
    yearly = yearly_returns(monthly_rows)
    worst_year, worst_year_return = min(yearly.items(), key=lambda item: item[1])
    worst_month = min(monthly_rows, key=lambda row: row["return_pct"])
    final_equity = equity
    cagr = final_equity ** (12 / len(data.months)) - 1 if final_equity > 0 else -1.0
    mdd = max_drawdown(daily_equity)
    month_end_mdd = max_drawdown(month_end_equity)
    sharpe = monthly_sharpe(monthly_returns)
    summary = {
        "universe": universe_name,
        "filter": filter_label,
        "sizing": sizing_label,
        "exit_mode": exit_label,
        "total_return_pct": (final_equity - 1) * 100,
        "final_equity": final_equity,
        "cagr_pct": cagr * 100,
        "mdd_pct": mdd * 100,
        "month_end_mdd_pct": month_end_mdd * 100,
        "sharpe": sharpe,
        "calmar": cagr / abs(mdd) if mdd < 0 else None,
        "win_rate_pct": sum(1 for value in monthly_returns if value > 0) / len(monthly_returns) * 100,
        "worst_month": worst_month["month"],
        "worst_month_pct": worst_month["return_pct"],
        "worst_year": worst_year,
        "worst_year_pct": worst_year_return * 100,
        "year_2022_pct": yearly.get("2022", 0.0) * 100,
        "year_2025_pct": yearly.get("2025", 0.0) * 100,
        "trades": trades,
        "emergency_exits": emergency_exits,
        "turnover": total_turnover,
        "avg_monthly_turnover": total_turnover / len(data.months),
        "total_cost_pct_initial_capital": total_cost * 100,
    }
    return Result(summary, monthly_rows, yearly)


def monthly_target(
    data: PositionData,
    universe_symbols: List[str],
    month: str,
    filter_id: str,
    sizing_id: str,
) -> Tuple[Dict[str, float], dict]:
    signal_month = previous_month(month)
    candidates = eligible_candidates(data, universe_symbols, signal_month, month)
    signal = signal_state(data, signal_month)
    if not candidates:
        return {"cash": 1.0}, {"selected": "cash", "reason": "no_candidates", **signal}

    ranked = sorted(candidates, key=lambda symbol: data.monthly_returns[symbol][signal_month], reverse=True)
    all_negative = all(data.monthly_returns[symbol][signal_month] < 0 for symbol in candidates)
    shock = bool(signal["shock_or_no_new_entry"])
    btc_above = bool(signal["btc_above_ema200"])
    filter_blocked = filter_reason(filter_id, btc_above, all_negative, shock)
    if filter_blocked:
        return {"cash": 1.0}, {"selected": "cash", "reason": filter_blocked, **signal, "all_negative": all_negative}

    weights = sizing_weights(ranked, sizing_id)
    return weights, {
        "selected": "+".join(short(symbol) for symbol, weight in weights.items() if symbol != "cash" and weight > 1e-12),
        "reason": "risk_on",
        **signal,
        "all_negative": all_negative,
    }


def filter_reason(filter_id: str, btc_above: bool, all_negative: bool, shock: bool) -> Optional[str]:
    if filter_id == "BTC_EMA200" and not btc_above:
        return "btc_below_ema200"
    if filter_id == "All_Negative" and all_negative:
        return "all_negative"
    if filter_id == "Composite":
        reasons = []
        if not btc_above:
            reasons.append("btc_below_ema200")
        if all_negative:
            reasons.append("all_negative")
        if shock:
            reasons.append("shock")
        if reasons:
            return "+".join(reasons)
    return None


def sizing_weights(ranked: List[str], sizing_id: str) -> Dict[str, float]:
    top1 = ranked[0]
    top2 = ranked[1] if len(ranked) > 1 else None
    if sizing_id == "Top1_100":
        return {top1: 1.0}
    if sizing_id == "Top1_70_Cash_30":
        return {top1: 0.70, "cash": 0.30}
    if sizing_id == "Top1_50_Cash_50":
        return {top1: 0.50, "cash": 0.50}
    if sizing_id == "Top1_70_Top2_30":
        return {top1: 0.70, top2: 0.30} if top2 else {top1: 0.70, "cash": 0.30}
    if sizing_id == "Top1_50_Top2_50":
        return {top1: 0.50, top2: 0.50} if top2 else {top1: 0.50, "cash": 0.50}
    if sizing_id == "Top1_50_Top2_30_Cash_20":
        return {top1: 0.50, top2: 0.30, "cash": 0.20} if top2 else {top1: 0.50, "cash": 0.50}
    if sizing_id == "DOGE_Cap_50":
        return doge_capped_weights(ranked, 0.50)
    if sizing_id == "DOGE_Cap_30":
        return doge_capped_weights(ranked, 0.30)
    raise ValueError(f"Unknown sizing mode: {sizing_id}")


def doge_capped_weights(ranked: List[str], cap: float) -> Dict[str, float]:
    top1 = ranked[0]
    if top1 != "DOGEUSDT":
        return {top1: 1.0}
    fallback = next((symbol for symbol in ranked[1:] if symbol != "DOGEUSDT"), None)
    if not fallback:
        return {"DOGEUSDT": cap, "cash": 1 - cap}
    return {"DOGEUSDT": cap, fallback: 1 - cap}


def month_days(data: PositionData, universe_symbols: Iterable[str], month: str) -> List[dict]:
    btc_days = data.daily_rows["BTCUSDT"].get(month, [])
    days = []
    for btc_day in btc_days:
        row = {"time": btc_day["time"], "returns": {}}
        complete = True
        for symbol in universe_symbols:
            match = next((item for item in data.daily_rows.get(symbol, {}).get(month, []) if item["time"] == btc_day["time"]), None)
            if match is None:
                complete = False
                break
            row["returns"][symbol] = match["return"]
        if complete:
            days.append(row)
    return days


def portfolio_daily_return(weights: Dict[str, float], day: dict) -> float:
    return sum(weight * day["returns"].get(symbol, 0.0) for symbol, weight in weights.items() if symbol != "cash")


def drift_daily_weights(weights: Dict[str, float], day: dict, gross_return: float) -> Dict[str, float]:
    denominator = 1 + gross_return
    if denominator <= 0:
        return {"cash": 1.0}
    drifted = {"cash": weights.get("cash", 0.0) / denominator}
    for symbol, weight in weights.items():
        if symbol == "cash":
            continue
        drifted[symbol] = weight * (1 + day["returns"].get(symbol, 0.0)) / denominator
    return normalize_weights(drifted)


def should_emergency_exit(data: PositionData, timestamp: int) -> bool:
    point = data.points_by_time.get(timestamp, {})
    stable_regime = point.get("stable_regime")
    stable_action_bias = point.get("stable_action_bias")
    close = point.get("close")
    ema200 = point.get("ema200")
    shock = stable_regime == "shock" or stable_action_bias == REGIMES["shock"]["action_bias"]
    btc_below_ema200 = bool(close is not None and ema200 is not None and close < ema200)
    return shock or btc_below_ema200


def yearly_returns(monthly_rows: List[dict]) -> Dict[str, float]:
    yearly: Dict[str, float] = {}
    for row in monthly_rows:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return {year: value - 1 for year, value in yearly.items()}


def max_drawdown(equity_curve: List[dict]) -> float:
    peak = equity_curve[0]["equity"] if equity_curve else 1.0
    mdd = 0.0
    for point in equity_curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, equity / peak - 1)
    return mdd


def monthly_sharpe(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev <= 0:
        return None
    return statistics.mean(returns) / stdev * math.sqrt(12)


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def build_report(data: PositionData, results: List[Result]) -> str:
    rows = [result.summary for result in results]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pass_rows = [row for row in rows if row["overall_pass"]]
    near_rows = [
        row
        for row in rows
        if row["cagr_pct"] >= PASS_CAGR and row["mdd_pct"] >= -45 and row["year_2022_pct"] >= PASS_2022
    ]
    best_rows = sorted(rows, key=lambda row: row["calmar"] or -999, reverse=True)[:15]
    composite_rows = [row for row in rows if row["filter"] == "복합 필터"]
    doge_rows = [row for row in composite_rows if row["universe"] == "BTC/ETH/DOGE"]
    no_doge_rows = [row for row in composite_rows if row["universe"] == "BTC/ETH only"]

    lines = [
        "# Strength Rotation Position Sizing 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        f"- 기간: {TEST_START} ~ {TEST_END}",
        "- 대상: BTC/ETH/DOGE, BTC/ETH only",
        "- 필터: BTC EMA200, 전체 약세, 복합 필터",
        "- 복합 필터: BTC > EMA200, 월말 shock/no_new_entry 아님, 전체 약세 아님",
        "- 월중 긴급 방어: 일봉 종가 기준 stable shock 또는 BTC 종가 < EMA200이면 현금화하고 다음 월말까지 재진입 금지",
        "- 비용: fee 0.10% + slippage 0.05% = 0.15% per traded notional",
        "- MDD는 일봉 mark-to-market equity 기준이다. `month_end_mdd_pct`는 CSV에 별도 제공한다.",
        "- DOGE cap 모드는 Top1이 DOGE일 때 초과분을 다음 순위 비-DOGE 자산에 배분한다. 없으면 현금으로 둔다.",
        "",
        "## 판정 기준",
        "",
        f"- CAGR >= {PASS_CAGR:.0f}%",
        f"- MDD >= {PASS_MDD:.0f}% 즉 낙폭 40% 이내",
        f"- 2022년 수익률 >= {PASS_2022:.0f}%",
        "- 2025년 수익률이 같은 유니버스/필터/exit의 Top1 100%보다 개선",
        "",
        "## 핵심 결론",
        "",
    ]
    lines.extend(key_takeaways(rows))
    lines.extend(
        [
            "",
            "## Overall Pass",
            "",
            metrics_table(pass_rows[:30]) if pass_rows else "판정 기준을 모두 만족한 조합은 없었다.",
            "",
            "## Near Pass",
            "",
            metrics_table(sorted(near_rows, key=lambda row: row["calmar"] or -999, reverse=True)[:20]) if near_rows else "근접 조합도 없었다.",
            "",
            "## Calmar 상위 15",
            "",
            metrics_table(best_rows),
            "",
            "## BTC/ETH/DOGE 복합 필터",
            "",
            metrics_table(sorted(doge_rows, key=lambda row: (row["exit_mode"], row["sizing"]))),
            "",
            "## BTC/ETH only 복합 필터",
            "",
            metrics_table(sorted(no_doge_rows, key=lambda row: (row["exit_mode"], row["sizing"]))),
            "",
            "## 연도별 수익률: 핵심 후보",
            "",
            yearly_focus_table(results),
            "",
            "## 산출물",
            "",
            "- `strength_rotation_position_sizing_summary.csv`",
            "- `strength_rotation_position_sizing_yearly.csv`",
            "- `strength_rotation_position_sizing_monthly.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def key_takeaways(rows: List[dict]) -> List[str]:
    lookup = {(row["universe"], row["filter"], row["sizing"], row["exit_mode"]): row for row in rows}
    main = lookup[("BTC/ETH/DOGE", "복합 필터", "Top1 100%", "월말 필터만")]
    main_emergency = lookup[("BTC/ETH/DOGE", "복합 필터", "Top1 100%", "월중 긴급 방어")]
    no_doge = lookup[("BTC/ETH only", "복합 필터", "Top1 100%", "월말 필터만")]
    best_pass = [row for row in rows if row["overall_pass"]]
    doge_pass = [row for row in best_pass if row["universe"] == "BTC/ETH/DOGE"]
    no_doge_pass = [row for row in best_pass if row["universe"] == "BTC/ETH only"]
    best_by_calmar = max(rows, key=lambda row: row["calmar"] or -999)
    lines = [
        f"- BTC/ETH/DOGE 복합 Top1 100%는 일봉 MDD {main['mdd_pct']:.1f}%, CAGR {main['cagr_pct']:.1f}%다.",
        f"- 같은 조합에 월중 긴급 방어를 넣으면 MDD {main_emergency['mdd_pct']:.1f}%, CAGR {main_emergency['cagr_pct']:.1f}%다.",
        f"- BTC/ETH only 복합 Top1 100%는 MDD {no_doge['mdd_pct']:.1f}%, CAGR {no_doge['cagr_pct']:.1f}%다.",
        f"- Calmar 1위는 {best_by_calmar['universe']} / {best_by_calmar['filter']} / {best_by_calmar['sizing']} / {best_by_calmar['exit_mode']}이며 CAGR {best_by_calmar['cagr_pct']:.1f}%, MDD {best_by_calmar['mdd_pct']:.1f}%다.",
    ]
    if best_pass:
        best = max(best_pass, key=lambda row: row["calmar"] or -999)
        lines.append(
            f"- 판정 기준을 모두 통과한 최고 Calmar 조합은 {best['universe']} / {best['filter']} / {best['sizing']} / {best['exit_mode']}이다."
        )
        lines.append(f"- DOGE 포함 통과 조합은 {len(doge_pass)}개, DOGE 제외 통과 조합은 {len(no_doge_pass)}개다.")
    else:
        lines.append("- CAGR 40%, MDD 40% 이내, 2022 -25% 이내, 2025 개선을 모두 만족한 조합은 없었다.")
    return lines


def metrics_table(rows: List[dict]) -> str:
    headers = ["Universe", "Filter", "Sizing", "Exit", "CAGR", "Total", "MDD", "Sharpe", "Calmar", "2022", "2025", "WorstM", "WorstY", "Trades", "Turnover", "Cost", "Pass"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["universe"],
                    row["filter"],
                    row["sizing"],
                    row["exit_mode"],
                    pct(row["cagr_pct"]),
                    pct(row["total_return_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    pct(row["year_2022_pct"]),
                    pct(row["year_2025_pct"]),
                    f"{row['worst_month']} {row['worst_month_pct']:.1f}%",
                    f"{row['worst_year']} {row['worst_year_pct']:.1f}%",
                    str(row["trades"]),
                    f"{row['turnover']:.2f}",
                    pct(row["total_cost_pct_initial_capital"]),
                    "PASS" if row["overall_pass"] else "",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def yearly_focus_table(results: List[Result]) -> str:
    focus = []
    for result in results:
        row = result.summary
        if row["filter"] == "복합 필터" and row["sizing"] in {
            "Top1 100%",
            "Top1 70% / Cash 30%",
            "Top1 50% / Cash 50%",
            "Top1 70% / Top2 30%",
            "DOGE max 50%",
            "DOGE max 30%",
        }:
            focus.append(result)
    headers = ["Universe", "Sizing", "Exit", "2020", "2021", "2022", "2023", "2024", "2025"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for result in focus:
        row = result.summary
        lines.append(
            "| "
            + " | ".join(
                [
                    row["universe"],
                    row["sizing"],
                    row["exit_mode"],
                    pct(result.yearly.get("2020", 0.0) * 100),
                    pct(result.yearly.get("2021", 0.0) * 100),
                    pct(result.yearly.get("2022", 0.0) * 100),
                    pct(result.yearly.get("2023", 0.0) * 100),
                    pct(result.yearly.get("2024", 0.0) * 100),
                    pct(result.yearly.get("2025", 0.0) * 100),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def pct(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"


def num(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


if __name__ == "__main__":
    main()
