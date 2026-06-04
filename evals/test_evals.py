"""
Pytest entry point for the eval harness — keeps the CLI in
`evals/run.py` and the pytest collection here.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.run import test_guardrail_eval  # noqa: F401  (re-export for collection)
