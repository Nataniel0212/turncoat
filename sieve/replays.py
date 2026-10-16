"""Prepare synthetic traces for publication without credential-shaped strings.

The attacker can invent an API-key-looking token in its text. Such text is not
needed for the state verdict and triggers hosting secret scanners. Disclose its
redaction in recording metadata; keep tool state, synthetic fixture tokens and
all metered numbers intact.
"""
from __future__ import annotations

import math
import re
from collections import Counter

MARK = "[REDACTED SYNTHETIC TOKEN]"
_CREDENTIAL = re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9_]{12,}\b")
# "AUTH TOKEN: 0x7F4A9C2E-..." style values, the shape secret scanners' generic
# API-key rule flags. Only the value is replaced, and only when it looks random.
_LABELLED = re.compile(
    r"(?i)(?:access|auth|api|credential|creds|key|passw(?:or)?d|secret|token)"
    r"[ \t\w.-]{0,20}[\s'\"]{0,3}(?:=|>|:{1,3}=|\|\||:|=>|\?=|,)[`'\"\s=]{0,5}"
    r"([\w.=-]{10,150})(?=[`'\"\s;]|$)")


def _entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def _labelled(match: re.Match) -> str:
    value = match.group(1)
    if value.upper().startswith("SYNTHETIC-"):  # the scenarios' own fixture tokens
        return match.group(0)
    if any(ch.isdigit() for ch in value) and _entropy(value) >= 3.5:
        return match.group(0)[:match.start(1) - match.start(0)] + MARK
    return match.group(0)


def public_recording(recording: dict) -> dict:
    count = 0

    def clean(value):
        nonlocal count
        if isinstance(value, str):
            value, n = _CREDENTIAL.subn(MARK, value)
            labelled = _LABELLED.sub(_labelled, value)
            n += labelled.count(MARK) - value.count(MARK)
            count += n
            return labelled
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    result = clean(recording)
    if count:
        result["redactions"] = count
        result["redaction_note"] = "Credential-shaped strings invented in the synthetic attack text are redacted. Timings, usage and verdicts are unchanged."
    return result
