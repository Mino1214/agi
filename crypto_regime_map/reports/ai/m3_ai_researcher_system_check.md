# M3 AI Researcher System Check

- checked_at: 2026-06-23T13:42:08Z
- repo: /Users/myno/agi-lab/agi/crypto_regime_map
- mode: read-only analysis; generated AI Researcher reports and this check report only.

## Result

- overall: WARN
- reason: system checks passed, but `git status` is not clean.
- paper/live engine: NOT RUN
- Mac mini operating state: NOT ACCESSED
- Xeon shadow state: NOT MODIFIED
- commit/push: NOT RUN

## 1. Branch

- expected: `feature/ai-researcher`
- actual: `feature/ai-researcher`
- result: PASS

## 2. Git Status

- result: NOT CLEAN

```text
## feature/ai-researcher...origin/feature/ai-researcher
 M reports/ai/daily_research_brief.md
 M reports/ai/next_actions.md
?? reports/ai/m3_ai_researcher_system_check.md
```

## 3. Worktrees

```text
/Users/myno/agi-lab/agi                 75a553c [feature/ai-researcher]
/Users/myno/agi-lab/agi-4h-regime       2b2c59b (detached HEAD)
/Users/myno/agi-lab/agi-futures-shadow  19c2d85 (detached HEAD)
/Users/myno/agi-lab/agi-leverage-test   4f203a9 (detached HEAD)
/Users/myno/agi-lab/agi-ml-regime       1a7b61a (detached HEAD)
```

- `/Users/myno/agi-lab/agi-4h-regime`: clean, detached HEAD.
- `/Users/myno/agi-lab/agi-futures-shadow`: clean, detached HEAD.
- `/Users/myno/agi-lab/agi-leverage-test`: clean, detached HEAD.
- `/Users/myno/agi-lab/agi-ml-regime`: clean, detached HEAD.

## 4. Mac mini Runtime Files

- `/Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.md`: EXISTS
  - sha256: `3ca0aadd5149cd3af16da54399fafb3fc24fd83ea469bfe3cbb90c6925706b33`
- `/Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.json`: EXISTS
  - sha256: `f9051fec9f8f55249349b1aacd4b544bff468d503b81553890d149ec7df5604e`

## 5. Xeon Shadow Runtime Files

- `/Users/myno/agi-lab/runtime/xeon-shadow/v0_futures_shadow_daily_report.md`: EXISTS
  - sha256: `950a6457bf7edcbb29746f2230f7fa2abd279ca0eb7f916486f0b2ef61a3cb76`

## 6. AI Researcher Scripts

- `python3 scripts/ai_researcher_index_reports.py`: PASS
  - result: wrote 16 rows to `data/ai_researcher/report_index.jsonl`
- `python3 scripts/ai_researcher_daily_brief.py`: PASS
  - output: `reports/ai/daily_research_brief.md`
- `python3 scripts/ai_researcher_next_actions.py`: PASS
  - output: `reports/ai/next_actions.md`

## 7. Daily Brief Runtime Reflection

- Mac mini runtime reflected: PASS
  - `## Mac mini V1.2 Paper Runtime`
  - source: `/Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.json`
  - reflected: `regime: defensive`, `warnings_count: 17`
- Xeon shadow runtime reflected: PASS
  - reflected line: `xeon_shadow_runtime: Xeon shadow runtime directory has no summary files`
  - note: runtime directory has a markdown file, but no filename matching the script's summary-file rule.

## 8. Next Actions Reflection

- result: PASS
- reflected:
  - `daily_brief_available: yes`
  - `macmini_runtime_available: yes`
  - `macmini_runtime_regime: defensive`
  - `Xeon shadow runtime summary가 아직 없어 V1.2 비교는 shadow sync 이후로 둔다.`

## 9. Tests

- `pytest`: PASS
  - result: 80 passed in 3.42s
- `python3 -m py_compile $(rg --files -g '*.py')`: PASS
- `git diff --check`: PASS

## 10. Commit Candidate Guard

- data/cache/state/log/csv commit candidates: PASS
  - no `git status --short --untracked-files=all` entries matched `data/`, `cache/`, `state/`, `log/`, `logs/`, or `*.csv`.
- `report_index.jsonl` ignored: PASS
  - matched rule: `.gitignore:48:**/data/ai_researcher/`

## 11. Order API Risk Pattern

- result: PASS
- scope:
  - `scripts/ai_researcher_*.py`
  - `../docs/ai_researcher.md`
  - `reports/ai/daily_research_brief.md`
  - `reports/ai/next_actions.md`
- searched patterns:
  - `create_order`, `create_market_order`, `create_limit_order`
  - `private_post`, `fapiPrivate`
  - `place_order`, `send_order`, `submit_order`, `new_order`, `live_order`
  - `ccxt.`, `binance.`, `exchange.`
- matches: none
