# AI Researcher Daily Brief

- generated_at: 2026-06-23T12:55:07Z
- indexed_reports: 16
- role: read-only researcher/auditor

## 1. 현재 생존 전략

- V0 1D regime는 현재 생존 기준선이다.
- 새 후보는 V0를 대체하지 않고, 독립 검증과 shadow 축적을 통과할 때까지 연구 상태로 둔다.
- 인덱스에서 PASS 판정 report는 감지되지 않았다.

## 2. 실패한 연구 요약

- ML Regime: FAIL. 운영 반영 대상이 아니다.
- 4H Regime: robustness FAIL. V0 대체 후보가 아니다.
- Diversified/Core-Satellite: FAIL. 운영 반영 대상이 아니다.
- 4h_regime: V4H Core/Satellite Audit (../agi-4h-regime/crypto_regime_map/reports/research/v4h_core_satellite_report.md) - | Variant | Group | Status | Reasons | Return | CAGR | MDD | Calmar | Trades | Sat Alloc | SOL+BNB Impact | |---|---|---|---|---|---|---|---|---|---|---| | SAT_SOL_BNB_REC92_25_...
- 4h_regime: V4H Diversified Robustness Report (../agi-4h-regime/crypto_regime_map/reports/research/v4h_diversified_robustness_report.md) - - Read-only audit/report only. Strategy modules, paper engine, live order logic, main checkout/merge, commit, and push were not touched. - Existing `V4H_STRICT_REC92_25` robustn...
- 4h_regime: V4H Symbol-Specific Recovery Control Audit (../agi-4h-regime/crypto_regime_map/reports/research/v4h_symbol_specific_recovery_report.md) - - Read-only audit/report only. Existing strategy, paper engine, live order logic, main checkout/merge, commit, and push were not touched. - Existing `V4H_STRICT_REC92_25` robust...
- ml_regime: ML Regime PoC Report (../agi-ml-regime/crypto_regime_map/reports/research/ml_regime_poc_report.md) - - Status: FAIL - Best model: Logistic Regression. - Recovery/uptrend precision delta vs baseline: 2.48%. - Shock recall: 2.90%. - Core objective is not above baseline or shock r...
- ml_regime: ML Regime v2 Report (../agi-ml-regime/crypto_regime_map/reports/research/ml_regime_v2_report.md) - - v0 verdict: FAIL - recovery/uptrend precision: 38.59% - baseline: 36.11% - shock recall: 2.90% - macro F1: 16.00%
- ml_regime: ML Regime v3 Hybrid Backtest Report (../agi-ml-regime/crypto_regime_map/reports/research/ml_regime_v3_hybrid_backtest_report.md) - - Status: FAIL - Best base hybrid: ML_OPP_SIZE_ADJUST total return -4.20%, Calmar -0.1168. - V0 base: total return 6.61%, MDD -26.94%, Calmar 0.1192. - 2x fee+slippage delta for...

## 3. WATCH 상태 연구 요약

- leverage는 effective exposure <= 1.0 조건만 후보로 남긴다.
- WATCH 후보는 실거래가 아니라 추가 리포트와 shadow 데이터로만 평가한다.
- 인덱스에서 WATCH report는 감지되지 않았다.
- leverage: V0 Integer Leverage Sensitivity Audit (../agi-leverage-test/crypto_regime_map/reports/research/v0_integer_leverage_sensitivity_report.md) - Maximum PASS candidate: **3x / size 25%** (effective exposure 0.75x), MDD -21.58%, Calmar 1.08, worst month -6.17%. Maximum combination with cost 2x + slippage 2x account surviv...
- leverage: V0 Leverage Sanity Check and Risk Policy (../agi-leverage-test/crypto_regime_map/reports/research/v0_leverage_sanity_and_risk_policy_report.md) - - Live default remains **V0 1x** spot/equivalent exposure. It is WATCH rather than PASS only because cost 2x + slippage 2x pushes MDD to -53.74%. - Futures paper candidates: **3...

## 4. Futures Shadow 상태

- 후보: 3x size25, 2x size50.
- 둘 다 production/live 주문 후보가 아니라 shadow 관찰 후보이다.
- futures_shadow: V0 Futures Paper Shadow Daily Run (../agi-futures-shadow/crypto_regime_map/reports/research/v0_futures_shadow_daily_report.md) - - V0 current: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/paper_alpha_engine_v1_2` - futures 3x size25: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_...
- futures_shadow: V0 Futures Paper Shadow Summary (../agi-futures-shadow/crypto_regime_map/reports/research/v0_futures_shadow_first_run.md) - - V0 current: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/paper_alpha_engine_v1_2` - futures 3x size25: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_...
- futures_shadow: V0 Futures Paper Shadow Setup Report (../agi-futures-shadow/crypto_regime_map/reports/research/v0_futures_shadow_setup_report.md) - Prepare paper-only futures shadow execution for V0 baseline candidates without changing the default V0 paper path, live order logic, or existing research outputs.

## Mac mini V1.2 Paper Runtime

- status: available
- source: /Users/myno/agi-lab/runtime/macmini-paper/v1_2_paper_runtime_summary.json
- timestamp: 2026-06-23T12:15:55+00:00
- equity: 1.0
- daily return: 0.0%
- open positions: 0
- orders/trades count: 0 / 0
- regime: defensive
- action_bias: reduce_risk
- can_enter: false
- entry_block_reason: regime_reduce_risk
- health_status: warning
- warnings_count: 17
- last updated: 2026-06-23 12:15 UTC
- xeon_shadow_runtime: Xeon shadow runtime summary not available
- interpretation: defensive/reduce_risk 상태에서 can_enter=false, 포지션/주문/체결 0건이므로 신규 진입 없음은 전략상 정상 대기 상태이다.

## 5. 오늘 확인할 항목

- sibling research worktree에 새 markdown report가 생겼는지 확인한다.
- V0 1D regime 기준선이 문서와 dashboard에 동일하게 표시되는지 확인한다.
- futures shadow 후보의 sample 수, drawdown, liquidation-touch 여부를 report로만 확인한다.
- data/cache/state/log/csv 산출물이 Git 후보에 들어오지 않는지 확인한다.

## 6. 다음 액션

- 운영 안정성 확인을 최우선으로 둔다.
- V0 유지와 shadow 데이터 축적을 새 전략 연구보다 앞에 둔다.
- dashboard에는 현재 기준선, 실패 후보, shadow 후보를 분리해서 표시한다.
- execution safety 점검은 read-only 코드와 주문 API 미사용 확인 중심으로 진행한다.

## 7. 금지해야 할 액션

- AI Researcher가 직접 주문하거나 paper/live engine을 실행하지 않는다.
- Mac mini 운영 state에 접근하거나 수정하지 않는다.
- Xeon shadow state를 수정하지 않는다.
- main 브랜치를 직접 수정하지 않는다.
- data/cache/state/log/csv와 report_index.jsonl을 commit하지 않는다.

## Current Conclusions

- V0 1D regime = 현재 생존 기준선
- ML Regime = FAIL
- 4H Regime = robustness FAIL
- Diversified/Core-Satellite = FAIL
- leverage = effective exposure <= 1.0만 후보
- futures shadow 후보 = 3x size25, 2x size50
- AI는 직접 매매하지 않고 Researcher/Auditor 역할
