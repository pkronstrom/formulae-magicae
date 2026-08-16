#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESERVED_DIRS=(".git")

usage() {
  cat <<EOF
Usage: vault.sh <command> [args]

Commands:
  catalog                        List all vaulted skills, grouped by category (default)
  update [category/name]         Pull one or all vaulted skills to latest remote
  add <url> <category> [name]    Clone a new skill into the vault
  remove <category/name>         Remove a vaulted skill
EOF
}

is_reserved() {
  local d="$1"
  for r in "${RESERVED_DIRS[@]}"; do
    [[ "$d" == "$r" ]] && return 0
  done
  return 1
}

cmd_catalog() {
  cd "$VAULT_DIR"
  for category_path in */; do
    local category="${category_path%/}"
    is_reserved "$category" && continue

    # Some repos mirror the same skill into several per-tool folders
    # (.cursor/skills/x, .claude/skills/x, plugin/skills/x, ...) with
    # identical name/description. Dedupe by name, keeping whichever path
    # is shortest — the least likely to be a nested tool-mirror copy.
    local raw
    raw=$(
      find "$category" -name SKILL.md 2>/dev/null | while IFS= read -r skill_md; do
        # Frontmatter description may be a single line ("description: text")
        # or a YAML block scalar ("description: |"/">" with the text on
        # indented lines below) — collapse either form to one line.
        IFS=$'\t' read -r name description <<< "$(awk '
          BEGIN { name = ""; desc = ""; in_desc = 0; desc_done = 0 }
          !in_desc && name == "" && /^name: / { n = $0; sub(/^name: */, "", n); name = n; next }
          !desc_done && !in_desc && /^description: *[|>]/ { in_desc = 1; next }
          !desc_done && !in_desc && /^description: / { d = $0; sub(/^description: */, "", d); desc = d; desc_done = 1; next }
          in_desc {
            if ($0 ~ /^[^ \t]/) { in_desc = 0; desc_done = 1; next }
            if ($0 == "") { next }
            line = $0; sub(/^[ \t]+/, "", line)
            desc = (desc == "") ? line : desc " " line
            next
          }
          END { print name "\t" desc }
        ' "$skill_md")"
        [[ -z "$name" ]] && continue
        printf '%s\t%s\t%s\n' "$name" "$description" "$skill_md"
      done
    )

    [[ -z "$raw" ]] && continue

    printf '## %s\n' "$category"
    printf '%s\n' "$raw" | awk -F'\t' '
      {
        if (!($1 in seen) || length($3) < best_len[$1]) {
          if (!($1 in seen)) order[++n] = $1
          seen[$1] = $0
          best_len[$1] = length($3)
        }
      }
      END {
        for (i = 1; i <= n; i++) {
          split(seen[order[i]], f, "\t")
          printf "- **%s** — %s (%s)\n", f[1], f[2], f[3]
        }
      }
    '
    printf '\n'
  done
}

cmd_update() {
  cd "$VAULT_DIR"
  if [[ $# -eq 0 ]]; then
    for category_path in */; do
      local category="${category_path%/}"
      is_reserved "$category" && continue
      for skill_path in "$category"/*/; do
        [[ -d "${skill_path}.git" ]] || continue
        echo "== ${skill_path%/} =="
        git -C "$skill_path" pull
      done
    done
  else
    [[ -d "$1/.git" ]] || { echo "error: '$1' is not a vaulted skill" >&2; exit 1; }
    git -C "$1" pull
  fi
}

cmd_add() {
  local url="${1:-}" category="${2:-}" name="${3:-}"
  if [[ -z "$url" || -z "$category" ]]; then
    echo "usage: vault.sh add <url> <category> [name]" >&2
    exit 1
  fi
  if is_reserved "$category"; then
    echo "error: '$category' is a reserved directory name" >&2
    exit 1
  fi
  cd "$VAULT_DIR"
  if [[ -z "$name" ]]; then
    name=$(basename "$url" .git)
  fi
  git clone "$url" "$category/$name"
}

cmd_remove() {
  local target="${1:-}"
  if [[ -z "$target" ]]; then
    echo "usage: vault.sh remove <category/name>" >&2
    exit 1
  fi
  cd "$VAULT_DIR"
  [[ -d "$target/.git" ]] || { echo "error: '$target' is not a vaulted skill" >&2; exit 1; }
  rm -rf "$target"
}

case "${1:-catalog}" in
  catalog) cmd_catalog ;;
  update) shift; cmd_update "$@" ;;
  add) shift; cmd_add "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  -h|--help|help) usage ;;
  *) echo "unknown command: $1" >&2; usage; exit 1 ;;
esac
