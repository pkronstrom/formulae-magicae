# Usage ledger and run log — debugging a thin or suspicious panel

Read this when a panel looks smaller than expected, a slot silently reported
"no findings", or `output_bytes` looks suspiciously small.

## Usage ledger

Pass `--report-usage=FILE` to append one normalized JSONL record per agent:

```json
{"tool":"openrouter","agent":"code-quality","model":"deepseek/deepseek-v4-pro","effort":null,
 "input_tokens":5809,"cached_input_tokens":0,"output_tokens":4509,"reasoning_tokens":0,
 "total_tokens":10318,"cost_usd":0.020995032}
```

Every backend reports different field names, so the wrapper normalizes them. `cost_usd` is only populated where the vendor reports it — `openrouter` (real billed cost) and `claude` (`total_cost_usd`); `codex` and `agy` report tokens only, since neither exposes a per-run price. A ledger failure never fails the review, it only warns.

**The ledger has survivorship bias — do not use it to check coverage.** It is
written at the very end of `dispatch.sh`, and `set -e` kills the script the
moment a backend fails, so **only successful runs are ever recorded**. The panel
that lost two of four slots wrote two ledger lines and left no trace of the rest.

## Run log

Separate from the ledger, always on, and it records failures. One JSONL record
per run at `~/.local/state/review-work/runs.jsonl` (override `REVIEW_WORK_LOG`,
set it empty to disable; trimmed to the last `REVIEW_WORK_LOG_KEEP`, default 500):

```json
{"ts":"2026-08-05T11:50:50Z","agent":"code-quality","tool":"pi","model":"z-ai/glm-4.7-flash",
 "effort":null,"outcome":"ok","exit":0,"duration_s":126,"output_bytes":1709,
 "output_file":"/tmp/review-out-glm.json"}
```

`outcome` is one of `ok`, `backend-error` (70), `timeout` (124), `missing-input`
(66), `parse-error` (65), `invalid-output` (69), `no-api-key` (78),
`usage-error` (64). **This is the thing to check when a panel looks thin**:
`output_bytes: 0` with a non-`ok` outcome is a slot that did not run, which is
the state that gets mis-reported as "an empty pass". Failures the ledger cannot
show:

```bash
python3 -c "
import json
for l in open('$HOME/.local/state/review-work/runs.jsonl'):
    r=json.loads(l)
    if r['outcome'] != 'ok':
        print(f\"{r['ts']} {r['tool']:<7} {r['outcome']:<14} {r['duration_s']}s\")"
```

One gap worth knowing: a timeout is logged by the outer wrapper, which only sees
an *explicit* model argument — `model` is `null` there when the backend default
was used. Everything else records the resolved model.

**`ok` used to mean "bytes arrived", not "a review happened" (fixed
2026-08-11).** On a `/revxflash` panel the DeepSeek V4 Flash slot answered with
the **JSON Schema itself** — `{"type":"object","properties":{…},"$schema":…}`,
with `status` and `agent` pasted *inside* `properties` — 327 well-formed bytes
containing no findings and no review. It parsed, so every check in the wrapper
was satisfied and the run log said `ok`. Same family as the `claude` prompt bug:
**the output stayed plausible, so nothing looked wrong.**

`dispatch.sh` now ends with a shape check, not a parse check. The output must be
an *instance* of the schema — required keys at the top level, `status` in the
enum, `scope`/`findings` arrays of objects — and it must say *something*: no
findings **and** an empty summary is rejected as an agent that returned nothing.
Failing that is exit 69 / `invalid-output`, and the file is moved to
`<output>.rejected` so the "no file means the slot did not run" contract in
Step 4 keeps holding while the evidence survives. The schema echo gets its own
error message, because it is a prompt bug rather than a weak model. Two other
things changed with it:

- Every backend prompt now asks for **an INSTANCE of the schema, never the
  schema document copied back**. Inlining the contract into the prompt is what
  invites the echo, and only `codex`/`agy`-gemini enforce it server-side.
- `pi`'s salvage no longer *prefers* a schema echo. It returned the first
  parseable object it found; when a model wrote the echo in `text` and the real
  review in `thinking`, the echo won. Schema-shaped objects are now skipped
  unless nothing better exists — verified on the shapes that produced this bug.

**A cheap model is more likely to do this, so read a suspiciously small
`output_bytes` as a question, not a pass.** Both flash-tier slots in that panel
came back under 600 bytes; one was a real clean review and one was this.

Native backends report `account-dependent` as their cost basis in the portable bundle. Determine subscription/credit/API billing from the actual account; backend identity alone cannot establish it.
