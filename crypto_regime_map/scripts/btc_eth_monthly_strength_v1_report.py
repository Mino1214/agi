"""BTC/ETH Monthly Strength v1 precision validation report.

The report is a standalone research artifact. It uses Binance spot daily
klines, evaluates complete UTC calendar months, and does not change runtime
application code.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from collector import fetch_ohlcv  # noqa: E402
from indicators import ema  # noqa: E402
from regime import REGIMES, build_payload_from_raw  # noqa: E402


FETCH_START = "2018-01-01T00:00:00+00:00"
FETCH_END = "2026-01-02T00:00:00+00:00"
TEST_START = "2020-01"
TEST_END = "2025-12"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
BASE_COST_RATE = 0.001
BASE_EMA_PERIOD = 200
BASE_LOOKBACK_MONTHS = 1
BASE_CASH_WEIGHT = 0.20


@dataclass
class StrengthConfig:
    name: str
    ema_period: int = BASE_EMA_PERIOD
    lookback_months: int = BASE_LOOKBACK_MONTHS
    cash_weight: float = BASE_CASH_WEIGHT
    cost_rate: float = BASE_COST_RATE
    emergency_defense: bool = True
    use_ema_filter: bool = True
    top1_share_of_risk: float = 0.625
    top2_share_of_risk: float = 0.375
    group: str = "Strategy"


@dataclass
class StaticConfig:
    name: str
    weights: Dict[str, float]
    cost_rate: float = BASE_COST_RATE
    rebalance_monthly: bool = False
    group: str = "Benchmark"


@dataclass
class StrategyResult:
    name: str
    summary: dict
    monthly_rows: List[dict]
    yearly_returns: Dict[str, float]
    daily_equity: List[dict]
    drawdown: dict


class BacktestData:
    def __init__(self, raw: Dict[str, List[dict]], payload: dict):
        self.raw = raw
        self.payload = payload
        self.months = month_range(TEST_START, TEST_END)
        self.daily_rows = build_daily_rows(raw)
        self.monthly_closes = build_monthly_closes(raw)
        self.points_by_time = {point["time"]: point for point in payload["points"]}
        self.ema_by_period: Dict[int, Dict[int, Optional[float]]] = {}

    def btc_ema_by_time(self, period: int) -> Dict[int, Optional[float]]:
        if period not in self.ema_by_period:
            candles = self.raw["BTCUSDT"]
            values = ema([row["close"] for row in candles], period)
            self.ema_by_period[period] = {row["time"]: value for row, value in zip(candles, values)}
        return self.ema_by_period[period]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON only if it covers the warmup window.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = load_raw(SYMBOLS, use_cache=args.use_cache)
    payload = build_payload_from_raw(raw, interval="1d", start=FETCH_START, symbols=SYMBOLS)
    data = BacktestData(raw=raw, payload=payload)

    base = run_strength_strategy(data, base_config())
    no_emergency = run_strength_strategy(
        data,
        StrengthConfig(
            name="BTC/ETH Top1 50 / Top2 30 / Cash 20 without emergency defense",
            emergency_defense=False,
            group="Benchmark",
        ),
    )
    benchmarks = [
        run_static_strategy(data, StaticConfig(name="BTC Buy & Hold", weights={"BTCUSDT": 1.0})),
        run_static_strategy(data, StaticConfig(name="ETH Buy & Hold", weights={"ETHUSDT": 1.0})),
        run_static_strategy(
            data,
            StaticConfig(
                name="BTC/ETH 50:50",
                weights={"BTCUSDT": 0.50, "ETHUSDT": 0.50},
                rebalance_monthly=True,
            ),
        ),
        run_strength_strategy(
            data,
            StrengthConfig(
                name="BTC/ETH monthly Top1 100%",
                cash_weight=0.0,
                emergency_defense=False,
                use_ema_filter=False,
                top1_share_of_risk=1.0,
                top2_share_of_risk=0.0,
                group="Benchmark",
            ),
        ),
        no_emergency,
    ]

    cost_results = [
        run_strength_strategy(data, base_config(name=f"Cost {rate * 100:.1f}%", cost_rate=rate, group="Cost sensitivity"))
        for rate in (0.0, 0.001, 0.002, 0.003)
    ]
    start_results = [
        run_strength_strategy(
            data,
            base_config(name=f"{year} start", group="Start-year sensitivity"),
            months=month_range(f"{year}-01", TEST_END),
        )
        for year in range(2020, 2026)
    ]
    parameter_results = parameter_sensitivity(data)

    report = build_report(data, base, benchmarks, cost_results, start_results, parameter_results)
    report_path = output_dir / "btc_eth_monthly_strength_v1_report.md"
    report_path.write_text(report, encoding="utf-8")

    write_csv(output_dir / "btc_eth_monthly_strength_v1_summary.csv", [base.summary])
    write_csv(output_dir / "btc_eth_monthly_strength_v1_trade_log.csv", base.monthly_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_benchmarks.csv", [result.summary for result in benchmarks])
    write_csv(output_dir / "btc_eth_monthly_strength_v1_cost_sensitivity.csv", [result.summary for result in cost_results])
    write_csv(output_dir / "btc_eth_monthly_strength_v1_start_year_sensitivity.csv", [result.summary for result in start_results])
    write_csv(output_dir / "btc_eth_monthly_strength_v1_parameter_sensitivity.csv", [result.summary for result in parameter_results])
    print(report_path)


def base_config(
    name: str = "BTC/ETH Monthly Strength v1",
    cost_rate: float = BASE_COST_RATE,
    group: str = "Strategy",
) -> StrengthConfig:
    return StrengthConfig(name=name, cost_rate=cost_rate, group=group)


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
    end_ts = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
    return candles[0]["time"] <= start_ts and candles[-1]["time"] >= end_ts


def build_daily_rows(raw: Dict[str, List[dict]]) -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = {}
    for symbol, candles in raw.items():
        previous_close = None
        rows = {}
        for row in candles:
            daily_return = row["close"] / previous_close - 1 if previous_close else None
            previous_close = row["close"]
            if daily_return is None:
                continue
            rows[date_from_ts(row["time"])] = {
                **row,
                "date": date_from_ts(row["time"]),
                "month": month_from_ts(row["time"]),
                "return": daily_return,
            }
        out[symbol] = rows
    return out


def build_monthly_closes(raw: Dict[str, List[dict]]) -> Dict[str, Dict[str, dict]]:
    closes: Dict[str, Dict[str, dict]] = {}
    for symbol, candles in raw.items():
        symbol_closes: Dict[str, dict] = {}
        for row in candles:
            month = month_from_ts(row["time"])
            if month not in symbol_closes or row["time"] > symbol_closes[month]["time"]:
                symbol_closes[month] = row
        closes[symbol] = symbol_closes
    return closes


def run_strength_strategy(data: BacktestData, config: StrengthConfig, months: Optional[List[str]] = None) -> StrategyResult:
    months = months or data.months
    equity = 1.0
    current_weights: Dict[str, float] = {"cash": 1.0}
    total_turnover = 0.0
    total_cost = 0.0
    trades = 0
    emergency_exits = 0
    monthly_rows: List[dict] = []
    initial_time = data.monthly_closes["BTCUSDT"].get(previous_month(months[0]), {}).get("time")
    daily_equity = [{"time": initial_time, "date": date_from_ts(initial_time) if initial_time else "", "equity": equity}]

    for month in months:
        start_equity = equity
        target, meta = strength_target(data, config, month)
        target = normalize_weights(target)
        turnover = risk_turnover(current_weights, target)
        month_turnover = turnover
        month_cost_rate = turnover * config.cost_rate
        if turnover > 1e-12:
            trades += 1
            total_turnover += turnover
            total_cost += equity * month_cost_rate
            equity *= 1 - month_cost_rate
            current_weights = dict(target)

        month_start_weights = dict(current_weights)
        month_emergency = False
        emergency_date = ""
        locked_cash = False

        for day in month_days(data, month):
            gross_return = portfolio_daily_return(current_weights, day)
            equity *= 1 + gross_return
            if equity <= 0:
                equity = 0.0
            current_weights = drift_daily_weights(current_weights, day, gross_return)
            daily_equity.append({"time": day["time"], "date": day["date"], "equity": equity})

            if config.emergency_defense and not locked_cash and should_emergency_exit(data, day["time"], config.ema_period):
                exit_turnover = risk_turnover(current_weights, {"cash": 1.0})
                locked_cash = True
                if exit_turnover > 1e-12:
                    exit_cost_rate = exit_turnover * config.cost_rate
                    total_turnover += exit_turnover
                    total_cost += equity * exit_cost_rate
                    month_turnover += exit_turnover
                    month_cost_rate += exit_cost_rate
                    trades += 1
                    emergency_exits += 1
                    month_emergency = True
                    emergency_date = day["date"]
                    equity *= 1 - exit_cost_rate
                    current_weights = {"cash": 1.0}
                    daily_equity[-1]["equity"] = equity

        month_return = equity / start_equity - 1 if start_equity else 0.0
        btc_month_return = monthly_return(data, "BTCUSDT", month)
        eth_month_return = monthly_return(data, "ETHUSDT", month)
        monthly_rows.append(
            {
                "strategy": config.name,
                "month": month,
                "decision_date": meta["decision_date"],
                "btc_lookback_return_pct": pct_number(meta["btc_lookback_return"]),
                "eth_lookback_return_pct": pct_number(meta["eth_lookback_return"]),
                "btc_above_ema": meta["btc_above_ema"],
                "top1": meta["top1"],
                "top2": meta["top2"],
                "target_weights": format_weights(target),
                "start_weights": format_weights(month_start_weights),
                "end_weights": format_weights(current_weights),
                "emergency_exit": month_emergency,
                "emergency_exit_date": emergency_date,
                "return_pct": month_return * 100,
                "btc_month_return_pct": pct_number(btc_month_return),
                "eth_month_return_pct": pct_number(eth_month_return),
                "turnover": month_turnover,
                "cost_pct": month_cost_rate * 100,
                "equity": equity,
                "reason": meta["reason"],
            }
        )

    summary = metric_row(
        config.name,
        config.group,
        monthly_rows,
        daily_equity,
        total_turnover,
        total_cost,
        trades,
        emergency_exits,
        {
            "ema_period": config.ema_period,
            "lookback_months": config.lookback_months,
            "cash_weight_pct": config.cash_weight * 100,
            "cost_rate_pct": config.cost_rate * 100,
            "emergency_defense": config.emergency_defense,
            "use_ema_filter": config.use_ema_filter,
        },
    )
    yearly = yearly_returns(monthly_rows)
    drawdown = drawdown_info(daily_equity)
    return StrategyResult(config.name, summary, monthly_rows, yearly, daily_equity, drawdown)


def run_static_strategy(data: BacktestData, config: StaticConfig) -> StrategyResult:
    equity = 1.0
    current_weights: Dict[str, float] = {"cash": 1.0}
    total_turnover = 0.0
    total_cost = 0.0
    trades = 0
    monthly_rows: List[dict] = []
    initial_time = data.monthly_closes["BTCUSDT"].get(previous_month(data.months[0]), {}).get("time")
    daily_equity = [{"time": initial_time, "date": date_from_ts(initial_time) if initial_time else "", "equity": equity}]

    for month in data.months:
        start_equity = equity
        if config.rebalance_monthly or current_weights == {"cash": 1.0}:
            target = normalize_weights(config.weights)
        else:
            target = dict(current_weights)
        turnover = risk_turnover(current_weights, target)
        cost_rate = turnover * config.cost_rate
        if turnover > 1e-12:
            trades += 1
            total_turnover += turnover
            total_cost += equity * cost_rate
            equity *= 1 - cost_rate
            current_weights = dict(target)

        for day in month_days(data, month):
            gross_return = portfolio_daily_return(current_weights, day)
            equity *= 1 + gross_return
            current_weights = drift_daily_weights(current_weights, day, gross_return)
            daily_equity.append({"time": day["time"], "date": day["date"], "equity": equity})

        monthly_rows.append(
            {
                "strategy": config.name,
                "month": month,
                "decision_date": data.monthly_closes["BTCUSDT"].get(previous_month(month), {}).get("date", ""),
                "btc_lookback_return_pct": "",
                "eth_lookback_return_pct": "",
                "btc_above_ema": "",
                "top1": "",
                "top2": "",
                "target_weights": format_weights(target),
                "start_weights": format_weights(target),
                "end_weights": format_weights(current_weights),
                "emergency_exit": False,
                "emergency_exit_date": "",
                "return_pct": (equity / start_equity - 1) * 100 if start_equity else 0.0,
                "btc_month_return_pct": pct_number(monthly_return(data, "BTCUSDT", month)),
                "eth_month_return_pct": pct_number(monthly_return(data, "ETHUSDT", month)),
                "turnover": turnover,
                "cost_pct": cost_rate * 100,
                "equity": equity,
                "reason": "static",
            }
        )

    summary = metric_row(
        config.name,
        config.group,
        monthly_rows,
        daily_equity,
        total_turnover,
        total_cost,
        trades,
        0,
        {
            "ema_period": "",
            "lookback_months": "",
            "cash_weight_pct": "",
            "cost_rate_pct": config.cost_rate * 100,
            "emergency_defense": False,
            "use_ema_filter": False,
        },
    )
    yearly = yearly_returns(monthly_rows)
    drawdown = drawdown_info(daily_equity)
    return StrategyResult(config.name, summary, monthly_rows, yearly, daily_equity, drawdown)


def strength_target(data: BacktestData, config: StrengthConfig, month: str) -> Tuple[Dict[str, float], dict]:
    signal_month = previous_month(month)
    signal_row = data.monthly_closes["BTCUSDT"].get(signal_month)
    btc_return = lookback_return(data, "BTCUSDT", signal_month, config.lookback_months)
    eth_return = lookback_return(data, "ETHUSDT", signal_month, config.lookback_months)
    btc_ema = data.btc_ema_by_time(config.ema_period).get(signal_row["time"]) if signal_row else None
    btc_above = bool(signal_row and btc_ema is not None and signal_row["close"] > btc_ema)
    decision_date = date_from_ts(signal_row["time"]) if signal_row else ""
    returns = {"BTCUSDT": btc_return, "ETHUSDT": eth_return}

    if btc_return is None or eth_return is None or signal_row is None or (config.use_ema_filter and btc_ema is None):
        return {"cash": 1.0}, {
            "decision_date": decision_date,
            "btc_lookback_return": btc_return,
            "eth_lookback_return": eth_return,
            "btc_above_ema": btc_above,
            "top1": "",
            "top2": "",
            "reason": "missing_signal",
        }

    ranked = sorted(SYMBOLS, key=lambda symbol: returns[symbol] if returns[symbol] is not None else -math.inf, reverse=True)
    top1, top2 = ranked[0], ranked[1]
    meta = {
        "decision_date": decision_date,
        "btc_lookback_return": btc_return,
        "eth_lookback_return": eth_return,
        "btc_above_ema": btc_above,
        "top1": short(top1),
        "top2": short(top2),
    }
    if config.use_ema_filter and not btc_above:
        return {"cash": 1.0}, {**meta, "reason": "btc_below_or_equal_ema"}

    risk_weight = max(0.0, 1 - config.cash_weight)
    weights = {"cash": config.cash_weight}
    if config.top1_share_of_risk > 0:
        weights[top1] = risk_weight * config.top1_share_of_risk
    if config.top2_share_of_risk > 0:
        weights[top2] = risk_weight * config.top2_share_of_risk
    return weights, {**meta, "reason": "risk_on"}


def should_emergency_exit(data: BacktestData, timestamp: int, ema_period: int) -> bool:
    point = data.points_by_time.get(timestamp, {})
    stable_regime = point.get("stable_regime")
    stable_action_bias = point.get("stable_action_bias")
    shock = stable_regime == "shock" or stable_action_bias == REGIMES["shock"]["action_bias"]
    close = point.get("close")
    btc_ema = data.btc_ema_by_time(ema_period).get(timestamp)
    btc_below_or_equal_ema = bool(close is not None and btc_ema is not None and close <= btc_ema)
    return shock or btc_below_or_equal_ema


def parameter_sensitivity(data: BacktestData) -> List[StrategyResult]:
    results: List[StrategyResult] = []
    for period in (150, 200, 250):
        results.append(
            run_strength_strategy(
                data,
                StrengthConfig(name=f"EMA{period}", ema_period=period, group="Parameter sensitivity"),
            )
        )
    for lookback in (1, 2, 3):
        results.append(
            run_strength_strategy(
                data,
                StrengthConfig(name=f"Lookback {lookback}M", lookback_months=lookback, group="Parameter sensitivity"),
            )
        )
    for cash in (0.10, 0.20, 0.30):
        results.append(
            run_strength_strategy(
                data,
                StrengthConfig(name=f"Cash {cash * 100:.0f}%", cash_weight=cash, group="Parameter sensitivity"),
            )
        )
    return results


def metric_row(
    name: str,
    group: str,
    monthly_rows: List[dict],
    daily_equity: List[dict],
    total_turnover: float,
    total_cost: float,
    trades: int,
    emergency_exits: int,
    extra: dict,
) -> dict:
    returns = [row["return_pct"] / 100 for row in monthly_rows]
    final_equity = monthly_rows[-1]["equity"] if monthly_rows else 1.0
    if group == "Start-year sensitivity" and monthly_rows:
        final_equity = monthly_rows[-1]["equity"]
    total_return = final_equity - 1
    years = len(monthly_rows) / 12 if monthly_rows else 0
    cagr = final_equity ** (1 / years) - 1 if years > 0 and final_equity > 0 else None
    mdd = drawdown_info(daily_equity)["mdd"]
    volatility = statistics.stdev(returns) * math.sqrt(12) if len(returns) > 1 else None
    sharpe = (statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(12)) if len(returns) > 1 and statistics.stdev(returns) > 0 else None
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    yearly = yearly_returns(monthly_rows)
    row = {
        "name": name,
        "group": group,
        "total_return_pct": total_return * 100,
        "final_equity": final_equity,
        "cagr_pct": pct_number(cagr),
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "volatility_pct": pct_number(volatility),
        "win_rate_pct": sum(1 for value in returns if value > 0) / len(returns) * 100 if returns else 0.0,
        "trades": trades,
        "emergency_exits": emergency_exits,
        "turnover": total_turnover,
        "total_cost_pct_initial_capital": total_cost * 100,
    }
    row.update(extra)
    for year in range(2020, 2026):
        row[str(year)] = yearly.get(str(year), 0.0) * 100
    return row


def drawdown_info(equity_curve: List[dict]) -> dict:
    if not equity_curve:
        return {"mdd": 0.0, "start_date": "", "end_date": "", "recovery_date": "", "peak_equity": 1.0, "trough_equity": 1.0}
    peak_equity = equity_curve[0]["equity"]
    peak_date = equity_curve[0]["date"]
    mdd = 0.0
    start_date = peak_date
    end_date = peak_date
    trough_index = 0
    peak_at_mdd = peak_equity
    for index, point in enumerate(equity_curve):
        equity = point["equity"]
        if equity > peak_equity:
            peak_equity = equity
            peak_date = point["date"]
        drawdown = equity / peak_equity - 1 if peak_equity > 0 else 0.0
        if drawdown < mdd:
            mdd = drawdown
            start_date = peak_date
            end_date = point["date"]
            trough_index = index
            peak_at_mdd = peak_equity
    recovery_date = ""
    if mdd < 0:
        for point in equity_curve[trough_index + 1 :]:
            if point["equity"] >= peak_at_mdd:
                recovery_date = point["date"]
                break
    return {
        "mdd": mdd,
        "start_date": start_date,
        "end_date": end_date,
        "recovery_date": recovery_date,
        "peak_equity": peak_at_mdd,
        "trough_equity": equity_curve[trough_index]["equity"],
    }


def monthly_win_rates(rows: List[dict]) -> Dict[str, dict]:
    out = {}
    for month_number in range(1, 13):
        key = f"{month_number:02d}"
        values = [row["return_pct"] for row in rows if row["month"][5:7] == key]
        out[key] = {
            "wins": sum(1 for value in values if value > 0),
            "total": len(values),
            "win_rate_pct": sum(1 for value in values if value > 0) / len(values) * 100 if values else 0.0,
        }
    return out


def yearly_returns(rows: List[dict]) -> Dict[str, float]:
    yearly: Dict[str, float] = {}
    for row in rows:
        year = row["month"][:4]
        yearly.setdefault(year, 1.0)
        yearly[year] *= 1 + row["return_pct"] / 100
    return {year: value - 1 for year, value in yearly.items()}


def lookback_return(data: BacktestData, symbol: str, signal_month: str, months: int) -> Optional[float]:
    current = data.monthly_closes.get(symbol, {}).get(signal_month)
    previous = data.monthly_closes.get(symbol, {}).get(shift_month(signal_month, -months))
    if not current or not previous or not previous.get("close"):
        return None
    return current["close"] / previous["close"] - 1


def monthly_return(data: BacktestData, symbol: str, month: str) -> Optional[float]:
    current = data.monthly_closes.get(symbol, {}).get(month)
    previous = data.monthly_closes.get(symbol, {}).get(previous_month(month))
    if not current or not previous or not previous.get("close"):
        return None
    return current["close"] / previous["close"] - 1


def month_days(data: BacktestData, month: str) -> List[dict]:
    days = []
    btc_rows = [row for row in data.daily_rows["BTCUSDT"].values() if row["month"] == month]
    for btc_day in sorted(btc_rows, key=lambda row: row["time"]):
        eth_day = data.daily_rows["ETHUSDT"].get(btc_day["date"])
        if not eth_day:
            continue
        days.append(
            {
                "time": btc_day["time"],
                "date": btc_day["date"],
                "returns": {"BTCUSDT": btc_day["return"], "ETHUSDT": eth_day["return"]},
            }
        )
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


def build_report(
    data: BacktestData,
    base: StrategyResult,
    benchmarks: List[StrategyResult],
    cost_results: List[StrategyResult],
    start_results: List[StrategyResult],
    parameter_results: List[StrategyResult],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    worst_months = sorted(base.monthly_rows, key=lambda row: row["return_pct"])[:10]
    best_months = sorted(base.monthly_rows, key=lambda row: row["return_pct"], reverse=True)[:10]
    monthly_wins = monthly_win_rates(base.monthly_rows)
    yearly = yearly_returns(base.monthly_rows)
    dd = base.drawdown
    lines = [
        "# BTC/ETH Monthly Strength v1 정밀 검증 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        f"- 기간: {TEST_START} ~ {TEST_END}, 완결 UTC 월 기준",
        "- 데이터: Binance Spot `1d` klines, `BTCUSDT`/`ETHUSDT`",
        "- 기본 비용: 거래대금당 0.10%. 비용 민감도는 0.00%/0.10%/0.20%/0.30%를 별도 계산한다.",
        "- 기본 후보는 `BTC/ETH Monthly Strength v1`로 고정한다. 민감도 표는 안정성 확인용이며 최적화 기준으로 쓰지 않는다.",
        "- 월중 긴급 방어 조건은 기존 프로젝트 정의를 따른다: 일봉 UTC 종가 기준 stable shock 또는 BTC 종가 <= 해당 EMA이면 전량 현금화하고 다음 월말 판단 전까지 재진입하지 않는다.",
        "- MDD는 일봉 mark-to-market equity 기준, Sharpe/변동성은 월수익률을 연율화하고 무위험수익률은 0%로 둔다.",
        "- Cash 수익률은 0%로 둔다.",
        "",
        "## 1. 전체 성과",
        "",
        metrics_table([base.summary]),
        "",
        "### 월별 승률",
        "",
        monthly_win_table(monthly_wins),
        "",
        "### 연도별 수익률",
        "",
        yearly_table(yearly),
        "",
        "## 2. 거래 로그",
        "",
        trade_log_table(base.monthly_rows),
        "",
        "## 3. 손실 구간 분석",
        "",
        f"- 최대 낙폭 시작일: {dd['start_date']}",
        f"- 최대 낙폭 종료일: {dd['end_date']}",
        f"- 회복일: {dd['recovery_date'] or '미회복'}",
        f"- 최대 낙폭: {dd['mdd'] * 100:.1f}%",
        f"- 시작 equity / 저점 equity: {dd['peak_equity']:.4f} / {dd['trough_equity']:.4f}",
        "",
        "### 낙폭 기간 동안 포지션",
        "",
        drawdown_position_table(base, dd),
        "",
        "### 손실 원인",
        "",
        drawdown_cause(base, dd),
        "",
        "## 4. 최악의 월 Top 10",
        "",
        month_rank_table(worst_months, include_filter=True),
        "",
        "## 5. 최고 월 Top 10",
        "",
        month_rank_table(best_months, include_filter=False),
        "",
        "## 6. 벤치마크 비교",
        "",
        metrics_table([result.summary for result in benchmarks]),
        "",
        "## 7. 비용 민감도",
        "",
        metrics_table([result.summary for result in cost_results]),
        "",
        "## 8. 시작연도 민감도",
        "",
        metrics_table([result.summary for result in start_results]),
        "",
        "## 9. 파라미터 민감도",
        "",
        "- EMA 민감도는 월말 활성화 필터와 월중 긴급 방어의 EMA 기간을 함께 변경한다.",
        "- Lookback 민감도는 BTC/ETH 상대강도 산정 기간만 변경한다.",
        "- Cash 민감도는 Top1:Top2 위험자산 비율 5:3을 유지하고 현금 비중만 10%/20%/30%로 변경한다.",
        "",
        metrics_table([result.summary for result in parameter_results]),
        "",
        "## 데이터 커버리지",
        "",
        data_coverage_table(data),
        "",
        "## 산출물",
        "",
        "- `btc_eth_monthly_strength_v1_report.md`",
        "- `btc_eth_monthly_strength_v1_summary.csv`",
        "- `btc_eth_monthly_strength_v1_trade_log.csv`",
        "- `btc_eth_monthly_strength_v1_benchmarks.csv`",
        "- `btc_eth_monthly_strength_v1_cost_sensitivity.csv`",
        "- `btc_eth_monthly_strength_v1_start_year_sensitivity.csv`",
        "- `btc_eth_monthly_strength_v1_parameter_sensitivity.csv`",
        "",
    ]
    return "\n".join(lines)


def metrics_table(rows: List[dict]) -> str:
    headers = ["Name", "Total", "CAGR", "MDD", "Sharpe", "Calmar", "Vol", "Win", "Trades", "Emergency", "Turnover", "Cost"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["name"],
                    pct(row["total_return_pct"]),
                    pct(row["cagr_pct"]),
                    pct(row["mdd_pct"]),
                    num(row["sharpe"]),
                    num(row["calmar"]),
                    pct(row["volatility_pct"]),
                    pct(row["win_rate_pct"]),
                    str(row["trades"]),
                    str(row["emergency_exits"]),
                    f"{row['turnover']:.2f}",
                    pct(row["total_cost_pct_initial_capital"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def monthly_win_table(rows: Dict[str, dict]) -> str:
    lines = ["| Month | Wins | Total | Win rate |", "|---|---:|---:|---:|"]
    for key, row in rows.items():
        lines.append(f"| {key} | {row['wins']} | {row['total']} | {row['win_rate_pct']:.1f}% |")
    return "\n".join(lines)


def yearly_table(yearly: Dict[str, float]) -> str:
    lines = ["| Year | Return |", "|---|---:|"]
    for year in range(2020, 2026):
        lines.append(f"| {year} | {yearly.get(str(year), 0.0) * 100:.1f}% |")
    return "\n".join(lines)


def trade_log_table(rows: List[dict]) -> str:
    headers = [
        "Month",
        "Decision",
        "BTC 1M",
        "ETH 1M",
        "Top1",
        "Top2",
        "Next target",
        "Emergency",
        "Emergency date",
        "Return",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["month"],
                    row["decision_date"],
                    pct(row["btc_lookback_return_pct"]),
                    pct(row["eth_lookback_return_pct"]),
                    row["top1"],
                    row["top2"],
                    row["target_weights"],
                    "Y" if row["emergency_exit"] else "N",
                    row["emergency_exit_date"],
                    pct(row["return_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def drawdown_position_table(base: StrategyResult, dd: dict) -> str:
    start_month = dd["start_date"][:7]
    end_month = dd["end_date"][:7]
    rows = [row for row in base.monthly_rows if start_month <= row["month"] <= end_month]
    counter = Counter(position_label(row) for row in rows)
    lines = ["| Position | Months |", "|---|---:|"]
    for label, count in counter.most_common():
        lines.append(f"| {label} | {count} |")
    return "\n".join(lines)


def drawdown_cause(base: StrategyResult, dd: dict) -> str:
    start_month = dd["start_date"][:7]
    end_month = dd["end_date"][:7]
    rows = [row for row in base.monthly_rows if start_month <= row["month"] <= end_month]
    if not rows:
        return "- 낙폭 구간 월별 로그가 없다."
    risk_on = [row for row in rows if "BTC" in row["target_weights"] or "ETH" in row["target_weights"]]
    cash_months = [row for row in rows if row["target_weights"] == "Cash 100.0%"]
    emergencies = [row for row in rows if row["emergency_exit"]]
    worst = min(rows, key=lambda row: row["return_pct"])
    btc_comp = compound_pct([row["btc_month_return_pct"] for row in rows])
    eth_comp = compound_pct([row["eth_month_return_pct"] for row in rows])
    return "\n".join(
        [
            f"- 낙폭 구간은 {start_month}~{end_month} 총 {len(rows)}개월이다. 이 중 리스크 온 {len(risk_on)}개월, 월초 Cash {len(cash_months)}개월, 월중 긴급 방어 {len(emergencies)}회였다.",
            f"- 같은 기간 BTC 누적 수익률은 {btc_comp:.1f}%, ETH 누적 수익률은 {eth_comp:.1f}%였다.",
            f"- 최대 손실 월은 {worst['month']}이며 전략 {worst['return_pct']:.1f}%, 포지션 {position_label(worst)}, BTC {worst['btc_month_return_pct']:.1f}%, ETH {worst['eth_month_return_pct']:.1f}%였다.",
            "- 손실은 월말 신호 이후 다음 달 초반의 BTC/ETH 하락을 일부 보유한 데서 발생했다. 긴급 방어는 손실을 절단했지만, 종가 확인 후 현금화하므로 방어 발생일까지의 하락은 반영된다.",
        ]
    )


def month_rank_table(rows: List[dict], include_filter: bool) -> str:
    headers = ["Month", "Return", "Position", "BTC return", "ETH return"]
    if include_filter:
        headers.append("Defense")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["month"],
            pct(row["return_pct"]),
            position_label(row),
            pct(row["btc_month_return_pct"]),
            pct(row["eth_month_return_pct"]),
        ]
        if include_filter:
            values.append("Y" if row["emergency_exit"] or row["reason"] != "risk_on" else "N")
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def data_coverage_table(data: BacktestData) -> str:
    lines = ["| Symbol | First day | Last day | Candles |", "|---|---:|---:|---:|"]
    for symbol in SYMBOLS:
        candles = data.raw[symbol]
        first = date_from_ts(candles[0]["time"]) if candles else ""
        last = date_from_ts(candles[-1]["time"]) if candles else ""
        lines.append(f"| {short(symbol)} | {first} | {last} | {len(candles)} |")
    return "\n".join(lines)


def position_label(row: dict) -> str:
    label = row["target_weights"]
    if row["emergency_exit"]:
        return f"{label} -> Cash on {row['emergency_exit_date']}"
    return label


def format_weights(weights: Dict[str, float]) -> str:
    labels = []
    for key in ("BTCUSDT", "ETHUSDT", "cash"):
        value = weights.get(key, 0.0)
        if value > 1e-10:
            labels.append(f"{short(key)} {value * 100:.1f}%")
    return " / ".join(labels) if labels else "Cash 100.0%"


def short(symbol: str) -> str:
    if symbol == "cash":
        return "Cash"
    return symbol.replace("USDT", "")


def compound_pct(values: Iterable[Optional[float]]) -> float:
    total = 1.0
    for value in values:
        if value is not None:
            total *= 1 + value / 100
    return (total - 1) * 100


def pct_number(value: Optional[float]) -> Optional[float]:
    return value * 100 if value is not None else None


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
    return shift_month(month, -1)


def shift_month(month: str, delta: int) -> str:
    year, month_number = [int(part) for part in month.split("-")]
    total = year * 12 + (month_number - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def date_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    main()
