# Migrate-doc flow

Convert one legacy planning or design doc into OpenSpec format. Run per-doc, not in bulk — quality matters.

## Inputs

- A path to an existing markdown doc, e.g.:
  - `docs/plans/save-load.md`
  - `docs/superpowers/specs/2026-03-12-netcode-design.md`
  - `notes/architecture/asset-pipeline.md`

## Steps

### 1. Read and classify

Read the source doc. Decide:

| Signal | Target |
|---|---|
| Describes a *planned* change, contains tasks/checklist, work not yet done | `openspec/changes/<id>/` (in-flight) |
| Describes *shipped* behavior of a current capability, no open tasks | `openspec/specs/<capability>/spec.md` |
| Pure brainstorm/options notes, no commitment yet | `openspec/explorations/<topic>.md` |
| Unclear | Ask the user which it is |

If shipped: also ask which capability name to file it under (look at existing `openspec/specs/` first). If new capability: pick a kebab-case name.

### 2. Convert

#### To a change folder

Create `openspec/changes/<id>/` containing:

- **`proposal.md`** — extract scope, motivation, out-of-scope from the source doc. Rewrite as: *Why* / *What changes* / *Out of scope*.
- **`design.md`** — extract technical approach, options, decisions, tradeoffs. Preserve rationale.
- **`specs/<capability>/spec.md`** — rewrite any behavior descriptions as GIVEN/WHEN/THEN scenarios. **Do not paste pseudocode.** If the source has pseudocode, convert to behavior or drop it.
- **`tasks.md`** — extract or generate 2–5 minute checklist items. Mark anything already done with `[x]`.

#### To a capability spec

Create or update `openspec/specs/<capability>/spec.md`. Format as GIVEN/WHEN/THEN scenarios describing **current** behavior. Strip implementation details, scoping notes, motivations — those don't belong in a current-state spec.

#### To an exploration seed

Use the template in `shape-flow.md` step 4. This is the lightest conversion.

### 3. Show the diff

Before writing, present the conversion to the user:

```
Source: docs/plans/save-load.md
Target: openspec/changes/deterministic-save-load/

Files to create:
  proposal.md   (~30 lines, distilled from source sections "Why" + "Goals")
  design.md     (~80 lines, from "Approach" + "Tradeoffs")
  specs/save-load/spec.md  (12 GIVEN/WHEN/THEN scenarios)
  tasks.md      (14 items, 4 marked done)

Items I dropped:
  - Section "Old idea (rejected Jan 2026)" — superseded
  - Pseudocode in "Implementation sketch" — converted to behavior

Items needing your call:
  - Two scenarios are ambiguous: <list them>
  - Source mentions "TBD: schema versioning" — leave as open question?
```

Wait for approval before writing files. If user wants edits, iterate.

### 4. Write the files

Create the target folder and files. Do **not** delete the source yet.

### 5. Decide source disposition

Ask:

> Source doc disposition?
> 1. **Stub** (recommended) — replace `<source>` with a one-line redirect to the new location. Keeps history clean and old links don't 404.
> 2. **Keep** — leave the original untouched. (Risk: drift. Only choose if the original is referenced from outside the repo.)
> 3. **Delete** — remove `<source>`. Choose only if confident it's orphaned.

Default to stub. The stub looks like:

```markdown
# Moved

This document was migrated to OpenSpec on YYYY-MM-DD.

→ `openspec/changes/deterministic-save-load/` (in-flight)
→ `openspec/specs/save-load/spec.md` (current behavior)
```

### 6. Update the roadmap

If the conversion produced a change folder, add an entry to "In progress". If it produced a capability spec, no roadmap update needed (it's already shipped). If it produced an exploration, add to "Drafted".

### 7. Stop

Do **not** chain into `go` automatically. The user may want to migrate more docs first. Just confirm:

> Migrated `<source>` → `<target>`. Source disposition: <stub/keep/delete>. Run `/spec-flow migrate <next-path>` for more, or `/spec-flow go <topic>` to continue work.
