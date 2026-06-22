# Alpha Engine v1 Futures Execution & Liquidation Audit 리포트

- 생성 시각: 2026-06-21 06:42 UTC
- 기간: 2020-01-01 ~ 2025-12-31 UTC
- 기존 Alpha Engine v1 및 funding audit 파일은 수정하지 않았다.
- Futures OHLCV는 Binance USD-M `/fapi/v1/klines`에서 별도 캐시로 수집했다.
- 청산가 추정은 isolated long, 설정 레버리지 3x, maintenance margin 0.5%, liquidation fee buffer 0.1% 가정이다.
- 실제 레버리지는 `initial_notional / entry_equity`로 계산했다.
- 청산 위험은 stop price가 liquidation price보다 낮거나 같거나, 보유 중 1H open이 liquidation price 이하로 갭다운한 경우로 정의했다.
- Spot/Futures 성과 차이 PASS 기준은 CAGR 변화 20% 이내, MDD 변화 5%p 이내, 거래 수 변화 10% 이내다.
- Funding audit의 40,260 trade rows는 8개 변형과 5개 funding 시나리오를 펼친 결과이며, 성과는 summary row별로 분리 계산했다.

## Pass/Fail

| Check | Result | Evidence |
|---|---|---|
| Unique base trades == 1140 | PASS | rows 1140, unique 1140, duplicates 0 |
| Funding audit row expansion explained | PASS | funding rows 40260, variants 8, scenarios 5, Alpha10 actual unique 1140 |
| Taker-only + funding Calmar >= 1.2 | PASS | Calmar 2.20 |
| Slippage 0.2% Calmar >= 1.0 | FAIL | Calmar 0.70 |
| Liquidation risk trades == 0 | FAIL | risk 1, 1H low touches 1, stop not first 1 |
| Spot/Futures OHLCV performance not materially changed | PASS | CAGR delta -1.9%, MDD delta -0.8pp, trade delta -0.8% |
| Liquidation stress MDD within -40% | PASS | stress MDD -30.2% |

## Unique Trade Count 감사

| Metric | Value |
|---|---:|
| Base Alpha10 trade rows | 1140 |
| Base Alpha10 unique trades | 1140 |
| Base duplicate rows | 0 |
| Funding audit trade rows | 40260 |
| Funding variants | 8 |
| Funding scenarios | 5 |
| Funding summary trade sum | 40260 |
| Funding Alpha10 actual unique trades | 1140 |
| Funding rows explained by variant/scenario summaries | True |

## Spot/Futures OHLCV 성과 비교

| Metric | Spot | Futures | Delta |
|---|---:|---:|---:|
| Trades | 1140 | 1131 | -0.8% |
| CAGR | 53.0% | 52.0% | -1.9% |
| MDD | -30.2% | -31.0% | -0.8%p |
| Calmar | 1.7547 | 1.6763 |  |
| Common unique trades | 839 |  |  |
| Spot-only unique trades | 301 |  |  |
| Futures-only unique trades | 292 |  |  |

## Futures OHLCV 가격 차이

| Symbol | Interval | Candles | Avg close diff | Max close diff | Avg high diff | Avg low diff |
|---|---|---:|---:|---:|---:|---:|
| BTC | 1h | 52576 | 0.1% | 2.6% | 0.1% | 0.1% |
| ETH | 1h | 52576 | 0.1% | 2.5% | 0.1% | 0.1% |
| SOL | 1h | 46413 | 0.1% | 23.9% | 0.1% | 0.1% |
| BNB | 1h | 51609 | 0.1% | 2.4% | 0.1% | 0.1% |
| XRP | 1h | 52448 | 0.1% | 6.7% | 0.1% | 0.1% |
| LINK | 1h | 52184 | 0.1% | 2.8% | 0.1% | 34.8% |
| AVAX | 1h | 46197 | 0.1% | 7.4% | 0.1% | 0.1% |
| DOGE | 1h | 47995 | 0.1% | 3.3% | 0.1% | 0.1% |
| ADA | 1h | 51848 | 0.1% | 3.6% | 0.1% | 0.1% |
| TON | 1h | 12254 | 0.0% | 0.4% | 0.1% | 0.1% |
| BTC | 4h | 13151 | 0.1% | 2.1% | 0.1% | 0.1% |
| ETH | 4h | 13151 | 0.1% | 2.5% | 0.1% | 0.1% |
| SOL | 4h | 11609 | 0.1% | 19.7% | 0.1% | 0.1% |
| BNB | 4h | 12909 | 0.1% | 1.8% | 0.1% | 0.1% |
| XRP | 4h | 13119 | 0.1% | 6.7% | 0.1% | 0.1% |
| LINK | 4h | 13053 | 0.1% | 2.6% | 0.1% | 139.0% |
| AVAX | 4h | 11555 | 0.1% | 7.4% | 0.1% | 0.1% |
| DOGE | 4h | 12004 | 0.1% | 10.5% | 0.1% | 0.1% |
| ADA | 4h | 12969 | 0.1% | 5.2% | 0.1% | 0.1% |
| TON | 4h | 3064 | 0.0% | 0.3% | 0.1% | 0.1% |

## 수수료 현실성

| Name | Group | Market | Fee | Slip | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Trades | Unique | Avg lev | Max lev | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Maker only fee 0.02% | Fee model | spot | 0.02% | 0.05% | False | 2303.3% | 69.9% | -24.2% | 2.5618 | 2.8907 | 1.4124 | 1140 | 1140 | 0.3094 | 2.7032 | 0 |
| Taker only fee 0.05% | Fee model | spot | 0.05% | 0.05% | False | 1798.5% | 63.3% | -26.5% | 2.3763 | 2.3912 | 1.3795 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Maker/taker mixed fee 0.035% | Fee model | spot | 0.035% | 0.05% | False | 2036.1% | 66.6% | -25.3% | 2.4690 | 2.6274 | 1.3957 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Fee stress 0.05% | Fee stress | spot | 0.05% | 0.05% | False | 1798.5% | 63.3% | -26.5% | 2.3763 | 2.3912 | 1.3795 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Fee stress 0.10% | Fee stress | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |
| Fee stress 0.20% | Fee stress | spot | 0.2% | 0.05% | False | 482.8% | 34.1% | -37.0% | 1.4536 | 0.9218 | 1.2487 | 1140 | 1140 | 0.3093 | 2.7028 | 0 |
| Fee stress 0.30% | Fee stress | spot | 0.3% | 0.05% | False | 164.7% | 17.6% | -44.1% | 0.8460 | 0.3995 | 1.1867 | 1140 | 1140 | 0.3093 | 2.7026 | 0 |
| Fee stress 0.50% | Fee stress | spot | 0.5% | 0.05% | False | -45.7% | -9.7% | -75.9% | -0.3375 | -0.1273 | 1.1048 | 1140 | 1140 | 0.3093 | 2.7022 | 0 |
| Taker only fee 0.05% + actual funding | Fee/Funding | spot | 0.05% | 0.05% | True | 1698.8% | 61.9% | -28.1% | 2.2404 | 2.2042 | 1.3365 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |

## 슬리피지 스트레스

| Name | Group | Market | Fee | Slip | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Trades | Unique | Avg lev | Max lev | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Base slippage 0.05% | Slippage stress | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |
| Slippage stress 0.10% | Slippage stress | spot | 0.1% | 0.1% | False | 715.0% | 41.8% | -32.3% | 1.7727 | 1.2956 | 1.2228 | 1151 | 1151 | 0.3030 | 2.3358 | 0 |
| Slippage stress 0.20% | Slippage stress | spot | 0.1% | 0.2% | False | 293.7% | 25.7% | -36.9% | 1.2518 | 0.6950 | 1.0715 | 1185 | 1185 | 0.2925 | 1.5942 | 0 |
| Slippage stress 0.50% | Slippage stress | spot | 0.1% | 0.5% | False | -45.5% | -9.6% | -72.9% | -0.4591 | -0.1319 | 0.7941 | 1295 | 1295 | 0.2914 | 2.6143 | 0 |
| Slippage stress 1.00% | Slippage stress | spot | 0.1% | 1% | False | -99.2% | -55.4% | -99.3% | -4.1941 | -0.5575 | 0.4786 | 1777 | 1777 | 0.3177 | 2.6255 | 0 |

## 손절 체결 현실성

| Name | Group | Market | Fee | Slip | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Trades | Unique | Avg lev | Max lev | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Spot OHLCV base | Base | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 1 |
| Conservative stop gap fill | Stop fill stress | spot | 0.1% | 0.05% | False | 1137.3% | 52.1% | -30.2% | 2.0417 | 1.7221 | 1.3235 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |

## 전체 실행 감사 요약

| Name | Group | Market | Fee | Slip | Funding | Total | CAGR | MDD | Sharpe | Calmar | PF | Trades | Unique | Avg lev | Max lev | Liq risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Spot OHLCV base | Base | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 1 |
| Futures OHLCV base | Futures OHLCV | futures | 0.1% | 0.05% | False | 1132.6% | 52.0% | -31.0% | 2.0209 | 1.6763 | 1.3811 | 1131 | 1131 | 0.2974 | 2.5015 | 1 |
| Maker only fee 0.02% | Fee model | spot | 0.02% | 0.05% | False | 2303.3% | 69.9% | -24.2% | 2.5618 | 2.8907 | 1.4124 | 1140 | 1140 | 0.3094 | 2.7032 | 0 |
| Taker only fee 0.05% | Fee model | spot | 0.05% | 0.05% | False | 1798.5% | 63.3% | -26.5% | 2.3763 | 2.3912 | 1.3795 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Maker/taker mixed fee 0.035% | Fee model | spot | 0.035% | 0.05% | False | 2036.1% | 66.6% | -25.3% | 2.4690 | 2.6274 | 1.3957 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Fee stress 0.05% | Fee stress | spot | 0.05% | 0.05% | False | 1798.5% | 63.3% | -26.5% | 2.3763 | 2.3912 | 1.3795 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Fee stress 0.10% | Fee stress | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |
| Fee stress 0.20% | Fee stress | spot | 0.2% | 0.05% | False | 482.8% | 34.1% | -37.0% | 1.4536 | 0.9218 | 1.2487 | 1140 | 1140 | 0.3093 | 2.7028 | 0 |
| Fee stress 0.30% | Fee stress | spot | 0.3% | 0.05% | False | 164.7% | 17.6% | -44.1% | 0.8460 | 0.3995 | 1.1867 | 1140 | 1140 | 0.3093 | 2.7026 | 0 |
| Fee stress 0.50% | Fee stress | spot | 0.5% | 0.05% | False | -45.7% | -9.7% | -75.9% | -0.3375 | -0.1273 | 1.1048 | 1140 | 1140 | 0.3093 | 2.7022 | 0 |
| Base slippage 0.05% | Slippage stress | spot | 0.1% | 0.05% | False | 1181.2% | 53.0% | -30.2% | 2.0677 | 1.7547 | 1.3301 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |
| Slippage stress 0.10% | Slippage stress | spot | 0.1% | 0.1% | False | 715.0% | 41.8% | -32.3% | 1.7727 | 1.2956 | 1.2228 | 1151 | 1151 | 0.3030 | 2.3358 | 0 |
| Slippage stress 0.20% | Slippage stress | spot | 0.1% | 0.2% | False | 293.7% | 25.7% | -36.9% | 1.2518 | 0.6950 | 1.0715 | 1185 | 1185 | 0.2925 | 1.5942 | 0 |
| Slippage stress 0.50% | Slippage stress | spot | 0.1% | 0.5% | False | -45.5% | -9.6% | -72.9% | -0.4591 | -0.1319 | 0.7941 | 1295 | 1295 | 0.2914 | 2.6143 | 0 |
| Slippage stress 1.00% | Slippage stress | spot | 0.1% | 1% | False | -99.2% | -55.4% | -99.3% | -4.1941 | -0.5575 | 0.4786 | 1777 | 1777 | 0.3177 | 2.6255 | 0 |
| Conservative stop gap fill | Stop fill stress | spot | 0.1% | 0.05% | False | 1137.3% | 52.1% | -30.2% | 2.0417 | 1.7221 | 1.3235 | 1140 | 1140 | 0.3094 | 2.7030 | 0 |
| Taker only fee 0.05% + actual funding | Fee/Funding | spot | 0.05% | 0.05% | True | 1698.8% | 61.9% | -28.1% | 2.2404 | 2.2042 | 1.3365 | 1140 | 1140 | 0.3094 | 2.7031 | 0 |
| Liquidation stress / spot base | Liquidation stress | spot | 0.1% | 0.05% | False | 1179.6% | 52.9% | -30.2% | 2.0643 | 1.7517 | 1.3292 | 1140 | 1140 | 0.3094 | 2.7030 | 1 |

## 레버리지 분포

| Metric | Value |
|---|---:|
| Trades | 1140 |
| Average leverage | 0.3094 |
| Median leverage | 0.2438 |
| Max leverage | 2.7030 |
| <= 1x trades | 1114 |
| >= 2x trades | 3 |
| >= 3x trades | 0 |
| >= 4x trades | 0 |

## 청산 위험 감사

| Metric | Value |
|---|---:|
| Trades | 1140 |
| Liquidation risk trades | 1 |
| 1H low touched liquidation price | 1 |
| 4H low touched liquidation price | 1 |
| Stop not before liquidation | 1 |
| Liquidation stress MDD | -30.2% |
| Liquidation stress Calmar | 1.7517 |

## Base Spot 청산 위험 거래

| Symbol | Entry | Exit | Entry | Stop | Liq | Min 1H low | PnL | Stress PnL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| DOGE | 2021-01-29 12:00 | 2021-02-11 20:00 | 0.0500 | 0.0149 | 0.0336 | 0.0222 | 0.0098 | -0.0060 |

## 산출물

- `alpha_engine_v1_futures_execution_audit_report.md`
- `alpha_engine_v1_futures_execution_audit_summary.csv`
- `alpha_engine_v1_futures_execution_audit_trades.csv`
