---
name: review-work
description: Review recent code changes via parallel isolated agents across five backends (codex, Antigravity, Claude, pi, OpenRouter) — 1-4 angles or a cross-vendor panel. Activated by /review-work and the rev shortcuts.
---

# review-work

Orchestrate parallel review agents over recent code changes. Each agent runs fully isolated — no shared session state, no user config, no stray MCP context — so agents cannot pollute each other or hallucinate about unrelated codebases. Every agent writes the same JSON-Schema-shaped object for reliable downstream parsing, whichever backend produced it.

Two orthogonal ways to scale a review:

- **Depth / angles** (`/rev1`–`/rev3`): more reviewers, each looking at a different aspect, mostly one model family.
- **Diversity** (`/revxflash`, `/revx`, `/revxhigh`, `/revxultra`): one aspect, several different base models, because different pretraining lineages fail differently. The four tiers vary model strength and cost, not the method.

## Layout of this bundled playbook

The Rev skill passes the absolute path of its bundled `review/` directory as `<skill-base>`. Resolve the following files inside that directory; do not look for a separately installed review-work skill:

- `SKILL.md` (this file) — the orchestration playbook.
- `dispatch.sh` — the wrapper that runs one agent on any backend with all isolation flags.
- `schema.json` — the JSON Schema enforced on every agent's output.
- `prompts/code-quality.md`, `prompts/design-alignment.md`, `prompts/architecture.md`, `prompts/ui-ux.md` — per-agent task prompts.

## Step 1: Detect Scope

Identify what to review:

```bash
git diff --name-only HEAD
# if empty, check recent commits:
git diff --name-only HEAD~3..HEAD
```

If both are empty or scope is ambiguous, ask the user:

1. **Uncommitted changes** — what they just worked on
2. **Last N commits** — recent committed work
3. **Specific files** — user specifies

### Reviewing a document rather than a change

Not every review target is a diff. "Review this plan", "check the design doc",
"look at the spec before I build it" ask about a file's *content*, and there may
be no commit that introduced it. When the target is one or more documents:

```bash
cat docs/plans/the-plan.md > /tmp/review-target.md      # or several, concatenated with headers
```

Pass that file where the diff normally goes. Every backend already treats the
positional file as "the thing under review" — `pi`, `agy` and `claude` read it by
path, `or` inlines it — so nothing in `dispatch.sh` needs to change.

**Never fabricate an empty patch to satisfy the diff-shaped call.** An empty
`/tmp/empty.patch` produces agents that correctly report nothing to review, which
then looks like a delivery failure and sends you debugging the wrapper. That has
happened: three retries and a wrong root-cause diagnosis blaming `run_claude`,
when the real problem was that a plan review had been forced into a diff-shaped
hole.

Angle selection follows the same table as any prose diff — `code-quality` adapts
to documents, `design-alignment` applies when there is something to align
against, and `architecture`/`ui-ux` usually do not.

Capture the unified diff to a file. Every backend takes it as a file path; how it reaches the model differs (stdin for codex/claude, by-path for agy/pi, inlined for openrouter) and `dispatch.sh` handles that:

```bash
git diff HEAD > /tmp/review-diff.patch
# OR for committed work:
git diff HEAD~3..HEAD > /tmp/review-diff.patch
```

## Step 2: Choose Review Mode

Ask the user — but only when the answer is genuinely missing. Skip this step entirely when the mode is already determined: invoked via rev1/rev2/rev3, or the arguments already name a mode and roster ("Panel mode, fast roster, minus agy"). Asking a question the caller has already answered reads as not having listened.

1. **Panel** (4 agents) — One angle, four vendors (Recommended; see below)
2. **Quick** (1 agent) — Code quality only
3. **Focused** (2 agents) — Code quality + design alignment
4. **Deep** (3 agents) — Code quality + design alignment + architecture
5. **Full** (4 agents) — Deep + UI/UX (for frontend changes)
6. **Custom** — Specify angles and tools

Panel leads because it is what the work actually calls for: measured over 60 days,
the panel shortcuts ran 53 times against 10 for the angle modes. One angle across
four lineages catches more than four angles from one lineage, because the failure
modes are uncorrelated. Reach for modes 2–5 when you want *coverage* of different
concerns rather than independent judgment on one.

Custom mode is the only way to use a non-codex backend (`--tool=agy`, `--tool=claude`, `--tool=pi`, `--tool=or`) or Claude's Task agents. When the user picks custom, ask which angles + tools.

**Pick angles by what the diff actually contains.** The mode numbers above assume a source-code change; a diff of plans and READMEs needs a different lens, and `ui-ux` on a backend diff is wasted spend.

| Diff is mostly | Useful angles | Skip |
|---|---|---|
| Source code | code-quality, architecture | ui-ux unless frontend |
| Docs, plans, specs, prompts | code-quality (it adapts — see below), design-alignment | architecture, ui-ux |
| Config, CI, manifests | code-quality (adapts) | ui-ux |
| Frontend | all four | — |

`code-quality` branches on content type: for prose and config it reviews accuracy, contradictions, and stale instructions rather than hunting for off-by-one errors, because code criteria applied to a document produce noise and a bare "no bugs found" on a plan is a non-answer. `ui-ux` and `design-alignment` self-gate and return `pass` when they do not apply, so a wrong angle costs a wasted agent rather than a wrong answer.

### Backends

| `--tool` | CLI | Default model | Schema enforcement |
|---|---|---|---|
| `codex` (default) | `codex exec` | `gpt-6.1-sol` @ `high` | yes (`--output-schema`) |
| `agy` | Antigravity CLI | `gemini-3.6-flash-high` | `gemini-*` models only |
| `claude` | `claude --print` | `sonnet` (Sonnet 5.5) @ `high` | prompt contract + salvage |
| `openrouter` (`or`) | HTTPS API, no tools | `deepseek/deepseek-v4-pro` | `response_format` + prompt fallback |
| `pi` | pi (lightweight harness) | `z-ai/glm-5.2` via OpenRouter | prompt contract + salvage |

**When GNU `timeout` is on PATH, every backend is under a wall-clock timeout**, and the ceiling **scales with
diff size** — `600s + 4s/KB`, clamped to `[600, 2400]`, overridable with
`--timeout=SECS` (`0` disables). Without `timeout`, the wrapper does not enforce this ceiling; install it or retain a host-managed process handle for supervision. A flat 900s was wrong at both ends: it false-timed
out large reviews and made a wedged small one waste fifteen minutes. Diffs over
100 KB also print a note suggesting you split them, because a patch that size
reviews badly regardless of how long you wait.

**The lesson worth keeping: a delivery bug looks like a quality issue, because the output stays plausible.** A silently prompt-less reviewer still fills the schema. If a backend starts producing reviews that never reference anything prompt-specific, suspect delivery before quality — see `references/backend-postmortems.md` for the incident history (the `claude` backend silently dropped its prompt for months; two `pi` isolation bugs; why `or` never gets faster on large diffs).

**How much harness an OpenRouter model gets.** This matters more than it looks: `--tool=or` has *no* harness at all — one HTTP call, no tools, the diff is the entire context. It cannot open a file or grep the repo, so it only finds bugs visible inside the diff text. Measured on one identical review, same model:

| Backend | Harness | Tokens | Cost |
|---|---|---|---|
| `or` | none — diff only | 7.9k | $0.009 |
| `pi` | read/grep/find/ls, read-only | **29.9k** | $0.0067 |

**Use `pi` by default** — it can open files, so it catches problems the diff text alone never shows (the stale-reference class of bug lives entirely outside the diff). It also came out *cheaper* despite more tokens, because its cache reads bill at a fraction of fresh input.

**Use `or` as the fallback** when you want a hard cost ceiling (one call, spend bounded by diff size — `pi` can wander a large repo), when the model is too weak to drive a tool loop, or when `pi` itself is broken. Accept that it is blind past the diff.

### Data privacy on OpenRouter

`--tool=or` and `--tool=pi` route through third-party OpenRouter providers of varying data policy — `dispatch.sh` enforces a zero-retention floor by default. Full detail (verified provider list, pricing guard, jurisdiction pinning, presets): `references/openrouter-privacy.md`.

### Visual review (screenshots)

**Do not route visual review through the dispatch agents — they consistently deprioritise a screenshot in favor of the source, and it was tested and found not worth a dedicated flag.** Read a screenshot directly in the orchestrating session instead, and fold the findings into the summary. Verified per-backend vision support, if you still want to try a dispatch agent: `references/vision-review.md`.

### Panel mode (cross-vendor)

Modes 1–4 vary the **angle** and hold the model roughly fixed. Panel mode inverts that: **one angle, four different base models**, because models from different pretraining lineages fail differently. A bug Sol cannot see is often obvious to Sonnet, and vice versa.

The balanced default — one agent per vendor lineage:

| Slot | Backend | Model | Why it earns the slot |
|---|---|---|---|
| 1 | `codex` | `gpt-6.1-sol` @ `high` | OpenAI lineage; balanced current coding tier |
| 2 | `claude` | `sonnet` (5.5) @ `high` | Anthropic lineage; current balanced coding tier |
| 3 | `pi` | `x-ai/grok-4.5` | xAI lineage; replaced the Google slot when agy's free quota proved unusable |
| 4 | `pi` | `z-ai/glm-5.2` | Chinese open-weight; best long-horizon of the open models (FrontierSWE 74.4 vs DeepSeek V4 Pro's 29.0) and leads SWE-bench Pro at 62.1 |

```bash
LEDGER=/tmp/review-usage.jsonl
D=<skill-base>/dispatch.sh; P=/tmp/review-prompt-quality.md; F=/tmp/review-diff.patch
$D --report-usage=$LEDGER              code-quality $P $F /tmp/out-sol.json  &
$D --report-usage=$LEDGER --tool=claude code-quality $P $F /tmp/out-sonnet.json &
$D --report-usage=$LEDGER --tool=pi     code-quality $P $F /tmp/out-grok.json x-ai/grok-4.5 &
$D --report-usage=$LEDGER --tool=pi     code-quality $P $F /tmp/out-glm.json z-ai/glm-5.2 &
```

**Use the identical prompt for every panel agent.** Do not paraphrase per model. The whole value of the panel is that model identity is the *only* variable — that is what makes agreement meaningful. If each agent gets differently-worded instructions, a disagreement no longer tells you whether the models genuinely differ or whether one was simply asked a different question, and the Step 4 consensus math (same file, ±5 lines → severity bump) stops being evidence of anything. Vary the **angle** when you want coverage; vary the **model** when you want independent judgment. Never vary both at once.

**Fast panel** (`/revxflash`) — same idea at the speed tier, four lineages for roughly the price of one slow agent:

| Backend | Model |
|---|---|
| `codex` | `gpt-6-luna` @ `medium` |
| `pi` | `x-ai/grok-4.3` |
| `pi` | `~deepseek/deepseek-v4-flash-latest` |
| `pi` | `z-ai/glm-4.7-flash` |

**Strong panel** (`/revxhigh`) — `codex` Astra at `xhigh`, `claude` Opus 5.5 at `high`, `pi` grok-4.5, and `pi` glm-5.2.

**Maximum panel** (`/revxultra`) — six agents: the above plus a second Anthropic slot (`claude` **fable**, which fails differently from Opus) and `pi` deepseek-v4-pro for dense logic, with Astra at `max`.

Both are escalation paths for work that is expensive to get wrong; neither is a default. Prices and per-slot reasoning live in the `/revx` table above and `references/pool-fallback.md`.

**Budget deliberate upgrades.** Balanced defaults use Sol 6.1 and Sonnet 5.5. Strong and maximum rosters upgrade to Astra and Opus, with Fable 5.1 added only in the maximum roster. Effort changes reasoning-token usage; model choice changes the rate as well. Check current pricing instead of applying old Sol/Terra ratios.

**Anthropic billing is account-dependent.** Opus and Sonnet may draw included quota; Fable can draw usage credits. Do not describe either quota or credits as free.

**The Google slot is absent from these bundled default rosters (2026-08-10).** Not a
capability judgement — the historical `agy` account used for these runs was unreliable for this workload. Measured
from the run log over five days: **0 successes in 12 attempts**, every one
`RESOURCE_EXHAUSTED`, because a 7-day quota window is emptied by a couple of
reviews. A slot that never runs is worse than no slot: it fails late, and a panel
that reports it as a finding-free pass silently turns N-1 opinions into N.

`x-ai/grok-4.5` takes the seat. It is a lineage nothing else in the panel shares,
it passes the privacy floor on xAI's own endpoint (verified with a live request),
and at $2/$6 it is mid-priced rather than frontier.

Google stays reachable, but **route it through OpenRouter, not `agy`** —
`pi google/gemini-3.6-flash:high`, or `~google/gemini-flash-latest` at
$1.50/$7.50, both of which pass the privacy floor. `+gemini` means the OpenRouter
path now; the native `agy` path is not a fallback worth offering.

The run log is unambiguous on this: `agy` completed **4 of 19** recorded runs,
failing 0-for-3, 0-for-3, 0-for-4, 0-for-2 and 0-for-2 on five of the six days it
was used, with one good day in between. The failures log as `backend-error`, not
quota exhaustion, so "wait for the window to reset" was the wrong diagnosis. The
same lineage through OpenRouter completed 8 of 9.

**Two Anthropic slots only in `/revxultra`.** This adds a second independent Anthropic review, not a new vendor lineage. Everywhere else, one per lineage.

All four rosters name *native* backends. When a slot's pool is dry — `agy` has already
tripped this in practice — every one of these models has an OpenRouter counterpart
reachable via `--tool=pi`; see [When a pool runs dry](#when-a-pool-runs-dry). Ask
the user before spending cash on a swap.

**The command files own the rosters.** `/revx`, `/revxflash`, `/revxhigh` and
`/revxultra` each define their own roster, and those definitions are
authoritative; the tables in this file describe the *shape* of panel mode and are
a copy for reading. Where the two disagree, the command file wins — and the
disagreement is a bug to fix, not a choice to make.

All four panels share one roster grammar: bare names set the roster (default if none given), then `+name` adds and `-name` removes.

**Group aliases** save spelling out a roster to express one constraint. They
resolve to the slots matching them in the current roster, so `-cn` means "the
default minus whatever Chinese-provider slots it has" rather than a fixed list:

| Alias | Slots it covers |
|---|---|
| `cn` | `z-ai/glm-*`, `deepseek/*`, `moonshotai/*`, `qwen/*` |
| `us` | `codex`, `claude`, `x-ai/*` |
| `anthropic` | `claude` slots (`sonnet`, `opus`, `fable`) |
| `metered` | every `pi`/`or` slot — the ones that cost cash |

`/revx -cn` is the jurisdiction filter that keeps coming up; `/revx -anthropic`
is the quota-saver `-sonnet` generalised. `/revx -sonnet` is the common cost-saver — in practice the Anthropic agent explores far more of the repo than the others and runs ~1M tokens of plan quota, roughly 16x the rest of the panel combined. Others can explore too; they just tend not to.

Optional 5th slot: `deepseek/deepseek-v4-pro` — LiveCodeBench 93.5% (highest of any model) and Codeforces 3206, so it is the specialist for algorithmic and logic bugs, but weak on long-horizon repo work. Add it when the diff is dense logic; skip it for wiring and plumbing changes.

Escalation: `moonshotai/kimi-k3` is the strongest open-weight model on measured capability, at $3/$15 per 1M — half of Sol, but ~4× GLM-5.2. Worth a slot only when the diff is genuinely hard.

**Qwen, as of 2026-09-02.** Two open-weight tiers pass the zero-retention floor:
`qwen/qwen3.8-2.4t-a95b` (`+qwen`) is the open-weight release of Qwen3.8 Max — 95B
active of 2.4T, 1M context, $2 → $6 /M — and `qwen/qwen3.8-27b` (`+qwen-27b`) is
the cheap dense tier at $0.42 → $2.55. The hosted tiers do not: `qwen3.8-max` and
`qwen3.8-flash` are refused outright. The same family, blocked in its hosted form
and usable in its open-weight one, is the clearest illustration of the rule.

At $2 → $6 the flagship Qwen undercuts `kimi-k3` ($3 → $15) by 2.5x on output for
a comparable class of model, which makes it the default open-weight escalation.
Same verdict still stands for `meta/muse-spark-1.x`, otherwise tempting at
$1.25/$4.25.

Zero-retention is enforced account-wide, so a single live request is the entire
test — a refusal *is* the policy failure. Retest a slug rather than predicting it.

Panel cost is roughly the sum of four cheap runs, not four expensive ones — measured on a small diff, the GLM and DeepSeek agents each bill about **$0.02**. Run with `--report-usage` and check the ledger rather than guessing.

### Model and reasoning effort

`dispatch.sh` defaults to **`gpt-6.1-sol` at `high`** — the daily-driver setting. Both are overridable per agent (5th and 6th positional args, or `--effort=`). Claude reviews also default to `high` and accept an explicit effort override.

| Job | Model | Effort |
|-----|-------|--------|
| Daily code review (rev1) | `gpt-6.1-sol` | `high` |
| Focused review (rev2) | `gpt-6.1-sol` | `xhigh` |
| Critical security audit (rev3) | `gpt-6-astra` | `high` |
| Complex bug hunting | `gpt-6-astra` | `xhigh` |
| Cheap triage / huge mechanical diffs | `gpt-6-luna` | `medium` |

Effort ladder: `low` → `medium` → `high` → `xhigh` → `max` → `ultra`. The local Codex cache advertises `ultra` for Sol 6.1 and Astra, but not Luna. Use `high` or deeper for substantive reviews; the explicit cheap-triage/flash modes use `medium` and trade depth for speed. Do not infer delegation from effort.

**Capability escalation.** Use Astra for the most demanding Codex reviews; Opus 5.5 and Fable 5.1 are explicit Anthropic alternatives. Follow account access and the preflight rather than historical benchmark rankings. Current models checked 2026-10-13 against the [OpenAI guide](https://developers.openai.com/api/docs/guides/latest-model), local Codex cache, and [Anthropic model lineup](https://platform.claude.com/docs/en/models/overview).

```bash
<skill-base>/dispatch.sh --tool=claude --effort=high code-quality $P $F /tmp/out.json fable
<skill-base>/dispatch.sh --tool=claude --effort=high code-quality $P $F /tmp/out.json opus
```

### Usage ledger and run log

Pass `--report-usage=FILE` to `dispatch.sh` for a normalized per-agent JSONL cost/token record (`references/logging-and-ledger.md` has the schema). A separate always-on run log at `~/.local/state/review-work/runs.jsonl` records every attempt including failures — **check this, not the ledger, when a panel looks thin**: the ledger only ever records successes. Full debugging walkthrough (survivorship bias, the schema-echo bug, reading `output_bytes`): `references/logging-and-ledger.md`.

**Credit discipline.** Quota and allowance are finite budgets. More agents, higher effort, and stronger model tiers all increase consumption. Use `max`/`ultra` deliberately, and inspect the preflight before a panel. Do not use historical Sol/Terra price ratios to estimate current models.

### Budget pools

Billing depends on the account and provider, not only the backend. Native Codex and Claude sessions can use subscriptions, credits, or API billing; do not infer someone else's funding from the CLI name. The preflight labels native pools as `account-dependent`. The following are possible pools:

| Pool | Backends | What a review actually spends | Failure mode |
|---|---|---|---|
| **Subscription quota** | `claude` | On a subscription, plan quota in a rolling window; API accounts can be metered. Interpret cost telemetry according to the account. | Exhausting it **blocks your own interactive Claude Code sessions** — the review competes with your day's work |
| **Account allowance** | `codex`, `agy` | Subscription or prepaid account credits | Can be exhausted or rate-limited |
| **Metered cash** | `openrouter` | Real money, billed per token | Unbounded in principle — but see the numbers |

Historical observations from one account setup (not current price or token guarantees):

- `openrouter` / GLM-5.2 — **$0.009 per review**. A hundred reviews is under a euro, and it touches **no quota at all**.
- `claude` / sonnet — **~500k tokens per review**, because it agentically explores the repo. That is the single heaviest draw in the whole skill, and it lands on the pool you need for actual development.

These observations do not establish costs for another account. Inspect current prices and account limits before choosing a billing pool; do not silently switch to a metered provider.

**Capability vs. behaviour — do not confuse them.** Every harnessed backend *can* read the whole repo: `codex` under `-s read-only` reads anywhere on disk (that sandbox restricts writes, not reads — verified by having it list a directory far outside its cwd), and `agy`, `pi`, and `claude` all run in the project directory with file tools. Only `--tool=or` is structurally blind, because it has no tools at all.

What differs is how much they *choose* to look. Token spend on one identical review:

| Backend | Tokens | Behaviour |
|---|---|---|
| `claude` / sonnet | 962.9k | explores aggressively across the repo |
| `agy` / gemini-flash | 47.6k | some exploration |
| `codex` / terra | 18.7k | mostly reads the diff |
| `pi` / glm-5.2 | 18.0k | mostly reads the diff |
| `or` / deepseek | 2.4k | cannot explore at all |

That gap turned out to be **prompting, not capability** — but the original reading of it was wrong, and the correction is the more useful lesson. The wrapper told `agy` and `pi` in as many words to "review only what it contains", and they obeyed. Sonnet was recorded as exploring *despite* that instruction.

It never defied anything: **it never received the instruction.** `--add-dir` swallowed the prompt (see the `claude` note under [Backends](#backends)), so Sonnet got a bare diff and no task and did what an agent with file tools and no boundaries does — read everything. The 962.9k figure is the cost of an unprompted agent, not of an aggressive one. Re-measure this row now that the prompt actually arrives before treating it as a property of the model.

Both are fixed: `prompts/code-quality.md` now has a **Verify against the repo** section directing agents to grep for stale references when a change renames, moves, or deletes anything, and the wrapper tells them they are inside the repo with read access. The instruction is deliberately bounded — "a handful of deliberate greps, not a survey" — because open-ended crawling is what turns a review into a million-token run.

Measured on a fixture where `validate_token` → `check_token` was renamed in one file, leaving stale references in `handlers.py` and `README.md` that the diff never touches:

| Backend | Found | Tokens |
|---|---|---|
| `pi` / glm-5.2 | both | 6.6k |
| `codex` / terra | both | 86.3k |
| `or` / deepseek | neither (correct) | 1.0k |

`codex` explores fine despite `-C /tmp`, so the cwd was never the blocker. `or` correctly reported nothing rather than claiming to have checked — its system prompt states it has no tools and must ignore any instruction to grep, which stops a toolless model from inventing verification it cannot perform.

Practical routing:

- Routine / pre-commit → `/revxflash` (no Anthropic slot at all; pennies of metered spend)
- Normal review → `/rev1` on the configured Codex account
- Subtle or security-sensitive → `/revx`, accepting one Sonnet-sized quota bite
- Expensive to get wrong (auth, crypto, money, migrations) → `/revxhigh`
- Pre-release audit, or a split verdict needing a stronger tiebreak → `/revxultra`, after telling the user what it costs
- Never → a 4-agent panel with `opus`/`fable` slots on a routine diff; that is the fastest way to burn a week's quota on plumbing changes

Check remaining Anthropic quota with `/usage` in an interactive Claude Code session, and codex limits with `/status` in the codex TUI. Neither is readable headlessly, so the ledger's `cost_basis` field is how you attribute a run after the fact:

```bash
python3 -c "
import json,collections
p=collections.Counter(); t=collections.Counter()
for l in open('/tmp/review-usage.jsonl'):
    r=json.loads(l); p[r['cost_basis']] += r.get('cost_usd') or 0; t[r['cost_basis']] += r['total_tokens']
for k in t: print(f'{k:<13}{t[k]:>9} tok  \${p[k]:.4f}')"
```

### When a pool runs dry

A panel slot can fail mid-run with a quota/rate-limit error (`agy` has tripped this in practice — resets measured in days, not minutes). Every panel model has an OpenRouter counterpart reachable via `--tool=pi`, so a dry pool costs you the *pool*, not the lineage. **Ask before falling back — never swap to metered OpenRouter spend silently.** Slot-by-slot fallback mapping and the ask-first rationale: `references/pool-fallback.md`.

## Step 2.5: Preflight — say what will run, and what it costs

Before dispatching anything, print the plan. A review fans out to several
providers on three different budgets, and the user cannot see any of that until
the money is already spent.

```bash
<skill-base>/scripts/preflight.py \
  --roster "codex:gpt-6.1-sol@high,claude:sonnet,pi:x-ai/grok-4.5,pi:z-ai/glm-5.2" \
  --diff /tmp/review-diff.patch
```

It prints one row per slot — backend, model, which budget it draws on, and for
metered slots an estimated dollar cost — plus the metered total. Prices come from
OpenRouter's live model list, cached for a day, so the estimate cannot quietly
rot the way a hardcoded table does.

**Then ask, whenever at least one slot is metered:**

> "That's N agents, M of them via OpenRouter at about $X. Run the full panel, or
> skip the OpenRouter slots?"

Skipping leaves the allowance and quota slots, which is a real review — smaller,
and free of cash spend. When no slot is metered there is nothing to decide, so
print the table and carry straight on rather than asking a question with one
answer.

The estimate is a forecast, not a quote: `pi` slots vary most, because how much
a harnessed agent reads is up to the agent. Report the ledger total afterwards so
the two can be compared.

## Step 3: Build Prompts and Dispatch

For each agent in the selected mode, build a task prompt file under `/tmp/` by concatenating:

1. The base prompt template from `<skill-base>/prompts/<agent-id>.md`.
2. Any per-agent context the orchestrator gathers (design docs for `design-alignment`; README/CLAUDE.md excerpts for `architecture`).

```bash
# Example: design-alignment agent
cp <skill-base>/prompts/design-alignment.md /tmp/review-prompt-design.md
echo "" >> /tmp/review-prompt-design.md
echo "## Design docs" >> /tmp/review-prompt-design.md
ls docs/plans/*.md 2>/dev/null | head -3 | while read f; do
  echo "### $f" >> /tmp/review-prompt-design.md
  cat "$f" >> /tmp/review-prompt-design.md
done

# Example: architecture agent
cp <skill-base>/prompts/architecture.md /tmp/review-prompt-architecture.md
{
  echo ""
  echo "## Project context"
  head -50 README.md 2>/dev/null
  echo "---"
  head -30 CLAUDE.md 2>/dev/null
} >> /tmp/review-prompt-architecture.md
```

Then dispatch each agent in **parallel** as a background Bash command:

```bash
# defaults: gpt-6.1-sol at high
<skill-base>/dispatch.sh code-quality      /tmp/review-prompt-quality.md       /tmp/review-diff.patch /tmp/review-out-quality.json &
<skill-base>/dispatch.sh design-alignment  /tmp/review-prompt-design.md        /tmp/review-diff.patch /tmp/review-out-design.json &
<skill-base>/dispatch.sh architecture      /tmp/review-prompt-architecture.md  /tmp/review-diff.patch /tmp/review-out-architecture.json &
<skill-base>/dispatch.sh ui-ux             /tmp/review-prompt-uiux.md          /tmp/review-diff.patch /tmp/review-out-uiux.json &

# explicit model + effort (5th and 6th args) — e.g. a security-grade architecture pass
<skill-base>/dispatch.sh architecture /tmp/review-prompt-architecture.md /tmp/review-diff.patch /tmp/review-out-architecture.json gpt-6-astra high &

# cross-vendor second opinion on the same diff
<skill-base>/dispatch.sh --tool=agy code-quality /tmp/review-prompt-quality.md /tmp/review-diff.patch /tmp/review-out-agy.json &
```

Mixing backends is the cheapest way to break correlated blind spots: two agents that share a base model tend to miss the same things, so a `codex` + `agy` pair on the same angle finds more than two codex agents do.

Use the calling host's process lifecycle for every dispatch invocation. When the host supports background completion notifications, retain each task handle and await its notification. When it provides process/session handles and a wait or resume tool instead, use those tools until every process completes. If neither exists, keep invocations attached; for a parallel shell batch, retain each PID and use shell `wait` to collect each exit status before the calling tool returns.

Do not finish the task after launch unless the host guarantees a continuation. Avoid tight polling; bounded waits on known handles are valid. After every job completes, inspect exit statuses and the expected output files. A notification signals completion, not success. Keep failed or missing outputs visible as incomplete review slots.

**Why the wrapper:** `dispatch.sh` encapsulates each backend's isolation flags, which are different everywhere and easy to get wrong:

- **codex** — `--ephemeral --ignore-user-config --ignore-rules -s read-only`. Without these it loads `~/.codex/config.toml` MCP servers (Linear auth failures) and hallucinates findings about unrelated codebases.
- **agy** — `--mode plan --disable-slash-commands`; diff by path, since piped stdin is silently ignored. In a headless session it can also auto-deny its own command permission and return an empty response — indistinguishable from a clean review until you notice the slot produced nothing. Drop the slot rather than retrying it.
- **claude** — `--no-session-persistence --permission-mode plan --strict-mcp-config --disable-slash-commands`.
- **pi** — ephemeral `PI_CODING_AGENT_DIR`, `PI_OFFLINE=1`, and a read-only tool allowlist. Not every model drives it well: `z-ai/glm-4.7-flash` has hung under `pi` and once wrote a 1.5 GB temp file before the timeout caught it. Route that model through `--tool=or` instead; the flash tiers generally suit the toolless path better.
- **openrouter** — no harness to isolate; the HTTP call has no tools at all.

It also normalizes what comes back: every backend emits a different envelope, and only some honor a schema, so the wrapper unwraps and salvages until the output file is the bare schema object. Where a backend accepts stdin, the diff goes that way to avoid argv truncation on large patches.

## Step 4: Synthesize Results

Read each `/tmp/review-out-*.json` file using the Read tool. The schema guarantees they are valid JSON objects with `agent`, `scope`, `status`, `findings[]`, `summary`.

**First, account for every slot you dispatched.** A backend that fails writes *no
output file at all* — `dispatch.sh` removes it up front and only writes on
success, so a missing file means that slot did not run. Check the file exists
before you read it, and check `wc -l` on the ledger matches the number of agents
you launched.

> A missing or unparseable output is **not a pass**. It is not "found nothing",
> not "clean", and not "an empty review". Say the slot **did not run**, and give
> the reason from its stderr — `dispatch.sh` surfaces the raw backend error
> (`Individual quota reached…`, `backend produced no result within Ns…`).

A slot can also return a file that parses and still contains no review — the
schema echoed back, an off-contract object, an empty summary with no findings.
`dispatch.sh` rejects those (exit 69, `invalid-output`) and moves them to
`<output>.rejected`, so the rule above covers them without any extra checking on
your side: **no file at the dispatched path = that slot did not review.** If you
want to know *why*, read the `.rejected` file.

This matters most in panel mode: reporting a dead slot as a finding-free pass
turns *N-1 opinions* into what looks like *N-way agreement*, which is the exact
signal the panel exists to produce. **Never count a non-running slot toward
consensus** — the ±5-line severity bump below applies only to slots that actually
returned. A three-agent panel where one backend is quota-dead is a two-agent
panel, and the summary must say so before it says anything else.

**Consensus detection.** Two findings are consensus when they target the same `file` and their `line` values are within 5 lines of each other. When consensus is detected, bump the merged finding's severity by one tier (low → medium → high → critical) and set `confidence: "high"`.

### Output contract

**Who is reading decides what you print.** There are two consumers and they want
opposite things — a human wants the findings, a subagent wants a parseable object.
Printing both to both is the current failure: it buries a human's answer under a
few hundred lines of JSON they will never read, and it forces a subagent to strip
prose it should never have received.

**Default — a human is reading. Print the Markdown summary only.**

Do **not** paste the consensus JSON into the reply. Every finding in it is already
in the summary above, and its `agents[]` array is a verbatim copy of files that
already exist at the output paths you dispatched to. Write it to
`/tmp/review-consensus.json` and reference it in a single line instead:

```
Full report: /tmp/review-consensus.json (6 agents, 9 findings)
```

**Exception — a subagent called you.** If you were spawned to *return* a review
rather than show one (`/agent-team`'s reviewer is the case that exists), print the
JSON object **only**, with no Markdown summary and no prose around it. Your return
value is data, not a message.

The two artifacts:

1. The Markdown summary — the default, and the only thing a human sees:

   ```markdown
   ## Review Summary

   **Scope**: <files reviewed>
   **Mode**: Quick / Focused / Deep / Full / Custom
   **Status**: pass | warn | fail

   ### Critical / High Priority
   - [file:line] Issue description (Source: code-quality / design-alignment / architecture / ui-ux)

   ### Medium Priority
   - ...

   ### Low Priority
   - ...

   ### Design Alignment
   <drift/gaps summary, or "No design docs found" if N/A>

   ### Consensus Issues
   <findings flagged by 2+ agents — these are highest confidence>
   ```

2. The consensus report — written to `/tmp/review-consensus.json`, and printed
   inline as a single fenced ```json block **only** when a subagent called you:

   ```json
   {
     "mode": "quick | focused | deep | full | custom",
     "scope": ["<files reviewed>"],
     "status": "pass | warn | fail",
     "agents": [
       { /* per-agent JSON object, verbatim from the agent output */ }
     ],
     "consensus_findings": [
       { /* merged findings flagged by 2+ agents, severity-bumped */ }
     ],
     "summary": "<one or two sentences across the whole review>"
   }
   ```

   Top-level `status` is the worst of the per-agent statuses: any `fail` → `fail`; else any `warn` → `warn`; else `pass`.

`/agent-team`'s reviewer subagent parses this object to triage findings into fix
tasks without re-parsing prose — it reads `consensus_findings` when present and
falls back to the union of `agents[*].findings`, which is why `agents[]` stays
verbatim in the machine path even though the same objects are on disk.

That subagent is the *only* reason the inline JSON exists. When a human asked for
the review, the file plus the Markdown summary carry everything, so print the path
and stop.

## Step 5: Next Steps

Ask the user:

1. **Fix now** — Create a TodoWrite checklist from the findings and implement fixes in the current session
2. **Plan fixes** — Write findings to a `docs/plans/` document using `/superpowers:writing-plans` for a separate session
3. **Acknowledge** — Summary noted, move on
