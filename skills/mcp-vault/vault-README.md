# MCP Vault

A directory of MCP server configs you want to keep, but don't want loaded into
your agent's tool namespace. Rare and special-case servers live here until you
need one, then connect in a single command.

Wraps [`mcpc`](https://github.com/apify/mcpc), which provides sessions, OAuth
with OS-keychain credential storage, and `${VAR}` expansion in config files.
The vault adds what mcpc doesn't have: per-server descriptions, a cache of what
tools each server had when last connected, and credential-state reporting.

## Layout

    <this vault>/
    ├── servers.json     # standard MCP config — mcpc reads this natively
    ├── meta/
    │   └── <name>.json  # description, cached tools, last used
    ├── .env             # secrets (gitignored)
    └── vault.sh

`servers.json` holds no vault-specific keys, so it stays portable to any other
MCP client, and `mcpc connect ./servers.json:<name>` works directly.

## Usage

    ./vault.sh list [tag]                    # grouped by tag; or just one tag
    ./vault.sh show <name>                   # cached tools, notes, description
    ./vault.sh add <url> [name] [--token T]  # vault a server (--token-env VAR to wire cold)
    ./vault.sh describe <name> <text>        # set the one-line description
    ./vault.sh note <name> <text>            # append a note (accumulates)
    ./vault.sh tag <name> <tag>...           # tag / untag
    ./vault.sh inspect <url>                 # probe a server NOT in the vault
    ./vault.sh warm <name> [--token]         # one-time auth
    ./vault.sh use <name>                    # connect + refresh the tool cache
    ./vault.sh cool <name>                   # close the session, keep everything
    ./vault.sh forget <name>                 # remove entry, metadata, AND credentials

After `use`, talk to mcpc directly:

    mcpc @<name> tools-list
    mcpc @<name> tools-call <tool> arg:=value

## Cold and warm

These describe **credentials**, not whether a process is running — mcpc manages
sessions itself (`connect` is idempotent and crashed sessions auto-restart).

- **cold** (○) — vaulted, but no usable credentials yet. Run `warm`.
- **warm** (●) — credentials exist, so connecting is one fast, non-interactive
  command.

State is computed on every run, never stored, so it can't go stale.

## Secrets

Bearer tokens live in `.env` (mode 0600, gitignored). `servers.json` only ever
references them:

```json
"headers": { "Authorization": "Bearer ${NOTION_MCP_TOKEN}" }
```

`vault.sh` exports `.env` before invoking mcpc, which expands the reference.
OAuth credentials aren't stored here at all — mcpc keeps those in the OS
keychain.

## Requirements

`mcpc` (`npm install -g @apify/mcpc`), `python3`, and `git`.
