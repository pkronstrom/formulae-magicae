# Claude Code adapter

Model names live here and in `agents/*.md` frontmatter — nowhere else. Edit
both when generations change.

```yaml
harness: claude
model_map:
  frontier: opus     # agents/work-frontier.md
  strong: opus       # work-frontier
  worker: sonnet     # agents/work-worker.md
phase_map: {}        # e.g. chunk_review: codex:gpt-5.6-terra, final_review: codex:gpt-5.6-sol
```

Frontier session: `/model opus`. Checklist: `TodoWrite` where the build has
it; otherwise a markdown checklist restated at the top of each message.

**Two built-in agents**, in `agents/`: `work-frontier` (planner, plan
reviewers, both review lenses, verifier, specialist — read/grep/glob + write
for its one output file) and `work-worker` (implementation, full tools).
Installed as a plugin they are `work:work-frontier` / `work:work-worker`;
from a symlinked skill, symlink `agents/*.md` into `~/.claude/agents/` once.
Spawn with `Agent(subagent_type: <agent>, prompt: <template from
context.md>)`; pass `model:` only for a `phase_map` override, and
`effort: medium` for a chunk checkpoint review (final review and plan
review stay at the agent's default). Give the phase's
workers and reviewer a `name` (`worker-a`, `worker-b`, `reviewer`) — parallel
workers coordinate directly with `SendMessage` to each other's name — so later chunks, fix
passes and the final review continue them with `SendMessage` and just the
new task lines. On CRITICAL, launch the two
reviewers as two `Agent` calls in one message; wait for both, then the
verifier.

**`codex:` entries in `phase_map`** are the one case that leaves the harness:
run them through the `codex` skill's review recipe (`codex exec … -s
read-only --ephemeral --ignore-user-config -o <findings path>`) as a
background Bash call, prompt per the template, told that its whole final
message is the findings file. Reviewers and the verifier only — a foreign
worker is not supported.
