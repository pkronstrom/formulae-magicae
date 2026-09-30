# Shape flow

Discovery phase. Take a fuzzy idea and produce a durable seed in `openspec/explorations/<topic>.md` ready for `/opsx:propose` later.

## When to run

- User says: "draft", "shape", "brainstorm", "let's think about", "explore the idea of".
- User has an idea but isn't sure of scope, design, or how it lands in the existing code.
- A `go` flow detected no exploration or change for the named topic.

Skip if the user already knows exactly what they want and where it goes — route directly to `/opsx:propose`.

## Steps

### 1. Pick the discovery mode

Read the user's framing and choose:

| Framing | Mode |
|---|---|
| Fuzzy goal, no concrete code reference, "I'm thinking maybe..." | **brainstorm only** |
| Concrete idea grounded in existing code, "add X to module Y" | **explore only** |
| New capability in an existing repo, both human and code uncertainty | **brainstorm → explore** |

If unclear, ask one question: *"Is this more about deciding what we want, or about figuring out how it fits the existing code?"*

### 2. Run brainstorming (if selected)

Invoke the `superpowers:brainstorming` skill (from the [Superpowers](https://github.com/obra/superpowers) plugin; if it is not installed, run the same discovery conversation inline). Constraints:
- Do not write application code.
- Do not save a separate design doc to `docs/superpowers/specs/` — the output goes into the exploration seed in step 4.
- Stop when there's a clear direction or 2–3 named alternatives with tradeoffs.

### 3. Run `/opsx:explore` (if selected)

Invoke `/opsx:explore <topic>`. The agent will read files, survey seams, and surface options. No artifacts written by OpenSpec itself — that's fine.

### 4. Write the exploration seed

Create `openspec/explorations/<topic-slug>.md` (kebab-case, e.g. `deterministic-save-load`):

```markdown
# <Topic title>

Date: <YYYY-MM-DD>
Status: drafted
Suggested change-id: <kebab-case-id>

## Summary

One paragraph: what we're considering and why.

## Context found in this codebase

- File paths, existing modules, current behaviors that constrain the design.
- (From `/opsx:explore` if it ran.)

## Options considered

### Option A — <name>
Pros:
Cons:

### Option B — <name>
Pros:
Cons:

## Recommended direction

Which option, and why. One paragraph.

## Out of scope

Bullet list of things explicitly NOT in this change.

## Open questions

Bullet list of unresolved decisions that need user input before `/opsx:propose`.

## Verification idea

How will we know this works? (Behavior-level, not implementation.)
```

This is **not a spec** — it's the seed `/opsx:propose` consumes. Specs come later, in `openspec/changes/<id>/specs/`.

### 5. Update the roadmap

If `.spec-flow.yaml` `roadmap.target` is set, add an entry under "Drafted":

```markdown
- **<Topic title>** — `openspec/explorations/<topic-slug>.md` (drafted YYYY-MM-DD)
```

For Linear, create or update an issue in the configured project with status "Backlog" and a link to the exploration. For Obsidian, append under the corresponding heading.

### 6. Hand off

Tell the user:

> Seed saved to `openspec/explorations/<topic-slug>.md`.
> Open questions: <list>.
> When ready, run `/spec-flow go <topic>` to propose, or edit the seed first.

Do **not** automatically call `/opsx:propose`. Let the user review the seed and resolve open questions before committing.
