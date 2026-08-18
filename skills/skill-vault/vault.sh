#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESERVED_DIRS=(".git")

usage() {
  cat <<EOF
Usage: vault.sh <command> [args]

Commands:
  find <query>                   Search names, descriptions and notes (start here)
  categories                     List categories with every skill name, no descriptions (cheap)
  catalog [category]             List vaulted skills, grouped by category; scope
                                  to one category to avoid dumping the whole vault
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

# Prints deduped "name\tdescription\tpath" lines for one category.
# Some repos mirror the same skill into several per-tool folders
# (.cursor/skills/x, .claude/skills/x, plugin/skills/x, ...) with
# identical name/description. Dedupe by name, keeping whichever path
# is shortest — the least likely to be a nested tool-mirror copy.
dedup_skills_in_category() {
  local category="$1"
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

  [[ -z "$raw" ]] && return

  printf '%s\n' "$raw" | awk -F'\t' '
    {
      if (!($1 in seen) || length($3) < best_len[$1]) {
        if (!($1 in seen)) order[++n] = $1
        seen[$1] = $0
        best_len[$1] = length($3)
      }
    }
    END {
      for (i = 1; i <= n; i++) print seen[order[i]]
    }
  '
}

cmd_categories() {
  cd "$VAULT_DIR"
  for category_path in */; do
    local category="${category_path%/}"
    is_reserved "$category" && continue
    local names
    names=$(dedup_skills_in_category "$category" | awk -F'\t' '{print $1}' | paste -sd, - | sed 's/,/, /g')
    [[ -z "$names" ]] && continue
    printf '## %s\n%s\n\n' "$category" "$names"
  done
}

cmd_catalog() {
  local only_category="${1:-}"
  cd "$VAULT_DIR"

  if [[ -n "$only_category" ]]; then
    [[ -d "$only_category" ]] || { echo "error: no such category '$only_category'" >&2; exit 1; }
    is_reserved "$only_category" && { echo "error: '$only_category' is a reserved directory name" >&2; exit 1; }
    set -- "$only_category/"
  else
    set -- */
  fi

  for category_path in "$@"; do
    local category="${category_path%/}"
    is_reserved "$category" && continue

    local deduped
    deduped=$(dedup_skills_in_category "$category")
    [[ -z "$deduped" ]] && continue

    printf '## %s\n' "$category"
    printf '%s\n' "$deduped" | awk -F'\t' '{ printf "- **%s** — %s (%s)\n", $1, $2, $3 }'
    printf '\n'
  done
}

# Search names, descriptions and NOTES.md. Filters cmd_catalog output rather
# than the filesystem, so dedup of tool-mirror copies comes for free and hits
# print in the same format the catalog uses.
cmd_find() {
  local query="${1:-}"
  [[ -n "$query" ]] || { echo "usage: vault.sh find <query>" >&2; exit 1; }
  cd "$VAULT_DIR"

  local lq found=0
  lq=$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')

  # index() is a fixed-string search: regex metacharacters in the query are
  # literal, so a malformed query cannot silently match nothing the way a
  # bare `grep -i -- "$query" || true` does.
  local hits
  hits=$(cmd_catalog | awk -v q="$lq" '
    # Truncate on a word boundary. Split points are ASCII spaces, so a
    # multibyte character is never cut in half — substr() does exactly that
    # under LC_ALL=C and emits illegal bytes.
    function truncate(s,   n, i, out) {
      if (length(s) <= 150) return s
      n = split(s, w, " "); out = w[1]
      for (i = 2; i <= n; i++) {
        if (length(out) + 1 + length(w[i]) > 150) return out " ..."
        out = out " " w[i]
      }
      return out
    }
    /^## / { cat = $0; next }
    index(tolower($0), q) {
      if (cat != shown) { if (shown != "") print ""; print cat; shown = cat }
      print truncate($0)
    }
  ')
  [[ -n "$hits" ]] && { printf '%s\n' "$hits"; found=1; }

  # Whole "## "-bounded sections, so a match on any line of a note still
  # prints the heading that says which skill the note is about.
  if [[ -f NOTES.md ]]; then
    local notes
    notes=$(awk -v q="$lq" '
      function flush() { if (hit && buf != "") print buf "\n" }
      /^## / { flush(); buf = $0; hit = index(tolower($0), q) ? 1 : 0; next }
      buf != "" { buf = buf "\n" $0; if (index(tolower($0), q)) hit = 1 }
      END { flush() }
    ' NOTES.md)
    [[ -n "$notes" ]] && { printf '\n## notes\n\n%s' "$notes"; found=1; }
  fi

  [[ $found -eq 1 ]] || echo "no skill matches '$query'"
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
  find) shift; cmd_find "$@" ;;
  categories) cmd_categories ;;
  catalog) shift; cmd_catalog "$@" ;;
  update) shift; cmd_update "$@" ;;
  add) shift; cmd_add "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  -h|--help|help) usage ;;
  *) echo "unknown command: $1" >&2; usage; exit 1 ;;
esac
