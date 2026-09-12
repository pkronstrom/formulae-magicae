# Claude Code adapter

Model names live here and nowhere else. Edit this block when generations
change.

```yaml
harness: claude
model_map:
  frontier: opus
  strong: opus
  worker: sonnet
phase_map: {}               # e.g. chunk_review: codex:gpt-5.6-terra, final_review: codex:gpt-5.6-sol
```

Frontier session: `/model opus`.

**Fresh-context agent:** the `Agent` tool, `subagent_type: general-purpose`,
`model:` from the map, prompt per the spawn protocol in SKILL.md. Give the
chunk worker a `name` (`worker-02`) so the fix pass can continue it with
`SendMessage` and just the findings path. Launch the two reviewers as two
`Agent` calls in one message so they run in parallel; wait for both, then
launch the verifier.

**`codex:` entries** run from Bash with `run_in_background: true`, prompt on
stdin, using the `codex exec` lines in `adapters/codex.md` — reviewers and the
verifier `-s read-only --ephemeral`, workers `-s workspace-write`. Launch the
two reviewers in one message and wait for the notifications; do not poll. A
Codex worker's fix pass continues via `codex exec resume --last`.

**Cross-vendor second opinion** (CRITICAL, optional): if the `review-work`
skill is installed, its `dispatch.sh` runs one lens on another vendor's model
in isolation — pass `references/review-<lens>.md` as the prompt file. Not
default; only when uncorrelated failure modes are worth the spend.
