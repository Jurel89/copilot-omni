---
name: mcp-setup
description: Understand and verify the MCP tools provided by copilot-omni
level: 2
---

# MCP Setup

copilot-omni serves 30 MCP tools over stdio JSON-RPC 2.0 via `mcp/server.py`. This skill helps you verify the MCP layer is healthy and understand what tools are available.

## Overview

MCP (Model Context Protocol) tools extend Copilot CLI sessions with structured capabilities for memory, state, tracing, and more. All copilot-omni MCP tools are served by a single Python file (`mcp/server.py`) using only the Python 3.9 stdlib.

## Step 1: Verify MCP Server Health

Run the built-in health check:

```bash
python3 scripts/omni.py doctor
```

Or test the MCP server directly:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 mcp/server.py
```

## Step 2: List Available MCP Tools

copilot-omni provides these MCP tool categories:

**Memory:**
- `memory_capture` — save a note to the memory store
- `memory_search` — query saved memories
- `memory_prune` — remove old memories
- `memory_export` — export memories to a file

**State:**
- `state_write` — persist key-value state
- `state_read` — read persisted state
- `state_clear` — remove state entries

**Wiki:**
- `wiki_write` — create or update a wiki entry
- `wiki_read` — read a wiki entry
- `wiki_query` — search the wiki
- `wiki_list` — list all wiki entries
- `wiki_ingest` — ingest external content
- `wiki_graph` — build a relationship graph

**Codebase:**
- `codebase_graph` — build a repository file/import/reference graph
- `codebase_impact` — show immediate refactor impact for a file

**Notepad:**
- `notepad_write` — write to the project notepad
- `notepad_read` — read from the notepad
- `notepad_prune` — clean old notepad entries

**Shared Memory:**
- `shared_memory_write` — write to shared memory
- `shared_memory_read` — read from shared memory

**Trace:**
- `trace_summary` — aggregate trace evidence
- `trace_timeline` — build a causal timeline

**Code Intelligence:**
- `lsp_hover` — get symbol info via LSP
- `lsp_goto_definition` — jump to definition
- `lsp_find_references` — find symbol references
- `ast_grep_search` — search code with AST patterns
- `ast_grep_replace` — replace code with AST patterns

**Policy + Health:**
- `policy_check` — validate against policy rules
- `health` — check plugin health
- `doctor` — run full diagnostics

## Step 3: Verify Tool Registration

Ensure the plugin manifest (`plugin.json`) correctly registers the MCP server:

```bash
python3 -c "import json; d=json.load(open('plugin.json')); print('mcpServer' in d and 'mcp/server.py' in str(d))"
```

The `.mcp.json` file at the plugin root should point to `mcp/server.py`:

```json
{
  "command": "python3",
  "args": ["mcp/server.py"]
}
```

## Step 4: Test a Tool Call

Test a simple state write/read cycle to confirm the full pipeline works:

```bash
# Write state
cat <<'PY' | python3 mcp/server.py
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"state_write","arguments":{"mode":"test","body":{"value":42}}}}
PY

# Read it back
cat <<'PY' | python3 mcp/server.py
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"state_read","arguments":{"mode":"test"}}}
PY
```

## Completion Message

```
MCP Configuration Check Complete!

BUILT-IN TOOLS:
- 30 MCP tools available via mcp/server.py
- All tools schema-validated on every call
- Storage: WAL-mode SQLite at $OMNI_HOME/omni.db

NEXT STEPS:
1. Use `/copilot-omni:omni-doctor` if any check failed
2. Tools are automatically available to all agents
3. See docs/STATE_MODES.md for the mode-key registry

USAGE TIPS:
- Memory: persist notes across sessions with memory_capture
- State: track workflow progress with state_write/state_read
- Wiki: build project knowledge bases with wiki_write
- Trace: investigate issues with trace_summary and trace_timeline

TROUBLESHOOTING:
- If mcp/server.py fails to start, run `python3 scripts/omni.py doctor --fix-python`
- Ensure Python 3.9+ is on PATH
- Check that $OMNI_HOME/omni.db is writable
- Run /copilot-omni:omni-doctor to diagnose issues
```

## Custom MCP Servers

If you need additional MCP servers beyond the 30 built-in tools, configure them through Copilot CLI's plugin system or your shell environment. copilot-omni does not provide a custom MCP installer; refer to the Copilot CLI documentation for adding external MCP servers.

## Common Issues

### MCP Server Not Responding
- Ensure Python 3.9+ is installed and `python3` is on PATH
- Check that `mcp/server.py` exists in the plugin directory
- Run `python3 scripts/omni.py doctor` for full diagnostics

### State Tool Errors
- Verify `$OMNI_HOME/omni.db` exists and is writable (default: `~/.omni/omni.db`)
- Run `python3 scripts/omni.py doctor` to check database schema

### Agents Not Using MCP Tools
- Confirm the plugin is installed: `copilot plugin list`
- Check `.mcp.json` points to the correct server path
- Restart your Copilot CLI session after plugin changes
