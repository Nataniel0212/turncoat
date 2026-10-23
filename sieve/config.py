"""Configuration and environment loading.

No secrets live in code. Keys come from the environment or a local .env file
(which is git-ignored). Model ids are configurable so they can be swapped
without a code change, with a fallback chain (Ultra -> Lightning).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so dry-run needs no third-party dependency.

    Only sets keys that are not already present in the real environment.
    """
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"'):
            value = value.strip('"').strip("'")
        elif value.startswith("#"):  # empty value followed by a comment
            value = ""
        elif " #" in value:  # unquoted inline comment
            value = value.split(" #", 1)[0].strip()
        key = key.strip()
        os.environ.setdefault(key, value)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    api_key: str
    base_url: str
    model_attacker: str
    model_target: str
    max_attempts: int
    budget_usd: float
    live: bool
    # Optional resilience fallback (e.g. Ultra -> Lightning) for the hosted demo.
    # Off by default so benchmark numbers are always on the named model.
    model_fallback: str = ""
    request_timeout_s: float = 60.0

    @classmethod
    def from_env(cls, live: bool, max_attempts: int | None = None,
                 budget_usd: float | None = None) -> "Config":
        load_dotenv()
        return cls(
            api_key=os.environ.get("NEBIUS_API_KEY", ""),
            base_url=os.environ.get("NEBIUS_BASE_URL",
                                    "https://api.tokenfactory.nebius.com/v1"),
            model_attacker=os.environ.get("MODEL_ATTACKER",
                                          "nvidia/Nemotron-3-Ultra-550b-a55b"),
            model_target=os.environ.get("MODEL_TARGET",
                                         "nvidia/Nemotron-3_5-Lightning"),
            max_attempts=max_attempts if max_attempts is not None
            else _env_int("MAX_ATTEMPTS", 10),
            budget_usd=budget_usd if budget_usd is not None
            else _env_float("BUDGET_USD", 3.00),
            live=live,
            model_fallback=os.environ.get("MODEL_FALLBACK", ""),
            request_timeout_s=max(1.0, _env_float("NEBIUS_TIMEOUT_S", 60.0)),
        )

    def require_live_ready(self) -> None:
        if not self.api_key:
            raise SystemExit(
                "NEBIUS_API_KEY is not set. Copy .env.example to .env and fill "
                "it in, or run without --live for an offline dry-run."
            )
