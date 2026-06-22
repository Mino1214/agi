# Hedge Engine v0 Decision Memo

- Decision date: 2026-06-21
- Hedge Engine v0 status: REJECTED
- Short Engine v0 status: REJECTED
- Current Paper Trading candidate: Alpha Long Engine v1.2 No Hedge

## Decision

Hedge Engine v0 is rejected as a research result. It must not be integrated into Long Engine v1.2, and Paper Engine must not connect to any Hedge Engine v0 logic.

The operating candidate is fixed as Alpha Long Engine v1.2 No Hedge.

## Baseline

| Candidate | CAGR | MDD | Calmar |
|---|---:|---:|---:|
| Alpha Long Engine v1.2 No Hedge | 31.4% | -28.1% | 1.12 |

## Hedge Engine v0 Findings

- Hedge v0 failed to improve MDD versus No Hedge.
- Hedge net benefit was mostly negative after cost and funding effects.
- Drawdown Hedge worsened MDD.
- Shock Hedge produced 0 trades because there was no long exposure to hedge under the tested condition.
- Conclusion: use cash defense and auto pause, not short or hedge overlays.

## Integration Lock

- Do not integrate Hedge Engine v0 with Long Engine v1.2.
- Do not connect Hedge Engine v0 to Paper Engine.
- Do not use Hedge Engine v0 as a Paper Trading candidate.
- Keep Paper Trading candidate as Alpha Long Engine v1.2 No Hedge.

## Short Engine v0 Summary

Short Engine v0 is also REJECTED. It remains research-only and must not be integrated into Long Engine v1.2 or Paper Engine.

Key reason: Short Engine v0 failed the practical deployment checks, including negative Calmar and negative total/CAGR results under actual funding.

## Next Operating Candidate

- Alpha Long Engine v1.2
- No DOGE
- alpha_score top 20%
- liquidation buffer
- taker-only
- actual funding
- slippage 0.2%
- No Hedge

## Pre-Paper Checklist

- Health Monitor full test pass
- Dashboard status cards normal
- paper_start_time configured
- No retroactive entry from historical signals
- Live trading API disabled
