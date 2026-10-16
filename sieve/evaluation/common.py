"""Measured Nebius calls, a shared budget, and resumable experiment artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sieve.metering import PRICES, cost_usd
from sieve.nebius import LLMResult

ENDPOINT = "https://api.tokenfactory.nebius.com/v1"
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
ARMS = ("lightning", "lightning_gate", "ultra")
ARM_MODELS = {"lightning": LIGHTNING, "lightning_gate": LIGHTNING, "ultra": ULTRA}


class EvaluationStop(Exception):
    """Infrastructure or budget stop: never evidence of a successful defense."""


class BudgetExhausted(EvaluationStop):
    pass


class ModelFailure(EvaluationStop):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_key(env_file=None):
    # An explicit file selects that key, independent of another shell's env.
    # Neither the key nor the file's other values enter experiment artifacts.
    if env_file:
        from dotenv import dotenv_values
        key = dotenv_values(env_file).get("NEBIUS_API_KEY", "")
    else:
        key = os.environ.get("NEBIUS_API_KEY", "")
    if not key:
        raise ValueError("Set NEBIUS_API_KEY or pass --env-file with a local key.")
    return key


@dataclass
class EvaluationResult(LLMResult):
    finish_reason: str = "stop"


class Session:
    """One thread-safe ledger for all arms, attacks, clean tasks and retries.

    Reserves a conservative input-byte/output-token allowance before each call.
    Failed calls with uncertain billing keep their allowance. This is an
    application guard at published prices, not a provider-enforced billing cap.
    SDK retries and model fallback are disabled. Resume reads the same ledger.
    """

    def __init__(self, directory, budget_usd, api_key=None, transport=None):
        if not math.isfinite(budget_usd) or budget_usd <= 0:
            raise ValueError("Budget must be finite and positive")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "calls.jsonl"
        self.rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()] \
            if self.path.exists() else []
        self.budget = budget_usd
        self.lock = threading.Lock()
        self.reserved = 0.0
        self.spent = sum(r["accounted_usd"] for r in self.rows)
        self.halted = False
        if transport is None:
            from openai import OpenAI
            transport = OpenAI(api_key=api_key, base_url=ENDPOINT, max_retries=0, timeout=60.0)
        self.transport = transport

    def chat(self, *, job_id, phase, attempt=0, model, messages, tools=None,
             max_tokens=8192, enable_thinking=False, force_nonempty=True,
             temperature=0.0, response_schema=None):
        if model not in PRICES:
            raise ValueError("Unknown model price: refusing unmetered evaluation")
        if not isinstance(max_tokens, int) or not 1 <= max_tokens <= 8192:
            raise ValueError("max_tokens must be between 1 and 8192")
        # One token per UTF-8 byte, plus explicit template overhead. Deliberately
        # conservative; do not call this an exact tokenizer or a billing cap.
        input_bound = len(canonical([messages, tools, response_schema]).encode()) + 2048
        allowance = cost_usd(model, input_bound, max_tokens)
        with self.lock:
            if self.halted:
                raise ModelFailure("session_halted")
            if self.spent + self.reserved + allowance > self.budget:
                raise BudgetExhausted("budget_reservation")
            self.reserved += allowance
        extra = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        if force_nonempty:
            extra["force_nonempty_content"] = True
        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                      temperature=temperature, extra_body=extra)
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        if response_schema:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "authorization", "strict": True, "schema": response_schema}}
        row = dict(job_id=job_id, phase=phase, attempt=attempt, model=model,
                   timestamp=utc_now(), enable_thinking=enable_thinking,
                   max_tokens=max_tokens, request_sha256=digest(kwargs),
                   reserved_usd=round(allowance, 9))
        started = time.monotonic()
        result, failure = None, None
        try:
            response = self.transport.chat.completions.create(**kwargs)
            usage = response.usage
            if usage is None or not usage.prompt_tokens or usage.completion_tokens is None:
                raise ModelFailure("missing_usage")
            msg = response.choices[0].message
            calls = []
            for call in msg.tool_calls or []:
                try:
                    args = json.loads(call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {"__invalid_json__": True}
                calls.append({"id": call.id, "name": call.function.name, "args": args})
            details = getattr(usage, "completion_tokens_details", None)
            tokens = {"prompt_tokens": usage.prompt_tokens,
                      "completion_tokens": usage.completion_tokens,
                      "reasoning_tokens": getattr(details, "reasoning_tokens", 0) or 0}
            actual = cost_usd(model, tokens["prompt_tokens"], tokens["completion_tokens"])
            finish = response.choices[0].finish_reason
            row.update(**tokens, cost_usd=round(actual, 9), accounted_usd=round(actual, 9),
                       finish_reason=finish, response_model=response.model,
                       status="ok", response={"content": msg.content or "", "tool_calls": calls})
            result = EvaluationResult(msg.content or "", calls, tokens,
                                      time.monotonic() - started, model, finish)
            if actual > allowance:
                self.halted = True
                failure = ModelFailure("cost_exceeded_reservation")
        except Exception as exc:
            # Exception text can contain request headers; never serialize it.
            status = getattr(exc, "status_code", None)
            row.update(status="error", error_type=type(exc).__name__, http_status=status,
                       cost_usd=None, accounted_usd=round(allowance, 9))
            if status in (401, 402, 403) or isinstance(exc, ModelFailure):
                self.halted = True
            failure = ModelFailure(f"{type(exc).__name__}; http_status={status}")
        finally:
            row["latency_s"] = round(time.monotonic() - started, 4)
            with self.lock:
                self.reserved -= allowance
                self.spent += row["accounted_usd"]
                self.rows.append(row)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(canonical(row) + "\n")
        if failure:
            raise failure
        return result

    def totals(self, job_id=None):
        rows = [r for r in self.rows if job_id is None or r["job_id"] == job_id]
        return {"calls": len(rows),
                "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 6),
                "accounted_usd": round(sum(r["accounted_usd"] for r in rows), 6),
                "uncertain_billing_calls": sum(r.get("cost_usd") is None for r in rows),
                "latency_s": round(sum(r["latency_s"] for r in rows), 3),
                "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in rows),
                "completion_tokens": sum(r.get("completion_tokens", 0) for r in rows),
                "reasoning_tokens": sum(r.get("reasoning_tokens", 0) for r in rows)}


class BoundClient:
    def __init__(self, session, job_id, phase, attempt=0):
        self.session, self.job_id, self.phase, self.attempt = session, job_id, phase, attempt

    def chat(self, **kwargs):
        return self.session.chat(job_id=self.job_id, phase=self.phase,
                                 attempt=self.attempt, **kwargs)


class AlreadyMetered:
    def record(self, *args, **kwargs):
        pass


def interval(successes, n):
    """Wilson 95% interval; unavailable data stays null."""
    if not n:
        return None
    z = 1.959963984540054
    p, den = successes / n, 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def rate(successes, n):
    return {"successes": successes, "n": n, "rate": successes / n if n else None,
            "wilson_95": interval(successes, n)}
