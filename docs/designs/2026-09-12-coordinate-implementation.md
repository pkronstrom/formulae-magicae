# coordinate — implementation plan

Spec: `2026-09-12-coordinate-design.md`. Size: STANDARD (one new skill, one
script, registrations). No changes to `skills/work/`.

## Chunk 1 — `skills/coordinate/coordinate.py`

Stdlib Python 3, one file. Subcommands:

| cmd | does |
|---|---|
| `connect <harness> [selector] [--brief TEXT]` | self from `$TMUX_PANE`, discover peer, write `peers.json`, send intro (+brief) |
| `launch [--worktree NAME]` | `workmux add` if asked; split window; start missing harness(es); register both |
| `send <peer> <text\|->` | drain outbox → readiness → paste → verify → Enter; `delivered\|held\|held-mixed` |
| `flush [--force]` | drain outbox; `--force` skips readiness |
| `status [--json]` | peers, liveness, held count, last 5 log lines |
| `log [-n N]` | tail of `messages.jsonl` |
| `disconnect` | delete `peers.json` |
| `panes <harness>` | debug: ranked candidate panes |
| `ready <pane> <harness>` | debug: readiness verdict + reason |

Internals: `project_key()` (git toplevel or cwd → slug), `state_dir()`,
`pane_harness(pane_id)` (walk `ps` tree from `pane_pid`), `classify(text,
harness) -> (ready, reason)`, `paste(pane, text, key, msg_id)`, file lock via
`fcntl.flock` on `state_dir/lock` around drain+send.

Done when: `python3 coordinate.py ready %<claude-pane> claude` says ready on an
idle pane and not-ready on this one (draft), and unit tests for `classify`
pass on captured fixtures.

## Chunk 2 — `skills/coordinate/SKILL.md` + `LICENSE`

Frontmatter description names `/coordinate`, `$coordinate` and the
`[COORDINATOR MESSAGE]` marker. Body: commands table, how to run the script
(derive path from the skill dir), intro text, protocol (envelope, kinds,
discipline, 2 rounds, trust), receiving rules, role shortcuts, the
"when /work is running" paragraph, fish aliases.

## Chunk 3 — registrations + tests

`.claude-plugin/marketplace.json`, `hawk-package.yaml`, README table + Codex
all-formulae line, `tests/test_repository.py` (EXPECTED_SKILLS and the Codex
install string), `tests/test_coordinate.py` (classifier fixtures, envelope
format, project key). `pytest -q` green.

## Chunk 4 — end-to-end

Scratch tmux window: `launch`-style split with a fresh `claude` (no Codex —
weekly limit nearly out); `connect claude --brief "reply with the single word
pong"` from a shell registered as the fake codex pane; expect an envelope back
via `send`. Kill the scratch window after.
