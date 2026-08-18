# Skill Vault

A holding pen for Claude Code (and other agent tool) skills you've downloaded
but aren't part of your active skill set. Skills live here, grouped by
category, invisible to your agent until the `skill-vault` meta-skill's
catalog surfaces them.

## Layout

    <this vault>/
    ├── vault.sh           # find / catalog / update / add / remove
    ├── README.md
    ├── NOTES.md           # your notes on vaulted skills (optional)
    ├── .gitignore         # ignores category dirs — see below
    └── <category>/
        └── <skill-name>/  # a plain `git clone`, not a submodule

## Usage

    ./vault.sh find <query>                # search names, descriptions and notes
    ./vault.sh catalog                     # list everything, grouped by category
    ./vault.sh update [category/name]      # pull one or all skills to latest
    ./vault.sh add <url> <category> [name] # clone a new skill into the vault
    ./vault.sh remove <category/name>      # remove a vaulted skill

`NOTES.md` is yours to write: one `## <category>/<skill-name>` section per
skill, freeform text below it. `find` searches it alongside the catalog, so
it is the place to record which reference file mattered or why you passed on
a skill. It sits at the vault root, outside the ignored category dirs, so it
is tracked and syncs with this repo. Create it when you have something to say.

`.git` is a reserved directory name — `vault.sh` skips it when building the
catalog and refuses to use it as a category.

Each vaulted skill is its own independent `git clone`, not a submodule of
this repo — no `.gitmodules`, no pinned commit tracked here. `.gitignore`
excludes every category subdirectory's contents, so this repo only ever
tracks `vault.sh` and its own docs; the clones' history and remotes are
untouched and fully usable on their own.

This vault was created by the `skill-vault` meta-skill's bootstrap step. Its
location is recorded in `~/.config/skill-vault/config` so the meta-skill can
find it again without asking. See that skill's `SKILL.md` (wherever it's
installed) for how the catalog gets used.
