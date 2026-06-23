"""Alpha Engine v1.2 paper trading engine.

This engine is intentionally paper-only. It refreshes market data, calculates
the Alpha Engine v1.2 signal set, creates virtual orders, manages virtual long
positions, applies available funding events, and writes CSV ledgers.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
SRC = ROOT / "src"
for path in (SCRIPT_DIR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from collector import INTERVAL_SECONDS, fetch_ohlcv  # noqa: E402

import alpha_engine_v1_execution_robustness_report as rb  # noqa: E402
import alpha_engine_v1_2_4h_regime as short_regime_4h  # noqa: E402
import alpha_engine_v1_2_defensive_probe as defensive_probe_rules  # noqa: E402
import alpha_engine_v1_funding_audit_report as funding  # noqa: E402
import alpha_engine_v1_report as alpha  # noqa: E402


STRATEGY_NAME = "Alpha Engine v1.2 Paper"
STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2"
DEFENSIVE_PROBE_STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2_defensive_probe"
SHORT_REGIME_4H_STATE_DIR = ROOT / "data" / "paper_alpha_engine_v1_2_short_regime_4h"
DEFENSIVE_PROBE_LOG_NAME = "defensive_probe_log.csv"
UNIVERSE = tuple(alpha.UNIVERSE_10)
TRADING_UNIVERSE = tuple(symbol for symbol in UNIVERSE if symbol != "DOGEUSDT")
SLIPPAGE_RATE = 0.0020
TAKER_FEE_RATE = 0.0005
TOP_SCORE_PCT = 0.20
INITIAL_CASH = 1.0
DAILY_REPORT_NAME = "paper_daily_report.md"
HEALTH_STATE_NAME = "health_state.json"
PAPER_PROFILE_STATE_NAME = "paper_profile.json"
STRATEGY_LOCK_NAME = "Alpha Long Engine v1.2 No Hedge"
STRATEGY_LOCK_VERSION = "v1.2-no-hedge"

PAPER_VARIANT = rb.RobustVariant(
    STRATEGY_NAME,
    exclude_doge=True,
    top_score_pct=TOP_SCORE_PCT,
    require_liquidation_buffer=True,
    group="Paper",
)
PAPER_CONFIG = rb.RunConfig(
    variant=PAPER_VARIANT,
    market_data="spot",
    slippage_rate=SLIPPAGE_RATE,
    fee_rate=TAKER_FEE_RATE,
)


@dataclass(frozen=True)
class PaperProfile:
    profile_id: str
    label: str
    exchange_leverage: int
    size_multiplier: float
    futures_shadow: bool = False
    liquidation_touch: bool = False

    @property
    def effective_exposure(self) -> float:
        return self.exchange_leverage * self.size_multiplier

    def state_row(self) -> dict:
        return {
            "paper_profile": self.profile_id,
            "label": self.label,
            "exchange_leverage": self.exchange_leverage,
            "size_multiplier": self.size_multiplier,
            "effective_exposure": self.effective_exposure,
            "mode": "futures_paper_shadow" if self.futures_shadow else "spot_or_1x_paper",
            "futures_shadow": self.futures_shadow,
            "liquidation_touch": self.liquidation_touch,
        }


DEFAULT_PAPER_PROFILE_ID = "v0_spot_or_1x"
PAPER_PROFILES = {
    DEFAULT_PAPER_PROFILE_ID: PaperProfile(
        profile_id=DEFAULT_PAPER_PROFILE_ID,
        label="V0_SPOT_OR_1X",
        exchange_leverage=1,
        size_multiplier=1.0,
        futures_shadow=False,
    ),
    "v0_futures_3x_size25": PaperProfile(
        profile_id="v0_futures_3x_size25",
        label="V0_FUTURES_3X_SIZE25",
        exchange_leverage=3,
        size_multiplier=0.25,
        futures_shadow=True,
    ),
    "v0_futures_2x_size50": PaperProfile(
        profile_id="v0_futures_2x_size50",
        label="V0_FUTURES_2X_SIZE50",
        exchange_leverage=2,
        size_multiplier=0.50,
        futures_shadow=True,
    ),
}
DEFAULT_PAPER_PROFILE = PAPER_PROFILES[DEFAULT_PAPER_PROFILE_ID]
FUTURES_SHADOW_STATE_DIRS = {
    "v0_futures_3x_size25": ROOT / "data" / "research_cache" / "paper_v0_futures_3x_size25",
    "v0_futures_2x_size50": ROOT / "data" / "research_cache" / "paper_v0_futures_2x_size50",
}

POSITION_FIELDS = [
    "position_id",
    "status",
    "symbol",
    "side",
    "opened_at",
    "opened_at_date",
    "signal_time",
    "signal_date",
    "order_id",
    "entry_price",
    "stop_price",
    "risk_distance",
    "risk_amount",
    "units",
    "initial_units",
    "entry_equity",
    "alpha_score",
    "trade_regime",
    "trade_action_bias",
    "liquidation_leverage_used",
    "liquidation_price_est",
    "symbol_leverage_cap",
    "raw_leverage",
    "applied_leverage",
    "realized_pnl",
    "funding_pnl",
    "partial_taken",
    "partial_time",
    "partial_date",
    "partial_price",
    "last_funding_time",
    "last_update_time",
    "last_update_date",
    "last_price",
    "unrealized_pnl",
    "notional",
    "liquidation_buffer_pct",
    "liquidation_risk",
]

ORDER_FIELDS = [
    "order_id",
    "created_time",
    "created_date",
    "signal_id",
    "signal_time",
    "signal_date",
    "fill_time",
    "fill_date",
    "symbol",
    "side",
    "type",
    "status",
    "reason",
    "alpha_score",
    "trade_regime",
    "trade_action_bias",
    "entry_price",
    "units",
    "notional",
    "fee",
    "raw_leverage",
    "applied_leverage",
    "position_id",
    "updated_time",
    "updated_date",
]

TRADE_FIELDS = [
    "event_id",
    "event_type",
    "position_id",
    "order_id",
    "timestamp",
    "date",
    "symbol",
    "side",
    "price",
    "units",
    "notional",
    "fee",
    "raw_leverage",
    "applied_leverage",
    "funding_rate",
    "funding_pnl",
    "pnl",
    "cash_delta",
    "equity_after",
    "reason",
    "alpha_score",
    "trade_regime",
    "trade_action_bias",
    "entry_price",
    "stop_price",
    "exit_price",
    "position_total_pnl",
    "hold_hours",
]

EQUITY_FIELDS = [
    "timestamp",
    "date",
    "equity",
    "cash",
    "open_unrealized",
    "cumulative_pnl",
    "drawdown_pct",
    "open_positions",
    "open_notional",
    "current_regime",
    "current_action_bias",
    "strategy_status",
    "max_drawdown_pct",
    "liquidation_risk_count",
]

SIGNAL_FIELDS = [
    "signal_id",
    "signal_time",
    "signal_date",
    "fill_time",
    "fill_date",
    "symbol",
    "alpha_score",
    "rank",
    "universe_size",
    "selected",
    "rejection_reason",
    "scan_status",
    "top_20_passed",
    "entry_block_reason",
    "top_score_pct",
    "top_rank_cutoff",
    "trade_regime",
    "trade_action_bias",
    "regime_reason",
    "close",
    "ema20",
    "ema50",
    "atr14",
    "ret_7d_pct",
    "ret_14d_pct",
    "btc_excess_7d_pct",
    "btc_excess_14d_pct",
]

STATE_FILES = {
    "positions": ("paper_positions.csv", POSITION_FIELDS),
    "orders": ("paper_orders.csv", ORDER_FIELDS),
    "trades": ("paper_trades.csv", TRADE_FIELDS),
    "equity": ("paper_equity.csv", EQUITY_FIELDS),
    "signals": ("paper_signals.csv", SIGNAL_FIELDS),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha Engine v1.2 paper trading engine")
    parser.add_argument("command", nargs="?", choices=["run-once", "loop", "dashboard", "report"], default="run-once")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--use-cache", action="store_true", help="Use cached OHLCV/funding data when it is current enough.")
    parser.add_argument("--sleep", type=int, default=3600, help="Loop sleep seconds.")
    parser.add_argument("--iterations", type=int, default=0, help="Loop iterations. 0 means forever.")
    parser.add_argument("--defensive-probe", action="store_true", help="Run the separate defensive_probe test variant.")
    parser.add_argument("--regime-timeframe", choices=["1d", "4h"], default="1d", help="Use the default 1D regime or the experimental BTC 4H short regime.")
    parser.add_argument("--short-regime-4h", action="store_true", help="Alias for --regime-timeframe 4h.")
    parser.add_argument(
        "--paper-profile",
        choices=sorted(PAPER_PROFILES),
        default=DEFAULT_PAPER_PROFILE_ID,
        help="Paper execution profile. Futures shadow profiles are disabled unless explicitly selected.",
    )
    args = parser.parse_args()

    regime_timeframe = "4h" if args.short_regime_4h else args.regime_timeframe
    state_dir_is_explicit = args.state_dir is not None
    state_dir = Path(args.state_dir) if args.state_dir else STATE_DIR
    default_profile_requested = args.paper_profile == DEFAULT_PAPER_PROFILE_ID
    default_state_requested = safe_resolve(state_dir) == safe_resolve(STATE_DIR)
    if args.defensive_probe and default_profile_requested and default_state_requested:
        state_dir = DEFENSIVE_PROBE_STATE_DIR
        state_dir_is_explicit = False
    if regime_timeframe == "4h" and default_profile_requested and default_state_requested:
        state_dir = SHORT_REGIME_4H_STATE_DIR
        state_dir_is_explicit = False
    try:
        paper_profile = prepare_paper_profile_run(
            args.paper_profile,
            state_dir,
            state_dir_is_explicit=state_dir_is_explicit,
            defensive_probe=args.defensive_probe,
            regime_timeframe=regime_timeframe,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "dashboard":
        print(build_dashboard(state_dir))
        return
    if args.command == "report":
        print(write_daily_report(state_dir))
        return
    if args.command == "loop":
        iterations = 0
        while args.iterations <= 0 or iterations < args.iterations:
            result = run_once(
                state_dir,
                use_cache=args.use_cache,
                defensive_probe=args.defensive_probe,
                regime_timeframe=regime_timeframe,
                paper_profile=paper_profile,
            )
            print(result["dashboard"], flush=True)
            iterations += 1
            if args.iterations > 0 and iterations >= args.iterations:
                break
            time.sleep(args.sleep)
        return

    result = run_once(
        state_dir,
        use_cache=args.use_cache,
        defensive_probe=args.defensive_probe,
        regime_timeframe=regime_timeframe,
        paper_profile=paper_profile,
    )
    print(result["dashboard"])


def paper_profile_for_id(profile_id: Optional[str]) -> PaperProfile:
    key = profile_id or DEFAULT_PAPER_PROFILE_ID
    try:
        return PAPER_PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported paper profile: {profile_id}") from exc


def prepare_paper_profile_run(
    profile_id: Optional[str],
    state_dir: Path,
    state_dir_is_explicit: bool,
    defensive_probe: bool = False,
    regime_timeframe: str = "1d",
) -> PaperProfile:
    profile = paper_profile_for_id(profile_id)
    validate_paper_profile(profile)
    validate_paper_profile_state_dir(profile, state_dir, state_dir_is_explicit)
    if profile.futures_shadow and defensive_probe:
        raise ValueError("futures shadow profiles cannot be combined with --defensive-probe")
    if profile.futures_shadow and normalize_regime_timeframe(regime_timeframe) != "1d":
        raise ValueError("futures shadow profiles are V0 1D baseline only")
    return profile


def validate_paper_profile(profile: PaperProfile) -> None:
    if int(profile.exchange_leverage) != profile.exchange_leverage or profile.exchange_leverage < 1:
        raise ValueError("exchange leverage must be a positive integer")
    if profile.exchange_leverage > 3:
        raise ValueError("risk policy violation: max_exchange_leverage is 3")
    if profile.exchange_leverage >= 5:
        raise ValueError("risk policy violation: 5x is disabled")
    if profile.size_multiplier <= 0:
        raise ValueError("size_multiplier must be positive")
    if profile.effective_exposure > 1.0 + 1e-12:
        raise ValueError("risk policy violation: max_effective_exposure is 1.0")
    if profile.liquidation_touch:
        raise ValueError("risk policy violation: liquidation touch profiles are disabled")
    if profile.exchange_leverage == 2 and profile.size_multiplier >= 0.75 - 1e-12:
        raise ValueError("risk policy violation: 2x size 75% or higher is disabled")
    if profile.exchange_leverage == 3 and profile.size_multiplier >= 0.50 - 1e-12:
        raise ValueError("risk policy violation: 3x size 50% or higher is disabled")
    if profile.exchange_leverage >= 2 and profile.size_multiplier >= 1.0 - 1e-12:
        raise ValueError("risk policy violation: pure 2x+ exposure is disabled")


def validate_paper_profile_state_dir(profile: PaperProfile, state_dir: Path, state_dir_is_explicit: bool) -> None:
    if not profile.futures_shadow:
        return
    if not state_dir_is_explicit:
        raise ValueError("futures shadow profiles require an explicit separate --state-dir")

    state_path = safe_resolve(state_dir)
    forbidden = {
        safe_resolve(STATE_DIR),
        safe_resolve(DEFENSIVE_PROBE_STATE_DIR),
        safe_resolve(SHORT_REGIME_4H_STATE_DIR),
    }
    if state_path in forbidden:
        raise ValueError("futures shadow profiles cannot use an existing V0 paper state-dir")

    for profile_id, expected_dir in FUTURES_SHADOW_STATE_DIRS.items():
        if profile_id != profile.profile_id and state_path == safe_resolve(expected_dir):
            raise ValueError(f"state-dir belongs to a different futures shadow profile: {profile_id}")


def paper_config_for_profile(profile: PaperProfile) -> rb.RunConfig:
    if not profile.futures_shadow:
        return PAPER_CONFIG
    variant = rb.RobustVariant(
        profile.label,
        exclude_doge=True,
        top_score_pct=TOP_SCORE_PCT,
        require_liquidation_buffer=False,
        group="PaperShadow",
    )
    return rb.RunConfig(
        variant=variant,
        market_data="futures_shadow",
        slippage_rate=SLIPPAGE_RATE,
        fee_rate=TAKER_FEE_RATE,
        global_max_leverage=float(profile.exchange_leverage),
    )


def applied_leverage_for_profile(profile: PaperProfile, raw_leverage: Optional[float]) -> int:
    if profile.futures_shadow:
        return int(profile.exchange_leverage)
    return applied_leverage_from_raw(raw_leverage)


def safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def run_once(
    state_dir: Path = STATE_DIR,
    use_cache: bool = False,
    now_ts: Optional[int] = None,
    defensive_probe: bool = False,
    regime_timeframe: str = "1d",
    paper_profile: PaperProfile = DEFAULT_PAPER_PROFILE,
) -> dict:
    validate_paper_profile(paper_profile)
    regime_timeframe = normalize_regime_timeframe(regime_timeframe)
    if paper_profile.futures_shadow and defensive_probe:
        raise ValueError("futures shadow profiles cannot be combined with defensive_probe")
    if paper_profile.futures_shadow and regime_timeframe != "1d":
        raise ValueError("futures shadow profiles are V0 1D baseline only")
    if paper_profile.futures_shadow:
        validate_paper_profile_state_dir(paper_profile, state_dir, state_dir_is_explicit=True)
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    ensure_state_files(state_dir)
    ensure_paper_profile_state(state_dir, paper_profile, now_ts)
    if defensive_probe:
        ensure_defensive_probe_log(state_dir)
    operating_state = ensure_operating_state(state_dir, now_ts)
    paper_start_ts = int(operating_state.get("paper_start_timestamp") or 0)
    entry_pause_reason = health_entry_pause_reason(state_dir)
    probe_health_gate = defensive_probe_rules.health_gate_from_state(load_health_state_dict(state_dir))

    raw_1d = load_latest_raw(UNIVERSE, "1d", alpha.FETCH_DAILY_START, use_cache, now_ts)
    raw_4h = load_latest_raw(UNIVERSE, "4h", alpha.FETCH_INTRADAY_START, use_cache, now_ts)
    raw_1h = load_latest_raw(UNIVERSE, "1h", alpha.FETCH_INTRADAY_START, use_cache, now_ts)
    configure_live_window(raw_1h, now_ts)
    data = alpha.AlphaData(raw_1d=raw_1d, raw_4h=raw_4h, raw_1h=raw_1h)
    short_regime_index = short_regime_4h.build_regime_indexes(raw_4h.get("BTCUSDT", [])) if regime_timeframe == "4h" else None
    rb.ACTIVE_DATA_BY_MARKET.clear()
    rb.ACTIVE_DATA_BY_MARKET.update({"spot": data})

    positions = load_positions(state_dir)
    orders = read_csv_rows(state_dir / STATE_FILES["orders"][0])
    trades = read_csv_rows(state_dir / STATE_FILES["trades"][0])
    equity_rows = read_csv_rows(state_dir / STATE_FILES["equity"][0])
    signal_rows = read_csv_rows(state_dir / STATE_FILES["signals"][0])
    cash = float(equity_rows[-1]["cash"]) if equity_rows and equity_rows[-1].get("cash") not in {"", None} else INITIAL_CASH

    funding_index = load_funding_index([symbol for symbol in TRADING_UNIVERSE], use_cache, now_ts)
    new_trade_rows: List[dict] = []
    new_equity_rows: List[dict] = []
    last_equity_time = int(float(equity_rows[-1]["timestamp"])) if equity_rows else initial_process_time(data, now_ts)
    closed_1h_times = [
        row["time"]
        for row in data.rows_1h.get("BTCUSDT", [])
        if row["time"] + 3600 > last_equity_time and row["time"] + 3600 <= now_ts
    ]

    for open_time in closed_1h_times:
        close_time = open_time + 3600
        cash, funding_events = apply_funding_events(positions, funding_index, data, close_time, cash)
        new_trade_rows.extend(funding_events)
        cash, closed_events = manage_positions_for_bar(data, positions, open_time, close_time, cash)
        new_trade_rows.extend(closed_events)
        cash, shock_events = close_shock_positions(data, positions, open_time, close_time, cash)
        new_trade_rows.extend(shock_events)
        new_equity_rows.append(snapshot_equity(data, positions, cash, close_time, open_time, equity_rows + new_equity_rows))

    orders, cash, entry_events = fill_pending_orders(
        data,
        positions,
        orders,
        cash,
        now_ts,
        entry_pause_reason=entry_pause_reason,
        paper_start_ts=paper_start_ts,
        defensive_probe=defensive_probe,
        paper_profile=paper_profile,
    )
    new_trade_rows.extend(entry_events)

    new_signal_rows, selected_signals = generate_new_signals(
        data,
        signal_rows,
        now_ts,
        defensive_probe=defensive_probe,
        probe_health_gate=probe_health_gate,
        regime_timeframe=regime_timeframe,
        short_regime_index=short_regime_index,
        short_health_gate=probe_health_gate,
    )
    if defensive_probe:
        append_defensive_probe_log(state_dir, new_signal_rows)
    new_signal_rows, selected_signals = apply_paper_start_gate(new_signal_rows, selected_signals, paper_start_ts)
    orders, cash, signal_entry_events = create_orders_for_signals(
        data,
        positions,
        orders,
        selected_signals,
        cash,
        now_ts,
        entry_pause_reason=entry_pause_reason,
        paper_start_ts=paper_start_ts,
        defensive_probe=defensive_probe,
        paper_profile=paper_profile,
    )
    new_trade_rows.extend(signal_entry_events)

    mark_time = latest_mark_time(data, now_ts)
    if mark_time is not None:
        snapshot = snapshot_equity(data, positions, cash, now_ts, mark_time, equity_rows + new_equity_rows)
        if not new_equity_rows or int(new_equity_rows[-1]["timestamp"]) != int(snapshot["timestamp"]):
            new_equity_rows.append(snapshot)

    signal_rows = merge_unique(signal_rows, new_signal_rows, "signal_id")
    trades = merge_unique(trades, new_trade_rows, "event_id")
    equity_rows = merge_unique(equity_rows, new_equity_rows, "timestamp")
    write_csv_rows(state_dir / STATE_FILES["signals"][0], signal_rows, SIGNAL_FIELDS)
    write_csv_rows(state_dir / STATE_FILES["orders"][0], orders, ORDER_FIELDS)
    write_csv_rows(state_dir / STATE_FILES["trades"][0], trades, TRADE_FIELDS)
    save_positions(state_dir, positions, data, mark_time)
    write_csv_rows(state_dir / STATE_FILES["equity"][0], equity_rows, EQUITY_FIELDS)

    maybe_write_daily_report(state_dir, now_ts)
    dashboard = build_dashboard(
        state_dir,
        current_regime=latest_display_regime(data, now_ts, regime_timeframe, short_regime_index),
        current_candidates=selected_signals,
    )
    return {
        "positions": len(positions),
        "orders_created": len([row for row in orders if int(float(row.get("created_time") or 0)) == now_ts]),
        "signals_created": len(new_signal_rows),
        "trades_created": len(new_trade_rows),
        "dashboard": dashboard,
    }


def normalize_regime_timeframe(value: str) -> str:
    normalized = str(value or "1d").lower()
    if normalized not in {"1d", "4h"}:
        raise ValueError(f"unsupported regime timeframe: {value}")
    return normalized


def configure_live_window(raw_1h: Dict[str, List[dict]], now_ts: int) -> None:
    btc_rows = raw_1h.get("BTCUSDT", [])
    latest_open = max((int(row["time"]) for row in btc_rows if int(row["time"]) <= now_ts), default=now_ts)
    alpha.TEST_END_TS = max(alpha.TEST_START_TS + 3600, latest_open + 3600)


def load_latest_raw(symbols: Iterable[str], interval: str, start: str, use_cache: bool, now_ts: int) -> Dict[str, List[dict]]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, List[dict]] = {}
    for symbol in symbols:
        path = raw_dir / f"{symbol}_{interval}.json"
        cached = read_json_list(path)
        if cached and use_cache and is_current_enough(cached, interval, now_ts):
            out[symbol] = cached
            continue

        fetch_start = start
        if cached and cached[0]["time"] <= iso_to_ts(start):
            fetch_start = ts_to_iso(int(cached[-1]["time"]) + INTERVAL_SECONDS[interval])
        try:
            fetched = fetch_ohlcv(symbol, interval, fetch_start, ts_to_iso(now_ts + INTERVAL_SECONDS[interval]))
        except RuntimeError:
            if cached:
                out[symbol] = cached
                continue
            raise
        merged = merge_candles(cached, fetched)
        path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        out[symbol] = merged
    return out


def is_current_enough(candles: List[dict], interval: str, now_ts: int) -> bool:
    if not candles:
        return False
    latest_open = int(candles[-1]["time"])
    return latest_open + INTERVAL_SECONDS[interval] > now_ts


def applied_leverage_from_raw(raw_leverage: Optional[float]) -> int:
    if raw_leverage is None or raw_leverage <= 1:
        return 1
    if raw_leverage <= 2:
        return 2
    if raw_leverage <= 3:
        return 3
    return 4


def raw_position_leverage(position: rb.RobustPosition, equity: float) -> float:
    if equity <= 0:
        return 0.0
    return position.initial_units * position.entry_price / equity


def liquidation_buffer_is_safe(entry_price: float, stop_price: float, applied_leverage: int) -> bool:
    if applied_leverage <= 1:
        return True
    safe_leverage = rb.max_safe_liquidation_leverage(entry_price, stop_price)
    if safe_leverage is None:
        return False
    return applied_leverage <= safe_leverage + 1e-12


def merge_candles(*groups: List[dict]) -> List[dict]:
    by_time = {}
    for group in groups:
        for row in group:
            by_time[int(row["time"])] = row
    return [by_time[key] for key in sorted(by_time)]


def generate_new_signals(
    data: alpha.AlphaData,
    existing_rows: List[dict],
    now_ts: int,
    defensive_probe: bool = False,
    probe_health_gate: Optional[dict] = None,
    regime_timeframe: str = "1d",
    short_regime_index: Optional[dict] = None,
    short_health_gate: Optional[dict] = None,
) -> Tuple[List[dict], List[dict]]:
    signal_times = scan_signal_times(data, now_ts)
    if not signal_times:
        return [], []
    last_existing = max((int(float(row["signal_time"])) for row in existing_rows if row.get("signal_time")), default=None)
    if last_existing is None:
        signal_times = [signal_times[-1]]
    else:
        newest_existing_batch = [
            row
            for row in existing_rows
            if int(float(row.get("signal_time") or 0)) == last_existing
        ]
        newest_symbols = {row.get("symbol") for row in newest_existing_batch}
        signal_times = [signal_time for signal_time in signal_times if signal_time > last_existing]
        expected_symbols = set(TRADING_UNIVERSE)
        if last_existing in scan_signal_times(data, now_ts) and len(newest_symbols & expected_symbols) < len(expected_symbols):
            signal_times.insert(0, last_existing)

    new_rows: List[dict] = []
    selected: List[dict] = []

    for signal_time in signal_times:
        rows, selected_rows = build_scan_signal_batch(
            data,
            signal_time,
            defensive_probe=defensive_probe,
            probe_health_gate=probe_health_gate,
            regime_timeframe=regime_timeframe,
            short_regime_index=short_regime_index,
            short_health_gate=short_health_gate,
        )
        new_rows.extend(rows)
        selected.extend(selected_rows)
    return new_rows, selected


def scan_signal_times(data: alpha.AlphaData, now_ts: int) -> List[int]:
    out = []
    for row in data.rows_4h.get("BTCUSDT", []):
        close_time = int(row["time"]) + 4 * 3600
        if close_time < alpha.TEST_START_TS or close_time > now_ts:
            continue
        out.append(close_time)
    return sorted(set(out))


def build_scan_signal_batch(
    data: alpha.AlphaData,
    signal_time: int,
    defensive_probe: bool = False,
    probe_health_gate: Optional[dict] = None,
    regime_timeframe: str = "1d",
    short_regime_index: Optional[dict] = None,
    short_health_gate: Optional[dict] = None,
) -> Tuple[List[dict], List[dict]]:
    open_time = signal_time - 4 * 3600
    scan_symbols = tuple(symbol for symbol in TRADING_UNIVERSE if symbol != "DOGEUSDT")
    rows_by_symbol = {symbol: data.by_time_4h.get(symbol, {}).get(open_time) for symbol in scan_symbols}
    btc = data.by_time_4h.get("BTCUSDT", {}).get(open_time)
    regime, size_multiplier, block_reason = scan_regime_gate(
        data,
        signal_time,
        scan_symbols,
        regime_timeframe=regime_timeframe,
        short_regime_index=short_regime_index,
        short_health_gate=short_health_gate,
    )
    rank_lookup, ranked_count = scan_rank_lookup(rows_by_symbol)
    top_n = max(1, math.ceil(len(scan_symbols) * TOP_SCORE_PCT))
    diagnostics = []
    for symbol in scan_symbols:
        diagnostics.append(
            diagnose_scan_signal(
                symbol,
                rows_by_symbol.get(symbol),
                btc,
                rank_lookup.get(symbol),
                ranked_count or len(scan_symbols),
                regime,
                size_multiplier,
                block_reason,
                signal_time,
            )
        )

    score_candidates = [row for row in diagnostics if not row.get("_quality_reason")]
    score_candidates.sort(key=lambda item: (float(item.get("alpha_score") or 0.0), -int(item.get("rank") or 999)), reverse=True)
    top_keys = {signal_key(row) for row in score_candidates[:top_n]}

    probe_health_gate = probe_health_gate or defensive_probe_rules.health_gate_from_state({})
    probe_decisions = defensive_probe_decisions(diagnostics, btc, signal_time, probe_health_gate) if defensive_probe else {}

    output_rows = []
    selected = []
    for row in sorted(diagnostics, key=lambda item: (not bool(item.get("_top_sort")), -float(item.get("alpha_score") or 0.0), int(item.get("rank") or 999), item["symbol"])):
        quality_reason = row.pop("_quality_reason", "")
        row.pop("_top_sort", None)
        top_20_passed = signal_key(row) in top_keys and not quality_reason
        entry_block_reason = ""
        rejection_reason = quality_reason
        if normalize_regime_timeframe(regime_timeframe) == "4h" and str(block_reason).startswith("health_"):
            quality_reason = ""
            top_20_passed = False
            rejection_reason = block_reason
            entry_block_reason = block_reason
        if not rejection_reason and not top_20_passed:
            rejection_reason = "alpha_score_not_top_20pct"
        if not rejection_reason:
            entry_block_reason = regime_rejection_reason(block_reason)
            rejection_reason = entry_block_reason
        original_can_enter = not rejection_reason
        if normalize_regime_timeframe(regime_timeframe) == "4h":
            row["size_multiplier"] = size_multiplier
        probe_decision = probe_decisions.get(signal_key(row))
        if probe_decision:
            row.update(defensive_probe_log_fields(row, signal_time, original_can_enter, probe_decision))
            if probe_decision["probe_can_enter"]:
                rejection_reason = ""
                entry_block_reason = ""
                row["probe_can_enter"] = True
                row["size_multiplier"] = defensive_probe_rules.PROBE_SIZE_MULTIPLIER
                row["stop_atr_multiple"] = defensive_probe_rules.PROBE_STOP_ATR_MULTIPLE
        is_selected = not rejection_reason
        row.update(
            {
                "selected": is_selected,
                "rejection_reason": rejection_reason,
                "scan_status": "scanned",
                "top_20_passed": top_20_passed,
                "entry_block_reason": entry_block_reason,
                "top_score_pct": TOP_SCORE_PCT,
                "top_rank_cutoff": top_n,
            }
        )
        output_rows.append(row)
        if is_selected:
            selected.append(
                {
                    **row,
                    "symbol": row["symbol"],
                    "fill_time": row["fill_time"],
                }
            )
    return output_rows, selected


def scan_regime_gate(
    data: alpha.AlphaData,
    signal_time: int,
    scan_symbols: Iterable[str],
    regime_timeframe: str = "1d",
    short_regime_index: Optional[dict] = None,
    short_health_gate: Optional[dict] = None,
) -> Tuple[dict, float, str]:
    daily_regime = data.regime_by_date.get(alpha.date_from_ts(signal_time), {})
    if normalize_regime_timeframe(regime_timeframe) == "1d":
        _allowed_symbols, size_multiplier, block_reason = alpha.allowed_by_regime(list(scan_symbols), daily_regime)
        return daily_regime, size_multiplier, block_reason

    short_row = None
    if short_regime_index:
        short_row = (short_regime_index.get("by_close_time") or {}).get(signal_time)
    _allowed_symbols, size_multiplier, block_reason, short_regime = short_regime_4h.gate_for_signal(
        scan_symbols,
        short_row,
        config=short_regime_4h.PAPER_4H_CONFIG,
        daily_regime=daily_regime,
        health_gate=short_health_gate,
    )
    return short_regime, size_multiplier, block_reason


def scan_rank_lookup(rows_by_symbol: Dict[str, Optional[dict]]) -> Tuple[Dict[str, int], int]:
    rank_values = {
        symbol: 0.5 * (row.get("ret_7d") or -999) + 0.5 * (row.get("ret_14d") or -999)
        for symbol, row in rows_by_symbol.items()
        if row and row.get("ret_7d") is not None and row.get("ret_14d") is not None
    }
    ranked = sorted(rank_values, key=rank_values.get, reverse=True)
    return {symbol: rank + 1 for rank, symbol in enumerate(ranked)}, len(ranked)


def diagnose_scan_signal(
    symbol: str,
    row: Optional[dict],
    btc: Optional[dict],
    rank: Optional[int],
    universe_size: int,
    regime: dict,
    size_multiplier: float,
    block_reason: str,
    signal_time: int,
) -> dict:
    base = base_scan_row(symbol, row, rank, universe_size, regime, block_reason, signal_time)
    if not row or not btc or rank is None:
        return {**base, "_quality_reason": "data_missing", "_top_sort": False}
    if None in {row.get("ema20"), row.get("ema50"), row.get("atr14"), row.get("volume20"), btc.get("ret_7d"), btc.get("ret_14d")}:
        return {**base, "_quality_reason": "data_missing", "_top_sort": False}

    close = row["close"]
    atr = row["atr14"]
    trend_ok = close > row["ema50"] and row["ema20"] > row["ema50"]
    overextended = close > row["ema20"] + alpha.OVEREXTENSION_ATR_MULTIPLE * atr
    pullback = alpha.recent_pullback(row)
    recovered = close > row["ema20"]
    if not trend_ok or overextended or pullback <= 0 or not recovered:
        return {**base, "_quality_reason": "alpha_score_below_min", "_top_sort": False}

    ret_7d = row["ret_7d"]
    ret_14d = row["ret_14d"]
    btc_excess_7d = ret_7d - btc["ret_7d"] if ret_7d is not None else None
    btc_excess_14d = ret_14d - btc["ret_14d"] if ret_14d is not None else None
    trend_score = 2.0
    relative_strength_score = 0.0
    if ret_7d and ret_7d > 0:
        relative_strength_score += 1.0
    if ret_14d and ret_14d > 0:
        relative_strength_score += 1.0
    if btc_excess_7d and btc_excess_7d > 0:
        relative_strength_score += 1.0
    if rank <= max(1, math.ceil(universe_size * 0.30)):
        relative_strength_score += 1.0
    volume_score = 1.0 if row["volume"] > row["volume20"] * 1.2 else 0.0
    atr_pct = atr / close if close else 999
    risk_distance_score = 1.5 if atr_pct <= 0.035 else 1.0 if atr_pct <= 0.06 else 0.5
    alpha_score = trend_score + relative_strength_score + pullback + volume_score + risk_distance_score
    quality_reason = "" if alpha_score >= alpha.MIN_ALPHA_SCORE else "alpha_score_below_min"
    return {
        **base,
        "trend_score": trend_score,
        "relative_strength_score": relative_strength_score,
        "pullback_score": pullback,
        "volume_score": volume_score,
        "risk_distance_score": risk_distance_score,
        "alpha_score": alpha_score,
        "ret_7d_pct": ret_7d * 100 if ret_7d is not None else "",
        "ret_14d_pct": ret_14d * 100 if ret_14d is not None else "",
        "btc_excess_7d_pct": btc_excess_7d * 100 if btc_excess_7d is not None else "",
        "btc_excess_14d_pct": btc_excess_14d * 100 if btc_excess_14d is not None else "",
        "_quality_reason": quality_reason,
        "_top_sort": not quality_reason,
    }


def base_scan_row(symbol: str, row: Optional[dict], rank: Optional[int], universe_size: int, regime: dict, block_reason: str, signal_time: int) -> dict:
    signal = {
        "symbol": symbol,
        "signal_time": signal_time,
        "signal_date": format_dt(signal_time),
    }
    return {
        "signal_id": paper_signal_id(signal),
        "signal_time": signal_time,
        "signal_date": format_dt(signal_time),
        "fill_time": signal_time,
        "fill_date": format_dt(signal_time),
        "symbol": symbol,
        "alpha_score": "",
        "rank": rank or "",
        "universe_size": universe_size,
        "trade_regime": regime.get("trade_regime", ""),
        "trade_action_bias": regime.get("trade_action_bias", ""),
        "regime_reason": block_reason,
        "close": row.get("close", "") if row else "",
        "ema20": row.get("ema20", "") if row else "",
        "ema50": row.get("ema50", "") if row else "",
        "atr14": row.get("atr14", "") if row else "",
        "ret_7d_pct": (row.get("ret_7d") * 100 if row and row.get("ret_7d") is not None else ""),
        "ret_14d_pct": (row.get("ret_14d") * 100 if row and row.get("ret_14d") is not None else ""),
        "btc_excess_7d_pct": "",
        "btc_excess_14d_pct": "",
    }


def regime_rejection_reason(block_reason: str) -> str:
    if block_reason in {"uptrend", "large_cap_lead", "eth_strength", "short_4h_uptrend", "short_4h_recovery", "hybrid_1d_defensive_4h_recovery"}:
        return ""
    if block_reason == "defensive_reduce_risk":
        return "defensive_no_entry"
    if block_reason in {"no_new_entry", "wait", "shock", "observe", "neutral"}:
        return "regime_no_entry"
    if block_reason.startswith("short_4h_") or block_reason.startswith("health_") or block_reason in {"daily_risk_off", "health_blocked"}:
        return block_reason
    return ""


def defensive_probe_decisions(diagnostics: List[dict], btc: Optional[dict], signal_time: int, probe_health_gate: dict) -> Dict[Tuple[str, int], dict]:
    decisions: Dict[Tuple[str, int], dict] = {}
    defensive_rows = [
        row
        for row in diagnostics
        if defensive_probe_rules.is_defensive_state(row.get("trade_regime", ""), row.get("trade_action_bias", ""), row.get("regime_reason", ""))
    ]
    sorted_rows = sorted(
        defensive_rows,
        key=lambda item: (float(item.get("alpha_score") or 0.0), -int(item.get("rank") or 999), item.get("symbol", "")),
        reverse=True,
    )
    selected_key = None
    for row in sorted_rows:
        key = signal_key(row)
        decision = defensive_probe_rules.evaluate_candidate(
            row,
            row.get("trade_regime", ""),
            row.get("trade_action_bias", ""),
            row.get("regime_reason", ""),
            btc,
            probe_health_gate,
            max_slot_available=selected_key is None,
        )
        if decision["probe_can_enter"]:
            selected_key = key
        decisions[key] = decision
    return decisions


def defensive_probe_log_fields(row: dict, signal_time: int, original_can_enter: bool, decision: dict) -> dict:
    log_row = defensive_probe_rules.log_row(
        signal_time,
        row.get("symbol", ""),
        row.get("trade_regime", ""),
        row.get("trade_action_bias", ""),
        original_can_enter,
        decision,
    )
    return {**log_row, "_defensive_probe_log": True}


def load_health_state_dict(state_dir: Path) -> dict:
    path = state_dir / HEALTH_STATE_NAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def health_entry_pause_reason(state_dir: Path) -> str:
    state = load_health_state_dict(state_dir)
    locked = state.get("status") == "paused" or state.get("new_entry_allowed") is False or state.get("can_enter") is False
    if not locked:
        return ""
    return str(state.get("pause_reason") or state.get("final_block_reason") or "health_paused")


def load_paper_profile_state(state_dir: Path) -> dict:
    path = state_dir / PAPER_PROFILE_STATE_NAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def ensure_paper_profile_state(state_dir: Path, profile: PaperProfile, now_ts: int) -> None:
    if not profile.futures_shadow:
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / PAPER_PROFILE_STATE_NAME
    existing = load_paper_profile_state(state_dir)
    existing_profile = existing.get("paper_profile")
    if existing_profile and existing_profile != profile.profile_id:
        raise ValueError(f"state-dir is locked to paper profile {existing_profile}")

    state = {
        **profile.state_row(),
        "created_timestamp": existing.get("created_timestamp") or now_ts,
        "created_time": existing.get("created_time") or format_dt(now_ts),
        "updated_timestamp": now_ts,
        "updated_time": format_dt(now_ts),
        "risk_policy": {
            "max_exchange_leverage": 3,
            "max_effective_exposure": 1.0,
            "futures_shadow_only": True,
            "disabled": [
                "5x",
                "liquidation_touch",
                "2x_size_75pct_or_higher",
                "3x_size_50pct_or_higher",
                "pure_2x_plus",
            ],
        },
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def defensive_probe_entry_pause_is_regime_only(reason: str) -> bool:
    return str(reason or "").lower() in {
        "defensive_no_entry",
        "regime_defensive",
        "regime_reduce_risk",
        "reduce_risk",
    }


def ensure_operating_state(state_dir: Path, now_ts: int) -> dict:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / HEALTH_STATE_NAME
    state = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        except json.JSONDecodeError:
            state = {}

    existing_name = state.get("strategy_lock_name") or state.get("strategy_name")
    if existing_name and existing_name != STRATEGY_LOCK_NAME:
        state["oos_reset_required"] = True
        state["oos_reset_reason"] = f"strategy changed from {existing_name} to {STRATEGY_LOCK_NAME}"
    state["strategy_locked"] = True
    state["strategy_lock_name"] = STRATEGY_LOCK_NAME
    state["strategy_name"] = STRATEGY_LOCK_NAME
    state["strategy_lock_version"] = STRATEGY_LOCK_VERSION
    state["strategy_change_requires_oos_reset"] = True
    if not state.get("strategy_lock_timestamp"):
        state["strategy_lock_timestamp"] = now_ts
    if not state.get("strategy_lock_time"):
        state["strategy_lock_time"] = format_dt(state["strategy_lock_timestamp"])
    if not state.get("paper_start_timestamp"):
        state["paper_start_timestamp"] = now_ts
    if not state.get("paper_start_time"):
        state["paper_start_time"] = format_dt(state["paper_start_timestamp"])
    state["oos_start_timestamp"] = state.get("paper_start_timestamp")
    state["oos_start_time"] = state.get("paper_start_time")
    state["oos_classification_rule"] = "Only signals, orders, trades, and health snapshots at or after paper_start_time are OOS."
    state.setdefault("oos_reset_required", False)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return state


def apply_paper_start_gate(signal_rows: List[dict], selected_signals: List[dict], paper_start_ts: int) -> Tuple[List[dict], List[dict]]:
    if paper_start_ts <= 0:
        return signal_rows, selected_signals
    updated = []
    for row in signal_rows:
        row = dict(row)
        signal_time = int(float(row.get("signal_time") or row.get("fill_time") or 0))
        if signal_time < paper_start_ts and str(row.get("selected", "")).lower() == "true":
            row["selected"] = False
            row["scan_status"] = "missed_signal"
            row["rejection_reason"] = "missed_signal_before_paper_start"
            row["entry_block_reason"] = "paper_start_time"
        updated.append(row)
    selected = [
        signal
        for signal in selected_signals
        if int(float(signal.get("signal_time") or signal.get("fill_time") or 0)) >= paper_start_ts
    ]
    return updated, selected


def selected_signal_is_order_candidate(signal: dict, paper_start_ts: int = 0) -> bool:
    if str(signal.get("symbol", "")).upper() == "DOGEUSDT":
        return False
    if str(signal.get("selected", "true")).lower() == "false":
        return False
    if signal.get("rejection_reason") or signal.get("entry_block_reason"):
        return False
    if is_blocked_trade_state(signal.get("trade_regime", ""), signal.get("trade_action_bias", "")) and not defensive_probe_rules.truthy(signal.get("probe_can_enter")):
        return False
    signal_time = int(float(signal.get("signal_time") or signal.get("fill_time") or 0))
    return paper_start_ts <= 0 or signal_time >= paper_start_ts


def is_blocked_trade_state(regime: str, action_bias: str) -> bool:
    regime_value = str(regime or "").lower()
    action_value = str(action_bias or "").lower()
    return regime_value in {"shock", "risk_off"} or action_value in {"reduce_risk", "shock", "no_new_entry", "wait", "block_entry"}


def order_is_defensive_probe(order: dict) -> bool:
    if defensive_probe_rules.truthy(order.get("probe_can_enter")):
        return True
    return defensive_probe_rules.is_defensive_state(
        order.get("trade_regime", ""),
        order.get("trade_action_bias", ""),
        order.get("reason", ""),
    )


def select_v1_2_signal_batch(signals: List[dict]) -> Tuple[List[dict], List[dict]]:
    batch = sorted((dict(signal) for signal in signals), key=lambda item: item["alpha_score"], reverse=True)
    eligible = [
        signal
        for signal in batch
        if signal.get("regime_reason") != "defensive_reduce_risk" and signal["symbol"] != "DOGE"
    ]
    top_n = max(1, math.ceil(len(eligible) * TOP_SCORE_PCT)) if eligible else 0
    selected_keys = {signal_key(signal) for signal in eligible[:top_n]}
    output_rows = []
    selected = []

    for signal in batch:
        rejection_reason = ""
        if signal["symbol"] == "DOGE":
            rejection_reason = "doge_excluded"
        elif signal.get("regime_reason") == "defensive_reduce_risk":
            rejection_reason = "defensive_no_entry"
        elif signal_key(signal) not in selected_keys:
            rejection_reason = "alpha_score_not_top_20pct"
        is_selected = not rejection_reason
        signal_id = paper_signal_id(signal)
        row = {
            "signal_id": signal_id,
            "signal_time": signal["signal_time"],
            "signal_date": signal["signal_date"],
            "fill_time": signal["signal_time"],
            "fill_date": signal["signal_date"],
            "symbol": f"{signal['symbol']}USDT",
            "alpha_score": signal["alpha_score"],
            "rank": signal["rank"],
            "universe_size": signal["universe_size"],
            "selected": is_selected,
            "rejection_reason": rejection_reason,
            "top_score_pct": TOP_SCORE_PCT,
            "top_rank_cutoff": top_n,
            "trade_regime": signal.get("trade_regime", ""),
            "trade_action_bias": signal.get("trade_action_bias", ""),
            "regime_reason": signal.get("regime_reason", ""),
            "close": signal.get("close", ""),
            "ema20": signal.get("ema20", ""),
            "ema50": signal.get("ema50", ""),
            "atr14": signal.get("atr14", ""),
            "ret_7d_pct": signal.get("ret_7d_pct", ""),
            "ret_14d_pct": signal.get("ret_14d_pct", ""),
            "btc_excess_7d_pct": signal.get("btc_excess_7d_pct", ""),
            "btc_excess_14d_pct": signal.get("btc_excess_14d_pct", ""),
        }
        output_rows.append(row)
        if is_selected:
            selected_signal = {**signal, "signal_id": signal_id, "symbol": f"{signal['symbol']}USDT", "fill_time": signal["signal_time"]}
            selected.append(selected_signal)
    return output_rows, selected


def create_orders_for_signals(
    data: alpha.AlphaData,
    positions: Dict[str, rb.RobustPosition],
    orders: List[dict],
    signals: List[dict],
    cash: float,
    now_ts: int,
    entry_pause_reason: str = "",
    paper_start_ts: int = 0,
    defensive_probe: bool = False,
    paper_profile: PaperProfile = DEFAULT_PAPER_PROFILE,
) -> Tuple[List[dict], float, List[dict]]:
    existing_order_ids = {row["order_id"] for row in orders}
    events: List[dict] = []
    if entry_pause_reason and not (defensive_probe and defensive_probe_entry_pause_is_regime_only(entry_pause_reason)):
        return orders, cash, events
    for signal in sorted(signals, key=lambda item: item["alpha_score"], reverse=True):
        if not selected_signal_is_order_candidate(signal, paper_start_ts):
            continue
        order_id = paper_order_id(signal)
        if order_id in existing_order_ids:
            continue
        order = make_order(signal, now_ts, paper_profile=paper_profile)
        symbol = signal["symbol"]
        if symbol in positions:
            order["status"] = "rejected"
            order["reason"] = "already_open"
            orders.append(order)
            continue
        orders.append(order)
        existing_order_ids.add(order_id)
    if not orders:
        return orders, cash, events
    return fill_pending_orders(
        data,
        positions,
        orders,
        cash,
        now_ts,
        events,
        paper_start_ts=paper_start_ts,
        entry_pause_reason=entry_pause_reason,
        defensive_probe=defensive_probe,
        paper_profile=paper_profile,
    )


def fill_pending_orders(
    data: alpha.AlphaData,
    positions: Dict[str, rb.RobustPosition],
    orders: List[dict],
    cash: float,
    now_ts: int,
    events: Optional[List[dict]] = None,
    entry_pause_reason: str = "",
    paper_start_ts: int = 0,
    defensive_probe: bool = False,
    paper_profile: PaperProfile = DEFAULT_PAPER_PROFILE,
) -> Tuple[List[dict], float, List[dict]]:
    events = events or []
    config = paper_config_for_profile(paper_profile)
    latest_open = latest_known_1h_open(data, now_ts)
    if latest_open is None:
        return orders, cash, events

    for order in sorted(orders, key=lambda item: (int(float(item.get("fill_time") or 0)), -float(item.get("alpha_score") or 0))):
        if order.get("status") != "pending":
            continue
        if entry_pause_reason and not (
            defensive_probe
            and defensive_probe_entry_pause_is_regime_only(entry_pause_reason)
            and order_is_defensive_probe(order)
        ):
            update_order(order, "rejected", now_ts, reason="health_paused")
            continue
        fill_time = int(float(order["fill_time"]))
        signal_time = int(float(order.get("signal_time") or fill_time))
        if paper_start_ts > 0 and signal_time < paper_start_ts:
            update_order(order, "rejected", now_ts, reason="missed_signal_before_paper_start")
            continue
        if fill_time > latest_open:
            continue
        symbol = order["symbol"]
        if symbol in positions:
            update_order(order, "rejected", now_ts, reason="already_open")
            continue
        if len(positions) >= config.variant.max_positions:
            update_order(order, "rejected", now_ts, reason="max_positions")
            continue
        row = data.by_time_1h.get(symbol, {}).get(fill_time)
        if not row or row.get("atr14") is None:
            update_order(order, "pending", now_ts, reason="missing_1h_execution_data")
            continue

        index_1h = data.index_1h.get(fill_time, len(data.times_1h) - 1)
        equity = rb.portfolio_equity(cash, positions, data, fill_time)
        if order_is_defensive_probe(order):
            order["size_multiplier"] = order.get("size_multiplier") or defensive_probe_rules.PROBE_SIZE_MULTIPLIER
            order["stop_atr_multiple"] = order.get("stop_atr_multiple") or defensive_probe_rules.PROBE_STOP_ATR_MULTIPLE
        apply_paper_profile_to_order(order, paper_profile)
        position, fee, reason = rb.create_position(data, config, order, row, fill_time, index_1h, equity, positions)
        if not position:
            update_order(order, "rejected", now_ts, reason=reason or "position_rejected")
            continue

        raw_leverage = raw_position_leverage(position, equity)
        applied_leverage = applied_leverage_for_profile(paper_profile, raw_leverage)
        liquidation_price = rb.liquidation_price_for(position.entry_price, applied_leverage)
        # Keep PnL sizing on the raw risk-sized notional; only the paper order leverage setting is integer.
        if config.variant.require_liquidation_buffer and not liquidation_buffer_is_safe(
            position.entry_price,
            position.stop_price,
            applied_leverage,
        ):
            update_order(
                order,
                "rejected",
                now_ts,
                reason="applied_leverage_liquidation_buffer",
                raw_leverage=raw_leverage,
                applied_leverage=applied_leverage,
            )
            continue
        if paper_profile.futures_shadow and not liquidation_buffer_is_safe(
            position.entry_price,
            position.stop_price,
            applied_leverage,
        ):
            update_order(
                order,
                "rejected",
                now_ts,
                reason="futures_shadow_liquidation_buffer",
                raw_leverage=raw_leverage,
                applied_leverage=applied_leverage,
            )
            continue

        position.liquidation_leverage_used = applied_leverage
        position.liquidation_price_est = liquidation_price
        attach_position_state(position, raw_leverage=raw_leverage, applied_leverage=applied_leverage)
        position_id = paper_position_id(order)
        attach_position_state(position, position_id=position_id, order_id=order["order_id"])
        cash -= fee
        positions[symbol] = position
        update_order(
            order,
            "filled",
            now_ts,
            reason="",
            entry_price=position.entry_price,
            units=position.units,
            notional=position.units * position.entry_price,
            fee=fee,
            raw_leverage=raw_leverage,
            applied_leverage=applied_leverage,
            position_id=position_id,
        )
        events.append(entry_event(position, order, fill_time, fee, cash, data))
    return orders, cash, events


def make_order(signal: dict, now_ts: int, paper_profile: PaperProfile = DEFAULT_PAPER_PROFILE) -> dict:
    order = {
        "order_id": paper_order_id(signal),
        "created_time": now_ts,
        "created_date": format_dt(now_ts),
        "signal_id": signal["signal_id"],
        "signal_time": signal["signal_time"],
        "signal_date": signal["signal_date"],
        "fill_time": signal["fill_time"],
        "fill_date": format_dt(signal["fill_time"]),
        "symbol": signal["symbol"],
        "side": "long",
        "type": "paper_market_next_1h_open",
        "status": "pending",
        "reason": "",
        "alpha_score": signal["alpha_score"],
        "trade_regime": signal.get("trade_regime", ""),
        "trade_action_bias": signal.get("trade_action_bias", ""),
        "entry_price": "",
        "units": "",
        "notional": "",
        "fee": "",
        "raw_leverage": "",
        "applied_leverage": "",
        "position_id": "",
        "updated_time": now_ts,
        "updated_date": format_dt(now_ts),
        "probe_can_enter": signal.get("probe_can_enter", False),
        "size_multiplier": signal.get("size_multiplier", ""),
        "stop_atr_multiple": signal.get("stop_atr_multiple", ""),
    }
    apply_paper_profile_to_order(order, paper_profile)
    return order


def apply_paper_profile_to_order(order: dict, profile: PaperProfile) -> None:
    if not profile.futures_shadow:
        return
    order["paper_profile"] = profile.profile_id
    order["exchange_leverage"] = int(profile.exchange_leverage)
    order["size_multiplier"] = profile.size_multiplier
    order["effective_exposure"] = profile.effective_exposure


def update_order(order: dict, status: str, now_ts: int, reason: str = "", **values) -> None:
    order["status"] = status
    order["reason"] = reason
    order["updated_time"] = now_ts
    order["updated_date"] = format_dt(now_ts)
    for key, value in values.items():
        order[key] = value


def manage_positions_for_bar(
    data: alpha.AlphaData,
    positions: Dict[str, rb.RobustPosition],
    open_time: int,
    close_time: int,
    cash: float,
) -> Tuple[float, List[dict]]:
    events = []
    for symbol in list(positions):
        position = positions[symbol]
        row = data.by_time_1h.get(symbol, {}).get(open_time)
        if not row:
            continue
        cash, position_events, closed = manage_position_once(data, position, row, close_time, cash)
        events.extend(position_events)
        if closed:
            positions.pop(symbol, None)
        else:
            set_position_attr(position, "last_update_time", close_time)
    return cash, events


def manage_position_once(
    data: alpha.AlphaData,
    position: rb.RobustPosition,
    row: dict,
    close_time: int,
    cash: float,
) -> Tuple[float, List[dict], bool]:
    events = []
    if position.liquidation_price_est and row["open"] <= position.liquidation_price_est:
        cash, event = close_position(data, position, position.liquidation_price_est, close_time, "liquidation_gap", cash)
        return cash, [event], True
    if row["low"] <= position.stop_price:
        cash, event = close_position(data, position, position.stop_price, close_time, "stop", cash)
        return cash, [event], True

    target_price = position.entry_price + position.risk_distance
    if not position.partial_taken and row["high"] >= target_price:
        close_units = position.units * 0.5
        exit_price = target_price * (1 - SLIPPAGE_RATE)
        fee = close_units * exit_price * TAKER_FEE_RATE
        pnl = close_units * (exit_price - position.entry_price) - fee
        cash += pnl
        position.realized_pnl += pnl
        position.units -= close_units
        position.risk_amount *= 0.5
        position.partial_taken = True
        position.partial_time = close_time
        position.partial_price = exit_price
        events.append(partial_exit_event(position, close_time, exit_price, close_units, fee, pnl, cash))

    row_4h = data.by_close_4h.get(position.symbol, {}).get(close_time)
    if row_4h:
        if row_4h.get("ema50") is not None and row_4h["close"] < row_4h["ema50"]:
            cash, event = close_position(data, position, row["close"] * (1 - SLIPPAGE_RATE), close_time, "ema50_exit", cash)
            return cash, events + [event], True
        if position.partial_taken and row_4h.get("ema20") is not None and row_4h["close"] < row_4h["ema20"]:
            cash, event = close_position(data, position, row["close"] * (1 - SLIPPAGE_RATE), close_time, "ema20_trailing_exit", cash)
            return cash, events + [event], True

    if close_time - position.entry_time >= alpha.MAX_HOLD_HOURS * 3600:
        cash, event = close_position(data, position, row["close"] * (1 - SLIPPAGE_RATE), close_time, "max_hold", cash)
        return cash, events + [event], True
    return cash, events, False


def close_shock_positions(
    data: alpha.AlphaData,
    positions: Dict[str, rb.RobustPosition],
    open_time: int,
    close_time: int,
    cash: float,
) -> Tuple[float, List[dict]]:
    events = []
    if not alpha.is_shock_date(data, alpha.date_from_ts(close_time)):
        return cash, events
    for symbol in list(positions):
        row = data.by_time_1h.get(symbol, {}).get(open_time)
        if not row:
            continue
        cash, event = close_position(data, positions.pop(symbol), row["close"] * (1 - SLIPPAGE_RATE), close_time, "shock_exit", cash)
        events.append(event)
    return cash, events


def close_position(
    data: alpha.AlphaData,
    position: rb.RobustPosition,
    exit_price: float,
    exit_time: int,
    reason: str,
    cash: float,
) -> Tuple[float, dict]:
    fee = position.units * exit_price * TAKER_FEE_RATE
    exit_pnl = position.units * (exit_price - position.entry_price) - fee
    cash += exit_pnl
    funding_pnl = float(get_position_attr(position, "funding_pnl", 0.0))
    total_pnl = position.realized_pnl + exit_pnl + funding_pnl
    hold_hours = (exit_time - position.entry_time) / 3600
    event = {
        "event_id": f"exit_{get_position_attr(position, 'position_id', '')}_{exit_time}",
        "event_type": "exit",
        "position_id": get_position_attr(position, "position_id", ""),
        "order_id": get_position_attr(position, "order_id", ""),
        "timestamp": exit_time,
        "date": format_dt(exit_time),
        "symbol": position.symbol,
        "side": "sell",
        "price": exit_price,
        "units": position.units,
        "notional": position.units * exit_price,
        "fee": fee,
        "raw_leverage": get_position_attr(position, "raw_leverage", raw_position_leverage(position, position.entry_equity)),
        "applied_leverage": get_position_attr(
            position,
            "applied_leverage",
            applied_leverage_from_raw(raw_position_leverage(position, position.entry_equity)),
        ),
        "funding_rate": "",
        "funding_pnl": funding_pnl,
        "pnl": exit_pnl,
        "cash_delta": exit_pnl,
        "equity_after": rb.portfolio_equity(cash, {}, data, exit_time) if data.times_1h else cash,
        "reason": reason,
        "alpha_score": position.signal_score,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "entry_price": position.entry_price,
        "stop_price": position.stop_price,
        "exit_price": exit_price,
        "position_total_pnl": total_pnl,
        "hold_hours": hold_hours,
    }
    return cash, event


def apply_funding_events(
    positions: Dict[str, rb.RobustPosition],
    funding_index: Dict[str, List[dict]],
    data: alpha.AlphaData,
    close_time: int,
    cash: float,
) -> Tuple[float, List[dict]]:
    events = []
    for position in positions.values():
        last_funding_time = int(get_position_attr(position, "last_funding_time", position.entry_time))
        for event in funding_index.get(position.symbol, []):
            funding_time = int(event["funding_time"])
            if funding_time <= last_funding_time:
                continue
            if funding_time < position.entry_time or funding_time >= close_time:
                continue
            mark_price = event["mark_price"] or mark_price_for(data, position.symbol, funding_time) or position.entry_price
            notional = position.units * mark_price
            rate = event["funding_rate"]
            pnl = -notional * rate
            cash += pnl
            current_funding = float(get_position_attr(position, "funding_pnl", 0.0)) + pnl
            set_position_attr(position, "funding_pnl", current_funding)
            set_position_attr(position, "last_funding_time", funding_time)
            events.append(funding_event(position, event, mark_price, notional, pnl, cash))
    return cash, events


def load_funding_index(symbols: Iterable[str], use_cache: bool, now_ts: int) -> Dict[str, List[dict]]:
    funding_info = funding.load_funding_info(use_cache)
    out = {}
    for symbol in symbols:
        interval_hours = funding_info.get(symbol, {}).get("fundingIntervalHours")
        out[symbol] = load_latest_funding_history(symbol, use_cache, interval_hours, now_ts)
    return out


def load_latest_funding_history(symbol: str, use_cache: bool, interval_hours: Optional[float], now_ts: int) -> List[dict]:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{symbol}_futures_funding_rate.json"
    cached = read_json_list(path)
    if cached and use_cache and int(cached[-1]["fundingTime"]) // 1000 >= now_ts - 12 * 3600:
        return normalize_latest_funding_rows(symbol, cached, interval_hours, now_ts)

    rows = list(cached)
    cursor_ms = funding.START_TS * 1000
    if rows:
        cursor_ms = int(rows[-1]["fundingTime"]) + 1
    end_ms = now_ts * 1000
    try:
        while cursor_ms < end_ms:
            batch = funding.request_json(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor_ms, "endTime": end_ms, "limit": 1000},
            )
            if not batch:
                break
            rows.extend(batch)
            next_cursor = int(batch[-1]["fundingTime"]) + 1
            if next_cursor <= cursor_ms:
                break
            cursor_ms = next_cursor
            if len(batch) < 1000:
                break
            time.sleep(0.08)
    except RuntimeError:
        rows = cached
    if rows:
        deduped = {int(row["fundingTime"]): row for row in rows}
        rows = [deduped[key] for key in sorted(deduped)]
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return normalize_latest_funding_rows(symbol, rows, interval_hours, now_ts)


def normalize_latest_funding_rows(symbol: str, rows: List[dict], interval_hours: Optional[float], now_ts: int) -> List[dict]:
    out = []
    sorted_rows = sorted(rows, key=lambda row: int(row["fundingTime"]))
    for index, row in enumerate(sorted_rows):
        funding_time = int(row["fundingTime"]) // 1000
        if funding_time < funding.START_TS or funding_time > now_ts:
            continue
        inferred_hours = interval_hours
        if inferred_hours is None and index > 0:
            inferred_hours = (int(row["fundingTime"]) - int(sorted_rows[index - 1]["fundingTime"])) / 3600000
        if inferred_hours is None:
            inferred_hours = 8.0
        out.append(
            {
                "symbol": symbol,
                "funding_time": funding_time,
                "funding_date": format_dt(funding_time),
                "funding_rate": float(row.get("fundingRate", 0.0)),
                "mark_price": float(row.get("markPrice") or 0.0),
                "funding_interval_hours": float(inferred_hours),
            }
        )
    return out


def snapshot_equity(
    data: alpha.AlphaData,
    positions: Dict[str, rb.RobustPosition],
    cash: float,
    timestamp: int,
    mark_time: int,
    existing_rows: Optional[List[dict]] = None,
) -> dict:
    equity = portfolio_equity_at(cash, positions, data, mark_time)
    open_unrealized = equity - cash
    open_notional = sum(position.units * mark_price_for(data, position.symbol, mark_time, position.entry_price) for position in positions.values())
    drawdown_pct = 0.0
    max_drawdown_pct = 0.0
    existing_rows = existing_rows or []
    if existing_rows:
        previous_equities = [float(row["equity"]) for row in existing_rows if row.get("equity")]
        peak = max(previous_equities + [equity])
        drawdown_pct = (equity / peak - 1) * 100 if peak else 0.0
        max_drawdown_pct = min([float(row.get("drawdown_pct") or 0.0) for row in existing_rows] + [drawdown_pct])
    regime = latest_regime(data, timestamp)
    liquidation_risks = sum(1 for position in positions.values() if liquidation_risk_now(position))
    status = strategy_status(regime, drawdown_pct, liquidation_risks)
    return {
        "timestamp": timestamp,
        "date": format_dt(timestamp),
        "equity": equity,
        "cash": cash,
        "open_unrealized": open_unrealized,
        "cumulative_pnl": equity - INITIAL_CASH,
        "drawdown_pct": drawdown_pct,
        "open_positions": len(positions),
        "open_notional": open_notional,
        "current_regime": regime.get("trade_regime", regime.get("regime", "")),
        "current_action_bias": regime.get("trade_action_bias", regime.get("action_bias", "")),
        "strategy_status": status,
        "max_drawdown_pct": max_drawdown_pct,
        "liquidation_risk_count": liquidation_risks,
    }


def strategy_status(regime: dict, drawdown_pct: float, liquidation_risks: int) -> str:
    action_bias = regime.get("trade_action_bias") or regime.get("action_bias")
    if liquidation_risks > 0 or drawdown_pct <= -15 + 1e-9 or action_bias in {"no_new_entry", "block_entry"}:
        return "paused"
    if drawdown_pct <= -10 + 1e-9 or action_bias in {"wait", "reduce_risk"}:
        return "warning"
    return "normal"


def build_dashboard(
    state_dir: Path,
    current_regime: Optional[dict] = None,
    current_candidates: Optional[List[dict]] = None,
) -> str:
    ensure_state_files(state_dir)
    positions = read_csv_rows(state_dir / STATE_FILES["positions"][0])
    equity_rows = read_csv_rows(state_dir / STATE_FILES["equity"][0])
    trade_rows = read_csv_rows(state_dir / STATE_FILES["trades"][0])
    signal_rows = read_csv_rows(state_dir / STATE_FILES["signals"][0])
    latest_equity = equity_rows[-1] if equity_rows else {}
    if current_regime is None:
        current_regime = {
            "trade_regime": latest_equity.get("current_regime", ""),
            "trade_action_bias": latest_equity.get("current_action_bias", ""),
        }
    if current_candidates is None:
        current_candidates = latest_selected_signal_rows(signal_rows)

    recent_20 = recent_closed_trades(trade_rows, 20)
    pf = profit_factor([float(row.get("position_total_pnl") or 0.0) for row in recent_20])
    win_rate = win_rate_pct([float(row.get("position_total_pnl") or 0.0) for row in recent_20])
    perf_30d = recent_equity_performance(equity_rows, 30)
    max_dd = min((float(row.get("drawdown_pct") or 0.0) for row in equity_rows), default=0.0)
    unrealized = sum(float(row.get("unrealized_pnl") or 0.0) for row in positions)
    cumulative = float(latest_equity.get("cumulative_pnl") or 0.0)
    status = latest_equity.get("strategy_status") or "normal"

    lines = [
        "# Alpha Engine v1.2 Paper Dashboard",
        "",
        *paper_profile_report_lines(state_dir),
        f"- current_regime: {current_regime.get('trade_regime') or current_regime.get('regime') or ''}",
        f"- current_action_bias: {current_regime.get('trade_action_bias') or current_regime.get('action_bias') or ''}",
        f"- strategy_status: {status}",
        f"- unrealized_pnl: {unrealized:.6f}",
        f"- cumulative_pnl: {cumulative:.6f}",
        f"- recent_30d_performance: {perf_30d:.2f}%",
        f"- recent_20_trade_pf: {format_optional(pf)}",
        f"- recent_20_trade_win_rate: {win_rate:.1f}%",
        f"- max_drawdown: {max_dd:.2f}%",
        "",
        "## Current Entry Candidates",
        candidate_table(current_candidates),
        "",
        "## Open Paper Positions",
        position_table(positions),
    ]
    return "\n".join(lines)


def paper_profile_report_lines(state_dir: Path) -> List[str]:
    profile = load_paper_profile_state(state_dir)
    if not profile:
        return []
    leverage = int(float(profile.get("exchange_leverage") or 1))
    size_multiplier = float(profile.get("size_multiplier") or 1.0)
    effective = float(profile.get("effective_exposure") or leverage * size_multiplier)
    return [
        f"- paper_profile: {profile.get('paper_profile', '')}",
        f"- paper_mode: {profile.get('mode', '')}",
        f"- exchange_leverage: {leverage}x",
        f"- size_multiplier: {size_multiplier:.2f}",
        f"- effective_exposure: {effective:.2f}x",
    ]


def maybe_write_daily_report(state_dir: Path, now_ts: int) -> None:
    today = datetime.fromtimestamp(now_ts, timezone.utc).strftime("%Y-%m-%d")
    marker = state_dir / f"paper_daily_report_{today}.md"
    if marker.exists():
        return
    report = daily_report_text(state_dir, now_ts)
    marker.write_text(report, encoding="utf-8")
    (state_dir / DAILY_REPORT_NAME).write_text(report, encoding="utf-8")


def write_daily_report(state_dir: Path, now_ts: Optional[int] = None) -> str:
    now_ts = int(now_ts or datetime.now(timezone.utc).timestamp())
    ensure_state_files(state_dir)
    report = daily_report_text(state_dir, now_ts)
    path = state_dir / DAILY_REPORT_NAME
    path.write_text(report, encoding="utf-8")
    return str(path)


def daily_report_text(state_dir: Path, now_ts: int) -> str:
    equity_rows = read_csv_rows(state_dir / STATE_FILES["equity"][0])
    trade_rows = read_csv_rows(state_dir / STATE_FILES["trades"][0])
    latest = equity_rows[-1] if equity_rows else {}
    today = datetime.fromtimestamp(now_ts, timezone.utc).strftime("%Y-%m-%d")
    closed_today = [
        row
        for row in trade_rows
        if row.get("event_type") == "exit" and row.get("date", "").startswith(today)
    ]
    lines = [
        f"# Alpha Engine v1.2 Paper Daily Report {today}",
        "",
        *paper_profile_report_lines(state_dir),
        f"- equity: {float(latest.get('equity') or INITIAL_CASH):.6f}",
        f"- cumulative_pnl: {float(latest.get('cumulative_pnl') or 0.0):.6f}",
        f"- open_positions: {latest.get('open_positions') or 0}",
        f"- strategy_status: {latest.get('strategy_status') or 'normal'}",
        f"- closed_trades_today: {len(closed_today)}",
        f"- closed_pnl_today: {sum(float(row.get('position_total_pnl') or 0.0) for row in closed_today):.6f}",
        "",
        build_dashboard(state_dir),
        "",
    ]
    return "\n".join(lines)


def save_positions(state_dir: Path, positions: Dict[str, rb.RobustPosition], data: alpha.AlphaData, mark_time: Optional[int]) -> None:
    rows = []
    for position in positions.values():
        last_price = mark_price_for(data, position.symbol, mark_time, position.entry_price) if mark_time is not None else position.entry_price
        unrealized = position.units * (last_price - position.entry_price)
        rows.append(position_to_row(position, last_price, unrealized))
    write_csv_rows(state_dir / STATE_FILES["positions"][0], rows, POSITION_FIELDS)


def load_positions(state_dir: Path) -> Dict[str, rb.RobustPosition]:
    rows = read_csv_rows(state_dir / STATE_FILES["positions"][0])
    positions = {}
    for row in rows:
        if row.get("status") and row["status"] != "open":
            continue
        position = rb.RobustPosition(
            symbol=row["symbol"],
            units=float(row["units"]),
            initial_units=float(row["initial_units"]),
            entry_price=float(row["entry_price"]),
            stop_price=float(row["stop_price"]),
            risk_distance=float(row["risk_distance"]),
            risk_amount=float(row["risk_amount"]),
            entry_time=int(float(row["opened_at"])),
            entry_index_1h=0,
            entry_equity=float(row["entry_equity"]),
            signal_time=int(float(row["signal_time"])),
            signal_score=float(row["alpha_score"]),
            regime=row.get("trade_regime", ""),
            action_bias=row.get("trade_action_bias", ""),
            liquidation_leverage_used=float(row["liquidation_leverage_used"]),
            liquidation_price_est=float(row["liquidation_price_est"]),
            symbol_leverage_cap=float(row["symbol_leverage_cap"]),
            realized_pnl=float(row.get("realized_pnl") or 0.0),
            partial_taken=str(row.get("partial_taken", "")).lower() == "true",
            partial_time=int(float(row["partial_time"])) if row.get("partial_time") else None,
            partial_price=float(row["partial_price"]) if row.get("partial_price") else None,
        )
        attach_position_state(
            position,
            position_id=row["position_id"],
            order_id=row["order_id"],
            raw_leverage=parse_float(row.get("raw_leverage"), raw_position_leverage(position, float(row["entry_equity"]))),
            applied_leverage=applied_leverage_from_raw(
                parse_float(
                    row.get("applied_leverage"),
                    applied_leverage_from_raw(raw_position_leverage(position, float(row["entry_equity"]))),
                )
            ),
            funding_pnl=float(row.get("funding_pnl") or 0.0),
            last_funding_time=int(float(row["last_funding_time"])) if row.get("last_funding_time") else int(float(row["opened_at"])),
            last_update_time=int(float(row["last_update_time"])) if row.get("last_update_time") else int(float(row["opened_at"])),
        )
        positions[position.symbol] = position
    return positions


def position_to_row(position: rb.RobustPosition, last_price: float, unrealized: float) -> dict:
    liquidation_buffer_pct = (
        (position.stop_price - position.liquidation_price_est) / position.entry_price * 100
        if position.entry_price
        else 0.0
    )
    return {
        "position_id": get_position_attr(position, "position_id", ""),
        "status": "open",
        "symbol": position.symbol,
        "side": "long",
        "opened_at": position.entry_time,
        "opened_at_date": format_dt(position.entry_time),
        "signal_time": position.signal_time,
        "signal_date": format_dt(position.signal_time),
        "order_id": get_position_attr(position, "order_id", ""),
        "entry_price": position.entry_price,
        "stop_price": position.stop_price,
        "risk_distance": position.risk_distance,
        "risk_amount": position.risk_amount,
        "units": position.units,
        "initial_units": position.initial_units,
        "entry_equity": position.entry_equity,
        "alpha_score": position.signal_score,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "liquidation_leverage_used": position.liquidation_leverage_used,
        "liquidation_price_est": position.liquidation_price_est,
        "symbol_leverage_cap": position.symbol_leverage_cap,
        "raw_leverage": get_position_attr(position, "raw_leverage", raw_position_leverage(position, position.entry_equity)),
        "applied_leverage": get_position_attr(
            position,
            "applied_leverage",
            applied_leverage_from_raw(raw_position_leverage(position, position.entry_equity)),
        ),
        "realized_pnl": position.realized_pnl,
        "funding_pnl": get_position_attr(position, "funding_pnl", 0.0),
        "partial_taken": position.partial_taken,
        "partial_time": position.partial_time or "",
        "partial_date": format_dt(position.partial_time) if position.partial_time else "",
        "partial_price": position.partial_price or "",
        "last_funding_time": get_position_attr(position, "last_funding_time", position.entry_time),
        "last_update_time": get_position_attr(position, "last_update_time", position.entry_time),
        "last_update_date": format_dt(get_position_attr(position, "last_update_time", position.entry_time)),
        "last_price": last_price,
        "unrealized_pnl": unrealized,
        "notional": position.units * last_price,
        "liquidation_buffer_pct": liquidation_buffer_pct,
        "liquidation_risk": liquidation_risk_now(position),
    }


def attach_position_state(position: rb.RobustPosition, **values) -> None:
    for key, value in values.items():
        set_position_attr(position, key, value)
    if get_position_attr(position, "funding_pnl", None) is None:
        set_position_attr(position, "funding_pnl", 0.0)
    if get_position_attr(position, "last_funding_time", None) is None:
        set_position_attr(position, "last_funding_time", position.entry_time)
    if get_position_attr(position, "last_update_time", None) is None:
        set_position_attr(position, "last_update_time", position.entry_time)


def entry_event(position: rb.RobustPosition, order: dict, fill_time: int, fee: float, cash: float, data: alpha.AlphaData) -> dict:
    return {
        "event_id": f"entry_{get_position_attr(position, 'position_id', '')}",
        "event_type": "entry",
        "position_id": get_position_attr(position, "position_id", ""),
        "order_id": order["order_id"],
        "timestamp": fill_time,
        "date": format_dt(fill_time),
        "symbol": position.symbol,
        "side": "buy",
        "price": position.entry_price,
        "units": position.units,
        "notional": position.units * position.entry_price,
        "fee": fee,
        "raw_leverage": get_position_attr(position, "raw_leverage", raw_position_leverage(position, position.entry_equity)),
        "applied_leverage": get_position_attr(
            position,
            "applied_leverage",
            applied_leverage_from_raw(raw_position_leverage(position, position.entry_equity)),
        ),
        "funding_rate": "",
        "funding_pnl": "",
        "pnl": -fee,
        "cash_delta": -fee,
        "equity_after": rb.portfolio_equity(cash, {position.symbol: position}, data, fill_time),
        "reason": "entry",
        "alpha_score": position.signal_score,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "entry_price": position.entry_price,
        "stop_price": position.stop_price,
        "exit_price": "",
        "position_total_pnl": "",
        "hold_hours": 0,
    }


def partial_exit_event(
    position: rb.RobustPosition,
    close_time: int,
    price: float,
    units: float,
    fee: float,
    pnl: float,
    cash: float,
) -> dict:
    return {
        "event_id": f"partial_{get_position_attr(position, 'position_id', '')}_{close_time}",
        "event_type": "partial_exit",
        "position_id": get_position_attr(position, "position_id", ""),
        "order_id": get_position_attr(position, "order_id", ""),
        "timestamp": close_time,
        "date": format_dt(close_time),
        "symbol": position.symbol,
        "side": "sell",
        "price": price,
        "units": units,
        "notional": units * price,
        "fee": fee,
        "raw_leverage": get_position_attr(position, "raw_leverage", raw_position_leverage(position, position.entry_equity)),
        "applied_leverage": get_position_attr(
            position,
            "applied_leverage",
            applied_leverage_from_raw(raw_position_leverage(position, position.entry_equity)),
        ),
        "funding_rate": "",
        "funding_pnl": "",
        "pnl": pnl,
        "cash_delta": pnl,
        "equity_after": cash,
        "reason": "take_profit_1r_half",
        "alpha_score": position.signal_score,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "entry_price": position.entry_price,
        "stop_price": position.stop_price,
        "exit_price": price,
        "position_total_pnl": "",
        "hold_hours": (close_time - position.entry_time) / 3600,
    }


def funding_event(position: rb.RobustPosition, event: dict, mark_price: float, notional: float, pnl: float, cash: float) -> dict:
    funding_time = int(event["funding_time"])
    return {
        "event_id": f"funding_{get_position_attr(position, 'position_id', '')}_{funding_time}",
        "event_type": "funding_fee",
        "position_id": get_position_attr(position, "position_id", ""),
        "order_id": get_position_attr(position, "order_id", ""),
        "timestamp": funding_time,
        "date": format_dt(funding_time),
        "symbol": position.symbol,
        "side": "funding",
        "price": mark_price,
        "units": position.units,
        "notional": notional,
        "fee": "",
        "raw_leverage": get_position_attr(position, "raw_leverage", raw_position_leverage(position, position.entry_equity)),
        "applied_leverage": get_position_attr(
            position,
            "applied_leverage",
            applied_leverage_from_raw(raw_position_leverage(position, position.entry_equity)),
        ),
        "funding_rate": event["funding_rate"],
        "funding_pnl": pnl,
        "pnl": pnl,
        "cash_delta": pnl,
        "equity_after": cash,
        "reason": "actual_funding",
        "alpha_score": position.signal_score,
        "trade_regime": position.regime,
        "trade_action_bias": position.action_bias,
        "entry_price": position.entry_price,
        "stop_price": position.stop_price,
        "exit_price": "",
        "position_total_pnl": "",
        "hold_hours": (funding_time - position.entry_time) / 3600,
    }


def portfolio_equity_at(cash: float, positions: Dict[str, rb.RobustPosition], data: alpha.AlphaData, mark_time: int) -> float:
    equity = cash
    for position in positions.values():
        price = mark_price_for(data, position.symbol, mark_time, position.entry_price)
        equity += position.units * (price - position.entry_price)
    return equity


def mark_price_for(data: alpha.AlphaData, symbol: str, time_value: Optional[int], fallback: Optional[float] = None) -> Optional[float]:
    if time_value is None:
        return fallback
    row = data.by_time_1h.get(symbol, {}).get(time_value)
    if row:
        return row["close"]
    rows = [row for row in data.rows_1h.get(symbol, []) if row["time"] <= time_value]
    return rows[-1]["close"] if rows else fallback


def liquidation_risk_now(position: rb.RobustPosition) -> bool:
    return bool(position.stop_price <= position.liquidation_price_est)


def latest_regime(data: alpha.AlphaData, now_ts: int) -> dict:
    date = alpha.date_from_ts(now_ts)
    if date in data.regime_by_date:
        return data.regime_by_date[date]
    if not data.regime_by_date:
        return {}
    latest_date = max(data.regime_by_date)
    return data.regime_by_date[latest_date]


def latest_display_regime(data: alpha.AlphaData, now_ts: int, regime_timeframe: str, short_regime_index: Optional[dict]) -> dict:
    if normalize_regime_timeframe(regime_timeframe) == "1d":
        return latest_regime(data, now_ts)
    rows = (short_regime_index or {}).get("rows") or []
    current = None
    for row in rows:
        if int(row.get("close_time") or 0) <= now_ts:
            current = row
        else:
            break
    return short_regime_4h.gate_regime_row(
        short_regime_4h.regime_from_row(current, short_regime_4h.PAPER_4H_CONFIG),
        short_regime_4h.action_bias_for_regime(short_regime_4h.regime_from_row(current, short_regime_4h.PAPER_4H_CONFIG)),
        current,
        latest_regime(data, now_ts),
    )


def initial_process_time(data: alpha.AlphaData, now_ts: int) -> int:
    latest = latest_closed_1h_open(data, now_ts)
    if latest is None:
        return now_ts
    return latest + 3600


def latest_closed_1h_open(data: alpha.AlphaData, now_ts: int) -> Optional[int]:
    return max((row["time"] for row in data.rows_1h.get("BTCUSDT", []) if row["time"] + 3600 <= now_ts), default=None)


def latest_known_1h_open(data: alpha.AlphaData, now_ts: int) -> Optional[int]:
    return max((row["time"] for row in data.rows_1h.get("BTCUSDT", []) if row["time"] <= now_ts), default=None)


def latest_mark_time(data: alpha.AlphaData, now_ts: int) -> Optional[int]:
    return latest_known_1h_open(data, now_ts) or latest_closed_1h_open(data, now_ts)


def latest_selected_signal_rows(signal_rows: List[dict]) -> List[dict]:
    selected = [row for row in signal_rows if str(row.get("selected", "")).lower() == "true"]
    latest_time = max((int(float(row["signal_time"])) for row in selected if row.get("signal_time")), default=None)
    if latest_time is None:
        return []
    return [row for row in selected if int(float(row["signal_time"])) == latest_time]


def recent_closed_trades(trade_rows: List[dict], limit: int) -> List[dict]:
    exits = [row for row in trade_rows if row.get("event_type") == "exit"]
    exits.sort(key=lambda row: int(float(row.get("timestamp") or 0)))
    return exits[-limit:]


def recent_equity_performance(equity_rows: List[dict], days: int) -> float:
    if len(equity_rows) < 2:
        return 0.0
    latest = equity_rows[-1]
    latest_ts = int(float(latest["timestamp"]))
    cutoff = latest_ts - days * 86400
    baseline = next((row for row in equity_rows if int(float(row["timestamp"])) >= cutoff), equity_rows[0])
    base_equity = float(baseline.get("equity") or INITIAL_CASH)
    latest_equity = float(latest.get("equity") or INITIAL_CASH)
    return (latest_equity / base_equity - 1) * 100 if base_equity else 0.0


def profit_factor(pnls: List[float]) -> Optional[float]:
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    if not losses:
        return None
    return sum(wins) / abs(sum(losses))


def win_rate_pct(pnls: List[float]) -> float:
    return len([value for value in pnls if value > 0]) / len(pnls) * 100 if pnls else 0.0


def candidate_table(rows: List[dict]) -> str:
    if not rows:
        return "_No current selected candidates._"
    lines = ["| Symbol | Alpha | Regime | Action bias | Fill |", "|---|---:|---|---|---|"]
    for row in rows[:10]:
        lines.append(
            f"| {row.get('symbol', '')} | {float(row.get('alpha_score') or 0.0):.2f} | "
            f"{row.get('trade_regime', '')} | {row.get('trade_action_bias', '')} | "
            f"{row.get('fill_date') or format_dt(int(row.get('fill_time') or 0))} |"
        )
    return "\n".join(lines)


def position_table(rows: List[dict]) -> str:
    if not rows:
        return "_No open paper positions._"
    lines = ["| Symbol | Entry | Last | Units | Unrealized | Funding | Liq risk |", "|---|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        lines.append(
            f"| {row.get('symbol', '')} | {float(row.get('entry_price') or 0.0):.6f} | "
            f"{float(row.get('last_price') or 0.0):.6f} | {float(row.get('units') or 0.0):.8f} | "
            f"{float(row.get('unrealized_pnl') or 0.0):.6f} | {float(row.get('funding_pnl') or 0.0):.6f} | "
            f"{row.get('liquidation_risk', '')} |"
        )
    return "\n".join(lines)


def ensure_state_files(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    for filename, fields in STATE_FILES.values():
        path = state_dir / filename
        if not path.exists():
            write_csv_rows(path, [], fields)
            continue
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
        if any(field not in header for field in fields):
            write_csv_rows(path, read_csv_rows(path), fields)


def ensure_defensive_probe_log(state_dir: Path) -> None:
    path = state_dir / DEFENSIVE_PROBE_LOG_NAME
    if not path.exists():
        write_csv_rows(path, [], defensive_probe_rules.PROBE_LOG_FIELDS)


def append_defensive_probe_log(state_dir: Path, signal_rows: List[dict]) -> None:
    rows = [
        {field: row.get(field, "") for field in defensive_probe_rules.PROBE_LOG_FIELDS}
        for row in signal_rows
        if row.get("_defensive_probe_log")
    ]
    if not rows:
        return
    path = state_dir / DEFENSIVE_PROBE_LOG_NAME
    existing = read_csv_rows(path)
    by_key = {defensive_probe_log_key(row): row for row in existing}
    for row in rows:
        by_key[defensive_probe_log_key(row)] = row
    write_csv_rows(path, sorted(by_key.values(), key=lambda row: (int(float(row.get("timestamp") or 0)), row.get("symbol", ""))), defensive_probe_rules.PROBE_LOG_FIELDS)


def defensive_probe_log_key(row: dict) -> str:
    return f"{row.get('timestamp', '')}|{row.get('symbol', '')}"


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key, "")) for key in fieldnames})


def merge_unique(existing: List[dict], new_rows: List[dict], key: str) -> List[dict]:
    merged = {str(row[key]): row for row in existing if row.get(key) not in {"", None}}
    for row in new_rows:
        merged[str(row[key])] = row
    def sort_key(row: dict) -> Tuple[int, str]:
        timestamp = row.get("timestamp") or row.get("signal_time") or row.get("created_time") or row.get(key) or 0
        try:
            return int(float(timestamp)), str(row.get(key, ""))
        except ValueError:
            return 0, str(row.get(key, ""))
    return sorted(merged.values(), key=sort_key)


def read_json_list(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) else []


def signal_key(signal: dict) -> Tuple[str, int]:
    return signal["symbol"], int(signal["signal_time"])


def paper_signal_id(signal: dict) -> str:
    symbol = signal["symbol"].lower()
    if symbol.endswith("usdt"):
        symbol = symbol[:-4]
    return f"sig_v1_2_{symbol}_{int(signal['signal_time'])}"


def paper_order_id(signal: dict) -> str:
    symbol = signal["symbol"].lower()
    if symbol.endswith("usdt"):
        symbol = symbol[:-4]
    return f"ord_v1_2_{symbol}_{int(signal['signal_time'])}"


def paper_position_id(order: dict) -> str:
    return f"pos_v1_2_{order['symbol'].lower()}_{int(float(order['fill_time']))}"


def get_position_attr(position: rb.RobustPosition, key: str, default=None):
    return getattr(position, key, default)


def set_position_attr(position: rb.RobustPosition, key: str, value) -> None:
    setattr(position, key, value)


def csv_value(value):
    if value is None:
        return ""
    return value


def parse_float(value, default: float = 0.0) -> float:
    if value in {"", None}:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def format_optional(value: Optional[float]) -> str:
    return "inf" if value is None else f"{value:.2f}"


def format_dt(timestamp: Optional[int]) -> str:
    if timestamp in {"", None}:
        return ""
    return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y-%m-%d %H:%M")


def ts_to_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat()


def iso_to_ts(value: str) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


if __name__ == "__main__":
    main()
