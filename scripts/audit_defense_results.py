"""Recompute saved evaluation verdicts and cost totals without any model calls.

Accepts either a private run directory or an exported public data bundle.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sieve.evaluation.common import ARMS, ENDPOINT, LIGHTNING, ULTRA, write_json
from sieve.evaluation.dojo import strict_security, suite
from sieve.evaluation.synthetic import benign_utility, control_utility
from sieve.metering import cost_usd
from sieve.scenarios import Env, get


def load(directory):
    if (directory / "records.json.gz").exists():
        with gzip.open(directory / "records.json.gz", "rt", encoding="utf-8") as fh:
            records = json.load(fh)
        with gzip.open(directory / "calls.json.gz", "rt", encoding="utf-8") as fh:
            calls = json.load(fh)
    else:
        records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((directory / "records").glob("*.json"))
                   if not p.name.endswith(".error.json")]
        calls = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return manifest, records, calls


def audit(directory):
    manifest, records, calls = load(Path(directory))
    failures, checks = [], 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    check(manifest["endpoint"] == ENDPOINT, "Nebius endpoint")
    check(len({r["job_id"] for r in records}) == len(records), "unique job IDs")
    check(all(c["model"] in (LIGHTNING, ULTRA) for c in calls), "named models only")
    check(all(c["phase"] != "gate" or c["enable_thinking"] for c in calls), "gate reasoning setting")
    for c in calls:
        if c["status"] == "ok":
            check(math.isclose(c["cost_usd"], cost_usd(c["model"], c["prompt_tokens"], c["completion_tokens"]),
                               abs_tol=1e-8), "per-call cost " + c["job_id"])
    s = suite()
    disagreements = 0
    for row in records:
        key = row["job_id"]
        job_calls = [c for c in calls if c["job_id"] == key]
        if "totals" in row:
            check(row["totals"]["calls"] == len(job_calls), "call count " + key)
            check(math.isclose(row["totals"]["cost_usd"], sum(c.get("cost_usd") or 0 for c in job_calls),
                               abs_tol=1e-6), "job cost " + key)
        if row["kind"] == "dojo_campaign":
            goal = s.get_injection_task_by_id(row["injection_task"])
            for n, a in enumerate(row["attempts"], 1):
                pre = s.environment_type.model_validate(a["pre_state"])
                post = s.environment_type.model_validate(a["post_state"])
                text = a["messages"][-1]["content"] or ""
                original = bool(goal.security(text, pre, post))
                strict = strict_security(goal, pre, post)
                check(original == a["upstream_attack_success"], f"upstream verdict {key}/{n}")
                check(strict == a["strict_attack_success"], f"strict verdict {key}/{n}")
                disagreements += original != strict
            check(row["attack_success"] == any(a["strict_attack_success"] for a in row["attempts"]),
                  "campaign verdict " + key)
        if row["kind"] == "synthetic_campaign":
            scenario = get(row["scenario"])
            for n, a in enumerate(row["attempts"], 1):
                check(scenario.classify(Env(state=a["state"])) == a["status"], f"synthetic verdict {key}/{n}")
            check(row["attack_success"] == any(a["status"] == "critical" for a in row["attempts"]),
                  "campaign verdict " + key)
        if row["kind"] == "synthetic_control" and "state" in row:
            env = Env(state=row["state"], transcript=row["transcript"].splitlines())
            utility = control_utility(row["scenario"], env) if row["mutation"] else benign_utility(
                row["scenario"], env, row["final_text"])
            check(utility == row["utility"], "control utility " + key)
    expected = (3 * len(ARMS) * manifest["synthetic_trials_per_scenario_arm"] +
                3 * len(ARMS) * 2 * manifest["clean_control_repetitions"] +
                len(manifest["user_tasks"]) * len(ARMS) +
                len(manifest["user_tasks"]) * len(manifest["injection_tasks"]) *
                (len(ARMS) + len(manifest["adaptive_agentdojo_arms"])))
    return {"checks": checks, "passed": not failures, "failures": failures,
            "records": len(records), "planned_records": expected,
            "all_planned_records_present": len(records) == expected,
            "incomplete_records": sum(not r.get("complete") for r in records),
            "calls": len(calls), "api_error_calls": sum(c["status"] != "ok" for c in calls),
            "original_vs_strict_disagreements": disagreements,
            "cost_usd": round(sum(c.get("cost_usd") or 0 for c in calls), 6)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    result = audit(args.directory)
    if args.save:
        write_json(args.directory / "audit.json", result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
