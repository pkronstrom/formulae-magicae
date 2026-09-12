# Writing the plan

Frontier model, fresh context for MAJOR/CRITICAL; the coordinator writes it
in-session for STANDARD and TINY, straight from the working design. Pack in
`context.md`.

The plan resolves architecture; it does not type the implementation twice.
Be exact about decisions, responsibilities, interfaces, data flow, invariants,
files, the existing pattern to reuse, edge cases, tests, acceptance and what is
explicitly *not* to be touched. Write pseudocode only for a non-obvious
algorithm or contract. Never pre-write routine production code — the worker
will write it once, against real code, with the tests running.

## Resolve, don't guess — the plan grill

The plan is where a wrong call is cheapest to fix and, once built on, most
expensive. Before chunking, list every plan-level decision the design leaves
open: the details brainstromming parked as "plan-time", interface shapes,
data formats, error and retry policy, names of new public things, what is
tested and how. Settle each from the code where the code decides it. For
the rest — the ones where a wrong guess costs a rewrite — ask the user
**once, in one batch**: up to five inline with a recommendation each; more
than that, `grill-singlefile` if installed (they answer async), else a
numbered list. Never a second round; what remains after the answers is the
planner's call, written down as a decision. A plan with a "TBD" in it is
not finished.

STANDARD gets the same discipline in-session, usually as zero or one
question.

## Chunks

Split into architecturally meaningful chunks a single worker can own from
implementation through local verification: *persistence path complete*,
*domain vertical slice complete*, *API contract complete*, *migration
complete*. Three to six chunks for a large feature; one or two for STANDARD.
Never chunk at TDD granularity — "write test / make it pass / refactor" is one
worker's inner loop, not three review checkpoints.

Order chunks so each leaves the tree building and tests green. If a chunk
cannot, say what is temporarily allowed to be red and why.

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
