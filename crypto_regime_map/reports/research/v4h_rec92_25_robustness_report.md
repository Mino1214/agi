# V4H REC92 25 Robustness/OOS Report

## Scope

- Read-only audit/report only. Existing strategy logic, live order logic, paper engine, and existing result files were not modified.
- Target final candidate assumption: `V4H_STRICT_REC92_25`.
- Compared targets: `V4H_STRICT_REC92_25`, `V4H_STRICT_REC92_15`, `V4H_STRICT_REC90_25_COOLDOWN`, `V0_BASELINE`.
- Base cost uses existing candidate fee/slippage. Cost stress multiplies both fee and slippage by 2x, 3x, and 5x.
- Market-state split is independent audit labeling from BTC daily EMA200 and 60D return: bull = close > EMA200 and 60D return > 5%, bear = close < EMA200 and 60D return < -5%, otherwise sideways.
- Monte Carlo shuffles the realized trade-return sequence 1000 times. Actual portfolio final return is shown separately because overlapping positions and partial exits mean the sequence model is a path-risk approximation, not a full portfolio replay.

## Final Verdict

**FAIL**

SOL removal cuts return by >150pp; one negative calendar year; multiple weak calendar years below 5%; bear-market trade PnL is negative; 3x fee/slippage produces severe loss; 5x fee/slippage nearly destroys equity

## Base Metrics

| Variant | Return | CAGR | MDD | PF | Win | Trades | Avg R | Return vs V0 | MDD extra |
|---|---|---|---|---|---|---|---|---|---|
| V0_BASELINE | 414.55% | 31.38% | -28.14% | 1.11 | 34.34% | 929.00 | 0.21 | 0.00% | 0.00% |
| V4H_STRICT_REC92_25 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 | 457.27% | -1.62% |
| V4H_STRICT_REC92_15 | 815.17% | 44.62% | -26.61% | 1.09 | 37.36% | 1515.00 | 0.20 | 400.61% | -1.52% |
| V4H_STRICT_REC90_25_COOLDOWN | 838.82% | 45.23% | -26.69% | 1.09 | 37.14% | 1540.00 | 0.17 | 424.27% | -1.45% |

## 1. Yearly OOS

| Variant | Year | Return | CAGR | MDD | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|---|---|
| V0_BASELINE | 2020.00 | 108.95% | 108.64% | -11.57% | 2.20 | 41.21% | 165.00 | 0.70 |
| V0_BASELINE | 2021.00 | 63.93% | 63.99% | -7.01% | 2.18 | 44.63% | 121.00 | 0.72 |
| V0_BASELINE | 2022.00 | 0.00% | 0.00% | 0.00% |  | 0.00% | 0.00 |  |
| V0_BASELINE | 2023.00 | 39.83% | 39.86% | -11.39% | 1.30 | 36.26% | 182.00 | 0.16 |
| V0_BASELINE | 2024.00 | 0.05% | 0.05% | -24.11% | 0.78 | 27.13% | 247.00 | -0.12 |
| V0_BASELINE | 2025.00 | 7.38% | 7.38% | -22.33% | 0.89 | 29.91% | 214.00 | -0.04 |
| V4H_STRICT_REC92_25 | 2020.00 | 128.07% | 127.69% | -8.35% | 2.18 | 46.58% | 234.00 | 0.68 |
| V4H_STRICT_REC92_25 | 2021.00 | 127.95% | 128.08% | -9.77% | 1.83 | 40.22% | 271.00 | 0.45 |
| V4H_STRICT_REC92_25 | 2022.00 | -3.28% | -3.29% | -7.74% | 0.64 | 30.37% | 135.00 | -0.12 |
| V4H_STRICT_REC92_25 | 2023.00 | 71.69% | 71.75% | -14.10% | 1.38 | 39.02% | 328.00 | 0.20 |
| V4H_STRICT_REC92_25 | 2024.00 | 10.51% | 10.48% | -22.73% | 0.89 | 33.44% | 305.00 | -0.04 |
| V4H_STRICT_REC92_25 | 2025.00 | 1.87% | 1.87% | -23.21% | 0.81 | 31.82% | 242.00 | -0.06 |
| V4H_STRICT_REC92_15 | 2020.00 | 121.38% | 121.02% | -8.34% | 2.14 | 46.58% | 234.00 | 0.68 |
| V4H_STRICT_REC92_15 | 2021.00 | 128.25% | 128.38% | -9.77% | 1.84 | 40.22% | 271.00 | 0.45 |
| V4H_STRICT_REC92_15 | 2022.00 | -4.05% | -4.05% | -7.74% | 0.61 | 30.37% | 135.00 | -0.12 |
| V4H_STRICT_REC92_15 | 2023.00 | 69.83% | 69.89% | -14.09% | 1.37 | 39.02% | 328.00 | 0.20 |
| V4H_STRICT_REC92_15 | 2024.00 | 10.12% | 10.09% | -23.04% | 0.89 | 33.44% | 305.00 | -0.04 |
| V4H_STRICT_REC92_15 | 2025.00 | 0.94% | 0.94% | -23.17% | 0.80 | 31.82% | 242.00 | -0.06 |
| V4H_STRICT_REC90_25_COOLDOWN | 2020.00 | 116.28% | 115.94% | -8.34% | 2.03 | 44.90% | 245.00 | 0.44 |
| V4H_STRICT_REC90_25_COOLDOWN | 2021.00 | 131.36% | 131.49% | -9.77% | 1.87 | 41.03% | 273.00 | 0.46 |
| V4H_STRICT_REC90_25_COOLDOWN | 2022.00 | -2.27% | -2.28% | -6.71% | 0.66 | 31.91% | 141.00 | -0.11 |
| V4H_STRICT_REC90_25_COOLDOWN | 2023.00 | 68.90% | 68.96% | -12.78% | 1.37 | 38.48% | 330.00 | 0.20 |
| V4H_STRICT_REC90_25_COOLDOWN | 2024.00 | 11.25% | 11.23% | -22.88% | 0.90 | 33.22% | 304.00 | -0.03 |
| V4H_STRICT_REC90_25_COOLDOWN | 2025.00 | 2.17% | 2.17% | -23.49% | 0.81 | 31.17% | 247.00 | -0.08 |

### Year Dependence Check

- `V4H_STRICT_REC92_25` is not a single-year-only result, but it is weak in 2022 and 2025.
- The strongest contribution is concentrated in 2020, 2021, and 2023.

## 2. Bull / Bear / Sideways

| Variant | State | PnL | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|
| V0_BASELINE | bull | 175.91% | 1.24 | 36.98% | 695.00 | 0.24 |
| V0_BASELINE | bear | -2.33% | 0.00 | 0.00% | 1.00 | -1.03 |
| V0_BASELINE | sideways | -58.25% | 0.80 | 26.61% | 233.00 | 0.12 |
| V4H_STRICT_REC92_25 | bull | 323.10% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_STRICT_REC92_25 | bear | -31.02% | 0.71 | 36.24% | 149.00 | 0.10 |
| V4H_STRICT_REC92_25 | sideways | -89.03% | 0.81 | 37.02% | 289.00 | 0.21 |
| V4H_STRICT_REC92_15 | bull | 311.61% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_STRICT_REC92_15 | bear | -30.53% | 0.66 | 36.24% | 149.00 | 0.10 |
| V4H_STRICT_REC92_15 | sideways | -94.86% | 0.79 | 37.02% | 289.00 | 0.21 |
| V4H_STRICT_REC90_25_COOLDOWN | bull | 325.89% | 1.20 | 38.03% | 1086.00 | 0.22 |
| V4H_STRICT_REC90_25_COOLDOWN | bear | -34.41% | 0.68 | 33.13% | 166.00 | 0.02 |
| V4H_STRICT_REC90_25_COOLDOWN | sideways | -97.22% | 0.78 | 36.33% | 289.00 | 0.06 |

## 3. Symbol Dependence

| Symbol | PnL | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|
| ADA | 15.68% | 1.06 | 36.99% | 219.00 | 0.08 |
| AVAX | -1.13% | 1.00 | 39.56% | 182.00 | 0.11 |
| BNB | 55.79% | 1.19 | 35.64% | 188.00 | 0.37 |
| BTC | 40.45% | 1.19 | 38.85% | 139.00 | 0.32 |
| ETH | -15.45% | 0.95 | 38.53% | 218.00 | 0.34 |
| LINK | -15.52% | 0.94 | 36.41% | 184.00 | 0.01 |
| SOL | 101.07% | 1.33 | 40.19% | 209.00 | 0.25 |
| TON | -94.95% | 0.17 | 24.32% | 37.00 | -0.60 |
| XRP | 117.11% | 1.60 | 35.00% | 140.00 | 0.31 |

## 4. Leave-One-Symbol-Out

| Variant | Excluded | Return | CAGR | MDD | PF | Trades | Return delta |
|---|---|---|---|---|---|---|---|
| V0_BASELINE | BNB | 265.82% | 24.12% | -29.35% | 1.06 | 876.00 | -148.73% |
| V4H_STRICT_REC92_25 | BNB | 553.71% | 36.73% | -25.87% | 1.03 | 1450.00 | -318.12% |
| V4H_STRICT_REC92_15 | BNB | 517.06% | 35.42% | -26.32% | 1.03 | 1450.00 | -298.11% |
| V4H_STRICT_REC90_25_COOLDOWN | BNB | 532.71% | 35.99% | -24.85% | 1.03 | 1470.00 | -306.11% |
| V0_BASELINE | SOL | 328.80% | 27.45% | -27.23% | 1.11 | 891.00 | -85.75% |
| V4H_STRICT_REC92_25 | SOL | 535.33% | 36.08% | -27.54% | 1.03 | 1463.00 | -336.49% |
| V4H_STRICT_REC92_15 | SOL | 500.80% | 34.82% | -27.25% | 1.03 | 1463.00 | -314.36% |
| V4H_STRICT_REC90_25_COOLDOWN | SOL | 506.99% | 35.05% | -26.77% | 1.03 | 1490.00 | -331.83% |
| V0_BASELINE | ETH | 258.21% | 23.69% | -23.99% | 1.07 | 908.00 | -156.35% |
| V4H_STRICT_REC92_25 | ETH | 789.13% | 43.92% | -20.16% | 1.12 | 1466.00 | -82.70% |
| V4H_STRICT_REC92_15 | ETH | 761.04% | 43.15% | -20.47% | 1.12 | 1466.00 | -54.13% |
| V4H_STRICT_REC90_25_COOLDOWN | ETH | 788.39% | 43.90% | -20.32% | 1.12 | 1486.00 | -50.43% |

### Focus Candidate LOSO

| Excluded | Return | CAGR | MDD | PF | Trades | Return delta |
|---|---|---|---|---|---|---|
| BNB | 553.71% | 36.73% | -25.87% | 1.03 | 1450.00 | -318.12% |
| SOL | 535.33% | 36.08% | -27.54% | 1.03 | 1463.00 | -336.49% |
| ETH | 789.13% | 43.92% | -20.16% | 1.12 | 1466.00 | -82.70% |

## 5. Cost Stress Extreme

| Variant | Cost | Return | CAGR | MDD | PF | Trades | Return vs V0 |
|---|---|---|---|---|---|---|---|
| V0_BASELINE | 1.00 | 414.55% | 31.38% | -28.14% | 1.11 | 929.00 | 0.00% |
| V4H_STRICT_REC92_25 | 1.00 | 871.82% | 46.07% | -26.52% | 1.09 | 1515.00 | 457.27% |
| V4H_STRICT_REC92_15 | 1.00 | 815.17% | 44.62% | -26.61% | 1.09 | 1515.00 | 400.61% |
| V4H_STRICT_REC90_25_COOLDOWN | 1.00 | 838.82% | 45.23% | -26.69% | 1.09 | 1540.00 | 424.27% |
| V0_BASELINE | 2.00 | 30.18% | 4.49% | -53.74% | 0.89 | 969.00 | 0.00% |
| V4H_STRICT_REC92_25 | 2.00 | 43.83% | 6.24% | -59.04% | 0.87 | 1583.00 | 13.65% |
| V4H_STRICT_REC92_15 | 2.00 | 40.76% | 5.86% | -59.10% | 0.87 | 1583.00 | 10.58% |
| V4H_STRICT_REC90_25_COOLDOWN | 2.00 | 41.59% | 5.97% | -59.33% | 0.87 | 1603.00 | 11.41% |
| V0_BASELINE | 3.00 | -78.90% | -22.84% | -86.84% | 0.72 | 1066.00 | 0.00% |
| V4H_STRICT_REC92_25 | 3.00 | -91.26% | -33.38% | -94.91% | 0.73 | 1705.00 | -12.36% |
| V4H_STRICT_REC92_15 | 3.00 | -90.61% | -32.57% | -94.50% | 0.72 | 1705.00 | -11.70% |
| V4H_STRICT_REC90_25_COOLDOWN | 3.00 | -90.33% | -32.24% | -94.60% | 0.72 | 1715.00 | -11.43% |
| V0_BASELINE | 5.00 | -100.00% | -96.84% | -100.00% | 0.51 | 1321.00 | 0.00% |
| V4H_STRICT_REC92_25 | 5.00 | -100.00% | -96.84% | -100.00% | 0.52 | 2037.00 | 0.00% |
| V4H_STRICT_REC92_15 | 5.00 | -100.00% | -96.84% | -100.00% | 0.52 | 2037.00 | 0.00% |
| V4H_STRICT_REC90_25_COOLDOWN | 5.00 | -100.00% | -96.84% | -100.00% | 0.52 | 2036.00 | 0.00% |

### Focus vs V0 Cost Check

| Variant | Cost | Return | MDD | Return vs V0 |
|---|---|---|---|---|
| V0_BASELINE | 1.00 | 414.55% | -28.14% | 0.00% |
| V4H_STRICT_REC92_25 | 1.00 | 871.82% | -26.52% | 457.27% |
| V0_BASELINE | 2.00 | 30.18% | -53.74% | 0.00% |
| V4H_STRICT_REC92_25 | 2.00 | 43.83% | -59.04% | 13.65% |
| V0_BASELINE | 3.00 | -78.90% | -86.84% | 0.00% |
| V4H_STRICT_REC92_25 | 3.00 | -91.26% | -94.91% | -12.36% |
| V0_BASELINE | 5.00 | -100.00% | -100.00% | 0.00% |
| V4H_STRICT_REC92_25 | 5.00 | -100.00% | -100.00% | 0.00% |

## 6. Alpha Score Sensitivity

| Threshold | Return | CAGR | MDD | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|---|
| 90.00 | 916.38% | 47.17% | -26.78% | 1.09 | 37.40% | 1559.00 | 0.20 |
| 91.00 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 92.00 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 93.00 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 94.00 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 95.00 | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |

## 7. Recovery Size Sensitivity

| Recovery size | Return | CAGR | MDD | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|---|
| 10.00% | 787.76% | 43.88% | -26.66% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 15.00% | 815.17% | 44.62% | -26.61% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 20.00% | 843.19% | 45.34% | -26.57% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 25.00% | 871.82% | 46.07% | -26.52% | 1.09 | 37.36% | 1515.00 | 0.20 |
| 30.00% | 901.09% | 46.79% | -26.47% | 1.09 | 37.36% | 1515.00 | 0.20 |

## 8. Walk Forward

| Fold | Split | Return | CAGR | MDD | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|---|---|
| train_2020_2022 | train | 402.82% | 71.30% | -10.37% | 1.47 | 40.47% | 640.00 | 0.41 |
| test_2023_2025 | test | 93.27% | 24.56% | -26.52% | 0.99 | 35.09% | 875.00 | 0.04 |
| expanding_train_2020_2020 | train | 128.07% | 127.69% | -8.35% | 2.18 | 46.58% | 234.00 | 0.68 |
| test_2021 | test | 127.95% | 128.08% | -9.77% | 1.83 | 40.22% | 271.00 | 0.45 |
| expanding_train_2020_2021 | train | 419.89% | 127.88% | -9.77% | 1.91 | 43.17% | 505.00 | 0.56 |
| test_2022 | test | -3.28% | -3.29% | -7.74% | 0.64 | 30.37% | 135.00 | -0.12 |
| expanding_train_2020_2022 | train | 402.82% | 71.30% | -10.37% | 1.47 | 40.47% | 640.00 | 0.41 |
| test_2023 | test | 71.69% | 71.75% | -14.10% | 1.38 | 39.02% | 328.00 | 0.20 |
| expanding_train_2020_2023 | train | 763.30% | 71.41% | -14.10% | 1.43 | 39.98% | 968.00 | 0.34 |
| test_2024 | test | 10.51% | 10.48% | -22.73% | 0.89 | 33.44% | 305.00 | -0.04 |
| expanding_train_2020_2024 | train | 854.00% | 56.97% | -22.73% | 1.20 | 38.41% | 1273.00 | 0.25 |
| test_2025 | test | 1.87% | 1.87% | -23.21% | 0.81 | 31.82% | 242.00 | -0.06 |

## 9. Monte Carlo

| Simulation | Runs | Actual final | Seq final | Median MDD | Worst MDD | Worst min equity | Worst max losses |
|---|---|---|---|---|---|---|---|
| summary | 1000.00 | 871.82% | 200.43% | -16.81% | -34.26% | 0.74 | 25.00 |

## Output Files

- `reports/research/v4h_rec92_25_robustness_report.md`
- `reports/research/v4h_rec92_25_robustness_summary.csv`
- `reports/research/v4h_rec92_25_robustness_yearly.csv`
- `reports/research/v4h_rec92_25_robustness_market_states.csv`
- `reports/research/v4h_rec92_25_robustness_symbols.csv`
- `reports/research/v4h_rec92_25_robustness_leave_one_symbol.csv`
- `reports/research/v4h_rec92_25_robustness_cost_stress.csv`
- `reports/research/v4h_rec92_25_robustness_alpha_sensitivity.csv`
- `reports/research/v4h_rec92_25_robustness_recovery_size_sensitivity.csv`
- `reports/research/v4h_rec92_25_robustness_walk_forward.csv`
- `reports/research/v4h_rec92_25_robustness_monte_carlo.csv`
