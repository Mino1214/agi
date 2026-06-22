"""Monthly 1M strength rotation defense-filter report.

The script is intentionally standalone: it reads Binance spot OHLCV, rebuilds
the current v4 regime labels in memory, and writes report artifacts under
``crypto_regime_map/reports`` without changing the app runtime code.
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


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from collector import fetch_ohlcv  # noqa: E402
from regime import DEFAULT_SYMBOLS, REGIMES, build_payload_from_raw  # noqa: E402


FETCH_START = "2018-01-01T00:00:00+00:00"
FETCH_END = "2026-01-02T00:00:00+00:00"
TEST_START = "2020-01"
TEST_END = "2025-12"
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005
TOTAL_COST_RATE = FEE_RATE + SLIPPAGE_RATE

UNIVERSES = {
    "BTC/ETH/DOGE": ["BTCUSDT", "ETHUSDT", "DOGEUSDT"],
    "BTC/ETH only": ["BTCUSDT", "ETHUSDT"],
    "BTC/ETH/SOL/BNB/DOGE": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"],
    "BTC/ETH + all top alts": list(DEFAULT_SYMBOLS),
}

VARIANTS = {
    "Top1": "기본 Top 1",
    "Top2": "Top 2 50/50",
    "BTC_EMA200": "BTC EMA200 필터",
    "All_Negative_Cash": "전체 약세 필터",
    "Shock_Cash": "v4 shock/no_new_entry 필터",
    "Composite": "복합 필터",
}

BENCHMARK_UNIVERSE = "Benchmarks"


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
    data = BacktestData(raw=raw, payload=payload)

    rows: List[dict] = []
    monthly_rows: List[dict] = []
    yearly_rows: List[dict] = []

    for universe_name, universe_symbols in UNIVERSES.items():
        for variant_id, variant_label in VARIANTS.items():
            result = run_rotation(data, universe_name, universe_symbols, variant_id, variant_label)
            rows.append(result.summary)
            monthly_rows.extend(result.monthly_rows)
            yearly_rows.append(result.yearly_row)

    benchmark_results = [
        run_static_strategy(data, "BTC Buy & Hold", {"BTCUSDT": 1.0}, rebalance=False),
        run_static_strategy(data, "ETH Buy & Hold", {"ETHUSDT": 1.0}, rebalance=False),
        run_static_strategy(data, "DOGE Buy & Hold", {"DOGEUSDT": 1.0}, rebalance=False),
        run_static_strategy(
            data,
            "BTC/ETH/DOGE Equal Weight Monthly",
            {"BTCUSDT": 1 / 3, "ETHUSDT": 1 / 3, "DOGEUSDT": 1 / 3},
            rebalance=True,
        ),
    ]
    for result in benchmark_results:
        rows.append(result.summary)
        monthly_rows.extend(result.monthly_rows)
        yearly_rows.append(result.yearly_row)

    write_csv(output_dir / "strength_rotation_summary.csv", rows)
    write_csv(output_dir / "strength_rotation_monthly.csv", monthly_rows)
    write_csv(output_dir / "strength_rotation_yearly.csv", yearly_rows)

    report = build_markdown_report(data, rows, yearly_rows)
    (output_dir / "strength_rotation_defense_report.md").write_text(report, encoding="utf-8")
    print(output_dir / "strength_rotation_defense_report.md")


class BacktestData:
    def __init__(self, raw: Dict[str, List[dict]], payload: dict):
        self.raw = raw
        self.payload = payload
        self.months = month_range(TEST_START, TEST_END)
        self.monthly_closes = build_monthly_closes(raw)
        self.monthly_returns = build_monthly_returns(self.monthly_closes)
        self.signal_points = build_signal_points(payload)


class Result:
    def __init__(self, summary: dict, monthly_rows: List[dict], yearly_row: dict):
        self.summary = summary
        self.monthly_rows = monthly_rows
        self.yearly_row = yearly_row


def load_raw(symbols: Iterable[str], use_cache: bool) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    out = {}
    for symbol in symbols:
        cached = read_cache(raw_dir / f"{symbol}_1d.json") if use_cache else []
        if cached and covers_window(cached):
            out[symbol] = cached
        else:
            out[symbol] = fetch_ohlcv(symbol, "1d", FETCH_START, FETCH_END)
    return out


def read_cache(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def covers_window(candles: List[dict]) -> bool:
    if not candles:
        return False
    start_ts = int(datetime.fromisoformat(FETCH_START).timestamp())
    end_ts = int(datetime.fromisoformat("2025-12-31T00:00:00+00:00").timestamp())
    return candles[0]["time"] <= start_ts and candles[-1]["time"] >= end_ts


def build_monthly_closes(raw: Dict[str, List[dict]]) -> Dict[str, Dict[str, dict]]:
    closes: Dict[str, Dict[str, dict]] = {}
    for symbol, candles in raw.items():
        by_month: Dict[str, dict] = {}
        for row in candles:
            month = month_from_ts(row["time"])
            if month not in by_month or row["time"] > by_month[month]["time"]:
                by_month[month] = row
        closes[symbol] = by_month
    return closes


def build_monthly_returns(monthly_closes: Dict[str, Dict[str, dict]]) -> Dict[str, Dict[str, float]]:
    returns: Dict[str, Dict[str, float]] = {}
    for symbol, closes in monthly_closes.items():
        symbol_returns: Dict[str, float] = {}
        for month, row in closes.items():
            previous = previous_month(month)
            previous_row = closes.get(previous)
            if previous_row and previous_row.get("close"):
                symbol_returns[month] = row["close"] / previous_row["close"] - 1
        returns[symbol] = symbol_returns
    return returns


def build_signal_points(payload: dict) -> Dict[str, dict]:
    by_month: Dict[str, dict] = {}
    for point in payload["points"]:
        month = month_from_ts(point["time"])
        if month not in by_month or point["time"] > by_month[month]["time"]:
            by_month[month] = point
    return by_month


def run_rotation(
    data: BacktestData,
    universe_name: str,
    universe_symbols: List[str],
    variant_id: str,
    variant_label: str,
) -> Result:
    def target_fn(month: str, current_weights: Dict[str, float]) -> Tuple[Dict[str, float], dict]:
        signal_month = previous_month(month)
        candidates = eligible_candidates(data, universe_symbols, signal_month, month)
        signal = signal_state(data, signal_month)
        if not candidates:
            return {"cash": 1.0}, {"selected": "cash", "reason": "no_candidates", **signal}

        ranked = sorted(candidates, key=lambda symbol: data.monthly_returns[symbol][signal_month], reverse=True)
        all_negative = all(data.monthly_returns[symbol][signal_month] < 0 for symbol in candidates)
        shock = bool(signal["shock_or_no_new_entry"])
        btc_above = bool(signal["btc_above_ema200"])

        if variant_id == "Top2":
            top = ranked[:2]
            weight = 1 / len(top)
            return {symbol: weight for symbol in top}, {
                "selected": "+".join(short(symbol) for symbol in top),
                "reason": "top2",
                **signal,
                "all_negative": all_negative,
            }
        if variant_id == "BTC_EMA200" and not btc_above:
            return {"cash": 1.0}, {"selected": "cash", "reason": "btc_below_ema200", **signal, "all_negative": all_negative}
        if variant_id == "All_Negative_Cash" and all_negative:
            return {"cash": 1.0}, {"selected": "cash", "reason": "all_negative", **signal, "all_negative": all_negative}
        if variant_id == "Shock_Cash" and shock:
            return {"cash": 1.0}, {"selected": "cash", "reason": "shock", **signal, "all_negative": all_negative}
        if variant_id == "Composite" and (not btc_above or shock or all_negative):
            reasons = []
            if not btc_above:
                reasons.append("btc_below_ema200")
            if shock:
                reasons.append("shock")
            if all_negative:
                reasons.append("all_negative")
            return {"cash": 1.0}, {"selected": "cash", "reason": "+".join(reasons), **signal, "all_negative": all_negative}

        selected = ranked[0]
        return {selected: 1.0}, {
            "selected": short(selected),
            "reason": "top1",
            **signal,
            "all_negative": all_negative,
        }

    return run_monthly_strategy(data, universe_name, variant_label, target_fn)


def run_static_strategy(data: BacktestData, label: str, weights: Dict[str, float], rebalance: bool) -> Result:
    def target_fn(month: str, current_weights: Dict[str, float]) -> Tuple[Dict[str, float], dict]:
        if not rebalance and any(current_weights.get(symbol, 0.0) > 0 for symbol in weights):
            return dict(current_weights), {"selected": label, "reason": "hold"}
        return dict(weights), {"selected": label, "reason": "static"}

    return run_monthly_strategy(data, BENCHMARK_UNIVERSE, label, target_fn)


def run_monthly_strategy(
    data: BacktestData,
    universe_name: str,
    label: str,
    target_fn: Callable[[str, Dict[str, float]], Tuple[Dict[str, float], dict]],
) -> Result:
    equity = 1.0
    current_weights: Dict[str, float] = {"cash": 1.0}
    records = []
    equity_curve = [{"month": previous_month(data.months[0]), "equity": equity}]
    total_turnover = 0.0
    total_cost = 0.0
    trades = 0

    for month in data.months:
        target, meta = target_fn(month, current_weights)
        target = normalize_weights(target)
        turnover = risk_turnover(current_weights, target)
        trading_cost_rate = turnover * TOTAL_COST_RATE
        if turnover > 1e-12:
            trades += 1
        total_turnover += turnover
        total_cost += equity * trading_cost_rate

        gross_return = portfolio_return(data, target, month)
        start_equity = equity
        equity = equity * (1 - trading_cost_rate) * (1 + gross_return)
        net_return = equity / start_equity - 1

        records.append(
            {
                "universe": universe_name,
                "variant": label,
                "month": month,
                "return": net_return,
                "gross_return": gross_return,
                "equity": equity,
                "turnover": turnover,
                "cost_rate": trading_cost_rate,
                "selected": meta.get("selected", ""),
                "reason": meta.get("reason", ""),
                "btc_above_ema200": meta.get("btc_above_ema200"),
                "shock_or_no_new_entry": meta.get("shock_or_no_new_entry"),
                "all_negative": meta.get("all_negative"),
                "trade_regime": meta.get("trade_regime"),
                "trade_action_bias": meta.get("trade_action_bias"),
                "weights": json.dumps({short(k): v for k, v in sorted(target.items()) if abs(v) > 1e-12}, sort_keys=True),
            }
        )
        equity_curve.append({"month": month, "equity": equity})
        current_weights = drift_weights(data, target, month, gross_return)

    metrics = metric_row(records, equity_curve, total_turnover, total_cost, trades)
    summary = {"universe": universe_name, "variant": label, **metrics}
    monthly_rows = [
        {
            **{key: row[key] for key in ("universe", "variant", "month", "selected", "reason", "weights", "trade_regime", "trade_action_bias")},
            "return_pct": row["return"] * 100,
            "gross_return_pct": row["gross_return"] * 100,
            "turnover": row["turnover"],
            "cost_pct": row["cost_rate"] * 100,
            "equity": row["equity"],
            "btc_above_ema200": row["btc_above_ema200"],
            "shock_or_no_new_entry": row["shock_or_no_new_entry"],
            "all_negative": row["all_negative"],
        }
        for row in records
    ]
    yearly = yearly_returns(records)
    yearly_row = {"universe": universe_name, "variant": label}
    yearly_row.update({str(year): yearly.get(str(year), 0.0) * 100 for year in range(2020, 2026)})
    return Result(summary=summary, monthly_rows=monthly_rows, yearly_row=yearly_row)


def eligible_candidates(data: BacktestData, symbols: List[str], signal_month: str, return_month: str) -> List[str]:
    return [
        symbol
        for symbol in symbols
        if signal_month in data.monthly_returns.get(symbol, {})
        and return_month in data.monthly_returns.get(symbol, {})
    ]


def signal_state(data: BacktestData, signal_month: str) -> dict:
    point = data.signal_points.get(signal_month, {})
    trade_regime = point.get("trade_regime")
    trade_action_bias = point.get("trade_action_bias")
    if not trade_action_bias and trade_regime:
        trade_action_bias = REGIMES.get(trade_regime, {}).get("action_bias")
    close = point.get("close")
    ema200 = point.get("ema200")
    return {
        "btc_above_ema200": bool(close is not None and ema200 is not None and close > ema200),
        "shock_or_no_new_entry": bool(trade_regime == "shock" or trade_action_bias == "no_new_entry"),
        "trade_regime": trade_regime,
        "trade_action_bias": trade_action_bias,
    }


def portfolio_return(data: BacktestData, weights: Dict[str, float], month: str) -> float:
    total = 0.0
    for symbol, weight in weights.items():
        if symbol == "cash":
            continue
        total += weight * data.monthly_returns.get(symbol, {}).get(month, 0.0)
    return total


def drift_weights(data: BacktestData, weights: Dict[str, float], month: str, gross_return: float) -> Dict[str, float]:
    denominator = 1 + gross_return
    if denominator <= 0:
        return {"cash": 1.0}
    drifted = {"cash": weights.get("cash", 0.0) / denominator}
    for symbol, weight in weights.items():
        if symbol == "cash":
            continue
        asset_return = data.monthly_returns.get(symbol, {}).get(month, 0.0)
        drifted[symbol] = weight * (1 + asset_return) / denominator
    return normalize_weights(drifted)


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    clean = {key: max(0.0, float(value or 0.0)) for key, value in weights.items()}
    total = sum(clean.values())
    if total <= 0:
        return {"cash": 1.0}
    normalized = {key: value / total for key, value in clean.items() if value > 1e-12}
    if "cash" not in normalized:
        normalized["cash"] = 0.0
    return normalized


def risk_turnover(current: Dict[str, float], target: Dict[str, float]) -> float:
    symbols = set(current) | set(target)
    symbols.discard("cash")
    return sum(abs(target.get(symbol, 0.0) - current.get(symbol, 0.0)) for symbol in symbols)


def metric_row(records: List[dict], equity_curve: List[dict], total_turnover: float, total_cost: float, trades: int) -> dict:
    returns = [row["return"] for row in records]
    final_equity = equity_curve[-1]["equity"] if equity_curve else 1.0
    total_return = final_equity - 1
    cagr = final_equity ** (12 / len(records)) - 1 if records and final_equity > 0 else None
    mdd = max_drawdown(equity_curve)
    sharpe = annualized_monthly_sharpe(returns)
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    return {
        "total_return_pct": total_return * 100,
        "final_equity": final_equity,
        "cagr_pct": none_or_pct(cagr),
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "win_rate_pct": sum(1 for value in returns if value > 0) / len(returns) * 100 if returns else 0.0,
        "trades": trades,
        "turnover": total_turnover,
        "avg_monthly_turnover": total_turnover / len(records) if records else 0.0,
        "total_cost_pct_initial_capital": total_cost * 100,
        "active_months": sum(1 for row in records if '"cash": 1.0' not in row["weights"]),
    }


def annualized_monthly_sharpe(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev <= 0:
        return None
    return statistics.mean(returns) / stdev * math.sqrt(12)


def max_drawdown(equity_curve: List[dict]) -> float:
    peak = equity_curve[0]["equity"] if equity_curve else 1.0
    mdd = 0.0
    for point in equity_curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, equity / peak - 1)
    return mdd


def yearly_returns(records: List[dict]) -> Dict[str, float]:
    by_year: Dict[str, float] = {}
    for row in records:
        year = row["month"][:4]
        by_year.setdefault(year, 1.0)
        by_year[year] *= 1 + row["return"]
    return {year: value - 1 for year, value in by_year.items()}


def month_range(start: str, end: str) -> List[str]:
    start_year, start_month = [int(part) for part in start.split("-")]
    end_year, end_month = [int(part) for part in end.split("-")]
    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def previous_month(month: str) -> str:
    year, month_number = [int(part) for part in month.split("-")]
    if month_number == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month_number - 1:02d}"


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def short(symbol: str) -> str:
    return symbol.replace("USDT", "")


def none_or_pct(value: Optional[float]) -> Optional[float]:
    return value * 100 if value is not None else None


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown_report(data: BacktestData, rows: List[dict], yearly_rows: List[dict]) -> str:
    strategy_rows = [row for row in rows if row["universe"] != BENCHMARK_UNIVERSE]
    benchmark_rows = [row for row in rows if row["universe"] == BENCHMARK_UNIVERSE]
    main_rows = [row for row in strategy_rows if row["universe"] == "BTC/ETH/DOGE"]
    base_by_universe = [row for row in strategy_rows if row["variant"] == VARIANTS["Top1"]]
    composite_by_universe = [row for row in strategy_rows if row["variant"] == VARIANTS["Composite"]]
    best_by_calmar = sorted(strategy_rows, key=lambda row: row.get("calmar") or -999, reverse=True)[:10]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# ETH/BTC Strength Rotation 방어 필터 비교 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        f"- 기간: {TEST_START} ~ {TEST_END}, 월말 UTC 종가 기준",
        "- 데이터: Binance Spot `1d` klines, `USDT` 페어",
        f"- 비용: fee {FEE_RATE * 100:.2f}% + slippage {SLIPPAGE_RATE * 100:.2f}% = {TOTAL_COST_RATE * 100:.2f}% per traded notional",
        "- 성과 지표는 모두 비용 반영 후 수치다. 현금 수익률은 0%로 둔다.",
        "- MDD는 월말 equity 기준이다. 일중/월중 낙폭은 반영하지 않는다.",
        "- `v4 shock/no_new_entry`는 신호월 말의 `trade_regime == shock` 또는 `trade_action_bias == no_new_entry`로 판정한다.",
        "- `전체 상위 알트 후보`는 현재 프로젝트 기본 유니버스인 BTC/ETH/SOL/BNB/XRP/DOGE/LINK/AVAX/ADA/TON이다. 상장 전 월은 후보에서 제외한다.",
        "",
        "## 데이터 커버리지",
        "",
        "| Symbol | First day | Last day | Candles |",
        "|---|---:|---:|---:|",
    ]
    for symbol in sorted(data.raw):
        candles = data.raw[symbol]
        first = datetime.fromtimestamp(candles[0]["time"], timezone.utc).date().isoformat() if candles else ""
        last = datetime.fromtimestamp(candles[-1]["time"], timezone.utc).date().isoformat() if candles else ""
        lines.append(f"| {short(symbol)} | {first} | {last} | {len(candles)} |")

    lines.extend(
        [
            "",
            "## 핵심 판정",
            "",
        ]
    )
    lines.extend(key_judgement_lines(strategy_rows, yearly_rows))

    lines.extend(
        [
            "",
            "## BTC/ETH/DOGE 메인 후보: 방어 필터 비교",
            "",
            metrics_table(main_rows),
            "",
            "## 유니버스별 기본 Top1 vs 복합 필터",
            "",
            universe_comparison_table(base_by_universe, composite_by_universe),
            "",
            "## Calmar 상위 10개 전략",
            "",
            metrics_table(best_by_calmar),
            "",
            "## 벤치마크",
            "",
            metrics_table(benchmark_rows),
            "",
            "## 연도별 수익률",
            "",
            yearly_table(yearly_rows),
            "",
            "## 산출물",
            "",
            "- `strength_rotation_summary.csv`: 전체 요약 지표",
            "- `strength_rotation_yearly.csv`: 전체 연도별 수익률",
            "- `strength_rotation_monthly.csv`: 전체 월별 수익률, 선택 자산, 필터 사유, turnover",
            "",
        ]
    )
    return "\n".join(lines)


def key_judgement_lines(strategy_rows: List[dict], yearly_rows: List[dict]) -> List[str]:
    lookup = {(row["universe"], row["variant"]): row for row in strategy_rows}
    yearly = {(row["universe"], row["variant"]): row for row in yearly_rows}
    main_base = lookup[("BTC/ETH/DOGE", VARIANTS["Top1"])]
    main_composite = lookup[("BTC/ETH/DOGE", VARIANTS["Composite"])]
    doge_ex_base = lookup[("BTC/ETH only", VARIANTS["Top1"])]
    doge_ex_composite = lookup[("BTC/ETH only", VARIANTS["Composite"])]
    mdd_reduction = abs(main_base["mdd_pct"]) - abs(main_composite["mdd_pct"])
    cagr_retention = main_composite["cagr_pct"] / main_base["cagr_pct"] if main_base["cagr_pct"] else None
    base_2022 = yearly[("BTC/ETH/DOGE", VARIANTS["Top1"])]["2022"]
    comp_2022 = yearly[("BTC/ETH/DOGE", VARIANTS["Composite"])]["2022"]
    base_2025 = yearly[("BTC/ETH/DOGE", VARIANTS["Top1"])]["2025"]
    comp_2025 = yearly[("BTC/ETH/DOGE", VARIANTS["Composite"])]["2025"]
    return [
        f"- 메인 BTC/ETH/DOGE Top1의 MDD는 {main_base['mdd_pct']:.1f}%이고, 복합 필터는 {main_composite['mdd_pct']:.1f}%다. 월말 기준 MDD를 {mdd_reduction:.1f}%p 줄였다.",
        f"- CAGR은 Top1 {main_base['cagr_pct']:.1f}%에서 복합 필터 {main_composite['cagr_pct']:.1f}%로 변했다. 유지율은 {cagr_retention * 100:.1f}%다.",
        f"- 2022년은 Top1 {base_2022:.1f}%에서 복합 필터 {comp_2022:.1f}%로 개선됐다.",
        f"- 2025년은 Top1 {base_2025:.1f}%에서 복합 필터 {comp_2025:.1f}%로 변했다.",
        f"- DOGE 제외 BTC/ETH only Top1은 CAGR {doge_ex_base['cagr_pct']:.1f}%, MDD {doge_ex_base['mdd_pct']:.1f}%다. 복합 필터는 CAGR {doge_ex_composite['cagr_pct']:.1f}%, MDD {doge_ex_composite['mdd_pct']:.1f}%다.",
    ]


def metrics_table(rows: List[dict]) -> str:
    headers = [
        "Universe",
        "Variant",
        "Total",
        "CAGR",
        "MDD",
        "Sharpe",
        "Calmar",
        "Win",
        "Trades",
        "Turnover",
        "Cost",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["universe"],
                    row["variant"],
                    pct_value(row["total_return_pct"]),
                    pct_value(row["cagr_pct"]),
                    pct_value(row["mdd_pct"]),
                    number(row["sharpe"]),
                    number(row["calmar"]),
                    pct_value(row["win_rate_pct"]),
                    str(row["trades"]),
                    f"{row['turnover']:.2f}",
                    pct_value(row["total_cost_pct_initial_capital"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def universe_comparison_table(base_rows: List[dict], composite_rows: List[dict]) -> str:
    composite = {row["universe"]: row for row in composite_rows}
    lines = [
        "| Universe | Top1 CAGR | Top1 MDD | Composite CAGR | Composite MDD | MDD 개선 | CAGR 유지율 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for base in base_rows:
        comp = composite[base["universe"]]
        mdd_improvement = abs(base["mdd_pct"]) - abs(comp["mdd_pct"])
        cagr_retention = comp["cagr_pct"] / base["cagr_pct"] * 100 if base["cagr_pct"] else None
        lines.append(
            f"| {base['universe']} | {pct_value(base['cagr_pct'])} | {pct_value(base['mdd_pct'])} | "
            f"{pct_value(comp['cagr_pct'])} | {pct_value(comp['mdd_pct'])} | "
            f"{mdd_improvement:.1f}%p | {pct_value(cagr_retention)} |"
        )
    return "\n".join(lines)


def yearly_table(rows: List[dict]) -> str:
    headers = ["Universe", "Variant", "2020", "2021", "2022", "2023", "2024", "2025"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["universe"],
                    row["variant"],
                    pct_value(row["2020"]),
                    pct_value(row["2021"]),
                    pct_value(row["2022"]),
                    pct_value(row["2023"]),
                    pct_value(row["2024"]),
                    pct_value(row["2025"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def pct_value(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"


def number(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


if __name__ == "__main__":
    main()
