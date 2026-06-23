"""Build a read-only index of AI Researcher source reports.

The indexer reads markdown reports from sibling research worktrees and the
current repository docs, then writes a local JSONL index. It never modifies the
source reports it reads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
REPO_ROOT = ROOT.parent
INDEX_PATH = ROOT / "data" / "ai_researcher" / "report_index.jsonl"


@dataclass(frozen=True)
class ReportSource:
    branch_group: str
    pattern: str


DEFAULT_SOURCES: Sequence[ReportSource] = (
    ReportSource("ml_regime", "../agi-ml-regime/crypto_regime_map/reports/research/*.md"),
    ReportSource("4h_regime", "../agi-4h-regime/crypto_regime_map/reports/research/*.md"),
    ReportSource("leverage", "../agi-leverage-test/crypto_regime_map/reports/research/*.md"),
    ReportSource("futures_shadow", "../agi-futures-shadow/crypto_regime_map/reports/research/*.md"),
    ReportSource("docs", "docs/*.md"),
)


VERDICTS = ("PASS", "WATCH", "FAIL")
VERDICT_TOKEN_RE = re.compile(r"\b(PASS|WATCH|FAIL)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\s*UTC|Z)?)?\b")
TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
STRATEGY_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:strategy(?:\s+name)?|candidate|engine|전략(?:명)?|기준\s*전략)\s*[:=：]\s*(.+?)\s*$",
    re.IGNORECASE,
)
VERDICT_LABEL_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:verdict|status|decision|result|conclusion|판정|상태|결론|결과)\s*[:=：|-]\s*(.+)$",
    re.IGNORECASE,
)
DATE_LABEL_RE = re.compile(r"(?:generated|created|date|생성|작성|시각|일자)", re.IGNORECASE)
SUMMARY_HEADING_RE = re.compile(r"^\s*#{2,}\s*(summary|요약|conclusion|결론|recommendation|권고)\s*$", re.IGNORECASE)
METRIC_RE = re.compile(
    r"(CAGR|MDD|Sharpe|Sortino|Calmar|PF|Win|Return|Drawdown|PnL|OOS|trade|"
    r"exposure|leverage|margin|liq|bankrupt|robust|수익|손실|승률|레버리지|노출|청산|파산|거래|성과)",
    re.IGNORECASE,
)
KOREAN_VERDICTS = {
    "통과": "PASS",
    "관찰": "WATCH",
    "주의": "WATCH",
    "실패": "FAIL",
    "탈락": "FAIL",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI Researcher markdown report index")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=str(INDEX_PATH))
    args = parser.parse_args()

    rows = build_report_index(repo_root=Path(args.repo_root), output_path=Path(args.output_path))
    print(f"Wrote {len(rows)} rows to {Path(args.output_path)}")


def build_report_index(
    repo_root: Path = REPO_ROOT,
    output_path: Path = INDEX_PATH,
    sources: Sequence[ReportSource] = DEFAULT_SOURCES,
) -> List[dict]:
    repo_root = Path(repo_root).resolve()
    rows: List[dict] = []
    for source in sources:
        for path in expand_source_pattern(repo_root, source.pattern):
            if path.is_file():
                rows.append(index_report(path=path, repo_root=repo_root, branch_group=source.branch_group))

    rows.sort(key=lambda row: (row["branch_group"], row["source_path"]))
    write_jsonl(output_path, rows)
    return rows


def expand_source_pattern(repo_root: Path, pattern: str) -> List[Path]:
    target = repo_root / pattern
    return sorted(path.resolve() for path in target.parent.glob(target.name))


def index_report(path: Path, repo_root: Path, branch_group: str) -> dict:
    text = read_text(path)
    title = extract_title(text, path)
    return {
        "source_path": display_path(path, repo_root),
        "branch_group": branch_group,
        "title": title,
        "detected_verdict": detect_verdict(text),
        "strategy_name": extract_strategy_name(text, title),
        "created_at_or_mtime": extract_created_at_or_mtime(text, path),
        "summary_snippet": extract_summary_snippet(text),
        "key_metrics_text": extract_key_metrics_text(text),
    }


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def display_path(path: Path, repo_root: Path) -> str:
    return os.path.relpath(path.resolve(), repo_root.resolve())


def extract_title(text: str, path: Path) -> str:
    match = TITLE_RE.search(text)
    if match:
        return clean_inline(match.group(1))
    return path.stem.replace("_", " ").replace("-", " ").title()


def detect_verdict(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:120]:
        labeled = VERDICT_LABEL_RE.search(strip_markdown(line))
        if labeled:
            verdict = verdict_from_fragment(labeled.group(1), include_korean=True)
            if verdict:
                return verdict

    for line in lines[:80]:
        clean = strip_markdown(line)
        if line.startswith("#") or short_verdict_line(clean):
            verdict = verdict_from_fragment(clean, include_korean=False)
            if verdict:
                return verdict

    return "UNKNOWN"


def short_verdict_line(line: str) -> bool:
    if len(line) > 120 or "|" in line:
        return False
    lowered = line.lower()
    keywords = ("verdict", "status", "decision", "result", "conclusion", "robustness", "recommendation")
    korean_keywords = ("판정", "상태", "결론", "결과", "강건성", "권고")
    return any(keyword in lowered for keyword in keywords) or any(keyword in line for keyword in korean_keywords)


def verdict_from_fragment(fragment: str, include_korean: bool = False) -> str:
    tokens = {match.group(1).upper() for match in VERDICT_TOKEN_RE.finditer(fragment)}
    if len(tokens) == 1:
        return next(iter(tokens))

    if include_korean:
        korean_hits = {verdict for word, verdict in KOREAN_VERDICTS.items() if word in fragment}
        if len(korean_hits) == 1:
            return next(iter(korean_hits))
    return ""


def extract_strategy_name(text: str, title: str) -> str:
    for line in text.splitlines()[:120]:
        match = STRATEGY_RE.match(strip_markdown(line))
        if match:
            return truncate(clean_inline(match.group(1)), 120)
    title_without_report = re.sub(r"\s+report$", "", title, flags=re.IGNORECASE)
    return truncate(title_without_report, 120)


def extract_created_at_or_mtime(text: str, path: Path) -> str:
    for line in text.splitlines()[:120]:
        if DATE_LABEL_RE.search(line):
            match = DATE_RE.search(line)
            if match:
                return match.group(0).replace("T", " ")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return mtime.isoformat(timespec="seconds").replace("+00:00", "Z")


def extract_summary_snippet(text: str) -> str:
    section = extract_named_summary_section(text)
    if section:
        return truncate(compact_text(section), 420)

    paragraphs = split_paragraphs(text)
    for paragraph in paragraphs:
        clean = compact_text(paragraph)
        if clean and not looks_like_metadata(clean):
            return truncate(clean, 420)
    return ""


def extract_named_summary_section(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if SUMMARY_HEADING_RE.match(line):
            captured = []
            for next_line in lines[index + 1 :]:
                if next_line.startswith("## "):
                    break
                if next_line.strip():
                    captured.append(next_line.strip())
                if len(captured) >= 8:
                    break
            return "\n".join(captured)
    return ""


def split_paragraphs(text: str) -> List[str]:
    paragraphs: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue
        if stripped.startswith("#"):
            continue
        current.append(stripped)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def looks_like_metadata(text: str) -> bool:
    lowered = text.lower()
    if text.startswith("|") or text.startswith("- 생성") or text.startswith("- 기준"):
        return True
    metadata_markers = ("generated", "created", "period", "initial capital", "수수료", "기간", "초기자본")
    return any(marker in lowered for marker in metadata_markers)


def extract_key_metrics_text(text: str) -> str:
    metrics: List[str] = []
    for line in text.splitlines():
        clean = compact_text(line)
        if not clean:
            continue
        if METRIC_RE.search(clean):
            metrics.append(truncate(clean, 220))
        if len(metrics) >= 8:
            break
    return truncate(" | ".join(metrics), 1000)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def strip_markdown(text: str) -> str:
    return text.replace("`", "").replace("*", "").replace("_", "").strip()


def clean_inline(text: str) -> str:
    return compact_text(strip_markdown(text).strip("# "))


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


if __name__ == "__main__":
    main()
