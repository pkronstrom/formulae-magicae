---
name: harness-security-audit
description: "Audit the live Claude Code and Codex setup (settings, permissions, hooks, MCP servers, agents, skills, enabled plugins, project trust) with a pinned AgentShield scan, then triage the findings against how the harness is really used. /harness-security-audit."
disable-model-invocation: true
---

# Harness Security Audit

A deterministic scanner finds the patterns; you decide which ones matter. The
scanner alone is not the audit: on a real setup it reports hundreds of
findings, and almost all of them are noise. The value is the triage.

## Hard rules

- **Pinned scanner, no install scripts.** `ecc-agentshield@1.6.0`, installed
  with `--ignore-scripts` into a cache directory. Never `npx ecc-agentshield`
  unpinned: it would run whatever version npm serves today over your
  credential files. Raise the pin only after reading the new version's diff.
- **Never** pass `--fix`, `--sandbox`, `--injection`, `--opus` or `--deep`.
  `--sandbox` executes your hooks; `--opus`/`--deep` send your config to an
  API. Fixes go through the approval step below.
- **Scan the staged copy, never `~/.claude` or `~/.codex` directly.** Raw
  roots include session logs, job worktrees and marketplace clones that are
  never loaded. One trial produced 53 GB of copies by following skill symlinks
  and 1,205 findings, nearly all from inactive marketplace repos.
- **Never print a secret.** Name the file, line and kind only.

## 1 — Install the pinned scanner (once)

```bash
C=~/.cache/harness-security-audit
[ -x $C/node_modules/.bin/agentshield ] || {
  mkdir -p $C && npm install --prefix $C --ignore-scripts --no-audit --no-fund ecc-agentshield@1.6.0
}
```

## 2 — Stage what is actually live

```bash
D=<this skill's directory>/scripts
OUT=$(mktemp -d)/stage
python3 $D/stage.py $OUT --project "$PWD"    # omit --project outside a repo
```

It copies the user-level config, hooks, agents, commands, skills (symlinks
followed, files over 512 KB and media skipped), the statusline script, and
only the plugins that are both installed and enabled. For Codex: `config.toml`,
`hooks.json`, `AGENTS.md`, rules, agents and `~/.agents/skills`. With
`--project`, the repo's agent config and package-manager files. It prints
each staged root and its file count; a root with zero files is not scanned.

## 3 — Scan each root

```bash
for r in $OUT/*/; do
  $C/node_modules/.bin/agentshield scan --path "$r" --format json \
    --output "$OUT/../$(basename $r).json" >/dev/null 2>&1
done   # exit 1/2 means findings, not failure; check the JSON exists
python3 $D/triage.py $OUT/../*.json
```

`triage.py` drops rule families that are noise for a personal harness (and
shows the counts, so nothing disappears silently), splits **yours** from
**plugin**, and hides secret evidence.

## 4 — Triage every remaining finding

Open the file at the line for each one. Classify:

- **Real** — the setting is live and widens what an agent or a cloned repo can
  do. Examples from a real run: Codex `trust_level = "trusted"` on `/` or on
  the home directory (every cloned repo's project config loads unprompted); an
  MCP server launched with `npx -y` and no version; no deny list at all.
- **Intentional** — real, but the user chose it: a worker agent with full
  tools, a statusline script they wrote, `skipDangerousModePermissionPrompt`.
  Say what it costs in one line and move on.
- **False positive** — the pattern matched text, not behaviour: "ignore
  previous instructions" inside a reviewer's *description of an attack*, a
  lockfile integrity hash read as an Azure key, a third-party plugin's
  example config.

Plugin findings matter only if they change what runs: a hook, an MCP server,
a script. Prose in a plugin's docs is not an attack surface.

## 5 — Present, approve, apply

One table, most severe first: finding · file:line · real / intentional /
false positive · proposed fix. Fixes are config edits, so make each one only
after the user approves it, and show the diff. For the
Codex trust entries, propose trusting the specific project directories the
user actually works in rather than deleting trust outright.

Then save a baseline per root so the next run shows only what changed:

```bash
for r in $OUT/*/; do
  $C/node_modules/.bin/agentshield scan --path "$r" \
    --save-baseline ~/.config/harness-security-audit/$(basename $r).baseline.json >/dev/null 2>&1
done
```

Next time, stage again and scan each root with `--baseline <its file>` in the
default terminal format (the JSON report has no comparison). Read the
`Baseline Comparison Report` at the end: triage only `NEW FINDINGS`.

## Adding to the noise list

`triage.py`'s `NOISE` list holds rule families checked against real findings.
Add one only after reading several of its hits and confirming none is real.
Never add one to improve the grade.
