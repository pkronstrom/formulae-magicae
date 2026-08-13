# Go flow

State-aware router for daily work. Inspects the repo and runs the right OpenSpec command.

## Steps

### 1. Locate context

```bash
test -d openspec || echo "no-openspec"
test -f openspec/.spec-flow.yaml || echo "no-config"
```

If `no-openspec`: tell user to run the **init** flow first. Stop.
If `no-config`: offer to finish init (steps 3–5 of `init-flow.md`). Ask before proceeding.

Read `openspec/.spec-flow.yaml` to learn `roadmap.target` and `verify`.

### 2. Resolve the topic

User invocation patterns:
- `/spec-flow go save-load` → topic given.
- `/spec-flow go` → no topic. List active changes:
  ```bash
  ls openspec/changes/ 2>/dev/null | grep -v archive
  ```
  Ask: *"Which change? Or shape a new one?"* Stop until answered.

### 3. Determine state

Check in this order; first match wins:

| Found | State | Action |
|---|---|---|
| `openspec/changes/<topic>/tasks.md` exists, has unchecked items | **apply** | Step 4 |
| `openspec/changes/<topic>/tasks.md` exists, all items checked | **archive** | Step 5 |
| `openspec/explorations/<topic>.md` exists, no change yet | **propose** | Step 6 |
| Nothing matches | **shape** | Hand off to `shape-flow.md` |

Slug matching is fuzzy: try exact, then close kebab-case match, then ask user to confirm.

### 4. Apply

Before invoking `/opsx:apply`:

**4a. Verify tasks.md was reviewed.** Look for one of:
- A `reviewed: true` line in the front of `tasks.md`, OR
- A `.reviewed` flag file alongside it.

If neither: stop and say:
> `tasks.md` has not been reviewed. Open `openspec/changes/<topic>/tasks.md` and read it end to end. Five minutes here saves hours of rework. Add `reviewed: true` to the top when done.

Do **not** proceed without review. This is non-negotiable.

**4b. Run `/opsx:apply`.** Wire in TDD discipline by including this instruction in the apply prompt:

> Implement strictly via RED/GREEN TDD: write a failing test first, then minimum code to pass, then refactor. After each task, run the verify commands from `openspec/.spec-flow.yaml`. If implementation reveals the spec is wrong, **stop and update the OpenSpec change before broadening scope** — never silently drift.

**4c. After apply finishes**, re-run the state check (step 3). If all tasks checked, fall through to **archive**.

### 5. Archive

**5a. Run verification commands** from `openspec/.spec-flow.yaml` `verify:` list. If any fail, stop and surface the failure. Do not archive on red.

If `verify` is `none` or empty, warn:
> No verification commands configured. Archiving without verification is risky. Continue anyway?

**5b. Run `/opsx:archive`.** This syncs the delta into `openspec/specs/` and moves the change to `openspec/changes/archive/<YYYY-MM-DD>-<topic>/`.

**5c. Update the roadmap** (Shipped section):

For markdown:
```markdown
- **<Topic>** — shipped YYYY-MM-DD, `openspec/changes/archive/YYYY-MM-DD-<topic>/`
```

For Linear: move issue to "Done" with the archive link in a comment. For Obsidian: move under "Shipped" heading.

**5d. Remind to merge.** Tell the user:
> Archived. Verify your branch is clean and ready to merge. The exploration seed at `openspec/explorations/<topic>.md` (if any) can be deleted — it's superseded by the archived change.

### 6. Propose

**6a. Read** `openspec/explorations/<topic>.md`.

**6b. Check for unresolved open questions.** If the seed has un-answered questions, stop and surface them:
> The exploration seed has open questions:
> - <question 1>
> - <question 2>
> Resolve these first (edit the seed), then re-run `/spec-flow go <topic>`.

**6c. Run `/opsx:propose`** with the seed as context. After it generates the change folder:

**6d. Update the roadmap** (move from Drafted → In progress):
```markdown
- **<Topic>** — in progress, `openspec/changes/<topic>/`, branch `<branch-name>`
```

**6e. Hand off.** Tell the user:
> Change proposed at `openspec/changes/<topic>/`. Read `tasks.md` end to end, then add `reviewed: true` at the top. Re-run `/spec-flow go <topic>` to start applying.

Then ask:
> Want me to open `openspec/changes/<topic>/tasks.md` in your default editor for manual review?

If yes, run `open openspec/changes/<topic>/tasks.md` (macOS) or `xdg-open` (Linux). Do not block on the editor — the user reviews on their own time and re-runs `/spec-flow go <topic>` when ready.

Do **not** automatically run `/opsx:apply` after propose. The review gate (step 4a) exists for a reason.
