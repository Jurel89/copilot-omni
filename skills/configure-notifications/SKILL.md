---
name: configure-notifications
description: Wire Telegram / Discord / Slack notifications for copilot-omni run events (start, progress, completion, error)
argument-hint: "<target> <webhook-or-token> [--events=start,progress,done,error]"
triggers: ["configure notifications", "setup notifications", "notify me", "slack webhook", "telegram bot", "discord webhook"]
priority: 60
level: 2
---

<Purpose>
Let copilot-omni post notifications to Telegram, Discord, or Slack when run
events fire. The skill is declarative: you give it a webhook (Discord,
Slack) or a bot token + chat-id pair (Telegram), and it writes a config
entry under .omni/config.json > notifications. The helper script
scripts/notify.py reads that config and emits on stdin → HTTP POST.
</Purpose>

<Use_When>
- User asks for Slack / Discord / Telegram notifications.
- User wants to know when a long autopilot run finishes.
- User is setting up an ops on-call handoff for a repo-scoped
  automation (CI mirror, nightly scheduled skill).
</Use_When>

<Do_Not_Use_When>
- User wants email — not supported by this skill (v1.1 backlog).
- User wants PagerDuty incidents — out of scope; integrate via Slack
  webhook + PagerDuty's Slack app.
- User wants per-event templating beyond the four built-in event
  types (start|progress|done|error) — edit scripts/notify.py directly.
</Do_Not_Use_When>

## Configuration shape

Entries are persisted under `.omni/config.json`:

```jsonc
{
  "notifications": [
    { "target": "telegram",
      "bot_token": "123:ABC…",
      "chat_id": "-1001234567890",
      "events": ["done", "error"] },
    { "target": "slack",
      "webhook": "https://hooks.slack.com/services/…",
      "events": ["start", "progress", "done", "error"] },
    { "target": "discord",
      "webhook": "https://discord.com/api/webhooks/…",
      "events": ["error"] }
  ]
}
```

- `events` defaults to `["done", "error"]` when omitted.
- Credentials never leave `.omni/config.json`; the hooks only read-through.

## Usage

```bash
# Add a Telegram channel for done+error events
python3 scripts/notify.py configure telegram \
    --bot-token "$TELEGRAM_BOT_TOKEN" \
    --chat-id "$TELEGRAM_CHAT_ID" \
    --events done,error

# Emit a test event
python3 scripts/notify.py emit done "autopilot finished cleanly"

# List configured targets (credentials elided)
python3 scripts/notify.py list
```

## Triggering from skills

Long-running skills (autopilot, ralph, ultrawork, team) SHOULD call
`scripts/notify.py emit <event> "<message>"` at the matching lifecycle
transitions. Failure to reach the remote service is non-fatal — notify.py
logs the HTTP error to stderr and exits 0 so the main run is not
blocked on a webhook outage.

## See also

- `docs/STATE-MACHINE.md` — the four-gate lifecycle that drives event
  emission points.
