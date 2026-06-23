# ML Regime v3 Hybrid Backtest Report

- Generated: 2026-06-22 14:26:45 UTC
- Scope: offline backtest/report only; ML remains OFF by default.
- Runtime paper engine and live order logic were not modified.
- V2 preserved as WATCH: Shock recall 94.46%, FPR 88.87%, Opportunity precision 70.80%, baseline 59.60%, delta +11.20%p.
- Prediction source: `/home/myno/바탕화면/agi/agi/crypto_regime_map/reports/research/ml_regime_v2_predictions.csv`
- Backtest window: 2023-12-23 to 2026-01-01 UTC, restricted to walk-forward prediction coverage.
- Trade-time ML lookup uses the previous UTC daily prediction only, so daily close features are never used on the same intraday trade date.
- Shock Guard is reference-only; p_shock never hard-blocks an entry.

## PASS/WATCH/FAIL

- Status: FAIL
- Best base hybrid: ML_OPP_SIZE_ADJUST total return -4.20%, Calmar -0.1168.
- V0 base: total return 6.61%, MDD -26.94%, Calmar 0.1192.
- 2x fee+slippage delta for best hybrid vs V0: return 15.00%, Calmar 0.0319.
- No base hybrid improves total return or Calmar versus V0.
- V0 trades allowed by p_opportunity >= 0.60 have weaker PF than blocked trades, so ML is not selecting better entries.

## Base Comparison

| Policy | Scenario | Return | CAGR | MDD | Calmar | Sharpe | Sortino | PF | Win | Trades | Avg R | Median Trade | Max Losses | Ret Δ | MDD Δ | Trades Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_EMA_BASELINE | base | 6.61% | 3.21% | -26.94% | 0.1192 | 0.2703 | 0.2268 | 0.8049 | 28.15% | 476 | -0.1002 | -0.51% | 17 | 0.00% | 0.00% | 0 |
| ML_OPP_FILTER_60 | base | -8.75% | -4.42% | -20.52% | -0.2153 | -0.3475 | -0.1984 | 0.6264 | 25.94% | 239 | -0.2143 | -0.50% | 17 | -15.36% | 6.42% | -237 |
| ML_OPP_FILTER_65 | base | -5.99% | -3.00% | -17.02% | -0.1764 | -0.2475 | -0.1290 | 0.6591 | 23.81% | 189 | -0.1962 | -0.48% | 14 | -12.60% | 9.92% | -287 |
| ML_OPP_FILTER_70 | base | -8.34% | -4.21% | -19.33% | -0.2177 | -0.5458 | -0.2267 | 0.4757 | 25.64% | 117 | -0.2969 | -0.38% | 15 | -14.96% | 7.61% | -359 |
| ML_OPP_SIZE_ADJUST | base | -4.20% | -2.10% | -17.95% | -0.1168 | -0.2160 | -0.1632 | 0.6762 | 28.15% | 476 | -0.1002 | -0.13% | 17 | -10.82% | 8.99% | 0 |
| ML_OPP_WITH_SHOCK_SOFT | base | -4.20% | -2.10% | -17.95% | -0.1168 | -0.2160 | -0.1632 | 0.6762 | 28.15% | 476 | -0.1002 | -0.13% | 17 | -10.82% | 8.99% | 0 |

## Cost Stress

| Policy | Scenario | Return | CAGR | MDD | Calmar | Sharpe | Sortino | PF | Win | Trades | Avg R | Median Trade | Max Losses | Ret Δ | MDD Δ | Trades Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_EMA_BASELINE | cost_2x_slippage_2x | -42.64% | -23.99% | -50.67% | -0.4736 | -1.5578 | -1.2827 | 0.5489 | 23.49% | 498 | -0.2767 | -0.52% | 21 | 0.00% | 0.00% | 0 |
| ML_OPP_FILTER_60 | cost_2x_slippage_2x | -35.22% | -19.29% | -38.08% | -0.5065 | -1.9199 | -1.0683 | 0.4098 | 20.55% | 253 | -0.4041 | -0.51% | 21 | 7.42% | 12.58% | -245 |
| ML_OPP_FILTER_65 | cost_2x_slippage_2x | -29.20% | -15.67% | -31.03% | -0.5050 | -1.6703 | -0.8415 | 0.4097 | 18.72% | 203 | -0.3976 | -0.51% | 17 | 13.44% | 19.63% | -295 |
| ML_OPP_FILTER_70 | cost_2x_slippage_2x | -21.24% | -11.12% | -28.72% | -0.3870 | -1.6100 | -0.6713 | 0.3187 | 22.76% | 123 | -0.4590 | -0.51% | 17 | 21.40% | 21.94% | -375 |
| ML_OPP_SIZE_ADJUST | cost_2x_slippage_2x | -27.64% | -14.76% | -33.41% | -0.4417 | -1.8699 | -1.3589 | 0.4680 | 23.49% | 498 | -0.2767 | -0.13% | 21 | 15.00% | 17.25% | 0 |
| ML_OPP_WITH_SHOCK_SOFT | cost_2x_slippage_2x | -27.64% | -14.76% | -33.41% | -0.4417 | -1.8699 | -1.3589 | 0.4680 | 23.49% | 498 | -0.2767 | -0.13% | 21 | 15.00% | 17.25% | 0 |
| V0_EMA_BASELINE | cost_3x_slippage_3x | -71.00% | -45.72% | -71.25% | -0.6416 | -3.5412 | -2.8674 | 0.3823 | 17.64% | 533 | -0.4435 | -0.53% | 26 | 0.00% | 0.00% | 0 |
| ML_OPP_FILTER_60 | cost_3x_slippage_3x | -53.60% | -31.55% | -54.07% | -0.5834 | -3.3807 | -1.8371 | 0.2939 | 15.02% | 273 | -0.5529 | -0.53% | 36 | 17.40% | 17.18% | -260 |
| ML_OPP_FILTER_65 | cost_3x_slippage_3x | -45.10% | -25.62% | -46.38% | -0.5524 | -2.8861 | -1.4312 | 0.2958 | 14.35% | 216 | -0.5434 | -0.53% | 27 | 25.89% | 24.87% | -317 |
| ML_OPP_FILTER_70 | cost_3x_slippage_3x | -31.51% | -17.04% | -36.99% | -0.4607 | -2.5270 | -1.0222 | 0.2281 | 18.90% | 127 | -0.5969 | -0.52% | 18 | 39.48% | 34.26% | -406 |
| ML_OPP_SIZE_ADJUST | cost_3x_slippage_3x | -46.97% | -26.88% | -47.51% | -0.5659 | -3.6532 | -2.6059 | 0.3275 | 17.64% | 533 | -0.4435 | -0.14% | 26 | 24.02% | 23.75% | 0 |
| ML_OPP_WITH_SHOCK_SOFT | cost_3x_slippage_3x | -46.97% | -26.88% | -47.51% | -0.5659 | -3.6532 | -2.6059 | 0.3275 | 17.64% | 533 | -0.4435 | -0.14% | 26 | 24.02% | 23.75% | 0 |

## V0 vs Best Hybrid

- Best hybrid by Calmar: ML_OPP_SIZE_ADJUST
- Total return delta vs V0: -10.82%
- MDD delta vs V0: 8.99%
- Calmar delta vs V0: -0.2360
- Trade count delta vs V0: 0
- V0 total return / MDD / Calmar: 6.61% / -26.94% / 0.1192

## Trade Attribution

| Group | Trades | Total PnL | Avg PnL | Win | PF | Median Return | Avg R |
|---|---:|---:|---:|---:|---:|---:|---:|
| allowed_by_opp_0.60 | 206 | -0.2256 | -0.0011 | 27.18% | 0.6218 | -0.42% | -0.2097 |
| blocked_by_opp_0.60 | 270 | -0.0532 | -0.0002 | 28.89% | 0.9361 | -0.51% | -0.0166 |
| allowed_by_opp_0.65 | 167 | -0.2243 | -0.0013 | 23.95% | 0.5473 | -0.44% | -0.2566 |
| blocked_by_opp_0.65 | 309 | -0.0545 | -0.0002 | 30.42% | 0.9416 | -0.51% | -0.0157 |
| allowed_by_opp_0.70 | 100 | -0.1824 | -0.0018 | 25.00% | 0.3736 | -0.38% | -0.3556 |
| blocked_by_opp_0.70 | 376 | -0.0964 | -0.0003 | 28.99% | 0.9153 | -0.51% | -0.0323 |
| ema_defensive_high_opportunity | 0 | 0.0000 |  | 0.00% |  |  |  |
| ema_uptrend_low_opportunity | 255 | -0.0545 | -0.0002 | 29.02% | 0.9301 | -0.51% | -0.0228 |

## Probability Bins

| Group | Trades | Total PnL | Avg PnL | Win | PF | Median Return | Avg R |
|---|---:|---:|---:|---:|---:|---:|---:|
| p_opportunity_lt_0_50 | 170 | -0.0307 | -0.0002 | 27.65% | 0.9444 | -0.51% | -0.0033 |
| p_opportunity_0_50_0_60 | 100 | -0.0225 | -0.0002 | 31.00% | 0.9198 | -0.46% | -0.0394 |
| p_opportunity_0_60_0_65 | 39 | -0.0012 | -0.0000 | 41.03% | 0.9877 | -0.10% | -0.0090 |
| p_opportunity_0_65_0_70 | 67 | -0.0419 | -0.0006 | 22.39% | 0.7948 | -0.47% | -0.1088 |
| p_opportunity_0_70_0_80 | 81 | -0.1420 | -0.0018 | 27.16% | 0.4045 | -0.50% | -0.3420 |
| p_opportunity_0_80_plus | 19 | -0.0403 | -0.0021 | 15.79% | 0.2335 | -0.20% | -0.4133 |
| p_shock_lt_0_30 | 32 | -0.1169 | -0.0037 | 18.75% | 0.1409 | -0.51% | -0.6689 |
| p_shock_0_30_0_50 | 437 | -0.1544 | -0.0004 | 28.60% | 0.8791 | -0.50% | -0.0563 |
| p_shock_0_50_0_70 | 7 | -0.0076 | -0.0011 | 42.86% | 0.5184 | -0.10% | -0.2399 |
| p_shock_0_70_0_85 | 0 | 0.0000 |  | 0.00% |  |  |  |
| p_shock_0_85_plus | 0 | 0.0000 |  | 0.00% |  |  |  |

## Monthly Returns

| Month | V0_EMA_BASELINE | ML_OPP_FILTER_60 | ML_OPP_FILTER_65 | ML_OPP_FILTER_70 | ML_OPP_SIZE_ADJUST | ML_OPP_WITH_SHOCK_SOFT |
|---|---|---|---|---|---|---|
| 2023-12 | -0.64% | 0.18% | 0.04% | 0.00% | 0.03% | 0.03% |
| 2024-01 | -4.92% | -0.82% | -2.67% | 0.40% | -1.24% | -1.24% |
| 2024-02 | 10.21% | 4.04% | 4.04% | 3.56% | 3.11% | 3.11% |
| 2024-03 | -3.42% | -3.38% | -3.37% | -3.18% | -3.66% | -3.66% |
| 2024-04 | -4.67% | -3.97% | -2.42% | -3.52% | -3.66% | -3.66% |
| 2024-05 | -6.59% | -4.70% | -3.75% | 0.68% | -2.89% | -2.89% |
| 2024-06 | 0.10% | 3.21% | 4.35% | 0.00% | 0.87% | 0.87% |
| 2024-07 | -2.87% | 0.00% | 0.00% | 0.00% | -0.72% | -0.72% |
| 2024-08 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2024-09 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2024-10 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2024-11 | 18.06% | 5.43% | 0.70% | -2.08% | 5.25% | 5.25% |
| 2024-12 | -3.11% | -1.69% | -0.65% | -3.89% | -3.04% | -3.04% |
| 2025-01 | 0.38% | -2.06% | -2.80% | 0.95% | 0.79% | 0.79% |
| 2025-02 | -1.88% | 0.19% | -0.76% | -0.42% | -0.63% | -0.63% |
| 2025-03 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2025-04 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2025-05 | -4.62% | -4.61% | -1.07% | -0.93% | -2.50% | -2.50% |
| 2025-06 | -7.69% | -1.94% | 0.00% | 0.00% | -1.86% | -1.86% |
| 2025-07 | 18.58% | 0.79% | 0.00% | 0.00% | 4.86% | 4.86% |
| 2025-08 | 1.32% | 0.00% | 0.00% | 0.00% | 0.36% | 0.36% |
| 2025-09 | -1.63% | -1.15% | 0.12% | 0.00% | -0.64% | -0.64% |
| 2025-10 | 4.47% | 2.04% | 2.52% | 0.00% | 1.88% | 1.88% |
| 2025-11 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| 2025-12 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

## Yearly Returns

| Year | V0_EMA_BASELINE | ML_OPP_FILTER_60 | ML_OPP_FILTER_65 | ML_OPP_FILTER_70 | ML_OPP_SIZE_ADJUST | ML_OPP_WITH_SHOCK_SOFT |
|---|---|---|---|---|---|---|
| 2023 | -0.64% | 0.18% | 0.04% | 0.00% | 0.03% | 0.03% |
| 2024 | 0.22% | -2.38% | -4.07% | -7.97% | -6.20% | -6.20% |
| 2025 | 7.07% | -6.69% | -2.04% | -0.40% | 2.10% | 2.10% |

## Lookahead / Leakage Audit

- Only v2 walk-forward predictions are used.
- Entry decisions use prediction date = fill UTC date minus one day.
- V0 and ML variants share the same data, fees, slippage, actual funding, top-score rule, liquidation buffer, and exits.
- Thresholds are fixed experiment constants: 0.60, 0.65, 0.70. They are not optimized on the test period.
- p_shock is used only for size reduction in `ML_OPP_WITH_SHOCK_SOFT`; it never blocks entries.
- Existing Alpha Engine v1.2 Candidate baseline code path remains unchanged; this script is standalone offline research.

## Decomposition

| Policy | Return Delta | MDD Delta | Trade Delta | Interpretation |
|---|---:|---:|---:|---|
| ML_OPP_FILTER_60 | -15.36% | 6.42% | -237 | drawdown improvement only |
| ML_OPP_FILTER_65 | -12.60% | 9.92% | -287 | drawdown improvement only |
| ML_OPP_FILTER_70 | -14.96% | 7.61% | -359 | drawdown improvement only |
| ML_OPP_SIZE_ADJUST | -10.82% | 8.99% | 0 | drawdown improvement only |
| ML_OPP_WITH_SHOCK_SOFT | -10.82% | 8.99% | 0 | drawdown improvement only |

## Outputs

- `ml_regime_v3_hybrid_backtest_report.md`
- `ml_regime_v3_hybrid_summary.csv`
- `ml_regime_v3_equity_curves.csv`
- `ml_regime_v3_trade_attribution.csv`
- `ml_regime_v3_cost_stress.csv`
- `ml_regime_v3_probability_bins.csv`
