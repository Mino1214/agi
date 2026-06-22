# Hedge Engine v0 리포트

- 생성 시각: 2026-06-21 12:40 UTC
- Hedge Engine v0는 수익 엔진이 아니라 Alpha Long Engine v1.2 후보의 하락 리스크를 줄이는 방어 엔진 연구다.
- Short Engine v0와 다르다. 목적은 BTC 숏으로 돈을 버는 것이 아니라 기존 롱 포지션의 MDD와 폭락 손실을 완화하는 것이다.
- 기존 Alpha Long Engine v1.2 파일, Paper Engine 파일, Short Engine v0 파일은 수정하지 않았다.
- 실제 주문 API 연결은 없고, Binance USD-M Futures BTCUSDT OHLCV/funding 데이터로만 백테스트했다.
- 기준 Long: No DOGE, alpha_score top 20%, liquidation buffer, taker-only 0.05%, slippage 0.2%, actual funding.

## 해석 메모

- No Hedge 대비 방어 효과가 비용과 funding 반영 후 유지되는지를 기준으로 판단했다.
- Hedge PnL은 BTC 숏 헤지 자체 손익이고, Long PnL은 기준 Alpha Long v1.2 후보의 funding 포함 손익이다.
- Shock Hedge는 기존 Long v1.2 후보를 그대로 유지한 조건에서 BTC 헤지 거래가 0회였다. v1.2 기준 Long이 shock/no_new_entry 구간에서 이미 신규/보유 리스크를 크게 줄여, 다음 1H open에 헤지할 long exposure가 없었던 것으로 해석한다.

## Pass / Fail

| Variant | Check | Result | Evidence |
|---|---|---|---|
| Defensive Hedge 20% | MDD reduction >= 15% | FAIL | MDD reduction -0.0% |
| Defensive Hedge 20% | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Defensive Hedge 20% | Calmar higher than No Hedge | FAIL | Calmar 1.12 vs 1.12 |
| Defensive Hedge 20% | Hedge net benefit positive | FAIL | Net benefit -0.00 |
| Defensive Hedge 20% | Cost-included effect maintained | FAIL | Net benefit -0.00, cost 0.00, funding 0.00 |
| Defensive Hedge 20% | Hedge trade count | PASS | Hedge trades 4, monthly 0.1 |
| Defensive Hedge 20% | Missed upside | PASS | Missed upside 0.00 |
| Defensive Hedge 30% | MDD reduction >= 15% | FAIL | MDD reduction -0.0% |
| Defensive Hedge 30% | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Defensive Hedge 30% | Calmar higher than No Hedge | FAIL | Calmar 1.11 vs 1.12 |
| Defensive Hedge 30% | Hedge net benefit positive | FAIL | Net benefit -0.00 |
| Defensive Hedge 30% | Cost-included effect maintained | FAIL | Net benefit -0.00, cost 0.01, funding 0.00 |
| Defensive Hedge 30% | Hedge trade count | PASS | Hedge trades 4, monthly 0.1 |
| Defensive Hedge 30% | Missed upside | PASS | Missed upside 0.00 |
| Shock Hedge 20% / keep longs | MDD reduction >= 15% | FAIL | MDD reduction 0.0% |
| Shock Hedge 20% / keep longs | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Shock Hedge 20% / keep longs | Calmar higher than No Hedge | FAIL | Calmar 1.12 vs 1.12 |
| Shock Hedge 20% / keep longs | Hedge net benefit positive | FAIL | Net benefit 0.00 |
| Shock Hedge 20% / keep longs | Cost-included effect maintained | FAIL | Net benefit 0.00, cost 0.00, funding 0.00 |
| Shock Hedge 20% / keep longs | Hedge trade count | PASS | Hedge trades 0, monthly 0.0 |
| Shock Hedge 20% / keep longs | Missed upside | PASS | Missed upside 0.00 |
| Shock Hedge 30% / keep longs | MDD reduction >= 15% | FAIL | MDD reduction 0.0% |
| Shock Hedge 30% / keep longs | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Shock Hedge 30% / keep longs | Calmar higher than No Hedge | FAIL | Calmar 1.12 vs 1.12 |
| Shock Hedge 30% / keep longs | Hedge net benefit positive | FAIL | Net benefit 0.00 |
| Shock Hedge 30% / keep longs | Cost-included effect maintained | FAIL | Net benefit 0.00, cost 0.00, funding 0.00 |
| Shock Hedge 30% / keep longs | Hedge trade count | PASS | Hedge trades 0, monthly 0.0 |
| Shock Hedge 30% / keep longs | Missed upside | PASS | Missed upside 0.00 |
| Shock Hedge 20% / reduce longs 50% | MDD reduction >= 15% | FAIL | MDD reduction 0.0% |
| Shock Hedge 20% / reduce longs 50% | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Shock Hedge 20% / reduce longs 50% | Calmar higher than No Hedge | FAIL | Calmar 1.12 vs 1.12 |
| Shock Hedge 20% / reduce longs 50% | Hedge net benefit positive | FAIL | Net benefit 0.00 |
| Shock Hedge 20% / reduce longs 50% | Cost-included effect maintained | FAIL | Net benefit 0.00, cost 0.00, funding 0.00 |
| Shock Hedge 20% / reduce longs 50% | Hedge trade count | PASS | Hedge trades 0, monthly 0.0 |
| Shock Hedge 20% / reduce longs 50% | Missed upside | PASS | Missed upside 0.00 |
| Shock Hedge 30% / reduce longs 50% | MDD reduction >= 15% | FAIL | MDD reduction 0.0% |
| Shock Hedge 30% / reduce longs 50% | CAGR damage <= 20% | PASS | CAGR damage 0.0% |
| Shock Hedge 30% / reduce longs 50% | Calmar higher than No Hedge | FAIL | Calmar 1.12 vs 1.12 |
| Shock Hedge 30% / reduce longs 50% | Hedge net benefit positive | FAIL | Net benefit 0.00 |
| Shock Hedge 30% / reduce longs 50% | Cost-included effect maintained | FAIL | Net benefit 0.00, cost 0.00, funding 0.00 |
| Shock Hedge 30% / reduce longs 50% | Hedge trade count | PASS | Hedge trades 0, monthly 0.0 |
| Shock Hedge 30% / reduce longs 50% | Missed upside | PASS | Missed upside 0.00 |
| Drawdown Hedge 20/30% | MDD reduction >= 15% | FAIL | MDD reduction -11.1% |
| Drawdown Hedge 20/30% | CAGR damage <= 20% | PASS | CAGR damage 8.6% |
| Drawdown Hedge 20/30% | Calmar higher than No Hedge | FAIL | Calmar 0.92 vs 1.12 |
| Drawdown Hedge 20/30% | Hedge net benefit positive | FAIL | Net benefit -0.60 |
| Drawdown Hedge 20/30% | Cost-included effect maintained | FAIL | Net benefit -0.60, cost 0.64, funding 0.06 |
| Drawdown Hedge 20/30% | Hedge trade count | PASS | Hedge trades 206, monthly 2.9 |
| Drawdown Hedge 20/30% | Missed upside | WARNING | Missed upside 1.02 |
| Volatility Hedge 20/30% | MDD reduction >= 15% | FAIL | MDD reduction -0.9% |
| Volatility Hedge 20/30% | CAGR damage <= 20% | PASS | CAGR damage 0.1% |
| Volatility Hedge 20/30% | Calmar higher than No Hedge | FAIL | Calmar 1.10 vs 1.12 |
| Volatility Hedge 20/30% | Hedge net benefit positive | FAIL | Net benefit -0.01 |
| Volatility Hedge 20/30% | Cost-included effect maintained | FAIL | Net benefit -0.01, cost 0.01, funding 0.00 |
| Volatility Hedge 20/30% | Hedge trade count | PASS | Hedge trades 10, monthly 0.1 |
| Volatility Hedge 20/30% | Missed upside | WARNING | Missed upside 0.01 |
| Composite Hedge 20/30% | MDD reduction >= 15% | FAIL | MDD reduction -1.1% |
| Composite Hedge 20/30% | CAGR damage <= 20% | PASS | CAGR damage 0.3% |
| Composite Hedge 20/30% | Calmar higher than No Hedge | FAIL | Calmar 1.10 vs 1.12 |
| Composite Hedge 20/30% | Hedge net benefit positive | FAIL | Net benefit -0.02 |
| Composite Hedge 20/30% | Cost-included effect maintained | FAIL | Net benefit -0.02, cost 0.01, funding 0.00 |
| Composite Hedge 20/30% | Hedge trade count | PASS | Hedge trades 8, monthly 0.1 |
| Composite Hedge 20/30% | Missed upside | PASS | Missed upside 0.00 |
| Best MDD | Best MDD reduction | INFO | Shock Hedge 20% / keep longs: 0.0% |
| Best Calmar | Best efficiency | INFO | Shock Hedge 20% / keep longs: Calmar 1.12 |

## 핵심 비교

| Name | Total | CAGR | MDD | Sharpe | Calmar | Hedge PnL | Funding | Cost | Net benefit | Trades | MDD red. | CAGR damage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Long v1.2 / No Hedge | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| Defensive Hedge 20% | 414.4% | 31.4% | -28.1% | 1.70 | 1.12 | -0.00 | 0.00 | 0.00 | -0.00 | 4 | -0.0% | 0.0% |
| Defensive Hedge 30% | 414.4% | 31.4% | -28.1% | 1.70 | 1.11 | -0.00 | 0.00 | 0.01 | -0.00 | 4 | -0.0% | 0.0% |
| Shock Hedge 20% / keep longs | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| Shock Hedge 30% / keep longs | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| Shock Hedge 20% / reduce longs 50% | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| Shock Hedge 30% / reduce longs 50% | 414.6% | 31.4% | -28.1% | 1.70 | 1.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| Drawdown Hedge 20/30% | 354.3% | 28.7% | -31.3% | 1.57 | 0.92 | -0.66 | 0.06 | 0.64 | -0.60 | 206 | -11.1% | 8.6% |
| Volatility Hedge 20/30% | 413.9% | 31.4% | -28.4% | 1.71 | 1.10 | -0.01 | 0.00 | 0.01 | -0.01 | 10 | -0.9% | 0.1% |
| Composite Hedge 20/30% | 412.7% | 31.3% | -28.5% | 1.69 | 1.10 | -0.02 | 0.00 | 0.01 | -0.02 | 8 | -1.1% | 0.3% |

## 민감도

| Name | Total | CAGR | MDD | Sharpe | Calmar | Hedge PnL | Funding | Cost | Net benefit | Trades | MDD red. | CAGR damage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Defensive Hedge 10% | 414.5% | 31.4% | -28.1% | 1.70 | 1.12 | -0.00 | 0.00 | 0.00 | -0.00 | 4 | -0.0% | 0.0% |
| Defensive Hedge 50% | 414.3% | 31.4% | -28.2% | 1.70 | 1.11 | -0.00 | 0.00 | 0.01 | -0.00 | 4 | -0.1% | 0.0% |
| Composite Hedge 10% | 413.6% | 31.3% | -28.3% | 1.70 | 1.11 | -0.01 | 0.00 | 0.00 | -0.01 | 8 | -0.6% | 0.1% |
| Composite Hedge 50% | 409.8% | 31.2% | -28.9% | 1.69 | 1.08 | -0.05 | 0.00 | 0.02 | -0.05 | 8 | -2.8% | 0.6% |
| Composite Hedge 20/30% / max hold 14d | 412.7% | 31.3% | -28.5% | 1.69 | 1.10 | -0.02 | 0.00 | 0.01 | -0.02 | 7 | -1.1% | 0.2% |
| Composite Hedge 20/30% / slippage 0.1% | 412.9% | 31.3% | -28.4% | 1.69 | 1.10 | -0.02 | 0.00 | 0.01 | -0.02 | 8 | -1.0% | 0.2% |
| Composite Hedge 20/30% / slippage 0.2% | 412.7% | 31.3% | -28.5% | 1.69 | 1.10 | -0.02 | 0.00 | 0.01 | -0.02 | 8 | -1.1% | 0.3% |
| Composite Hedge 20/30% / slippage 0.3% | 412.4% | 31.3% | -28.5% | 1.69 | 1.10 | -0.02 | 0.00 | 0.01 | -0.02 | 8 | -1.2% | 0.3% |
| Composite Hedge 20/30% / slippage 0.5% | 412.0% | 31.3% | -28.5% | 1.69 | 1.10 | -0.03 | 0.00 | 0.02 | -0.03 | 8 | -1.4% | 0.4% |

## Hedge Ratio별 성과

| Name | Ratio | CAGR | MDD | Calmar | Net benefit | Trades |
|---|---:|---:|---:|---:|---:|---:|
| Defensive Hedge 20% | 0.2 | 31.4% | -28.1% | 1.12 | -0.00 | 4 |
| Defensive Hedge 30% | 0.3 | 31.4% | -28.1% | 1.11 | -0.00 | 4 |
| Composite Hedge 20/30% | 0.20/0.30 | 31.3% | -28.5% | 1.10 | -0.02 | 8 |
| Defensive Hedge 10% | 0.1 | 31.4% | -28.1% | 1.12 | -0.00 | 4 |
| Defensive Hedge 50% | 0.5 | 31.4% | -28.2% | 1.11 | -0.00 | 4 |
| Composite Hedge 10% | 0.10/0.10 | 31.3% | -28.3% | 1.11 | -0.01 | 8 |
| Composite Hedge 50% | 0.50/0.50 | 31.2% | -28.9% | 1.08 | -0.05 | 8 |

## 진입 / 청산 사유

| Entry reason | Exit reason | Trades |
|---|---|---:|
| drawdown_5 | condition_released | 69 |
| drawdown_5 | condition_changed | 44 |
| drawdown_10 | condition_changed | 43 |
| composite_2_conditions | condition_released | 40 |
| drawdown_10 | max_hold | 30 |
| drawdown_5 | max_hold | 20 |
| reduce_risk | condition_released | 16 |
| composite_2_conditions | condition_changed | 16 |
| volatility_15x | condition_released | 7 |
| composite_2_conditions | max_hold | 7 |
| volatility_15x | condition_changed | 1 |
| volatility_2x | condition_changed | 1 |
| volatility_15x | max_hold | 1 |

## 룩어헤드 감사

| Check | Value |
|---|---:|
| Hedge trades | 295 |
| Lookahead failures | 0 |
| Same candle signal/execution | 0 |
| Minimum signal-to-execution lag hours | 1.0 |

## 최악 월 Top 10

| Name | Month | Return |
|---|---|---:|
| Drawdown Hedge 20/30% | 2024-05 | -9.3% |
| Drawdown Hedge 20/30% | 2025-06 | -8.6% |
| Composite Hedge 20/30% | 2025-06 | -8.1% |
| Alpha Long v1.2 / No Hedge | 2025-06 | -8.1% |
| Shock Hedge 20% / keep longs | 2025-06 | -8.1% |
| Shock Hedge 30% / keep longs | 2025-06 | -8.1% |
| Shock Hedge 20% / reduce longs 50% | 2025-06 | -8.1% |
| Shock Hedge 30% / reduce longs 50% | 2025-06 | -8.1% |
| Composite Hedge 20/30% | 2024-05 | -7.0% |
| Alpha Long v1.2 / No Hedge | 2024-05 | -6.9% |

## 최고 월 Top 10

| Name | Month | Return |
|---|---|---:|
| Drawdown Hedge 20/30% | 2021-02 | 44.7% |
| Alpha Long v1.2 / No Hedge | 2021-02 | 44.2% |
| Shock Hedge 20% / keep longs | 2021-02 | 44.2% |
| Shock Hedge 30% / keep longs | 2021-02 | 44.2% |
| Shock Hedge 20% / reduce longs 50% | 2021-02 | 44.2% |
| Shock Hedge 30% / reduce longs 50% | 2021-02 | 44.2% |
| Composite Hedge 20/30% | 2021-02 | 44.2% |
| Alpha Long v1.2 / No Hedge | 2020-07 | 32.2% |
| Shock Hedge 20% / keep longs | 2020-07 | 32.2% |
| Shock Hedge 30% / keep longs | 2020-07 | 32.2% |

## MDD 방어 효과

| Name | MDD | MDD reduction | Baseline MDD window benefit | Hedge net benefit | Missed upside |
|---|---:|---:|---:|---:|---:|
| Defensive Hedge 20% | -28.1% | -0.0% | -0.0% | -0.00 | 0.00 |
| Defensive Hedge 30% | -28.1% | -0.0% | -0.0% | -0.00 | 0.00 |
| Shock Hedge 20% / keep longs | -28.1% | 0.0% | 0.0% | 0.00 | 0.00 |
| Shock Hedge 30% / keep longs | -28.1% | 0.0% | 0.0% | 0.00 | 0.00 |
| Shock Hedge 20% / reduce longs 50% | -28.1% | 0.0% | 0.0% | 0.00 | 0.00 |
| Shock Hedge 30% / reduce longs 50% | -28.1% | 0.0% | 0.0% | 0.00 | 0.00 |
| Drawdown Hedge 20/30% | -31.3% | -11.1% | -3.1% | -0.60 | 1.02 |
| Volatility Hedge 20/30% | -28.4% | -0.9% | -0.3% | -0.01 | 0.01 |
| Composite Hedge 20/30% | -28.5% | -1.1% | -0.3% | -0.02 | 0.00 |
| Defensive Hedge 10% | -28.1% | -0.0% | -0.0% | -0.00 | 0.00 |
| Defensive Hedge 50% | -28.2% | -0.1% | -0.0% | -0.00 | 0.00 |
| Composite Hedge 10% | -28.3% | -0.6% | -0.2% | -0.01 | 0.00 |
| Composite Hedge 50% | -28.9% | -2.8% | -0.8% | -0.05 | 0.01 |
| Composite Hedge 20/30% / max hold 14d | -28.5% | -1.1% | -0.3% | -0.02 | 0.00 |
| Composite Hedge 20/30% / slippage 0.1% | -28.4% | -1.0% | -0.3% | -0.02 | 0.00 |
| Composite Hedge 20/30% / slippage 0.2% | -28.5% | -1.1% | -0.3% | -0.02 | 0.00 |
| Composite Hedge 20/30% / slippage 0.3% | -28.5% | -1.2% | -0.3% | -0.02 | 0.01 |
| Composite Hedge 20/30% / slippage 0.5% | -28.5% | -1.4% | -0.4% | -0.03 | 0.01 |

## Net / Gross Exposure

| Name | Avg net | Max net | Avg gross | Max gross |
|---|---:|---:|---:|---:|
| Defensive Hedge 20% | 12.3% | 235.7% | 12.3% | 235.7% |
| Defensive Hedge 30% | 12.3% | 235.7% | 12.3% | 235.7% |
| Shock Hedge 20% / keep longs | 12.3% | 235.6% | 12.3% | 235.6% |
| Shock Hedge 30% / keep longs | 12.3% | 235.6% | 12.3% | 235.6% |
| Shock Hedge 20% / reduce longs 50% | 12.3% | 235.6% | 12.3% | 235.6% |
| Shock Hedge 30% / reduce longs 50% | 12.3% | 235.6% | 12.3% | 235.6% |
| Drawdown Hedge 20/30% | 12.0% | 233.4% | 15.3% | 278.8% |
| Volatility Hedge 20/30% | 12.3% | 236.0% | 12.3% | 236.0% |
| Composite Hedge 20/30% | 12.3% | 236.7% | 12.4% | 236.7% |
| Defensive Hedge 10% | 12.3% | 235.7% | 12.3% | 235.7% |
| Defensive Hedge 50% | 12.3% | 235.8% | 12.3% | 235.8% |
| Composite Hedge 10% | 12.3% | 236.2% | 12.3% | 236.2% |
| Composite Hedge 50% | 12.3% | 238.4% | 12.4% | 238.4% |
| Composite Hedge 20/30% / max hold 14d | 12.3% | 236.7% | 12.4% | 236.7% |
| Composite Hedge 20/30% / slippage 0.1% | 12.3% | 236.6% | 12.4% | 236.6% |
| Composite Hedge 20/30% / slippage 0.2% | 12.3% | 236.7% | 12.4% | 236.7% |
| Composite Hedge 20/30% / slippage 0.3% | 12.3% | 236.9% | 12.4% | 236.9% |
| Composite Hedge 20/30% / slippage 0.5% | 12.3% | 237.2% | 12.4% | 237.2% |

## 연도별 수익률

| Name | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| Alpha Long v1.2 / No Hedge | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Defensive Hedge 20% | 109.2% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Defensive Hedge 30% | 109.2% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Shock Hedge 20% / keep longs | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Shock Hedge 30% / keep longs | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Shock Hedge 20% / reduce longs 50% | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Shock Hedge 30% / reduce longs 50% | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Drawdown Hedge 20/30% | 102.6% | 64.8% | 0.0% | 39.2% | -2.3% | 0.1% |
| Volatility Hedge 20/30% | 110.5% | 63.5% | 0.0% | 39.2% | -0.2% | 7.4% |
| Composite Hedge 20/30% | 109.4% | 63.6% | 0.0% | 39.4% | -0.1% | 7.5% |
| Defensive Hedge 10% | 109.3% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |
| Defensive Hedge 50% | 109.2% | 63.7% | 0.0% | 39.5% | 0.2% | 7.4% |

## 월별 수익률 최근 12개월

| Name | 2025-01 | 2025-02 | 2025-03 | 2025-04 | 2025-05 | 2025-06 | 2025-07 | 2025-08 | 2025-09 | 2025-10 | 2025-11 | 2025-12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Alpha Long v1.2 / No Hedge | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Defensive Hedge 20% | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Defensive Hedge 30% | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Shock Hedge 20% / keep longs | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Shock Hedge 30% / keep longs | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Shock Hedge 20% / reduce longs 50% | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Shock Hedge 30% / reduce longs 50% | 0.4% | -2.0% | 0.0% | 0.0% | -4.9% | -8.1% | 19.7% | 1.4% | -1.7% | 4.7% | 0.0% | 0.0% |
| Drawdown Hedge 20/30% | -2.1% | -0.8% | 0.0% | 0.0% | -5.4% | -8.6% | 18.5% | 0.7% | -3.0% | 2.9% | 0.0% | 0.0% |

## Hedge 거래 Top 20 손실

| Variant | Entry | Exit | Reason | PnL | Funding | Cost | Hold |
|---|---|---|---|---:|---:|---:|---:|
| Drawdown Hedge 20/30% | 2024-11-07 04:00 | 2024-11-14 04:00 | drawdown_10->max_hold | -0.09 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2025-01-03 12:00 | 2025-01-06 16:00 | drawdown_10->condition_changed | -0.08 | 0.00 | 0.01 | 3.17 |
| Drawdown Hedge 20/30% | 2024-05-12 12:00 | 2024-05-19 12:00 | drawdown_10->max_hold | -0.07 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2024-02-06 14:00 | 2024-02-09 13:00 | drawdown_5->condition_released | -0.06 | 0.00 | 0.00 | 2.96 |
| Drawdown Hedge 20/30% | 2025-07-10 04:00 | 2025-07-17 04:00 | drawdown_10->max_hold | -0.06 | 0.00 | 0.00 | 7.00 |
| Composite Hedge 50% | 2024-03-09 00:00 | 2024-03-12 01:00 | composite_2_conditions->condition_released | -0.04 | 0.00 | 0.00 | 3.04 |
| Drawdown Hedge 20/30% | 2024-03-25 09:00 | 2024-03-25 16:00 | drawdown_10->condition_changed | -0.04 | 0.00 | 0.00 | 0.29 |
| Drawdown Hedge 20/30% | 2025-10-01 09:00 | 2025-10-03 17:00 | drawdown_5->condition_released | -0.04 | 0.00 | 0.00 | 2.33 |
| Drawdown Hedge 20/30% | 2023-06-17 20:00 | 2023-06-21 03:00 | drawdown_5->condition_released | -0.04 | 0.00 | 0.00 | 3.29 |
| Drawdown Hedge 20/30% | 2025-05-20 00:00 | 2025-05-27 00:00 | drawdown_10->max_hold | -0.03 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2025-08-07 08:00 | 2025-08-11 03:00 | drawdown_5->condition_released | -0.03 | 0.00 | 0.00 | 3.79 |
| Drawdown Hedge 20/30% | 2020-12-16 12:00 | 2020-12-17 09:00 | drawdown_5->condition_released | -0.03 | 0.00 | 0.00 | 0.88 |
| Drawdown Hedge 20/30% | 2024-05-19 12:00 | 2024-05-26 12:00 | drawdown_10->max_hold | -0.02 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2025-10-01 08:00 | 2025-10-01 09:00 | drawdown_10->condition_changed | -0.02 | 0.00 | 0.01 | 0.04 |
| Drawdown Hedge 20/30% | 2024-11-16 00:00 | 2024-11-23 00:00 | drawdown_10->max_hold | -0.02 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2025-07-03 04:00 | 2025-07-10 04:00 | drawdown_10->max_hold | -0.02 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2024-12-11 17:00 | 2024-12-18 17:00 | drawdown_5->max_hold | -0.02 | 0.00 | 0.00 | 7.00 |
| Drawdown Hedge 20/30% | 2023-05-01 17:00 | 2023-05-05 18:00 | drawdown_5->condition_released | -0.02 | 0.00 | 0.00 | 4.04 |
| Drawdown Hedge 20/30% | 2025-06-03 00:00 | 2025-06-10 00:00 | drawdown_10->max_hold | -0.02 | 0.00 | 0.00 | 7.00 |
| Composite Hedge 20/30% / slippage 0.5% | 2024-03-09 00:00 | 2024-03-12 01:00 | composite_2_conditions->condition_released | -0.02 | 0.00 | 0.00 | 3.04 |

## 산출물

- `hedge_engine_v0_report.md`
- `hedge_engine_v0_summary.csv`
- `hedge_engine_v0_trades.csv`
- `hedge_engine_v0_monthly.csv`
- `hedge_engine_v0_yearly.csv`
