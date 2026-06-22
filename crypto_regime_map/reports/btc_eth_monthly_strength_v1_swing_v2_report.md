# BTC/ETH Monthly Strength v1 Swing v2 리포트

- 생성 시각: 2026-06-21 05:22 UTC
- 기간: 2020-01-01 ~ 2025-12-31 UTC
- 기준 전략: BTC/ETH Monthly Strength v1
- 월별 목표 비중은 v1과 동일하게 `Top1 50% / Top2 30% / Cash 20%`, BTC <= EMA200이면 Cash 100%로 계산했다.
- Swing v2는 4H 신호를 독립 전략으로 쓰지 않고, 월별 목표 비중의 신규 매수 타이밍 필터로만 사용한다.
- 월초 목표 비중이 감소하거나 Cash 전환이면 초과 보유분은 월초 4H open에서 정리하고, 늘려야 하는 비중만 EMA50 눌림 후 EMA20 회복을 기다린다.
- EMA50 눌림은 기존 비교와 동일하게 `low <= EMA50 + 0.25 ATR`로 판정했다.
- 손절 후 재진입 금지는 해당 월 종료 전까지 같은 심볼 재진입을 막는 것으로 정의했다.
- CAGR 유지 pass 기준은 Monthly v1 CAGR의 80% 이상, 재진입 감소 pass 기준은 기존 EMA50 눌림 대비 4H 이내 재진입 50% 이하로 둔다.

## 최종 판정

| Check | Result | Evidence |
|---|---|---|
| overall_pass_candidates | FAIL | 0 / 16 candidates passed all criteria |
| best_calmar_candidate | INFO | Swing v2 monthly_defense / 청산 후 72시간 재진입 금지 Calmar 1.10, MDD -41.6%, CAGR 45.6% |
| best_mdd_candidate | INFO | Swing v2 ema50_single / 월 후보당 최대 1회 진입 MDD -15.0%, CAGR 6.9% |

- 전체 통과 후보: 0개

## Calmar 상위 Swing v2 후보

| Strategy | CAGR | MDD | Calmar | Trades | Re-entry | Overall |
|---|---|---|---|---|---|---|
| Swing v2 monthly_defense / 청산 후 72시간 재진입 금지 | 45.6% | -41.6% | 1.10 | 36 | 0 | FAIL |
| Swing v2 monthly_defense / 손절 후 월말까지 재진입 금지 | 45.6% | -41.6% | 1.10 | 36 | 0 | FAIL |
| Swing v2 monthly_defense / 월 후보당 최대 2회 진입 | 45.6% | -41.6% | 1.09 | 36 | 0 | FAIL |
| Swing v2 monthly_defense / 월 후보당 최대 1회 진입 | 45.5% | -41.7% | 1.09 | 36 | 0 | FAIL |
| Swing v2 atr_only / 월 후보당 최대 2회 진입 | 44.1% | -45.5% | 0.97 | 51 | 0 | FAIL |
| Swing v2 ema50_two / 월 후보당 최대 2회 진입 | 19.4% | -23.0% | 0.85 | 197 | 31 | FAIL |
| Swing v2 atr_only / 손절 후 월말까지 재진입 금지 | 35.5% | -44.5% | 0.80 | 39 | 0 | FAIL |
| Swing v2 atr_only / 월 후보당 최대 1회 진입 | 35.2% | -44.8% | 0.79 | 41 | 0 | FAIL |

## 비교 대상 전체 성과

| Strategy | Type | CAGR | MDD | Sharpe | Calmar | Trades | Monthly trades | Avg hold | PF | Avg MAE | Avg MFE | 4H re-entry |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Monthly v1 | Benchmark | 50.8% | -38.2% | 1.21 | 1.33 | 70 | 0.97 |  | 3.23 |  |  |  |
| EMA50 눌림 기존 | Independent 4H | 36.2% | -37.3% | 1.19 | 0.97 | 407 | 5.65 | 1.94 | 1.81 | -1.4% | 3.8% | 116 |
| EMA50 눌림 + 48h 쿨다운 | Independent 4H | 23.6% | -31.9% | 0.99 | 0.74 | 228 | 3.17 | 2.36 | 1.85 | -1.6% | 4.4% | 0 |
| Swing v2 ema50_single / 월 후보당 최대 1회 진입 | Swing v2 | 6.9% | -15.0% | 0.64 | 0.46 | 100 | 1.39 | 2.96 | 2.01 | -1.8% | 5.4% | 0 |
| Swing v2 ema50_single / 월 후보당 최대 2회 진입 | Swing v2 | 8.7% | -22.4% | 0.64 | 0.39 | 200 | 2.78 | 2.39 | 1.71 | -1.7% | 4.7% | 32 |
| Swing v2 ema50_single / 청산 후 72시간 재진입 금지 | Swing v2 | 3.5% | -37.8% | 0.28 | 0.09 | 418 | 5.81 | 1.79 | 1.17 | -1.6% | 3.4% | 0 |
| Swing v2 ema50_single / 손절 후 월말까지 재진입 금지 | Swing v2 | 17.2% | -56.4% | 0.68 | 0.31 | 1444 | 20.06 | 1.24 | 1.28 | -1.2% | 2.8% | 805 |
| Swing v2 ema50_two / 월 후보당 최대 1회 진입 | Swing v2 | 9.3% | -16.7% | 0.70 | 0.55 | 100 | 1.39 | 3.81 | 2.19 | -2.3% | 6.8% | 0 |
| Swing v2 ema50_two / 월 후보당 최대 2회 진입 | Swing v2 | 19.4% | -23.0% | 1.06 | 0.85 | 197 | 2.74 | 3.52 | 2.33 | -2.1% | 6.4% | 31 |
| Swing v2 ema50_two / 청산 후 72시간 재진입 금지 | Swing v2 | 5.0% | -33.3% | 0.34 | 0.15 | 393 | 5.46 | 2.46 | 1.21 | -2.1% | 4.1% | 0 |
| Swing v2 ema50_two / 손절 후 월말까지 재진입 금지 | Swing v2 | 21.0% | -49.5% | 0.76 | 0.42 | 1213 | 16.85 | 1.56 | 1.33 | -1.5% | 3.1% | 646 |
| Swing v2 atr_only / 월 후보당 최대 1회 진입 | Swing v2 | 35.2% | -44.8% | 0.97 | 0.79 | 41 | 0.57 | 56.29 | 1.17 | -12.0% | 22.4% | 0 |
| Swing v2 atr_only / 월 후보당 최대 2회 진입 | Swing v2 | 44.1% | -45.5% | 1.10 | 0.97 | 51 | 0.71 | 53.43 | 1.08 | -11.5% | 20.3% | 0 |
| Swing v2 atr_only / 청산 후 72시간 재진입 금지 | Swing v2 | 38.1% | -52.0% | 0.99 | 0.73 | 57 | 0.79 | 48.37 | 0.82 | -11.2% | 17.6% | 0 |
| Swing v2 atr_only / 손절 후 월말까지 재진입 금지 | Swing v2 | 35.5% | -44.5% | 0.99 | 0.80 | 39 | 0.54 | 56.83 | 1.09 | -12.4% | 22.2% | 0 |
| Swing v2 monthly_defense / 월 후보당 최대 1회 진입 | Swing v2 | 45.5% | -41.7% | 1.29 | 1.09 | 36 | 0.50 | 60.60 | 3.85 | -12.5% | 35.6% | 0 |
| Swing v2 monthly_defense / 월 후보당 최대 2회 진입 | Swing v2 | 45.6% | -41.6% | 1.29 | 1.09 | 36 | 0.50 | 60.60 | 3.80 | -12.6% | 35.4% | 0 |
| Swing v2 monthly_defense / 청산 후 72시간 재진입 금지 | Swing v2 | 45.6% | -41.6% | 1.29 | 1.10 | 36 | 0.50 | 60.60 | 3.76 | -12.6% | 35.3% | 0 |
| Swing v2 monthly_defense / 손절 후 월말까지 재진입 금지 | Swing v2 | 45.6% | -41.6% | 1.29 | 1.10 | 36 | 0.50 | 60.60 | 3.76 | -12.6% | 35.3% | 0 |

## Swing v2 후보 판정 매트릭스

| Strategy | MDD | CAGR | Trades | Re-entry | Calmar | Overall |
|---|---|---|---|---|---|---|
| Swing v2 ema50_single / 월 후보당 최대 1회 진입 | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 ema50_single / 월 후보당 최대 2회 진입 | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 ema50_single / 청산 후 72시간 재진입 금지 | PASS | FAIL | FAIL | PASS | FAIL | FAIL |
| Swing v2 ema50_single / 손절 후 월말까지 재진입 금지 | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Swing v2 ema50_two / 월 후보당 최대 1회 진입 | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 ema50_two / 월 후보당 최대 2회 진입 | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 ema50_two / 청산 후 72시간 재진입 금지 | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 ema50_two / 손절 후 월말까지 재진입 금지 | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Swing v2 atr_only / 월 후보당 최대 1회 진입 | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 atr_only / 월 후보당 최대 2회 진입 | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| Swing v2 atr_only / 청산 후 72시간 재진입 금지 | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 atr_only / 손절 후 월말까지 재진입 금지 | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| Swing v2 monthly_defense / 월 후보당 최대 1회 진입 | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| Swing v2 monthly_defense / 월 후보당 최대 2회 진입 | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| Swing v2 monthly_defense / 청산 후 72시간 재진입 금지 | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| Swing v2 monthly_defense / 손절 후 월말까지 재진입 금지 | FAIL | PASS | PASS | PASS | FAIL | FAIL |

## 연도별 수익률

| Strategy | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| Monthly v1 | 141.6% | 217.4% | -3.4% | -10.2% | 48.5% | 19.1% |
| EMA50 눌림 기존 | 185.0% | 63.8% | -2.2% | 15.2% | 14.5% | 6.3% |
| EMA50 눌림 + 48h 쿨다운 | 195.9% | 6.1% | -2.2% | 18.7% | -2.1% | -0.2% |
| Swing v2 ema50_single / 월 후보당 최대 1회 진입 | 6.9% | 20.8% | -2.0% | 8.0% | 8.1% | 0.9% |
| Swing v2 ema50_single / 월 후보당 최대 2회 진입 | 13.3% | 55.2% | -2.7% | -2.1% | 4.8% | -5.8% |
| Swing v2 ema50_single / 청산 후 72시간 재진입 금지 | 19.7% | 42.5% | -8.5% | -4.2% | -8.0% | -10.4% |
| Swing v2 ema50_single / 손절 후 월말까지 재진입 금지 | 112.9% | 63.8% | -15.6% | -8.4% | 21.7% | -20.8% |
| Swing v2 ema50_two / 월 후보당 최대 1회 진입 | 3.3% | 54.6% | -2.3% | 4.5% | 2.9% | 1.3% |
| Swing v2 ema50_two / 월 후보당 최대 2회 진입 | 25.2% | 58.9% | -3.2% | -2.0% | 26.9% | 21.2% |
| Swing v2 ema50_two / 청산 후 72시간 재진입 금지 | 21.7% | 12.5% | -10.5% | -2.4% | 31.3% | -14.6% |
| Swing v2 ema50_two / 손절 후 월말까지 재진입 금지 | 104.4% | 62.5% | -16.1% | 3.5% | 30.6% | -16.8% |
| Swing v2 atr_only / 월 후보당 최대 1회 진입 | 128.2% | 119.4% | -2.9% | -6.6% | 47.3% | -8.7% |

## 월별 수익률 샘플

| Strategy | 2025-01 | 2025-02 | 2025-03 | 2025-04 | 2025-05 | 2025-06 | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Monthly v1 | 4.4% | -17.7% | 0.0% | 0.0% | 17.7% | -0.1% | 18.6% | 7.4% | -1.2% | -3.0% | -3.4% | 0.0% |
| EMA50 눌림 기존 | 2.6% | -10.6% | -6.0% | 8.3% | -5.6% | -3.3% | 37.2% | -0.2% | -3.0% | -3.4% | -2.7% | 0.0% |
| EMA50 눌림 + 48h 쿨다운 | -6.6% | -7.4% | -4.1% | 8.3% | -3.7% | -3.8% | 36.9% | -8.8% | -1.6% | -1.8% | -0.7% | 0.0% |
| Swing v2 ema50_single / 월 후보당 최대 1회 진입 | 0.6% | -1.1% | 0.0% | 0.0% | 3.1% | -0.6% | -0.4% | -0.2% | -1.1% | 1.4% | -0.6% | 0.0% |
| Swing v2 ema50_single / 월 후보당 최대 2회 진입 | 0.2% | -2.4% | 0.0% | 0.0% | 2.4% | -2.6% | -0.6% | -0.4% | -1.0% | 0.6% | -2.1% | 0.0% |
| Swing v2 ema50_single / 청산 후 72시간 재진입 금지 | -6.2% | -3.2% | 0.0% | 0.0% | 0.9% | -2.5% | 13.2% | -3.9% | -1.1% | -3.2% | -2.6% | -1.1% |
| Swing v2 ema50_single / 손절 후 월말까지 재진입 금지 | -3.7% | -10.9% | 0.0% | 0.0% | 9.9% | -3.9% | 11.9% | -0.2% | -4.8% | -6.3% | -11.2% | -1.1% |
| Swing v2 ema50_two / 월 후보당 최대 1회 진입 | -0.1% | -2.1% | 0.0% | 0.0% | 5.7% | -0.6% | -0.7% | -0.2% | -1.1% | 1.3% | -0.6% | 0.0% |
| Swing v2 ema50_two / 월 후보당 최대 2회 진입 | -0.4% | -3.2% | 0.0% | 0.0% | 15.5% | -4.8% | 18.7% | -0.8% | -1.3% | 0.4% | -2.0% | 0.0% |
| Swing v2 ema50_two / 청산 후 72시간 재진입 금지 | -8.5% | -4.1% | 0.0% | 0.0% | 2.0% | -3.0% | 15.0% | -5.9% | -1.4% | -3.9% | -2.9% | -1.1% |
| Swing v2 ema50_two / 손절 후 월말까지 재진입 금지 | -5.2% | -11.4% | 0.0% | 0.0% | 13.8% | -6.7% | 14.3% | 2.5% | -2.8% | -6.2% | -11.7% | -1.1% |
| Swing v2 atr_only / 월 후보당 최대 1회 진입 | 4.0% | -18.0% | -0.1% | 0.0% | 4.0% | -1.8% | 19.7% | 8.0% | -2.0% | -7.1% | -10.9% | 0.0% |

## 최악 월 Top 10

| Rank | Strategy | Month | Return |
|---|---|---|---:|
| 1 | Swing v2 atr_only / 청산 후 72시간 재진입 금지 | 2025-02 | -19.8% |
| 2 | Swing v2 atr_only / 월 후보당 최대 2회 진입 | 2025-02 | -19.8% |
| 3 | Swing v2 atr_only / 청산 후 72시간 재진입 금지 | 2021-12 | -19.6% |
| 4 | Swing v2 monthly_defense / 청산 후 72시간 재진입 금지 | 2025-02 | -18.5% |
| 5 | Swing v2 monthly_defense / 손절 후 월말까지 재진입 금지 | 2025-02 | -18.5% |
| 6 | Swing v2 monthly_defense / 월 후보당 최대 2회 진입 | 2025-02 | -18.5% |
| 7 | Swing v2 monthly_defense / 월 후보당 최대 1회 진입 | 2025-02 | -18.3% |
| 8 | Swing v2 atr_only / 월 후보당 최대 1회 진입 | 2025-02 | -18.0% |
| 9 | Monthly v1 | 2025-02 | -17.7% |
| 10 | Swing v2 ema50_two / 손절 후 월말까지 재진입 금지 | 2021-12 | -17.6% |

## 최고 월 Top 10

| Rank | Strategy | Month | Return |
|---|---|---|---:|
| 1 | EMA50 눌림 기존 | 2025-07 | 37.2% |
| 2 | EMA50 눌림 + 48h 쿨다운 | 2025-07 | 36.9% |
| 3 | Swing v2 atr_only / 월 후보당 최대 2회 진입 | 2020-11 | 36.7% |
| 4 | Swing v2 atr_only / 청산 후 72시간 재진입 금지 | 2020-11 | 36.7% |
| 5 | Swing v2 atr_only / 손절 후 월말까지 재진입 금지 | 2020-11 | 36.7% |
| 6 | Swing v2 atr_only / 월 후보당 최대 1회 진입 | 2020-11 | 36.6% |
| 7 | Monthly v1 | 2024-02 | 35.7% |
| 8 | Swing v2 atr_only / 월 후보당 최대 1회 진입 | 2024-02 | 35.1% |
| 9 | Swing v2 monthly_defense / 월 후보당 최대 1회 진입 | 2024-02 | 35.1% |
| 10 | Swing v2 atr_only / 월 후보당 최대 2회 진입 | 2024-02 | 35.1% |

## 데이터 커버리지

| Symbol | Interval | First | Last | Candles |
|---|---|---:|---:|---:|
| BTC | 1d | 2018-01-01 | 2026-01-02 | 2924 |
| ETH | 1d | 2018-01-01 | 2026-01-02 | 2924 |
| BTC | 4h | 2018-01-01 | 2026-01-02 | 17523 |
| ETH | 4h | 2018-01-01 | 2026-01-02 | 17523 |

## 산출물

- `btc_eth_monthly_strength_v1_swing_v2_report.md`
- `btc_eth_monthly_strength_v1_swing_v2_summary.csv`
- `btc_eth_monthly_strength_v1_swing_v2_candidates.csv`
- `btc_eth_monthly_strength_v1_swing_v2_verdicts.csv`
- `btc_eth_monthly_strength_v1_swing_v2_monthly_returns.csv`
- `btc_eth_monthly_strength_v1_swing_v2_yearly_returns.csv`
- `btc_eth_monthly_strength_v1_swing_v2_monthly_rankings.csv`
- `btc_eth_monthly_strength_v1_swing_v2_trades.csv`
