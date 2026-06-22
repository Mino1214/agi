# AGI Trading Workspace

Mac mini 운영 서버와 Xeon 연구 서버가 같은 repo를 쓰되, 브랜치와 실행 범위를 분리한다. 상세 정책은 [docs/branch_strategy.md](docs/branch_strategy.md), Xeon 초기 세팅은 [docs/xeon_research_setup.md](docs/xeon_research_setup.md)를 기준으로 한다.

## Repository Layout

| Path | Role |
| --- | --- |
| `crypto_regime_map/` | Regime dashboard, Alpha Engine paper run, research reports |
| `docs/` | 운영/연구 정책 문서 |
| `whitepaper.md` | 상위 설계 문서 |

## Branch Roles

| Branch | Machine | Run scope |
| --- | --- | --- |
| `main` | Mac mini | 안정 운영 버전. paper, dashboard, health만 실행 |
| `dev` | 통합 검증 | `research/*` 후보를 운영 반영 전에 검증 |
| `research/xeon-setup` | Xeon | 연구 서버 초기 세팅과 실행 확인 |
| `research/ml-regime` | Xeon | ML/regime research and training |
| `research/4h-regime` | Xeon | 4H regime experiments, backtests, reports |
| `research/leverage-test` | Xeon | leverage/risk replay reports |

Mac mini는 `main`만 pull하고 실험 브랜치를 checkout하지 않는다.

```bash
git switch main
git pull --ff-only origin main
```

Xeon은 `research/*` 브랜치에서만 개발, 백테스트, ML 학습, 리포트 생성을 한다.

```bash
git fetch origin
git switch research/xeon-setup
git pull --ff-only origin research/xeon-setup
```

연구 결과가 통과하면 `dev`로 PR 또는 merge 후보가 되고, `dev` 검증 후에만 `main` 후보가 된다. Xeon에서 `main`을 직접 수정하지 않는다.

## Crypto Regime Map Operations

Dashboard:

```bash
cd crypto_regime_map
python3 src/main.py --host 127.0.0.1 --port 8788
```

Alpha Engine paper:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once --use-cache
python3 scripts/alpha_engine_v1_2_paper_engine.py loop --use-cache --sleep 3600
python3 scripts/alpha_engine_v1_2_paper_engine.py report
```

Health:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_health_monitor.py check
python3 scripts/alpha_engine_v1_2_health_monitor.py report
```

Paper control panel:

```bash
cd crypto_regime_map
scripts/manage_paper_control_panel.sh start
scripts/manage_paper_control_panel.sh status
scripts/manage_paper_control_panel.sh stop
```

Direct control panel run:

```bash
cd crypto_regime_map
python3 scripts/paper_control_panel.py --host 127.0.0.1 --port 8790 --use-cache
```

## Research Commands

4H regime:

```bash
git switch research/4h-regime
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_4h_regime_report.py
python3 scripts/alpha_engine_v1_2_4h_regime_audit.py
```

ML regime dependencies:

```bash
git switch research/ml-regime
cd crypto_regime_map
python3 -m pip install -r requirements-research.txt
```

Leverage test:

```bash
git switch research/leverage-test
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_leverage_sensitivity_report.py
python3 scripts/alpha_engine_v1_execution_robustness_report.py
python3 scripts/alpha_engine_v1_futures_execution_audit_report.py
```

Paper run-once on Xeon must use a research state dir:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --state-dir data/research_paper_run_once
```

## Verification

```bash
cd crypto_regime_map
python3 -m pytest
python3 -m py_compile src/*.py scripts/*.py tests/*.py
```

Do not run Mac mini paper checks against research branches. Do not commit runtime state, logs, report CSVs, raw/cache data, secrets, or large model artifacts.

## Git Hygiene

- Keep API keys, exchange keys, passwords, and tokens in environment variables or local `.env` files.
- Keep `.env`, secret json/yaml, key files, runtime state, logs, pid files, market-data caches, SQLite/db files, dashboard HTML, and generated CSVs out of Git.
- Keep important markdown summaries in `reports/**/*.md` trackable.
- Keep generated report tables in `reports/**/*.csv` untracked by default.
- Keep large model artifacts such as `*.pkl`, `*.joblib`, `*.parquet`, `*.onnx`, `*.pt`, and `*.ckpt` untracked.

If an ignored file is already tracked, remove it from the index only:

```bash
git rm --cached <path>
```

The local file remains on disk. If a real secret reached a remote, rotate that credential.
