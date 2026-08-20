#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESERVED_DIRS=(".git")

# Where promoted skills are linked, and where the agent's session logs live.
# Both overridable so this works on a machine that lays Claude out differently.
PROMOTE_DIR="${SKILL_VAULT_PROMOTE_DIR:-$HOME/.claude/skills}"
LOG_DIR="${SKILL_VAULT_LOG_DIR:-$HOME/.claude/projects}"
PROMOTED_LEDGER="$VAULT_DIR/.promoted"

# Links in PROMOTE_DIR that this vault did not create belong to some component
# manager. Which one, and what its disable command is, is not something this
# script needs to know: it reports the target and stops, and the agent reading
# the skill routes to the right tool. Encoding that here would mean either
# hard-coding a vendor or executing a command string out of a config file.

# Sessions in which a skill was referenced, before it counts as a habit.
PROMOTE_THRESHOLD="${SKILL_VAULT_PROMOTE_THRESHOLD:-3}"

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
  remove <category/name>         Remove a vaulted skill (--force if it has no
                                  remote, i.e. the vault holds the only copy)

  usage [--days N]               Rank vaulted skills by how often you actually
                                  reach for them, mined from agent session logs
  promote <name|path>            Link a skill into the active skill set
  demote <name> [--to-vault C]   Take a skill out of the active set: unlink it,
                                  disable it in its manager, or — for an
                                  unmanaged directory — move it into category C
  promoted [--repair]            List promotions; --repair recreates missing links
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

# ---------------------------------------------------------------------------
# Usage tracking and promotion
# ---------------------------------------------------------------------------

# Vault-relative dir of every SKILL.md, with the skill's declared name.
# Prints "name\tvault-relative-dir".
all_skill_dirs() {
  cd "$VAULT_DIR"
  find . -name SKILL.md -not -path './.git/*' 2>/dev/null | while IFS= read -r skill_md; do
    local dir name
    dir="${skill_md#./}"; dir="${dir%/SKILL.md}"
    name=$(awk '/^name: / { sub(/^name: */, ""); print; exit }' "$skill_md")
    [[ -z "$name" ]] && continue
    printf '%s\t%s\n' "$name" "$dir"
  done
}

# Resolve a user-supplied target — a skill name, or a vault-relative path — to
# the directory holding its SKILL.md. Ambiguity is an error, not a coin flip:
# several vaulted repos ship a skill of the same name.
resolve_skill_dir() {
  local target="${1:-}"
  [[ -n "$target" ]] || { echo "error: no skill given" >&2; return 1; }

  local stripped="${target%/}"; stripped="${stripped%/SKILL.md}"
  if [[ -f "$VAULT_DIR/$stripped/SKILL.md" ]]; then
    printf '%s\n' "$stripped"
    return 0
  fi

  local matches
  matches=$(all_skill_dirs | awk -F'\t' -v n="$target" '$1 == n { print $2 }')
  local count
  count=$(printf '%s' "$matches" | grep -c . || true)

  case "$count" in
    1) printf '%s\n' "$matches" ;;
    0) echo "error: no vaulted skill named '$target' (try: vault.sh find $target)" >&2; return 1 ;;
    *) {
         echo "error: '$target' is ambiguous — $count skills share that name:"
         printf '%s\n' "$matches" | sed 's/^/  /'
         echo "pass the full path instead"
       } >&2
       return 1 ;;
  esac
}

is_promoted() {
  local dir="$1" name="$2" link="$PROMOTE_DIR/$2"
  [[ -L "$link" ]] || return 1
  [[ "$(readlink "$link")" == "$VAULT_DIR/$dir" ]]
}

# Count references to each vaulted SKILL.md across agent session logs.
# Sessions, not raw reads, is the ranking signal: one session that re-reads a
# skill six times is one habit, not six.
scan_usage() {
  local days="${1:-0}"
  [[ -d "$LOG_DIR" ]] || { echo "error: no session logs at $LOG_DIR" >&2; return 1; }

  local -a logs=()
  if [[ "$days" -gt 0 ]]; then
    while IFS= read -r f; do logs+=("$f"); done < <(find "$LOG_DIR" -name '*.jsonl' -mtime "-${days}" 2>/dev/null)
  else
    while IFS= read -r f; do logs+=("$f"); done < <(find "$LOG_DIR" -name '*.jsonl' 2>/dev/null)
  fi
  [[ ${#logs[@]} -gt 0 ]] || return 0

  # A path may appear in a tool call, a tool result, or the assistant's own
  # prose. All three mean the skill came up, so none are filtered out — but
  # the path must exist on disk, which drops typos and stale references.
  grep -RHo "$VAULT_DIR/[A-Za-z0-9._/-]*SKILL\.md" "${logs[@]}" 2>/dev/null \
    | awk -F: -v vault="$VAULT_DIR/" '
        {
          file = $1; path = $2
          sub("^.*" vault, "", path); sub(/\/SKILL\.md$/, "", path)
          if (path == "") next
          reads[path]++
          if (!((path SUBSEP file) in seen)) { seen[path SUBSEP file] = 1; sessions[path]++ }
        }
        END { for (p in reads) printf "%d\t%d\t%s\n", sessions[p], reads[p], p }
      ' \
    | while IFS=$'\t' read -r sessions reads path; do
        [[ -f "$VAULT_DIR/$path/SKILL.md" ]] || continue
        printf '%s\t%s\t%s\n' "$sessions" "$reads" "$path"
      done \
    | sort -rn -k1 -k2
}

cmd_usage() {
  local days=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --days) days="${2:-0}"; shift 2 ;;
      --days=*) days="${1#*=}"; shift ;;
      *) echo "usage: vault.sh usage [--days N]" >&2; exit 1 ;;
    esac
  done

  local rows
  rows=$(scan_usage "$days")
  if [[ -z "$rows" ]]; then
    echo "no vaulted skill has been used yet${days:+ in the last $days days}"
    return
  fi

  printf '%-9s %-7s %-11s %s\n' 'SESSIONS' 'READS' 'STATE' 'SKILL'
  local suggestions=0
  while IFS=$'\t' read -r sessions reads path; do
    local name state
    name=$(awk '/^name: / { sub(/^name: */, ""); print; exit }' "$VAULT_DIR/$path/SKILL.md")
    if is_promoted "$path" "$name"; then
      state="promoted"
    elif [[ "$sessions" -ge "$PROMOTE_THRESHOLD" ]]; then
      state="→ promote?"; suggestions=$((suggestions + 1))
    else
      state="vaulted"
    fi
    printf '%-9s %-7s %-11s %s  (%s)\n' "$sessions" "$reads" "$state" "$name" "$path"
  done <<< "$rows"

  if [[ "$suggestions" -gt 0 ]]; then
    echo
    echo "$suggestions skill(s) used in $PROMOTE_THRESHOLD+ sessions and still vaulted."
    echo "Promote one with: vault.sh promote <name>"
  fi
}

cmd_promote() {
  local target="${1:-}"
  [[ -n "$target" ]] || { echo "usage: vault.sh promote <name|category/path>" >&2; exit 1; }

  local dir name src link
  dir=$(resolve_skill_dir "$target") || exit 1
  src="$VAULT_DIR/$dir"
  name=$(awk '/^name: / { sub(/^name: */, ""); print; exit }' "$src/SKILL.md")
  [[ -n "$name" ]] || { echo "error: $dir/SKILL.md has no name in its frontmatter" >&2; exit 1; }
  link="$PROMOTE_DIR/$name"

  mkdir -p "$PROMOTE_DIR"

  # Never clobber something another tool owns. A hawk-managed symlink or a real
  # directory here means the name is already taken by a different skill, and
  # silently replacing it would be an unattributable breakage later.
  if [[ -e "$link" || -L "$link" ]]; then
    if is_promoted "$dir" "$name"; then
      echo "already promoted: $name -> $dir"
      return 0
    fi
    {
      echo "error: $link already exists and is not this vaulted skill"
      echo "  it points at: $(readlink "$link" 2>/dev/null || echo '(a real directory)')"
      echo "  resolve that first — this command will not replace another tool's skill"
    } >&2
    exit 1
  fi

  ln -s "$src" "$link"
  printf '%s\t%s\n' "$name" "$dir" >> "$PROMOTED_LEDGER"
  echo "promoted: $name -> $link"
  echo "It is now an active skill. Invoke it directly; stop reading it out of the vault."
}

drop_from_ledger() {
  [[ -f "$PROMOTED_LEDGER" ]] || return 0
  local tmp; tmp=$(mktemp)
  awk -F'\t' -v n="$1" '$1 != n' "$PROMOTED_LEDGER" > "$tmp" && mv "$tmp" "$PROMOTED_LEDGER"
}

# Demotion means three different operations depending on who owns the skill,
# and conflating them loses work:
#
#   link into this vault   unlink it; the vault copy is the original
#   link into a manager    the manager owns it — ask the manager to disable it,
#                           never touch its link, and never move its registry
#                           copy (the source of truth is the package repo, and
#                           the next update would undo the move anyway)
#   a real directory       nothing manages it, so demoting it means moving it
#                           into the vault or it is simply deleted
cmd_demote() {
  local name="" category=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --to-vault) category="${2:-}"; shift 2 ;;
      --to-vault=*) category="${1#*=}"; shift ;;
      -*) echo "usage: vault.sh demote <name> [--to-vault <category>]" >&2; exit 1 ;;
      *) name="$1"; shift ;;
    esac
  done
  [[ -n "$name" ]] || { echo "usage: vault.sh demote <name> [--to-vault <category>]" >&2; exit 1; }

  local link="$PROMOTE_DIR/$name"

  # Not there at all: still clear the ledger, so a link removed by hand or by
  # someone else's prune doesn't linger as a phantom promotion.
  if [[ ! -e "$link" && ! -L "$link" ]]; then
    drop_from_ledger "$name"
    echo "not active: $name (nothing at $link)"
    return 0
  fi

  # Case 1 — ours.
  if [[ -L "$link" ]] && [[ "$(readlink "$link")" == "$VAULT_DIR"/* ]]; then
    rm "$link"
    drop_from_ledger "$name"
    echo "demoted: $name (still in the vault at $VAULT_DIR)"
    return 0
  fi

  # Case 2 — someone else's link.
  if [[ -L "$link" ]]; then
    {
      echo "not ours: $name is managed by another tool"
      echo "  link:   $link"
      echo "  target: $(readlink "$link")"
      echo "  Ask that tool to disable the skill. Do not delete the link and do"
      echo "  not move what it points at — its next sync would undo either one."
    } >&2
    exit 2
  fi

  # Case 3 — a real directory, owned by nobody.
  [[ -f "$link/SKILL.md" ]] || {
    echo "error: $link is not a skill directory — refusing to touch it" >&2
    exit 1
  }

  if [[ -z "$category" ]]; then
    {
      echo "error: $name is a real directory, not a link — nothing manages it"
      echo "  demoting it means moving it into the vault, which needs a category:"
      echo "    vault.sh demote $name --to-vault <category>"
      echo "  categories in use: $(cd "$VAULT_DIR" && for d in */; do [[ "$d" == ".git/" ]] || printf '%s ' "${d%/}"; done)"
      echo "  (to delete it instead, remove the directory yourself — this will not)"
    } >&2
    exit 1
  fi

  is_reserved "$category" && { echo "error: '$category' is a reserved directory name" >&2; exit 1; }

  local dest="$VAULT_DIR/$category/$name"
  [[ -e "$dest" ]] && { echo "error: $dest already exists" >&2; exit 1; }

  mkdir -p "$VAULT_DIR/$category"
  mv "$link" "$dest"
  drop_from_ledger "$name"
  echo "demoted: $name moved into the vault at $category/$name"

  # Everything else in the vault is a clone with a remote behind it. This one
  # is not, so say so once, here, rather than letting `update` skip it and
  # `remove` delete it as if it were replaceable.
  if [[ ! -d "$dest/.git" ]]; then
    echo "note: it has no git remote, so 'vault.sh update' skips it and this is"
    echo "      now the only copy. Back it up if it holds work you can't redo."
  fi
}

# The ledger exists because these links live in a directory other tools manage.
# A component manager pruning what it does not recognise would otherwise remove
# promotions with nothing recording that they were ever there.
cmd_promoted() {
  local repair=0
  [[ "${1:-}" == "--repair" ]] && repair=1

  if [[ ! -s "$PROMOTED_LEDGER" ]]; then
    echo "nothing promoted yet (see: vault.sh usage)"
    return
  fi

  local missing=0
  while IFS=$'\t' read -r name dir; do
    [[ -n "$name" ]] || continue
    if [[ ! -f "$VAULT_DIR/$dir/SKILL.md" ]]; then
      echo "✗ $name — gone from the vault ($dir); demote it"
      continue
    fi
    if is_promoted "$dir" "$name"; then
      echo "✓ $name  ($dir)"
    elif [[ -e "$PROMOTE_DIR/$name" || -L "$PROMOTE_DIR/$name" ]]; then
      echo "✗ $name — $PROMOTE_DIR/$name is owned by something else now"
    elif [[ "$repair" -eq 1 ]]; then
      mkdir -p "$PROMOTE_DIR"
      ln -s "$VAULT_DIR/$dir" "$PROMOTE_DIR/$name"
      echo "✓ $name — link recreated  ($dir)"
    else
      echo "✗ $name — link missing; run: vault.sh promoted --repair"
      missing=$((missing + 1))
    fi
  done < "$PROMOTED_LEDGER"

  [[ "$missing" -gt 0 ]] && echo && echo "$missing promotion(s) lost their link."
  return 0
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
  local target="" force=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force) force=1; shift ;;
      *) target="$1"; shift ;;
    esac
  done
  if [[ -z "$target" ]]; then
    echo "usage: vault.sh remove <category/name> [--force]" >&2
    exit 1
  fi
  cd "$VAULT_DIR"
  target="${target%/}"
  [[ -f "$target/SKILL.md" || -d "$target/.git" ]] || {
    echo "error: '$target' is not a vaulted skill" >&2; exit 1
  }

  # A clone can be re-fetched; a skill adopted from disk by `demote` cannot.
  # Deleting the only copy of something is a different act from dropping a
  # cached clone, so it takes an explicit --force.
  if [[ ! -d "$target/.git" && "$force" -eq 0 ]]; then
    {
      echo "error: '$target' has no git remote — this is its only copy"
      echo "  deleting it cannot be undone by re-cloning. If that's intended:"
      echo "    vault.sh remove $target --force"
    } >&2
    exit 1
  fi

  rm -rf "$target"
  echo "removed: $target"
}

case "${1:-catalog}" in
  find) shift; cmd_find "$@" ;;
  categories) cmd_categories ;;
  catalog) shift; cmd_catalog "$@" ;;
  update) shift; cmd_update "$@" ;;
  add) shift; cmd_add "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  usage) shift; cmd_usage "$@" ;;
  promote) shift; cmd_promote "$@" ;;
  demote) shift; cmd_demote "$@" ;;
  promoted) shift; cmd_promoted "$@" ;;
  -h|--help|help) usage ;;
  *) echo "unknown command: $1" >&2; usage; exit 1 ;;
esac
