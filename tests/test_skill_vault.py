"""skill-vault search and notes behaviour."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills/skill-vault"
VAULT_SH = SKILL_DIR / "vault.sh"
SKILL_MD = SKILL_DIR / "SKILL.md"


def write_skill(path: Path, name: str, description: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        dedent(
            f"""\
            ---
            name: {name}
            description: {description}
            ---

            # {name}
            """
        )
    )


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A throwaway vault shaped like the real one: monorepo clones, a tool
    mirror under a hidden directory, and a name colliding across categories."""
    root = tmp_path / "vault"
    root.mkdir()
    shutil.copy(VAULT_SH, root / "vault.sh")
    (root / "vault.sh").chmod(0o755)
    # The real vault ignores clone contents; ripgrep would honour this and
    # search nothing, so it must be present for the regression to be real.
    (root / ".gitignore").write_text("/*/*/\n")

    # A multi-skill clone, as anthropic/skills is.
    write_skill(
        root / "anthropic/skills/skills/mcp-builder",
        "mcp-builder",
        "Guide for creating high-quality MCP servers with well-designed tools.",
    )
    write_skill(
        root / "anthropic/skills/skills/pdf",
        "pdf",
        "Work with PDF files: extract text, merge, split, fill forms.",
    )
    (root / "anthropic/skills/.git").mkdir(parents=True)

    # A clone with a tool-mirror duplicate under a hidden directory. Only one
    # entry should survive dedup.
    write_skill(
        root / "productivity/mempalace/skills/recall",
        "recall",
        "Search the palace before answering about past work.",
    )
    write_skill(
        root / "productivity/mempalace/.antigravity-plugin/skills/recall",
        "recall",
        "Search the palace before answering about past work.",
    )
    (root / "productivity/mempalace/.git").mkdir(parents=True)

    # Same skill name in a second category — why headings matter.
    write_skill(
        root / "engineering/toolkit/skills/prototype",
        "prototype",
        "Engineering prototype helper.",
    )
    write_skill(
        root / "frontend/kit/skills/prototype",
        "prototype",
        "Frontend prototype helper.",
    )
    return root


def run(vault: Path, *args: str, env: dict | None = None):
    return subprocess.run(
        [str(vault / "vault.sh"), *args],
        capture_output=True,
        text=True,
        cwd=vault,
        env=env,
    )


# --- matching -------------------------------------------------------------


def test_find_matches_by_name(vault: Path):
    out = run(vault, "find", "mcp-builder").stdout
    assert "mcp-builder" in out
    assert "pdf" not in out


def test_find_matches_by_description_only(vault: Path):
    """"forms" appears only in pdf's description, never in its name."""
    out = run(vault, "find", "forms").stdout
    assert "pdf" in out
    assert "mcp-builder" not in out


def test_find_is_case_insensitive(vault: Path):
    assert "mcp-builder" in run(vault, "find", "MCP-BUILDER").stdout


def test_find_matches_notes_text(vault: Path):
    (vault / "NOTES.md").write_text(
        "## anthropic/mcp-builder\nThe eval harness is the good part.\n"
    )
    out = run(vault, "find", "eval harness").stdout
    assert "eval harness" in out


# --- attribution ----------------------------------------------------------


def test_find_prints_category_headings(vault: Path):
    """A bare `catalog | grep` drops these, making colliding names ambiguous."""
    out = run(vault, "find", "prototype").stdout
    assert "## engineering" in out
    assert "## frontend" in out


def test_find_prints_note_heading_for_later_line_match(vault: Path):
    """Match on line 4 of a note must still name the skill it belongs to."""
    (vault / "NOTES.md").write_text(
        dedent(
            """\
            ## anthropic/mcp-builder
            aka: mcp
            tags: #mcp
            The eval harness is the good part.
            """
        )
    )
    out = run(vault, "find", "eval harness").stdout
    assert "## anthropic/mcp-builder" in out


def test_find_dedups_hidden_tool_mirror(vault: Path):
    """The .antigravity-plugin copy must not appear as a second hit."""
    out = run(vault, "find", "recall").stdout
    assert out.count("**recall**") == 1
    assert ".antigravity-plugin" not in out


# --- robustness -----------------------------------------------------------


def test_find_treats_regex_metacharacters_literally(vault: Path):
    """`grep -i -- '['` errors and, wrapped in `|| true`, reports no matches."""
    write_skill(
        vault / "engineering/toolkit/skills/bracket",
        "bracket",
        "Handles [keyword] templates.",
    )
    result = run(vault, "find", "[")
    assert "bracket" in result.stdout
    assert "no skill matches" not in result.stdout


def test_find_no_match_message_and_zero_exit(vault: Path):
    result = run(vault, "find", "zzzznope")
    assert "no skill matches 'zzzznope'" in result.stdout
    assert result.returncode == 0


def test_find_without_argument_exits_nonzero(vault: Path):
    result = run(vault, "find")
    assert result.returncode != 0
    assert "usage:" in result.stderr


def test_find_works_without_notes_file(vault: Path):
    assert not (vault / "NOTES.md").exists()
    result = run(vault, "find", "mcp-builder")
    assert result.returncode == 0
    assert "mcp-builder" in result.stdout


def test_find_truncation_is_locale_independent(vault: Path):
    """substr() splits multibyte characters under LC_ALL=C and emits illegal
    bytes; word-boundary truncation must not."""
    write_skill(
        vault / "engineering/toolkit/skills/longdesc",
        "longdesc",
        "Uses em—dashes and — more — of them " + "padding words " * 40,
    )
    import os

    base = dict(os.environ)
    c_out = run(vault, "find", "longdesc", env={**base, "LC_ALL": "C"}).stdout
    u_out = run(
        vault, "find", "longdesc", env={**base, "LC_ALL": "en_US.UTF-8"}
    ).stdout
    assert c_out == u_out
    c_out.encode("utf-8").decode("utf-8")  # raises if truncation split a char


def test_find_truncates_long_descriptions(vault: Path):
    write_skill(
        vault / "engineering/toolkit/skills/verbose",
        "verbose",
        "word " * 200,
    )
    line = next(
        l for l in run(vault, "find", "verbose").stdout.splitlines() if "verbose" in l
    )
    assert line.endswith("...")
    assert len(line) < 300


# --- wiring and non-regression -------------------------------------------


def test_find_is_reachable_and_documented(vault: Path):
    assert "unknown command" not in run(vault, "find", "pdf").stderr
    assert "find <query>" in run(vault, "--help").stdout


def test_notes_file_does_not_change_catalog_or_categories(vault: Path):
    before_cat = run(vault, "catalog").stdout
    before_cats = run(vault, "categories").stdout
    (vault / "NOTES.md").write_text("## anthropic/mcp-builder\nA note.\n")
    assert run(vault, "catalog").stdout == before_cat
    assert run(vault, "categories").stdout == before_cats


def test_skill_md_documents_find_and_notes():
    text = SKILL_MD.read_text()
    assert "vault.sh find" in text
    assert "NOTES.md" in text
