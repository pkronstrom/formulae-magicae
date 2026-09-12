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

## Chunks

Split into architecturally meaningful chunks a single worker can own from
implementation through local verification: *persistence path complete*,
*domain vertical slice complete*, *API contract complete*, *migration
complete*. Three to six chunks for a large feature; one or two for STANDARD.
Never chunk at TDD granularity — "write test / make it pass / refactor" is one
worker's inner loop, not three review checkpoints.

Order chunks so each leaves the tree building and tests green. If a chunk
cannot, say what is temporarily allowed to be red and why.

## Files

`.work/plan.md` — goal, chunk list with one-line goals, the acceptance for the
whole feature, non-goals, and *things not to redesign*.

`.work/chunks/NN-<slug>.md` — one per chunk, self-contained, because the worker
receives the chunk and not the plan:

```markdown
# Chunk 2 — Quote pricing resolution

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

## The one-pattern rule

For every chunk name **one** representative existing file the worker should
follow, and why. This is the highest-value line in the chunk: it is what stops
a worker from inventing a second architectural style. If no such file exists,
say so — that is itself a design signal worth a sentence.

Close by writing `state.yaml` (`phase: plan-review` for MAJOR/CRITICAL,
`phase: execute` otherwise, `current_chunk: 1`). The plan is the handoff;
reply with the chunk list only.
