#!/usr/bin/env python3
"""Render the part of a session transcript where a target skill was actually used.

Usage:
  extract_usage.py <transcript.jsonl> <target> [-o OUT.md] [--before 2] [--max-turns 0]
                   [--trunc 1200] [--thinking] [--metrics-only]

Produces a readable episode plus a metrics block. Raw trace text is preserved and
only long tool payloads are truncated: pre-summarising a trace throws away exactly
the small surprises (a retry, a correction, a wasted read) that a skill review is
looking for, so keep the evidence and let the reader do the compressing.
"""
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path
from collections import Counter

INTERRUPT = re.compile(r"\[Request interrupted|user doesn't want to|user has denied|"
                       r"tool use was rejected|Claude requested permissions", re.I)

def blocks(msg):
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []

def clip(s, n):
    s = s if isinstance(s, str) else json.dumps(s, default=str)
    s = s.strip()
    return s if len(s) <= n else s[:n] + f"\n… [+{len(s)-n} chars truncated]"

def target_hit(line, target, rec=None):
    t = re.escape(target)
    if (re.search(r'"skill"\s*:\s*"(?:[\w.-]+:)?%s"' % t, line)
            or re.search(r'<command-name>/?(?:[\w.-]+:)?%s</command-name>' % t, line)
            or re.search(r'"mcp__%s__' % t, line)):
        return True
    # A path match only counts inside an assistant tool input: `git status` and
    # `ls` output mention SKILL.md paths constantly, and those are results.
    pat = re.compile(r'[/\\]%s[/\\]SKILL\.md' % t)
    if not pat.search(line) or not isinstance(rec, dict) or rec.get("type") != "assistant":
        return False
    content = (rec.get("message") or {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        and pat.search(json.dumps(b.get("input"), default=str))
        for b in content)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript"); ap.add_argument("target")
    ap.add_argument("-o", "--out")
    ap.add_argument("--before", type=int, default=2, help="user turns of lead-in to keep")
    ap.add_argument("--max-turns", type=int, default=10,
                    help="stop after N user turns past the invocation (0 = run to end of session)")
    ap.add_argument("--trunc", type=int, default=1200)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--metrics-only", action="store_true")
    a = ap.parse_args()

    recs, start = [], None
    for line in Path(a.transcript).open(errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") not in ("user", "assistant", "system"):
            continue
        recs.append(d)
        if start is None and target_hit(line, a.target, d):
            start = len(recs) - 1

    if start is None:
        print(f"'{a.target}' not used in this transcript", file=sys.stderr)
        return 1

    # rewind past a few user turns so the request that led here is visible
    def is_user_turn(d):
        """Tool results are also type=user, so a naive check counts them as turns
        and starts the episode mid-result. Require actual typed text."""
        if d.get("type") != "user" or d.get("isMeta"):
            return False
        bs = blocks(d.get("message") or {})
        if any(b.get("type") == "tool_result" for b in bs):
            return False
        return any(b.get("type") == "text" and b.get("text", "").strip() for b in bs)

    i, seen = start, 0
    while i > 0 and seen < a.before:
        i -= 1
        if is_user_turn(recs[i]):
            seen += 1
    episode = recs[i:]

    tools, errs, interrupts = Counter(), 0, 0
    tok = Counter()
    stamps = []
    lines, uturns, pending = [], 0, {}

    for d in episode:
        if d.get("timestamp"):
            stamps.append(d["timestamp"])
        typ, msg = d.get("type"), d.get("message") or {}
        if typ == "assistant":
            u = msg.get("usage") or {}
            tok["out"] += u.get("output_tokens", 0)
            tok["in"] += u.get("input_tokens", 0)
            tok["cache_write"] += u.get("cache_creation_input_tokens", 0)
            tok["cache_read"] += u.get("cache_read_input_tokens", 0)
            for b in blocks(msg):
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    lines.append(f"\n**CLAUDE:** {clip(b['text'], a.trunc)}")
                elif bt == "thinking" and a.thinking and b.get("thinking", "").strip():
                    lines.append(f"\n*(thinking)* {clip(b['thinking'], a.trunc)}")
                elif bt == "tool_use":
                    tools[b.get("name")] += 1
                    pending[b.get("id")] = b.get("name")
                    lines.append(f"\n  → {b.get('name')}({clip(b.get('input'), 320)})")
        elif typ == "user":
            raw = json.dumps(msg, default=str)
            if INTERRUPT.search(raw):
                interrupts += 1
            toolres = [b for b in blocks(msg) if b.get("type") == "tool_result"]
            if toolres:
                for b in toolres:
                    bad = b.get("is_error")
                    errs += bool(bad)
                    name = pending.get(b.get("tool_use_id"), "tool")
                    tag = "ERROR" if bad else "result"
                    lines.append(f"    ← {name} {tag}: {clip(b.get('content'), a.trunc//2)}")
            elif is_user_turn(d):
                uturns += 1
                if a.max_turns and uturns > a.max_turns:
                    lines.append("\n*(episode truncated at --max-turns)*")
                    break
                txt = "".join(b.get("text", "") for b in blocks(msg) if b.get("type") == "text")
                if txt.strip():
                    lines.append(f"\n---\n**USER:** {clip(txt, a.trunc)}")
        elif typ == "system" and d.get("content"):
            c = str(d["content"])
            if INTERRUPT.search(c):
                interrupts += 1
                lines.append(f"\n  ⚠ {clip(c, 300)}")

    # Sessions get resumed hours or days later, so end-minus-start is meaningless.
    # Sum the gaps between consecutive records and drop anything over IDLE_GAP,
    # which leaves roughly the time the model and user were actually working.
    IDLE_GAP = 900  # seconds
    active = idle = 0.0
    try:
        ts = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]
        for x, y in zip(ts, ts[1:]):
            g = (y - x).total_seconds()
            if 0 <= g <= IDLE_GAP:
                active += g
            elif g > IDLE_GAP:
                idle += g
    except Exception:
        pass
    dur = f"{active/60:.1f} min active" + (f" (+{idle/3600:.1f} h idle/resumed)" if idle > IDLE_GAP else "")

    head = [f"# Usage episode — `{a.target}`",
            f"source: `{a.transcript}`", "",
            "## Metrics", "",
            f"- user turns in episode: {uturns}",
            f"- wall clock: {dur or 'unknown'}",
            f"- tokens: {tok['out']:,} out, {tok['in']:,} fresh in, "
            f"{tok['cache_write']:,} cache-write, {tok['cache_read']:,} cache-read",
            f"- tool calls: {sum(tools.values())} — " + ", ".join(f"{k}×{v}" for k, v in tools.most_common(12)),
            f"- tool errors: {errs}",
            f"- interruptions / permission denials: {interrupts}", ""]
    out = "\n".join(head) if a.metrics_only else "\n".join(head + ["## Trace", ""] + lines)

    if a.out:
        Path(a.out).write_text(out)
        print(f"wrote {a.out} ({len(out):,} chars)")
    else:
        print(out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
