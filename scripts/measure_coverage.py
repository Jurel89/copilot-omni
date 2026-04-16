#!/usr/bin/env python3
"""WS10 per-module coverage measurement tool.

Usage
-----
    python3 scripts/measure_coverage.py --all     # run suite, report, print JSON
    python3 scripts/measure_coverage.py --check   # same + exit 1 if any module under target
    python3 scripts/measure_coverage.py --report  # parse existing .coverage file and report

Prerequisites
-------------
    pip install coverage   (or: pip install -r requirements-dev.txt)

The tool shells out to ``python -m coverage`` (same Python interpreter) to
run pytest under coverage, then parses the JSON report to produce a
per-module breakdown.

Per-module targets (locked in WS10 spec, F16/critic §7 #15)
------------------------------------------------------------
    mcp/       >= 80%
    hooks/     >= 70%
    scripts/   >= 60%

Stdlib only (plus subprocess call to coverage). No third-party imports at
module level.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Per-module targets (WS10 locked decisions)
# ---------------------------------------------------------------------------

MODULE_TARGETS: Dict[str, float] = {
    "mcp": 80.0,
    "hooks": 70.0,
    "scripts": 60.0,
}

# Modules we explicitly track (relative to ROOT)
TRACKED_MODULES = list(MODULE_TARGETS.keys())


# ---------------------------------------------------------------------------
# Coverage runner
# ---------------------------------------------------------------------------


def _python() -> str:
    """Return the current Python interpreter path."""
    return sys.executable


def _ensure_coverage() -> bool:
    """Return True if `coverage` package is importable."""
    import importlib.util
    return importlib.util.find_spec("coverage") is not None


def run_suite(cov_json_path: Path) -> subprocess.CompletedProcess:
    """Run pytest under coverage and produce a JSON report at *cov_json_path*."""
    if not _ensure_coverage():
        print(
            "ERROR: 'coverage' package not found.\n"
            "Install with: pip install coverage  (or pip install -r requirements-dev.txt)",
            file=sys.stderr,
        )
        sys.exit(2)

    # Source: track all three target module dirs
    source_arg = ",".join(
        str(ROOT / module) for module in TRACKED_MODULES
    )

    # Step 1: run pytest under coverage
    run_cmd = [
        _python(), "-m", "coverage", "run",
        f"--source={source_arg}",
        "--branch",                        # branch coverage (more accurate)
        "-m", "pytest", "-q",
        "--tb=no",                         # suppress tracebacks in coverage run
        str(ROOT / "tests"),
    ]
    print(f"[measure_coverage] Running: {' '.join(run_cmd)}", flush=True)
    run_result = subprocess.run(run_cmd, cwd=str(ROOT))

    # Step 2: export JSON report
    json_cmd = [
        _python(), "-m", "coverage", "json",
        "-o", str(cov_json_path),
        "--include",
        ",".join(f"{ROOT / m}/*" for m in TRACKED_MODULES),
    ]
    print(f"[measure_coverage] Exporting JSON: {' '.join(json_cmd)}", flush=True)
    json_result = subprocess.run(json_cmd, cwd=str(ROOT), capture_output=True, text=True)

    if json_result.returncode != 0:
        print(f"[measure_coverage] coverage json error:\n{json_result.stderr}", file=sys.stderr)

    return run_result


# ---------------------------------------------------------------------------
# Report parser
# ---------------------------------------------------------------------------


def parse_coverage_json(cov_json_path: Path) -> Dict[str, Any]:
    """Parse coverage.json and return per-module line-coverage summary.

    Returns a dict mapping module prefix → {
        "line_coverage": float,   # 0.0–100.0
        "missing_lines": list,    # list of "file:line_no" strings
        "status": "ok" | "fail",  # vs per-module target
    }
    """
    try:
        data = json.loads(cov_json_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: coverage JSON not found at {cov_json_path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"ERROR: cannot parse coverage JSON: {exc}", file=sys.stderr)
        sys.exit(2)

    # Aggregate per module
    module_stats: Dict[str, Dict[str, Any]] = {}
    for module in TRACKED_MODULES:
        module_stats[module] = {
            "num_statements": 0,
            "num_executed": 0,
            "missing": [],  # list of "relative/path.py:42"
        }

    files = data.get("files", {})
    for file_path_str, file_data in files.items():
        file_path = Path(file_path_str)
        # Determine which module this file belongs to
        matched_module: Optional[str] = None
        for m in TRACKED_MODULES:
            module_abs = ROOT / m
            try:
                file_path.relative_to(module_abs)
                matched_module = m
                break
            except ValueError:
                pass
        if matched_module is None:
            continue

        summary = file_data.get("summary", {})
        num_stmts = summary.get("num_statements", 0)
        num_missing = summary.get("missing_lines", 0)
        num_executed = num_stmts - num_missing

        missing_lines = file_data.get("missing_lines", [])
        try:
            rel = str(file_path.relative_to(ROOT))
        except ValueError:
            rel = file_path_str

        module_stats[matched_module]["num_statements"] += num_stmts
        module_stats[matched_module]["num_executed"] += num_executed
        for ln in missing_lines:
            module_stats[matched_module]["missing"].append(f"{rel}:{ln}")

    # Build report
    report: Dict[str, Any] = {}
    for module, stats in module_stats.items():
        total = stats["num_statements"]
        executed = stats["num_executed"]
        if total == 0:
            # C9: 0 statements means instrumentation failed or the module was
            # not executed at all. Reporting 100% here would make the coverage
            # gate a rubber stamp. Mark as "unmeasured" and set coverage to 0.0
            # so --check correctly fails.
            pct = 0.0
            status = "unmeasured"
        else:
            pct = round(executed / total * 100, 1)
            target = MODULE_TARGETS[module]
            status = "ok" if pct >= target else "fail"

        target = MODULE_TARGETS[module]
        report[module] = {
            "line_coverage": pct,
            "missing_lines": stats["missing"][:50],  # cap at 50 for readability
            "status": status,
            "target": target,
            "num_statements": total,
            "num_executed": executed,
        }

    return report


# ---------------------------------------------------------------------------
# Printer
# ---------------------------------------------------------------------------


def print_report(report: Dict[str, Any]) -> None:
    """Print a human-readable coverage table, then emit JSON."""
    print("\n" + "=" * 60)
    print(f"{'Module':<12} {'Coverage':>10} {'Target':>8} {'Status':>8}")
    print("-" * 60)
    for module, info in sorted(report.items()):
        cov = f"{info['line_coverage']:.1f}%"
        tgt = f"{info['target']:.0f}%"
        status = info["status"].upper()
        print(f"{module:<12} {cov:>10} {tgt:>8} {status:>8}")
    print("=" * 60)

    any_fail = any(v["status"] in ("fail", "unmeasured") for v in report.values())
    print(f"\nOverall: {'FAIL — some modules below target' if any_fail else 'PASS — all modules meet targets'}\n")

    print("JSON report:")
    print(json.dumps(report, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="measure_coverage",
        description="WS10 per-module coverage measurement for copilot-omni.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        dest="run_all",
        help="Run test suite under coverage, report results, exit 0 always.",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Run test suite under coverage, report results; exit 1 if any module below target.",
    )
    group.add_argument(
        "--report",
        action="store_true",
        help="Parse existing coverage.json (from a previous run) and report without re-running.",
    )
    parser.add_argument(
        "--json-path",
        default=str(ROOT / "coverage.json"),
        metavar="PATH",
        help="Path to write/read coverage JSON (default: ./coverage.json).",
    )
    args = parser.parse_args(argv)

    cov_json = Path(args.json_path)

    if args.report:
        # Just parse whatever exists
        report = parse_coverage_json(cov_json)
        print_report(report)
        return 0

    # --all or --check: run suite first
    run_result = run_suite(cov_json)

    if not cov_json.exists():
        print("ERROR: coverage JSON was not produced. Check coverage output above.", file=sys.stderr)
        return 2

    report = parse_coverage_json(cov_json)
    print_report(report)

    if args.check:
        any_fail = any(v["status"] in ("fail", "unmeasured") for v in report.values())
        if any_fail:
            print("COVERAGE CHECK FAILED: one or more modules below target.", file=sys.stderr)
            return 1
        return 0

    # --all: always exit 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
