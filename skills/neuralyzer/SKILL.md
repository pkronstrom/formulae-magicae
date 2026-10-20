---
name: neuralyzer
description: List what your agents remember, or make them forget one thing everywhere — memory files, memory MCPs, project docs and, if you approve, past session transcripts. /neuralyzer, /neuralyzer-forget.
---

# Neuralyzer

Two jobs: show the user what agents on this machine remember, and erase one
thing so it does not come back.

Deleting one memory file is rarely enough. Agents get things back from the
memory index, a global instruction file, a project's CLAUDE.md or design doc, a
skill's notes file, a memory MCP, and old transcripts that later sessions read
or that a harness turns back into memories. This skill finds every copy, the
user approves the list, the copies are removed, and a second scan checks that
nothing is left. When the user says the agent "somehow remembers" something,
the scan also shows where the agent gets it from: usually a file that loads at
the start of every session.

`NZ` is `neuralyzer.py` next to this SKILL.md. Run `python3 "$NZ" …`. It needs
only the Python standard library and runs `rg` and `fd` when they are installed.
`python3 "$NZ" --help` lists every store it knows.

| Invocation | Mode |
|---|---|
| `/neuralyzer`, `/neuralyzer list` | List |
| `/neuralyzer forget <thing>`, `/neuralyzer-forget <thing>`, "forget about X" | Forget |
| `/neuralyzer <anything else>` | Forget, with that as the thing |

In Codex, invoke it as `$neuralyzer …`.

## List

1. `python3 "$NZ" list`: the current project's memories in full, other
   projects as counts, and global instruction files, Codex and Gemini memory.
   Use `--all` to expand every project, or `--project DIR` for another project.
2. Memory tools: if this session has MCP tools whose names suggest memory
   (memory, remember, knowledge, graph, notes, vault, blackboard), call their
   list or search tools as well.
3. Show one compact table per store: entry, one-line description, type. Do not
   paste file bodies. End with: "`/neuralyzer-forget <thing>` erases one."

## Forget

### 1. Pin down the target

Turn the request into search terms: the name, aliases, abbreviations, old
names, file and directory names, URLs, hostnames, identifiers, handles. Propose
the list and ask the user once to confirm it or add terms. If a term is short or
an ordinary word, use `--word` and expect false hits.

Scope: the current project, every project where the memory scan finds the
thing, and any project the user names.

### 2. Scan (read-only, run the parts in parallel)

Send these as parallel tool calls in one message:

- **a. Memory and skills**: `python3 "$NZ" scan --tier memory,skills TERM…`.
  It searches agent memory and global instruction files, and skills, commands,
  agents and plugins by their resolved path. Before you edit a skill file, find
  where it is maintained. A plugin cache is replaced on the next update, and a
  package manager's installed copy is overwritten on the next sync. Edit the
  source and reinstall.
- **b. Memory MCPs**: search each memory tool for each term. Some examples: the
  reference MCP memory server (`search_nodes`, then `delete_observations` or
  `delete_entities`), mem0/OpenMemory (`search_memory`, `delete_memories`),
  vector stores (search, then delete by id), note-vault servers (search, then
  edit the note). If a server keeps a backing file on disk, add its directory
  with `--root` so later scans cover it.
- **c. Project docs**: run this in each project root:
  `rg -n -i -F --hidden -g '!.git' -e T1 -e T2 .` plus `fd -H -i T1` for file
  names. Sort the hits into three groups: instruction files (CLAUDE.md,
  CLAUDE.local.md, AGENTS.md, GEMINI.md, `.claude/`, `.codex/`, `.agents/`,
  `.cursor/`), docs (READMEs, `docs/`, ADRs, plans, specs, handoffs, notes,
  changelogs), and code.
- **d. History**: `python3 "$NZ" scan --tier history TERM…`. It reports match
  counts for transcripts, prompt logs, file snapshots, caches and app databases
  of Claude Code, Codex, Gemini and OpenCode. Add `--root DIR` for any other
  harness home.

To keep the scan cheap:

- Read only the files that matched, and only around the matching lines
  (`rg -n -C2`). Do not open whole files to check them.
- Never read transcripts into context. They are large, and the history scan
  gives counts, dates and project paths, which is all you need.
- Send long docs (more than about 400 lines), and docs that discuss the thing
  without naming it ("the old provider", "that approach"), to cheap scouts in
  parallel. In Claude Code, use the Agent tool with `subagent_type: Explore`
  and `model: haiku`. In Codex, use a subagent on the luna model, or run
  `codex exec -m gpt-6-luna -s read-only "<brief>"`. Give each scout the terms,
  one sentence on what the thing is, and the files to read. Ask it to return
  `path:line-range` and a reason of 10 words or fewer for every passage about
  the thing, including indirect references, and to change nothing. Scouts
  report and you make the edits. With many projects, give each project to one
  scout that runs part (c) and returns a hit table.
- Hundreds of history hits usually mean the thing is named in text that every
  session loads: a skill or command description, a global instruction file, a
  memory index. Remove that source first. After that, the history redaction is
  one bulk pass.

### 3. Show the hit map and ask

Show one table: location, number of hits, proposed action.

| Hit | Action |
|---|---|
| Memory file entirely about the thing | Delete the file, its line in the index (`MEMORY.md`), and `[[links]]` to it in other memories |
| Memory file partly about it | Remove those sentences and keep the rest |
| Instruction file or doc | Remove the passage, then reword what is left so it reads naturally |
| Code | List only. Change it only if the user asks |
| Memory MCP entry | Delete it with that server's own delete tool |
| History | Redact, after the separate question below |

Ask once about memory and docs: apply everything, or let the user choose.
Then ask separately about history, because rewriting old transcripts of every
harness cannot be undone. Run `python3 "$NZ" redact TERM…`, which only shows
what would change, show its summary, and ask. That question also covers this
session: yes means the request itself is erased too (see Apply).

### 4. Apply

- Re-read each file just before you edit it, because another session may have
  changed it.
- Delete exact file paths. Never run `rm -r` on a directory.
- In project repositories, do not commit the changes. Show `git diff --stat`.
  Tell the user once that git history still contains the old text, and that
  rewriting history is their decision because it breaks existing clones.
- History: the redact run replaces each match with `[neuralyzed]`. It parses
  `.json` and `.jsonl` files as JSON so they stay valid, updates databases in
  place with freed pages zeroed, keeps file modification times, and never
  rewrites settings or credential files. Pass the terms on stdin and add
  `--follow`:

  ```sh
  python3 "$NZ" redact - --apply --follow <<'EOF'
  term one
  term two
  EOF
  ```

  Old files are rewritten immediately. Files changed in the last 10 minutes
  are skipped, because a running session is still appending to them; this
  session's transcript and the prompt log are among them. `--follow` hands the
  skipped files to a detached watcher. The watcher keeps the terms in memory
  only, and it redacts each file once the file has been untouched for 10
  minutes, which includes after the session exits. Passing the terms on stdin
  keeps them out of the watcher's process arguments. The watcher stops when
  every file it was given has been redacted, or after 24 hours.

### 5. Verify

Run scans a, c and d again with the same terms. The only hits left should be
skipped live files, code the user chose to keep, and git history. If anything
else is left, fix it and scan again.

### 6. Report

Keep the report short:

- What was removed: the number of entries in each store.
- What is left, and why.
- **This session.** The watcher erases the session from disk 10 minutes after
  it goes quiet. Until then the session's context still holds the thing, so
  tell the user to end the session (`/clear`, or exit) once they have read the
  report. If the watcher may not finish (the machine sleeps or reboots within
  24 hours), give the user this fallback to run from a plain terminal after the
  session closes. It reads the terms from stdin, and the leading space keeps
  the command out of shell history (fish by default, bash with `ignorespace`,
  zsh with `hist_ignore_space`):
  ` python3 <absolute path of NZ> redact - --skip-recent 0 --apply`
- What this skill cannot reach. Name only the items that apply:
  - Server-side memory in hosted apps (claude.ai, ChatGPT and others). The
    user clears it in that app's settings.
  - Backups, cloud sync, other machines, git history, and remote stores that
    have no delete tool.

## Rules

- **Leave no tombstone.** Do not write a memory, note or doc line saying the
  thing was forgotten, or naming it as something to avoid. A line like that
  brings the thing back. If the user wants a guard against it, ask them how to
  word it without the name.
- In the report, refer to the thing in the user's own words. Do not summarize
  what was erased.
- Scouts only read and report. Only you edit.
- When you edit part of a memory, keep the rest intact. If nothing useful is
  left, delete the file.
