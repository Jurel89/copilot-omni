# v1 → v2 Migration Rollback (last resort)

`scripts/omni_migrate_v1_to_v2.py --rollback` reverses the forward migration by
renaming `.omni/` back to `.omc/` in both the repo root and `~/.omc/`. It is a
last-resort recovery path and should only be used when the v2 code path is
confirmed broken on your system and you need the legacy v1 state directory
back to work around it.

## What the forward migration does

```
<repo>/.omc/  → <repo>/.omni/
~/.omc/       → ~/.omni/
```

Env-var renames handled manually (the migrator never touches shell profiles):
`OMC_SKIP_HOOKS` → `OMNI_SKIP_HOOKS`, `DISABLE_OMC` → `DISABLE_OMNI`,
`/oh-my-claudecode:*` slash-commands → `/copilot-omni:*`.

## What rollback does

`--rollback --apply` performs the inverse rename. Like the forward path the
rollback is idempotent: it refuses to overwrite an existing `.omc/` if one is
already present on disk.

```
<repo>/.omni/  → <repo>/.omc/
~/.omni/       → ~/.omc/
```

Rollback always prints a dry-run preview first; only `--apply` mutates.

## Before rolling back

1. Stop every running Copilot/Claude CLI process that might be writing to
   `.omni/` (there is no rename lock — a racing writer will lose).
2. Commit or stash any uncommitted changes under `.omni/`. `git mv` is used
   inside the repo for history preservation but will still error on dirty
   files.
3. Read `git log -- .omni/` to confirm what v2-era content will be moving back
   — anything written since the forward migration travels with the directory,
   so pinning and branching v2 state before rollback is recommended.

## Running

```bash
# 1. Dry-run (default) — no changes, shows what would be moved
python3 scripts/omni_migrate_v1_to_v2.py --rollback

# 2. Apply — actually moves .omni/ back to .omc/
python3 scripts/omni_migrate_v1_to_v2.py --rollback --apply
```

## After rolling back

Revert your shell profile:

```
export OMC_SKIP_HOOKS=1        # if you had OMNI_SKIP_HOOKS set
export DISABLE_OMC=1           # if you had DISABLE_OMNI set
```

And revert any scripted references from `/copilot-omni:*` back to the
`/oh-my-claudecode:*` equivalents.

## Known limitations

- Rollback is a directory rename, not a content downgrade. If v2 wrote SQLite
  rows or file layouts that v1 cannot parse, rollback restores the v2 state
  *under the v1 name*. Restore from a pre-migration backup when the schema
  has genuinely diverged.
- When both `<repo>/.omni/` and `<repo>/.omc/` exist, rollback refuses that
  location with a WARN line. Resolve the conflict manually (pick one).
- Rollback never touches shell profiles, IDE settings, or CI configuration —
  those revert by hand.
