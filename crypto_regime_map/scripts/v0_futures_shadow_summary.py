"""Read-only V0 futures paper shadow summary.

The script reads three paper state directories and renders a markdown
comparison. It does not run the paper engine and does not mutate state files.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only V0 futures shadow paper summary")
    parser.add_argument("--v0-state-dir", default=str(paper.STATE_DIR))
    parser.add_argument("--futures-3x-size25-state-dir", default=str(paper.FUTURES_SHADOW_STATE_DIRS["v0_futures_3x_size25"]))
    parser.add_argument("--futures-2x-size50-state-dir", default=str(paper.FUTURES_SHADOW_STATE_DIRS["v0_futures_2x_size50"]))
    parser.add_argument("--output", default="", help="Optional markdown output path. Omit to print to stdout only.")
    args = parser.parse_args()

    summaries = [
        summarize_state("V0 current", "v0_spot_or_1x", Path(args.v0_state_dir)),
        summarize_state("futures 3x size25", "v0_futures_3x_size25", Path(args.futures_3x_size25_state_dir)),
        summarize_state("futures 2x size50", "v0_futures_2x_size50", Path(args.futures_2x_size50_state_dir)),
    ]
    report = render_report(summaries)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(str(output))
        return
    print(report)


def summarize_state(label: str, expected_profile: str, state_dir: Path) -> dict:
    profile = read_json(state_dir / paper.PAPER_PROFILE_STATE_NAME)
    equity_rows = read_csv_rows(state_dir / paper.STATE_FILES["equity"][0])
    order_rows = read_csv_rows(state_dir / paper.STATE_FILES["orders"][0])
    trade_rows = read_csv_rows(state_dir / paper.STATE_FILES["trades"][0])
    position_rows = read_csv_rows(state_dir / paper.STATE_FILES["positions"][0])
    signal_rows = read_csv_rows(state_dir / paper.STATE_FILES["signals"][0])
    latest = equity_rows[-1] if equity_rows else {}
    closed_trades = [row for row in trade_rows if row.get("event_type") == "exit"]
    open_positions = [row for row in position_rows if row.get("status", "open") == "open"]
    expected = paper.PAPER_PROFILES.get(expected_profile, paper.DEFAULT_PAPER_PROFILE)
    profile_id = str(profile.get("paper_profile") or expected_profile)
    leverage = float(profile.get("exchange_leverage") or expected.exchange_leverage)
    size_multiplier = float(profile.get("size_multiplier") or expected.size_multiplier)
    effective = float(profile.get("effective_exposure") or leverage * size_multiplier)
    equity = number(latest.get("equity"), paper.INITIAL_CASH)
    max_drawdown = min((number(row.get("drawdown_pct"), 0.0) for row in equity_rows), default=0.0)
    liquidation_risk_count = int(number(latest.get("liquidation_risk_count"), 0.0))
    return {
        "label": label,
        "profile": profile_id,
        "state_dir": str(state_dir),
        "state_exists": state_dir.exists(),
        "exchange_leverage": leverage,
        "size_multiplier": size_multiplier,
        "effective_exposure": effective,
        "latest_equity": equity,
        "cumulative_pnl": number(latest.get("cumulative_pnl"), equity - paper.INITIAL_CASH),
        "max_drawdown_pct": max_drawdown,
        "orders": len(order_rows),
        "open_positions": int(number(latest.get("open_positions"), float(len(open_positions)))),
        "positions": len(position_rows),
        "open_notional": number(latest.get("open_notional"), sum(number(row.get("notional"), 0.0) for row in open_positions)),
        "trades": len(trade_rows),
        "signals": len(signal_rows),
        "closed_trades": len(closed_trades),
        "current_regime": latest.get("current_regime", ""),
        "current_action_bias": latest.get("current_action_bias", ""),
        "last_equity_time": latest.get("date", ""),
        "strategy_status": latest.get("strategy_status", "missing" if not equity_rows else ""),
        "liquidation_risk_count": liquidation_risk_count,
    }


def render_report(rows: List[dict]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# V0 Futures Paper Shadow Summary",
        "",
        f"- generated_at: {generated}",
        "- source: paper state CSV ledgers only",
        "- mutation: none; this script does not run paper, order, or live execution paths",
        "",
        "| Candidate | Profile | State exists | Leverage | Size | Effective | Equity | Orders | Positions | Trades | Signals | Regime | Action bias | Max DD | Open notional | Liq risk | Status | Last equity |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['profile']} | {str(row['state_exists']).lower()} | "
            f"{row['exchange_leverage']:.0f}x | {row['size_multiplier']:.2f} | {row['effective_exposure']:.2f}x | "
            f"{row['latest_equity']:.6f} | {row['orders']} | {row['positions']} | {row['trades']} | {row['signals']} | "
            f"{row['current_regime']} | {row['current_action_bias']} | {row['max_drawdown_pct']:.2f}% | "
            f"{row['open_notional']:.6f} | {row['liquidation_risk_count']} | {row['strategy_status']} | {row['last_equity_time']} |"
        )
    lines.extend(
        [
            "",
            "## State Directories",
            "",
        ]
    )
    for row in rows:
        lines.append(f"- {row['label']}: `{row['state_dir']}`")
    lines.append("")
    return "\n".join(lines)


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def number(value, default: float = 0.0) -> float:
    if value in {"", None}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    main()
