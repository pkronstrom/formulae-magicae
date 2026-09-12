---
name: work
description: "/work <task> — idea to verified feature in one command: interactive design with the strongest model until the shape converges, then autonomous plan → plan review → cheaper worker implements chunks → fresh-context correctness and design review → verified fixes → final review. Sizes itself from the code. Use for /work, $work, 'work on X end to end', and the subcommands brainstorm, plan, quick, continue, review, status."
---

# work

Spend frontier intelligence where judgment matters — design, planning, attacking
the plan, review. Let a cheaper capable model type the code. Cross every phase
boundary by writing state, not by carrying context. Protect the architecture
while the codebase grows.

Not a swarm: one planner, one worker at a time, two reviewers only where two
lenses add real value — the final pass and CRITICAL — one verifier when two
reviewers ran, zero managers.

## Commands

| command | does |
|---|---|
| `/work <task>` | the whole thing: design ↔ user, then autonomous to done |
| `/work brainstorm <task>` | design only; never implements |
| `/work plan <task>` | design as needed, plan, review the plan, stop |
| `/work quick <task>` | bias to TINY for clearly local, mechanical work |
| `/work continue` | resume from `.work/state.yaml`, fresh session or not |
| `/work review` | both lenses + verifier on the current change, report; no fixes |
| `/work status` | phase, chunk, open decisions, verification state |

`/work` in Codex is `$work` (or `$<plugin>:work` when installed as a plugin). `review` reviews `git diff <base_ref>` when
`state.yaml` exists, else the commits ahead of the default branch plus the
working tree; say the base before launching, and write the goal paragraph
yourself from the diff.

## Roles, not model names

The workflow speaks in semantic roles; the adapter for the harness you are in
maps them to real models and names the two built-in agents that carry them —
`work-frontier` (plan, review, verify) and `work-worker` (implement). Read
`adapters/claude.md` or `adapters/codex.md` first — once — and never write a
provider model name anywhere else.

```yaml
frontier: highest reasoning quality available   # design, plan, plan review, chunk + final review
strong:   strong reasoning, cheaper than top    # finding verification
worker:   cost-effective implementation         # code, tests, mechanical changes, routine debugging
```

A map value is `[backend:]model`; no prefix means the harness you are in.
When the user switches a phase's model mid-run ("use opus for reviews"),
that is a `phase_map` entry written into `state.yaml`; the adapter already
holds the invocation — nothing to rediscover.
An optional `phase_map` overrides the role for one phase (`plan`,
`plan_review`, `execute`, `chunk_review`, `verify`, `final_review`), so a
Claude session can send reviews to a Codex model or the reverse — different
pretraining lineages fail differently, which is worth more than a second
reviewer from the same family. Discovery is always this session.

The design conversation runs *in this session*, so this session must be on
the frontier model. If it is not, say so and stop until the user switches or
says go.

**Spawn protocol.** Every fresh-context step is one of the two built-in
agents with the template from `references/context.md` as its task — brief
path, pack paths, chunk section, output path — and nothing else. The agent
definition already says what it is and how it ends (its output file written,
a one-line reply); the reference file is the brief. Never paraphrase the
brief, never paste whole files; project-specific invariants belong in the
chunk section of the plan, not in the task. An agent run outside the harness
(a `phase_map` entry) cannot write `.work`; its whole reply *is* the file and
the coordinator captures it to the path. The coordinator reads an output
file only when the next step needs it, and never re-derives in this session
what a file already says.

## Size the work from the code, not the sentence

Never classify from the opening line. Two moments, not one:

1. **Before discovery**, a quick look at the code answers one question only —
   *is this obviously local?* Yes: short in-session discovery. No, or any
   doubt: brainstromming. That routes discovery; it is not the level.
2. **When the design converges**, classify for real and record it in
   `state.yaml`. It can go either way: a brainstromming session that ends at
   "reuse the existing seam" is STANDARD; a short chat that surfaces a
   migration, a second subsystem or several phases escalates into
   brainstromming and lands at MAJOR or CRITICAL. Re-classify if
   implementation proves it wrong.

Every STANDARD-or-larger run gets a `MASTERPLAN.md` line. When discovery
decomposes the work into phases — a whole app, a multi-phase rollout — each phase gets one, and **only the first unchecked
phase is planned**, fully, before anything is built. Each later phase gets
its own discovery, plan grill and plan review when its turn comes; the
overall design is context for it, not a substitute. Never write one
twenty-chunk plan.

| level | shape | flow |
|---|---|---|
| TINY | local, mechanical, few files, known pattern, no decisions | coordinator writes `.work/chunk.md` (Goal, Files, Follow this pattern, Do not) → worker → tests → done → one dated line in `MASTERPLAN.md` if it matters to the whole picture |
| STANDARD | one contained subsystem, minor decisions, little architectural impact | short design in-session (1–2 questions, no brainstromming) → coordinator writes plan + 1–2 chunks in-session → worker → one final review, both lenses → fix → verify |
| MAJOR | crosses modules or layers; changes API, schema, data flow; moves a seam; real state/async | brainstromming ↔ user → fresh planner + plan grill → two adversarial plan reviewers + verifier → chunks, one reviewer each → final two-lens review |
| CRITICAL | security/auth, migration or data-loss risk, distributed/concurrent, infra, large blast radius | MAJOR, with two independent reviewers + verifier at chunk checkpoints too, and one specialist reviewer where the task creates a real extra failure domain |

`quick` biases to TINY; it does not forbid escalation.

## The flow

```text
INTERACTIVE   user ↔ frontier   discover / inspect / challenge / design   → references/discover.md
              ↓ converged: no open question is likely to reshape the implementation
              plan; grill the plan-level tail once, batched             → references/writing-plans.md
AUTONOMOUS    attack the plan, amend                                     → references/review-plan.md
              for each chunk:
                set chunk_base, launch worker: implement + tests + commit → references/execute.md
                reviewers (per level) → verifier → fix pass → commit     → references/review-*.md, verify-findings.md
                propagate Deviations into later chunk sections
              final whole-change review → fix pass → deterministic checks
              done → offer feedback capture                              → references/feedback.md
```

**Announce the transition once**, after plan review and before chunk 1, in
one line: level, chunk count, the branch chunks will be committed on, and
that the next stop is done or a consequential decision. (TINY: the same
line before its worker launches.) Then **do not stop to ask** "approve plan?", "continue?", "review now?", "next chunk?". Plans,
reviewer findings, fixes and refactors the agreed design requires are yours.
Interrupt only for a genuinely consequential open decision: materially
different product behaviour, requirements that conflict, a destructive or
irreversible action, an architectural fork with real tradeoffs that
implementation exposed, or a chunk still red after one fresh-worker retry
(show the failing output). A fix pass that leaves the checks red does not
commit: the coordinator keeps `chunk_base`, writes the failing output to the
chunk handoff, launches one fresh worker with the fix-pass pack plus that
output, and if still red, stops and asks. The one scheduled exception is the plan grill:
plan-level questions the planner cannot settle from the code, asked once, in
one batch, before anything is built — a wrong guess there is the expensive
kind. Bring it with 1–3 options and a recommendation,
write the answer into the design, continue.

**What the user sees.** A live checklist in the harness's plan tool
(adapter names it): one item per phase of this run, the current phase's
chunks nested under it, exactly one in progress; `MASTERPLAN.md` phases
beyond this run appear as one trailing item each. Update it at every
`state.yaml` write — the checklist does the restating. Every message to the
user is shaped as the `adhd` skill prescribes, whether or not it is
installed: next action or question first, state restated ("chunk 2/4 done:
pricing resolution; reviewing"), completed work shown concretely, errors as
cause + fix, no preamble, no recap, no closer. Nothing from handoffs or
findings files reaches the user unless they ask.

Load each reference only when entering its phase.

## Documents and state

**All work goes through the master plan and a plan document.** Every
STANDARD-or-larger run is a line in `MASTERPLAN.md` and a plan file; nothing
is built that neither names. TINY skips the plan file — its chunk is
`.work/chunk.md` — and gets a `MASTERPLAN.md` line only when the change is
relevant to the whole picture: one dated line saying what was done, ticked. They live where the project keeps plans (`docs/plans/`
unless the repo plainly uses something else) and are maintained to the end:

```text
MASTERPLAN.md                                   the checklist; created on the first run if absent
docs/plans/<date>-<topic>-design.md             MAJOR/CRITICAL: brainstromming's spec, with the sections discover.md names
docs/plans/<date>-<topic>-implementation.md     STANDARD+: Status line, Design section (when there is no design file), one `## Chunk N` section per chunk
docs/plans/archive/                             both files move here when the work is done
```

```markdown
# Gateway — master plan

Two or three paragraphs: what this is, where it is going, the architecture
in one breath. The whole picture, not the steps.

## Phases
- [x] Phase 1 — Persistence (done 2026-09-10) → docs/plans/archive/2026-09-08-persistence-implementation.md
- [ ] Phase 2 — Sync (depends on 1) ← current → docs/plans/2026-09-12-sync-implementation.md
  - settles the event schema Phase 3 renders; at-least-once delivery, dedupe server-side
- [ ] Phase 3 — UI
- [x] 2026-09-11 — retry backoff made jittered (tiny; no plan)

## For the next planner
- Seam: all persistence goes through src/store/*; legacy/ has a second style — do not follow it.
- Blocker: Phase 3 needs the event schema Phase 2 settles (its plan, Chunk 3).
- Debt: retry logic lives in both net/ and sync/ — collapse when Phase 3 touches it.
```

Keep it un-polluted. One line per phase or feature — status, dependencies,
links — and a few bullets only for a genuinely big phase. Steps are never
duplicated here; the plan holds them. *For the next planner* is what a
fresh planner must read or know to make a cohesive decision for the next
phase: seams to respect, blockers, debt worth collapsing, files to read
first. Pointers, not essays; ten lines is plenty; remove an entry the run
that resolves it. It is written at *done* from the run's Deviations and
Risks, and read at the start of the next discovery and plan.

Local, per-run state:

```text
.work/
├── state.yaml          phase, level, current chunk, document paths, verification, open decisions
├── handoffs/           plan-review.md, chunk-NN.md, <phase>-<lens>.md, <phase>-findings.md
├── prompts/            only for phase_map entries that leave the harness
└── feedback/           opt-in run records for skill-improver
```

`state.yaml` is written at every phase boundary and read by `/work continue`
and `/work status`. Keep it flat:

```yaml
task: add offline telemetry buffering to the gateway
level: major
phase: execute            # discover | plan | plan-review | execute | review | final-review | done
current_chunk: 2
base_ref: 3f9c1a2         # HEAD when /work started, written before discovery; final review diffs against it
chunk_base: 8b77e01       # HEAD immediately before the current chunk's worker launched
docs: {design: docs/plans/2026-09-12-sync-design.md, plan: docs/plans/2026-09-12-sync-implementation.md}
masterplan_phase: "Phase 2 — Sync"   # when MASTERPLAN.md exists
last_handoff: .work/handoffs/chunk-01-findings.md
verified: {tests: pass, typecheck: pass, lint: pass, build: n/a}
open_decisions: []
```

Before writing `base_ref`, the tree must be clean: a dirty tree at start is
the user's work, not the feature's — ask whether to commit it, stash it, or
include it, and do not start until answered. `base_ref` is written once, at
start. The coordinator sets `chunk_base` to
HEAD immediately before launching each chunk's worker — after the previous
chunk's fix commit — so `git diff <chunk_base>` is exactly this chunk. The
worker commits the chunk when it reports and the fix pass commits as a
follow-up. Do not create branches unless the project's rules ask for it.
`.work/` is local state — add it to `.git/info/exclude`, not to the repo,
unless the project wants it tracked. The design, the plan and `MASTERPLAN.md`
are committed with chunk 01; say so.

A new `/work <task>` over a `.work/` whose phase is `done` replaces everything
but `feedback/` and is a new feature, whatever `MASTERPLAN.md` says. Over any
other phase, ask: continue it, or discard it. `/work continue` with phase
`done` and an unchecked phase in `MASTERPLAN.md` starts that phase —
discovery, plan grill, plan review, all of it — and says so.

`/work continue`: read `state.yaml` and the `last_handoff`, re-enter the
phase. A dirty tree relative to `chunk_base` is partial chunk work: hand the
worker `git diff <chunk_base>` as prior progress; never reset it without
asking. Nothing else from the previous session is needed; if it is, the
handoff was written badly — fix the handoff, not the process.

## Escalation and refresh are different tools

A worker escalates one thing: a decision the chunk does not make and the code
forces — a plan that is provably invalid, or a choice that would need a new
file, abstraction, dependency, config flag or public interface. That decision
comes to frontier reasoning (this session, with the design and the worker's
handoff — not its transcript); the design and later chunks are amended; the
worker continues. Ordinary coding trouble is the worker's to solve.

Every chunk is a fresh worker. Mid-chunk, a worker that contradicts a recorded
decision or has gone noisy is restarted with the same pack — not escalated to
a stronger model.

## Review, not review loops

After a review: verified findings → fix pass → tests → commit → continue.
Re-review only when the fix was large, changed architecture, a finding
demanded verification, or tests surfaced new uncertainty. Never re-run a full
review after every fix.

| level | checkpoint review | final review |
|---|---|---|
| tiny | none | none, unless the diff turned out risky |
| standard | none | one reviewer, both lenses in one pass |

"Both lenses in one pass" = one reviewer given both `review-correctness.md`
and `review-design.md`, writing one file, `<phase>-review.md`, in the
correctness format with each finding tagged by lens.
| major | one reviewer, both lenses, after each chunk | two independent reviewers + verifier |
| critical | two independent reviewers + verifier after each chunk | as major + one specialist |

Reviewers write `.work/handoffs/<phase>-<lens>.md`. When two or more ran, the
verifier gets those paths and writes `<phase>-findings.md`; skip the verifier
when both files are empty. A single reviewer's file goes to the fix pass
directly. Reviewers never talk to each other. The CRITICAL specialist has no
reference file: write its lens ad hoc in five lines naming the extra failure
domain (migration, security, concurrency, contract, UI state), give it the
chunk-review pack, and feed it to the verifier like the others.

## Done

A feature is done when every chunk is committed, the final review's verified
findings are fixed, and the deterministic checks in `verified:` all pass in a
fresh run — not from memory of them passing. That fresh run is the
coordinator's one: per chunk, the worker's pasted check output is the
evidence, and the reviewer sees the same diff; do not re-run the suites in
this session after every chunk. Then close the documents:
set `Status: done <date>` in the plan, tick and date the `MASTERPLAN.md`
line, update *For the next planner* from the handoffs' Deviations and Risks
(add what the next phase must know, remove what this run resolved), move the
design and plan to `docs/plans/archive/` and fix the link, commit as
`<topic>: done`. Report plainly — and if `MASTERPLAN.md` has an
unchecked phase, name it as the next `/work`. Then ask once: *"Feature complete. Capture this run as feedback for improving /work?"*
(`references/feedback.md`). Never mutate this skill after a single run.
