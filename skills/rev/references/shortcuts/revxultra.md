---
name: revxultra
description: Maximum-coverage cross-vendor panel — six agents, strength from quota and effort, metered spend still bounded, via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Panel** mode, on the maximum roster: six agents, both Anthropic tiers, and the algorithmic specialist.

The user invoked: `/revxultra $ARGUMENTS`

## Roster

| Backend | Model | Cost basis | Why the slot |
|---|---|---|---|
| `codex` | `gpt-6-astra` @ `max` | account-dependent | Highest Codex tier, maximum effort |
| `claude` | `opus` (5.5) @ `high` | account quota or credits | Strong coding and reasoning |
| `claude` | `fable` (5.1) @ `high` | account quota or credits | Demanding long-horizon reasoning |
| `pi` | `x-ai/grok-4.5` | 2.00 → 6.00 $/M | xAI lineage — nothing else in the panel shares its priors |
| `pi` | `deepseek/deepseek-v4-pro` | 0.43 → 0.87 $/M | LiveCodeBench 93.5%, Codeforces 3206 — dense logic |
| `pi` | `z-ai/glm-5.2` | 0.76 → 2.42 $/M | Best long-horizon of the cheap open models |

Same `$ARGUMENTS` grammar as `/revx`, against this roster as the base.

## Why six

Two Anthropic tiers provide independent reviews within the same provider; they do not add a new vendor lineage. Astra runs at `max`; Opus 5.5 and Fable 5.1 run at `high`. Reserve this roster for difficult reviews and use the preflight to inspect the budget.

**No Google slot** — the native `agy` path completed 4 of 19 recorded runs
(`backend-error`, not quota). `+gemini` routes Google through OpenRouter.

## Cost

The most expensive roster here, and the one to justify out loud before running.
Step 2.5's preflight prints the metered estimate; the Anthropic slots draw quota
that competes with your own sessions. Reserve it for a pre-release audit or a
split verdict that needs a stronger tiebreak.
