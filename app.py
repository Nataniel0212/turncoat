"""Turncoat web demo — a FastAPI app (Vercel's Python runtime serves it as one
function; the static UI in public/ is served by the CDN).

    py -3.12 -m uvicorn app:app --reload     # local, http://127.0.0.1:8000

POST /api/attack streams one live red-team campaign as NDJSON: every attacker
injection, every tool call the agent makes, the deterministic verdict and the
metered cost of each Nemotron call on Nebius Token Factory, as it happens.
"""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from sieve import scenarios
from sieve.config import Config, load_dotenv
from sieve.guard import Denied, Guard
from sieve.targets import web_targets

load_dotenv()

ROOT = Path(__file__).resolve().parent
RUNS_DIR = str(Path(tempfile.gettempdir()) / "sieve-runs")
HEARTBEAT_S = 10
# Offline mode for tests and UI work: the deterministic fakes, no key, no spend.
FAKE_LLM = os.environ.get("SIEVE_FAKE_LLM") == "1"

# Agent-under-test choices: key -> (label, model id), shared with the catalog.
TARGETS = web_targets()

app = FastAPI(title="Turncoat", docs_url=None, redoc_url=None)
guard = Guard()


class AttackRequest(BaseModel):
    scenario: str = "inbox"
    target: str = "lightning"
    code: str | None = None


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or request.headers.get("x-real-ip", "")
            or (request.client.host if request.client else "unknown"))


@app.get("/api/health")
def health():
    cfg = Config.from_env(live=True)
    return {"ok": True, "attacker": cfg.model_attacker,
            "targets": {k: {"label": v[0], "id": v[1]} for k, v in TARGETS.items()},
            "key_configured": bool(cfg.api_key) or FAKE_LLM, "fake_llm": FAKE_LLM,
            **guard.status()}


@app.get("/api/scenarios")
def list_scenarios():
    return scenarios.public_catalog()


@app.post("/api/attack")
def attack(body: AttackRequest, request: Request):
    if body.scenario not in scenarios.REGISTRY:
        return JSONResponse({"error": "unknown_scenario"}, status_code=400)
    if body.target not in TARGETS:
        return JSONResponse({"error": "unknown_target"}, status_code=400)

    cfg = Config.from_env(live=True)
    if not cfg.api_key and not FAKE_LLM:
        return JSONResponse({"error": "no_key", "message": "Live runs are not "
                             "configured on this deployment."}, status_code=503)
    try:
        ticket = guard.reserve(body.code, _client_ip(request))
    except Denied as d:
        return JSONResponse({"error": d.code, "message": d.message}, status_code=d.status)

    cfg = replace(cfg, model_target=TARGETS[body.target][1],
                  budget_usd=guard.limits.run_budget,
                  max_attempts=guard.limits.max_attempts)
    scn = scenarios.get(body.scenario)
    events: queue.Queue = queue.Queue()
    done = object()

    def work() -> None:
        from sieve.loop import run_spike
        cost = guard.limits.run_budget  # if anything fails, keep the reservation
        try:
            if FAKE_LLM:
                from sieve.fakes import FakeClient
                client = FakeClient(scn)
            else:
                from sieve.nebius import LiveClient
                client = LiveClient(cfg)
            res = run_spike(client, cfg, scn, runs_dir=RUNS_DIR, on_event=events.put)
            cost = res["totals"]["cost_usd"]
            print(json.dumps({"sieve_run": body.scenario, "target": body.target,
                              "judge": ticket["judge"], "cost_usd": cost,
                              "stopped": res["stopped_reason"]}))
        except Exception as exc:  # noqa: BLE001 - surface to the UI, fail closed
            events.put({"type": "error", "kind": type(exc).__name__,
                        "message": "The live run failed upstream. Showing a "
                                   "recorded run instead is the safe fallback."})
        finally:
            guard.settle(ticket, cost)
            events.put(done)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        t0 = time.time()
        while True:
            try:
                ev = events.get(timeout=HEARTBEAT_S)
            except queue.Empty:
                yield json.dumps({"type": "ping"}) + "\n"
                continue
            if ev is done:
                return
            ev = {**ev, "t": round(time.time() - t0, 3)}
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


# Locally, serve the static UI too. On Vercel the CDN serves public/.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=ROOT / "public", html=True), name="static")
