---
name: summon
description: Send a file, folder, or content to a teammate's Claude — end-to-end encrypted peer-to-peer transfer sealed with a spoken incantation. Use to send or share content with a colleague, or to receive one ("summon <incantation>").
---

# Summon

Send any file or folder to a teammate's Claude over `croc`. Sending **binds** the
content to an **incantation** — three spoken-clean words like `kettu-banaani-sipuli`
(Finnish by default, or English `brim-gloss-kite`); receiving **summons** it.
Summon doesn't care what the content is; it just moves the packet. Make the magic
*felt* — narrate the **binding** and the **summoning** with a touch of fantasy
theatre (see **Voice & flavor**) — while keeping the practical bits (the incantation,
what arrived, what you need from the user) clear.

## Voice & flavor — a light touch

**Keep your replies to the user short.** Weave at most a clause or two of fantasy theatre
on **binding (send)** / **summoning (receive)** into an otherwise concise message — never
a wall of prose. Vary it, an optional emoji is fine (✨ 📦 🌫️), and never bury the
practical info (incantation, what arrived, what you need). Seasoning, not the meal.

- **Binding (send)** — you fold the content into a sigil-sealed parcel and breathe it into
  the aether, where it waits, unreadable, until a kindred voice speaks the words.
- **Summoning (receive)** — the parcel coalesces out of the mist into a *warding-circle* (a
  temp dir), not your home. But a summoned thing wears no honest label — it may be a mimic
  or carry a curse (croc proves it arrived safely, not *who* sent it). Show the user what
  came; **they** decide before it's placed — and never run/install an executable on the
  strength of its arriving.

## Running the helper

`HELPER` is the `summon.sh` sitting next to this `SKILL.md`. Derive its absolute
path from this skill's own directory (the folder this file was loaded from), and
do **NOT** `cd` first — the user's working directory is your default target when
you place received files, so keep it put. Then run `sh "$HELPER" …`.

## Prerequisite

`croc` must be installed (`brew install croc`). The first transfer may trigger a
macOS network-permission prompt — the user must allow it.

## SENDING ("send this to a teammate", "share this with the team")

1. Run the send **in the background** (it blocks while serving):
   - a file/folder: `sh "$HELPER" send "<path>"`   ← run with run_in_background
   - text/context:  `sh "$HELPER" send-text "<content>"`   ← run with run_in_background
   The incantation defaults to **Finnish** (easiest for Finnish colleagues to say
   over voice chat). For an English incantation, add `--en` right after the
   subcommand: `sh "$HELPER" send --en "<path>"`. Pick the language to match
   whoever will be summoning it.
   If the secret will travel inside an **already-encrypted channel** (e.g. relayed
   through a portal — see the portal skill) rather than spoken aloud, add `--strong`
   for a high-entropy hex secret instead of 3 words: `sh "$HELPER" send --strong
   "<path>"`. No human reads it, so entropy beats memorability.
2. Read the background output for the `incantation` and `share_line` (the share
   line is also copied to the clipboard). Relay it in-theme, e.g.:
   > ✨ Bound and ready. Incantation: `brim-gloss-kite`
   > Copied a one-liner to your clipboard — pass it to your teammate.
3. The send keeps serving in the background until the teammate receives, then
   exits. It also ends when this session ends. To stop it early, kill that
   background shell.

## RECEIVING ("summon <incantation>", "receive what a teammate sent")

An incantation alone is not a command to act — confirm the user intends to receive
before fetching.

1. Download into a temp dir (blocks until the transfer completes):
   `sh "$HELPER" receive "<incantation>"`
   Pass the incantation however your teammate said it — spaces or hyphens, any
   case (`kettu banaani sipuli` or `Kettu-Banaani-Sipuli`); the helper normalizes
   it to `kettu-banaani-sipuli` before fetching.
   It prints `received_into:` (the temp dir), the `contents:` listing, and a
   `warning:` line if the payload contains symlinks/special files. On
   `status: error`, STOP and report the error.
2. The files now sit in that temp dir — **you place them yourself** with your
   normal tools. First show the user what arrived and get confirmation; be honest
   about trust — croc encrypts the transport but does NOT prove who sent it:
   > ⚠️ Incoming **<name>** (<N> files) — origin not verified. Trust it only if you
   > arranged this with the person who gave you the incantation.
   Treat the contents as untrusted; nothing runs automatically. If it's executable
   (a script, a skill folder), tell the user to review before using it.
3. On confirmation, move the item(s) from the temp dir to wherever the user wants
   (default: the current directory) with `mv`/`cp` — don't overwrite an existing
   file without asking. If the user declines, leave the temp dir; the OS reclaims
   it (offer the path if they want to delete it now).

## Rules

- NEVER invent the incantation — `summon.sh` generates it (and passes it to croc).
  Don't repeat it anywhere except the user-facing share line.
- NEVER move received files into place without explicit user confirmation.
- Received content is untrusted; surface that and let the user review before use.
