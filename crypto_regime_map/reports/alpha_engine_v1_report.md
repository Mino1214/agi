# Alpha Engine v1 리포트

- 생성 시각: 2026-06-21 05:45 UTC
- 기간: 2020-01-01 ~ 2025-12-31 UTC
- 데이터: Binance Spot 1D/4H/1H OHLCV. Futures funding fee는 optional 항목으로 이번 리포트에는 반영하지 않았다.
- 레짐은 `trade_regime` / `trade_action_bias`만 사용했다. `stable_regime` 당일 값은 매매 필터에 직접 사용하지 않았다.
- 기본 비용은 진입/청산 각각 수수료 0.10%, 슬리피지 0.05%로 반영했다.
- 기본 리스크는 심볼당 0.5%, 포트폴리오 전체 1.5%, 동시 보유 3개로 제한했다.
- `next_open`은 4H 신호 봉이 닫힌 직후 새 1H 봉 open 체결로 처리한다. 타임스탬프는 같을 수 있지만 같은 4H 봉 내부 체결은 아니다.

## Pass/Fail

| Check | Result | Evidence |
|---|---|---|
| MDD lower than BTC buy-and-hold | PASS | Alpha10 MDD -30.2%, BTC B&H MDD -76.6% |
| Calmar better than Monthly v1 | PASS | Alpha10 Calmar 1.75, Monthly v1 Calmar 1.33 |
| Trade count not excessive | PASS | Alpha10 average monthly trades 15.8 |
| Symbol concentration | PASS | Best symbol positive PnL share 50.8% |
| 10-symbol expansion | PASS | Alpha10 Calmar 1.75, Alpha4 Calmar 1.09 |
| 4x leverage | PASS | 4x MDD -24.2% |

## 룩어헤드 감사

| Variant | Trades | Lookahead fail | Min lag hours | Same timestamp fills |
|---|---:|---:|---:|---:|
| Alpha Engine v1 / 10 symbols | 1140 | 0 | 0.0 | 1140 |
| Alpha Engine v1 / 10 symbols / 2x | 1140 | 0 | 0.0 | 1140 |
| Alpha Engine v1 / 10 symbols / 3x | 1140 | 0 | 0.0 | 1140 |
| Alpha Engine v1 / 10 symbols / 4x | 1140 | 0 | 0.0 | 1140 |
| Alpha Engine v1 / 10 symbols / defensive 50% | 2292 | 0 | 0.0 | 2292 |
| Alpha Engine v1 / 10 symbols / next 1H close | 1173 | 0 | 1.0 | 0 |
| Alpha Engine v1 / 10 symbols / no shock exit | 1132 | 0 | 0.0 | 1132 |
| Alpha Engine v1 / 4 symbols | 873 | 0 | 0.0 | 873 |
| Alpha Engine v1 / 4 symbols / 2x | 873 | 0 | 0.0 | 873 |
| Alpha Engine v1 / 4 symbols / 3x | 873 | 0 | 0.0 | 873 |
| Alpha Engine v1 / 4 symbols / 4x | 873 | 0 | 0.0 | 873 |
| Alpha Engine v1 / 4 symbols / base cost | 873 | 0 | 0.0 | 873 |
| Alpha Engine v1 / 4 symbols / defensive 50% | 1693 | 0 | 0.0 | 1693 |
| Alpha Engine v1 / 4 symbols / high cost | 880 | 0 | 0.0 | 880 |
| Alpha Engine v1 / 4 symbols / low cost | 866 | 0 | 0.0 | 866 |
| Alpha Engine v1 / 4 symbols / next 1H close | 883 | 0 | 1.0 | 0 |
| Alpha Engine v1 / 4 symbols / no shock exit | 867 | 0 | 0.0 | 867 |
| Alpha Engine v1 / BTC only | 250 | 0 | 0.0 | 250 |
| Alpha Engine v1 / BTC/ETH only | 494 | 0 | 0.0 | 494 |
| Alpha Engine v1 / ETH only | 244 | 0 | 0.0 | 244 |

## 전체 성과

| Name | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Payoff | Trades | Monthly trades | Avg hold | MAE | MFE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/ETH Monthly Strength v1 | 1075.9% | 50.8% | -38.2% | 1.21 | 1.33 |  | 37.5% |  | 70 | 0.97 |  |  |  |
| Buy & Hold BTC | 1116.9% | 51.7% | -76.6% | 0.96 | 0.67 |  | 56.9% |  | 1 | 0.01 |  |  |  |
| Buy & Hold ETH | 2198.4% | 68.6% | -79.3% | 1.00 | 0.87 |  | 55.6% |  | 1 | 0.01 |  |  |  |
| Alpha Engine v1 / 4 symbols | 307.8% | 26.4% | -24.2% | 1.50 | 1.09 | 1.42 | 35.1% | 2.63 | 873 | 12.12 | 1.56 | -2.4% | 5.3% |
| Alpha Engine v1 / 10 symbols | 1181.2% | 53.0% | -30.2% | 2.07 | 1.75 | 1.68 | 35.7% | 3.03 | 1140 | 15.83 | 1.50 | -3.0% | 6.5% |
| Alpha Engine v1 / BTC only | 32.6% | 4.8% | -10.4% | 0.74 | 0.46 | 1.25 | 30.8% | 2.81 | 250 | 3.47 | 1.62 | -1.7% | 3.3% |
| Alpha Engine v1 / ETH only | 82.4% | 10.5% | -11.4% | 1.22 | 0.93 | 1.75 | 34.0% | 3.40 | 244 | 3.39 | 1.62 | -2.3% | 4.9% |
| Alpha Engine v1 / BTC/ETH only | 132.9% | 15.1% | -17.7% | 1.20 | 0.86 | 1.49 | 32.4% | 3.11 | 494 | 6.86 | 1.62 | -2.0% | 4.1% |

## 레버리지별 성과

| Name | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Payoff | Trades | Monthly trades | Avg hold | MAE | MFE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Engine v1 / 4 symbols / 2x | 296.1% | 25.8% | -24.2% | 1.50 | 1.07 | 1.40 | 35.1% | 2.59 | 873 | 12.12 | 1.56 | -2.4% | 5.3% |
| Alpha Engine v1 / 4 symbols / 3x | 307.8% | 26.4% | -24.2% | 1.50 | 1.09 | 1.42 | 35.1% | 2.63 | 873 | 12.12 | 1.56 | -2.4% | 5.3% |
| Alpha Engine v1 / 4 symbols / 4x | 307.2% | 26.4% | -24.2% | 1.50 | 1.09 | 1.42 | 35.1% | 2.63 | 873 | 12.12 | 1.56 | -2.4% | 5.3% |
| Alpha Engine v1 / 10 symbols / 2x | 1141.0% | 52.1% | -30.2% | 2.07 | 1.73 | 1.66 | 35.7% | 3.00 | 1140 | 15.83 | 1.50 | -3.0% | 6.5% |
| Alpha Engine v1 / 10 symbols / 3x | 1181.2% | 53.0% | -30.2% | 2.07 | 1.75 | 1.68 | 35.7% | 3.03 | 1140 | 15.83 | 1.50 | -3.0% | 6.5% |
| Alpha Engine v1 / 10 symbols / 4x | 1178.7% | 52.9% | -30.2% | 2.07 | 1.75 | 1.68 | 35.7% | 3.03 | 1140 | 15.83 | 1.50 | -3.0% | 6.5% |

## 수수료/슬리피지 민감도

| Name | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Payoff | Trades | Monthly trades | Avg hold | MAE | MFE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Engine v1 / 4 symbols / low cost | 658.1% | 40.1% | -15.2% | 2.10 | 2.64 | 1.64 | 36.6% | 2.84 | 866 | 12.03 | 1.57 | -2.4% | 5.4% |
| Alpha Engine v1 / 4 symbols / base cost | 307.8% | 26.4% | -24.2% | 1.50 | 1.09 | 1.42 | 35.1% | 2.63 | 873 | 12.12 | 1.56 | -2.4% | 5.3% |
| Alpha Engine v1 / 4 symbols / high cost | 47.3% | 6.7% | -47.7% | 0.48 | 0.14 | 1.15 | 32.0% | 2.44 | 880 | 12.22 | 1.55 | -2.4% | 5.2% |

## 타이밍/레짐/청산 민감도

| Name | Total | CAGR | MDD | Sharpe | Calmar | PF | Win | Payoff | Trades | Monthly trades | Avg hold | MAE | MFE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Engine v1 / 4 symbols / defensive 50% | 618.5% | 38.9% | -17.1% | 1.88 | 2.27 | 1.37 | 35.8% | 2.46 | 1693 | 23.51 | 1.58 | -2.4% | 4.9% |
| Alpha Engine v1 / 10 symbols / defensive 50% | 3000.0% | 77.2% | -28.3% | 2.48 | 2.73 | 1.56 | 34.7% | 2.93 | 2292 | 31.83 | 1.48 | -2.9% | 5.8% |
| Alpha Engine v1 / 4 symbols / next 1H close | 206.9% | 20.5% | -31.4% | 1.29 | 0.65 | 1.30 | 34.7% | 2.45 | 883 | 12.26 | 1.51 | -2.3% | 5.2% |
| Alpha Engine v1 / 10 symbols / next 1H close | 568.3% | 37.2% | -29.6% | 1.73 | 1.26 | 1.45 | 33.5% | 2.88 | 1173 | 16.29 | 1.41 | -2.8% | 6.4% |
| Alpha Engine v1 / 4 symbols / no shock exit | 327.0% | 27.4% | -23.6% | 1.54 | 1.16 | 1.45 | 35.2% | 2.67 | 867 | 12.04 | 1.59 | -2.4% | 5.4% |
| Alpha Engine v1 / 10 symbols / no shock exit | 1483.5% | 58.4% | -30.0% | 2.18 | 1.95 | 1.77 | 35.6% | 3.21 | 1132 | 15.72 | 1.53 | -3.0% | 6.7% |

## 심볼별 성과

| Symbol | Trades | PnL | Avg return |
|---|---:|---:|---:|
| XRP | 105 | 4.42 | 0.5% |
| ETH | 146 | 1.81 | 0.5% |
| BNB | 159 | 0.81 | 0.2% |
| BTC | 142 | 0.78 | 0.2% |
| DOGE | 100 | 0.57 | 0.1% |
| ADA | 107 | 0.32 | 0.1% |
| SOL | 117 | -0.07 | 0.0% |
| LINK | 135 | -0.37 | 0.0% |
| AVAX | 100 | -0.67 | -0.1% |
| TON | 29 | -0.93 | -0.3% |

## 레짐별 성과

| trade_regime | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| uptrend | 1105 | 6.44 | 35.1% | 0.2% | 1.64 |
| large_cap_lead | 14 | 0.70 | 85.7% | 1.5% | 20.50 |
| eth_strength | 21 | -0.48 | 33.3% | -0.2% | 0.44 |

## Action Bias별 성과

| trade_action_bias | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| long_allowed | 1105 | 6.44 | 35.1% | 0.2% | 1.64 |
| btc_eth_preferred | 14 | 0.70 | 85.7% | 1.5% | 20.50 |
| alt_watch | 21 | -0.48 | 33.3% | -0.2% | 0.44 |

## 청산 사유별 통계

| exit_reason | Trades | PnL | Win | Avg return | PF |
|---|---:|---:|---:|---:|---:|
| ema20_trailing_exit | 360 | 22.09 | 99.4% | 1.1% | 29118.45 |
| max_hold | 3 | 2.50 | 100.0% | 17.5% |  |
| shock_exit | 15 | 1.35 | 86.7% | 3.4% | 1093.63 |
| ema50_exit | 111 | -0.69 | 29.7% | -0.0% | 0.85 |
| stop | 651 | -18.58 | 0.0% | -0.4% | 0.00 |

## 진입 품질

| Metric | Value |
|---|---:|
| Entry +1D avg | 0.3% |
| Entry +3D avg | 0.9% |
| Entry +7D avg | 2.3% |
| Avg MAE | -3.0% |
| Avg MFE | 6.5% |

## 최악 거래 Top 20

| Variant | Symbol | Entry | Exit | Reason | Return | Hold | MAE | MFE |
|---|---|---|---|---|---:|---:|---:|---:|
| Alpha Engine v1 / 10 symbols | ETH | 2023-05-27 12:00 | 2023-05-27 14:00 | stop | -0.7% | 0.08 | -0.9% | 0.2% |
| Alpha Engine v1 / 10 symbols | ETH | 2023-08-10 20:00 | 2023-08-11 03:00 | stop | -0.7% | 0.29 | -0.4% | 0.2% |
| Alpha Engine v1 / 10 symbols | BNB | 2025-06-27 00:00 | 2025-06-27 02:00 | stop | -0.6% | 0.08 | -0.5% | 0.4% |
| Alpha Engine v1 / 10 symbols | BNB | 2025-07-06 00:00 | 2025-07-06 05:00 | stop | -0.6% | 0.21 | -0.4% | 0.0% |
| Alpha Engine v1 / 10 symbols | BTC | 2024-02-04 04:00 | 2024-02-04 06:00 | stop | -0.6% | 0.08 | -0.7% | 0.0% |
| Alpha Engine v1 / 10 symbols | ADA | 2023-06-05 00:00 | 2023-06-05 02:00 | stop | -0.6% | 0.08 | -0.9% | 0.4% |
| Alpha Engine v1 / 10 symbols | TON | 2025-10-04 12:00 | 2025-10-04 14:00 | stop | -0.6% | 0.08 | -0.5% | 0.6% |
| Alpha Engine v1 / 10 symbols | ETH | 2023-12-29 00:00 | 2023-12-29 02:00 | stop | -0.6% | 0.08 | -1.5% | 0.8% |
| Alpha Engine v1 / 10 symbols | BTC | 2025-09-07 12:00 | 2025-09-08 01:00 | stop | -0.6% | 0.54 | -0.6% | 0.2% |
| Alpha Engine v1 / 10 symbols | DOGE | 2023-05-18 16:00 | 2023-05-18 18:00 | stop | -0.6% | 0.08 | -2.8% | 0.7% |
| Alpha Engine v1 / 10 symbols | BTC | 2020-10-06 12:00 | 2020-10-06 16:00 | stop | -0.6% | 0.17 | -0.8% | 0.5% |
| Alpha Engine v1 / 10 symbols | ETH | 2023-11-13 04:00 | 2023-11-13 07:00 | stop | -0.6% | 0.12 | -0.6% | 0.8% |
| Alpha Engine v1 / 10 symbols | BNB | 2023-08-06 04:00 | 2023-08-06 14:00 | stop | -0.6% | 0.42 | -0.8% | 0.2% |
| Alpha Engine v1 / 10 symbols | AVAX | 2025-06-11 20:00 | 2025-06-11 22:00 | stop | -0.6% | 0.08 | -1.8% | 1.0% |
| Alpha Engine v1 / 10 symbols | BTC | 2024-02-04 12:00 | 2024-02-04 18:00 | stop | -0.6% | 0.25 | -0.8% | 0.1% |
| Alpha Engine v1 / 10 symbols | BNB | 2024-05-26 16:00 | 2024-05-26 22:00 | stop | -0.6% | 0.25 | -0.7% | 0.2% |
| Alpha Engine v1 / 10 symbols | BNB | 2023-07-12 16:00 | 2023-07-12 18:00 | stop | -0.6% | 0.08 | -0.6% | 0.0% |
| Alpha Engine v1 / 10 symbols | BNB | 2025-06-12 04:00 | 2025-06-12 13:00 | stop | -0.6% | 0.38 | -0.7% | 0.4% |
| Alpha Engine v1 / 10 symbols | ADA | 2023-05-24 00:00 | 2023-05-24 02:00 | stop | -0.6% | 0.08 | -0.8% | 0.0% |
| Alpha Engine v1 / 10 symbols | ETH | 2023-05-27 04:00 | 2023-05-27 12:00 | stop | -0.6% | 0.33 | -0.7% | 0.0% |

## 최고 거래 Top 20

| Variant | Symbol | Entry | Exit | Reason | Return | Hold | MAE | MFE |
|---|---|---|---|---|---:|---:|---:|---:|
| Alpha Engine v1 / 10 symbols | XRP | 2024-11-28 16:00 | 2024-12-04 20:00 | ema20_trailing_exit | 41.3% | 6.17 | -0.1% | 102.7% |
| Alpha Engine v1 / 10 symbols | ETH | 2020-07-22 08:00 | 2020-08-03 00:00 | shock_exit | 39.6% | 11.67 | -0.3% | 71.6% |
| Alpha Engine v1 / 10 symbols | BNB | 2021-01-29 04:00 | 2021-02-12 04:00 | max_hold | 33.1% | 14.00 | -1.5% | 249.9% |
| Alpha Engine v1 / 10 symbols | ADA | 2023-12-03 20:00 | 2023-12-11 08:00 | ema20_trailing_exit | 16.6% | 7.50 | -0.1% | 65.9% |
| Alpha Engine v1 / 10 symbols | XRP | 2025-07-06 08:00 | 2025-07-20 08:00 | max_hold | 15.6% | 14.00 | -0.1% | 64.3% |
| Alpha Engine v1 / 10 symbols | BTC | 2020-07-22 08:00 | 2020-08-02 08:00 | ema20_trailing_exit | 11.1% | 11.00 | -0.2% | 30.3% |
| Alpha Engine v1 / 10 symbols | BTC | 2023-06-19 00:00 | 2023-06-26 04:00 | ema20_trailing_exit | 10.2% | 7.17 | -0.4% | 19.3% |
| Alpha Engine v1 / 10 symbols | DOGE | 2024-02-26 16:00 | 2024-03-05 20:00 | ema20_trailing_exit | 9.4% | 8.17 | -0.2% | 138.1% |
| Alpha Engine v1 / 10 symbols | BTC | 2020-10-18 20:00 | 2020-10-28 16:00 | ema20_trailing_exit | 6.9% | 9.83 | -0.3% | 21.2% |
| Alpha Engine v1 / 10 symbols | BTC | 2024-02-07 16:00 | 2024-02-17 16:00 | ema20_trailing_exit | 6.6% | 10.00 | -0.2% | 22.6% |
| Alpha Engine v1 / 10 symbols | ETH | 2021-01-02 08:00 | 2021-01-11 04:00 | ema50_exit | 6.5% | 8.83 | -1.7% | 83.3% |
| Alpha Engine v1 / 10 symbols | AVAX | 2021-02-07 04:00 | 2021-02-13 20:00 | ema20_trailing_exit | 5.9% | 6.67 | -3.4% | 223.8% |
| Alpha Engine v1 / 10 symbols | BNB | 2024-06-02 20:00 | 2024-06-07 20:00 | ema20_trailing_exit | 5.9% | 5.00 | -0.3% | 20.4% |
| Alpha Engine v1 / 10 symbols | BTC | 2025-09-30 12:00 | 2025-10-07 16:00 | ema20_trailing_exit | 4.9% | 7.17 | -0.3% | 11.6% |
| Alpha Engine v1 / 10 symbols | XRP | 2024-11-10 00:00 | 2024-11-13 00:00 | shock_exit | 4.7% | 3.00 | -0.7% | 32.4% |
| Alpha Engine v1 / 10 symbols | ETH | 2025-08-07 08:00 | 2025-08-14 20:00 | ema20_trailing_exit | 4.7% | 7.50 | -0.0% | 29.3% |
| Alpha Engine v1 / 10 symbols | BTC | 2023-11-30 20:00 | 2023-12-11 04:00 | ema50_exit | 4.4% | 10.33 | -0.4% | 18.4% |
| Alpha Engine v1 / 10 symbols | ADA | 2023-11-02 16:00 | 2023-11-07 16:00 | ema20_trailing_exit | 4.4% | 5.00 | -0.8% | 25.0% |
| Alpha Engine v1 / 10 symbols | BNB | 2025-09-30 20:00 | 2025-10-09 16:00 | ema20_trailing_exit | 4.1% | 8.83 | -0.6% | 34.0% |
| Alpha Engine v1 / 10 symbols | ETH | 2025-07-15 08:00 | 2025-07-22 08:00 | ema20_trailing_exit | 3.9% | 7.00 | -0.7% | 29.6% |

## 연도별 수익률

| Name | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| BTC/ETH Monthly Strength v1 | 141.6% | 217.4% | -3.4% | -10.2% | 48.5% | 19.1% |
| Buy & Hold BTC | 301.6% | 59.8% | -64.2% | 155.6% | 121.3% | -6.3% |
| Buy & Hold ETH | 469.6% | 399.2% | -67.5% | 90.8% | 46.3% | -11.0% |
| Alpha Engine v1 / 4 symbols | 89.7% | 64.2% | 0.0% | 4.4% | 13.4% | 10.6% |
| Alpha Engine v1 / 10 symbols | 137.8% | 89.0% | 0.0% | 40.1% | 87.9% | 8.3% |
| Alpha Engine v1 / BTC only | 16.5% | 3.2% | 0.0% | 4.5% | 5.2% | 0.4% |
| Alpha Engine v1 / ETH only | 53.0% | 19.9% | 0.0% | -6.7% | 2.9% | 3.5% |
| Alpha Engine v1 / BTC/ETH only | 72.7% | 23.5% | 0.0% | -2.7% | 8.1% | 3.8% |
| Alpha Engine v1 / 4 symbols / defensive 50% | 109.7% | 83.0% | 15.2% | 22.2% | 23.4% | 7.7% |
| Alpha Engine v1 / 10 symbols / defensive 50% | 192.4% | 134.4% | 29.1% | 64.7% | 106.7% | 2.8% |
| Alpha Engine v1 / 4 symbols / next 1H close | 60.0% | 68.1% | 0.0% | -2.6% | 7.0% | 9.5% |
| Alpha Engine v1 / 10 symbols / next 1H close | 92.1% | 106.6% | 0.0% | 18.1% | 30.2% | 9.5% |

## 월별 수익률 샘플

| Name | 2025-01 | 2025-02 | 2025-03 | 2025-04 | 2025-05 | 2025-06 | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/ETH Monthly Strength v1 | 4.4% | -17.7% | 0.0% | 0.0% | 17.7% | -0.1% | 18.6% | 7.4% | -1.2% | -3.0% | -3.4% | 0.0% |
| Buy & Hold BTC | 9.5% | -17.7% | -2.1% | 14.1% | 11.1% | 2.4% | 8.0% | -6.5% | 5.4% | -3.9% | -17.6% | -3.0% |
| Buy & Hold ETH | -1.1% | -32.2% | -18.6% | -1.6% | 40.9% | -1.7% | 48.8% | 18.7% | -5.6% | -7.2% | -22.3% | -0.7% |
| Alpha Engine v1 / 4 symbols | -3.0% | -4.6% | 0.0% | 0.0% | -1.9% | -2.2% | 9.7% | 5.2% | 0.8% | 7.0% | 0.0% | 0.0% |
| Alpha Engine v1 / 10 symbols | -2.9% | -5.3% | 0.0% | 0.0% | -1.6% | -7.6% | 18.4% | 3.6% | 0.1% | 5.7% | 0.0% | 0.0% |
| Alpha Engine v1 / BTC only | -0.6% | -0.5% | 0.0% | 0.0% | -0.6% | -0.1% | -0.9% | 0.3% | -0.2% | 3.1% | 0.0% | 0.0% |
| Alpha Engine v1 / ETH only | -3.8% | -0.4% | 0.0% | 0.0% | -0.0% | -0.9% | 5.4% | 4.1% | -0.6% | 0.1% | 0.0% | 0.0% |
| Alpha Engine v1 / BTC/ETH only | -4.4% | -0.9% | 0.0% | 0.0% | -0.6% | -1.1% | 4.3% | 4.3% | -0.8% | 3.2% | 0.0% | 0.0% |
| Alpha Engine v1 / 4 symbols / defensive 50% | -3.0% | -4.6% | 0.2% | 1.3% | 0.5% | -2.2% | 9.7% | 5.2% | 0.8% | 6.5% | -1.2% | -4.7% |
| Alpha Engine v1 / 10 symbols / defensive 50% | -2.9% | -5.3% | 0.6% | 0.2% | 0.3% | -7.6% | 18.4% | 3.6% | 0.1% | 4.0% | -3.1% | -3.2% |
| Alpha Engine v1 / 4 symbols / next 1H close | -3.6% | -3.8% | 0.0% | 0.0% | -4.2% | -5.0% | 11.4% | 4.7% | 2.5% | 8.4% | 0.0% | 0.0% |
| Alpha Engine v1 / 10 symbols / next 1H close | -4.8% | -7.0% | 0.0% | 0.0% | -3.8% | -7.0% | 22.0% | 2.9% | 2.7% | 7.3% | 0.0% | 0.0% |

## 데이터 커버리지

| Symbol | 1D | 4H | 1H |
|---|---:|---:|---:|
| BTC | 2924 | 15344 | 61333 |
| ETH | 2924 | 15344 | 61333 |
| SOL | 1971 | 11820 | 47255 |
| BNB | 2924 | 15344 | 61333 |
| XRP | 2801 | 15344 | 61333 |
| LINK | 2544 | 15252 | 60963 |
| AVAX | 1929 | 11568 | 46247 |
| DOGE | 2374 | 14234 | 56897 |
| ADA | 2818 | 15344 | 61333 |
| TON | 513 | 3071 | 12279 |

## 산출물

- `alpha_engine_v1_report.md`
- `alpha_engine_v1_summary.csv`
- `alpha_engine_v1_trades.csv`
- `alpha_engine_v1_signals.csv`
