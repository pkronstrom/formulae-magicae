# Discover

The interactive phase. Frontier model, this session, the user in the loop.
Write `base_ref` (HEAD) to `state.yaml` before anything else.

**Obviously local** (provisional TINY/STANDARD): hold it yourself — read the
code first, ask the one or two questions that change the shape, offer options
with a recommendation, distill straight into the plan's Design section
(shape below).
The moment it stops looking local — a migration, a second subsystem, several
phases — switch to brainstromming; nothing is lost, the design file carries
over.

**Everything else: run the `brainstromming` skill** — it already does the
job: inspect before inventing, one load-bearing question at a time, options
with a recommendation, architecture altitude only, a written and verified spec,
a cross-vendor attack on it. Do not re-implement it. If it is not installed,
hold the conversation yourself at the same altitude. Under `/work` it differs
in four ways:

1. **Skip its exit question.** `/work` knows the exit: `brainstorm` stops
   after the spec, `plan` after the plan, plain `/work` runs to done.
2. **Its spec is the working design.** Point `state.yaml → artifacts.design`
   at the file it wrote. Before closing, make sure the spec carries the
   `# Decisions`, `# Invariants`, `# Non-goals` and `# Relevant existing
   architecture` sections below — append them if it did not; every later
   pack cites them by name.
3. **Its step tracking becomes `/work`'s checklist; keep `MASTERPLAN.md`.**
   Its seven steps nest under the *Design* item of the run's checklist
   (SKILL.md) instead of a list of their own. When it decomposes the work
   into phases, write them there (shape in SKILL.md),
   mark the first `← current`, and design *that phase* to convergence —
   later phases get a line each, not a spec.
4. **Its cross-vendor spec review counts.** It is the design's adversarial
   pass; the plan review that follows attacks the plan, not the design again.

Classify when the design converges, not before (SKILL.md). A brainstromming
session may well end at STANDARD; then skip its cross-vendor review — STANDARD
gets one adversarial pass, the final review.

## Be opinionated about simplicity

Prefer the project's existing patterns. Resist speculative flexibility,
abstraction before a second variant exists, configuration nobody asked for,
frameworks, parallel concepts where an existing one suffices, and "future
proofing" without a current requirement. Say so when the user drifts there,
with the reason.

## Convergence

Discovery ends when no open question is likely to materially change the
implementation's shape. Concretely, these are understood — or irrelevant and
said to be:

- intended behaviour, scope, non-scope
- architectural boundaries; who owns which state and data
- failure behaviour that matters; compatibility and migration
- likely affected subsystems
- how acceptance will be judged (tests, checks)

Straightforward tasks converge in minutes. Do not manufacture questions to fill
the checklist.

## The working design

Whichever file holds it — brainstromming's spec, or the Design section at the
top of a STANDARD plan — the design is distilled continuously, not written at
the end. Conclusions only; the conversation is disposable. When an open
question is answered, it becomes a decision and leaves "Open".

```markdown
# Goal
One paragraph.

# Decisions
- SQLite owns the durable queue.
- The existing cloud client owns flushing; delivery is at-least-once.

# Invariants
- Buffered telemetry never silently disappears.
- Ordering is preserved per device.
- Domain logic stays out of transport handlers.

# Non-goals
- General-purpose job queue.

# Relevant existing architecture
- Retry logic: src/net/retry.ts — reuse, do not fork.
- Persistence seam: src/store/*.ts follow one shape; the new store follows it.

# Open questions
- (none)
```

Close the phase by writing `state.yaml` (`level`, `phase: plan`) and
announcing the transition (SKILL.md). The design file is the handoff; do not
write a second one.
