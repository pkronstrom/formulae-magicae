#!/usr/bin/env bash
# dispatch.sh — run one review agent on any backend, with full isolation.
#
# Usage:
#   dispatch.sh [--tool=codex|agy|claude|pi|or] [--effort=LEVEL] [--timeout=SECS] \
#               [--report-usage=FILE] \
#               <agent-id> <prompt-file> <diff-file> <output-file> [model] [effort]
#
# Args:
#   --tool          backend to use (default: codex)
#   --effort        reasoning effort (codex and claude; also accepted as 6th positional)
#   --timeout       seconds before the backend is killed (default scales with diff
#                   size: 600s + 4s/KB, clamped to [600,2400]; 0 disables)
#   --report-usage  append one normalized JSONL token-usage record per run to FILE
#   agent-id     identifier for the agent (e.g. code-quality, design-alignment)
#   prompt-file  path to a markdown file with the agent's task prompt
#   diff-file    path to the unified diff (delivery differs per backend, below)
#   output-file  path where the agent writes its final JSON response
#   model        optional model override
#   effort       optional reasoning effort override
#
# Backends and their defaults:
#   codex   -> gpt-6.1-sol at effort=high        (account-dependent billing)
#   agy     -> gemini-3.6-flash-high               (Antigravity CLI; replaced
#              Gemini CLI, shut down for Pro/Ultra tiers on 2026-06-18)
#   claude  -> sonnet (Sonnet 5.5; haiku skims review diffs)   (plan quota)
#   pi      -> z-ai/glm-5.2 via OpenRouter         (metered; lightweight harness)
#   or      -> deepseek/deepseek-v4-pro            (metered; NO harness at all)
#
# Harness depth for OpenRouter models, measured on one identical review:
#   or   no tools, diff is the entire context      7.9k tokens   $0.009
#   pi   read/grep/find/ls, read-only             29.9k tokens   $0.0067
# `pi` is the default: it can actually open files, so it finds problems the diff
# text alone does not show. `or` is the fallback — one HTTP call, so cost is
# bounded by diff size and it works with models too weak to drive a tool loop,
# at the price of never seeing beyond the diff.
#
# (Routing OpenRouter through the codex harness also works — set
# model_providers.<n>.wire_api="responses", since 0.146 dropped "chat" — but it
# cost 424k tokens/~$0.21 for the same review, ~30x pi, and codex's
# --output-schema does not bind through that provider anyway. Not worth it.)
#
# Both OpenRouter paths need OPENROUTER_API_KEY.
#
# Codex reasoning effort: low | medium | high | xhigh | max | ultra (ultra is
# sol/terra only). Review work wants `high` as the floor — lower efforts skim.
# Effort does not change the per-token rate, it changes how many reasoning
# output tokens are burned, and output bills ~6x input. Escalate the effort on
# terra before escalating the model to sol.
#
# Antigravity encodes effort IN the model slug (gemini-3.6-flash-high,
# gemini-3.1-pro-low, ...). Passing --model with a suffixed slug together with
# --effort is a hard error, so run_agy only forwards --effort for bare slugs.
# agy tops out at `high`; xhigh/max/ultra are clamped to high.
# `agy models` lists what your account can actually reach.
#
# Isolation goals (and how each backend achieves them):
#   - no persistent session state    codex: --ephemeral
#                                    agy:   (no --continue/--conversation)
#                                    claude: --no-session-persistence
#                                    pi:    --no-session
#   - skip user config & MCP         codex: --ignore-user-config --ignore-rules
#                                    agy:   --disable-slash-commands (plugins are
#                                           opt-in per `agy plugin list`)
#                                    claude: --bare
#                                    pi:    ephemeral PI_CODING_AGENT_DIR
#   - read-only sandbox              codex: -s read-only
#                                    agy:   --mode plan
#                                    claude: --permission-mode plan
#                                    pi:    --tools read,grep,find,ls (no bash/
#                                           edit/write — a reviewer never writes)
#   - structured JSON output         codex: --output-schema FILE
#                                    agy:   --json-schema FILE (enforced for
#                                           gemini-* only — see below)
#                                    claude/pi/or: prompt contract + salvage
#                                            (claude CANNOT use --json-schema —
#                                             it injects a second enforcement
#                                             turn the model answers in
#                                             isolation; see run_claude)
#   - read prompt/diff outside cwd   codex: --add-dir, -C /tmp
#                                    agy:   --add-dir
#                                    claude: --add-dir
#                                    pi:    reads by absolute path
#
# pi needs PI_OFFLINE=1 alongside the ephemeral config dir: a fresh dir otherwise
# triggers pi's startup extension sync, which hangs past any sane timeout. The
# ephemeral dir also sidesteps a broken user extension aborting the run outright.
#
# Diff delivery differs by backend. codex and claude read it from stdin, which
# avoids argv truncation on large patches. agy IGNORES piped stdin entirely
# (verified: it answers as if no diff arrived), so run_agy passes the diff by
# PATH and lets the agent read it with its own file tools; pi does the same.
# The `or` backend has no file tools, so the diff is inlined into the request.
#
# agy --output-format json also wraps the model reply in a transport envelope
# ({conversation_id, status, response, usage}), so run_agy unwraps `.response`
# before writing OUTPUT_FILE. Every backend ends up producing the bare schema
# object.
#
# Caveat: --json-schema is only ENFORCED for agy's gemini-* models. The
# passthrough models it also serves (claude-sonnet-4-6, claude-opus-4-6-thinking,
# gpt-oss-120b-medium) ignore the schema and answer in prose; run_agy salvages
# embedded JSON when it can and errors clearly when it cannot. Prefer gemini-*
# slugs here — for Claude models use --tool=claude, which asks for the schema in
# the prompt body instead.
#
# Whatever the backend, the last thing this script does is check that the output
# is a review INSTANCE and not merely well-formed bytes — see "Did this slot
# actually review?" at the bottom. Failing that check is exit 69
# (`invalid-output`), and the file is moved aside to <output>.rejected so a dead
# slot stays visibly dead.

set -euo pipefail

# Wall-clock guard. A backend that never returns used to look like a silent hang:
# every run_* sends the model's stdout to a temp file, so the caller sees zero
# bytes whether the agent is thinking, wedged, or streaming megabytes. Re-exec
# under `timeout` (bash cannot time out a function) so the failure is loud and
# attributable. --timeout=0, or no timeout(1) on PATH, restores the old
# run-forever behaviour.
# The ceiling scales with diff size, because one fixed number cannot be right at
# both ends: a 5 KB diff still running after 15 minutes is wedged, while a 135 KB
# diff legitimately takes minutes (measured: 215s through pi, and the same diff
# through the harness-free `or` backend did not finish in 600s — bigger inputs are
# slow at the provider, not in the harness). A flat 900s produced both false
# timeouts on large reviews and 15-minute waits on small dead ones.
#
#   budget = 600s + 4s per KB of diff, clamped to [600, 2400]
#
# An explicit --timeout=N or DISPATCH_TIMEOUT=N always wins; 0 disables.
_scan_positionals() {  # -> _pos array, _tool
  _pos=(); _tool="codex"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tool=*) _tool="${1#*=}"; shift ;;
      --tool) _tool="${2:-codex}"; shift 2 ;;
      --effort|--report-usage) shift 2 ;;
      --*) shift ;;
      *) _pos+=("$1"); shift ;;
    esac
  done
}
_scan_positionals "$@"

_explicit_timeout=""
for _arg in "$@"; do
  case "$_arg" in --timeout=*) _explicit_timeout="${_arg#*=}" ;; esac
done

if [[ -n "$_explicit_timeout" ]]; then
  DISPATCH_TIMEOUT="$_explicit_timeout"
elif [[ -n "${DISPATCH_TIMEOUT:-}" ]]; then
  :   # caller set it in the environment
else
  _diff_kb=0
  if [[ ${#_pos[@]} -ge 3 && -f "${_pos[2]}" ]]; then
    _diff_kb=$(( $(wc -c < "${_pos[2]}" 2>/dev/null || echo 0) / 1024 ))
  fi
  DISPATCH_TIMEOUT=$(( 600 + _diff_kb * 4 ))
  (( DISPATCH_TIMEOUT > 2400 )) && DISPATCH_TIMEOUT=2400
  (( DISPATCH_TIMEOUT < 600 )) && DISPATCH_TIMEOUT=600
  # Only the outer process narrates; the inner re-exec recomputes the same value.
  if (( _diff_kb > 100 )) && [[ -z "${DISPATCH_TIMEOUT_ACTIVE:-}" ]]; then
    echo "note: diff is ${_diff_kb}KB — timeout raised to ${DISPATCH_TIMEOUT}s." >&2
    echo "  a diff this size also reviews poorly; consider splitting it by path or commit." >&2
  fi
fi

# Run log config is needed by BOTH sides of the re-exec: the inner process logs
# every ordinary outcome, the outer logs the timeout (a signalled death does not
# run the inner's EXIT trap). See the _log_run comment further down.
RUN_LOG="${REVIEW_WORK_LOG-${XDG_STATE_HOME:-$HOME/.local/state}/review-work/runs.jsonl}"
RUN_LOG_KEEP="${REVIEW_WORK_LOG_KEEP:-500}"

_emit_run_log() {  # agent tool model effort outcome exit duration output_file
  [[ -z "$RUN_LOG" ]] && return 0
  local out_bytes=0
  [[ -f "$8" ]] && out_bytes="$(wc -c < "$8" 2>/dev/null | tr -d ' ')"
  {
    mkdir -p "$(dirname "$RUN_LOG")" 2>/dev/null &&
    TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" A="$1" T="$2" M="$3" E="$4" \
    O="$5" C="$6" D="$7" F="$8" B="$out_bytes" \
    python3 -c 'import json,os,sys
sys.stdout.write(json.dumps({
    "ts": os.environ["TS"], "agent": os.environ["A"], "tool": os.environ["T"],
    "model": os.environ["M"] or None, "effort": os.environ["E"] or None,
    "outcome": os.environ["O"], "exit": int(os.environ["C"]),
    "duration_s": int(os.environ["D"]), "output_bytes": int(os.environ["B"]),
    "output_file": os.environ["F"],
}) + "\n")' >> "$RUN_LOG" &&
    if [[ "$RUN_LOG_KEEP" -gt 0 ]]; then
      tail -n "$RUN_LOG_KEEP" "$RUN_LOG" > "$RUN_LOG.tmp" 2>/dev/null &&
        mv "$RUN_LOG.tmp" "$RUN_LOG"
    fi
  } >/dev/null 2>&1 || true
  return 0
}

if [[ -z "${DISPATCH_TIMEOUT_ACTIVE:-}" && "$DISPATCH_TIMEOUT" != "0" ]] \
   && command -v timeout >/dev/null 2>&1; then
  export DISPATCH_TIMEOUT_ACTIVE=1
  _t0=$SECONDS
  set +e
  # NOT --foreground, and -k is load-bearing. Without --foreground the child
  # gets its own process group, so the backend CLI dies with the shell instead
  # of being orphaned and left billing. -k escalates to KILL if it ignores TERM.
  # Do NOT add a TERM trap in the inner process: bash defers traps until the
  # running foreground command returns, so a trapped TERM makes `timeout` wait
  # for the very backend it is trying to bound — measured, a 3s timeout took
  # 30s to fire with a trap and 3s without.
  timeout -k 10 "$DISPATCH_TIMEOUT" "$0" "$@"
  _status=$?
  set -e
  if [[ $_status -eq 124 ]]; then
    echo "error: backend produced no result within ${DISPATCH_TIMEOUT}s and was killed" >&2
    echo "  raise it with --timeout=N, or disable with --timeout=0" >&2
    # The inner process was signalled, so it logged nothing. Recover the agent
    # id and output path from argv: positionals follow the leading options.
    # _pos/_tool already populated by _scan_positionals above.
    _a=""; _o=""; _m=""
    [[ ${#_pos[@]} -ge 1 ]] && _a="${_pos[0]}"
    [[ ${#_pos[@]} -ge 4 ]] && _o="${_pos[3]}"
    [[ ${#_pos[@]} -ge 5 ]] && _m="${_pos[4]}"
    _emit_run_log "$_a" "$_tool" "$_m" "" "timeout" 124 "$((SECONDS - _t0))" "$_o"
  fi
  exit $_status
fi

TOOL="codex"
EFFORT_OVERRIDE=""
REPORT_USAGE=""

while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --tool=*)          TOOL="${1#*=}"; shift ;;
    --tool)            TOOL="$2"; shift 2 ;;
    --effort=*)        EFFORT_OVERRIDE="${1#*=}"; shift ;;
    --effort)          EFFORT_OVERRIDE="$2"; shift 2 ;;
    --report-usage=*)  REPORT_USAGE="${1#*=}"; shift ;;
    --report-usage)    REPORT_USAGE="$2"; shift 2 ;;
    --timeout=*)       shift ;;  # consumed by the re-exec guard above
    *)                 echo "error: unknown option: $1" >&2; exit 64 ;;
  esac
done


if [[ $# -lt 4 ]]; then
  echo "usage: $0 [--tool=codex|agy|claude|pi|or] [--effort=LEVEL] [--timeout=SECS] [--report-usage=FILE] <agent-id> <prompt-file> <diff-file> <output-file> [model] [effort]" >&2
  exit 64
fi

AGENT_ID="$1"
PROMPT_FILE="$2"
DIFF_FILE="$3"
OUTPUT_FILE="$4"
MODEL_OVERRIDE="${5:-}"
EFFORT_OVERRIDE="${6:-$EFFORT_OVERRIDE}"

# Set by each backend so the usage ledger can record what actually ran. Declared
# here, before the first thing that can exit, so the run-log trap below can read
# them no matter how early the failure is.
RESOLVED_MODEL=""
RESOLVED_EFFORT=""
TELEMETRY_RAW=""

# ── Run log ────────────────────────────────────────────────────────────────
# Always on, and deliberately separate from --report-usage. The usage ledger
# only records runs that SUCCEEDED: `set -e` kills the script the moment a
# run_* returns non-zero, long before the ledger write at the bottom. A panel
# that dispatched four agents and lost two produced a two-line ledger and no
# other trace — which is why a quota-dead backend, a timeout, and a prompt that
# never arrived all had to be reconstructed afterwards from /tmp mtimes.
#
# The ledger answers "what did this cost". This answers "what did I run, and
# what happened to it" — failures included. Disable with REVIEW_WORK_LOG=.
_RUN_START=$SECONDS

_log_run() {
  local code="$1" outcome
  case "$code" in
    0)   outcome="ok" ;;
    64)  outcome="usage-error" ;;
    # 65 covers both "the backend wrote something we could not parse" and "the
    # backend wrote nothing at all", and those need opposite fixes: the first is
    # a salvage problem, the second is the model never finishing its loop.
    # Reporting both as parse-error sent one investigation into widening the
    # salvage while every failing run had an empty file. Split them.
    65)  if [[ -s "$OUTPUT_FILE" || -s "$OUTPUT_FILE.rejected" ]]; then
           outcome="parse-error"
         else
           outcome="empty-output"
         fi ;;
    66)  outcome="missing-input" ;;
    69)  outcome="invalid-output" ;;
    70)  outcome="backend-error" ;;
    78)  outcome="no-api-key" ;;
    124) outcome="timeout" ;;
    *)   outcome="error" ;;
  esac
  _emit_run_log "$AGENT_ID" "$TOOL" \
    "${RESOLVED_MODEL:-${MODEL_OVERRIDE:-}}" \
    "${RESOLVED_EFFORT:-${EFFORT_OVERRIDE:-}}" \
    "$outcome" "$code" "$((SECONDS - _RUN_START))" "$OUTPUT_FILE"
}

# EXIT only. A TERM trap here would defer until the running backend returns and
# silently defeat the timeout guard (measured: 3s timeout took 30s to fire), so
# the outer process logs the timeout case instead.
trap '_log_run $?' EXIT

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SKILL_DIR/schema.json"

for f in "$PROMPT_FILE" "$DIFF_FILE" "$SCHEMA_FILE"; do
  if [[ ! -f "$f" ]]; then
    echo "error: missing file: $f" >&2
    exit 66
  fi
done

mkdir -p "$(dirname "$OUTPUT_FILE")"
rm -f "$OUTPUT_FILE"

PROMPT_BODY="$(cat "$PROMPT_FILE")"

# Sandbox needs explicit access to any dir referenced via file paths.
PROMPT_DIR="$(dirname "$PROMPT_FILE")"
DIFF_DIR="$(dirname "$DIFF_FILE")"

# Set by each backend so the usage ledger can record what actually ran.
RESOLVED_MODEL=""
RESOLVED_EFFORT=""
TELEMETRY_RAW=""


run_codex() {
  local model="${MODEL_OVERRIDE:-gpt-6.1-sol}"
  local effort="${EFFORT_OVERRIDE:-high}"
  RESOLVED_MODEL="$model"
  RESOLVED_EFFORT="$effort"
  local add_dirs=(--add-dir /tmp)
  [[ "$PROMPT_DIR" != /tmp ]] && add_dirs+=(--add-dir "$PROMPT_DIR")
  [[ "$DIFF_DIR"   != /tmp ]] && add_dirs+=(--add-dir "$DIFF_DIR")

  # --json only when reporting: it replaces codex's human progress output with
  # a JSONL event stream, and turn.completed carries the token usage. -o and
  # --output-schema keep working alongside it.
  local json_args=()
  if [[ -n "$REPORT_USAGE" ]]; then
    TELEMETRY_RAW="$(mktemp)"
    json_args=(--json)
  fi

  # Build argv once; the redirect has to be written literally, since
  # ${VAR:+> file} expands to a plain argument rather than a redirection.
  local args=(exec
    --ephemeral
    --ignore-user-config
    --ignore-rules
    --skip-git-repo-check
    -C /tmp
    -s read-only
    ${add_dirs[@]+"${add_dirs[@]}"}
    ${json_args[@]+"${json_args[@]}"}
    -m "$model"
    -c model_reasoning_effort="$effort"

    --output-schema "$SCHEMA_FILE"
    -o "$OUTPUT_FILE"
    "$PROMPT_BODY")

  if [[ -n "$TELEMETRY_RAW" ]]; then
    cat "$DIFF_FILE" | codex "${args[@]}" > "$TELEMETRY_RAW"
  else
    cat "$DIFF_FILE" | codex "${args[@]}"
  fi
}

run_agy() {
  local model="${MODEL_OVERRIDE:-gemini-3.6-flash-high}"
  RESOLVED_EFFORT="$EFFORT_OVERRIDE"
  local add_dirs=(--add-dir /tmp)
  [[ "$PROMPT_DIR" != /tmp ]] && add_dirs+=(--add-dir "$PROMPT_DIR")
  [[ "$DIFF_DIR"   != /tmp ]] && add_dirs+=(--add-dir "$DIFF_DIR")

  # Effort is part of the agy model name, not a flag. Passing --effort next to a
  # suffixed slug is an error, and non-gemini slugs (claude-*, gpt-oss-*) reject
  # --effort outright — so resolve it into the slug and never pass the flag.
  if [[ -n "$EFFORT_OVERRIDE" && "$model" == gemini-* && ! "$model" =~ -(low|medium|high)$ ]]; then
    local effort="$EFFORT_OVERRIDE"
    case "$effort" in
      xhigh|max|ultra) effort="high" ;;   # agy tops out at high
    esac
    model="${model}-${effort}"
  fi
  RESOLVED_MODEL="$model"

  # agy ignores piped stdin, so the diff goes in by path and the agent reads it.
  local augmented_prompt
  augmented_prompt="$PROMPT_BODY

---
The unified diff under review is the file $DIFF_FILE. Read it first. You are in
the repository it applies to and may read any file in it — verify the change
against the surrounding code as instructed above. Return the result as JSON
matching the enforced schema — an INSTANCE of it, filled with your actual
findings, never the schema document itself."

  local raw_out
  raw_out="$(mktemp)"

  # agy reports invalid models/flags on stdout, so surface raw_out on failure —
  # and use `if !` rather than $? capture, which `set -e` would preempt.
  if ! agy --print "$augmented_prompt" \
    --model "$model" \
    --mode plan \
    --disable-slash-commands \
    --output-format json \
    --json-schema "$SCHEMA_FILE" \
    --print-timeout 15m \
    ${add_dirs[@]+"${add_dirs[@]}"} \
    > "$raw_out"; then
    echo "error: agy failed (agent=$AGENT_ID, model=$model):" >&2
    cat "$raw_out" >&2
    rm -f "$raw_out"
    return 70
  fi

  # Unwrap {conversation_id, status, response} -> bare schema object.
  if ! python3 - "$raw_out" "$OUTPUT_FILE" <<'PY'
import json, re, sys

raw, dest = sys.argv[1], sys.argv[2]
with open(raw) as f:
    payload = json.load(f)

body = payload.get("response", payload) if isinstance(payload, dict) else payload

if isinstance(body, str):
    try:
        body = json.loads(body)
    except ValueError:
        # Schema enforcement only binds agy's gemini-* models; the claude-*/
        # gpt-oss-* passthroughs answer in prose. Salvage embedded JSON, and
        # fail loudly rather than writing prose into a schema-typed file.
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.S)
        span = fenced.group(1) if fenced else None
        if span is None:
            start, end = body.find("{"), body.rfind("}")
            span = body[start:end + 1] if 0 <= start < end else None
        if span is None:
            raise SystemExit(
                "agy returned prose, not schema JSON — --json-schema is only "
                "enforced for gemini-* models on this backend"
            )
        body = json.loads(span)

with open(dest, "w") as f:
    json.dump(body, f)
PY
  then
    echo "error: could not unwrap agy response envelope; raw output kept at $raw_out" >&2
    return 65
  fi

  # The same envelope carries the usage block; keep it for the ledger.
  if [[ -n "$REPORT_USAGE" ]]; then
    TELEMETRY_RAW="$raw_out"
  else
    rm -f "$raw_out"
  fi
}

run_openrouter() {
  local model="${MODEL_OVERRIDE:-deepseek/deepseek-v4-pro}"
  RESOLVED_MODEL="$model"
  RESOLVED_EFFORT="$EFFORT_OVERRIDE"

  if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "error: OPENROUTER_API_KEY is not set (agent=$AGENT_ID)" >&2
    return 78
  fi

  # Plain OpenAI-compatible HTTP call — no agentic loop, no sandbox needed:
  # the diff is the whole context and we already have it on disk. Python owns
  # the request so the diff never has to survive shell quoting.
  local raw_out
  raw_out="$(mktemp)"

  if ! python3 - "$model" "$PROMPT_FILE" "$DIFF_FILE" "$SCHEMA_FILE" "$OUTPUT_FILE" "$raw_out" <<'PY'
import json, os, re, sys, urllib.error, urllib.request

model, prompt_f, diff_f, schema_f, dest, raw_dest = sys.argv[1:7]

prompt = open(prompt_f).read()
diff = open(diff_f).read()
schema = json.load(open(schema_f))

body = {
    "model": model,
    "messages": [
        {"role": "system",
         "content": "You are a code reviewer. Reply with a single JSON object "
                    "matching the required schema. No prose, no code fences.\n"
                    "Return an INSTANCE of that schema, filled with your actual "
                    "findings — never the schema document itself.\n"
                    "You have NO tools and NO repository access in this run: the "
                    "diff below is everything you can see. Ignore any instruction "
                    "to grep or open files, and never claim to have checked "
                    "something outside the diff."},
        {"role": "user",
         "content": f"{prompt}\n\n## Required JSON schema\n\n"
                    f"{json.dumps(schema)}\n\n## Unified diff under review\n\n"
                    f"```diff\n{diff}\n```"},
    ],
    # Structured outputs where the provider supports it; the schema also rides
    # in the prompt above so unsupported models still have the contract.
    "response_format": {
        "type": "json_schema",
        "json_schema": {"name": "review", "strict": True, "schema": schema},
    },
    # Ask OpenRouter to bill-report the call so the ledger gets a real cost.
    "usage": {"include": True},
}

# Privacy floor for proprietary code. Unconstrained, one model can route to
# 30+ providers of wildly varying policy. Verified behaviour:
#   zdr=true               -> only endpoints that retain nothing
#   data_collection="deny" -> excludes providers that store or train on inputs
# If nothing satisfies the policy the request HARD-ERRORS ("No allowed
# providers are available") rather than silently falling back — that failure
# mode is the point, so never relax this to make a run succeed.
provider_prefs = {"zdr": True, "data_collection": "deny"}

# Route to the CHEAPEST compliant provider. Measured on glm-5.2 across the ZDR
# pool (400 output tokens each):
#   sort=price      -> Novita    43.8 tok/s  $0.00075
#   sort=latency    -> CoreWeave 50.5 tok/s  $0.00099
#   sort=throughput -> BaseTen   89.7 tok/s  $0.00270
# Speed costs ~3.6x for ~2x the tokens/sec. Reviews run in parallel in the
# background, so the wall-clock win rarely justifies it — set
# OPENROUTER_SORT=throughput per-run if you are genuinely waiting.
provider_prefs["sort"] = os.environ.get("OPENROUTER_SORT", "price")

# Guard rail so "fastest" can never become "outrageous": cap the completion
# price ($/M tokens). Routing picks the fastest endpoint UNDER the cap, and
# hard-errors if none qualifies rather than silently overspending.
#
# The cap is derived from the model's own price distribution rather than being
# a fixed number, because "expensive" is model-relative — $15/M is an outlier
# for GLM-5.2 and the going rate for Kimi K3. Taking the MEDIAN across the
# model's endpoints and allowing a multiple of it means a single new
# ultra-priced provider can never win the route, however fast it is, and the
# ceiling tracks the market as prices drift.
max_out = os.environ.get("OPENROUTER_MAX_OUT_PRICE", "").strip()
if max_out:
    provider_prefs["max_price"] = {"completion": float(max_out)}
else:
    try:
        with urllib.request.urlopen(
            f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=20
        ) as r:
            eps = json.load(r)["data"].get("endpoints", [])
        prices = sorted(
            p for p in (
                float((e.get("pricing") or {}).get("completion") or 0) * 1e6
                for e in eps
            ) if p > 0
        )
        if prices:
            mid = len(prices) // 2
            median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
            mult = float(os.environ.get("OPENROUTER_PRICE_MULT", "1.5"))
            cap = round(median * mult, 4)
            provider_prefs["max_price"] = {"completion": cap}
            print(f"openrouter: price ceiling ${cap}/M out "
                  f"(median ${median:.2f} x {mult})", file=sys.stderr)
    except Exception as exc:
        # Never fail a review over a metadata fetch, but say so loudly: this
        # run is going out uncapped.
        print(f"openrouter: WARNING could not derive price ceiling ({exc}); "
              f"routing uncapped", file=sys.stderr)

# ZDR is not data residency: a compliant provider may still sit in another
# jurisdiction. Pin an allowlist when that matters, e.g.
#   OPENROUTER_ONLY="Fireworks,Together,DeepInfra,BaseTen,CoreWeave"
only = os.environ.get("OPENROUTER_ONLY", "").strip()
if only:
    provider_prefs["only"] = [p.strip() for p in only.split(",") if p.strip()]

body["provider"] = provider_prefs

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(body).encode(),
    headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        "X-Title": "hawk-hooks review-work",
    },
)

try:
    with urllib.request.urlopen(req, timeout=900) as r:
        payload = json.load(r)
except urllib.error.HTTPError as e:
    sys.exit(f"openrouter HTTP {e.code}: {e.read().decode()[:400]}")

with open(raw_dest, "w") as f:
    json.dump(payload, f)

served_by = payload.get("provider")
if served_by:
    print(f"openrouter: served by {served_by} (zdr, no-training)", file=sys.stderr)

if payload.get("error"):
    sys.exit(f"openrouter error: {json.dumps(payload['error'])[:400]}")

choice = payload["choices"][0]
message = choice.get("message", {})
# Some models (notably reasoning-style ones) return content: null and put the
# text in `reasoning`; a truncated response leaves both empty.
content = message.get("content") or message.get("reasoning") or ""
if not content.strip():
    sys.exit(f"empty content from {model} "
             f"(finish_reason={choice.get('finish_reason')!r}) — "
             f"model may not support response_format json_schema")

try:
    obj = json.loads(content)
except ValueError:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    span = fenced.group(1) if fenced else None
    if span is None:
        start, end = content.find("{"), content.rfind("}")
        span = content[start:end + 1] if 0 <= start < end else None
    if span is None:
        sys.exit(f"model returned non-JSON content: {content[:300]}")
    obj = json.loads(span)

with open(dest, "w") as f:
    json.dump(obj, f)
PY
  then
    echo "error: openrouter failed (agent=$AGENT_ID, model=$model)" >&2
    rm -f "$raw_out"
    return 70
  fi

  if [[ -n "$REPORT_USAGE" ]]; then
    TELEMETRY_RAW="$raw_out"
  else
    rm -f "$raw_out"
  fi
}

run_pi() {
  # pi is a lightweight harness (read/bash/edit/write/grep/find/ls) that speaks
  # 15+ providers including OpenRouter. It gives OpenRouter models real agentic
  # exploration at a fraction of codex's harness overhead — measured on the same
  # review: pi 17.7k tokens vs codex-as-harness 424k, same model.
  local model="${MODEL_OVERRIDE:-z-ai/glm-5.2}"
  local provider="${PI_PROVIDER:-openrouter}"

  if [[ "$provider" == "openrouter" && -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "error: OPENROUTER_API_KEY is not set (agent=$AGENT_ID)" >&2
    return 78
  fi

  # pi builds its own request body and exposes no hook to inject OpenRouter's
  # provider-routing block (models.json supports headers, not body params), so
  # the per-request privacy floor used by run_openrouter cannot reach it.
  #
  # This is covered at the ACCOUNT level instead: Privacy -> Zero Data Retention
  # -> "Non-frontier" forces every non-frontier model request onto a ZDR
  # endpoint server-side, whatever the client. Verified deterministically —
  # qwen3.8-max (which has no ZDR endpoint anywhere) is rejected with
  # "No endpoints available matching your guardrail restrictions and data
  # policy" on a request carrying no provider block at all.
  #
  # OPENROUTER_PRESET remains supported for scoping the policy to review runs
  # instead of the whole account: create one at openrouter.ai/settings/presets
  # and its slug is appended as "<model>@preset/<slug>".
  if [[ "$provider" == "openrouter" && -n "${OPENROUTER_PRESET:-}" ]]; then
    model="${model}@preset/${OPENROUTER_PRESET}"
  fi

  RESOLVED_MODEL="$model"
  RESOLVED_EFFORT="$EFFORT_OVERRIDE"

  local raw_out clean_cfg
  raw_out="$(mktemp)"
  # Ephemeral config dir = pi's equivalent of --ignore-user-config: no user
  # settings and, critically, no user extensions. A single broken extension in
  # ~/.pi/agent otherwise aborts the run before the model is ever called.
  clean_cfg="$(mktemp -d)"

  # Copy ONLY the model catalog across. The ephemeral dir exists to drop user
  # extensions, but it drops pi's model catalog with them — and without it every
  # OpenRouter slug pi does not bundle resolves as an unknown "custom model id"
  # with NO context length and NO max-output metadata:
  #
  #   Warning: Model "deepseek/deepseek-v4-flash-0731" not found for provider
  #   "openrouter". Using custom model id.
  #
  # The tell is that `pi --list-models` knows the model perfectly well (1M ctx,
  # 65.5K max out) while the dispatched run does not — because --list-models
  # reads ~/.pi/agent and the run reads an empty temp dir. A model whose output
  # ceiling pi cannot see is a plausible source of the truncated replies behind
  # the observed parse-errors. Two JSON files, no extensions, isolation intact.
  local _cat
  for _cat in models.json models-store.json; do
    if [[ -f "$HOME/.pi/agent/$_cat" ]]; then
      cp "$HOME/.pi/agent/$_cat" "$clean_cfg/" 2>/dev/null || true
    fi
  done

  # Read-only tool allowlist: no bash, no edit, no write. A reviewer needs to
  # look around, never to change anything.
  #
  # message_update events are dropped on the way to disk. pi re-sends the WHOLE
  # accumulated message inside every token delta, so raw output grows O(n²) with
  # reasoning length: measured on a 37KB diff with glm-5.2 (a heavy thinker),
  # 5.5MB at 45s, 51MB at 105s, 67MB at 150s and still streaming — per-event
  # size climbing 164B to 40KB. From the caller it looks like a silent hang,
  # because pi's stdout goes to a temp file. Nothing downstream reads these
  # events: both the answer and the usage/cost block come from message_end.
  if ! PI_OFFLINE=1 PI_CODING_AGENT_DIR="$clean_cfg" pi --print \
    --provider "$provider" \
    --model "$model" \
    --no-session \
    --tools read,grep,find,ls \
    --mode json \
    "$PROMPT_BODY

---
The unified diff under review is the file $DIFF_FILE. Read it first. You are in
the repository it applies to and have read/grep/find/ls tools — verify the change
against the surrounding code as instructed above. Return ONLY a JSON object
matching this schema — an INSTANCE of it, filled with your actual findings,
never the schema document below copied back:

$(cat "$SCHEMA_FILE")" < /dev/null \
       | { grep -v '"type":"message_update"' || true; } > "$raw_out"; then
    echo "error: pi failed (agent=$AGENT_ID, provider=$provider, model=$model)" >&2
    rm -f "$raw_out"; rm -rf "$clean_cfg"
    return 70
  fi

  # pi --mode json emits a JSONL event stream. The answer normally lands in the
  # last assistant message_end as a "text" content part, but reasoning-heavy
  # models sometimes leave it only in "thinking", and a long run can end without
  # a clean final message at all. Salvage widens outward through those cases
  # rather than failing on the first one — every pi parse-error observed so far
  # was a well-formed object the narrow extractor could not reach.
  if ! python3 - "$raw_out" "$OUTPUT_FILE" <<'PY'
import json, sys

raw, dest = sys.argv[1], sys.argv[2]
REQUIRED = {"agent", "scope", "status", "findings", "summary"}


def balanced_objects(s):
    """Yield every balanced {...} span, string-aware so braces in text do not
    break nesting. find('{')..rfind('}') gets this wrong whenever the model
    writes prose around the object or emits more than one."""
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    yield s[start:i + 1]


def looks_like_schema(obj):
    """A model that answers with the CONTRACT instead of a review:
    {"type":"object","properties":{...},"$schema":...}. It parses, it is
    well-formed, and it contains no review — never prefer it over a real one."""
    return "$schema" in obj or (obj.get("type") == "object" and "properties" in obj)


def extract(text):
    """Best schema-shaped object in a blob, else any parseable object that is
    not the schema echoed back."""
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and (REQUIRED.issubset(obj)
                                      or not looks_like_schema(obj)):
            return obj
    except ValueError:
        pass
    best = None
    for span in balanced_objects(text):
        try:
            obj = json.loads(span)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if REQUIRED.issubset(obj):   # prefer a real review object
            best = obj
        elif best is None and not looks_like_schema(obj):
            best = obj
    return best


# Collect candidate blobs, most-authoritative last.
texts, thinks = [], []
for line in open(raw, errors="replace"):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") != "message_end":
        continue
    msg = ev.get("message") or {}
    if msg.get("role") != "assistant":
        continue
    for part in msg.get("content") or []:
        kind = part.get("type")
        if kind == "text":
            texts.append(part.get("text", ""))
        elif kind == "thinking":
            thinks.append(part.get("thinking") or part.get("text") or "")

obj = None
for blob in (list(reversed(texts))          # last text part wins
             + ["\n".join(texts)]          # then all text concatenated
             + list(reversed(thinks))):     # then reasoning, as a last resort
    obj = extract(blob)
    if obj:
        break

if obj is None:
    where = f"{len(texts)} text / {len(thinks)} thinking part(s)"
    sample = (texts[-1] if texts else (thinks[-1] if thinks else ""))[:300]
    sys.exit(f"pi output had no parseable JSON object ({where}); tail: {sample!r}")

with open(dest, "w") as f:
    json.dump(obj, f)
PY
  then
    echo "error: could not parse pi output; raw kept at $raw_out" >&2
    rm -rf "$clean_cfg"
    return 65
  fi

  rm -rf "$clean_cfg"

  if [[ -n "$REPORT_USAGE" ]]; then
    TELEMETRY_RAW="$raw_out"
  else
    rm -f "$raw_out"
  fi
}

run_claude() {
  local model="${MODEL_OVERRIDE:-sonnet}"
  local effort="${EFFORT_OVERRIDE:-high}"
  RESOLVED_MODEL="$model"
  RESOLVED_EFFORT="$effort"
  local add_dirs=(--add-dir /tmp)
  [[ "$PROMPT_DIR" != /tmp ]] && add_dirs+=(--add-dir "$PROMPT_DIR")
  [[ "$DIFF_DIR"   != /tmp ]] && add_dirs+=(--add-dir "$DIFF_DIR")

  local raw_out
  raw_out="$(mktemp)"

  # Not using --bare: it disables keychain/OAuth, requiring ANTHROPIC_API_KEY.
  # Softer profile that keeps auth working but kills MCP, session persistence,
  # and slash commands. CLAUDE.md may still be loaded (acceptable — claude
  # hallucination risk is lower than codex's MCP-injection issue).
  #
  # NOT using --json-schema, deliberately. It does not constrain the first turn;
  # it appends a second synthetic user turn reading "[structured-output-enforce]
  # You MUST call the StructuredOutput tool to complete this request." The model
  # then answers *that message in isolation* and reports there is no task —
  # verified on the wire, where turn 1 answered the prompt correctly and turn 2
  # replied "your message doesn't provide any task". Sonnet goes further and
  # refuses outright, objecting that the bracketed prefix "isn't a real system
  # contract" and that emitting findings would be fabricating them. The result
  # is a well-formed schema object whose summary says the review never happened.
  # Asking for the schema in the prompt body — the same contract run_pi and
  # run_openrouter use — keeps everything in the turn that has the diff.
  # Read-only comes from the tool allowlist, NOT --permission-mode plan. Plan
  # mode makes the CLI treat the run as "produce a plan and call ExitPlanMode",
  # so the model answers "since plan mode is active, I need a concrete task to
  # plan" and never reviews. An allowlist of Read/Grep/Glob is the same
  # guarantee pi gets from --tools read,grep,find,ls: look, never write.
  #
  # NEVER put the prompt in a trailing positional argument here. `--add-dir` is
  # VARIADIC (--add-dir <paths...>): it swallows every following non-option
  # argument, so `--add-dir /tmp "$PROMPT_BODY"` registers the entire prompt as
  # a directory path and the model never sees it. Reproduce with:
  #   claude -p --model haiku --add-dir /tmp "say MARKER"
  #   -> Error: Input must be provided either through stdin or as a prompt
  #      argument when using --print
  #
  # That error only appears when stdin is empty. Piping the diff in hid it for
  # months: the CLI saw input, the task text was gone, and the model — handed a
  # diff plus a review-shaped schema — simply inferred the task and reviewed it.
  # The output had correct scope, severities and messages, so nothing looked
  # wrong. Verified 2026-08-05: a marker token planted in the prompt never
  # reaches the model, yet the review still comes back well-formed and correct.
  # The 12:56 "No explicit task was provided alongside the diff" run was not a
  # regression — it was the same broken call, on a turn where the model declined
  # to improvise instead of covering for it.
  #
  # So: the whole task arrives on stdin as one message, the diff goes by PATH,
  # and no positional argument follows the flags — the contract run_agy and
  # run_pi already use.
  if ! printf '%s\n\n---\nThe unified diff under review is the file %s. Read it first.\nYou are in the repository it applies to and have Read/Grep/Glob — verify the\nchange against the surrounding code as instructed above.\n\nReturn ONLY a JSON object matching this schema — an INSTANCE of it, filled with\nyour actual findings, never the schema document below copied back. No prose, no\ncode fence:\n\n%s\n' \
       "$PROMPT_BODY" "$DIFF_FILE" "$(cat "$SCHEMA_FILE")" | claude \
    --print \
    --no-session-persistence \
    --allowed-tools Read Grep Glob \
    --disallowed-tools Bash Edit Write NotebookEdit \
    --strict-mcp-config \
    --disable-slash-commands \
    --model "$model" \
    --effort "$effort" \
    --output-format json \
    ${add_dirs[@]+"${add_dirs[@]}"} \
    > "$raw_out"; then
    echo "error: claude failed (agent=$AGENT_ID, model=$model)" >&2
    rm -f "$raw_out"
    return 70
  fi

  # claude --output-format json returns a run envelope, not the schema object:
  # {type, subtype, result, structured_output, usage, total_cost_usd, ...}.
  # Unwrap it so every backend writes the same bare object to OUTPUT_FILE.
  # Without --json-schema, structured_output is absent and `result` is the
  # model's text, so salvage it the same way run_pi does.
  if ! python3 - "$raw_out" "$OUTPUT_FILE" <<'PY'
import json, re, sys
raw, dest = sys.argv[1], sys.argv[2]
with open(raw) as f:
    payload = json.load(f)
body = payload.get("structured_output")
if body is None:
    body = payload.get("result", payload)
if isinstance(body, str):
    text = body
    try:
        body = json.loads(text)
    except ValueError:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        span = fenced.group(1) if fenced else None
        if span is None:
            start, end = text.find("{"), text.rfind("}")
            span = text[start:end + 1] if 0 <= start < end else None
        if span is None:
            sys.exit(f"claude returned non-JSON content: {text[:300]}")
        body = json.loads(span)
with open(dest, "w") as f:
    json.dump(body, f)
PY
  then
    echo "error: could not unwrap claude envelope; raw output kept at $raw_out" >&2
    return 65
  fi

  if [[ -n "$REPORT_USAGE" ]]; then
    TELEMETRY_RAW="$raw_out"
  else
    rm -f "$raw_out"
  fi
}

case "$TOOL" in
  codex)      run_codex ;;
  agy)        run_agy ;;
  claude)     run_claude ;;
  openrouter|or) TOOL="openrouter"; run_openrouter ;;
  pi)         run_pi ;;
  gemini) echo "error: the gemini backend is gone — Gemini CLI was replaced by Antigravity CLI; use --tool=agy" >&2; exit 64 ;;
  *)          echo "error: unknown --tool: $TOOL (expected codex|agy|claude|pi|or)" >&2; exit 64 ;;
esac

if [[ ! -s "$OUTPUT_FILE" ]]; then
  echo "error: $TOOL produced no output at $OUTPUT_FILE (agent=$AGENT_ID)" >&2
  exit 70
fi

# Schema enforcement is not universal: codex's --output-schema binds OpenAI
# models but NOT models served through the OpenRouter provider, which answer in
# prose with the JSON fenced inside. Salvage those in place; a file that already
# parses is left untouched.
python3 - "$OUTPUT_FILE" <<'PY' || echo "warning: $OUTPUT_FILE is not valid JSON and could not be salvaged (agent=$AGENT_ID, tool=$TOOL)" >&2
import json, re, sys

path = sys.argv[1]
text = open(path).read()

try:
    json.loads(text)
    sys.exit(0)          # already clean
except ValueError:
    pass

fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
span = fenced.group(1) if fenced else None
if span is None:
    start, end = text.find("{"), text.rfind("}")
    span = text[start:end + 1] if 0 <= start < end else None
if span is None:
    sys.exit(1)

obj = json.loads(span)   # raises -> exit non-zero -> warning above
with open(path, "w") as f:
    json.dump(obj, f)
PY

# Usage ledger: one normalized JSONL record per agent run. Each backend reports
# different field names (and only claude reports a dollar cost), so normalize to
# a shared shape. Never fatal — a broken ledger must not fail a good review.
if [[ -n "$REPORT_USAGE" && -n "$TELEMETRY_RAW" && -s "$TELEMETRY_RAW" ]]; then
  python3 - "$TOOL" "$AGENT_ID" "$RESOLVED_MODEL" "$RESOLVED_EFFORT" \
           "$TELEMETRY_RAW" "$REPORT_USAGE" <<'PY' || echo "warning: usage ledger write failed (agent=$AGENT_ID)" >&2
import json, sys

tool, agent, model, effort, raw, dest = sys.argv[1:7]

# cost_basis says which budget pool this run drew from, because a dollar figure
# alone is misleading across backends:
#   metered      real cash, billed per token          (openrouter)
#   subscription plan quota; cost_usd is the API-equivalent estimate the CLI
#                reports, NOT an amount charged                 (subscription-based Claude account)
#   allowance    subscription or prepaid account credit pool          (codex, agy)
COST_BASIS = {"openrouter": "metered",
              "claude": "account-dependent", "codex": "account-dependent", "agy": "account-dependent",
              "pi": "metered"}

rec = {"tool": tool, "agent": agent, "model": model, "effort": effort or None,
       "cost_basis": COST_BASIS.get(tool, "unknown"),
       "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
       "reasoning_tokens": 0, "total_tokens": None, "cost_usd": None}

if tool == "codex":
    # JSONL event stream; the last turn.completed holds the turn's usage.
    usage = {}
    with open(raw) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "turn.completed" and ev.get("usage"):
                usage = ev["usage"]
    rec["input_tokens"] = usage.get("input_tokens", 0)
    rec["cached_input_tokens"] = usage.get("cached_input_tokens", 0)
    rec["output_tokens"] = usage.get("output_tokens", 0)
    rec["reasoning_tokens"] = usage.get("reasoning_output_tokens", 0)
elif tool == "pi":
    # JSONL too; the last assistant message_end carries usage AND a real cost
    # breakdown (pi is the only backend that reports both).
    usage = {}
    with open(raw) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "message_end":
                u = (ev.get("message") or {}).get("usage")
                if u:
                    usage = u
    rec["input_tokens"] = usage.get("input", 0)
    rec["cached_input_tokens"] = usage.get("cacheRead", 0)
    rec["output_tokens"] = usage.get("output", 0)
    rec["total_tokens"] = usage.get("totalTokens")
    rec["cost_usd"] = (usage.get("cost") or {}).get("total")
else:
    with open(raw) as f:
        payload = json.load(f)
    usage = payload.get("usage", {}) or {}
    if tool == "agy":
        rec["input_tokens"] = usage.get("input_tokens", 0)
        rec["cached_input_tokens"] = usage.get("cache_read_tokens", 0)
        rec["output_tokens"] = usage.get("output_tokens", 0)
        rec["reasoning_tokens"] = usage.get("thinking_tokens", 0)
        rec["total_tokens"] = usage.get("total_tokens")
    elif tool == "claude":
        rec["input_tokens"] = usage.get("input_tokens", 0)
        rec["cached_input_tokens"] = usage.get("cache_read_input_tokens", 0)
        rec["output_tokens"] = usage.get("output_tokens", 0)
        rec["cost_usd"] = payload.get("total_cost_usd")
    elif tool == "openrouter":
        details = usage.get("prompt_tokens_details") or {}
        rec["input_tokens"] = usage.get("prompt_tokens", 0)
        rec["cached_input_tokens"] = details.get("cached_tokens", 0)
        rec["output_tokens"] = usage.get("completion_tokens", 0)
        rec["total_tokens"] = usage.get("total_tokens")
        rec["cost_usd"] = usage.get("cost")

if rec["total_tokens"] is None:
    rec["total_tokens"] = (rec["input_tokens"] + rec["cached_input_tokens"]
                           + rec["output_tokens"])

with open(dest, "a") as f:
    f.write(json.dumps(rec) + "\n")
PY
fi

if [[ -n "$TELEMETRY_RAW" ]]; then
  rm -f "$TELEMETRY_RAW"
fi

# ── Did this slot actually review? ─────────────────────────────────────────
# Everything above only ever asked "did bytes arrive". They did, in the failure
# this gate exists for: on 2026-08-11 a /revxflash DeepSeek V4 Flash slot
# returned the JSON SCHEMA back — {"type":"object","properties":{...},"$schema":
# ...} with `status` and `agent` pasted inside `properties` — 327 well-formed
# bytes, no findings anywhere, logged `ok`. A panel that counts that as a
# finding-free pass turns three opinions into four, which is the one thing panel
# mode exists not to do.
#
# So the last word is a shape check, not a parse check. It runs AFTER the usage
# ledger deliberately: the run cost real tokens whether or not it produced a
# review, and the ledger should say so.
#
# A rejected output is MOVED to <output>.rejected rather than left in place, so
# the Step 4 contract holds unchanged — no file at the dispatched path means
# that slot did not run — while the evidence survives for debugging.
if ! _invalid="$(python3 - "$OUTPUT_FILE" 2>&1 <<'PY'
import json, sys

REQUIRED = ("agent", "scope", "status", "findings", "summary")

try:
    obj = json.load(open(sys.argv[1]))
except ValueError as exc:
    sys.exit(f"not valid JSON ({exc})")

if not isinstance(obj, dict):
    sys.exit(f"top level is a {type(obj).__name__}, not an object")

missing = [k for k in REQUIRED if k not in obj]
if missing:
    # Distinguish the schema echo from a merely incomplete review: it is a
    # different bug with a different fix (prompt wording, not model capability).
    if "$schema" in obj or (obj.get("type") == "object" and "properties" in obj):
        sys.exit("the model returned the JSON Schema itself instead of a review")
    sys.exit(f"missing required key(s): {', '.join(missing)}")

if obj["status"] not in ("pass", "warn", "fail"):
    sys.exit(f"status is {obj['status']!r}, expected pass|warn|fail")
for key in ("scope", "findings"):
    if not isinstance(obj[key], list):
        sys.exit(f"{key} is a {type(obj[key]).__name__}, not an array")
for i, f in enumerate(obj["findings"]):
    if not isinstance(f, dict):
        sys.exit(f"findings[{i}] is a {type(f).__name__}, not an object")

# No findings AND nothing said about why. A genuine clean pass still writes a
# summary; this shape is an agent that produced nothing at all.
if not obj["findings"] and not str(obj.get("summary") or "").strip():
    sys.exit("no findings and an empty summary — the agent returned nothing")
PY
)"; then
  mv -f "$OUTPUT_FILE" "$OUTPUT_FILE.rejected" 2>/dev/null || true
  echo "error: $TOOL produced no usable review (agent=$AGENT_ID, model=${RESOLVED_MODEL:-?})" >&2
  echo "  $_invalid" >&2
  echo "  rejected output kept at $OUTPUT_FILE.rejected — this slot did NOT review" >&2
  exit 69
fi
