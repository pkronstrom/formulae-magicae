import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NZ = ROOT / "skills/neuralyzer/neuralyzer.py"
OLD = time.time() - 2 * 86400


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def write(path, text, old=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if old:
        os.utime(path, (OLD, OLD))
    return path


def make_db(path, table, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {table} (body TEXT, n INTEGER)")
    con.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows)
    con.commit()
    con.close()
    return path


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    project = (tmp_path / "proj").resolve()
    project.mkdir()
    claude = home / ".claude"
    mem = claude / "projects" / slug(project) / "memory"
    files = {
        "project": project,
        "index": write(mem / "MEMORY.md", "- [Zorblax](zorblax.md) — the zorblax notes\n"),
        "memory": write(mem / "zorblax.md",
                        "---\nname: zorblax\ndescription: How Zorblax is deployed\n"
                        "metadata:\n  type: project\n---\n\nZorblax runs on port 9.\n"),
        "other": write(mem / "other.md", "---\nname: other\ndescription: Unrelated\n---\nhi\n"),
        "transcript": write(claude / "projects" / slug(project) / "s1.jsonl", "\n".join([
            json.dumps({"type": "user", "cwd": str(project),
                        "message": {"content": "tell me about Zorblax ünïcode"}}, ensure_ascii=False),
            json.dumps({"type": "assistant", "message": {"content": "nothing here"}}),
            "not json but zorblax anyway",
        ]) + "\n"),
        "live": write(claude / "projects" / slug(project) / "live.jsonl",
                      json.dumps({"cwd": str(project), "text": "zorblax now"}) + "\n", old=False),
        "prompts": write(claude / "history.jsonl", json.dumps({"display": "/forget zorblax"}) + "\n"),
        "settings": write(claude / "settings.json", '{"allow": ["Bash(zorblax:*)"]}\n'),
        "skill": write(claude / "skills/demo/SKILL.md", "Use zorblax for demos.\n"),
        "rollout": write(home / ".codex/sessions/2026/01/01/rollout-1.jsonl",
                         json.dumps({"payload": {"cwd": str(project), "text": "ZORBLAX deploy"}}) + "\n"),
        "chat": write(home / ".gemini/tmp/abc/chats/c.json",
                      json.dumps({"messages": [{"text": "zorblax again"}, {"text": "fine"}]}, indent=2) + "\n"),
        "codex_memory": make_db(home / ".codex/memories_1.sqlite", "stage1_outputs",
                                [("Zorblax prefers blue", 1), ("unrelated", 2)]),
        "state": make_db(home / ".codex/state_5.sqlite", "threads", [("zorblax thread", 1)]),
    }
    files["home"] = home
    return files


def run(home, *args, stdin=None, minimal_path=False):
    env = {k: v for k, v in os.environ.items()
           if k not in {"CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"}}
    env["HOME"] = str(home["home"])
    if minimal_path:
        env["PATH"] = "/usr/bin:/bin"
    return subprocess.run([sys.executable, str(NZ), *args], env=env, input=stdin,
                          capture_output=True, text=True, check=True,
                          cwd=home["project"]).stdout


def db_bodies(path):
    con = sqlite3.connect(path)
    rows = [r[0] for r in con.execute("SELECT body FROM " + (
        "stage1_outputs" if "memories" in path.name else "threads"))]
    con.close()
    return rows


def test_list_shows_current_project_memories_and_codex_store(home):
    out = run(home, "list")
    assert f"{home['project']}  (2)  ← this project" in out
    assert "zorblax.md: [project] How Zorblax is deployed" in out
    assert "stage1_outputs: 2" in out


@pytest.mark.parametrize("minimal_path", [False, True], ids=["rg-fd", "stdlib-fallback"])
def test_scan_finds_every_tier(home, minimal_path):
    out = run(home, "scan", "zorblax", minimal_path=minimal_path)
    memory, rest = out.split("## skills")
    skills, history = rest.split("## history")
    assert str(home["memory"]) in memory and str(home["index"]) in memory
    assert str(home["other"]) not in memory
    assert "stage1_outputs.body: 1 rows" in memory
    assert str(home["skill"]) in skills
    assert "claude/projects: 2 files" in history
    assert "codex/sessions: 1 files" in history
    assert "gemini/tmp: 1 files" in history
    assert f"cwd={home['project']}" in history
    assert "threads.body: 1 rows" in history
    config = history.split("## config and credentials")[1]
    assert str(home["settings"]) in config
    assert str(home["skill"]) not in history


def test_redact_is_a_dry_run_by_default(home):
    before = {k: p.read_bytes() for k, p in home.items() if isinstance(p, Path) and p.is_file()}
    out = run(home, "redact", "zorblax")
    assert "would redact" in out and "dry run" in out
    assert before == {k: home[k].read_bytes() for k in before}


def test_redact_apply_rewrites_history_and_memory_databases_only(home):
    mtime = home["transcript"].stat().st_mtime
    out = run(home, "redact", "zorblax", "--apply")

    lines = home["transcript"].read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["message"]["content"] == "tell me about [neuralyzed] ünïcode"
    assert json.loads(lines[1]) == {"type": "assistant", "message": {"content": "nothing here"}}
    assert lines[2] == "not json but [neuralyzed] anyway"
    assert home["transcript"].stat().st_mtime == mtime

    assert "[neuralyzed] deploy" in home["rollout"].read_text()
    chat = home["chat"].read_text()
    assert chat.startswith('{\n  "messages"') and "[neuralyzed] again" in chat
    assert "[neuralyzed]" in home["prompts"].read_text()
    assert db_bodies(home["codex_memory"]) == ["[neuralyzed] prefers blue", "unrelated"]
    assert db_bodies(home["state"]) == ["[neuralyzed] thread"]

    for untouched in ("settings", "memory", "index", "skill", "live"):
        assert "zorblax" in home[untouched].read_text().lower(), untouched
    assert f"skipped {home['live']}" in out


def test_terms_from_stdin_and_skip_recent_zero(home):
    run(home, "redact", "-", "--skip-recent", "0", "--apply", stdin="Zorblax\n\n")
    assert "[neuralyzed]" in home["live"].read_text()


def test_follow_redacts_the_live_session_once_it_goes_quiet(home):
    out = run(home, "redact", "-", "--skip-recent", "0.03", "--apply", "--follow",
              stdin="zorblax\n")
    assert "following 1 live files" in out and "zorblax" not in out
    assert "zorblax" in home["live"].read_text()
    deadline = time.time() + 15
    while "[neuralyzed]" not in home["live"].read_text() and time.time() < deadline:
        time.sleep(0.5)
    assert json.loads(home["live"].read_text())["text"] == "[neuralyzed] now"


def test_word_mode_does_not_match_inside_words(home):
    out = run(home, "scan", "orbla", "--word", "--tier", "memory,history")
    assert str(home["memory"]) not in out
    assert "files," not in out
