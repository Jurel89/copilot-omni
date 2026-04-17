"""Phase-C C13: cross-OS portability invariants.

These tests run on every OS and assert that the code paths that could have
drifted between POSIX and Windows behave as documented in
docs/PORTABILITY-AUDIT.md.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPathNormalisation(unittest.TestCase):

    def test_nfc_collapses_decomposed_form(self):
        composed = "naïve"
        decomposed = unicodedata.normalize("NFD", composed)
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(unicodedata.normalize("NFC", decomposed), composed)

    def test_os_replace_is_atomic_within_dir(self):
        """os.replace overwrites the destination atomically on both platforms."""
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.txt"
            b = Path(td) / "b.txt"
            a.write_text("aaa")
            b.write_text("bbb")
            os.replace(str(a), str(b))
            self.assertFalse(a.exists())
            self.assertEqual(b.read_text(), "aaa")


class TestProcessProbes(unittest.TestCase):

    def test_is_pid_alive_self(self):
        mod = _load("pool_portable", "scripts/subagent_pool.py")
        self.assertTrue(mod._is_pid_alive(os.getpid()))

    def test_is_pid_alive_far_future(self):
        mod = _load("pool_portable_dead", "scripts/subagent_pool.py")
        self.assertFalse(mod._is_pid_alive(99_999_999))


class TestRssProbe(unittest.TestCase):

    def test_self_rss_on_linux(self):
        mod = _load("pool_portable_rss", "scripts/subagent_pool.py")
        rss = mod._rss_mb(os.getpid())
        if sys.platform.startswith("linux"):
            self.assertIsNotNone(rss)
            self.assertGreater(rss, 0)
        else:
            # Non-Linux POSIX or unsupported platform → None is allowed.
            self.assertTrue(rss is None or rss >= 0)


class TestModuleImportsAreGuarded(unittest.TestCase):
    """Platform-specific stdlib modules must be imported lazily, otherwise
    importing the file on the opposite OS would crash at module-load time."""

    def test_subagent_pool_toplevel_imports(self):
        src = (ROOT / "scripts" / "subagent_pool.py").read_text(encoding="utf-8")
        # fcntl/msvcrt must only appear inside a guarded block — i.e. they
        # cannot be at column 0 as a bare `import fcntl`.
        lines = src.splitlines()
        for mod in ("fcntl", "msvcrt"):
            top_imports = [l for l in lines if l.startswith(f"import {mod}")]
            self.assertEqual(top_imports, [],
                             f"{mod} must be inside a platform guard, not a top-level import")

    def test_audit_writer_platform_dispatch(self):
        src = (ROOT / "hooks" / "_hook_lib.py").read_text(encoding="utf-8")
        # Both branches must be wired in the same module.
        self.assertIn("fcntl", src)
        self.assertIn("msvcrt", src)


class TestDocExists(unittest.TestCase):

    def test_portability_audit_doc(self):
        doc = ROOT / "docs" / "PORTABILITY-AUDIT.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("Platform-dispatched sites", text)
        self.assertIn("NFC", text)


if __name__ == "__main__":
    unittest.main()
