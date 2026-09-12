# Codex adapter

Model names live here and in `adapters/codex-agents/*.toml` — nowhere else.
Edit both when generations change; the short spoken names are not valid
model slugs.

```yaml
harness: codex
model_map:
  frontier: gpt-5.6-sol     # work_frontier.toml — a ChatGPT-plan account refuses sol (HTTP 400); use gpt-5.6-terra at xhigh there
  strong: gpt-5.6-sol
  worker: gpt-5.6-terra     # work_worker.toml
phase_map: {}               # e.g. chunk_review: claude:opus
```

Frontier session: `codex -m gpt-5.6-sol`. Checklist: a markdown checklist
restated at the top of each message (no plan tool in codex-cli 0.154).

**Two built-in agents**, in `adapters/codex-agents/`: `work_frontier`
(planner, plan reviewers, both review lenses, verifier, specialist) and
`work_worker` (implementation). Register them once in `~/.codex/config.toml`
— project-scoped `.codex/agents/` has an open bug — with absolute paths:

```toml
[agents.work_frontier]
description = "$work frontier: plan, review, verify"
config_file = "/abs/path/to/skills/work/adapters/codex-agents/work_frontier.toml"

[agents.work_worker]
description = "$work worker: implement one chunk"
config_file = "/abs/path/to/skills/work/adapters/codex-agents/work_worker.toml"
```

Spawn with `multi_agent_v1__spawn_agent({agent_type: "work_frontier" |
"work_worker", message: <template from context.md>})` (`features.multi_agent`,
verified codex-cli 0.154); pass `model` / `reasoning_effort` only for a
`phase_map` override. `wait_agent({targets, timeout_ms})` blocks on several;
`send_input({target, message})` continues the worker for the fix pass;
`close_agent({target})` once its file is read. Native agents share the
workspace and write their own files. Approve source access once at the
start, not per agent. Never `codex exec resume` for `$work continue` — the
transcript is not the state.

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
