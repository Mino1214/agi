"""Daily/loop runner for V0 futures paper shadow profiles.

This script runs only the two approved futures paper shadow profiles in fixed
research_cache state directories, then writes a comparison summary. It does
not call live execution or exchange order APIs.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import alpha_engine_v1_2_paper_engine as paper  # noqa: E402
import v0_futures_shadow_summary as shadow_summary  # noqa: E402


APPROVED_SHADOW_PROFILE_IDS = ("v0_futures_3x_size25", "v0_futures_2x_size50")
RESEARCH_CACHE_DIR = ROOT / "data" / "research_cache"
LOG_DIR = RESEARCH_CACHE_DIR / "logs"
LOG_PATH = LOG_DIR / "v0_futures_shadow_daily_runner.log"
LOCK_PATH = RESEARCH_CACHE_DIR / "v0_futures_shadow_daily_runner.lock"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "v0_futures_shadow_daily_report.md"


class RunnerLockError(RuntimeError):
    pass


class RunnerLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: Optional[int] = None

    def __enter__(self) -> "RunnerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RunnerLockError(f"runner lock exists: {self.path}") from exc
        payload = f"pid={os.getpid()} started_at={utc_now()}\n"
        os.write(self.fd, payload.encode("utf-8"))
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run approved V0 futures paper shadows and write a summary")
    parser.add_argument("command", nargs="?", choices=["run-once", "loop"], default="run-once")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown summary output path.")
    parser.add_argument("--sleep", type=int, default=3600, help="Loop sleep seconds.")
    parser.add_argument("--iterations", type=int, default=0, help="Loop iterations. 0 means forever.")
    parser.add_argument("--now-ts", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        if args.command == "loop":
            exit_code = run_loop(
                output_path=Path(args.output),
                sleep_seconds=args.sleep,
                iterations=args.iterations,
                now_ts=args.now_ts,
            )
            raise SystemExit(exit_code)
        result = run_daily_shadow(
            output_path=Path(args.output),
            now_ts=args.now_ts,
        )
        print(result["output_path"])
        raise SystemExit(result["exit_code"])
    except RunnerLockError as exc:
        append_log(LOG_PATH, f"LOCKED {exc}")
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


def run_loop(
    output_path: Path = DEFAULT_OUTPUT,
    use_cache: bool = True,
    cache_only: bool = True,
    sleep_seconds: int = 3600,
    iterations: int = 0,
    now_ts: Optional[int] = None,
    runner: Callable[..., dict] = paper.run_once,
    lock_path: Path = LOCK_PATH,
    log_path: Path = LOG_PATH,
) -> int:
    loops = 0
    worst_exit_code = 0
    while iterations <= 0 or loops < iterations:
        result = run_daily_shadow(
            output_path=output_path,
            use_cache=use_cache,
            cache_only=cache_only,
            now_ts=now_ts,
            runner=runner,
            lock_path=lock_path,
            log_path=log_path,
        )
        worst_exit_code = max(worst_exit_code, int(result["exit_code"]))
        loops += 1
        if iterations > 0 and loops >= iterations:
            break
        time.sleep(max(1, int(sleep_seconds)))
    return worst_exit_code


def run_daily_shadow(
    output_path: Path = DEFAULT_OUTPUT,
    use_cache: bool = True,
    cache_only: bool = True,
    now_ts: Optional[int] = None,
    runner: Callable[..., dict] = paper.run_once,
    lock_path: Path = LOCK_PATH,
    log_path: Path = LOG_PATH,
) -> dict:
    with RunnerLock(lock_path):
        append_log(log_path, f"START output={output_path}")
        run_results = run_shadow_profiles(
            use_cache=use_cache,
            cache_only=cache_only,
            now_ts=now_ts,
            runner=runner,
            log_path=log_path,
        )
        report = build_summary_report(run_results, log_path=log_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        exit_code = overall_exit_code(run_results)
        append_log(log_path, f"FINISH exit_code={exit_code} output={output_path}")
        return {
            "output_path": str(output_path),
            "profiles": [row["profile_id"] for row in run_results],
            "run_results": run_results,
            "exit_code": exit_code,
            "log_path": str(log_path),
        }


def run_shadow_profiles(
    use_cache: bool = True,
    cache_only: bool = True,
    now_ts: Optional[int] = None,
    runner: Callable[..., dict] = paper.run_once,
    log_path: Path = LOG_PATH,
) -> List[dict]:
    results = []
    for profile_id in APPROVED_SHADOW_PROFILE_IDS:
        profile = paper.paper_profile_for_id(profile_id)
        state_dir = fixed_shadow_state_dir(profile_id)
        started = utc_now()
        append_log(log_path, f"PROFILE_START profile={profile_id} state_dir={state_dir}")
        try:
            paper.validate_paper_profile(profile)
            paper.validate_paper_profile_state_dir(profile, state_dir, state_dir_is_explicit=True)
            result = call_profile_runner(
                runner,
                state_dir,
                use_cache=use_cache,
                cache_only=cache_only,
                now_ts=now_ts,
                profile=profile,
            )
            row = profile_result_row(profile_id, state_dir, started, utc_now(), "success", result=result)
            append_log(
                log_path,
                "PROFILE_SUCCESS "
                f"profile={profile_id} orders={row['orders_created']} signals={row['signals_created']} "
                f"trades={row['trades_created']} positions={row['positions']}",
            )
        except Exception as exc:  # keep the other approved shadow running
            row = profile_result_row(profile_id, state_dir, started, utc_now(), "failed", error=f"{type(exc).__name__}: {exc}")
            append_log(log_path, f"PROFILE_FAILED profile={profile_id} error={row['error']}")
        results.append(row)
    return results


def call_profile_runner(
    runner: Callable[..., dict],
    state_dir: Path,
    use_cache: bool,
    cache_only: bool,
    now_ts: Optional[int],
    profile: paper.PaperProfile,
) -> dict:
    context = cache_only_market_data() if cache_only and runner is paper.run_once else nullcontext()
    with context:
        return runner(
            state_dir,
            use_cache=True if cache_only else use_cache,
            now_ts=now_ts,
            paper_profile=profile,
        )


@contextmanager
def cache_only_market_data():
    original_fetch_ohlcv = paper.fetch_ohlcv
    original_load_latest_funding_history = paper.load_latest_funding_history

    def blocked_fetch_ohlcv(*_args, **_kwargs):
        raise RuntimeError("futures shadow runner is cache-only")

    def cached_funding_history(symbol: str, _use_cache: bool, interval_hours: Optional[float], now_ts: int) -> List[dict]:
        path = paper.ROOT / "data" / "raw" / f"{symbol}_futures_funding_rate.json"
        return paper.normalize_latest_funding_rows(symbol, paper.read_json_list(path), interval_hours, now_ts)

    paper.fetch_ohlcv = blocked_fetch_ohlcv
    paper.load_latest_funding_history = cached_funding_history
    try:
        yield
    finally:
        paper.fetch_ohlcv = original_fetch_ohlcv
        paper.load_latest_funding_history = original_load_latest_funding_history


def profile_result_row(
    profile_id: str,
    state_dir: Path,
    started_at: str,
    finished_at: str,
    status: str,
    result: Optional[dict] = None,
    error: str = "",
) -> dict:
    result = result or {}
    return {
        "profile_id": profile_id,
        "state_dir": str(state_dir),
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "error": error,
        "dashboard": result.get("dashboard", ""),
        "orders_created": result.get("orders_created", 0),
        "signals_created": result.get("signals_created", 0),
        "trades_created": result.get("trades_created", 0),
        "positions": result.get("positions", 0),
    }


def build_summary_report(run_results: Iterable[dict], log_path: Path = LOG_PATH) -> str:
    run_rows = list(run_results)
    summary_rows = [
        shadow_summary.summarize_state("V0 current", "v0_spot_or_1x", paper.STATE_DIR),
        shadow_summary.summarize_state("futures 3x size25", "v0_futures_3x_size25", fixed_shadow_state_dir("v0_futures_3x_size25")),
        shadow_summary.summarize_state("futures 2x size50", "v0_futures_2x_size50", fixed_shadow_state_dir("v0_futures_2x_size50")),
    ]
    generated = utc_now()
    exit_code = overall_exit_code(run_rows)
    lines = [
        "# V0 Futures Paper Shadow Daily Run",
        "",
        f"- generated_at: {generated}",
        "- runner: `v0_futures_shadow_daily_runner.py`",
        "- executed_profiles: `v0_futures_3x_size25`, `v0_futures_2x_size50`",
        "- execution_scope: futures paper shadow only; no live or exchange order APIs",
        f"- exit_code: {exit_code}",
        f"- log_path: `{log_path}`",
        "",
        "## Run Results",
        "",
        "| Profile | Status | State dir | Orders created | Signals created | Trades created | Open positions | Error |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in run_rows:
        lines.append(
            f"| {row['profile_id']} | {row['status']} | `{row['state_dir']}` | {row['orders_created']} | "
            f"{row['signals_created']} | {row['trades_created']} | {row['positions']} | {row['error']} |"
        )
    lines.extend(["", "## State Summary", "", shadow_summary.render_report(summary_rows)])
    return "\n".join(lines)


def fixed_shadow_state_dir(profile_id: str) -> Path:
    if profile_id not in APPROVED_SHADOW_PROFILE_IDS:
        raise ValueError(f"unsupported futures shadow profile: {profile_id}")
    state_dir = paper.FUTURES_SHADOW_STATE_DIRS[profile_id]
    expected_root = paper.ROOT / "data" / "research_cache"
    resolved = paper.safe_resolve(state_dir)
    if expected_root.resolve(strict=False) not in resolved.parents:
        raise ValueError("futures shadow state-dir must remain under data/research_cache")
    return state_dir


def overall_exit_code(run_results: Iterable[dict]) -> int:
    return 0 if all(row.get("status") == "success" for row in run_results) else 1


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} {message}\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


if __name__ == "__main__":
    main()
