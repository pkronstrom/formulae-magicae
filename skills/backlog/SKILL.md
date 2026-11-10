---
name: backlog
description: Keeps a small task backlog as Markdown files in the repo's backlog/ folder, committed with the code; nothing to install. Use for /backlog, when the user asks to add, list, start, finish, drop or prune tasks, or asks what to work on next in a repo that has a backlog/ folder.
---

# Backlog

Tasks are Markdown files in `backlog/` at the repo root, committed with the code. Use
your own file tools (read, write, edit, search); they work on every OS. Without them,
use your shell's search: `grep`, `Select-String` or `findstr`.

If the repo's `AGENTS.md` or `CLAUDE.md` names another task tracker (such as
`Task tracker: jira`), use that instead and don't create `backlog/`.

## A task

`backlog/0007-fix-login-redirect.md`:

```markdown
---
status: doing
priority: high
depends: 0003
session: 3f2a9c1e-…
---
# Fix login redirect

What and why, in a few lines.

## Notes
- 2026-11-08: cause is in auth/callback.ts
```

- Name: four-digit ID and a short kebab-case title. Next ID: the highest number starting
  a file name in `backlog/` or `backlog/archive/`, plus one.
- `status`: `todo`, `doing`, `done` or `dropped`.
- Optional: `priority` (`high` or `low`); `depends` (IDs; the task waits while any is
  `todo` or `doing`); `owner` (a person); `session` (the agent session that started it:
  `${CLAUDE_SESSION_ID}`, or your agent's name and the date if that reads as a placeholder).

## Commands

- `/backlog` or "what's next?": list `doing`, then `todo` by priority and ID; mark tasks that wait.
- `add <title>`: new task with `status: todo`; write a body only from what you were told.
- `start <id>`: set `status: doing` and `session`. If another session has it, ask the user first.
- `done <id>` or `drop <id>`: set the status and add a dated note saying what was done, or why not.
- `note <id> <text>`, `prio <id> high|normal|low`, or just `<id>` to show it.
- `prune`: only when asked; follow `prune.md` next to this file.

## Rules

- Change task files in the same commit as the work.
- Notes are for the next person: decisions, causes, where you stopped.
- Two branches can create the same ID; renumber the newer file after the merge.
- On first creating `backlog/`, offer once to add these lines to `AGENTS.md` (or
  `CLAUDE.md` if only that exists):

  ```
  Task tracker: backlog
  Tasks live in backlog/; check it before starting work. How: <path to this SKILL.md>
  ```
