---
name: wire-trigger
description: Use when the user asks to wire a trigger, defer a follow-up until a teammate signals, create a re-review link, or wait for an external one-shot signal.
---

# wire-trigger

Wire one future agent action to an opaque ntfy link. This is a standalone skill. The
default waits inside the current tool call and returns control to the same active turn.
`wire.py` lives beside this file, uses only Python's standard library, and never imports
hawk; hawk is a distribution mechanism, not a runtime dependency.

## Default: wait in this turn

Infer a short summary and a concrete future prompt from the conversation. Create a
tool-neutral foreground trigger:

```bash
python3 /absolute/path/to/wire-trigger/wire.py create \
  --summary "Re-review PR #123" \
  --prompt "Re-review PR #123 now. Check whether the earlier findings were resolved." \
  --cwd /absolute/path/to/repository \
  --allow-unconfirmed-get \
  --json
```

Resolve the script path from the directory containing this `SKILL.md`; do not hard-code
an agent-specific installation directory.

Before waiting, send a `commentary` update containing ready-to-paste prose and the
returned link. The user must be able to copy the link while the tool call is blocked:

> I've reviewed the PR. Once the updates are ready for another pass, trigger my review
> agent here: `<link>`
>
> The link becomes active two minutes after it was created.

Then wait using the returned task ID:

```bash
python3 wire.py wait <task-id> --json
```

Use a long-running tool call and yield periodically rather than imposing a short agent
timeout. When `wait` returns `state: triggered`, execute its locally returned `prompt`
in this same active turn. The wrapper only receives the signal; it never launches an
agent in foreground mode.

If the agent turn, terminal, or machine exits, foreground waiting does not wake itself.
This default is intended for a same-workday handoff while the current agent remains
open.

## Explicit detached alternatives

Use detached session dispatch only when the user asks to close the current turn and
resume that exact persisted conversation later:

```bash
python3 wire.py create ... \
  --detach --tool codex --session-id "$CODEX_THREAD_ID" \
  --allow-unconfirmed-get --allow-session-permissions --json
```

An open interactive session may reject detached resume because it already has an active
writer. The wrapper records that failure; it never guesses another session.

Use a fresh context only when requested:

```bash
python3 wire.py create ... --fresh --tool codex --allow-unconfirmed-get --json
```

Use another product only when the user explicitly selects an executor:

```bash
python3 wire.py create ... --executor claude --allow-unconfirmed-get --json
```

`--fresh` and `--executor` imply detached operation. Fresh prompts must be
self-contained and use conservative read-only/plan permissions.

## Direct-link warning

The link is a direct GET capability. Signals published during the first two minutes
after creation are discarded so ordinary chat previews can settle. A delayed
link-preview scanner in Slack, Teams, email, or a security product may still activate
it after that window. Only wire non-destructive review or analysis prompts.
`--allow-unconfirmed-get` acknowledges this; detached session targets also require
`--allow-session-permissions` because a resumed conversation may retain broader
permissions.

## Operations

```bash
python3 wire.py wait <id>              # default foreground consumer
python3 wire.py status
python3 wire.py show <id>
python3 wire.py show <id> --reveal-link
python3 wire.py attach <id> --tool claude --session-id <exact-id> \
  --allow-session-permissions
python3 wire.py attach <id> --tool codex --fresh
python3 wire.py cancel <id>
python3 wire.py retry <id>
python3 wire.py start                  # explicit detached listener
python3 wire.py stop
python3 wire.py listen                 # detached listener diagnostics
```

Attach and cancel work only while a task is armed. Retry applies only to detached
`busy`, `failed`, or `uncertain` attempts; the listener never guesses whether an
ambiguous run is safe to repeat.

## Storage, privacy, and delivery

Durable tasks and run logs live under
`${XDG_STATE_HOME:-~/.local/state}/wire-trigger/`; configuration uses
`${XDG_CONFIG_HOME:-~/.config}/wire-trigger/`; runtime files use the OS temporary
directory. `WIRE_TRIGGER_STATE_HOME`, `WIRE_TRIGGER_CONFIG_HOME`, and
`WIRE_TRIGGER_RUNTIME_HOME` override these paths.

Every trigger gets a cryptographically random topic. Only that topic and the word
`triggered` leave the machine; prompts, paths, and session IDs stay local. The URL is a
bearer capability, so reveal or resend it deliberately.

ntfy caches messages for 12 hours by default. A short disconnect can be replayed, but a
longer outage may lose the signal. Foreground wait reconnects while its tool call is
alive. Detached listeners are not login services, so start one again after reboot.
Duplicate clicks and cached replay are harmless because the first local claim wins.
