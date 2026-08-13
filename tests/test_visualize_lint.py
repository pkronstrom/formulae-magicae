"""Mermaid hazard handling for the visualize skill.

`;` and `#` are statement separator and comment introducer in Mermaid. In a
sequenceDiagram, note and message text is lexed as `[^#\\n;]*`, so a semicolon
in prose silently ends the statement and the remainder is parsed as a new one —
which is how a plain sentence produces a wall of expected-token names.

Mermaid runs encodeEntities() over the raw source before the lexer sees it, so
`#59;` and `#35;` are safe everywhere. These tests are what keep the escaping
targeted: text payloads only, never URLs, comments, or already-escaped codes.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "visualize"
ASSEMBLE = SKILL / "assemble.sh"
LINT = SKILL / "mermaid-lint.awk"
FIXTURES = REPO / "tests" / "fixtures" / "visualize"


def lint(md_text, tmp_path, name="src.md"):
    """Run the linter over markdown text; return (stdout, stderr)."""
    src = tmp_path / name
    src.write_text(md_text, encoding="utf-8")
    r = subprocess.run(
        ["awk", "-f", str(LINT), "-v", f"src={src}", str(src)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout, r.stderr


def seq(*body):
    return "# T\n\n## S\n\n```mermaid\nsequenceDiagram\n" + "\n".join(body) + "\n```\n"


def test_semicolon_in_note_text_is_escaped(tmp_path):
    """The reported bug: a semicolon ends the note and the rest fails to parse."""
    out, err = lint(seq("  Note over A: done at completion; a NEW action cancels it"), tmp_path)
    assert "completion#59; a NEW action" in out
    assert ";" not in out.split("Note over A:")[1].split("\n")[0].replace("#59;", "")
    assert "auto-fixed" in err


def test_semicolon_in_message_text_is_escaped(tmp_path):
    out, _ = lint(seq("  A->>B: queued; then resolved"), tmp_path)
    assert "queued#59; then resolved" in out


def test_hash_in_sequence_text_is_escaped(tmp_path):
    """`#` opens a Mermaid comment, truncating the text just like `;`."""
    out, _ = lint(seq("  A-->>B: costs #5 per tick"), tmp_path)
    assert "costs #35;5 per tick" in out


def test_block_keyword_text_is_escaped(tmp_path):
    out, _ = lint(seq("  alt invalid; rejected", "  end"), tmp_path)
    assert "alt invalid#59; rejected" in out


def test_existing_entity_codes_are_not_double_escaped(tmp_path):
    """Escaping `#` and `;` in two passes would corrupt the first pass's output."""
    out, err = lint(seq("  Note over E: already #59; and #quot;quoted#quot; here"), tmp_path)
    assert "already #59; and #quot;quoted#quot; here" in out
    assert "#35;59;" not in out
    assert "auto-fixed" not in err


def test_link_lines_are_never_touched(tmp_path):
    """`link` carries URLs, where a `#` fragment is load-bearing."""
    out, _ = lint(seq("  link A: Docs @ https://example.com/docs#anchor"), tmp_path)
    assert "https://example.com/docs#anchor" in out


def test_mermaid_comments_are_never_touched(tmp_path):
    out, _ = lint(seq("  %% a comment; with a semicolon"), tmp_path)
    assert "%% a comment; with a semicolon" in out


def test_participant_lines_are_not_mangled(tmp_path):
    """No arrow and no note keyword means no text payload to escape."""
    out, _ = lint(seq("  participant A as Registry; Ltd"), tmp_path)
    assert "participant A as Registry; Ltd" in out


def test_prose_outside_mermaid_fences_is_untouched(tmp_path):
    """The markdown around the diagrams is not Mermaid and must survive verbatim."""
    md = "# T\n\nProse with; a semicolon and a #hash.\n\n" + seq("  A->>B: hi")
    out, _ = lint(md, tmp_path)
    assert "Prose with; a semicolon and a #hash." in out


def test_flowchart_labels_warn_but_are_not_rewritten(tmp_path):
    """Flowchart label spans are too varied to rewrite unattended."""
    md = "# T\n\n## S\n\n```mermaid\nflowchart LR\n  a[label; here] --> b\n```\n"
    out, err = lint(md, tmp_path)
    assert "a[label; here] --> b" in out, "the source must not be rewritten"
    assert "quote it" in err


def test_quoted_flowchart_label_does_not_warn(tmp_path):
    md = '# T\n\n## S\n\n```mermaid\nflowchart LR\n  a["label; here"] --> b\n```\n'
    _, err = lint(md, tmp_path)
    assert err.strip() == ""


def test_end_as_flowchart_node_id_warns(tmp_path):
    md = "# T\n\n## S\n\n```mermaid\nflowchart LR\n  end[done] --> b\n```\n"
    _, err = lint(md, tmp_path)
    assert "reserved flowchart keyword" in err


def test_elk_layout_warns(tmp_path):
    """ELK is not in the bundle; SKILL.md says so and this enforces it."""
    md = "# T\n\n## S\n\n```mermaid\n---\nconfig:\n  layout: elk\n---\nflowchart LR\n  a --> b\n```\n"
    _, err = lint(md, tmp_path)
    assert "elk" in err.lower()


def test_frontmatter_does_not_break_type_detection(tmp_path):
    """A block opening with `---` still has to reach its real diagram type."""
    md = (
        "# T\n\n## S\n\n```mermaid\n---\ntitle: X\n---\nsequenceDiagram\n"
        "  A->>B: queued; then resolved\n```\n"
    )
    out, _ = lint(md, tmp_path)
    assert "queued#59; then resolved" in out


def test_unclosed_fence_warns(tmp_path):
    md = "# T\n\n## S\n\n```mermaid\nflowchart LR\n  a --> b\n"
    _, err = lint(md, tmp_path)
    assert "unclosed" in err


def test_unknown_diagram_type_warns(tmp_path):
    md = "# T\n\n## S\n\n```mermaid\n  a --> b\n```\n"
    _, err = lint(md, tmp_path)
    assert "unrecognised diagram type" in err


def test_multibyte_text_survives_assembly(tmp_path):
    """macOS ships the one-true-awk, which in a UTF-8 locale fails on multibyte
    input and SILENTLY TRUNCATES the record.

    A real document lost 9 of its 15 em dashes and everything after them on the
    affected lines, with no error that stopped the build. assemble.sh pins
    LC_ALL=C so the pass is byte-oriented; this is what keeps it that way.
    """
    src = tmp_path / "utf8.md"
    src.write_text(
        "# Ünïcødé — a title\n\n"
        "## Séction — with an em dash\n\n"
        "Prose with — em dashes — and ✓ ✕ ⇄ symbols, plus 日本語.\n\n"
        "```mermaid\nsequenceDiagram\n"
        "  Note over S: tick T — character due;<br/>cooldown elapsed — or urgent wake\n"
        "  A->>B: café; naïve — résumé\n"
        "```\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    subprocess.run(
        [str(ASSEMBLE), str(src), str(out), "Ünïcødé"], check=True, capture_output=True
    )
    html = out.read_text(encoding="utf-8")
    body = html.split('id="viz-src">')[1].split("\n</script>")[0]

    original = src.read_text(encoding="utf-8")
    assert body.count("—") == original.count("—"), "em dashes were lost in assembly"
    assert "日本語" in body and "✓ ✕ ⇄" in body and "café" in body
    assert "�" not in body, "text was mangled into replacement characters"
    # The whole of each affected line must survive, not just its head.
    assert "cooldown elapsed — or urgent wake" in body
    assert "naïve — résumé" in body
    # And the escaping still has to have happened on those same lines.
    assert "character due#59;" in body
    assert "café#59; naïve" in body


def test_assemble_escapes_and_still_writes_output(tmp_path):
    """Warnings must never cost the user their page."""
    src = FIXTURES / "hazards.md"
    out = tmp_path / "out.html"
    r = subprocess.run(
        [str(ASSEMBLE), str(src), str(out), "Hazards"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert out.is_file(), "a lint warning must not suppress the output file"
    html = out.read_text(encoding="utf-8")
    assert "completion#59;" in html, "escaping did not survive assembly"
    assert "quote it" in r.stderr, "flowchart warnings must reach stderr"


def test_assemble_still_escapes_script_terminators(tmp_path):
    """The linter runs before the sed that protects the raw-text script block."""
    src = tmp_path / "hostile.md"
    src.write_text(
        "# T\n\nText with </script> in it.\n\n"
        "```mermaid\nsequenceDiagram\n  A->>B: a; b\n```\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    subprocess.run([str(ASSEMBLE), str(src), str(out), "T"], check=True, capture_output=True)
    html = out.read_text(encoding="utf-8")
    body = html.split('id="viz-src">')[1].split("\n</script>")[0]
    assert "</script" not in body, "the linter pass broke script-terminator escaping"
    assert "a#59; b" in body
