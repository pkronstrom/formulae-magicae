---
name: rev
description: Review code changes, plans, or documents with isolated reviewers. Use for /rev, /rev1, /rev2, /rev3, /revx, /revxflash, /revxhigh, /revxultra, or a requested multi-model review.
---

# Rev

Route a compact review invocation to the review playbook bundled in this skill. Preserve the dispatcher and backend routing. This directory is self-contained; no installed sibling skill is required.

## Dependencies

The bundle includes the review prompts, JSON schema, dispatcher, preflight helper, and all presets. Runtime requirements are selected by backend:

| Review path | Required tools/access |
| --- | --- |
| All paths | Bash and Python 3 (standard library; no pip packages) |
| `/rev 1`, `2`, `3` | Authenticated `codex` CLI |
| Anthropic slot | Authenticated `claude` CLI |
| Harnessed OpenRouter slot (`pi`) | `pi` coding-agent CLI and `OPENROUTER_API_KEY` |
| Direct OpenRouter (`or`) | `OPENROUTER_API_KEY` and network access; no extra CLI |
| Optional Antigravity (`agy`) | Authenticated `agy` CLI |
| Runtime timeouts | GNU `timeout` on PATH (optional; otherwise the dispatcher cannot enforce its timeout) |

The standard cross-vendor panel uses Codex, Claude, and `pi`; choose a Codex-only mode when the other backends are unavailable. Do not install tools or switch to a metered provider silently. Shell utilities such as `git`, `mktemp`, and `wc` must also be on PATH.

## Invocation

`/rev [mode] [panel-roster arguments]`

| Mode | Bundled configuration | Review configuration |
| --- | --- | --- |
| `1` | `references/shortcuts/rev1.md` | One Sol 6.1 code-quality reviewer at `high` |
| `2` | `references/shortcuts/rev2.md` | Sol 6.1 code-quality + design-alignment reviewers at `xhigh` |
| `3` | `references/shortcuts/rev3.md` | Three Astra reviewers: code quality, design alignment, architecture |
| `x` | `references/shortcuts/revx.md` | Standard four-vendor panel |
| `xflash` | `references/shortcuts/revxflash.md` | Fast, low-cost four-vendor panel |
| `xhigh` | `references/shortcuts/revxhigh.md` | Strong four-vendor panel |
| `xultra` | `references/shortcuts/revxultra.md` | Six-agent maximum-coverage panel |

With no mode, ask the user to choose one. Reject an unknown mode and show the
valid values.

Text after the mode can specify scope, roster, or both. Preserve it unchanged for the selected configuration. Do not interpret a path or task sentence as a model name. This preserves the existing bare-name and `+model`/`-model` grammar.

## Execution

Read `review/SKILL.md` and the selected configuration from `references/shortcuts/`, relative to this skill directory. In the playbook and its references, `<skill-base>` means the absolute path to this skill's `review/` directory; its `dispatch.sh`, `schema.json`, `prompts/`, `references/`, and `scripts/` are all inside that directory. Shortcut commands are optional aliases: an isolated install can always use `/rev <mode>`. Detect the diff and produce the review exactly as the playbook specifies.

The dispatcher selects the backend by lane: use `codex exec` for Codex lanes and
`claude --print` for Anthropic lanes. Never run an Anthropic reviewer through
Codex.

## Long-running reviewers

Keep each review process handle until completion. Use a host completion notification or its task-wait operation when available; otherwise keep execution attached and wait for the process. Never assume background launch re-invokes this session. Collect each exit status and output before merging findings; a failed or missing result is an incomplete panel, not a clean review.
