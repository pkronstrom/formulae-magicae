---
name: spec-flow
description: Spec-driven development workflow — wraps OpenSpec with a discovery/shape phase and a state-aware router. Use when the user wants to draft, plan, implement, or close a non-trivial feature or refactor with persistent design intent.
---

# spec-flow

Opinionated workflow that combines **Superpowers brainstorming** (discovery) with **OpenSpec** (durable change records). The goal is one source of truth — `openspec/specs/` for capabilities, `openspec/changes/<id>/` for in-flight work, `openspec/changes/archive/` for history.

This skill does not reinvent OpenSpec. It calls the canonical commands and adds the things OpenSpec does not provide: a fused brainstorm+explore phase, a roadmap, verification wiring, and one-doc migration from legacy plans.

## Prerequisite check

Before any flow, verify OpenSpec is installed:

```bash
openspec --version
```

If missing, instruct: `npm install -g @fission-ai/openspec@latest` (also supports pnpm, yarn, bun, nix).

## Routing

Pick the flow based on what the user is asking for. If unclear, ask one question.

| User intent | Flow | Read this file |
|---|---|---|
| "set up openspec in this project", "init spec-flow", first-time bootstrap | **init** | `init-flow.md` |
| "let's draft / shape / brainstorm", fuzzy idea, not ready to commit | **shape** | `shape-flow.md` |
| "let's work on / implement / continue / finish X" | **go** | `go-flow.md` |
| "migrate this old doc to openspec" | **migrate** | `migrate-doc.md` |

Always read `concepts.md` once per session before acting — it covers the single-source-of-truth rule, the brainstorm-vs-explore distinction, and the anti-patterns that break this workflow.

## State detection (used by `go`)

Read in this order:

1. `openspec/` directory missing → recommend running the **init** flow.
2. `openspec/.spec-flow.yaml` missing → init was incomplete; offer to finish it.
3. User named a topic/feature:
   - Match in `openspec/changes/<id>/` → **active change**, route to apply or archive.
   - Match in `openspec/explorations/<topic>.md` → **shaped but not proposed**, route to `/opsx:propose`.
   - No match → route to **shape**.
4. No topic given → list active changes (`ls openspec/changes/`) and ask.

## Roadmap updates

If `openspec/.spec-flow.yaml` declares a roadmap location, update it at three transitions:

| Trigger | Roadmap action |
|---|---|
| `shape` produced an exploration seed | Add entry under "Drafted" |
| `/opsx:propose` ran (during `go`) | Move to "In progress" with change ID + branch |
| `/opsx:archive` ran (during `go`) | Move to "Shipped" with date + archive path |

Roadmap target may be `openspec/roadmap.md`, another markdown file, Linear (use the linear MCP), or Obsidian (use the obsidian skill). If `roadmap: none`, skip silently.

## Always-on rules

These apply regardless of flow:

- **Single source of truth.** When OpenSpec has the answer, do not also write to `docs/superpowers/specs/`, `docs/plans/`, or chat-only notes. If a parallel doc exists, propose migrating it (run the **migrate** flow).
- **Archive is the last action.** Never finish work without `/opsx:archive` — otherwise the next session reads stale `openspec/specs/` and reimplements.
- **One logical unit per change.** "Add X and refactor Y" → two changes.
- **Specs are behavior, not pseudocode.** GIVEN/WHEN/THEN scenarios, not implementation outlines.
- **Verify before claiming completion.** Run the commands in `openspec/.spec-flow.yaml` `verify:` list before suggesting archive.
- **If implementation reveals the spec is wrong, update the OpenSpec change before broadening scope.** Do not silently drift.

## When to skip this skill entirely

Typo fixes, one-line changes, throwaway experiments, prototypes you intend to delete. The full pipeline takes ~20% of project time upfront — only worth it for non-trivial features, refactors, architecture changes, public API changes, serialization changes, networking changes, or module-boundary changes.
