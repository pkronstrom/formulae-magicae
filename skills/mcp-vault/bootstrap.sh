#!/usr/bin/env bash
# Locates or creates the MCP vault. The agent asks the user where to put it
# (this script never prompts interactively); it only ever acts on an explicit
# path.
#
#   bootstrap.sh check         prints the vault path if already configured and
#                               it still exists, exits 1 with no output otherwise
#   bootstrap.sh init <path>   creates a vault at <path> if none is configured
#                               yet, records it, and prints the path. If already
#                               configured, prints the existing path unchanged
#                               (no-op) rather than silently relocating it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/mcp-vault"
CONFIG_FILE="$CONFIG_DIR/config"

configured_path() {
  [[ -f "$CONFIG_FILE" ]] || return 1
  local path
  path="$(head -1 "$CONFIG_FILE" | tr -d '[:space:]')"
  [[ -n "$path" && -d "$path" ]] || return 1
  printf '%s\n' "$path"
}

cmd_check() {
  configured_path
}

cmd_init() {
  local existing
  if existing="$(configured_path)"; then
    printf '%s\n' "$existing"
    return 0
  fi

  local path="${1:?usage: bootstrap.sh init <path>}"
  path="${path/#\~/$HOME}"

  mkdir -p "$path/meta"
  if [[ ! -d "$path/.git" ]]; then
    git -C "$path" init -q
  fi

  [[ -f "$path/vault.sh" ]] || cp "$HERE/vault.sh" "$path/vault.sh"
  chmod +x "$path/vault.sh"
  [[ -f "$path/README.md" ]] || cp "$HERE/vault-README.md" "$path/README.md"
  # .gitignore must exist before any secret can be written, so .env is never
  # committable even for a moment.
  [[ -f "$path/.gitignore" ]] || cp "$HERE/vault-gitignore" "$path/.gitignore"
  [[ -f "$path/servers.json" ]] || printf '{\n  "mcpServers": {}\n}\n' > "$path/servers.json"

  mkdir -p "$CONFIG_DIR"
  printf '%s\n' "$path" > "$CONFIG_FILE"

  printf '%s\n' "$path"
}

case "${1:-}" in
  check) cmd_check ;;
  init) shift; cmd_init "$@" ;;
  *) echo "usage: bootstrap.sh {check|init <path>}" >&2; exit 1 ;;
esac
