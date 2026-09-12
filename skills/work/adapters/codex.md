# Codex adapter

Model names live here and nowhere else. Edit this block when generations
change; the short spoken names are not valid `-m` slugs.

```yaml
harness: codex
model_map:
  frontier: gpt-5.6-sol     # "sol"
  strong: gpt-5.6-sol
  worker: gpt-5.6-terra     # "terra"
effort: {frontier: high, strong: medium, worker: medium}
```

Frontier session: `codex -m gpt-5.6-sol`.

**Fresh-context agent**, two options:

1. *Native subagents* when `features.multi_agent = true` in `~/.codex/config.toml`:
   spawn an agent with the role's reference file plus the context pack as its
   task. The model comes from the agent's config, so declare two agents once —
   `[agents.work_worker]` on the worker model and `[agents.work_reviewer]` on the
   frontier model, read-only — and reuse them.
2. *`codex exec`* from the shell — always available, fully isolated, runs in the
   background so two reviewers can overlap (verified on codex-cli 0.154):

   ```bash
   # worker: writes, sees AGENTS.md
   codex exec -m gpt-5.6-terra -c model_reasoning_effort="medium" \
     -s workspace-write -C "$PWD" - < .work/prompts/chunk-02.md
   # reviewer / verifier: read-only, ephemeral
   codex exec -m gpt-5.6-sol -c model_reasoning_effort="high" \
     -s read-only --ephemeral -C "$PWD" - < .work/prompts/review-correctness-02.md &
   ```

   Build each prompt file per the spawn protocol in SKILL.md. Reasoning depth
   is the `-c model_reasoning_effort` override; there is no `--effort` flag.
   The fix pass continues the chunk worker: `codex exec resume --last -` with
   the findings path on stdin. Never resume for `$work continue` — the
   transcript is not the state.
