"""Assembly pipeline for the visualize skill.

The markdown source lives inside a raw-text `<script type="text/markdown">`
element, which HTML tokenization terminates at the first literal `</script`
regardless of the type attribute. Since the source is agent-written plan text,
a plan that merely discusses HTML would silently truncate the document. These
tests are what stop that shipping.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSEMBLE = REPO / "skills" / "visualize" / "assemble.sh"
FIXTURES = REPO / "tests" / "fixtures" / "visualize"


def assemble(tmp_path, md_name, title="Test Doc", out_name="out.html"):
    """Run assemble.sh on a fixture and return the generated HTML."""
    src = FIXTURES / md_name
    out = tmp_path / out_name
    result = subprocess.run(
        [str(ASSEMBLE), str(src), str(out), title],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"assemble.sh failed: {result.stderr}"
    return out.read_text(encoding="utf-8")


def test_hostile_markdown_does_not_terminate_the_source_block(tmp_path):
    """A plan that discusses HTML must not truncate its own source block."""
    html = assemble(tmp_path, "hostile.md")
    body = re.search(
        r'<script type="text/markdown" id="viz-src">(.*?)\n</script>',
        html,
        flags=re.S,
    )
    assert body, "viz-src block not found or terminated early"
    inner = body.group(1)
    assert "</script" not in inner, "unescaped </script survived into the block"
    assert "<!--" not in inner, "unescaped <!-- survived into the block"
    assert "<\\/script" in inner, "the escaped form should be present"
    assert "flowchart LR" in inner, "content after the hostile text was lost"


def test_engine_marker_survives_assembly(tmp_path):
    """The engine must be appended intact, exactly once."""
    html = assemble(tmp_path, "hostile.md")
    assert html.count("ENGINE START") == 1
    declared = "MERMAID_VERSION" in html
    assert declared


def test_marks_block_precedes_source_block(tmp_path):
    """Marks must come first so a long document cannot push them out of reach."""
    html = assemble(tmp_path, "long.md")
    assert html.index('id="viz-marks"') < html.index('id="viz-src"')


def test_marks_readable_within_first_40_lines(tmp_path):
    """SKILL.md tells the agent to read feedback with `head -40`."""
    html = assemble(tmp_path, "long.md")
    head = "\n".join(html.splitlines()[:40])
    assert 'id="viz-marks"' in head
    assert '"docId"' in head


def test_docid_is_path_derived_and_stable(tmp_path):
    html = assemble(tmp_path, "long.md")
    m = re.search(r'"docId"\s*:\s*"([^"]+)"', html)
    assert m, "docId missing"
    assert m.group(1).startswith("viz:"), m.group(1)
    assert m.group(1).endswith("/long"), m.group(1)
    # Regenerating must not change it, or annotations orphan on every revision.
    again = assemble(tmp_path, "long.md", out_name="again.html")
    assert re.search(r'"docId"\s*:\s*"([^"]+)"', again).group(1) == m.group(1)


def test_docid_differs_across_projects_with_the_same_layout(tmp_path):
    """All file:// pages may share one localStorage bucket, so two projects
    laid out identically must not collide on the same key."""
    docids = []
    for project in ("alpha", "beta"):
        viz = tmp_path / project / "docs" / "viz"
        viz.mkdir(parents=True)
        src = viz / "plan.md"
        src.write_text("# Plan\n\n## A\n\n```mermaid\nflowchart LR\n  a --> b\n```\n")
        out = viz / "plan.html"
        subprocess.run(
            [str(ASSEMBLE), str(src), str(out), "Plan"], check=True, capture_output=True
        )
        html = out.read_text(encoding="utf-8")
        docids.append(re.search(r'"docId"\s*:\s*"([^"]+)"', html).group(1))

    assert docids[0] != docids[1], (
        f"both projects got docId {docids[0]!r} — annotations would overwrite "
        "each other in a shared file:// storage bucket"
    )


def test_existing_marks_survive_regeneration(tmp_path):
    """Revising the diagram must not destroy the user's annotations."""
    out = tmp_path / "out.html"
    src = FIXTURES / "long.md"
    subprocess.run(
        [str(ASSEMBLE), str(src), str(out), "Long"], check=True, capture_output=True
    )

    # Simulate the user annotating and the page saving marks back.
    html = out.read_text(encoding="utf-8")
    annotated = html.replace(
        '"marks":[]',
        '"marks":[{"kind":"note","section":"long-document","node":"a","text":"why?"}]',
    )
    assert annotated != html, "fixture replace did not match the marks block"
    out.write_text(annotated, encoding="utf-8")

    # Agent revises the diagram and regenerates over the same path.
    subprocess.run(
        [str(ASSEMBLE), str(src), str(out), "Long"], check=True, capture_output=True
    )

    regenerated = out.read_text(encoding="utf-8")
    assert '"text":"why?"' in regenerated, "regeneration destroyed user annotations"
