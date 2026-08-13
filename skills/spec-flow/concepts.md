# spec-flow concepts

Read this once per session before running any flow.

## Roles, sharply

| Tool | Owns | Output |
|---|---|---|
| Superpowers `brainstorming` skill | The *user's* intent and design space — fuzzy, greenfield-style | Verbal exploration, optional summary |
| `/opsx:explore` | The *codebase* — reads files, surveys seams | Optional notes in `openspec/explorations/` |
| `/opsx:propose` | Committed change record | `openspec/changes/<id>/{proposal.md, design.md, specs/, tasks.md}` |
| `/opsx:apply` | Implementation | Code + tests |
| `/opsx:archive` | Sync delta into canonical specs, version the change | `openspec/changes/archive/<date>-<id>/` + updated `openspec/specs/` |
| Tests / lints / compiler | Reality check | Pass/fail |

## Brainstorm vs explore

These overlap; the difference is **what's being investigated**.

- Use **brainstorming** when the human is the bottleneck (unclear goals, missing constraints, undecided tradeoffs).
- Use **`/opsx:explore`** when the codebase is the bottleneck ("how is this currently structured? where would X plug in?").
- Use **both, in sequence**, for non-trivial features in an existing repo.

`shape` flow handles the choice automatically based on the user's framing.

## Folder layout (canonical, after `openspec init`)

```
openspec/
├── specs/                              # Current truth — capability specs
│   └── <capability>/spec.md
├── changes/
│   ├── <change-id>/                    # In-flight, one per logical unit
│   │   ├── proposal.md
│   │   ├── design.md
│   │   ├── specs/                      # Delta — GIVEN/WHEN/THEN
│   │   └── tasks.md
│   └── archive/
│       └── <YYYY-MM-DD>-<change-id>/   # Versioned history, never overwritten
└── explorations/                       # Optional — shape outputs live here
    └── <topic>.md
```

`spec-flow` adds two files:

```
openspec/
├── .spec-flow.yaml      # roadmap target, verify commands, profile
└── roadmap.md           # only if roadmap target = openspec/roadmap.md
```

## Anti-patterns (the ones that actually bite)

1. **Forgetting to archive.** Next session reads stale `openspec/specs/` and reimplements. *Archive is always the last action before merging.*
2. **Two design docs for the same feature.** `docs/plans/X.md` + `openspec/changes/<id>/design.md` drift within an hour. Migrate or delete one.
3. **Pseudocode in specs.** Specs describe behavior, not implementation. Over-specification eats Claude's solution space.
4. **Approving `tasks.md` without reading it.** Five minutes reading it saves hours of rework. The `go` flow refuses to start `apply` if `tasks.md` was never reviewed.
5. **Mixing units of work.** "Add X and refactor Y" → two changes. `propose` rejects scope-mixed proposals.
6. **Pipeline overkill.** A 30-minute task does not need `/opsx:propose`. Skill skip-rule applies.
7. **Drift during apply.** If implementation reveals the spec is wrong, update the OpenSpec change before broadening scope. Never silently widen.

## What this skill does *not* do

- Reinvent `openspec init` — it calls the real one.
- Manage parallel changes via worktrees — use `git worktree` directly or the Superpowers `using-git-worktrees` skill.
- Replace `/opsx:propose`, `/opsx:apply`, `/opsx:archive` — it invokes them.
- Decide what's a "non-trivial change" — that's a judgement call; ask the user when unclear.
