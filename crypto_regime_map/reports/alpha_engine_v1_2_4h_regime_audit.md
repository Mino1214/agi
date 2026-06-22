# Alpha Engine v1.2 4H Regime Focused Audit

- 기존 V0/V4H comparison 로직은 수정하지 않고 별도 read-only audit 스크립트로 재계산했다.
- 감사 대상: V4H_strict, recovery size 25/50, recovery 제거/제한 변형.
- 비용 stress: fee 2x, slippage 2x, fee+slippage 2x, fee+slippage 3x.

## PASS/WATCH/FAIL

| Variant | Status | Reasons | Return vs V0 | MDD extra | 2x cost+slip vs V0 | Whipsaw PnL |
|---|---|---|---|---|---|---|
| V0_1D | BASELINE | baseline | 0.00% | 0.00% | 0.00% | 109.36% |
| V4H_strict | FAIL | cost 2x + slippage 2x under V0 | 315.25% | -0.68% | -2.87% | 146.44% |
| V4H_recovery_size_25 | FAIL | cost 2x + slippage 2x under V0; recovery PF <= 1.0 | 178.10% | -4.40% | -22.67% | 113.18% |
| V4H_recovery_size_50 | FAIL | cost 2x + slippage 2x under V0; recovery PF <= 1.0 | 212.55% | -4.39% | -37.09% | 92.04% |
| V4H_no_recovery | FAIL | cost 2x + slippage 2x under V0 | 82.57% | -4.50% | -30.88% | 83.53% |
| V4H_recovery_only_if_1D_not_defensive | FAIL | cost 2x + slippage 2x under V0 | 173.79% | -4.39% | -24.97% | 133.25% |
| V4H_recovery_score_90 | FAIL | cost 2x + slippage 2x under V0 | 331.96% | -4.41% | -9.40% | 152.53% |
| V4H_recovery_score_90_size_25 | FAIL | cost 2x + slippage 2x under V0 | 217.11% | -3.95% | -13.58% | 124.42% |

## Base Metrics

| Variant | Return | CAGR | MDD | Sharpe | Sortino | Calmar | PF | Win | Trades | Max losses | Avg R | Median trade |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_1D | 414.55% | 31.38% | -28.14% | 1.70 | 1.21 | 1.12 | 1.11 | 34.34% | 929.00 | 19.00 | 0.21 | -0.43% |
| V4H_strict | 729.80% | 42.27% | -27.45% | 1.95 | 1.68 | 1.54 | 1.08 | 35.98% | 1387.00 | 20.00 | 0.15 | -0.21% |
| V4H_recovery_size_25 | 592.65% | 38.06% | -23.74% | 1.90 | 1.67 | 1.60 | 1.08 | 34.37% | 1612.00 | 24.00 | 0.11 | -0.13% |
| V4H_recovery_size_50 | 627.11% | 39.18% | -23.75% | 1.87 | 1.68 | 1.65 | 1.06 | 34.37% | 1612.00 | 24.00 | 0.11 | -0.24% |
| V4H_no_recovery | 497.13% | 34.68% | -23.63% | 1.73 | 1.42 | 1.47 | 1.07 | 35.26% | 1282.00 | 17.00 | 0.12 | -0.20% |
| V4H_recovery_only_if_1D_not_defensive | 588.34% | 37.91% | -23.75% | 1.83 | 1.53 | 1.60 | 1.10 | 34.37% | 1388.00 | 21.00 | 0.14 | -0.22% |
| V4H_recovery_score_90 | 746.52% | 42.75% | -23.72% | 2.03 | 1.78 | 1.80 | 1.09 | 36.91% | 1455.00 | 15.00 | 0.17 | -0.16% |
| V4H_recovery_score_90_size_25 | 631.66% | 39.32% | -24.19% | 1.95 | 1.68 | 1.63 | 1.09 | 36.91% | 1455.00 | 15.00 | 0.17 | -0.13% |

## Cost Stress

| Variant | Scenario | Return | CAGR | MDD | PF | Trades |
|---|---|---|---|---|---|---|
| V0_1D | cost_2x | 279.61% | 24.89% | -35.67% | 1.08 | 929.00 |
| V4H_strict | cost_2x | 451.85% | 32.93% | -35.30% | 1.05 | 1387.00 |
| V4H_recovery_size_25 | cost_2x | 368.76% | 29.36% | -28.88% | 1.05 | 1612.00 |
| V4H_recovery_size_50 | cost_2x | 372.62% | 29.54% | -29.78% | 1.03 | 1612.00 |
| V4H_no_recovery | cost_2x | 304.72% | 26.23% | -30.99% | 1.04 | 1282.00 |
| V4H_recovery_only_if_1D_not_defensive | cost_2x | 360.23% | 28.96% | -29.26% | 1.06 | 1388.00 |
| V4H_recovery_score_90 | cost_2x | 467.99% | 33.57% | -30.81% | 1.06 | 1455.00 |
| V4H_recovery_score_90_size_25 | cost_2x | 400.14% | 30.76% | -30.83% | 1.06 | 1455.00 |
| V0_1D | slippage_2x | 78.75% | 10.16% | -47.38% | 0.91 | 969.00 |
| V4H_strict | slippage_2x | 97.84% | 12.04% | -47.81% | 0.88 | 1446.00 |
| V4H_recovery_size_25 | slippage_2x | 64.29% | 8.62% | -40.71% | 0.86 | 1694.00 |
| V4H_recovery_size_50 | slippage_2x | 50.18% | 7.01% | -42.46% | 0.85 | 1694.00 |
| V4H_no_recovery | slippage_2x | 50.93% | 7.10% | -42.37% | 0.86 | 1336.00 |
| V4H_recovery_only_if_1D_not_defensive | slippage_2x | 62.20% | 8.39% | -41.02% | 0.87 | 1448.00 |
| V4H_recovery_score_90 | slippage_2x | 85.96% | 10.89% | -42.63% | 0.87 | 1520.00 |
| V4H_recovery_score_90_size_25 | slippage_2x | 75.68% | 9.84% | -42.22% | 0.87 | 1520.00 |
| V0_1D | cost_2x_slippage_2x | 30.18% | 4.49% | -53.74% | 0.89 | 969.00 |
| V4H_strict | cost_2x_slippage_2x | 27.31% | 4.11% | -61.03% | 0.87 | 1446.00 |
| V4H_recovery_size_25 | cost_2x_slippage_2x | 7.51% | 1.21% | -53.26% | 0.85 | 1694.00 |
| V4H_recovery_size_50 | cost_2x_slippage_2x | -6.91% | -1.19% | -58.36% | 0.83 | 1694.00 |
| V4H_no_recovery | cost_2x_slippage_2x | -0.70% | -0.12% | -55.34% | 0.84 | 1336.00 |
| V4H_recovery_only_if_1D_not_defensive | cost_2x_slippage_2x | 5.20% | 0.85% | -56.84% | 0.85 | 1448.00 |
| V4H_recovery_score_90 | cost_2x_slippage_2x | 20.78% | 3.20% | -52.26% | 0.86 | 1520.00 |
| V4H_recovery_score_90_size_25 | cost_2x_slippage_2x | 16.60% | 2.59% | -52.09% | 0.85 | 1520.00 |
| V0_1D | cost_3x_slippage_3x | -78.90% | -22.84% | -86.84% | 0.72 | 1066.00 |
| V4H_strict | cost_3x_slippage_3x | -91.63% | -33.85% | -95.43% | 0.72 | 1547.00 |
| V4H_recovery_size_25 | cost_3x_slippage_3x | -91.90% | -34.21% | -93.83% | 0.69 | 1826.00 |
| V4H_recovery_size_50 | cost_3x_slippage_3x | -97.62% | -46.35% | -98.12% | 0.68 | 1826.00 |
| V4H_no_recovery | cost_3x_slippage_3x | -91.07% | -33.14% | -93.10% | 0.68 | 1424.00 |
| V4H_recovery_only_if_1D_not_defensive | cost_3x_slippage_3x | -92.70% | -35.35% | -94.31% | 0.68 | 1551.00 |
| V4H_recovery_score_90 | cost_3x_slippage_3x | -91.16% | -33.25% | -93.81% | 0.71 | 1628.00 |
| V4H_recovery_score_90_size_25 | cost_3x_slippage_3x | -89.13% | -30.92% | -92.32% | 0.70 | 1628.00 |

## Recovery Summary

| Variant | Trades | PnL | PF | Win | Max losses | MDD contrib |
|---|---|---|---|---|---|---|
| V0_1D | 0.00 | 0.00% |  | 0.00% | 0.00 | 0.00% |
| V4H_strict | 0.00 | 0.00% |  | 0.00% | 0.00 | 0.00% |
| V4H_recovery_size_25 | 431.00 | -23.10% | 0.84 | 28.31% | 24.00 | -38.08% |
| V4H_recovery_size_50 | 431.00 | -50.81% | 0.83 | 28.31% | 24.00 | -80.70% |
| V4H_no_recovery | 0.00 | 0.00% |  | 0.00% | 0.00 | 0.00% |
| V4H_recovery_only_if_1D_not_defensive | 149.00 | 20.58% | 1.22 | 25.50% | 14.00 | -43.13% |
| V4H_recovery_score_90 | 245.00 | 45.29% | 1.27 | 39.59% | 11.00 | -26.66% |
| V4H_recovery_score_90_size_25 | 245.00 | 21.47% | 1.29 | 39.59% | 11.00 | -11.67% |

## Whipsaw Summary

| Variant | Transitions | Whipsaw | Rec->Def losses | Stop 1 | Stop 3 | Stop 5 | Whipsaw PnL | Whipsaw share |
|---|---|---|---|---|---|---|---|---|
| V0_1D | 446.00 | 181.00 | 0.00 | 42.00 | 63.00 | 82.00 | 109.36% | 94.82% |
| V4H_strict | 446.00 | 181.00 | 0.00 | 56.00 | 89.00 | 124.00 | 146.44% | 89.91% |
| V4H_recovery_size_25 | 446.00 | 181.00 | 47.00 | 152.00 | 219.00 | 265.00 | 113.18% | 87.37% |
| V4H_recovery_size_50 | 446.00 | 181.00 | 47.00 | 152.00 | 219.00 | 265.00 | 92.04% | 84.80% |
| V4H_no_recovery | 446.00 | 181.00 | 0.00 | 72.00 | 110.00 | 143.00 | 83.53% | 86.37% |
| V4H_recovery_only_if_1D_not_defensive | 446.00 | 181.00 | 22.00 | 108.00 | 161.00 | 197.00 | 133.25% | 91.00% |
| V4H_recovery_score_90 | 446.00 | 181.00 | 31.00 | 104.00 | 163.00 | 201.00 | 152.53% | 89.80% |
| V4H_recovery_score_90_size_25 | 446.00 | 181.00 | 31.00 | 104.00 | 163.00 | 201.00 | 124.42% | 88.13% |

## Regime Performance

| Variant | Regime | Trades | PnL | PF | Avg R | MDD contrib |
|---|---|---|---|---|---|---|
| V0_1D | uptrend | 900.00 | 84.89% | 1.08 | 0.19 | -232.68% |
| V0_1D | large_cap_lead | 14.00 | 41.87% | 12.51 | 2.15 | -2.91% |
| V0_1D | eth_strength | 15.00 | -11.43% | 0.58 | -0.27 | -24.89% |
| V4H_strict | uptrend | 1387.00 | 162.87% | 1.08 | 0.15 | -347.69% |
| V4H_recovery_size_25 | uptrend | 1181.00 | 152.64% | 1.11 | 0.15 | -232.08% |
| V4H_recovery_size_25 | recovery | 431.00 | -23.10% | 0.84 | -0.03 | -38.08% |
| V4H_recovery_size_50 | uptrend | 1181.00 | 159.35% | 1.11 | 0.15 | -243.07% |
| V4H_recovery_size_50 | recovery | 431.00 | -50.81% | 0.83 | -0.03 | -80.70% |
| V4H_no_recovery | uptrend | 1282.00 | 96.71% | 1.07 | 0.12 | -221.42% |
| V4H_recovery_only_if_1D_not_defensive | uptrend | 1239.00 | 125.85% | 1.09 | 0.13 | -216.69% |
| V4H_recovery_only_if_1D_not_defensive | recovery | 149.00 | 20.58% | 1.22 | 0.25 | -43.13% |
| V4H_recovery_score_90 | uptrend | 1210.00 | 124.55% | 1.07 | 0.14 | -305.88% |
| V4H_recovery_score_90 | recovery | 245.00 | 45.29% | 1.27 | 0.31 | -26.66% |
| V4H_recovery_score_90_size_25 | uptrend | 1210.00 | 119.71% | 1.08 | 0.14 | -269.21% |
| V4H_recovery_score_90_size_25 | recovery | 245.00 | 21.47% | 1.29 | 0.31 | -11.67% |

## 산출물

- `alpha_engine_v1_2_4h_regime_audit.md`
- `alpha_engine_v1_2_4h_regime_audit_summary.csv`
- `alpha_engine_v1_2_4h_regime_audit_recovery_analysis.csv`
- `alpha_engine_v1_2_4h_regime_audit_whipsaw_analysis.csv`
- `alpha_engine_v1_2_4h_regime_audit_regime_performance.csv`
- `alpha_engine_v1_2_4h_regime_audit_variant_comparison.csv`
