import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ai_researcher_daily_brief as daily  # noqa: E402
import ai_researcher_index_reports as indexer  # noqa: E402
import ai_researcher_next_actions as next_actions  # noqa: E402


class AiResearcherTests(unittest.TestCase):
    def test_report_index_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "agi"
            repo_root.mkdir()
            report_path = (
                repo_root.parent
                / "agi-ml-regime"
                / "crypto_regime_map"
                / "reports"
                / "research"
                / "ml_regime_report.md"
            )
            write_text(
                report_path,
                """# ML Regime Research Report

- 생성 시각: 2026-06-22 10:00 UTC
- Strategy: ML Regime
- Verdict: FAIL

## Summary

ML regime did not beat the V0 baseline.

| Metric | Value |
| --- | ---: |
| CAGR | 1.2% |
| MDD | -70.0% |
""",
            )
            docs_path = repo_root / "docs" / "operations.md"
            write_text(docs_path, "# Operations Notes\n\nRead-only notes.\n")
            output_path = repo_root / "crypto_regime_map" / "data" / "ai_researcher" / "report_index.jsonl"

            rows = indexer.build_report_index(
                repo_root=repo_root,
                output_path=output_path,
                sources=(
                    indexer.ReportSource(
                        "ml_regime",
                        "../agi-ml-regime/crypto_regime_map/reports/research/*.md",
                    ),
                    indexer.ReportSource("docs", "docs/*.md"),
                ),
            )

            self.assertEqual(len(rows), 2)
            ml_row = next(row for row in rows if row["branch_group"] == "ml_regime")
            self.assertEqual(ml_row["detected_verdict"], "FAIL")
            self.assertEqual(ml_row["strategy_name"], "ML Regime")
            self.assertIn("CAGR", ml_row["key_metrics_text"])
            self.assertIn("../agi-ml-regime/", ml_row["source_path"])
            self.assertTrue(output_path.exists())
            written_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(written_rows, rows)

    def test_pass_watch_fail_detection(self):
        cases = {
            "Verdict: PASS\nThe candidate is acceptable.": "PASS",
            "Status: WATCH\nNeeds more samples.": "WATCH",
            "# 4H Regime robustness FAIL\n\nMDD is unstable.": "FAIL",
            "결론: 실패\n운영 후보가 아니다.": "FAIL",
            "This document only describes process.": "UNKNOWN",
            "`detected_verdict`: `PASS`, `WATCH`, `FAIL`, `UNKNOWN`": "UNKNOWN",
            "연구 결과가 통과하면 dev 후보가 된다.": "UNKNOWN",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(indexer.detect_verdict(text), expected)

    def test_daily_brief_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            index_path = tmp_path / "report_index.jsonl"
            output_path = tmp_path / "daily_research_brief.md"
            write_jsonl(
                index_path,
                [
                    {
                        "source_path": "../agi-ml-regime/crypto_regime_map/reports/research/ml.md",
                        "branch_group": "ml_regime",
                        "title": "ML Regime",
                        "detected_verdict": "FAIL",
                        "strategy_name": "ML Regime",
                        "created_at_or_mtime": "2026-06-22 10:00 UTC",
                        "summary_snippet": "Did not beat V0.",
                        "key_metrics_text": "MDD -70%",
                    },
                    {
                        "source_path": "../agi-leverage-test/crypto_regime_map/reports/research/lev.md",
                        "branch_group": "leverage",
                        "title": "Leverage Candidate",
                        "detected_verdict": "WATCH",
                        "strategy_name": "Leverage",
                        "created_at_or_mtime": "2026-06-22 11:00 UTC",
                        "summary_snippet": "Only effective exposure <= 1.0 remains.",
                        "key_metrics_text": "Max gross 1.0x",
                    },
                ],
            )

            text = daily.generate_daily_brief(index_path=index_path, output_path=output_path)

            self.assertTrue(output_path.exists())
            self.assertIn("## 1. 현재 생존 전략", text)
            self.assertIn("## 7. 금지해야 할 액션", text)
            self.assertIn("V0 1D regime = 현재 생존 기준선", text)
            self.assertIn("ML Regime: FAIL", text)
            self.assertIn("effective exposure <= 1.0", text)
            self.assertIn("AI는 직접 매매하지 않고 Researcher/Auditor 역할", text)

    def test_next_actions_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            index_path = tmp_path / "report_index.jsonl"
            daily_path = tmp_path / "daily.md"
            output_path = tmp_path / "next_actions.md"
            write_jsonl(
                index_path,
                [
                    {"branch_group": "ml_regime", "detected_verdict": "FAIL"},
                    {"branch_group": "futures_shadow", "detected_verdict": "WATCH"},
                ],
            )
            daily_path.write_text("# Daily\n\nV0 baseline.", encoding="utf-8")

            text = next_actions.generate_next_actions(
                index_path=index_path,
                daily_brief_path=daily_path,
                output_path=output_path,
            )

            self.assertTrue(output_path.exists())
            priorities = [
                "Priority 1. 운영 안정성",
                "Priority 2. V0 유지",
                "Priority 3. Shadow 데이터 축적",
                "Priority 4. Dashboard 개선",
                "Priority 5. Execution safety",
                "Priority 6. 새 전략 연구 후순위",
            ]
            positions = [text.index(priority) for priority in priorities]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("paper/live engine 실행 금지", text)
            self.assertIn("futures_shadow_reports: 1", text)

    def test_source_report_is_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "agi"
            repo_root.mkdir()
            report_path = (
                repo_root.parent
                / "agi-4h-regime"
                / "crypto_regime_map"
                / "reports"
                / "research"
                / "4h_report.md"
            )
            write_text(report_path, "# 4H Regime robustness FAIL\n\n## Summary\n\nUnstable.")
            before_bytes = report_path.read_bytes()
            before_mtime_ns = report_path.stat().st_mtime_ns

            indexer.build_report_index(
                repo_root=repo_root,
                output_path=repo_root / "crypto_regime_map" / "data" / "ai_researcher" / "report_index.jsonl",
                sources=(
                    indexer.ReportSource(
                        "4h_regime",
                        "../agi-4h-regime/crypto_regime_map/reports/research/*.md",
                    ),
                ),
            )

            self.assertEqual(report_path.read_bytes(), before_bytes)
            self.assertEqual(report_path.stat().st_mtime_ns, before_mtime_ns)

    @unittest.skipUnless(shutil.which("git") and (REPO_ROOT / ".git").exists(), "git repo not available")
    def test_ai_researcher_data_output_is_gitignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", "crypto_regime_map/data/ai_researcher/report_index.jsonl"],
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


if __name__ == "__main__":
    unittest.main()
