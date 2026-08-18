---
name: mcp-vault
description: A vault of MCP servers kept out of the active tool namespace until needed — rare, special-case, or one-off servers. Use to see which MCP servers are stashed and what tools they have, to connect ("warm up") one and call its tools, to probe what an unknown MCP URL offers, or to vault a new server from a URL and token.
---

# MCP Vault

Rarely-used MCP servers don't belong in the agent's permanent tool namespace.
The vault keeps their configs on disk with a description and a cached tool
list, so you can see what's available without connecting to anything, then
connect only the one you need.

Built on `mcpc`, a universal MCP CLI client. `bootstrap.sh` and `vault.sh` live
beside this file. This is a standalone skill; hawk can distribute it but is
never needed at runtime.

## Step 0: Find or create the vault

```bash
<skill's base directory>/bootstrap.sh check
```

If it prints a path, that's the vault (`$VAULT`) — go to Step 1.

If it prints nothing (exit 1), no vault exists yet. Ask the user:

> "You don't have an MCP vault yet. Where should I create one? Default:
> `~/.mcp-vault`."

Then run, with their answer or the default:

```bash
<skill's base directory>/bootstrap.sh init <chosen-path>
```

This creates the vault as a git repo with a `.gitignore` that excludes `.env`,
and records the location in `~/.config/mcp-vault/config` so later runs skip
straight to Step 1.

`mcpc` must be installed: `npm install -g @apify/mcpc`. `vault.sh` says so if
it's missing.

## Step 1: See what's vaulted

```bash
$VAULT/vault.sh list
```

Each server shows its description, credential state, and how many tools it had
when last connected — no connections are made. For one server's full tool list
with descriptions:

```bash
$VAULT/vault.sh show <name>
```

**● warm** means credentials are ready and connecting is one fast command.
**○ cold** means it needs a one-time `warm` first. This is about credentials,
not running processes — mcpc manages sessions itself.

## Step 2: Use a server

```bash
$VAULT/vault.sh use <name>       # connects, refreshes the cached tool list
```

Then call its tools through mcpc directly:

```bash
mcpc @<name> tools-list
mcpc @<name> tools-get <tool>                    # full schema for one tool
mcpc @<name> tools-call <tool> arg:="value"
mcpc @<name> tools-call <tool> --json            # machine-readable output
```

mcpc covers the rest of MCP too — `resources-list`, `resources-read`,
`prompts-list`, `prompts-get`, `tasks-list`. Run `mcpc --help`, or read its own
bundled skill via `mcpc help --skill`, rather than guessing.

If a server is cold, `use` refuses and tells you to warm it — it will not
connect with missing credentials.

## Warming a cold server

```bash
$VAULT/vault.sh warm <name>            # OAuth: opens a browser, saves a profile
$VAULT/vault.sh warm <name> --token    # prompts for a bearer token instead
```

OAuth credentials go to the OS keychain (mcpc handles this). Bearer tokens go
to `$VAULT/.env`, mode 0600 and gitignored, referenced from `servers.json` as
`${VAR}` — never written into the config itself.

This is one-time. Afterwards the server is warm and `use` just works.

## Adding a server

```bash
$VAULT/vault.sh add <url>                        # public or OAuth server
$VAULT/vault.sh add <url> [name] --token <TOKEN> # bearer-token server
```

`add` writes the entry, connects, and caches the tool list. The name defaults
to the domain's main label (`mcp.notion.com` → `notion`); that name is the
alias from then on, so the URL is never retyped.

If the server doesn't answer, it's still vaulted — as cold, with zero tools
cached — and `add` says so rather than reporting false success.

Always give it a description afterwards, since `list` is only as useful as its
descriptions:

```bash
$VAULT/vault.sh describe <name> "Notion workspace — search pages, append blocks."
```

## Probing an unknown server

To see what an MCP URL offers **without** vaulting it:

```bash
$VAULT/vault.sh inspect <url>
```

Connects to a temporary session, lists the tools, prints them, and tears the
session down. Nothing is saved. Use this before `add` when the user pastes a
URL and asks what's in it.

## Removing a server

```bash
$VAULT/vault.sh forget <name>
```

Removes the `servers.json` entry, its metadata, and its `.env` line.

## Stdio servers

`add` only accepts URLs. Stdio (command-based) entries launch a local process
on connect, so vaulting one is deliberately a manual edit of `servers.json` —
add it by hand only after reading what the command actually runs.
