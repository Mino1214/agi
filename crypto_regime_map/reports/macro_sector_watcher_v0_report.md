# Macro / Sector Watcher v0 Report

- generated_at: 2026-06-21 15:19 UTC
- data_asof: 2026-06-21
- mode: 관찰 전용 / 매매 미반영
- boundary: Alpha Long Engine v1.2 진입/청산 로직 미수정, Paper Engine 주문 로직 미수정
- oos_policy: OOS 전략 성과와 섞지 않고 data/macro_sector 아래에 별도 기록
- fetch_mode: best_effort_online

## Dashboard Cards

### Macro 상태 카드
| item | value |
| --- | --- |
| trade_regime/action_bias | defensive / reduce_risk |
| macro_summary | macro headwind / risk-off leaning; DXY 7D +0.99%, 10Y 7D +0.01pp, 2Y 7D +0.14pp, QQQ 7D +3.28%, Gold 7D -1.00% |
| DXY | 100.85 (+0.99% 7D, source=yahoo:DX-Y.NYB) |
| US 10Y yield | 4.46% (+0.01pp 7D, source=treasury:daily_yield_curve) |
| US 2Y yield | 4.19% (+0.14pp 7D, source=treasury:daily_yield_curve) |
| QQQ | 740.62 (+3.28% 7D, source=yahoo:QQQ) |
| Gold | 4172.90 (-1.00% 7D, source=yahoo:GC=F) |
| BTC dominance | 56.21% (n/a 7D, source=coingecko:global) |
| stablecoin supply | $283.48B (n/a 7D, source=coingecko:coins_markets) |

### Sector strength 카드
| side | sector | members | 7D avg | 7D vs BTC | alpha avg | volume 7D chg |
| --- | --- | --- | --- | --- | --- | --- |
| strong | high_beta_l1 | SOL | +3.58% | +6.01% | 9.50 | -15.43% |
| strong | smart_contract | ETH | +0.33% | +2.76% | 9.50 | -5.15% |
| strong | tokenization_infra | ETH | +0.33% | +2.76% | 9.50 | -5.15% |
| weak | l1 | AVAX, ADA | -9.54% | -7.11% | n/a | +35.17% |
| weak | institutional_subnet | AVAX | -7.39% | -4.96% | n/a | +88.72% |
| weak | exchange_ecosystem | BNB | -4.25% | -1.82% | n/a | +12.11% |

### RWA watch 카드
| asset/sector | role | 7D | 30D | vs BTC 7D | status |
| --- | --- | --- | --- | --- | --- |
| ETH | alpha_universe | +0.33% | -16.19% | +2.76% | available |
| LINK | alpha_universe | -2.87% | -15.65% | -0.44% | available |
| ONDO | watchlist | -7.34% | -11.22% | -4.91% | available |
| MKR | watchlist | n/a | n/a | n/a | daily_ohlcv_unavailable |
| AAVE | watchlist | +9.79% | -12.90% | +12.22% | available |
| oracle | sector | -2.87% | -15.65% | -0.44% | sector_average |
| rwa | sector | -7.34% | -11.22% | -4.91% | sector_average |
| defi_lending | sector | +9.79% | -12.90% | +12.22% | sector_average |
| tokenization_infra | sector | +0.33% | -16.19% | +2.76% | sector_average |
| stablecoin_supply | macro_proxy | - | - | - | $283.48B (n/a 7D, source=coingecko:coins_markets) |

## 오늘 강한 섹터
| sector | members | 7D avg | 7D vs BTC | 30D avg |
| --- | --- | --- | --- | --- |
| high_beta_l1 | SOL | +3.58% | +6.01% | -12.52% |
| smart_contract | ETH | +0.33% | +2.76% | -16.19% |
| tokenization_infra | ETH | +0.33% | +2.76% | -16.19% |

## 오늘 약한 섹터
| sector | members | 7D avg | 7D vs BTC | 30D avg |
| --- | --- | --- | --- | --- |
| l1 | AVAX, ADA | -9.54% | -7.11% | -32.32% |
| institutional_subnet | AVAX | -7.39% | -4.96% | -31.31% |
| exchange_ecosystem | BNB | -4.25% | -1.82% | -9.21% |

## Alpha Signal / Sector Alignment
| item | value |
| --- | --- |
| status | no_entry_allowed_observation_only |
| signal_type | top_20_passed |
| signal_symbols | ETH, SOL |
| signal_sectors | high_beta_l1, smart_contract, tokenization_infra |
| top_strength_sectors | high_beta_l1, smart_contract, tokenization_infra |
| overlap | high_beta_l1, smart_contract, tokenization_infra |
| order_usage | 관찰 전용 / 주문 결정 미반영 |

## RWA / Tokenization Watch
| item | value |
| --- | --- |
| RWA watchlist | ONDO 7D -7.34%; MKR 7D n/a; AAVE 7D +9.79% |
| oracle sector 7D | -2.87% |
| DeFi lending sector 7D | +9.79% |
| tokenization infra sector 7D | +0.33% |
| tokenized treasury market size | unavailable |

## Data Availability
| item | value |
| --- | --- |
| asset_rows | 12 |
| asset_data_available | 11 |
| macro_unavailable | - |
| latest_equity_timestamp | 2026-06-21 14:25 |
