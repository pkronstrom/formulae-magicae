# Init flow

Bootstrap a project for spec-driven development. Wraps `openspec init` and adds roadmap + verification configuration.

## Steps

### 1. Detect prior state

```bash
test -d openspec && echo "openspec exists" || echo "fresh"
test -f openspec/.spec-flow.yaml && echo "spec-flow configured"
```

Branches:
- **Fresh** → run all steps below.
- **OpenSpec exists, spec-flow not configured** → skip step 2, do steps 3–5.
- **Both exist** → ask: *"spec-flow is already configured. Reconfigure roadmap / verify commands, or migrate a doc?"* Route accordingly.

### 2. Run `openspec init`

```bash
openspec init
```

If the command is missing, stop and instruct:

```
npm install -g @fission-ai/openspec@latest
```

This creates `openspec/specs/`, `openspec/changes/`, and the `/opsx:*` slash commands.

### 3. Ask the configuration questions

Ask one at a time. Do not batch.

**Q1 — Roadmap location:**

> Where should the project roadmap live?
> 1. `openspec/roadmap.md` (recommended, lives with the specs)
> 2. `docs/roadmap.md` or another markdown path (you specify)
> 3. Linear (give the team / project ID)
> 4. Obsidian (give the vault-relative path)
> 5. None — skip roadmap updates

**Q2 — Verification commands:**

> What commands verify a change is ready to merge? Common: tests, lint, format-check, type-check.
> Examples:
>   Rust:    `cargo fmt --check`, `cargo clippy --all-targets --all-features -- -D warnings`, `cargo test`
>   Node:    `npm run lint`, `npm run typecheck`, `npm test`
>   Python:  `ruff check .`, `mypy .`, `pytest -q`

Accept a list; allow "none" for prototypes (will warn at archive time).

**Q3 — OpenSpec profile (only ask if user mentions advanced workflow):**

> OpenSpec has a `core` profile (4 commands: explore/propose/apply/archive) and an `expanded` profile (adds new/continue/ff/verify/sync/bulk-archive). Default is core. Switch?

Most users want core. Don't push the question.

### 4. Write `openspec/.spec-flow.yaml`

```yaml
# spec-flow configuration — extends OpenSpec
roadmap:
  target: <one of: openspec/roadmap.md | docs/roadmap.md | linear:<team-id> | obsidian:<path> | none>
verify:
  - <command 1>
  - <command 2>
profile: core   # or expanded
```

### 5. Scaffold the roadmap

Only if `roadmap.target` is a markdown path that doesn't exist yet. Use this template:

```markdown
# Roadmap

Tracking for spec-driven changes. Updated automatically by `spec-flow`.

## Drafted

_Ideas in `openspec/explorations/`. Not yet committed to a change._

## In progress

_Active `openspec/changes/<id>/`. Branch + tasks.md status._

## Shipped

_Archived in `openspec/changes/archive/`. Newest first._
```

For Linear / Obsidian, do nothing on init — the roadmap is updated only at transitions, via the corresponding MCP / skill.

### 6. Offer migration

> Have any existing planning docs (e.g. `docs/plans/*.md`, `docs/superpowers/specs/*.md`) you want to migrate into OpenSpec? Provide one path, or "none" to skip.

If yes → invoke the **migrate** flow (`migrate-doc.md`) on each path, one at a time. Don't try to migrate a directory in bulk — quality matters more than throughput.

### 7. Print the cheatsheet

End with a short summary the user can refer to:

```
spec-flow ready.

Daily commands:
  /spec-flow shape <idea>     # fuzzy → openspec/explorations/<topic>.md
  /spec-flow go [feature]     # state-aware: propose / apply / archive
  /spec-flow migrate <path>   # convert one legacy doc

OpenSpec primitives (called for you, but available directly):
  openspec init
  /opsx:explore  /opsx:propose  /opsx:apply  /opsx:archive

Source of truth:
  openspec/specs/         capabilities (current truth)
  openspec/changes/<id>/  in-flight work
  openspec/changes/archive/  history

Roadmap: <chosen target>
Verify: <commands>
```
