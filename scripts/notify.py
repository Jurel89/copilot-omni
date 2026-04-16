#!/usr/bin/env python3
"""Phase-C C15: notification dispatcher for copilot-omni.

Reads configured targets from .omni/config.json > notifications and
posts messages to each webhook. Supported targets:

- telegram  — Bot API (bot_token + chat_id)
- slack     — incoming webhook URL
- discord   — webhook URL

Network failures are ALWAYS non-fatal: the caller should not block on
a webhook outage. Errors are logged to stderr; exit code is 0.

Stdlib only (uses urllib.request).

Usage:
    python3 scripts/notify.py configure <target> [--bot-token X] \\
        [--chat-id Y] [--webhook Z] [--events start,done,error]

    python3 scripts/notify.py emit <event> "<message>"
    python3 scripts/notify.py list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_EVENTS = ("done", "error")
SUPPORTED = ("telegram", "slack", "discord")
DEFAULT_TIMEOUT = 10.0


def _config_path(repo_root: Path) -> Path:
    return repo_root / ".omni" / "config.json"


def _load_config(repo_root: Path) -> dict:
    p = _config_path(repo_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(repo_root: Path, data: dict) -> None:
    p = _config_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))


def _parse_events(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_EVENTS)
    return [e.strip() for e in raw.split(",") if e.strip()]


def configure(repo_root: Path, target: str, *, bot_token: str | None,
              chat_id: str | None, webhook: str | None,
              events: list[str]) -> dict:
    if target not in SUPPORTED:
        raise ValueError(f"unsupported target {target!r}; one of {SUPPORTED}")
    entry: dict[str, Any] = {"target": target, "events": events}
    if target == "telegram":
        if not bot_token or not chat_id:
            raise ValueError("telegram requires --bot-token and --chat-id")
        entry["bot_token"] = bot_token
        entry["chat_id"] = chat_id
    else:
        if not webhook:
            raise ValueError(f"{target} requires --webhook")
        entry["webhook"] = webhook
    cfg = _load_config(repo_root)
    targets = cfg.setdefault("notifications", [])
    # Replace existing entry for the same target+identifier.
    ident_key = "webhook" if target != "telegram" else "chat_id"
    ident = entry[ident_key]
    targets[:] = [t for t in targets
                  if not (t.get("target") == target
                          and t.get(ident_key) == ident)]
    targets.append(entry)
    _save_config(repo_root, cfg)
    return entry


def list_targets(repo_root: Path) -> list[dict]:
    cfg = _load_config(repo_root)
    out: list[dict] = []
    for t in cfg.get("notifications", []):
        masked = dict(t)
        if "bot_token" in masked:
            masked["bot_token"] = masked["bot_token"][:6] + "…"
        if "webhook" in masked:
            # Mask the whole path component after the host.
            wh = masked["webhook"]
            if "://" in wh:
                scheme, rest = wh.split("://", 1)
                host = rest.split("/", 1)[0]
                masked["webhook"] = f"{scheme}://{host}/…"
        out.append(masked)
    return out


def _post(url: str, payload: dict, headers: dict | None = None,
          timeout: float = DEFAULT_TIMEOUT) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(1024).decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"network error: {exc}"


def emit(repo_root: Path, event: str, message: str) -> int:
    """Emit *message* for *event* to every matching configured target.

    Returns 0 even on network failure (non-fatal per contract).
    """
    cfg = _load_config(repo_root)
    targets = cfg.get("notifications", [])
    delivered = 0
    for t in targets:
        if event not in t.get("events", DEFAULT_EVENTS):
            continue
        target = t.get("target")
        body = f"[{event}] {message}"
        if target == "telegram":
            url = (f"https://api.telegram.org/bot{t['bot_token']}"
                   "/sendMessage")
            status, resp = _post(url, {"chat_id": t["chat_id"], "text": body})
        elif target == "slack":
            status, resp = _post(t["webhook"], {"text": body})
        elif target == "discord":
            status, resp = _post(t["webhook"], {"content": body})
        else:
            continue
        if 200 <= status < 300:
            delivered += 1
        else:
            print(f"notify: {target} POST failed status={status}: {resp[:160]}",
                  file=sys.stderr)
    return delivered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Notification dispatcher (Phase-C C15)"
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("configure", help="Add/replace a notification target")
    c.add_argument("target", choices=SUPPORTED)
    c.add_argument("--bot-token")
    c.add_argument("--chat-id")
    c.add_argument("--webhook")
    c.add_argument("--events", default=",".join(DEFAULT_EVENTS))

    sub.add_parser("list", help="List configured targets (credentials masked)")

    e = sub.add_parser("emit", help="Emit an event to all matching targets")
    e.add_argument("event")
    e.add_argument("message")

    args = parser.parse_args(argv)
    repo_root = args.repo_root or Path.cwd()

    if args.command == "configure":
        try:
            entry = configure(
                repo_root, args.target,
                bot_token=args.bot_token,
                chat_id=args.chat_id,
                webhook=args.webhook,
                events=_parse_events(args.events),
            )
        except ValueError as exc:
            print(f"notify configure: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(entry, indent=2))
        return 0
    if args.command == "list":
        print(json.dumps(list_targets(repo_root), indent=2))
        return 0
    if args.command == "emit":
        delivered = emit(repo_root, args.event, args.message)
        print(f"delivered={delivered}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
