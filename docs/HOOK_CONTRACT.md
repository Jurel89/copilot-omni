# Hook Contract Reference

**Version:** 2.1.1
**Applies to:** `hooks/session_start.py`, `hooks/pre_tool_use.py`

---

## 1. Overview

copilot-omni ships two lifecycle hooks as pure Python stdlib scripts. They are
invoked by GitHub Copilot CLI at the corresponding lifecycle event (`sessionStart`
and `preToolUse`). Each reads a JSON payload from stdin and writes a JSON response
to stdout.

Both hooks **fail open**: on any unhandled error they exit 0 and emit `{}` so the
session is never blocked by the plugin. If a Copilot CLI version stops emitting
one of these events, the corresponding hook simply never runs — the plugin stays
inert rather than broken.

Hooks not shipped by this plugin:

| Event                 | Status                              |
|-----------------------|-------------------------------------|
| `postToolUse`         | No handler shipped (event allowed).  |
| `userPromptSubmitted` | No handler shipped (event allowed).  |
| `errorOccurred`       | No handler shipped (event allowed).  |
| `sessionEnd`          | No handler shipped (event allowed).  |

Adding a handler is a matter of dropping a file under `hooks/` and registering it
in `hooks/hooks.json`. `tests/test_hook_contract_alignment.py` then keeps the
config and this doc in sync.

---

## 2. Event Shapes

### 2.1 `sessionStart` — `hooks/session_start.py` (LIVE)

**Stdin:** `{}` (no payload required; may include session metadata).

**Stdout:**
```json
{
  "additionalContext": "<omni-banner>copilot-omni vX.Y.Z | N skills | N agents | pool=N</omni-banner>\n<policy-warning>...</policy-warning>"
}
```

The `<omni-banner>` tag is always present. Its four segments match the template
produced by `_compute_banner` in the hook itself (version, skill count, agent
count, pool cap). `<policy-warning>` lines appear only when a policy file under
`policies/` has permissions more permissive than `0o644`.

### 2.2 `preToolUse` — `hooks/pre_tool_use.py` (LIVE)

**Stdin:**
```json
{
  "tool_name": "shell",
  "tool_args": { "command": "ls -la" }
}
```
Alternate field names `toolName` / `toolArgs` are also accepted. `tool_args`
may be a JSON-encoded string (current Copilot CLI behaviour) or a native
object (legacy / test harness). The hook normalises both to a dict.

**Stdout:**
```json
{ "permissionDecision": "allow" }
{ "permissionDecision": "deny", "permissionDecisionReason": "..." }
```

Policy enforcement reads the active profile under `policies/` and applies
`deny_commands` / `protected_paths`. On decode errors, shlex parse failures,
or any other exception, the hook emits `{}` and exits 0.

---

## 3. Kill Switches

| Env var                      | Scope                              |
|------------------------------|------------------------------------|
| `OMNI_SKIP_HOOKS=1`          | Disable all hooks                  |
| `DISABLE_OMNI=1`             | Disable all hooks (alternate form) |
| `OMNI_SKIP_SESSION_START=1`  | Disable only `session_start.py`    |
| `OMNI_SKIP_PRE_TOOL_USE=1`   | Disable only `pre_tool_use.py`     |

When any kill switch is active the selected hook:

- exits with code 0
- writes `{}` to stdout
- skips audit and metrics writes

### Legacy aliases (deprecated — removed in v3.0.0)

| Env var              | Behaviour                                                   |
|----------------------|-------------------------------------------------------------|
| `OMC_SKIP_HOOKS=1`   | Same as `OMNI_SKIP_HOOKS=1`; emits deprecation warning once. |
| `DISABLE_OMC=1`      | Same as `DISABLE_OMNI=1`; emits deprecation warning once.    |

The deprecation warning is de-duplicated via
`.omni/cache/omc-deprecation-warned` (one emission per project). <!-- omni-rename-allow: legacy sentinel filename -->

---

## 4. Audit Log Schema

**File:** `.omni/audit/hooks.jsonl`
**Format:** one JSON object per line (JSONL).
**Access:** atomic file-locked append (POSIX `fcntl.flock`, Windows `msvcrt.locking`).

### Record fields

| Field             | Type   | Description |
|-------------------|--------|-------------|
| `ts`              | float  | Unix timestamp (seconds since epoch) |
| `hook`            | string | Hook name: `pre_tool_use` or `session_start` |
| `event_name`      | string | Event type (same as hook name) |
| `tool_name`       | string | Tool being invoked (empty for session hook) |
| `prompt_excerpt`  | string | First 120 chars of command (empty where not applicable) |
| `action`          | string | `allow`, `deny`, `log`, `banner` |
| `reason`          | string | Human-readable reason (empty for allow) |

### Example

```jsonl
{"ts": 1714000000.123, "hook": "session_start", "event_name": "session_start", "tool_name": "", "prompt_excerpt": "", "action": "banner", "reason": ""}
{"ts": 1714000001.456, "hook": "pre_tool_use", "event_name": "pre_tool_use", "tool_name": "shell", "prompt_excerpt": "sudo rm -rf /", "action": "deny", "reason": "copilot-omni policy: blocked command 'sudo '"}
```

---

## 5. Metrics Schema

**File:** `.omni/audit/metrics.jsonl`
**Format:** one JSON object per line (JSONL).
**Access:** same atomic file-lock as audit log.

### Record fields

| Field    | Type   | Description |
|----------|--------|-------------|
| `ts`     | float  | Unix timestamp |
| `name`   | string | Metric name (see below) |
| `value`  | any    | Numeric or string metric value |
| `labels` | object | Key-value labels |

### Emitted metrics

| Metric name        | Value type | Labels          | Description |
|--------------------|------------|-----------------|-------------|
| `hook_latency_ms`  | float      | `hook`          | End-to-end hook execution time in milliseconds |
| `hook_exit_code`   | int        | `hook`, `action`| Always 0 (hooks never exit non-zero) |

---

## 6. Policy File Expectations

Policy files live under `policies/` (e.g. `policies/standard.json`,
`policies/strict.json`, `policies/permissive.json`).

**Permission:** files should have mode `<= 0o644` (owner read/write, group/world
read-only). At session start, `session_start.py` checks every `policies/*.json`;
files with mode `> 0o644` produce a `<policy-warning>` in the banner context.
This does **not** fail the session.

**Schema:**
```json
{
  "profile": "standard",
  "description": "...",
  "deny_commands": ["sudo ", "rm -rf /", "..."],
  "protected_paths": [".omni/config.json", "AGENTS.md", "..."]
}
```

---

## 7. Timeout Budget

Each hook must complete within **5 seconds** (Copilot CLI hard wall). Implementation
target is p99 < 100ms.

| Hook            | Typical latency                       | Bottleneck                |
|-----------------|---------------------------------------|---------------------------|
| `session_start` | < 30ms (cache hit) / < 80ms (miss)    | Skill-tree scan on miss   |
| `pre_tool_use`  | < 5ms                                 | Policy JSON read          |

File-lock acquisition is bounded to **1 second** per audit write. If the lock
cannot be acquired within budget, the write is dropped with a stderr warning and
the hook never blocks past this limit.

---

## 8. Shared Library

Both hooks share `hooks/_hook_lib.py` which provides:

- `_hook_disabled(hook_name)` — kill-switch check
- `_deprecation_warn()` — one-shot legacy-var warning
- `_append_audit(record)` — atomic JSONL audit append
- `_write_metric(name, value, labels)` — atomic JSONL metrics append

`_hook_lib.py` is loaded via `importlib.util.spec_from_file_location` so it does
not need to be on `sys.path` and the hook scripts remain self-contained.

---

## 9. Regression Test

`tests/test_hook_contract_alignment.py` parses `hooks/hooks.json` and this
document together and asserts:

1. Every event registered in `hooks/hooks.json` is documented as LIVE here.
2. Every event documented as LIVE here is registered in `hooks/hooks.json`.
3. The banner template string in this document matches the shape emitted by
   `hooks/session_start.py:_compute_banner` (same segment count + separator).

Any drift between the shipped config, the shipped hook code, and this contract
breaks CI immediately. The pre-contract-reset audit found a version of this
document that contradicted the shipped config; the regression test exists so
that cannot recur.

---

## 10. Deprecation Timeline

| Version | Change |
|---------|--------|
| v2.1.1 (current) | Hook docs aligned to shipped config. Stale "removed" notes on `preToolUse` cleared. `OMNI_SKIP_PRE_TOOL_USE` kill switch documented as live. |
| v2.1.0           | Retired the front-door router and its `OMNI_ROUTER_ENFORCE` hook branch. |
| v3.0.0           | `OMC_SKIP_HOOKS` and `DISABLE_OMC` aliases **removed**. Use `OMNI_SKIP_HOOKS` / `DISABLE_OMNI`. |
