# V4H Strict Selective Recovery Report

## Scope

- Offline/read-only backtest only. No production order path, paper default path, or existing V0/V4H audit file was modified.
- Baseline V0 uses the existing 1D regime gate with DOGE exclusion, alpha_score top 20%, liquidation buffer, actual funding, base fee/slippage.
- V4H variants use strict BTC 4H uptrend gating. Selective recovery variants allow only BTC 4H recovery entries whose normalized alpha_score_pct meets the listed threshold.
- Normalization used here: raw alpha_score on the 0-10.5 scale is multiplied by 10. Thus REC90 means raw alpha_score >= 9.0 and REC92 means raw alpha_score >= 9.2.
- Cooldown variant uses a same-symbol recovery-entry cooldown of 24 hours after a filled recovery entry.
- WAIT1 variants block the first 4H close immediately after transition into uptrend/recovery; the next 4H candle may enter only if the regime still holds.

## PASS/WATCH/FAIL

| Variant | Status | Reasons | Return vs V0 | CAGR vs V0 | MDD extra | 2x cost+slip vs V0 | Recovery PF | Trades | Stops |
|---|---|---|---|---|---|---|---|---|---|
| V0_1D | BASELINE | baseline | 0.00% | 0.00% | 0.00% | 0.00% |  | 929.00 | 559.00 |
| V4H_STRICT_BASE | FAIL | cost 2x + slippage 2x under V0 | 315.25% | 10.89% | -0.68% | -2.87% |  | 1387.00 | 757.00 |
| V4H_STRICT_REC90_25 | WATCH | recovery depends heavily on one symbol | 459.09% | 14.73% | -1.67% | 12.21% | 1.18 | 1575.00 | 861.00 |
| V4H_STRICT_REC90_15 | WATCH | recovery depends heavily on one symbol | 413.48% | 13.57% | -1.57% | 11.32% | 1.18 | 1575.00 | 861.00 |
| V4H_STRICT_REC92_25 | PASS | meets selective recovery audit thresholds | 423.20% | 13.82% | -1.94% | 8.02% | 1.38 | 1529.00 | 832.00 |
| V4H_STRICT_REC92_15 | PASS | meets selective recovery audit thresholds | 376.62% | 12.59% | -1.71% | 5.84% | 1.38 | 1529.00 | 832.00 |
| V4H_STRICT_REC90_25_COOLDOWN | PASS | meets selective recovery audit thresholds | 389.85% | 12.95% | -1.78% | 5.86% | 1.26 | 1549.00 | 848.00 |
| V4H_STRICT_WAIT1 | FAIL | cost 2x + slippage 2x under V0 | 280.53% | 9.88% | -0.64% | -10.39% |  | 1378.00 | 750.00 |
| V4H_STRICT_REC90_25_WAIT1 | FAIL | cost 2x + slippage 2x under V0 | 393.06% | 13.03% | -0.68% | -1.44% | 1.28 | 1555.00 | 850.00 |

## Base Metrics

| Variant | Return | CAGR | MDD | Calmar | PF | Win | Trades | Avg hold d | Stop rate |
|---|---|---|---|---|---|---|---|---|---|
| V0_1D | 414.55% | 31.38% | -28.14% | 1.12 | 1.11 | 34.34% | 929.00 | 1.55 | 60.17% |
| V4H_STRICT_BASE | 729.80% | 42.27% | -27.45% | 1.54 | 1.08 | 35.98% | 1387.00 | 1.49 | 54.58% |
| V4H_STRICT_REC90_25 | 873.64% | 46.12% | -26.46% | 1.74 | 1.09 | 36.76% | 1575.00 | 1.53 | 54.67% |
| V4H_STRICT_REC90_15 | 828.04% | 44.95% | -26.57% | 1.69 | 1.09 | 36.76% | 1575.00 | 1.53 | 54.67% |
| V4H_STRICT_REC92_25 | 837.76% | 45.20% | -26.19% | 1.73 | 1.09 | 36.89% | 1529.00 | 1.53 | 54.41% |
| V4H_STRICT_REC92_15 | 791.18% | 43.98% | -26.42% | 1.66 | 1.08 | 36.89% | 1529.00 | 1.53 | 54.41% |
| V4H_STRICT_REC90_25_COOLDOWN | 804.40% | 44.33% | -26.36% | 1.68 | 1.09 | 36.73% | 1549.00 | 1.53 | 54.74% |
| V4H_STRICT_WAIT1 | 695.08% | 41.27% | -27.50% | 1.50 | 1.06 | 35.99% | 1378.00 | 1.49 | 54.43% |
| V4H_STRICT_REC90_25_WAIT1 | 807.62% | 44.42% | -27.46% | 1.62 | 1.06 | 36.72% | 1555.00 | 1.52 | 54.66% |

## Cost Stress: 2x Fee + 2x Slippage

| Variant | Return | CAGR | MDD | Calmar | Return vs V0 | Calmar vs V0 | Trades |
|---|---|---|---|---|---|---|---|
| V0_1D | 30.18% | 4.49% | -53.74% | 0.08 | 0.00% | 0.00 | 969.00 |
| V4H_STRICT_BASE | 27.31% | 4.11% | -61.03% | 0.07 | -2.87% | -0.02 | 1446.00 |
| V4H_STRICT_REC90_25 | 42.39% | 6.07% | -59.72% | 0.10 | 12.21% | 0.02 | 1644.00 |
| V4H_STRICT_REC90_15 | 41.50% | 5.95% | -59.46% | 0.10 | 11.32% | 0.02 | 1644.00 |
| V4H_STRICT_REC92_25 | 38.20% | 5.54% | -59.78% | 0.09 | 8.02% | 0.01 | 1596.00 |
| V4H_STRICT_REC92_15 | 36.01% | 5.26% | -59.78% | 0.09 | 5.84% | 0.00 | 1596.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 36.04% | 5.26% | -60.07% | 0.09 | 5.86% | 0.00 | 1613.00 |
| V4H_STRICT_WAIT1 | 19.78% | 3.05% | -62.13% | 0.05 | -10.39% | -0.03 | 1437.00 |
| V4H_STRICT_REC90_25_WAIT1 | 28.74% | 4.30% | -61.43% | 0.07 | -1.44% | -0.01 | 1625.00 |

## Cost Stress: 3x Fee + 3x Slippage

| Variant | Return | CAGR | MDD | Calmar | Return vs V0 | Trades |
|---|---|---|---|---|---|---|
| V0_1D | -78.90% | -22.84% | -86.84% | -0.26 | 0.00% | 1066.00 |
| V4H_STRICT_BASE | -91.63% | -33.85% | -95.43% | -0.35 | -12.73% | 1547.00 |
| V4H_STRICT_REC90_25 | -90.22% | -32.12% | -94.72% | -0.34 | -11.32% | 1762.00 |
| V4H_STRICT_REC90_15 | -89.33% | -31.13% | -94.23% | -0.33 | -10.43% | 1762.00 |
| V4H_STRICT_REC92_25 | -91.08% | -33.15% | -95.06% | -0.35 | -12.18% | 1717.00 |
| V4H_STRICT_REC92_15 | -90.42% | -32.35% | -94.63% | -0.34 | -11.52% | 1717.00 |
| V4H_STRICT_REC90_25_COOLDOWN | -91.19% | -33.29% | -95.16% | -0.35 | -12.29% | 1725.00 |
| V4H_STRICT_WAIT1 | -92.89% | -35.63% | -95.50% | -0.37 | -13.99% | 1538.00 |
| V4H_STRICT_REC90_25_WAIT1 | -92.70% | -35.35% | -95.47% | -0.37 | -13.80% | 1744.00 |

## Recovery vs Uptrend

| Variant | Recovery trades | Recovery PnL | Recovery PF | Recovery stops | Uptrend trades | Uptrend PnL | Uptrend PF | Uptrend stops |
|---|---|---|---|---|---|---|---|---|
| V0_1D | 0.00 | 0.00% |  | 0.00 | 900.00 | 84.89% | 1.08 | 546.00 |
| V4H_STRICT_BASE | 0.00 | 0.00% |  | 0.00 | 1387.00 | 162.87% | 1.08 | 757.00 |
| V4H_STRICT_REC90_25 | 259.00 | 19.24% | 1.18 | 163.00 | 1316.00 | 186.74% | 1.09 | 698.00 |
| V4H_STRICT_REC90_15 | 259.00 | 11.39% | 1.18 | 163.00 | 1316.00 | 184.57% | 1.09 | 698.00 |
| V4H_STRICT_REC92_25 | 202.00 | 28.98% | 1.38 | 124.00 | 1327.00 | 161.84% | 1.08 | 708.00 |
| V4H_STRICT_REC92_15 | 202.00 | 16.99% | 1.38 | 124.00 | 1327.00 | 160.31% | 1.08 | 708.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 226.00 | 22.04% | 1.26 | 144.00 | 1323.00 | 161.07% | 1.08 | 704.00 |
| V4H_STRICT_WAIT1 | 0.00 | 0.00% |  | 0.00 | 1378.00 | 120.96% | 1.06 | 750.00 |
| V4H_STRICT_REC90_25_WAIT1 | 237.00 | 26.39% | 1.28 | 148.00 | 1318.00 | 113.36% | 1.05 | 702.00 |

## Recovery Symbol Performance

| Variant | Symbol | Trades | PnL | PF | Win | Stops | Avg hold h | Worst trade |
|---|---|---|---|---|---|---|---|---|
| V4H_STRICT_REC90_25 | ADA | 38.00 | -2.60% | 0.80 | 31.58% | 25.00 | 30.00 | -0.14% |
| V4H_STRICT_REC90_25 | AVAX | 25.00 | 4.60% | 1.39 | 36.00% | 16.00 | 40.52 | -0.13% |
| V4H_STRICT_REC90_25 | BNB | 35.00 | 15.03% | 2.37 | 40.00% | 20.00 | 49.03 | -0.13% |
| V4H_STRICT_REC90_25 | BTC | 8.00 | 3.45% | 2.05 | 50.00% | 4.00 | 56.12 | -0.13% |
| V4H_STRICT_REC90_25 | ETH | 37.00 | 5.90% | 1.46 | 29.73% | 25.00 | 37.22 | -0.14% |
| V4H_STRICT_REC90_25 | LINK | 33.00 | -5.17% | 0.67 | 36.36% | 21.00 | 32.33 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 45.00 | 9.04% | 1.47 | 37.78% | 28.00 | 42.38 | -0.13% |
| V4H_STRICT_REC90_25 | TON | 9.00 | -1.18% | 0.76 | 55.56% | 4.00 | 26.11 | -0.13% |
| V4H_STRICT_REC90_25 | XRP | 29.00 | -9.83% | 0.31 | 27.59% | 20.00 | 34.66 | -0.13% |
| V4H_STRICT_REC90_15 | ADA | 38.00 | -1.50% | 0.80 | 31.58% | 25.00 | 30.00 | -0.08% |
| V4H_STRICT_REC90_15 | AVAX | 25.00 | 2.63% | 1.38 | 36.00% | 16.00 | 40.52 | -0.08% |
| V4H_STRICT_REC90_15 | BNB | 35.00 | 8.69% | 2.36 | 40.00% | 20.00 | 49.03 | -0.08% |
| V4H_STRICT_REC90_15 | BTC | 8.00 | 2.03% | 2.07 | 50.00% | 4.00 | 56.12 | -0.08% |
| V4H_STRICT_REC90_15 | ETH | 37.00 | 3.61% | 1.48 | 29.73% | 25.00 | 37.22 | -0.08% |
| V4H_STRICT_REC90_15 | LINK | 33.00 | -2.95% | 0.68 | 36.36% | 21.00 | 32.33 | -0.08% |
| V4H_STRICT_REC90_15 | SOL | 45.00 | 5.20% | 1.47 | 37.78% | 28.00 | 42.38 | -0.08% |
| V4H_STRICT_REC90_15 | TON | 9.00 | -0.67% | 0.77 | 55.56% | 4.00 | 26.11 | -0.08% |
| V4H_STRICT_REC90_15 | XRP | 29.00 | -5.65% | 0.32 | 27.59% | 20.00 | 34.66 | -0.08% |
| V4H_STRICT_REC92_25 | ADA | 26.00 | 0.04% | 1.00 | 34.62% | 17.00 | 32.15 | -0.14% |
| V4H_STRICT_REC92_25 | AVAX | 21.00 | 6.57% | 1.81 | 42.86% | 12.00 | 44.24 | -0.13% |
| V4H_STRICT_REC92_25 | BNB | 29.00 | 14.99% | 2.93 | 44.83% | 16.00 | 53.45 | -0.13% |
| V4H_STRICT_REC92_25 | BTC | 7.00 | -0.10% | 0.97 | 42.86% | 4.00 | 42.43 | -0.13% |
| V4H_STRICT_REC92_25 | ETH | 28.00 | 10.61% | 2.28 | 35.71% | 18.00 | 48.18 | -0.13% |
| V4H_STRICT_REC92_25 | LINK | 24.00 | -5.72% | 0.43 | 33.33% | 16.00 | 27.58 | -0.13% |
| V4H_STRICT_REC92_25 | SOL | 34.00 | 12.11% | 1.88 | 38.24% | 21.00 | 47.24 | -0.13% |
| V4H_STRICT_REC92_25 | TON | 8.00 | -2.00% | 0.60 | 50.00% | 4.00 | 21.38 | -0.13% |
| V4H_STRICT_REC92_25 | XRP | 25.00 | -7.53% | 0.37 | 32.00% | 16.00 | 38.36 | -0.13% |
| V4H_STRICT_REC92_15 | ADA | 26.00 | 0.01% | 1.00 | 34.62% | 17.00 | 32.15 | -0.08% |
| V4H_STRICT_REC92_15 | AVAX | 21.00 | 3.76% | 1.80 | 42.86% | 12.00 | 44.24 | -0.08% |
| V4H_STRICT_REC92_15 | BNB | 29.00 | 8.68% | 2.92 | 44.83% | 16.00 | 53.45 | -0.08% |
| V4H_STRICT_REC92_15 | BTC | 7.00 | -0.03% | 0.98 | 42.86% | 4.00 | 42.43 | -0.08% |
| V4H_STRICT_REC92_15 | ETH | 28.00 | 6.36% | 2.32 | 35.71% | 18.00 | 48.18 | -0.08% |
| V4H_STRICT_REC92_15 | LINK | 24.00 | -3.33% | 0.43 | 33.33% | 16.00 | 27.58 | -0.08% |
| V4H_STRICT_REC92_15 | SOL | 34.00 | 7.00% | 1.88 | 38.24% | 21.00 | 47.24 | -0.08% |
| V4H_STRICT_REC92_15 | TON | 8.00 | -1.14% | 0.60 | 50.00% | 4.00 | 21.38 | -0.08% |
| V4H_STRICT_REC92_15 | XRP | 25.00 | -4.32% | 0.37 | 32.00% | 16.00 | 38.36 | -0.08% |
| V4H_STRICT_REC90_25_COOLDOWN | ADA | 28.00 | -2.42% | 0.76 | 32.14% | 19.00 | 32.64 | -0.14% |
| V4H_STRICT_REC90_25_COOLDOWN | AVAX | 23.00 | 12.05% | 2.21 | 39.13% | 14.00 | 52.26 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | BNB | 31.00 | 14.09% | 2.47 | 35.48% | 19.00 | 50.52 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | BTC | 8.00 | 3.24% | 2.07 | 50.00% | 4.00 | 56.12 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | ETH | 34.00 | -3.82% | 0.68 | 23.53% | 26.00 | 30.44 | -0.14% |
| V4H_STRICT_REC90_25_COOLDOWN | LINK | 29.00 | -1.49% | 0.87 | 41.38% | 17.00 | 36.10 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | SOL | 39.00 | 8.01% | 1.53 | 38.46% | 24.00 | 43.36 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | TON | 8.00 | -0.04% | 0.99 | 62.50% | 3.00 | 28.62 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | XRP | 26.00 | -7.58% | 0.33 | 30.77% | 18.00 | 36.31 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | ADA | 31.00 | -0.95% | 0.91 | 35.48% | 20.00 | 30.42 | -0.14% |
| V4H_STRICT_REC90_25_WAIT1 | AVAX | 26.00 | 11.68% | 1.99 | 38.46% | 16.00 | 47.58 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | BNB | 29.00 | 13.33% | 2.73 | 44.83% | 15.00 | 50.41 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | BTC | 7.00 | 4.61% | 3.14 | 57.14% | 3.00 | 63.14 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | ETH | 37.00 | 4.09% | 1.30 | 24.32% | 27.00 | 33.16 | -0.14% |
| V4H_STRICT_REC90_25_WAIT1 | LINK | 30.00 | -5.15% | 0.65 | 33.33% | 20.00 | 32.13 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | SOL | 41.00 | 8.19% | 1.47 | 39.02% | 25.00 | 43.24 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | TON | 9.00 | -1.10% | 0.77 | 55.56% | 4.00 | 24.11 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | XRP | 27.00 | -8.31% | 0.32 | 29.63% | 18.00 | 34.48 | -0.13% |

## BTC/SOL/BNB Recovery Loss Concentration

| Variant | Symbol | Period | Loss trades | Loss PnL | Stops | Worst trade |
|---|---|---|---|---|---|---|
| V4H_STRICT_REC90_25_WAIT1 | SOL | 2024-01 | 3.00 | -2.38% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 2024-01 | 3.00 | -2.35% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | BNB | 2024-08 | 2.00 | -2.33% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25 | BNB | 2024-08 | 2.00 | -2.33% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | BNB | 2024-09 | 2.00 | -2.27% | 2.00 | -0.13% |
| V4H_STRICT_REC92_25 | SOL | 2024-01 | 3.00 | -2.27% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25 | BNB | 2024-09 | 2.00 | -2.26% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | BNB | 2024-08 | 3.00 | -2.17% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | SOL | 2022-12 | 3.00 | -2.06% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 2022-12 | 3.00 | -2.06% | 3.00 | -0.13% |
| V4H_STRICT_REC92_25 | SOL | 2022-12 | 3.00 | -2.01% | 3.00 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 2025-10 | 2.00 | -1.57% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 2021-07 | 4.00 | -1.52% | 4.00 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | SOL | 2021-07 | 4.00 | -1.51% | 4.00 | -0.13% |
| V4H_STRICT_REC92_25 | SOL | 2025-10 | 2.00 | -1.50% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25_WAIT1 | SOL | 2025-10 | 2.00 | -1.47% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25 | SOL | 2023-08 | 2.00 | -1.45% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25_COOLDOWN | SOL | 2025-10 | 2.00 | -1.43% | 2.00 | -0.13% |
| V4H_STRICT_REC90_25 | BNB | 2025-09 | 1.00 | -1.42% | 1.00 | -0.13% |
| V4H_STRICT_REC92_25 | SOL | 2023-08 | 2.00 | -1.40% | 2.00 | -0.13% |

## Transition Summary

| Variant | Transitions | Whipsaw | Transition trades | Transition PnL | Stop 1 | Stop 2 | Stop 3 |
|---|---|---|---|---|---|---|---|
| V0_1D | 495.00 | 267.00 | 929.00 | 115.33% | 37.00 | 47.00 | 56.00 |
| V4H_STRICT_BASE | 495.00 | 267.00 | 1387.00 | 162.87% | 47.00 | 58.00 | 71.00 |
| V4H_STRICT_REC90_25 | 495.00 | 267.00 | 1575.00 | 205.97% | 83.00 | 106.00 | 133.00 |
| V4H_STRICT_REC90_15 | 495.00 | 267.00 | 1575.00 | 195.97% | 83.00 | 106.00 | 133.00 |
| V4H_STRICT_REC92_25 | 495.00 | 267.00 | 1529.00 | 190.81% | 75.00 | 97.00 | 120.00 |
| V4H_STRICT_REC92_15 | 495.00 | 267.00 | 1529.00 | 177.29% | 75.00 | 97.00 | 120.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 495.00 | 267.00 | 1549.00 | 183.11% | 83.00 | 101.00 | 126.00 |
| V4H_STRICT_WAIT1 | 495.00 | 267.00 | 1378.00 | 120.96% | 27.00 | 39.00 | 54.00 |
| V4H_STRICT_REC90_25_WAIT1 | 495.00 | 267.00 | 1555.00 | 139.76% | 50.00 | 73.00 | 104.00 |

## Entries Within 1/2/3 Candles After Transition

| Variant | Window | To regime | Trades | PnL | PF | Stops | Avg hold h |
|---|---|---|---|---|---|---|---|
| V0_1D | 1.00 | uptrend | 10.00 | 21.18% | 3.43 | 5.00 | 54.00 |
| V0_1D | 1.00 | recovery | 20.00 | -5.89% | 0.70 | 11.00 | 41.45 |
| V0_1D | 2.00 | uptrend | 18.00 | 71.00% | 5.94 | 8.00 | 56.78 |
| V0_1D | 2.00 | recovery | 32.00 | -0.32% | 0.99 | 19.00 | 37.38 |
| V0_1D | 3.00 | uptrend | 23.00 | 64.23% | 4.02 | 12.00 | 48.65 |
| V0_1D | 3.00 | recovery | 43.00 | -5.87% | 0.86 | 25.00 | 36.21 |
| V4H_STRICT_BASE | 1.00 | uptrend | 51.00 | 69.05% | 2.12 | 30.00 | 43.24 |
| V4H_STRICT_BASE | 2.00 | uptrend | 80.00 | 140.39% | 2.59 | 47.00 | 47.14 |
| V4H_STRICT_BASE | 3.00 | uptrend | 98.00 | 163.60% | 2.53 | 58.00 | 46.48 |
| V4H_STRICT_REC90_25 | 1.00 | uptrend | 37.00 | 38.48% | 1.73 | 20.00 | 41.81 |
| V4H_STRICT_REC90_25 | 1.00 | recovery | 60.00 | -5.04% | 0.80 | 39.00 | 39.60 |
| V4H_STRICT_REC90_25 | 2.00 | uptrend | 60.00 | 100.96% | 2.38 | 31.00 | 47.12 |
| V4H_STRICT_REC90_25 | 2.00 | recovery | 87.00 | 3.12% | 1.09 | 52.00 | 43.21 |
| V4H_STRICT_REC90_25 | 3.00 | uptrend | 73.00 | 93.21% | 2.04 | 40.00 | 44.64 |
| V4H_STRICT_REC90_25 | 3.00 | recovery | 105.00 | -3.63% | 0.91 | 66.00 | 40.40 |
| V4H_STRICT_REC90_15 | 1.00 | uptrend | 37.00 | 36.77% | 1.72 | 20.00 | 41.81 |
| V4H_STRICT_REC90_15 | 1.00 | recovery | 60.00 | -2.92% | 0.80 | 39.00 | 39.60 |
| V4H_STRICT_REC90_15 | 2.00 | uptrend | 60.00 | 97.90% | 2.38 | 31.00 | 47.12 |
| V4H_STRICT_REC90_15 | 2.00 | recovery | 87.00 | 1.83% | 1.09 | 52.00 | 43.21 |
| V4H_STRICT_REC90_15 | 3.00 | uptrend | 73.00 | 90.57% | 2.04 | 40.00 | 44.64 |
| V4H_STRICT_REC90_15 | 3.00 | recovery | 105.00 | -2.11% | 0.91 | 66.00 | 40.40 |
| V4H_STRICT_REC92_25 | 1.00 | uptrend | 39.00 | 32.39% | 1.58 | 22.00 | 40.15 |
| V4H_STRICT_REC92_25 | 1.00 | recovery | 51.00 | -2.78% | 0.87 | 32.00 | 42.69 |
| V4H_STRICT_REC92_25 | 2.00 | uptrend | 61.00 | 94.68% | 2.25 | 33.00 | 46.46 |
| V4H_STRICT_REC92_25 | 2.00 | recovery | 71.00 | 5.11% | 1.19 | 42.00 | 44.90 |
| V4H_STRICT_REC92_25 | 3.00 | uptrend | 75.00 | 82.88% | 1.86 | 43.00 | 43.57 |
| V4H_STRICT_REC92_25 | 3.00 | recovery | 86.00 | -0.34% | 0.99 | 54.00 | 41.69 |
| V4H_STRICT_REC92_15 | 1.00 | uptrend | 39.00 | 30.79% | 1.57 | 22.00 | 40.15 |
| V4H_STRICT_REC92_15 | 1.00 | recovery | 51.00 | -1.62% | 0.87 | 32.00 | 42.69 |
| V4H_STRICT_REC92_15 | 2.00 | uptrend | 61.00 | 91.72% | 2.24 | 33.00 | 46.46 |
| V4H_STRICT_REC92_15 | 2.00 | recovery | 71.00 | 2.97% | 1.19 | 42.00 | 44.90 |
| V4H_STRICT_REC92_15 | 3.00 | uptrend | 75.00 | 80.48% | 1.86 | 43.00 | 43.57 |
| V4H_STRICT_REC92_15 | 3.00 | recovery | 86.00 | -0.22% | 0.99 | 54.00 | 41.69 |
| V4H_STRICT_REC90_25_COOLDOWN | 1.00 | uptrend | 39.00 | 36.14% | 1.71 | 21.00 | 40.95 |
| V4H_STRICT_REC90_25_COOLDOWN | 1.00 | recovery | 58.00 | -4.77% | 0.80 | 39.00 | 39.93 |
| V4H_STRICT_REC90_25_COOLDOWN | 2.00 | uptrend | 62.00 | 95.19% | 2.36 | 32.00 | 46.40 |
| V4H_STRICT_REC90_25_COOLDOWN | 2.00 | recovery | 82.00 | 1.66% | 1.05 | 51.00 | 43.57 |
| V4H_STRICT_REC90_25_COOLDOWN | 3.00 | uptrend | 76.00 | 87.51% | 2.02 | 42.00 | 43.57 |
| V4H_STRICT_REC90_25_COOLDOWN | 3.00 | recovery | 92.00 | -2.23% | 0.94 | 59.00 | 42.72 |
| V4H_STRICT_WAIT1 | 2.00 | uptrend | 52.00 | 101.65% | 2.99 | 27.00 | 50.75 |
| V4H_STRICT_WAIT1 | 3.00 | uptrend | 70.00 | 122.22% | 2.69 | 39.00 | 48.14 |
| V4H_STRICT_REC90_25_WAIT1 | 2.00 | uptrend | 39.00 | 46.76% | 2.08 | 20.00 | 46.62 |
| V4H_STRICT_REC90_25_WAIT1 | 2.00 | recovery | 54.00 | 0.07% | 1.00 | 30.00 | 45.76 |
| V4H_STRICT_REC90_25_WAIT1 | 3.00 | uptrend | 52.00 | 39.39% | 1.66 | 29.00 | 43.27 |
| V4H_STRICT_REC90_25_WAIT1 | 3.00 | recovery | 74.00 | -0.62% | 0.98 | 44.00 | 43.69 |

## Yearly Performance

| Variant | Year | Return |
|---|---|---|
| V0_1D | 2020 | 109.28% |
| V0_1D | 2021 | 63.67% |
| V0_1D | 2022 | 0.00% |
| V0_1D | 2023 | 39.51% |
| V0_1D | 2024 | 0.23% |
| V0_1D | 2025 | 7.42% |
| V4H_STRICT_BASE | 2020 | 105.15% |
| V4H_STRICT_BASE | 2021 | 126.39% |
| V4H_STRICT_BASE | 2022 | -8.14% |
| V4H_STRICT_BASE | 2023 | 71.78% |
| V4H_STRICT_BASE | 2024 | 11.41% |
| V4H_STRICT_BASE | 2025 | 1.64% |
| V4H_STRICT_REC90_15 | 2020 | 119.68% |
| V4H_STRICT_REC90_15 | 2021 | 132.19% |
| V4H_STRICT_REC90_15 | 2022 | -4.80% |
| V4H_STRICT_REC90_15 | 2023 | 70.22% |
| V4H_STRICT_REC90_15 | 2024 | 10.83% |
| V4H_STRICT_REC90_15 | 2025 | 1.27% |
| V4H_STRICT_REC90_25 | 2020 | 125.14% |
| V4H_STRICT_REC90_25 | 2021 | 131.65% |
| V4H_STRICT_REC90_25 | 2022 | -4.30% |
| V4H_STRICT_REC90_25 | 2023 | 71.66% |
| V4H_STRICT_REC90_25 | 2024 | 11.42% |
| V4H_STRICT_REC90_25 | 2025 | 1.95% |
| V4H_STRICT_REC90_25_COOLDOWN | 2020 | 112.21% |
| V4H_STRICT_REC90_25_COOLDOWN | 2021 | 131.21% |
| V4H_STRICT_REC90_25_COOLDOWN | 2022 | -4.11% |
| V4H_STRICT_REC90_25_COOLDOWN | 2023 | 67.87% |
| V4H_STRICT_REC90_25_COOLDOWN | 2024 | 11.75% |
| V4H_STRICT_REC90_25_COOLDOWN | 2025 | 2.42% |
| V4H_STRICT_REC90_25_WAIT1 | 2020 | 126.74% |
| V4H_STRICT_REC90_25_WAIT1 | 2021 | 134.10% |
| V4H_STRICT_REC90_25_WAIT1 | 2022 | -5.41% |
| V4H_STRICT_REC90_25_WAIT1 | 2023 | 73.43% |
| V4H_STRICT_REC90_25_WAIT1 | 2024 | 10.14% |
| V4H_STRICT_REC90_25_WAIT1 | 2025 | -5.41% |
| V4H_STRICT_REC92_15 | 2020 | 119.70% |
| V4H_STRICT_REC92_15 | 2021 | 127.84% |
| V4H_STRICT_REC92_15 | 2022 | -5.61% |
| V4H_STRICT_REC92_15 | 2023 | 68.79% |
| V4H_STRICT_REC92_15 | 2024 | 10.51% |
| V4H_STRICT_REC92_15 | 2025 | 1.08% |
| V4H_STRICT_REC92_25 | 2020 | 125.19% |
| V4H_STRICT_REC92_25 | 2021 | 127.47% |
| V4H_STRICT_REC92_25 | 2022 | -5.12% |
| V4H_STRICT_REC92_25 | 2023 | 70.17% |
| V4H_STRICT_REC92_25 | 2024 | 11.00% |
| V4H_STRICT_REC92_25 | 2025 | 2.11% |
| V4H_STRICT_WAIT1 | 2020 | 106.48% |
| V4H_STRICT_WAIT1 | 2021 | 131.81% |
| V4H_STRICT_WAIT1 | 2022 | -9.16% |
| V4H_STRICT_WAIT1 | 2023 | 72.95% |
| V4H_STRICT_WAIT1 | 2024 | 10.79% |
| V4H_STRICT_WAIT1 | 2025 | -4.56% |

## Worst Monthly Returns

| Variant | Month | Return |
|---|---|---|
| V4H_STRICT_WAIT1 | 2025-06 | -8.17% |
| V4H_STRICT_BASE | 2025-06 | -8.17% |
| V4H_STRICT_REC92_15 | 2025-06 | -8.15% |
| V4H_STRICT_REC90_25_WAIT1 | 2025-06 | -8.15% |
| V4H_STRICT_REC92_25 | 2025-06 | -8.14% |
| V4H_STRICT_REC90_25_COOLDOWN | 2025-06 | -8.14% |
| V4H_STRICT_REC90_15 | 2025-06 | -8.14% |
| V4H_STRICT_REC90_25 | 2025-06 | -8.13% |
| V0_1D | 2025-06 | -8.11% |
| V0_1D | 2024-05 | -6.94% |
| V0_1D | 2023-08 | -6.56% |
| V4H_STRICT_WAIT1 | 2025-04 | -6.13% |
| V4H_STRICT_REC90_25_WAIT1 | 2025-04 | -6.00% |
| V4H_STRICT_REC92_25 | 2024-04 | -5.47% |
| V4H_STRICT_REC90_25_WAIT1 | 2024-04 | -5.47% |
| V4H_STRICT_REC90_25_COOLDOWN | 2024-04 | -5.46% |
| V4H_STRICT_REC90_25 | 2024-04 | -5.46% |
| V4H_STRICT_REC92_15 | 2024-04 | -5.42% |
| V4H_STRICT_REC90_15 | 2024-04 | -5.41% |
| V4H_STRICT_BASE | 2024-04 | -5.36% |

## Checksum / Leakage Notes

- Existing audit script HEAD blob: `90dfe623c120ad8695d1f61aa6f29bbffb822798`; working-tree blob: `90dfe623c120ad8695d1f61aa6f29bbffb822798`.
- Existing audit report HEAD blob: `3a5cc92a8f26886e6369811ce886f6bf3bebbe07`; working-tree blob: `3a5cc92a8f26886e6369811ce886f6bf3bebbe07`.
- All generated trades retain `lookahead_pass=True`; entry timestamps are at or after the 4H close signal timestamp.
- WAIT1 and transition analyses use only current and prior 4H regime rows; no future candle is used for entry eligibility.

## Artifacts

- `v4h_strict_selective_recovery_report.md`
- `v4h_strict_selective_recovery_summary.csv`
- `v4h_strict_selective_recovery_cost_stress.csv`
- `v4h_strict_selective_recovery_recovery_trades.csv`
- `v4h_strict_selective_recovery_symbol_analysis.csv`
- `v4h_strict_selective_recovery_transition_analysis.csv`
- `v4h_strict_selective_recovery_equity_curves.csv`
