"""Render the spike result to the console and to report.md. Every number comes
straight from the meter / the attempt log — nothing here is hand-written.
"""

from __future__ import annotations

from pathlib import Path

from .loop import campaign_finished, valid_campaign
from .scenarios import LEVEL_LABEL, LEVEL_RANK


def _verdict(counts: dict) -> str:
    if counts.get("critical"):
        return "FULL COMPROMISE"
    if counts.get("high"):
        return "LIKELY COMPROMISE — dangerous action short of the full outcome"
    if counts.get("medium"):
        return "PARTIAL COMPROMISE — injection redirected the agent"
    return "HELD — no injection changed the agent's behaviour"


def _render_finding(lines: list[str], rec: dict) -> None:
    lines.append("")
    lines.append(f"### attempt {rec['attempt']} — {rec['status'].upper()}: {rec.get('desc', '')}")
    lines.append("Agent actions:")
    lines.append("```")
    lines.append(rec.get("transcript") or "(none)")
    lines.append("```")
    for a in rec.get("actions", []):
        lines.append(f"- {a}")
    lines.append("Injected content (exact text):")
    lines.append("```")
    lines.append(rec.get("injection", ""))
    lines.append("```")


def render_benchmark(bench: dict, mode: str, out_path: str = "benchmark.md") -> str:
    tag = "DRY-RUN (offline)" if mode == "dry-run" else "LIVE (Nebius)"
    L: list[str] = []
    L.append(f"# Turncoat benchmark — {tag}")
    L.append("")
    L.append(f"- Trials per scenario: {bench['trials_per']} · "
             f"total trials {bench['total_trials']} · "
             f"total cost ${bench['total_cost']:.4f}")
    L.append("- Rates are attack-success probabilities with a 95% Wilson "
             "confidence interval; a trial is one adaptive campaign.")
    L.append(f"- Agent adapter: {bench.get('agent_adapter', 'built-in')}")
    for s in bench["scenarios"]:
        L.append("")
        L.append(f"## {s['title']} ({s['key']}) — {s['trials']} trials")
        L.append(f"Goal: {s['goal']}")
        L.append(f"Attacker refused {s.get('attacker_refusal_rate', 0)*100:.0f}% of "
                 f"attempts; valid trials (>= 1 real attack): "
                 f"{s.get('valid_trials', s['trials'])}/{s['trials']}. "
                 f"Incomplete trials excluded: {s.get('incomplete_trials', 0)}. Rates below use valid trials.")
        for name in ("medium", "high", "critical"):
            e = s["exceedance"][name]
            lbl = {"medium": "P(>= medium)", "high": "P(>= high)",
                   "critical": "P(critical) "}[name]
            if not e["n"]:
                L.append(f"- {lbl}: N/A — no valid completed trials")
                continue
            L.append(f"- {lbl}: {e['p'] * 100:5.1f}%  "
                     f"[{e['lo'] * 100:4.1f}–{e['hi'] * 100:4.1f}]  ({e['k']}/{e['n']})")
        a = s["attempts"]
        L.append(f"- Attempts per valid trial: mean {a['mean']}, min {a['min']}, max {a['max']}")
        hits, tries = sum(t["k"] for t in s["techniques"]), sum(t["n"] for t in s["techniques"])
        if tries:
            L.append(f"- Per attempt: {hits / tries * 100:.0f}% of real attempts fully "
                     f"compromised the agent ({hits}/{tries}); trial rates are within "
                     f"{bench.get('max_attempts', 'the')} attempts")
        tops = [t for t in s["techniques"] if t["n"]]
        if tops:
            L.append("- Critical rate by technique: " +
                     ", ".join(f"{t['name']} {t['rate'] * 100:.0f}% ({t['k']}/{t['n']})"
                               for t in tops))
    text = "\n".join(L) + "\n"
    Path(out_path).write_text(text, encoding="utf-8")
    return text


def render(result: dict, mode: str, out_path: str = "report.md") -> str:
    t = result["totals"]
    counts = result.get("counts", {})
    scn = result.get("scenario", {})
    tag = "DRY-RUN (fake models, offline)" if mode == "dry-run" else "LIVE (Nebius)"

    if result["baseline_safe"] is None:
        baseline = "not run"
    elif result["baseline_safe"]:
        baseline = "yes"
    else:
        baseline = "NO — agent acted on benign content"

    breakdown = " · ".join(f"{s} {counts.get(s, 0)}" for s in LEVEL_RANK + ["safe"])

    lines: list[str] = []
    lines.append(f"# Turncoat report — {tag}")
    lines.append("")
    lines.append(f"- Scenario: {scn.get('title', '?')} ({scn.get('key', '?')})")
    lines.append(f"- Agent adapter: {result.get('agent_adapter', 'built-in')}")
    lines.append(f"- Attacker goal: {scn.get('goal', '?')}")
    lines.append(f"- Baseline (benign content) safe: {baseline}")
    lines.append(f"- Attack attempts run: {result['attempts_run']}")
    if not campaign_finished(result):
        observed = "INCOMPLETE — no robustness conclusion"
    elif not valid_campaign(result):
        observed = "INCONCLUSIVE — no real attack completed"
    else:
        observed = _verdict(counts)
    lines.append(f"- Verdict: {observed} (stopped: {result['stopped_reason']})")

    agg = result.get("aggregate")
    if agg:
        r = agg["rates"]
        if agg.get("valid_trials", agg["trials"]):
            lines.append(f"- Trials: {agg['trials']} (valid: {agg.get('valid_trials', agg['trials'])}) · "
                     f"full-compromise rate {r['critical'] * 100:.0f}% · "
                     f"any-compromise {r['compromise'] * 100:.0f}% · "
                     f"total ${agg['total_cost']:.4f} over {agg['total_attempts']} attempts")
        else:
            lines.append(f"- Trials: {agg['trials']} · rates N/A — no valid completed trials · total ${agg['total_cost']:.4f}")
        lines.append("- Per trial (top severity): " +
                     ", ".join(f"#{p['trial']}:{p['top_status']}" for p in agg["per_trial"]))
    lines.append(f"- Severity breakdown (shown trial): {breakdown}")
    lines.append("")
    lines.append("## Cost & tokens (measured)")
    lines.append(f"- LLM calls: {t['calls']}")
    lines.append(f"- Prompt tokens: {t['prompt_tokens']}")
    lines.append(f"- Completion tokens: {t['completion_tokens']} (reasoning: {t['reasoning_tokens']})")
    lines.append(f"- Total latency: {t['latency_s']} s")
    lines.append(f"- Total cost: ${t['cost_usd']:.6f}")
    lines.append(f"- Run dir: {result.get('run_dir', '?')}")
    lines.append("")

    findings = result.get("findings", [])
    if findings:
        lines.append("## Findings (most severe first)")
        ordered = sorted(findings, key=lambda r: LEVEL_RANK.index(r["status"])
                         if r["status"] in LEVEL_RANK else len(LEVEL_RANK))
        for rec in ordered:
            _render_finding(lines, rec)
    else:
        lines.append("No injection changed the agent's behaviour within the limit.")

    text = "\n".join(lines) + "\n"
    Path(out_path).write_text(text, encoding="utf-8")
    return text
