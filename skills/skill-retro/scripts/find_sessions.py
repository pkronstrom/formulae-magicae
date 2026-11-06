#!/usr/bin/env python3
"""Find Claude Code sessions where a target skill/command/MCP server was used.

Usage:
  find_sessions.py <target> [--limit N] [--since YYYY-MM-DD] [--projects DIR] [--json]

Matching is deliberately broad: a skill leaves different traces depending on how
it was reached (Skill tool, slash command, a plugin-qualified name, or the model
just reading SKILL.md). Missing a real usage is worse than one false positive,
which the extraction step filters out anyway.
"""
import argparse, json, os, re, sys
from pathlib import Path

def markers(target: str):
    t = re.escape(target)
    return [
        ("skill-tool", re.compile(r'"skill"\s*:\s*"(?:[\w.-]+:)?%s"' % t)),
        ("slash-command", re.compile(r'<command-name>/?(?:[\w.-]+:)?%s</command-name>' % t)),
        ("read-skill-md", re.compile(r'[/\\]%s[/\\]SKILL\.md' % t)),
        ("mcp-tool", re.compile(r'"mcp__%s__' % t)),
        ("subagent", re.compile(r'"subagent_type"\s*:\s*"(?:[\w.-]+:)?%s"' % t)),
    ]

def real_read(line, pat):
    """A skill's path shows up in `git status` and `ls` output constantly, and
    those are tool RESULTS, not the model opening the file. Only count the path
    when it appears in an assistant's tool input."""
    try:
        d = json.loads(line)
    except Exception:
        return False
    if d.get("type") != "assistant":
        return False
    msg = d.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            if pat.search(json.dumps(b.get("input"), default=str)):
                return True
    return False


def scan(path: Path, pats):
    hits, first, last, cwd, sid = 0, None, None, None, None
    kinds = set()
    try:
        with path.open(errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                m = [k for k, p in pats if p.search(line)]
                if "read-skill-md" in m:
                    rp = dict(pats)["read-skill-md"]
                    if not real_read(line, rp):
                        m.remove("read-skill-md")
                if m:
                    kinds.update(m)
                    hits += 1
                    if first is None:
                        first = n
                    last = n
                    if cwd is None:
                        try:
                            d = json.loads(line)
                            cwd, sid = d.get("cwd"), d.get("sessionId")
                        except Exception:
                            pass
    except OSError:
        return None
    if not hits:
        return None
    if sid is None:
        sid = path.stem
    return {"file": str(path), "session_id": sid, "cwd": cwd,
            "hits": hits, "first_line": first, "last_line": last,
            "matched": sorted(kinds),
            "mtime": path.stat().st_mtime, "size": path.stat().st_size}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--since", help="only sessions modified on/after this date (YYYY-MM-DD)")
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cutoff = 0.0
    if a.since:
        import datetime
        cutoff = datetime.datetime.strptime(a.since, "%Y-%m-%d").timestamp()

    pats = markers(a.target)
    files = sorted(Path(a.projects).rglob("*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files:
        if f.stat().st_mtime < cutoff:
            continue
        r = scan(f, pats)
        if r:
            out.append(r)
            if len(out) >= a.limit:
                break

    if a.json:
        print(json.dumps(out, indent=2))
        return
    if not out:
        print(f"no sessions found using '{a.target}' (searched {len(files)} transcripts)")
        return
    import datetime
    print(f"{len(out)} session(s) using '{a.target}', newest first:\n")
    for r in out:
        when = datetime.datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M")
        proj = (r["cwd"] or Path(r["file"]).parent.name).replace(os.path.expanduser("~"), "~")
        print(f"  {when}  hits={r['hits']:<3} via {','.join(r['matched'])}  {proj}")
        print(f"     {r['file']}")

if __name__ == "__main__":
    main()
