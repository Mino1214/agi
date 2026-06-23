# AI Researcher

AI Researcher v0는 M3 Pro에서 실행하는 read-only 연구 정리 계층이다. 실거래, paper engine, 운영 state, shadow state를 직접 제어하지 않고 여러 worktree에 흩어진 markdown report를 읽어 인덱스와 요약 리포트를 만든다.

## M3 Pro Role

M3 Pro는 연구 결과를 모으는 감사자 역할을 맡는다.

- sibling worktree의 research report와 현재 repo 문서를 읽는다.
- 실패한 연구, 관찰 후보, 현재 기준선을 분리해서 daily brief를 만든다.
- 다음 액션을 운영 안정성, V0 유지, shadow 축적 순서로 정렬한다.
- 나중에 local LLM을 붙일 때도 주문 권한 없이 report summarizer로만 동작한다.

## System Layout

| Machine | Branch/Worktree | Role |
| --- | --- | --- |
| Mac mini | `main` | 운영 서버. 승인된 paper/dashboard/health 범위만 실행 |
| Xeon | `research/*` worktree | 백테스트, ML, 4H, leverage, futures shadow 연구 |
| M3 Pro | `feature/ai-researcher` | markdown report index, daily brief, next action 생성 |

M3 Pro는 Mac mini 운영 state를 읽거나 수정하지 않는다. Xeon shadow state도 수정하지 않고, 이미 생성된 markdown report만 읽는다.

## What It Does

- `../agi-ml-regime/crypto_regime_map/reports/research/*.md` 읽기
- `../agi-4h-regime/crypto_regime_map/reports/research/*.md` 읽기
- `../agi-leverage-test/crypto_regime_map/reports/research/*.md` 읽기
- `../agi-futures-shadow/crypto_regime_map/reports/research/*.md` 읽기
- 현재 repo의 `docs/*.md` 읽기
- local JSONL index 생성
- daily research brief 생성
- prioritized next actions 생성

## What It Does Not Do

- 실거래 주문을 만들거나 전송하지 않는다.
- paper/live engine을 실행하지 않는다.
- Mac mini 운영 state에 접근하지 않는다.
- Xeon shadow state를 수정하지 않는다.
- `main` 브랜치를 직접 수정하지 않는다.
- `data/cache/state/log/csv` 산출물을 commit 대상으로 만들지 않는다.

## Commands

```bash
cd ~/agi-lab/agi
python3 crypto_regime_map/scripts/ai_researcher_index_reports.py
python3 crypto_regime_map/scripts/ai_researcher_daily_brief.py
python3 crypto_regime_map/scripts/ai_researcher_next_actions.py
```

검증:

```bash
python3 -m pytest crypto_regime_map/tests -q
python3 -m py_compile crypto_regime_map/src/*.py crypto_regime_map/scripts/*.py crypto_regime_map/tests/*.py
git diff --check
git status --short
```

## Outputs

| Output | Commit policy |
| --- | --- |
| `crypto_regime_map/data/ai_researcher/report_index.jsonl` | local only, ignored |
| `crypto_regime_map/reports/ai/daily_research_brief.md` | markdown report |
| `crypto_regime_map/reports/ai/next_actions.md` | markdown report |

`data/ai_researcher/`는 `.gitignore` 대상이다. report index는 재생성 가능한 local cache로 취급한다.

## Current Research Conclusions

- V0 1D regime is the current survival baseline.
- ML Regime failed and is not an operations candidate.
- 4H Regime failed robustness checks.
- Diversified/Core-Satellite failed.
- Leverage candidates are limited to effective exposure at or below 1.0.
- Futures shadow candidates are 3x size25 and 2x size50.
- AI remains a Researcher/Auditor and does not trade directly.

## Future Ollama/LLM Direction

Ollama or another local LLM can be connected after v0 by feeding it only the generated JSONL index and markdown reports. The LLM should return summaries, contradictions, missing evidence, and proposed checklist items. It should not receive exchange credentials, live order APIs, paper state write paths, or shell commands that can start engines.
