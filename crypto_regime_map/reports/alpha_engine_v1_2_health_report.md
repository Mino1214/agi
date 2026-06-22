# Alpha Engine v1.2 Health Report

- generated_at: 2026-06-22 12:24 UTC
- status: warning
- beginner_message: 데이터는 정상입니다. 하지만 현재 시장 상태가 방어 모드라 주문하지 않습니다.
- new_entry_allowed: False
- pause_reason: regime_reduce_risk
- last_normal_run_at: -
- human_summary: warning: data.missing_candles - BTCUSDT 1h 캔들 누락이 감지됐습니다.
- strategy_locked: Alpha Long Engine v1.2 No Hedge
- oos_rule: paper_start_time 이후 데이터만 OOS로 분류하며 전략 변경 시 OOS reset 필요

## Dashboard Metrics

- recent_20_trade_pf: 
- recent_50_trade_pf: 
- recent_30d_mdd_pct: 0
- recent_7d_trade_count: 0
- recent_30d_trade_count: 0

## Component Status

- system: normal
- data: warning
- signal: warning
- order_position: normal
- risk: normal
- performance: normal
- frequency: normal

## Signal Scan

- scan_count: 9
- entry_candidates: 0

| symbol | alpha_score | top_20 | selected | block_reason |
|---|---:|---|---|---|
| ADAUSDT |  | False | False | alpha_score_below_min |
| AVAXUSDT |  | False | False | alpha_score_below_min |
| BNBUSDT |  | False | False | alpha_score_below_min |
| BTCUSDT |  | False | False | alpha_score_below_min |
| ETHUSDT | 9.5 | True | False | defensive_no_entry |
| LINKUSDT |  | False | False | alpha_score_below_min |
| SOLUSDT | 9 | True | False | defensive_no_entry |
| TONUSDT |  | False | False | alpha_score_below_min |
| XRPUSDT |  | False | False | alpha_score_below_min |

## Findings

- [warning] data.missing_candles: BTCUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: ETHUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: SOLUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: BNBUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: XRPUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: ADAUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: AVAXUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: LINKUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: DOGEUSDT 1h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: BTCUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: ETHUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: BNBUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: XRPUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: ADAUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: LINKUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] data.missing_candles: DOGEUSDT 4h 캔들 누락이 감지됐습니다.
- [warning] signal.missing_signal_after_4h_close: 마지막 4H 봉 마감 후 신호가 생성되지 않았습니다.
