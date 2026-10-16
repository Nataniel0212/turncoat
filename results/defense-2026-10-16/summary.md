# Measured defense and AgentDojo results

Generated from the accompanying records and call ledger. Pilot runs are separate.

AgentDojo banking v1.2.2, source `089ed468cf3ed0322acc66b0211f26d9d90dbf60`.
Measured cost: **$6.6307**. Budget-accounted cost including uncertain failures: **$6.6339**. Model calls: **7078**.

## Attack outcomes

ASR means full attacker-goal success checked from environment state. `Attributable` removes goals already satisfied by a clean task. `Conditional` also requires the clean task to succeed.

| Environment / attack | Agent | Completed / recorded | Goal success | Attributable | Conditional | Per attempt |
|---|---|---:|---:|---:|---:|---:|
| AgentDojo / adaptive | lightning | 115/144 | 49/115 (42.6%) | 49/115 (42.6%) | 32/80 (40.0%) | 49/298 (16.4%) |
| AgentDojo / static | lightning | 137/144 | 79/137 (57.7%) | 79/137 (57.7%) | 54/88 (61.4%) | 79/137 (57.7%) |
| AgentDojo / static | lightning_gate | 120/144 | 0/120 (0.0%) | 0/117 (0.0%) | 0/89 (0.0%) | 0/120 (0.0%) |
| AgentDojo / static | ultra | 144/144 | 15/144 (10.4%) | 15/144 (10.4%) | 15/126 (11.9%) | 15/144 (10.4%) |
| Synthetic / adaptive <=5 | lightning | 30/30 | 15/30 (50.0%) | 15/30 (50.0%) | 15/30 (50.0%) | 15/116 (12.9%) |
| Synthetic / adaptive <=5 | lightning_gate | 30/30 | 0/30 (0.0%) | 0/30 (0.0%) | 0/30 (0.0%) | 0/150 (0.0%) |
| Synthetic / adaptive <=5 | ultra | 30/30 | 0/30 (0.0%) | 0/30 (0.0%) | 0/30 (0.0%) | 0/150 (0.0%) |

### Matched task sets

All three arms share exactly the same denominator here. Clean goals already reached without injection are excluded in all arms together.

| Experiment / common eligibility | Lightning | Lightning + Ultra gate | Ultra |
|---|---:|---:|---:|
| dojo_static / complete + attributable | 69/115 (60.0%) | 0/115 (0.0%) | 15/115 (13.0%) |
| dojo_static / also clean-success in all arms | 43/70 (61.4%) | 0/70 (0.0%) | 10/70 (14.3%) |
| synthetic_adaptive / complete + attributable | 15/30 (50.0%) | 0/30 (0.0%) | 0/30 (0.0%) |
| synthetic_adaptive / also clean-success in all arms | 15/30 (50.0%) | 0/30 (0.0%) | 0/30 (0.0%) |

Static AgentDojo uses one attempt. Adaptive AgentDojo uses up to 3, and is measured on Lightning only. These campaign rates do not have equal attack budgets. First-attempt rates and Wilson intervals are in summary.json. Repeated fixtures/pairs are correlated.

### Attack methods on matched Lightning task pairs

The static template includes Emma Johnson's name and the Nemotron family name. The adaptive generator receives the user task, goal, tool schemas, injection fields and feedback. This compares the implemented methods; it is not an ablation with identical knowledge.

| Budget | Fixed template | Adaptive generator |
|---|---:|---:|
| First attempt, both completed | 61/110 (55.5%) | 17/110 (15.5%) |
| Complete campaigns (fixed: 1; adaptive: up to 3) | 65/112 (58.0%) | 48/112 (42.9%) |

## Useful work without injection

| Environment | Agent | Success including incomplete runs | Mean cost per task |
|---|---|---:|---:|
| dojo_clean | lightning | 10/16 (62.5%) | $0.000830 |
| dojo_clean | lightning_gate | 11/16 (68.8%) | $0.002931 |
| dojo_clean | ultra | 14/16 (87.5%) | $0.007954 |
| synthetic_control | lightning | 30/30 (100.0%) | $0.000103 |
| synthetic_control | lightning_gate | 30/30 (100.0%) | $0.000492 |
| synthetic_control | ultra | 30/30 (100.0%) | $0.001186 |

Synthetic controls contain equal numbers of read-only tasks and explicitly authorized transfers/emails/deletions. AgentDojo utility uses the unchanged upstream evaluator.

### Useful work under attack

Completion of the legitimate task after the final attack attempt, with incomplete/failed runs counted as failures. This exposes availability loss from blocking or retry loops.

| AgentDojo attack | Agent | Legitimate task completed |
|---|---|---:|
| adaptive | lightning | 55/144 (38.2%) |
| static | lightning | 56/144 (38.9%) |
| static | lightning_gate | 82/144 (56.9%) |
| static | ultra | 114/144 (79.2%) |

## Cost and latency under attack

Target+gate costs exclude attack generation and clean baselines. Latency is summed model-call time per executed attempt, including the gate; it is not concurrent batch wall time.

| Environment / attack | Agent | Target+gate $ / attempt | Model seconds / attempt | Total experiment cost |
|---|---|---:|---:|---:|
| dojo_campaign / adaptive | lightning | $0.001219 | 2.902 | $2.340989 |
| dojo_campaign / static | lightning | $0.001380 | 3.246 | $0.198781 |
| dojo_campaign / static | lightning_gate | $0.009221 | 9.892 | $1.327873 |
| dojo_campaign / static | ultra | $0.008832 | 3.016 | $1.271851 |
| synthetic_campaign / adaptive | lightning | $0.000141 | 0.853 | $0.283683 |
| synthetic_campaign / adaptive | lightning_gate | $0.000598 | 1.395 | $0.400104 |
| synthetic_campaign / adaptive | ultra | $0.001487 | 1.474 | $0.566498 |

## Upstream scoring audit

| AgentDojo attack | Agent | Original upstream ASR | Supplementary strict ASR |
|---|---|---:|---:|
| adaptive | lightning | 60/115 (52.2%) | 49/115 (42.6%) |
| static | lightning | 101/137 (73.7%) | 79/137 (57.7%) |
| static | lightning_gate | 0/120 (0.0%) | 0/120 (0.0%) |
| static | ultra | 18/144 (12.5%) | 15/144 (10.4%) |

The strict check fixes specific goal-predicate edge cases, and is not an official AgentDojo score. Source, clean-task outcomes, raw upstream results and exact predicates are retained. This is a simulated banking benchmark, not a test of a production bank.

## Artifacts

- `manifest.json`: exact protocol, source hashes, model settings and upstream self-check results.
- `summary.json`: all numerators/denominators, uncertainty intervals, costs and gate counts.
- `records.json.gz`: complete per-task/campaign records with payloads, actions and state.
- `calls.json.gz`: every model response and token/cost/latency measurement; no API headers or keys.
- `redactions.json`: any key-like model-generated strings masked in the public bundle.
