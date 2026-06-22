"""Binance OHLCV collection and local caching."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_BASE_URLS = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
)

INTERVAL_SECONDS = {
    "1d": 24 * 60 * 60,
    "4h": 4 * 60 * 60,
    "1h": 60 * 60,
    "15m": 15 * 60,
}


def load_or_fetch_many(
    symbols: Iterable[str],
    interval: str,
    start: str,
    raw_dir: Path,
    refresh: bool = False,
) -> Dict[str, List[dict]]:
    return {
        symbol: load_or_fetch_ohlcv(symbol, interval, start, raw_dir, refresh=refresh)
        for symbol in symbols
    }


def load_or_fetch_ohlcv(
    symbol: str,
    interval: str,
    start: str,
    raw_dir: Path,
    refresh: bool = False,
) -> List[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_path = raw_dir / f"{symbol}_{interval}.json"
    cached = _read_cache(cache_path)
    if cached and not refresh and not _is_stale(cached, interval):
        return cached

    candles = fetch_ohlcv(symbol, interval, start)
    if candles:
        cache_path.write_text(json.dumps(candles, ensure_ascii=False), encoding="utf-8")
        return candles
    return cached


def fetch_ohlcv(symbol: str, interval: str, start: str, end: Optional[str] = None) -> List[dict]:
    if interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported interval: {interval}")

    start_ms = _date_to_ms(start)
    end_ms = _date_to_ms(end) if end else int(datetime.now(timezone.utc).timestamp() * 1000)
    interval_ms = INTERVAL_SECONDS[interval] * 1000
    rows: List[dict] = []
    cursor = start_ms

    while cursor < end_ms:
        batch = _request_klines(symbol, interval, cursor, end_ms)
        if not batch:
            break
        for item in batch:
            rows.append(_normalize_kline(item))
        next_cursor = int(batch[-1][0]) + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.12)

    deduped = {item["time"]: item for item in rows}
    return [deduped[key] for key in sorted(deduped)]


def _request_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    query = urlencode(
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        }
    )
    last_error: Optional[Exception] = None
    for base_url in BINANCE_BASE_URLS:
        request = Request(
            f"{base_url}/api/v3/klines?{query}",
            headers={"User-Agent": "crypto-regime-map/0.1"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
    if last_error:
        raise RuntimeError(f"Binance kline request failed for {symbol}: {last_error}") from last_error
    return []


def _normalize_kline(item: list) -> dict:
    return {
        "time": int(item[0]) // 1000,
        "open": float(item[1]),
        "high": float(item[2]),
        "low": float(item[3]),
        "close": float(item[4]),
        "volume": float(item[5]),
    }


def _read_cache(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _is_stale(candles: List[dict], interval: str) -> bool:
    if not candles:
        return True
    interval_seconds = INTERVAL_SECONDS.get(interval)
    if interval_seconds is None:
        return True
    now = int(datetime.now(timezone.utc).timestamp())
    latest_open = int(candles[-1]["time"])
    return now - latest_open > interval_seconds


def _date_to_ms(value: Optional[str]) -> int:
    if not value:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)
