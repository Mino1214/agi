# V0 Integer Leverage Sensitivity Audit

- Generated: 2026-06-23 02:48 UTC
- Scope: V0 baseline only, Alpha Engine v1.2 Candidate / 1D EMA regime gate.
- Runtime paths changed: none. This audit imports existing modules, reads cached raw/funding data, and writes reports only.
- Initial equity: 1,000 USD.
- Exchange leverage is integer-only. Position notional is scaled by `effective_exposure = leverage * size_multiplier`.
- Replay model: V0 entries/exits/partials are regenerated per cost scenario, then exposure is replayed with compounding, fees, slippage-adjusted prices, actual funding, and hourly mark-to-market equity.
- Liquidation model: long futures estimate `entry * (1 - 1/leverage + maintenance_margin + liquidation_fee_buffer)` with maintenance 0.5% and buffer 0.1%; 1x has no liquidation price.

## Verdict

Maximum PASS candidate: **3x / size 25%** (effective exposure 0.75x), MDD -21.58%, Calmar 1.08, worst month -6.17%. Maximum combination with cost 2x + slippage 2x account survival and no liquidation/margin flag: **3x / size 75%** (effective exposure 2.25x).

## Test A - Pure Leverage

| Scenario | verdict | Final | Return | CAGR | MDD | calmar | PF | Win | Trades | Max losses | Worst month | Worst year | Liq touch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x / size 100% | WATCH | $5,146.94 | 414.69% | 31.39% | -28.14% | 1.12 | 1.40 | 45.64% | 929 | 10 | -8.27% | 0.00% | 0 |
| 2x / size 100% | FAIL | $20,357.09 | 1935.71% | 65.22% | -50.67% | 1.29 | 1.26 | 45.64% | 929 | 10 | -16.81% | -2.40% | 0 |
| 3x / size 100% | FAIL | $63,800.43 | 6280.04% | 99.86% | -67.86% | 1.47 | 1.18 | 45.64% | 929 | 10 | -25.67% | -7.56% | 0 |
| 4x / size 100% | FAIL | $163,471.92 | 16247.19% | 133.79% | -80.71% | 1.66 | 1.13 | 45.64% | 929 | 10 | -35.32% | -14.86% | 0 |
| 5x / size 100% | FAIL | $348,619.66 | 34761.97% | 165.23% | -90.12% | 1.83 | 1.09 | 45.64% | 929 | 10 | -46.64% | -23.81% | 1 |

## Test B - Practical Exposure

| Scenario | Eff exp | verdict | Final | Return | CAGR | MDD | calmar | PF | Win | Trades | Max losses | Worst month | Worst year | Liq touch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x / size 100% | 1.00 | WATCH | $5,146.94 | 414.69% | 31.39% | -28.14% | 1.12 | 1.40 | 45.64% | 929 | 10 | -8.27% | 0.00% | 0 |
| 2x / size 25% | 0.50 | PASS | $2,344.89 | 134.49% | 15.26% | -14.66% | 1.04 | 1.51 | 45.64% | 929 | 10 | -4.07% | 0.00% | 0 |
| 2x / size 50% | 1.00 | WATCH | $5,146.94 | 414.69% | 31.39% | -28.14% | 1.12 | 1.40 | 45.64% | 929 | 10 | -8.27% | 0.00% | 0 |
| 2x / size 75% | 1.50 | FAIL | $10,563.34 | 956.33% | 48.11% | -40.13% | 1.20 | 1.32 | 45.64% | 929 | 10 | -12.52% | -0.75% | 0 |
| 2x / size 100% | 2.00 | FAIL | $20,357.09 | 1935.71% | 65.22% | -50.67% | 1.29 | 1.26 | 45.64% | 929 | 10 | -16.81% | -2.40% | 0 |
| 3x / size 25% | 0.75 | PASS | $3,503.88 | 250.39% | 23.24% | -21.58% | 1.08 | 1.45 | 45.64% | 929 | 10 | -6.17% | 0.00% | 0 |
| 3x / size 50% | 1.50 | FAIL | $10,563.34 | 956.33% | 48.11% | -40.13% | 1.20 | 1.32 | 45.64% | 929 | 10 | -12.52% | -0.75% | 0 |
| 3x / size 75% | 2.25 | FAIL | $27,643.63 | 2664.36% | 73.86% | -55.43% | 1.33 | 1.24 | 45.64% | 929 | 10 | -18.98% | -3.46% | 0 |
| 3x / size 100% | 3.00 | FAIL | $63,800.43 | 6280.04% | 99.86% | -67.86% | 1.47 | 1.18 | 45.64% | 929 | 10 | -25.67% | -7.56% | 0 |
| 4x / size 25% | 1.00 | WATCH | $5,146.94 | 414.69% | 31.39% | -28.14% | 1.12 | 1.40 | 45.64% | 929 | 10 | -8.27% | 0.00% | 0 |
| 4x / size 50% | 2.00 | FAIL | $20,357.09 | 1935.71% | 65.22% | -50.67% | 1.29 | 1.26 | 45.64% | 929 | 10 | -16.81% | -2.40% | 0 |
| 5x / size 25% | 1.25 | FAIL | $7,434.06 | 643.41% | 39.69% | -34.32% | 1.16 | 1.36 | 45.64% | 929 | 10 | -10.39% | -0.18% | 1 |
| 5x / size 50% | 2.50 | FAIL | $37,019.08 | 3601.91% | 82.53% | -59.87% | 1.38 | 1.22 | 45.64% | 929 | 10 | -21.17% | -4.68% | 1 |

## Cost Stress Focus

| Scenario ID | Cost | Final | Return | MDD | calmar | PF | Trades | bankrupt | margin_call | Liq touch |
|---|---|---|---|---|---|---|---|---|---|---|
| A_pure_1x | base | $5,146.94 | 414.69% | -28.14% | 1.12 | 1.40 | 929 | false | false | 0 |
| A_pure_1x | cost_2x_slippage_2x | $1,302.16 | 30.22% | -53.74% | 0.08 | 1.05 | 969 | false | false | 0 |
| A_pure_1x | cost_3x_slippage_3x | $211.02 | -78.90% | -86.84% | -0.26 | 0.79 | 1066 | false | false | 0 |
| A_pure_2x | base | $20,357.09 | 1935.71% | -50.67% | 1.29 | 1.26 | 929 | false | false | 0 |
| A_pure_2x | cost_2x_slippage_2x | $1,108.43 | 10.84% | -85.47% | 0.02 | 1.01 | 969 | false | false | 0 |
| A_pure_2x | cost_3x_slippage_3x | $0.00 | -100.00% | -100.01% | -1.00 | 0.85 | 754 | true | true | 0 |
| A_pure_3x | base | $63,800.43 | 6280.04% | -67.86% | 1.47 | 1.18 | 929 | false | false | 0 |
| A_pure_3x | cost_2x_slippage_2x | $0.00 | -100.00% | -100.02% | -1.00 | 0.98 | 843 | true | true | 0 |
| A_pure_3x | cost_3x_slippage_3x | $0.00 | -100.00% | -100.09% | -1.00 | 0.90 | 644 | true | true | 0 |
| A_pure_4x | base | $163,471.92 | 16247.19% | -80.71% | 1.66 | 1.13 | 929 | false | false | 0 |
| A_pure_4x | cost_2x_slippage_2x | $0.00 | -100.00% | -100.20% | -1.00 | 0.99 | 685 | true | true | 0 |
| A_pure_4x | cost_3x_slippage_3x | $0.00 | -100.00% | -100.12% | -1.00 | 0.92 | 441 | true | true | 0 |
| A_pure_5x | base | $348,619.66 | 34761.97% | -90.12% | 1.83 | 1.09 | 929 | false | false | 1 |
| A_pure_5x | cost_2x_slippage_2x | $0.00 | -100.00% | -100.23% | -1.00 | 0.99 | 648 | true | true | 1 |
| A_pure_5x | cost_3x_slippage_3x | $0.00 | -100.00% | -100.12% | -1.00 | 0.94 | 424 | true | true | 1 |
| B_2x_size_50 | base | $5,146.94 | 414.69% | -28.14% | 1.12 | 1.40 | 929 | false | false | 0 |
| B_2x_size_50 | cost_2x_slippage_2x | $1,302.16 | 30.22% | -53.74% | 0.08 | 1.05 | 969 | false | false | 0 |
| B_2x_size_50 | cost_3x_slippage_3x | $211.02 | -78.90% | -86.84% | -0.26 | 0.79 | 1066 | false | false | 0 |
| B_2x_size_75 | base | $10,563.34 | 956.33% | -40.13% | 1.20 | 1.32 | 929 | false | false | 0 |
| B_2x_size_75 | cost_2x_slippage_2x | $1,287.75 | 28.78% | -71.82% | 0.06 | 1.03 | 969 | false | false | 0 |
| B_2x_size_75 | cost_3x_slippage_3x | $0.00 | -100.00% | -100.10% | -1.00 | 0.81 | 940 | true | true | 0 |
| B_3x_size_50 | base | $10,563.34 | 956.33% | -40.13% | 1.20 | 1.32 | 929 | false | false | 0 |
| B_3x_size_50 | cost_2x_slippage_2x | $1,287.75 | 28.78% | -71.82% | 0.06 | 1.03 | 969 | false | false | 0 |
| B_3x_size_50 | cost_3x_slippage_3x | $0.00 | -100.00% | -100.10% | -1.00 | 0.81 | 940 | true | true | 0 |

## Effective Exposure Matrix

| Scenario ID | leverage | Size | Eff exp | verdict | Return | MDD | calmar | 2x cost+slip return | 2x cost+slip MDD |
|---|---|---|---|---|---|---|---|---|---|
| B_2x_size_25 | 2 | 25% | 0.50 | PASS | 134.49% | -14.66% | 1.04 | 19.13% | -30.12% |
| B_3x_size_25 | 3 | 25% | 0.75 | PASS | 250.39% | -21.58% | 1.08 | 25.97% | -42.68% |
| A_pure_1x | 1 | 100% | 1.00 | WATCH | 414.69% | -28.14% | 1.12 | 30.22% | -53.74% |
| B_1x_size_100 | 1 | 100% | 1.00 | WATCH | 414.69% | -28.14% | 1.12 | 30.22% | -53.74% |
| B_2x_size_50 | 2 | 50% | 1.00 | WATCH | 414.69% | -28.14% | 1.12 | 30.22% | -53.74% |
| B_4x_size_25 | 4 | 25% | 1.00 | WATCH | 414.69% | -28.14% | 1.12 | 30.22% | -53.74% |
| B_5x_size_25 | 5 | 25% | 1.25 | FAIL | 643.41% | -34.32% | 1.16 | 31.33% | -63.41% |
| B_2x_size_75 | 2 | 75% | 1.50 | FAIL | 956.33% | -40.13% | 1.20 | 28.78% | -71.82% |
| B_3x_size_50 | 3 | 50% | 1.50 | FAIL | 956.33% | -40.13% | 1.20 | 28.78% | -71.82% |
| A_pure_2x | 2 | 100% | 2.00 | FAIL | 1935.71% | -50.67% | 1.29 | 10.84% | -85.47% |
| B_2x_size_100 | 2 | 100% | 2.00 | FAIL | 1935.71% | -50.67% | 1.29 | 10.84% | -85.47% |
| B_4x_size_50 | 4 | 50% | 2.00 | FAIL | 1935.71% | -50.67% | 1.29 | 10.84% | -85.47% |
| B_3x_size_75 | 3 | 75% | 2.25 | FAIL | 2664.36% | -55.43% | 1.33 | -5.32% | -90.96% |
| B_5x_size_50 | 5 | 50% | 2.50 | FAIL | 3601.91% | -59.87% | 1.38 | -26.71% | -95.71% |
| A_pure_3x | 3 | 100% | 3.00 | FAIL | 6280.04% | -67.86% | 1.47 | -100.00% | -100.02% |
| B_3x_size_100 | 3 | 100% | 3.00 | FAIL | 6280.04% | -67.86% | 1.47 | -100.00% | -100.02% |
| A_pure_4x | 4 | 100% | 4.00 | FAIL | 16247.19% | -80.71% | 1.66 | -100.00% | -100.20% |
| A_pure_5x | 5 | 100% | 5.00 | FAIL | 34761.97% | -90.12% | 1.83 | -100.00% | -100.23% |

## 2x Size Sensitivity

| Scenario | Eff exp | verdict | Final | Return | MDD | calmar | Worst month | Liq touch |
|---|---|---|---|---|---|---|---|---|
| 2x / size 25% | 0.50 | PASS | $2,344.89 | 134.49% | -14.66% | 1.04 | -4.07% | 0 |
| 2x / size 50% | 1.00 | WATCH | $5,146.94 | 414.69% | -28.14% | 1.12 | -8.27% | 0 |
| 2x / size 75% | 1.50 | FAIL | $10,563.34 | 956.33% | -40.13% | 1.20 | -12.52% | 0 |
| 2x / size 100% | 2.00 | FAIL | $20,357.09 | 1935.71% | -50.67% | 1.29 | -16.81% | 0 |

## 3x Size Sensitivity

| Scenario | Eff exp | verdict | Final | Return | MDD | calmar | Worst month | Liq touch |
|---|---|---|---|---|---|---|---|---|
| 3x / size 25% | 0.75 | PASS | $3,503.88 | 250.39% | -21.58% | 1.08 | -6.17% | 0 |
| 3x / size 50% | 1.50 | FAIL | $10,563.34 | 956.33% | -40.13% | 1.20 | -12.52% | 0 |
| 3x / size 75% | 2.25 | FAIL | $27,643.63 | 2664.36% | -55.43% | 1.33 | -18.98% | 0 |
| 3x / size 100% | 3.00 | FAIL | $63,800.43 | 6280.04% | -67.86% | 1.47 | -25.67% | 0 |

## MDD Threshold Flags

| Scenario ID | Scenario | MDD | mdd_breach_40 | mdd_breach_50 | mdd_breach_60 | Min equity | DD duration days |
|---|---|---|---|---|---|---|---|
| A_pure_5x | 5x / size 100% | -90.12% | true | true | true | $995.75 | 794.8 |
| A_pure_4x | 4x / size 100% | -80.71% | true | true | true | $996.60 | 794.8 |
| A_pure_3x | 3x / size 100% | -67.86% | true | true | true | $997.45 | 794.8 |
| B_3x_size_100 | 3x / size 100% | -67.86% | true | true | true | $997.45 | 794.8 |
| B_5x_size_50 | 5x / size 50% | -59.87% | true | true | false | $997.88 | 794.8 |
| B_3x_size_75 | 3x / size 75% | -55.43% | true | true | false | $998.09 | 794.8 |
| A_pure_2x | 2x / size 100% | -50.67% | true | true | false | $998.30 | 776.1 |
| B_2x_size_100 | 2x / size 100% | -50.67% | true | true | false | $998.30 | 776.1 |
| B_4x_size_50 | 4x / size 50% | -50.67% | true | true | false | $998.30 | 776.1 |
| B_2x_size_75 | 2x / size 75% | -40.13% | true | false | false | $998.73 | 776.0 |
| B_3x_size_50 | 3x / size 50% | -40.13% | true | false | false | $998.73 | 776.0 |

## Notes

- PASS requires base MDD within -35%, no liquidation/margin-call risk, survival under cost 2x + slippage 2x, tolerable worst month, and Calmar not materially worse than 1x.
- WATCH marks MDD -35% to -50%, weak cost stress, large worst month/year, or Calmar below 70% of 1x.
- FAIL marks MDD worse than -50%, any liquidation/margin-call/bankruptcy risk, severe cost stress collapse, or excessive worst-month/year loss.
- CSV files are under `crypto_regime_map/reports/research/` and remain ignored by `.gitignore`; this Markdown report is the only intended commit candidate.

## Output Files

- `v0_integer_leverage_sensitivity_report.md`
- `v0_integer_leverage_summary.csv`
- `v0_integer_leverage_exposure_matrix.csv`
- `v0_integer_leverage_equity_curves.csv`
- `v0_integer_leverage_monthly_returns.csv`
- `v0_integer_leverage_yearly_returns.csv`
- `v0_integer_leverage_cost_stress.csv`
- `v0_integer_leverage_liquidation_risk.csv`
