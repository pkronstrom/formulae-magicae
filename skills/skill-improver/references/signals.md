# What counts as a finding

Read this before your first analysis pass. It is the difference between a review
that changes how a skill behaves and one that produces a tidy list of nothing.

The test every candidate finding must pass: **would fixing this change what
happens on the next run, for a different task?** A finding that only describes
what went wrong in one particular job is task context, not a skill defect.

---

## Friction — the skill made the run harder

| Signal in the trace | What it usually means |
|---|---|
| Tool errors, then a retry with different arguments | The skill named a command, path or flag that doesn't work here |
| Permission denial or an interruption right after the skill loads | The skill reaches for a tool the user doesn't want it using, or doesn't warn that it will |
| User corrects direction within ~2 turns of the skill loading | The skill's opening move is wrong, or its trigger is too broad |
| Long clarifying exchange before work starts | The skill should have told the model what to assume, or which question is actually worth asking |
| The model announces it will do X, then does Y | Two parts of the skill disagree with each other |

The user-correction signal is the highest-value one in the whole catalogue.
Someone stopped what they were doing to say "no, not like that". Quote them
verbatim in the finding — their phrasing usually contains the fix.

## Waste — the skill cost more than it needed to

- **Re-derivation.** The model works out something the skill could have stated:
  probing for a binary's flags, discovering a file layout, reconstructing a
  convention. Every episode paying this cost is a line the skill should contain.
- **Repeated improvisation.** Two or more episodes independently write a similar
  helper script or run the same multi-command sequence. Bundle it into
  `scripts/` and point at it. This is the single highest-leverage fix available,
  because it converts recurring cost into one-time cost.
- **Bulk reads.** A whole file read when a `sed -n` range would do; a command
  whose output is mostly discarded. Suggest the narrower call.
- **Reference files loaded and unused.** The skill points at a reference the
  model reads and then ignores. Either the pointer's trigger condition is wrong,
  or the content is not what the pointer promises.
- **Sections never loaded at all.** Skills pay for their body on every
  invocation. A section untouched across every mined episode is a standing tax —
  but check *why* before cutting: a rare-but-critical branch is not dead weight.

## Drift — documented rules the model doesn't follow

When a rule is stated and violated repeatedly, the rule is the problem. Three
fixes, in order of preference:

1. **Structural enforcement.** Make the right thing the path of least
   resistance: a bundled script that does it, a step ordering that makes skipping
   it awkward, a required output field that makes the omission visible.
2. **Explain the why.** A rule with a reason attached survives contact with a
   model that thinks it knows better. A bare imperative doesn't.
3. **Delete it.** A rule nobody follows and nothing enforces is noise that dilutes
   the rules that matter.

Escalating to capitals is not on the list. If a skill has accumulated ALWAYS and
NEVER, that is evidence of previous rounds of this failure, not a solution.

## Gaps — the skill is silent where it shouldn't be

- The same edge case is handled ad hoc in several episodes.
- The model consistently adds a step the skill never mentions — it is doing the
  right thing from general judgment, and the skill should claim it.
- A stated assumption is false in most real runs (a path, a tool, a default).
- Something in the environment changed and the skill hasn't noticed: a renamed
  flag, a replaced tool, a moved path.

## Under-service — the skill let the model do too little

The hardest family to see, because nothing in the trace looks wrong. Every other
family is a way of noticing that the skill made the run heavier than it needed
to be; this one asks whether it made it lighter than it should have been.

- An episode that finished fast and clean, and produced a result the user then
  had to correct, redo, or argue with.
- A verification step the skill mentions softly enough that most episodes skip
  it — and the episodes that skipped it are the ones that went wrong.
- The model narrowing the task to the part the skill describes well, leaving the
  rest of what the user asked unaddressed.
- A skill that was made faster by a previous round of this loop, followed by
  episodes that are quicker and worse.

Findings here usually argue for adding weight, which will feel wrong after a
morning of deleting dead sections. Add it anyway when the evidence is there.

## Context-engineering findings

These are about how the skill spends the context window, and they only become
visible with the metrics header in front of you:

- **Front-loading.** Detail needed in one branch sitting in the always-loaded
  body. Move it to a reference with a clear trigger condition.
- **Pointer quality.** Every reference pointer should say *when* to load it, not
  just that it exists. "See `x.md` for details" gets ignored; "load `x.md` before
  editing any bundled script" gets followed.
- **Order.** What the model needs first should appear first. A skill that puts
  its decision criteria after its procedure makes the model read twice.
- **Output-shape drift.** If episodes produce inconsistent output formats, the
  skill is describing the shape rather than showing it. A template beats a
  description.

---

## Not findings

Leave these out — including them costs the user's trust in the table:

- One-off corrections specific to a single task's peculiarities.
- Tool or harness bugs unrelated to the skill's instructions. Worth mentioning to
  the user in a line, not worth a table row or an edit.
- Failures no version of the skill could have prevented — the task was hard, the
  API was down, the model misread something no sentence would have clarified.
  The test: name the sentence that would have prevented it. If you cannot, it is
  not a finding about the skill.
- Style preferences with no trace evidence behind them.
- Anything already declined in the ledger, unless new episodes genuinely change
  the picture — and if they do, say explicitly that this was declined before and
  what changed.
- Speculative additions for cases that have never occurred. Skills accrete this
  way and it is why they get slow.
