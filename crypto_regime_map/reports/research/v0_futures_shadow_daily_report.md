# V0 Futures Paper Shadow Daily Run

- generated_at: 2026-06-23 11:07:53 UTC
- runner: `v0_futures_shadow_daily_runner.py`
- executed_profiles: `v0_futures_3x_size25`, `v0_futures_2x_size50`
- execution_scope: futures paper shadow only; no live or exchange order APIs
- exit_code: 0
- log_path: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/logs/v0_futures_shadow_daily_runner.log`

## Run Results

| Profile | Status | State dir | Orders created | Signals created | Trades created | Open positions | Error |
|---|---|---|---:|---:|---:|---:|---|
| v0_futures_3x_size25 | success | `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25` | 0 | 0 | 0 | 0 |  |
| v0_futures_2x_size50 | success | `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50` | 0 | 0 | 0 | 0 |  |

## State Summary

# V0 Futures Paper Shadow Summary

- generated_at: 2026-06-23 11:07 UTC
- source: paper state CSV ledgers only
- mutation: none; this script does not run paper, order, or live execution paths

| Candidate | Profile | State exists | Leverage | Size | Effective | Equity | Orders | Positions | Trades | Signals | Regime | Action bias | Max DD | Open notional | Liq risk | Status | Last equity |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|---|
| V0 current | v0_spot_or_1x | false | 1x | 1.00 | 1.00x | 1.000000 | 0 | 0 | 0 | 0 |  |  | 0.00% | 0.000000 | 0 | missing |  |
| futures 3x size25 | v0_futures_3x_size25 | true | 3x | 0.25 | 0.75x | 1.000000 | 0 | 0 | 0 | 18 | defensive | reduce_risk | 0.00% | 0.000000 | 0 | warning | 2026-06-23 11:06 |
| futures 2x size50 | v0_futures_2x_size50 | true | 2x | 0.50 | 1.00x | 1.000000 | 0 | 0 | 0 | 18 | defensive | reduce_risk | 0.00% | 0.000000 | 0 | warning | 2026-06-23 11:07 |

## State Directories

- V0 current: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/paper_alpha_engine_v1_2`
- futures 3x size25: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25`
- futures 2x size50: `/home/myno/바탕화면/agi/agi/crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50`
