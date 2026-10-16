# Feedback: Turncoat (Nebius x NVIDIA Global AI Hackathon)

**TL;DR: top 3 asks**
1. **Per-key spend caps and low-balance alerts on Token Factory.** Every public demo has to rebuild a budget guard because HTTP 402 is the only stop.
2. **Document how reasoning tokens are counted, and add a real thinking budget.** It is unclear whether `reasoning_tokens` sits inside `completion_tokens`, and Lightning with thinking on can spend the whole `max_tokens` on reasoning.
3. **Make Nemotron 3 Ultra's safety behaviour consistent across the reasoning toggle, and document it.** On the same sanctioned evaluation task, it refused 25–54% of attempts with thinking on (60 campaigns, even with reframed retries) and 0% with thinking off.

**Context.** Solo builder in Sweden (EU). Turncoat is an automated prompt-injection benchmark for tool-using agents, started Oct 14, 2026. Environment: Windows 11, Python 3.12, the stock `openai` Python SDK. Measured usage in the final model comparison alone: 2,193 calls, 2.0M input and 0.31M output tokens, $2.27. In total, about 330 benchmark campaigns cost about $7.9. Some observations below come from an earlier structured-output prototype I built and dropped during the same hackathon. They are marked *(earlier prototype)*.

---

## 1. Nebius Token Factory

**What I used it for:** all inference for three Nemotron models through the OpenAI-compatible chat completions API, with tool calling, the reasoning toggle (`extra_body.chat_template_kwargs.enable_thinking`), `force_nonempty_content`, and `response_format` json_schema *(earlier prototype)*.

**What worked well (please keep):**
- **Drop-in compatibility.** The stock `openai` SDK with `base_url` set was the whole integration. A three-model comparison only meant swapping a model ID in config.
- **Reasoning passthrough works.** `enable_thinking` is honoured per call, and `completion_tokens_details.reasoning_tokens` comes back populated (186 to 2,478 in my early runs).
- **`force_nonempty_content`** was accepted on every tool-calling call. `max_tokens=8192` on Lightning multi-step tool calls caused no truncation.
- **Usage is always returned.** My guard for a missing `usage` never fired.
- **No tool-call XML leaked into `content`** in my runs. I kept a sanitizer on anyway.
- **Stable at volume.** The 2,193-call comparison ran to completion with no fatal error. *(Earlier prototype:)* no 429s or 5xx with 8 parallel workers.
- **Price enables statistics.** 60 full campaigns cost $0.99, which turns red-teaming from anecdotes into confidence intervals.
- **Strict json_schema works on Nemotron** *(earlier prototype)*: a 115-value enum was enforced on Lightning and Ultra, with 0 invalid answers from Ultra over 175 calls.

**Onboarding (zero to hello world):** account, credits and key were done on Oct 13. The first smoke test that evening listed all four NVIDIA models, accepted the thinking toggle and JSON mode, and returned in 0.3–1.0 s per call for under $0.001. I did not time signup-to-first-response precisely, so I do not report an onboarding duration. The only real setup step after that was putting the key in an env variable.

**What needs work:**

### TF-1 · No spend cap: HTTP 402 is the only stop
- **Severity:** major for anyone hosting a public demo · **Frequency:** every deployment
- **Observed:** there is no per-key or per-project spend cap and no low-balance alert, so credits can run out in the middle of a call. I never hit a 402. I built a guard with a Redis option that reserves a budget before a run and settles to the metered cost afterwards. The current deployment uses per-instance counters and requires a judge code; public runs stay disabled until a shared store is configured. A budget stop runs between calls, so the last call can cross the threshold by its own cost.
- **Impact:** every hackathon project must stay live until Dec 15. A drained balance means a dead demo during judging.
- **Suggested fix:** per-key hard caps (daily and total), email or webhook alerts at user-set thresholds, and the remaining balance in a response header.

### TF-2 · Reasoning-token accounting is undocumented
- **Severity:** minor (cost correctness) · **Frequency:** every reasoning call
- **Observed:** one run reported 6,803 completion tokens, 2,773 of them reasoning. *(Earlier prototype:)* `reasoning_tokens=16384` equalled `max_tokens=16384`. Both suggest reasoning is counted inside `completion_tokens` and against `max_tokens`, but I found no docs that say so.
- **Impact:** cost meters either double-count or under-count. Turncoat computes cost from `completion_tokens` only, which is correct only if reasoning is included.
- **Suggested fix:** one sentence plus a usage example in the API reference: "`reasoning_tokens` is a subset of `completion_tokens`, billed at the output rate."

### TF-3 · Unfinished reasoning can end up in `content` *(earlier prototype)*
- **Steps:** Lightning, `enable_thinking: true`, `force_nonempty_content: true`, `max_tokens=16384`, a multi-step task.
- **Actual:** in 6 replies in one run, the whole budget went to reasoning: `reasoning_tokens=16384`, `reasoning_content=None`, and the unfinished chain of thought arrived in `content`, apparently through `force_nonempty_content`.
- **Expected:** `finish_reason="length"` and reasoning kept out of `content`.
- **Suggested fix:** never move unfinished reasoning into `content`, signal truncation clearly, and document how `force_nonempty_content` interacts with reasoning.

### TF-4 · JSON mode can degenerate and is billed in full *(earlier prototype)*
- **Actual:** Ultra in `json_object` mode once produced a 16,384-token, whitespace-padded, malformed reply that was billed in full. In `json_object` mode Ultra also drifted from the requested keys (22 of 33 replies in one run). With strict `json_schema` it did not.
- **Suggested fix:** a whitespace-loop guard in constrained decoding, and a "json_schema: strict" tag in the catalog. No Nemotron currently carries the "JSON mode" tag, even though strict schemas worked.

### TF-5 · Model status and IDs are hard to rely on
- **Observed:** on Oct 13 the public catalog listed `nvidia/nemotron-3-super-120b-a12b` with `status: "error"` and no reason or ETA, so I designed around Lightning and Ultra and never used Super. The four Nemotron IDs also use four spelling conventions (`NVIDIA-Nemotron-3-Nano-30B-A3B`, `nemotron-3-super-…`, `Nemotron-3-Ultra-…`, `Nemotron-3_5-Lightning`). I avoided typos only by copying them into env variables.
- **Suggested fix:** a per-model status with reason and ETA on status.nebius.com and in `/v1/models`, case-insensitive IDs with family aliases, and `Deprecation`/`Sunset` headers before a model is removed (models are not rerouted automatically).

### TF-6 · Serverless calls have no usage view
- **Observed:** latency and error dashboards are documented for dedicated endpoints only. I wrote my own per-call JSONL metering (model, tokens, reasoning tokens, latency, cost) to get p50/p95 per model.
- **Suggested fix:** a serverless usage page per key and model (calls, tokens, p50/p95, errors by code) with CSV export.

**Would I build on it again?** **Yes.** The OpenAI-compatible API and the price per token made a statistically meaningful benchmark possible on hackathon credits. A spend cap would make it safe to host publicly without custom guard code.

---

### TF-7 · Secret scanners do not recognise Token Factory keys

- **Step (2026-10-16):** ran gitleaks 8.30.1 with its default rules over the repo before deploying the public demo.
- **Observed:** it flagged my *fake* fixture token but **not** the real Token Factory key in the git-ignored `.env` (a ~230-character dotted token with no distinctive prefix).
- **Impact:** default secret scanning (gitleaks, and likely GitHub push protection) would let a Token Factory key be pushed without any warning. With no spend cap, a leaked key is directly billable.
- **Workaround:** a custom gitleaks rule, plus a direct search of the git history for the key value.
- **Suggestion:** give keys a distinctive prefix (for example `ntf_`), register the format with GitHub secret scanning and gitleaks, and pair it with per-key spend caps (TF-1).

## 2. NVIDIA Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`)

**What I used it for:** (a) the attacker, an adaptive payload generator in a sanctioned, fully synthetic evaluation (thinking off, temperature 1.0); (b) an agent under test in the model comparison.

**What worked well:**
- **As a target it held: 0 of 30 campaigns** across email, bank and documents. It was not passive. It called its tools, did the task, and explicitly flagged the injected message as suspicious. That is a strong, publishable robustness result for the flagship.
- **Latency:** as attacker, p50 1.43 s and p95 3.67 s over 646 calls; as target, p50 0.56 s and p95 0.98 s over 660 calls.
- **Reasoning toggle and `medium_effort` behaved as documented** *(earlier prototype)*.

**What needs work:**

### NM-1 · Refusal behaviour depends on the reasoning toggle
- **Severity:** major for evaluation and safety teams · **Frequency:** systematic
- **Observed:** on the same sanctioned, synthetic red-team generation task (bank scenario), Ultra refused **25–54%** of attempts per scenario with `enable_thinking: true` (60 campaigns, after two reframed retries per attempt) and **0%** with it off. Before the fix, refusals in early benchmark attempts ran at 72–86%, and they silently made the agents under test look safe. Over 60 benchmark and 90 comparison campaigns with thinking off, my detector found no refusals.
- **Impact:** two problems. (1) Evaluation results depend on a toggle most users don't think of as safety-relevant. My first benchmark rated two agents as safe when they had barely been tested. (2) From a safety point of view, the policy is not stable across modes.
- **Suggested fix:** make refusal behaviour consistent between thinking on and off. Document how reasoning mode affects safety behaviour in the model card. Publish guidance for authorized safety-evaluation use, so that evaluation results are reproducible.

### NM-2 · Tool and format discipline in agents *(earlier prototype)*
- **Observed:** Ultra called tools that were not in the provided list (`read_bytes` 4 times, `read_file` once) and often left a required free-text field empty while spending thousands of reasoning tokens.
- **Suggested fix:** guidance on whether to send `reasoning_content` back between turns in multi-step agents, plus an example agent loop in the model card.

**Would I build with it again?** **Yes**, both as the strong model in a pipeline and as the safe default for agents with dangerous tools. Its 0/30 is the most useful result in my project.

---

## 3. NVIDIA Nemotron 3.5 Lightning (`nvidia/Nemotron-3_5-Lightning`)

**What I used it for:** the default agent under test, a tool-calling assistant (thinking off, temperature 0.3, `max_tokens` 8192, `force_nonempty_content`).

**What worked well:**
- **Fastest in my runs:** p50 0.34 s, p95 0.76 s, max 0.96 s over 445 target calls.
- **Cheap:** all 445 target calls together cost $0.025. Tool calls were well-formed and parsed every time.

**What needs work:**

### NM-3 · High injection susceptibility in tool-using roles
- **Observed:** with a system prompt that tells it to treat tool output as data, Lightning was fully compromised in 100% of bank campaigns (20/20, CI 84–100%) and 95% of email campaigns (19/20, CI 76–99%). On the same tasks, Ultra was compromised in 0%.
- **Impact:** Lightning is Nebius's suggested default for agents, so many hackathon agents will inherit this.
- **Suggested fix:** publish prompt-injection robustness numbers (for example AgentDojo) in the model card, recommend a confirmation step or a stronger model for high-risk tool calls, and consider training the model to respect a dedicated marker for untrusted tool output.

### NM-4 · No usable thinking budget *(earlier prototype)*
- **Observed:** with thinking on and ~5k-token prompts, Lightning ran to the token limit on 15 of 23 tasks. 6 tasks still failed after 45k tokens of retries. `reasoning_effort="low"` and `medium_effort` still reached 16,384 tokens on a hard case, while `low_effort` (undocumented for Lightning) stopped at 9.7k. With thinking on in `json_object` mode, it once wrapped its answer in `{"": {...}}`.
- **Suggested fix:** a documented thinking-budget parameter for Lightning on Token Factory, and documentation of which effort flags it accepts.

**Would I build with it again?** **Yes**, for speed and cost, but not unguarded on tools that move money or data.

---

## 4. NVIDIA Nemotron 3 Nano 30B (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`)

**What I used it for:** an agent under test in the model comparison.

**What worked well:** tool calling worked with the same code and prompts. It was cheap: all 442 target calls together cost $0.021.

**What needs work:**
- **Slower than Lightning at the same price.** p50 0.73 s vs 0.34 s, p95 2.40 s vs 0.76 s, max 7.39 s. Its injection results (email 60%, bank 100%, docs 0%) do not differ significantly from Lightning at n = 10. The catalog should say when to choose Nano over Lightning.
- **Catalog metadata:** the release date is listed as 2025-02-01; the model card says 2025-12-15.

**Would I build with it again?** **Probably not for agents.** At the same price, Lightning was faster in my workload.

## 5. NVIDIA Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`)

**Not used.** On 2026-10-13, the day I planned the build, the public catalog showed `status: "error"` for Super with no explanation, so I chose not to depend on it. A visible reason and ETA (TF-5) would have let me plan around it.

## 6. Nebius AI Cloud (Serverless Jobs / Endpoints)

**Not used.** The demo only needs inference, and the hackathon credits cover Token Factory only. AI Cloud has a separate console and separate billing, so a second setup was not worth it for this project. Letting hackathon credits cover a small Serverless Endpoint would have made me try it for hosting the demo backend.

---

## Appendix: measured data (model comparison, 90 campaigns, 2,193 calls, thinking off throughout)

| Model | Role | Calls | p50 | p95 | Max | Input tokens | Output tokens | Cost |
|---|---|---|---|---|---|---|---|---|
| Nemotron 3 Ultra | attacker | 646 | 1.43 s | 3.67 s | 10.29 s | 1,019,164 | 236,069 | $1.727 |
| Nemotron 3 Ultra | target | 660 | 0.56 s | 0.98 s | 4.65 s | 406,280 | 29,367 | $0.494 |
| Nemotron 3.5 Lightning | target | 445 | 0.34 s | 0.76 s | 0.96 s | 317,755 | 23,674 | $0.025 |
| Nemotron 3 Nano 30B | target | 442 | 0.73 s | 2.40 s | 7.39 s | 257,219 | 23,410 | $0.021 |

Cost per campaign by target model: Lightning $0.013, Nano $0.019, Ultra $0.043. Source: `runs/*/metrics.jsonl`; cost is the real token counts times the published rate.
