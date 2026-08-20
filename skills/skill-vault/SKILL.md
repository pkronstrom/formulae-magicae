---
name: skill-vault
description: Catalog of downloaded-but-inactive skills in a personal vault, grouped by category. Use when a specialized vaulted skill might beat improvising — e.g. frontend/design work — when asked to add, update, or remove one, or to see which vaulted skills get used often enough to promote into the active skill set.
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

`init` writes `vault.sh` only when creating the vault, so an existing vault
keeps whatever version created it. If `$VAULT/vault.sh` rejects a command
this skill documents, that's the cause — refresh it:

```bash
<skill's base directory>/bootstrap.sh sync
```

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

Read it in place and follow it. Its own relative references to bundled
scripts or reference files still resolve correctly, since it's being read
from its real location on disk.

Don't install a skill just because you used it once — that's what the vault
is avoiding. Installing is a separate, deliberate step, driven by evidence
of a habit rather than by a single hit: see **Promoting** below.

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

## Promoting what you keep reaching for

A skill you reach for every week shouldn't need a catalog lookup and a file
read every time. `promote` links it into the active skill set so it's just
there; the vault keeps holding the ones you don't.

### Seeing what you actually use

```bash
$VAULT/vault.sh usage            # all time
$VAULT/vault.sh usage --days 30
```

This mines the agent's own session logs for references to vaulted
`SKILL.md` paths — nothing has to be recorded as you go, so it works
retroactively over history that predates the feature. Skills are ranked by
**sessions**, not raw reads: one session that re-reads a skill six times is
one habit, not six. Anything used in 3+ sessions and still vaulted is
flagged `→ promote?`.

Two things it can't tell you. It counts *references*, so a skill discussed
but rejected still scores. And it only sees this machine's logs. Treat the
ranking as a prompt to think, not a verdict.

**Don't run this on every visit to the vault** — it greps every session log
on the machine. Run it when the user asks about their habits, or when you
notice you've reached for the same vaulted skill several times.

### Promoting and undoing it

```bash
$VAULT/vault.sh promote <name>                    # or the full category/path
$VAULT/vault.sh demote <name> [--to-vault <cat>]
$VAULT/vault.sh promoted [--repair]
```

`promote` symlinks the skill's directory into `~/.claude/skills/<name>`
(override with `SKILL_VAULT_PROMOTE_DIR`). Because it's a link and not a
copy, `vault.sh update` keeps a promoted skill current — there's no forked
second copy to drift.

Take the target from the ranking, or accept a name the user gives. If a name
is ambiguous — several vaulted repos ship a `skill-status` — `promote`
refuses and prints the candidates rather than guessing; pass the full path.
It also refuses to overwrite a name already taken by another tool's skill,
and says who holds it.

**A promotion lands in the next session, not this one.** The active skill
set is read at session start.

### Demoting depends on who owns the skill

`demote` takes a skill *out* of the active set, and the active skill
directory holds three different kinds of thing. It works out which it's
looking at rather than assuming everything there came from here:

| **A link into this vault** | unlinked. The vault copy is the original, so nothing is lost. |
| **A link into a component manager's registry** (hawk) | the manager owns it. `demote` runs `hawk disable <name>` and re-syncs instead of touching the link — deleting it directly would be undone by that tool's next sync. The package still holds the skill; `hawk enable <name>` puts it back. |
| **A real directory** | nothing manages it, so it exists only there. `demote` will not delete it. Pass `--to-vault <category>` to move it into the vault instead; without that it refuses and lists the categories. |

A link pointing somewhere else entirely is an error, not a guess — it names
the target and tells you to use whatever tool owns it.

A skill adopted this way arrives with no git remote, so `update` skips it
and the vault holds its only copy. `remove` knows that and refuses to delete
a remote-less skill without `--force`, because a clone can be re-fetched and
this cannot.

Three things worth saying out loud when you promote something:

- The link points into the vault, so **local edits to a promoted skill are
  still destroyed by `vault.sh update`.** Promotion is about reach, not
  ownership. A skill you want to *modify* has to be forked out of the vault
  into wherever you keep your own.
- Promotion has a standing cost: an active skill's description sits in
  context every session, used or not. That's the whole reason the vault
  exists. Promote what earns it and demote what stops earning it.
- The links live in a directory other tools may manage. `$VAULT/.promoted`
  records every promotion so a component manager that prunes what it doesn't
  recognise can't silently undo them — `promoted --repair` puts them back.
  The ledger is machine-local and gitignored.

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
