---
name: task-tracker
description: Use when a workflow is about to plan, record or read work across more than one session, before creating a MASTERPLAN.md or TODO file, or when the user asks which task system a repo should use.
---

# Task tracker

The user's task system wins. This skill finds it, or helps the user pick one, and
says how phased work is written down in it.

## 1. Find what the repo uses

Run this from the repo root:

```bash
cat CLAUDE.md AGENTS.md 2>/dev/null | sed -n 's/^Task tracker: //p'
```

| Result | Tracker |
|---|---|
| a name, such as `aven` or `linear` | that system |
| nothing, and `MASTERPLAN.md` exists | `MASTERPLAN.md` |
| nothing, and a `TODO.md` holds open work | `TODO.md` |
| nothing else | none yet: go to step 2 |

A repo that names a tracker never gets a new `MASTERPLAN.md` or `TODO.md`.

## 2. Choose, when there is none yet

Match the work:

| Work | Fits | Ask? |
|---|---|---|
| one task, finished in this session | the session's own plan or task tool | no, and create no file |
| longer work with phases or dependencies | `MASTERPLAN.md` or `TODO.md`, as a chain | yes, recommending this |
| several streams, deadlines, deferred work, or several people or devices | a dedicated tracker | yes, recommending this |

When two rows could fit, recommend the simpler system. When asking, use
`AskUserQuestion` where available, with the recommended option moved first:

- **Session tasks:** nothing saved; for work that ends with this session.
- **`MASTERPLAN.md`:** a chain of phases in git; reads top to bottom, and needs no other tool.
- **Aven:** a local task database outside the repo, with dependencies, epics, deferral and a phone app.
- **Linear:** hosted and team-friendly, with projects and issue dependencies; needs an account.

Other answers are welcome, such as `TODO.md`, GitHub Issues or an existing tool.

Once the user picks a lasting system, offer to add `Task tracker: <name>` to the
repo's `CLAUDE.md` or `AGENTS.md`, so nobody has to ask again. For a system whose
`/<name>-migrate` skill exists, offer that too when old tracking is in place.

## 3. Write phased work as a chain

Each phase names what it depends on, one phase is current, and only that phase
gets planned. Finishing it makes the next one current.

| Tracker | Phase | Link in the chain | Current |
|---|---|---|---|
| `MASTERPLAN.md`, `TODO.md` | one checkbox line | `(depends on N)` | `← current` |
| Aven, Linear or similar | one item under a parent such as an epic or project | a real dependency between items | its in-progress status |

The plan's steps stay in its plan document, and the item links to that by path.
Put the overview and the reasoning behind the order in the file's opening or the
parent's description.

## 4. Use the tracker

Load the `<name>-tracker` skill if one exists; it says how this system holds the
following. Otherwise use what the repo's instructions and the tool's own CLI or
MCP provide:

- the overview
- phases, with order, status and a link to each plan
- notes for whoever plans the next phase

If the tool isn't reachable, stop and say so rather than falling back to a file.
