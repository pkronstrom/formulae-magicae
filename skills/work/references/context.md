# Context packs and handoffs

The workflow chooses *phase + model + context*, not just the model. Every
fresh-context agent gets the smallest sufficient pack, as file paths, assembled
by the coordinator. Progressive disclosure: more code is retrieved by the agent
when it needs it, not preloaded on the chance it might. This table is the one
source; the references do not restate it.

| phase | pack |
|---|---|
| discover | repo rules · relevant architecture · code as discovered · working design · the live conversation |
| plan | repo rules · working design · relevant architecture and source — **not** the discovery transcript |
| plan review | goal · working design · the plan with its chunk sections · relevant contracts — **not** planner reasoning |
| execute chunk | repo rules · design Decisions + Invariants · this chunk section of the plan (TINY: `.work/chunk.md`) · files it names · relevant tests · the one pattern file · previous chunk's handoff (Decisions, Deviations, Relevant files) |
| chunk review | goal (one paragraph) · design Invariants · **the chunk section** · `git diff <chunk_base>` · neighbouring code — **not** worker reasoning or handoff prose |
| verify findings | the reviewers' findings files · diff · design/chunk where cited |
| fix pass | continued worker: the findings file only · fresh worker: findings file · chunk section · design Invariants · only the files the findings cite |
| final review | goal · working design · plan · `git diff <base_ref>` · relevant tests |

"Repo rules" means the project's `CLAUDE.md` / `AGENTS.md` and equivalents,
which most harnesses load anyway — do not paste them twice. The diff is the
review target; reviewers open changed files themselves where a hunk needs its
surroundings — do not hand them whole files.

"Neighbouring code" is defined, not guessed: the chunk's pattern file, the
files its *Do not* section names, and — for stateful changes — the module that
*owns* the state (state machine, lifecycle owner) even when the diff does not
touch it. That is where lifecycle bugs are visible.

## Handoffs

A phase boundary is crossed by writing state and reading it back in a fresh
context — never by carrying the transcript. Where the phase's artifact already
holds its conclusions (the design, the plan, a findings file) that artifact
*is* the handoff. Write a separate handoff only where there is none: after
plan review (what changed and why) and after each worker chunk. Conclusions,
not history: no discarded alternatives, no reviewer essays, no previous
chunks' detail.

```markdown
# Handoff — <phase / chunk>

## Goal
One sentence.

## Decisions / invariants
- only those the next phase must honour

## Completed
- ...

## Deviations
- from the chunk/plan, with reason — or "none"

## Relevant files
- ...

## Verified state
- tests: <command> → pass (42)   build: n/a   lint: pass   typecheck: pass

## Remaining
- ...

## Risks / watch-outs
- ...

## Next
Exact next phase and input.
```

Twenty to forty lines. If a handoff needs more, the phase was too big or the
design is missing a decision — fix that, not the handoff length.
