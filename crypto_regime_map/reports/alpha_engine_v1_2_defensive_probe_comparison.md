# Alpha Engine v1.2 Defensive Probe 비교 리포트

- 생성 시각: 2026-06-22 06:45 UTC
- 기간: 2020-01-01 ~ 2025-12-31 UTC
- 공통 비용: taker-only 0.05%, slippage 0.2%, actual funding.
- V0: 기존 v1.2 candidate 조건(DOGE 제외, alpha_score top 20%, liquidation buffer).
- V1: V0 유지 + defensive에서 score 85점 환산 이상, relative strength 통과, BTC panic 아님일 때 1개만 25% 사이즈 probe.

## Summary

| Variant | Return | MDD | Win | PF | Trades | Def entries | Def return | Def loss | Max losses | Avg R | Extra return | Extra MDD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 Candidate v1.2 | 414.55% | -28.14% | 34.34% | 1.11 | 929.00 | 0.00 | 0.00% | 0.00% | 19.00 | 0.21 | 0.00% | 0.00% |
| V1 defensive_probe | 504.77% | -29.32% | 30.80% | 1.06 | 1779.00 | 862.00 | -24.96% | 73.09% | 33.00 | 0.11 | 90.22% | -1.19% |

## Probe Log Summary

| Metric | Value |
|---|---:|
| evaluated defensive candidates | 13652 |
| probe entries allowed | 3050 |
| reasons | btc_panic_condition:240, passed:3050, probe_max_one_per_batch:2524, relative_strength_failed:690, score_below_85:7148 |

## 산출물

- `alpha_engine_v1_2_defensive_probe_comparison.md`
- `alpha_engine_v1_2_defensive_probe_summary.csv`
- `alpha_engine_v1_2_defensive_probe_log.csv`
