#!/usr/bin/env python3
"""Local Copilot CLI + plugin integration test harness.

Two-tier design:
  Tier 1 — No auth required.  Preflight checks + omni doctor + MCP smoke +
            discovery smoke + verify_plugin_contract --all.  Always runs.
  Tier 2 — Auth required.  Trial-mode plugin load + slash-command probe +
            hook audit check.  Skipped cleanly when auth is absent.

Exit codes:
  0 — Tier 1 all passed AND (Tier 2 all passed OR Tier 2 cleanly skipped).
  1 — Any real failure.

Log: .omni/integration-test/last-run.log (append, timestamped header).
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_PYTHON = (3, 9)
COPILOT_NPM_PACKAGE = "@github/copilot"
AUTH_PROBE_TIMEOUT = 30   # seconds
PLUGIN_LOAD_TIMEOUT = 60  # seconds
AUTH_MISSING_KEYWORDS = ("login", "authenticate", "unauthorized", "sign in")
# Copilot CLI surfaces quota exhaustion with phrases like "You have no quota"
# or "quota exceeded" or "rate limit". When we see these in Tier 2, the user's
# subscription bucket is empty — not a plugin bug — so we SKIP downstream
# Tier 2 steps rather than FAIL.
QUOTA_EXHAUSTED_KEYWORDS = ("no quota", "quota exceeded", "rate limit", "quota limit")
_quota_exhausted = False

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_steps: list[tuple[str, str, str]] = []  # (name, status, note)
_log_lines: list[str] = []


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _log(msg: str) -> None:
    line = f"[{_ts()}] {msg}"
    _log_lines.append(line)
    print(line)


def _record(name: str, status: str, note: str = "") -> None:
    _steps.append((name, status, note))
    symbol = {"PASS": "+", "FAIL": "X", "SKIP": "-"}.get(status, "?")
    _log(f"  [{symbol}] {name}" + (f" — {note}" if note else ""))


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    stdin_devnull: bool = False,
) -> tuple[int, str, str]:
    """Run *cmd*, return (returncode, stdout, stderr). Never raises on non-zero."""
    kwargs: dict = dict(
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )
    if stdin_devnull:
        kwargs["stdin"] = subprocess.DEVNULL
    try:
        r = subprocess.run(cmd, **kwargs)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT after {timeout}s"
    except FileNotFoundError:
        return -2, "", f"command not found: {cmd[0]}"
    except Exception as exc:  # noqa: BLE001
        return -3, "", str(exc)


def _tail(text: str, n: int = 200) -> str:
    return text[-n:] if len(text) > n else text


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------
def _find_repo_root() -> Path | None:
    """Walk upward from this script's location to find the repo root."""
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / ".claude-plugin" / "plugin.json").exists() and (
        candidate / "scripts" / "omni.py"
    ).exists():
        return candidate
    return None


# ---------------------------------------------------------------------------
# Tier 1 helpers
# ---------------------------------------------------------------------------
def preflight_copilot() -> bool:
    """Ensure `copilot` binary is available; install via npm if missing."""
    _log("Tier 1 / Step 1: preflight copilot binary")
    rc, out, err = _run(["copilot", "--version"])
    if rc == 0:
        version = (out + err).strip().splitlines()[0] if (out + err).strip() else "(unknown)"
        _record("copilot --version", PASS, version)
        return True

    # Binary missing — try npm install
    if rc == -2:
        _log("  copilot not found; attempting npm install -g " + COPILOT_NPM_PACKAGE)
        _log("  WARNING: This will modify npm's global install prefix. On "
             "corporate machines where the global prefix is a system directory "
             "(e.g. /usr/lib/node_modules) this will either fail with a "
             "permission error or require sudo. If the install fails, either "
             "configure a user-writable prefix (npm config set prefix "
             "~/.npm-global) or install copilot manually, then re-run.")
        npm = shutil.which("npm")
        if not npm:
            _record(
                "copilot binary",
                FAIL,
                "copilot not found and npm is not on PATH. "
                "Install Node.js ≥ 18 then re-run: npm install -g " + COPILOT_NPM_PACKAGE,
            )
            return False

        rc2, out2, err2 = _run(
            [npm, "install", "-g", COPILOT_NPM_PACKAGE], timeout=180
        )
        _log(f"  npm install exit={rc2}")
        _log(f"  npm stdout (tail): {_tail(out2)}")
        _log(f"  npm stderr (tail): {_tail(err2)}")
        if rc2 != 0:
            _record(
                "copilot install",
                FAIL,
                f"npm install -g {COPILOT_NPM_PACKAGE} failed (exit {rc2}). "
                f"stderr tail: {_tail(err2, 120)}",
            )
            return False

        # Verify again after install
        rc3, out3, err3 = _run(["copilot", "--version"])
        if rc3 != 0:
            _record(
                "copilot --version (post-install)",
                FAIL,
                "copilot still not found after npm install. "
                "Restart your shell or add npm global bin to PATH.",
            )
            return False
        version = (out3 + err3).strip().splitlines()[0] if (out3 + err3).strip() else "(unknown)"
        _record("copilot --version (post-install)", PASS, version)
        return True

    # Some other error (permission, etc.)
    _record("copilot --version", FAIL, f"exit {rc}: {_tail(err)}")
    return False


def preflight_python() -> bool:
    _log("Tier 1 / Step 2: preflight Python ≥ 3.9")
    v = sys.version_info[:2]
    if v >= MIN_PYTHON:
        _record("python3 version", PASS, f"{sys.version.split()[0]}")
        return True
    _record(
        "python3 version",
        FAIL,
        f"found {v[0]}.{v[1]}, need ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
    )
    return False


def preflight_repo(repo_root: Path | None) -> bool:
    _log("Tier 1 / Step 3: preflight repo layout")
    if repo_root is None:
        _record(
            "repo layout",
            FAIL,
            "Not inside a copilot-omni checkout "
            "(missing .claude-plugin/plugin.json or scripts/omni.py). "
            "Run this script from within the cloned repository.",
        )
        return False
    _record("repo layout", PASS, str(repo_root))
    return True


def run_omni_doctor(repo_root: Path) -> bool:
    _log("Tier 1 / Step 4: python3 scripts/omni.py doctor")
    rc, out, err = _run(
        [sys.executable, str(repo_root / "scripts" / "omni.py"), "doctor"],
        cwd=repo_root,
        timeout=60,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    if rc == 0:
        _record("omni.py doctor", PASS)
        return True
    _record("omni.py doctor", FAIL, f"exit {rc}  output: {_tail(combined, 300)}")
    return False


def run_mcp_smoke(repo_root: Path) -> bool:
    _log("Tier 1 / Step 5: python3 scripts/mcp_smoke.py")
    rc, out, err = _run(
        [sys.executable, str(repo_root / "scripts" / "mcp_smoke.py")],
        cwd=repo_root,
        timeout=60,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    if rc == 0:
        _record("mcp_smoke.py", PASS)
        return True
    _record("mcp_smoke.py", FAIL, f"exit {rc}  output: {_tail(combined, 300)}")
    return False


def run_discovery_smoke(repo_root: Path) -> bool:
    _log("Tier 1 / Step 6: python3 scripts/discovery_smoke.py --probe layout")
    rc, out, err = _run(
        [sys.executable, str(repo_root / "scripts" / "discovery_smoke.py"), "--probe", "layout"],
        cwd=repo_root,
        timeout=60,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    if rc == 0:
        _record("discovery_smoke.py --probe layout", PASS)
        return True
    _record("discovery_smoke.py --probe layout", FAIL, f"exit {rc}  output: {_tail(combined, 300)}")
    return False


def run_contract_validator(repo_root: Path) -> bool:
    _log("Tier 1 / Step 7: python3 scripts/verify_plugin_contract.py --all")
    rc, out, err = _run(
        [sys.executable, str(repo_root / "scripts" / "verify_plugin_contract.py"), "--all"],
        cwd=repo_root,
        timeout=120,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    if rc == 0:
        _record("verify_plugin_contract.py --all", PASS)
        return True
    _record(
        "verify_plugin_contract.py --all",
        FAIL,
        f"exit {rc}  output: {_tail(combined, 400)}",
    )
    return False


# ---------------------------------------------------------------------------
# Tier 2 helpers
# ---------------------------------------------------------------------------
def probe_auth() -> bool:
    """Return True if copilot appears authenticated."""
    _log("Tier 2 / Step 8: auth probe")
    rc, out, err = _run(
        ["copilot", "-p", "print ok", "--allow-all"],
        timeout=AUTH_PROBE_TIMEOUT,
        stdin_devnull=True,
    )
    combined = (out + err).lower()
    if rc != 0 or any(kw in combined for kw in AUTH_MISSING_KEYWORDS):
        _log(f"  auth probe: exit={rc}, auth appears absent")
        return False
    _log(f"  auth probe: exit={rc}, auth present")
    return True


def run_plugin_load(repo_root: Path, workdir: Path) -> bool:
    global _quota_exhausted
    _log("Tier 2 / Step 10: trial-mode plugin load")
    # Use --plugin-dir rather than marketplace install because the branch is
    # not necessarily pushed to GitHub at the time the harness is run locally.
    rc, out, err = _run(
        [
            "copilot",
            "--plugin-dir", str(repo_root),
            "-p", "say: copilot-omni loaded",
            "--allow-all",
        ],
        cwd=workdir,
        timeout=PLUGIN_LOAD_TIMEOUT,
        stdin_devnull=True,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    combined_lower = combined.lower()
    if any(kw in combined_lower for kw in QUOTA_EXHAUSTED_KEYWORDS):
        _quota_exhausted = True
        _record(
            "plugin load (trial-mode)",
            SKIP,
            f"Copilot subscription quota exhausted — tail: {_tail(combined, 160)}",
        )
        return True
    if rc != 0:
        _record("plugin load (trial-mode)", FAIL, f"exit {rc}  tail: {_tail(combined, 200)}")
        return False
    loader_errors = ("failed to parse plugin.json", "plugin load error", "failed to load plugin")
    combined_lower = combined.lower()
    for err_substr in loader_errors:
        if err_substr in combined_lower:
            _record("plugin load (trial-mode)", FAIL, f"loader error detected: {err_substr!r}")
            return False
    _record("plugin load (trial-mode)", PASS)
    return True


def run_skill_probe(repo_root: Path, workdir: Path) -> bool:
    """Invoke /copilot-omni:omni-status (lightest command in commands/)."""
    global _quota_exhausted
    _log("Tier 2 / Step 11: trivial skill probe (/copilot-omni:omni-status)")
    if _quota_exhausted:
        _record(
            "skill probe /copilot-omni:omni-status",
            SKIP,
            "skipped — upstream step already detected Copilot quota exhaustion",
        )
        return True
    rc, out, err = _run(
        [
            "copilot",
            "--plugin-dir", str(repo_root),
            "-p", "/copilot-omni:omni-status",
            "--allow-all",
        ],
        cwd=workdir,
        timeout=PLUGIN_LOAD_TIMEOUT,
        stdin_devnull=True,
    )
    combined = out + err
    _log(f"  exit={rc}  tail: {_tail(combined)}")
    combined_lower = combined.lower()
    if any(kw in combined_lower for kw in QUOTA_EXHAUSTED_KEYWORDS):
        _quota_exhausted = True
        _record(
            "skill probe /copilot-omni:omni-status",
            SKIP,
            f"Copilot subscription quota exhausted — tail: {_tail(combined, 160)}",
        )
        return True
    if rc != 0:
        _record("skill probe /copilot-omni:omni-status", FAIL, f"exit {rc}  tail: {_tail(combined, 200)}")
        return False
    if not combined.strip():
        _record("skill probe /copilot-omni:omni-status", FAIL, "no output returned")
        return False
    skill_errors = ("skill registration error", "failed to register", "skill not found")
    combined_lower = combined.lower()
    for e in skill_errors:
        if e in combined_lower:
            _record("skill probe /copilot-omni:omni-status", FAIL, f"skill error: {e!r}")
            return False
    _record("skill probe /copilot-omni:omni-status", PASS, f"output len={len(combined.strip())}")
    return True


def run_hook_audit_check(workdir: Path) -> bool:
    _log("Tier 2 / Step 12: hook audit check")
    if _quota_exhausted:
        _record(
            "hook audit dir",
            SKIP,
            "skipped — skill probe hit quota exhaustion, copilot never reached hook-firing stage",
        )
        return True
    audit_dir = workdir / ".omni" / "audit"
    hooks_log = audit_dir / "hooks.jsonl"
    if not audit_dir.exists():
        _record(
            "hook audit dir",
            FAIL,
            f"{audit_dir} does not exist after copilot invocation — "
            "session_start hook did not fire. This is a real bug.",
        )
        return False
    if not hooks_log.exists():
        _record(
            "hook audit hooks.jsonl",
            FAIL,
            f"{hooks_log} not found. Hook events are not being written.",
        )
        return False
    lines = [l for l in hooks_log.read_text(errors="replace").splitlines() if l.strip()]
    if len(lines) < 1:
        _record("hook audit hooks.jsonl", FAIL, "file is empty — no hook events recorded")
        return False
    _record("hook audit hooks.jsonl", PASS, f"{len(lines)} entries")
    return True


# ---------------------------------------------------------------------------
# Log flush
# ---------------------------------------------------------------------------
def _flush_log(repo_root: Path) -> None:
    log_dir = repo_root / ".omni" / "integration-test"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "last-run.log"
    header = f"\n{'='*72}\n Integration test run — {_ts()}\n{'='*72}\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(header)
        for line in _log_lines:
            fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def _print_summary() -> None:
    print()
    print("=" * 60)
    print("  INTEGRATION TEST SUMMARY")
    print("=" * 60)
    for name, status, note in _steps:
        symbol = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}.get(status, status)
        line = f"  [{symbol}]  {name}"
        if note:
            # Wrap long notes
            wrapped = textwrap.fill(note, width=72, subsequent_indent=" " * 11)
            print(f"{line}")
            print(f"           {wrapped}")
        else:
            print(line)
    print("-" * 60)
    failed = [n for n, s, _ in _steps if s == FAIL]
    skipped = [n for n, s, _ in _steps if s == SKIP]
    passed = [n for n, s, _ in _steps if s == PASS]
    print(f"  Passed:  {len(passed)}   Skipped: {len(skipped)}   Failed: {len(failed)}")
    if failed:
        print(f"\n  FAILED steps: {', '.join(failed)}")
        print("\n  Overall: FAIL")
    else:
        print("\n  Overall: PASS")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    _log("copilot-omni local integration test harness starting")
    _log(f"Python {sys.version}  Platform: {platform.system()} {platform.release()}")

    repo_root = _find_repo_root()

    # ---- Tier 1 ----
    _log("")
    _log("=== TIER 1: No auth required ===")

    t1_ok = True
    t1_ok &= preflight_copilot()
    t1_ok &= preflight_python()
    t1_ok &= preflight_repo(repo_root)

    if not t1_ok or repo_root is None:
        _log("Tier 1 preflight failed — aborting.")
        _print_summary()
        _flush_log(repo_root or Path.cwd())
        return 1

    t1_ok &= run_omni_doctor(repo_root)
    t1_ok &= run_mcp_smoke(repo_root)
    t1_ok &= run_discovery_smoke(repo_root)
    t1_ok &= run_contract_validator(repo_root)

    if not t1_ok:
        _log("Tier 1 FAILED — skipping Tier 2.")
        _print_summary()
        _flush_log(repo_root)
        return 1

    _log("Tier 1 complete — all steps passed.")

    # ---- Tier 2 ----
    _log("")
    _log("=== TIER 2: Auth required ===")

    auth_present = probe_auth()
    if not auth_present:
        _record("Tier 2 (auth)", SKIP, "copilot auth session absent — run `copilot auth login` to enable Tier 2")
        _log("Tier 2 skipped cleanly (no auth). Tier 1 passed. Overall: PASS.")
        _print_summary()
        _flush_log(repo_root)
        return 0

    # Auth present — create ephemeral workdir
    workdir = Path(tempfile.mkdtemp(prefix="copilot-omni-itest-"))
    _log(f"Tier 2 ephemeral workdir: {workdir}")

    t2_ok = True
    try:
        t2_ok &= run_plugin_load(repo_root, workdir)
        t2_ok &= run_skill_probe(repo_root, workdir)
        t2_ok &= run_hook_audit_check(workdir)
    finally:
        keep = os.environ.get("KEEP_ITEST_WORKDIR", "") == "1"
        if keep:
            _log(f"KEEP_ITEST_WORKDIR=1 — workdir preserved at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
            _log(f"Cleaned up workdir {workdir}")

    _print_summary()
    _flush_log(repo_root)
    return 0 if t2_ok else 1


if __name__ == "__main__":
    sys.exit(main())
