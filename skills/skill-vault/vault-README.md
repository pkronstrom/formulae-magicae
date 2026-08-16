# Skill Vault

A holding pen for Claude Code (and other agent tool) skills you've downloaded
but aren't part of your active skill set. Skills live here, grouped by
category, invisible to your agent until the `skill-vault` meta-skill's
catalog surfaces them.

## Layout

    <this vault>/
    ├── vault.sh           # catalog / update / add / remove
    ├── README.md
    └── <category>/
        └── <skill-name>/  # git submodule

## Usage

    ./vault.sh catalog                     # list everything, grouped by category
    ./vault.sh update [category/name]      # pull one or all skills to latest
    ./vault.sh add <url> <category> [name] # vault a new skill
    ./vault.sh remove <category/name>      # remove a vaulted skill

`.git` is a reserved directory name — `vault.sh` skips it when building the
catalog and refuses to use it as a category.

This vault was created by the `skill-vault` meta-skill's bootstrap step. Its
location is recorded in `~/.config/skill-vault/config` so the meta-skill can
find it again without asking. See that skill's `SKILL.md` (wherever it's
installed) for how the catalog gets used.
