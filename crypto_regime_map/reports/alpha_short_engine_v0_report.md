# Alpha Short Engine v0 리포트

- 생성 시각: 2026-06-21 11:50 UTC
- 기간: 2020-01-01 00:00 ~ 2026-01-02 01:00 UTC
- Short Engine v0는 실전 투입용이 아니라 연구/백테스트 전용이다.
- Alpha Long Engine v1.2와 통합하지 않았고, 기존 `alpha_engine_v1_2` 관련 파일도 수정하지 않았다.
- Paper Trading 연결 전 별도 감사가 필요하다.
- 통과하더라도 최소 3개월 별도 Paper Trading 검증이 필요하다.
- 실제 주문 API 연결은 없다. 데이터 조회는 Binance USD-M Futures OHLCV/funding history만 사용한다.
- DOGE는 v0 유니버스에서 제외했다.

## Pass / Fail

| Check | Result | Evidence |
|---|---|---|
| 4 symbols Calmar >= 1.0 at 0.2% slippage | FAIL | Calmar -0.08 |
| 4 symbols MDD within -35% | PASS | MDD -7.5% |
| 4 symbols liquidation risk 0 | PASS | Liquidation risk trades 0 |
| 4 symbols actual funding Calmar >= 0.8 minimum | FAIL | Funding-included Calmar -0.08 |
| 4 symbols symbol PnL concentration | WARNING | Max positive PnL share 100.0% |
| 4 symbols trade count | PASS | Trades 81 |
| 4 symbols annual dependency | WARNING | Largest positive year share 0.0%, positive years 0 |
| 9 symbols Calmar >= 1.0 at 0.2% slippage | FAIL | Calmar -0.07 |
| 9 symbols MDD within -35% | PASS | MDD -10.4% |
| 9 symbols liquidation risk 0 | PASS | Liquidation risk trades 0 |
| 9 symbols actual funding Calmar >= 0.8 minimum | FAIL | Funding-included Calmar -0.07 |
| 9 symbols symbol PnL concentration | PASS | Max positive PnL share 43.5% |
| 9 symbols trade count | PASS | Trades 155 |
| 9 symbols annual dependency | WARNING | Largest positive year share 100.0%, positive years 1 |
| 4 symbols shock chasing comparison | KEEP_SHOCK_FORBID | Base Calmar -0.08, shock-allow Calmar -0.11 |
| 9 symbols shock chasing comparison | KEEP_SHOCK_FORBID | Base Calmar -0.07, shock-allow Calmar -0.12 |
| 4 symbols vs 9 symbols stability | PREFER_9_SYMBOLS_OR_REVIEW | 4 Calmar -0.08, MDD -7.5%; 9 Calmar -0.07, MDD -10.4% |

## 핵심 성과

| Name | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Trades | Monthly | Funding PnL | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols | actual funding | -3.3% | -0.6% | -7.5% | -0.40 | -0.08 | 0.83 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 9 symbols | actual funding | -4.4% | -0.7% | -10.4% | -0.34 | -0.07 | 0.88 | 43.2% | 155 | 2.12 | -0.00 | 0 |

## 비교 및 민감도

| Name | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Trades | Monthly | Funding PnL | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols / shock forced flat | actual funding | -2.0% | -0.3% | -6.9% | -0.24 | -0.05 | 0.90 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 9 symbols / shock forced flat | actual funding | -1.4% | -0.2% | -9.0% | -0.09 | -0.03 | 0.96 | 43.2% | 155 | 2.12 | -0.00 | 0 |
| Short Engine v0 / 4 symbols / shock allow comparison | actual funding | -6.4% | -1.1% | -9.8% | -0.78 | -0.11 | 0.72 | 31.5% | 89 | 1.22 | 0.00 | 0 |
| Short Engine v0 / 9 symbols / shock allow comparison | actual funding | -9.7% | -1.7% | -13.8% | -0.79 | -0.12 | 0.76 | 40.6% | 170 | 2.33 | -0.00 | 0 |
| Short Engine v0 / 4 symbols / next 1H close | actual funding | -4.8% | -0.8% | -8.4% | -0.58 | -0.10 | 0.77 | 30.5% | 82 | 1.12 | 0.00 | 0 |
| Short Engine v0 / 9 symbols / next 1H close | actual funding | -6.3% | -1.1% | -11.5% | -0.52 | -0.09 | 0.83 | 40.4% | 156 | 2.14 | -0.00 | 0 |
| Short Engine v0 / 4 symbols / max hold 10d | actual funding | -3.5% | -0.6% | -7.6% | -0.42 | -0.08 | 0.82 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 9 symbols / max hold 10d | actual funding | -4.2% | -0.7% | -10.0% | -0.33 | -0.07 | 0.88 | 43.0% | 151 | 2.07 | -0.00 | 0 |
| Short Engine v0 / 4 symbols / slippage 0.1% | actual funding | -2.3% | -0.4% | -7.5% | -0.26 | -0.05 | 0.89 | 33.3% | 84 | 1.15 | 0.00 | 0 |
| Short Engine v0 / 4 symbols / slippage 0.2% | actual funding | -3.3% | -0.6% | -7.5% | -0.40 | -0.08 | 0.83 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 4 symbols / slippage 0.3% | actual funding | -4.8% | -0.8% | -7.9% | -0.62 | -0.10 | 0.76 | 32.1% | 78 | 1.07 | 0.00 | 0 |
| Short Engine v0 / 4 symbols / slippage 0.5% | actual funding | -7.6% | -1.3% | -9.6% | -1.14 | -0.14 | 0.61 | 27.6% | 76 | 1.04 | 0.00 | 0 |
| Short Engine v0 / 9 symbols / slippage 0.1% | actual funding | -1.0% | -0.2% | -10.4% | -0.04 | -0.02 | 0.97 | 44.2% | 163 | 2.23 | -0.00 | 0 |
| Short Engine v0 / 9 symbols / slippage 0.2% | actual funding | -4.4% | -0.7% | -10.4% | -0.34 | -0.07 | 0.88 | 43.2% | 155 | 2.12 | -0.00 | 0 |
| Short Engine v0 / 9 symbols / slippage 0.3% | actual funding | -7.3% | -1.3% | -11.3% | -0.63 | -0.11 | 0.79 | 43.1% | 153 | 2.10 | -0.00 | 0 |
| Short Engine v0 / 9 symbols / slippage 0.5% | actual funding | -14.6% | -2.6% | -16.8% | -1.41 | -0.15 | 0.61 | 36.9% | 149 | 2.04 | -0.00 | 0 |

## Funding 포함 / 제외 비교

| Name | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Trades | Monthly | Funding PnL | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols | funding excluded | -3.4% | -0.6% | -7.5% | -0.41 | -0.08 | 0.83 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 4 symbols | actual funding | -3.3% | -0.6% | -7.5% | -0.40 | -0.08 | 0.83 | 33.3% | 81 | 1.11 | 0.00 | 0 |
| Short Engine v0 / 9 symbols | funding excluded | -4.2% | -0.7% | -10.4% | -0.33 | -0.07 | 0.88 | 43.2% | 155 | 2.12 | 0.00 | 0 |
| Short Engine v0 / 9 symbols | actual funding | -4.4% | -0.7% | -10.4% | -0.34 | -0.07 | 0.88 | 43.2% | 155 | 2.12 | -0.00 | 0 |

## Alpha Long Engine v1.2 참고값

| Name | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Trades | Monthly | Funding PnL | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Reference only / Alpha Long Engine v1.2 / Candidate v1.2 / leverage cap | actual | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 1.11 |  | 929 | 12.90 |  | 0 |

## 룩어헤드 감사

| Check | Value |
|---|---:|
| 1D regime source | trade_regime / trade_action_bias only |
| stable_regime same-day direct use | 0 |
| Trade lookahead failures | 0 |
| Signal rule failures | 0 |
| Same candle signal/execution trades | 0 |
| Minimum available-to-execution lag hours | 0.0 |

## OOS / Walk-forward

| Name | Window | Months | Return | Result |
|---|---|---:|---:|---|
| Short Engine v0 / 4 symbols | 2020-2023 train | 48 | 0.0% | ok |
| Short Engine v0 / 4 symbols | 2024 test | 12 | -3.3% | ok |
| Short Engine v0 / 4 symbols | 2020-2024 train | 60 | -3.3% | ok |
| Short Engine v0 / 4 symbols | 2025 test | 12 | -0.1% | ok |
| Short Engine v0 / 4 symbols | 2026 OOS | 1 | 0.0% | no_data |
| Short Engine v0 / 9 symbols | 2020-2023 train | 48 | 0.0% | ok |
| Short Engine v0 / 9 symbols | 2024 test | 12 | -4.8% | ok |
| Short Engine v0 / 9 symbols | 2020-2024 train | 60 | -4.8% | ok |
| Short Engine v0 / 9 symbols | 2025 test | 12 | 1.3% | ok |
| Short Engine v0 / 9 symbols | 2026 OOS | 1 | -0.8% | no_data |

## 분기별 Rolling 성과

| Name | 2023-Q2 | 2023-Q3 | 2023-Q4 | 2024-Q1 | 2024-Q2 | 2024-Q3 | 2024-Q4 | 2025-Q1 | 2025-Q2 | 2025-Q3 | 2025-Q4 | 2026-Q1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols | 0.0% | 0.0% | 0.0% | 0.0% | 0.6% | -2.6% | -1.3% | 1.6% | -1.1% | 0.0% | -0.5% | 0.0% |
| Short Engine v0 / 9 symbols | 0.0% | 0.0% | 0.0% | 0.0% | 1.1% | -4.5% | -1.4% | 2.0% | -3.1% | 0.0% | 2.5% | -0.8% |

## 심볼별 성과

| symbol | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| AVAX | 30 | 0.02 | 50.0% | 0.1% | 1.30 |
| ADA | 25 | 0.02 | 48.0% | 0.1% | 1.39 |
| LINK | 16 | 0.01 | 43.8% | 0.0% | 1.14 |
| TON | 29 | -0.00 | 48.3% | -0.0% | 0.94 |
| XRP | 17 | -0.01 | 41.2% | -0.1% | 0.69 |
| BNB | 23 | -0.02 | 43.5% | -0.1% | 0.69 |
| SOL | 42 | -0.04 | 35.7% | -0.1% | 0.61 |
| ETH | 54 | -0.04 | 25.9% | -0.1% | 0.72 |

## 레짐별 성과

| trade_regime | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| defensive | 236 | -0.08 | 39.8% | -0.0% | 0.86 |

## Action Bias별 성과

| trade_action_bias | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| reduce_risk | 236 | -0.08 | 39.8% | -0.0% | 0.86 |

## 진입 품질

| Metric | Value |
|---|---:|
| Entry +1D avg | 0.0% |
| Entry +3D avg | -0.4% |
| Entry +7D avg | 0.4% |
| Avg MAE | -2.6% |
| Avg MFE | 5.3% |
| Avg MAE/MFE | 3.41 |
| Avg winning trade | 0.5% |
| Avg losing trade | -0.4% |

## 신호 / 스킵 통계

| Reason | Count |
|---|---:|
| uptrend_long_allowed_block | 4842 |
| already_open | 2981 |
| entered | 731 |
| neutral_observe_wait | 651 |
| score_not_top_20pct | 342 |
| max_positions | 279 |
| shock_no_new_entry | 116 |
| large_cap_lead_block | 72 |

## Funding 요약

| Metric | Value |
|---|---:|
| Funding PnL | -0.00 |
| Funding income | 0.01 |
| Funding cost | 0.01 |
| Funding cost / income | 1.10 |
| Funding events | 1386 |

## 최악 거래 Top 20

| Variant | Symbol | Entry | Exit | Reason | Return | Funding | Hold | MAE | MFE |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| Short Engine v0 / 9 symbols | AVAX | 2025-12-06 16:00 | 2025-12-07 01:00 | stop | -0.5% | -0.00 | 0.38 | -1.7% | 0.1% |
| Short Engine v0 / 4 symbols | ETH | 2024-07-28 21:00 | 2024-07-29 01:00 | stop | -0.5% | 0.00 | 0.17 | -1.7% | 0.0% |
| Short Engine v0 / 9 symbols | ETH | 2024-09-13 05:00 | 2024-09-13 16:00 | stop | -0.5% | 0.00 | 0.46 | -3.3% | 0.3% |
| Short Engine v0 / 4 symbols | ETH | 2024-09-13 05:00 | 2024-09-13 16:00 | stop | -0.5% | 0.00 | 0.46 | -3.3% | 0.3% |
| Short Engine v0 / 9 symbols | TON | 2024-07-11 12:00 | 2024-07-12 00:00 | stop | -0.5% | -0.00 | 0.50 | -2.5% | 0.8% |
| Short Engine v0 / 9 symbols | TON | 2024-10-12 03:00 | 2024-10-12 10:00 | stop | -0.5% | 0.00 | 0.29 | -2.0% | 0.0% |
| Short Engine v0 / 4 symbols | ETH | 2024-07-27 02:00 | 2024-07-27 13:00 | stop | -0.5% | 0.00 | 0.46 | -2.7% | 0.0% |
| Short Engine v0 / 9 symbols | XRP | 2024-07-10 19:00 | 2024-07-11 07:00 | stop | -0.5% | -0.00 | 0.50 | -2.6% | 0.1% |
| Short Engine v0 / 9 symbols | XRP | 2024-10-13 23:00 | 2024-10-14 04:00 | stop | -0.5% | 0.00 | 0.21 | -1.9% | 0.3% |
| Short Engine v0 / 9 symbols | TON | 2024-10-28 14:00 | 2024-10-28 23:00 | stop | -0.5% | 0.00 | 0.38 | -2.0% | 0.7% |
| Short Engine v0 / 9 symbols | AVAX | 2025-10-26 02:00 | 2025-10-26 09:00 | stop | -0.5% | 0.00 | 0.29 | -3.4% | 0.8% |
| Short Engine v0 / 9 symbols | XRP | 2025-12-07 08:00 | 2025-12-07 18:00 | stop | -0.5% | -0.00 | 0.42 | -4.2% | 1.9% |
| Short Engine v0 / 9 symbols | TON | 2024-10-29 11:00 | 2024-10-29 17:00 | stop | -0.5% | 0.00 | 0.25 | -3.1% | 0.2% |
| Short Engine v0 / 4 symbols | SOL | 2024-08-23 12:00 | 2024-08-23 15:00 | stop | -0.5% | 0.00 | 0.12 | -2.8% | 0.4% |
| Short Engine v0 / 9 symbols | SOL | 2024-08-23 12:00 | 2024-08-23 15:00 | stop | -0.5% | 0.00 | 0.12 | -2.8% | 0.4% |
| Short Engine v0 / 9 symbols | TON | 2025-12-22 19:00 | 2025-12-24 17:00 | stop | -0.5% | -0.00 | 1.92 | -2.2% | 1.2% |
| Short Engine v0 / 4 symbols | BNB | 2025-10-29 19:00 | 2025-10-30 11:00 | stop | -0.5% | 0.00 | 0.67 | -2.3% | 1.5% |
| Short Engine v0 / 9 symbols | BNB | 2025-10-29 19:00 | 2025-10-30 11:00 | stop | -0.5% | 0.00 | 0.67 | -2.3% | 1.5% |
| Short Engine v0 / 4 symbols | BNB | 2025-12-02 00:00 | 2025-12-02 11:00 | stop | -0.5% | 0.00 | 0.46 | -2.5% | 0.6% |
| Short Engine v0 / 9 symbols | SOL | 2024-08-22 16:00 | 2024-08-23 01:00 | stop | -0.5% | 0.00 | 0.38 | -2.2% | 0.0% |

## 최고 거래 Top 20

| Variant | Symbol | Entry | Exit | Reason | Return | Funding | Hold | MAE | MFE |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| Short Engine v0 / 4 symbols | ETH | 2024-07-31 16:00 | 2024-08-07 16:00 | max_hold | 3.8% | 0.00 | 7.00 | -1.1% | 56.0% |
| Short Engine v0 / 9 symbols | LINK | 2024-07-31 14:00 | 2024-08-07 14:00 | max_hold | 2.8% | -0.00 | 7.00 | -0.6% | 67.2% |
| Short Engine v0 / 9 symbols | ADA | 2024-07-30 12:00 | 2024-08-06 12:00 | max_hold | 1.9% | 0.00 | 7.00 | -1.1% | 46.6% |
| Short Engine v0 / 9 symbols | TON | 2024-07-20 20:00 | 2024-07-27 20:00 | max_hold | 1.7% | -0.00 | 7.00 | -0.4% | 12.7% |
| Short Engine v0 / 4 symbols | ETH | 2025-04-06 07:00 | 2025-04-09 20:00 | ema20_recovery_trailing_exit | 1.5% | -0.00 | 3.54 | -0.4% | 29.6% |
| Short Engine v0 / 4 symbols | ETH | 2025-11-01 00:00 | 2025-11-07 20:00 | ema20_recovery_trailing_exit | 1.4% | 0.00 | 6.83 | -2.0% | 25.7% |
| Short Engine v0 / 4 symbols | ETH | 2025-03-09 04:00 | 2025-03-14 16:00 | ema20_recovery_trailing_exit | 1.3% | 0.00 | 5.50 | -0.7% | 24.4% |
| Short Engine v0 / 9 symbols | AVAX | 2025-12-12 15:00 | 2025-12-19 15:00 | max_hold | 1.1% | -0.00 | 7.00 | -0.2% | 19.7% |
| Short Engine v0 / 9 symbols | SOL | 2025-03-08 20:00 | 2025-03-13 12:00 | ema20_recovery_trailing_exit | 1.0% | -0.00 | 4.67 | -1.3% | 23.5% |
| Short Engine v0 / 4 symbols | SOL | 2025-03-08 20:00 | 2025-03-13 12:00 | ema20_recovery_trailing_exit | 1.0% | -0.00 | 4.67 | -1.3% | 23.5% |
| Short Engine v0 / 9 symbols | XRP | 2025-12-13 17:00 | 2025-12-18 16:00 | ema20_recovery_trailing_exit | 1.0% | -0.00 | 4.96 | -0.4% | 10.7% |
| Short Engine v0 / 9 symbols | ADA | 2025-10-31 08:00 | 2025-11-07 08:00 | ema20_recovery_trailing_exit | 0.9% | 0.00 | 7.00 | -1.7% | 24.5% |
| Short Engine v0 / 9 symbols | XRP | 2025-03-27 20:00 | 2025-04-01 16:00 | ema20_recovery_trailing_exit | 0.9% | -0.00 | 4.83 | -1.1% | 15.4% |
| Short Engine v0 / 9 symbols | AVAX | 2025-03-09 02:00 | 2025-03-12 12:00 | ema20_recovery_trailing_exit | 0.9% | -0.00 | 3.42 | -0.3% | 33.2% |
| Short Engine v0 / 4 symbols | SOL | 2025-11-12 16:00 | 2025-11-18 16:00 | ema20_recovery_trailing_exit | 0.9% | 0.00 | 6.00 | -1.2% | 20.7% |
| Short Engine v0 / 9 symbols | SOL | 2025-11-12 16:00 | 2025-11-18 16:00 | ema20_recovery_trailing_exit | 0.9% | 0.00 | 6.00 | -1.2% | 20.7% |
| Short Engine v0 / 4 symbols | BNB | 2025-10-31 02:00 | 2025-11-07 02:00 | max_hold | 0.9% | -0.00 | 7.00 | -2.0% | 23.2% |
| Short Engine v0 / 9 symbols | ADA | 2025-11-18 12:00 | 2025-11-24 20:00 | ema20_recovery_trailing_exit | 0.8% | 0.00 | 6.33 | -3.1% | 20.7% |
| Short Engine v0 / 9 symbols | AVAX | 2025-11-19 00:00 | 2025-11-24 16:00 | ema20_recovery_trailing_exit | 0.8% | -0.00 | 5.67 | -0.9% | 18.8% |
| Short Engine v0 / 9 symbols | AVAX | 2024-06-16 01:00 | 2024-06-20 08:00 | ema20_recovery_trailing_exit | 0.8% | 0.00 | 4.29 | -1.8% | 22.2% |

## 연도별 수익률

| Name | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols | 0.0% | 0.0% | 0.0% | 0.0% | -3.3% | -0.1% | 0.0% |
| Short Engine v0 / 9 symbols | 0.0% | 0.0% | 0.0% | 0.0% | -4.8% | 1.3% | -0.8% |
| Short Engine v0 / 4 symbols / shock forced flat | 0.0% | 0.0% | 0.0% | 0.0% | -2.8% | 0.9% | 0.0% |
| Short Engine v0 / 9 symbols / shock forced flat | 0.0% | 0.0% | 0.0% | 0.0% | -3.3% | 2.9% | -0.8% |
| Short Engine v0 / 4 symbols / shock allow comparison | 0.0% | 0.0% | 0.0% | 0.0% | -3.9% | -2.6% | 0.0% |
| Short Engine v0 / 9 symbols / shock allow comparison | 0.0% | 0.0% | 0.0% | 0.0% | -6.5% | -2.6% | -0.8% |
| Short Engine v0 / 4 symbols / next 1H close | 0.0% | 0.0% | 0.0% | 0.0% | -3.6% | -1.2% | 0.0% |
| Short Engine v0 / 9 symbols / next 1H close | 0.0% | 0.0% | 0.0% | 0.0% | -4.5% | -1.1% | -0.8% |
| Short Engine v0 / 4 symbols / max hold 10d | 0.0% | 0.0% | 0.0% | 0.0% | -3.4% | -0.1% | 0.0% |
| Short Engine v0 / 9 symbols / max hold 10d | 0.0% | 0.0% | 0.0% | 0.0% | -4.6% | 1.3% | -0.8% |
| Short Engine v0 / 4 symbols / slippage 0.1% | 0.0% | 0.0% | 0.0% | 0.0% | -3.1% | 0.8% | 0.0% |
| Short Engine v0 / 4 symbols / slippage 0.2% | 0.0% | 0.0% | 0.0% | 0.0% | -3.3% | -0.1% | 0.0% |
| Short Engine v0 / 4 symbols / slippage 0.3% | 0.0% | 0.0% | 0.0% | 0.0% | -3.7% | -1.1% | 0.0% |
| Short Engine v0 / 4 symbols / slippage 0.5% | 0.0% | 0.0% | 0.0% | 0.0% | -4.4% | -3.4% | 0.0% |

## 월별 수익률 최근 12개월

| Name | 2025-02 | 2025-03 | 2025-04 | 2025-05 | 2025-06 | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 | 2026-01 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Short Engine v0 / 4 symbols | 0.0% | 1.6% | -1.0% | -0.1% | 0.0% | 0.0% | 0.0% | 0.0% | -1.6% | 2.4% | -1.2% | 0.0% |
| Short Engine v0 / 9 symbols | 0.0% | 2.0% | -2.7% | -0.4% | 0.0% | 0.0% | 0.0% | 0.0% | 1.0% | 2.0% | -0.5% | -0.8% |
| BTC Buy & Hold | -19.1% | -2.7% | 14.4% | 10.4% | 4.2% | 8.7% | -7.7% | 5.1% | -5.2% | -16.2% | -2.5% | 1.7% |

## 데이터 커버리지

| Symbol | 1D | 4H | 1H | Funding | 1H first | 1H last |
|---|---:|---:|---:|---:|---|---|
| BTC | 2309 | 13845 | 55376 | 6580 | 2019-09-08 17:00 | 2026-01-02 00:00 |
| ETH | 2229 | 13368 | 53466 | 6580 | 2019-11-27 07:00 | 2026-01-02 00:00 |
| SOL | 1937 | 11616 | 46458 | 5885 | 2020-09-14 07:00 | 2026-01-02 00:00 |
| BNB | 2154 | 12917 | 51665 | 6459 | 2020-02-10 08:00 | 2026-01-02 00:00 |
| XRP | 2189 | 13127 | 52505 | 6564 | 2020-01-06 08:00 | 2026-01-02 00:00 |
| LINK | 2178 | 13061 | 52241 | 6531 | 2020-01-17 08:00 | 2026-01-02 00:00 |
| AVAX | 1928 | 11562 | 46242 | 5783 | 2020-09-23 07:00 | 2026-01-02 00:00 |
| ADA | 2164 | 12977 | 51905 | 6524 | 2020-01-31 08:00 | 2026-01-02 00:00 |
| TON | 673 | 4030 | 16117 | 4030 | 2024-03-01 12:00 | 2026-01-02 00:00 |

## 산출물

- `alpha_short_engine_v0_report.md`
- `alpha_short_engine_v0_summary.csv`
- `alpha_short_engine_v0_trades.csv`
- `alpha_short_engine_v0_signals.csv`
- `alpha_short_engine_v0_monthly.csv`
- `alpha_short_engine_v0_yearly.csv`
