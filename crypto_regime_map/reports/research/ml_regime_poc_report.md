# ML Regime PoC Report

- Generated: 2026-06-22 13:42:56 UTC
- Scope: offline research/report only; paper engine and live order logic untouched.
- Default runtime state: ML Regime OFF.
- Label horizon: 14 days.
- Usable data period: 2020-08-30 to 2026-06-08.
- Usable rows after warmup/label drop: 2109.

## Verdict

- Status: FAIL
- Best model: Logistic Regression.
- Recovery/uptrend precision delta vs baseline: 2.48%.
- Shock recall: 2.90%.
- Core objective is not above baseline or shock recall is too low.

## Features

- Used feature count: 22
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

## Label Distribution

| Label | Count | Share |
|---|---:|---:|
| shock | 614 | 29.11% |
| defensive | 94 | 4.46% |
| chop | 637 | 30.20% |
| recovery | 354 | 16.79% |
| uptrend | 410 | 19.44% |

## Model Performance

| Model | Folds | Accuracy | Balanced Acc | Macro F1 | Recovery/Uptrend Precision | Baseline | Shock Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 5 | 19.67% | 20.47% | 16.00% | 38.59% | 36.11% | 2.90% |
| LightGBM | 5 | 22.89% | 16.35% | 15.44% | 29.91% | 36.11% | 20.60% |
| Random Forest | 5 | 22.11% | 16.36% | 14.95% | 28.11% | 36.11% | 19.82% |

## Walk-Forward Folds

| Model | Fold | Train | Test | Macro F1 | Recovery/Uptrend Precision | Shock Recall |
|---|---:|---|---|---:|---:|---:|
| Logistic Regression | 1 | 2020-08-30 to 2023-12-21 | 2023-12-22 to 2024-06-18 | 16.41% | 39.13% | 6.00% |
| Random Forest | 1 | 2020-08-30 to 2023-12-21 | 2023-12-22 to 2024-06-18 | 14.99% | 23.40% | 40.00% |
| LightGBM | 1 | 2020-08-30 to 2023-12-21 | 2023-12-22 to 2024-06-18 | 13.90% | 34.15% | 40.00% |
| Logistic Regression | 2 | 2020-08-30 to 2024-06-18 | 2024-06-19 to 2024-12-15 | 19.48% | 51.67% | 0.00% |
| Random Forest | 2 | 2020-08-30 to 2024-06-18 | 2024-06-19 to 2024-12-15 | 7.79% | 41.10% | 0.00% |
| LightGBM | 2 | 2020-08-30 to 2024-06-18 | 2024-06-19 to 2024-12-15 | 11.54% | 52.38% | 6.67% |
| Logistic Regression | 3 | 2020-08-30 to 2024-12-15 | 2024-12-16 to 2025-06-13 | 13.52% | 32.52% | 6.00% |
| Random Forest | 3 | 2020-08-30 to 2024-12-15 | 2024-12-16 to 2025-06-13 | 15.74% | 23.29% | 6.00% |
| LightGBM | 3 | 2020-08-30 to 2024-12-15 | 2024-12-16 to 2025-06-13 | 20.26% | 31.82% | 8.00% |
| Logistic Regression | 4 | 2020-08-30 to 2025-06-13 | 2025-06-14 to 2025-12-10 | 17.50% | 29.41% | 2.50% |
| Random Forest | 4 | 2020-08-30 to 2025-06-13 | 2025-06-14 to 2025-12-10 | 19.64% | 20.00% | 15.00% |
| LightGBM | 4 | 2020-08-30 to 2025-06-13 | 2025-06-14 to 2025-12-10 | 14.49% | 7.69% | 15.00% |
| Logistic Regression | 5 | 2020-08-30 to 2025-12-10 | 2025-12-11 to 2026-06-08 | 13.11% | 40.23% | 0.00% |
| Random Forest | 5 | 2020-08-30 to 2025-12-10 | 2025-12-11 to 2026-06-08 | 16.59% | 32.79% | 38.10% |
| LightGBM | 5 | 2020-08-30 to 2025-12-10 | 2025-12-11 to 2026-06-08 | 17.03% | 23.53% | 33.33% |

## Feature Importance

| Model | Rank | Feature | Importance |
|---|---:|---|---:|
| LightGBM | 1 | volatility_30d | 0.0736 |
| LightGBM | 2 | volatility_7d | 0.0632 |
| LightGBM | 3 | ema200_slope | 0.0600 |
| LightGBM | 4 | distance_to_ema200 | 0.0549 |
| LightGBM | 5 | btc_funding_rate_7d | 0.0522 |
| LightGBM | 6 | eth_btc_return_spread_7d | 0.0499 |
| LightGBM | 7 | eth_btc_trend | 0.0488 |
| LightGBM | 8 | sol_btc_trend | 0.0488 |
| LightGBM | 9 | volatility_14d | 0.0465 |
| LightGBM | 10 | return_7d | 0.0465 |
| LightGBM | 11 | return_3d | 0.0445 |
| LightGBM | 12 | return_14d | 0.0440 |
| LightGBM | 13 | drawdown_from_90d_high | 0.0422 |
| LightGBM | 14 | ema20_slope | 0.0418 |
| LightGBM | 15 | ema50_slope | 0.0418 |
| LightGBM | 16 | volume_change_7d | 0.0402 |
| LightGBM | 17 | return_1d | 0.0397 |
| LightGBM | 18 | sol_btc_return_spread_7d | 0.0392 |
| LightGBM | 19 | distance_to_ema50 | 0.0356 |
| LightGBM | 20 | btc_funding_rate | 0.0337 |
| Logistic Regression | 1 | distance_to_ema50 | 0.0826 |
| Logistic Regression | 2 | ema200_slope | 0.0809 |
| Logistic Regression | 3 | btc_funding_rate_7d | 0.0771 |
| Logistic Regression | 4 | ema20_slope | 0.0634 |
| Logistic Regression | 5 | drawdown_from_90d_high | 0.0625 |
| Logistic Regression | 6 | return_14d | 0.0602 |
| Logistic Regression | 7 | distance_to_ema20 | 0.0550 |
| Logistic Regression | 8 | drawdown_from_30d_high | 0.0547 |
| Logistic Regression | 9 | sol_btc_trend | 0.0505 |
| Logistic Regression | 10 | distance_to_ema200 | 0.0500 |
| Logistic Regression | 11 | sol_btc_return_spread_7d | 0.0491 |
| Logistic Regression | 12 | volatility_30d | 0.0396 |
| Logistic Regression | 13 | eth_btc_trend | 0.0372 |
| Logistic Regression | 14 | volatility_14d | 0.0327 |
| Logistic Regression | 15 | return_7d | 0.0323 |
| Logistic Regression | 16 | eth_btc_return_spread_7d | 0.0313 |
| Logistic Regression | 17 | return_1d | 0.0299 |
| Logistic Regression | 18 | ema50_slope | 0.0260 |
| Logistic Regression | 19 | btc_funding_rate | 0.0259 |
| Logistic Regression | 20 | volume_change_7d | 0.0243 |
| Random Forest | 1 | volatility_30d | 0.0723 |
| Random Forest | 2 | sol_btc_trend | 0.0584 |
| Random Forest | 3 | ema200_slope | 0.0576 |
| Random Forest | 4 | btc_funding_rate_7d | 0.0564 |
| Random Forest | 5 | distance_to_ema200 | 0.0564 |
| Random Forest | 6 | volatility_7d | 0.0529 |
| Random Forest | 7 | return_7d | 0.0517 |
| Random Forest | 8 | volatility_14d | 0.0513 |
| Random Forest | 9 | eth_btc_trend | 0.0495 |
| Random Forest | 10 | ema50_slope | 0.0479 |
| Random Forest | 11 | drawdown_from_90d_high | 0.0458 |
| Random Forest | 12 | sol_btc_return_spread_7d | 0.0450 |
| Random Forest | 13 | distance_to_ema50 | 0.0438 |
| Random Forest | 14 | ema20_slope | 0.0421 |
| Random Forest | 15 | eth_btc_return_spread_7d | 0.0408 |
| Random Forest | 16 | return_14d | 0.0407 |
| Random Forest | 17 | drawdown_from_30d_high | 0.0357 |
| Random Forest | 18 | distance_to_ema20 | 0.0343 |
| Random Forest | 19 | return_3d | 0.0319 |
| Random Forest | 20 | btc_funding_rate | 0.0312 |

## EMA vs ML Mismatch Examples

| Date | Model | ML Regime | EMA Regime | Actual Label | Probability |
|---|---|---|---|---|---:|
| 2023-12-22 | Logistic Regression | defensive | uptrend | chop | 32.50% |
| 2024-03-07 | Logistic Regression | shock | uptrend | chop | 49.75% |
| 2024-06-10 | Logistic Regression | chop | uptrend | shock | 30.29% |
| 2024-08-14 | Logistic Regression | shock | defensive | chop | 30.03% |
| 2024-10-14 | Logistic Regression | defensive | uptrend | recovery | 25.38% |
| 2025-03-01 | Logistic Regression | uptrend | defensive | shock | 39.42% |
| 2025-04-30 | Logistic Regression | defensive | uptrend | uptrend | 28.03% |
| 2025-07-09 | Logistic Regression | defensive | uptrend | recovery | 32.48% |
| 2025-09-03 | Logistic Regression | defensive | uptrend | recovery | 30.38% |
| 2025-11-17 | Logistic Regression | chop | defensive | shock | 30.33% |
| 2026-01-22 | Logistic Regression | uptrend | defensive | shock | 25.44% |
| 2026-04-01 | Logistic Regression | chop | defensive | uptrend | 22.90% |

## Lookahead And Leakage Checks

- Features use pct_change, rolling, and EMA calculations based on current or prior rows only.
- Funding features are shifted by one daily row before joining.
- Labels use future returns and future low drawdown only after feature generation.
- Walk-forward uses expanding train windows and later test windows; shuffle is not used.
- Paper engine, live execution, state files, and order generation code were not imported or changed.

## Skipped Models

- none

## Next Steps

- Tighten label thresholds and test 7d vs 14d horizon side by side.
- Add verified open interest, dominance, and TOTAL/TOTAL2/TOTAL3 caches before making model decisions.
- Keep ML output as a research-only report until shock recall and recovery/uptrend precision are stable across folds.
- If promoted later, add an explicit feature flag and paper-only shadow logging before any execution integration.
