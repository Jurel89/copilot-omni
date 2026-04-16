# Test Strategy

This document is the single source of truth for how `copilot-omni` is tested, how tests are organized, how to run them, and what the per-module coverage bar is.

## Test categories

Tests live under `tests/` and are categorized by pytest markers registered in `pytest.ini`:

| Marker | Purpose | Default |
|---|---|---|
| `unit` | Single-module behavior under mocked I/O | Run by default |
| `integration` | Cross-module invariants (router + hooks + subagent + MCP) | Run by default |
| `e2e` | End-to-end pipeline recipes parsed from `SKILL.md` | Run by default under FAKE |
| `tmux` | Requires `tmux` binary on PATH | Skipped if unavailable |
| `slow` | Exceeds ~2 seconds | Run by default; `-m "not slow"` excludes |

## Running subsets

```bash
# Full suite (what CI runs)
python3 -m pytest -q

# Skip slow + tmux tests for rapid iteration
python3 -m pytest -q -m "not slow and not tmux"

# Just integration smokes
python3 -m pytest tests/test_integration_phase_b.py -v

# One module at a time
python3 -m pytest tests/test_router.py tests/test_router_gaps.py -v
```

## FAKE subagent contract

Tests that exercise pipeline recipes (autopilot/ralph/ultrawork/ultraqa/ralplan/team) do NOT invoke real `copilot`. They set `OMNI_SUBAGENT_FAKE=1` which:

- Bypasses the real `copilot -p` call in `scripts/subagent.py`.
- Runs a synthetic inline Python one-liner that sleeps `OMNI_SUBAGENT_FAKE_SLEEP_SECS` (default 0.05 in tests) and exits `OMNI_SUBAGENT_FAKE_EXIT_CODE` (default 0).
- Optionally reads scripted per-agent responses from `OMNI_SUBAGENT_FAKE_RESPONSE_FILE` (see `tests/fixtures/ralplan-*.json`).
- Requires `PYTEST_CURRENT_TEST` or `OMNI_TEST_MODE=1` to activate — production invocations refuse the hatch (ADR-0010 + WS7 T4 guard).

A real-Copilot nightly job is tracked in `docs/PHASE-C-BACKLOG.md`; it is NOT in the default matrix.

## Coverage targets

Per-module line coverage gates, enforced by `python3 scripts/measure_coverage.py --check`:

| Module | Target | Rationale |
|---|---|---|
| `mcp/` | ≥ 80% | MCP server is the state API backbone; schema violations → silent data loss |
| `hooks/` | ≥ 70% | Kill switches, audit logging, routing — must be reliable |
| `scripts/` | ≥ 60% | Broad surface; some CLI-heavy paths are harder to cover cleanly |

The `coverage` package is a dev-only dependency (`requirements-dev.txt`). CI installs it on the `coverage` job (Linux py3.11 only).

```bash
# Install dev-deps once
python3 -m pip install --user -r requirements-dev.txt
# or in CI / sandboxed system Python
python3 -m pip install --break-system-packages -r requirements-dev.txt

# Run the coverage gate
python3 scripts/measure_coverage.py --all
python3 scripts/measure_coverage.py --check  # exits 1 if any module under target
```

## Adding a new test

1. Place it under `tests/test_<topic>.py`.
2. Declare markers at the top: `pytestmark = [pytest.mark.integration]` for anything cross-module.
3. For tests that exercise a `SKILL.md` recipe: use `tests/_pipeline_runner.py` — never re-implement skill logic inside the test.
4. For tests that need a fresh run-dir: use a `tmp_path` fixture plus a UUID-based session id to avoid cross-test contamination.
5. For scripted subagent responses: check in a JSON fixture under `tests/fixtures/` and point to it via `OMNI_SUBAGENT_FAKE_RESPONSE_FILE`.
6. Integration smokes belong in `tests/test_integration_phase_b.py` — keep them FAST (< 200 ms each) and cross-wave.

## CI expectations

`.github/workflows/ci.yml` runs:

- `lint & contract validator` across Python 3.9/3.10/3.11/3.12 — fast (~15 s per cell).
- `unit tests (ubuntu / py <version>)` — the full pytest suite; ~7–8 minutes on GitHub hosted runners.
- `mcp-smoke`, `discovery-smoke` — quick JSON-RPC and layout checks.
- `coverage` — the per-module gate (Linux py3.11 only); fails the pipeline if any module drops below its target.
- `copilot-smoke` — best-effort `npm install -g @github/copilot` + offline discovery (continue-on-error).

## Flake policy

- If a test passes locally and fails once on CI: open an issue, tag `flake`. Do NOT re-run until investigated.
- If the root cause is a timing race (cancel cascade, pool backpressure): widen the accepted states or use `wait_for_terminal` with a real budget. Never sleep + assert.
- If the root cause is a CI-resource constraint (hook latency budget): tighten the production code, not the test.

## References

- `pytest.ini` — marker registry and default options
- `scripts/measure_coverage.py` — coverage harness
- `requirements-dev.txt` — dev dependencies (coverage)
- `docs/ADR/ADR-0006-mode-composition.md` — cancel cascade protocol (guides e2e test shape)
- `docs/ADR/ADR-0010-subagent-back-pressure.md` — pool semantics (guides stress-test shape)
- `.omni/plans/wave-3-WS10-report.md` — WS10 completion report with starting/ending coverage numbers
