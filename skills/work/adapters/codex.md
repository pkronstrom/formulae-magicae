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

Frontier session: `codex -m gpt-5.6-sol`. Checklist: the plan tool if this
Codex build exposes one (`update_plan`); otherwise a markdown checklist
restated at the top of each message.

**Every agent is native:** the runtime's spawn tool (`features.multi_agent`),
model and effort from the map, prompt per the spawn protocol in SKILL.md.
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
