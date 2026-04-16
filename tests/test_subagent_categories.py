"""Tests for subagent.py --category flag (WS4)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Load subagent and category_resolver from the scripts/ directory directly
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_module(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


subagent = _load_module("subagent")
resolver = _load_module("category_resolver")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_agent_args(**overrides):
    """Return default kwargs for run_agent(), with overrides applied."""
    defaults = {
        "name": "executor",
        "prompt": "do the thing",
        "allow_all": False,
        "model": None,
        "category": None,
        "timeout": 1800,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests: resolution path (--category, no --model)
# ---------------------------------------------------------------------------


def test_category_quick_resolves_to_model(monkeypatch):
    """--category quick should resolve and pass --model to copilot."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/copilot")
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return mock.Mock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    # Override the resolver to return a known model without shelling out
    def fake_checker(model: str) -> bool:
        return True

    with mock.patch.object(subagent, "_resolve_category", return_value="claude-haiku-4-5"):
        rc = subagent.run_agent(
            "executor", "do the thing",
            allow_all=False, model=None, category="quick",
        )

    assert rc == 0


def test_category_deep_resolves_to_model(monkeypatch):
    """--category deep resolves via category_resolver and passes --model."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/copilot")
    used_models: list = []

    def fake_run(cmd, **kwargs):
        # Capture what --model was passed (if any)
        if "--model" in cmd:
            idx = cmd.index("--model")
            used_models.append(cmd[idx + 1])
        return mock.Mock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    # Use real resolver with a fake availability checker that always says True
    def always_available(model: str) -> bool:
        return True

    cfg = resolver.load_default_categories()
    res = resolver.resolve("deep", config=cfg, availability_checker=always_available)
    assert res["model"] == "claude-sonnet-4.5"
    assert res["fallbacks_tried"] == []
    assert res["available_check"] == "ok"


def test_category_ultrabrain_default(monkeypatch):
    """ultrabrain category defaults to claude-opus-4-6."""
    def always_available(model: str) -> bool:
        return True

    cfg = resolver.load_default_categories()
    res = resolver.resolve("ultrabrain", config=cfg, availability_checker=always_available)
    assert res["model"] == "claude-opus-4-6"
    assert res["primary"] == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Tests: override path (--model wins over --category)
# ---------------------------------------------------------------------------


def test_explicit_model_overrides_category(monkeypatch):
    """If --model and --category both given, --model wins."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/copilot")
    used_models: list = []

    def fake_run(cmd, **kwargs):
        if "--model" in cmd:
            idx = cmd.index("--model")
            used_models.append(cmd[idx + 1])
        return mock.Mock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    rc = subagent.run_agent(
        "executor", "do the thing",
        allow_all=False, model="explicit-model-override", category="quick",
    )
    assert rc == 0
    assert used_models == ["explicit-model-override"]


# ---------------------------------------------------------------------------
# Tests: neither given — behavior unchanged
# ---------------------------------------------------------------------------


def test_neither_model_nor_category(monkeypatch):
    """If neither --model nor --category given, no --model flag is passed."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/copilot")
    full_cmd: list = []

    def fake_run(cmd, **kwargs):
        full_cmd.extend(cmd)
        return mock.Mock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    rc = subagent.run_agent(
        "executor", "do the thing",
        allow_all=False, model=None, category=None,
    )
    assert rc == 0
    assert "--model" not in full_cmd


# ---------------------------------------------------------------------------
# Tests: unknown category → clean error
# ---------------------------------------------------------------------------


def test_unknown_category_returns_error(monkeypatch, capsys):
    """An unknown category should return exit code 1 without calling copilot."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/copilot")
    called = []

    def fake_run(cmd, **kwargs):
        called.append(cmd)
        return mock.Mock(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    rc = subagent.run_agent(
        "executor", "do the thing",
        allow_all=False, model=None, category="nonexistent-category",
    )
    assert rc == 1
    assert called == []  # copilot was never invoked
    captured = capsys.readouterr()
    assert "nonexistent-category" in captured.err or "unknown" in captured.err.lower()


# ---------------------------------------------------------------------------
# Tests: category resolver fallback walk
# ---------------------------------------------------------------------------


def test_fallback_walk_when_primary_unavailable():
    """Resolver should walk fallbacks when primary model is unavailable."""

    def primary_down(model: str) -> bool:
        # Only the first fallback is available
        return model == "gpt-5-mini"

    cfg = resolver.load_default_categories()
    res = resolver.resolve("quick", config=cfg, availability_checker=primary_down)
    assert res["model"] == "gpt-5-mini"
    assert res["primary"] == "claude-haiku-4-5"
    assert "gpt-5-mini" in res["fallbacks_tried"]


def test_fallback_exhausted_returns_primary():
    """When all fallbacks are down, resolver returns primary (fail-open)."""

    def all_down(model: str) -> bool:
        return False

    cfg = resolver.load_default_categories()
    res = resolver.resolve("quick", config=cfg, availability_checker=all_down)
    # Must return primary even when all are down
    assert res["model"] == res["primary"]
    assert len(res["fallbacks_tried"]) == len(cfg["quick"]["fallbacks"])


def test_resolver_never_raises_on_bad_input():
    """resolve() must not raise for any input."""
    res = resolver.resolve("totally-invalid-cat")
    assert isinstance(res, dict)
    assert "model" in res
    assert "available_check" in res


# ---------------------------------------------------------------------------
# Tests: resolver resolution dict shape
# ---------------------------------------------------------------------------


def test_resolution_dict_has_required_keys():
    """resolve() always returns a dict with all required keys."""
    def always_ok(model: str) -> bool:
        return True

    for cat in resolver.known_categories():
        res = resolver.resolve(cat, availability_checker=always_ok)
        assert "category" in res
        assert "model" in res
        assert "primary" in res
        assert "fallbacks_tried" in res
        assert "available_check" in res
        assert "ts" in res
        assert res["category"] == cat
        assert isinstance(res["fallbacks_tried"], list)


# ---------------------------------------------------------------------------
# Tests: CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_known_flag(capsys):
    """--known should print the three category names and exit 0."""
    rc = resolver.main(["--known"])
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert rc == 0
    assert set(lines) == {"quick", "deep", "ultrabrain"}


def test_cli_json_flag(capsys):
    """--json <category> should print valid JSON with required keys."""
    rc = resolver.main(["--json", "deep"])
    captured = capsys.readouterr()
    assert rc == 0
    data = __import__("json").loads(captured.out)
    assert data["category"] == "deep"
    assert "model" in data
    assert "primary" in data
    assert "fallbacks_tried" in data


def test_cli_unknown_category_exits_nonzero(capsys):
    """Passing an unknown category to the CLI should exit non-zero."""
    rc = resolver.main(["unknown-cat"])
    assert rc != 0


def test_cli_no_args_exits_2(capsys):
    """Running with no arguments should exit with code 2 (usage error)."""
    rc = resolver.main([])
    assert rc == 2
