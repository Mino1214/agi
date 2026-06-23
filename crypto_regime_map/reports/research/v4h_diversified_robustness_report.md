# V4H Diversified Robustness Report

## Scope

- Read-only audit/report only. Strategy modules, paper engine, live order logic, main checkout/merge, commit, and push were not touched.
- Existing `V4H_STRICT_REC92_25` robustness FAIL is preserved as-is; this audit writes only `v4h_diversified_*` outputs.
- Diversification cap used in this audit: existing same-symbol simultaneous position limit = 1, plus rolling 30D max 2 new entries per symbol for diversified variants.
- Concentration failure thresholds: top1 positive PnL share > 35%, top2 positive PnL share > 55%, or recovery top1 positive PnL share > 40%.

## PASS/WATCH/FAIL

| Variant | Status | Reasons | Return | CAGR | MDD | Calmar | PF | Trades | Top1 | Top2 | Recovery top1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_BASELINE | BASELINE | baseline | 414.55% | 31.38% | -28.14% | 1.12 | 1.11 | 929.00 | 17.54% | 32.86% | 0.00% |
| V4H_STRICT_BASE | FAIL | bear PnL worse than V0; sideways PnL worse than V0; 2x fee/slippage <= V0; 3x cost stress weak; 5x cost stress weak | 729.80% | 42.27% | -27.45% | 1.54 | 1.08 | 1387.00 | 15.62% | 31.08% | 0.00% |
| V4H_STRICT_REC92_25 | FAIL | bear PnL worse than V0; sideways PnL worse than V0; 3x cost stress weak; 5x cost stress weak | 871.82% | 46.07% | -26.52% | 1.74 | 1.09 | 1515.00 | 16.40% | 30.78% | 23.19% |
| V4H_STRICT_REC92_15 | FAIL | bear PnL worse than V0; sideways PnL worse than V0; 3x cost stress weak; 5x cost stress weak | 815.17% | 44.62% | -26.61% | 1.68 | 1.09 | 1515.00 | 16.27% | 30.54% | 23.04% |
| V4H_STRICT_REC90_25_COOLDOWN | FAIL | bear PnL worse than V0; sideways PnL worse than V0; 3x cost stress weak; 5x cost stress weak | 838.82% | 45.23% | -26.69% | 1.69 | 1.09 | 1540.00 | 15.54% | 30.06% | 22.50% |
| V4H_REC92_15_DIVERSIFIED | FAIL | base return/CAGR not above V0; SOL removal Calmar <= V0; SOL+BNB removal return <= V0; bear PnL worse than V0; 2x fee/slippage <= V0; BNB removal edge weakened; 3x cost stress weak; 5x cost stress weak | 161.48% | 17.37% | -14.30% | 1.21 | 1.22 | 678.00 | 16.04% | 30.68% | 27.11% |
| V4H_REC92_10_DIVERSIFIED | FAIL | base return/CAGR not above V0; SOL removal Calmar <= V0; SOL+BNB removal return <= V0; bear PnL worse than V0; 2x fee/slippage <= V0; BNB removal edge weakened; 3x cost stress weak; 5x cost stress weak | 156.87% | 17.02% | -14.51% | 1.17 | 1.21 | 678.00 | 16.09% | 30.72% | 27.04% |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | FAIL | base return/CAGR not above V0; SOL removal Calmar <= V0; SOL+BNB removal return <= V0; bear PnL worse than V0; 2x fee/slippage <= V0; BNB removal edge weakened; 3x cost stress weak; 5x cost stress weak | 125.73% | 14.53% | -14.51% | 1.00 | 1.14 | 692.00 | 17.16% | 32.16% | 24.05% |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | FAIL | base return/CAGR not above V0; SOL removal Calmar <= V0; SOL+BNB removal return <= V0; bear PnL worse than V0; 2x fee/slippage <= V0; BNB removal edge weakened; 3x cost stress weak; 5x cost stress weak | 112.42% | 13.38% | -14.97% | 0.89 | 1.09 | 587.00 | 16.98% | 33.37% | 0.00% |

## Diversified Candidates

| Variant | Return vs V0 | MDD extra vs V0 | Calmar vs V0 | Trades vs REC92_25 | MDD vs REC92_25 | Calmar vs REC92_25 |
|---|---|---|---|---|---|---|
| V4H_REC92_15_DIVERSIFIED | -253.08% | -13.84% | 0.10 | -837.00 | 12.22% | -0.52 |
| V4H_REC92_10_DIVERSIFIED | -257.68% | -13.62% | 0.06 | -837.00 | 12.00% | -0.56 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | -288.82% | -13.62% | -0.11 | -823.00 | 12.00% | -0.74 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | -302.13% | -13.16% | -0.22 | -928.00 | 11.54% | -0.84 |

## Leave-SOL/BNB-Out

| Variant | Excluded | Return | Calmar | Return vs V0 same exclusion | Calmar vs V0 same exclusion | Return delta vs full |
|---|---|---|---|---|---|---|
| V4H_REC92_15_DIVERSIFIED | SOL | 133.56% | 0.68 | -195.24% | -0.32 | -27.92% |
| V4H_REC92_10_DIVERSIFIED | SOL | 129.88% | 0.65 | -198.92% | -0.36 | -26.99% |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | SOL | 162.70% | 0.91 | -166.10% | -0.10 | 36.97% |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | SOL | 118.77% | 0.71 | -210.04% | -0.30 | 6.34% |
| V4H_REC92_15_DIVERSIFIED | BNB | 143.16% | 1.18 | -122.66% | 0.36 | -18.32% |
| V4H_REC92_10_DIVERSIFIED | BNB | 137.91% | 1.13 | -127.91% | 0.31 | -18.96% |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | BNB | 114.96% | 1.13 | -150.86% | 0.31 | -10.77% |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | BNB | 100.00% | 1.06 | -165.82% | 0.24 | -12.43% |
| V4H_REC92_15_DIVERSIFIED | SOL+BNB | 97.48% | 1.33 | -101.24% | 0.68 | -64.00% |
| V4H_REC92_10_DIVERSIFIED | SOL+BNB | 95.66% | 1.34 | -103.06% | 0.69 | -61.22% |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | SOL+BNB | 89.62% | 1.26 | -109.10% | 0.61 | -36.12% |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | SOL+BNB | 76.32% | 0.70 | -122.40% | 0.05 | -36.11% |

## Symbol Concentration

| Variant | Top1 symbol | Top1 share | Top2 share | Recovery top1 symbol | Recovery top1 share | Fail |
|---|---|---|---|---|---|---|
| V0_BASELINE | BNB | 17.54% | 32.86% | ADA | 0.00% | false |
| V4H_STRICT_BASE | SOL | 15.62% | 31.08% | ADA | 0.00% | false |
| V4H_STRICT_REC92_25 | SOL | 16.40% | 30.78% | SOL | 23.19% | false |
| V4H_STRICT_REC92_15 | SOL | 16.27% | 30.54% | SOL | 23.04% | false |
| V4H_STRICT_REC90_25_COOLDOWN | SOL | 15.54% | 30.06% | BNB | 22.50% | false |
| V4H_REC92_15_DIVERSIFIED | ADA | 16.04% | 30.68% | SOL | 27.11% | false |
| V4H_REC92_10_DIVERSIFIED | ADA | 16.09% | 30.72% | SOL | 27.04% | false |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | ADA | 17.16% | 32.16% | AVAX | 24.05% | false |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | ETH | 16.98% | 33.37% | ADA | 0.00% | false |

## Cost Stress

| Variant | Cost | Return | MDD | Calmar | Return vs V0 | Calmar vs V0 |
|---|---|---|---|---|---|---|
| V0_BASELINE | 1.00 | 414.55% | -28.14% | 1.12 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 1.00 | 729.80% | -27.45% | 1.54 | 315.25% | 0.42 |
| V4H_STRICT_REC92_25 | 1.00 | 871.82% | -26.52% | 1.74 | 457.27% | 0.62 |
| V4H_STRICT_REC92_15 | 1.00 | 815.17% | -26.61% | 1.68 | 400.61% | 0.56 |
| V4H_STRICT_REC90_25_COOLDOWN | 1.00 | 838.82% | -26.69% | 1.69 | 424.27% | 0.58 |
| V4H_REC92_15_DIVERSIFIED | 1.00 | 161.48% | -14.30% | 1.21 | -253.08% | 0.10 |
| V4H_REC92_10_DIVERSIFIED | 1.00 | 156.87% | -14.51% | 1.17 | -257.68% | 0.06 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 1.00 | 125.73% | -14.51% | 1.00 | -288.82% | -0.11 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 1.00 | 112.42% | -14.97% | 0.89 | -302.13% | -0.22 |
| V0_BASELINE | 2.00 | 30.18% | -53.74% | 0.08 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 2.00 | 27.31% | -61.03% | 0.07 | -2.87% | -0.02 |
| V4H_STRICT_REC92_25 | 2.00 | 43.83% | -59.04% | 0.11 | 13.65% | 0.02 |
| V4H_STRICT_REC92_15 | 2.00 | 40.76% | -59.10% | 0.10 | 10.58% | 0.02 |
| V4H_STRICT_REC90_25_COOLDOWN | 2.00 | 41.59% | -59.33% | 0.10 | 11.41% | 0.02 |
| V4H_REC92_15_DIVERSIFIED | 2.00 | 22.96% | -27.92% | 0.13 | -7.22% | 0.04 |
| V4H_REC92_10_DIVERSIFIED | 2.00 | 22.16% | -27.99% | 0.12 | -8.02% | 0.04 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2.00 | 8.50% | -28.56% | 0.05 | -21.68% | -0.04 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2.00 | 0.99% | -31.31% | 0.01 | -29.19% | -0.08 |
| V0_BASELINE | 3.00 | -78.90% | -86.84% | -0.26 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 3.00 | -91.63% | -95.43% | -0.35 | -12.73% | -0.09 |
| V4H_STRICT_REC92_25 | 3.00 | -91.26% | -94.91% | -0.35 | -12.36% | -0.09 |
| V4H_STRICT_REC92_15 | 3.00 | -90.61% | -94.50% | -0.34 | -11.70% | -0.08 |
| V4H_STRICT_REC90_25_COOLDOWN | 3.00 | -90.33% | -94.60% | -0.34 | -11.43% | -0.08 |
| V4H_REC92_15_DIVERSIFIED | 3.00 | -42.20% | -55.94% | -0.16 | 36.70% | 0.11 |
| V4H_REC92_10_DIVERSIFIED | 3.00 | -41.57% | -55.54% | -0.15 | 37.33% | 0.11 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 3.00 | -51.87% | -58.35% | -0.20 | 27.03% | 0.07 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 3.00 | -50.91% | -60.56% | -0.18 | 27.99% | 0.08 |
| V0_BASELINE | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_STRICT_REC92_25 | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_STRICT_REC92_15 | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_REC92_15_DIVERSIFIED | 5.00 | -83.00% | -84.31% | -0.30 | 17.00% | 0.67 |
| V4H_REC92_10_DIVERSIFIED | 5.00 | -82.49% | -83.85% | -0.30 | 17.51% | 0.67 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 5.00 | -84.30% | -85.63% | -0.31 | 15.70% | 0.66 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 5.00 | -88.90% | -88.90% | -0.34 | 11.10% | 0.62 |

## Yearly OOS

| Variant | Year | Return | CAGR | MDD | Calmar | PF | Win | Trades |
|---|---|---|---|---|---|---|---|---|
| V0_BASELINE | 2020.00 | 108.95% | 108.64% | -11.57% | 9.39 | 2.20 | 41.21% | 165.00 |
| V0_BASELINE | 2021.00 | 63.93% | 63.99% | -7.01% | 9.13 | 2.18 | 44.63% | 121.00 |
| V0_BASELINE | 2022.00 | 0.00% | 0.00% | 0.00% |  |  | 0.00% | 0.00 |
| V0_BASELINE | 2023.00 | 39.83% | 39.86% | -11.39% | 3.50 | 1.30 | 36.26% | 182.00 |
| V0_BASELINE | 2024.00 | 0.05% | 0.05% | -24.11% | 0.00 | 0.78 | 27.13% | 247.00 |
| V0_BASELINE | 2025.00 | 7.38% | 7.38% | -22.33% | 0.33 | 0.89 | 29.91% | 214.00 |
| V4H_STRICT_BASE | 2020.00 | 104.89% | 104.59% | -8.35% | 12.53 | 1.91 | 43.36% | 226.00 |
| V4H_STRICT_BASE | 2021.00 | 126.67% | 126.80% | -9.77% | 12.97 | 1.84 | 41.20% | 250.00 |
| V4H_STRICT_BASE | 2022.00 | -8.14% | -8.15% | -11.59% | -0.70 | 0.54 | 23.30% | 103.00 |
| V4H_STRICT_BASE | 2023.00 | 72.18% | 72.24% | -14.08% | 5.13 | 1.36 | 37.26% | 314.00 |
| V4H_STRICT_BASE | 2024.00 | 11.15% | 11.13% | -22.41% | 0.50 | 0.90 | 32.62% | 282.00 |
| V4H_STRICT_BASE | 2025.00 | 1.64% | 1.64% | -23.17% | 0.07 | 0.83 | 30.66% | 212.00 |
| V4H_STRICT_REC92_25 | 2020.00 | 128.07% | 127.69% | -8.35% | 15.30 | 2.18 | 46.58% | 234.00 |
| V4H_STRICT_REC92_25 | 2021.00 | 127.95% | 128.08% | -9.77% | 13.11 | 1.83 | 40.22% | 271.00 |
| V4H_STRICT_REC92_25 | 2022.00 | -3.28% | -3.29% | -7.74% | -0.42 | 0.64 | 30.37% | 135.00 |
| V4H_STRICT_REC92_25 | 2023.00 | 71.69% | 71.75% | -14.10% | 5.09 | 1.38 | 39.02% | 328.00 |
| V4H_STRICT_REC92_25 | 2024.00 | 10.51% | 10.48% | -22.73% | 0.46 | 0.89 | 33.44% | 305.00 |
| V4H_STRICT_REC92_25 | 2025.00 | 1.87% | 1.87% | -23.21% | 0.08 | 0.81 | 31.82% | 242.00 |
| V4H_STRICT_REC92_15 | 2020.00 | 121.38% | 121.02% | -8.34% | 14.51 | 2.14 | 46.58% | 234.00 |
| V4H_STRICT_REC92_15 | 2021.00 | 128.25% | 128.38% | -9.77% | 13.14 | 1.84 | 40.22% | 271.00 |
| V4H_STRICT_REC92_15 | 2022.00 | -4.05% | -4.05% | -7.74% | -0.52 | 0.61 | 30.37% | 135.00 |
| V4H_STRICT_REC92_15 | 2023.00 | 69.83% | 69.89% | -14.09% | 4.96 | 1.37 | 39.02% | 328.00 |
| V4H_STRICT_REC92_15 | 2024.00 | 10.12% | 10.09% | -23.04% | 0.44 | 0.89 | 33.44% | 305.00 |
| V4H_STRICT_REC92_15 | 2025.00 | 0.94% | 0.94% | -23.17% | 0.04 | 0.80 | 31.82% | 242.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2020.00 | 116.28% | 115.94% | -8.34% | 13.90 | 2.03 | 44.90% | 245.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2021.00 | 131.36% | 131.49% | -9.77% | 13.46 | 1.87 | 41.03% | 273.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2022.00 | -2.27% | -2.28% | -6.71% | -0.34 | 0.66 | 31.91% | 141.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2023.00 | 68.90% | 68.96% | -12.78% | 5.39 | 1.37 | 38.48% | 330.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2024.00 | 11.25% | 11.23% | -22.88% | 0.49 | 0.90 | 33.22% | 304.00 |
| V4H_STRICT_REC90_25_COOLDOWN | 2025.00 | 2.17% | 2.17% | -23.49% | 0.09 | 0.81 | 31.17% | 247.00 |
| V4H_REC92_15_DIVERSIFIED | 2020.00 | 31.76% | 31.68% | -7.94% | 3.99 | 1.77 | 40.74% | 108.00 |
| V4H_REC92_15_DIVERSIFIED | 2021.00 | 36.19% | 36.21% | -8.05% | 4.50 | 1.66 | 40.68% | 118.00 |
| V4H_REC92_15_DIVERSIFIED | 2022.00 | -1.49% | -1.49% | -5.55% | -0.27 | 0.68 | 34.57% | 81.00 |
| V4H_REC92_15_DIVERSIFIED | 2023.00 | 35.66% | 35.69% | -7.40% | 4.83 | 1.79 | 42.19% | 128.00 |
| V4H_REC92_15_DIVERSIFIED | 2024.00 | 4.07% | 4.06% | -10.11% | 0.40 | 0.83 | 33.08% | 130.00 |
| V4H_REC92_15_DIVERSIFIED | 2025.00 | 4.78% | 4.78% | -6.91% | 0.69 | 0.90 | 34.51% | 113.00 |
| V4H_REC92_10_DIVERSIFIED | 2020.00 | 31.42% | 31.34% | -7.94% | 3.95 | 1.78 | 40.74% | 108.00 |
| V4H_REC92_10_DIVERSIFIED | 2021.00 | 36.03% | 36.06% | -8.05% | 4.48 | 1.66 | 40.68% | 118.00 |
| V4H_REC92_10_DIVERSIFIED | 2022.00 | -1.83% | -1.83% | -5.61% | -0.33 | 0.67 | 34.57% | 81.00 |
| V4H_REC92_10_DIVERSIFIED | 2023.00 | 34.96% | 34.99% | -7.40% | 4.73 | 1.78 | 42.19% | 128.00 |
| V4H_REC92_10_DIVERSIFIED | 2024.00 | 3.82% | 3.81% | -10.27% | 0.37 | 0.83 | 33.08% | 130.00 |
| V4H_REC92_10_DIVERSIFIED | 2025.00 | 4.47% | 4.47% | -6.86% | 0.65 | 0.89 | 34.51% | 113.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2020.00 | 26.28% | 26.22% | -8.32% | 3.15 | 1.52 | 37.84% | 111.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2021.00 | 32.38% | 32.41% | -8.17% | 3.97 | 1.56 | 40.65% | 123.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2022.00 | 0.03% | 0.03% | -5.19% | 0.01 | 0.76 | 36.90% | 84.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2023.00 | 23.25% | 23.27% | -7.38% | 3.15 | 1.40 | 37.69% | 130.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2024.00 | 4.73% | 4.72% | -9.88% | 0.48 | 0.85 | 33.08% | 130.00 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | 2025.00 | 4.58% | 4.58% | -9.39% | 0.49 | 0.89 | 32.46% | 114.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2020.00 | 22.19% | 22.14% | -9.31% | 2.38 | 1.38 | 32.04% | 103.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2021.00 | 43.22% | 43.26% | -5.90% | 7.33 | 1.88 | 43.27% | 104.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2022.00 | -8.21% | -8.22% | -9.30% | -0.88 | 0.40 | 17.24% | 58.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2023.00 | 28.04% | 28.06% | -10.16% | 2.76 | 1.52 | 35.45% | 110.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2024.00 | 3.02% | 3.01% | -10.28% | 0.29 | 0.81 | 32.50% | 120.00 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | 2025.00 | 0.26% | 0.26% | -7.01% | 0.04 | 0.73 | 33.70% | 92.00 |

## Bull / Bear / Sideways

| Variant | State | PnL | PF | Win | Trades | Avg R |
|---|---|---|---|---|---|---|
| V0_BASELINE | bull | 175.91% | 1.24 | 36.98% | 695.00 | 0.24 |
| V0_BASELINE | bear | -2.33% | 0.00 | 0.00% | 1.00 | -1.03 |
| V0_BASELINE | sideways | -58.25% | 0.80 | 26.61% | 233.00 | 0.12 |
| V4H_STRICT_BASE | bull | 306.26% | 1.21 | 37.90% | 1066.00 | 0.22 |
| V4H_STRICT_BASE | bear | -38.37% | 0.47 | 21.74% | 69.00 | -0.22 |
| V4H_STRICT_BASE | sideways | -105.02% | 0.77 | 31.75% | 252.00 | -0.03 |
| V4H_STRICT_REC92_25 | bull | 323.10% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_STRICT_REC92_25 | bear | -31.02% | 0.71 | 36.24% | 149.00 | 0.10 |
| V4H_STRICT_REC92_25 | sideways | -89.03% | 0.81 | 37.02% | 289.00 | 0.21 |
| V4H_STRICT_REC92_15 | bull | 311.61% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_STRICT_REC92_15 | bear | -30.53% | 0.66 | 36.24% | 149.00 | 0.10 |
| V4H_STRICT_REC92_15 | sideways | -94.86% | 0.79 | 37.02% | 289.00 | 0.21 |
| V4H_STRICT_REC90_25_COOLDOWN | bull | 325.89% | 1.20 | 38.03% | 1086.00 | 0.22 |
| V4H_STRICT_REC90_25_COOLDOWN | bear | -34.41% | 0.68 | 33.13% | 166.00 | 0.02 |
| V4H_STRICT_REC90_25_COOLDOWN | sideways | -97.22% | 0.78 | 36.33% | 289.00 | 0.06 |
| V4H_REC92_15_DIVERSIFIED | bull | 67.46% | 1.32 | 36.71% | 414.00 | 0.20 |
| V4H_REC92_15_DIVERSIFIED | bear | -3.33% | 0.82 | 41.35% | 104.00 | 0.21 |
| V4H_REC92_15_DIVERSIFIED | sideways | -0.57% | 0.99 | 38.51% | 161.00 | 0.14 |
| V4H_REC92_10_DIVERSIFIED | bull | 66.95% | 1.32 | 36.71% | 414.00 | 0.20 |
| V4H_REC92_10_DIVERSIFIED | bear | -4.16% | 0.75 | 41.35% | 104.00 | 0.21 |
| V4H_REC92_10_DIVERSIFIED | sideways | -1.26% | 0.98 | 38.51% | 161.00 | 0.14 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | bull | 42.99% | 1.22 | 36.10% | 421.00 | 0.16 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | bear | -2.63% | 0.88 | 37.17% | 113.00 | 0.07 |
| V4H_REC90_25_COOLDOWN_DIVERSIFIED | sideways | -2.48% | 0.96 | 37.11% | 159.00 | 0.12 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | bull | 45.36% | 1.25 | 37.22% | 403.00 | 0.16 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | bear | -9.53% | 0.56 | 19.57% | 46.00 | -0.19 |
| V4H_STRICT_NO_RECOVERY_DIVERSIFIED | sideways | -10.63% | 0.87 | 27.54% | 138.00 | 0.01 |

## Output Files

- `reports/research/v4h_diversified_robustness_report.md`
- `reports/research/v4h_diversified_summary.csv`
- `reports/research/v4h_diversified_leave_one_symbol.csv`
- `reports/research/v4h_diversified_symbol_concentration.csv`
- `reports/research/v4h_diversified_cost_stress.csv`
- `reports/research/v4h_diversified_oos_yearly.csv`
- `reports/research/v4h_diversified_regime_performance.csv`
