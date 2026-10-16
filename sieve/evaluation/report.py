"""Derive all tables from per-task records and export an auditable data bundle."""
from __future__ import annotations

import gzip
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from .common import ARMS, digest, rate, write_json


def summarize(records, calls):
    groups = defaultdict(list)
    for row in records:
        key = (row.get("kind"), row.get("attack_type", ""), row.get("arm"))
        groups[key].append(row)
    output = []
    for (kind, attack, arm), rows in sorted(groups.items()):
        if not kind:
            continue
        complete = [r for r in rows if r.get("complete")]
        entry = {"kind": kind, "attack_type": attack, "arm": arm,
                 "records": len(rows), "completed": len(complete)}
        ids = {r["job_id"] for r in rows}
        metrics = [c for c in calls if c["job_id"] in ids]
        entry["cost_usd"] = round(sum(c.get("cost_usd") or 0 for c in metrics), 6)
        entry["accounted_usd"] = round(sum(c["accounted_usd"] for c in metrics), 6)
        entry["cost_by_phase"] = {phase: round(sum(c.get("cost_usd") or 0 for c in metrics if c["phase"] == phase), 6)
                                  for phase in ("attacker", "target", "baseline", "clean", "gate")}
        target_calls = [c for c in metrics if c["phase"] in ("target", "gate")]
        if kind.endswith("campaign"):
            valid = [r for r in rows if r.get("valid")]
            attributable = [r for r in valid if r.get("attributable")] if kind == "dojo_campaign" else valid
            conditional = [r for r in valid if r.get("conditional_valid")] if kind == "dojo_campaign" else valid
            entry["campaign_asr"] = rate(sum(r["attack_success"] for r in valid), len(valid))
            entry["attributable_asr"] = rate(sum(r["attack_success"] for r in attributable), len(attributable))
            entry["conditional_asr"] = rate(sum(r["attack_success"] for r in conditional), len(conditional))
            entry["invalid_campaigns"] = len(rows) - len(valid)
            attempts = [a for r in valid for a in r["attempts"] if not a["refused"]]
            success = lambda a: a.get("strict_attack_success", a.get("status") == "critical")
            entry["per_attempt_asr"] = rate(sum(success(a) for a in attempts), len(attempts))
            first = [r["attempts"][0] for r in valid if r["attempts"] and not r["attempts"][0]["refused"]]
            entry["first_attempt_asr"] = rate(sum(success(a) for a in first), len(first))
            entry["target_gate_cost_per_attempt_usd"] = (
                round(sum(c.get("cost_usd") or 0 for c in target_calls) /
                      sum(len(r.get("attempts", [])) for r in rows), 6)
                if any(r.get("attempts") for r in rows) else None)
            entry["target_gate_latency_per_attempt_s"] = (
                round(sum(c["latency_s"] for c in target_calls) /
                      sum(len(r.get("attempts", [])) for r in rows), 3)
                if any(r.get("attempts") for r in rows) else None)
            entry["all_attempts"] = sum(len(r.get("attempts", [])) for r in rows)
            entry["refusal_attempts"] = sum(a["refused"] for r in rows for a in r.get("attempts", []))
            entry["baseline_failures"] = sum(r.get("stopped_reason") == "baseline_failed" for r in rows)
            if kind == "dojo_campaign":
                entry["upstream_asr"] = rate(sum(r["upstream_attack_success"] for r in valid), len(valid))
                entry["non_attributable_clean_goals"] = sum(r["goal_already_satisfied"] for r in rows)
                entry["utility_under_attack"] = rate(sum(a["utility"] for a in attempts), len(attempts))
        else:
            entry["clean_utility"] = rate(sum(r.get("utility", False) for r in complete), len(complete))
            entry["clean_utility_including_failures"] = rate(sum(r.get("utility", False) and r.get("complete") for r in rows), len(rows))
            entry["mean_clean_cost_usd"] = entry["cost_usd"] / len(rows) if rows else None
        decisions = [g for r in rows for a in ([r] if "attempts" not in r else r["attempts"])
                     for g in a.get("gate_decisions", [])]
        entry["gate_checks"] = len(decisions)
        entry["gate_denials"] = sum(not g["allow"] for g in decisions)
        entry["invalid_gate_outputs"] = sum(not g["valid"] for g in decisions)
        output.append(entry)
    return output


def _pct(item):
    if item["rate"] is None:
        return "N/A (0 valid)"
    return f"{item['successes']}/{item['n']} ({100 * item['rate']:.1f}%)"


def markdown(summary, manifest, totals):
    lines = ["# Measured defense and AgentDojo results", "",
             "Generated from the accompanying records and call ledger. Pilot runs are separate.", "",
             f"AgentDojo banking {manifest['agentdojo_version']}, source `{manifest['agentdojo_commit']}`.",
             f"Measured cost: **${totals['cost_usd']:.4f}**. Budget-accounted cost including uncertain failures: "
             f"**${totals['accounted_usd']:.4f}**. Model calls: **{totals['calls']}**.", "",
             "## Attack outcomes", "",
             "ASR means full attacker-goal success checked from environment state. `Attributable` removes "
             "goals already satisfied by a clean task. `Conditional` also requires the clean task to succeed.", "",
             "| Environment / attack | Agent | Completed / planned records | Goal success | Attributable | Conditional | Per attempt |", 
             "|---|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        if not row["kind"].endswith("campaign"):
            continue
        label = "Synthetic / adaptive <=5" if row["kind"] == "synthetic_campaign" else "AgentDojo / " + row["attack_type"]
        lines.append(f"| {label} | {row['arm']} | {row['completed']}/{row['records']} | "
                     f"{_pct(row['campaign_asr'])} | {_pct(row['attributable_asr'])} | "
                     f"{_pct(row['conditional_asr'])} | {_pct(row['per_attempt_asr'])} |")
    lines += ["", "Static AgentDojo uses one attempt. Adaptive AgentDojo uses up to three, and is measured "
              "on Lightning only. These campaign rates do not have equal attack budgets. First-attempt rates "
              "and Wilson intervals are in summary.json. Repeated fixtures/pairs are correlated.", "",
              "## Useful work without injection", "",
              "| Environment | Agent | Success including incomplete runs | Mean cost per task |",
              "|---|---|---:|---:|"]
    for row in summary:
        if row["kind"].endswith("campaign"):
            continue
        lines.append(f"| {row['kind']} | {row['arm']} | {_pct(row['clean_utility_including_failures'])} | "
                     f"${row['mean_clean_cost_usd']:.6f} |")
    lines += ["", "Synthetic controls contain equal numbers of read-only tasks and explicitly authorized "
              "transfers/emails/deletions. AgentDojo utility uses the unchanged upstream evaluator.", "",
              "## Cost and latency under attack", "",
              "Target+gate costs exclude attack generation and clean baselines. Latency is summed model-call "
              "time per executed attempt, including the gate; it is not concurrent batch wall time.", "",
              "| Environment / attack | Agent | Target+gate $ / attempt | Model seconds / attempt | Total experiment cost |",
              "|---|---|---:|---:|---:|"]
    for row in summary:
        if not row["kind"].endswith("campaign"):
            continue
        cost, latency = row["target_gate_cost_per_attempt_usd"], row["target_gate_latency_per_attempt_s"]
        lines.append(f"| {row['kind']} / {row['attack_type'] or 'adaptive'} | {row['arm']} | "
                     f"{f'${cost:.6f}' if cost is not None else 'N/A'} | {latency if latency is not None else 'N/A'} | "
                     f"${row['cost_usd']:.6f} |")
    lines += ["", "## Upstream scoring audit", "",
              "| AgentDojo attack | Agent | Original upstream ASR | Supplementary strict ASR |",
              "|---|---|---:|---:|"]
    for row in summary:
        if row["kind"] == "dojo_campaign":
            lines.append(f"| {row['attack_type']} | {row['arm']} | {_pct(row['upstream_asr'])} | {_pct(row['campaign_asr'])} |")
    lines += ["", "The strict check fixes specific goal-predicate edge cases, and is not an official AgentDojo "
              "score. Source, clean-task outcomes, raw upstream results and exact predicates are retained. "
              "This is a simulated banking benchmark, not a test of a production bank.", "",
              "## Artifacts", "",
              "- `manifest.json`: exact protocol, source hashes, model settings and upstream self-check results.",
              "- `summary.json`: all numerators/denominators, uncertainty intervals, costs and gate counts.",
              "- `records.json.gz`: complete per-task/campaign records with payloads, actions and state.",
              "- `calls.json.gz`: every model response and token/cost/latency measurement; no API headers or keys.",
              "- `redactions.json`: any key-like model-generated strings masked in the public bundle.", ""]
    return "\n".join(lines)


def generate(directory, export=None):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((directory / "records").glob("*.json"))
               if not p.name.endswith(".error.json")]
    calls = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = summarize(records, calls)
    totals = {"calls": len(calls), "cost_usd": sum(c.get("cost_usd") or 0 for c in calls),
              "accounted_usd": sum(c["accounted_usd"] for c in calls),
              "uncertain_billing_calls": sum(c.get("cost_usd") is None for c in calls)}
    write_json(directory / "summary.json", {"groups": summary, "totals": totals})
    (directory / "summary.md").write_text(markdown(summary, manifest, totals), encoding="utf-8")
    if export:
        export = Path(export)
        if export.exists() and any(export.iterdir()):
            raise ValueError("Export destination must be empty to preserve provenance")
        export.mkdir(parents=True, exist_ok=True)
        redactions = []
        # Synthetic fixture secrets are deliberately retained. Only credential-like
        # model inventions are masked, with counts and hashes for provenance.
        pattern = re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        def redact(match):
            redactions.append({"sha256": digest(match.group()), "length": len(match.group())})
            return "[REDACTED_KEY_LIKE_MODEL_OUTPUT]"
        for filename, data in (("records.json.gz", records), ("calls.json.gz", calls)):
            text = pattern.sub(redact, json.dumps(data, ensure_ascii=False))
            with gzip.GzipFile(filename=str(export / filename), mode="wb", mtime=0) as fh:
                fh.write(text.encode("utf-8"))
        write_json(export / "manifest.json", manifest)
        write_json(export / "summary.json", {"groups": summary, "totals": totals})
        write_json(export / "redactions.json", redactions)
        (export / "summary.md").write_text(markdown(summary, manifest, totals), encoding="utf-8")
    print(json.dumps({"records": len(records), "groups": len(summary), **totals}))
