# AI Researcher Next Actions

- generated_at: 2026-06-23T13:44:34Z
- indexed_reports: 16
- daily_brief_available: yes
- detected_fail_reports: 6
- detected_watch_reports: 0
- futures_shadow_reports: 3
- macmini_runtime_available: yes
- macmini_runtime_regime: defensive
- macmini_runtime_warnings_count: 16

## Priority 1. 운영 안정성

- Git 후보에 data/cache/state/log/csv와 report_index.jsonl이 없는지 확인한다.
- AI Researcher 변경이 주문 API, paper/live engine loop, 운영 state 경로를 건드리지 않았는지 확인한다.
- daily brief와 next actions 산출물이 재현 가능하게 생성되는지 확인한다.
- V1.2 paper는 defensive/reduce_risk 상태라 신규 진입 없음이 정상이다.
- warnings_count가 0보다 크므로 warning detail expansion이 필요하다.
- Xeon shadow runtime summary가 아직 없어 V1.2 비교는 shadow sync 이후로 둔다.

## Priority 2. V0 유지

- V0 1D regime를 현재 생존 기준선으로 유지한다.
- ML Regime, 4H Regime, Diversified/Core-Satellite 실패 결론을 V0 대체 근거로 쓰지 않는다.
- dashboard와 문서에서 V0 baseline과 연구 후보를 분리한다.

## Priority 3. Shadow 데이터 축적

- futures shadow 후보는 3x size25와 2x size50만 관찰한다.
- sample 수, MDD, liquidation-touch, margin-call 여부를 report로만 누적한다.
- shadow state는 수정하지 않고, 이미 생성된 markdown report만 인덱싱한다.
- shadow와 V1.2 비교는 runtime shadow sync 완료 후 강화한다.

## Priority 4. Dashboard 개선

- 운영 화면에 baseline, failed research, watch research, futures shadow를 별도 섹션으로 노출한다.
- 사람 검토용 링크는 markdown report 경로 중심으로 둔다.
- AI 산출물은 Researcher/Auditor badge를 붙여 주문 권한과 분리한다.

## Priority 5. Execution safety

- 새 코드에서 주문 생성, 주문 전송, exchange client 호출 패턴이 추가되지 않았는지 확인한다.
- state/log/cache/csv 생성물은 ignored 상태를 유지한다.
- Mac mini 운영 state와 Xeon shadow state를 읽거나 쓰는 CLI 옵션을 만들지 않는다.

## Priority 6. 새 전략 연구 후순위

- 신규 alpha나 regime 연구는 운영 안정성, V0 유지, shadow 축적 이후로 미룬다.
- 새 전략 연구보다 shadow 데이터 축적을 우선한다.
- 새 후보가 필요하면 먼저 markdown report와 index row로만 들어오게 한다.
- AI Researcher는 후보 제안보다 실패 근거 정리와 다음 검증 항목 정리에 집중한다.

## Do Not Do

- paper/live engine 실행 금지.
- 실거래 주문 로직 수정 금지.
- Mac mini 운영 state 접근 금지.
- Xeon shadow state 수정 금지.
- main 직접 수정 금지.
