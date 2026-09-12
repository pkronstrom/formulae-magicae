# Writing the plan

Frontier model, fresh context for MAJOR/CRITICAL; the coordinator writes it
in-session for STANDARD and TINY, straight from the working design. Pack in
`context.md`.

Budget: about 200 lines, at most four chunks, and about fifteen file reads —
the files the design names plus the ones the chunks will touch, not a survey
of the codebase. A question you would need more exploration to settle is a
grill question, not a reading list; a plan that needs a fifth chunk is two
phases — return it as such and stop.

Read `MASTERPLAN.md` first — its *For the next planner* section is what the
previous runs learned: the seams to respect, the blockers, the files to
open. Plan against that picture, not just this phase.

The plan resolves architecture; it does not type the implementation twice.
Be exact about decisions, responsibilities, interfaces, data flow, invariants,
files, the existing pattern to reuse, edge cases, tests, acceptance and what is
explicitly *not* to be touched. Write pseudocode only for a non-obvious
algorithm or contract. Never pre-write routine production code — the worker
will write it once, against real code, with the tests running.

## Resolve, don't guess — the plan grill

The plan is where a wrong call is cheapest to fix and, once built on, most
expensive. So before the planner is spawned, **this session grills the user
at plan altitude, brainstromming-style**: the conversation simply continues
past design convergence into the plan-level decisions the design leaves open
— the details brainstromming parked as "plan-time", interface shapes, data
formats, error and retry policy, names of new public things, what is tested
and how, and any UX or UI detail the design left open (SKILL.md, *Whose
decision*). Settle from the code whatever the code decides; ask the rest
**one question per message**, live, with 2–4 options and the recommendation
marked (`AskUserQuestion` where the harness has it, prose otherwise). Stop
when you could predict the answer to the next one — usually two to five
questions, sometimes none. Write each answer into the design as a decision
as you go.

The planner receives a design with those decisions made and does not grill.
If it still meets a decision it cannot settle from the code and the design,
it returns that question instead of guessing; this session asks it the same
way, then continues the planner with the answer. A plan with a "TBD" in it
is not finished.

STANDARD gets the same discipline in-session, usually as zero or one
question.

## Chunks

Split into architecturally meaningful chunks a single worker can own from
implementation through local verification: *persistence path complete*,
*domain vertical slice complete*, *API contract complete*, *migration
complete*. Two to four chunks for a MAJOR phase; one or two for STANDARD.
More than four is a second phase, not a longer plan.
Never chunk at TDD granularity — "write test / make it pass / refactor" is one
worker's inner loop, not three review checkpoints.

Order chunks so each leaves the tree building and tests green. If a chunk
cannot, say what is temporarily allowed to be red and why. Every chunk
states *Depends on* (a chunk, or none) and its *Files* are its ownership:
two chunks with disjoint files and no dependency between them are
parallelizable, and the plan should prefer such cuts where the design
allows — that is where wall-clock is won.

## The plan document

`docs/plans/<date>-<topic>-implementation.md`, next to the design it
implements. Header: `Status: in progress` (→ `done <date>` at the end), the
goal, the design link (or the Design section itself for STANDARD), the chunk
list with one-line goals, the acceptance for the whole feature, non-goals,
and *things not to redesign*. Then one `## Chunk N` section per chunk,
self-contained — the worker is pointed at its section and reads only that:

```markdown
## Chunk 2 — Quote pricing resolution

## Goal
Resolve quote-line prices by the existing price-source priority.

## Architecture
Resolution stays in PricingService. The router validates and delegates.

## Files
- src/services/pricing.ts
- src/server/routers/quotes.ts
- tests/pricing.test.ts

## Depends on
Chunk 1 (the price-source table). *Files* is ownership: a chunk whose
files are disjoint from another's and that depends on nothing unfinished
can run in parallel with it.

## Invariants
- manual override always wins
- a missing price never silently becomes zero
- no pricing rules in the router

## Follow this existing pattern
src/services/supplier-pricing.ts — the established service boundary for this
subsystem. Match its shape; do not introduce a second style.

## Implementation notes
- reuse resolveSupplierPrice(); the transaction boundary stays in QuoteService
- no generic pricing-strategy framework

## Edge cases
- ...

## Acceptance
- tests listed above pass; typecheck and lint clean
- ...

## Do not
- redesign the pricing model; touch unrelated serialization
```

## Thorough means

No UX or UI choice is left to the worker: every screen, flow and
interaction the chunk touches is described in the chunk section as the user
decided it.

Every chunk names its interfaces, its files, the pattern to follow, its edge
cases, and an acceptance a worker can run. No chunk depends on a decision
another chunk has not yet made. The worker should never have to choose a
shape — only to build one.

## The one-pattern rule

For every chunk name **one** representative existing file the worker should
follow, and why. This is the highest-value line in the chunk: it is what stops
a worker from inventing a second architectural style. If no such file exists,
say so — that is itself a design signal worth a sentence.

Add or update the run's `MASTERPLAN.md` line with the plan's link (create the
file if absent). Close by
writing `state.yaml` (`phase: plan-review` for MAJOR/CRITICAL, `phase:
execute` otherwise, `current_chunk: 1`). The plan is the handoff; reply with
the chunk list only.
