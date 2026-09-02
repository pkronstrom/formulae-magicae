# The ledger

`~/.claude/skill-improver/<target>/ledger.md` is the memory of this loop. Without
it, every run re-proposes what the user already rejected and nobody ever learns
whether last month's edit worked.

Read it in Step 2. Append to it in Step 9. Never rewrite it wholesale — it is an
append-only record, and its value is that old entries stay exactly as written.

## Format

One section per run, newest appended at the bottom.

```markdown
## 2026-09-02 — 9 episodes mined (2026-07-14 → 2026-09-01)

| id | tier | finding | evidence | verdict |
|----|------|---------|----------|---------|
| F1 | red | Step 3 re-reads config every run | 6/9 eps | applied — commit a91f2c3 |
| F2 | red | "ALWAYS snapshot first" ignored | 5/9 eps | applied — moved into scripts/apply.sh |
| F3 | orange | ffmpeg probe rewritten each time | 4/9 eps | declined — "I want to see the command each time" |
| F4 | yellow | §"Legacy formats" never loaded | 0/9 eps | deferred — check again after 5 more runs |

**Follow-up on 2026-08-04 run:** F1 (bundle the chart helper) — 4 episodes since,
none rewrote the helper. Working. F5 (shorter description) — 4 episodes, still
only fired when named explicitly. Not working; the description is not the cause.
```

## Verdicts

- `applied` — landed. Record the commit hash, or the snapshot path when the home
  isn't a git repo. The hash is what makes a revert cheap later.
- `declined` — the user said no. **Record their reason verbatim.** The reason is
  the reusable part: it tells the next run what the skill is actually for, and
  three declines with related reasons usually mean the whole line of analysis has
  misread the skill's purpose.
- `deferred` — plausible, not yet enough evidence. Note what evidence would settle
  it, so a later run knows what it is looking for.
- `superseded` — a later finding replaced this one. Point at the id.

A declined finding does not come back. If new episodes genuinely change the
picture, raise it as a new id and state in the table that it was declined before
and what changed.

## Follow-up

Each run closes the previous one. For every `applied` finding, look only at
episodes dated after it landed and answer honestly: did the behaviour stop?

Three answers are allowed, and the third is common and fine:

- **Working** — the pattern is gone from later episodes.
- **Not working** — the pattern persists. Say so, and treat the original diagnosis
  as suspect rather than immediately editing harder in the same direction. A fix
  that didn't take usually means the cause was somewhere else.
- **Can't tell** — too few episodes since. Never dress this up as success.

Keeping failed edits visible is the point. A record that only contains wins is a
record that has stopped being evidence.

## Multiple targets

One directory per target, so an improver run on one skill never has to read
another's history. If a finding clearly applies to a sibling skill, note it in
this run's section as a cross-reference and mention it to the user — do not edit
the sibling, and do not silently drop the observation either.
