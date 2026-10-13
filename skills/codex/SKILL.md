---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention GPT models for implementation, or delegate coding tasks to Codex. Default model is gpt-6.1-sol at medium effort.
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Invocation

You will usually be called as `/codex [model] [effort] [task]` — "sol high",
"terra subagent", "sol medium review the backup logic". Parse the leading words
as model and effort when they match; everything else is the task.

Expand the short name before it reaches the CLI. The bare word is what gets
spoken, but it is not a valid slug:

| Spoken | Pass to `-m` |
|--------|--------------|
| `sol` | `gpt-6.1-sol` |
| `astra` | `gpt-6-astra` |
| `terra` | `gpt-5.6-terra` |
| `luna` | `gpt-6-luna` |

`-m sol` fails with `Model metadata for 'sol' not found`, then HTTP 400 "The
'sol' model is not supported when using Codex with a ChatGPT account" — the run
dies after you have already backgrounded it, so the cost lands minutes later.

## Defaults

Use `gpt-6.1-sol` at `medium` by default. Explicit model and effort arguments override these defaults. `terra` remains an explicit legacy option; do not invent a GPT-6 Terra slug.

```bash
codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" -s workspace-write "your task here"
```

Access other models with `-m <model>` or via `config.toml`. Always pass the selected effort explicitly; the model or account's own default may differ from this command's default.
Reasoning depth is a config override, not a flag: `-c model_reasoning_effort="high"`. There is no `--effort` flag in `codex exec`.

## Prerequisites

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

If a run fails with `401 Unauthorized`, `token_invalidated`, or "Please try
signing in again", the ChatGPT auth token has expired. Nothing works until it is
renewed: run `codex login`, or ask the user whether to fall back to another
provider for this task.

## Running It

Codex can run for minutes. Use the calling host's execution lifecycle; `run_in_background` is a host-tool option, not a `codex exec` flag.

- If the host supports background tasks with completion notifications, retain the returned task handle and await that notification. Yielding the current turn is safe only when the host guarantees a continuation for this task.
- If the host returns a running process/session handle and provides a wait or resume operation, retain the handle and use that operation until the process completes. Examples include a shell tool's session handle plus its wait/read operation. The exact tool names depend on the host.
- Without either mechanism, keep the CLI invocation attached and wait for its exit. Do not detach it with `&` and end the task expecting an automatic wake-up.

Avoid tight polling or repeated output-directory checks. Completion notifications are preferable when supported; a bounded wait on a known process handle is valid when they are not. Answer independent user questions while the run continues, then return to the active task.

After completion, inspect the exit status and final output before reporting success. Read any requested result file and perform the validation required by the task. A launch acknowledgement, a notification, or an existing output file alone does not prove the run succeeded. If execution fails, report the actual failure and continue recovery within the authorized scope.

Give the prompt as a positional argument, and redirect stdin from `/dev/null`
unless you are deliberately piping into it:

```bash
codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" -s workspace-write \
  "your task here" < /dev/null
```

Without the redirect, a prompt that lands anywhere but the positional slot makes
codex print `Reading additional input from stdin...` and block. It exits cleanly
and writes nothing, so the failure reads as an empty result rather than an error.

## Handoff Strategy

Codex does **not** inherit the parent agent's reasoning context. Keep the handoff as small as possible.

1. Use a short direct prompt for small, self-contained tasks.

```bash
codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" -s workspace-write "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run the relevant tests."
```

2. Pipe stdin for transient generated context.

```bash
pytest -q tests/auth 2>&1 | codex exec -m gpt-6.1-sol -s workspace-write "Use the failing test output from stdin to diagnose and fix the issue. Run the same tests after the fix."
```

3. Write findings to a file when the context is long, structured, or reusable.

```bash
codex exec -m gpt-6.1-sol -s workspace-write "Read docs/plans/codex-findings.md, implement the requested changes, and run relevant verification commands."
```

Prefer short prompts over piping, and piping over files, unless reuse or prompt size makes a file clearer.

## Review Recipe

For a read-only review of work in a repo, this is the combination that works —
codex reads the repo, writes its verdict to a file you can read back, and cannot
touch the tree:

```bash
codex exec -m gpt-6.1-sol -c model_reasoning_effort="high" \
  -C <repo> -s read-only \
  --add-dir <scratchpad> -o <scratchpad>/review.md \
  "review <what>, focusing on <angle>" < /dev/null
```

`--add-dir` is what makes the scratchpad writable; without it `-o` fails when the
output path sits outside the workspace. After the process completes through the host's notification or wait mechanism, check its exit status and read the result file.

## Models

Current defaults and aliases, checked 2026-10-13 against official OpenAI documentation and the local Codex model cache:

| Model | Alias | Role |
|-------|-------|------|
| `gpt-6.1-sol` | `sol` | **Default.** Balanced speed, cost, and intelligence for coding |
| `gpt-6-astra` | `astra` | Highest intelligence for demanding reasoning, coding, and reviews |
| `gpt-6-luna` | `luna` | Fast, cost-effective focused tasks and mechanical edits |
| `gpt-6-sol` | full slug | Previous Sol release; use explicitly when pinned |
| `gpt-5.6-terra` | `terra` | Legacy cost-conscious option; selectable when available |

Other legacy IDs in the current cache include `gpt-5.6-sol`, `gpt-5.6-luna`, and `gpt-5.5`. Preserve an explicitly requested full slug rather than upgrading it silently. Model access depends on the account; cache presence does not guarantee a successful request.

Sources: [OpenAI model guide](https://developers.openai.com/api/docs/guides/latest-model) and `~/.codex/models_cache.json`. Recheck these before changing the table; do not hardcode relative prices from an older generation.

Verify what your account actually exposes — the CLI refreshes `~/.codex/models_cache.json` on each run:

```bash
python3 -c "
import json, os
p = os.path.expanduser('~/.codex/models_cache.json')
try:
    models = json.load(open(p)).get('models', [])
except (OSError, ValueError):
    raise SystemExit(f'no usable model cache at {p} — run any codex command first')
for m in models:
    print(m.get('slug'), [r.get('effort') for r in m.get('supported_reasoning_levels', [])])
"
```

Check the cache timestamp as well as its contents. A stale cache is inconclusive; refresh through the CLI before treating it as the current account inventory.

## Reasoning Effort

`-c model_reasoning_effort="<level>"`. The ladder, cheapest first:

| Level | Use for | Sol 6.1 | Astra 6 | Luna 6 |
|-------|---------|-----|-------|------|
| `low` | Mechanical, well-scoped edits | ✓ | ✓ | ✓ |
| `medium` | Default — everyday tasks | ✓ | ✓ | ✓ |
| `high` | Complex problems, reviews, audits | ✓ | ✓ | ✓ |
| `xhigh` | Deep debugging, architecture, hard reasoning | ✓ | ✓ | ✓ |
| `max` | Hardest problems, no time pressure | ✓ | ✓ | ✓ |
| `ultra` | Codex-specific highest effort; delegation follows harness settings | ✓ | ✓ | — |

Use the levels advertised by the installed Codex cache for the selected model. `minimal` and `none` are not advertised here; Astra and Sol 6.1 do not support `none`. API and Codex effort surfaces differ, including Codex-specific `ultra`; do not infer automatic delegation from an effort level.

**Cost model.** Effort changes reasoning-token usage rather than the model's per-token price. Compare current pricing for the selected model and account; old Sol/Terra price ratios do not describe GPT-6. Keep `max` and `ultra` opt-in.

Codex's **Fast** (`priority`) service tier is a separate multiplier — more speed, more credits — and is unrelated to reasoning effort. Control it with `-c service_tier=...`; leave it off for batch and review work.

## Useful Switches

- `-s read-only|workspace-write|danger-full-access`: sandbox level. `workspace-write` is the everyday autonomous mode
- `-c model_reasoning_effort="high"`: increase effort
- `--json`: stream JSONL events
- `--output-schema <file>`: enforce structured final output
- `-o <file>`: write the final message to a file
- `--add-dir <path>`: allow writes in extra directories
- `--skip-git-repo-check`: allow non-git workspaces
- `--ephemeral`: do not persist session state
- `-p <profile>`: use a config profile

There is no single documented "no tools" switch in `codex exec`. Constrain Codex with a tighter prompt and `-s read-only`.

### Verified flag surface

The complete `codex exec` option list, verified against **codex-cli 0.162.1**:

```
-c --config       --enable          --disable        --strict-config
-i --image        -m --model        --oss            --local-provider
-p --profile      -s --sandbox      --approve-for-me -C --cd
--add-dir         --thread-source   --cyber-access-program
--skip-git-repo-check
--ephemeral       --ignore-user-config  --ignore-rules
--output-schema   --color           --json           -o --output-last-message
```

Trust this list while `codex --version` still reports 0.162.1, and skip the
`--help` round-trip. On any other version, re-check with `codex exec --help`
before relying on a flag — the surface does move: `--full-auto` was a valid
alias for `-s workspace-write` through 0.150.x and is now rejected outright
(`error: unexpected argument '--full-auto' found`).

For which *models* the account can currently reach, use the `models_cache.json`
snippet in the Models section above rather than guessing. Two caveats it will not
tell you: only full slugs work (`gpt-6.1-sol`, never `sol`), and a ChatGPT-plan
account can refuse a model the cache lists, with HTTP 400 at run time.

## Examples

```bash
# Read-only investigation
codex exec -m gpt-6.1-sol -s read-only "Analyze the codebase structure and summarize the main modules."

# Standard implementation
codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" -s workspace-write "Implement the feature in src/foo.ts and run relevant tests."

# Fast, cheap pass
codex exec -m gpt-6-luna -s workspace-write "Rename the helper and update its callers."

# Complex bug hunting
codex exec -m gpt-6-astra -c model_reasoning_effort="xhigh" -s workspace-write "Diagnose the intermittent deadlock in the worker pool and fix it."

# Long-running agent work at highest Codex effort
codex exec -m gpt-6-astra -c model_reasoning_effort="ultra" -s workspace-write "Work through the migration plan end-to-end."

# Structured CI output
codex exec -m gpt-6-luna --json --output-schema ./schema.json "Run tests and summarize failures."
```

## Best Practices

- Use `gpt-6.1-sol` at `medium` by default; use `gpt-6-luna` for focused cheap tasks and `gpt-6-astra` for the hardest work
- Raise effort deliberately — `high` for reviews and audits, `xhigh` for hard debugging, `max`/`ultra` only when a run is worth several times the tokens
- Keep handoff context minimal and explicit
- Choose short prompt vs stdin vs file intentionally
- Start with `-s read-only` for investigation tasks
- Use `--json` + `--output-schema` for CI integrations
- Check `codex exec --help` on the installed version before relying on newer flags not shown there
- Use `--dangerously-bypass-approvals-and-sandbox` only in isolated environments
- Run relevant tests after changes
