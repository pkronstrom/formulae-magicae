---
name: revxhigh
description: Strong cross-vendor panel — one angle, four lineages, strength bought from quota and effort rather than premium per-token models, via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Panel** mode, on the strong roster.

The user invoked: `/revxhigh $ARGUMENTS`

## Roster

| Backend | Model | Cost basis |
|---|---|---|
| `codex` | `gpt-6-astra` @ `xhigh` | account-dependent |
| `claude` | `opus` (5.5) @ `high` | account-dependent |
| `pi` | `x-ai/grok-4.5` | metered, 2.00 → 6.00 $/M |
| `pi` | `z-ai/glm-5.2` | metered, 0.76 → 2.42 $/M |

Same `$ARGUMENTS` grammar as `/revx`, against this roster as the base: bare names replace it, `+name` adds, `-name` removes.

## Where the strength comes from

Astra at `xhigh` and Opus 5.5 at `high` are explicit upgrades from the balanced roster. Higher effort consumes more reasoning tokens; a stronger model also changes the token rate. Quota is a finite budget, not free strength. The metered slots keep their existing models.

**No Google slot.** The native `agy` path completed 4 of 19 recorded runs,
failing with `backend-error` rather than quota exhaustion. `x-ai/grok-4.5` holds
the seat: a lineage nothing else here shares, $2/$6, passes the privacy floor.
`+gemini` routes Google through OpenRouter instead.

Additional models remain opt-in: `+kimi` and `+fable`. Check current prices and whether Fable draws usage credits before dispatch.
