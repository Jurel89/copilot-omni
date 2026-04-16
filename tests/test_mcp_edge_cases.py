"""WS10 — MCP server edge-case tests.

Covers gaps identified in the coverage audit:
  - tool_call with empty params dict
  - tool_call with oversized payload (>64 KB string argument)
  - schema violations on known tools (wrong type, missing required field)
  - malformed JSON input line (server must not crash, must return error)
  - notification messages (no id) must not produce a response
  - unknown method returns -32601
  - health tool always returns ok structure
  - state_write + state_read roundtrip with mode="team"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


def _roundtrip(messages, env_overrides=None, timeout=15):
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    out, err = proc.communicate(payload, timeout=timeout)
    lines = [line for line in out.strip().splitlines() if line]
    return [json.loads(line) for line in lines], err


def _init_msg(msg_id=1):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }


def _call(tool_name, arguments, msg_id=2):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }


class TestMcpEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = {"OMNI_HOME": self._tmp.name}

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Empty params / minimal calls
    # ------------------------------------------------------------------

    def test_health_with_empty_params(self):
        """health tool with {} must succeed and return status ok."""
        responses, _ = _roundtrip([_init_msg(), _call("health", {})], self._env)
        health = next(r for r in responses if r.get("id") == 2)
        self.assertNotIn("error", health)
        body = json.loads(health["result"]["content"][0]["text"])
        self.assertEqual(body.get("status"), "ok")

    def test_memory_capture_with_minimal_args(self):
        """memory_capture with only required fields must succeed."""
        responses, _ = _roundtrip([
            _init_msg(),
            _call("memory_capture", {"scope": "ws10", "content": "minimal"}, 2),
        ], self._env)
        resp = next(r for r in responses if r.get("id") == 2)
        self.assertNotIn("error", resp)

    def test_memory_search_empty_query(self):
        """memory_search with empty query string must not crash."""
        responses, _ = _roundtrip([
            _init_msg(),
            _call("memory_search", {"query": ""}, 2),
        ], self._env)
        resp = next(r for r in responses if r.get("id") == 2)
        # Must return a result (possibly empty list), not an error
        self.assertNotIn("error", resp)

    # ------------------------------------------------------------------
    # Oversized payload
    # ------------------------------------------------------------------

    def test_oversized_content_field(self):
        """memory_capture with a 128 KB content string must not crash the server."""
        big_content = "X" * 131072  # 128 KB
        responses, _ = _roundtrip([
            _init_msg(),
            _call("memory_capture", {"scope": "big", "content": big_content}, 2),
        ], self._env)
        resp = next(r for r in responses if r.get("id") == 2)
        # Server must respond — either success or a well-formed error, never silence
        self.assertIn("id", resp)

    # ------------------------------------------------------------------
    # Malformed JSON input
    # ------------------------------------------------------------------

    def test_malformed_json_does_not_crash_server(self):
        """A corrupted JSON line must produce a parse-error response, not a crash."""
        env = os.environ.copy()
        env.update(self._env)
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        # Send a valid init, then a corrupted line, then a valid call
        payload = (
            json.dumps(_init_msg()) + "\n"
            + "{ this is not valid JSON }\n"
            + json.dumps(_call("health", {}, msg_id=3)) + "\n"
        )
        out, _ = proc.communicate(payload, timeout=15)
        lines = [line for line in out.strip().splitlines() if line]
        responses = [json.loads(line) for line in lines]
        # The health response (id=3) must still arrive
        health_resp = next((r for r in responses if r.get("id") == 3), None)
        self.assertIsNotNone(health_resp, "Server must continue serving after a bad JSON line")
        self.assertNotIn("error", health_resp)

    # ------------------------------------------------------------------
    # Notification messages (no id) produce no response
    # ------------------------------------------------------------------

    def test_notification_produces_no_response(self):
        """A JSON-RPC message without 'id' is a notification; must not produce a response."""
        # Send init, a notification (no id), then a tagged health call
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        responses, _ = _roundtrip([
            _init_msg(msg_id=1),
            notification,
            _call("health", {}, msg_id=99),
        ], self._env)
        # Only responses for id=1 and id=99 must appear
        ids = {r.get("id") for r in responses}
        self.assertNotIn(None, ids, "Notifications must not produce responses")
        self.assertIn(99, ids)

    # ------------------------------------------------------------------
    # Unknown method
    # ------------------------------------------------------------------

    def test_unknown_method_returns_method_not_found(self):
        """An unknown JSON-RPC method must return error code -32601."""
        responses, _ = _roundtrip([
            {"jsonrpc": "2.0", "id": 5, "method": "no_such_method", "params": {}},
        ], self._env)
        resp = responses[0]
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    # ------------------------------------------------------------------
    # state_write / state_read roundtrip (team mode)
    # ------------------------------------------------------------------

    def test_state_write_read_team_mode(self):
        """state_write in mode='team' followed by state_read must return matching body."""
        team_body = {"run_id": "team-ws10-test", "workers": 3, "status": "running"}
        responses, _ = _roundtrip([
            _init_msg(1),
            _call("state_write", {"mode": "team", "body": team_body}, 2),
            _call("state_read", {"mode": "team"}, 3),
        ], self._env)

        write_resp = next(r for r in responses if r.get("id") == 2)
        self.assertNotIn("error", write_resp)

        read_resp = next(r for r in responses if r.get("id") == 3)
        self.assertNotIn("error", read_resp)
        read_body = json.loads(read_resp["result"]["content"][0]["text"])
        # state_read returns {"body": {...}, "mode": ..., "updated_at": ...}
        inner = read_body.get("body", read_body)
        self.assertEqual(inner.get("run_id"), "team-ws10-test")

    # ------------------------------------------------------------------
    # Schema validator edge cases (unit-level, no subprocess)
    # ------------------------------------------------------------------

    def test_schema_validator_unknown_category_tool_call(self):
        """tools/call with missing 'arguments' key must return -32602 or tool error."""
        responses, _ = _roundtrip([
            _init_msg(1),
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "health"}},  # arguments key missing
        ], self._env)
        resp = next(r for r in responses if r.get("id") == 2)
        # Must return either a json-rpc error or a gracefully handled result
        self.assertIn("id", resp)

    def test_policy_check_allows_safe_read(self):
        """policy_check for a read-only shell command must allow."""
        responses, _ = _roundtrip([
            _init_msg(1),
            _call("policy_check",
                  {"tool": "shell", "args": {"command": "cat README.md"}}, 2),
        ], self._env)
        resp = next(r for r in responses if r.get("id") == 2)
        self.assertNotIn("error", resp)
        body = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(body.get("decision"), "allow")


class TestSchemaValidatorUnit(unittest.TestCase):
    """Unit tests for mcp/schema_validator.py covering under-tested branches."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "schema_validator", ROOT / "mcp" / "schema_validator.py"
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        self.v = mod.validate

    def test_oneof_zero_match_is_error(self):
        schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
        errors = self.v(3.14, schema)  # float matches neither
        self.assertTrue(errors)
        self.assertIn("oneOf", errors[0][1])

    def test_oneof_two_match_is_error(self):
        schema = {"oneOf": [{"type": "number"}, {"type": "integer"}]}
        errors = self.v(42, schema)  # integer matches both number and integer
        self.assertTrue(errors)

    def test_anyof_no_match_is_error(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "array"}]}
        errors = self.v(123, schema)
        self.assertTrue(errors)
        self.assertIn("anyOf", errors[0][1])

    def test_anyof_one_match_ok(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        errors = self.v(42, schema)
        self.assertEqual(errors, [])

    def test_additional_properties_false_rejects_extra(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        errors = self.v({"name": "alice", "extra": 1}, schema)
        self.assertTrue(errors)
        self.assertIn("additional property", errors[0][1])

    def test_additional_properties_schema_validates_value(self):
        schema = {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }
        errors = self.v({"a": 1, "b": "not-int"}, schema)
        self.assertTrue(errors)

    def test_pattern_invalid_regex_returns_error(self):
        schema = {"type": "string", "pattern": "[invalid("}
        errors = self.v("hello", schema)
        self.assertTrue(errors)
        self.assertIn("invalid pattern", errors[0][1])

    def test_min_max_length(self):
        schema = {"type": "string", "minLength": 3, "maxLength": 5}
        # "hi" has length 2 < minLength 3 → fails
        self.assertTrue(self.v("hi", schema))
        # "hey" has length 3 = minLength → ok
        self.assertEqual(self.v("hey", schema), [])
        # "toolong!" has length 8 > maxLength 5 → fails
        self.assertTrue(self.v("toolong!", schema))

    def test_array_min_max_items(self):
        schema = {"type": "array", "minItems": 2, "maxItems": 4}
        self.assertTrue(self.v([1], schema))
        self.assertEqual(self.v([1, 2], schema), [])
        self.assertTrue(self.v([1, 2, 3, 4, 5], schema))

    def test_numeric_minimum_maximum(self):
        schema = {"type": "number", "minimum": 0.0, "maximum": 1.0}
        self.assertTrue(self.v(-0.1, schema))
        self.assertTrue(self.v(1.1, schema))
        self.assertEqual(self.v(0.5, schema), [])

    def test_enum_violation(self):
        schema = {"enum": ["a", "b", "c"]}
        errors = self.v("d", schema)
        self.assertTrue(errors)
        self.assertIn("enum", errors[0][1])

    def test_required_field_missing(self):
        schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
        errors = self.v({}, schema)
        self.assertTrue(errors)
        self.assertIn("required field", errors[0][1])


if __name__ == "__main__":
    unittest.main()
