# Security

## Reporting vulnerabilities

Email the maintainer or open a private GitHub security advisory. Please do not open public issues for vulnerabilities.

## Threat model

Copilot Omni is a **development-time orchestration layer** for GitHub Copilot CLI sessions. It runs with the same privileges as the Copilot CLI process itself — which is the same as the user. It does not run services, network listeners, privileged daemons, or background agents.

### In scope

- Protecting plugin-managed files (`.omni/config.json`, `.claude-plugin/plugin.json`, `AGENTS.md`, …) from accidental modification by the LLM.
- Defense-in-depth against obviously-dangerous shell commands (`sudo`, `rm -rf /`, `mkfs`, fork bombs, `dd if=/dev/zero`).
- Keeping the runtime footprint EDR-compatible: pure Python stdlib, no compiled artifacts, no third-party imports.
- Path-traversal protection for MCP tools that write to disk (`wiki_write`). The shared `_safe_identifier` / `_safe_child_path` helpers in `mcp/server.py` reject absolute paths, `..` segments, and non-alphanumeric run IDs. (The legacy `artifact_write` and `workspace` tools were removed in Phase-C C23; their traversal guards remain covered by `tests/test_security.py::TestPathTraversalHelpers`.)
- Stdlib-only discipline enforced at CI-time by `scripts/check_stdlib_only.py`.

### Out of scope (explicit non-goals)

- **Policy engine is advisory, not authoritative.** Policy enforcement is via the MCP `policy_check` tool, which does best-effort pattern matching on tool arguments. Skilled adversaries who control the LLM's input can craft commands that bypass substring and token matching (base64-piped payloads, unusual binary paths, command substitution). The engine raises the cost of accidental damage; it is not a sandbox.
- **No authentication.** The MCP server listens on stdio, started by Copilot CLI under the invoking user. Anyone who can start `python3 mcp/server.py` on your machine can already read your files.
- **No crypto.** The SQLite store at `$OMNI_HOME/omni.db` is plaintext. Don't put secrets in `memory_capture`/`wiki_write` unless you encrypt them upstream.
- **Supply chain of Copilot CLI itself** is not validated by this plugin.

### Policy profiles

Three shipped profiles, selected via `$OMNI_POLICY_PROFILE`:

| Profile | Use case |
|---------|----------|
| `permissive` | Trusted solo dev, minimal guardrails |
| `standard` (default) | Corporate dev laptop with EDR |
| `strict` | Shared build host / heightened review |

Custom profiles live at `<cwd>/.omni/policy-<name>.json`. **Project-level policy files are trusted on read.** If you `cd` into a hostile repo that ships `.omni/policy-standard.json` with an empty `deny_commands`, you have disabled the project-scoped policy. The plugin-default policy still applies. We intentionally do not sign policy files; treat them the way you treat `.envrc` or `package.json` scripts.

### Known bypasses (documented, accepted)

- **Base64 / eval / background subshell** bypass deny-patterns: `printf '%s' c29 | base64 -d | sh` is not matched. The pre-tool hook does not evaluate shell-equivalent meanings; pattern-matching shell commands for intent is undecidable.
- **Unicode normalization** on case-insensitive filesystems: path comparison is case-folded but not NFC/NFD normalized. A filename differing only in combining-character form may evade protected-path checks. On Linux this is not exploitable.
- **Non-canonical tool names** (tools the LLM invokes under a name we don't know about) are not gated. The hook matches against a known set: `shell`, `bash`, `write`, `edit`, `edit_file`, `multi_edit`, `multiedit`, `patch`, `apply_patch`, `str_replace_editor`. New tool names added by future Copilot CLI versions will fail open until the plugin is updated.

### Hardening recommendations

1. Use profile=`strict` on CI and shared build hosts.
2. Run Copilot CLI without `--allow-all` for untrusted sessions; the plugin's subagent helper now defaults to interactive approval (opt in via `OMNI_SUBAGENT_ALLOW_ALL=1`).
3. Consider writing a custom `.omni/policy-<you>.json` that extends `protected_paths` with your repo's secret files and deploy configs.
4. Review `.omni/audit/tool-audit.log` periodically. Rotate and archive.

## Disclosure history

- 2026-04-16: initial v1.0.0 release.

## References

- `policies/*.json` — shipped profiles.
- `mcp/server.py` `policy_check` tool — runtime policy enforcement (MCP endpoint).
- `tests/test_security.py` — regression suite.
