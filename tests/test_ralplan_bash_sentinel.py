"""Phase-C C10 + C31: real-bash regression for the ralplan clarifying-question
sentinel-file pattern.

This test extracts the new sentinel-driven block from skills/ralplan/SKILL.md
and runs it under a real /bin/bash so we catch the exact shell behaviour that
the old 'if python3 - <<PYEOF … PYEOF then' pattern depended on.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

pytestmark_slow = "pytest.mark.slow"  # informational; marker applied via pytest.ini


SCRIPT = r"""
set -euo pipefail

RUN_DIR="$1"
PLAN_FILE="$2"

CLARIFY_SENTINEL="${RUN_DIR}/_clarify_check.py"
cat > "${CLARIFY_SENTINEL}" <<'PYEOF'
import os, re, sys, json
from pathlib import Path

raw = Path(os.environ["PLAN_FILE"] + ".raw")
text = raw.read_text(errors="replace") if raw.exists() else ""
m = re.search(r"<clarifying-question>(.*?)</clarifying-question>", text, re.DOTALL)
if m:
    question = m.group(1).strip()
    run_dir = Path(os.environ["RUN_DIR"])
    (run_dir / "pending-question.md").write_text(question)
    status_path = run_dir / "status.json"
    try:
        status = json.loads(status_path.read_text())
    except Exception:
        status = {}
    status["state"] = "awaiting-input"
    tmp = status_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2))
    os.replace(str(tmp), str(status_path))
    print("ralplan: planner asked a clarifying question — state=awaiting-input")
    print(f"Question: {question}")
    sys.exit(0)
sys.exit(1)
PYEOF

if RUN_DIR="${RUN_DIR}" PLAN_FILE="${PLAN_FILE}" python3 "${CLARIFY_SENTINEL}"; then
    rm -f "${CLARIFY_SENTINEL}"
    echo "branch=question"
    exit 0
fi
rm -f "${CLARIFY_SENTINEL}"
echo "branch=continue"
"""


@unittest.skipUnless(shutil.which("bash"), "bash required")
class TestRalplanBashSentinel(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.plan = self.run_dir / "plan.md"
        (self.run_dir / "status.json").write_text(json.dumps({"state": "planning"}))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self) -> subprocess.CompletedProcess:
        script_path = Path(self.tmp.name) / "driver.sh"
        script_path.write_text(SCRIPT)
        return subprocess.run(
            ["bash", str(script_path), str(self.run_dir), str(self.plan)],
            capture_output=True, text=True, timeout=30,
        )

    def test_question_branch(self):
        raw = self.plan.with_suffix(self.plan.suffix + ".raw")
        raw.write_text("blah\n<clarifying-question>What's the deadline?</clarifying-question>\nmore")
        result = self._run()
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("branch=question", result.stdout)
        pending = self.run_dir / "pending-question.md"
        self.assertTrue(pending.exists())
        self.assertIn("deadline", pending.read_text())
        status = json.loads((self.run_dir / "status.json").read_text())
        self.assertEqual(status["state"], "awaiting-input")

    def test_continue_branch(self):
        raw = self.plan.with_suffix(self.plan.suffix + ".raw")
        raw.write_text("plan body with no question")
        result = self._run()
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("branch=continue", result.stdout)
        self.assertFalse((self.run_dir / "pending-question.md").exists())

    def test_missing_raw_file_continues(self):
        # No plan_file.raw exists at all; the sentinel must treat that as
        # "no question" rather than crashing.
        result = self._run()
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("branch=continue", result.stdout)

    def test_sentinel_file_cleaned_up(self):
        raw = self.plan.with_suffix(self.plan.suffix + ".raw")
        raw.write_text("plan body")
        self._run()
        self.assertFalse((self.run_dir / "_clarify_check.py").exists())

    def test_skill_md_has_new_pattern(self):
        """Regression: the Critic P10 shell-if heredoc must not return.

        We strip the migration comment block before searching — the comment
        legitimately names the banned pattern as the thing we replaced.
        """
        text = (ROOT / "skills" / "ralplan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("CLARIFY_SENTINEL", text)
        # Drop the commentary lines so the literal reference in the explanation
        # isn't mistaken for the bug returning.
        code_only = "\n".join(
            line for line in text.splitlines()
            if 'shell-if heredoc pattern' not in line
               and '"if python3 - <<PYEOF ... PYEOF then"' not in line
        )
        self.assertNotIn('if python3 - <<PYEOF', code_only)


if __name__ == "__main__":
    unittest.main()
