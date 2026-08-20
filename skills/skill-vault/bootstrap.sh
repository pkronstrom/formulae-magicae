#!/usr/bin/env bash
# Locates or creates the skill vault. The agent asks the user where to put
# it (this script never prompts interactively); it only ever acts on an
# explicit path.
#
#   bootstrap.sh check         prints the vault path if already configured
#                               and it still exists, exits 1 with no output
#                               otherwise
#   bootstrap.sh init <path>   creates a vault at <path> if none is
#                               configured yet, records it, and prints the
#                               path. If already configured, prints the
#                               existing path unchanged (no-op) rather than
#                               silently relocating it.
#   bootstrap.sh sync          copies this skill's vault.sh over the one in
#                               the configured vault. init writes vault.sh
#                               only when creating the vault, so without
#                               this an existing vault stays frozen at the
#                               version that created it and never gains
#                               commands added to the skill later.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/skill-vault"
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

  mkdir -p "$path"
  if [[ ! -d "$path/.git" ]]; then
    git -C "$path" init -q
  fi

  [[ -f "$path/vault.sh" ]] || cp "$HERE/vault.sh" "$path/vault.sh"
  chmod +x "$path/vault.sh"
  [[ -f "$path/README.md" ]] || cp "$HERE/vault-README.md" "$path/README.md"
  [[ -f "$path/.gitignore" ]] || cp "$HERE/vault-gitignore" "$path/.gitignore"

  mkdir -p "$CONFIG_DIR"
  printf '%s\n' "$path" > "$CONFIG_FILE"

  printf '%s\n' "$path"
}

# Only vault.sh is refreshed. README.md and .gitignore are the user's after
# creation — a vault whose .gitignore was edited must not have that reverted
# by an unrelated script update.
cmd_sync() {
  local path
  path="$(configured_path)" || { echo "error: no vault configured" >&2; exit 1; }

  if cmp -s "$HERE/vault.sh" "$path/vault.sh"; then
    echo "vault.sh already current at $path"
    return 0
  fi

  cp "$HERE/vault.sh" "$path/vault.sh"
  chmod +x "$path/vault.sh"
  echo "vault.sh updated at $path"
}

case "${1:-}" in
  check) cmd_check ;;
  init) shift; cmd_init "$@" ;;
  sync) cmd_sync ;;
  *) echo "usage: bootstrap.sh {check|init <path>|sync}" >&2; exit 1 ;;
esac
