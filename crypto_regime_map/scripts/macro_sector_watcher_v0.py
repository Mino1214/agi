"""Macro / Sector Watcher v0.

Read-only observer for macro proxies, crypto sector strength, and RWA watchlist
state. This script intentionally does not import or modify Alpha Long Engine
v1.2 strategy code or Paper Engine order logic.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
RAW_DIR = ROOT / "data" / "raw"
PAPER_STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2"
MACRO_SECTOR_DIR = ROOT / "data" / "macro_sector"
SECTOR_MAP_PATH = MACRO_SECTOR_DIR / "sector_map.yaml"
DAILY_CSV_PATH = MACRO_SECTOR_DIR / "macro_sector_daily.csv"
REPORT_PATH = ROOT / "reports" / "macro_sector_watcher_v0_report.md"

ACTIVE_UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "ADAUSDT",
    "TONUSDT",
)
WATCHLIST = ("ONDOUSDT", "MKRUSDT", "AAVEUSDT")
RWA_RELATED_SECTORS = {
    "rwa",
    "rwa_infra",
    "oracle",
    "defi_lending",
    "defi",
    "real_world_yield",
    "tokenization_infra",
}
STABLECOIN_IDS = (
    "tether",
    "usd-coin",
    "dai",
    "first-digital-usd",
    "ethena-usde",
    "usds",
    "frax",
    "paypal-usd",
)

DEFAULT_SECTOR_MAP = {
    "active_universe": {
        "BTCUSDT": {"asset": "BTC", "sectors": ["store_of_value"]},
        "ETHUSDT": {"asset": "ETH", "sectors": ["smart_contract", "tokenization_infra"]},
        "SOLUSDT": {"asset": "SOL", "sectors": ["high_beta_l1"]},
        "BNBUSDT": {"asset": "BNB", "sectors": ["exchange_ecosystem"]},
        "XRPUSDT": {"asset": "XRP", "sectors": ["payments"]},
        "LINKUSDT": {"asset": "LINK", "sectors": ["oracle", "rwa_infra"]},
        "AVAXUSDT": {"asset": "AVAX", "sectors": ["l1", "institutional_subnet"]},
        "ADAUSDT": {"asset": "ADA", "sectors": ["l1"]},
        "TONUSDT": {"asset": "TON", "sectors": ["consumer_l1"]},
    },
    "watchlist": {
        "ONDOUSDT": {"asset": "ONDO", "sectors": ["rwa"]},
        "MKRUSDT": {"asset": "MKR", "sectors": ["defi", "real_world_yield"]},
        "AAVEUSDT": {"asset": "AAVE", "sectors": ["defi_lending"]},
    },
    "reserved_sectors": ["stablecoin_infra", "meme_high_beta"],
}

DAILY_FIELDS = [
    "date",
    "generated_at",
    "data_asof",
    "row_type",
    "name",
    "symbol",
    "role",
    "sectors",
    "source",
    "trade_regime",
    "action_bias",
    "alpha_score",
    "rank",
    "selected",
    "top_20_passed",
    "close",
    "ret_7d_pct",
    "ret_14d_pct",
    "ret_30d_pct",
    "volume_change_7d_pct",
    "btc_relative_7d_pct",
    "btc_relative_14d_pct",
    "btc_relative_30d_pct",
    "sector_member_count",
    "sector_active_member_count",
    "sector_watchlist_member_count",
    "sector_avg_ret_7d_pct",
    "sector_avg_ret_14d_pct",
    "sector_avg_ret_30d_pct",
    "sector_avg_alpha_score",
    "sector_avg_volume_change_7d_pct",
    "sector_relative_strength_7d_pct",
    "macro_value",
    "macro_unit",
    "macro_change_7d",
    "macro_change_30d",
    "notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Macro / Sector Watcher v0 report")
    parser.add_argument("--sector-map", default=str(SECTOR_MAP_PATH))
    parser.add_argument("--daily-csv", default=str(DAILY_CSV_PATH))
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--paper-state-dir", default=str(PAPER_STATE_DIR))
    parser.add_argument("--offline", action="store_true", help="Do not fetch macro or missing watchlist data.")
    parser.add_argument("--now-ts", type=int, default=0)
    parser.add_argument("--tokenized-treasury-market-size-usd", type=float, default=None)
    parser.add_argument("--tokenized-treasury-source", default="manual_input")
    args = parser.parse_args()

    result = generate_report(
        sector_map_path=Path(args.sector_map),
        daily_csv_path=Path(args.daily_csv),
        report_path=Path(args.report_path),
        paper_state_dir=Path(args.paper_state_dir),
        offline=args.offline,
        now_ts=args.now_ts or None,
        tokenized_treasury_market_size_usd=args.tokenized_treasury_market_size_usd,
        tokenized_treasury_source=args.tokenized_treasury_source,
    )
    print(result["report_path"])


def generate_report(
    sector_map_path: Path = SECTOR_MAP_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
    report_path: Path = REPORT_PATH,
    paper_state_dir: Path = PAPER_STATE_DIR,
    offline: bool = False,
    now_ts: Optional[int] = None,
    tokenized_treasury_market_size_usd: Optional[float] = None,
    tokenized_treasury_source: str = "manual_input",
) -> dict:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    generated_at = ts_label(now_ts)
    observation_date = datetime.fromtimestamp(now_ts, timezone.utc).date().isoformat()

    sector_map = load_sector_map(sector_map_path)
    signals = latest_signal_rows(paper_state_dir)
    equity = latest_equity_row(paper_state_dir)
    asset_rows = build_asset_rows(sector_map, signals, now_ts, offline)
    sector_rows = build_sector_rows(asset_rows)
    macro_rows = build_macro_rows(
        offline=offline,
        tokenized_treasury_market_size_usd=tokenized_treasury_market_size_usd,
        tokenized_treasury_source=tokenized_treasury_source,
    )
    alignment = build_alignment(asset_rows, sector_rows, signals, equity)

    data_asof = latest_data_asof(asset_rows) or observation_date
    csv_rows = build_daily_rows(
        observation_date=observation_date,
        generated_at=generated_at,
        data_asof=data_asof,
        asset_rows=asset_rows,
        sector_rows=sector_rows,
        macro_rows=macro_rows,
        alignment=alignment,
    )
    write_daily_csv(daily_csv_path, observation_date, csv_rows)

    report_text = build_markdown(
        generated_at=generated_at,
        data_asof=data_asof,
        asset_rows=asset_rows,
        sector_rows=sector_rows,
        macro_rows=macro_rows,
        equity=equity,
        alignment=alignment,
        offline=offline,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")

    return {
        "report_path": report_path,
        "daily_csv_path": daily_csv_path,
        "sector_map_path": sector_map_path,
        "rows_written": len(csv_rows),
    }


def load_sector_map(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_default_sector_map(path)
    parsed = parse_simple_sector_yaml(path.read_text(encoding="utf-8"))
    if not parsed["active_universe"] and not parsed["watchlist"]:
        return DEFAULT_SECTOR_MAP
    return parsed


def write_default_sector_map(path: Path) -> None:
    lines = [
        "# Macro / Sector Watcher v0 sector tags.",
        "# Observation only. Alpha Long Engine v1.2 and Paper Engine do not import this file.",
        "",
    ]
    for section in ("active_universe", "watchlist"):
        lines.append(f"{section}:")
        for symbol, info in DEFAULT_SECTOR_MAP[section].items():
            lines.extend(
                [
                    f"  {symbol}:",
                    f"    asset: {info['asset']}",
                    "    sectors:",
                ]
            )
            lines.extend(f"      - {sector}" for sector in info["sectors"])
    lines.append("")
    lines.append("reserved_sectors:")
    lines.extend(f"  - {sector}" for sector in DEFAULT_SECTOR_MAP["reserved_sectors"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_simple_sector_yaml(text: str) -> dict:
    parsed = {"active_universe": {}, "watchlist": {}, "reserved_sectors": []}
    section = ""
    symbol = ""
    in_sectors = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            symbol = ""
            in_sectors = False
            continue
        if section in {"active_universe", "watchlist"}:
            if indent == 2 and stripped.endswith(":"):
                symbol = stripped[:-1].upper()
                parsed[section][symbol] = {"asset": symbol.replace("USDT", ""), "sectors": []}
                in_sectors = False
            elif symbol and indent == 4 and stripped.startswith("asset:"):
                parsed[section][symbol]["asset"] = stripped.split(":", 1)[1].strip()
                in_sectors = False
            elif symbol and indent == 4 and stripped == "sectors:":
                in_sectors = True
            elif symbol and in_sectors and indent == 6 and stripped.startswith("- "):
                parsed[section][symbol]["sectors"].append(stripped[2:].strip())
        elif section == "reserved_sectors" and indent == 2 and stripped.startswith("- "):
            parsed["reserved_sectors"].append(stripped[2:].strip())
    return parsed


def flatten_sector_map(sector_map: dict) -> List[dict]:
    rows = []
    for section, role in (("active_universe", "alpha_universe"), ("watchlist", "watchlist")):
        for symbol, info in sector_map.get(section, {}).items():
            rows.append(
                {
                    "symbol": symbol.upper(),
                    "asset": info.get("asset") or symbol.replace("USDT", ""),
                    "role": role,
                    "sectors": list(info.get("sectors") or []),
                }
            )
    return rows


def latest_signal_rows(state_dir: Path) -> List[dict]:
    rows = read_csv_rows(state_dir / "paper_signals.csv")
    rows = [row for row in rows if to_int(row.get("signal_time")) is not None]
    if not rows:
        return []
    latest_time = max(to_int(row.get("signal_time")) or 0 for row in rows)
    return [row for row in rows if to_int(row.get("signal_time")) == latest_time]


def latest_equity_row(state_dir: Path) -> dict:
    rows = read_csv_rows(state_dir / "paper_equity.csv")
    return rows[-1] if rows else {}


def build_asset_rows(sector_map: dict, signal_rows: List[dict], now_ts: int, offline: bool) -> List[dict]:
    signal_by_symbol = {row.get("symbol", "").upper(): row for row in signal_rows}
    assets = []
    for item in flatten_sector_map(sector_map):
        symbol = item["symbol"]
        candles, source, note = load_daily_candles(symbol, now_ts, allow_fetch=not offline)
        latest = candles[-1] if candles else {}
        signal = signal_by_symbol.get(symbol, {})
        row = {
            **item,
            "source": source,
            "notes": note,
            "data_asof": candle_date(latest) if latest else "",
            "close": to_float(latest.get("close")) if latest else None,
            "ret_7d_pct": pct_return(candles, 7),
            "ret_14d_pct": pct_return(candles, 14),
            "ret_30d_pct": pct_return(candles, 30),
            "volume_change_7d_pct": volume_change_pct(candles, 7),
            "alpha_score": to_float(signal.get("alpha_score")),
            "rank": signal.get("rank", ""),
            "selected": signal.get("selected", ""),
            "top_20_passed": signal.get("top_20_passed", ""),
            "trade_regime": signal.get("trade_regime", ""),
            "action_bias": signal.get("trade_action_bias", ""),
        }
        assets.append(row)

    btc = next((row for row in assets if row["symbol"] == "BTCUSDT"), {})
    for row in assets:
        row["btc_relative_7d_pct"] = subtract(row.get("ret_7d_pct"), btc.get("ret_7d_pct"))
        row["btc_relative_14d_pct"] = subtract(row.get("ret_14d_pct"), btc.get("ret_14d_pct"))
        row["btc_relative_30d_pct"] = subtract(row.get("ret_30d_pct"), btc.get("ret_30d_pct"))
    return assets


def load_daily_candles(symbol: str, now_ts: int, allow_fetch: bool) -> Tuple[List[dict], str, str]:
    path = RAW_DIR / f"{symbol}_1d.json"
    candles = read_json_rows(path)
    candles = sorted((row for row in candles if to_int(row.get("time"), 0) <= now_ts), key=lambda row: int(row["time"]))
    if candles:
        return candles, str(path.relative_to(ROOT)), ""
    if not allow_fetch:
        return [], "", "daily_ohlcv_unavailable_offline"
    fetched = fetch_binance_daily(symbol, now_ts=now_ts)
    if fetched:
        return fetched, "binance_spot_api", "fetched_for_observation_only"
    return [], "", "daily_ohlcv_unavailable"


def fetch_binance_daily(symbol: str, now_ts: int, days: int = 120) -> List[dict]:
    start_ms = max(0, now_ts - days * 86400) * 1000
    end_ms = now_ts * 1000
    query = urlencode(
        {
            "symbol": symbol.upper(),
            "interval": "1d",
            "startTime": int(start_ms),
            "endTime": int(end_ms),
            "limit": 1000,
        }
    )
    try:
        payload = fetch_json(f"https://api.binance.com/api/v3/klines?{query}", timeout=12)
    except RuntimeError:
        try:
            payload = fetch_json(f"https://data-api.binance.vision/api/v3/klines?{query}", timeout=12)
        except RuntimeError:
            return []
    rows = []
    for item in payload if isinstance(payload, list) else []:
        rows.append(
            {
                "time": int(item[0]) // 1000,
                "open": to_float(item[1]),
                "high": to_float(item[2]),
                "low": to_float(item[3]),
                "close": to_float(item[4]),
                "volume": to_float(item[5]),
            }
        )
    return rows


def build_sector_rows(asset_rows: List[dict]) -> List[dict]:
    sectors = sorted({sector for row in asset_rows for sector in row["sectors"]})
    rows = []
    btc_ret = next((row.get("ret_7d_pct") for row in asset_rows if row["symbol"] == "BTCUSDT"), None)
    for sector in sectors:
        members = [row for row in asset_rows if sector in row["sectors"]]
        available = [row for row in members if row.get("close") is not None]
        avg_7d = mean_present(row.get("ret_7d_pct") for row in available)
        rows.append(
            {
                "sector": sector,
                "members": [row["asset"] for row in members],
                "active_members": [row["asset"] for row in members if row["role"] == "alpha_universe"],
                "watchlist_members": [row["asset"] for row in members if row["role"] == "watchlist"],
                "avg_ret_7d_pct": avg_7d,
                "avg_ret_14d_pct": mean_present(row.get("ret_14d_pct") for row in available),
                "avg_ret_30d_pct": mean_present(row.get("ret_30d_pct") for row in available),
                "avg_alpha_score": mean_present(row.get("alpha_score") for row in members),
                "avg_volume_change_7d_pct": mean_present(row.get("volume_change_7d_pct") for row in available),
                "relative_strength_7d_pct": subtract(avg_7d, btc_ret),
                "member_count": len(members),
                "active_member_count": sum(1 for row in members if row["role"] == "alpha_universe"),
                "watchlist_member_count": sum(1 for row in members if row["role"] == "watchlist"),
            }
        )
    return rows


def build_macro_rows(
    offline: bool,
    tokenized_treasury_market_size_usd: Optional[float],
    tokenized_treasury_source: str,
) -> List[dict]:
    rows = []
    if offline:
        rows.extend(unavailable_macro_rows())
    else:
        rows.append(fetch_yahoo_macro("DXY", "DX-Y.NYB", "index_level"))
        treasury_rows = fetch_treasury_yield_curve_rows()
        ten_year = treasury_yield_macro("US 10Y yield", "10Y", treasury_rows)
        two_year = treasury_yield_macro("US 2Y yield", "2Y", treasury_rows)
        if ten_year.get("value") is None or two_year.get("value") is None:
            if ten_year.get("value") is None:
                ten_year = fetch_fred_macro("US 10Y yield", "DGS10", "yield_pct")
            if two_year.get("value") is None:
                two_year = fetch_fred_macro("US 2Y yield", "DGS2", "yield_pct")
        rows.append(ten_year)
        rows.append(two_year)
        rows.append(fetch_yahoo_macro("QQQ", "QQQ", "price_usd"))
        rows.append(fetch_yahoo_macro("Gold", "GC=F", "price_usd"))
        rows.append(fetch_btc_dominance())
        rows.append(fetch_stablecoin_supply())

    rows.append(
        {
            "name": "tokenized_treasury_market_size",
            "value": tokenized_treasury_market_size_usd,
            "unit": "usd",
            "change_7d": None,
            "change_30d": None,
            "source": tokenized_treasury_source if tokenized_treasury_market_size_usd is not None else "manual_input_missing",
            "notes": "manual_input" if tokenized_treasury_market_size_usd is not None else "not_recorded",
        }
    )
    return rows


def unavailable_macro_rows() -> List[dict]:
    names = [
        ("DXY", "index_level"),
        ("US 10Y yield", "yield_pct"),
        ("US 2Y yield", "yield_pct"),
        ("QQQ", "price_usd"),
        ("Gold", "price_usd"),
        ("BTC dominance", "pct"),
        ("stablecoin_supply", "usd"),
    ]
    return [
        {
            "name": name,
            "value": None,
            "unit": unit,
            "change_7d": None,
            "change_30d": None,
            "source": "",
            "notes": "offline_mode",
        }
        for name, unit in names
    ]


def fetch_yahoo_macro(name: str, symbol: str, unit: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?range=6mo&interval=1d"
    try:
        payload = fetch_json(url, timeout=12)
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
        series = []
        for ts, close in zip(timestamps, closes):
            value = to_float(close)
            if value is not None:
                series.append((datetime.fromtimestamp(int(ts), timezone.utc).date(), value))
        return macro_from_series(name, unit, f"yahoo:{symbol}", series, change_mode="pct")
    except (KeyError, IndexError, RuntimeError, TypeError, ValueError) as exc:
        return macro_unavailable(name, unit, f"yahoo:{symbol}", str(exc))


def fetch_fred_macro(name: str, series_id: str, unit: str) -> dict:
    start = (datetime.now(timezone.utc).date() - timedelta(days=240)).isoformat()
    query = urlencode({"id": series_id, "observation_start": start})
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}"
    try:
        text = fetch_text(url, timeout=12)
        series = []
        for row in csv.DictReader(text.splitlines()):
            value = to_float(row.get(series_id))
            if value is None:
                continue
            series.append((date.fromisoformat(row["observation_date"]), value))
        return macro_from_series(name, unit, f"fred:{series_id}", series, change_mode="diff")
    except (RuntimeError, ValueError, KeyError) as exc:
        return macro_unavailable(name, unit, f"fred:{series_id}", str(exc))


def fetch_treasury_yield_curve_rows() -> List[dict]:
    year = datetime.now(timezone.utc).date().year
    query = urlencode({"type": "daily_treasury_yield_curve", "field_tdr_date_value": year})
    url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?{query}"
    try:
        text = fetch_text(url, timeout=12)
    except RuntimeError:
        return []
    rows = []
    for block in re.findall(r"<tr>\s*(.*?)</tr>", text, flags=re.S):
        date_match = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})', block)
        if not date_match:
            continue
        item = {"date": date.fromisoformat(date_match.group(1))}
        for field, label in (("2year", "2Y"), ("10year", "10Y")):
            cell = treasury_cell(block, field)
            item[label] = to_float(cell)
        if item.get("2Y") is not None or item.get("10Y") is not None:
            rows.append(item)
    return rows


def treasury_cell(row_block: str, field: str) -> str:
    for cell in re.findall(r"<td[^>]*>.*?</td>", row_block, flags=re.S):
        if f"view-field-bc-{field}-table-column" not in cell:
            continue
        inner = re.sub(r"<[^>]+>", "", cell)
        return inner.replace("&nbsp;", " ").strip()
    return ""


def treasury_yield_macro(name: str, field: str, rows: List[dict]) -> dict:
    series = [(row["date"], row[field]) for row in rows if row.get(field) is not None]
    if not series:
        return macro_unavailable(name, "yield_pct", "treasury:daily_yield_curve", "empty_series")
    return macro_from_series(name, "yield_pct", "treasury:daily_yield_curve", series, change_mode="diff")


def fetch_btc_dominance() -> dict:
    try:
        payload = fetch_json("https://api.coingecko.com/api/v3/global", timeout=12)
        value = to_float(payload["data"]["market_cap_percentage"].get("btc"))
        return {
            "name": "BTC dominance",
            "value": value,
            "unit": "pct",
            "change_7d": None,
            "change_30d": None,
            "source": "coingecko:global",
            "notes": "current_snapshot_only",
        }
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return macro_unavailable("BTC dominance", "pct", "coingecko:global", str(exc))


def fetch_stablecoin_supply() -> dict:
    query = urlencode(
        {
            "vs_currency": "usd",
            "ids": ",".join(STABLECOIN_IDS),
            "order": "market_cap_desc",
            "per_page": len(STABLECOIN_IDS),
            "page": 1,
            "sparkline": "false",
        }
    )
    try:
        payload = fetch_json(f"https://api.coingecko.com/api/v3/coins/markets?{query}", timeout=12)
        market_caps = [to_float(item.get("market_cap")) for item in payload if isinstance(item, dict)]
        value = sum(item for item in market_caps if item is not None)
        return {
            "name": "stablecoin_supply",
            "value": value if value > 0 else None,
            "unit": "usd",
            "change_7d": None,
            "change_30d": None,
            "source": "coingecko:coins_markets",
            "notes": "major_stablecoin_market_cap_sum_snapshot",
        }
    except (RuntimeError, TypeError, ValueError) as exc:
        return macro_unavailable("stablecoin_supply", "usd", "coingecko:coins_markets", str(exc))


def macro_from_series(name: str, unit: str, source: str, series: List[Tuple[date, float]], change_mode: str) -> dict:
    clean = sorted((day, value) for day, value in series if value is not None)
    if not clean:
        return macro_unavailable(name, unit, source, "empty_series")
    latest_day, latest_value = clean[-1]
    value_7d = value_on_or_before(clean, latest_day - timedelta(days=7))
    value_30d = value_on_or_before(clean, latest_day - timedelta(days=30))
    return {
        "name": name,
        "value": latest_value,
        "unit": unit,
        "change_7d": change_value(latest_value, value_7d, change_mode),
        "change_30d": change_value(latest_value, value_30d, change_mode),
        "source": source,
        "notes": f"asof={latest_day.isoformat()}",
    }


def macro_unavailable(name: str, unit: str, source: str, note: str) -> dict:
    return {
        "name": name,
        "value": None,
        "unit": unit,
        "change_7d": None,
        "change_30d": None,
        "source": source,
        "notes": f"unavailable:{note}",
    }


def build_alignment(asset_rows: List[dict], sector_rows: List[dict], signal_rows: List[dict], equity: dict) -> dict:
    signal_symbols = [row.get("symbol", "").upper() for row in signal_rows if truthy(row.get("selected"))]
    signal_type = "selected"
    if not signal_symbols:
        signal_symbols = [row.get("symbol", "").upper() for row in signal_rows if truthy(row.get("top_20_passed"))]
        signal_type = "top_20_passed"
    if not signal_symbols:
        scored = sorted(
            (row for row in asset_rows if row.get("alpha_score") is not None),
            key=lambda row: row["alpha_score"],
            reverse=True,
        )
        signal_symbols = [row["symbol"] for row in scored[:3]]
        signal_type = "top_alpha_score_snapshot" if signal_symbols else "none"

    asset_by_symbol = {row["symbol"]: row for row in asset_rows}
    signal_assets = [asset_by_symbol[symbol] for symbol in signal_symbols if symbol in asset_by_symbol]
    signal_sectors = sorted({sector for row in signal_assets for sector in row["sectors"]})
    strong_sectors = [row["sector"] for row in top_sectors(sector_rows, strongest=True, active_only=True, limit=3)]
    overlap = sorted(set(signal_sectors) & set(strong_sectors))
    action_bias = equity.get("current_action_bias") or first_present(row.get("action_bias") for row in asset_rows)
    trade_regime = equity.get("current_regime") or first_present(row.get("trade_regime") for row in asset_rows)

    if not signal_assets:
        status = "no_alpha_signal_snapshot"
    elif action_bias in {"reduce_risk", "no_new_entry", "wait"} and signal_type != "selected":
        status = "no_entry_allowed_observation_only"
    elif overlap:
        status = "aligned_with_strong_sector"
    else:
        status = "not_aligned_with_top_strength"

    return {
        "status": status,
        "signal_type": signal_type,
        "symbols": [row["asset"] for row in signal_assets],
        "sectors": signal_sectors,
        "strong_sectors": strong_sectors,
        "overlap": overlap,
        "trade_regime": trade_regime or "",
        "action_bias": action_bias or "",
        "notes": "observation_only_not_used_for_order_decisions",
    }


def build_daily_rows(
    observation_date: str,
    generated_at: str,
    data_asof: str,
    asset_rows: List[dict],
    sector_rows: List[dict],
    macro_rows: List[dict],
    alignment: dict,
) -> List[dict]:
    rows = []
    for row in asset_rows:
        rows.append(
            base_daily_row(observation_date, generated_at, row.get("data_asof") or data_asof)
            | {
                "row_type": "asset",
                "name": row["asset"],
                "symbol": row["symbol"],
                "role": row["role"],
                "sectors": "|".join(row["sectors"]),
                "source": row["source"],
                "trade_regime": row.get("trade_regime", ""),
                "action_bias": row.get("action_bias", ""),
                "alpha_score": row.get("alpha_score"),
                "rank": row.get("rank", ""),
                "selected": row.get("selected", ""),
                "top_20_passed": row.get("top_20_passed", ""),
                "close": row.get("close"),
                "ret_7d_pct": row.get("ret_7d_pct"),
                "ret_14d_pct": row.get("ret_14d_pct"),
                "ret_30d_pct": row.get("ret_30d_pct"),
                "volume_change_7d_pct": row.get("volume_change_7d_pct"),
                "btc_relative_7d_pct": row.get("btc_relative_7d_pct"),
                "btc_relative_14d_pct": row.get("btc_relative_14d_pct"),
                "btc_relative_30d_pct": row.get("btc_relative_30d_pct"),
                "notes": row.get("notes", ""),
            }
        )
    for row in sector_rows:
        rows.append(
            base_daily_row(observation_date, generated_at, data_asof)
            | {
                "row_type": "sector",
                "name": row["sector"],
                "role": "mixed" if row["watchlist_member_count"] else "alpha_universe",
                "sectors": row["sector"],
                "sector_member_count": row["member_count"],
                "sector_active_member_count": row["active_member_count"],
                "sector_watchlist_member_count": row["watchlist_member_count"],
                "sector_avg_ret_7d_pct": row.get("avg_ret_7d_pct"),
                "sector_avg_ret_14d_pct": row.get("avg_ret_14d_pct"),
                "sector_avg_ret_30d_pct": row.get("avg_ret_30d_pct"),
                "sector_avg_alpha_score": row.get("avg_alpha_score"),
                "sector_avg_volume_change_7d_pct": row.get("avg_volume_change_7d_pct"),
                "sector_relative_strength_7d_pct": row.get("relative_strength_7d_pct"),
                "notes": "members=" + "|".join(row["members"]),
            }
        )
    for row in macro_rows:
        rows.append(
            base_daily_row(observation_date, generated_at, data_asof)
            | {
                "row_type": "macro",
                "name": row["name"],
                "source": row.get("source", ""),
                "macro_value": row.get("value"),
                "macro_unit": row.get("unit", ""),
                "macro_change_7d": row.get("change_7d"),
                "macro_change_30d": row.get("change_30d"),
                "notes": row.get("notes", ""),
            }
        )
    rows.append(
        base_daily_row(observation_date, generated_at, data_asof)
        | {
            "row_type": "alignment",
            "name": "alpha_signal_sector_alignment",
            "trade_regime": alignment["trade_regime"],
            "action_bias": alignment["action_bias"],
            "notes": (
                f"status={alignment['status']};signal_type={alignment['signal_type']};"
                f"symbols={'|'.join(alignment['symbols'])};sectors={'|'.join(alignment['sectors'])};"
                f"strong_sectors={'|'.join(alignment['strong_sectors'])};overlap={'|'.join(alignment['overlap'])};"
                f"{alignment['notes']}"
            ),
        }
    )
    return [{field: csv_cell(row.get(field, "")) for field in DAILY_FIELDS} for row in rows]


def base_daily_row(observation_date: str, generated_at: str, data_asof: str) -> dict:
    return {"date": observation_date, "generated_at": generated_at, "data_asof": data_asof}


def write_daily_csv(path: Path, observation_date: str, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_csv_rows(path)
    kept = [row for row in existing if row.get("date") != observation_date]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        for row in kept + rows:
            writer.writerow({field: row.get(field, "") for field in DAILY_FIELDS})


def build_markdown(
    generated_at: str,
    data_asof: str,
    asset_rows: List[dict],
    sector_rows: List[dict],
    macro_rows: List[dict],
    equity: dict,
    alignment: dict,
    offline: bool,
) -> str:
    macro_by_name = {row["name"]: row for row in macro_rows}
    strong = top_sectors(sector_rows, strongest=True, active_only=True, limit=3)
    weak = top_sectors(sector_rows, strongest=False, active_only=True, limit=3)
    rwa_assets = [
        row
        for row in asset_rows
        if row["role"] == "watchlist" or any(sector in RWA_RELATED_SECTORS for sector in row["sectors"])
    ]
    unavailable_macro = [row["name"] for row in macro_rows if row.get("value") is None and row["name"] != "tokenized_treasury_market_size"]
    lines = [
        "# Macro / Sector Watcher v0 Report",
        "",
        f"- generated_at: {generated_at}",
        f"- data_asof: {data_asof}",
        "- mode: 관찰 전용 / 매매 미반영",
        "- boundary: Alpha Long Engine v1.2 진입/청산 로직 미수정, Paper Engine 주문 로직 미수정",
        "- oos_policy: OOS 전략 성과와 섞지 않고 data/macro_sector 아래에 별도 기록",
        f"- fetch_mode: {'offline' if offline else 'best_effort_online'}",
        "",
        "## Dashboard Cards",
        "",
        "### Macro 상태 카드",
        markdown_table(
            ["item", "value"],
            [
                ["trade_regime/action_bias", f"{alignment['trade_regime'] or '-'} / {alignment['action_bias'] or '-'}"],
                ["macro_summary", macro_environment_summary(macro_by_name)],
                ["DXY", macro_display(macro_by_name.get("DXY"))],
                ["US 10Y yield", macro_display(macro_by_name.get("US 10Y yield"))],
                ["US 2Y yield", macro_display(macro_by_name.get("US 2Y yield"))],
                ["QQQ", macro_display(macro_by_name.get("QQQ"))],
                ["Gold", macro_display(macro_by_name.get("Gold"))],
                ["BTC dominance", macro_display(macro_by_name.get("BTC dominance"))],
                ["stablecoin supply", macro_display(macro_by_name.get("stablecoin_supply"))],
            ],
        ),
        "",
        "### Sector strength 카드",
        markdown_table(
            ["side", "sector", "members", "7D avg", "7D vs BTC", "alpha avg", "volume 7D chg"],
            [["strong", *sector_display(row)] for row in strong] + [["weak", *sector_display(row)] for row in weak],
        ),
        "",
        "### RWA watch 카드",
        markdown_table(
            ["asset/sector", "role", "7D", "30D", "vs BTC 7D", "status"],
            rwa_watch_rows(rwa_assets, sector_rows, macro_by_name),
        ),
        "",
        "## 오늘 강한 섹터",
        markdown_table(["sector", "members", "7D avg", "7D vs BTC", "30D avg"], [sector_short_row(row) for row in strong]),
        "",
        "## 오늘 약한 섹터",
        markdown_table(["sector", "members", "7D avg", "7D vs BTC", "30D avg"], [sector_short_row(row) for row in weak]),
        "",
        "## Alpha Signal / Sector Alignment",
        markdown_table(
            ["item", "value"],
            [
                ["status", alignment["status"]],
                ["signal_type", alignment["signal_type"]],
                ["signal_symbols", ", ".join(alignment["symbols"]) or "-"],
                ["signal_sectors", ", ".join(alignment["sectors"]) or "-"],
                ["top_strength_sectors", ", ".join(alignment["strong_sectors"]) or "-"],
                ["overlap", ", ".join(alignment["overlap"]) or "-"],
                ["order_usage", "관찰 전용 / 주문 결정 미반영"],
            ],
        ),
        "",
        "## RWA / Tokenization Watch",
        markdown_table(
            ["item", "value"],
            [
                ["RWA watchlist", watchlist_summary(asset_rows)],
                ["oracle sector 7D", sector_metric(sector_rows, "oracle", "avg_ret_7d_pct")],
                ["DeFi lending sector 7D", sector_metric(sector_rows, "defi_lending", "avg_ret_7d_pct")],
                ["tokenization infra sector 7D", sector_metric(sector_rows, "tokenization_infra", "avg_ret_7d_pct")],
                ["tokenized treasury market size", macro_display(macro_by_name.get("tokenized_treasury_market_size"))],
            ],
        ),
        "",
        "## Data Availability",
        markdown_table(
            ["item", "value"],
            [
                ["asset_rows", str(len(asset_rows))],
                ["asset_data_available", str(sum(1 for row in asset_rows if row.get("close") is not None))],
                ["macro_unavailable", ", ".join(unavailable_macro) or "-"],
                ["latest_equity_timestamp", equity.get("date", "-") if equity else "-"],
            ],
        ),
    ]
    return "\n".join(lines) + "\n"


def top_sectors(sector_rows: List[dict], strongest: bool, active_only: bool, limit: int) -> List[dict]:
    rows = [
        row
        for row in sector_rows
        if row.get("avg_ret_7d_pct") is not None and (not active_only or row.get("active_member_count", 0) > 0)
    ]
    return sorted(rows, key=lambda row: (row.get("relative_strength_7d_pct") is None, row.get("relative_strength_7d_pct") or 0), reverse=strongest)[
        :limit
    ]


def sector_display(row: dict) -> List[str]:
    return [
        row["sector"],
        ", ".join(row["members"]),
        fmt_pct(row.get("avg_ret_7d_pct")),
        fmt_pct(row.get("relative_strength_7d_pct")),
        fmt_float(row.get("avg_alpha_score")),
        fmt_pct(row.get("avg_volume_change_7d_pct")),
    ]


def sector_short_row(row: dict) -> List[str]:
    return [
        row["sector"],
        ", ".join(row["members"]),
        fmt_pct(row.get("avg_ret_7d_pct")),
        fmt_pct(row.get("relative_strength_7d_pct")),
        fmt_pct(row.get("avg_ret_30d_pct")),
    ]


def rwa_watch_rows(asset_rows: List[dict], sector_rows: List[dict], macro_by_name: Dict[str, dict]) -> List[List[str]]:
    rows = []
    for row in asset_rows:
        status = "available" if row.get("close") is not None else row.get("notes") or "unavailable"
        rows.append(
            [
                row["asset"],
                row["role"],
                fmt_pct(row.get("ret_7d_pct")),
                fmt_pct(row.get("ret_30d_pct")),
                fmt_pct(row.get("btc_relative_7d_pct")),
                status,
            ]
        )
    for sector in ("oracle", "rwa", "defi_lending", "tokenization_infra"):
        sector_row = next((item for item in sector_rows if item["sector"] == sector), None)
        if sector_row:
            rows.append(
                [
                    sector,
                    "sector",
                    fmt_pct(sector_row.get("avg_ret_7d_pct")),
                    fmt_pct(sector_row.get("avg_ret_30d_pct")),
                    fmt_pct(sector_row.get("relative_strength_7d_pct")),
                    "sector_average",
                ]
            )
    rows.append(
        [
            "stablecoin_supply",
            "macro_proxy",
            "-",
            "-",
            "-",
            macro_display(macro_by_name.get("stablecoin_supply")),
        ]
    )
    return rows


def macro_environment_summary(macro_by_name: Dict[str, dict]) -> str:
    dxy = macro_by_name.get("DXY", {})
    ten = macro_by_name.get("US 10Y yield", {})
    two = macro_by_name.get("US 2Y yield", {})
    qqq = macro_by_name.get("QQQ", {})
    gold = macro_by_name.get("Gold", {})
    if not any(row.get("value") is not None for row in (dxy, ten, two, qqq, gold)):
        return "macro proxy unavailable; crypto sector-only observation"

    risk_on = 0
    risk_off = 0
    if value_gt(qqq.get("change_7d"), 0):
        risk_on += 1
    elif value_lt(qqq.get("change_7d"), 0):
        risk_off += 1
    if value_lt(dxy.get("change_7d"), 0):
        risk_on += 1
    elif value_gt(dxy.get("change_7d"), 0):
        risk_off += 1
    if value_le(ten.get("change_7d"), 0) and value_le(two.get("change_7d"), 0):
        risk_on += 1
    elif value_gt(ten.get("change_7d"), 0) or value_gt(two.get("change_7d"), 0):
        risk_off += 1
    if value_gt(gold.get("change_7d"), 0) and risk_off:
        risk_off += 1

    if risk_on > risk_off:
        bias = "risk-on leaning"
    elif risk_off > risk_on:
        bias = "macro headwind / risk-off leaning"
    else:
        bias = "mixed macro"
    return (
        f"{bias}; DXY 7D {fmt_change(dxy)}, 10Y 7D {fmt_change(ten)}, "
        f"2Y 7D {fmt_change(two)}, QQQ 7D {fmt_change(qqq)}, Gold 7D {fmt_change(gold)}"
    )


def macro_display(row: Optional[dict]) -> str:
    if not row or row.get("value") is None:
        return "unavailable"
    value = row["value"]
    unit = row.get("unit", "")
    if unit == "usd":
        value_text = fmt_usd(value)
    elif unit == "pct" or unit == "yield_pct":
        value_text = f"{fmt_float(value)}%"
    else:
        value_text = fmt_float(value)
    return f"{value_text} ({fmt_change(row)} 7D, source={row.get('source', '-')})"


def fmt_change(row: dict) -> str:
    value = row.get("change_7d")
    if value is None:
        return "n/a"
    if row.get("unit") == "yield_pct":
        return f"{value:+.2f}pp"
    return f"{value:+.2f}%"


def sector_metric(sector_rows: List[dict], sector: str, field: str) -> str:
    row = next((item for item in sector_rows if item["sector"] == sector), None)
    if not row:
        return "unavailable"
    return fmt_pct(row.get(field))


def watchlist_summary(asset_rows: List[dict]) -> str:
    items = []
    for symbol in WATCHLIST:
        row = next((item for item in asset_rows if item["symbol"] == symbol), None)
        if row:
            items.append(f"{row['asset']} 7D {fmt_pct(row.get('ret_7d_pct'))}")
    return "; ".join(items) or "unavailable"


def markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(str(cell) for cell in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def fetch_json(url: str, timeout: int) -> object:
    return json.loads(fetch_text(url, timeout))


def fetch_text(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": "crypto-regime-map/macro-sector-watcher-v0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def pct_return(candles: List[dict], days: int) -> Optional[float]:
    if len(candles) <= days:
        return None
    latest = to_float(candles[-1].get("close"))
    base = to_float(candles[-1 - days].get("close"))
    if latest is None or base in (None, 0):
        return None
    return (latest / base - 1) * 100


def volume_change_pct(candles: List[dict], days: int) -> Optional[float]:
    if len(candles) < days * 2:
        return None
    recent = mean_present(to_float(row.get("volume")) for row in candles[-days:])
    prior = mean_present(to_float(row.get("volume")) for row in candles[-days * 2 : -days])
    if recent is None or prior in (None, 0):
        return None
    return (recent / prior - 1) * 100


def value_on_or_before(series: List[Tuple[date, float]], target: date) -> Optional[float]:
    candidates = [value for day, value in series if day <= target]
    return candidates[-1] if candidates else None


def change_value(latest: float, prior: Optional[float], mode: str) -> Optional[float]:
    if prior in (None, 0):
        return None
    if mode == "diff":
        return latest - prior
    return (latest / prior - 1) * 100


def latest_data_asof(asset_rows: List[dict]) -> str:
    values = [row.get("data_asof", "") for row in asset_rows if row.get("data_asof")]
    return max(values) if values else ""


def candle_date(row: dict) -> str:
    ts = to_int(row.get("time"), 0)
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else ""


def subtract(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None or right is None:
        return None
    return left - right


def mean_present(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    return statistics.mean(clean) if clean else None


def first_present(values: Iterable[object]) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_float(value: object, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def value_gt(value: Optional[float], threshold: float) -> bool:
    return value is not None and value > threshold


def value_lt(value: Optional[float], threshold: float) -> bool:
    return value is not None and value < threshold


def value_le(value: Optional[float], threshold: float) -> bool:
    return value is not None and value <= threshold


def csv_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    return value


def fmt_pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def fmt_float(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def fmt_usd(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def ts_label(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    main()
