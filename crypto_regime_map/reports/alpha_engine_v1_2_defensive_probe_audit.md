# Alpha Engine v1.2 Defensive Probe Audit

- 생성 시각: 2026-06-22 06:43 UTC
- 분석 범위: 2020-01-01 ~ 2025-12-31 UTC
- 원칙: 기존 V0/V1 전략 소스와 paper/probe state는 변경하지 않고, reports 산출물만 생성했다.
- score 85는 기존 0~10 alpha_score 스케일에서 8.5 이상으로 환산했다.

## Final Verdict

- 판정: **FAIL**
- 사유: cost_2x_advantage_lost;defensive_pf_lte_1
- 비용 2배 추가 수익: -31.56%
- 추가 MDD 악화폭: 1.19%
- defensive PF: 0.91
- lookahead/data leakage 의심: False

## Defensive Entry Quality

| Metric | Value |
|---|---:|
| defensive_trade_count | 862.00 |
| defensive_win_rate_pct | 26.91% |
| defensive_profit_factor | 0.91 |
| defensive_avg_gain_pct | 0.28% |
| defensive_avg_loss_pct | -0.10% |
| defensive_average_r | 0.00 |
| defensive_max_consecutive_losses | 33.00 |
| defensive_expectancy_pct | 0.00% |
| defensive_median_trade_return_pct | -0.13% |
| defensive_best_trade_symbol | ETH |
| defensive_best_trade_return_pct | 3.49% |
| defensive_worst_trade_symbol | XRP |
| defensive_worst_trade_return_pct | -0.13% |

## Symbol Concentration

| symbol | trade_count | total_pnl | win_rate_pct | profit_factor | average_r | mdd_contribution_pct | additional_return_contribution_pct |
|---|---|---|---|---|---|---|---|
| SOL | 96.00 | 0.14 | 30.21% | 1.47 | 0.28 | -7.72% | 15.72% |
| ETH | 133.00 | 0.12 | 24.81% | 1.27 | 0.31 | -13.27% | 12.88% |
| BTC | 48.00 | 0.06 | 29.17% | 1.40 | 0.26 | -4.44% | 6.46% |
| AVAX | 104.00 | -0.01 | 25.96% | 0.98 | 0.02 | -12.23% | -0.87% |
| LINK | 104.00 | -0.04 | 31.73% | 0.86 | -0.01 | -8.95% | -4.25% |
| ADA | 121.00 | -0.07 | 27.27% | 0.79 | -0.09 | -8.65% | -7.38% |
| TON | 24.00 | -0.07 | 25.00% | 0.41 | -0.37 | -9.85% | -7.78% |
| BNB | 130.00 | -0.14 | 24.62% | 0.66 | -0.21 | -14.73% | -15.11% |
| XRP | 102.00 | -0.25 | 24.51% | 0.38 | -0.33 | -25.31% | -27.34% |

- top 2 profit symbol share: 81.58%
- top 2 loss symbol share: 67.68%

## Period / Market State

| period | market_state | v0_return_pct | v1_return_pct | v1_minus_v0_pct | v0_mdd_pct | v1_mdd_pct | defensive_probe_trade_count | defensive_probe_pnl |
|---|---|---|---|---|---|---|---|---|
| 2020-01 | rebound | 0.00% | 1.01% | 1.01% | 0.00% | -1.47% | 34.00 | 0.01 |
| 2020-02 | downtrend | 5.92% | 6.46% | 0.54% | -3.59% | -3.20% | 8.00 | 0.00 |
| 2020-03 | downtrend | -2.01% | -2.36% | -0.35% | -3.02% | -3.40% | 4.00 | -0.00 |
| 2020-04 | rebound | 0.00% | 2.64% | 2.64% | 0.00% | -0.95% | 20.00 | 0.02 |
| 2020-05 | rebound | 0.00% | 0.97% | 0.97% | 0.00% | -1.53% | 25.00 | 0.01 |
| 2020-06 | range | -0.90% | -1.09% | -0.19% | -1.03% | -2.18% | 19.00 | -0.01 |
| 2020-07 | rebound | 32.21% | 32.22% | 0.00% | -4.47% | -4.48% | 0.00 | 0.00 |
| 2020-08 | range | 9.44% | 9.44% | 0.00% | -9.80% | -9.80% | 0.00 | 0.00 |
| 2020-09 | downtrend | -0.18% | -0.78% | -0.60% | -3.34% | -3.90% | 14.00 | -0.02 |
| 2020-10 | rebound | 10.89% | 10.88% | -0.00% | -5.59% | -5.59% | 0.00 | 0.00 |
| 2020-11 | rebound | 20.11% | 20.11% | -0.00% | -6.45% | -6.45% | 0.00 | 0.00 |
| 2020-12 | rebound | 5.77% | 5.77% | -0.00% | -6.75% | -6.75% | 0.00 | 0.00 |
| 2021-01 | rebound | 4.68% | 4.68% | -0.00% | -7.01% | -7.01% | 0.00 | 0.00 |
| 2021-02 | rebound | 44.19% | 44.19% | -0.00% | -5.54% | -5.54% | 0.00 | 0.00 |
| 2021-03 | rebound | -0.30% | -0.30% | 0.00% | -4.12% | -4.12% | 0.00 | 0.00 |
| 2021-04 | range | 5.48% | 5.48% | -0.00% | -2.65% | -2.65% | 0.00 | 0.00 |
| 2021-05 | downtrend | 3.11% | 3.11% | -0.00% | -3.10% | -3.10% | 0.00 | 0.00 |
| 2021-06 | downtrend | 0.00% | -2.12% | -2.12% | 0.00% | -2.16% | 26.00 | -0.09 |

### Market State Aggregate

| market_state | period_count | avg_v1_minus_v0_pct | defensive_probe_trade_count | defensive_probe_pnl |
|---|---|---|---|---|
| downtrend | 22.00 | -0.20% | 248.00 | -0.50 |
| range | 16.00 | -0.21% | 203.00 | -0.28 |
| rebound | 34.00 | 0.72% | 411.00 | 0.53 |
| unknown | 1.00 | 0.03% | 0.00 | 0.00 |

## Cost Stress

| case | v0_total_return_pct | v1_total_return_pct | v1_additional_return_pct | v0_mdd_pct | v1_mdd_pct | v1_additional_mdd_pct | v1_profit_factor | v1_trade_count |
|---|---|---|---|---|---|---|---|---|
| base | 414.55% | 504.77% | 90.22% | -28.14% | -29.32% | 1.19% | 1.06 | 1779.00 |
| fee_2x | 279.61% | 312.08% | 32.47% | -35.67% | -37.80% | 2.13% | 1.03 | 1779.00 |
| fee_3x | 178.84% | 178.84% | -0.01% | -42.60% | -45.53% | 2.93% | 1.01 | 1779.00 |
| slippage_2x | 78.75% | 50.20% | -28.55% | -47.38% | -51.76% | 4.38% | 0.86 | 1914.00 |
| slippage_3x | -50.12% | -72.22% | -22.10% | -73.69% | -84.65% | 10.96% | 0.71 | 2102.00 |
| fee_2x_slippage_2x | 30.18% | -1.39% | -31.56% | -53.74% | -61.41% | 7.67% | 0.85 | 1914.00 |
| fee_3x_slippage_3x | -78.90% | -94.03% | -15.13% | -86.84% | -96.08% | 9.24% | 0.70 | 2102.00 |

## Parameter Sensitivity

| variant | total_return_pct | mdd_pct | profit_factor | trade_count | defensive_trade_count | average_r | max_consecutive_losses | additional_return_vs_v0_pct | additional_mdd_vs_v0_pct |
|---|---|---|---|---|---|---|---|---|---|
| V1_85_25 | 504.77% | -29.32% | 1.06 | 1779.00 | 862.00 | 0.11 | 33.00 | 90.22% | 1.19% |
| V1_90_25 | 490.32% | -29.35% | 1.06 | 1650.00 | 733.00 | 0.11 | 32.00 | 75.77% | 1.21% |
| V1_90_15 | 458.73% | -29.06% | 1.08 | 1650.00 | 733.00 | 0.11 | 32.00 | 44.18% | 0.92% |
| V1_85_15 | 467.23% | -29.04% | 1.08 | 1779.00 | 862.00 | 0.11 | 33.00 | 52.68% | 0.90% |
| V1_90_25_cooldown | 484.63% | -28.66% | 1.06 | 1622.00 | 704.00 | 0.11 | 36.00 | 70.08% | 0.53% |
| V1_85_25_cooldown | 525.54% | -27.93% | 1.07 | 1715.00 | 797.00 | 0.13 | 37.00 | 110.98% | 0.00% |

## Lookahead / Data Leakage Check

- 진입 판단은 4H 신호 close timestamp 이후 `next_open` 실행 timestamp에서 이루어지는 기존 경로를 재사용했다.
- `lookahead_pass` 실패 수: 0
- V0/V1은 스크립트에서 같은 `AlphaData` 객체와 같은 funding index를 공유한다.
- `--use-cache` 사용 시 raw OHLCV/funding 캐시를 한 번 로드한 뒤 모든 변형에 동일하게 주입한다.
- V1은 V0보다 유리한 별도 데이터 경로를 쓰지 않는다.

## CSV Outputs

- `alpha_engine_v1_2_defensive_probe_audit.csv`
- `alpha_engine_v1_2_defensive_probe_audit_params.csv`
- `alpha_engine_v1_2_defensive_probe_audit_costs.csv`
- `alpha_engine_v1_2_defensive_probe_audit_symbols.csv`
- `alpha_engine_v1_2_defensive_probe_audit_periods.csv`
