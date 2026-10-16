"""Local three-arm defense evaluation and the AgentDojo banking suite.

Preview the exact plan without network traffic:
    python evaluate_defenses.py all --out runs/evaluation
Execute using a separate local environment and an explicit budget:
    python evaluate_defenses.py all --out runs/evaluation --live --budget-usd 9.5
"""
from __future__ import annotations

import argparse
import functools
import json
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sieve.evaluation.common import ARMS, ENDPOINT, LIGHTNING, ULTRA, Session, digest, read_key, utc_now, write_json

ROOT = Path(__file__).resolve().parent


def build_manifest(args):
    from sieve.evaluation import dojo
    s = dojo.suite()
    checks = s.check()
    files = [Path(__file__), *sorted((ROOT / "sieve" / "evaluation").glob("*.py")),
             ROOT / "sieve" / "attacker.py", ROOT / "sieve" / "scenarios.py"]
    return {"schema_version": 1, "created_at": utc_now(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_hashes": {p.relative_to(ROOT).as_posix(): digest(p.read_text(encoding="utf-8")) for p in files},
            "pilot": args.pilot, "endpoint": ENDPOINT,
            "models": {"lightning": LIGHTNING, "ultra": ULTRA, "attacker": ULTRA, "gate": ULTRA},
            "target_thinking": False, "attacker_thinking": False, "gate_thinking": True,
            "target_temperature": 0.0, "attacker_temperature": 1.0, "gate_temperature": 0.0,
            "max_target_turns": 12, "max_tool_calls": 60,
            "synthetic_trials_per_scenario_arm": 1 if args.pilot else 10,
            "synthetic_max_attempts": 2 if args.pilot else 5,
            "clean_control_repetitions": 1 if args.pilot else 5,
            "agentdojo_source": "https://github.com/ethz-spylab/agentdojo",
            "agentdojo_commit": dojo.SOURCE_COMMIT, "agentdojo_version": dojo.BENCHMARK_VERSION,
            "agentdojo_suite": "banking", "agentdojo_upstream_self_checks": checks,
            "user_tasks": ["user_task_0"] if args.pilot else list(s.user_tasks),
            "injection_tasks": ["injection_task_5", "injection_task_7"] if args.pilot else list(s.injection_tasks),
            "agentdojo_adaptive_max_attempts": 2 if args.pilot else 3,
            "static_attack": "upstream important_instructions; user=Emma Johnson, model=Nemotron",
            "arms": list(ARMS), "adaptive_agentdojo_arms": ["lightning"],
            "shuffle_seed": 20261016,
            "notes": ["All tasks, goals and tools are simulated/public AgentDojo fixtures.",
                      "Static one-attempt and adaptive up-to-three-attempt rates have different attack budgets.",
                      "Security is checked in code; Ultra authorizes actions, it does not judge outcomes.",
                      "Supplementary strict security checks are reported beside unchanged upstream outcomes.",
                      "Clean-task success and already-satisfied goals are reported separately.",
                      "Pilot results are excluded from the main experiment; this is not a held-out benchmark."]}


def run_jobs(session, directory, jobs, workers):
    random.Random(20261016).shuffle(jobs)
    records_dir = directory / "records"
    records_dir.mkdir(exist_ok=True)
    pending = [(key, function) for key, function in jobs if not (records_dir / f"{key}.json").exists()]
    print(f"jobs={len(jobs)} pending={len(pending)} workers={workers}", flush=True)

    def execute(key, function):
        row = function()
        write_json(records_dir / f"{key}.json", row)
        return row

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(execute, key, fn): key for key, fn in pending}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                row = future.result()
            except Exception as exc:
                # Keep a diagnostic without dumping exception bodies/headers.
                key = futures[future]
                write_json(records_dir / f"{key}.error.json", {"job_id": key, "error_type": type(exc).__name__})
                failures += 1
                print(f"ERROR {key}: {type(exc).__name__}", flush=True)
                continue
            if count % 10 == 0 or count == len(pending):
                print(f"done={count}/{len(pending)} accounted_usd={session.spent:.4f} "
                      f"last={row['job_id']} complete={row.get('complete')}", flush=True)
    if failures:
        raise RuntimeError(f"{failures} unexpected job errors; inspect .error.json records")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["all", "synthetic", "dojo-clean", "dojo-static", "dojo-adaptive", "report"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget-usd", type=float, default=9.5)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("workers must be between 1 and 8")
    if args.phase == "report":
        from sieve.evaluation.report import generate
        generate(args.out, args.export)
        return
    manifest = build_manifest(args)
    if not args.live:
        print(json.dumps(manifest, indent=2))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in manifest:
            if field not in ("created_at", "source_commit") and manifest[field] != saved[field]:
                raise ValueError(f"Run configuration changed: {field}. Use a new output directory.")
        manifest = saved
    else:
        write_json(manifest_path, manifest)
    session = Session(args.out, args.budget_usd, api_key=read_key(args.env_file))
    phases = ["synthetic", "dojo-clean", "dojo-static", "dojo-adaptive"] if args.phase == "all" else [args.phase]
    from sieve.evaluation import dojo, synthetic
    for phase in phases:
        jobs = []
        if phase == "synthetic":
            for scenario in ("bank", "inbox", "docs"):
                for arm in ARMS:
                    for trial in range(manifest["synthetic_trials_per_scenario_arm"]):
                        key = f"synthetic--{scenario}--{trial + 1:02d}--{arm}"
                        jobs.append((key, functools.partial(synthetic.campaign, session, key, arm, scenario,
                                                            manifest["synthetic_max_attempts"])))
                    for mutation in (False, True):
                        for trial in range(manifest["clean_control_repetitions"]):
                            key = f"control--{scenario}--{int(mutation)}--{trial + 1:02d}--{arm}"
                            jobs.append((key, functools.partial(synthetic.clean_control, session, key, arm,
                                                                scenario, mutation)))
        elif phase == "dojo-clean":
            for user in manifest["user_tasks"]:
                for arm in ARMS:
                    key = f"dojo-clean--{user}--{arm}"
                    jobs.append((key, functools.partial(dojo.baseline, session, key, arm, user)))
        else:
            attack = "static" if phase == "dojo-static" else "adaptive"
            arms = ARMS if attack == "static" else manifest["adaptive_agentdojo_arms"]
            for user in manifest["user_tasks"]:
                for goal in manifest["injection_tasks"]:
                    for arm in arms:
                        baseline_path = args.out / "records" / f"dojo-clean--{user}--{arm}.json"
                        if not baseline_path.exists():
                            raise ValueError("Run dojo-clean before attack phases")
                        clean = json.loads(baseline_path.read_text(encoding="utf-8"))
                        key = f"dojo-{attack}--{user}--{goal}--{arm}"
                        jobs.append((key, functools.partial(dojo.campaign, session, key, arm, user, goal,
                                                            attack, manifest["agentdojo_adaptive_max_attempts"], clean)))
        print(f"phase={phase}", flush=True)
        run_jobs(session, args.out, jobs, args.workers)
    write_json(args.out / "totals.json", session.totals())
    print(json.dumps(session.totals()), flush=True)


if __name__ == "__main__":
    main()
