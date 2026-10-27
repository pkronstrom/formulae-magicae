# Claude Code adapter

Model names live here and in `agents/*.md` frontmatter — nowhere else. Edit
both when generations change.

```yaml
harness: claude
model_map:
  frontier: opus     # agents/work-frontier.md
  strong: opus       # work-frontier
  worker: sonnet     # agents/work-worker.md
phase_map: {}        # e.g. chunk_review: codex:gpt-5.6-terra, final_review: codex:gpt-6.1-sol
```

Frontier session: `/model opus`. Checklist: `TaskCreate`/`TaskUpdate` (often
deferred — load them, with `SendMessage`, in one ToolSearch), or `TodoWrite`
on older builds; if neither is in the tool list, a markdown checklist
restated at the top of each message, without searching.

**Two built-in agents**, in `agents/`: `work-frontier` (planner, plan
reviewers, both review lenses, verifier, specialist — read/grep/glob + write
for its one output file) and `work-worker` (implementation, full tools).
Installed as a plugin they are `work:work-frontier` / `work:work-worker`;
from a symlinked skill, symlink `agents/*.md` into `~/.claude/agents/` once.
Spawn with `Agent(subagent_type: <agent>, prompt: <template from
context.md>)`; pass `model:` only for a `phase_map` override, and
`effort: medium` for a chunk checkpoint review (final review and plan
review stay at the agent's default). A standing project or user rule about
models ("Opus implementers") is written once as a `phase_map` entry at
classification; spawns then follow `state.yaml`. Give the phase's
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

**Cross-vendor review** — the design attack, or a final review alongside the
native reviewer — runs through the `rev` skill's wrapper in the background;
do not read `dispatch.sh`. The prompt file is the angle prompt with its
context appended (the design, for `design-alignment`); the target is the
spec, or the `.diff` file:

```bash
D=<rev skill dir>/review
cat $D/prompts/code-quality.md > .work/prompts/<phase>-sol.md   # design-alignment: append the design file
$D/dispatch.sh code-quality .work/prompts/<phase>-sol.md <spec.md | .work/handoffs/<step>.diff> \
  .work/handoffs/<phase>-sol.json gpt-6.1-sol medium
```

`code-quality` for a spec, `design-alignment` for a diff against the design.
Its findings are judged like a native reviewer's. A raw `codex exec` that
times out "negotiating with the code-mode host" needs
`-c features.code_mode_host=false` and the files inlined in the prompt; out
of quota, skip it and say so in one line.
