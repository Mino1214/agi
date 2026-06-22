# Xeon Research Setup

이 문서는 Xeon 연구 서버에서 `crypto_regime_map`을 개발, 백테스트, ML regime 실험용으로 쓰기 위한 기준이다. Mac mini 운영 코드와 paper state는 공유하거나 덮어쓰지 않는다.

## Clone And Branch

Xeon은 `research/*` 브랜치에서만 작업한다.

```bash
git clone <repo-url> AGI
cd AGI
git fetch origin
git switch research/xeon-setup
git pull --ff-only origin research/xeon-setup
```

새 실험은 목적에 맞는 브랜치에서 시작한다.

```bash
git switch research/ml-regime
git switch research/4h-regime
git switch research/leverage-test
```

Xeon에서 `main`을 직접 수정하지 않는다. 운영 반영 후보는 `research/*`에서 검증한 뒤 `dev`로 PR 또는 merge 후보를 만든다.

## Python Environment

기본 실행 환경:

```bash
cd crypto_regime_map
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

ML regime 연구가 필요할 때만 optional research 의존성을 설치한다.

```bash
python3 -m pip install -r requirements-research.txt
```

`requirements-research.txt`는 `pandas`, `numpy`, `scikit-learn`, `lightgbm`, `xgboost`, `joblib`, `matplotlib`을 포함한다.

## Local Data Rules

Xeon의 데이터와 산출물은 로컬 연구 산출물이다.

- Mac mini의 `data/paper*/` state를 복사해 덮어쓰지 않는다.
- paper 실험은 `--state-dir data/research_*`처럼 별도 state dir을 쓴다.
- `data/raw/*.json` market-data cache는 로컬에 두고 Git에 올리지 않는다.
- `reports/*.md`는 중요한 결론이면 Git 추적 가능하다.
- `reports/*.csv`, `data/**/*.csv`, cache, 모델 산출물은 기본적으로 Git에 올리지 않는다.
- API key, exchange key, secret json/yaml은 repo 파일에 두지 않는다.

## Allowed Work

Xeon에서 허용되는 작업:

- 백테스트
- ML 학습과 feature/regime 실험
- 리포트 생성
- research-only 의존성 추가
- 운영 반영 전 후보 검증

Xeon에서 금지되는 작업:

- live order 실행
- API 주문 로직 수정
- `main` 직접 수정
- 운영 dashboard 상시 실행
- Mac mini paper state와 연구 state 혼용

## Verification Commands

기본 테스트:

```bash
cd crypto_regime_map
python3 -m pytest
python3 -m py_compile src/*.py scripts/*.py tests/*.py
```

paper run-once 검증은 운영 state와 분리해서 실행한다.

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --state-dir data/research_paper_run_once
```

4H regime 리포트:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_4h_regime_report.py
python3 scripts/alpha_engine_v1_2_4h_regime_audit.py
```

leverage/risk 리포트:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_leverage_sensitivity_report.py
python3 scripts/alpha_engine_v1_execution_robustness_report.py
python3 scripts/alpha_engine_v1_futures_execution_audit_report.py
```

health 확인:

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_health_monitor.py check
python3 scripts/alpha_engine_v1_2_health_monitor.py report
```

## Merge Candidate Rule

`research/*` 결과가 아래 기준을 통과할 때만 `dev` 후보가 된다.

- `pytest` 통과
- `py_compile` 통과
- 필요한 백테스트/리포트 산출
- `git status --short`에서 의도한 변경만 남음
- secret, runtime state, report CSV, model artifact가 staged/tracked되지 않음

`dev`에서 다시 검증한 뒤 운영자가 승인한 변경만 `main`으로 보낸다. Mac mini는 승인된 `main`만 `pull --ff-only`로 받는다.
