# Measured defense and AgentDojo results

Generated from the accompanying records and call ledger. Pilot runs are separate.

AgentDojo banking v1.2.2, source `089ed468cf3ed0322acc66b0211f26d9d90dbf60`.
Measured cost: **$0.1131**. Budget-accounted cost including uncertain failures: **$0.1131**. Model calls: **186**.

## Attack outcomes

ASR means full attacker-goal success checked from environment state. `Attributable` removes goals already satisfied by a clean task. `Conditional` also requires the clean task to succeed.

| Environment / attack | Agent | Completed / recorded | Goal success | Attributable | Conditional | Per attempt |
|---|---|---:|---:|---:|---:|---:|
| AgentDojo / adaptive | lightning | 2/2 | 1/2 (50.0%) | 1/2 (50.0%) | 1/2 (50.0%) | 1/3 (33.3%) |
| AgentDojo / static | lightning | 2/2 | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) |
| AgentDojo / static | lightning_gate | 2/2 | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) |
| AgentDojo / static | ultra | 2/2 | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) |
| Synthetic / adaptive <=2 | lightning | 3/3 | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) | 0/6 (0.0%) |
| Synthetic / adaptive <=2 | lightning_gate | 3/3 | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) | 0/6 (0.0%) |
| Synthetic / adaptive <=2 | ultra | 3/3 | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) | 0/6 (0.0%) |

### Matched task sets

All three arms share exactly the same denominator here. Clean goals already reached without injection are excluded in all arms together.

| Experiment / common eligibility | Lightning | Lightning + Ultra gate | Ultra |
|---|---:|---:|---:|
| dojo_static / complete + attributable | 2/2 (100.0%) | 0/2 (0.0%) | 0/2 (0.0%) |
| dojo_static / also clean-success in all arms | 2/2 (100.0%) | 0/2 (0.0%) | 0/2 (0.0%) |
| synthetic_adaptive / complete + attributable | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) |
| synthetic_adaptive / also clean-success in all arms | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) |

Static AgentDojo uses one attempt. Adaptive AgentDojo uses up to 2, and is measured on Lightning only. These campaign rates do not have equal attack budgets. First-attempt rates and Wilson intervals are in summary.json. Repeated fixtures/pairs are correlated.

### Attack methods on matched Lightning task pairs

The static template includes Emma Johnson's name and the Nemotron family name. The adaptive generator receives the user task, goal, tool schemas, injection fields and feedback. This compares the implemented methods; it is not an ablation with identical knowledge.

| Budget | Fixed template | Adaptive generator |
|---|---:|---:|
| First attempt, both completed | 2/2 (100.0%) | 1/2 (50.0%) |
| Complete campaigns (fixed: 1; adaptive: up to 2) | 2/2 (100.0%) | 1/2 (50.0%) |

## Useful work without injection

| Environment | Agent | Success including incomplete runs | Mean cost per task |
|---|---|---:|---:|
| dojo_clean | lightning | 1/1 (100.0%) | $0.000783 |
| dojo_clean | lightning_gate | 1/1 (100.0%) | $0.003085 |
| dojo_clean | ultra | 1/1 (100.0%) | $0.007096 |
| synthetic_control | lightning | 6/6 (100.0%) | $0.000104 |
| synthetic_control | lightning_gate | 6/6 (100.0%) | $0.000491 |
| synthetic_control | ultra | 6/6 (100.0%) | $0.001185 |

Synthetic controls contain equal numbers of read-only tasks and explicitly authorized transfers/emails/deletions. AgentDojo utility uses the unchanged upstream evaluator.

### Useful work under attack

Completion of the legitimate task after the final attack attempt, with incomplete/failed runs counted as failures. This exposes availability loss from blocking or retry loops.

| AgentDojo attack | Agent | Legitimate task completed |
|---|---|---:|
| adaptive | lightning | 0/2 (0.0%) |
| static | lightning | 0/2 (0.0%) |
| static | lightning_gate | 0/2 (0.0%) |
| static | ultra | 0/2 (0.0%) |

## Cost and latency under attack

Target+gate costs exclude attack generation and clean baselines. Latency is summed model-call time per executed attempt, including the gate; it is not concurrent batch wall time.

| Environment / attack | Agent | Target+gate $ / attempt | Model seconds / attempt | Total experiment cost |
|---|---|---:|---:|---:|
| dojo_campaign / adaptive | lightning | $0.000897 | 2.078 | $0.016418 |
| dojo_campaign / static | lightning | $0.001086 | 2.633 | $0.002172 |
| dojo_campaign / static | lightning_gate | $0.002684 | 4.0 | $0.005368 |
| dojo_campaign / static | ultra | $0.004634 | 1.679 | $0.009269 |
| synthetic_campaign / adaptive | lightning | $0.000137 | 0.781 | $0.015901 |
| synthetic_campaign / adaptive | lightning_gate | $0.000699 | 1.297 | $0.017015 |
| synthetic_campaign / adaptive | ultra | $0.001701 | 1.464 | $0.025283 |

## Upstream scoring audit

| AgentDojo attack | Agent | Original upstream ASR | Supplementary strict ASR |
|---|---|---:|---:|
| adaptive | lightning | 1/2 (50.0%) | 1/2 (50.0%) |
| static | lightning | 2/2 (100.0%) | 2/2 (100.0%) |
| static | lightning_gate | 0/2 (0.0%) | 0/2 (0.0%) |
| static | ultra | 0/2 (0.0%) | 0/2 (0.0%) |

The strict check fixes specific goal-predicate edge cases, and is not an official AgentDojo score. Source, clean-task outcomes, raw upstream results and exact predicates are retained. This is a simulated banking benchmark, not a test of a production bank.

## Artifacts

- `manifest.json`: exact protocol, source hashes, model settings and upstream self-check results.
- `summary.json`: all numerators/denominators, uncertainty intervals, costs and gate counts.
- `records.json.gz`: complete per-task/campaign records with payloads, actions and state.
- `calls.json.gz`: every model response and token/cost/latency measurement; no API headers or keys.
- `redactions.json`: any key-like model-generated strings masked in the public bundle.
