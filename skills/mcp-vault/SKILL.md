---
name: mcp-vault
description: A vault of MCP servers kept out of the active tool namespace until needed — rare, special-case, or one-off servers. Use to see which MCP servers are stashed and what tools they have, to connect ("warm up") one and call its tools, or to probe what an unknown MCP URL offers. Also use when asked to add an MCP server, to decide whether it belongs in the vault or permanently in the agent's own MCP config — ask the user which unless they said.
---

# MCP Vault

Rarely-used MCP servers don't belong in the agent's permanent tool namespace.
The vault keeps their configs on disk with a description and a cached tool
list, so you can see what's available without connecting to anything, then
connect only the one you need.

Built on `mcpc`, a universal MCP CLI client. `bootstrap.sh` and `vault.sh` live
beside this file. This is a standalone skill; hawk can distribute it but is
never needed at runtime.

## First: is the vault even the right destination?

"Add an MCP server at `<url>`" is ambiguous — it could mean *load it into the
agent permanently* or *stash it here*. *Ask which, and do not assume*, unless
the user already said (e.g. "vault this", "add to the vault", "I'll rarely use
this", or they name the other destination explicitly).

| | Where it goes | How |
|---|---|---|
| Used often; want its tools always available | The agent's own MCP config | However this machine manages MCP servers — the host's own command, or its component manager if one is in use |
| Rare, one-off, special-case, or just being tried out | This vault | `vault.sh add <url>` |

The trade-off to state plainly if the user is unsure: a permanently-loaded
server puts **all** of its tool definitions in the agent's context for every
session, whether used or not. A vaulted one costs nothing until connected, but
takes an explicit `use` first.

When the user only wants to know what a server offers before deciding, neither
applies yet — run `vault.sh inspect <url>` (below), which saves nothing.

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

Servers are grouped by tag, each showing its description, credential state, and
how many tools it had when last connected — no connections are made. Narrow to
one tag when the task is clearly in that area:

```bash
$VAULT/vault.sh list homelab      # only #homelab servers
```

For one server's full tool list, notes, and description:

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

Confirm the vault is the intended destination first — see the routing table at
the top of this skill.

```bash
$VAULT/vault.sh add <url>                        # public or OAuth server
$VAULT/vault.sh add <url> [name] --token <TOKEN> # bearer-token server
```

`add` writes the entry, connects, and caches the tool list. The name defaults
to the domain's main label (`mcp.notion.com` → `notion`); that name is the
alias from then on, so the URL is never retyped.

If the server doesn't answer, it's still vaulted — as cold, with zero tools
cached — and `add` says so rather than reporting false success.

If the server needs a bearer token you don't have yet, wire it now and warm it
later:

```bash
$VAULT/vault.sh add <url> <name> --token-env HOMELAB_AI_TOKEN
```

Always give it a description and tags afterwards — `list` is only as useful as
what's written on the entries:

```bash
$VAULT/vault.sh describe <name> "Notion workspace — search pages, append blocks."
$VAULT/vault.sh tag <name> work docs
```

## Tags and notes

Tags group the `list` output. A server can carry several and appears under each;
untagged ones collect at the end. Type them without `#` — a bare `#tag` at the
start of a shell word is a comment, so `tag foo #work` silently drops it (a
leading `#` is stripped if you quote it).

```bash
$VAULT/vault.sh tag <name> work homelab
$VAULT/vault.sh untag <name> work
```

**Notes accumulate, and you are expected to write them as you work.** When you
learn something about a server that the next session would otherwise have to
rediscover — which of its lists or resources is for what, a tool's real
behavior versus its description, a quirk, a broken config, why it won't
connect — append it:

```bash
$VAULT/vault.sh note <name> "The #obsidian memo list is the capture inbox; #read is the reading queue."
$VAULT/vault.sh note <name> --set "…"    # replace everything instead
$VAULT/vault.sh note <name> --clear
```

This is the vault's memory. The cached tool list says what a server *has*;
notes say what it's *for* and what bit you last time.

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
add it by hand only after reading what the command actually runs:

```json
"dodo": { "command": "dodo", "args": ["mcp"] }
```

Then `use <name>` as normal. Check the command's own `--help` first: a bare
binary name often starts an interactive UI rather than an MCP server, and the
failure looks like a connection error rather than a wrong command.

## Known limitation: SSE-only servers

`mcpc` speaks Streamable HTTP and has no transport flag. A server that only
serves the older HTTP+SSE transport (a `/sse` endpoint) fails with
`Method Not Allowed` (405) and cannot be reached through the vault at all.
Record that in the server's notes rather than leaving it looking merely cold —
its credentials may be perfectly fine.
