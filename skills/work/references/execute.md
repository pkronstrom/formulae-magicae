# Execute a chunk

Worker model, fresh context per chunk. Pack in `context.md`.

You are building the agreed thing. Follow the architecture in the chunk and the
pattern it names; honour the previous chunk's Decisions and Deviations.
Implement only this chunk. Read the relevant source before writing. Match the
project's idiom — comment density, naming, error handling. Run the tests,
typecheck, lint and build the project actually uses; debug ordinary failures
yourself. If `superpowers:test-driven-development` or
`superpowers:systematic-debugging` are available, use them; they are the inner
loop, not checkpoints.

Do not reinterpret the architecture. Do not add abstractions, options, files,
dependencies, config flags or public exports the chunk did not call for. Do
not touch what the chunk's *Do not* section names. The one escalation: a plan
that is **provably invalid** in the code, or a decision the chunk does not
make that would need any of the items just listed. Stop that part, finish
what is independent of it, and report it under *Remaining* with evidence —
do not decide it yourself. Everything else is yours.

Before reporting done, run the deterministic checks from a clean state and
paste their real output line. Commit the chunk on the current branch with a
message naming it (`chunk 02: quote pricing resolution`).

## Report

Write `.work/handoffs/chunk-NN.md` in the handoff format (`context.md`) and
reply with its path and the verified-state line only. Under *Deviations* list
every place you departed from the chunk and why — "none" is a fine answer;
silence is not.

## Fix pass

**The same worker, continued** — its context already holds the chunk, the
files and the pattern; send it only the findings file (adapter says how).
Spawn a fresh worker instead only if the chunk worker was noisy or
contradicted a decision; its pack is then the findings file, the chunk section,
the design's Invariants, and only the files the findings cite. Fix the listed
findings and nothing else; the chunk's *Do
not* still applies. A finding you can show is false — `file:line` and the
reason — goes under *Deviations* in the handoff, not into the code. Rerun the
checks, commit as a follow-up (`chunk 02: review fixes`), append a *Fix pass*
section to `chunk-NN.md`, reply with the path and the check results.

## After the fix pass (coordinator)

Read only the *Deviations* of `chunk-NN.md`. Amend any later chunk section of the
plan that names an affected file or interface. Then one `state.yaml` write:
`last_handoff` = this chunk's handoff, `current_chunk` + 1 (or `phase:
final-review` after the last), `chunk_base` = HEAD, `verified` from the
handoff. Update the checklist. Next chunk.
