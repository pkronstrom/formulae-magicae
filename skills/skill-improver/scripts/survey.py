#!/usr/bin/env python3
"""Rank skills/commands by real usage and by how stale their last review is.

Usage:
  survey.py [--days 60] [--min-sessions 2] [--limit 25] [--projects DIR]
            [--ledgers DIR] [--json]

Answers "what is worth improving next" from two facts the filesystem already
knows: how often each skill actually ran, and when it was last reviewed. The
interesting cell is heavy use with no review behind it.
"""
import argparse, json, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Only unambiguous invocation markers. A path like /<name>/SKILL.md is skipped
# on purpose: it shows up in `git status` and `ls` output constantly, which in a
# whole-corpus scan would bury the real signal under repo noise.
SKILL_TOOL = re.compile(r'"skill"\s*:\s*"([\w.:-]+)"')
SLASH_CMD = re.compile(r'<command-name>/?([\w.:-]+)</command-name>')
# Must be the tool_use `name` field. A bare mcp__server__tool string also appears
# in the deferred-tool listing of every session's system prompt, so the loose
# pattern reports availability, not use, and buries real signal under it.
MCP_TOOL = re.compile(r'"name"\s*:\s*"mcp__([\w-]+)__')

# Harness built-ins arrive as <command-name> but are not editable targets.
BUILTINS = {
    "clear", "model", "rename", "compact", "help", "config", "cost", "init",
    "review", "vim", "terminal-setup", "logout", "login", "resume", "status",
    "doctor", "bug", "release-notes", "memory", "add-dir", "agents", "mcp",
    "permissions", "hooks", "export", "todos", "context", "usage", "fast",
    "tasks", "workflows", "artifacts", "feedback", "privacy-settings",
}

def resolve(name: str, kind: str):
    """Where the target actually lives, or None if it is not an editable artefact."""
    if kind == "mcp":
        return "(mcp server)"
    cands = [
        Path.home() / ".claude/skills" / name / "SKILL.md",
        Path.home() / ".claude/commands" / f"{name}.md",
        Path.home() / ".config/hawk-hooks/registry/prompts" / f"{name}.md",
        Path.home() / ".config/hawk-hooks/registry/skills" / name / "SKILL.md",
    ]
    cands += list((Path.home() / ".claude/plugins").glob(f"*/skills/{name}/SKILL.md"))
    cands += list((Path.home() / ".claude/plugins").glob(f"*/*/skills/{name}/SKILL.md"))
    for c in cands:
        if c.exists():
            return str(c).replace(str(Path.home()), "~")
    return None

def scan(projects: Path, cutoff: float):
    sessions = defaultdict(set)      # name -> {session file}
    hits = defaultdict(int)
    kinds = {}
    last_used = {}
    files = [f for f in projects.rglob("*.jsonl") if f.stat().st_mtime >= cutoff]
    for f in files:
        mtime = f.stat().st_mtime
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for pat, kind in ((SKILL_TOOL, "skill"), (SLASH_CMD, "command"), (MCP_TOOL, "mcp")):
            for m in pat.finditer(text):
                name = m.group(1).split(":")[-1]
                if kind == "command" and name in BUILTINS:
                    continue
                kinds.setdefault(name, kind)
                sessions[name].add(f)
                hits[name] += 1
                if mtime > last_used.get(name, 0):
                    last_used[name] = mtime
    return sessions, hits, kinds, last_used, len(files)

def last_review(ledgers: Path, name: str):
    """Most recent run date recorded in the target's ledger, or None."""
    led = ledgers / name / "ledger.md"
    if not led.exists():
        return None
    dates = re.findall(r"^##\s+(\d{4}-\d{2}-\d{2})", led.read_text(), re.M)
    if not dates:
        return None
    return max(datetime.strptime(d, "%Y-%m-%d") for d in dates)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--min-sessions", type=int, default=2)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--ledgers", default=os.path.expanduser("~/.claude/skill-improver"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    now = datetime.now()
    cutoff = (now - timedelta(days=a.days)).timestamp()
    sessions, hits, kinds, last_used, nfiles = scan(Path(a.projects), cutoff)
    ledgers = Path(a.ledgers)

    rows = []
    for name, sess in sessions.items():
        n = len(sess)
        if n < a.min_sessions:
            continue
        kind = kinds[name]
        home = resolve(name, kind)
        if home is None:
            continue          # not an artefact we could edit; nothing to improve
        rev = last_review(ledgers, name)
        # Sessions recorded after the last review are the evidence a re-run
        # would actually have to work with; without them a review repeats itself.
        fresh = n if rev is None else sum(
            1 for f in sess if datetime.fromtimestamp(f.stat().st_mtime) > rev)
        age = None if rev is None else (now - rev).days
        rows.append({"name": name, "kind": kind, "home": home,
                     "sessions": n, "invocations": hits[name],
                     "last_used": datetime.fromtimestamp(last_used[name]).strftime("%Y-%m-%d"),
                     "last_review": rev.strftime("%Y-%m-%d") if rev else None,
                     "review_age_days": age, "new_sessions": fresh})

    def priority(r):
        if r["new_sessions"] < 4:
            return "thin"                                  # not enough new evidence yet
        if r["last_review"] is None:
            return "never reviewed"
        if r["review_age_days"] >= 90:
            return "stale"
        return "recent"

    order = {"never reviewed": 0, "stale": 1, "thin": 2, "recent": 3}
    for r in rows:
        r["priority"] = priority(r)
    rows.sort(key=lambda r: (order[r["priority"]], -r["new_sessions"], -r["sessions"]))
    rows = rows[:a.limit]

    if a.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"{len(rows)} candidates from {nfiles} sessions in the last {a.days} days\n")
    print(f"{'target':<26} {'kind':<8} {'sess':>5} {'new':>5} {'last used':>11}  {'last review':>13}  priority")
    print("-" * 88)
    for r in rows:
        rev = r["last_review"] or "never"
        if r["review_age_days"] is not None:
            rev += f" ({r['review_age_days']}d)"
        print(f"{r['name']:<26} {r['kind']:<8} {r['sessions']:>5} {r['new_sessions']:>5} "
              f"{r['last_used']:>11}  {rev:>13}  {r['priority']}")

if __name__ == "__main__":
    main()
