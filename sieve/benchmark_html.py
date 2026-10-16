"""Benchmark HTML report with inline-SVG charts.

Charts (no external library — inline SVG, legible in light and dark):
  A. Severity-threshold exceedance per scenario — P(>= medium / >= high /
     critical) as one sequential hue at three opacities (ordinal), with 95%
     Wilson CI whiskers and value labels. A data table backs it for access.
  B. Critical rate by attack technique — single-hue horizontal bars.

Text is always drawn in text tokens, never a series colour; identity comes from
labels and a legend, not colour alone.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

THRESH = [("medium", "≥ medium", 0.42), ("high", "≥ high", 0.70),
          ("critical", "critical", 1.0)]


def _esc(x) -> str:
    return html.escape(str(x))


HEAD = """<meta name="claude:viewport-fit-sides" content="cover">
<title>Turncoat Benchmark</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-2:#eef1f5; --fg:#161a20;
  --muted:#5c636e; --line:#dde2e8; --accent:#3a63d8; --heat:#cf3a1f;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0d1016; --surface:#151a21; --surface-2:#1b222c; --fg:#e7ecf2;
  --muted:#99a3b1; --line:#283039; --accent:#7098ff; --heat:#ff7a52; color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0d1016; --surface:#151a21; --surface-2:#1b222c; --fg:#e7ecf2;
  --muted:#99a3b1; --line:#283039; --accent:#7098ff; --heat:#ff7a52; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:900px;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:32px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  padding-bottom:18px;border-bottom:1px solid var(--line)}
.brand{font-family:var(--mono);font-weight:600;font-size:22px;letter-spacing:.14em}
.brand b{color:var(--accent)}
.tagline{color:var(--muted);font-size:13.5px;min-width:0;flex:1}
.badge{font-family:var(--mono);font-size:11px;letter-spacing:.1em;padding:4px 9px;
  border:1px solid var(--line);border-radius:999px;color:var(--muted)}
#theme{cursor:pointer;background:var(--surface-2);color:var(--fg)}
.lead{margin-top:18px;color:var(--muted);font-size:13.5px}
.lead b{color:var(--fg);font-family:var(--mono);font-weight:500}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.tile .k{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-family:var(--mono);font-size:20px;font-weight:600;margin-top:6px;font-variant-numeric:tabular-nums}
h2.section{font-family:var(--mono);font-size:13px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);margin:30px 0 6px}
.cap{color:var(--muted);font-size:12.5px;margin:0 0 12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 16px 10px}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:2px 0 10px;font-family:var(--mono);font-size:12px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:12px;height:12px;border-radius:3px;background:var(--heat);display:inline-block}
svg{width:100%;height:auto;display:block}
.chart text{font-family:var(--mono);fill:var(--muted)}
.chart .val{fill:var(--fg);font-weight:600}
.chart .grp{fill:var(--fg);font-family:var(--sans);font-weight:600}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:8px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right;font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-family:var(--mono);font-weight:500}
details{margin-top:10px}
summary{cursor:pointer;font-family:var(--mono);font-size:12px;color:var(--accent)}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;line-height:1.7}
footer .mono{color:var(--fg)}
@media (max-width:640px){.tiles{grid-template-columns:repeat(2,1fr)}}
</style>"""

X0 = 196       # left edge of plot (room for labels)
X1 = 606       # right edge (0..100%)
SCALE = (X1 - X0) / 100.0


def _xpct(p: float) -> float:
    return X0 + p * 100 * SCALE


def _gridlines(top: float, bottom: float) -> str:
    out = []
    for pct in (0, 25, 50, 75, 100):
        x = _xpct(pct / 100)
        out.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" '
                   f'stroke="var(--line)" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{top - 6}" text-anchor="middle" '
                   f'font-size="10">{pct}</text>')
    return "".join(out)


def _exceedance_chart(scenarios: list) -> str:
    row_h, grp_gap, top = 26, 16, 34
    y = top
    body = []
    for s in scenarios:
        body.append(f'<text class="grp" x="8" y="{y + 12}" font-size="13">'
                    f'{_esc(s["title"])}</text>')
        y += 20
        for key, label, opacity in THRESH:
            e = s["exceedance"][key]
            mid = y + row_h / 2
            bx = _xpct(e["p"])
            body.append(f'<text x="{X0 - 10}" y="{mid + 4:.1f}" text-anchor="end" '
                        f'font-size="11">{label}</text>')
            if not e["n"]:
                body.append(f'<text x="{X0 + 8}" y="{mid + 4:.1f}" font-size="11">N/A — no valid trials</text>')
                y += row_h
                continue
            body.append(f'<rect x="{X0}" y="{mid - 7:.1f}" width="{max(0, bx - X0):.1f}" '
                        f'height="14" rx="3" fill="var(--heat)" fill-opacity="{opacity}">'
                        f'<title>{_esc(s["title"])} · {label}: {e["p"]*100:.1f}% '
                        f'(95% CI {e["lo"]*100:.0f}–{e["hi"]*100:.0f}, {e["k"]}/{e["n"]})</title>'
                        f'</rect>')
            # CI whisker
            xl, xh = _xpct(e["lo"]), _xpct(e["hi"])
            body.append(f'<line x1="{xl:.1f}" y1="{mid:.1f}" x2="{xh:.1f}" y2="{mid:.1f}" '
                        f'stroke="var(--fg)" stroke-width="1.5"/>')
            for xc in (xl, xh):
                body.append(f'<line x1="{xc:.1f}" y1="{mid - 4:.1f}" x2="{xc:.1f}" '
                            f'y2="{mid + 4:.1f}" stroke="var(--fg)" stroke-width="1.5"/>')
            body.append(f'<text class="val" x="{xh + 8:.1f}" y="{mid + 4:.1f}" '
                        f'font-size="11">{e["p"]*100:.0f}%</text>')
            y += row_h
        y += grp_gap
    height = y + 6
    return (f'<svg class="chart" viewBox="0 0 640 {height:.0f}" '
            f'role="img" aria-label="Severity-threshold exceedance per scenario">'
            f'{_gridlines(top, height - 6)}{"".join(body)}</svg>')


def _technique_chart(scenarios: list) -> str:
    agg = {}
    for s in scenarios:
        for t in s["techniques"]:
            a = agg.setdefault(t["name"], {"k": 0, "n": 0})
            a["k"] += t["k"]
            a["n"] += t["n"]
    rows = [{"name": k, "rate": (v["k"] / v["n"] if v["n"] else 0.0),
             "k": v["k"], "n": v["n"]} for k, v in agg.items() if v["n"]]
    rows.sort(key=lambda r: r["rate"], reverse=True)
    row_h, top = 26, 30
    y = top
    body = []
    for r in rows:
        mid = y + row_h / 2
        bx = _xpct(r["rate"])
        body.append(f'<text x="{X0 - 10}" y="{mid + 4:.1f}" text-anchor="end" '
                    f'font-size="11">{_esc(r["name"])}</text>')
        body.append(f'<rect x="{X0}" y="{mid - 7:.1f}" width="{max(0, bx - X0):.1f}" '
                    f'height="14" rx="3" fill="var(--accent)">'
                    f'<title>{_esc(r["name"])}: {r["rate"]*100:.1f}% critical '
                    f'({r["k"]}/{r["n"]} attempts)</title></rect>')
        body.append(f'<text class="val" x="{bx + 8:.1f}" y="{mid + 4:.1f}" '
                    f'font-size="11">{r["rate"]*100:.0f}% ({r["k"]}/{r["n"]})</text>')
        y += row_h
    height = y + 6
    return (f'<svg class="chart" viewBox="0 0 640 {height:.0f}" role="img" '
            f'aria-label="Critical rate by attack technique">'
            f'{_gridlines(top, height - 6)}{"".join(body)}</svg>')


def _table(scenarios: list) -> str:
    rows = ["<tr><th>scenario</th><th>P(≥med)</th><th>P(≥high)</th>"
            "<th>P(crit)</th><th>95% CI (crit)</th><th>valid/all</th>"
            "<th>refused</th></tr>"]
    for s in scenarios:
        c = s["exceedance"]
        if not c["critical"]["n"]:
            rows.append(f'<tr><td>{_esc(s["title"])}</td><td colspan="4">N/A — no valid trials</td>'
                        f'<td>0/{s["trials"]}</td><td>{s.get("attacker_refusal_rate", 0)*100:.0f}%</td></tr>')
            continue
        rows.append(
            f'<tr><td>{_esc(s["title"])}</td>'
            f'<td>{c["medium"]["p"]*100:.0f}%</td>'
            f'<td>{c["high"]["p"]*100:.0f}%</td>'
            f'<td>{c["critical"]["p"]*100:.0f}%</td>'
            f'<td>{c["critical"]["lo"]*100:.0f}–{c["critical"]["hi"]*100:.0f}</td>'
            f'<td>{s.get("valid_trials", s["trials"])}/{s["trials"]}</td>'
            f'<td>{s.get("attacker_refusal_rate", 0)*100:.0f}%</td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def _body(bench: dict) -> str:
    mode = bench.get("mode", "live")
    models = bench.get("models", {})
    mode_label = "LIVE · NEBIUS TOKEN FACTORY" if mode == "live" else "DRY-RUN · OFFLINE"
    legend = "".join(
        f'<span><i style="opacity:{op}"></i>{_esc(lbl)}</span>' for _, lbl, op in THRESH)

    tiles = "".join([
        f'<div class="tile"><div class="k">scenarios</div><div class="v">{len(bench["scenarios"])}</div></div>',
        f'<div class="tile"><div class="k">trials / scenario</div><div class="v">{bench["trials_per"]}</div></div>',
        f'<div class="tile"><div class="k">total trials</div><div class="v">{bench["total_trials"]}</div></div>',
        f'<div class="tile"><div class="k">total cost</div><div class="v">${bench["total_cost"]:.3f}</div></div>',
    ])

    return f"""<div class="wrap">
<header>
  <div class="brand">TURN<b>COAT</b></div>
  <div class="tagline">Prompt-injection benchmark for tool-using AI agents</div>
  <span class="badge">{mode_label}</span>
  <span class="badge" id="theme">◐ theme</span>
</header>

<p class="lead">Attack-success probabilities over independent trials, each a 95%
Wilson confidence interval. Target <b>{_esc(models.get('target', '?'))}</b>,
attacker <b>{_esc(models.get('attacker', '?'))}</b>. A trial is one adaptive
campaign; success is checked against the agent's actual actions. Generated
{_esc(bench.get('generated', ''))}. Synthetic data only.
Agent adapter: {_esc(bench.get('agent_adapter', 'built-in'))}.</p>

<div class="tiles">{tiles}</div>

<h2 class="section">How deep does the crack go — per scenario</h2>
<p class="cap">For each agent, the probability a single attack campaign reaches at
least each severity level (whiskers = 95% CI). The attacker model sometimes
refuses to write a payload; rates use only valid trials (≥ 1 real attack), and
refusal rates are in the table. Incomplete campaigns and unsafe baselines are excluded.</p>
<div class="card">
  <div class="legend">{legend}</div>
  {_exceedance_chart(bench["scenarios"])}
  <details><summary>Show the numbers</summary>{_table(bench["scenarios"])}</details>
</div>

<h2 class="section">Which attack techniques get through</h2>
<p class="cap">Share of attempts using each technique that reached a full
(critical) compromise, pooled across scenarios. Valid trials only, the same set
as the rates above.</p>
<div class="card">{_technique_chart(bench["scenarios"])}</div>

<footer>
  <span class="mono">Turncoat</span> · measured on Nebius Token Factory with NVIDIA
  Nemotron · {_esc(bench['total_trials'])} trials, ${bench['total_cost']:.3f}<br>
  Rates estimate this attacker against this agent within this attempt budget —
  not an absolute vulnerability. Every number comes from the run logs.
</footer>
</div>

<script>
(function(){{
  try{{var t=localStorage.getItem('sieve-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}
  var b=document.getElementById('theme');
  if(b)b.addEventListener('click',function(){{
    var cur=document.documentElement.getAttribute('data-theme');
    var dark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next=cur==='dark'?'light':(cur==='light'?'dark':(dark?'light':'dark'));
    document.documentElement.setAttribute('data-theme',next);
    try{{localStorage.setItem('sieve-theme',next);}}catch(e){{}}
  }});
}})();
</script>"""


def fragment(bench: dict) -> str:
    return HEAD + "\n" + _body(bench)


def standalone(bench: dict) -> str:
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, "
            "viewport-fit=cover\">\n" + HEAD + "\n</head>\n<body>\n" + _body(bench)
            + "\n</body>\n</html>\n")


if __name__ == "__main__":
    import sys
    bdir = Path(sys.argv[1])
    frag = "--fragment" in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    out = Path(args[0]) if args else bdir / ("benchmark.fragment.html" if frag
                                             else "benchmark.html")
    data = json.loads((bdir / "benchmark.json").read_text(encoding="utf-8"))
    out.write_text(fragment(data) if frag else standalone(data), encoding="utf-8")
    print(f"wrote {out}")
