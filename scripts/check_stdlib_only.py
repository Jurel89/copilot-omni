#!/usr/bin/env python3
"""AST-based enforcement of the stdlib-only discipline.

Walks every `.py` file in the repo (excluding tests/ and scripts/ themselves
where a `subprocess` helper may import `signal` etc.) and rejects any import
of a module not in the allowlist.

Failure modes:
- a relative import (`from .foo import bar`) is permitted unconditionally.
- an absolute import (`import numpy`, `from requests import get`) that is not
  in the stdlib allowlist triggers a non-zero exit.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent

ALLOWED = {
    # Core
    "argparse", "ast", "base64", "collections", "contextlib", "copy",
    "dataclasses", "datetime", "difflib", "enum", "errno", "fnmatch",
    "functools", "getpass", "glob", "hashlib", "hmac", "html", "http",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "logging", "math", "mmap", "operator", "os", "pathlib", "pickle",
    "platform", "py_compile", "queue", "random", "re", "secrets",
    "select", "shlex", "shutil", "signal", "socket", "sqlite3", "ssl",
    "stat", "string", "struct", "subprocess", "sys", "tempfile",
    "textwrap", "threading", "time", "traceback", "types", "typing",
    "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
    "zlib",
    "__future__",
}

SCAN_PATHS = [
    ROOT / "mcp",
    ROOT / "hooks",
    ROOT / "scripts",
]


def _iter_py(paths: Iterable[Path]):
    for root in paths:
        for p in root.rglob("*.py"):
            if ".git" in p.parts:
                continue
            yield p


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def main() -> int:
    failures = []
    for p in _iter_py(SCAN_PATHS):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"{p}: failed to parse: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _top(alias.name)
                    if mod not in ALLOWED:
                        failures.append(f"{p}:{node.lineno} forbidden import {alias.name!r}")
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative import
                if not node.module:
                    continue
                mod = _top(node.module)
                if mod not in ALLOWED:
                    failures.append(f"{p}:{node.lineno} forbidden from-import {node.module!r}")
    if failures:
        print("stdlib-only violations:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"stdlib-only OK — scanned {sum(1 for _ in _iter_py(SCAN_PATHS))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
