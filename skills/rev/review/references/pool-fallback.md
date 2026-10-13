# When a pool runs dry

Read this when a panel slot fails mid-run with a quota/rate-limit error.

Every panel slot except `pi` sits on a pool that can be exhausted, and a panel is
the *most* likely thing to exhaust one — four agents fire at once, so a dry pool
takes out a slot mid-run rather than at a convenient moment.

`agy` is the one that has actually tripped in practice (2026-08-04, on `/revx`'s
`gemini-3.6-flash-high` slot). It fails hard, not gracefully:

```
Print mode: run ended with error and no response: Individual quota reached.
Please upgrade your subscription to increase your limits. Resets in 124h23m43s.
```

That is `RESOURCE_EXHAUSTED (code 429)`, and it is **per account, not per model** —
`/revxflash`'s `gemini-3.6-flash-medium` slot is dead the moment `/revx`'s `-high`
slot kills the quota. The reset is measured in **days**. Retrying, downgrading
effort, or switching `gemini-*` slug all fail identically. `dispatch.sh` surfaces
the raw text on failure, so the string is visible in the agent's stderr.

Check the live OpenRouter catalog for each exact model before offering a swap. Availability and IDs can differ from native providers. A verified counterpart preserves the vendor lineage while changing the billing pool:

| Slot | Native | OpenRouter equivalent via `--tool=pi` |
|---|---|---|
| `codex` `gpt-6.1-sol` @ `high` | account-dependent billing | Verify the same model in the live OpenRouter catalog before proposing a fallback |
| `claude` `sonnet` | Anthropic plan quota | Verify the current Sonnet 5.5 slug in the live catalog |
| `agy` `gemini-3.6-flash-high` | account-dependent billing | `google/gemini-3.6-flash:high` |
| `agy` `gemini-3.6-flash-medium` (flash panel) | account-dependent billing | `google/gemini-3.6-flash:medium` |
| `pi` `z-ai/glm-5.2` | already metered | unchanged |

Reasoning effort moves out of the slug and onto the model as `:<level>` — pi takes
`off|minimal|low|medium|high|xhigh|max`, so the `-high`/`-medium` distinction the
panels rely on is preserved exactly.

```bash
# /revx slot 3, when agy's quota is gone
$D --report-usage=$LEDGER --tool=pi code-quality $P $F /tmp/out-gemini.json google/gemini-3.6-flash:high
```

**Ask before falling back — do not swap silently.** The native slots run on quota
or a prepaid allowance; OpenRouter is real money. Tell the user which slot died,
what the swap costs, and let them choose. A panel is cheap (~$0.02 per open-weight
agent on a small diff) but that is not a decision to make on someone's behalf, and
"the review silently cost cash" is a worse surprise than a three-agent panel.

Reasonable answers include dropping the slot entirely — `/revx -gemini` still
gives you three lineages, and a three-model panel is far better than no review.
Say that out loud as an option rather than defaulting to spend.
