# Alpha Long v1.2 Operation Stabilization Report

Generated: 2026-06-21 14:26 UTC

## Scope

- Target strategy: Alpha Long Engine v1.2 No Hedge
- Scope: paper/OOS operation stabilization only
- No strategy logic, alpha_score gate, regime gate, Short/Hedge logic, or live order API was changed.

## Health Monitor

- Current health status: `warning`
- Previous critical cause: active trading data gaps and stale signal-delay detection.
- Repair result: `20468` candle rows repaired, `0` duplicate rows removed, validation `pass`.
- Current data gate:
  - failed gap count: `0`
  - trading failed gap count: `0`
  - repairable gap count: `0`
  - unrepairable gap count: `0`
- Current final block reason: `regime_reduce_risk`
- Signal health: `normal`

Critical was cleared. The remaining warning is from historical missing-candle diagnostics that are not currently failing the trading data gate.

## Paper Engine

- `run-once --use-cache` completed successfully.
- `paper_signals.csv` was updated.
- Current rows after the run:
  - signals: `18`
  - orders: `0`
  - trades: `0`
  - positions: `0`
  - equity snapshots: `14`
- In `reduce_risk` / defensive state, no order was created.
- Signals before `paper_start_time` are treated as `missed_signal` records only and are not order candidates.
- DOGE exclusion, alpha_score top 20% gate, and liquidation buffer behavior remain enforced by the existing strategy rules.

## Dashboard

- Local health endpoint: `http://127.0.0.1:8790/health` returned `ok: true`.
- Domain health endpoint: `https://paper.medicalnewshub.info/health` returned `ok: true`.
- Dashboard PID: `55534`
- Last restart time: `2026-06-21 14:25 UTC`
- Loop status: running
- Loop interval: `3600` seconds
- Last loop run time: `2026-06-21 14:25 UTC`
- Restart command: `scripts/manage_paper_control_panel.sh restart`

Dashboard process metadata is written to:

- `data/paper_control_panel.pid`
- `data/paper_control_panel_state.json`

The dashboard API exposes process, loop, and health state through `/health`.

## Control Panel

The control panel now surfaces operational state on the first screen:

- health status
- current regime and action bias
- new-entry availability
- last strategy run and data update times
- dashboard PID, alive state, and last restart time

Signal, position, health-flow, and chart views are backed by existing paper CSV state. The chart uses TradingView Lightweight Charts and renders event badges for `B`, `S`, `TP`, `SL`, and `MS`, plus current position price lines when positions exist.

## OOS Boundary

- `strategy_locked`: `true`
- `strategy_lock_name`: `Alpha Long Engine v1.2 No Hedge`
- `strategy_lock_time`: `2026-06-21 14:13 UTC`
- `paper_start_time`: `2026-06-21 14:13 UTC`
- `oos_start_time`: `2026-06-21 14:13 UTC`

Only data after `paper_start_time` / `oos_start_time` should be classified as OOS. Any future strategy change requires an OOS reset.

## Remaining Blockers

- New entries are currently blocked by `regime_reduce_risk`.
- Paper trades and OOS trade samples remain `0` until an eligible post-start signal appears under an entry-allowed regime.
- The 72-hour stability window has been prepared and started, but it is not complete yet.
