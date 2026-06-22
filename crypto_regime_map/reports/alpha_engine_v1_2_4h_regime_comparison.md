# Alpha Engine v1.2 4H Regime 비교 리포트

- V0_1D_regime: 기존 1D trade_regime gate + v1.2 조건(DOGE 제외, alpha_score top 20%, liquidation buffer).
- V4H 계열: BTC 4H close/EMA20/EMA50/EMA200 + volatility shock filter로 신규 진입 gate만 실험.
- 분석 스크립트는 cached raw/funding JSON을 읽고 reports 산출물만 쓴다.

## Summary

| Variant | Return | CAGR | MDD | Sharpe | Sortino | Calmar | PF | Win | Trades | Avg R | Max losses | Recovery entries | Return vs V0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_1D_regime | 414.55% | 31.38% | -28.14% | 1.70 | 1.21 | 1.12 | 1.11 | 34.34% | 929.00 | 0.21 | 19.00 | 0.00 | 0.00% |
| V4H_basic | 497.13% | 34.68% | -23.63% | 1.73 | 1.42 | 1.47 | 1.07 | 35.26% | 1282.00 | 0.12 | 17.00 | 0.00 | 82.57% |
| V4H_recovery_size_50 | 627.11% | 39.18% | -23.75% | 1.87 | 1.68 | 1.65 | 1.06 | 34.37% | 1612.00 | 0.11 | 24.00 | 431.00 | 212.55% |
| V4H_recovery_size_25 | 592.65% | 38.06% | -23.74% | 1.90 | 1.67 | 1.60 | 1.08 | 34.37% | 1612.00 | 0.11 | 24.00 | 431.00 | 178.10% |
| V4H_strict | 729.80% | 42.27% | -27.45% | 1.95 | 1.68 | 1.54 | 1.08 | 35.98% | 1387.00 | 0.15 | 20.00 | 0.00 | 315.25% |
| V4H_hybrid | 391.31% | 30.38% | -20.18% | 1.85 | 1.52 | 1.50 | 1.15 | 34.23% | 1481.00 | 0.13 | 24.00 | 420.00 | -23.24% |

## 추가 분석

| Variant | 1D def + 4H rec/up bars | Entries | Return | Avg lead h | Fake recovery losses | Transitions | Whipsaw |
|---|---|---|---|---|---|---|---|
| V0_1D_regime | 3125.00 | 0.00 | 0.00% | 306.22 | 0.00 | 446.00 | 181.00 |
| V4H_basic | 3125.00 | 470.00 | 10.66% | 306.22 | 0.00 | 446.00 | 181.00 |
| V4H_recovery_size_50 | 3125.00 | 694.00 | -37.54% | 306.22 | 309.00 | 446.00 | 181.00 |
| V4H_recovery_size_25 | 3125.00 | 694.00 | 0.36% | 306.22 | 309.00 | 446.00 | 181.00 |
| V4H_strict | 3125.00 | 487.00 | 14.28% | 306.22 | 0.00 | 446.00 | 181.00 |
| V4H_hybrid | 3125.00 | 694.00 | -14.44% | 306.22 | 300.00 | 446.00 | 181.00 |

## Regime별 성과

| Variant | Regime | Entries | Return | Win | PF | Avg R |
|---|---|---|---|---|---|---|
| V0_1D_regime | eth_strength | 15.00 | -11.43% | 26.67% | 0.58 | -0.27 |
| V0_1D_regime | large_cap_lead | 14.00 | 41.87% | 85.71% | 12.51 | 2.15 |
| V0_1D_regime | uptrend | 900.00 | 84.89% | 33.67% | 1.08 | 0.19 |
| V4H_basic | uptrend | 1282.00 | 96.71% | 35.26% | 1.07 | 0.12 |
| V4H_recovery_size_50 | recovery | 431.00 | -50.81% | 28.31% | 0.83 | -0.03 |
| V4H_recovery_size_50 | uptrend | 1181.00 | 159.35% | 36.58% | 1.11 | 0.15 |
| V4H_recovery_size_25 | recovery | 431.00 | -23.10% | 28.31% | 0.84 | -0.03 |
| V4H_recovery_size_25 | uptrend | 1181.00 | 152.64% | 36.58% | 1.11 | 0.15 |
| V4H_strict | uptrend | 1387.00 | 162.87% | 35.98% | 1.08 | 0.15 |
| V4H_hybrid | recovery | 420.00 | -7.12% | 28.57% | 0.95 | -0.02 |
| V4H_hybrid | uptrend | 1061.00 | 136.54% | 36.48% | 1.19 | 0.19 |

## 산출물

- `alpha_engine_v1_2_4h_regime_comparison.md`
- `alpha_engine_v1_2_4h_regime_comparison.csv`
- `alpha_engine_v1_2_4h_regime_log.csv`
- `alpha_engine_v1_2_4h_regime_transitions.csv`
- `alpha_engine_v1_2_4h_regime_equity_1000.csv`
- `alpha_engine_v1_2_4h_regime_cost_stress.csv`
- `alpha_engine_v1_2_4h_regime_monthly_returns.csv`
- `alpha_engine_v1_2_4h_regime_yearly_returns.csv`
