"""Render the measured results into public/index.html as static HTML.

    py -3.12 scripts/build_page.py

Reads only results/*.json and results/*.md (written by the benchmark and the
model comparison) and fills the <!-- build:NAME --> ... <!-- /build:NAME -->
blocks, so no number on the page is typed by hand and the results need no
JavaScript. Re-run after a new benchmark.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sieve.benchmark import wilson  # noqa: E402
from sieve.scenarios import public_catalog  # noqa: E402
from sieve.targets import LABELS as NAMES, web_targets  # noqa: E402

RES = ROOT / "results"
PAGE = ROOT / "public" / "index.html"
LABEL = {"inbox": "Email assistant", "bank": "Banking assistant", "docs": "Document assistant"}


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def day(stamp: str, year: bool = False) -> str:
    """'2026-10-16 08:56' -> '16 Oct' (or '16 Oct 2026')."""
    d = datetime.strptime(stamp[:10], "%Y-%m-%d")
    return f"{d.day} {d:%b %Y}" if year else f"{d.day} {d:%b}"


def counted(values, noun: str) -> str:
    """'20 trials' when every value agrees, '17–20 trials' when a run was cut short."""
    lo, hi = min(values), max(values)
    return f"{lo} {noun}" if lo == hi else f"{lo}–{hi} {noun}"


def parse_md(path: Path) -> dict:
    """The 15 Oct run only survives as its markdown report; read its rates back."""
    text = path.read_text(encoding="utf-8")
    run = {"total_cost": float(re.search(r"total cost \$([\d.]+)", text).group(1)),
           "trials_per": int(re.search(r"Trials per scenario: (\d+)", text).group(1)),
           "generated": re.search(r"\d{4}-\d{2}-\d{2}", path.stem).group(0),
           "scenarios": []}
    for key, trials, body in re.findall(r"^## .*?\((\w+)\)\D*(\d+) trials\n(.*?)(?=^## |\Z)",
                                        text, re.M | re.S):
        k, n = map(int, re.search(r"P\(critical\).*?\((\d+)/(\d+)\)", body).groups())
        p, lo, hi = wilson(k, n)
        mean, least, most = re.search(r"mean ([\d.]+), min (\d+), max (\d+)", body).groups()
        refused = float(re.search(r"Attacker refused ([\d.]+)%", body).group(1)) / 100
        techniques = [{"k": int(a), "n": int(b)} for a, b in
                      re.findall(r"\((\d+)/(\d+)\)", body.split("technique:")[1])]
        run["scenarios"].append({"key": key, "trials": int(trials), "exceedance": {"critical": {
            "k": k, "n": n, "p": p, "lo": lo, "hi": hi}},
            "attempts": {"mean": float(mean), "min": int(least), "max": int(most)},
            "techniques": techniques, "attacker_refusal_rate": refused})
    run["total_trials"] = sum(s["trials"] for s in run["scenarios"])
    return run


def per_attempt(s: dict) -> str:
    """Full compromises per real attempt, from the per-technique counts."""
    k, n = sum(t["k"] for t in s["techniques"]), sum(t["n"] for t in s["techniques"])
    return f"{pct(k / n)} per attempt" if n else "no real attempts"


def attempt_cap(run: dict) -> int | None:
    """The per-campaign attempt cap: recorded by newer runs; for older ones, a
    valid campaign that was not compromised ran exactly to the cap."""
    if run.get("max_attempts"):
        return run["max_attempts"]
    held = [s["attempts"]["max"] for s in run["scenarios"]
            if s["exceedance"]["critical"]["k"] < s["exceedance"]["critical"]["n"]]
    return max(held) if held else None


def attempts_note(runs: list[dict]) -> str:
    """State the attempt cap when the results establish it, else the observed range."""
    caps = {attempt_cap(r) for r in runs}
    if len(caps) == 1 and None not in caps:
        return f"Up to {caps.pop()} attempts per campaign."
    lo = min(s["attempts"]["min"] for r in runs for s in r["scenarios"])
    hi = max(s["attempts"]["max"] for r in runs for s in r["scenarios"])
    return f"Campaigns ran {lo}–{hi} attempts."


def overlap_note(comp: dict) -> str:
    """Name the model pairs whose rates differ but whose 95% intervals overlap."""
    pairs = []
    for key in comp["scenarios"]:
        cells = [(m["name"], m["scenarios"][key]["critical"]) for m in comp["models"]]
        for i, (a, ea) in enumerate(cells):
            for b, eb in cells[i + 1:]:
                if (ea["n"] and eb["n"] and ea["p"] != eb["p"]
                        and ea["lo"] <= eb["hi"] and eb["lo"] <= ea["hi"]):
                    pairs.append(f"{a} and {b} ({LABEL[key].lower()})")
    return (" Overlapping intervals, so no established difference: " + "; ".join(pairs) + ".") \
        if pairs else ""


def defense_section() -> str:
    """Render the audited AgentDojo matched-set result into the public page."""
    text = (RES / "defense-2026-10-16" / "summary.md").read_text(encoding="utf-8")
    row = re.search(
        r"\| dojo_static / also clean-success in all arms \| "
        r"([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|",
        text,
    )
    if not row:
        raise ValueError("Could not find the audited AgentDojo matched-set row")
    values = [part.strip() for part in row.groups()]
    labels = ["Lightning", "Lightning + Ultra gate", "Ultra"]
    cards = "".join(
        f'<div class="card defense-card"><div class="cap">{label}</div>'
        f'<div class="defense-value">{escape(value)}</div>'
        f'<div class="note">attacker-goal success on the same 70 clean-success pairs</div></div>'
        for label, value in zip(labels, values)
    )
    return (
        '<div class="defense-grid">' + cards + '</div>'
        '<p class="note">AgentDojo banking v1.2.2. The gate observed 0/70 successes, '
        'but zero observed successes is not a security guarantee; incomplete runs and '
        '<a href="https://github.com/Nataniel0212/turncoat/tree/main/results/defense-2026-10-16">'
        'the full audit data</a> are disclosed.</p>'
    )


def ci_row(label: str, e: dict, note: str) -> str:
    if not e["n"]:  # no valid trials is missing data, never a 0% rate
        return (
            f'<div class="cirow"><div class="lbl"><span style="color:var(--fg)">{escape(label)}</span>'
            f'<b>N/A</b></div><div class="track" role="img" aria-label="{escape(label)}: '
            f'no valid trials"></div><div class="lbl"><span>{escape(note)}</span>'
            f'<span>no valid trials</span></div></div>')
    low = " low" if e["p"] < 0.5 else ""
    return (
        f'<div class="cirow"><div class="lbl"><span style="color:var(--fg)">{escape(label)}</span>'
        f'<b>{pct(e["p"])}</b></div>'
        f'<div class="track" role="img" aria-label="{escape(label)}: {pct(e["p"])}, 95% CI '
        f'{pct(e["lo"])} to {pct(e["hi"])}">'
        f'<div class="fill{low}" style="width:{e["p"] * 100:.1f}%"></div>'
        f'<div class="whisk" style="left:{e["lo"] * 100:.1f}%;width:{(e["hi"] - e["lo"]) * 100:.1f}%"></div>'
        f'</div><div class="lbl"><span>{escape(note)}</span>'
        f'<span>95% CI {pct(e["lo"])}–{pct(e["hi"])}</span></div></div>')


def bench_card(title: str, run: dict) -> str:
    rows = "".join(
        ci_row(LABEL[s["key"]], s["exceedance"]["critical"],
               f'{s["exceedance"]["critical"]["k"]}/{s["exceedance"]["critical"]["n"]} · '
               f'{per_attempt(s)} · mean {s["attempts"]["mean"]} attempts')
        for s in run["scenarios"])
    refusals = " / ".join(pct(s.get("attacker_refusal_rate", 0)) for s in run["scenarios"])
    trials = counted([s["trials"] for s in run["scenarios"]], "trials")
    return (f'<div class="card"><div class="cap">{escape(title)} · {trials} per agent · '
            f'${run["total_cost"]:.2f}</div><div class="cibar">{rows}</div>'
            f'<div class="note">Attacker refusals: {refusals}.</div></div>')


def render() -> tuple[str, dict]:
    day1 = parse_md(RES / "benchmark-2026-10-15.md")
    day2 = json.loads((RES / "benchmark-2026-10-16.json").read_text(encoding="utf-8"))
    comp = json.loads((RES / "compare-2026-10-15.json").read_text(encoding="utf-8"))
    stats = json.loads((RES / "campaign-stats-2026-10-16.json").read_text(encoding="utf-8"))
    target = NAMES.get(day2["models"]["target"], day2["models"]["target"])
    by_key = {s["key"]: s for s in day2["scenarios"]}
    cap = attempt_cap(day2)
    within = f" within {cap} attempts" if cap else ""
    hero = (f'<figcaption class="cap">Full compromise{within} · {escape(target)} agents · '
            f'{day(day2["generated"], year=True)}</figcaption>')
    hero += '<div class="cibar">' + "".join(
        ci_row(LABEL[key], by_key[key]["exceedance"]["critical"],
               f'{by_key[key]["exceedance"]["critical"]["k"]}/{by_key[key]["exceedance"]["critical"]["n"]} '
               f'campaigns · {per_attempt(by_key[key])}')
        for key in ("bank", "inbox", "docs")) + '</div>'
    hero += '<div class="foot-note">Whiskers: 95% Wilson intervals. Synthetic agents; not a general model rating.</div>'
    measured = stats[day2["models"]["target"]]
    total = day1["total_trials"] + day2["total_trials"]
    days = len({day1["generated"][:10], day2["generated"][:10]})
    facts = "".join(f'<div class="fact"><div class="v">{value}</div><div class="k">{label}</div></div>'
                    for value, label in [
                        (str(total), f"benchmark campaigns · {days} days"),
                        (f'${day2["total_cost"]:.2f}', f'{day2["total_trials"]}-campaign replication'),
                        (f'${measured["median_cost_usd"]:.4f}', "median campaign · replication"),
                        (f'{measured["median_model_time_s"]:.1f}s', "median model time · replication")])
    bench = '<div class="bench">' + bench_card(f'{day(day1["generated"])} · first run', day1)
    bench += bench_card(f'{day(day2["generated"])} · independent replication', day2) + '</div>'
    bench += (f'<p class="note">Target: {escape(target)}. {attempts_note([day1, day2])} '
              'Each interval describes one day, not pooled trials. '
              '<a href="https://github.com/Nataniel0212/turncoat/tree/main/results">Raw reports and methodology ↗</a></p>')
    compare = '<div class="tablewrap"><table class="comparison"><caption>Full-compromise rate by target model</caption><thead><tr><th>Target model</th>'
    compare += "".join(f'<th>{escape(LABEL[k])}</th>' for k in comp["scenarios"]) + '</tr></thead><tbody>'
    for model in comp["models"]:
        compare += f'<tr><th scope="row">{escape(model["name"])}</th>'
        for key in comp["scenarios"]:
            e = model["scenarios"][key]["critical"]
            if not e["n"]:
                compare += '<td class="cell"><div class="p">N/A</div><div class="kn">no valid trials</div></td>'
                continue
            cls = "hot" if e["p"] >= 0.5 else "cool" if e["k"] == 0 else ""
            compare += (f'<td class="cell {cls}"><div class="p">{pct(e["p"])}</div>'
                        f'<div class="kn">{e["k"]}/{e["n"]} · CI {pct(e["lo"])}–{pct(e["hi"])}</div></td>')
        compare += '</tr>'
    cells = counted([s.get("trials", comp["trials_per"]) for m in comp["models"]
                     for s in m["scenarios"].values()], "campaigns")
    compare += (f'</tbody></table></div><p class="note">{cells} per cell · '
                f'${comp["total_cost"]:.2f} total. Zero observed compromises does not establish immunity.'
                f'{overlap_note(comp)}</p>')
    tech = '<div class="techs">'
    for scn in day2["scenarios"]:
        tech += f'<div class="card"><div class="cap">{escape(LABEL[scn["key"]])}</div>'
        for t in scn["techniques"]:
            rate = pct(t["rate"]) if t["n"] else "N/A"
            tech += (f'<div class="trow"><span class="nm">{escape(t["name"])}</span>'
                     f'<span class="bar" aria-hidden="true"><i style="width:{t["rate"] * 100:.1f}%"></i></span>'
                     f'<span class="v"><b>{rate}</b> {t["k"]}/{t["n"]}</span></div>')
        tech += '</div>'
    tech += (f'</div><p class="note">{day(day2["generated"])} replication. Technique order is fixed: '
             'these rates also reflect attempt position and prior feedback, not isolated causal effects.</p>')
    html = PAGE.read_text(encoding="utf-8")
    for name, body in {"hero": hero, "facts": facts, "bench": bench, "compare": compare,
                       "tech": tech, "defense": defense_section()}.items():
        pattern = rf"(<!-- build:{name} -->).*?(<!-- /build:{name} -->)"
        html, count = re.subn(pattern, lambda m: m[1] + "\n" + body + "\n" + m[2], html, flags=re.S)
        if count != 1:
            raise ValueError(f"Expected exactly one build block: {name}, found {count}")
    catalog = {
        "scenarios": public_catalog(),
        "targets": {key: {"label": label, "id": model}
                    for key, (label, model) in web_targets().items()},
        "replays": sorted(p.stem for p in (ROOT / "public/data/replays").glob("*.json")),
    }
    return html, catalog


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Fail if generated assets are stale")
    args = ap.parse_args()
    html, catalog = render()
    outputs = {PAGE: html, ROOT / "public/data/catalog.json": json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"}
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Stale generated asset: {path.relative_to(ROOT)}; run scripts/build_page.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Path.write_text(newline=...) only exists on newer Python versions;
            # use open() so the offline builder also works on Python 3.9.
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
    print("Page and offline catalog are up to date." if args.check else "Built page and offline catalog.")


if __name__ == "__main__":
    main()
