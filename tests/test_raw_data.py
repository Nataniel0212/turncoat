"""The published tables must be recomputable from the checked-in campaign data."""
import importlib.util
import json
from pathlib import Path

import pytest

from sieve.replays import MARK, public_recording

ROOT = Path(__file__).resolve().parents[1]


def _export():
    spec = importlib.util.spec_from_file_location("export_raw_under_test", ROOT / "scripts/export_raw.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["replication-2026-10-16", "compare-2026-10-15"])
def test_raw_campaigns_reproduce_published_tables(name):
    export = _export()
    lines = (ROOT / "results/raw" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    campaigns = [json.loads(line) for line in lines]
    assert len({c["campaign"] for c in campaigns}) == len(campaigns)
    export.check(name, campaigns)  # every k/n, technique count, mean and cost


def test_redaction_masks_invented_tokens_but_keeps_fixtures_and_words():
    # Assembled at runtime so this test does not itself resemble a leaked key.
    invented = "0x7F4A" + "9C2E-11B8-4C2D"
    text = (f"AUTH TOKEN: {invented} then key: transfer_funds; "
            "secret value: SYNTHETIC-SECRET-7Q2X9")
    out = public_recording({"events": [{"text": text}]})
    cleaned = out["events"][0]["text"]
    assert invented not in cleaned and MARK in cleaned
    assert "key: transfer_funds" in cleaned
    assert "SYNTHETIC-SECRET-7Q2X9" in cleaned
    assert out["redactions"] == 1
    assert public_recording(out) == out
