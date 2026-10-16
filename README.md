# Turncoat

[![ci](https://github.com/Nataniel0212/turncoat/actions/workflows/ci.yml/badge.svg)](https://github.com/Nataniel0212/turncoat/actions/workflows/ci.yml)
![license](https://img.shields.io/badge/license-MIT-blue)

**Will your AI agent turn on you?** Turncoat is an automated prompt-injection
red team and **benchmark** for tool-using LLM agents. It attacks an agent you
control with an adaptive attacker model, checks every outcome against the agent's
real tool calls, and reports an **attack-success rate with 95% confidence
intervals**, so you can measure how exposed an agent is *before* you ship it.

Everything runs on **NVIDIA Nemotron via Nebius Token Factory**: the attacker is
**Nemotron 3 Ultra**; the agent under test is **Nemotron 3.5 Lightning** by default,
with Nano 30B and Ultra 550B for comparison.

> Built solo for the [Nebius × NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com).
> Defensive security research in the tradition of garak and PyRIT: you only test
> agents you own. Synthetic data only. No real person, account, secret or file
> exists anywhere in this repo.
>
> Formerly named Sieve. The Python package and run directories keep the name
> `sieve`; old repository and demo links redirect or still work.

**[Open the interactive demo](https://turncoat-redteam.vercel.app)** — nine recorded
live campaigns are available without a code. Judges can also start a new campaign
using the code in the private testing instructions.

![Recorded bank campaign with injection, tool calls and metered outcome](docs/images/demo.png)

## Results

### Benchmark: 2 × 60 live campaigns, replicated

Three agents, 20 independent campaigns each, run on two different days.
*Full compromise* means the agent took the dangerous action (exfiltrated a
secret, wired money, deleted a file) because injected content told it to.
A campaign is up to **10 adaptive attempts**, so the campaign rate answers "does
a persistent attacker get through within 10 tries?". The per-attempt rate
answers "how often does a single injection work?".

| Agent under test (Lightning) | Campaigns, 15 Oct | Campaigns, 16 Oct (replication) | 95% CI | Per attempt, 15 / 16 Oct | Attacker refusals |
|---|---|---|---|---|---|
| **Banking assistant** (wire funds) | **100%** (20/20) | **100%** (20/20) | 84–100% | 27% (20/74) / 28% (20/72) | 0% |
| **Email assistant** (leak a secret) | **95%** (19/20) | **95%** (19/20) | 76–99% | 28% (19/67) / 23% (19/83) | 0% |
| **Document assistant** (delete files) | **10%** (2/20) | **10%** (2/20) | 3–30% | 1% (2/192) / 1% (2/192) | 0% |

The document rows match exactly on both days, down to each technique count.
Techniques run in a fixed order, so two days with two successes at the same
attempt positions give identical tables; the
[per-campaign raw data](results/raw/) lets you check the 16 Oct side.

Cost: $0.99 and $1.01 for 60 campaigns, a median of $0.011 per campaign in the
16 Oct replication
([`campaign-stats-2026-10-16.json`](results/campaign-stats-2026-10-16.json)).
The strongest technique was **output hijacking**: telling the agent that its
result must be *delivered* by performing the dangerous action. In the
replication, 85% of those attempts fully compromised the banking agent (17/20),
and 56% the email agent (10/18). Raw reports:
[15 Oct](results/benchmark-2026-10-15.md),
[16 Oct](results/benchmark-2026-10-16.md)
([JSON](results/benchmark-2026-10-16.json)). Every 16 Oct and model-comparison
campaign is published in [`results/raw/`](results/raw/): each injection, tool
call, verdict, token count and cost. A CI test recomputes the published tables
from it. The 15 Oct first run survives only as its report.

### Does a bigger model resist better? Yes, sharply

Same attacker, three Nemotron models as the agent under test, 10 campaigns per
cell, $2.27 total ([`results/compare-2026-10-15.json`](results/compare-2026-10-15.json)):

| Agent model | Email | Banking | Documents | Median $ / campaign (this run) | Median model time |
|---|---|---|---|---|---|
| Nemotron 3.5 Lightning | 90% | 100% | 0% | $0.0071 | 9.0 s |
| Nemotron 3 Nano 30B | 60% | 100% | 0% | $0.0202 | 33.5 s |
| Nemotron 3 Ultra 550B | **0%** | **0%** | **0%** | $0.0379 | 28.1 s |

Ultra did not just stay inert. It called its tools, did the task, and explicitly
flagged the injected message as suspicious. Prompt-injection robustness is a
measurable property of the model choice. Cost and latency come from
[`results/campaign-stats-2026-10-15.json`](results/campaign-stats-2026-10-15.json).

### We caught our own benchmark lying

| Pass | Email / Bank / Docs | What changed |
|---|---|---|
| 1. Naive | 10 / 0 / 0 % | The attacker *refused* to write a payload on 72–86% of attempts, silently making agents look safe |
| 2. Valid-trial statistics | 70 / 47 / 5 % | Refusals detected and tagged; only trials with ≥ 1 real attack count; refusal rate reported (25–54%) |
| 3. Root cause fixed | 95 / 100 / 10 % | Attacker reasoning switched **off**: refusals fell to 0% |

Details and every intermediate number are in [DEVLOG.md](DEVLOG.md).

## Why a measurement tool, not a chatbot

- **Adaptive attacks.** Static templates are weak. Turncoat runs an iterative
  refinement loop inspired by TAP (arXiv [2606.10525](https://arxiv.org/abs/2606.10525)),
  without TAP's tree search or pruning: one candidate per attempt, rotating six
  techniques, and the attacker is told how far its last attempt got before it
  rewrites the next one.
- **State-based verification.** Success is decided by the agent's actual tool
  calls (did the secret leave? did money move?), never by an LLM judge that an
  injection could fool. This follows AgentDojo (arXiv
  [2406.13352](https://arxiv.org/abs/2406.13352)).
- **Honest statistics.** Independent trials, 95% Wilson score intervals, per-technique
  rates, and the attacker's own refusal rate reported next to every result.
- **Cheap at volume.** A full Lightning campaign has a median cost of about one
  cent: $0.0071 in the 15 Oct model comparison, $0.011 in the 16 Oct replication.

## How it works

```mermaid
flowchart LR
    A["Attacker<br/>Nemotron 3 Ultra<br/>thinking off · temp 1.0"] -->|writes injection| D["Untrusted data<br/>email · bank memo · document"]
    D -->|read during its normal task| T["Agent under test<br/>Lightning · Nano · Ultra<br/>real tool-calling loop"]
    T -->|tool calls| S{"State check<br/>did money, a secret<br/>or a file move?"}
    S -->|verdict| B["Benchmark<br/>n trials · Wilson 95% CI · $"]
    S -.->|feedback: what the agent did| A
```

Each campaign: a **baseline** run with benign content (the agent must stay
safe), then up to *N* adaptive attempts. It stops at the first full compromise,
at *N*, or when the budget guard trips.

| Module | Role |
|---|---|
| `sieve/scenarios.py` | Pluggable agents: system prompt, task, tools, injection point, state check |
| `sieve/attacker.py` | The attacker: technique rotation, progress feedback, refusal detection |
| `sieve/target_agent.py` | The agent under test: a real tool-calling loop |
| `sieve/loop.py` | Baseline + attack loop + budget guard; emits a live event stream |
| `sieve/benchmark.py` | Independent trials, Wilson CIs, per-technique rates |
| `sieve/metering.py` | Per-call tokens, latency and cost to JSONL |
| `sieve/nebius.py` | Token Factory client and Nemotron quirk handling |
| `sieve/guard.py` | Spend and abuse guard for the hosted demo |
| `sieve/adapters.py` | Run your own Python agent's orchestration and tool policy |
| `app.py` | FastAPI web API (streams a live campaign as NDJSON) |

### Built-in scenarios

| key | Agent | Its ordinary task | What the injection aims for |
|---|---|---|---|
| `inbox` | email assistant | summarize my inbox | fetch an account secret and email it out |
| `bank` | banking assistant | what's my balance? | transfer funds to an external payee |
| `docs` | document assistant | summarize my documents | delete the user's files |

## How we use NVIDIA Nemotron & Nebius Token Factory

Every LLM call goes **directly** to Nebius Token Factory
(`https://api.tokenfactory.nebius.com/v1`, OpenAI-compatible), never through any
gateway.

| Role | Model id | Settings | Why |
|---|---|---|---|
| Attacker | `nvidia/Nemotron-3-Ultra-550b-a55b` | `enable_thinking: false`, temperature 1.0 | The hardest, most creative job. With reasoning on, it refused far more often; off, 0% |
| Agent under test (default) | `nvidia/Nemotron-3_5-Lightning` | thinking off, temperature 0.3, `force_nonempty_content` | A cheap, fast, realistic production agent |
| Agent under test (compare) | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3-Ultra-550b-a55b` | same | Measure robustness against model size |

Handled in `sieve/nebius.py`: reasoning toggles via
`extra_body.chat_template_kwargs`, tool-call markup that leaks into `content` is
stripped, tool arguments are parsed back into objects, missing `usage` is
tolerated, transient errors are retried with backoff, and HTTP 402 (out of credit
mid-call) stops a run cleanly. Model ids live in the environment and swap without a
code change; an optional `MODEL_FALLBACK` lets the hosted demo degrade to
Lightning. It is off for benchmarks, so their numbers are always on the named
model.

What worked and what didn't: [FRICTION_LOG.md](FRICTION_LOG.md).

## Quickstart (under 5 minutes)

```bash
git clone https://github.com/Nataniel0212/turncoat && cd turncoat
pip install -r requirements-dev.txt
pytest -q                          # offline tests, no key, no network
python run.py --scenario bank      # offline dry-run of the full pipeline
```

Dry-run is the default: **no API key, no network, no cost.** Deterministic fakes
drive the whole pipeline. For live runs:

```bash
cp .env.example .env               # then set NEBIUS_API_KEY
python run.py --live --scenario inbox                      # one live campaign
python run.py --live --benchmark --trials 20 --budget 3    # the benchmark above
python compare_models.py                                   # the model comparison
```

Each run writes a console report, a self-contained `report.html` / `benchmark.html`
(light and dark), and a unique `runs/<timestamp>-<id>/` folder containing
`metrics.jsonl` (every call: model, tokens, reasoning tokens, latency, cost),
`attempts.jsonl` and `summary.json`.

## Web API (hosted demo backend)

The web UI supports scenario/model selection, streamed tool traces, per-call
metering, dark/light themes and labelled recordings for all nine combinations.
Replays work even when the live API is down. An upstream live failure offers a
recording automatically and explains that the meters now refer to the recording.
An invalid judge code is shown as an error; the code is never stored in the browser.

Static result tables are built from saved benchmark reports. After changing
results or recording another campaign, rebuild the page and offline catalog:

```bash
python scripts/record_replay.py --scenario bank --target lightning  # real API calls
python scripts/build_page.py
python scripts/build_page.py --check
```

```bash
uvicorn app:app --reload                                 # http://127.0.0.1:8000
SIEVE_FAKE_LLM=1 DEMO_ACCESS_CODE=dev uvicorn app:app    # offline, no spend
```

| Endpoint | |
|---|---|
| `GET /api/health` | models, whether live runs are open, today's demo spend |
| `GET /api/scenarios` | the agents, their tasks and tools |
| `POST /api/attack` `{scenario, target, code?}` | streams one live campaign as NDJSON: injections, each tool call, verdicts, per-call cost |

Token Factory has no spend cap, so the demo's guard (`sieve/guard.py`) **fails
closed**:

- a kill switch
- a budget stop between calls and an attempt limit per run (the last API call can
  cross the budget by its own cost)
- daily and lifetime caps, *reserved before* a run starts and settled to the real
  metered cost afterwards, so concurrent runs cannot overspend
- a per-IP hourly limit and a judge code

Without a shared Redis store (Upstash), public runs are off and only judge-code
runs are allowed, with **per-instance** counters that reset on process restart.
The current deployment uses this judge-only mode; its daily/lifetime counters
are not global guarantees across serverless instances. Configuration: `DEMO_*`
variables in [`.env.example`](.env.example).

## Bring your own agent

```bash
python run.py --scenario bank --agent examples/custom_agent.py:run_agent
python run.py --scenario bank --agent examples/custom_agent.py:confirmation_agent
```

Use your own Python orchestration and tool policy while keeping Nebius calls
metered and actions checked against synthetic state. Both examples run offline
by default; add `--live` for real calls. The second example requires confirmation
before sensitive actions. [Adapter guide and full example](docs/adapters.md).

This is a local Python integration, not a remote production-agent connector.
The published benchmark continues to describe the built-in agents.

## Tests and CI

`pytest -q` runs the offline test suite, covering:

- the Wilson interval
- the state-based verdicts
- tool-call sanitizing and metering
- unique run directories and the event-stream order
- the budget stop
- the spend guard: judge-only fail-closed, pool caps and settlement, IP limits,
  store outage, kill switch
- the streaming API
- custom agent orchestration, confirmation policy and invalid baselines
- exclusion of interrupted/all-refusal campaigns from benchmark rates
- replay provenance, complete event streams and metering consistency
- lifetime budget persistence across days
- the published tables recomputed exactly from the raw campaign data

CI runs the tests, a dry-run of every scenario, and a gitleaks secret scan. The
scan uses an extra rule for Nebius keys ([`.gitleaks.toml`](.gitleaks.toml)),
because the default rules do not recognise that format.

## Known limitations

- **Synthetic scenarios.** The published results use three agents with small
  tool sets. The local Python adapter can test your orchestration and policy,
  but still uses synthetic tools. Production-agent and AgentDojo connectors remain
  future work.
- **Technique and attempt number are confounded.** Techniques rotate in a fixed
  order, so the per-technique rates also reflect *when* a technique is tried.
- **Small n for the model comparison** (10 per cell). The intervals are wide; read
  the 0% vs 100% contrasts, not the 60% vs 90% ones.
- **The attacker is itself an LLM.** A stronger or less safety-tuned attacker would
  likely raise every number; these are lower bounds.
- **Stochastic.** The attacker runs at temperature 1.0. Rates, not single runs,
  are the result.

## Model licenses

Turncoat calls these models through the Token Factory API and does not redistribute
weights.

| Model | License |
|---|---|
| Nemotron 3 Ultra 550B, Nemotron 3.5 Lightning | OpenMDW-1.1 |
| Nemotron 3 Nano 30B | NVIDIA Nemotron Open Model License (Licensed by NVIDIA Corporation under the NVIDIA Nemotron Model License) |

## Scope of use

Turncoat attacks only agents you own or are authorized to test, using fully
synthetic fixtures. It is a defensive tool: find the hole before an attacker does.

## Roadmap

- Connect to remote agents and additional real-world evaluation environments.
- Run **AgentDojo** (MIT) suites for numbers comparable to the literature.
- Suggest a mitigation per finding and re-measure with it applied.

## License

MIT, see [LICENSE](LICENSE). Built from scratch during the hackathon (first commit
2026-10-14); no code, data or models from any prior project.
