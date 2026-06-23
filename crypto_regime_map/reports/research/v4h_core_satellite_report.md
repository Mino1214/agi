# V4H Core/Satellite Audit

## Scope

- Read-only audit/report only. Strategy, paper engine, live order logic, checkout/merge, commit, and push were not touched.
- Core excludes SOL/BNB; Satellite trades SOL/BNB only; Core+Satellite combines independent equity curves by account allocation.
- Satellite pause rules are audit-only wrappers for new entries: rolling 30D drawdown <= -10% or monthly loss <= -8%.
- Cost stress is run for comparison baselines and the combined shortlist selected from the base Core/Satellite grid.

## Final Read

- Combined shortlist status counts: PASS 0, WATCH 0, FAIL 3.
- Best Core only: `CORE_NO_SOL_BNB_REC92_25` return 315.76%, MDD -28.34%, Calmar 0.95, status FAIL.
- Best Satellite only: `SAT_SOL_BNB_REC92_25_CD72H` with pause `none` return 118.55%, MDD -15.79%, Calmar 0.88.

## Summary

| Variant | Group | Status | Reasons | Return | CAGR | MDD | Calmar | Trades | Sat Alloc | SOL+BNB Impact |
|---|---|---|---|---|---|---|---|---|---|---|
| SAT_SOL_BNB_REC92_25_CD72H | satellite_best | WATCH | satellite is evaluated only as capped return engine, not standalone portfolio | 118.55% | 13.91% | -15.79% | 0.88 | 736.00 |  |  |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | combined_shortlist | FAIL | Core+Satellite return/CAGR/Calmar not all above V0; cost 2x weaker than V0; 2022/2025 OOS not improved; Core remains weaker than V0 without satellite; cost 3x stress weak; cost 5x stress weak | 266.46% | 24.16% | -25.40% | 0.95 | 2129.00 | 25.00% | -29.64% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | combined_shortlist | FAIL | Core+Satellite return/CAGR/Calmar not all above V0; cost 2x weaker than V0; 2022/2025 OOS not improved; Core remains weaker than V0 without satellite; cost 3x stress weak; cost 5x stress weak | 266.46% | 24.16% | -25.40% | 0.95 | 2129.00 | 25.00% | -29.64% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | combined_shortlist | FAIL | Core+Satellite return/CAGR/Calmar not all above V0; cost 2x weaker than V0; 2022/2025 OOS not improved; Core remains weaker than V0 without satellite; cost 3x stress weak; cost 5x stress weak | 266.46% | 24.16% | -25.40% | 0.95 | 2129.00 | 25.00% | -29.64% |
| CORE_NO_SOL_BNB_REC92_25 | core_best | FAIL | Core Calmar not above V0; Core return below V0 | 315.76% | 26.80% | -28.34% | 0.95 | 1393.00 |  |  |
| V4H_REC92_25_ORIGINAL | comparison | BASELINE | comparison baseline | 871.82% | 46.07% | -26.52% | 1.74 | 1515.00 |  |  |
| V4H_REC92_25_SOLBNB_94_15 | comparison | BASELINE | comparison baseline | 848.54% | 45.48% | -26.68% | 1.70 | 1515.00 |  |  |
| V4H_REC92_15_ALL | comparison | BASELINE | comparison baseline | 815.17% | 44.62% | -26.61% | 1.68 | 1515.00 |  |  |
| V4H_STRICT_BASE | comparison | BASELINE | comparison baseline | 729.80% | 42.27% | -27.45% | 1.54 | 1387.00 |  |  |
| V0_BASELINE | comparison | BASELINE | comparison baseline | 414.55% | 31.38% | -28.14% | 1.12 | 929.00 |  |  |

## Core Only

| Variant | Threshold | Size | Return | CAGR | MDD | Calmar | Recovery PF | Trades |
|---|---|---|---|---|---|---|---|---|
| CORE_NO_SOL_BNB_REC92_25 | 92.00 | 25.00% | 315.76% | 26.80% | -28.34% | 0.95 | 1.42 | 1393.00 |
| CORE_NO_SOL_BNB_REC94_25 | 94.00 | 25.00% | 315.76% | 26.80% | -28.34% | 0.95 | 1.42 | 1393.00 |
| CORE_NO_SOL_BNB_REC90_25 | 90.00 | 25.00% | 319.48% | 26.99% | -28.94% | 0.93 | 1.25 | 1439.00 |
| CORE_NO_SOL_BNB_REC92_15 | 92.00 | 15.00% | 295.90% | 25.77% | -28.31% | 0.91 | 1.43 | 1393.00 |
| CORE_NO_SOL_BNB_REC94_15 | 94.00 | 15.00% | 295.90% | 25.77% | -28.31% | 0.91 | 1.43 | 1393.00 |
| CORE_NO_SOL_BNB_REC90_15 | 90.00 | 15.00% | 299.69% | 25.97% | -28.78% | 0.90 | 1.26 | 1439.00 |
| CORE_NO_SOL_BNB_REC92_10 | 92.00 | 10.00% | 286.17% | 25.25% | -28.30% | 0.89 | 1.44 | 1393.00 |
| CORE_NO_SOL_BNB_REC94_10 | 94.00 | 10.00% | 286.17% | 25.25% | -28.30% | 0.89 | 1.44 | 1393.00 |
| CORE_NO_SOL_BNB_REC90_10 | 90.00 | 10.00% | 289.98% | 25.45% | -28.70% | 0.89 | 1.26 | 1439.00 |

## Satellite Only Top 20

| Variant | Pause | Return | CAGR | MDD | Calmar | Recovery PF | Trades | Pause Skips |
|---|---|---|---|---|---|---|---|---|
| SAT_SOL_BNB_REC92_25_CD72H | none | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CD72H | rolling_30d_dd | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CD72H | monthly_loss | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD72H | none | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD72H | rolling_30d_dd | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD72H | monthly_loss | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC95_25_CD72H | none | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC95_25_CD72H | rolling_30d_dd | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC95_25_CD72H | monthly_loss | 118.55% | 13.91% | -15.79% | 0.88 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CD48H | none | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CD48H | rolling_30d_dd | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CD48H | monthly_loss | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD48H | none | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD48H | rolling_30d_dd | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC94_25_CD48H | monthly_loss | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC95_25_CD48H | none | 117.67% | 13.84% | -15.94% | 0.87 | 1.90 | 740.00 | 0.00 |
| SAT_SOL_BNB_REC92_15_CD72H | none | 113.96% | 13.51% | -15.96% | 0.85 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC94_15_CD72H | none | 113.96% | 13.51% | -15.96% | 0.85 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC95_15_CD72H | none | 113.96% | 13.51% | -15.96% | 0.85 | 2.15 | 736.00 | 0.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | none | 114.03% | 13.52% | -16.05% | 0.84 | 1.58 | 753.00 | 0.00 |

## Combined Top 30

| Variant | Return | CAGR | MDD | Calmar | Sat Alloc | Pause | SOL+BNB Delta | Impact Improvement | Sat MDD Contribution |
|---|---|---|---|---|---|---|---|---|---|
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC94_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_NOPAUSE | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | none | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_ROLL30DD | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | rolling_30d_dd | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC95_25_CD72H__SAT25_MONTHLOSS | 266.46% | 24.16% | -25.40% | 0.95 | 25.00% | monthly_loss | -29.64% | 94.67% | 4.97% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_NOPAUSE | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | none | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_ROLL30DD | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | rolling_30d_dd | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_MONTHLOSS | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | monthly_loss | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT20_NOPAUSE | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | none | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT20_ROLL30DD | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | rolling_30d_dd | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC94_25_CD72H__SAT20_MONTHLOSS | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | monthly_loss | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT20_NOPAUSE | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | none | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT20_ROLL30DD | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | rolling_30d_dd | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC95_25_CD72H__SAT20_MONTHLOSS | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | monthly_loss | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_NOPAUSE | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | none | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_ROLL30DD | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | rolling_30d_dd | -23.71% | 95.74% | 3.77% |
| CS_CORE_NO_SOL_BNB_REC94_25__SAT_SOL_BNB_REC92_25_CD72H__SAT20_MONTHLOSS | 276.32% | 24.71% | -26.00% | 0.95 | 20.00% | monthly_loss | -23.71% | 95.74% | 3.77% |

## Cost Stress

| Variant | Cost | Return | MDD | Calmar | Return vs V0 | Calmar vs V0 |
|---|---|---|---|---|---|---|
| V0_BASELINE | 1.00 | 414.55% | -28.14% | 1.12 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 1.00 | 729.80% | -27.45% | 1.54 | 315.25% | 0.42 |
| V4H_REC92_25_ORIGINAL | 1.00 | 871.82% | -26.52% | 1.74 | 457.27% | 0.62 |
| V4H_REC92_15_ALL | 1.00 | 815.17% | -26.61% | 1.68 | 400.61% | 0.56 |
| V0_BASELINE | 2.00 | 30.18% | -53.74% | 0.08 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 2.00 | 27.31% | -61.03% | 0.07 | -2.87% | -0.02 |
| V4H_REC92_25_ORIGINAL | 2.00 | 43.83% | -59.04% | 0.11 | 13.65% | 0.02 |
| V4H_REC92_15_ALL | 2.00 | 40.76% | -59.10% | 0.10 | 10.58% | 0.02 |
| V0_BASELINE | 3.00 | -78.90% | -86.84% | -0.26 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 3.00 | -91.63% | -95.43% | -0.35 | -12.73% | -0.09 |
| V4H_REC92_25_ORIGINAL | 3.00 | -91.26% | -94.91% | -0.35 | -12.36% | -0.09 |
| V4H_REC92_15_ALL | 3.00 | -90.61% | -94.50% | -0.34 | -11.70% | -0.08 |
| V0_BASELINE | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | 0.00 |
| V4H_STRICT_BASE | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_REC92_25_ORIGINAL | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| V4H_REC92_15_ALL | 5.00 | -100.00% | -100.00% | -0.97 | 0.00% | -0.00 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | 2.00 | -16.61% | -64.36% | -0.05 | -46.79% | -0.13 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | 2.00 | -16.61% | -64.36% | -0.05 | -46.79% | -0.13 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | 2.00 | -16.61% | -64.36% | -0.05 | -46.79% | -0.13 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | 3.00 | -90.79% | -93.48% | -0.35 | -11.89% | -0.09 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | 3.00 | -89.31% | -92.43% | -0.34 | -10.41% | -0.07 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | 3.00 | -90.16% | -93.03% | -0.34 | -11.26% | -0.08 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_NOPAUSE | 5.00 | -99.96% | -99.97% | -0.73 | 0.04% | 0.24 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_ROLL30DD | 5.00 | -98.67% | -98.73% | -0.52 | 1.33% | 0.45 |
| CS_CORE_NO_SOL_BNB_REC92_25__SAT_SOL_BNB_REC92_25_CD72H__SAT25_MONTHLOSS | 5.00 | -99.17% | -99.21% | -0.55 | 0.83% | 0.41 |

## 2022 / 2025 OOS

| Variant | Group | Year | Return | CAGR | MDD | Calmar | Trades |
|---|---|---|---|---|---|---|---|
| V0_BASELINE | comparison | 2022.00 | 0.00% | 0.00% | 0.00% |  | 0.00 |
| V0_BASELINE | comparison | 2025.00 | 7.38% | 7.38% | -22.33% | 0.33 | 214.00 |
| V4H_STRICT_BASE | comparison | 2022.00 | -8.14% | -8.15% | -11.59% | -0.70 | 103.00 |
| V4H_STRICT_BASE | comparison | 2025.00 | 1.64% | 1.64% | -23.17% | 0.07 | 212.00 |
| V4H_REC92_25_ORIGINAL | comparison | 2022.00 | -3.28% | -3.29% | -7.74% | -0.42 | 135.00 |
| V4H_REC92_25_ORIGINAL | comparison | 2025.00 | 1.87% | 1.87% | -23.21% | 0.08 | 242.00 |
| V4H_REC92_15_ALL | comparison | 2022.00 | -4.05% | -4.05% | -7.74% | -0.52 | 135.00 |
| V4H_REC92_15_ALL | comparison | 2025.00 | 0.94% | 0.94% | -23.17% | 0.04 | 242.00 |
| V4H_REC92_25_SOLBNB_94_15 | comparison | 2022.00 | -3.85% | -3.85% | -7.71% | -0.50 | 135.00 |
| V4H_REC92_25_SOLBNB_94_15 | comparison | 2025.00 | 1.13% | 1.13% | -23.31% | 0.05 | 242.00 |
| CORE_NO_SOL_BNB_REC90_10 | core | 2022.00 | -5.67% | -5.67% | -8.91% | -0.64 | 129.00 |
| CORE_NO_SOL_BNB_REC90_10 | core | 2025.00 | 0.96% | 0.96% | -19.02% | 0.05 | 227.00 |
| CORE_NO_SOL_BNB_REC90_15 | core | 2022.00 | -5.37% | -5.37% | -8.64% | -0.62 | 129.00 |
| CORE_NO_SOL_BNB_REC90_15 | core | 2025.00 | 0.85% | 0.85% | -19.22% | 0.04 | 227.00 |
| CORE_NO_SOL_BNB_REC90_25 | core | 2022.00 | -4.77% | -4.77% | -8.11% | -0.59 | 129.00 |
| CORE_NO_SOL_BNB_REC90_25 | core | 2025.00 | 0.63% | 0.63% | -19.63% | 0.03 | 227.00 |
| CORE_NO_SOL_BNB_REC92_10 | core | 2022.00 | -5.96% | -5.97% | -9.09% | -0.66 | 121.00 |
| CORE_NO_SOL_BNB_REC92_10 | core | 2025.00 | 1.31% | 1.31% | -18.84% | 0.07 | 216.00 |
| CORE_NO_SOL_BNB_REC92_15 | core | 2022.00 | -5.81% | -5.81% | -8.91% | -0.65 | 121.00 |
| CORE_NO_SOL_BNB_REC92_15 | core | 2025.00 | 1.37% | 1.37% | -18.95% | 0.07 | 216.00 |
| CORE_NO_SOL_BNB_REC92_25 | core | 2022.00 | -5.51% | -5.51% | -8.55% | -0.64 | 121.00 |
| CORE_NO_SOL_BNB_REC92_25 | core | 2025.00 | 1.49% | 1.49% | -19.17% | 0.08 | 216.00 |
| CORE_NO_SOL_BNB_REC94_10 | core | 2022.00 | -5.96% | -5.97% | -9.09% | -0.66 | 121.00 |
| CORE_NO_SOL_BNB_REC94_10 | core | 2025.00 | 1.31% | 1.31% | -18.84% | 0.07 | 216.00 |
| CORE_NO_SOL_BNB_REC94_15 | core | 2022.00 | -5.81% | -5.81% | -8.91% | -0.65 | 121.00 |
| CORE_NO_SOL_BNB_REC94_15 | core | 2025.00 | 1.37% | 1.37% | -18.95% | 0.07 | 216.00 |
| CORE_NO_SOL_BNB_REC94_25 | core | 2022.00 | -5.51% | -5.51% | -8.55% | -0.64 | 121.00 |
| CORE_NO_SOL_BNB_REC94_25 | core | 2025.00 | 1.49% | 1.49% | -19.17% | 0.08 | 216.00 |
| SAT_SOL_BNB_REC92_05_CDNONE | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.97 | 60.00 |
| SAT_SOL_BNB_REC92_05_CDNONE | satellite | 2025.00 | -3.06% | -3.06% | -9.40% | -0.33 | 110.00 |
| SAT_SOL_BNB_REC92_05_CD48H | satellite | 2022.00 | 4.89% | 4.89% | -5.10% | 0.96 | 58.00 |
| SAT_SOL_BNB_REC92_05_CD48H | satellite | 2025.00 | -3.00% | -3.00% | -9.40% | -0.32 | 107.00 |
| SAT_SOL_BNB_REC92_05_CD72H | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.96 | 57.00 |
| SAT_SOL_BNB_REC92_05_CD72H | satellite | 2025.00 | -2.96% | -2.96% | -9.40% | -0.32 | 105.00 |
| SAT_SOL_BNB_REC92_10_CDNONE | satellite | 2022.00 | 5.09% | 5.09% | -5.06% | 1.01 | 60.00 |
| SAT_SOL_BNB_REC92_10_CDNONE | satellite | 2025.00 | -2.82% | -2.83% | -9.40% | -0.30 | 110.00 |
| SAT_SOL_BNB_REC92_10_CD48H | satellite | 2022.00 | 5.02% | 5.03% | -5.06% | 0.99 | 58.00 |
| SAT_SOL_BNB_REC92_10_CD48H | satellite | 2025.00 | -2.70% | -2.70% | -9.39% | -0.29 | 107.00 |
| SAT_SOL_BNB_REC92_10_CD72H | satellite | 2022.00 | 5.08% | 5.08% | -5.06% | 1.00 | 57.00 |
| SAT_SOL_BNB_REC92_10_CD72H | satellite | 2025.00 | -2.63% | -2.63% | -9.39% | -0.28 | 105.00 |
| SAT_SOL_BNB_REC92_15_CDNONE | satellite | 2022.00 | 5.25% | 5.26% | -5.02% | 1.05 | 60.00 |
| SAT_SOL_BNB_REC92_15_CDNONE | satellite | 2025.00 | -2.59% | -2.59% | -9.40% | -0.28 | 110.00 |
| SAT_SOL_BNB_REC92_15_CD48H | satellite | 2022.00 | 5.16% | 5.16% | -5.02% | 1.03 | 58.00 |
| SAT_SOL_BNB_REC92_15_CD48H | satellite | 2025.00 | -2.41% | -2.41% | -9.39% | -0.26 | 107.00 |
| SAT_SOL_BNB_REC92_15_CD72H | satellite | 2022.00 | 5.24% | 5.24% | -5.02% | 1.04 | 57.00 |
| SAT_SOL_BNB_REC92_15_CD72H | satellite | 2025.00 | -2.30% | -2.30% | -9.39% | -0.25 | 105.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | satellite | 2022.00 | 5.58% | 5.58% | -4.95% | 1.13 | 60.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | satellite | 2025.00 | -2.12% | -2.12% | -9.39% | -0.23 | 110.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC94_05_CDNONE | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.97 | 60.00 |
| SAT_SOL_BNB_REC94_05_CDNONE | satellite | 2025.00 | -3.06% | -3.06% | -9.40% | -0.33 | 110.00 |
| SAT_SOL_BNB_REC94_05_CD48H | satellite | 2022.00 | 4.89% | 4.89% | -5.10% | 0.96 | 58.00 |
| SAT_SOL_BNB_REC94_05_CD48H | satellite | 2025.00 | -3.00% | -3.00% | -9.40% | -0.32 | 107.00 |
| SAT_SOL_BNB_REC94_05_CD72H | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.96 | 57.00 |
| SAT_SOL_BNB_REC94_05_CD72H | satellite | 2025.00 | -2.96% | -2.96% | -9.40% | -0.32 | 105.00 |
| SAT_SOL_BNB_REC94_10_CDNONE | satellite | 2022.00 | 5.09% | 5.09% | -5.06% | 1.01 | 60.00 |
| SAT_SOL_BNB_REC94_10_CDNONE | satellite | 2025.00 | -2.82% | -2.83% | -9.40% | -0.30 | 110.00 |
| SAT_SOL_BNB_REC94_10_CD48H | satellite | 2022.00 | 5.02% | 5.03% | -5.06% | 0.99 | 58.00 |
| SAT_SOL_BNB_REC94_10_CD48H | satellite | 2025.00 | -2.70% | -2.70% | -9.39% | -0.29 | 107.00 |
| SAT_SOL_BNB_REC94_10_CD72H | satellite | 2022.00 | 5.08% | 5.08% | -5.06% | 1.00 | 57.00 |
| SAT_SOL_BNB_REC94_10_CD72H | satellite | 2025.00 | -2.63% | -2.63% | -9.39% | -0.28 | 105.00 |
| SAT_SOL_BNB_REC94_15_CDNONE | satellite | 2022.00 | 5.25% | 5.26% | -5.02% | 1.05 | 60.00 |
| SAT_SOL_BNB_REC94_15_CDNONE | satellite | 2025.00 | -2.59% | -2.59% | -9.40% | -0.28 | 110.00 |
| SAT_SOL_BNB_REC94_15_CD48H | satellite | 2022.00 | 5.16% | 5.16% | -5.02% | 1.03 | 58.00 |
| SAT_SOL_BNB_REC94_15_CD48H | satellite | 2025.00 | -2.41% | -2.41% | -9.39% | -0.26 | 107.00 |
| SAT_SOL_BNB_REC94_15_CD72H | satellite | 2022.00 | 5.24% | 5.24% | -5.02% | 1.04 | 57.00 |
| SAT_SOL_BNB_REC94_15_CD72H | satellite | 2025.00 | -2.30% | -2.30% | -9.39% | -0.25 | 105.00 |
| SAT_SOL_BNB_REC94_25_CDNONE | satellite | 2022.00 | 5.58% | 5.58% | -4.95% | 1.13 | 60.00 |
| SAT_SOL_BNB_REC94_25_CDNONE | satellite | 2025.00 | -2.12% | -2.12% | -9.39% | -0.23 | 110.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC95_05_CDNONE | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.97 | 60.00 |
| SAT_SOL_BNB_REC95_05_CDNONE | satellite | 2025.00 | -3.06% | -3.06% | -9.40% | -0.33 | 110.00 |
| SAT_SOL_BNB_REC95_05_CD48H | satellite | 2022.00 | 4.89% | 4.89% | -5.10% | 0.96 | 58.00 |
| SAT_SOL_BNB_REC95_05_CD48H | satellite | 2025.00 | -3.00% | -3.00% | -9.40% | -0.32 | 107.00 |
| SAT_SOL_BNB_REC95_05_CD72H | satellite | 2022.00 | 4.92% | 4.92% | -5.10% | 0.96 | 57.00 |
| SAT_SOL_BNB_REC95_05_CD72H | satellite | 2025.00 | -2.96% | -2.96% | -9.40% | -0.32 | 105.00 |
| SAT_SOL_BNB_REC95_10_CDNONE | satellite | 2022.00 | 5.09% | 5.09% | -5.06% | 1.01 | 60.00 |
| SAT_SOL_BNB_REC95_10_CDNONE | satellite | 2025.00 | -2.82% | -2.83% | -9.40% | -0.30 | 110.00 |
| SAT_SOL_BNB_REC95_10_CD48H | satellite | 2022.00 | 5.02% | 5.03% | -5.06% | 0.99 | 58.00 |
| SAT_SOL_BNB_REC95_10_CD48H | satellite | 2025.00 | -2.70% | -2.70% | -9.39% | -0.29 | 107.00 |
| SAT_SOL_BNB_REC95_10_CD72H | satellite | 2022.00 | 5.08% | 5.08% | -5.06% | 1.00 | 57.00 |
| SAT_SOL_BNB_REC95_10_CD72H | satellite | 2025.00 | -2.63% | -2.63% | -9.39% | -0.28 | 105.00 |
| SAT_SOL_BNB_REC95_15_CDNONE | satellite | 2022.00 | 5.25% | 5.26% | -5.02% | 1.05 | 60.00 |
| SAT_SOL_BNB_REC95_15_CDNONE | satellite | 2025.00 | -2.59% | -2.59% | -9.40% | -0.28 | 110.00 |
| SAT_SOL_BNB_REC95_15_CD48H | satellite | 2022.00 | 5.16% | 5.16% | -5.02% | 1.03 | 58.00 |
| SAT_SOL_BNB_REC95_15_CD48H | satellite | 2025.00 | -2.41% | -2.41% | -9.39% | -0.26 | 107.00 |
| SAT_SOL_BNB_REC95_15_CD72H | satellite | 2022.00 | 5.24% | 5.24% | -5.02% | 1.04 | 57.00 |
| SAT_SOL_BNB_REC95_15_CD72H | satellite | 2025.00 | -2.30% | -2.30% | -9.39% | -0.25 | 105.00 |
| SAT_SOL_BNB_REC95_25_CDNONE | satellite | 2022.00 | 5.58% | 5.58% | -4.95% | 1.13 | 60.00 |
| SAT_SOL_BNB_REC95_25_CDNONE | satellite | 2025.00 | -2.12% | -2.12% | -9.39% | -0.23 | 110.00 |
| SAT_SOL_BNB_REC95_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC95_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2022.00 | 5.56% | 5.57% | -4.94% | 1.13 | 57.00 |
| SAT_SOL_BNB_REC95_25_CD72H | satellite | 2025.00 | -1.64% | -1.64% | -9.39% | -0.17 | 105.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2022.00 | 5.42% | 5.42% | -4.94% | 1.10 | 58.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | 2025.00 | -1.81% | -1.81% | -9.39% | -0.19 | 107.00 |

## Bull / Bear / Sideways

| Variant | Group | State | PnL | PF | Win | Trades |
|---|---|---|---|---|---|---|
| V0_BASELINE | comparison | bull | 175.91% | 1.24 | 36.98% | 695.00 |
| V0_BASELINE | comparison | bear | -2.33% | 0.00 | 0.00% | 1.00 |
| V0_BASELINE | comparison | sideways | -58.25% | 0.80 | 26.61% | 233.00 |
| V4H_STRICT_BASE | comparison | bull | 306.26% | 1.21 | 37.90% | 1066.00 |
| V4H_STRICT_BASE | comparison | bear | -38.37% | 0.47 | 21.74% | 69.00 |
| V4H_STRICT_BASE | comparison | sideways | -105.02% | 0.77 | 31.75% | 252.00 |
| V4H_REC92_25_ORIGINAL | comparison | bull | 323.10% | 1.19 | 37.66% | 1078.00 |
| V4H_REC92_25_ORIGINAL | comparison | bear | -31.02% | 0.71 | 36.24% | 149.00 |
| V4H_REC92_25_ORIGINAL | comparison | sideways | -89.03% | 0.81 | 37.02% | 289.00 |
| V4H_REC92_15_ALL | comparison | bull | 311.61% | 1.19 | 37.66% | 1078.00 |
| V4H_REC92_15_ALL | comparison | bear | -30.53% | 0.66 | 36.24% | 149.00 |
| V4H_REC92_15_ALL | comparison | sideways | -94.86% | 0.79 | 37.02% | 289.00 |
| V4H_REC92_25_SOLBNB_94_15 | comparison | bull | 318.19% | 1.19 | 37.66% | 1078.00 |
| V4H_REC92_25_SOLBNB_94_15 | comparison | bear | -32.61% | 0.68 | 36.24% | 149.00 |
| V4H_REC92_25_SOLBNB_94_15 | comparison | sideways | -94.01% | 0.80 | 37.02% | 289.00 |
| CORE_NO_SOL_BNB_REC90_10 | core | bull | 47.91% | 1.05 | 35.79% | 1003.00 |
| CORE_NO_SOL_BNB_REC90_10 | core | bear | -22.15% | 0.62 | 31.52% | 165.00 |
| CORE_NO_SOL_BNB_REC90_10 | core | sideways | -58.25% | 0.74 | 35.29% | 272.00 |
| CORE_NO_SOL_BNB_REC90_15 | core | bull | 46.23% | 1.05 | 35.79% | 1003.00 |
| CORE_NO_SOL_BNB_REC90_15 | core | bear | -22.91% | 0.64 | 31.52% | 165.00 |
| CORE_NO_SOL_BNB_REC90_15 | core | sideways | -55.94% | 0.75 | 35.29% | 272.00 |
| CORE_NO_SOL_BNB_REC90_25 | core | bull | 42.62% | 1.05 | 35.79% | 1003.00 |
| CORE_NO_SOL_BNB_REC90_25 | core | bear | -24.60% | 0.68 | 31.52% | 165.00 |
| CORE_NO_SOL_BNB_REC90_25 | core | sideways | -51.13% | 0.79 | 35.29% | 272.00 |
| CORE_NO_SOL_BNB_REC92_10 | core | bull | 44.53% | 1.05 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC92_10 | core | bear | -22.72% | 0.60 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC92_10 | core | sideways | -54.71% | 0.75 | 37.16% | 261.00 |
| CORE_NO_SOL_BNB_REC92_15 | core | bull | 43.06% | 1.05 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC92_15 | core | bear | -23.17% | 0.63 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC92_15 | core | sideways | -52.01% | 0.77 | 37.16% | 261.00 |
| CORE_NO_SOL_BNB_REC92_25 | core | bull | 39.92% | 1.04 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC92_25 | core | bear | -24.18% | 0.67 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC92_25 | core | sideways | -46.37% | 0.80 | 37.16% | 261.00 |
| CORE_NO_SOL_BNB_REC94_10 | core | bull | 44.53% | 1.05 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC94_10 | core | bear | -22.72% | 0.60 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC94_10 | core | sideways | -54.71% | 0.75 | 37.16% | 261.00 |
| CORE_NO_SOL_BNB_REC94_15 | core | bull | 43.06% | 1.05 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC94_15 | core | bear | -23.17% | 0.63 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC94_15 | core | sideways | -52.01% | 0.77 | 37.16% | 261.00 |
| CORE_NO_SOL_BNB_REC94_25 | core | bull | 39.92% | 1.04 | 35.73% | 988.00 |
| CORE_NO_SOL_BNB_REC94_25 | core | bear | -24.18% | 0.67 | 31.03% | 145.00 |
| CORE_NO_SOL_BNB_REC94_25 | core | sideways | -46.37% | 0.80 | 37.16% | 261.00 |
| SAT_SOL_BNB_REC92_05_CDNONE | satellite | bull | 23.35% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC92_05_CDNONE | satellite | bear | -7.60% | 0.48 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC92_05_CDNONE | satellite | sideways | 3.76% | 1.07 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC92_05_CD48H | satellite | bull | 23.13% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_05_CD48H | satellite | bear | -7.39% | 0.49 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC92_05_CD48H | satellite | sideways | 5.90% | 1.10 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC92_05_CD72H | satellite | bull | 23.12% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_05_CD72H | satellite | bear | -7.31% | 0.49 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC92_05_CD72H | satellite | sideways | 5.95% | 1.10 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC92_10_CDNONE | satellite | bull | 23.73% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC92_10_CDNONE | satellite | bear | -8.01% | 0.49 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC92_10_CDNONE | satellite | sideways | 4.74% | 1.08 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC92_10_CD48H | satellite | bull | 23.53% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_10_CD48H | satellite | bear | -7.59% | 0.51 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC92_10_CD48H | satellite | sideways | 6.93% | 1.12 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC92_10_CD72H | satellite | bull | 23.51% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_10_CD72H | satellite | bear | -7.43% | 0.51 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC92_10_CD72H | satellite | sideways | 7.01% | 1.12 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC92_15_CDNONE | satellite | bull | 24.12% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC92_15_CDNONE | satellite | bear | -8.43% | 0.50 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC92_15_CDNONE | satellite | sideways | 5.73% | 1.10 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC92_15_CD48H | satellite | bull | 23.93% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_15_CD48H | satellite | bear | -7.80% | 0.52 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC92_15_CD48H | satellite | sideways | 7.95% | 1.13 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC92_15_CD72H | satellite | bull | 23.91% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_15_CD72H | satellite | bear | -7.55% | 0.53 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC92_15_CD72H | satellite | sideways | 8.08% | 1.14 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | satellite | bull | 24.92% | 1.10 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | satellite | bear | -9.28% | 0.51 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC92_25_CDNONE | satellite | sideways | 7.71% | 1.13 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | bull | 24.76% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | bear | -8.22% | 0.55 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC92_25_CD48H | satellite | sideways | 10.02% | 1.16 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | bull | 24.72% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | bear | -7.80% | 0.55 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC92_25_CD72H | satellite | sideways | 10.25% | 1.17 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC94_05_CDNONE | satellite | bull | 23.35% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC94_05_CDNONE | satellite | bear | -7.60% | 0.48 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC94_05_CDNONE | satellite | sideways | 3.76% | 1.07 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC94_05_CD48H | satellite | bull | 23.13% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_05_CD48H | satellite | bear | -7.39% | 0.49 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC94_05_CD48H | satellite | sideways | 5.90% | 1.10 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC94_05_CD72H | satellite | bull | 23.12% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_05_CD72H | satellite | bear | -7.31% | 0.49 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC94_05_CD72H | satellite | sideways | 5.95% | 1.10 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC94_10_CDNONE | satellite | bull | 23.73% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC94_10_CDNONE | satellite | bear | -8.01% | 0.49 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC94_10_CDNONE | satellite | sideways | 4.74% | 1.08 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC94_10_CD48H | satellite | bull | 23.53% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_10_CD48H | satellite | bear | -7.59% | 0.51 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC94_10_CD48H | satellite | sideways | 6.93% | 1.12 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC94_10_CD72H | satellite | bull | 23.51% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_10_CD72H | satellite | bear | -7.43% | 0.51 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC94_10_CD72H | satellite | sideways | 7.01% | 1.12 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC94_15_CDNONE | satellite | bull | 24.12% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC94_15_CDNONE | satellite | bear | -8.43% | 0.50 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC94_15_CDNONE | satellite | sideways | 5.73% | 1.10 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC94_15_CD48H | satellite | bull | 23.93% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_15_CD48H | satellite | bear | -7.80% | 0.52 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC94_15_CD48H | satellite | sideways | 7.95% | 1.13 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC94_15_CD72H | satellite | bull | 23.91% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_15_CD72H | satellite | bear | -7.55% | 0.53 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC94_15_CD72H | satellite | sideways | 8.08% | 1.14 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC94_25_CDNONE | satellite | bull | 24.92% | 1.10 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC94_25_CDNONE | satellite | bear | -9.28% | 0.51 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC94_25_CDNONE | satellite | sideways | 7.71% | 1.13 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | bull | 24.76% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | bear | -8.22% | 0.55 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC94_25_CD48H | satellite | sideways | 10.02% | 1.16 | 37.70% | 122.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | bull | 24.72% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | bear | -7.80% | 0.55 | 27.45% | 51.00 |
| SAT_SOL_BNB_REC94_25_CD72H | satellite | sideways | 10.25% | 1.17 | 37.19% | 121.00 |
| SAT_SOL_BNB_REC95_05_CDNONE | satellite | bull | 23.35% | 1.09 | 36.22% | 566.00 |
| SAT_SOL_BNB_REC95_05_CDNONE | satellite | bear | -7.60% | 0.48 | 26.67% | 60.00 |
| SAT_SOL_BNB_REC95_05_CDNONE | satellite | sideways | 3.76% | 1.07 | 36.22% | 127.00 |
| SAT_SOL_BNB_REC95_05_CD48H | satellite | bull | 23.13% | 1.09 | 36.17% | 564.00 |
| SAT_SOL_BNB_REC95_05_CD48H | satellite | bear | -7.39% | 0.49 | 25.93% | 54.00 |
| SAT_SOL_BNB_REC95_05_CD48H | satellite | sideways | 5.90% | 1.10 | 37.70% | 122.00 |

## Output Files

- `reports/research/v4h_core_satellite_report.md`
- `reports/research/v4h_core_satellite_summary.csv`
- `reports/research/v4h_core_satellite_core_only.csv`
- `reports/research/v4h_core_satellite_satellite_only.csv`
- `reports/research/v4h_core_satellite_combined.csv`
- `reports/research/v4h_core_satellite_cost_stress.csv`
- `reports/research/v4h_core_satellite_oos_yearly.csv`
- `reports/research/v4h_core_satellite_regime_performance.csv`
- `reports/research/v4h_core_satellite_symbol_contribution.csv`
