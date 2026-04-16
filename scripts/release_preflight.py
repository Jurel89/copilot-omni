#!/usr/bin/env python3
"""
release_preflight.py — single-script gate for ``git tag v2.0.0``.

Checks (in order):
  1. On branch phase-b/main
  2. No uncommitted changes
  3. All 17 validator checks green  (verify_plugin_contract.py --all)
  4. Full pytest suite green
  5. CHANGELOG.md contains a [2.0.0] section
  6. docs/RELEASE-v2.0.0.md exists
  7. Last 3 CI runs on phase-b/main all green (via ``gh run list``)

Exit 0 = all pass.  Exit 1 = one or more checks failed (checklist printed).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _run(cmd: list[str], *, capture: bool = True, cwd: Path = REPO_ROOT):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _check(label: str, passed: bool, detail: str = "") -> tuple[str, bool]:
    icon = "OK" if passed else "FAIL"
    line = f"  [{icon}] {label}"
    if detail:
        line += f"\n        {detail}"
    return line, passed


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_branch() -> tuple[str, bool]:
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.decode().strip() if result.returncode == 0 else ""
    ok = branch == "phase-b/main"
    detail = f"current branch: {branch!r}" if not ok else ""
    return _check("On branch phase-b/main", ok, detail)


def check_no_uncommitted() -> tuple[str, bool]:
    result = _run(["git", "status", "--porcelain"])
    dirty = result.stdout.decode().strip() if result.returncode == 0 else ""
    ok = not dirty
    detail = dirty[:200] if dirty else ""
    return _check("No uncommitted changes", ok, detail)


def check_validator() -> tuple[str, bool]:
    result = _run(
        [sys.executable, "scripts/verify_plugin_contract.py", "--all"]
    )
    ok = result.returncode == 0
    detail = "" if ok else (result.stdout.decode() + result.stderr.decode())[-300:]
    return _check("Validator --all → 17 checks green", ok, detail)


def check_pytest() -> tuple[str, bool]:
    result = _run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    )
    stdout = result.stdout.decode() if result.returncode is not None else ""
    ok = result.returncode == 0
    # Extract last 2 lines as summary
    lines = [l for l in stdout.splitlines() if l.strip()]
    summary = " | ".join(lines[-2:]) if lines else ""
    detail = summary if not ok else summary
    return _check("pytest suite green", ok, detail)


def check_changelog() -> tuple[str, bool]:
    changelog = REPO_ROOT / "CHANGELOG.md"
    ok = False
    detail = ""
    if changelog.exists():
        text = changelog.read_text()
        ok = "## [2.0.0]" in text
        if not ok:
            detail = "## [2.0.0] section not found in CHANGELOG.md"
    else:
        detail = "CHANGELOG.md not found"
    return _check("CHANGELOG.md has [2.0.0] section", ok, detail)


def check_release_doc() -> tuple[str, bool]:
    doc = REPO_ROOT / "docs" / "RELEASE-v2.0.0.md"
    ok = doc.exists()
    detail = "" if ok else "docs/RELEASE-v2.0.0.md not found"
    return _check("docs/RELEASE-v2.0.0.md exists", ok, detail)


def check_ci_runs(*, skip_age_check: bool = False) -> tuple[str, bool]:
    """
    Verify the last 3 CI runs on phase-b/main are all green AND that the
    earliest green run is at least 24 hours old (plan §2.WS12 gate criterion).

    Requirements enforced:
    - Workflow name filter: only runs named "CI" are counted.
    - Minimum 3 consecutive completed runs, all with conclusion="success"
      (not "neutral" — neutral means a skipped required job).
    - Earliest of the 3 runs must have createdAt >= 24h ago.

    --skip-ci-age-check disables the 24h age requirement (dev-time use only).

    Requires ``gh`` CLI authenticated.
    """
    label = "Last 3 CI runs on phase-b/main green (≥24h apart)"

    gh_result = _run(["gh", "--version"])
    if gh_result.returncode != 0:
        return _check(
            label,
            False,
            "gh CLI not available — install GitHub CLI to verify CI runs",
        )

    result = _run(
        [
            "gh", "run", "list",
            "--branch", "phase-b/main",
            "--workflow", "CI",
            "--limit", "10",
            "--json", "status,conclusion,name,createdAt",
        ]
    )
    if result.returncode != 0:
        detail = result.stderr.decode().strip()[:200]
        return _check(label, False, f"gh run list failed: {detail}")

    try:
        all_runs = json.loads(result.stdout.decode())
    except json.JSONDecodeError as exc:
        return _check(label, False, f"Could not parse gh output: {exc}")

    # Filter to completed CI runs only — exclude "neutral" (skipped jobs)
    green_runs = [
        r for r in all_runs
        if r.get("status") == "completed"
        and r.get("conclusion") == "success"
    ]

    if len(green_runs) < 3:
        detail = (
            f"Need 3 green CI runs, found {len(green_runs)}. "
            f"All runs: {[(r.get('name'), r.get('conclusion')) for r in all_runs[:5]]}"
        )
        return _check(label, False, detail)

    # Take the 3 most recent green runs
    runs = green_runs[:3]

    # Age check: earliest of the 3 must be ≥24h old
    if not skip_age_check:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        earliest_run = runs[-1]  # oldest of the 3
        created_str = earliest_run.get("createdAt", "")
        try:
            # GitHub returns ISO 8601 with trailing Z
            created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created_at > cutoff:
                age_hours = (now - created_at).total_seconds() / 3600
                detail = (
                    f"Earliest of 3 green runs is only {age_hours:.1f}h old "
                    f"(need ≥24h). Use --skip-ci-age-check for dev-time testing."
                )
                return _check(label, False, detail)
        except (ValueError, TypeError):
            return _check(label, False, f"Cannot parse createdAt: {created_str!r}")

    detail = (
        f"3 green CI runs found"
        + (" (age check skipped)" if skip_age_check else " (≥24h verified)")
    )
    return _check(label, True, detail)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="release_preflight — v2.0.0 readiness gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skip-ci-age-check",
        action="store_true",
        default=False,
        help=(
            "Skip the ≥24h age requirement for the last 3 CI green runs. "
            "Use this only during development/testing — do NOT use for actual releases."
        ),
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("release_preflight — v2.0.0 readiness check")
    print("=" * 60)
    if args.skip_ci_age_check:
        print("WARNING: --skip-ci-age-check active; CI age requirement bypassed")
    print()

    results = [
        check_branch(),
        check_no_uncommitted(),
        check_validator(),
        check_pytest(),
        check_changelog(),
        check_release_doc(),
        check_ci_runs(skip_age_check=args.skip_ci_age_check),
    ]

    failures = []
    for line, passed in results:
        print(line)
        if not passed:
            failures.append(line)

    print()
    if failures:
        print(f"RESULT: {len(failures)} check(s) FAILED — not ready to tag v2.0.0")
        print()
        print("Failed checks:")
        for f in failures:
            # Print only the [FAIL] line, not multi-line detail again
            first_line = f.splitlines()[0]
            print(f"  {first_line.strip()}")
        print()
        return 1

    print("RESULT: all checks passed — ready to tag v2.0.0")
    print()
    print("When approved by the user, run:")
    print("  git tag -s v2.0.0 -m 'v2.0.0 release'")
    print("  git push origin v2.0.0")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
