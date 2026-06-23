# Futures Paper Shadow

이 문서는 V0 기준선은 유지하면서 futures paper shadow 후보를 별도 state-dir에서 병행 실행하기 위한 기준이다.

## Scope

- 기본 paper 실행은 `v0_spot_or_1x`이며 futures shadow는 기본값 OFF다.
- futures shadow는 paper-only다. live 주문, exchange 주문, reduce-only 주문을 만들지 않는다.
- futures shadow는 V0 1D EMA regime 기준선만 대상으로 한다.
- `--defensive-probe`, `--short-regime-4h`, `--regime-timeframe 4h`와 함께 실행하지 않는다.
- 기존 V0 paper state-dir는 futures shadow 실행에 사용할 수 없다.

## Profiles

| Profile | Label | Exchange leverage | Size multiplier | Effective exposure | State dir |
|---|---|---:|---:|---:|---|
| `v0_spot_or_1x` | `V0_SPOT_OR_1X` | 1x | 1.00 | 1.00x | existing V0 paper state |
| `v0_futures_3x_size25` | `V0_FUTURES_3X_SIZE25` | 3x | 0.25 | 0.75x | `crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25` |
| `v0_futures_2x_size50` | `V0_FUTURES_2X_SIZE50` | 2x | 0.50 | 1.00x | `crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50` |

## Risk Policy

- `max_exchange_leverage = 3`
- `max_effective_exposure = 1.0`
- `5x` disabled
- liquidation touch 발생 조합 disabled
- `2x size 75%` 이상 disabled
- `3x size 50%` 이상 disabled
- pure `2x+` exposure disabled
- 기본 실거래 후보는 V0 1x only
- futures profiles are paper shadow only

## Commands

Run the 3x / size 25% shadow:

```bash
python3 crypto_regime_map/scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --paper-profile v0_futures_3x_size25 \
  --state-dir crypto_regime_map/data/research_cache/paper_v0_futures_3x_size25
```

Run the 2x / size 50% shadow:

```bash
python3 crypto_regime_map/scripts/alpha_engine_v1_2_paper_engine.py run-once \
  --use-cache \
  --paper-profile v0_futures_2x_size50 \
  --state-dir crypto_regime_map/data/research_cache/paper_v0_futures_2x_size50
```

Generate a read-only comparison summary:

```bash
python3 crypto_regime_map/scripts/v0_futures_shadow_summary.py \
  --output crypto_regime_map/reports/research/v0_futures_shadow_summary.md
```

Without `--output`, the summary script prints Markdown to stdout and does not write files.

## State Separation

Each state-dir contains its own `paper_positions.csv`, `paper_orders.csv`, `paper_trades.csv`, `paper_equity.csv`, `paper_signals.csv`, daily reports, health state, and `paper_profile.json`.

The futures profile guard blocks:

- missing explicit `--state-dir`
- existing V0 paper state-dir
- defensive probe or 4H regime combination
- state-dir already locked to a different futures profile
- risk policy violations

The generated state, cache, CSV, and daily report files are ignored by Git.
