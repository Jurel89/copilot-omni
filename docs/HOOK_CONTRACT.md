# Hook Contract Reference

**Version:** 2.1.0
**Applies to:** `hooks/session_start.py`

> **Note (v2.1.0):** `hooks/pre_tool_use.py`, `hooks/post_tool_use.py`, and `hooks/user_prompt_submit.py` were **removed in v2.1.0** — these lifecycle events are not emitted by GitHub Copilot CLI. Policy enforcement is via the MCP `policy_check` tool. The removed sections below are retained as historical record.

---

## 1. Overview

The one active lifecycle hook is a pure Python stdlib script. It is invoked by the Copilot CLI at session start. The hook reads a JSON payload from stdin and writes a JSON response to stdout.

The hook **fails open**: on any unhandled error the hook exits 0 and returns `{}` so the pipeline is never blocked.

---

## 2. Event Shapes

### 2.1 `sessionStart` — `hooks/session_start.py`

**Stdin:** `{}` (no payload required; may include session metadata)

**Stdout:**
```json
{
  "additionalContext": "<omni-banner>copilot-omni vX.Y.Z | N skills | N agents | N commands | router=on|off | pool=N</omni-banner>\n<policy-warning>...</policy-warning>"
}
```

The `<omni-banner>` tag is always present. `<policy-warning>` lines appear only when a policy file under `policies/` has permissions more permissive than `0o644`.

---

### 2.2 `preToolUse` — `hooks/pre_tool_use.py` _(Removed in v2.1.0 — this lifecycle event is not emitted by GitHub Copilot CLI)_

**Stdin:**
```json
{
  "tool_name": "shell",
  "tool_args": { "command": "ls -la" }
}
```
Alternate field names `toolName` / `toolArgs` are also accepted.

**Stdout:**
```json
{ "permissionDecision": "allow" }
{ "permissionDecision": "deny", "permissionDecisionReason": "..." }
```

---

### 2.3 `postToolUse` — `hooks/post_tool_use.py` _(Removed in v2.1.0 — this lifecycle event is not emitted by GitHub Copilot CLI)_

**Stdin:**
```json
{
  "tool_name": "shell",
  "status": "completed"
}
```

**Stdout:** `{}` (always empty; hook is audit-only)

---

### 2.4 `userPromptSubmit` — `hooks/user_prompt_submit.py` _(Removed in v2.1.0 — this lifecycle event is not emitted by GitHub Copilot CLI)_

**Stdin:**
```json
{
  "prompt": "fix the login bug in auth.py:42",
  "session_id": "optional-session-id"
}
```

**Stdout:**
```json
{
  "additionalContext": "<router-decision proceed=\"true\" score=\"0.85\"></router-decision>\n<skill-trigger-hint skill=\"wiki\" triggers=\"wiki\">...</skill-trigger-hint>"
}
```

The `<router-decision>` tag is always present. `<skill-trigger-hint>` appears only when a skill's `triggers:` frontmatter matches the prompt.

---

## 3. Kill Switches

### 3.1 Canonical (preferred)

| Env var | Scope |
|---|---|
| `OMNI_SKIP_HOOKS=1` | Disable all hooks |
| `DISABLE_OMNI=1` | Disable all hooks (alternate form) |
| `OMNI_SKIP_SESSION_START=1` | Disable only `session_start.py` |

The following are inert (hooks removed in v2.1.0):
| `OMNI_SKIP_PRE_TOOL_USE=1` | No-op (hook removed) |
| `OMNI_SKIP_POST_TOOL_USE=1` | No-op (hook removed) |
| `OMNI_SKIP_USER_PROMPT_SUBMIT=1` | No-op (hook removed) |

When any kill switch is active:
- Hook exits with code 0
- stdout is `{}`
- No audit records are written
- No metrics are written

### 3.2 Legacy aliases (deprecated — removed in v3.0.0)

| Env var | Behavior |
|---|---|
| `OMC_SKIP_HOOKS=1` | Same as `OMNI_SKIP_HOOKS=1`; emits deprecation warning to stderr |
| `DISABLE_OMC=1` | Same as `DISABLE_OMNI=1`; emits deprecation warning to stderr |

The deprecation warning is de-duplicated via `.omni/cache/omc-deprecation-warned` sentinel file: it is emitted at most once per project. <!-- omni-rename-allow: legacy sentinel filename -->

**Migration:** Replace `OMC_SKIP_HOOKS` with `OMNI_SKIP_HOOKS`, and `DISABLE_OMC` with `DISABLE_OMNI`. Deadline: v3.0.0.

---

## 4. Audit Log Schema

**File:** `.omni/audit/hooks.jsonl`
**Format:** One JSON object per line (JSONL).
**Access:** Atomic file-locked append (POSIX `fcntl.flock`, Windows `msvcrt.locking`).

### Record fields

| Field | Type | Description |
|---|---|---|
| `ts` | float | Unix timestamp (seconds since epoch) |
| `hook` | string | Hook name: `pre_tool_use`, `post_tool_use`, `session_start`, `user_prompt_submit` |
| `event_name` | string | Event type (same as hook name for now) |
| `tool_name` | string | Tool being invoked (empty for session/prompt hooks) |
| `prompt_excerpt` | string | First 120 chars of command or prompt (empty if not applicable) |
| `action` | string | `allow`, `deny`, `log`, `banner`, `router_dispatch` |
| `reason` | string | Human-readable reason (empty for allow) |

### Example

```jsonl
{"ts": 1714000000.123, "hook": "pre_tool_use", "event_name": "pre_tool_use", "tool_name": "shell", "prompt_excerpt": "ls -la", "action": "allow", "reason": ""}
{"ts": 1714000001.456, "hook": "pre_tool_use", "event_name": "pre_tool_use", "tool_name": "shell", "prompt_excerpt": "sudo rm -rf /", "action": "deny", "reason": "copilot-omni policy: blocked command 'sudo '"}
```

---

## 5. Metrics Schema

**File:** `.omni/audit/metrics.jsonl`
**Format:** One JSON object per line (JSONL).
**Access:** Same atomic file-lock as audit log.

### Record fields

| Field | Type | Description |
|---|---|---|
| `ts` | float | Unix timestamp |
| `name` | string | Metric name (see below) |
| `value` | any | Numeric or string metric value |
| `labels` | object | Key-value labels |

### Emitted metrics

| Metric name | Value type | Labels | Description |
|---|---|---|---|
| `hook_latency_ms` | float | `hook` | End-to-end hook execution time in milliseconds |
| `hook_exit_code` | int | `hook`, `action` | Always 0 (hooks never exit non-zero) |
| `router_decision` | string | `hook` | Router decision: `proceed`, `redirect`, `bypass` |
| `skill_trigger_matched` | int (0/1) | `hook` | 1 if a skill trigger matched the prompt |

---

## 6. Policy File Expectations

Policy files live under `policies/` (e.g. `policies/standard.json`, `policies/strict.json`, `policies/permissive.json`).

**Permission:** Files should have mode `<= 0o644` (owner read-write, group/world read-only).  
**Detection:** At session start, `session_start.py` checks all `policies/*.json` files. Files with mode `> 0o644` cause a `<policy-warning>` in the banner context. This does NOT fail the session.

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

## 7. Frontmatter `triggers:` Integration

`user_prompt_submit.py` reads `triggers:` fields from each skill's `SKILL.md` frontmatter at hook startup. When the user's prompt contains a trigger string (case-insensitive substring match), a `<skill-trigger-hint>` block is appended to `additionalContext`.

**Frontmatter format:**
```yaml
---
name: wiki
triggers: ["wiki", "wiki this", "wiki add"]
---
```

**Output block:**
```
<skill-trigger-hint skill="wiki" triggers="wiki, wiki this">Skill /wiki matched trigger(s): wiki, wiki this</skill-trigger-hint>
```

The trigger map is built once at hook startup (expected overhead < 20ms for 30-skill trees). It is held in the `_TRIGGER_MAP` module-level dict.

---

## 8. Timeout Budget

Each hook must complete within **5 seconds** (harness hard wall). Implementation target is p99 < 100ms.

| Hook | Typical latency | Bottleneck |
|---|---|---|
| `session_start` | < 30ms (cache hit) / < 80ms (cache miss) | Skill tree scan on cache miss |
| `pre_tool_use` | < 5ms | Policy JSON read |
| `post_tool_use` | < 5ms | Audit file append |
| `user_prompt_submit` | < 50ms | Router classify + trigger scan |

File lock acquisition is bounded to **1 second** per audit write. If the lock cannot be acquired within budget, the write is dropped with a stderr warning — the hook never blocks past this limit.

---

## 9. Shared Library

All hooks share `hooks/_hook_lib.py` which provides:

- `_hook_disabled(hook_name)` — kill-switch check
- `_deprecation_warn()` — one-shot legacy var warning
- `_append_audit(record)` — atomic JSONL audit append
- `_write_metric(name, value, labels)` — atomic JSONL metrics append

`_hook_lib.py` is loaded via `importlib.util.spec_from_file_location` so it does not need to be on `sys.path` and the hook scripts remain self-contained.

---

## 10. Deprecation Timeline

| Version | Change |
|---|---|
| v2.0.0 (current) | `OMC_SKIP_HOOKS` and `DISABLE_OMC` accepted with deprecation warning |
| v3.0.0 | `OMC_SKIP_HOOKS` and `DISABLE_OMC` **removed**. Use `OMNI_SKIP_HOOKS` / `DISABLE_OMNI`. |
