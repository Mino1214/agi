# Xeon Quant System Role Check

- generated_at_kst: 2026-06-23 22:34:21 KST
- generated_at_utc: 2026-06-23 13:34:21 UTC
- scope: Xeon futures paper shadow daily report generation and M3 report sync
- exclusions: no main checkout, no commit/push, no live order execution, no V1.2 operating paper state read, no auto registration

## Executive Summary

- current_branch: `feature/futures-paper-shadow`
- futures shadow runner: present; latest runner log shows both approved futures shadow profiles completed successfully with exit_code 0.
- shadow state dirs: both approved futures shadow dirs exist under `crypto_regime_map/data/research_cache`.
- M3 sync target: Tailscale hostname `myno-macbookpro`; sync script ran successfully and local/remote SHA-256 matched.
- live order API pattern: no exchange/live order API call pattern found in `scripts`, `src`, or `tests`; only paper virtual order helpers matched the broad `create_order` pattern.
- git candidates under `data/state/csv/log`: none found.
- systemd timer: `v0-futures-shadow.timer` is already registered, enabled, and active. No registration was performed during this check.

## 1. Branch

- current branch: `feature/futures-paper-shadow`
- no checkout was performed.

## 2. Git Status

```text
## feature/futures-paper-shadow...origin/feature/futures-paper-shadow
 M crypto_regime_map/reports/research/v0_futures_shadow_daily_report.md
?? crypto_regime_map/reports/research/ml_regime_poc_report.md
?? crypto_regime_map/reports/research/ml_regime_v2_report.md
?? crypto_regime_map/reports/research/ml_regime_v3_hybrid_backtest_report.md
?? crypto_regime_map/reports/research/v0_futures_shadow_daily.md
?? crypto_regime_map/reports/research/v0_integer_leverage_sensitivity_report.md
?? crypto_regime_map/reports/research/v0_leverage_sanity_and_risk_policy_report.md
?? crypto_regime_map/reports/research/v4h_core_satellite_report.md
?? crypto_regime_map/reports/research/v4h_diversified_robustness_report.md
?? crypto_regime_map/reports/research/v4h_rec92_25_robustness_report.md
?? crypto_regime_map/reports/research/v4h_strict_selective_recovery_report.md
?? crypto_regime_map/reports/research/v4h_symbol_specific_recovery_report.md
?? crypto_regime_map/scripts/ml_regime_train_report.py
?? crypto_regime_map/scripts/ml_regime_v2_report.py
?? crypto_regime_map/scripts/ml_regime_v3_hybrid_backtest.py
?? crypto_regime_map/scripts/ml_regime_walk_forward_report.py
?? crypto_regime_map/scripts/sync_xeon_shadow_daily_report.sh
?? crypto_regime_map/scripts/v4h_core_satellite_audit.py
?? crypto_regime_map/scripts/v4h_diversified_robustness_audit.py
?? crypto_regime_map/scripts/v4h_rec92_25_robustness_audit.py
?? crypto_regime_map/scripts/v4h_symbol_specific_recovery_audit.py
?? crypto_regime_map/src/ml_regime_features.py
?? crypto_regime_map/src/ml_regime_labels.py
?? crypto_regime_map/src/ml_regime_models.py
?? crypto_regime_map/src/ml_regime_v2.py
?? crypto_regime_map/tests/test_ml_regime_features.py
?? crypto_regime_map/tests/test_ml_regime_labels.py
?? crypto_regime_map/tests/test_ml_regime_v2.py
?? crypto_regime_map/tests/test_ml_regime_v3_hybrid.py
```

## 3. Futures Shadow Daily Runner

- runner: `crypto_regime_map/scripts/v0_futures_shadow_daily_runner.py`
- approved profiles: `v0_futures_3x_size25`, `v0_futures_2x_size50`
- fixed state root: `crypto_regime_map/data/research_cache`
- behavior observed from source: cache-only market data guard blocks live OHLCV fetches during shadow runner execution; no exchange order API path is called.
- latest log excerpt status:

```text
2026-06-23 12:09:02 UTC START output=crypto_regime_map/reports/research/v0_futures_shadow_daily_report.md
2026-06-23 12:09:49 UTC PROFILE_SUCCESS profile=v0_futures_3x_size25 orders=0 signals=9 trades=0 positions=0
2026-06-23 12:10:38 UTC PROFILE_SUCCESS profile=v0_futures_2x_size50 orders=0 signals=9 trades=0 positions=0
2026-06-23 12:10:38 UTC FINISH exit_code=0 output=crypto_regime_map/reports/research/v0_futures_shadow_daily_report.md
```

## 4. Shadow State Directories

| Profile | State dir | Exists | Files present |
|---|---|---:|---|
| `v0_futures_3x_size25` | `crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25` | yes | `health_state.json`, `paper_profile.json`, paper CSV ledgers, daily markdown |
| `v0_futures_2x_size50` | `crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50` | yes | `health_state.json`, `paper_profile.json`, paper CSV ledgers, daily markdown |

Only the two futures shadow state dirs above were inspected.

## 5. `v0_futures_3x_size25` Status

- profile lock: `paper_profile=v0_futures_3x_size25`
- mode: `futures_paper_shadow`
- exchange_leverage: `3`
- size_multiplier: `0.25`
- effective_exposure: `0.75`
- liquidation_touch: `false`
- latest equity row: `equity=1.0`, `cash=1.0`, `open_positions=0`, `open_notional=0`, `current_regime=defensive`, `current_action_bias=reduce_risk`, `strategy_status=warning`, `liquidation_risk_count=0`
- data rows: equity `11`, orders `0`, positions `0`, trades `0`, signals `27`

## 6. `v0_futures_2x_size50` Status

- profile lock: `paper_profile=v0_futures_2x_size50`
- mode: `futures_paper_shadow`
- exchange_leverage: `2`
- size_multiplier: `0.50`
- effective_exposure: `1.00`
- liquidation_touch: `false`
- latest equity row: `equity=1.0`, `cash=1.0`, `open_positions=0`, `open_notional=0`, `current_regime=defensive`, `current_action_bias=reduce_risk`, `strategy_status=warning`, `liquidation_risk_count=0`
- data rows: equity `11`, orders `0`, positions `0`, trades `0`, signals `27`

## 7. Sync Script Check

- script: `crypto_regime_map/scripts/sync_xeon_shadow_daily_report.sh`
- `bash -n`: pass
- manual sync command:

```bash
M3_HOST=myno-macbookpro \
M3_USER=myno \
./crypto_regime_map/scripts/sync_xeon_shadow_daily_report.sh
```

- result: success
- synced file: `v0_futures_shadow_daily_report.md`
- same-basename json: local absent, remote absent
- no `data`, `state`, `csv`, or `log` directory copy is performed by the sync script.

## 8. M3 Tailscale Hostname Sync

`tailscale status`:

```text
100.74.6.105    myno             linux
100.117.144.21  macmini          macOS
100.124.61.67   myno-macbookpro  macOS
```

- sync target used: `myno-macbookpro`
- remote dest: `/Users/myno/agi-lab/runtime/xeon-shadow`
- remote contents after sync: only `v0_futures_shadow_daily_report.md`
- local SHA-256: `950a6457bf7edcbb29746f2230f7fa2abd279ca0eb7f916486f0b2ef61a3cb76`
- remote SHA-256: `950a6457bf7edcbb29746f2230f7fa2abd279ca0eb7f916486f0b2ef61a3cb76`
- verdict: local and remote report hashes match.

## 9. Live Order API Pattern Check

- strict live/exchange order API pattern scan result: no matches.
- patterns checked included `futures_create_order`, `private_post`, Binance `/fapi/v1/order`, Binance `/api/v3/order`, `ccxt.`, and mutating HTTP verbs via `requests`/`httpx`.
- broad `create_order` scan only matched paper virtual order helper names:
  - `crypto_regime_map/scripts/alpha_engine_v1_2_paper_engine.py:create_orders_for_signals`
  - related unit tests

Verdict: no live order API pattern addition detected in the checked code paths.

## 10. Git Candidate Check For `data/state/csv/log`

- `git status --porcelain` filtered for root and `crypto_regime_map/` `data`, `state`, `csv`, `log`, `logs`: no matches.
- `git ls-files --others --exclude-standard` filtered for those paths: no matches.

Verdict: full `data/state/csv/log` dirs are not git candidates.

## 11. systemd Timer Registration

- timer: `v0-futures-shadow.timer`
- registration state: already registered and enabled before this check.
- current state: active waiting.
- next trigger observed: `Wed 2026-06-24 09:10:00 KST`
- service: `v0-futures-shadow.service`, inactive oneshot.
- service command:

```text
/usr/bin/python3 crypto_regime_map/scripts/v0_futures_shadow_daily_runner.py run-once --output crypto_regime_map/reports/research/v0_futures_shadow_daily_report.md
```

No systemd registration, enable, disable, start, or stop action was performed during this check.

## 12. Auto Registration Need

- 신규 등록 필요 여부: no, because `v0-futures-shadow.timer` already exists and is enabled.
- operational note: if the intended state is "not automatically registered yet", the current machine is already past that state. Disabling/removing the timer is a separate operator decision and was not performed.

## Command Results

| Check | Command | Result |
|---|---|---|
| tests | `pytest -q` | pass, `95 passed in 21.93s` |
| py compile | `rg --files -g '*.py' crypto_regime_map \| xargs python3 -m py_compile` | pass |
| sync shell syntax | `bash -n crypto_regime_map/scripts/sync_xeon_shadow_daily_report.sh` | pass |
| runner-related shell syntax | `find crypto_regime_map -type f -name '*.sh' -print -exec bash -n {} \;` | pass for `sync_xeon_shadow_daily_report.sh`, `manage_paper_control_panel.sh` |
| sync execution | `M3_HOST=myno-macbookpro M3_USER=myno ./crypto_regime_map/scripts/sync_xeon_shadow_daily_report.sh` | pass |
| SHA compare | local `shasum -a 256`, remote `shasum -a 256` | match |
| Tailscale | `tailscale status` | pass |

## Final Verdict

Xeon currently functions as the futures paper shadow runner host and report sync source for M3. The shadow report sync path is working through Tailscale hostname `myno-macbookpro`, and only the report markdown is present remotely. The main risk item is operational: a systemd user timer is already enabled for the daily shadow runner despite the stated expectation that auto registration may still be pending.
