# Data privacy on OpenRouter

Read this before or while using `--tool=or` / `--tool=pi` — it does not apply to
`codex`, `agy`, or `claude`.

Review diffs are proprietary source. Unconstrained, a single model can route to **30+ third-party providers** of wildly varying policy — GLM-5.2 alone lists 34, including hosts you have no relationship with.

`dispatch.sh` therefore sends a privacy floor on every `--tool=or` request:

```json
"provider": {"zdr": true, "data_collection": "deny"}
```

- `zdr: true` — only endpoints that retain nothing.
- `data_collection: "deny"` — excludes providers that store *or train on* inputs.
- If nothing satisfies the policy the request **hard-errors** (`No endpoints found matching your data policy`) instead of quietly falling back. Verified. That failure mode is the feature — never relax it just to make a run succeed.

Verified ZDR + no-training availability (each tested with a live request):

| Model | ZDR endpoint | Example server |
|---|---|---|
| `z-ai/glm-5.2` | ✅ | Phala |
| `z-ai/glm-4.7-flash` | ✅ | DeepInfra |
| `deepseek/deepseek-v4-pro` | ✅ | SiliconFlow |
| `deepseek/deepseek-v4-flash-0731` | ✅ | Venice |
| `moonshotai/kimi-k3` | ✅ | Together |
| `x-ai/grok-4.3` | ✅ | xAI (direct) |
| `x-ai/grok-4.5` | ✅ | xAI (direct) |
| `~deepseek/deepseek-v4-flash-latest` | ✅ | AkashML |
| `~google/gemini-flash-latest` | ✅ | Google (direct) |
| `qwen/qwen3.7-max` | ❌ **none** | — request fails under the policy |
| `qwen/qwen3.8-max` | ❌ **none** | now listed on OpenRouter (2026-08-10, $2/$6) but still single-provider Alibaba — retested, still fails |
| `meta/muse-spark-1.1` / `1.2` | ❌ **none** | $1.25/$4.25 and an otherwise attractive Meta lineage — no ZDR endpoint, fails |

**Are ZDR providers more expensive?** Not inherently — the compliant pool spans both the cheapest and the priciest endpoints for a model. What costs money is asking for *speed*. Measured on `glm-5.2`, 400 output tokens, ZDR pool only:

| `sort` | Provider | tok/s | Cost |
|---|---|---|---|
| `price` (default) | Novita | 43.8 | **$0.00075** |
| `latency` | CoreWeave | 50.5 | $0.00099 |
| `throughput` | BaseTen | 89.7 | $0.00270 |

**Speed costs ~3.6× for ~2× the tokens/sec**, so `dispatch.sh` defaults to `sort: "price"` — cheapest compliant provider. Panel agents run in parallel in the background, so the wall-clock saving rarely justifies the premium. Set `OPENROUTER_SORT=throughput` on a run you are genuinely waiting on.

**Price-drift guard.** Sorting by price already means a new ultra-priced provider can never win the route, but the ceiling stays on as a backstop for when the sort is overridden. Rather than a fixed number — "expensive" is model-relative, since $15/M is an outlier for GLM-5.2 and the going rate for Kimi K3 — the cap is derived from the model's own endpoint distribution:

```
cap = median(completion price across endpoints) × OPENROUTER_PRICE_MULT   # default 1.5
```

| Model | endpoints | min | median | max | cap @1.5× | excluded |
|---|---|---|---|---|---|---|
| `z-ai/glm-5.2` | 34 | 1.50 | 4.25 | 7.26 | 6.38 | 5 |
| `deepseek/deepseek-v4-flash-0731` | 16 | 0.18 | 0.28 | 1.00 | 0.42 | 1 |
| `moonshotai/kimi-k3` | 12 | 14.00 | 15.00 | 22.50 | 22.50 | 0 |

Median rather than mean, because the mean is dragged upward by exactly the outlier being guarded against. The ceiling tracks the market as prices drift. Routing hard-errors if nothing sits under the cap (verified with a deliberately impossible $0.10 cap) rather than silently overspending, and each run prints the ceiling it derived. Override with `OPENROUTER_MAX_OUT_PRICE` ($/M), or widen with `OPENROUTER_PRICE_MULT`. If the metadata fetch fails the run continues **uncapped with a loud warning** — a review should not die over a pricing lookup.

Two things this does **not** give you:

1. **ZDR is not data residency.** The serving provider is chosen per request and varies run to run — the same model resolved to CoreWeave, SiliconFlow, and Phala on three consecutive calls. Some are US, some are not. If jurisdiction matters, pin an allowlist: `OPENROUTER_ONLY="Fireworks,Together,DeepInfra,BaseTen,CoreWeave"`, which `dispatch.sh` forwards as `provider.only`.
2. **The per-request block does not reach `--tool=pi`.** pi builds its own body and its `models.json` only supports custom *headers*, not body params — OpenRouter's routing policy is body-only, so there is no way to inject it client-side. Two server-side fixes, either of which covers pi and any other harness:

   **A. Preset (preferred, scoped).** Create one at `openrouter.ai/settings/presets` — call it `review-zdr`, set `zdr: true` and `data_collection: deny` (plus a `sort` if you like) — then:

   ```bash
   export OPENROUTER_PRESET=review-zdr
   ```

   `dispatch.sh` appends `@preset/<slug>` to the model it hands pi, so the policy is enforced server-side. Verified that the syntax is live: an unknown slug fails with `preset_not_found` rather than an invalid-model error. This is scoped to review runs and leaves your other OpenRouter usage alone. Until it is set, every pi run prints a warning saying it is governed only by account defaults.

   **B. Account default (blunt, global).** Toggle ZDR and disable training at `openrouter.ai/settings/privacy`. Covers every request from every client, but changes behavior for all your OpenRouter usage.

   Preset creation needs a provisioning key, so neither can be scripted with a standard API key — both are one-time dashboard actions. There is no settings API to read the current state either (`/me`, `/settings`, `/account` all 404), which is why the wrapper warns rather than pretending to verify.

Each `or` run prints which provider actually served it, so the choice is auditable after the fact.

Backend requirements and quirks:

- `openrouter` and `pi` both need `OPENROUTER_API_KEY`.
- `pi` runs with an ephemeral `PI_CODING_AGENT_DIR` and `PI_OFFLINE=1`. Both are load-bearing: a broken extension in `~/.pi/agent` otherwise aborts the run before the model is called, and a fresh config dir without `PI_OFFLINE` does startup network work that **hangs past any sane timeout**.
- `pi` gets a read-only tool allowlist (`read,grep,find,ls`) — no `bash`, `edit`, or `write`. A reviewer looks, never touches.
- Schema enforcement does not survive the OpenRouter paths, so both salvage fenced JSON from prose. A final salvage pass repairs any backend's output file in place.
- `openrouter` and `pi` report **real billed cost**; `pi` additionally breaks out cache reads.

The `gemini` backend is gone — Gemini CLI was shut down for Pro/Ultra tiers on 2026-06-18 and replaced by Antigravity CLI. Passing `--tool=gemini` now errors with a pointer to `agy`.

Two `agy` quirks the wrapper already handles, worth knowing before you hand-roll a call: it **ignores piped stdin** (the diff goes in by path instead), and reasoning effort is **part of the model slug** (`gemini-3.6-flash-high`), so `--effort` alongside a suffixed slug is a hard error. `agy` also serves `claude-sonnet-4-6` and `gpt-oss-120b-medium`, but those ignore `--json-schema` — for Claude models prefer `--tool=claude`.
