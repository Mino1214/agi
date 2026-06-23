"""Read-only runtime summary loading for AI Researcher reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple


MACMINI_RUNTIME_JSON_PATH = Path(
    "/Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.json"
)
MACMINI_RUNTIME_MD_PATH = Path("/Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.md")
XEON_SHADOW_RUNTIME_DIR = Path("/Users/myno/agi-lab/runtime/xeon-shadow")


@dataclass(frozen=True)
class MacMiniRuntimeSummary:
    source_path: str
    available: bool = False
    warning: str = ""
    timestamp: str = ""
    current_equity: Any = None
    daily_return_pct: Any = None
    open_positions: Any = None
    orders_count: Any = None
    trades_count: Any = None
    current_regime: str = ""
    action_bias: str = ""
    can_enter: Optional[bool] = None
    entry_block_reason: str = ""
    health_status: str = ""
    warnings_count: Any = None
    last_updated_time: str = ""


@dataclass(frozen=True)
class ShadowRuntimeSummary:
    source_dir: str
    available: bool = False
    summary_files: Tuple[str, ...] = ()
    warning: str = ""


@dataclass(frozen=True)
class RuntimeSources:
    macmini: MacMiniRuntimeSummary
    shadow: ShadowRuntimeSummary


def load_runtime_sources(
    macmini_json_path: Path = MACMINI_RUNTIME_JSON_PATH,
    shadow_runtime_dir: Path = XEON_SHADOW_RUNTIME_DIR,
) -> RuntimeSources:
    """Load runtime summaries without touching source runtime state."""

    return RuntimeSources(
        macmini=load_macmini_runtime_summary(Path(macmini_json_path)),
        shadow=inspect_shadow_runtime_dir(Path(shadow_runtime_dir)),
    )


def load_macmini_runtime_summary(path: Path = MACMINI_RUNTIME_JSON_PATH) -> MacMiniRuntimeSummary:
    path = Path(path)
    if not path.exists():
        return MacMiniRuntimeSummary(
            source_path=str(path),
            warning="Mac mini runtime summary not available",
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return MacMiniRuntimeSummary(
            source_path=str(path),
            warning=f"Mac mini runtime JSON parse failed: {exc.msg}",
        )
    except OSError as exc:
        return MacMiniRuntimeSummary(
            source_path=str(path),
            warning=f"Mac mini runtime summary read failed: {exc}",
        )

    if not isinstance(payload, dict):
        return MacMiniRuntimeSummary(
            source_path=str(path),
            warning="Mac mini runtime JSON parse failed: root is not an object",
        )

    return MacMiniRuntimeSummary(
        source_path=str(path),
        available=True,
        timestamp=string_value(payload.get("timestamp")),
        current_equity=payload.get("current_equity"),
        daily_return_pct=payload.get("daily_return_pct"),
        open_positions=open_positions_count(payload.get("open_positions")),
        orders_count=payload.get("orders_count"),
        trades_count=payload.get("trades_count"),
        current_regime=string_value(payload.get("current_regime")),
        action_bias=string_value(payload.get("action_bias")),
        can_enter=bool_or_none(payload.get("can_enter")),
        entry_block_reason=string_value(payload.get("entry_block_reason")),
        health_status=string_value(payload.get("health_status")),
        warnings_count=warnings_count(payload),
        last_updated_time=string_value(payload.get("last_updated_time")),
    )


def inspect_shadow_runtime_dir(path: Path = XEON_SHADOW_RUNTIME_DIR) -> ShadowRuntimeSummary:
    path = Path(path)
    if not path.exists():
        return ShadowRuntimeSummary(
            source_dir=str(path),
            warning="Xeon shadow runtime summary not available",
        )

    try:
        candidates = sorted(path.rglob("*"))
    except OSError as exc:
        return ShadowRuntimeSummary(
            source_dir=str(path),
            warning=f"Xeon shadow runtime summary read failed: {exc}",
        )

    summary_files = tuple(
        str(candidate)
        for candidate in candidates
        if candidate.is_file()
        and candidate.suffix.lower() in {".json", ".md"}
        and "summary" in candidate.name.lower()
    )
    if not summary_files:
        return ShadowRuntimeSummary(
            source_dir=str(path),
            warning="Xeon shadow runtime directory has no summary files",
        )

    return ShadowRuntimeSummary(source_dir=str(path), available=True, summary_files=summary_files[:5])


def open_positions_count(value: Any) -> Any:
    if isinstance(value, dict):
        if "count" in value:
            return value.get("count")
        positions = value.get("positions")
        if isinstance(positions, list):
            return len(positions)
    if isinstance(value, list):
        return len(value)
    return value


def warnings_count(payload: dict) -> Any:
    if payload.get("warnings_count") is not None:
        return payload.get("warnings_count")
    latest_warnings = payload.get("latest_warnings")
    if isinstance(latest_warnings, list):
        return len(latest_warnings)
    return None


def bool_or_none(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def is_normal_defensive_wait(summary: MacMiniRuntimeSummary) -> bool:
    return (
        summary.available
        and summary.current_regime == "defensive"
        and summary.action_bias == "reduce_risk"
        and summary.can_enter is False
        and summary.entry_block_reason == "regime_reduce_risk"
        and numeric_value(summary.open_positions) == 0
        and numeric_value(summary.orders_count) == 0
        and numeric_value(summary.trades_count) == 0
    )


def numeric_value(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
