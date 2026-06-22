# Alpha Long v1.2 Paper Stability Report

Generated: 2026-06-21 14:26 UTC

## Test Window

- Test type: 72-hour paper stability observation
- Status: prepared and loop started
- Loop start time: `2026-06-21 14:25 UTC`
- Loop interval: `3600` seconds
- Expected cadence: one paper run per hour
- Dashboard process: alive, PID `55534`
- Health endpoint: `https://paper.medicalnewshub.info/health`

This report is the start-of-window baseline. The 72-hour result should be updated after the observation window completes.

## Baseline Counters

- paper health records: `22`
- health events: `369`
- signal rows: `18`
- order rows: `0`
- trade rows: `0`
- open position rows: `0`
- equity rows: `14`

## Latest Health Snapshot

- health status: `warning`
- data component: `warning`
- signal component: `normal`
- risk component: `normal`
- order/position component: `normal`
- final block reason: `regime_reduce_risk`
- new entry allowed: `false`
- active trading data gaps: `0`
- unrepairable gaps: `0`

## 72-Hour Metrics To Track

The loop and CSV outputs are prepared to track:

- execution count
- failure count
- data missing count
- signal generation count
- order generation count
- order block count
- health status changes

Primary files:

- `data/paper_alpha_engine_v1_2/paper_health.csv`
- `data/paper_alpha_engine_v1_2/health_events.csv`
- `data/paper_alpha_engine_v1_2/paper_signals.csv`
- `data/paper_alpha_engine_v1_2/paper_orders.csv`
- `data/paper_alpha_engine_v1_2/paper_trades.csv`
- `data/paper_alpha_engine_v1_2/paper_positions.csv`
- `data/paper_alpha_engine_v1_2/paper_equity.csv`

## Current Interpretation

The paper engine is running, but no order or trade has been created because the current action bias is `reduce_risk`. This is expected behavior and should not be treated as a paper engine failure.

## Post-Window Pass Criteria

- Loop remains alive for 72 hours or records a recoverable restart with timestamp.
- Hourly runs continue without uncaught process death.
- Any data gap is either repaired or recorded with a readable failure reason.
- No orders are created during `reduce_risk`, `shock`, or other blocked states.
- No order is created from a signal before `paper_start_time`.
- OOS samples include only records after `2026-06-21 14:13 UTC`.
