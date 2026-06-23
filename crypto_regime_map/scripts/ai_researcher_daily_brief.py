"""Generate the AI Researcher daily brief from the local report index."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
INDEX_PATH = ROOT / "data" / "ai_researcher" / "report_index.jsonl"
REPORT_PATH = ROOT / "reports" / "ai" / "daily_research_brief.md"


CURRENT_CONCLUSIONS = (
    "V0 1D regime = 현재 생존 기준선",
    "ML Regime = FAIL",
    "4H Regime = robustness FAIL",
    "Diversified/Core-Satellite = FAIL",
    "leverage = effective exposure <= 1.0만 후보",
    "futures shadow 후보 = 3x size25, 2x size50",
    "AI는 직접 매매하지 않고 Researcher/Auditor 역할",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI Researcher daily brief")
    parser.add_argument("--index-path", default=str(INDEX_PATH))
    parser.add_argument("--output-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    text = generate_daily_brief(index_path=Path(args.index_path), output_path=Path(args.output_path))
    print(text)


def generate_daily_brief(index_path: Path = INDEX_PATH, output_path: Path = REPORT_PATH) -> str:
    rows = load_index(index_path)
    generated_at = utc_now_label()
    text = build_daily_brief(rows, generated_at=generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text


def build_daily_brief(rows: List[dict], generated_at: str) -> str:
    pass_rows = rows_by_verdict(rows, "PASS")
    fail_rows = rows_by_verdict(rows, "FAIL")
    watch_rows = rows_by_verdict(rows, "WATCH")
    leverage_rows = rows_by_branch(rows, "leverage")
    futures_rows = rows_by_branch(rows, "futures_shadow")

    lines = [
        "# AI Researcher Daily Brief",
        "",
        f"- generated_at: {generated_at}",
        f"- indexed_reports: {len(rows)}",
        "- role: read-only researcher/auditor",
        "",
        "## 1. 현재 생존 전략",
        "",
        "- V0 1D regime는 현재 생존 기준선이다.",
        "- 새 후보는 V0를 대체하지 않고, 독립 검증과 shadow 축적을 통과할 때까지 연구 상태로 둔다.",
        *format_rows(pass_rows, empty="- 인덱스에서 PASS 판정 report는 감지되지 않았다."),
        "",
        "## 2. 실패한 연구 요약",
        "",
        "- ML Regime: FAIL. 운영 반영 대상이 아니다.",
        "- 4H Regime: robustness FAIL. V0 대체 후보가 아니다.",
        "- Diversified/Core-Satellite: FAIL. 운영 반영 대상이 아니다.",
        *format_rows(fail_rows, empty="- 인덱스에서 추가 FAIL report는 감지되지 않았다."),
        "",
        "## 3. WATCH 상태 연구 요약",
        "",
        "- leverage는 effective exposure <= 1.0 조건만 후보로 남긴다.",
        "- WATCH 후보는 실거래가 아니라 추가 리포트와 shadow 데이터로만 평가한다.",
        *format_rows(watch_rows, empty="- 인덱스에서 WATCH report는 감지되지 않았다."),
        *format_rows(leverage_rows, empty="- leverage worktree report는 현재 인덱스에 없다."),
        "",
        "## 4. Futures Shadow 상태",
        "",
        "- 후보: 3x size25, 2x size50.",
        "- 둘 다 production/live 주문 후보가 아니라 shadow 관찰 후보이다.",
        *format_rows(futures_rows, empty="- futures shadow worktree report는 현재 인덱스에 없다."),
        "",
        "## 5. 오늘 확인할 항목",
        "",
        "- sibling research worktree에 새 markdown report가 생겼는지 확인한다.",
        "- V0 1D regime 기준선이 문서와 dashboard에 동일하게 표시되는지 확인한다.",
        "- futures shadow 후보의 sample 수, drawdown, liquidation-touch 여부를 report로만 확인한다.",
        "- data/cache/state/log/csv 산출물이 Git 후보에 들어오지 않는지 확인한다.",
        "",
        "## 6. 다음 액션",
        "",
        "- 운영 안정성 확인을 최우선으로 둔다.",
        "- V0 유지와 shadow 데이터 축적을 새 전략 연구보다 앞에 둔다.",
        "- dashboard에는 현재 기준선, 실패 후보, shadow 후보를 분리해서 표시한다.",
        "- execution safety 점검은 read-only 코드와 주문 API 미사용 확인 중심으로 진행한다.",
        "",
        "## 7. 금지해야 할 액션",
        "",
        "- AI Researcher가 직접 주문하거나 paper/live engine을 실행하지 않는다.",
        "- Mac mini 운영 state에 접근하거나 수정하지 않는다.",
        "- Xeon shadow state를 수정하지 않는다.",
        "- main 브랜치를 직접 수정하지 않는다.",
        "- data/cache/state/log/csv와 report_index.jsonl을 commit하지 않는다.",
        "",
        "## Current Conclusions",
        "",
        *[f"- {item}" for item in CURRENT_CONCLUSIONS],
        "",
    ]
    return "\n".join(lines)


def load_index(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def rows_by_verdict(rows: Iterable[dict], verdict: str) -> List[dict]:
    return [row for row in rows if row.get("detected_verdict") == verdict]


def rows_by_branch(rows: Iterable[dict], branch_group: str) -> List[dict]:
    return [row for row in rows if row.get("branch_group") == branch_group]


def format_rows(rows: List[dict], empty: str, limit: int = 6) -> List[str]:
    if not rows:
        return [empty]
    formatted = []
    for row in rows[:limit]:
        summary = row.get("summary_snippet") or row.get("key_metrics_text") or "summary 없음"
        formatted.append(
            f"- {row.get('branch_group', 'unknown')}: {row.get('title', 'Untitled')} "
            f"({row.get('source_path', '')}) - {truncate(summary, 180)}"
        )
    if len(rows) > limit:
        formatted.append(f"- additional_reports: {len(rows) - limit}")
    return formatted


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def utc_now_label() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    main()
