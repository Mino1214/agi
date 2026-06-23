# V0 Futures Paper Shadow Setup Report

## Objective

Prepare paper-only futures shadow execution for V0 baseline candidates without changing the default V0 paper path, live order logic, or existing research outputs.

## Candidates

| Candidate | Paper profile | Exchange leverage | Size multiplier | Effective exposure | Status |
|---|---|---:|---:|---:|---|
| V0_SPOT_OR_1X | `v0_spot_or_1x` | 1x | 1.00 | 1.00x | default paper baseline |
| V0_FUTURES_3X_SIZE25 | `v0_futures_3x_size25` | 3x | 0.25 | 0.75x | paper shadow only |
| V0_FUTURES_2X_SIZE50 | `v0_futures_2x_size50` | 2x | 0.50 | 1.00x | paper shadow only |

## Implementation Summary

- Added `--paper-profile` to `alpha_engine_v1_2_paper_engine.py`.
- The default profile is `v0_spot_or_1x`, so existing paper run-once behavior remains the default.
- Futures profiles require an explicit separate `--state-dir`.
- Futures profiles write and validate `paper_profile.json` inside the selected shadow state-dir.
- The shadow state-dir owns separate orders, trades, positions, equity, signals, daily report, and health files.
- Dashboard/report text for a shadow state includes leverage, size multiplier, and effective exposure from profile metadata.
- Added read-only `v0_futures_shadow_summary.py` to compare V0 current, 3x size25, and 2x size50 state dirs.

## Risk Guard

The paper engine blocks futures shadow execution when any of the following is true:

- exchange leverage is not a positive integer
- exchange leverage exceeds 3x
- effective exposure exceeds 1.0x
- the profile is a 5x profile
- the profile has known liquidation touch
- 2x size is 75% or higher
- 3x size is 50% or higher
- pure 2x+ exposure is requested
- futures profile is combined with defensive probe or 4H regime
- futures profile uses the default V0 paper state-dir
- the selected state-dir is already locked to another futures profile

## Run Commands

```bash
python3 crypto_regime_map/scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --paper-profile v0_futures_3x_size25 \
  --state-dir crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25
```

```bash
python3 crypto_regime_map/scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --paper-profile v0_futures_2x_size50 \
  --state-dir crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50
```

```bash
python3 crypto_regime_map/scripts/v0_futures_shadow_summary.py \
  --output crypto_regime_map/reports/research/v0_futures_shadow_summary.md
```

## Operational Boundary

This setup remains paper shadow only. It does not add live execution, exchange order placement, reduce-only order placement, or changes to the existing operational dashboard.
