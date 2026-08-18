---
name: skill-vault
description: Catalog of downloaded-but-inactive skills in a personal vault, grouped by category. Use when a specialized vaulted skill might beat improvising — e.g. frontend/design work — or when asked to add, update, or remove one.
---

# Skill Vault

A skill vault holds skills that have been downloaded but aren't part of the
active skill set — kept out of the way until they're actually relevant to
the task at hand. `bootstrap.sh` and `vault.sh` live beside this file; this
is a standalone skill and never requires hawk to run, though hawk (or any
other tool) can distribute it.

## Step 0: Find or create the vault

`bootstrap.sh` lives beside this `SKILL.md`, in the base directory this
skill was loaded from. Run:

```bash
<skill's base directory>/bootstrap.sh check
```

If it prints a path, that's the vault (`$VAULT`) — skip to Step 1.

If it prints nothing (exit 1), no vault has been set up on this machine
yet. Ask the user:

> "You don't have a skill vault yet. Where should I create one? Default:
> `~/.skill-vault`."

Then run, using their answer (or the default if they just confirm):

```bash
<skill's base directory>/bootstrap.sh init <chosen-path>
```

This creates the directory (as its own git repo), copies in `vault.sh` and
a starter `README.md`, and records the path in
`~/.config/skill-vault/config` so future invocations skip straight to Step
1 via `check`. The printed path is `$VAULT` for the rest of this skill.

## Step 1: Search

When you know roughly what you need, search — don't browse. One call:

```bash
$VAULT/vault.sh find <query>
```

It matches names, descriptions and notes, printing hits in catalog format
under their category heading, with long descriptions truncated. Matching is
case-insensitive and literal, so `find '['` searches for a bracket rather
than erroring.

A query is a substring, not a concept: `find mcp` finds skills whose name or
description contains "mcp", and will also return skills that merely mention
it in passing. Skim the hits and read the promising one. If a search comes
back empty or too noisy, browse instead.

## Step 2: Browse what's available

The vault can grow to hundreds of skills — don't dump the whole thing by
default. Run:

```bash
$VAULT/vault.sh categories
```

This is cheap: every category with every skill name, no descriptions. Pick
the category (or categories) that plausibly fit the current task, then run:

```bash
$VAULT/vault.sh catalog <category>
```

for each one to see full descriptions and paths. Only fall back to
`vault.sh catalog` with no argument (every category, full detail) if the
task is genuinely ambiguous about which category applies.

## Step 3: Use a relevant skill

If an entry looks relevant to the current task, read it directly and follow
its instructions as if it had been invoked normally:

Read `$VAULT/<path from catalog output>`

Do not copy, symlink, or otherwise install the vaulted skill into the
active skill set — just read it in place and follow it. Its own relative
references to bundled scripts or reference files still resolve correctly,
since it's being read from its real location on disk.

If nothing in the catalog is relevant, proceed with the task normally.

## Recording what you learn

A vaulted skill's `SKILL.md` says what its author claims it does. It can't say
which of its reference files was the useful one, which of two overlapping
skills won, or why one was rejected. Write that down — `find` searches it, so
the next session gets it for free.

Notes live in `$VAULT/NOTES.md`, one section per skill, keyed the same way
`catalog` names things:

```markdown
## anthropic/mcp-builder
aka: mcp
tags: #mcp #api-design
The eval harness is the good part — 10 questions run against a real agent.
reference/mcp_best_practices.md is the file you actually want.
```

Append to it directly; there is no command. Create the file if absent.
`aka:` and `tags:` are conventions that give `find` something to match — no
schema, nothing validates them, and anything else you write is fine too.

Worth a note: which reference file mattered, why a skill was rejected, which
of two similar skills to reach for. Not worth a note: a restatement of the
skill's own description.

If an upstream `update` renames a skill, its note keeps the old heading and
nothing repairs it. `find` still surfaces the text; fix the heading by hand
if it bothers you.

## Adding, updating, or removing a vaulted skill

If asked to vault a skill (e.g. "add this skill to the vault", pasting a
repo URL), update one, or remove one, use `vault.sh` directly — do not
hand-edit the category folders.

```bash
$VAULT/vault.sh add <url> <category> [name]    # clone a new skill into the vault
$VAULT/vault.sh update [category/name]         # pull one skill, or all, to latest remote
$VAULT/vault.sh remove <category/name>          # remove a vaulted skill
```

Each vaulted skill is its own plain `git clone` — not a submodule, no
pinned commit tracked by the vault repo itself.

- `<url>` — the skill's git repo URL.
- `<category>` — which top-level folder it goes in (e.g. `frontend`,
  `backend`, `ai`). Reuse an existing category from the catalog when the
  skill fits one; otherwise a new category folder is created automatically
  on first use — no separate setup step needed.
- `[name]` — optional; defaults to the repo name from the URL. Only needed
  when a repo name would collide with a skill already in that category or
  isn't descriptive on its own.
- `category/name` for `update`/`remove` is the skill's path exactly as it
  appears in parentheses at the end of each `catalog` entry, e.g.
  `frontend/taste-skill`.

`.git` is a reserved name and can't be used as a category. After adding,
removing, or updating, run `catalog` again to confirm the change landed.
