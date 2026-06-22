"""Leverage sensitivity replay for Candidate v1.2.

This report keeps Candidate v1.2 entries and exits fixed from the existing
candidate trade CSV, then replays only the position notional at fixed leverage
levels. It does not modify strategy selection, exits, fees, slippage, or data.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
INITIAL_EQUITY = 1000.0
START_TS = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
END_TS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
SCENARIOS = (1.0, 2.0, 3.0, 5.0)
MAX_POSITION_SLOTS = 3
FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0020
MAINTENANCE_MARGIN_RATE = 0.005
LIQUIDATION_FEE_BUFFER = 0.001
PRIMARY_VARIANT = "Candidate v1.2 / no leverage cap"


SUMMARY_FIELDS = [
    "leverage",
    "initial_equity_usd",
    "final_equity_usd",
    "total_return_pct",
    "cagr_pct",
    "mdd_pct",
    "sharpe",
    "sortino",
    "calmar",
    "profit_factor",
    "win_rate_pct",
    "max_consecutive_losses",
    "trades",
    "bankrupt",
    "margin_call",
    "liquidation_touch_trades",
    "min_equity_usd",
    "max_single_position_exposure_x",
    "max_gross_exposure_x",
]

MONTHLY_FIELDS = ["leverage", "month", "return_pct", "equity_usd"]
YEARLY_FIELDS = ["leverage", "year", "return_pct", "equity_usd"]
CURVE_FIELDS = ["leverage", "time", "date", "equity_usd", "cash_usd", "gross_notional_usd", "gross_exposure_x"]
TRADE_FIELDS = [
    "leverage",
    "trade_index",
    "symbol",
    "entry_date",
    "exit_date",
    "entry_equity_usd",
    "notional_usd",
    "pnl_usd",
    "funding_pnl_usd",
    "net_pnl_usd",
    "return_on_entry_equity_pct",
    "liquidation_price_est",
    "liquidation_touch",
    "margin_call_risk",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = load_candidate_trades(ROOT / "reports" / "alpha_engine_v1_2_candidate_trades.csv")
    rows_1h = load_1h_rows(trades)
    results = [replay_scenario(leverage, trades, rows_1h) for leverage in SCENARIOS]

    write_csv(output_dir / "alpha_engine_v1_2_leverage_sensitivity_summary.csv", [r["summary"] for r in results], SUMMARY_FIELDS)
    write_csv(output_dir / "alpha_engine_v1_2_leverage_sensitivity_monthly.csv", flatten(r["monthly"] for r in results), MONTHLY_FIELDS)
    write_csv(output_dir / "alpha_engine_v1_2_leverage_sensitivity_yearly.csv", flatten(r["yearly"] for r in results), YEARLY_FIELDS)
    write_csv(output_dir / "alpha_engine_v1_2_leverage_sensitivity_equity_curve.csv", flatten(r["curve"] for r in results), CURVE_FIELDS)
    write_csv(output_dir / "alpha_engine_v1_2_leverage_sensitivity_trades.csv", flatten(r["trades"] for r in results), TRADE_FIELDS)

    report = build_report(results)
    report_path = output_dir / "alpha_engine_v1_2_leverage_sensitivity_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report_path)


def load_candidate_trades(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = [
            normalize_trade(row, index)
            for index, row in enumerate(csv.DictReader(f))
            if row.get("variant") == PRIMARY_VARIANT
            and row.get("run_group") == "default"
            and row.get("scenario") == "actual_funding"
        ]
    return sorted(rows, key=lambda row: (row["entry_timestamp"], row["exit_timestamp"], row["trade_index"]))


def normalize_trade(row: dict, index: int) -> dict:
    row = dict(row)
    row["trade_index"] = int(row.get("trade_index") or index)
    for key in [
        "entry_timestamp",
        "exit_timestamp",
        "partial_time",
    ]:
        row[key] = int(float(row[key])) if row.get(key) not in {"", None} else None
    for key in [
        "entry_price",
        "exit_price",
        "stop_price",
        "partial_price",
        "initial_notional",
        "pnl",
        "funding_pnl",
        "pnl_after_funding",
    ]:
        row[key] = float(row[key]) if row.get(key) not in {"", None} else 0.0
    row["symbol_usdt"] = f"{row['symbol']}USDT"
    row["partial_taken"] = truthy(row.get("partial_taken"))
    return row


def load_1h_rows(trades: List[dict]) -> Dict[str, Dict[int, dict]]:
    symbols = sorted({trade["symbol_usdt"] for trade in trades} | {"BTCUSDT"})
    out: Dict[str, Dict[int, dict]] = {}
    for symbol in symbols:
        path = ROOT / "data" / "raw" / f"{symbol}_1h.json"
        if not path.exists():
            out[symbol] = {}
            continue
        import json

        rows = json.loads(path.read_text(encoding="utf-8"))
        out[symbol] = {int(row["time"]): row for row in rows}
    return out


def replay_scenario(leverage: float, trades: List[dict], rows_1h: Dict[str, Dict[int, dict]]) -> dict:
    cash = INITIAL_EQUITY
    positions: Dict[int, dict] = {}
    trade_rows: List[dict] = []
    curve: List[dict] = []
    bankrupt = False
    margin_call = False
    liquidation_touch_count = 0
    max_single_exposure = 0.0
    max_gross_exposure = 0.0

    entries = group_by_time(trades, "entry_timestamp")
    exits = group_by_time(trades, "exit_timestamp")
    partials = group_partials_by_time(trades)
    times = sorted(t for t in rows_1h.get("BTCUSDT", {}) if START_TS <= t < END_TS)
    curve.append(curve_row(leverage, START_TS, cash, cash, 0.0))

    for time in times:
        # Existing engine manages exits before new entries at each timestamp.
        for trade in partials.get(time, []):
            position = positions.get(trade["trade_index"])
            if not position or position["partial_done"]:
                continue
            close_units = position["units"] * 0.5
            proceeds = close_units * trade["partial_price"]
            pnl = close_units * (trade["partial_price"] - position["entry_price"]) - proceeds * FEE_RATE
            cash += pnl
            position["units"] -= close_units
            position["realized_pnl"] += pnl
            position["partial_done"] = True

        for trade in exits.get(time, []):
            position = positions.pop(trade["trade_index"], None)
            if not position:
                continue
            proceeds = position["units"] * trade["exit_price"]
            exit_pnl = position["units"] * (trade["exit_price"] - position["entry_price"]) - proceeds * FEE_RATE
            funding_pnl = scaled_funding_pnl(trade, position["notional"])
            net_pnl = position["realized_pnl"] + exit_pnl + funding_pnl
            cash += exit_pnl + funding_pnl
            trade_rows.append(
                {
                    "leverage": fmt_leverage(leverage),
                    "trade_index": trade["trade_index"],
                    "symbol": trade["symbol"],
                    "entry_date": trade["entry_date"],
                    "exit_date": trade["exit_date"],
                    "entry_equity_usd": position["entry_equity"],
                    "notional_usd": position["notional"],
                    "pnl_usd": position["realized_pnl"] + exit_pnl,
                    "funding_pnl_usd": funding_pnl,
                    "net_pnl_usd": net_pnl,
                    "return_on_entry_equity_pct": net_pnl / position["entry_equity"] * 100 if position["entry_equity"] else 0.0,
                    "liquidation_price_est": position["liquidation_price"],
                    "liquidation_touch": position["liquidation_touch"],
                    "margin_call_risk": position["margin_call_risk"],
                }
            )

        equity_before_entries = account_equity(cash, positions, rows_1h, time)
        for trade in entries.get(time, []):
            if bankrupt or equity_before_entries <= 0:
                bankrupt = True
                continue
            entry_equity = account_equity(cash, positions, rows_1h, time)
            if entry_equity <= 0:
                bankrupt = True
                continue
            notional = entry_equity * leverage / MAX_POSITION_SLOTS
            units = notional / trade["entry_price"] if trade["entry_price"] else 0.0
            entry_fee = notional * FEE_RATE
            cash -= entry_fee
            liquidation_price = liquidation_price_for(trade["entry_price"], leverage)
            liquidation_touch, margin_call_risk = liquidation_flags(trade, liquidation_price, rows_1h)
            liquidation_touch_count += int(liquidation_touch)
            margin_call = margin_call or margin_call_risk
            max_single_exposure = max(max_single_exposure, notional / entry_equity if entry_equity else 0.0)
            positions[trade["trade_index"]] = {
                "symbol": trade["symbol_usdt"],
                "units": units,
                "entry_price": trade["entry_price"],
                "entry_equity": entry_equity,
                "notional": notional,
                "realized_pnl": 0.0,
                "partial_done": False,
                "liquidation_price": liquidation_price,
                "liquidation_touch": liquidation_touch,
                "margin_call_risk": margin_call_risk,
            }

        equity = account_equity(cash, positions, rows_1h, time)
        gross_notional = current_gross_notional(positions, rows_1h, time)
        gross_exposure = gross_notional / equity if equity > 0 else math.inf if gross_notional > 0 else 0.0
        maintenance_required = gross_notional * MAINTENANCE_MARGIN_RATE
        margin_call = margin_call or (gross_notional > 0 and equity <= maintenance_required)
        max_gross_exposure = max(max_gross_exposure, gross_exposure if math.isfinite(gross_exposure) else 999.0)
        curve.append(curve_row(leverage, time, equity, cash, gross_notional))
        if equity <= 0:
            bankrupt = True
            cash = 0.0
            positions.clear()
            curve.append(curve_row(leverage, time, 0.0, 0.0, 0.0))
            break

    final_equity = curve[-1]["equity_usd"]
    summary = summary_row(
        leverage,
        final_equity,
        curve,
        trade_rows,
        bankrupt,
        margin_call,
        liquidation_touch_count,
        max_single_exposure,
        max_gross_exposure,
    )
    return {
        "summary": summary,
        "monthly": period_returns(leverage, curve, "%Y-%m", "month"),
        "yearly": period_returns(leverage, curve, "%Y", "year"),
        "curve": curve,
        "trades": trade_rows,
    }


def account_equity(cash: float, positions: Dict[int, dict], rows_1h: Dict[str, Dict[int, dict]], time: int) -> float:
    equity = cash
    for position in positions.values():
        row = rows_1h.get(position["symbol"], {}).get(time)
        if row:
            equity += position["units"] * (float(row["close"]) - position["entry_price"])
    return equity


def current_gross_notional(positions: Dict[int, dict], rows_1h: Dict[str, Dict[int, dict]], time: int) -> float:
    gross = 0.0
    for position in positions.values():
        row = rows_1h.get(position["symbol"], {}).get(time)
        price = float(row["close"]) if row else position["entry_price"]
        gross += abs(position["units"] * price)
    return gross


def liquidation_flags(trade: dict, liquidation_price: float, rows_1h: Dict[str, Dict[int, dict]]) -> tuple[bool, bool]:
    if liquidation_price <= 0:
        return False, False
    rows = rows_1h.get(trade["symbol_usdt"], {})
    relevant = [
        row
        for time, row in rows.items()
        if trade["entry_timestamp"] <= time < trade["exit_timestamp"]
    ]
    low_touch = any(float(row["low"]) <= liquidation_price for row in relevant)
    gap_touch = any(float(row["open"]) <= liquidation_price for row in relevant)
    stop_after_liq = trade["stop_price"] <= liquidation_price
    return low_touch, bool(gap_touch or stop_after_liq)


def scaled_funding_pnl(trade: dict, notional: float) -> float:
    base_notional = trade["initial_notional"]
    if not base_notional:
        return 0.0
    return trade["funding_pnl"] / base_notional * notional


def liquidation_price_for(entry_price: float, leverage: float) -> float:
    if leverage <= 1:
        return 0.0
    return max(0.0, entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN_RATE + LIQUIDATION_FEE_BUFFER))


def summary_row(
    leverage: float,
    final_equity: float,
    curve: List[dict],
    trades: List[dict],
    bankrupt: bool,
    margin_call: bool,
    liquidation_touch_count: int,
    max_single_exposure: float,
    max_gross_exposure: float,
) -> dict:
    total_return = final_equity / INITIAL_EQUITY - 1
    years = (END_TS - START_TS) / (365.25 * 86400)
    cagr = (final_equity / INITIAL_EQUITY) ** (1 / years) - 1 if final_equity > 0 else -1.0
    mdd = max_drawdown(curve)
    hourly_returns = returns_from_curve(curve)
    sharpe = annualized_sharpe(hourly_returns)
    sortino = annualized_sortino(hourly_returns)
    pnls = [float(row["net_pnl_usd"]) for row in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    return {
        "leverage": fmt_leverage(leverage),
        "initial_equity_usd": INITIAL_EQUITY,
        "final_equity_usd": final_equity,
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": cagr / abs(mdd) if mdd < 0 else "",
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else "",
        "win_rate_pct": len(wins) / len(pnls) * 100 if pnls else 0.0,
        "max_consecutive_losses": max_consecutive_losses(pnls),
        "trades": len(trades),
        "bankrupt": bankrupt,
        "margin_call": margin_call,
        "liquidation_touch_trades": liquidation_touch_count,
        "min_equity_usd": min(row["equity_usd"] for row in curve),
        "max_single_position_exposure_x": max_single_exposure,
        "max_gross_exposure_x": max_gross_exposure,
    }


def period_returns(leverage: float, curve: List[dict], fmt: str, key_name: str) -> List[dict]:
    by_period: Dict[str, dict] = {}
    for row in curve:
        label = datetime.fromtimestamp(row["time"], tz=timezone.utc).strftime(fmt)
        by_period[label] = row
    rows = []
    prev_equity = INITIAL_EQUITY
    for label in sorted(by_period):
        equity = by_period[label]["equity_usd"]
        rows.append(
            {
                "leverage": fmt_leverage(leverage),
                key_name: label,
                "return_pct": (equity / prev_equity - 1) * 100 if prev_equity else 0.0,
                "equity_usd": equity,
            }
        )
        prev_equity = equity
    return rows


def curve_row(leverage: float, time: int, equity: float, cash: float, gross_notional: float) -> dict:
    return {
        "leverage": fmt_leverage(leverage),
        "time": time,
        "date": format_dt(time),
        "equity_usd": equity,
        "cash_usd": cash,
        "gross_notional_usd": gross_notional,
        "gross_exposure_x": gross_notional / equity if equity > 0 else "",
    }


def max_drawdown(curve: List[dict]) -> float:
    peak = curve[0]["equity_usd"] if curve else INITIAL_EQUITY
    mdd = 0.0
    for row in curve:
        equity = row["equity_usd"]
        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, equity / peak - 1)
    return mdd


def returns_from_curve(curve: List[dict]) -> List[float]:
    returns = []
    for previous, current in zip(curve, curve[1:]):
        prev = previous["equity_usd"]
        curr = current["equity_usd"]
        if prev > 0:
            returns.append(curr / prev - 1)
    return returns


def annualized_sharpe(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev <= 0:
        return None
    return statistics.mean(returns) / stdev * math.sqrt(365 * 24)


def annualized_sortino(returns: List[float]) -> Optional[float]:
    downside = [value for value in returns if value < 0]
    if len(downside) < 2:
        return None
    downside_dev = statistics.stdev(downside)
    if downside_dev <= 0:
        return None
    return statistics.mean(returns) / downside_dev * math.sqrt(365 * 24)


def max_consecutive_losses(pnls: Iterable[float]) -> int:
    current = 0
    max_seen = 0
    for pnl in pnls:
        if pnl < 0:
            current += 1
            max_seen = max(max_seen, current)
        else:
            current = 0
    return max_seen


def group_by_time(rows: List[dict], key: str) -> Dict[int, List[dict]]:
    grouped: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            grouped[row[key]].append(row)
    for items in grouped.values():
        items.sort(key=lambda row: row["trade_index"])
    return grouped


def group_partials_by_time(rows: List[dict]) -> Dict[int, List[dict]]:
    grouped: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        if row["partial_taken"] and row.get("partial_time"):
            grouped[row["partial_time"]].append(row)
    for items in grouped.values():
        items.sort(key=lambda row: row["trade_index"])
    return grouped


def build_report(results: List[dict]) -> str:
    summaries = [result["summary"] for result in results]
    recommendation = recommend(summaries)
    lines = [
        "# Alpha Engine v1.2 Leverage Sensitivity Report",
        "",
        f"- 생성 시각: {format_dt(int(datetime.now(timezone.utc).timestamp()))}",
        "- 기준 전략: Candidate v1.2 / no leverage cap",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 초기자본: 1,000 USD",
        "- 거래 기준: 기존 Candidate v1.2 거래 CSV의 진입/청산/부분청산 시점을 고정",
        "- 수수료/슬리피지: taker fee 0.05%, slippage 0.2%",
        "- 레버리지 정의: Candidate v1.2의 동시 보유 한도 3개를 유지하고, 신규 포지션 1개의 초기 notional = 진입 시점 계좌 equity x 시나리오 배율 / 3",
        "- funding: 기존 actual funding PnL을 포지션 notional 비율로 선형 스케일해 청산 시 반영",
        "",
        "## Summary",
        "",
        summary_table(summaries),
        "",
        "## Recommendation",
        "",
        recommendation,
        "",
        "## Monthly Returns",
        "",
        monthly_table(results),
        "",
        "## Annual Returns",
        "",
        yearly_table(results),
        "",
        "## Output Files",
        "",
        "- `reports/alpha_engine_v1_2_leverage_sensitivity_summary.csv`",
        "- `reports/alpha_engine_v1_2_leverage_sensitivity_monthly.csv`",
        "- `reports/alpha_engine_v1_2_leverage_sensitivity_yearly.csv`",
        "- `reports/alpha_engine_v1_2_leverage_sensitivity_equity_curve.csv`",
        "- `reports/alpha_engine_v1_2_leverage_sensitivity_trades.csv`",
    ]
    return "\n".join(lines) + "\n"


def recommend(summaries: List[dict]) -> str:
    viable = [
        row
        for row in summaries
        if not truthy(row["bankrupt"])
        and not truthy(row["margin_call"])
        and float(row["mdd_pct"]) >= -50.0
    ]
    if not viable:
        viable = [row for row in summaries if not truthy(row["bankrupt"])]
    if not viable:
        return "모든 시나리오가 파산 처리되어 추천 레버리지를 제시할 수 없습니다."
    best = max(
        viable,
        key=lambda row: (
            float(row["calmar"] or -999),
            float(row["cagr_pct"]),
            float(row["mdd_pct"]),
        ),
    )
    base = (
        f"수익 대비 MDD 기준으로는 **{best['leverage']}**가 가장 균형적입니다. "
        f"CAGR {pct(best['cagr_pct'])}, MDD {pct(best['mdd_pct'])}, Calmar {num(best['calmar'])}입니다."
    )
    if float(best["mdd_pct"]) < -50.0:
        return base + " 다만 MDD가 -50%를 넘기 때문에 실전 권장이라기보다 네 가지 후보 중 가장 덜 불리한 선택입니다."
    return base


def summary_table(rows: List[dict]) -> str:
    header = (
        "| Lev | Final | Return | CAGR | MDD | Sharpe | Sortino | Calmar | PF | Win | "
        "Max loss streak | Bankrupt | Margin call | Liq touch | Min equity | Max single | Max gross |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|"
    lines = [header, sep]
    for row in rows:
        lines.append(
            f"| {row['leverage']} | ${float(row['final_equity_usd']):,.2f} | {pct(row['total_return_pct'])} | "
            f"{pct(row['cagr_pct'])} | {pct(row['mdd_pct'])} | {num(row['sharpe'])} | {num(row['sortino'])} | "
            f"{num(row['calmar'])} | {num(row['profit_factor'])} | {pct(row['win_rate_pct'])} | "
            f"{row['max_consecutive_losses']} | {row['bankrupt']} | {row['margin_call']} | "
            f"{row['liquidation_touch_trades']} | ${float(row['min_equity_usd']):,.2f} | "
            f"{num(row['max_single_position_exposure_x'])}x | {num(row['max_gross_exposure_x'])}x |"
        )
    return "\n".join(lines)


def monthly_table(results: List[dict]) -> str:
    months = sorted({row["month"] for result in results for row in result["monthly"]})
    by_lev = {result["summary"]["leverage"]: {row["month"]: row for row in result["monthly"]} for result in results}
    lines = ["| Month | " + " | ".join(by_lev) + " |", "|" + "---|" * (len(by_lev) + 1)]
    for month in months:
        values = [pct(by_lev[lev].get(month, {}).get("return_pct", "")) for lev in by_lev]
        lines.append(f"| {month} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def yearly_table(results: List[dict]) -> str:
    years = sorted({row["year"] for result in results for row in result["yearly"]})
    by_lev = {result["summary"]["leverage"]: {row["year"]: row for row in result["yearly"]} for result in results}
    lines = ["| Year | " + " | ".join(by_lev) + " |", "|" + "---|" * (len(by_lev) + 1)]
    for year in years:
        values = [pct(by_lev[lev].get(year, {}).get("return_pct", "")) for lev in by_lev]
        lines.append(f"| {year} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_csv(path: Path, rows: List[dict], fields: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def flatten(groups: Iterable[List[dict]]) -> List[dict]:
    out: List[dict] = []
    for rows in groups:
        out.extend(rows)
    return out


def format_dt(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_leverage(value: float) -> str:
    return f"{value:g}x"


def truthy(value) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def pct(value) -> str:
    if value in {"", None}:
        return "-"
    return f"{float(value):.2f}%"


def num(value) -> str:
    if value in {"", None}:
        return "-"
    return f"{float(value):.4f}"


if __name__ == "__main__":
    main()
