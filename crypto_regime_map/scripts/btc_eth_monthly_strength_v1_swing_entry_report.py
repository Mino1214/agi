"""BTC/ETH Monthly Strength v1 swing-entry comparison report.

The monthly v1 strategy is not modified. This report compares 4H execution
styles that use the same BTC/ETH/Cash universe, BTC daily EMA200 top filter,
and BTC-vs-ETH relative strength idea.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import btc_eth_monthly_strength_v1_report as v1  # noqa: E402


FETCH_START = "2018-01-01T00:00:00+00:00"
FETCH_END = "2026-01-02T00:00:00+00:00"
TEST_START_TS = int(datetime.fromisoformat("2020-01-01T00:00:00+00:00").timestamp())
TEST_END_TS = int(datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp())
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL_SECONDS = 4 * 60 * 60
PERIODS_PER_YEAR = 365 * 6
FEE_RATE = 0.001
STOP_ATR_MULTIPLE = 1.75
PULLBACK_ATR_TOLERANCE = 0.25
OVERHEAT_ATR_MULTIPLE = 2.0
MAX_HOLD_DAYS = 14.0
BREAKOUT_LOOKBACK_BARS = 20
ENTRY_QUALITY_DAYS = (1, 3, 7)


@dataclass
class Method:
    key: str
    name: str


METHODS = [
    Method("immediate", "즉시 진입"),
    Method("avoid_overheat", "과열 회피 진입"),
    Method("ema20_pullback", "EMA20 눌림 진입"),
    Method("ema50_pullback", "EMA50 눌림 진입"),
    Method("split_entry", "분할 진입"),
]


class SwingData:
    def __init__(self, raw_1d: Dict[str, List[dict]], raw_4h: Dict[str, List[dict]]):
        self.raw_1d = raw_1d
        self.raw_4h = raw_4h
        self.daily = build_daily_state(raw_1d)
        self.bars = build_4h_bars(raw_4h, self.daily)
        self.asset_bars = {symbol: {row["time"]: row for row in add_4h_indicators(raw_4h[symbol])} for symbol in SYMBOLS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--use-cache", action="store_true", help="Use local raw JSON if available and complete.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_1d = load_raw(SYMBOLS, "1d", args.use_cache)
    raw_4h = load_raw(SYMBOLS, "4h", args.use_cache)
    data = SwingData(raw_1d, raw_4h)

    results = [run_method(data, method) for method in METHODS]
    summary_rows = [result["summary"] for result in results]
    trade_rows = [trade for result in results for trade in result["trades"]]
    comparison_rows = compare_to_immediate(summary_rows)

    report = build_report(data, summary_rows, comparison_rows, trade_rows)
    report_path = output_dir / "btc_eth_monthly_strength_v1_swing_entry_report.md"
    report_path.write_text(report, encoding="utf-8")
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_summary.csv", summary_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_comparison.csv", comparison_rows)
    write_csv(output_dir / "btc_eth_monthly_strength_v1_swing_entry_trades.csv", trade_rows)
    print(report_path)


def load_raw(symbols: Iterable[str], interval: str, use_cache: bool) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    out = {}
    for symbol in symbols:
        cache_path = raw_dir / f"{symbol}_{interval}.json"
        cached = v1.read_cache(cache_path) if use_cache else []
        if cached and covers_window(cached):
            out[symbol] = cached
        else:
            out[symbol] = v1.fetch_ohlcv(symbol, interval, FETCH_START, FETCH_END)
    return out


def covers_window(candles: List[dict]) -> bool:
    return bool(candles and candles[0]["time"] <= TEST_START_TS and candles[-1]["time"] >= TEST_END_TS - 1)


def build_daily_state(raw_1d: Dict[str, List[dict]]) -> Dict[str, dict]:
    btc_rows = raw_1d["BTCUSDT"]
    eth_rows_by_time = {row["time"]: row for row in raw_1d["ETHUSDT"]}
    btc_ema200 = v1.ema([row["close"] for row in btc_rows], 200)
    state = {}
    for index, btc in enumerate(btc_rows):
        if index < 14:
            continue
        eth = eth_rows_by_time.get(btc["time"])
        if not eth:
            continue
        btc_prev = btc_rows[index - 14]
        eth_prev = eth_rows_by_time.get(btc_prev["time"])
        if not eth_prev:
            continue
        btc_return = btc["close"] / btc_prev["close"] - 1
        eth_return = eth["close"] / eth_prev["close"] - 1
        date = date_from_ts(btc["time"])
        state[date] = {
            "btc_close": btc["close"],
            "btc_ema200": btc_ema200[index],
            "btc_above_ema200": bool(btc_ema200[index] is not None and btc["close"] > btc_ema200[index]),
            "candidate": "BTCUSDT" if btc_return >= eth_return else "ETHUSDT",
            "btc_14d_return": btc_return,
            "eth_14d_return": eth_return,
        }
    return state


def add_4h_indicators(candles: List[dict]) -> List[dict]:
    rows = [dict(row) for row in candles]
    closes = [row["close"] for row in rows]
    ema20 = v1.ema(closes, 20)
    ema50 = v1.ema(closes, 50)
    atr14 = atr(rows, 14)
    for index, row in enumerate(rows):
        row["ema20"] = ema20[index]
        row["ema50"] = ema50[index]
        row["atr14"] = atr14[index]
    return rows


def build_4h_bars(raw_4h: Dict[str, List[dict]], daily: Dict[str, dict]) -> List[dict]:
    btc_rows = {row["time"]: row for row in add_4h_indicators(raw_4h["BTCUSDT"])}
    eth_rows = {row["time"]: row for row in add_4h_indicators(raw_4h["ETHUSDT"])}
    bars = []
    for timestamp in sorted(set(btc_rows) & set(eth_rows)):
        if timestamp < TEST_START_TS or timestamp >= TEST_END_TS:
            continue
        daily_key = completed_daily_key(timestamp)
        daily_state = daily.get(daily_key)
        if not daily_state:
            continue
        bars.append(
            {
                "time": timestamp,
                "date": datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "close_time": timestamp + INTERVAL_SECONDS,
                "daily_key": daily_key,
                "daily": daily_state,
                "assets": {"BTCUSDT": btc_rows[timestamp], "ETHUSDT": eth_rows[timestamp]},
            }
        )
    return bars


def run_method(data: SwingData, method: Method) -> dict:
    cash = 1.0
    units = 0.0
    symbol: Optional[str] = None
    avg_entry_price = 0.0
    entry_equity = 1.0
    entry_time = 0
    entry_index = 0
    entry_atr = 0.0
    entry_parts: List[dict] = []
    pending: Optional[dict] = None
    waiting: Dict[str, object] = {}
    split_state = {"ema20_added": False, "breakout_added": False}
    trades: List[dict] = []
    equity_curve = [{"time": TEST_START_TS, "equity": 1.0}]

    for index, bar in enumerate(data.bars):
        if pending and pending["index"] == index:
            cash, units, symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr = execute_entry(
                data,
                bar,
                index,
                pending,
                cash,
                units,
                symbol,
                avg_entry_price,
                entry_equity,
                entry_time,
                entry_index,
                entry_atr,
                entry_parts,
            )
            pending = None

        equity = mark_equity(cash, units, symbol, bar, use_close=True)
        exited = False
        if symbol:
            exit_reason = exit_reason_for(bar, symbol, avg_entry_price, entry_atr, entry_time)
            if exit_reason:
                cash, trade = execute_exit(data, method, bar, index, cash, units, symbol, entry_equity, entry_time, entry_index, entry_parts, exit_reason)
                trades.append(trade)
                units = 0.0
                symbol = None
                avg_entry_price = 0.0
                entry_parts = []
                split_state = {"ema20_added": False, "breakout_added": False}
                waiting = {}
                exited = True
                equity = cash

        equity_curve.append({"time": bar["close_time"], "equity": equity})
        if index + 1 >= len(data.bars):
            continue

        if symbol and method.key == "split_entry" and not exited and pending is None:
            add_order = split_add_order(data, index, bar, symbol, split_state)
            if add_order:
                pending = add_order
                if add_order["part"] == "ema20_recovery":
                    split_state["ema20_added"] = True
                if add_order["part"] == "breakout":
                    split_state["breakout_added"] = True
            continue

        if symbol or exited or pending is not None:
            continue

        candidate = candidate_if_tradeable(bar)
        if not candidate:
            waiting = {}
            continue
        order, waiting = entry_order_for_method(data, method, index, bar, candidate, waiting)
        if order:
            pending = order

    if symbol:
        last_index = len(data.bars) - 1
        last_bar = data.bars[last_index]
        cash, trade = execute_exit(data, method, last_bar, last_index, cash, units, symbol, entry_equity, entry_time, entry_index, entry_parts, "end_of_test")
        trades.append(trade)
        equity_curve.append({"time": last_bar["close_time"], "equity": cash})

    summary = summary_row(method, equity_curve, trades)
    return {"summary": summary, "trades": trades, "equity_curve": equity_curve}


def execute_entry(
    data: SwingData,
    bar: dict,
    index: int,
    order: dict,
    cash: float,
    units: float,
    symbol: Optional[str],
    avg_entry_price: float,
    entry_equity: float,
    entry_time: int,
    entry_index: int,
    entry_atr: float,
    entry_parts: List[dict],
) -> Tuple[float, float, str, float, float, int, int, float]:
    fill_symbol = order["symbol"]
    price = bar["assets"][fill_symbol]["open"]
    equity = mark_equity(cash, units, symbol, bar, use_close=False)
    current_value = units * price if symbol == fill_symbol else 0.0
    target_value = equity * order["target_weight"]
    notional = max(0.0, target_value - current_value)
    if notional <= 1e-12:
        return cash, units, fill_symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr
    cost = notional * FEE_RATE
    buy_units = notional / price
    if not symbol:
        entry_equity = equity
        entry_time = bar["time"]
        entry_index = index
        entry_atr = bar["assets"][fill_symbol]["atr14"] or 0.0
        avg_entry_price = price
        units = 0.0
    avg_entry_price = ((units * avg_entry_price) + notional) / (units + buy_units) if units + buy_units > 0 else price
    cash -= notional + cost
    units += buy_units
    entry_parts.append({"date": bar["date"], "part": order["part"], "target_weight": order["target_weight"], "price": price})
    return cash, units, fill_symbol, avg_entry_price, entry_equity, entry_time, entry_index, entry_atr


def execute_exit(
    data: SwingData,
    method: Method,
    bar: dict,
    index: int,
    cash: float,
    units: float,
    symbol: str,
    entry_equity: float,
    entry_time: int,
    entry_index: int,
    entry_parts: List[dict],
    exit_reason: str,
) -> Tuple[float, dict]:
    price = bar["assets"][symbol]["close"]
    proceeds = units * price
    cost = proceeds * FEE_RATE
    cash_after = cash + proceeds - cost
    hold_days = (bar["close_time"] - entry_time) / 86400
    quality = entry_quality(data, symbol, entry_index, entry_parts[0]["price"])
    trade = {
        "method": method.name,
        "symbol": v1.short(symbol),
        "entry_date": datetime.fromtimestamp(entry_time, timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "exit_date": datetime.fromtimestamp(bar["close_time"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "exit_reason": exit_reason,
        "parts": json.dumps(entry_parts, ensure_ascii=False),
        "hold_days": hold_days,
        "trade_return_pct": (cash_after / entry_equity - 1) * 100 if entry_equity else 0.0,
        "entry_after_1d_pct": quality["entry_after_1d_pct"],
        "entry_after_3d_pct": quality["entry_after_3d_pct"],
        "entry_after_7d_pct": quality["entry_after_7d_pct"],
        "entry_mae_7d_pct": quality["entry_mae_7d_pct"],
        "stuck_after_1d": quality["stuck_after_1d"],
    }
    return cash_after, trade


def entry_order_for_method(data: SwingData, method: Method, index: int, bar: dict, candidate: str, waiting: Dict[str, object]) -> Tuple[Optional[dict], Dict[str, object]]:
    asset = bar["assets"][candidate]
    if missing_entry_indicators(asset):
        return None, waiting
    if method.key == "immediate":
        return entry_order(index, candidate, 0.80, "immediate"), {}
    if method.key == "avoid_overheat":
        overheat = asset["close"] > asset["ema20"] + OVERHEAT_ATR_MULTIPLE * asset["atr14"]
        return (None, {"candidate": candidate, "mode": method.key}) if overheat else (entry_order(index, candidate, 0.80, "not_overheated"), {})
    if method.key in {"ema20_pullback", "ema50_pullback"}:
        if waiting.get("candidate") != candidate or waiting.get("mode") != method.key:
            waiting = {"candidate": candidate, "mode": method.key, "touched": False}
        ema_key = "ema20" if method.key == "ema20_pullback" else "ema50"
        touched = bool(waiting.get("touched")) or asset["low"] <= asset[ema_key] + PULLBACK_ATR_TOLERANCE * asset["atr14"]
        recover_level = asset["ema20"]
        recovered = touched and asset["close"] > recover_level
        waiting["touched"] = touched
        if recovered:
            return entry_order(index, candidate, 0.80, method.key), {}
        return None, waiting
    if method.key == "split_entry":
        return entry_order(index, candidate, 0.30, "initial_30"), {}
    raise ValueError(f"Unknown method: {method.key}")


def split_add_order(data: SwingData, index: int, bar: dict, symbol: str, split_state: dict) -> Optional[dict]:
    asset = bar["assets"][symbol]
    previous = data.bars[index - 1]["assets"][symbol] if index > 0 else None
    if missing_entry_indicators(asset) or not candidate_if_tradeable(bar):
        return None
    if not split_state["ema20_added"] and previous and previous["close"] <= previous["ema20"] and asset["close"] > asset["ema20"]:
        return entry_order(index, symbol, 0.60, "ema20_recovery")
    if not split_state["breakout_added"] and index >= BREAKOUT_LOOKBACK_BARS:
        prior_high = max(data.bars[item]["assets"][symbol]["high"] for item in range(index - BREAKOUT_LOOKBACK_BARS, index))
        if asset["close"] > prior_high:
            return entry_order(index, symbol, 0.80, "breakout")
    return None


def entry_order(index: int, symbol: str, target_weight: float, part: str) -> dict:
    return {"index": index + 1, "symbol": symbol, "target_weight": target_weight, "part": part}


def exit_reason_for(bar: dict, symbol: str, avg_entry_price: float, entry_atr: float, entry_time: int) -> str:
    asset = bar["assets"][symbol]
    if not bar["daily"]["btc_above_ema200"]:
        return "btc_1d_ema200_exit"
    if asset["ema50"] is not None and asset["close"] < asset["ema50"]:
        return "ema50_exit"
    if entry_atr and asset["close"] <= avg_entry_price - STOP_ATR_MULTIPLE * entry_atr:
        return "atr_stop"
    hold_days = (bar["close_time"] - entry_time) / 86400
    if hold_days >= MAX_HOLD_DAYS:
        return "max_hold"
    return ""


def candidate_if_tradeable(bar: dict) -> Optional[str]:
    daily = bar["daily"]
    if not daily["btc_above_ema200"]:
        return None
    return daily["candidate"]


def missing_entry_indicators(asset: dict) -> bool:
    return asset["ema20"] is None or asset["ema50"] is None or asset["atr14"] is None


def mark_equity(cash: float, units: float, symbol: Optional[str], bar: dict, use_close: bool) -> float:
    if not symbol:
        return cash
    price_key = "close" if use_close else "open"
    return cash + units * bar["assets"][symbol][price_key]


def entry_quality(data: SwingData, symbol: str, entry_index: int, entry_price: float) -> dict:
    out = {}
    for days in ENTRY_QUALITY_DAYS:
        offset = days * 6
        if entry_index + offset < len(data.bars):
            close = data.bars[entry_index + offset]["assets"][symbol]["close"]
            out[f"entry_after_{days}d_pct"] = (close / entry_price - 1) * 100
        else:
            out[f"entry_after_{days}d_pct"] = None
    end = min(len(data.bars), entry_index + 7 * 6 + 1)
    lows = [data.bars[item]["assets"][symbol]["low"] for item in range(entry_index, end)]
    out["entry_mae_7d_pct"] = (min(lows) / entry_price - 1) * 100 if lows else None
    out["stuck_after_1d"] = bool(out["entry_after_1d_pct"] is not None and out["entry_after_1d_pct"] < 0)
    return out


def summary_row(method: Method, equity_curve: List[dict], trades: List[dict]) -> dict:
    final_equity = equity_curve[-1]["equity"] if equity_curve else 1.0
    years = (TEST_END_TS - TEST_START_TS) / (365.25 * 86400)
    cagr = final_equity ** (1 / years) - 1 if final_equity > 0 else None
    returns = [equity_curve[index]["equity"] / equity_curve[index - 1]["equity"] - 1 for index in range(1, len(equity_curve)) if equity_curve[index - 1]["equity"] > 0]
    stdev = statistics.stdev(returns) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / stdev * math.sqrt(PERIODS_PER_YEAR) if stdev and stdev > 0 else None
    mdd = max_drawdown(equity_curve)
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    trade_returns = [trade["trade_return_pct"] for trade in trades]
    wins = [value for value in trade_returns if value > 0]
    losses = [value for value in trade_returns if value < 0]
    stuck_values = [trade["stuck_after_1d"] for trade in trades if trade["entry_after_1d_pct"] is not None]
    return {
        "method": method.name,
        "total_return_pct": (final_equity - 1) * 100,
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "trades": len(trades),
        "avg_hold_days": statistics.mean([trade["hold_days"] for trade in trades]) if trades else None,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "avg_win_pct": statistics.mean(wins) if wins else None,
        "avg_loss_pct": statistics.mean(losses) if losses else None,
        "entry_after_1d_avg_pct": mean_present([trade["entry_after_1d_pct"] for trade in trades]),
        "entry_after_3d_avg_pct": mean_present([trade["entry_after_3d_pct"] for trade in trades]),
        "entry_after_7d_avg_pct": mean_present([trade["entry_after_7d_pct"] for trade in trades]),
        "entry_mae_7d_avg_pct": mean_present([trade["entry_mae_7d_pct"] for trade in trades]),
        "stuck_after_1d_pct": sum(1 for value in stuck_values if value) / len(stuck_values) * 100 if stuck_values else None,
    }


def compare_to_immediate(rows: List[dict]) -> List[dict]:
    immediate = next(row for row in rows if row["method"] == "즉시 진입")
    out = []
    for row in rows:
        cagr_delta = row["cagr_pct"] - immediate["cagr_pct"] if row["cagr_pct"] is not None and immediate["cagr_pct"] is not None else None
        mdd_change = row["mdd_pct"] - immediate["mdd_pct"]
        stuck_change = (row["stuck_after_1d_pct"] or 0.0) - (immediate["stuck_after_1d_pct"] or 0.0)
        trade_ratio = row["trades"] / immediate["trades"] if immediate["trades"] else None
        out.append(
            {
                "method": row["method"],
                "cagr_delta_pct_point": cagr_delta,
                "mdd_change_pct_point": mdd_change,
                "stuck_change_pct_point": stuck_change,
                "trade_count_ratio": trade_ratio,
                "mdd_improved": row["mdd_pct"] > immediate["mdd_pct"],
                "stuck_improved": (row["stuck_after_1d_pct"] or 0.0) < (immediate["stuck_after_1d_pct"] or 0.0),
                "return_not_overly_damaged": bool(cagr_delta is not None and cagr_delta >= -5.0),
                "trades_not_excessive": bool(trade_ratio is not None and trade_ratio <= 1.5),
            }
        )
    return out


def build_report(data: SwingData, summary_rows: List[dict], comparison_rows: List[dict], trade_rows: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# BTC/ETH Monthly Strength v1 스윙 진입 방식 비교 리포트",
        "",
        f"- 생성 시각: {generated_at}",
        "- 기간: 2020-01-01 ~ 2025-12-31 UTC",
        "- 데이터: Binance Spot `1d`/`4h` klines, `BTCUSDT`/`ETHUSDT`",
        "- 상위 필터: 직전 완결 1D 기준 BTC 종가 > EMA200일 때만 신규 진입 가능",
        "- 후보 선택: 직전 완결 1D 기준 최근 14일 수익률이 더 높은 자산",
        "- 1~4번 방식은 후보 자산 80%, Cash 20%로 진입한다. 분할 진입은 30%/30%/20%로 최대 80%까지 채운다.",
        f"- ATR 손절은 모든 방식에 동일하게 {STOP_ATR_MULTIPLE:.2f} ATR로 고정했다.",
        f"- EMA 근처 눌림은 `low <= EMA + {PULLBACK_ATR_TOLERANCE:.2f} ATR`로 판정했다.",
        "- 진입 후 물린 비율은 진입 1일 후 후보 자산 수익률이 음수인 거래 비율이다.",
        "- 진입 직후 최대 역행폭은 진입 후 7일 동안 후보 자산 저가 기준 MAE다.",
        f"- 비용은 거래대금당 {FEE_RATE * 100:.2f}%로 반영했다.",
        "",
        "## 성과 비교",
        "",
        summary_table(summary_rows),
        "",
        "## 즉시 진입 대비 판정",
        "",
        comparison_table(comparison_rows),
        "",
        "## 핵심 확인",
        "",
        key_findings(summary_rows, comparison_rows),
        "",
        "## 청산 사유 분포",
        "",
        exit_reason_table(trade_rows),
        "",
        "## 최근 거래 샘플",
        "",
        trade_sample_table(trade_rows),
        "",
        "## 데이터 커버리지",
        "",
        coverage_table(data),
        "",
        "## 산출물",
        "",
        "- `btc_eth_monthly_strength_v1_swing_entry_report.md`",
        "- `btc_eth_monthly_strength_v1_swing_entry_summary.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_comparison.csv`",
        "- `btc_eth_monthly_strength_v1_swing_entry_trades.csv`",
        "",
    ]
    return "\n".join(lines)


def summary_table(rows: List[dict]) -> str:
    headers = [
        "Method",
        "CAGR",
        "MDD",
        "Sharpe",
        "Calmar",
        "Trades",
        "Avg hold",
        "Win",
        "Avg win",
        "Avg loss",
        "1D",
        "3D",
        "7D",
        "MAE7D",
        "Stuck",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["method"],
            pct(row["cagr_pct"]),
            pct(row["mdd_pct"]),
            num(row["sharpe"]),
            num(row["calmar"]),
            str(row["trades"]),
            num(row["avg_hold_days"]),
            pct(row["win_rate_pct"]),
            pct(row["avg_win_pct"]),
            pct(row["avg_loss_pct"]),
            pct(row["entry_after_1d_avg_pct"]),
            pct(row["entry_after_3d_avg_pct"]),
            pct(row["entry_after_7d_avg_pct"]),
            pct(row["entry_mae_7d_avg_pct"]),
            pct(row["stuck_after_1d_pct"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def comparison_table(rows: List[dict]) -> str:
    headers = ["Method", "CAGR delta", "MDD change", "Stuck change", "Trade ratio", "MDD", "Stuck", "Return", "Trades"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [
            row["method"],
            pp(row["cagr_delta_pct_point"]),
            pp(row["mdd_change_pct_point"]),
            pp(row["stuck_change_pct_point"]),
            num(row["trade_count_ratio"]),
            "PASS" if row["mdd_improved"] else "FAIL",
            "PASS" if row["stuck_improved"] else "FAIL",
            "PASS" if row["return_not_overly_damaged"] else "FAIL",
            "PASS" if row["trades_not_excessive"] else "FAIL",
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def key_findings(summary_rows: List[dict], comparison_rows: List[dict]) -> str:
    immediate = next(row for row in summary_rows if row["method"] == "즉시 진입")
    candidates = [row for row in summary_rows if row["method"] != "즉시 진입"]
    best_mdd = max(candidates, key=lambda row: row["mdd_pct"])
    best_stuck = min(candidates, key=lambda row: row["stuck_after_1d_pct"] if row["stuck_after_1d_pct"] is not None else 999)
    best_calmar = max(summary_rows, key=lambda row: row["calmar"] or -999)
    lines = [
        f"- 즉시 진입 기준 MDD는 {immediate['mdd_pct']:.1f}%, 진입 1일 후 물린 비율은 {immediate['stuck_after_1d_pct']:.1f}%다.",
        f"- 낙폭이 가장 작은 대안은 {best_mdd['method']}이며 MDD {best_mdd['mdd_pct']:.1f}%다.",
        f"- 진입 직후 손실 확률이 가장 낮은 대안은 {best_stuck['method']}이며 물린 비율 {best_stuck['stuck_after_1d_pct']:.1f}%다.",
        f"- Calmar 기준 1위는 {best_calmar['method']}이며 CAGR {best_calmar['cagr_pct']:.1f}%, MDD {best_calmar['mdd_pct']:.1f}%다.",
    ]
    return "\n".join(lines)


def exit_reason_table(trades: List[dict]) -> str:
    counts: Dict[Tuple[str, str], int] = {}
    for trade in trades:
        key = (trade["method"], trade["exit_reason"])
        counts[key] = counts.get(key, 0) + 1
    lines = ["| Method | Exit reason | Count |", "|---|---|---:|"]
    for method in [item.name for item in METHODS]:
        method_counts = [(reason, count) for (name, reason), count in counts.items() if name == method]
        for reason, count in sorted(method_counts, key=lambda item: (-item[1], item[0])):
            lines.append(f"| {method} | {reason} | {count} |")
    return "\n".join(lines)


def trade_sample_table(trades: List[dict]) -> str:
    rows = sorted(trades, key=lambda row: row["entry_date"], reverse=True)[:20]
    lines = ["| Method | Symbol | Entry | Exit | Reason | Return | Hold | 1D | MAE7D |", "|---|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["method"],
                    row["symbol"],
                    row["entry_date"],
                    row["exit_date"],
                    row["exit_reason"],
                    pct(row["trade_return_pct"]),
                    num(row["hold_days"]),
                    pct(row["entry_after_1d_pct"]),
                    pct(row["entry_mae_7d_pct"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def coverage_table(data: SwingData) -> str:
    lines = ["| Symbol | Interval | First | Last | Candles |", "|---|---|---:|---:|---:|"]
    for interval, raw in (("1d", data.raw_1d), ("4h", data.raw_4h)):
        for symbol in SYMBOLS:
            candles = raw[symbol]
            lines.append(
                f"| {v1.short(symbol)} | {interval} | {date_from_ts(candles[0]['time'])} | "
                f"{date_from_ts(candles[-1]['time'])} | {len(candles)} |"
            )
    return "\n".join(lines)


def atr(rows: List[dict], period: int) -> List[Optional[float]]:
    true_ranges = []
    previous_close = None
    for row in rows:
        high = row["high"]
        low = row["low"]
        if previous_close is None:
            value = high - low
        else:
            value = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(value)
        previous_close = row["close"]
    out: List[Optional[float]] = []
    for index in range(len(true_ranges)):
        if index + 1 < period:
            out.append(None)
        else:
            out.append(sum(true_ranges[index + 1 - period : index + 1]) / period)
    return out


def max_drawdown(curve: List[dict]) -> float:
    peak = curve[0]["equity"] if curve else 1.0
    mdd = 0.0
    for point in curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, equity / peak - 1)
    return mdd


def mean_present(values: List[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    return statistics.mean(clean) if clean else None


def completed_daily_key(open_timestamp: int) -> str:
    close_dt = datetime.fromtimestamp(open_timestamp + INTERVAL_SECONDS, timezone.utc)
    completed_day = close_dt.date() - timedelta(days=1)
    return completed_day.isoformat()


def date_from_ts(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def pct(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.1f}%"


def pp(value: Optional[float]) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):+.1f}%p"


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
