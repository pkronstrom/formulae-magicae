# Claude Code adapter

Model names live here and nowhere else. Edit this block when generations
change.

```yaml
harness: claude
model_map:
  frontier: opus
  strong: opus
  worker: sonnet
```

Frontier session: `/model opus`.

**Fresh-context agent:** the `Agent` tool, `subagent_type: general-purpose`,
`model:` from the map, prompt per the spawn protocol in SKILL.md. Give the
chunk worker a `name` (`worker-02`) so the fix pass can continue it with
`SendMessage` and just the findings path. Launch the two reviewers as two
`Agent` calls in one message so they run in parallel; wait for both, then
launch the verifier.

**Cross-vendor second opinion** (CRITICAL, optional): if the `review-work`
skill is installed, its `dispatch.sh` runs one lens on another vendor's model
in isolation — pass `references/review-<lens>.md` as the prompt file. Not
default; only when uncorrelated failure modes are worth the spend.
