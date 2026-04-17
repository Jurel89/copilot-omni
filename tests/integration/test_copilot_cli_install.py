"""Local-only Copilot CLI + plugin integration smoke.

This test is intentionally excluded from every CI workflow. It shells out to
scripts/integration_test_local.py which installs the copilot CLI if missing
and exercises the shipped plugin surface against a real copilot binary.

Run manually: `python3 -m pytest -m integration_local -q`
Or directly:  `./scripts/itest`
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration_local
def test_harness_runs_clean():
    harness = REPO_ROOT / "scripts" / "integration_test_local.py"
    assert harness.exists(), f"Missing {harness}"
    result = subprocess.run(
        [sys.executable, str(harness)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    # The harness exits 0 on both "all pass" and "tier-1 pass + tier-2 skipped".
    # Any failure should surface the full log to help debug.
    if result.returncode != 0:
        log_path = REPO_ROOT / ".omni" / "integration-test" / "last-run.log"
        log_tail = log_path.read_text()[-4000:] if log_path.exists() else "(no log)"
        pytest.fail(
            f"Harness failed (exit {result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
            f"log tail:\n{log_tail}"
        )
