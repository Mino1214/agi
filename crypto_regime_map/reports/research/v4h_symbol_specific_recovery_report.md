# V4H Symbol-Specific Recovery Control Audit

## Scope

- Read-only audit/report only. Existing strategy, paper engine, live order logic, main checkout/merge, commit, and push were not touched.
- Existing `V4H_STRICT_REC92_25` robustness FAIL and diversified FAIL reports are preserved by checksum.
- New variants keep SOL/BNB in the universe and only change recovery score/size/cooldown for SOL/BNB recovery entries.

## PASS/WATCH/FAIL

| Variant | Status | Reasons | Return | CAGR | MDD | Calmar | PF | Trades | Top1 | Top2 |
|---|---|---|---|---|---|---|---|---|---|---|
| V0_BASELINE | BASELINE | baseline | 414.55% | 31.38% | -28.14% | 1.12 | 1.11 | 929.00 | 17.54% | 32.86% |
| V4H_STRICT_BASE | FAIL | 2x fee/slippage weaker than V0; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 729.80% | 42.27% | -27.45% | 1.54 | 1.08 | 1387.00 | 15.62% | 31.08% |
| V4H_STRICT_REC92_25 | WATCH | SOL removal edge still large; BNB removal edge still large; SOL+BNB removal edge still large; 3x cost stress weak | 871.82% | 46.07% | -26.52% | 1.74 | 1.09 | 1515.00 | 16.40% | 30.78% |
| V4H_REC92_15_DIVERSIFIED | FAIL | 2x fee/slippage weaker than V0; base return/CAGR not above V0; 3x cost stress weak | 161.48% | 17.37% | -14.30% | 1.21 | 1.22 | 678.00 | 16.04% | 30.68% |
| V4H_REC92_25_SOLBNB_94_15 | WATCH | SOL removal edge still large; BNB removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 848.54% | 45.48% | -26.68% | 1.70 | 1.09 | 1515.00 | 16.13% | 30.26% |
| V4H_REC92_25_SOLBNB_95_10 | WATCH | SOL removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 837.06% | 45.19% | -26.77% | 1.69 | 1.08 | 1515.00 | 16.00% | 30.00% |
| V4H_REC92_20_SOLBNB_94_15 | WATCH | SOL removal edge still large; BNB removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 831.79% | 45.05% | -26.65% | 1.69 | 1.09 | 1515.00 | 16.20% | 30.40% |
| V4H_REC92_25_SOLBNB_COOLDOWN | FAIL | top1 contribution not reduced vs REC92_25; SOL removal edge still large; BNB removal edge still large; SOL+BNB removal edge still large; 3x cost stress weak | 872.76% | 46.09% | -26.43% | 1.74 | 1.09 | 1510.00 | 16.42% | 30.79% |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | WATCH | SOL removal edge still large; BNB removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 849.09% | 45.49% | -26.63% | 1.71 | 1.09 | 1510.00 | 16.14% | 30.27% |
| V4H_REC92_15_ALL | WATCH | SOL removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 815.17% | 44.62% | -26.61% | 1.68 | 1.09 | 1515.00 | 16.27% | 30.54% |
| V4H_REC94_15_ALL | WATCH | SOL removal edge still large; SOL+BNB removal edge still large; 2022/2025 not improved; 3x cost stress weak | 815.17% | 44.62% | -26.61% | 1.68 | 1.09 | 1515.00 | 16.27% | 30.54% |

## SOL/BNB Leave-Out

| Variant | Excluded | Return | Calmar | Return delta vs full | Return vs V0 same exclusion | Calmar vs V0 same exclusion |
|---|---|---|---|---|---|---|
| V4H_REC92_25_SOLBNB_94_15 | SOL | 525.06% | 1.29 | -323.48% | 196.26% | 0.29 |
| V4H_REC92_25_SOLBNB_95_10 | SOL | 519.97% | 1.29 | -317.09% | 191.16% | 0.28 |
| V4H_REC92_20_SOLBNB_94_15 | SOL | 512.88% | 1.29 | -318.91% | 184.08% | 0.28 |
| V4H_REC92_25_SOLBNB_COOLDOWN | SOL | 534.35% | 1.31 | -338.41% | 205.55% | 0.30 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | SOL | 524.48% | 1.29 | -324.61% | 195.68% | 0.29 |
| V4H_REC92_15_ALL | SOL | 500.80% | 1.28 | -314.36% | 172.00% | 0.27 |
| V4H_REC94_15_ALL | SOL | 500.80% | 1.28 | -314.36% | 172.00% | 0.27 |
| V4H_REC92_25_SOLBNB_94_15 | BNB | 546.17% | 1.39 | -302.37% | 280.36% | 0.57 |
| V4H_REC92_25_SOLBNB_95_10 | BNB | 542.43% | 1.38 | -294.63% | 276.61% | 0.56 |
| V4H_REC92_20_SOLBNB_94_15 | BNB | 531.52% | 1.37 | -300.28% | 265.70% | 0.55 |
| V4H_REC92_25_SOLBNB_COOLDOWN | BNB | 554.86% | 1.42 | -317.91% | 289.04% | 0.60 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | BNB | 546.86% | 1.40 | -302.23% | 281.04% | 0.57 |
| V4H_REC92_15_ALL | BNB | 517.06% | 1.35 | -298.11% | 251.24% | 0.52 |
| V4H_REC94_15_ALL | BNB | 517.06% | 1.35 | -298.11% | 251.24% | 0.52 |
| V4H_REC92_25_SOLBNB_94_15 | SOL+BNB | 315.76% | 0.95 | -532.78% | 117.04% | 0.30 |
| V4H_REC92_25_SOLBNB_95_10 | SOL+BNB | 315.76% | 0.95 | -521.30% | 117.04% | 0.30 |
| V4H_REC92_20_SOLBNB_94_15 | SOL+BNB | 305.76% | 0.93 | -526.03% | 107.04% | 0.28 |
| V4H_REC92_25_SOLBNB_COOLDOWN | SOL+BNB | 315.76% | 0.95 | -557.00% | 117.04% | 0.30 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | SOL+BNB | 315.76% | 0.95 | -533.33% | 117.04% | 0.30 |
| V4H_REC92_15_ALL | SOL+BNB | 295.90% | 0.91 | -519.27% | 97.18% | 0.26 |
| V4H_REC94_15_ALL | SOL+BNB | 295.90% | 0.91 | -519.27% | 97.18% | 0.26 |

## Recovery PF Breakdown

| Variant | Group | Trades | PnL | PF | Win | Avg R |
|---|---|---|---|---|---|---|
| V0_BASELINE | ALL_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V0_BASELINE | SOL_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V0_BASELINE | BNB_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V0_BASELINE | NON_SOLBNB_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V4H_STRICT_BASE | ALL_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V4H_STRICT_BASE | SOL_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V4H_STRICT_BASE | BNB_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V4H_STRICT_BASE | NON_SOLBNB_RECOVERY | 0.00 | 0.00% |  | 0.00% |  |
| V4H_STRICT_REC92_25 | ALL_RECOVERY | 190.00 | 34.26% | 1.47 | 42.11% | 0.43 |
| V4H_STRICT_REC92_25 | SOL_RECOVERY | 32.00 | 12.77% | 2.07 | 40.62% | 0.37 |
| V4H_STRICT_REC92_25 | BNB_RECOVERY | 23.00 | 17.59% | 3.95 | 56.52% | 0.97 |
| V4H_STRICT_REC92_25 | NON_SOLBNB_RECOVERY | 135.00 | 3.90% | 1.07 | 40.00% | 0.36 |
| V4H_REC92_15_DIVERSIFIED | ALL_RECOVERY | 150.00 | 5.30% | 1.53 | 46.00% | 0.24 |
| V4H_REC92_15_DIVERSIFIED | SOL_RECOVERY | 26.00 | 2.76% | 2.99 | 46.15% | 0.62 |
| V4H_REC92_15_DIVERSIFIED | BNB_RECOVERY | 17.00 | 0.71% | 1.78 | 58.82% | 0.39 |
| V4H_REC92_15_DIVERSIFIED | NON_SOLBNB_RECOVERY | 107.00 | 1.83% | 1.24 | 43.93% | 0.12 |
| V4H_REC92_25_SOLBNB_94_15 | ALL_RECOVERY | 190.00 | 21.99% | 1.34 | 42.11% | 0.43 |
| V4H_REC92_25_SOLBNB_94_15 | SOL_RECOVERY | 32.00 | 7.56% | 2.07 | 40.62% | 0.37 |
| V4H_REC92_25_SOLBNB_94_15 | BNB_RECOVERY | 23.00 | 10.43% | 3.94 | 56.52% | 0.97 |
| V4H_REC92_25_SOLBNB_94_15 | NON_SOLBNB_RECOVERY | 135.00 | 4.00% | 1.07 | 40.00% | 0.36 |
| V4H_REC92_25_SOLBNB_95_10 | ALL_RECOVERY | 190.00 | 15.97% | 1.26 | 42.11% | 0.43 |
| V4H_REC92_25_SOLBNB_95_10 | SOL_RECOVERY | 32.00 | 5.01% | 2.07 | 40.62% | 0.37 |
| V4H_REC92_25_SOLBNB_95_10 | BNB_RECOVERY | 23.00 | 6.92% | 3.94 | 56.52% | 0.97 |
| V4H_REC92_25_SOLBNB_95_10 | NON_SOLBNB_RECOVERY | 135.00 | 4.05% | 1.08 | 40.00% | 0.36 |
| V4H_REC92_20_SOLBNB_94_15 | ALL_RECOVERY | 190.00 | 20.99% | 1.40 | 42.11% | 0.43 |
| V4H_REC92_20_SOLBNB_94_15 | SOL_RECOVERY | 32.00 | 7.44% | 2.07 | 40.62% | 0.37 |
| V4H_REC92_20_SOLBNB_94_15 | BNB_RECOVERY | 23.00 | 10.27% | 3.94 | 56.52% | 0.97 |
| V4H_REC92_20_SOLBNB_94_15 | NON_SOLBNB_RECOVERY | 135.00 | 3.28% | 1.08 | 40.00% | 0.36 |
| V4H_REC92_25_SOLBNB_COOLDOWN | ALL_RECOVERY | 185.00 | 36.37% | 1.51 | 42.16% | 0.46 |
| V4H_REC92_25_SOLBNB_COOLDOWN | SOL_RECOVERY | 28.00 | 14.98% | 2.47 | 42.86% | 0.51 |
| V4H_REC92_25_SOLBNB_COOLDOWN | BNB_RECOVERY | 22.00 | 17.48% | 3.93 | 54.55% | 1.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | NON_SOLBNB_RECOVERY | 135.00 | 3.91% | 1.07 | 40.00% | 0.36 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | ALL_RECOVERY | 185.00 | 23.24% | 1.37 | 42.16% | 0.46 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | SOL_RECOVERY | 28.00 | 8.87% | 2.47 | 42.86% | 0.51 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | BNB_RECOVERY | 22.00 | 10.36% | 3.92 | 54.55% | 1.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | NON_SOLBNB_RECOVERY | 135.00 | 4.00% | 1.07 | 40.00% | 0.36 |
| V4H_REC92_15_ALL | ALL_RECOVERY | 190.00 | 19.95% | 1.48 | 42.11% | 0.43 |
| V4H_REC92_15_ALL | SOL_RECOVERY | 32.00 | 7.32% | 2.07 | 40.62% | 0.37 |
| V4H_REC92_15_ALL | BNB_RECOVERY | 23.00 | 10.10% | 3.94 | 56.52% | 0.97 |
| V4H_REC92_15_ALL | NON_SOLBNB_RECOVERY | 135.00 | 2.53% | 1.08 | 40.00% | 0.36 |
| V4H_REC94_15_ALL | ALL_RECOVERY | 190.00 | 19.95% | 1.48 | 42.11% | 0.43 |
| V4H_REC94_15_ALL | SOL_RECOVERY | 32.00 | 7.32% | 2.07 | 40.62% | 0.37 |
| V4H_REC94_15_ALL | BNB_RECOVERY | 23.00 | 10.10% | 3.94 | 56.52% | 0.97 |
| V4H_REC94_15_ALL | NON_SOLBNB_RECOVERY | 135.00 | 2.53% | 1.08 | 40.00% | 0.36 |

## Cost Stress

| Variant | Cost | Return | MDD | Calmar | Return vs V0 | Calmar vs V0 |
|---|---|---|---|---|---|---|
| V0_BASELINE | 1.00 | 414.55% | -28.14% | 1.12 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 1.00 | 729.80% | -27.45% | 1.54 | 315.25% | 0.42 |
| V4H_STRICT_REC92_25 | 1.00 | 871.82% | -26.52% | 1.74 | 457.27% | 0.62 |
| V4H_REC92_15_DIVERSIFIED | 1.00 | 161.48% | -14.30% | 1.21 | -253.08% | 0.10 |
| V4H_REC92_25_SOLBNB_94_15 | 1.00 | 848.54% | -26.68% | 1.70 | 433.99% | 0.59 |
| V4H_REC92_25_SOLBNB_95_10 | 1.00 | 837.06% | -26.77% | 1.69 | 422.51% | 0.57 |
| V4H_REC92_20_SOLBNB_94_15 | 1.00 | 831.79% | -26.65% | 1.69 | 417.24% | 0.58 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 1.00 | 872.76% | -26.43% | 1.74 | 458.21% | 0.63 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 1.00 | 849.09% | -26.63% | 1.71 | 434.54% | 0.59 |
| V4H_REC92_15_ALL | 1.00 | 815.17% | -26.61% | 1.68 | 400.61% | 0.56 |
| V4H_REC94_15_ALL | 1.00 | 815.17% | -26.61% | 1.68 | 400.61% | 0.56 |
| V0_BASELINE | 2.00 | 30.18% | -53.74% | 0.08 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 2.00 | 27.31% | -61.03% | 0.07 | -2.87% | -0.02 |
| V4H_STRICT_REC92_25 | 2.00 | 43.83% | -59.04% | 0.11 | 13.65% | 0.02 |
| V4H_REC92_15_DIVERSIFIED | 2.00 | 22.96% | -27.92% | 0.13 | -7.22% | 0.04 |
| V4H_REC92_25_SOLBNB_94_15 | 2.00 | 42.40% | -59.26% | 0.10 | 12.22% | 0.02 |
| V4H_REC92_25_SOLBNB_95_10 | 2.00 | 41.68% | -59.37% | 0.10 | 11.50% | 0.02 |
| V4H_REC92_20_SOLBNB_94_15 | 2.00 | 41.58% | -59.18% | 0.10 | 11.40% | 0.02 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2.00 | 43.78% | -58.87% | 0.11 | 13.60% | 0.02 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2.00 | 42.04% | -59.16% | 0.10 | 11.86% | 0.02 |
| V4H_REC92_15_ALL | 2.00 | 40.76% | -59.10% | 0.10 | 10.58% | 0.02 |
| V4H_REC94_15_ALL | 2.00 | 40.76% | -59.10% | 0.10 | 10.58% | 0.02 |
| V0_BASELINE | 3.00 | -78.90% | -86.84% | -0.26 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 3.00 | -91.63% | -95.43% | -0.35 | -12.73% | -0.09 |
| V4H_STRICT_REC92_25 | 3.00 | -91.26% | -94.91% | -0.35 | -12.36% | -0.09 |
| V4H_REC92_15_DIVERSIFIED | 3.00 | -42.20% | -55.94% | -0.16 | 36.70% | 0.11 |
| V4H_REC92_25_SOLBNB_94_15 | 3.00 | -91.18% | -94.83% | -0.35 | -12.28% | -0.09 |
| V4H_REC92_25_SOLBNB_95_10 | 3.00 | -91.13% | -94.79% | -0.35 | -12.23% | -0.09 |
| V4H_REC92_20_SOLBNB_94_15 | 3.00 | -90.89% | -94.66% | -0.35 | -11.99% | -0.08 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 3.00 | -91.00% | -94.73% | -0.35 | -12.10% | -0.09 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 3.00 | -91.05% | -94.73% | -0.35 | -12.15% | -0.09 |
| V4H_REC92_15_ALL | 3.00 | -90.61% | -94.50% | -0.34 | -11.70% | -0.08 |
| V4H_REC94_15_ALL | 3.00 | -90.61% | -94.50% | -0.34 | -11.70% | -0.08 |

## Yearly OOS

| Variant | Year | Return | CAGR | MDD | Calmar | PF | Trades |
|---|---|---|---|---|---|---|---|
| V0_BASELINE | 2020.00 | 108.95% | 108.64% | -11.57% | 9.39 | 2.20 | 165.00 |
| V0_BASELINE | 2021.00 | 63.93% | 63.99% | -7.01% | 9.13 | 2.18 | 121.00 |
| V0_BASELINE | 2022.00 | 0.00% | 0.00% | 0.00% |  |  | 0.00 |
| V0_BASELINE | 2023.00 | 39.83% | 39.86% | -11.39% | 3.50 | 1.30 | 182.00 |
| V0_BASELINE | 2024.00 | 0.05% | 0.05% | -24.11% | 0.00 | 0.78 | 247.00 |
| V0_BASELINE | 2025.00 | 7.38% | 7.38% | -22.33% | 0.33 | 0.89 | 214.00 |
| V4H_STRICT_BASE | 2020.00 | 104.89% | 104.59% | -8.35% | 12.53 | 1.91 | 226.00 |
| V4H_STRICT_BASE | 2021.00 | 126.67% | 126.80% | -9.77% | 12.97 | 1.84 | 250.00 |
| V4H_STRICT_BASE | 2022.00 | -8.14% | -8.15% | -11.59% | -0.70 | 0.54 | 103.00 |
| V4H_STRICT_BASE | 2023.00 | 72.18% | 72.24% | -14.08% | 5.13 | 1.36 | 314.00 |
| V4H_STRICT_BASE | 2024.00 | 11.15% | 11.13% | -22.41% | 0.50 | 0.90 | 282.00 |
| V4H_STRICT_BASE | 2025.00 | 1.64% | 1.64% | -23.17% | 0.07 | 0.83 | 212.00 |
| V4H_STRICT_REC92_25 | 2020.00 | 128.07% | 127.69% | -8.35% | 15.30 | 2.18 | 234.00 |
| V4H_STRICT_REC92_25 | 2021.00 | 127.95% | 128.08% | -9.77% | 13.11 | 1.83 | 271.00 |
| V4H_STRICT_REC92_25 | 2022.00 | -3.28% | -3.29% | -7.74% | -0.42 | 0.64 | 135.00 |
| V4H_STRICT_REC92_25 | 2023.00 | 71.69% | 71.75% | -14.10% | 5.09 | 1.38 | 328.00 |
| V4H_STRICT_REC92_25 | 2024.00 | 10.51% | 10.48% | -22.73% | 0.46 | 0.89 | 305.00 |
| V4H_STRICT_REC92_25 | 2025.00 | 1.87% | 1.87% | -23.21% | 0.08 | 0.81 | 242.00 |
| V4H_REC92_15_DIVERSIFIED | 2020.00 | 31.76% | 31.68% | -7.94% | 3.99 | 1.77 | 108.00 |
| V4H_REC92_15_DIVERSIFIED | 2021.00 | 36.19% | 36.21% | -8.05% | 4.50 | 1.66 | 118.00 |
| V4H_REC92_15_DIVERSIFIED | 2022.00 | -1.49% | -1.49% | -5.55% | -0.27 | 0.68 | 81.00 |
| V4H_REC92_15_DIVERSIFIED | 2023.00 | 35.66% | 35.69% | -7.40% | 4.83 | 1.79 | 128.00 |
| V4H_REC92_15_DIVERSIFIED | 2024.00 | 4.07% | 4.06% | -10.11% | 0.40 | 0.83 | 130.00 |
| V4H_REC92_15_DIVERSIFIED | 2025.00 | 4.78% | 4.78% | -6.91% | 0.69 | 0.90 | 113.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2020.00 | 127.46% | 127.08% | -8.35% | 15.23 | 2.18 | 234.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2021.00 | 128.44% | 128.57% | -9.77% | 13.16 | 1.83 | 271.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2022.00 | -3.85% | -3.85% | -7.71% | -0.50 | 0.62 | 135.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2023.00 | 70.40% | 70.46% | -14.01% | 5.03 | 1.37 | 328.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2024.00 | 10.17% | 10.15% | -23.00% | 0.44 | 0.88 | 305.00 |
| V4H_REC92_25_SOLBNB_94_15 | 2025.00 | 1.13% | 1.13% | -23.31% | 0.05 | 0.80 | 242.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2020.00 | 127.15% | 126.77% | -8.35% | 15.19 | 2.18 | 234.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2021.00 | 128.69% | 128.82% | -9.77% | 13.18 | 1.84 | 271.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2022.00 | -4.13% | -4.13% | -7.69% | -0.54 | 0.61 | 135.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2023.00 | 69.75% | 69.81% | -13.96% | 5.00 | 1.37 | 328.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2024.00 | 10.01% | 9.99% | -23.13% | 0.43 | 0.88 | 305.00 |
| V4H_REC92_25_SOLBNB_95_10 | 2025.00 | 0.76% | 0.76% | -23.37% | 0.03 | 0.80 | 242.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2020.00 | 124.41% | 124.04% | -8.34% | 14.87 | 2.16 | 234.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2021.00 | 128.35% | 128.48% | -9.77% | 13.15 | 1.84 | 271.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2022.00 | -3.95% | -3.95% | -7.72% | -0.51 | 0.62 | 135.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2023.00 | 70.11% | 70.18% | -14.05% | 5.00 | 1.37 | 328.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2024.00 | 10.15% | 10.12% | -23.02% | 0.44 | 0.89 | 305.00 |
| V4H_REC92_20_SOLBNB_94_15 | 2025.00 | 1.03% | 1.03% | -23.24% | 0.04 | 0.80 | 242.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2020.00 | 128.07% | 127.69% | -8.35% | 15.30 | 2.18 | 234.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2021.00 | 128.26% | 128.39% | -9.77% | 13.14 | 1.83 | 270.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2022.00 | -3.36% | -3.36% | -7.74% | -0.43 | 0.64 | 134.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2023.00 | 71.69% | 71.75% | -14.10% | 5.09 | 1.38 | 328.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2024.00 | 10.45% | 10.43% | -22.73% | 0.46 | 0.89 | 303.00 |
| V4H_REC92_25_SOLBNB_COOLDOWN | 2025.00 | 1.96% | 1.96% | -23.11% | 0.08 | 0.81 | 241.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2020.00 | 127.46% | 127.08% | -8.35% | 15.23 | 2.18 | 234.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2021.00 | 128.63% | 128.76% | -9.77% | 13.18 | 1.84 | 270.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2022.00 | -3.89% | -3.89% | -7.70% | -0.51 | 0.62 | 134.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2023.00 | 70.39% | 70.46% | -14.01% | 5.03 | 1.37 | 328.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2024.00 | 10.14% | 10.12% | -23.00% | 0.44 | 0.88 | 303.00 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | 2025.00 | 1.18% | 1.18% | -23.26% | 0.05 | 0.80 | 241.00 |
| V4H_REC92_15_ALL | 2020.00 | 121.38% | 121.02% | -8.34% | 14.51 | 2.14 | 234.00 |
| V4H_REC92_15_ALL | 2021.00 | 128.25% | 128.38% | -9.77% | 13.14 | 1.84 | 271.00 |
| V4H_REC92_15_ALL | 2022.00 | -4.05% | -4.05% | -7.74% | -0.52 | 0.61 | 135.00 |
| V4H_REC92_15_ALL | 2023.00 | 69.83% | 69.89% | -14.09% | 4.96 | 1.37 | 328.00 |
| V4H_REC92_15_ALL | 2024.00 | 10.12% | 10.09% | -23.04% | 0.44 | 0.89 | 305.00 |
| V4H_REC92_15_ALL | 2025.00 | 0.94% | 0.94% | -23.17% | 0.04 | 0.80 | 242.00 |
| V4H_REC94_15_ALL | 2020.00 | 121.38% | 121.02% | -8.34% | 14.51 | 2.14 | 234.00 |
| V4H_REC94_15_ALL | 2021.00 | 128.25% | 128.38% | -9.77% | 13.14 | 1.84 | 271.00 |
| V4H_REC94_15_ALL | 2022.00 | -4.05% | -4.05% | -7.74% | -0.52 | 0.61 | 135.00 |
| V4H_REC94_15_ALL | 2023.00 | 69.83% | 69.89% | -14.09% | 4.96 | 1.37 | 328.00 |
| V4H_REC94_15_ALL | 2024.00 | 10.12% | 10.09% | -23.04% | 0.44 | 0.89 | 305.00 |
| V4H_REC94_15_ALL | 2025.00 | 0.94% | 0.94% | -23.17% | 0.04 | 0.80 | 242.00 |

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
| V4H_REC92_15_DIVERSIFIED | bull | 67.46% | 1.32 | 36.71% | 414.00 | 0.20 |
| V4H_REC92_15_DIVERSIFIED | bear | -3.33% | 0.82 | 41.35% | 104.00 | 0.21 |
| V4H_REC92_15_DIVERSIFIED | sideways | -0.57% | 0.99 | 38.51% | 161.00 | 0.14 |
| V4H_REC92_25_SOLBNB_94_15 | bull | 318.19% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_REC92_25_SOLBNB_94_15 | bear | -32.61% | 0.68 | 36.24% | 149.00 | 0.10 |
| V4H_REC92_25_SOLBNB_94_15 | sideways | -94.01% | 0.80 | 37.02% | 289.00 | 0.21 |
| V4H_REC92_25_SOLBNB_95_10 | bull | 315.79% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_REC92_25_SOLBNB_95_10 | bear | -33.40% | 0.67 | 36.24% | 149.00 | 0.10 |
| V4H_REC92_25_SOLBNB_95_10 | sideways | -96.47% | 0.79 | 37.02% | 289.00 | 0.21 |
| V4H_REC92_20_SOLBNB_94_15 | bull | 314.91% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_REC92_20_SOLBNB_94_15 | bear | -31.55% | 0.67 | 36.24% | 149.00 | 0.10 |
| V4H_REC92_20_SOLBNB_94_15 | sideways | -94.44% | 0.79 | 37.02% | 289.00 | 0.21 |
| V4H_REC92_25_SOLBNB_COOLDOWN | bull | 323.33% | 1.19 | 37.64% | 1076.00 | 0.21 |
| V4H_REC92_25_SOLBNB_COOLDOWN | bear | -29.23% | 0.72 | 36.05% | 147.00 | 0.11 |
| V4H_REC92_25_SOLBNB_COOLDOWN | sideways | -88.90% | 0.81 | 37.15% | 288.00 | 0.21 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | bull | 318.32% | 1.19 | 37.64% | 1076.00 | 0.21 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | bear | -31.56% | 0.69 | 36.05% | 147.00 | 0.11 |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | sideways | -93.94% | 0.80 | 37.15% | 288.00 | 0.21 |
| V4H_REC92_15_ALL | bull | 311.61% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_REC92_15_ALL | bear | -30.53% | 0.66 | 36.24% | 149.00 | 0.10 |
| V4H_REC92_15_ALL | sideways | -94.86% | 0.79 | 37.02% | 289.00 | 0.21 |
| V4H_REC94_15_ALL | bull | 311.61% | 1.19 | 37.66% | 1078.00 | 0.21 |
| V4H_REC94_15_ALL | bear | -30.53% | 0.66 | 36.24% | 149.00 | 0.10 |
| V4H_REC94_15_ALL | sideways | -94.86% | 0.79 | 37.02% | 289.00 | 0.21 |

## Symbol Concentration

| Variant | Top1 symbol | Top1 share | Top2 share |
|---|---|---|---|
| V0_BASELINE | BNB | 17.54% | 32.86% |
| V4H_STRICT_BASE | SOL | 15.62% | 31.08% |
| V4H_STRICT_REC92_25 | SOL | 16.40% | 30.78% |
| V4H_REC92_15_DIVERSIFIED | ADA | 16.04% | 30.68% |
| V4H_REC92_25_SOLBNB_94_15 | SOL | 16.13% | 30.26% |
| V4H_REC92_25_SOLBNB_95_10 | SOL | 16.00% | 30.00% |
| V4H_REC92_20_SOLBNB_94_15 | SOL | 16.20% | 30.40% |
| V4H_REC92_25_SOLBNB_COOLDOWN | SOL | 16.42% | 30.79% |
| V4H_REC92_25_SOLBNB_94_15_COOLDOWN | SOL | 16.14% | 30.27% |
| V4H_REC92_15_ALL | SOL | 16.27% | 30.54% |
| V4H_REC94_15_ALL | SOL | 16.27% | 30.54% |

## Audit Notes

- Final symbol-specific verdict: PASS 0, WATCH 4, FAIL 1. No symbol-specific candidate reached PASS.
- SOL/BNB-specific score/size controls lowered top1 contribution from 16.40% to a best 16.00% among non-cooldown-only controls, but SOL+BNB removal still reduced return by -557.00pp to -521.30pp.
- Recovery PF stayed above the PASS floor for the controlled variants: 1.26 minimum.
- Cost 2x remained above V0 for controlled variants, but cost 3x stayed negative for all symbol-specific candidates; best 3x return was -90.89%.
- 2022/2025 did not provide the required improvement for the score/size controls; best 2022 among symbol-specific candidates was -3.36% and best 2025 was 1.96%.
- `V4H_REC94_15_ALL` matched `V4H_REC92_15_ALL` exactly in this audit, so the 94 threshold did not remove any filled recovery trades under the existing signal/top-score execution path.

## Output Files

- `reports/research/v4h_symbol_specific_recovery_report.md`
- `reports/research/v4h_symbol_specific_summary.csv`
- `reports/research/v4h_symbol_specific_leave_symbol.csv`
- `reports/research/v4h_symbol_specific_recovery_by_symbol.csv`
- `reports/research/v4h_symbol_specific_cost_stress.csv`
- `reports/research/v4h_symbol_specific_oos_yearly.csv`
- `reports/research/v4h_symbol_specific_regime_performance.csv`
- `reports/research/v4h_symbol_specific_concentration.csv`
