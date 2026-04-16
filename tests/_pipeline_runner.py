#!/usr/bin/env python3
"""Pipeline runner — parse a SKILL.md and execute its bash/python recipes.

This is a minimal parser + subprocess invoker for e2e testing of autopilot and ralph
SKILL.md files under OMNI_SUBAGENT_FAKE=1.  It is NOT a re-implementation of the
skills — it just extracts the shell code blocks and runs them in sequence via bash.

Usage:
    OMNI_SUBAGENT_FAKE=1 OMNI_SESSION_ID=<id> \\
        python3 tests/_pipeline_runner.py autopilot "fix the login bug"

    OMNI_SUBAGENT_FAKE=1 OMNI_SESSION_ID=<id> \\
        python3 tests/_pipeline_runner.py ralph "add error handling"
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"

# Banned primitives — the runner asserts none exist before executing
_BANNED_PRIMITIVES: tuple[str, ...] = (
    r"Task\s*\(",
    r"Skill\s*\(",
    r"AskUserQuestion\s*\(",
    r"SendMessage\s*\(",
    r"TeamCreate\s*\(",
    r"TeamDelete\s*\(",
)

# ---------------------------------------------------------------------------
# Parser: extract bash code blocks from SKILL.md
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(\w*)\s*$", re.MULTILINE)
_BANNED_RE = re.compile("|".join(_BANNED_PRIMITIVES))


def extract_bash_blocks(skill_md: str) -> list[str]:
    """Return a list of bash/shell code blocks from the skill markdown.

    Only blocks fenced with ```bash, ```sh, or ``` (no language) are returned.
    Python heredoc blocks embedded inside bash (<<'PYEOF') are kept as-is since
    they are part of the bash script.
    """
    blocks: list[str] = []
    lines = skill_md.splitlines()
    i = 0
    in_block = False
    lang = ""
    current: list[str] = []

    while i < len(lines):
        line = lines[i]
        m = _FENCE_RE.match(line)
        if m and not in_block:
            lang = m.group(1).lower()
            if lang in ("bash", "sh", ""):
                in_block = True
                current = []
        elif in_block and line.strip() == "```":
            in_block = False
            if current:
                blocks.append("\n".join(current))
            current = []
        elif in_block:
            current.append(line)
        i += 1

    return blocks


def check_no_banned_primitives(skill_path: Path) -> list[str]:
    """Scan the SKILL.md for banned Claude primitives outside of code fences.

    Returns a list of violation strings (empty = clean).
    """
    text = skill_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    violations: list[str] = []
    in_fence = False

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        if not in_fence and _BANNED_RE.search(line):
            violations.append(f"  {skill_path.name}:{lineno}: {line.strip()[:120]}")

    return violations


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_skill(
    skill_name: str,
    prompt: str,
    *,
    session_id: Optional[str] = None,
    env_overrides: Optional[dict] = None,
    fake_sleep_secs: float = 0.05,
    stop_on_phase: Optional[int] = None,
) -> "RunResult":
    """Execute the bash blocks from a SKILL.md in sequence.

    Parameters
    ----------
    skill_name:
        Name of the skill directory under skills/ (e.g. "autopilot", "ralph").
    prompt:
        The {{PROMPT}} substitution value.
    session_id:
        OMNI_SESSION_ID to use; generated if not provided.
    env_overrides:
        Additional env vars to inject (merged over os.environ).
    fake_sleep_secs:
        OMNI_SUBAGENT_FAKE_SLEEP_SECS — keep tiny for tests.
    stop_on_phase:
        If set, stop execution after completing this many bash blocks (for
        partial-run tests, e.g. to simulate a mid-phase kill).
    """
    import uuid
    skill_path = _SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

    skill_md = skill_path.read_text(encoding="utf-8", errors="replace")

    # Primitive check before execution
    violations = check_no_banned_primitives(skill_path)

    session_id = session_id or str(uuid.uuid4())
    blocks = extract_bash_blocks(skill_md)

    env = dict(os.environ)
    env["OMNI_SUBAGENT_FAKE"] = "1"
    env["OMNI_SUBAGENT_FAKE_SLEEP_SECS"] = str(fake_sleep_secs)
    env["OMNI_SESSION_ID"] = session_id
    # Point scripts/ to the repo root
    env.setdefault("PYTHONPATH", str(_REPO_ROOT))
    if env_overrides:
        env.update(env_overrides)

    # Build a combined script with {{PROMPT}} substituted
    combined_lines: list[str] = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"export OMNI_SUBAGENT_FAKE=1",
        f"export OMNI_SUBAGENT_FAKE_SLEEP_SECS={fake_sleep_secs}",
        f'export OMNI_SESSION_ID="{session_id}"',
        f"cd {_REPO_ROOT}",
        "",
    ]

    n_blocks = len(blocks) if stop_on_phase is None else stop_on_phase
    executed_blocks: list[str] = []

    for idx, block in enumerate(blocks[:n_blocks]):
        # Replace {{PROMPT}} with the actual prompt (escaped for bash)
        safe_prompt = prompt.replace("'", "'\\''")
        block_subst = block.replace("{{PROMPT}}", safe_prompt)
        combined_lines.append(f"# --- Block {idx} ---")
        combined_lines.append(block_subst)
        combined_lines.append("")
        executed_blocks.append(block_subst)

    script = "\n".join(combined_lines)

    # Write to a temp file and execute
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(script)
        tmp_path = tf.name

    try:
        result = subprocess.run(
            ["bash", tmp_path],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(_REPO_ROOT),
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            skill_name=skill_name,
            session_id=session_id,
            exit_code=124,
            stdout="",
            stderr=f"timeout: {exc}",
            blocks_executed=executed_blocks,
            primitive_violations=violations,
            error="timeout",
        )
    finally:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass

    return RunResult(
        skill_name=skill_name,
        session_id=session_id,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        blocks_executed=executed_blocks,
        primitive_violations=violations,
    )


class RunResult:
    """Result of a pipeline run."""

    def __init__(
        self,
        skill_name: str,
        session_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        blocks_executed: list[str],
        primitive_violations: list[str],
        error: str = "",
    ):
        self.skill_name = skill_name
        self.session_id = session_id
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.blocks_executed = blocks_executed
        self.primitive_violations = primitive_violations
        self.error = error
        self.run_dir = (
            _REPO_ROOT / ".omni" / "runs" / f"{skill_name}-{session_id}"
        )

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    def phase_status(self, phase_n: int) -> dict | None:
        """Read phase-N/status.json from the run-dir. Returns None if absent."""
        import json
        p = self.run_dir / f"phase-{phase_n}" / "status.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def iteration_status(self, iteration_n: int) -> dict | None:
        """Read iteration-N/status.json. Returns None if absent."""
        import json
        p = self.run_dir / f"iteration-{iteration_n}" / "status.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def __repr__(self) -> str:
        return (
            f"RunResult(skill={self.skill_name}, session={self.session_id}, "
            f"exit={self.exit_code}, blocks={len(self.blocks_executed)}, "
            f"primitives={len(self.primitive_violations)})"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a SKILL.md recipe via bash for e2e testing"
    )
    parser.add_argument("skill", help="Skill name (autopilot, ralph, ...)")
    parser.add_argument("prompt", help="Task prompt ({{PROMPT}} substitution)")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--fake-sleep", type=float, default=0.05)
    parser.add_argument("--stop-on-block", type=int, default=None,
                        help="Stop after N bash blocks (for partial-run tests)")
    args = parser.parse_args(argv)

    result = run_skill(
        args.skill,
        args.prompt,
        session_id=args.session_id,
        fake_sleep_secs=args.fake_sleep,
        stop_on_phase=args.stop_on_block,
    )

    print(f"\n{'='*60}")
    print(f"Skill:    {result.skill_name}")
    print(f"Session:  {result.session_id}")
    print(f"Exit:     {result.exit_code}")
    print(f"Run dir:  {result.run_dir}")
    print(f"Blocks:   {len(result.blocks_executed)}")
    if result.primitive_violations:
        print(f"\nBANNED PRIMITIVES ({len(result.primitive_violations)}):")
        for v in result.primitive_violations:
            print(v)
    if result.stdout:
        print(f"\n--- stdout ---\n{result.stdout[-2000:]}")
    if result.stderr:
        print(f"\n--- stderr ---\n{result.stderr[-1000:]}")

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
