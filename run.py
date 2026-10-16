"""Turncoat CLI.

    py -3.12 run.py              # offline dry-run (no key, no cost)
    py -3.12 run.py --live       # real run against Nebius Token Factory
    py -3.12 run.py --attempts 15 --budget 2.0

Dry-run is the default on purpose: it never spends money and never needs a key.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sieve import html_report, scenarios
from sieve.config import Config
from sieve.loop import run_spike
from sieve.report import render, render_benchmark


def main() -> None:
    ap = argparse.ArgumentParser(description="Turncoat — prompt-injection red-team spike")
    ap.add_argument("--live", action="store_true",
                    help="use Nebius Token Factory (needs NEBIUS_API_KEY)")
    ap.add_argument("--scenario", default="inbox", choices=list(scenarios.REGISTRY),
                    help="which agent to attack")
    ap.add_argument("--attempts", type=int, default=None, help="max attack attempts")
    ap.add_argument("--budget", type=float, default=None, help="USD budget cap (total)")
    ap.add_argument("--trials", type=int, default=1,
                    help="run N times and report an attack-success rate")
    ap.add_argument("--benchmark", action="store_true",
                    help="run N trials per scenario with statistics (uses --trials)")
    ap.add_argument("--agent", help="trusted local Python adapter: path/to/agent.py:run_agent")
    args = ap.parse_args()
    target_runner = None
    if args.agent:
        from sieve.adapters import load_adapter
        try:
            target_runner = load_adapter(args.agent)
        except (ValueError, TypeError) as exc:
            ap.error(str(exc))

    cfg = Config.from_env(live=args.live, max_attempts=args.attempts,
                          budget_usd=args.budget)
    scn = scenarios.get(args.scenario)

    if args.live:
        cfg.require_live_ready()
        from sieve.nebius import LiveClient
        make_client = lambda _scn: LiveClient(cfg)  # noqa: E731
        mode = "live"
    else:
        from sieve.fakes import FakeClient
        make_client = lambda _scn: FakeClient(_scn)  # noqa: E731
        mode = "dry-run"

    if args.benchmark:
        from sieve import benchmark, benchmark_html
        bench = benchmark.run_benchmark(make_client, cfg, list(scenarios.REGISTRY),
                                        trials_per=args.trials, target_runner=target_runner)
        bench["mode"] = mode
        bench["models"] = {"attacker": cfg.model_attacker, "target": cfg.model_target}

        text = render_benchmark(bench, mode)              # writes ./benchmark.md
        bdir = Path("runs") / f"bench-{time.strftime('%Y%m%d-%H%M%S')}"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "benchmark.json").write_text(
            json.dumps(bench, indent=2, ensure_ascii=False), encoding="utf-8")
        html_doc = benchmark_html.standalone(bench)
        Path("benchmark.html").write_text(html_doc, encoding="utf-8")
        (bdir / "benchmark.html").write_text(html_doc, encoding="utf-8")
        (bdir / "benchmark.md").write_text(text, encoding="utf-8")
        print(text)
        print(f"\nBenchmark: benchmark.html · data in {bdir}")
        return

    client = make_client(scn)
    if args.trials and args.trials > 1:
        from sieve.trials import run_trials
        result = run_trials(client, cfg, scn, args.trials, target_runner=target_runner)
    else:
        result = run_spike(client, cfg, scn, target_runner=target_runner)
    result["mode"] = mode
    result["models"] = {"attacker": cfg.model_attacker, "target": cfg.model_target}

    text = render(result, mode)            # writes ./report.md
    html_doc = html_report.standalone(result)
    Path("report.html").write_text(html_doc, encoding="utf-8")

    run_dir = result.get("run_dir")
    if run_dir:
        rd = Path(run_dir)
        (rd / "report.md").write_text(text, encoding="utf-8")
        (rd / "report.html").write_text(html_doc, encoding="utf-8")
        (rd / "summary.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(text)
    print(f"\nHTML report: report.html  (and {run_dir}\\report.html)")


if __name__ == "__main__":
    main()
