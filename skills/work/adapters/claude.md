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

Frontier session: `/model opus`. Checklist: `TodoWrite`.

**Every agent is native:** the `Agent` tool, `subagent_type: general-purpose`,
`model:` from the map, prompt per the spawn protocol in SKILL.md. Give the
chunk worker a `name` (`worker-02`) so the fix pass continues it with
`SendMessage` and just the findings path. Launch the two reviewers as two
`Agent` calls in one message so they run in parallel; wait for both, then
launch the verifier. Native agents write their own handoff or findings file.

**`codex:` entries in `phase_map`** are the one case that leaves the harness:
run them through the `codex` skill's review recipe (`codex exec … -s
read-only --ephemeral --ignore-user-config -o <findings path>`) as a
background Bash call, prompt per the spawn protocol, told that its whole
final message is the findings file. Reviewers and the verifier only — a
foreign worker is not supported.
