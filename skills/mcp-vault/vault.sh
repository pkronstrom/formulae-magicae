#!/usr/bin/env bash
# MCP vault — a directory of MCP server configs kept out of the active tool
# namespace until needed. Wraps `mcpc`; adds descriptions, a cold tool cache,
# and credential-state reporting.
set -euo pipefail

VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVERS="$VAULT_DIR/servers.json"
META_DIR="$VAULT_DIR/meta"
ENV_FILE="$VAULT_DIR/.env"

usage() {
  cat <<EOF
Usage: vault.sh <command> [args]

Commands:
  list                            Every server: description, cold/warm, tools (default)
  show <name>                     Full description and cached tool list for one server
  add <url> [name] [--token T]    Vault a server; --token sets bearer auth immediately
  describe <name> <text>          Set a server's description
  inspect <url>                   Probe a server NOT in the vault; persists nothing
  warm <name> [--token]           One-time auth: OAuth login, or capture a bearer token
  use <name>                      Connect (idempotent) and refresh the cached tool list
  forget <name>                   Remove the entry, its metadata, and its .env line

After 'use', talk to mcpc directly:  mcpc @<name> tools-call <tool> arg:=value
EOF
}

die() { echo "error: $*" >&2; exit 1; }

require_mcpc() {
  command -v mcpc >/dev/null 2>&1 || die "mcpc is not installed. Install it with:
  npm install -g @apify/mcpc"
}

# Load vault secrets so mcpc can expand \${VAR} references in servers.json.
load_env() {
  [[ -f "$ENV_FILE" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

ensure_layout() {
  mkdir -p "$META_DIR"
  [[ -f "$SERVERS" ]] || printf '{\n  "mcpServers": {}\n}\n' > "$SERVERS"
}

# ── JSON helpers (python3: always present on macOS, unlike jq) ───────────────

# Read one field out of a server's metadata file.
meta_get() {
  local name="$1" field="$2"
  local f="$META_DIR/$name.json"
  [[ -f "$f" ]] || return 1
  python3 -c '
import json,sys
try:
    d = json.load(open(sys.argv[1]))
except (json.JSONDecodeError, OSError):
    sys.exit(1)
v = d.get(sys.argv[2], "")
print(v if not isinstance(v, (list, dict)) else json.dumps(v))
' "$f" "$field" 2>/dev/null
}

server_url() {
  python3 -c '
import json,sys
d = json.load(open(sys.argv[1]))
e = d.get("mcpServers", {}).get(sys.argv[2])
print("" if e is None else e.get("url", ""))
' "$SERVERS" "$1"
}

server_exists() {
  python3 -c '
import json,sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if sys.argv[2] in d.get("mcpServers", {}) else 1)
' "$SERVERS" "$1" 2>/dev/null
}

server_names() {
  python3 -c '
import json,sys
d = json.load(open(sys.argv[1]))
for k in d.get("mcpServers", {}):
    print(k)
' "$SERVERS" 2>/dev/null
}

require_server() {
  server_exists "$1" && return 0
  local available
  available="$(server_names | paste -sd, - | sed 's/,/, /g')"
  die "no vaulted server named '$1'. Available: ${available:-<none>}"
}

# mcpc's session auto-naming: main domain label, ignoring a leading "mcp.".
derive_name() {
  python3 -c '
import re,sys
from urllib.parse import urlparse
host = (urlparse(sys.argv[1]).hostname or sys.argv[1])
host = re.sub(r"^mcp\.", "", host)
labels = [l for l in host.split(".") if l]
print(re.sub(r"[^a-zA-Z0-9_-]", "-", labels[0]) if labels else "server")
' "$1"
}

# ── credential state ────────────────────────────────────────────────────────

# Does mcpc hold a saved OAuth profile for this server's URL?
has_oauth_profile() {
  local url="$1"
  command -v mcpc >/dev/null 2>&1 || return 1
  mcpc --json 2>/dev/null | python3 -c '
import json,sys
from urllib.parse import urlparse
want = urlparse(sys.argv[1]).hostname or ""
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
for p in d.get("profiles", []):
    if (urlparse(p.get("serverUrl", "")).hostname or "") == want:
        sys.exit(0)
sys.exit(1)
' "$url" 2>/dev/null
}

env_var_set() {
  local var="$1"
  [[ -n "${!var:-}" ]] && return 0
  [[ -f "$ENV_FILE" ]] && grep -qE "^[[:space:]]*(export[[:space:]]+)?${var}=.+" "$ENV_FILE"
}

# Prints "warm" or "cold" — computed, never stored, so it cannot go stale.
cred_state() {
  local name="$1" auth
  auth="$(meta_get "$name" auth || echo none)"
  case "$auth" in
    token)
      local var
      var="$(meta_get "$name" token_env || echo "")"
      [[ -n "$var" ]] && env_var_set "$var" && echo warm || echo cold
      ;;
    oauth)
      has_oauth_profile "$(server_url "$name")" && echo warm || echo cold
      ;;
    *) echo warm ;;
  esac
}

# ── metadata writes ─────────────────────────────────────────────────────────

write_meta() {
  # write_meta <name> <auth> <token_env> <description>
  local name="$1" auth="$2" token_env="$3" desc="$4"
  python3 -c '
import json,os,sys
path, name, auth, token_env, desc = sys.argv[1:6]
d = {}
if os.path.exists(path):
    try:
        d = json.load(open(path))
    except json.JSONDecodeError:
        d = {}
d["name"] = name
d["auth"] = auth
if auth == "token":
    d["token_env"] = token_env
else:
    d.pop("token_env", None)
if desc:
    d["description"] = desc
d.setdefault("description", "")
d.setdefault("tools", [])
json.dump(d, open(path, "w"), indent=2)
open(path, "a").write("\n")
' "$META_DIR/$name.json" "$name" "$auth" "$token_env" "$desc"
}

# Snapshot a live session's tool list into the server's metadata.
snapshot_tools() {
  local name="$1"
  local out
  if ! out="$(mcpc "@$name" tools-list --json 2>/dev/null)"; then
    echo "  (could not list tools — cache left unchanged)" >&2
    return 1
  fi
  printf '%s' "$out" | python3 -c '
import json,sys,datetime
path = sys.argv[1]
try:
    raw = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
tools = raw.get("tools", raw) if isinstance(raw, dict) else raw
if not isinstance(tools, list):
    sys.exit(1)
d = json.load(open(path))
d["tools"] = [
    {"name": t.get("name", ""), "description": (t.get("description") or "").strip()}
    for t in tools if isinstance(t, dict)
]
d["last_used"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(d, open(path, "w"), indent=2)
open(path, "a").write("\n")
print(len(d["tools"]))
' "$META_DIR/$name.json"
}

# ── commands ────────────────────────────────────────────────────────────────

cmd_list() {
  ensure_layout
  local found=0
  for name in $(server_names); do
    found=1
    local desc state count last
    desc="$(meta_get "$name" description || echo "")"
    state="$(cred_state "$name")"
    count="$(python3 -c '
import json,sys
try:
    print(len(json.load(open(sys.argv[1])).get("tools", [])))
except Exception:
    print(0)
' "$META_DIR/$name.json" 2>/dev/null || echo 0)"
    last="$(meta_get "$name" last_used || echo "")"
    local mark="●"; [[ "$state" == cold ]] && mark="○"
    printf '%s %-16s %s\n' "$mark" "$name" "${desc:-(no description)}"
    printf '    %s · %s tools%s\n' "$state" "$count" "${last:+ · last used ${last%T*}}"
  done
  if [[ "$found" == 0 ]]; then
    echo "No servers vaulted yet."
    echo "↳ vault.sh add https://mcp.example.com/mcp"
  else
    echo
    echo "● warm (credentials ready)   ○ cold (run: vault.sh warm <name>)"
  fi
}

cmd_show() {
  local name="${1:-}"; [[ -n "$name" ]] || die "usage: vault.sh show <name>"
  ensure_layout; require_server "$name"
  local f="$META_DIR/$name.json"
  echo "# $name  [$(cred_state "$name")]"
  echo "url: $(server_url "$name")"
  [[ -f "$f" ]] || { echo "(no metadata yet — run: vault.sh use $name)"; return 0; }
  python3 -c '
import json,sys
d = json.load(open(sys.argv[1]))
if d.get("description"): print("\n" + d["description"])
if d.get("auth") == "token": print("auth: bearer token via ${%s}" % d.get("token_env",""))
elif d.get("auth") == "oauth": print("auth: OAuth (mcpc profile)")
tools = d.get("tools", [])
print("\ntools (%d, as of %s):" % (len(tools), d.get("last_used","never")))
for t in tools:
    desc = t.get("description","")
    print("  - %s%s" % (t["name"], " — " + desc if desc else ""))
' "$f"
}

cmd_describe() {
  local name="${1:-}"; shift || true
  local text="${*:-}"
  [[ -n "$name" && -n "$text" ]] || die "usage: vault.sh describe <name> <text>"
  ensure_layout; require_server "$name"
  write_meta "$name" "$(meta_get "$name" auth || echo none)" \
             "$(meta_get "$name" token_env || echo "")" "$text"
  echo "✓ described $name"
}

cmd_add() {
  require_mcpc; ensure_layout
  local url="" name="" token="" desc=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --token) token="${2:-}"; shift 2 || die "--token needs a value" ;;
      --description) desc="${2:-}"; shift 2 || die "--description needs a value" ;;
      -*) die "unknown flag: $1" ;;
      *) if [[ -z "$url" ]]; then url="$1"; else name="$1"; fi; shift ;;
    esac
  done
  [[ -n "$url" ]] || die "usage: vault.sh add <url> [name] [--token TOKEN]"
  [[ "$url" == http://* || "$url" == https://* ]] || url="https://$url"
  [[ -n "$name" ]] || name="$(derive_name "$url")"
  server_exists "$name" && die "'$name' is already vaulted (vault.sh show $name)"

  local auth=none token_env=""
  if [[ -n "$token" ]]; then
    auth=token
    token_env="$(printf '%s' "$name" | tr '[:lower:]-' '[:upper:]_')_MCP_TOKEN"
    umask 077
    touch "$ENV_FILE"
    printf '%s=%s\n' "$token_env" "$token" >> "$ENV_FILE"
    echo "✓ token stored in .env as \$$token_env"
  fi

  python3 -c '
import json,sys
path, name, url, token_env = sys.argv[1:5]
d = json.load(open(path))
entry = {"url": url}
if token_env:
    entry["headers"] = {"Authorization": "Bearer ${%s}" % token_env}
d.setdefault("mcpServers", {})[name] = entry
json.dump(d, open(path, "w"), indent=2)
open(path, "a").write("\n")
' "$SERVERS" "$name" "$url" "$token_env"
  write_meta "$name" "$auth" "$token_env" "$desc"
  echo "✓ vaulted $name → $url"

  load_env
  echo "connecting to snapshot its tools…"
  # `mcpc connect` returns 0 as soon as the bridge starts, even when the server
  # is unreachable — so a successful tool listing, not connect's exit code, is
  # what proves the server actually answered.
  local n=""
  if mcpc connect "$SERVERS:$name" "@$name" >/dev/null 2>&1 && n="$(snapshot_tools "$name")"; then
    echo "✓ connected — cached $n tools"
    [[ -z "$(meta_get "$name" description)" ]] && \
      echo "↳ add a description: vault.sh describe $name \"…\""
  else
    # Vaulted regardless; the entry is still usable once credentials exist.
    mcpc close "@$name" >/dev/null 2>&1 || true
    [[ "$auth" == none ]] && write_meta "$name" oauth "" "$desc"
    echo "⚠ no answer from the server — vaulted as cold, 0 tools cached"
    echo "  (it may need authentication, or the URL may be wrong)"
    echo "↳ vault.sh warm $name"
  fi
}

cmd_inspect() {
  require_mcpc
  local url="${1:-}"; [[ -n "$url" ]] || die "usage: vault.sh inspect <url>"
  [[ "$url" == http://* || "$url" == https://* ]] || url="https://$url"
  local tmp="mcpvault_probe"
  echo "probing $url (nothing will be saved)…"
  # Always tear the probe session down, even if listing fails.
  trap 'mcpc close "@$tmp" >/dev/null 2>&1 || true' RETURN
  mcpc connect "$url" "@$tmp" >/dev/null 2>&1 \
    || die "could not connect to $url (it may require authentication)"
  mcpc "@$tmp" tools-list
}

cmd_warm() {
  require_mcpc; ensure_layout
  local name="${1:-}"; [[ -n "$name" ]] || die "usage: vault.sh warm <name> [--token]"
  require_server "$name"
  local force_token=0
  [[ "${2:-}" == "--token" ]] && force_token=1
  local auth; auth="$(meta_get "$name" auth || echo none)"
  local url; url="$(server_url "$name")"

  if [[ "$force_token" == 1 || "$auth" == token ]]; then
    local var; var="$(meta_get "$name" token_env || echo "")"
    [[ -n "$var" ]] || var="$(printf '%s' "$name" | tr '[:lower:]-' '[:upper:]_')_MCP_TOKEN"
    printf 'Bearer token for %s: ' "$name" >&2
    local token; read -rs token; echo >&2
    [[ -n "$token" ]] || die "no token entered"
    umask 077
    touch "$ENV_FILE"
    # Replace any existing line for this var rather than appending a duplicate.
    if grep -qE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" 2>/dev/null; then
      local tmpf; tmpf="$(mktemp)"
      grep -vE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" > "$tmpf"
      mv "$tmpf" "$ENV_FILE"
    fi
    printf '%s=%s\n' "$var" "$token" >> "$ENV_FILE"
    python3 -c '
import json,sys
path, name, var = sys.argv[1:4]
d = json.load(open(path))
d["mcpServers"][name].setdefault("headers", {})["Authorization"] = "Bearer ${%s}" % var
json.dump(d, open(path, "w"), indent=2)
open(path, "a").write("\n")
' "$SERVERS" "$name" "$var"
    write_meta "$name" token "$var" "$(meta_get "$name" description || echo "")"
    echo "✓ $name is warm (token in .env as \$$var)"
  else
    echo "opening browser for OAuth login to $url…"
    mcpc login "$url" || die "login failed"
    write_meta "$name" oauth "" "$(meta_get "$name" description || echo "")"
    echo "✓ $name is warm (OAuth profile saved)"
  fi
}

cmd_use() {
  require_mcpc; ensure_layout
  local name="${1:-}"; [[ -n "$name" ]] || die "usage: vault.sh use <name>"
  require_server "$name"

  # mcpc only WARNS on an unresolved ${VAR} and substitutes an empty string,
  # which would connect with an empty bearer token and fail confusingly.
  if [[ "$(meta_get "$name" auth || echo none)" == token ]]; then
    local var; var="$(meta_get "$name" token_env || echo "")"
    env_var_set "$var" || die "$name is cold — \$$var is not set.
↳ vault.sh warm $name"
  fi

  load_env
  mcpc connect "$SERVERS:$name" "@$name" >/dev/null 2>&1 \
    || die "could not start a session for $name. If this is an auth failure, run:
  vault.sh warm $name"
  # connect returns 0 once the bridge starts; only a tool listing proves the
  # server actually answered, so don't claim success before that.
  local n
  if ! n="$(snapshot_tools "$name")"; then
    echo "⚠ session @$name started but the server did not answer." >&2
    echo "  Check its state:  mcpc @$name" >&2
    echo "  If unauthorized:  vault.sh warm $name" >&2
    exit 1
  fi
  echo "✓ @$name is live — $n tools"
  echo "↳ mcpc @$name tools-list"
  echo "↳ mcpc @$name tools-call <tool> arg:=value"
}

cmd_forget() {
  ensure_layout
  local name="${1:-}"; [[ -n "$name" ]] || die "usage: vault.sh forget <name>"
  require_server "$name"
  local var; var="$(meta_get "$name" token_env || echo "")"
  command -v mcpc >/dev/null 2>&1 && mcpc close "@$name" >/dev/null 2>&1 || true
  python3 -c '
import json,sys
path, name = sys.argv[1:3]
d = json.load(open(path))
d.get("mcpServers", {}).pop(name, None)
json.dump(d, open(path, "w"), indent=2)
open(path, "a").write("\n")
' "$SERVERS" "$name"
  rm -f "$META_DIR/$name.json"
  if [[ -n "$var" && -f "$ENV_FILE" ]]; then
    local tmpf; tmpf="$(mktemp)"
    grep -vE "^[[:space:]]*(export[[:space:]]+)?${var}=" "$ENV_FILE" > "$tmpf" || true
    mv "$tmpf" "$ENV_FILE"
    echo "✓ removed \$$var from .env"
  fi
  echo "✓ forgot $name"
}

case "${1:-list}" in
  list)     shift || true; cmd_list ;;
  show)     shift; cmd_show "$@" ;;
  add)      shift; cmd_add "$@" ;;
  describe) shift; cmd_describe "$@" ;;
  inspect)  shift; cmd_inspect "$@" ;;
  warm)     shift; cmd_warm "$@" ;;
  use)      shift; cmd_use "$@" ;;
  forget)   shift; cmd_forget "$@" ;;
  -h|--help|help) usage ;;
  *) echo "unknown command: $1" >&2; usage; exit 1 ;;
esac
