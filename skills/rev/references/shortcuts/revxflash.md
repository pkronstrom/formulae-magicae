---
name: revxflash
description: Fast cross-vendor panel — four cheap/fast models, one angle, via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Panel** mode, but on the fast roster: four different vendor lineages, all on their speed tier.

The user invoked: `/revxflash $ARGUMENTS`

## Roster

| Backend | Model | $/M in → out |
|---|---|---|
| `codex` | `gpt-6-luna` @ `medium` | — |
| `pi` | `x-ai/grok-4.3` | 1.25 → 2.50 |
| `pi` | `~deepseek/deepseek-v4-flash-latest` | 0.08 → 0.25 |
| `pi` | `z-ai/glm-4.7-flash` | 0.06 → 0.40 |

**The flash slots stay on `pi`, with a caveat worth knowing.** Through
2026-08-19 these slots returned an *empty* output file roughly one run in four
(78 runs, 77% completed) — the model never finished driving pi's tool loop, so
there was nothing to parse. The cause was identified as pi losing its model
catalog inside the ephemeral config dir, which left it blind to each model's
output ceiling; `dispatch.sh` has copied `models.json` across since 2026-08-20.

Since that fix these slots have run **2 for 2**. That is early, not proof. Check
before concluding either way:

```bash
python3 -c "
import json,os,collections
rows=[json.loads(l) for l in open(os.path.expanduser('~/.local/state/review-work/runs.jsonl'))]
f={'z-ai/glm-4.7-flash','deepseek/deepseek-v4-flash-0731','~deepseek/deepseek-v4-flash-latest'}
r=[x for x in rows if x.get('model') in f and x.get('tool')=='pi' and x['ts'][:10]>='2026-08-20']
print(len(r),'runs since the fix,',sum(1 for x in r if x.get('outcome')=='ok'),'ok')"
```

If the empties return, route these two slots to `--tool=or`, where the identical
models completed 6 of 6. That costs their file tools — `or` sees only the diff —
which is an acceptable trade for a pre-commit sweep but not a free one.

Same `$ARGUMENTS` handling as `/revx` — scope, roster, or both — against the roster above as the base: bare names replace it, `+name` adds, `-name` removes. So `/revxflash -glm-4.7-flash` runs three, `/revxflash +haiku` adds the Anthropic lineage back.

Nothing extra to set for cost: `dispatch.sh` already routes to the cheapest zero-retention provider by default. These models are fast enough that the throughput premium buys little — the point of this mode is *adequate and cheap*.

This is the pre-commit sanity sweep: four lineages for roughly the price of one slow agent. It trades depth for breadth, so it catches *shallow-but-diverse* problems — stale references, contradictions, obvious mistakes — while missing subtle cross-file reasoning bugs.

Notes on what is deliberately absent:

- **No Anthropic slot.** `haiku` is the only fast Claude tier and it skims review diffs; `sonnet` is thorough but slow and by far the most expensive agent in the full panel. Add `+haiku` if you want the lineage represented anyway.
- **No codex Fast/priority tier.** That is a billing multiplier, not a capability one — `medium` effort on Luna is the cheaper way to go faster.

Escalate to `/revx` when the diff is security-sensitive or logic-dense. Use `/rev1` when you want depth on one model instead of breadth across four.
