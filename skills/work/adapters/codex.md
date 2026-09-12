# Codex adapter

Model names live here and nowhere else. Edit this block when generations
change; the short spoken names are not valid model slugs.

```yaml
harness: codex
model_map:
  frontier: gpt-5.6-sol     # "sol" — a ChatGPT-plan account refuses it (HTTP 400); use gpt-5.6-terra at xhigh there
  strong: gpt-5.6-sol
  worker: gpt-5.6-terra     # "terra"
effort: {frontier: high, strong: medium, worker: medium}
phase_map: {}               # e.g. chunk_review: claude:opus
```

Frontier session: `codex -m gpt-5.6-sol`. Checklist: a markdown checklist
restated at the top of each message (no plan tool in codex-cli 0.154).

**Every agent is native** (`features.multi_agent`, verified codex-cli 0.154):
`multi_agent_v1__spawn_agent({model, reasoning_effort, message})` with model
and effort from the map and the prompt per the spawn protocol in SKILL.md;
`wait_agent({targets, timeout_ms})` to block on several at once;
`send_input({target, message})` continues a worker for the fix pass;
`close_agent({target})` once its file is read.
Reviewers and the verifier are told in their first line to change nothing
under the repo except their findings file. Native agents share the workspace,
write their own handoff or findings file, and the fix pass continues the same
worker agent. Reading the project's source, tests and plans is what these
agents are for — approve that once at the start, not per agent. Never `codex
exec resume` for `$work continue` — the transcript is not the state.

**`claude:` entries in `phase_map`** are the one case that leaves the
harness — reviewers and the verifier only, read-only, so the reply is the
file; prompt on stdin, run in the background:

```bash
claude -p --model opus --no-session-persistence --strict-mcp-config \
  --disable-slash-commands --allowed-tools Read Grep Glob \
  --disallowed-tools Bash Edit Write NotebookEdit \
  < .work/prompts/review-design-02.md > .work/handoffs/chunk-02-design.md &
```

Read-only comes from the tool allowlist, not `--permission-mode plan` (plan
mode makes it plan instead of review). Never put the prompt in a positional
argument — `--add-dir` is variadic and swallows it.
