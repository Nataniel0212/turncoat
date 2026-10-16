"""Publish the per-campaign raw data behind the published results.

    py -3.12 scripts/export_raw.py

Reads the local run directories of the live runs whose raw data still exists
(the 16 Oct replication and the 15 Oct model comparison), checks that they
reproduce the published tables exactly, then writes one JSON line per campaign
to results/raw/. Credential-shaped strings the attacker invented are redacted
(sieve.replays); verdicts, tool calls, tokens, latency and cost are unchanged.
The 15 Oct first benchmark survives only as its markdown report.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sieve.attacker import TECHNIQUE_NAMES  # noqa: E402
from sieve.replays import public_recording  # noqa: E402
from sieve.scenarios import REGISTRY  # noqa: E402

RAW = ROOT / "results" / "raw"
SETS = {
    "replication-2026-10-16": ("runs/20261016-08*", "results/benchmark-2026-10-16.json"),
    "compare-2026-10-15": ("runs/20261015-02*", "results/compare-2026-10-15.json"),
}
TOOL_SCENARIO = {t["function"]["name"]: key for key, s in REGISTRY.items() for t in s.tools}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _scenario(attempts: list[dict]) -> str:
    """Infer the scenario from the tools the agent called (each scenario has its own)."""
    found = {TOOL_SCENARIO[line.split()[1]] for a in attempts
             for line in (a.get("transcript") or "").splitlines()
             if line.startswith("tool: ") and line.split()[1] in TOOL_SCENARIO}
    if len(found) != 1:
        raise ValueError(f"cannot infer the scenario from tool calls: {sorted(found)}")
    return found.pop()


def load_campaigns(pattern: str) -> list[dict]:
    """Live campaigns only: offline dry-runs share the directory but report ~0 s latency."""
    out = []
    for d in sorted(glob.glob(str(ROOT / pattern))):
        metrics, attempts = Path(d) / "metrics.jsonl", Path(d) / "attempts.jsonl"
        if not (metrics.exists() and attempts.exists()):
            continue
        calls, tries = _jsonl(metrics), _jsonl(attempts)
        if not any(c["latency_s"] > 0.05 for c in calls):
            continue
        target = next(c["model"] for c in calls if c["phase"] != "attacker")
        attacker = next((c["model"] for c in calls if c["phase"] == "attacker"), None)
        out.append({"campaign": Path(d).name, "scenario": _scenario(tries),
                    "target": target, "attacker": attacker,
                    "compromised": any(a["status"] == "critical" for a in tries),
                    "attempts": tries, "calls": calls,
                    "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
                    "model_time_s": round(sum(c["latency_s"] for c in calls), 3)})
    return out


def summarize(campaigns: list[dict]) -> dict:
    """Per (target, scenario): campaigns, full compromises, mean attempts, and
    per-technique and per-attempt full-compromise counts."""
    cells: dict = defaultdict(lambda: {"n": 0, "k": 0, "attempts": 0,
                                       "tech": {t: [0, 0] for t in TECHNIQUE_NAMES}})
    for c in campaigns:
        cell = cells[(c["target"], c["scenario"])]
        cell["n"] += 1
        cell["k"] += c["compromised"]
        cell["attempts"] += len(c["attempts"])
        for a in c["attempts"]:
            if a.get("refused"):
                continue
            cell["tech"][a["technique"]][1] += 1
            cell["tech"][a["technique"]][0] += a["status"] == "critical"
    for cell in cells.values():
        cell["per_attempt"] = [sum(k for k, _ in cell["tech"].values()),
                               sum(n for _, n in cell["tech"].values())]
    return dict(cells)


def check(name: str, campaigns: list[dict]) -> None:
    """Fail unless the raw campaigns reproduce the published table exactly."""
    published = json.loads((ROOT / SETS[name][1]).read_text(encoding="utf-8"))
    cells = summarize(campaigns)
    if name.startswith("replication"):
        target = published["models"]["target"]
        assert round(sum(c["cost_usd"] for c in campaigns), 2) == round(published["total_cost"], 2)
        for s in published["scenarios"]:
            cell, crit = cells[(target, s["key"])], s["exceedance"]["critical"]
            assert (cell["k"], cell["n"]) == (crit["k"], crit["n"]), s["key"]
            assert round(cell["attempts"] / cell["n"], 2) == s["attempts"]["mean"], s["key"]
            for t in s["techniques"]:
                assert cell["tech"][t["name"]] == [t["k"], t["n"]], (s["key"], t["name"])
    else:
        for model in published["models"]:
            assert round(sum(c["cost_usd"] for c in campaigns if c["target"] == model["id"]), 2) \
                == round(model["cost"], 2), model["name"]
            for key, cell_pub in model["scenarios"].items():
                cell, crit = cells[(model["id"], key)], cell_pub["critical"]
                assert (cell["k"], cell["n"]) == (crit["k"], crit["n"]), (model["name"], key)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (pattern, _) in SETS.items():
        campaigns = load_campaigns(pattern)
        check(name, campaigns)
        public = [public_recording(c) for c in campaigns]
        redactions = sum(c.get("redactions", 0) for c in public)
        lines = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in public)
        (RAW / f"{name}.jsonl").write_text(lines, encoding="utf-8", newline="\n")
        print(f"{name}: {len(campaigns)} campaigns reproduce {SETS[name][1]}; "
              f"{redactions} redacted strings")


if __name__ == "__main__":
    main()
