"""Render runs/compare.json (model comparison) into an HTML report with a grouped
bar chart: full-compromise rate per scenario, one bar per target model.

Models are an ordinal size scale (Lightning < Nano < Ultra), so they use a single
sequential blue ramp (light -> dark), not arbitrary categorical hues.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

try:
    from .targets import LABELS
except ImportError:  # run as a script: python sieve/compare_html.py
    from targets import LABELS

SCEN_NAME = {"inbox": "Email", "bank": "Banking", "docs": "Document"}


def _esc(x) -> str:
    return html.escape(str(x))


HEAD = """<meta name="claude:viewport-fit-sides" content="cover">
<title>Model Comparison</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-2:#edf0f4; --fg:#131821;
  --muted:#596170; --line:#dde2e9; --accent:#2f58cc;
  --m1:#a9c4f5; --m2:#4f7fe0; --m3:#1f3f9e;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b0e13; --surface:#141a22; --surface-2:#1a212b; --fg:#e8edf3;
  --muted:#99a3b1; --line:#262f3b; --accent:#6f97ff;
  --m1:#39507f; --m2:#6f97ff; --m3:#aecbff; color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0b0e13; --surface:#141a22; --surface-2:#1a212b; --fg:#e8edf3;
  --muted:#99a3b1; --line:#262f3b; --accent:#6f97ff;
  --m1:#39507f; --m2:#6f97ff; --m3:#aecbff; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.6}
.wrap{max-width:860px;margin:0 auto;
  padding-left:max(18px,env(safe-area-inset-left,0px));
  padding-right:max(18px,env(safe-area-inset-right,0px));padding-block:32px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;padding-bottom:16px;border-bottom:1px solid var(--line)}
.brand{font-family:var(--mono);font-weight:600;font-size:21px;letter-spacing:.14em}
.brand b{color:var(--accent)}
.tagline{color:var(--muted);font-size:13.5px;flex:1;min-width:0}
.badge{font-family:var(--mono);font-size:11px;letter-spacing:.1em;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--muted)}
#theme{cursor:pointer;color:var(--fg)}
h1{font-size:clamp(22px,4vw,30px);letter-spacing:-.01em;margin:22px 0 6px;text-wrap:balance}
.sub{color:var(--muted);font-size:14.5px;max-width:64ch;margin:0 0 18px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:6px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:12px;height:12px;border-radius:3px;display:inline-block}
svg{width:100%;height:auto;display:block}
.chart text{font-family:var(--mono);fill:var(--muted)}
.chart .val{fill:var(--fg);font-weight:600}
.chart .grp{fill:var(--fg)}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:20px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-family:var(--mono);font-weight:500}
.take{background:var(--surface-2);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-top:20px;font-size:14.5px}
.take b{font-family:var(--mono);font-weight:600}
footer{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;line-height:1.7}
</style>"""

# chart geometry
PL, PR, PT, PB = 52, 500, 24, 252   # plot box
PH = PB - PT


def _y(p):  # p in 0..1
    return PB - p * PH


def _chart(scens, models):
    groups = len(scens)
    gw = (PR - PL) / groups
    bw = 26
    gap = 6
    inner = len(models) * bw + (len(models) - 1) * gap
    body = []
    # gridlines
    for pct in (0, 25, 50, 75, 100):
        y = _y(pct / 100)
        body.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{PR}" y2="{y:.1f}" stroke="var(--line)"/>')
        body.append(f'<text x="{PL-8}" y="{y+3:.1f}" font-size="10" text-anchor="end">{pct}</text>')
    for i, sk in enumerate(scens):
        gx = PL + i * gw + (gw - inner) / 2
        for j, m in enumerate(models):
            e = m["scenarios"][sk]["critical"]
            x = gx + j * (bw + gap)
            if not e["n"]:  # no valid trials is missing data, not a 0% rate
                body.append(f'<text class="val" x="{x + bw / 2:.1f}" y="{_y(0) - 6:.1f}" '
                            f'font-size="10.5" text-anchor="middle"><title>{_esc(m["name"])} on '
                            f'{SCEN_NAME.get(sk, sk)}: no valid trials</title>N/A</text>')
                continue
            h = e["p"] * PH
            body.append(f'<rect x="{x:.1f}" y="{_y(e["p"]):.1f}" width="{bw}" height="{h:.1f}" '
                        f'rx="3" fill="var(--m{j+1})"><title>{_esc(m["name"])} on '
                        f'{SCEN_NAME.get(sk, sk)}: {e["p"]*100:.0f}% (95% CI '
                        f'{e["lo"]*100:.0f}-{e["hi"]*100:.0f})</title></rect>')
            # CI whisker
            cx = x + bw / 2
            body.append(f'<line x1="{cx:.1f}" y1="{_y(e["hi"]):.1f}" x2="{cx:.1f}" '
                        f'y2="{_y(e["lo"]):.1f}" stroke="var(--fg)" stroke-width="1.3"/>')
            body.append(f'<text class="val" x="{cx:.1f}" y="{_y(e["p"])-6:.1f}" '
                        f'font-size="10.5" text-anchor="middle">{e["p"]*100:.0f}</text>')
        body.append(f'<text class="grp" x="{gx+inner/2:.1f}" y="{PB+18}" font-size="12" '
                    f'text-anchor="middle">{SCEN_NAME.get(sk, sk)}</text>')
    return (f'<svg class="chart" viewBox="0 0 520 284" role="img" '
            f'aria-label="Full-compromise rate per scenario by target model">'
            f'{"".join(body)}</svg>')


def _worst(model: dict, scens) -> float | None:
    """A model's highest full-compromise rate over cells with valid trials."""
    rates = [model["scenarios"][s]["critical"]["p"] for s in scens
             if model["scenarios"][s]["critical"]["n"]]
    return max(rates) if rates else None


def _headline(scens, models) -> str:
    # Claim the ranking only when the data shows it: the first-listed (smallest)
    # model's worst cell is above the last-listed (largest) model's.
    first, last = _worst(models[0], scens), _worst(models[-1], scens)
    if len(models) > 1 and first is not None and last is not None and first > last:
        return "Stronger Nemotron models resisted prompt injection better"
    return "Prompt-injection resistance by Nemotron model"


def _takeaway(scens, models) -> str:
    parts = []
    for m in models:
        worst = _worst(m, scens)
        if worst is None:
            parts.append(f"{_esc(m['name'])} has no valid trials")
        elif worst:
            parts.append(f"{_esc(m['name'])} was fully compromised in up to "
                         f"{worst * 100:.0f}% of campaigns in a scenario")
        else:
            parts.append(f"<b>{_esc(m['name'])} had no full compromise in any scenario</b> "
                         "(zero observed is not proof of immunity)")
    return "; ".join(parts) + "."


def _rate(e: dict) -> str:
    return f'{e["p"] * 100:.0f}%' if e["n"] else "N/A"


def _table(scens, models):
    head = "<tr><th>target model</th>" + "".join(
        f"<th>{SCEN_NAME.get(s, s)}</th>" for s in scens) + "<th>cost</th></tr>"
    rows = [head]
    for m in models:
        cells = "".join(f'<td>{_rate(m["scenarios"][s]["critical"])}</td>' for s in scens)
        rows.append(f'<tr><td>{_esc(m["name"])}</td>{cells}<td>${m["cost"]:.2f}</td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def _body(data):
    scens = data["scenarios"]
    models = data["models"]
    names = [m["name"] for m in models]
    legend = "".join(
        f'<span><i style="background:var(--m{j+1})"></i>{_esc(n)}</span>'
        for j, n in enumerate(names))
    return f"""<div class="wrap">
<header>
  <div class="brand">TURN<b>COAT</b></div>
  <div class="tagline">Model comparison: does a stronger agent resist prompt injection?</div>
  <span class="badge mono">LIVE · NEBIUS</span>
  <span class="badge mono" id="theme">theme</span>
</header>

<h1>{_headline(scens, models)}</h1>
<p class="sub">Same attacker ({_esc(LABELS.get(data.get('attacker', ''), data.get('attacker', '?')))}), same scenarios, {data['trials_per']} trials
each. Only the agent under test changes. Bars show the full-compromise rate;
whiskers are 95% confidence intervals.</p>

<div class="card">
  <div class="legend">{legend}</div>
  {_chart(scens, models)}
</div>

{_table(scens, models)}

<div class="take">
  <b>Takeaway.</b> {_takeaway(scens, models)} Security is a model-choice tradeoff
  you can now measure.
</div>

<footer>
  Generated {_esc(data.get('generated',''))} · total ${data.get('total_cost',0):.2f} ·
  {data['trials_per']} trials per cell (wide CIs — a screening comparison, not a
  final ranking). Attacker: {_esc(data.get('attacker',''))}. Synthetic data only.
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


def fragment(data):
    return HEAD + "\n" + _body(data)


def standalone(data):
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, "
            "viewport-fit=cover\">\n" + HEAD + "\n</head>\n<body>\n" + _body(data)
            + "\n</body>\n</html>\n")


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/compare.json")
    frag = "--fragment" in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    out = Path(args[0]) if args else Path("compare.html")
    data = json.loads(src.read_text(encoding="utf-8"))
    out.write_text(fragment(data) if frag else standalone(data), encoding="utf-8")
    print(f"wrote {out}")
