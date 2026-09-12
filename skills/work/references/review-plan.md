# Adversarial plan review

MAJOR and CRITICAL only. Two fresh-context frontier reviewers, read-only, one
lens each, in parallel, never conversing; then the verifier. Once per
feature, and a wrong plan costs a rewrite — this is the review not to trim.
Pack in `context.md`. The design was already attacked at discovery; attack
the *plan*.

Your job is to prove the plan will cause trouble before implementation begins.
It is not to make the architecture fancier, propose alternatives that seem
cleaner, add future features, or show range. Recommend a change only where it
addresses a concrete risk, an incorrect assumption, or a structural defect.
Never expand scope.

Verify against the actual code. A finding that rests on "the plan assumes X"
must say whether X is true in the repo, with the file.

## Lens A — coupling and operational correctness

hidden coupling · assumptions about existing code that are false · incorrect
boundaries · missing prerequisites · partial-failure behaviour · concurrency and
state lifecycle · migration and deployment hazards · steps that are mutually
incompatible · likely implementation traps.

## Lens B — seams, scope, simplicity

poor seams · scope explosion · YAGNI · speculative abstraction · unnecessary
dependencies or configuration · a second way of doing something the project
already does · chunks that cannot leave the tree green · assumptions that
should be verified before building on them.

## Output

Findings only, ranked, each with: severity (`BLOCKER` / `DESIGN` /
`SUSPICION`), the claim, the evidence (`file:line` or plan section), and the
smallest plan change that resolves it. Zero findings is a valid answer.
Write `.work/handoffs/plan-review-<lens>.md`; reply with the path and count.

## Afterwards (coordinator)

Run the verifier (`verify-findings.md`) on both files unless both are empty.
Amend the design and
the chunk sections for verified findings — amend, don't rewrite.
Record what changed in `.work/handoffs/plan-review.md`, set `phase: execute`.
