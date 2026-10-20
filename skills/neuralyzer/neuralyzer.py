#!/usr/bin/env python3
"""Find and erase what coding agents remember about a thing.

  neuralyzer.py list   [--all] [--project DIR]
  neuralyzer.py scan   TERM... [--tier memory,skills,history] [--word] [--root DIR]... [--limit N]
  neuralyzer.py redact TERM... [--tier history,memory] [--word] [--root DIR]... [--skip-recent MIN] [--apply [--follow]]

Tiers:
  memory   agent memory: Claude Code project memory, global CLAUDE.md and rules,
           Codex AGENTS.md and memories (markdown + sqlite), GEMINI.md, OpenCode AGENTS.md
  skills   installed skills, commands, agents and plugins, resolved to their source
  history  everything else under the harness homes: transcripts, prompt logs,
           file snapshots, caches, app databases (Claude Code, Codex, Gemini, OpenCode)

TERM "-" reads terms from stdin, one per line, keeping them out of argv and shell
history. Matching is case-insensitive; --word anchors to word edges.

redact is a dry run unless --apply. It rewrites history files and memory-tier
databases, replacing each match with [neuralyzed]. Memory markdown, skills and
project docs are edited by the agent, not here. Settings and credential files
are reported, never rewritten. Files modified in the last --skip-recent minutes
(default 10) are skipped, so live sessions are left alone.

--follow erases the live session too: a detached watcher keeps the terms in
memory and redacts each skipped file once it has been untouched for
--skip-recent minutes, also after the session exits. It gives up after 24 hours.
Pass the terms on stdin ("-") so they are not visible in the watcher's argv.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
CLAUDE = Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")
CODEX = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
GEMINI = HOME / ".gemini"
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")

MARK = "[neuralyzed]"
FOLLOW_HOURS = 24
SQLITE_MAGIC = b"SQLite format 3\0"
SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
# Configuration and credentials, not memory: reported, never rewritten.
CONFIG_NAME = re.compile(
    r"settings|config|auth|credential|oauth|token|secret|keybinding|installation_id"
    r"|\.claude\.json|\.env", re.I)
# Installed code under a harness home, not anything an agent wrote down.
NOT_HISTORY = {"skills", "plugins", "commands", "agents", "prompts", "packages",
               "vendor_imports", "node_repl", "node_modules", "bin", ".git"}
INSTRUCTION_FILES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md"}


# ---------------------------------------------------------------- stores

def memory_paths():
    paths = sorted(CLAUDE.glob("projects/*/memory"))
    paths += [CLAUDE / "CLAUDE.md", CLAUDE / "rules", CODEX / "AGENTS.md",
              CODEX / "memories", GEMINI / "GEMINI.md", XDG_CONFIG / "opencode/AGENTS.md"]
    paths += sorted(CODEX.glob("memories*.sqlite"))
    return [p for p in paths if p.exists()]


def skill_paths():
    paths = [CLAUDE / name for name in ("skills", "commands", "agents", "plugins")]
    paths += [CODEX / name for name in ("skills", "prompts", "agents")]
    paths += [HOME / ".agents/skills", GEMINI / "commands", GEMINI / "skills",
              XDG_CONFIG / "opencode"]
    return [p for p in paths if p.exists()]


def history_roots(extra):
    roots = [CLAUDE, CODEX, GEMINI, XDG_DATA / "opencode", *map(Path, extra)]
    return [p for p in roots if p.exists()]


def under(path, bases):
    return any(path == b or b in path.parents for b in bases)


def history_kind(path, roots, memory):
    """'history', 'config', or None when the file belongs to another tier."""
    if path.is_symlink() or under(path, memory):
        return None
    root = max((r for r in roots if r in path.parents), key=lambda r: len(r.parts), default=None)
    if root is None:
        return None
    rel = path.relative_to(root).parts
    if rel[0] in NOT_HISTORY or (len(rel) == 1 and path.name in INSTRUCTION_FILES):
        return None
    return "config" if CONFIG_NAME.search(path.name) else "history"


def group_of(path, roots):
    root = max((r for r in roots if r in path.parents), key=lambda r: len(r.parts))
    rel = path.relative_to(root).parts
    return f"{root.name.lstrip('.')}/{rel[0]}" if len(rel) > 1 else root.name.lstrip(".")


# ---------------------------------------------------------------- matching

def pattern(terms, word):
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"\b(?:{alts})\b" if word else alts, re.I)


def walk(root, follow, max_depth=None):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if d != ".git"
                       and (max_depth is None or depth + 1 < max_depth)]
        for name in filenames:
            path = Path(dirpath, name)
            if follow or not path.is_symlink():
                yield path


def matching_files(terms, roots, word, follow=False):
    """{path: matches} for text files under roots that contain any term."""
    files = [r for r in roots if r.is_file()]
    dirs = [r for r in roots if r.is_dir()]
    if not files + dirs:
        return {}
    if shutil.which("rg"):
        cmd = ["rg", "--count-matches", "--with-filename", "--null", "-i", "-F",
               "--hidden", "--no-ignore", "--no-messages"]
        cmd += ["-w"] if word else []
        cmd += ["-L"] if follow else []
        for term in terms:
            cmd += ["-e", term]
        out = subprocess.run(cmd + ["--", *map(str, files + dirs)], capture_output=True).stdout
        return {Path(m.group(1).decode(errors="surrogateescape")): int(m.group(2))
                for m in re.finditer(rb"(.+?)\0(\d+)\n", out, re.S)}
    rx = pattern(terms, word)
    found = {}
    for path in files + [p for d in dirs for p in walk(d, follow)]:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" not in data[:4096]:
            n = len(rx.findall(data.decode(errors="ignore")))
            if n:
                found[path] = n
    return found


def sqlite_files(roots):
    """SQLite databases near the top of each root (deeper ones are tool scratch)."""
    dirs = [str(r) for r in roots if r.is_dir()]
    if shutil.which("fd") and dirs:
        cmd = ["fd", "-H", "-I", "-t", "f", "--max-depth", "3", "-0",
               *[a for s in SQLITE_SUFFIXES for a in ("-e", s[1:])], ".", *dirs]
        out = subprocess.run(cmd, capture_output=True).stdout
        candidates = [Path(p.decode(errors="surrogateescape")) for p in out.split(b"\0") if p]
    else:
        candidates = [p for d in dirs for p in walk(Path(d), False, max_depth=3)
                      if p.suffix in SQLITE_SUFFIXES]
    candidates += [r for r in roots if r.is_file() and r.suffix in SQLITE_SUFFIXES]
    out = []
    for path in candidates:
        if CONFIG_NAME.search(path.name) or path.is_symlink():
            continue
        try:
            with path.open("rb") as fh:
                if fh.read(16) == SQLITE_MAGIC:
                    out.append(path)
        except OSError:
            pass
    return sorted(set(out))


def is_text(path):
    try:
        with path.open("rb") as fh:
            return b"\0" not in fh.read(4096)
    except OSError:
        return False


def read_text(path):
    return path.read_text(encoding="utf-8", errors="surrogateescape")


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def match_sql(col, terms, ascii_terms):
    """SQL condition true when col matches, and its arguments."""
    if not ascii_terms:
        return f"nz_hit({ident(col)})", []
    likes = " OR ".join(f"{ident(col)} LIKE ? ESCAPE '\\'" for _ in terms)
    args = ["%" + re.sub(r"([%_\\])", r"\\\1", t) + "%" for t in terms]
    return f"(({likes}) AND nz_hit({ident(col)}))", args


def sqlite_hits(db, rx, terms, apply):
    """{'table.column': rows} for text cells that match; rewritten when apply."""
    mode = "rw" if apply else "ro"
    con = sqlite3.connect(f"file:{db}?mode={mode}", uri=True, timeout=2)
    try:
        con.create_function("nz_hit", 1, lambda s: isinstance(s, str) and bool(rx.search(s)),
                            deterministic=True)
        con.create_function("nz_sub", 1, lambda s: rx.sub(MARK, s) if isinstance(s, str) else s,
                            deterministic=True)
        if apply:
            con.execute("PRAGMA secure_delete=ON")  # zero the freed pages too
        # LIKE is case-insensitive only for ASCII, so it can only prefilter ASCII terms.
        ascii_terms = all(t.isascii() for t in terms)
        tables = con.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
        virtual = [n for n, sql in tables if (sql or "").upper().startswith("CREATE VIRTUAL")]
        hits = {}
        for table, _ in tables:
            if table.startswith("sqlite_") or any(table.startswith(v + "_") for v in virtual):
                continue
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({ident(table)})")]
            conds = [match_sql(col, terms, ascii_terms) for col in cols]
            sums = ", ".join(f"coalesce(sum({sql}), 0)" for sql, _ in conds)
            args = [a for _, col_args in conds for a in col_args]
            counts = con.execute(f"SELECT {sums} FROM {ident(table)}", args).fetchone()
            for col, (sql, col_args), n in zip(cols, conds, counts):
                if n:
                    hits[f"{table}.{col}"] = n
                    if apply:
                        con.execute(f"UPDATE {ident(table)} SET {ident(col)} = nz_sub({ident(col)}) "
                                    f"WHERE {sql}", col_args)
        if apply:
            con.commit()
            try:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
        return hits
    finally:
        con.close()


# ---------------------------------------------------------------- redaction

def scrub(value, rx):
    if isinstance(value, str):
        return rx.sub(MARK, value)
    if isinstance(value, list):
        return [scrub(v, rx) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, rx) for k, v in value.items()}
    return value


def redact_json_line(line, rx):
    try:
        return json.dumps(scrub(json.loads(line), rx), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        return rx.sub(MARK, line)


def redacted(path, rx):
    raw = read_text(path)
    if path.suffix == ".jsonl":
        return "\n".join(redact_json_line(l, rx) if rx.search(l) else l for l in raw.split("\n"))
    if path.suffix == ".json":
        try:
            data = json.loads(raw)
        except ValueError:
            return rx.sub(MARK, raw)
        indent = re.search(r"\n( +)\S", raw[:400])
        out = json.dumps(scrub(data, rx), ensure_ascii=False,
                         indent=len(indent.group(1)) if indent else None,
                         separators=None if indent else (",", ":"))
        return out + ("\n" if raw.endswith("\n") else "")
    return rx.sub(MARK, raw)


def follow(paths, rx, minutes):
    """Fork a watcher that redacts each path once it has gone quiet."""
    sys.stdout.flush()
    pid = os.fork()
    if pid:
        print(f"following {len(paths)} live files: each is redacted once untouched for "
              f"{minutes:g} min (watcher pid {pid}, gives up after {FOLLOW_HOURS} h)")
        return
    os.setsid()  # survive the harness ending its process group
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):  # release the caller's pipes so its tool call returns
        os.dup2(devnull, fd)
    pending = set(paths)
    deadline = time.time() + FOLLOW_HOURS * 3600
    while pending and time.time() < deadline:
        time.sleep(max(1.0, min(60.0, minutes * 30)))
        for path in list(pending):
            try:
                if time.time() - path.stat().st_mtime < minutes * 60:
                    continue
                if rx.search(read_text(path)):
                    write_keeping_times(path, redacted(path, rx))
            except OSError:
                pass
            pending.discard(path)
    os._exit(0)


def write_keeping_times(path, text):
    st = path.stat()
    tmp = path.with_name(f".{path.name}.neuralyzer-tmp")
    tmp.write_text(text, encoding="utf-8", errors="surrogateescape")
    os.chmod(tmp, st.st_mode & 0o7777)
    os.replace(tmp, path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


# ---------------------------------------------------------------- reporting helpers

def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


_cwd_cache = {}


def cwd_of(transcript):
    """The working directory a Claude Code or Codex transcript was recorded in."""
    if transcript not in _cwd_cache:
        cwd = None
        try:
            with transcript.open("rb") as fh:
                m = re.search(rb'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', fh.read(256 * 1024))
            if m:
                cwd = json.loads(b'"' + m.group(1) + b'"')
        except (OSError, ValueError):
            pass
        _cwd_cache[transcript] = cwd
    return _cwd_cache[transcript]


def unslug(name, base="/"):
    """Walk the filesystem to the directory whose slug is name, if it still exists."""
    rest = name[1:] if base == "/" else name
    try:
        entries = os.listdir(base)
    except OSError:
        return None
    for entry in entries:
        s = slug(entry)
        path = os.path.join(base, entry)
        if rest == s:
            return path
        if rest.startswith(s + "-") and os.path.isdir(path):
            found = unslug(rest[len(s) + 1:], path)
            if found:
                return found
    return None


def project_of(slug_dir):
    for transcript in sorted(slug_dir.glob("*.jsonl"))[:5]:
        cwd = cwd_of(transcript)
        if cwd:
            return cwd
    return unslug(slug_dir.name) or slug_dir.name


def day(path):
    return time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))


def frontmatter(path):
    text = read_text(path)
    meta = {}
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    head, body = (m.group(1), m.group(2)) if m else ("", text)
    for key in ("name", "description", "type"):
        km = re.search(rf"(?m)^\s*{key}:\s*(.+)$", head)
        if km:
            meta[key] = km.group(1).strip().strip("'\"")
    first = next((l.strip("# ").strip() for l in body.splitlines() if l.strip()), "")
    meta.setdefault("name", path.stem)
    meta.setdefault("description", first[:160])
    return meta


def show_lines(path, rx, limit=5):
    try:
        lines = read_text(path).splitlines()
    except OSError:
        return
    hits = [(i, l) for i, l in enumerate(lines, 1) if rx.search(l)]
    for i, line in hits[:limit]:
        print(f"      {i}: {line.strip()[:160]}")
    if len(hits) > limit:
        print(f"      … +{len(hits) - limit} more lines")


# ---------------------------------------------------------------- commands

def cmd_list(args):
    here = Path(args.project).resolve()
    slugs = {slug(here)}
    top = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    if top:
        slugs.add(slug(Path(top)))
    dirs = sorted(CLAUDE.glob("projects/*/memory"))
    dirs.sort(key=lambda d: d.parent.name not in slugs)
    print("## Claude Code project memory")
    for d in dirs:
        entries = [frontmatter(p) | {"file": p.relative_to(d)}
                   for p in sorted(d.rglob("*.md")) if p.name != "MEMORY.md"]
        if not entries:
            continue
        current = d.parent.name in slugs
        print(f"\n{project_of(d.parent)}  ({len(entries)}){'  ← this project' if current else ''}")
        print(f"  {d}")
        if current or args.all:
            for e in entries:
                kind = f"[{e['type']}] " if "type" in e else ""
                print(f"  - {e['file']}: {kind}{e['description']}")
    for path in (CLAUDE / "CLAUDE.md", CODEX / "AGENTS.md", GEMINI / "GEMINI.md",
                 XDG_CONFIG / "opencode/AGENTS.md"):
        if path.is_file() and path.stat().st_size:
            print(f"\n## {path}  ({len(read_text(path).splitlines())} lines)")
            if path.parent == GEMINI:
                added = read_text(path).partition("## Gemini Added Memories")[2]
                for line in added.splitlines():
                    if line.startswith("- "):
                        print(f"  {line}")
    for d in (CLAUDE / "rules", CODEX / "memories"):
        files = sorted(d.rglob("*.md")) if d.is_dir() else []
        if files:
            print(f"\n## {d}")
            for p in files:
                print(f"  - {p.relative_to(d)}: {frontmatter(p)['description']}")
    for db in sorted(CODEX.glob("memories*.sqlite")):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            rows = {n: con.execute(f"SELECT count(*) FROM {ident(n)}").fetchone()[0] for n in names}
            con.close()
        except sqlite3.Error as e:
            rows = {"error": str(e)}
        print(f"\n## {db}")
        print("  " + ", ".join(f"{k}: {v}" for k, v in rows.items() if not k.startswith("_")))


def cmd_scan(args, terms):
    rx = pattern(terms, args.word)
    tiers = set(args.tier.split(","))
    memory = memory_paths()
    if "memory" in tiers:
        print("## memory")
        texts = [p for p in memory if p.suffix != ".sqlite"]
        for path, n in sorted(matching_files(terms, texts, args.word).items()):
            if not is_text(path):
                continue
            slug_dir = next((d.parent for d in memory if d.name == "memory" and d in path.parents), None)
            where = f"  [project: {project_of(slug_dir)}]" if slug_dir else ""
            print(f"  {path}  {n}{where}")
            show_lines(path, rx)
        for db in [p for p in memory if p.suffix == ".sqlite"]:
            report_sqlite(db, rx, terms)
    if "skills" in tiers:
        print("## skills  (by resolved path)")
        sources = {}
        for path, n in matching_files(terms, skill_paths(), args.word, follow=True).items():
            if is_text(path):
                sources.setdefault(path.resolve(), [n, []])[1].append(path)
        for real, (n, installed) in sorted(sources.items()):
            print(f"  {real}  {n}")
            for path in sorted(installed):
                if path != real:
                    print(f"    installed as {path}")
            show_lines(real, rx, limit=3)
    if "history" in tiers:
        print("## history  (counts only)")
        roots = history_roots(args.root)
        hist, config = collect_history(terms, roots, memory, args.word)
        report_groups(hist, roots, args.limit)
        for db in [d for d in sqlite_files(roots) if history_kind(d, roots, memory) == "history"]:
            report_sqlite(db, rx, terms)
        if config:
            print("## config and credentials  (reported, never rewritten)")
            for path, n in sorted(config.items()):
                print(f"  {path}  {n}")


def collect_history(terms, roots, memory, word):
    """({path: matches} for history files, {path: matches} for config files)."""
    hist, config = {}, {}
    for path, n in matching_files(terms, roots, word).items():
        kind = history_kind(path, roots, memory)
        if kind and is_text(path):
            (hist if kind == "history" else config)[path] = n
    return hist, config


def report_groups(hits, roots, limit):
    groups = {}
    for path, n in hits.items():
        groups.setdefault(group_of(path, roots), []).append((n, path))
    for name, items in sorted(groups.items()):
        items.sort(key=lambda x: (-x[0], str(x[1])))
        print(f"  {name}: {len(items)} files, {sum(n for n, _ in items)} hits")
        for n, path in items[:limit]:
            cwd = cwd_of(path) if path.suffix == ".jsonl" else None
            print(f"    {path}  {n}  {day(path)}" + (f"  cwd={cwd}" if cwd else ""))
        if len(items) > limit:
            print(f"    … +{len(items) - limit} more files")


def report_sqlite(db, rx, terms):
    try:
        hits = sqlite_hits(db, rx, terms, apply=False)
    except sqlite3.Error as e:
        print(f"  {db}  (sqlite: {e})")
        return
    if hits:
        print(f"  {db}  " + ", ".join(f"{k}: {n} rows" for k, n in hits.items()))


def cmd_redact(args, terms):
    rx = pattern(terms, args.word)
    tiers = set(args.tier.split(","))
    memory = memory_paths()
    roots = history_roots(args.root)
    files, dbs = {}, []
    if "history" in tiers:
        files, _ = collect_history(terms, roots, memory, args.word)
        dbs += [d for d in sqlite_files(roots) if history_kind(d, roots, memory) == "history"]
    if "memory" in tiers:
        dbs += [p for p in memory if p.suffix == ".sqlite"]
    cutoff = time.time() - args.skip_recent * 60
    verb = "redacted" if args.apply else "would redact"
    done, skipped = {}, []
    for path, n in sorted(files.items()):
        if path.stat().st_mtime > cutoff:
            skipped.append(path)
            continue
        if args.apply:
            write_keeping_times(path, redacted(path, rx))
        group = done.setdefault(group_of(path, roots), [0, 0])
        group[0] += 1
        group[1] += n
    for name, (nfiles, nhits) in sorted(done.items()):
        print(f"{verb}  {name}: {nfiles} files, {nhits} hits")
    for db in dbs:
        try:
            hits = sqlite_hits(db, rx, terms, apply=args.apply)
        except sqlite3.Error as e:
            print(f"failed  {db}: {e} — close the app that holds it and rerun")
            continue
        if hits:
            print(f"{verb}  {db}: " + ", ".join(f"{k}: {n} rows" for k, n in hits.items()))
    for path in skipped:
        print(f"skipped {path}  (modified in the last {args.skip_recent:g} min; live session?)")
    if not args.apply:
        print("dry run: nothing written. Add --apply to rewrite.")
    elif args.follow and skipped:
        follow(skipped, rx, args.skip_recent)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="memory entries, current project first")
    ls.add_argument("--all", action="store_true", help="show every project's entries")
    ls.add_argument("--project", default=".", help="project directory (default: cwd)")
    for name, tiers in (("scan", "memory,skills,history"), ("redact", "history,memory")):
        p = sub.add_parser(name)
        p.add_argument("terms", nargs="+", help='terms to match; "-" reads them from stdin')
        p.add_argument("--tier", default=tiers)
        p.add_argument("--word", action="store_true", help="match whole words only")
        p.add_argument("--root", action="append", default=[], help="extra harness home to include")
        if name == "scan":
            p.add_argument("--limit", type=int, default=15, help="files shown per history group")
        else:
            p.add_argument("--skip-recent", type=float, default=10, metavar="MIN")
            p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
            p.add_argument("--follow", action="store_true",
                           help="with --apply: redact skipped live files once they go quiet")
    args = ap.parse_args()
    if args.cmd == "list":
        return cmd_list(args)
    terms = args.terms
    if terms == ["-"]:
        if sys.stdin.isatty():
            print("terms, one per line, then Ctrl-D:", file=sys.stderr)
        terms = [t.strip() for t in sys.stdin.read().splitlines()]
    terms = [t for t in terms if t]
    if not terms:
        ap.error("no terms")
    (cmd_scan if args.cmd == "scan" else cmd_redact)(args, terms)


if __name__ == "__main__":
    main()
