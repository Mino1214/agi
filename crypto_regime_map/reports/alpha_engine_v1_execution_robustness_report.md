# Alpha Engine v1 Execution Robustness v1.1 리포트

- 생성 시각: 2026-06-21 07:46 UTC
- 기간: 2020-01-01 ~ 2025-12-31 UTC
- 기존 Alpha Engine v1, funding audit, futures execution audit 파일은 수정하지 않았다.
- 새 알파 조건은 추가하지 않고 기존 Alpha 신호를 주문 단계에서만 필터링했다.
- 비용 기준은 taker-only 0.05%, funding은 실제 funding과 보수적 연 -10% 비용 시나리오를 비교했다.
- `alpha_score 상위 20%`는 같은 4H 신호 시점의 후보 중 상위 20%만 주문으로 넘기는 방식이다.
- 청산 안전거리는 `stop_price - liquidation_price >= 0.5 * 손절폭`을 만족하도록 isolated leverage를 자동 축소하고, 불가능하면 스킵한다.

## Pass/Fail

| Check | Result | Evidence |
|---|---|---|
| Slippage 0.2% Calmar >= 1.0 | FAIL | Conservative v1.1 spot actual funding 0.2% slippage Calmar 0.92 |
| Liquidation risk trades == 0 | PASS | risk trades 0 |
| Taker-only + actual funding Calmar >= 1.2 | PASS | base slippage Calmar 2.87 |
| CAGR retention >= 70% of Original | PASS | retention 84.6% vs Original same stress |
| MDD within -35% | PASS | MDD -29.3% |
| Trade count reduced by >= 30% | PASS | trade reduction 36.3% (1185 -> 755) |
| Symbol concentration < 50% | PASS | largest positive PnL share 39.2% |

## Slippage 0.2% + Actual Funding 비교

| Variant | Market | Slip | Funding | CAGR | MDD | Sharpe | Calmar | PF | Trades | Monthly | Hold | Avg lev | Max lev | >=3x | >=4x | Liq risk | Skipped | Max symbol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Original Alpha Engine v1 / 10 symbols | spot | 0.2% | actual_funding | 31.9% | -35.7% | 1.4251 | 0.8919 | 1.0608 | 1185 | 16.4583 | 1.4345 | 0.2925 | 1.5942 | 0 | 0 | 1 | 25592 | 61.8% |
| No DOGE | spot | 0.2% | actual_funding | 32.1% | -35.9% | 1.4553 | 0.8957 | 1.0788 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.6% |
| No DOGE + symbol leverage cap | spot | 0.2% | actual_funding | 32.1% | -35.9% | 1.4553 | 0.8957 | 1.0788 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.6% |
| No DOGE + liquidation safety buffer | spot | 0.2% | actual_funding | 32.1% | -35.9% | 1.4553 | 0.8957 | 1.0788 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.6% |
| No DOGE + alpha_score top 20% | spot | 0.2% | actual_funding | 31.4% | -28.1% | 1.6974 | 1.1154 | 1.1116 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.9% |
| No DOGE + top 20% + symbol leverage cap | spot | 0.2% | actual_funding | 31.4% | -28.1% | 1.6974 | 1.1154 | 1.1116 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.9% |
| No DOGE + top 20% + liquidation buffer | spot | 0.2% | actual_funding | 31.4% | -28.1% | 1.6974 | 1.1154 | 1.1116 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.9% |
| Conservative v1.1 | spot | 0.2% | actual_funding | 26.9% | -29.3% | 1.7518 | 0.9195 | 1.1561 | 755 | 10.4861 | 1.5407 | 0.2872 | 1.8553 | 0 | 0 | 0 | 26022 | 39.2% |

## Base Slippage 0.05% + Actual Funding 비교

| Variant | Market | Slip | Funding | CAGR | MDD | Sharpe | Calmar | PF | Trades | Monthly | Hold | Avg lev | Max lev | >=3x | >=4x | Liq risk | Skipped | Max symbol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Original Alpha Engine v1 / 10 symbols | spot | 0.05% | actual_funding | 61.9% | -28.1% | 2.2404 | 2.2042 | 1.3365 | 1140 | 15.8333 | 1.4959 | 0.3094 | 2.7031 | 0 | 0 | 1 | 25637 | 52.9% |
| No DOGE | spot | 0.05% | actual_funding | 60.8% | -28.2% | 2.2391 | 2.1571 | 1.3623 | 1098 | 15.2500 | 1.5165 | 0.3154 | 2.7031 | 0 | 0 | 0 | 25679 | 52.7% |
| No DOGE + symbol leverage cap | spot | 0.05% | actual_funding | 60.8% | -28.2% | 2.2391 | 2.1571 | 1.3623 | 1098 | 15.2500 | 1.5165 | 0.3154 | 2.7031 | 0 | 0 | 0 | 25679 | 52.7% |
| No DOGE + liquidation safety buffer | spot | 0.05% | actual_funding | 60.8% | -28.2% | 2.2391 | 2.1571 | 1.3623 | 1098 | 15.2500 | 1.5165 | 0.3154 | 2.7031 | 0 | 0 | 0 | 25679 | 52.7% |
| No DOGE + alpha_score top 20% | spot | 0.05% | actual_funding | 53.5% | -16.9% | 2.4274 | 3.1721 | 1.3495 | 899 | 12.4861 | 1.6197 | 0.2931 | 2.4252 | 0 | 0 | 0 | 25878 | 23.5% |
| No DOGE + top 20% + symbol leverage cap | spot | 0.05% | actual_funding | 53.5% | -16.9% | 2.4274 | 3.1721 | 1.3495 | 899 | 12.4861 | 1.6197 | 0.2931 | 2.4252 | 0 | 0 | 0 | 25878 | 23.5% |
| No DOGE + top 20% + liquidation buffer | spot | 0.05% | actual_funding | 53.5% | -16.9% | 2.4274 | 3.1721 | 1.3495 | 899 | 12.4861 | 1.6197 | 0.2931 | 2.4252 | 0 | 0 | 0 | 25878 | 23.5% |
| Conservative v1.1 | spot | 0.05% | actual_funding | 44.5% | -15.5% | 2.4254 | 2.8734 | 1.4060 | 729 | 10.1250 | 1.6062 | 0.3022 | 2.8901 | 0 | 0 | 0 | 26048 | 27.7% |

## Conservative v1.1 Slippage Stress

| Variant | Market | Slip | Funding | CAGR | MDD | Sharpe | Calmar | PF | Trades | Monthly | Hold | Avg lev | Max lev | >=3x | >=4x | Liq risk | Skipped | Max symbol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Conservative v1.1 | spot | 0.05% | actual_funding | 44.5% | -15.5% | 2.4254 | 2.8734 | 1.4060 | 729 | 10.1250 | 1.6062 | 0.3022 | 2.8901 | 0 | 0 | 0 | 26048 | 27.7% |
| Conservative v1.1 | spot | 0.1% | actual_funding | 35.9% | -23.0% | 2.1165 | 1.5603 | 1.2728 | 745 | 10.3472 | 1.5653 | 0.2999 | 2.8901 | 0 | 0 | 0 | 26032 | 31.8% |
| Conservative v1.1 | spot | 0.2% | actual_funding | 26.9% | -29.3% | 1.7518 | 0.9195 | 1.1561 | 755 | 10.4861 | 1.5407 | 0.2872 | 1.8553 | 0 | 0 | 0 | 26022 | 39.2% |
| Conservative v1.1 | spot | 0.3% | actual_funding | 17.3% | -36.9% | 1.2369 | 0.4677 | 1.0352 | 774 | 10.7500 | 1.4973 | 0.2796 | 1.3553 | 0 | 0 | 0 | 26003 | 59.4% |
| Conservative v1.1 | spot | 0.5% | actual_funding | 3.2% | -52.7% | 0.3051 | 0.0615 | 0.8695 | 820 | 11.3889 | 1.4004 | 0.2732 | 1.3174 | 0 | 0 | 0 | 25957 | 81.4% |

## 보수적 Funding 연 -10% 비교

| Variant | Market | Slip | Funding | CAGR | MDD | Sharpe | Calmar | PF | Trades | Monthly | Hold | Avg lev | Max lev | >=3x | >=4x | Liq risk | Skipped | Max symbol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Original Alpha Engine v1 / 10 symbols | spot | 0.2% | annual_cost_10 | 32.6% | -34.9% | 1.4941 | 0.9322 | 1.0736 | 1185 | 16.4583 | 1.4345 | 0.2925 | 1.5942 | 0 | 0 | 1 | 25592 | 61.1% |
| No DOGE | spot | 0.2% | annual_cost_10 | 32.8% | -35.1% | 1.5272 | 0.9361 | 1.0921 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.3% |
| No DOGE + symbol leverage cap | spot | 0.2% | annual_cost_10 | 32.8% | -35.1% | 1.5272 | 0.9361 | 1.0921 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.3% |
| No DOGE + liquidation safety buffer | spot | 0.2% | annual_cost_10 | 32.8% | -35.1% | 1.5272 | 0.9361 | 1.0921 | 1142 | 15.8611 | 1.4533 | 0.3001 | 1.5942 | 0 | 0 | 0 | 25635 | 59.3% |
| No DOGE + alpha_score top 20% | spot | 0.2% | annual_cost_10 | 32.0% | -27.2% | 1.7707 | 1.1786 | 1.1266 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.8% |
| No DOGE + top 20% + symbol leverage cap | spot | 0.2% | annual_cost_10 | 32.0% | -27.2% | 1.7707 | 1.1786 | 1.1266 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.8% |
| No DOGE + top 20% + liquidation buffer | spot | 0.2% | annual_cost_10 | 32.0% | -27.2% | 1.7707 | 1.1786 | 1.1266 | 929 | 12.9028 | 1.5511 | 0.2797 | 1.4062 | 0 | 0 | 0 | 25848 | 29.8% |
| Conservative v1.1 | spot | 0.2% | annual_cost_10 | 27.4% | -28.7% | 1.8104 | 0.9535 | 1.1681 | 755 | 10.4861 | 1.5407 | 0.2872 | 1.8553 | 0 | 0 | 0 | 26022 | 41.8% |

## Original vs v1.1 동일 기준 Spot/Futures

| Variant | Market | Slip | Funding | CAGR | MDD | Sharpe | Calmar | PF | Trades | Monthly | Hold | Avg lev | Max lev | >=3x | >=4x | Liq risk | Skipped | Max symbol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Original Alpha Engine v1 / 10 symbols | spot | 0.05% | actual_funding | 61.9% | -28.1% | 2.2404 | 2.2042 | 1.3365 | 1140 | 15.8333 | 1.4959 | 0.3094 | 2.7031 | 0 | 0 | 1 | 25637 | 52.9% |
| Conservative v1.1 | spot | 0.05% | actual_funding | 44.5% | -15.5% | 2.4254 | 2.8734 | 1.4060 | 729 | 10.1250 | 1.6062 | 0.3022 | 2.8901 | 0 | 0 | 0 | 26048 | 27.7% |
| Original Alpha Engine v1 / 10 symbols | futures | 0.05% | actual_funding | 60.5% | -28.9% | 2.1940 | 2.0915 | 1.3970 | 1131 | 15.7083 | 1.4674 | 0.2974 | 2.5024 | 0 | 0 | 1 | 24865 | 57.0% |
| Conservative v1.1 | futures | 0.05% | actual_funding | 36.0% | -15.2% | 2.2020 | 2.3577 | 1.3910 | 720 | 10.0000 | 1.5626 | 0.2971 | 2.8962 | 0 | 0 | 0 | 25276 | 26.3% |

## Calmar 1.60 vs 2.20 차이 원인

| Item | Funding audit Calmar 1.60 | Futures execution audit Calmar 2.20 |
|---|---|---|
| 기준 variant | `Alpha Engine v1 / 10 symbols` actual funding | `Taker only fee 0.05% + actual funding` |
| Trade set | Alpha10 1140 unique trades | 같은 Alpha10 1140 unique trades |
| 비용 가정 | 기존 Alpha 기본 수수료 0.10%, 슬리피지 0.05% | taker-only 0.05%, 슬리피지 0.05% |
| OHLCV 기준 | Spot OHLCV equity curve에 funding overlay | Spot OHLCV, 실행 감사 내 수수료 변경 후 funding overlay |
| 핵심 원인 | funding 비용이 성과를 낮춘 기준선 | 수수료가 0.10%에서 0.05%로 낮아져 CAGR/MDD가 개선됨 |

## Conservative v1.1 스킵 사유

| Slip | Skipped | Reasons |
|---:|---:|---|
| 0.05% | 26048 | alpha_score_not_top_20pct:7455; already_open_or_pending:2387; defensive_no_entry:13652; doge_excluded:1270; max_positions:1284 |
| 0.1% | 26032 | alpha_score_not_top_20pct:7455; already_open_or_pending:2371; defensive_no_entry:13652; doge_excluded:1270; max_positions:1284 |
| 0.2% | 26022 | alpha_score_not_top_20pct:7455; already_open_or_pending:2363; defensive_no_entry:13652; doge_excluded:1270; max_positions:1282 |
| 0.3% | 26003 | alpha_score_not_top_20pct:7455; already_open_or_pending:2345; defensive_no_entry:13652; doge_excluded:1270; max_positions:1281 |
| 0.5% | 25957 | alpha_score_not_top_20pct:7455; already_open_or_pending:2307; defensive_no_entry:13652; doge_excluded:1270; max_positions:1273 |

## Conservative v1.1 심볼별 성과

| Symbol | Trades | PnL | Positive PnL share | MDD contribution |
|---|---:|---:|---:|---:|
| ETH | 96 | 0.7365 | 39.2% | -0.3224 |
| XRP | 71 | 0.3550 | 18.9% | -0.2235 |
| ADA | 71 | 0.3270 | 17.4% | -0.2537 |
| BTC | 86 | 0.2394 | 12.7% | -0.2798 |
| BNB | 135 | 0.2199 | 11.7% | -0.5874 |
| SOL | 106 | -0.0694 | 0.0% | -0.3541 |
| AVAX | 74 | -0.0839 | 0.0% | -0.2914 |
| LINK | 92 | -0.2518 | 0.0% | -0.3887 |
| TON | 24 | -0.3270 | 0.0% | -0.3554 |

## Conservative v1.1 Alpha Score 구간별 성과

| Alpha score bucket | Trades | PnL | Win rate | PF |
|---|---:|---:|---:|---:|
| 5-6 | 4 | -0.0547 | 25.0% | 0.0846 |
| 6-7 | 26 | -0.0890 | 38.5% | 0.6573 |
| 7-8 | 82 | 0.6272 | 24.4% | 1.7599 |
| 8+ | 643 | 0.6623 | 34.4% | 1.1069 |

## 산출물

- `alpha_engine_v1_execution_robustness_report.md`
- `alpha_engine_v1_execution_robustness_summary.csv`
- `alpha_engine_v1_execution_robustness_trades.csv`
