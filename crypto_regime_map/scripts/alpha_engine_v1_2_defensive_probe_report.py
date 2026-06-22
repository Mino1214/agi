"""V0 vs defensive_probe V1 comparison for Alpha Engine v1.2."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_candidate_report as candidate  # noqa: E402
import alpha_engine_v1_2_defensive_probe as defensive_probe_rules  # noqa: E402
import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402
import btc_eth_monthly_strength_v1_swing_entry_report as swing  # noqa: E402


SYMBOLS = tuple(alpha.UNIVERSE_10)


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

    runs = [
        run_variant(data, funding_index, v0_variant()),
        run_variant(data, funding_index, v1_variant()),
    ]
    summary_rows = build_summary_rows(runs)
    probe_log_rows = runs[1]["result"].probe_log

    report_path = output_dir / "alpha_engine_v1_2_defensive_probe_comparison.md"
    summary_path = output_dir / "alpha_engine_v1_2_defensive_probe_summary.csv"
    log_path = output_dir / "alpha_engine_v1_2_defensive_probe_log.csv"

    report_path.write_text(build_report(summary_rows, probe_log_rows), encoding="utf-8")
    write_csv(summary_path, summary_rows)
    write_csv(log_path, probe_log_rows, defensive_probe_rules.PROBE_LOG_FIELDS)
    print(report_path)


def v0_variant() -> rb.RobustVariant:
    return rb.RobustVariant(
        "V0 Candidate v1.2",
        exclude_doge=True,
        top_score_pct=candidate.TOP_SCORE_PCT if hasattr(candidate, "TOP_SCORE_PCT") else 0.20,
        require_liquidation_buffer=True,
        group="V0",
    )


def v1_variant() -> rb.RobustVariant:
    return rb.RobustVariant(
        "V1 defensive_probe",
        exclude_doge=True,
        top_score_pct=candidate.TOP_SCORE_PCT if hasattr(candidate, "TOP_SCORE_PCT") else 0.20,
        require_liquidation_buffer=True,
        defensive_probe=True,
        group="V1",
    )


def run_variant(data: alpha.AlphaData, funding_index: dict, variant: rb.RobustVariant) -> dict:
    config = rb.RunConfig(
        variant=variant,
        market_data="spot",
        slippage_rate=candidate.BASE_SLIPPAGE,
        fee_rate=candidate.BASE_FEE,
    )
    result = rb.run_robust_engine(data, config)
    liq_trades = rb.annotate_liquidation(result.trades, result)
    trades, cashflows = rb.annotate_funding_fast(liq_trades, funding_index, "actual_funding", "actual funding", "actual")
    adjusted_curve = funding.adjusted_equity_curve(result.equity_curve, cashflows)
    return {"variant": variant.name, "config": config, "result": result, "trades": trades, "curve": adjusted_curve}


def build_summary_rows(runs: List[dict]) -> List[dict]:
    base_metrics = metrics(runs[0])
    rows = []
    for run in runs:
        row = metrics(run)
        row["additional_return_vs_v0_pct"] = row["total_return_pct"] - base_metrics["total_return_pct"]
        row["additional_mdd_vs_v0_pct"] = row["mdd_pct"] - base_metrics["mdd_pct"]
        rows.append(row)
    return rows


def metrics(run: dict) -> dict:
    trades = run["trades"]
    curve = run["curve"]
    final_equity = curve[-1]["equity"] if curve else 1.0
    pnls = [float(trade["pnl_after_funding"]) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    defensive_trades = [trade for trade in trades if is_defensive_trade(trade)]
    defensive_pnls = [float(trade["pnl_after_funding"]) for trade in defensive_trades]
    return {
        "variant": run["variant"],
        "fee_rate_pct": run["config"].fee_rate * 100,
        "slippage_rate_pct": run["config"].slippage_rate * 100,
        "total_return_pct": (final_equity - 1) * 100,
        "mdd_pct": swing.max_drawdown(curve) * 100,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "trade_count": len(trades),
        "defensive_entry_count": len(defensive_trades),
        "defensive_entry_return_pct": sum(defensive_pnls) * 100,
        "defensive_entry_loss_rate_pct": len([pnl for pnl in defensive_pnls if pnl < 0]) / len(defensive_pnls) * 100 if defensive_pnls else 0.0,
        "max_consecutive_losses": max_consecutive_losses(trades),
        "average_r": mean_present(r_multiple(trade) for trade in trades),
    }


def is_defensive_trade(trade: dict) -> bool:
    return str(trade.get("trade_regime", "")).lower() == "defensive" or str(trade.get("trade_action_bias", "")).lower() == "reduce_risk"


def max_consecutive_losses(trades: List[dict]) -> int:
    max_count = 0
    current = 0
    for trade in sorted(trades, key=lambda item: int(item.get("exit_timestamp") or 0)):
        if float(trade.get("pnl_after_funding") or 0.0) < 0:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def r_multiple(trade: dict) -> Optional[float]:
    risk_pct = float(trade.get("risk_distance_pct") or 0.0) / 100
    initial_risk = float(trade.get("initial_units") or 0.0) * float(trade.get("entry_price") or 0.0) * risk_pct
    if initial_risk <= 0:
        return None
    return float(trade.get("pnl_after_funding") or 0.0) / initial_risk


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    return statistics.mean(clean) if clean else None


def build_report(summary_rows: List[dict], probe_log_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Alpha Engine v1.2 Defensive Probe 비교 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 공통 비용: taker-only 0.05%, slippage 0.2%, actual funding.",
        "- V0: 기존 v1.2 candidate 조건(DOGE 제외, alpha_score top 20%, liquidation buffer).",
        "- V1: V0 유지 + defensive에서 score 85점 환산 이상, relative strength 통과, BTC panic 아님일 때 1개만 25% 사이즈 probe.",
        "",
        "## Summary",
        "",
        summary_table(summary_rows),
        "",
        "## Probe Log Summary",
        "",
        probe_log_table(probe_log_rows),
        "",
        "## 산출물",
        "",
        "- `alpha_engine_v1_2_defensive_probe_comparison.md`",
        "- `alpha_engine_v1_2_defensive_probe_summary.csv`",
        "- `alpha_engine_v1_2_defensive_probe_log.csv`",
        "",
    ]
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = ["Variant", "Return", "MDD", "Win", "PF", "Trades", "Def entries", "Def return", "Def loss", "Max losses", "Avg R", "Extra return", "Extra MDD"]
    keys = [
        "variant",
        "total_return_pct",
        "mdd_pct",
        "win_rate_pct",
        "profit_factor",
        "trade_count",
        "defensive_entry_count",
        "defensive_entry_return_pct",
        "defensive_entry_loss_rate_pct",
        "max_consecutive_losses",
        "average_r",
        "additional_return_vs_v0_pct",
        "additional_mdd_vs_v0_pct",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [format_value(row.get(key), percent=key.endswith("_pct")) for key in keys]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def probe_log_table(rows: List[dict]) -> str:
    total = len(rows)
    passed = len([row for row in rows if defensive_probe_rules.truthy(row.get("probe_can_enter"))])
    reasons = {}
    for row in rows:
        reason = row.get("block_reason") or row.get("probe_reason") or "passed"
        reasons[reason] = reasons.get(reason, 0) + 1
    reason_text = ", ".join(f"{key}:{value}" for key, value in sorted(reasons.items()))
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| evaluated defensive candidates | {total} |",
            f"| probe entries allowed | {passed} |",
            f"| reasons | {reason_text} |",
        ]
    )


def format_value(value, percent: bool = False) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    suffix = "%" if percent else ""
    return f"{float(value):.2f}{suffix}"


def write_csv(path: Path, rows: List[dict], fieldnames: Optional[List[str]] = None) -> None:
    fieldnames = fieldnames or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if fieldnames:
            writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
