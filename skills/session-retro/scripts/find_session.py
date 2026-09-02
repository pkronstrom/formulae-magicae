#!/usr/bin/env python3
"""Locate agent session transcripts on this machine, across hosts.

Usage:
  find_session.py resolve <session-id>            where is this session's transcript
  find_session.py list [--project DIR]            recent sessions, newest first
  find_session.py similar <session-id>            sessions from the same working directory

Options:
  --host {claude,codex,opencode,all}   default: all
  --limit N                            default: 20
  --since YYYY-MM-DD                   only sessions modified on/after this date
  --json                               machine-readable output

Session ids may be given in full or as a unique prefix. Hosts store transcripts
differently, so the resolved `path` is a file for Claude and Codex and a
directory of message files for OpenCode; `meta` names the metadata file when the
host keeps one separately.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_PROJECTS = Path(os.environ.get("CLAUDE_PROJECTS_DIR", HOME / ".claude/projects"))
CODEX_SESSIONS = Path(os.environ.get("CODEX_SESSIONS_DIR", HOME / ".codex/sessions"))
OPENCODE_STORAGE = Path(
    os.environ.get("OPENCODE_STORAGE_DIR", HOME / ".local/share/opencode/storage")
)

CODEX_ROLLOUT = re.compile(r"^rollout-.*?-([0-9a-fA-F-]{36})\.jsonl$")


class Session(dict):
    """A located session. Keys: host, id, path, meta, cwd, title, mtime."""

    @property
    def when(self):
        return dt.datetime.fromtimestamp(self["mtime"]).strftime("%Y-%m-%d %H:%M")


def _head_field(path, field, lines=5):
    """First value of `field` in the opening JSON lines of a transcript."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _ in range(lines):
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for scope in (rec, rec.get("payload") or {}):
                    if isinstance(scope, dict) and scope.get(field):
                        return scope[field]
    except OSError:
        pass
    return None


def claude_sessions():
    if not CLAUDE_PROJECTS.is_dir():
        return
    for path in CLAUDE_PROJECTS.glob("*/*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        yield Session(
            host="claude",
            id=path.stem,
            path=str(path),
            meta=None,
            cwd=None,  # resolved lazily; reading every transcript head is slow
            title=None,
            mtime=mtime,
            _slug=path.parent.name,
        )


def codex_sessions():
    if not CODEX_SESSIONS.is_dir():
        return
    for path in CODEX_SESSIONS.rglob("rollout-*.jsonl"):
        match = CODEX_ROLLOUT.match(path.name)
        if not match:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        yield Session(
            host="codex",
            id=match.group(1),
            path=str(path),
            meta=None,
            cwd=None,
            title=None,
            mtime=mtime,
        )


def opencode_sessions():
    root = OPENCODE_STORAGE / "session"
    if not root.is_dir():
        return
    for path in root.glob("*/ses_*.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        messages = OPENCODE_STORAGE / "message" / meta.get("id", "")
        updated = (meta.get("time") or {}).get("updated")
        mtime = updated / 1000 if isinstance(updated, (int, float)) else path.stat().st_mtime
        yield Session(
            host="opencode",
            id=meta.get("id", path.stem),
            path=str(messages if messages.is_dir() else path),
            meta=str(path),
            cwd=meta.get("directory"),
            title=meta.get("title"),
            mtime=mtime,
        )


LOADERS = {
    "claude": claude_sessions,
    "codex": codex_sessions,
    "opencode": opencode_sessions,
}


def fill_cwd(session):
    """Resolve a session's working directory, reading the transcript if needed."""
    if session.get("cwd"):
        return session["cwd"]
    path = Path(session["path"])
    if session["host"] in ("claude", "codex") and path.is_file():
        session["cwd"] = _head_field(path, "cwd")
    if not session.get("cwd") and session.get("_slug"):
        # Claude's directory slug is a lossy encoding of the path; good enough
        # for grouping when the transcript itself does not say.
        session["cwd"] = "/" + session["_slug"].strip("-").replace("-", "/")
    return session.get("cwd")


def collect(hosts, since=None):
    sessions = []
    for host in hosts:
        sessions.extend(LOADERS[host]())
    if since:
        sessions = [s for s in sessions if s["mtime"] >= since]
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


def find_by_id(sessions, session_id):
    exact = [s for s in sessions if s["id"] == session_id]
    if exact:
        return exact
    return [s for s in sessions if s["id"].startswith(session_id)]


def emit(rows, as_json, header=None):
    for row in rows:
        row.pop("_slug", None)
    if as_json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return
    if header:
        print(header + "\n")
    if not rows:
        print("no sessions found")
        return
    for row in rows:
        title = row.get("title") or ""
        print(f"{row['host']:<9} {Session(row).when}  {row['id']}")
        print(f"          {row.get('cwd') or '?'}{'  — ' + title if title else ''}")
        print(f"          {row['path']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["resolve", "list", "similar"])
    ap.add_argument("session_id", nargs="?")
    ap.add_argument("--host", choices=[*LOADERS, "all"], default="all")
    ap.add_argument("--project", help="only sessions whose working directory is under this path")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--since", help="YYYY-MM-DD")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    hosts = list(LOADERS) if args.host == "all" else [args.host]
    since = None
    if args.since:
        since = dt.datetime.strptime(args.since, "%Y-%m-%d").timestamp()
    sessions = collect(hosts, since)

    if args.mode == "resolve":
        if not args.session_id:
            ap.error("resolve needs a session id")
        hits = find_by_id(sessions, args.session_id)
        for hit in hits:
            fill_cwd(hit)
        if not hits:
            print(f"no session matching '{args.session_id}' in {', '.join(hosts)}")
            return 1
        emit(hits[: args.limit], args.json)
        return 0

    if args.mode == "similar":
        if not args.session_id:
            ap.error("similar needs a session id")
        hits = find_by_id(sessions, args.session_id)
        if not hits:
            print(f"no session matching '{args.session_id}'")
            return 1
        anchor = hits[0]
        target = fill_cwd(anchor)
        if not target:
            print("could not determine the anchor session's working directory")
            return 1
        rows = []
        for s in sessions:
            if s["id"] == anchor["id"]:
                continue
            if fill_cwd(s) == target:
                rows.append(s)
            if len(rows) >= args.limit:
                break
        emit(rows, args.json, header=f"sessions from {target} (anchor {anchor['id']})")
        return 0

    rows = []
    for s in sessions:
        if args.project:
            if not (fill_cwd(s) or "").startswith(str(Path(args.project).expanduser())):
                continue
        else:
            fill_cwd(s)
        rows.append(s)
        if len(rows) >= args.limit:
            break
    emit(rows, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
