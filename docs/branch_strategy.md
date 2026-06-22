# Branch Strategy

이 repo는 하나만 유지하고, 서버 역할은 브랜치와 실행 범위로 분리한다.

## Branches

| Branch | Machine | Purpose |
| --- | --- | --- |
| `main` | Mac mini 운영 서버 | 안정 운영 버전. paper, dashboard, health만 실행 |
| `dev` | 통합 검증 | `research/*` 후보를 모아 운영 반영 전 검증 |
| `research/xeon-setup` | Xeon 연구 서버 | Xeon 초기 세팅, 의존성, 로컬 실행 확인 |
| `research/ml-regime` | Xeon 연구 서버 | ML regime 후보 학습과 검증 |
| `research/4h-regime` | Xeon 연구 서버 | 4H regime 실험, 백테스트, 리포트 생성 |
| `research/leverage-test` | Xeon 연구 서버 | leverage sensitivity와 리스크 실험 |

브랜치는 한 번만 만들고 원격에 올린 뒤 계속 재사용한다.

```bash
git switch main
git pull --ff-only origin main
git switch -c dev
git switch main
git switch -c research/xeon-setup
git switch main
git switch -c research/ml-regime
git switch main
git switch -c research/4h-regime
git switch main
git switch -c research/leverage-test
```

## Promotion Flow

연구 서버의 결과는 `research/*`에서 끝까지 검증한다. 모델이나 전략 후보가 통과하면 `dev`로 PR 또는 merge 후보가 되고, `dev`에서 테스트와 리포트 검토를 통과한 변경만 `main` 후보가 된다.

`main`은 Mac mini 운영 안정 버전이다. Xeon에서 `main`을 직접 수정하지 않고, Mac mini에서도 실험 브랜치를 checkout하지 않는다.

## Mac Mini Operations

Mac mini는 운영 기준 브랜치인 `main`만 받는다.

```bash
git switch main
git pull --ff-only origin main
```

운영 서버에서 허용되는 범위:

- paper engine
- dashboard/control panel
- health monitor
- 명시적으로 승인된 live 관련 실행 경로

운영 서버에서 금지되는 범위:

- `research/*` 또는 `dev` checkout
- 연구용 백테스트
- ML 학습
- 대량 리포트 생성
- Xeon 연구 state를 Mac mini paper state 위에 덮어쓰기

### Crypto Regime Map

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once --use-cache
python3 scripts/alpha_engine_v1_2_paper_engine.py loop --use-cache --sleep 3600
python3 scripts/alpha_engine_v1_2_paper_engine.py report
python3 scripts/alpha_engine_v1_2_health_monitor.py check
python3 scripts/alpha_engine_v1_2_health_monitor.py report
python3 src/main.py --host 127.0.0.1 --port 8788
```

Paper control panel:

```bash
cd crypto_regime_map
scripts/manage_paper_control_panel.sh start
scripts/manage_paper_control_panel.sh status
scripts/manage_paper_control_panel.sh stop
```

직접 control panel을 띄울 때:

```bash
cd crypto_regime_map
python3 scripts/paper_control_panel.py --host 127.0.0.1 --port 8790 --use-cache
```

## Xeon Research

Xeon 연구 서버는 `research/*` 브랜치에서만 개발, 백테스트, ML 학습, 리포트 생성을 한다.

```bash
git fetch origin
git switch research/xeon-setup
git pull --ff-only origin research/xeon-setup
```

허용 범위:

- backtest
- ML training/research
- report generation
- research-only requirements 설치

금지 범위:

- live order
- API 주문 로직 수정
- 운영 dashboard 상시 실행
- Mac mini 운영 state 공유 또는 덮어쓰기
- `main` 직접 수정

### `research/4h-regime`

```bash
git switch research/4h-regime
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_4h_regime_report.py
python3 scripts/alpha_engine_v1_2_4h_regime_audit.py
```

4H regime paper variant를 일회성으로 검증할 때는 Xeon의 별도 state dir을 지정한다.

```bash
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --short-regime-4h \
  --use-cache \
  --state-dir data/research_paper_4h
```

### `research/ml-regime`

```bash
git switch research/ml-regime
cd crypto_regime_map
python3 -m pip install -r requirements-research.txt
```

ML 후보가 생기면 결과 리포트는 `reports/*.md`로 남기고, 대용량 모델 산출물과 CSV는 Git에 올리지 않는다.

### `research/leverage-test`

```bash
git switch research/leverage-test
cd crypto_regime_map
python3 scripts/alpha_engine_v1_2_leverage_sensitivity_report.py
python3 scripts/alpha_engine_v1_execution_robustness_report.py
python3 scripts/alpha_engine_v1_futures_execution_audit_report.py
```

## Test And Report Commands

```bash
cd crypto_regime_map
python3 -m pytest
python3 -m py_compile src/*.py scripts/*.py tests/*.py
python3 scripts/alpha_engine_v1_2_paper_engine.py run-once --use-cache
python3 scripts/alpha_engine_v1_2_4h_regime_report.py
python3 scripts/alpha_engine_v1_2_4h_regime_audit.py
python3 scripts/alpha_engine_v1_2_leverage_sensitivity_report.py
```

Mac mini에서는 paper `run-once`가 운영 state를 쓸 수 있으므로 운영 담당자가 직접 실행한다. Xeon에서는 `--state-dir data/research_*` 형태로 운영 state와 분리한다.

## Git Hygiene

민감정보와 실행 산출물은 Git에 올리지 않는다.

- `.env`, `.env.*`, API key, exchange key, secret/private key 파일 제외
- secret json/yaml, credential json/yaml 제외
- `data/cache/` 제외
- `data/raw/*.json` market-data cache 제외
- `data/paper*/`, `data/*state*` 제외
- logs, pid, sqlite/db, dashboard HTML 제외
- `__pycache__`, `.pytest_cache` 제외
- `data/**/*.csv`, `reports/**/*.csv` 제외
- 중요한 markdown 요약 리포트인 `reports/**/*.md`는 추적 가능
- 대용량 모델 산출물(`*.pkl`, `*.joblib`, `*.parquet`, `*.onnx`, `*.pt`, `*.ckpt` 등) 제외

이미 Git에 올라간 제외 대상은 로컬 파일을 지우지 않고 인덱스에서만 제거한다.

```bash
git rm --cached <path>
```

민감값이 한 번이라도 원격에 올라간 경우에는 파일 제거와 별개로 해당 key를 폐기하고 재발급한다.
