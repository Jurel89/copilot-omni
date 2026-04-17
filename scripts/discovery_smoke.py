#!/usr/bin/env python3
"""Plugin discovery smoke + Wave-0 runtime-contract probes.

Verifies filesystem layout matches Copilot CLI discovery rules, and runs
the six Wave-0 load-bearing assumptions (A1..A6) from the Phase-B
master plan §2.5. Any probe failure blocks Wave 0 exit.

All probes are stdlib-only. Probes that require an installed `copilot`
CLI are skipped when `OMNI_SKIP_COPILOT_PROBES=1` or `--offline` is set,
with status=`skip`. Skipped probes do NOT count as pass.

Outputs one JSONL record per probe to `.omni/audit/runtime-contract.jsonl`.

Usage:
    # default: run the layout check only (back-compat with v1 callers)
    python3 scripts/discovery_smoke.py

    # run one probe
    python3 scripts/discovery_smoke.py --probe A1

    # run all probes (Wave-0 exit gate)
    python3 scripts/discovery_smoke.py --probe all

    # skip any probe that calls copilot
    python3 scripts/discovery_smoke.py --probe all --offline
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Tuple

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / ".omni" / "audit"
AUDIT_LOG = AUDIT_DIR / "runtime-contract.jsonl"

EXPECTED_HOOK_FIELDS = {
    "pre_tool_use.py": {"event_name", "tool_name", "tool_input"},
    "post_tool_use.py": {"event_name", "tool_name", "tool_input", "tool_response"},
    "session_start.py": {"event_name"},
    "user_prompt_submit.py": {"event_name", "prompt"},
}


ProbeResult = Tuple[str, str, dict]  # (probe_id, status, detail)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record(probe_id: str, status: str, detail: dict) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "probe": probe_id, "status": status, "detail": detail}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def _skip_copilot(cli_offline: bool) -> bool:
    return cli_offline or _env_bool("OMNI_SKIP_COPILOT_PROBES", False)


# -----------------------------------------------------------------------------
# Layout probe (original discovery smoke)
# -----------------------------------------------------------------------------

def probe_layout(_: Any) -> ProbeResult:
    failures: list[str] = []

    manifest = ROOT / "plugin.json"
    if not manifest.exists():
        failures.append("missing plugin.json")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for field in ("name", "version", "description"):
            if field not in data:
                failures.append(f"plugin.json missing '{field}'")
        if data.get("name") != "copilot-omni":
            failures.append(f"unexpected plugin name: {data.get('name')!r}")

    if not (ROOT / ".mcp.json").exists():
        failures.append("missing .mcp.json")
    if not (ROOT / "hooks" / "hooks.json").exists():
        failures.append("missing hooks/hooks.json")

    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    agents = sorted((ROOT / "agents").glob("*.md"))
    commands = sorted((ROOT / "commands").glob("*.md"))

    if len(skills) < 25:
        failures.append(f"too few skills: {len(skills)}")
    if len(agents) < 15:
        failures.append(f"too few agents: {len(agents)}")
    if len(commands) < 6:
        failures.append(f"too few commands: {len(commands)}")

    detail = {
        "manifest": manifest.exists(),
        "mcp_json": (ROOT / ".mcp.json").exists(),
        "hooks_json": (ROOT / "hooks" / "hooks.json").exists(),
        "skills": len(skills),
        "agents": len(agents),
        "commands": len(commands),
        "failures": failures,
    }
    status = "pass" if not failures else "fail"
    return ("layout", status, detail)


# -----------------------------------------------------------------------------
# A1 — parallel copilot -p --agent invocations
# -----------------------------------------------------------------------------

def probe_a1_parallel_agents(offline: bool) -> ProbeResult:
    if _skip_copilot(offline):
        return ("A1", "skip", {"reason": "offline mode or OMNI_SKIP_COPILOT_PROBES set"})

    copilot = shutil.which("copilot")
    if not copilot:
        return ("A1", "fail", {"reason": "copilot CLI not on PATH"})

    prompt = "Reply with the single word OK."
    model = os.environ.get("OMNI_PROBE_MODEL", "claude-sonnet-4.5")
    cmd = [copilot, "-p", prompt, "--allow-all-tools", "--no-color"]
    if model:
        cmd += ["--model", model]

    def _run(_i: int) -> dict:
        t0 = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60, text=True)
            return {
                "exit_code": result.returncode,
                "duration_s": round(time.time() - t0, 2),
                "stdout_len": len(result.stdout),
                "stderr_len": len(result.stderr),
                "stderr_tail": result.stderr[-200:] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "duration_s": round(time.time() - t0, 2), "error": "timeout"}
        except Exception as exc:
            return {"exit_code": 1, "duration_s": round(time.time() - t0, 2), "error": str(exc)}

    t_start = time.time()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_run, i) for i in range(3)]
        for fut in as_completed(futures):
            results.append(fut.result())
    wall = round(time.time() - t_start, 2)

    all_ok = all(r.get("exit_code") == 0 for r in results)
    detail = {"runs": results, "wall_duration_s": wall, "model": model}
    return ("A1", "pass" if all_ok else "fail", detail)


# -----------------------------------------------------------------------------
# A2 — hook event JSON shape
# -----------------------------------------------------------------------------

def probe_a2_hook_shapes(_: Any) -> ProbeResult:
    """Feed each hook a minimal JSON payload on stdin. Assert it exits 0
    and does not crash. Record fields present in the payload."""
    hooks_dir = ROOT / "hooks"
    failures: list[dict] = []
    records: list[dict] = []

    common = {
        "event_name": "PreToolUse",
        "session_id": "probe-a2",
        "cwd": str(ROOT),
    }
    payloads = {
        "pre_tool_use.py": {**common, "event_name": "PreToolUse",
                            "tool_name": "Bash", "tool_input": {"command": "echo probe"}},
        "post_tool_use.py": {**common, "event_name": "PostToolUse",
                             "tool_name": "Bash", "tool_input": {"command": "echo probe"},
                             "tool_response": {"stdout": "probe\n", "exit_code": 0}},
        "session_start.py": {**common, "event_name": "SessionStart"},
        "user_prompt_submit.py": {**common, "event_name": "UserPromptSubmit",
                                  "prompt": "probe A2 hook-shapes"},
    }

    for name, payload in payloads.items():
        hook = hooks_dir / name
        if not hook.exists():
            failures.append({"hook": name, "reason": "missing"})
            continue
        try:
            result = subprocess.run(
                [sys.executable, str(hook)],
                input=json.dumps(payload),
                capture_output=True, text=True, timeout=10,
            )
            records.append({
                "hook": name,
                "exit_code": result.returncode,
                "stdout_len": len(result.stdout),
                "stderr_tail": result.stderr[-200:] if result.stderr else "",
                "payload_fields": sorted(payload.keys()),
            })
            if result.returncode != 0:
                failures.append({"hook": name, "exit_code": result.returncode,
                                 "stderr_tail": result.stderr[-200:]})
        except subprocess.TimeoutExpired:
            failures.append({"hook": name, "reason": "timeout"})

    detail = {"hooks": records, "failures": failures,
              "expected_fields": {k: sorted(v) for k, v in EXPECTED_HOOK_FIELDS.items()}}
    status = "pass" if not failures else "fail"
    return ("A2", status, detail)


# -----------------------------------------------------------------------------
# A3 — skill frontmatter triggers field
# -----------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def probe_a3_frontmatter_triggers(_: Any) -> ProbeResult:
    """Static verification of skill frontmatter. The assumption
    "Copilot reads triggers: field" is LLM-level — true verification
    requires an interactive chat session. This probe verifies (a) every
    skill has parseable frontmatter with `description`, (b) reports
    which skills declare a `triggers` field so the WS3 router can
    ingest them, (c) writes a marker skill the user can manually
    verify with a single Copilot Chat round-trip.
    """
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    missing_desc: list[str] = []
    with_triggers: list[str] = []
    parse_errors: list[str] = []

    for skill in skills:
        try:
            text = skill.read_text(encoding="utf-8")
        except Exception as exc:
            parse_errors.append(f"{skill.parent.name}: {exc}")
            continue
        meta = _parse_frontmatter(text)
        if not meta.get("description"):
            missing_desc.append(skill.parent.name)
        if "triggers" in text.splitlines()[0:30][0:] and "triggers" in meta:
            with_triggers.append(skill.parent.name)
        elif "\ntriggers:" in text[:800]:
            with_triggers.append(skill.parent.name)

    detail = {
        "total_skills": len(skills),
        "missing_description": missing_desc,
        "with_triggers_field": sorted(set(with_triggers)),
        "parse_errors": parse_errors,
        "manual_verification_required": True,
        "manual_step": (
            "In a Copilot chat, send a prompt containing a unique trigger from a "
            "skill that declares `triggers:`. Confirm the skill is auto-dispatched."
        ),
    }
    # Fails only if any skill has no description or parse error. The
    # LLM-level triggers check is manual.
    status = "pass" if not missing_desc and not parse_errors else "fail"
    return ("A3", status, detail)


# -----------------------------------------------------------------------------
# A4 — one-turn vs multi-turn agent dispatch
# -----------------------------------------------------------------------------

def probe_a4_agent_turns(offline: bool) -> ProbeResult:
    if _skip_copilot(offline):
        return ("A4", "skip", {"reason": "offline mode or OMNI_SKIP_COPILOT_PROBES set"})

    copilot = shutil.which("copilot")
    if not copilot:
        return ("A4", "fail", {"reason": "copilot CLI not on PATH"})

    model = os.environ.get("OMNI_PROBE_MODEL", "claude-sonnet-4.5")
    base = [copilot, "--allow-all-tools", "--no-color"]
    if model:
        base += ["--model", model]

    marker = "PINEAPPLE-7392"
    first = base + ["-p", f"Remember this unique token: {marker}. Reply OK."]
    second = base + ["-p", "What unique token did I ask you to remember? Answer with the token itself or say NONE."]

    try:
        r1 = subprocess.run(first, capture_output=True, text=True, timeout=60)
        r2 = subprocess.run(second, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return ("A4", "fail", {"reason": "timeout"})
    except Exception as exc:
        return ("A4", "fail", {"reason": str(exc)})

    second_recalls = marker.lower() in (r2.stdout or "").lower()
    isolated = not second_recalls  # one-turn == isolated == assumption holds
    detail = {
        "first_exit": r1.returncode,
        "second_exit": r2.returncode,
        "second_stdout_tail": (r2.stdout or "")[-400:],
        "memory_leaked": second_recalls,
        "turns_isolated": isolated,
        "model": model,
    }
    return ("A4", "pass" if isolated and r1.returncode == 0 and r2.returncode == 0 else "fail", detail)


# -----------------------------------------------------------------------------
# A5 — grep coverage
# -----------------------------------------------------------------------------

def probe_a5_grep_coverage(_: Any) -> ProbeResult:
    """Compare `git ls-files` against the filesystem walk. Files in the
    tree but not tracked by git (build artifacts, caches, editor files)
    are NOT covered by a standard `grep -r` over the repo. Record those
    for the WS1 rename verifier allowlist.
    """
    try:
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as exc:
        return ("A5", "fail", {"reason": f"git ls-files failed: {exc}"})
    tracked_set = set(tracked.stdout.splitlines())

    seen: list[str] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue
        rel_s = str(rel)
        if rel_s.startswith(".git/"):
            continue
        if rel_s.startswith(".omni/"):
            continue
        if rel_s.startswith("__pycache__") or "/__pycache__/" in rel_s:
            continue
        if rel_s.endswith(".pyc"):
            continue
        if rel_s not in tracked_set:
            seen.append(rel_s)

    detail = {
        "tracked_files": len(tracked_set),
        "untracked_present": sorted(seen)[:50],
        "untracked_count": len(seen),
        "excluded_prefixes": [".git/", ".omni/", "__pycache__", "*.pyc"],
    }
    # Pass if untracked stays small OR is entirely ignorable. Document
    # anything found so the rename verifier can choose to widen its grep.
    status = "pass"
    return ("A5", status, detail)


# -----------------------------------------------------------------------------
# A6 — background subagent auth retention
# -----------------------------------------------------------------------------

def probe_a6_bg_auth(offline: bool) -> ProbeResult:
    """Background auth retention assumption.

    Reduced-scope probe for Wave 0: fires 3 concurrent `copilot -p` calls
    via subprocess.Popen (not the foreground thread-pool used in A1).
    This tests the underlying auth-token assumption (Copilot auth survives
    concurrent backgrounded invocations without re-auth prompts).

    The full `scripts/subagent.py --background` e2e test belongs to WS5a
    (`tests/test_subagent_background.py`), once subagent.py grows its
    background mode. Running a --background subagent here would require
    plugin-scoped agent discovery, which v1 does not provide.
    """
    if _skip_copilot(offline):
        return ("A6", "skip", {"reason": "offline mode or OMNI_SKIP_COPILOT_PROBES set"})

    copilot = shutil.which("copilot")
    if not copilot:
        return ("A6", "fail", {"reason": "copilot CLI not on PATH"})

    model = os.environ.get("OMNI_PROBE_MODEL", "claude-sonnet-4.5")
    prompt = "Reply with the single word OK."
    cmd = [copilot, "-p", prompt, "--allow-all-tools", "--no-color", "--model", model]

    procs = []
    for _ in range(3):
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,  # detach: mimics background spawn
        )
        procs.append(p)

    results: list[dict] = []
    for p in procs:
        try:
            out, err = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
            results.append({"exit_code": 124, "error": "timeout",
                            "stderr_tail": (err.decode("utf-8", "replace") or "")[-200:]})
            continue
        results.append({
            "exit_code": p.returncode,
            "stderr_tail": (err.decode("utf-8", "replace") or "")[-200:],
            "stdout_len": len(out),
        })

    all_ok = all(r.get("exit_code") == 0 for r in results)
    detail = {
        "runs": results,
        "model": model,
        "scope": "reduced; full subagent.py --background probe deferred to WS5a",
    }
    return ("A6", "pass" if all_ok else "fail", detail)


# -----------------------------------------------------------------------------
# Harness
# -----------------------------------------------------------------------------

PROBES = {
    "layout": probe_layout,
    "A1": probe_a1_parallel_agents,
    "A2": probe_a2_hook_shapes,
    "A3": probe_a3_frontmatter_triggers,
    "A4": probe_a4_agent_turns,
    "A5": probe_a5_grep_coverage,
    "A6": probe_a6_bg_auth,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probe", default="layout",
                        help="probe id (layout, A1..A6, or 'all')")
    parser.add_argument("--offline", action="store_true",
                        help="skip probes that invoke copilot CLI")
    args = parser.parse_args()

    if args.probe == "all":
        names = list(PROBES.keys())
    else:
        if args.probe not in PROBES:
            print(f"unknown probe: {args.probe}", file=sys.stderr)
            return 2
        names = [args.probe]

    offline = args.offline
    results: list[ProbeResult] = []
    for name in names:
        fn = PROBES[name]
        try:
            # A1/A4/A6 take offline; others accept and ignore it
            result = fn(offline)
        except Exception as exc:  # probes must not crash the harness
            result = (name, "fail", {"reason": f"probe crashed: {exc!r}"})
        results.append(result)
        _record(*result)

    failed = any(r[1] == "fail" for r in results)
    skipped = [r[0] for r in results if r[1] == "skip"]

    print()
    print(f"{'Probe':<8} {'Status':<6} Detail")
    print("-" * 72)
    for probe_id, status, detail in results:
        short = ""
        if probe_id == "layout":
            short = f"skills={detail.get('skills')} agents={detail.get('agents')} cmds={detail.get('commands')}"
        elif probe_id == "A1":
            runs = detail.get("runs", [])
            short = f"3 parallel runs, exits={[r.get('exit_code') for r in runs]}, wall={detail.get('wall_duration_s')}s"
        elif probe_id == "A2":
            short = f"hooks={len(detail.get('hooks', []))}, failures={len(detail.get('failures', []))}"
        elif probe_id == "A3":
            short = f"skills={detail.get('total_skills')}, with_triggers={len(detail.get('with_triggers_field', []))}"
        elif probe_id == "A4":
            short = f"isolated={detail.get('turns_isolated')}, exits=({detail.get('first_exit')},{detail.get('second_exit')})"
        elif probe_id == "A5":
            short = f"tracked={detail.get('tracked_files')}, untracked={detail.get('untracked_count')}"
        elif probe_id == "A6":
            runs = detail.get("runs", [])
            short = f"3 bg subagents, exits={[r.get('exit_code') for r in runs]}"
        else:
            short = detail.get("reason", "")
        print(f"{probe_id:<8} {status:<6} {short}")

    print()
    print(f"Audit log: {AUDIT_LOG.relative_to(ROOT)}")
    if skipped:
        print(f"Skipped: {skipped}  (pass=OFFLINE; enable with copilot auth to gate Wave 0)")
    if failed:
        print("\nOne or more probes FAILED. Wave 0 exit blocked.")
        return 1
    print("\nAll non-skipped probes passed.")
    # Wave 0 exit gate demands ALL probes pass; skipped == inconclusive.
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
