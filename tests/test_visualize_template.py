"""Invariants for the visualize skill's HTML engine template.

The template is a pre-built artifact, not generated code, so these tests guard
the properties that silently break a single-file app: external references,
module scripts, and unbalanced script tags.
"""

import base64
import re
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "skills" / "visualize" / "template.html"
PACKED_TYPE = "viz/deflate-b64"


def _mermaid_source() -> str:
    """The Mermaid bundle as JS, whether it is stored packed or plain.

    Packed, the block holds raw-deflate + base64 and is inflated at boot by
    #viz-mermaid-loader; plain, it is the bundle itself. Both are valid states —
    pack-mermaid.py --unpack produces the second so Mermaid can be upgraded.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r'<script id="viz-mermaid"([^>]*)>', html)
    assert m, "no #viz-mermaid block"
    body = html[m.end() : html.index("</script>", m.end())]
    if PACKED_TYPE not in m.group(1):
        return body
    return zlib.decompress(base64.b64decode(body.strip()), -15).decode()


def test_template_exists():
    assert TEMPLATE.is_file(), f"{TEMPLATE} not found"


def test_packed_bundle_inflates_and_has_a_loader():
    """When the bundle is packed, the file needs the loader that inflates it —
    and the payload must actually be valid deflate. Shipping one without the
    other is a blank page, and it fails at the user, not in CI."""
    html = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r'<script id="viz-mermaid"([^>]*)>', html)
    assert m, "no #viz-mermaid block"
    if PACKED_TYPE not in m.group(1):
        return  # stored plain; the loader is a documented no-op
    assert 'id="viz-mermaid-loader"' in html, "packed bundle with no loader to inflate it"
    assert "DecompressionStream" in html, "loader must inflate via DecompressionStream"
    assert "__vizMermaidReady" in html, "engine must be able to await the bundle"
    # _mermaid_source() raises on a corrupt payload; this asserts it is the bundle.
    assert "__esbuild_esm_mermaid" in _mermaid_source(), "payload is not the Mermaid bundle"


def test_packed_payload_cannot_terminate_its_own_script_element():
    """Base64 has no '<', so the packed form removes the raw-text hazard the
    plain bundle lives with. Assert it rather than assume it."""
    html = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r'<script id="viz-mermaid"([^>]*)>', html)
    if not m or PACKED_TYPE not in m.group(1):
        return
    body = html[m.end() : html.index("</script>", m.end())]
    assert "<" not in body, "packed payload contains '<' — it is not pure base64"


def test_template_has_no_external_references():
    """The output must work offline, from a USB stick, with no network.

    Any http(s):// or protocol-relative URL in an attribute that triggers a
    fetch breaks that guarantee.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    fetching_attrs = re.findall(
        r'(?:src|href)\s*=\s*["\'](?!#)([^"\']+)["\']', html, flags=re.I
    )
    external = [u for u in fetching_attrs if u.startswith(("http://", "https://", "//"))]
    assert external == [], f"external references break offline use: {external}"


def test_mermaid_is_vendored_and_pinned():
    """Anchor resolution depends on render output, so the version is a
    deliberate choice, not whatever a CDN serves today."""
    html = TEMPLATE.read_text(encoding="utf-8")
    # Bind to a local first: `assert "x" in html` would dump 3.4 MB on failure.
    declared = "MERMAID_VERSION" in html
    assert declared, "engine must declare the pinned version"
    m = re.search(r'MERMAID_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', html)
    assert m, "MERMAID_VERSION must be a concrete x.y.z string"
    assert m.group(1).startswith("11."), f"expected Mermaid 11.x, got {m.group(1)}"
    # Size is no longer a proxy for "inlined": the bundle is stored raw-deflate
    # + base64 (pack-mermaid.py), so the file is ~1.7 MB while carrying the same
    # ~3.5 MB of Mermaid. Assert on what actually matters — that the bundle is
    # present and expands to something bundle-sized.
    assert len(_mermaid_source()) > 3_000_000, "Mermaid does not appear to be inlined"


def test_no_module_scripts():
    """Module scripts are CORS-blocked on file:// — a double-clicked file
    would silently render nothing."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'type="module"' not in html, "module scripts are CORS-blocked on file://"
    assert "type='module'" not in html, "module scripts are CORS-blocked on file://"


def test_no_runtime_dynamic_imports():
    """A lazy import() would fetch at runtime and break offline use, which the
    external-reference test cannot see."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "import.meta" not in html, "import.meta implies a module context"


def test_script_tags_are_balanced():
    """An inline <script> is terminated by the byte sequence `</script`
    anywhere inside it — including in a string, regex, or comment. This is the
    most common way a generated single-file app arrives broken."""
    html = TEMPLATE.read_text(encoding="utf-8")
    opens = len(re.findall(r"<script\b", html, flags=re.I))
    closes = len(re.findall(r"</script", html, flags=re.I))
    assert opens == closes, (
        f"{closes} `</script` sequences for {opens} <script> tags — "
        "a string, regex, or comment is terminating a script element early"
    )

def test_no_external_css_urls():
    """The attribute check above cannot see CSS url() references.

    latex.css ships @font-face rules pointing at relative ./fonts/*.woff2 that
    are not distributed; left in, they 404 silently from file:// and the page
    falls back to a system face without ever failing a test.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    # Only the stylesheet: the vendored Mermaid bundle builds url() strings in
    # JS, and inline SVG uses url(#fragment) filter references.
    style = re.search(r"<style>(.*?)</style>", html, flags=re.S)
    assert style, "no <style> block found"
    urls = re.findall(r"url\(\s*['\"]?([^)'\"]+)", style.group(1))
    external = [u for u in urls if not u.startswith(("data:", "#"))]
    assert external == [], f"CSS references files that are not embedded: {external[:5]}"


def test_saved_file_does_not_bake_in_highlight_wrappers():
    """Highlights are re-derived from #viz-marks on load.

    A `<mark>` left in the saved HTML splits the very text nodes that quote
    matching runs against, so reopening a saved file would fail to re-anchor and
    then wrap a second time on top of the first.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    fn = html[html.index("function serializeDocument"):]
    fn = fn[: fn.index("\n  }")]
    assert ".viz-comment" in fn, "margin comments must be stripped before saving"
    assert "#viz-bubble" in fn, "the selection bubble must be stripped before saving"
    assert 'querySelectorAll("mark.viz-hl")' in fn, "highlight wrappers must be unwrapped"


def test_dark_theme_defines_the_latex_tokens_it_inherits():
    """latex.css declares these only under .latex-dark, which is never applied.

    Left unset, the error panel's <pre> renders as a pale light-theme slab on
    dark paper.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    # The rule, not a prose mention of the selector in a comment.
    block = html[html.index(':root[data-theme="dark"] {'):]
    block = block[: block.index("}")]
    for token in ("--pre-bg-color", "--kbd-bg-color", "--table-border-color"):
        assert token in block, f"{token} is not defined for the dark theme"


def test_latex_face_is_embedded():
    """The LaTeX look depends on Latin Modern actually being present."""
    css = TEMPLATE.read_text(encoding="utf-8")
    declared = "'Latin Modern'" in css
    assert declared, "Latin Modern must be the first font-family"
    faces = css.count("@font-face")
    assert faces >= 4, f"expected regular/italic/bold/bold-italic, found {faces}"
