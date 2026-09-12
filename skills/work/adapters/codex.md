# Codex adapter

Model names live here and nowhere else. Edit this block when generations
change; the short spoken names are not valid `-m` slugs.

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

**Fresh-context agent:** `codex exec` from the shell — isolated, runs in the
background so two reviewers can overlap (verified on codex-cli 0.154). Native
subagents (`features.multi_agent`) are not used: no verified spawn syntax
selects a model or enforces read-only.

```bash
# worker: writes, sees AGENTS.md; keep the log — it holds the session id
codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" \
  -s workspace-write -C "$PWD" - < .work/prompts/chunk-02.md > .work/logs/chunk-02.log
grep -m1 'session id:' .work/logs/chunk-02.log        # → state.yaml worker_session
# reviewer / verifier: read-only cannot write .work, so the reply is the file
codex exec -m gpt-5.6-sol -c model_reasoning_effort="high" \
  -s read-only --ephemeral --ignore-user-config -C "$PWD" \
  -o .work/handoffs/chunk-02-correctness.md - < .work/prompts/review-correctness-02.md &
```

Build each prompt file per the spawn protocol in SKILL.md; tell read-only
agents their whole final message is the findings file. Reasoning depth is the
`-c model_reasoning_effort` override; there is no `--effort` flag. The fix
pass continues the chunk worker by its recorded id — `codex exec resume
<worker_session> -` with the findings path on stdin — never `--last`, which
is whatever session ran most recently in this repo. Never resume for `$work
continue` — the transcript is not the state.

**`claude:` entries** — reviewers and the verifier, read-only (so the reply
is the file), prompt on stdin, run in the background:

```bash
claude -p --model opus --no-session-persistence --strict-mcp-config \
  --disable-slash-commands --allowed-tools Read Grep Glob \
  --disallowed-tools Bash Edit Write NotebookEdit \
  < .work/prompts/review-design-02.md > .work/handoffs/chunk-02-design.md &
```

Read-only comes from the tool allowlist, not `--permission-mode plan` (plan
mode makes it plan instead of review). Never put the prompt in a positional
argument. A `claude:` *worker* needs write tools and a permission mode the
project accepts; that path is not verified — prefer the native worker.
