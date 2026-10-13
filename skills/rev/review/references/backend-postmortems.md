# Backend postmortems

Incident history for `dispatch.sh` backends. Read this when a backend is behaving
strangely and you suspect a delivery bug rather than a model-quality issue — the
pattern in every incident below is "the output stayed plausible, so nothing looked
wrong."

## The `claude` backend never actually received its prompt

From the first version of this script until 2026-08-05. `--add-dir` is variadic
(`--add-dir <paths...>`), so it consumed the trailing positional prompt as a
directory path. Piping the diff on stdin masked it completely: the CLI had
input, so it never raised `Input must be provided either through stdin or as a
prompt argument`, and a model handed a diff plus a review-shaped schema just
inferred the task and reviewed it. **Verified: a marker token planted in the
prompt never reaches the model, yet the review comes back with correct scope,
severities and messages.** Every `--tool=claude` review before that date was the
model reverse-engineering its job from the schema field names.

It surfaced only because one run stopped improvising and said
"No explicit task was provided alongside the diff" — not a regression, the same
broken call on a less charitable turn. Fixed by sending the task on stdin as the
sole channel with the diff by path, and no positional argument after the flags.

Two things changed alongside it. `--json-schema` is gone: it does not constrain
the answering turn, it appends a second synthetic user turn
(`[structured-output-enforce] You MUST call the StructuredOutput tool…`) that the
model answers *in isolation* — Sonnet refuses outright, objecting the bracketed
prefix "isn't a real system contract". And `--permission-mode plan` is replaced
by a `Read/Grep/Glob` allowlist, because plan mode made the model ask what it was
supposed to plan instead of reviewing.

## Two `pi` failure modes, fixed 2026-08-10, both harness-side

**Lost model metadata.** The ephemeral `PI_CODING_AGENT_DIR` exists to drop user
extensions, but it dropped pi's **model catalog** with them. Every OpenRouter slug
pi does not bundle then resolved as an unknown custom model id with no context
length and no max-output — `Warning: Model "deepseek/deepseek-v4-flash-0731" not
found for provider "openrouter"`. The tell: `pi --list-models` knows the model
(1M ctx, 65.5K out) while the dispatched run does not, because one reads
`~/.pi/agent` and the other an empty temp dir. `run_pi` now copies `models.json`
and `models-store.json` into the clean dir — two files, no extensions, isolation
intact.

**Brittle salvage.** Five parse-errors came from well-formed objects the extractor
could not reach. The old logic took only `text` parts of the last assistant
message and then `find('{')`..`rfind('}')`. Verified broken on: an answer left
entirely in a `thinking` block, prose containing a brace (`f"{u}"`) before the
object, and two objects in one reply. The parser now scans balanced, string-aware
brace spans, prefers the span carrying the schema's required keys, and falls back
across text → concatenated text → reasoning. Ten shapes unit-tested, including two
that must still fail (truncated JSON, no JSON at all) so real breakage stays loud.

## The harness is not what makes large diffs slow

Same 135 KB diff: `pi` (with tools) returned in 215s; `or` (one HTTP call, no
harness) did not finish in 600s. Latency scales with input at the provider —
reaching for `or` to make a big review faster makes it slower and blinder.

## Routing OpenRouter through the codex harness

Also works — set `model_providers.<name>.wire_api = "responses"`, as codex 0.146
dropped `"chat"` — but it is not worth it and is deliberately not wired in: the
same review cost 424k tokens / ~$0.21, about 30× `pi`, and codex's
`--output-schema` does not bind through that provider anyway, so it needs the
same salvage path.
