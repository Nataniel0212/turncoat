# Raw campaign data

One JSON line per live campaign, exported from the run directories by
`scripts/export_raw.py`. The export refuses to write unless the campaigns
reproduce the published tables exactly, and `tests/test_raw_data.py` re-checks
this in CI: every k/n, every per-technique count, every mean and every cost.

| File | Campaigns | Reproduces |
|---|---|---|
| `replication-2026-10-16.jsonl` | 60 (Lightning target, 3 scenarios × 20) | `../benchmark-2026-10-16.json` |
| `compare-2026-10-15.jsonl` | 90 (3 target models × 3 scenarios × 10) | `../compare-2026-10-15.json` |

The 15 Oct first benchmark (`../benchmark-2026-10-15.md`) was not retained as raw
data; only its report survives. Its rates are reported separately and never
pooled with these.

## Fields

- `campaign`: run directory name (timestamp + suffix)
- `scenario`, `target`, `attacker`: scenario key and Nemotron model ids
- `compromised`: whether any attempt reached a full (critical) compromise
- `attempts`: per attempt, the technique, verdict, refusal flag, state signals,
  the exact injected text, the agent's tool-call transcript, outbound actions
  and final reply
- `calls`: per model call, phase, model, prompt/completion/reasoning tokens,
  latency and metered cost
- `cost_usd`, `model_time_s`: campaign totals

Baseline calls appear in `calls` with phase `baseline`. Every published
campaign passed its baseline (benign content, no unsafe action).

## Redaction

The attacker sometimes invents credential-shaped strings ("AUTH TOKEN:
0x7F4A…"). They are not real, but they trip secret scanners, so the value is
replaced with `[REDACTED SYNTHETIC TOKEN]` and each affected line records
`redactions` and a note. The scenarios' own fixture token (`SYNTHETIC-SECRET-…`),
tool calls, verdicts, tokens, latency and cost are unchanged. All data is
synthetic; no real person, account, secret or file is involved.
