"""
Cloven eval harness.

Loads each JSON fixture in ./fixtures/ and asserts that the guardrail
classifies each `expected_llm_claim` exactly as the fixture predicts.
This is *not* an end-to-end test of the LLM (we don't want test
flakiness coupled to model behaviour) — it's a regression suite for
the deterministic guardrail across realistic UK financial scenarios.

Run with:
    pytest evals/

Or standalone for a CLI report:
    python -m evals.run
"""

import json
import sys
from pathlib import Path

import pytest

# Make project root importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guardrail import classify_claim  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures() -> list[dict]:
    fixtures: list[dict] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        with path.open() as f:
            fixtures.append(json.load(f))
    return fixtures


def _pairs() -> list[tuple[str, str, str]]:
    """Flatten fixtures into (fixture_id, claim, expected_class) triples."""
    out = []
    for fx in _load_fixtures():
        for claim, expected in fx["expected_verdicts"].items():
            out.append((fx["id"], claim, expected))
    return out


@pytest.mark.parametrize(
    "fixture_id,claim,expected",
    _pairs(),
    ids=[f"{fid}::{claim[:40]}" for fid, claim, _ in _pairs()],
)
def test_guardrail_eval(fixture_id, claim, expected):
    v = classify_claim(claim)
    assert v.classification == expected, (
        f"[{fixture_id}] expected '{expected}', got '{v.classification}' — "
        f"P={v.personal} S={v.specific_product} A={v.action} "
        f"(reason={v.reason_code})"
    )


def main() -> int:
    """CLI runner: prints a table and a pass/fail summary."""
    pairs = _pairs()
    fails = 0
    print(f"{'FIXTURE':<24} {'EXPECTED':<12} {'ACTUAL':<12} CLAIM")
    print("-" * 100)
    for fid, claim, expected in pairs:
        v = classify_claim(claim)
        mark = "✓" if v.classification == expected else "✗"
        if v.classification != expected:
            fails += 1
        print(f"{mark} {fid:<22} {expected:<12} {v.classification:<12} {claim[:60]}")
    total = len(pairs)
    print(f"\n{total - fails}/{total} passed, {fails} failed")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
