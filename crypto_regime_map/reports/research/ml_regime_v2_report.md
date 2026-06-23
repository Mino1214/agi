# ML Regime v2 Report

- Generated: 2026-06-22 14:04:55 UTC
- Scope: offline research/report/backtest only; paper engine and live order logic untouched.
- Default runtime state: ML Regime v2 OFF.

## v0 Failure Summary

- v0 verdict: FAIL
- recovery/uptrend precision: 38.59%
- baseline: 36.11%
- shock recall: 2.90%
- macro F1: 16.00%

## v2 Structure

- Stage 1 Shock Guard: binary probability model for future 14d max drawdown breach.
- Stage 2 Recovery/Uptrend Detector: binary opportunity model trained/evaluated on non-shock rows.
- Thresholds are selected inside each train fold only, then applied unchanged to the later test fold.
- Opportunity pass check uses precision improvement over baseline as a rough cost/slippage buffer; no fills or orders are modeled.
- final_ml_state: shock_guard first, recovery_candidate second, otherwise neutral_or_follow_ema.

## Data

- Usable data period: 2020-08-30 to 2026-06-08
- Usable rows after warmup/label drop: 2109
- Shock label: future_max_drawdown_14d <= -8.00%
- Opportunity label: 14d return >= 5% with 14d drawdown > -8%, or 7d return >= 3% with 7d drawdown > -5%.

## Features

- Used feature count: 37
- return_1d
- return_3d
- return_7d
- return_14d
- distance_to_ema20
- distance_to_ema50
- distance_to_ema200
- ema20_slope
- ema50_slope
- ema200_slope
- volatility_7d
- volatility_14d
- volatility_30d
- drawdown_from_30d_high
- drawdown_from_90d_high
- volume_change_7d
- eth_btc_return_spread_7d
- eth_btc_trend
- sol_btc_return_spread_7d
- sol_btc_trend
- btc_funding_rate
- btc_funding_rate_7d
- eth_btc_return_spread_3d
- eth_btc_return_spread_14d
- sol_btc_return_spread_3d
- sol_btc_return_spread_14d
- volume_zscore_30d
- volatility_compression
- drawdown_recovery_ratio
- btc_funding_rate_change_7d
- btc_1h_return_6h
- btc_4h_return_12h
- btc_4h_return_24h
- btc_4h_return_48h
- btc_4h_distance_to_ema50
- btc_4h_distance_to_ema200
- btc_4h_volatility_7d

## Missing Features

- btc_open_interest_change_7d
- btc_dominance_trend_30d
- total_market_trend_30d
- total2_market_trend_30d
- total3_market_trend_30d
- BTCDOM cache missing (BTCDOMUSDT_1d.json, BTC_D_1d.json, BTC.D_1d.json, BTC_DOMINANCE_1d.json)
- TOTAL cache missing (TOTAL_1d.json, TOTALUSDT_1d.json)
- TOTAL2 cache missing (TOTAL2_1d.json, TOTAL2USDT_1d.json)
- TOTAL3 cache missing (TOTAL3_1d.json, TOTAL3USDT_1d.json)
- cache missing (BTCUSDT_futures_open_interest.json, BTCUSDT_open_interest.json, BTCUSDT_futures_open_interest_hist.json)

## Shock Label Distribution

| Label | Count | Share |
|---|---:|---:|
| not_shock | 1312 | 62.21% |
| shock | 797 | 37.79% |

## Opportunity Label Distribution

| Label | Count | Share |
|---|---:|---:|
| not_opportunity | 513 | 39.10% |
| opportunity | 799 | 60.90% |

## Shock Guard Walk-Forward

| Model | Folds | Threshold | Recall | Precision | FPR | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 5 | 0.21 | 94.46% | 36.93% | 88.87% | 38.10% | 50.70% |
| LightGBM | 5 | 0.80 | 3.50% | 39.11% | 6.08% | 31.52% | 44.05% |
| Random Forest | 5 | 0.74 | 1.21% | 16.00% | 1.59% | 31.21% | 42.14% |

## Opportunity Detector Walk-Forward

| Model | Folds | Threshold | Precision | Baseline | Delta | Recall | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Random Forest | 5 | 0.72 | 70.80% | 59.60% | 11.20% | 9.12% | 61.35% | 45.67% |
| LightGBM | 5 | 0.55 | 61.30% | 59.60% | 1.71% | 46.64% | 62.90% | 48.73% |
| Logistic Regression | 5 | 0.16 | 60.14% | 59.60% | 0.55% | 85.47% | 55.76% | 45.34% |

## Selected Threshold Results

| Task | Model | Fold | Test | Threshold | Precision | Recall | FPR | PR-AUC |
|---|---|---:|---|---:|---:|---:|---:|---:|
| shock | Logistic Regression | 1 | 2023-12-22 to 2024-06-18 | 0.10 | 38.33% | 100.00% | 100.00% | 54.23% |
| shock | Random Forest | 1 | 2023-12-22 to 2024-06-18 | 0.75 | 30.00% | 4.35% | 6.31% | 35.64% |
| shock | LightGBM | 1 | 2023-12-22 to 2024-06-18 | 0.85 | 36.36% | 5.80% | 6.31% | 38.16% |
| shock | Logistic Regression | 2 | 2024-06-19 to 2024-12-15 | 0.25 | 32.78% | 100.00% | 100.00% | 29.72% |
| shock | Random Forest | 2 | 2024-06-19 to 2024-12-15 | 0.75 | 0.00% | 0.00% | 0.00% | 28.78% |
| shock | LightGBM | 2 | 2024-06-19 to 2024-12-15 | 0.85 | 100.00% | 1.69% | 0.00% | 29.26% |
| shock | Logistic Regression | 3 | 2024-12-16 to 2025-06-13 | 0.35 | 47.96% | 72.31% | 44.35% | 40.31% |
| shock | Random Forest | 3 | 2024-12-16 to 2025-06-13 | 0.75 | 0.00% | 0.00% | 0.00% | 26.83% |
| shock | LightGBM | 3 | 2024-12-16 to 2025-06-13 | 0.80 | 25.00% | 1.54% | 2.61% | 27.59% |
| shock | Logistic Regression | 4 | 2025-06-14 to 2025-12-10 | 0.20 | 32.78% | 100.00% | 100.00% | 43.35% |
| shock | Random Forest | 4 | 2025-06-14 to 2025-12-10 | 0.75 | 50.00% | 1.69% | 0.83% | 37.94% |
| shock | LightGBM | 4 | 2025-06-14 to 2025-12-10 | 0.80 | 23.08% | 5.08% | 8.26% | 34.86% |
| shock | Logistic Regression | 5 | 2025-12-11 to 2026-06-08 | 0.15 | 32.78% | 100.00% | 100.00% | 22.90% |
| shock | Random Forest | 5 | 2025-12-11 to 2026-06-08 | 0.70 | 0.00% | 0.00% | 0.83% | 26.87% |
| shock | LightGBM | 5 | 2025-12-11 to 2026-06-08 | 0.70 | 11.11% | 3.39% | 13.22% | 27.75% |
| opportunity | Logistic Regression | 1 | 2023-12-22 to 2024-06-18 | 0.05 | 71.17% | 100.00% | 100.00% | 59.89% |
| opportunity | Random Forest | 1 | 2023-12-22 to 2024-06-18 | 0.70 | 56.67% | 21.52% | 40.62% | 62.41% |
| opportunity | LightGBM | 1 | 2023-12-22 to 2024-06-18 | 0.50 | 63.29% | 63.29% | 90.62% | 60.99% |
| opportunity | Logistic Regression | 2 | 2024-06-19 to 2024-12-15 | 0.60 | 81.25% | 27.37% | 23.08% | 80.57% |
| opportunity | Random Forest | 2 | 2024-06-19 to 2024-12-15 | 0.75 | 100.00% | 2.11% | 0.00% | 78.37% |
| opportunity | LightGBM | 2 | 2024-06-19 to 2024-12-15 | 0.55 | 82.54% | 54.74% | 42.31% | 85.79% |
| opportunity | Logistic Regression | 3 | 2024-12-16 to 2025-06-13 | 0.05 | 57.39% | 100.00% | 100.00% | 58.52% |
| opportunity | Random Forest | 3 | 2024-12-16 to 2025-06-13 | 0.75 | 68.75% | 16.67% | 10.20% | 59.85% |
| opportunity | LightGBM | 3 | 2024-12-16 to 2025-06-13 | 0.50 | 55.13% | 65.15% | 71.43% | 64.12% |
| opportunity | Logistic Regression | 4 | 2025-06-14 to 2025-12-10 | 0.05 | 41.32% | 100.00% | 100.00% | 34.19% |
| opportunity | Random Forest | 4 | 2025-06-14 to 2025-12-10 | 0.70 | 100.00% | 2.00% | 0.00% | 63.25% |
| opportunity | LightGBM | 4 | 2025-06-14 to 2025-12-10 | 0.55 | 55.56% | 30.00% | 16.90% | 56.83% |
| opportunity | Logistic Regression | 5 | 2025-12-11 to 2026-06-08 | 0.05 | 49.59% | 100.00% | 100.00% | 45.63% |
| opportunity | Random Forest | 5 | 2025-12-11 to 2026-06-08 | 0.70 | 28.57% | 3.33% | 8.20% | 42.88% |
| opportunity | LightGBM | 5 | 2025-12-11 to 2026-06-08 | 0.65 | 50.00% | 20.00% | 19.67% | 46.78% |

## final_ml_state Distribution

| State | Count | Share |
|---|---:|---:|
| neutral_or_follow_ema | 1145 | 42.41% |
| recovery_candidate | 677 | 25.07% |
| shock_guard | 878 | 32.52% |

## Feature Importance

| Task | Model | Rank | Feature | Importance |
|---|---|---:|---|---:|
| opportunity | LightGBM | 1 | ema200_slope | 0.0604 |
| opportunity | LightGBM | 2 | volatility_compression | 0.0592 |
| opportunity | LightGBM | 3 | distance_to_ema200 | 0.0590 |
| opportunity | LightGBM | 4 | volatility_14d | 0.0568 |
| opportunity | LightGBM | 5 | volatility_30d | 0.0427 |
| opportunity | LightGBM | 6 | drawdown_from_90d_high | 0.0423 |
| opportunity | LightGBM | 7 | sol_btc_trend | 0.0398 |
| opportunity | LightGBM | 8 | eth_btc_return_spread_14d | 0.0390 |
| opportunity | LightGBM | 9 | sol_btc_return_spread_7d | 0.0359 |
| opportunity | LightGBM | 10 | eth_btc_trend | 0.0344 |
| opportunity | LightGBM | 11 | btc_1h_return_6h | 0.0321 |
| opportunity | LightGBM | 12 | ema50_slope | 0.0294 |
| opportunity | LightGBM | 13 | btc_4h_volatility_7d | 0.0269 |
| opportunity | LightGBM | 14 | eth_btc_return_spread_3d | 0.0259 |
| opportunity | LightGBM | 15 | sol_btc_return_spread_3d | 0.0259 |
| opportunity | LightGBM | 16 | drawdown_from_30d_high | 0.0250 |
| opportunity | LightGBM | 17 | drawdown_recovery_ratio | 0.0240 |
| opportunity | LightGBM | 18 | volume_change_7d | 0.0237 |
| opportunity | LightGBM | 19 | distance_to_ema50 | 0.0232 |
| opportunity | LightGBM | 20 | return_14d | 0.0232 |
| opportunity | Logistic Regression | 1 | drawdown_from_90d_high | 0.0937 |
| opportunity | Logistic Regression | 2 | btc_4h_distance_to_ema200 | 0.0771 |
| opportunity | Logistic Regression | 3 | distance_to_ema20 | 0.0727 |
| opportunity | Logistic Regression | 4 | volatility_7d | 0.0667 |
| opportunity | Logistic Regression | 5 | ema20_slope | 0.0565 |
| opportunity | Logistic Regression | 6 | ema200_slope | 0.0543 |
| opportunity | Logistic Regression | 7 | sol_btc_trend | 0.0508 |
| opportunity | Logistic Regression | 8 | eth_btc_trend | 0.0433 |
| opportunity | Logistic Regression | 9 | btc_4h_distance_to_ema50 | 0.0389 |
| opportunity | Logistic Regression | 10 | return_14d | 0.0382 |
| opportunity | Logistic Regression | 11 | ema50_slope | 0.0361 |
| opportunity | Logistic Regression | 12 | distance_to_ema200 | 0.0306 |
| opportunity | Logistic Regression | 13 | drawdown_from_30d_high | 0.0305 |
| opportunity | Logistic Regression | 14 | drawdown_recovery_ratio | 0.0302 |
| opportunity | Logistic Regression | 15 | btc_4h_return_48h | 0.0269 |
| opportunity | Logistic Regression | 16 | sol_btc_return_spread_14d | 0.0263 |
| opportunity | Logistic Regression | 17 | volatility_30d | 0.0260 |
| opportunity | Logistic Regression | 18 | volatility_compression | 0.0245 |
| opportunity | Logistic Regression | 19 | btc_1h_return_6h | 0.0234 |
| opportunity | Logistic Regression | 20 | distance_to_ema50 | 0.0202 |
| opportunity | Random Forest | 1 | ema200_slope | 0.0684 |
| opportunity | Random Forest | 2 | distance_to_ema200 | 0.0671 |
| opportunity | Random Forest | 3 | volatility_14d | 0.0464 |
| opportunity | Random Forest | 4 | volatility_30d | 0.0391 |
| opportunity | Random Forest | 5 | sol_btc_trend | 0.0387 |
| opportunity | Random Forest | 6 | eth_btc_trend | 0.0359 |
| opportunity | Random Forest | 7 | ema50_slope | 0.0336 |
| opportunity | Random Forest | 8 | eth_btc_return_spread_14d | 0.0324 |
| opportunity | Random Forest | 9 | sol_btc_return_spread_3d | 0.0323 |
| opportunity | Random Forest | 10 | drawdown_from_90d_high | 0.0314 |
| opportunity | Random Forest | 11 | btc_funding_rate_7d | 0.0304 |
| opportunity | Random Forest | 12 | btc_4h_volatility_7d | 0.0302 |
| opportunity | Random Forest | 13 | volatility_compression | 0.0297 |
| opportunity | Random Forest | 14 | sol_btc_return_spread_7d | 0.0296 |
| opportunity | Random Forest | 15 | sol_btc_return_spread_14d | 0.0278 |
| opportunity | Random Forest | 16 | distance_to_ema50 | 0.0269 |
| opportunity | Random Forest | 17 | volatility_7d | 0.0256 |
| opportunity | Random Forest | 18 | ema20_slope | 0.0237 |
| opportunity | Random Forest | 19 | return_14d | 0.0234 |
| opportunity | Random Forest | 20 | btc_4h_distance_to_ema200 | 0.0227 |
| shock | LightGBM | 1 | volatility_30d | 0.0753 |
| shock | LightGBM | 2 | ema200_slope | 0.0676 |
| shock | LightGBM | 3 | btc_funding_rate_7d | 0.0545 |
| shock | LightGBM | 4 | btc_4h_volatility_7d | 0.0488 |
| shock | LightGBM | 5 | volatility_compression | 0.0463 |
| shock | LightGBM | 6 | distance_to_ema200 | 0.0425 |
| shock | LightGBM | 7 | eth_btc_return_spread_14d | 0.0418 |
| shock | LightGBM | 8 | volatility_14d | 0.0395 |
| shock | LightGBM | 9 | volatility_7d | 0.0379 |
| shock | LightGBM | 10 | eth_btc_trend | 0.0360 |
| shock | LightGBM | 11 | ema50_slope | 0.0344 |
| shock | LightGBM | 12 | drawdown_from_90d_high | 0.0342 |
| shock | LightGBM | 13 | sol_btc_return_spread_14d | 0.0333 |
| shock | LightGBM | 14 | ema20_slope | 0.0307 |
| shock | LightGBM | 15 | return_14d | 0.0292 |
| shock | LightGBM | 16 | distance_to_ema50 | 0.0280 |
| shock | LightGBM | 17 | sol_btc_trend | 0.0267 |
| shock | LightGBM | 18 | sol_btc_return_spread_7d | 0.0266 |
| shock | LightGBM | 19 | return_7d | 0.0233 |
| shock | LightGBM | 20 | drawdown_from_30d_high | 0.0203 |

## EMA vs ML v2 Mismatch Examples

| Date | Model | ML State | EMA Regime | Shock | Opportunity | p_shock | p_opportunity |
|---|---|---|---|---:|---:|---:|---:|
| 2023-12-22 | Logistic Regression | shock_guard | uptrend | 0 | 0 | 46.00% | 57.73% |
| 2024-02-07 | Logistic Regression | shock_guard | uptrend | 0 | 1 | 44.90% | 58.51% |
| 2024-03-25 | Logistic Regression | shock_guard | uptrend | 0 | 0 | 47.21% | 57.40% |
| 2024-05-11 | Logistic Regression | shock_guard | uptrend | 0 | 1 | 42.31% | 57.65% |
| 2024-06-27 | Logistic Regression | shock_guard | uptrend | 1 | 0 | 34.78% | 55.36% |
| 2024-09-28 | Logistic Regression | shock_guard | uptrend | 1 | 0 | 32.88% | 56.94% |
| 2024-11-14 | Logistic Regression | shock_guard | uptrend | 0 | 1 | 38.61% | 60.00% |
| 2025-01-01 | Logistic Regression | shock_guard | uptrend | 0 | 1 | 37.09% | 63.22% |
| 2025-03-09 | Logistic Regression | recovery_candidate | defensive | 0 | 1 | 34.34% | 61.10% |
| 2025-05-29 | Logistic Regression | shock_guard | uptrend | 0 | 0 | 36.84% | 64.84% |
| 2025-07-16 | Logistic Regression | shock_guard | uptrend | 0 | 0 | 28.96% | 71.01% |
| 2025-09-01 | Logistic Regression | shock_guard | uptrend | 0 | 1 | 30.18% | 70.28% |

## Lookahead And Leakage Checks

- 1D features use current and prior rows only.
- 1H/4H features are grouped by UTC date after computing rolling/pct_change values on prior intraday rows.
- Funding level is shifted by one daily row before use; funding change uses prior shifted values.
- Forward 7d/14d return and drawdown are used only for labels.
- Walk-forward folds are time ordered and never shuffled.
- Thresholds are selected on train fold probabilities only; test fold thresholds are never optimized.
- Paper engine, execution state, and live order code are not imported by this report.

## Skipped Models

- none

## PASS/WATCH/FAIL

- Status: WATCH
- Best shock model: Logistic Regression recall 94.46%, FPR 88.87%.
- Best opportunity model: Random Forest precision 70.80%, delta 11.20%.
- Shock Guard recall clears the floor, but false positives are high.
