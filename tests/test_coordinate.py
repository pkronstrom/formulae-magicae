import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/coordinate/coordinate.py"

spec = importlib.util.spec_from_file_location("coordinate", SCRIPT)
coordinate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinate)

CLAUDE_IDLE = """
─────────────────────────────────────────────────── bouillon ─
❯
───────────────────────────────────────────────────────────────
  ops ✶ ctx 63% | codename-bouillon(main* +1) | e52a4c39
"""
CLAUDE_BUSY = """
✻ Thinking… (esc to interrupt)
───────────────────────────────────────────────────────────────
❯
───────────────────────────────────────────────────────────────
"""
CLAUDE_DRAFT = """
───────────────────────────────────────────────────────────────
❯ Ideally; I would have a fish/tmux alias: "claudex" that spawns
  codex session on right pane
───────────────────────────────────────────────────────────────
"""
CLAUDE_DIALOG = """
  Bash command
  rm -rf build/

  Do you want to proceed?
❯ 1. Yes
  2. Yes, and don't ask again for rm commands
  3. No

  Esc to cancel
"""
CODEX_IDLE = """
─ Worked for 7m 48s ─────────────────────────────────────────────
› Ask Codex to do anything
  gpt-6-astra medium · ~/Projects/own/turbollm · Main [default]
"""
CODEX_DIALOG = """
  Would you like to run the following command?
  $ rm -rf build/
› 1. Yes
  2. No, and tell Codex what to do differently
"""
CODEX_DRAFT = """
› review the plan in .work/plan.md and
  gpt-6-astra medium · ~/Projects/own/turbollm · Main [default]
"""
BLANK = "\n\n   loading…\n"


def test_classify_claude():
    assert coordinate.classify(CLAUDE_IDLE, "claude") == (True, "empty prompt")
    assert coordinate.classify(CLAUDE_BUSY, "claude") == (True, "empty prompt")
    assert coordinate.classify(CLAUDE_DRAFT, "claude") == (False, "draft in prompt")
    assert coordinate.classify(CLAUDE_DIALOG, "claude") == (False, "dialog open")
    assert coordinate.classify(BLANK, "claude") == (False, "no prompt visible")


def test_classify_codex():
    assert coordinate.classify(CODEX_IDLE, "codex") == (True, "empty prompt")
    assert coordinate.classify(CODEX_DIALOG, "codex") == (False, "dialog open")
    assert coordinate.classify(CODEX_DRAFT, "codex") == (False, "draft in prompt")
    assert coordinate.classify(BLANK, "codex") == (False, "no prompt visible")


def test_envelope_carries_reply_line_and_thread():
    text = coordinate.envelope("claude/main", 7, "ask review-plan .work/plan.md\n", re_id="5")
    head, reply, blank, body = text.split("\n")
    assert head == "[COORDINATOR MESSAGE] from: claude/main  id: 7  re: 5"
    assert reply.startswith("reply: python3 ") and reply.endswith('send claude/main "<text>"')
    assert blank == "" and body == "ask review-plan .work/plan.md"


def test_project_key_is_stable_and_per_root(tmp_path):
    a = coordinate.project_key(tmp_path)
    assert a == coordinate.project_key(tmp_path)
    assert a.startswith(tmp_path.name + "-")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sub = tmp_path / "deep" / "er"
    sub.mkdir(parents=True)
    assert coordinate.project_key(sub) == coordinate.project_key(tmp_path)


def test_parse_etime():
    assert coordinate.parse_etime("05:07") == 307
    assert coordinate.parse_etime("01:02:03") == 3723
    assert coordinate.parse_etime("2-01:00:00") == 2 * 86400 + 3600


def test_help_exits_zero_and_unknown_command_nonzero():
    env = {**os.environ, "XDG_STATE_HOME": "/nonexistent"}
    ok = subprocess.run([sys.executable, SCRIPT, "--help"], capture_output=True, text=True, env=env)
    assert ok.returncode == 0 and "connect <harness>" in ok.stdout
    bad = subprocess.run([sys.executable, SCRIPT, "bogus"], capture_output=True, text=True, env=env)
    assert bad.returncode == 1
