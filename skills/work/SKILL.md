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
lenses add real value, one verifier when two reviewers ran, zero managers.

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

`/work` in Codex is `$work`. `review` reviews `git diff <base_ref>` when
`state.yaml` exists, else the commits ahead of the default branch plus the
working tree; say the base before launching, and write the goal paragraph
yourself from the diff.

## Roles, not model names

The workflow speaks in semantic roles; the adapter for the harness you are in
maps them to real models and says how to spawn a fresh-context agent. Read
`adapters/claude.md` or `adapters/codex.md` first — once — and never write a
provider model name anywhere else.

```yaml
frontier: highest reasoning quality available   # design, plan, plan review, chunk + final review
strong:   strong reasoning, cheaper than top    # finding verification
worker:   cost-effective implementation         # code, tests, mechanical changes, routine debugging
```

The design conversation runs *in this session*, so this session must be on
the frontier model. If it is not, say so and stop until the user switches or
says go.

**Spawn protocol, every fresh-context agent.** Prompt = the role's reference
file path + the context pack from `references/context.md` as file paths — the
agent reads them; never paste whole files. First line for reviewers and the
verifier: read-only, no edits, no commits. Every agent ends by writing its
output file (handoff, findings, plan) and replying with **one line** — the
file path and a count or status. The coordinator reads the file only when the
next step needs it. Never re-derive in this session what a file already says.

## Size the work from the code, not the sentence

Never classify from the opening line. Look first: the subsystem, the existing
pattern, what the change actually touches. Something that sounds large may reuse
an existing seam and be STANDARD; a "small" change may expose a migration and be
MAJOR. Classify once the shape is known, record it in `state.yaml`, and
re-classify if implementation proves it wrong.

| level | shape | flow |
|---|---|---|
| TINY | local, mechanical, few files, known pattern, no decisions | coordinator writes one minimal chunk file (Goal, Files, Follow this pattern, Do not) → worker → tests → done |
| STANDARD | one contained subsystem, minor decisions, little architectural impact | short design in-session (1–2 questions, no brainstromming) → coordinator writes plan + 1–2 chunks in-session → worker → one final review, both lenses → fix → verify |
| MAJOR | crosses modules or layers; changes API, schema, data flow; moves a seam; real state/async | brainstromming ↔ user → fresh planner → one adversarial plan reviewer → chunks with two-lens review → final two-lens review |
| CRITICAL | security/auth, migration or data-loss risk, distributed/concurrent, infra, large blast radius | MAJOR, with two independent plan reviewers + verifier, and one specialist reviewer where the task creates a real extra failure domain |

`quick` biases to TINY; it does not forbid escalation.

## The flow

```text
INTERACTIVE   user ↔ frontier   discover / inspect / challenge / design   → references/discover.md
              ↓ converged: no open question is likely to reshape the implementation
AUTONOMOUS    plan                                                       → references/writing-plans.md
              attack the plan, amend                                     → references/review-plan.md
              for each chunk:
                set chunk_base, launch worker: implement + tests + commit → references/execute.md
                reviewers (per level) → verifier → fix pass → commit     → references/review-*.md, verify-findings.md
                propagate Deviations into later chunk files
              final whole-change review → fix pass → deterministic checks
              done → offer feedback capture                              → references/feedback.md
```

**Announce the transition once**, in one line: level, chunk count, the
branch chunks will be committed on, and that the next stop is done or a
consequential decision. Before the first worker launch at any level — TINY
included — say that chunks commit on the current branch. Then **do not stop
to ask** "approve plan?", "continue?", "review now?", "next chunk?". Plans,
reviewer findings, fixes and refactors the agreed design requires are yours.
Interrupt only for a genuinely consequential open decision: materially
different product behaviour, requirements that conflict, a destructive or
irreversible action, an architectural fork with real tradeoffs that
implementation exposed, or a chunk still red after one fresh-worker retry
(show the failing output). Bring it with 1–3 options and a recommendation,
write the answer into the design, continue.

**Progress signal.** At every `state.yaml` write print one line — phase,
chunk N/M, commit, verified-finding count. Nothing from handoffs or findings
files reaches the user unless they ask.

Load each reference only when entering its phase.

## State on disk

```text
.work/
├── state.yaml          phase, level, current chunk, artifact paths, verification, open decisions
├── working-design.md   durable design (or the path the design phase produced — see discover.md)
├── plan.md             chunk list + acceptance; chunks/NN-<slug>.md hold each chunk
├── chunks/
├── handoffs/           plan-review.md, chunk-NN.md, <phase>-<lens>.md, <phase>-findings.md
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
artifacts: {design: .work/working-design.md, plan: .work/plan.md}
last_handoff: .work/handoffs/chunk-01-findings.md
verified: {tests: pass, typecheck: pass, lint: pass, build: n/a}
open_decisions: []
```

`base_ref` is written once, at start. The coordinator sets `chunk_base` to
HEAD immediately before launching each chunk's worker — after the previous
chunk's fix commit — so `git diff <chunk_base>` is exactly this chunk. The
worker commits the chunk when it reports and the fix pass commits as a
follow-up. Do not create branches unless the project's rules ask for it.
`.work/` is local state — add it to `.git/info/exclude`, not to the repo,
unless the project wants it tracked. A design spec written under a tracked
path is committed with chunk 01; say so.

A new `/work <task>` over a `.work/` whose phase is `done` replaces everything
but `feedback/`. Over any other phase, ask: continue it, or discard it.

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
| major | correctness + design after each chunk; a small chunk (`git diff --stat <chunk_base>`) gets the standard shape | correctness + design, fresh context |
| critical | as major | as major + one specialist |

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
fresh run — not from memory of them passing. Report that plainly, then ask
once: *"Feature complete. Capture this run as feedback for improving /work?"*
(`references/feedback.md`). Never mutate this skill after a single run.
