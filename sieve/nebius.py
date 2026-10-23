"""Nebius Token Factory client (OpenAI-compatible).

All LLM traffic goes directly to Token Factory — never through any gateway.
Handles the documented Nemotron/Token Factory quirks:
  * tool-call XML can leak into content -> sanitize several formats out
  * reasoning toggled via extra_body.chat_template_kwargs.enable_thinking
  * force_nonempty_content for agent calls
  * tool-call arguments parsed back into a dict (object, not JSON string)
  * usage may be missing -> defaults to zeros
  * transient errors retried with backoff; HTTP 402 -> PaymentRequiredError
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from .errors import PaymentRequiredError

# Strip the different shapes a leaked tool call can take in `content`.
_TOOLCALL_PATTERNS = [
    re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\|tool_call\|>.*?(<\|/tool_call\|>|$)", re.DOTALL | re.IGNORECASE),
    re.compile(r"\[TOOL_CALL\].*?(\[/TOOL_CALL\]|$)", re.DOTALL | re.IGNORECASE),
    re.compile(r"<tool_call>.*$", re.DOTALL | re.IGNORECASE),  # unclosed tail
]

_RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
_RETRY_NAMES = {"APITimeoutError", "APIConnectionError",
                "InternalServerError", "RateLimitError"}


def sanitize(content: str | None) -> str:
    if not content:
        return ""
    text = content
    for pat in _TOOLCALL_PATTERNS:
        text = pat.sub("", text)
    return text.strip()


def _classify_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 402:
        return "payment"
    if status in _RETRY_STATUS or type(exc).__name__ in _RETRY_NAMES:
        return "retry"
    return "fatal"


@dataclass
class LLMResult:
    content: str
    tool_calls: list  # [{"id", "name", "args": dict}]
    usage: dict       # prompt_tokens, completion_tokens, reasoning_tokens
    latency_s: float
    model: str


class LiveClient:
    """Thin wrapper over the OpenAI SDK pointed at Token Factory."""

    def __init__(self, cfg, max_retries: int = 3, backoff_s: float = 1.0) -> None:
        from openai import OpenAI  # imported lazily so dry-run needs no dep
        # Keep an abandoned browser request from holding a serverless worker and
        # real API credit forever. Retries remain ours so metering sees each call.
        self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key,
                              timeout=getattr(cfg, "request_timeout_s", 60.0),
                              max_retries=0)
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._fallback = getattr(cfg, "model_fallback", "") or ""

    def chat(self, model, messages, tools=None, max_tokens=8192,
             enable_thinking=False, force_nonempty=False,
             temperature=None) -> LLMResult:
        extra_body: dict = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        if force_nonempty:
            extra_body["force_nonempty_content"] = True

        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                      extra_body=extra_body)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if temperature is not None:
            kwargs["temperature"] = temperature

        for i in range(self._max_retries + 1):
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 - classify then re-raise
                kind = _classify_error(exc)
                if kind == "payment":
                    raise PaymentRequiredError(str(exc)) from exc
                if kind == "retry" and i < self._max_retries:
                    time.sleep(self._backoff_s * (2 ** i))
                    continue
                if self._fallback and model != self._fallback:
                    # The model is unavailable: degrade once to the fallback. The
                    # metered row carries the model that actually answered.
                    return self.chat(self._fallback, messages, tools=tools,
                                     max_tokens=max_tokens,
                                     enable_thinking=enable_thinking,
                                     force_nonempty=force_nonempty,
                                     temperature=temperature)
                raise
            return self._parse(resp, model, time.time() - t0)
        raise RuntimeError("unreachable")  # pragma: no cover

    @staticmethod
    def _parse(resp, model, latency) -> LLMResult:
        msg = resp.choices[0].message
        tool_calls = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})

        u = getattr(resp, "usage", None)
        details = getattr(u, "completion_tokens_details", None)
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
            "reasoning_tokens": getattr(details, "reasoning_tokens", 0) or 0,
        }
        return LLMResult(sanitize(msg.content), tool_calls, usage, latency, model)
