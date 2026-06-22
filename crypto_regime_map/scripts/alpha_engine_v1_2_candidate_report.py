"""Alpha Engine v1.2 candidate report.

Standalone paper-candidate validation for the execution robustness winner:
No DOGE + alpha_score top 20%, with liquidation safety check and optional
symbol leverage caps. Existing Alpha Engine and audit files are not modified.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)
BASE_SLIPPAGE = 0.0020
BASE_FEE = 0.0005
FEE_SENSITIVITY = (0.0010, 0.0020, 0.0030, 0.0050)
ACTUAL_FUNDING = ("actual_funding", "actual funding", "actual")
TEST_YEARS = (2024, 2025)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local OHLCV/funding JSON when available.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = alpha.load_raw(SYMBOLS, "1d", args.use_cache, alpha.FETCH_DAILY_START)
    raw_4h = alpha.load_raw(SYMBOLS, "4h", args.use_cache, alpha.FETCH_INTRADAY_START)
    raw_1h = alpha.load_raw(SYMBOLS, "1h", args.use_cache, alpha.FETCH_INTRADAY_START)
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})

    funding_info = funding.load_funding_info(args.use_cache)
    funding_by_symbol = {
        symbol: funding.load_funding_history(symbol, args.use_cache, funding_info.get(symbol, {}).get("fundingIntervalHours"))
        for symbol in SYMBOLS
    }
    funding_index = rb.build_time_index(funding_by_symbol, time_key="funding_time")

    comparison_variants = build_comparison_variants()
    runs = [
        run_and_evaluate(
            data,
            funding_index,
            variant,
            fee_rate=BASE_FEE,
            slippage_rate=BASE_SLIPPAGE,
            run_group="default",
        )
        for variant in comparison_variants
    ]

    candidate_variants = [
        variant for variant in comparison_variants if variant.name in {"Candidate v1.2 / no leverage cap", "Candidate v1.2 / leverage cap"}
    ]
    cost_runs = [
        run_and_evaluate(
            data,
            funding_index,
            variant,
            fee_rate=fee_rate,
            slippage_rate=BASE_SLIPPAGE,
            run_group="fee_sensitivity",
        )
        for variant in candidate_variants
        for fee_rate in FEE_SENSITIVITY
    ]

    all_rows = [item["summary"] for item in runs + cost_runs]
    default_trades = [trade for item in runs for trade in item["trades"]]
    monthly_rows = [row for item in runs + cost_runs for row in item["monthly"]]
    yearly_rows = [row for item in runs + cost_runs for row in item["yearly"]]
    pass_fail_rows = pass_fail(all_rows, yearly_rows)
    report = build_report(all_rows, default_trades, monthly_rows, yearly_rows, pass_fail_rows)

    report_path = output_dir / "alpha_engine_v1_2_candidate_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "alpha_engine_v1_2_candidate_summary.csv", all_rows)
    write_csv(output_dir / "alpha_engine_v1_2_candidate_trades.csv", default_trades)
    write_csv(output_dir / "alpha_engine_v1_2_candidate_monthly.csv", monthly_rows)
    write_csv(output_dir / "alpha_engine_v1_2_candidate_yearly.csv", yearly_rows)
    print(report_path)


def build_comparison_variants() -> List[rb.RobustVariant]:
    return [
        rb.RobustVariant("Original Alpha Engine v1", group="Comparison"),
        rb.RobustVariant(
            "Conservative v1.1",
            exclude_doge=True,
            use_symbol_leverage_cap=True,
            require_liquidation_buffer=True,
            top_score_pct=0.20,
            max_positions=2,
            group="Comparison",
        ),
        rb.RobustVariant("No DOGE + alpha_score top 20%", exclude_doge=True, top_score_pct=0.20, group="Comparison"),
        rb.RobustVariant(
            "No DOGE + alpha_score top 20% + leverage cap",
            exclude_doge=True,
            top_score_pct=0.20,
            use_symbol_leverage_cap=True,
            group="Comparison",
        ),
        rb.RobustVariant(
            "Candidate v1.2 / no leverage cap",
            exclude_doge=True,
            top_score_pct=0.20,
            require_liquidation_buffer=True,
            group="Candidate",
        ),
        rb.RobustVariant(
            "Candidate v1.2 / leverage cap",
            exclude_doge=True,
            top_score_pct=0.20,
            use_symbol_leverage_cap=True,
            require_liquidation_buffer=True,
            group="Candidate",
        ),
    ]


def run_and_evaluate(
    data: alpha.AlphaData,
    funding_index: Dict[str, Tuple[List[int], List[dict]]],
    variant: rb.RobustVariant,
    fee_rate: float,
    slippage_rate: float,
    run_group: str,
) -> dict:
    config = rb.RunConfig(variant=variant, market_data="spot", slippage_rate=slippage_rate, fee_rate=fee_rate)
    result = rb.run_robust_engine(data, config)
    liq_trades = rb.annotate_liquidation(result.trades, result)
    scenario_key, scenario_name, scenario_value = ACTUAL_FUNDING
    trades, cashflows = rb.annotate_funding_fast(liq_trades, funding_index, scenario_key, scenario_name, scenario_value)
    adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    name = variant.name
    summary = make_summary(name, run_group, config, result, trades, adjusted_curve)
    monthly = monthly_returns(name, run_group, config, adjusted_curve)
    yearly = yearly_returns(name, run_group, monthly)
    return {
        "summary": summary,
        "trades": add_run_metadata(trades, name, run_group, config),
        "monthly": monthly,
        "yearly": yearly,
        "curve": adjusted_curve,
    }


def make_summary(name: str, run_group: str, config: rb.RunConfig, result: rb.RunResult, trades: List[dict], curve: List[dict]) -> dict:
    final_equity = curve[-1]["equity"] if curve else 1.0
    years = (alpha.TEST_END_TS - alpha.TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [curve[index]["equity"] / curve[index - 1]["equity"] - 1 for index in range(1, len(curve)) if curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(365 * 24) if stdev and stdev > 0 else None
    mdd = swing.max_drawdown(curve)
    pnls = [float(trade["pnl_after_funding"]) for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    leverages = [float(trade["actual_leverage"]) for trade in trades]
    hold_days = [float(trade["hold_days"]) for trade in trades]
    symbol_rows = symbol_stats(trades)
    return {
        "variant": name,
        "run_group": run_group,
        "slippage_rate_pct": config.slippage_rate * 100,
        "fee_rate_pct": config.fee_rate * 100,
        "funding": "actual",
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "sharpe": sharpe,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trades": len(trades),
        "avg_hold_days": mean_present(hold_days),
        "median_hold_days": statistics.median(hold_days) if hold_days else None,
        "avg_monthly_trades": len(trades) / len(alpha.MONTHS),
        "avg_leverage": statistics.mean(leverages) if leverages else None,
        "max_leverage": max(leverages) if leverages else None,
        "liquidation_risk_trades": sum(1 for trade in trades if truthy(trade.get("liquidation_risk"))),
        "max_symbol_positive_pnl_share_pct": max((row["positive_pnl_share_pct"] for row in symbol_rows), default=0.0),
        "trades_gte_3x": sum(1 for value in leverages if value >= 3.0),
        "trades_gte_4x": sum(1 for value in leverages if value >= 4.0),
        "skipped_trades": sum(result.skip_counter.values()),
        "skip_reasons": "; ".join(f"{key}:{value}" for key, value in sorted(result.skip_counter.items())),
    }


def monthly_returns(name: str, run_group: str, config: rb.RunConfig, curve: List[dict]) -> List[dict]:
    rows = []
    raw = alpha.monthly_returns_from_curve(name, curve)
    for row in raw:
        rows.append(
            {
                "variant": name,
                "run_group": run_group,
                "slippage_rate_pct": config.slippage_rate * 100,
                "fee_rate_pct": config.fee_rate * 100,
                "month": row["month"],
                "return_pct": row["return_pct"],
            }
        )
    return rows


def yearly_returns(name: str, run_group: str, monthly: List[dict]) -> List[dict]:
    yearly: Dict[str, float] = {}
    for row in monthly:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return [
        {
            "variant": name,
            "run_group": run_group,
            "year": year,
            "return_pct": (value - 1) * 100,
        }
        for year, value in sorted(yearly.items())
    ]


def add_run_metadata(trades: List[dict], name: str, run_group: str, config: rb.RunConfig) -> List[dict]:
    out = []
    for trade in trades:
        out.append(
            {
                **trade,
                "candidate_variant": name,
                "run_group": run_group,
                "run_slippage_rate_pct": config.slippage_rate * 100,
                "run_fee_rate_pct": config.fee_rate * 100,
            }
        )
    return out


def pass_fail(summary_rows: List[dict], yearly_rows: List[dict]) -> List[dict]:
    candidates = [
        row
        for row in summary_rows
        if row["run_group"] == "default" and row["variant"] in {"Candidate v1.2 / no leverage cap", "Candidate v1.2 / leverage cap"}
    ]
    primary = max(candidates, key=lambda row: row["calmar"] or -999)
    oos = {
        int(row["year"]): row
        for row in yearly_rows
        if row["variant"] == primary["variant"] and row["run_group"] == "default" and int(row["year"]) in TEST_YEARS
    }
    severe_oos = [year for year, row in oos.items() if row["return_pct"] <= -20]
    monthly = primary["avg_monthly_trades"]
    return [
        {
            "check": "slippage 0.2% Calmar >= 1.0",
            "result": "PASS" if (primary.get("calmar") or 0.0) >= 1.0 else "FAIL",
            "evidence": f"{primary['variant']} Calmar {primary.get('calmar', 0.0):.2f}",
        },
        {
            "check": "liquidation risk == 0",
            "result": "PASS" if primary.get("liquidation_risk_trades", 999) == 0 else "FAIL",
            "evidence": f"liquidation risk trades {primary.get('liquidation_risk_trades')}",
        },
        {
            "check": "CAGR >= 25%",
            "result": "PASS" if (primary.get("cagr_pct") or 0.0) >= 25 else "FAIL",
            "evidence": f"CAGR {primary.get('cagr_pct', 0.0):.1f}%",
        },
        {
            "check": "MDD within -35%",
            "result": "PASS" if (primary.get("mdd_pct") or -999) >= -35 else "FAIL",
            "evidence": f"MDD {primary.get('mdd_pct', 0.0):.1f}%",
        },
        {
            "check": "2024/2025 severe negative warning",
            "result": "WARNING" if severe_oos else "PASS",
            "evidence": ", ".join(str(year) for year in severe_oos) if severe_oos else "no year <= -20%",
        },
        {
            "check": "monthly trades ideal 5-15",
            "result": "IDEAL" if 5 <= monthly <= 15 else "OUT_OF_RANGE",
            "evidence": f"monthly trades {monthly:.1f}",
        },
        {
            "check": "symbol PnL contribution < 50%",
            "result": "PASS" if (primary.get("max_symbol_positive_pnl_share_pct") or 0.0) < 50 else "WARNING",
            "evidence": f"max positive PnL share {primary.get('max_symbol_positive_pnl_share_pct', 0.0):.1f}%",
        },
    ]


def build_report(summary_rows: List[dict], trades: List[dict], monthly_rows: List[dict], yearly_rows: List[dict], pass_fail_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    default_rows = [row for row in summary_rows if row["run_group"] == "default"]
    fee_rows = [row for row in summary_rows if row["run_group"] == "fee_sensitivity"]
    primary_name = best_candidate(default_rows)["variant"]
    primary_trades = [row for row in trades if row["candidate_variant"] == primary_name and row["run_group"] == "default"]
    primary_monthly = [row for row in monthly_rows if row["variant"] == primary_name and row["run_group"] == "default"]
    primary_yearly = [row for row in yearly_rows if row["variant"] == primary_name and row["run_group"] == "default"]
    lines = [
        "# Alpha Engine v1.2 Candidate 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 후보 조건: DOGE 제외, alpha_score 상위 20%, taker-only 0.05%, actual funding, slippage 0.2%, 동시 보유 최대 3개.",
        "- liquidation safety check는 candidate 변형에 포함했다. 심볼별 leverage cap 적용/미적용을 함께 비교했다.",
        "- 2026 OOS는 현재 Alpha Engine 공통 백테스트 윈도우가 2025-12-31 UTC까지라 산출 가능한 구간이 없다.",
        "",
        "## Pass/Fail",
        "",
        pass_fail_table(pass_fail_rows),
        "",
        "## 기본 비교",
        "",
        summary_table(default_rows),
        "",
        "## 비용 민감도",
        "",
        summary_table(fee_rows),
        "",
        "## 연도별 수익률",
        "",
        yearly_table(primary_yearly),
        "",
        "## 월별 수익률",
        "",
        monthly_table(primary_monthly),
        "",
        "## OOS 2024 / 2025 / 2026 가능 구간",
        "",
        oos_table(primary_yearly),
        "",
        "## 심볼별 성과",
        "",
        symbol_table(symbol_stats(primary_trades)),
        "",
        "## 최악 거래 Top 20",
        "",
        trade_table(sorted(primary_trades, key=lambda row: float(row["pnl_after_funding"]))[:20]),
        "",
        "## 최고 거래 Top 20",
        "",
        trade_table(sorted(primary_trades, key=lambda row: float(row["pnl_after_funding"]), reverse=True)[:20]),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_2_candidate_report.md`",
        "- `alpha_engine_v1_2_candidate_summary.csv`",
        "- `alpha_engine_v1_2_candidate_trades.csv`",
        "- `alpha_engine_v1_2_candidate_monthly.csv`",
        "- `alpha_engine_v1_2_candidate_yearly.csv`",
        "",
    ]
    return "\n".join(lines)


def best_candidate(rows: List[dict]) -> dict:
    candidates = [row for row in rows if row["variant"] in {"Candidate v1.2 / no leverage cap", "Candidate v1.2 / leverage cap"}]
    return max(candidates, key=lambda row: row["calmar"] or -999)


def summary_table(rows: List[dict]) -> str:
    headers = ["Variant", "Fee", "Slip", "CAGR", "MDD", "Calmar", "Sharpe", "PF", "Trades", "Avg hold", "Median hold", "Monthly", "Avg lev", "Max lev", "Liq risk", "Max symbol"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["variant"],
            pct_rate(row["fee_rate_pct"]),
            pct_rate(row["slippage_rate_pct"]),
            pct(row["cagr_pct"]),
            pct(row["mdd_pct"]),
            num(row["calmar"]),
            num(row["sharpe"]),
            num(row["profit_factor"]),
            str(row["trades"]),
            num(row["avg_hold_days"]),
            num(row["median_hold_days"]),
            num(row["avg_monthly_trades"]),
            num(row["avg_leverage"]),
            num(row["max_leverage"]),
            str(row["liquidation_risk_trades"]),
            pct(row["max_symbol_positive_pnl_share_pct"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def pass_fail_table(rows: List[dict]) -> str:
    lines = ["| Check | Result | Evidence |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['check']} | {row['result']} | {row['evidence']} |")
    return "\n".join(lines)


def yearly_table(rows: List[dict]) -> str:
    lines = ["| Year | Return |", "|---|---:|"]
    for row in rows:
        lines.append(f"| {row['year']} | {pct(row['return_pct'])} |")
    return "\n".join(lines)


def monthly_table(rows: List[dict]) -> str:
    lines = ["| Month | Return |", "|---|---:|"]
    for row in rows:
        lines.append(f"| {row['month']} | {pct(row['return_pct'])} |")
    return "\n".join(lines)


def oos_table(rows: List[dict]) -> str:
    lookup = {int(row["year"]): row["return_pct"] for row in rows}
    lines = ["| Segment | Return | Note |", "|---|---:|---|"]
    for year in (2024, 2025):
        value = lookup.get(year)
        note = "warning threshold <= -20%" if value is not None and value <= -20 else ""
        lines.append(f"| {year} | {pct(value)} | {note} |")
    lines.append("| 2026 available |  | current Alpha backtest window ends at 2025-12-31 UTC |")
    return "\n".join(lines)


def symbol_stats(trades: List[dict]) -> List[dict]:
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["symbol"]].append(trade)
    positive_total = sum(max(sum(float(item["pnl_after_funding"]) for item in items), 0.0) for items in grouped.values())
    rows = []
    for symbol, items in grouped.items():
        pnl = sum(float(item["pnl_after_funding"]) for item in items)
        rows.append(
            {
                "symbol": symbol,
                "trades": len(items),
                "pnl": pnl,
                "positive_pnl_share_pct": max(pnl, 0.0) / positive_total * 100 if positive_total > 0 else 0.0,
            }
        )
    return sorted(rows, key=lambda row: row["pnl"], reverse=True)


def symbol_table(rows: List[dict]) -> str:
    lines = ["| Symbol | Trades | PnL | Positive PnL share |", "|---|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['symbol']} | {row['trades']} | {num(row['pnl'])} | {pct(row['positive_pnl_share_pct'])} |")
    return "\n".join(lines)


def trade_table(rows: List[dict]) -> str:
    lines = ["| Symbol | Entry | Exit | Reason | Alpha | PnL | Return | Funding | MAE | MFE |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['entry_date']} | {row['exit_date']} | {row['exit_reason']} | "
            f"{num(row['alpha_score'])} | {num(row['pnl_after_funding'])} | {pct(row['trade_return_after_funding_pct'])} | "
            f"{num(row['funding_pnl'])} | {pct(row['mae_pct'])} | {pct(row['mfe_pct'])} |"
        )
    return "\n".join(lines)


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and value != ""]
    return statistics.mean(clean) if clean else None


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def pct_rate(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def num(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.4f}"


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
