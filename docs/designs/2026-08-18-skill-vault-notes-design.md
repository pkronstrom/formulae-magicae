# Skill vault notes and search design

**Status:** Approved for implementation.

## Goal

Make a large skill vault searchable, and give the user somewhere to record what
they learned about a vaulted skill.

The vault holds roughly 450 skills across 9 categories. The only way to find one
today is `vault.sh categories` followed by guessing a category and running
`vault.sh catalog <category>`. Nothing searches. A user looking for "a skill about
MCP best practices" has to read category listings and pattern-match by eye, and a
skill whose name does not contain the search term is effectively invisible.

There is also nowhere to record judgement. A vaulted skill's own `SKILL.md` says
what its author claims it does; it cannot say "the eval harness is the good part"
or "superseded by the other one". That knowledge is currently lost between
sessions.

## Constraints

- `skill-vault` is standalone: bash, `git`, and the POSIX toolchain. It must not
  acquire a new hard dependency, and must keep working without `hawk`.
- `categories` must stay cheap. It exists specifically to avoid dumping the vault.
- Vaulted skills are plain clones. Anything written into a clone is lost on
  `update`, so user-authored content must live outside them.
- Existing output formats stay byte-identical for a vault with no notes.

## Storage: `NOTES.md`

A single `NOTES.md` at the vault root. One section per annotated skill:

```markdown
## anthropic/mcp-builder
aka: mcp
tags: #mcp #api-design
The eval harness is the good part — 10 questions run against a real agent.
reference/mcp_best_practices.md is the file you actually want.

## engineering/tool-design
tags: #mcp #api-design
Consolidation principle: fewer fatter tools beat many thin ones.
```

- The heading is `## <category>/<skill-name>`, where `<skill-name>` is the
  frontmatter `name` — the identifier `catalog` already displays and dedupes on.
- Everything below a heading is freeform. `aka:` and `tags:` are conventions that
  aid grep, not parsed fields. Nothing validates them.
- The file lives at the vault root, so the vault's `/*/*/` gitignore rule does not
  match it. It is tracked and syncs between machines with no gitignore change.
- The file is created on first write and absent otherwise.

Rejected: per-skill JSON sidecars under `meta/`, keyed the same way. They require a
`!/meta/` gitignore exception (the `/*/*/` rule would otherwise swallow
`meta/anthropic/`), a python3 read/modify/write helper per field, and commands to
manipulate fields that a text editor already manipulates. A single file is
greppable in one pass and hand-editable. If it ever grows unmanageable, splitting
it is a mechanical change that does not alter the search interface.

Keying on the frontmatter name means an upstream rename orphans a note. This is
accepted and not handled: the note remains in `NOTES.md`, `find` still surfaces it,
and no code detects or prunes it.

## Search: `vault.sh find <query>`

```bash
cmd_find() {
  local query="${1:-}"
  [[ -n "$query" ]] || { echo "usage: vault.sh find <query>" >&2; exit 1; }
  cd "$VAULT_DIR"

  local lq found=0
  lq=$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')

  # Catalog hits, keeping the "## category" heading above each group.
  # index() is a fixed-string search: regex metacharacters in the query are
  # literal, and a malformed query cannot silently match nothing.
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

  # Note hits, printed as whole "## "-bounded sections so every match is
  # attributable to a skill regardless of which line inside it matched.
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
```

Wiring, without which the command is unreachable — `vault.sh find` otherwise
falls through to the `*)` catch-all and exits `unknown command: find`:

```bash
# in the case block
  find) shift; cmd_find "$@" ;;

# in usage()
  find <query>                   Search names, descriptions and notes
```

`find` filters `cmd_catalog` output rather than searching the filesystem. This
reuses the existing `dedup_skills_in_category` logic, so tool-mirror duplicates
(`.antigravity-plugin/skills/x` alongside `skills/x`) are already collapsed.

Three behaviours are deliberate and each was verified against the real ~450-skill
vault:

- **Category headings are re-emitted.** A plain `cmd_catalog | grep` drops every
  `## category` line, because grep prints only matching lines and a heading does
  not contain the query. Skill names are unique only within a category —
  `prototype` and `code-review` each exist in two — so a bare list of matches is
  ambiguous. The awk pass tracks the current heading and prints it once above the
  first match in each category.
- **Matching is fixed-string, and errors are not masked.** With `grep` the query
  is a regex and `|| true` swallows its error, so `vault.sh find '['` prints "no
  skill matches" and exits 0 — a malformed query is indistinguishable from an
  empty vault. `index()` has no metacharacters, so `[` matches literally.
- **Descriptions are truncated to ~150 characters on a word boundary.** Some
  frontmatter descriptions run to a full screen each; untruncated, a 7-hit search
  is unreadable. Word-boundary truncation is locale-independent, which
  `substr($0, 1, 150)` is not: under `LC_ALL=C` it splits multibyte characters
  and produces illegal byte sequences (verified — `cut` rejects the output).

A full `cmd_catalog` pass over ~450 skills measures 1.6s. No caching.

`grep` was considered for the filtering step and rejected for the reasons above,
not on dependency grounds. Note that the earlier `ripgrep` objections — that the
vault's `/*/*/` gitignore makes `rg` search zero files, and that `rg` skips hidden
directories — **do not apply to this design**, because `cmd_find` filters a stream
and reads one file by path rather than traversing the vault. Those traps are real
and remain relevant to anyone grepping the vault by hand; they are documented in
SKILL.md for that reason, not as a justification for this implementation.

## Commands not added

No `note`, `tag`, `untag`, `alias`, `show`, or `tags` command, and no `--tag`
filter on `catalog`.

Writing a note is appending text to a markdown file, which both the user and the
agent can already do. Reading one is `find`, or opening the file. Tags and `aka:`
are grep targets, so a dedicated filter would return what `find` returns. Building
seven commands over a store that exists to hold freeform prose would add parsing,
validation, and failure modes in exchange for typing convenience.

`categories` and `catalog` are unchanged. No annotation marker is added to their
output; discovering that a note exists is what `find` is for.

## SKILL.md changes

The workflow currently reads: list categories, pick one, read its catalog. It
becomes search-first.

- **Step 1 — search.** `vault.sh find <query>` for a known need. State that this is
  the normal entry point.
- **Step 2 — browse.** `categories`, then `catalog <category>`, for when the need is
  vague or the search is empty. This is the current Step 1 content, demoted.
- **Step 3 — use a skill.** Unchanged: read it in place, do not install it.
- **New section — recording notes.** Append to `NOTES.md` under a
  `## <category>/<name>` heading after learning something about a vaulted skill
  that its own `SKILL.md` does not say: which reference file is the useful one,
  which of two overlapping skills won, why one was rejected. Include the file
  format and state that `aka:`/`tags:` are grep conventions, not schema.

`vault-README.md`, seeded into new vaults by `bootstrap.sh`, gains a line
describing `NOTES.md`. `bootstrap.sh` does not create `NOTES.md`.

## Testing

`tests/test_skill_vault.py`, matching the repository's existing pytest layout. A
fixture builds a throwaway vault in `tmp_path` containing at minimum: two
categories; one multi-skill clone (mirroring the real `anthropic/skills` shape);
one clone with a tool-mirror duplicate under a hidden directory; and a `NOTES.md`.

Cases:

- `find` matches a skill by frontmatter name.
- `find` matches a skill by a word appearing only in its description.
- `find` matches text appearing only in `NOTES.md`.
- `find` prints the `## category` heading above each group of matches.
- `find` prints the whole `## category/skill` note section when the match is on a
  later line of that note, not just the matching line.
- `find` treats regex metacharacters literally: `find '['` returns entries
  containing a literal `[` rather than erroring and reporting no matches.
- `find` truncates long descriptions on a word boundary, and its output is
  byte-identical under `LC_ALL=C` and a UTF-8 locale (no split multibyte
  characters).
- `find` collapses tool-mirror duplicates, including the hidden-directory copy that
  `ripgrep` would skip.
- `find` with no match prints the no-match message and exits 0.
- `find` with no argument prints usage and exits non-zero.
- `find` succeeds when `NOTES.md` is absent.
- `vault.sh find` is reachable through the `case` dispatcher and listed in
  `usage()`.
- `categories` and `catalog` output is unchanged by the presence of `NOTES.md`.

## Out of scope

- Installing vaulted skills into the active skill set. The vault reads in place.
- Any change to `add`, `update`, or `remove`.
- Migrating existing vaults. `NOTES.md` is absent until first written.
