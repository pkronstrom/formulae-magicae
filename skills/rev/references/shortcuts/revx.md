---
name: revx
description: Cross-vendor panel review — one angle, four different base models via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Panel** mode: the code-quality angle run against several different base models in parallel, one per vendor lineage.

The user invoked: `/revx $ARGUMENTS`

`$ARGUMENTS` carries **scope, roster, or both**, and in practice it is usually
scope — "review docs/plans/x.md", "the branch feat/y against master". Read model
names and `+`/`-` adjustments as roster; read everything else as what to review
and hand it to the review playbook as the target. Only roster tokens change the
roster: a path or a sentence never does.

## Roster

If `$ARGUMENTS` names no models, use the default roster:

| Backend | Model |
|---|---|
| `codex` | `gpt-6.1-sol` @ `high` |
| `claude` | `sonnet` (5.5) @ `high` |
| `pi` | `x-ai/grok-4.5` |
| `pi` | `z-ai/glm-5.2` |

This file is the **authoritative** definition of the `/revx` roster. `review-work`'s
SKILL.md describes panel mode in general and cites these tables; where the two
ever disagree, this file wins.

**One grammar: bare names set the roster, `+`/`-` adjust it.**

1. Start from a base roster: the bare names given, or the default four if none were given.
2. Apply every `+name` as an addition and every `-name` as a removal, in order.

That single rule covers all cases:

| Input | Result |
|---|---|
| `/revx` | the default four |
| `/revx -sonnet` | default four minus Sonnet → 3 agents |
| `/revx +deepseek` | default four plus DeepSeek → 5 agents |
| `/revx +deepseek -sonnet` | swap Sonnet for DeepSeek → 4 agents |
| `/revx deepseek glm kimi` | exactly those three, default discarded |
| `/revx terra sonnet -sonnet` | terra (bare list wins, then the removal applies to it) |

Match `-name` against the roster by the same aliases used below, so `-sonnet`, `-claude`, and `-opus` all remove the Anthropic slot. If a `-name` matches nothing, say so and carry on rather than failing — a no-op removal is not worth aborting a review over.

`/revx -sonnet` is the cheap default worth knowing: in practice the Anthropic agent explores far more of the repo than the rest and burns ~1M tokens of account-dependent, roughly 16× the whole rest of the panel. The other harnessed backends *can* read the repo too — they just tend to stop at the diff — so this trades thoroughness for quota, not capability. Drop it when the diff is self-contained.

Each named model routes to whichever backend serves it:

| What the user types | Backend | Model used |
|---|---|---|
| `astra`, `sol`, `luna`, `terra`, or any full `gpt-*` ID | `codex` | `astra` → `gpt-6-astra`, `sol` → `gpt-6.1-sol`, `luna` → `gpt-6-luna`, `terra` → `gpt-5.6-terra`; full IDs verbatim, all @ `high` |
| `sonnet`, `opus`, `fable`, `haiku` | `claude` | as typed |
| `flash`, `pro`, or any `gemini-*` | `pi` / `or` | `google/gemini-*` on OpenRouter — **never `agy`**, whose native path succeeded 4 of 19 recorded runs (79% `backend-error`, not quota). The same lineage via OpenRouter succeeded 8 of 9. |
| `deepseek`, `glm`, `kimi` | `pi` | that vendor's current best — `deepseek/deepseek-v4-pro`, `z-ai/glm-5.2`, `moonshotai/kimi-k3` |
| `qwen` | `pi` / `or` | `qwen/qwen3.8-2.4t-a95b` — the open-weight variant of Qwen3.8 Max (95B active of 2.4T, 1M ctx, $2 → $6 /M). Verified 2026-09-02. |
| `qwen-27b` | `pi` / `or` | `qwen/qwen3.8-27b` — the cheap dense tier, $0.42 → $2.55 /M |
| anything shaped `vendor/model` | `pi` (harnessed) or `openrouter` (diff-only) | verbatim |

```
/revx                          # the default four
/revx -sonnet                  # default minus the quota-hungry Anthropic slot
/revx +deepseek                # default four PLUS DeepSeek — five agents
/revx +deepseek -sonnet        # swap one for the other
/revx +opus +kimi              # default plus two more — six agents
/revx deepseek glm kimi        # exactly those three, default discarded
/revx opus fable               # two Anthropic tiers head to head
```

`/revx +qwen` now works. It resolves to `qwen/qwen3.8-2.4t-a95b`, which is the
**open-weight release of Qwen3.8 Max** — the same flagship the guardrail refuses
in its hosted form. That is the open-weight rule paying off literally: identical
model family, one slug blocked and one usable. `+qwen-27b` gets the cheap dense
tier instead.

At $2 → $6 /M it is the cheaper of the two frontier open-weight escalations:
`+kimi` is $3 → $15, so Qwen costs 2.5x less on output for a comparable class of
model. Prefer `+qwen` when the diff is hard and you want an open-weight opinion;
keep `+kimi` for when you specifically want Moonshot's priors.

The hosted tiers still refuse: `qwen3.8-max` and `qwen3.8-flash` come back with
*"No endpoints available matching your guardrail restrictions"*.

**Zero-retention is enforced account-wide, so the API response is the whole
test.** There is no provider list to inspect and no data policy to reason about:
send one request, and if it is refused the model fails the floor. As a rule of
thumb open-weight tiers pass and hosted flagship tiers do not, but check rather
than predict:

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"<slug>","max_tokens":400,"messages":[{"role":"user","content":"Reply with exactly: OK"}]}'
```

Give it real `max_tokens` — reasoning models spend their first hundred tokens
thinking, and a tiny budget returns an empty message that reads like a failure
but is not.

Verify unfamiliar OpenRouter slugs before dispatching — `curl -s https://openrouter.ai/api/v1/models` lists what actually exists, and a wrong slug fails that agent.

## Rules

Give every agent the **identical** prompt. Model identity must be the only variable, or the consensus scoring in Step 4 means nothing.

Pass `--report-usage=/tmp/review-usage.jsonl` to every dispatch and report the panel's total cost in the summary. Only `openrouter` and `claude` report a dollar cost; `codex` and `agy` report tokens only.

**Print the Markdown summary, not the JSON.** Write the consensus report to `/tmp/review-consensus.json` and reference it in one line — the panel's findings are already in the summary, and a fenced block of every agent's raw object buries the answer the user asked for. The inline JSON is only for a subagent that was spawned to return a review; see the skill's Output contract.

Where `/rev1`–`/rev3` scale *depth* on one model family, this scales *diversity* at one depth — reach for it on security-sensitive or subtle-logic diffs, or when you suspect the usual reviewer has a blind spot. In Step 4, weight findings that two or more vendors independently flag: cross-lineage agreement is the strongest signal this skill can produce.
