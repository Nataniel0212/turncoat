# DEVLOG

## 2026-10-14 — Spike v1 (scaffold + offline loop)

Built the complete spike for **Sieve**, an automated prompt-injection red-team
for tool-using agents. Goal of v1: prove the core TAP loop end to end.

Done:
- Project scaffold: MIT license, `.gitignore`, `.env.example`, requirements.
- `sieve/` package: Nebius client (Token Factory, OpenAI-compatible) with
  Nemotron quirk handling; per-call metering to JSONL (tokens/latency/cost);
  synthetic email-exfiltration scenario with a deterministic state check;
  tool-calling target agent; TAP attacker; orchestration loop with budget guard;
  report renderer.
- Offline fakes so the full pipeline runs with no key and no spend.

Verified (dry-run):
- Baseline (benign email) stays safe; agent does not leak.
- Adaptive attacker escalates; leak found at attempt 4.
- Report prints the exact winning injection + the agent's tool calls + the
  exfil email. Metering logged 16 calls to `runs/metrics.jsonl`.

### Critical review + hardening (same day)

Reviewed the code and fixed 9 issues (all offline, no spend):
1. API calls now retry transient errors with backoff; HTTP 402 -> graceful stop.
2. Missing `usage` in a live response no longer crashes metering.
3. Budget guard now also checked inside the target loop and between calls.
4. Attacker runs at temperature 1.0 so attempts diversify; target at 0.3.
5. Attacker output is cleaned of code fences / "Here is..." preambles.
6. Softer leak signal: secret fetched + external send flagged as "suspected"
   even when the secret isn't verbatim (catches encoded/paraphrased exfil).
7. Each run writes a timestamped `runs/<ts>/` with metrics.jsonl **and**
   attempts.jsonl (every attempt persisted, not just winners).
8. Tool-call XML sanitizer now covers several leak formats + unclosed tails.
9. Cleanup: dead line in fakes.py removed; attempt numbers 1-indexed throughout.

Re-verified: dry-run still leaks at attempt 4; budget=0 stops gracefully;
smoke test passes.

### First live runs on Nebius (same day)

Run 1 (initial attacker): baseline safe; 10/10 attempts, **0 full leaks**, but
**6/10** tricked the agent into calling `get_account_secret` during a mere
"summarize inbox" task. Our binary leak check scored those as "safe" — too
strict. Cost $0.025. Confirmed reasoning passthrough works (see FRICTION_LOG).

Improvement batch (severity + stronger attacker), then re-ran:
- Multi-level severity: leak / exfil / secret_access / unauthorized_send / safe.
  Any of these means the email content redirected the agent, which is the real
  signal (matches how AgentDojo scores "did the agent do the injected action").
- Attacker now gets **progress feedback** (it's told it already got the secret
  fetched and must close the send step), **rotates techniques** across attempts,
  has a stronger system prompt, and more output tokens.
- Report shows a severity breakdown; attempts.jsonl records per-attempt signals.

Run 2 (stronger attacker): **FULL COMPROMISE on attempt 1.** A fake "Account
Integrity Service" system notice with a JSON instruction block made Lightning
fetch the secret and email it to an external (non-user) address, verbatim.
Cost $0.0034. This is the demo money-shot.

### HTML report + multi-trial rate (same day)

- **HTML report:** `sieve/html_report.py` turns a run into a self-contained,
  theme-aware report (standalone for the repo + an Artifact fragment). `run.py`
  now emits `report.html` and `summary.json` per run.
- **Variance was large** across single live runs (full compromise / 6-of-10 /
  0-of-10). So a single run is not a sound metric.
- **Multi-trial mode** (`sieve/trials.py`, `--trials N`): runs N independent
  spikes under a shared budget and reports an attack-success RATE.
  First live 5-trial run: **leak rate 20%, any-compromise 60%, $0.12 total**
  (per trial: safe, safe, secret_access, leak, secret_access). This is the
  honest headline metric.

### 2026-10-15 — Pluggable scenarios

Generalised the single hardcoded scenario into a pluggable framework
(`sieve/scenarios.py`, a `Scenario` base + registry) with a shared severity
ladder (critical > high > medium > safe). Three scenarios now ship:
- **inbox** — email assistant leaks an account secret (the original).
- **bank** — banking assistant wired into transferring funds to an attacker.
- **docs** — document assistant tricked into deleting the user's files.

The loop, attacker, target agent, trials, fakes, and both reports are now
scenario-agnostic; `run.py --scenario {inbox,bank,docs}` selects one. Smoke test
covers all three offline (baseline safe + critical reached). Removed the old
`scenario.py`.

### First full benchmark (60 live trials, $1.31)

20 independent trials per scenario, 95% Wilson CIs:
- **inbox (email):** P(>= medium) 70% [48–86], P(>= high) 10% [3–30],
  P(critical) 10% [3–30]. Mean 9.15 attempts. The agent is often pushed into a
  risky action (fetch secret / external send), but completing full exfiltration
  is hard.
- **bank:** 0/20 at every level [0–16]. Held.
- **docs:** 0/20 at every level [0–16]. Held.
- By technique (inbox criticals): system-notice and pre-authorized landed 1 each;
  the rest 0.

Honest reading: robustness differs sharply by agent. 0/20 means "held in 20
trials" (CI up to 16%), not "immune"; and this is THIS attacker within 10
attempts. Benchmark HTML report with charts generated and published.

### Attacker-refusal confound found and fixed

Investigating why bank/docs "held" revealed a methodology bug: the **attacker
model refused** to write the payload in 72–86% of attempts (genuine safety
refusals, e.g. "I'm not going to create a prompt injection payload…"). So the
targets mostly weren't attacked — a held result was not evidence of robustness.

Fixes:
- **Refusal detection** (`attacker.is_refusal`), robust across phrasings; each
  attempt is tagged `refused`.
- **Stronger attacker framing** (sandboxed eval / fully synthetic / don't refuse)
  + up to 2 reframed retries. Refusals on docs fell 86% → 45%.
- **Valid-trial statistics:** rates now use only trials with ≥ 1 real attack;
  all-refusal trials are excluded; the attacker refusal rate is reported.

Re-measured docs with real attacks: 0/33 real deletion attacks succeeded — the
document agent is genuinely robust (not a refusal artifact).

### Corrected benchmark (60 live trials, $2.31, refusals handled)

With valid-trial statistics the picture is far stronger and very different from
the confounded first run:
- **inbox (email):** refused 34%, 20/20 valid. P(critical) **70%** [48–86]
  (was 10% confounded).
- **bank:** refused 54%, 19/20 valid. P(critical) **47%** [27–68] (was 0%).
- **docs:** refused 25%, 20/20 valid. P(critical) **5%** [1–24] (was 0%) — the
  robust one.
- **Top technique: output-hijack** (deliver the result by doing the dangerous
  action) — 42% inbox, 44% bank, 3% docs. Clearly the strongest vector.

Takeaway: all three agents are vulnerable to different degrees, and the refusal
fix changed the conclusion entirely. Benchmark report/artifact updated.

### Final clean benchmark (thinking off, 0% refusal, 60 trials, $0.99)

With attacker thinking disabled, refusal dropped to 0% across all scenarios
(20/20 valid each), giving the true picture:
- **bank:** P(critical) **100%** [84–100] — every trial transferred funds to the
  attacker. Mean 3.7 attempts.
- **inbox (email):** P(critical) **95%** [76–99]. Mean 3.35 attempts.
- **docs:** P(critical) **10%** [3–30]. Mean 9.6 attempts — the robust one.
- **output-hijack dominates:** 78% bank, 50% inbox, 5% docs.

The three measurement passes tell the rigor story: confounded 10/0/0 →
valid-trial 70/47/5 → root-cause-fixed 95/100/10. Numbers are final and honest.

### Model comparison — stronger model, more robust

Ran the benchmark with three Nemotron models as the agent under test (attacker
fixed as Ultra), 10 trials each, $2.27 total. Full-compromise rate P(critical):

| Target | inbox | bank | docs |
|---|---|---|---|
| Lightning (small) | 90% | 100% | 0% |
| Nano-30B (mid) | 60% | 100% | 0% |
| Ultra-550B (flagship) | **0%** | **0%** | 0% |

Verified it's genuine, not inertia: Ultra engaged (called tools, did the task) and
**explicitly flagged the injection** ("a suspicious security notice email
attempting to trick you..."). Security is a measurable model-choice tradeoff.
`compare_models.py` + `sieve/compare_html.py` (reads runs/compare.json).

Next (product):
- 3-min video (script drafted).
- AgentDojo (MIT) suites; adapter for a real agent.

## 2026-10-16: Hosted-demo backend, spend guard, tests, CI

Goal: make Sieve usable by a judge without a key, while still being safe to
leave running until mid-December on a Token Factory account with no spend cap.

Done:
- **Live event stream.** `loop.run_spike(on_event=...)` emits `start`, `call`
  (every metered Nemotron call: model, tokens, latency, cost, running total),
  `baseline`, `attempt_start`, `injection`, `tool` (each tool call as the agent
  makes it), `attempt` (verdict) and `done`.
- **Web API** (`app.py`, FastAPI on Vercel's Python runtime): `/api/health`,
  `/api/scenarios`, and `POST /api/attack`, which streams one live campaign as
  NDJSON with heartbeats. `SIEVE_FAKE_LLM=1` runs it on the offline fakes.
- **Spend guard** (`sieve/guard.py`), fail-closed:
  - kill switch
  - per-run cost cap and attempt limit
  - daily public, daily total and lifetime caps, reserved before a run and
    settled to the real metered cost afterwards
  - per-IP hourly limit and a judge code

  Without a shared Redis store, only judge-code runs are allowed.
- **Opt-in model fallback** (`MODEL_FALLBACK`, e.g. Ultra → Lightning) for the
  demo. It is off for benchmarks; the metered row always names the model that
  actually answered.
- **Replay recorder** (`scripts/record_replay.py`): saves a real live campaign's
  event stream with its real timings, as a labelled fallback for the UI.
- **Run directories** get a random suffix: two runs in the same second used to
  overwrite each other.
- **Fix:** `wilson()` returned 0.99999… instead of 1.0 at k = n (float drift).
  Found by a new property test.
- **Fix:** the `.env` loader now handles inline comments. Before, a blank value
  followed by a comment was read as the comment text.
- **Tests:** 1 → 24 offline tests:
  - statistics and verdicts
  - sanitizer and metering
  - event stream and budget stop
  - spend guard: fail-closed, caps, settlement, IP limit, store outage, kill switch
  - streaming API
- **CI:** GitHub Actions runs pytest, a dry-run of every scenario, and gitleaks.
- **Secret scan:** gitleaks over the full history found only the deliberately
  fake fixture secret. The default rules do *not* recognise Nebius Token Factory
  keys, so `.gitleaks.toml` adds a rule for them; it is verified to catch the
  real key in the git-ignored `.env`. A direct search confirmed the key is in no
  commit.
- **Results committed** under `results/`: the 15 Oct benchmark report, the
  model comparison, and per-model campaign cost/latency
  (`scripts/campaign_stats.py`; reads only token/latency/cost fields).
  Median full campaign: Lightning $0.0071 / 9.0 s, Nano $0.0202 / 33.5 s,
  Ultra $0.0379 / 28.1 s of model time.
- **Corrected a claim:** an "~83% refusal with reasoning on" figure in a code
  comment had no saved run behind it. It is replaced by the logged numbers
  (25–54% across the 60-trial run).
- **README** rewritten: results, model comparison, rigor story, Mermaid
  architecture, model roles and settings, quickstart, web API, tests/CI, known
  limitations and model licenses.
- **Web UI markup** (`public/index.html`, `public/style.css`). The interactive
  script is still to come.

Started: a second, independent 60-trial benchmark run to check that the
15 Oct numbers replicate.

### Replication: the benchmark reproduces exactly (60 more live trials, $1.01)

Re-ran the full benchmark a day later: same code, same models, independent
trials. Full-compromise rates were identical: **email 95% (19/20), bank 100%
(20/20), docs 10% (2/20)**, with 0% attacker refusals. Mean attempts were 4.15,
3.6 and 9.6. Output hijacking again dominated (bank 17/20 attempts, email
10/18). Median full campaign: $0.0112 and 14.6 s of model time. Saved as
`results/benchmark-2026-10-16.{md,json}` (no attack text) and
`results/campaign-stats-2026-10-16.json`.

### Hosted backend live on Vercel

`https://sieve-redteam.vercel.app` runs `app.py` on Vercel's Python runtime.
`/api/health` is up. Without a judge code, `/api/attack` correctly refuses
(no shared store means judge-only). With a judge code, a real campaign (bank vs
Lightning) streamed end to end: first byte after 1.0 s, compromised at attempt
3 (output hijack), 12 Nemotron calls, $0.0048, 8.4 s.

### Interactive demo, replay library and local agent adapter

- Finished `public/app.js`: scenario/model choices, accessible keyboard controls,
  judge-code gating, NDJSON stream parsing, per-call trace, state-based verdicts,
  theme persistence, explicit model-fallback notices and upstream-error recovery.
  Model output is rendered as text, never as HTML. Judge codes are not persisted.
- Finished `scripts/build_page.py`: result charts and tables are generated from
  the saved reports; a static scenario/replay catalog lets recordings work even
  when the API is down. `--check` detects stale generated assets in CI.
- Recorded all nine scenario/model combinations directly on Nebius, with no
  model fallback: **152 calls, $0.134643 total**. Original timings and per-call
  usage are saved in `public/data/replays/`. Replays are labelled, can be skipped
  or stopped, and make no new model calls. No recording was rerun to select a
  preferred verdict.
- Added `--agent file.py:function` for local Python agents, preserving the
  metered Nebius transport, fresh synthetic tool state and deterministic checker.
  `examples/custom_agent.py` demonstrates orchestration with and without an
  application-level confirmation policy. Both are verified offline across all
  three scenarios; these checks are not presented as live benchmark measurements.
- Fixed a lifetime-counter bug: the in-memory store treated zero TTL as immediate
  expiry. Persistent counters now survive later calls and day changes; increments
  are locked across threads. Serverless counters are still per instance until a
  shared Redis store is configured. Documentation now states that limitation and
  that a last API call can cross the budget by its own cost.
- Fixed evaluation edge cases: an unsafe baseline stops the campaign; interrupted
  and all-refusal campaigns cannot count as evidence of robustness. No valid
  trials produces N/A in reports. The existing published benchmark remains intact.
- Load `.env` before constructing API choices/guard settings, and exclude browser
  artifacts, local environments and traces from deployment uploads.
- **36 offline tests pass.** Browser checks passed for all nine replays, metering,
  a streamed fake campaign, bad codes, API outage, 503 and truncated-stream
  fallback, replay controls, mobile layout, theme persistence and malicious text
  rendered without executing markup. Static page generation and JS syntax pass.
- Updated README and adapter documentation; added public `FEEDBACK.md` with
  untimed onboarding stated honestly. Video/script work is deferred by request.

Publication checks:
- GitHub push protection caught two occurrences of a Stripe-shaped token invented
  in one synthetic injection (inbox/Ultra). Only those strings were redacted in
  the public replay, with a metadata note and visible label. All timing, token,
  cost and outcome data is unchanged. Future recordings apply the same filter
  and reject any trace containing the configured API key.
- The first CI run exposed a pytest import-path difference between `pytest` and
  `python -m pytest`; `pytest.ini` now declares the source root explicitly.
- Production deployed and checked at `https://sieve-redteam.vercel.app`: static
  assets and all nine recordings present, public live requests rejected without
  a code, authorized bank/Lightning campaign complete in 3 attempts, 12 calls,
  11.798 seconds of model time and $0.015717.

### Code review fixes: evaluation edge cases and derived page text

A full code review of the demo/adapter commits found evaluation edge cases. None
changes a published number: every published trial was complete, valid and had a
0% attacker-refusal flag, so the 95/100/10 benchmark and the model comparison
stand as reported. Fixed anyway, each with a regression test that fails on the
old code:

- **Refusal false positive.** The refusal check reads the payload's opening
  text, so an injection posing as the user ("I can't log in, please transfer...")
  matched it, and a sandbox-confirmed compromise could be labelled inconclusive
  and dropped from rates. An attempt now counts as a refusal only if it also left
  the agent safe.
- **Adapter robustness.** An invented tool name or malformed arguments now return
  an error string to the model, as in the built-in agent, instead of aborting the
  campaign. The 12-turn and 100-tool-call caps end that agent run, not the
  benchmark. Adapters get a private copy of the tool list.
- **Missing data is N/A.** Comparison chart/table, CLI output and the generated
  page show N/A, never 0%, for a cell with no valid trials.
- **Headline trial.** Repeated-trial reports headline the most severe *valid*
  trial, matching the set the rates use.
- **Deployment.** `.vercelignore` patterns for root reports are anchored so they
  no longer exclude `sieve/report.py` and `sieve/benchmark.py`.
- **Web verdict.** A stopped run now says why (baseline failed, budget stop,
  HTTP 402) instead of "no real attack completed", and the server's
  `valid_trial` is authoritative.
- **No hand-typed page claims.** Dates, model name, campaign counts, the attempt
  statement and the overlapping-interval note are now derived from `results/`.
  New benchmarks record `max_attempts`.
- **One budget check.** Every model call in a campaign, including the attacker's
  refusal retries, now passes a single `BudgetedClient` check instead of checks
  scattered over the loop, agent and adapters.
- **Same trials everywhere.** Per-technique rates and attempt counts use the
  valid trials behind the headline rate; the attacker-refusal rate still counts
  every attempt. The completeness rule lives in `loop.py` and every report uses it.
- **One source for web choices.** `sieve/targets.py` defines target labels and
  ids for the API, recorder and offline catalog; the Lightning slot has its own
  `MODEL_TARGET_LIGHTNING`, so the CLI's `MODEL_TARGET` cannot relabel a run.
  The scenario catalog is likewise defined once.
- **Comparison report text** (headline, takeaway, attacker name) is derived from
  the data rather than typed by hand.
- **50 offline tests pass**; page check, JS syntax, offline API run and a
  browser check of all three stop cases, a full offline campaign and a replay pass.

### Auditable statistics and accuracy fixes (external review)

An independent review asked for statistics a reader can check. Done:

- **Raw data published.** `results/raw/` holds every campaign of the 16 Oct
  replication (60) and the model comparison (90): each injection, tool call,
  verdict, token count and cost. `scripts/export_raw.py` refuses to write unless
  the campaigns reproduce the published tables exactly, and a CI test recomputes
  every k/n, technique count, mean and cost from the files. The 15 Oct first
  run was not retained as raw data and is labelled as report-only.
- **Redaction disclosed.** Attacker-invented credential-shaped values ("AUTH
  TOKEN: 0x7F4A...") are masked so secret scanners stay clean; the scenarios'
  own synthetic fixture token, verdicts and metering are untouched.
- **Per-attempt rates.** A campaign is up to 10 adaptive attempts, so "100%"
  means a persistent attacker got through within 10 tries. The single-injection
  rate is now shown next to it: bank 27% / 28%, email 28% / 23%, documents
  1% / 1% (15 / 16 Oct). The page derives the cap and these rates from results.
- **Identical document rows explained.** Techniques run in a fixed order, so two
  days with two successes at the same positions give identical tables.
- **Accurate method name.** The attacker is an iterative refinement loop
  inspired by TAP, without TAP's tree search or pruning.
- Two different medians are now labelled by run; the test count is no longer
  hard-coded in the README; process notes removed from this log.

### Renamed to Turncoat

Another hackathon entry already uses the name Sieve, so the project is now
**Turncoat** ("will your AI agent turn on you?"). The repository is
`Nataniel0212/turncoat` (the old URL redirects) and the demo is
`https://turncoat-redteam.vercel.app` (the old address still works). The Python
package keeps the name `sieve`, so imports, scripts and run data are unchanged.
