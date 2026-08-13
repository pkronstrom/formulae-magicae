"""Deck-file handling for the bento-slides skill.

A `.bento.html` file is the document, the editor and the player at once. The
document lives in one `<script id="bento-doc">` block, and the invariant that
keeps it parseable is that every `<` inside it is written as the JSON escape
`\\u003c`. Miss that and a deck whose text merely mentions `</script>`
truncates its own data block: the JSON is gone and the file will not open.

The failure is silent at author time, which is why the rule is scripted rather
than left to an agent, and why these tests exist. The `</script` count guard is
necessary but catches almost nothing on its own — most of what follows covers
the preflight checks around it.
"""

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "bento-slides"
BENTO = SKILL / "bento.sh"
RUNTIME = SKILL / "runtime" / "Bento_Slides.bento.html"
PRESETS = SKILL / "styles" / "presets.json"
FONTS = SKILL / "styles" / "fonts"

DOC_OPEN = '<script type="application/bento+json" id="bento-doc">'


def run(*args, expect=0, env=None):
    """Invoke bento.sh; assert the exit status and return the result."""
    r = subprocess.run(
        [str(BENTO), *map(str, args)], capture_output=True, text=True, env=env
    )
    assert r.returncode == expect, (
        f"expected exit {expect}, got {r.returncode}\nstdout: {r.stdout}\nstderr: {r.stderr}"
    )
    return r


def test_xdg_cache_home_controls_chrome_profile(tmp_path):
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    assert run("cache-path", env=env).stdout.strip() == str(
        tmp_path / "cache/bento-slides/chrome-profile"
    )


@pytest.mark.parametrize("value", ["", "relative/cache"])
def test_xdg_cache_home_empty_or_relative_falls_back(monkeypatch, tmp_path, value):
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = value
    env["HOME"] = str(tmp_path / "home")
    assert run("cache-path", env=env).stdout.strip() == str(
        tmp_path / "home/.cache/bento-slides/chrome-profile"
    )


def new_deck(tmp_path, topic="Test Deck", style="plain"):
    r = run("new", topic, "--style", style, "--dir", tmp_path)
    return Path(r.stdout.strip())


def read_doc(deck, *extra, expect=0):
    r = run("read", deck, *extra, expect=expect)
    return json.loads(r.stdout) if expect == 0 else r


def write_doc(deck, doc, tmp_path, expect=0, name="doc.json"):
    p = Path(tmp_path) / name
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return run("write", deck, p, expect=expect)


def doc_block(deck):
    """The raw, still-escaped text of the document block."""
    html = Path(deck).read_text(encoding="utf-8")
    start = html.index(DOC_OPEN) + len(DOC_OPEN)
    return html[start:html.index("</script>", start)]


# --------------------------------------------------------------------------
# the escaping invariant


def test_literal_script_tag_in_text_survives(tmp_path):
    """A deck whose own text contains `</script>` must round-trip intact, and
    the file's `</script` count must not move. This is the failure the whole
    script exists to prevent."""
    deck = new_deck(tmp_path)
    before = Path(deck).read_text(encoding="utf-8").count("</script")

    doc = read_doc(deck)
    hostile = 'Hostile: </script><script>alert(1)</script> & <b>bold</b>'
    doc["slides"][0]["elements"][0]["html"] = hostile
    doc["slides"][0]["notes"] = "notes with </script> too"
    write_doc(deck, doc, tmp_path)

    assert Path(deck).read_text(encoding="utf-8").count("</script") == before
    assert "</script" not in doc_block(deck)
    assert "\\u003c" in doc_block(deck)
    assert read_doc(deck)["slides"][0]["elements"][0]["html"] == hostile


def test_structural_json_is_untouched_by_escaping(tmp_path):
    """`<` only ever occurs inside strings in a serialized document, so
    escaping every one of them cannot corrupt the JSON structure."""
    deck = new_deck(tmp_path)
    doc = read_doc(deck)
    doc["title"] = "<<<>>>"
    doc["slides"][0]["elements"][0]["html"] = "a < b < c"
    write_doc(deck, doc, tmp_path)
    got = read_doc(deck)
    assert got["title"] == "<<<>>>"
    assert got["slides"][0]["elements"][0]["html"] == "a < b < c"


def test_round_trip_is_lossless_and_byte_stable(tmp_path):
    """read -> write leaves the file byte-identical, so an edit cycle that
    changes nothing changes nothing on disk."""
    deck = new_deck(tmp_path, style="signal")
    before = Path(deck).read_bytes()
    doc = read_doc(deck)
    write_doc(deck, doc, tmp_path)
    assert Path(deck).read_bytes() == before
    assert read_doc(deck) == doc


# --------------------------------------------------------------------------
# write preflight — the checks the </script count cannot make


def test_write_rejects_malformed_json(tmp_path):
    deck = new_deck(tmp_path)
    before = Path(deck).read_bytes()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = run("write", deck, bad, expect=1)
    assert "not valid JSON" in r.stderr
    assert Path(deck).read_bytes() == before, "a rejected write must not touch the deck"


def test_write_rejects_a_non_slides_document(tmp_path):
    """Bento has other document formats; rewriting one with the Slides contract
    corrupts it in a way no later check notices."""
    deck = new_deck(tmp_path)
    before = Path(deck).read_bytes()
    doc = read_doc(deck)
    doc["format"] = "bento/spaces"
    r = write_doc(deck, doc, tmp_path, expect=1)
    assert "bento/slides" in r.stderr
    assert Path(deck).read_bytes() == before


def test_write_rejects_zero_doc_blocks(tmp_path):
    target = tmp_path / "not-a-deck.html"
    target.write_text("<html><body>nothing here</body></html>", encoding="utf-8")
    doc = read_doc(new_deck(tmp_path))
    r = write_doc(target, doc, tmp_path, expect=1)
    assert "exactly one" in r.stderr


def test_write_rejects_multiple_doc_blocks(tmp_path):
    deck = new_deck(tmp_path)
    doubled = tmp_path / "doubled.html"
    doubled.write_text(
        Path(deck).read_text(encoding="utf-8") + DOC_OPEN + "</script>",
        encoding="utf-8",
    )
    r = write_doc(doubled, read_doc(deck), tmp_path, expect=1)
    assert "exactly one" in r.stderr


def test_read_rejects_an_empty_shell(tmp_path):
    """The shipped runtime's block is empty on disk. That is a blank app, not a
    deck, and reading it should say so rather than fail on a JSON error."""
    shell = tmp_path / "shell.bento.html"
    shutil.copy(RUNTIME, shell)
    r = run("read", shell, expect=1)
    assert "empty" in r.stderr.lower()


# --------------------------------------------------------------------------
# assets stay out of the agent's context, and survive anyway


def test_read_withholds_assets_by_default(tmp_path):
    """Embedded fonts are ~85 KB of base64 per deck. Handing that to whoever is
    editing the slides floods their context with payload they cannot use."""
    deck = new_deck(tmp_path, style="signal")
    lean = run("read", deck)
    full = run("read", deck, "--with-assets")
    assert "assets" not in json.loads(lean.stdout)
    assert json.loads(full.stdout)["assets"]
    assert len(lean.stdout) * 20 < len(full.stdout), "withholding barely helped"
    assert "withheld 2 asset" in lean.stderr


def test_write_carries_assets_forward(tmp_path):
    """Since `read` omits them, a plain edit cycle must not delete them — that
    would strand doc.fonts pointing at nothing and fall back silently."""
    deck = new_deck(tmp_path, style="terra")
    doc = read_doc(deck)
    assert "assets" not in doc
    doc["title"] = "Edited"
    r = write_doc(deck, doc, tmp_path)
    assert "carried 2 existing asset" in r.stderr

    full = json.loads(run("read", deck, "--with-assets").stdout)
    assert full["title"] == "Edited"
    assert all(f["asset"] in full["assets"] for f in full["fonts"])


def test_an_explicit_empty_assets_still_clears(tmp_path):
    """Carry-forward is for an absent key, not an empty one — otherwise there
    would be no way to drop assets deliberately."""
    deck = new_deck(tmp_path, style="picnic")
    doc = read_doc(deck)
    doc["assets"] = {}
    doc["fonts"] = []          # or the font guard below would refuse the write
    write_doc(deck, doc, tmp_path)
    assert not json.loads(run("read", deck, "--with-assets").stdout).get("assets")


def test_write_refuses_a_font_with_no_asset(tmp_path):
    """The silent-fallback trap, caught at write time rather than on someone
    else's machine."""
    deck = new_deck(tmp_path, style="signal")
    doc = read_doc(deck)
    doc["fonts"] = [{"family": "Ghost", "asset": "font-ghost", "weight": "400"}]
    doc["assets"] = {}
    r = write_doc(deck, doc, tmp_path, expect=1)
    assert "font-ghost" in r.stderr and "doc.assets" in r.stderr


# --------------------------------------------------------------------------
# collaboration keys — the safety ordering


def shared_deck(tmp_path):
    deck = new_deck(tmp_path)
    doc = read_doc(deck)
    doc["collab"] = {
        "room": "r1",
        "ownerPriv": "SECRET-OWNER-KEY",
        "invite": "SECRET-INVITE-KEY",
    }
    write_doc(deck, doc, tmp_path)
    return deck


def test_inspect_reports_sharing_without_emitting_keys(tmp_path):
    """`inspect` exists so that discovering a deck is shared does not itself
    spill the keys. A warning issued after the secret is on screen is not a
    control."""
    deck = shared_deck(tmp_path)
    r = run("inspect", deck, expect=3)
    assert "SECRET" not in r.stdout
    assert "SECRET" not in r.stderr
    assert "ownerPriv" in r.stdout and "invite" in r.stdout  # names, not values
    assert "shared" in r.stdout


def test_inspect_on_an_unshared_deck_is_clean(tmp_path):
    r = run("inspect", new_deck(tmp_path))
    assert "collabKeys   []" in r.stdout


def test_read_refuses_a_shared_deck_without_the_flag(tmp_path):
    deck = shared_deck(tmp_path)
    r = run("read", deck, expect=3)
    assert "SECRET" not in r.stdout and "SECRET" not in r.stderr
    assert "inspect" in r.stderr


def test_read_allow_shared_is_the_only_way_through(tmp_path):
    deck = shared_deck(tmp_path)
    doc = json.loads(run("read", deck, "--allow-shared").stdout)
    assert doc["collab"]["ownerPriv"] == "SECRET-OWNER-KEY"


def test_a_collab_block_without_keys_is_not_shared(tmp_path):
    """`collab` alone is not a secret — only the key fields are."""
    deck = new_deck(tmp_path)
    doc = read_doc(deck)
    doc["collab"] = {"room": "r1"}
    write_doc(deck, doc, tmp_path)
    assert "collabKeys   []" in run("inspect", deck).stdout
    read_doc(deck)  # and read does not refuse


# --------------------------------------------------------------------------
# new — slug safety and a bootable document


@pytest.mark.parametrize("topic", [
    "../../etc/passwd",
    "-rf",
    "a/b/c",
    "with\ttabs\nand\nnewlines",
    "x" * 300,
    "  ...  ",
])
def test_new_slugs_hostile_topics_into_the_target_directory(tmp_path, topic):
    """The raw topic reaches the filesystem otherwise."""
    deck = new_deck(tmp_path, topic=topic)
    assert deck.parent == tmp_path, f"{deck} escaped the target directory"
    assert deck.name.endswith(".bento.html")
    stem = deck.name[: -len(".bento.html")]
    assert stem and not stem.startswith("-")
    assert all(c.isalnum() or c in "._-" for c in stem), stem
    assert len(deck.name) < 100


def test_new_refuses_to_overwrite(tmp_path):
    """The deck it would clobber is the user's work, not a build artifact."""
    deck = new_deck(tmp_path, topic="Same Topic")
    marker = deck.read_bytes()
    r = run("new", "Same Topic", "--style", "plain", "--dir", tmp_path, expect=1)
    assert "already exists" in r.stderr
    assert deck.read_bytes() == marker


def test_new_produces_a_bootable_document(tmp_path):
    """`size` and `theme.fontFamily` are required — without them the app will
    not boot, and nothing later would tell you."""
    doc = read_doc(new_deck(tmp_path, style="terra"))
    assert doc["format"] == "bento/slides"
    assert doc["size"] == {"width": 1280, "height": 720}
    assert doc["theme"]["fontFamily"]
    assert doc["slides"] and doc["slides"][0]["elements"]


def test_new_omits_docid_and_collab(tmp_path):
    """Fresh decks let the app mint these on first open; `docId` is the
    document's identity and must never be generated by us."""
    doc = read_doc(new_deck(tmp_path))
    assert "docId" not in doc
    assert "collab" not in doc


def test_new_rejects_an_unknown_style(tmp_path):
    r = run("new", "X", "--style", "chartreuse", "--dir", tmp_path, expect=2)
    assert "unknown style" in r.stderr


# --------------------------------------------------------------------------
# presets — the silent-fallback guard


def presets():
    return json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]


def test_presets_parse_and_carry_house_rules():
    """A preset that only set colours would produce a deck with the right
    palette and the wrong instincts."""
    for name, p in presets().items():
        assert p["houseRules"].strip(), f"{name} has no house rules"
        assert p["look"].strip(), f"{name} has no description"
        for key in ("background", "color", "accent", "fontFamily"):
            assert p["theme"][key], f"{name}.theme.{key} missing"


@pytest.mark.parametrize("style", sorted(presets()))
def test_every_named_family_is_actually_embedded(tmp_path, style):
    """A fontFamily naming a face the document does not carry falls back
    silently, and it looks right to the author because they have the typeface
    installed. Everyone else gets the fallback."""
    doc = json.loads(run("read", new_deck(tmp_path, style=style),
                         "--with-assets").stdout)
    fonts = doc.get("fonts", [])
    assets = doc.get("assets", {})
    for entry in fonts:
        assert entry["asset"] in assets, f"{style}: {entry['family']} has no asset"
        assert assets[entry["asset"]].startswith("data:font/woff2;base64,")

    embedded = {f["family"] for f in fonts}
    named = {doc["theme"]["fontFamily"]}
    for slide in doc["slides"]:
        for el in slide["elements"]:
            if el.get("fontFamily"):
                named.add(el["fontFamily"])
    for stack in named:
        first = stack.split(",")[0].strip().strip("'\"")
        # Either an embedded face, or a system keyword meant as one.
        assert first in embedded or first in {
            "system-ui", "-apple-system", "sans-serif", "serif", "monospace",
        }, f"{style}: {first!r} is named but not embedded"


@pytest.mark.parametrize("style", sorted(presets()))
def test_preset_font_files_exist_and_decode(style):
    for entry in presets()[style].get("fonts", []):
        blob = FONTS / entry["file"]
        assert blob.is_file(), f"{style} names {entry['file']}, which is missing"
        base64.b64decode(blob.read_text(encoding="utf-8").strip(), validate=True)


def test_plain_embeds_nothing(tmp_path):
    """`plain` satisfies the guard by naming only system stacks and declaring
    no fonts at all. That is a pass, not an exemption."""
    doc = read_doc(new_deck(tmp_path, style="plain"))
    assert "fonts" not in doc and "assets" not in doc


def test_every_shipped_face_is_licensed():
    """Both licences require their text to travel with the fonts, and this
    repository is public."""
    licences = list(FONTS.glob("LICENSE-*"))
    assert licences, "no licence text ships with the fonts"
    for blob in FONTS.glob("*.b64"):
        assert blob.stat().st_size > 0
    names = " ".join(p.name for p in licences)
    assert "OFL" in names and "GUST" in names


def test_latex_ships_true_italics():
    """The published guide lists doc.fonts as {family, asset, weight}, but the
    runtime also honours `style` — which is how the latex preset gets real
    italic Latin Modern instead of a synthesized slant."""
    styles = {f.get("style") for f in presets()["latex"]["fonts"]}
    assert "italic" in styles


# --------------------------------------------------------------------------
# check — validate() without an interactive browser

CHROME = next(
    (c for c in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"]
     if Path(c).is_file()),
    shutil.which("google-chrome") or shutil.which("chromium"),
)
needs_chrome = pytest.mark.skipif(not CHROME, reason="no Chrome/Chromium installed")


@needs_chrome
def test_check_passes_a_clean_deck(tmp_path):
    r = run("check", new_deck(tmp_path, style="signal"))
    assert "0 error(s)" in r.stderr
    assert "clean" in r.stderr


@needs_chrome
def test_check_reports_a_broken_link_as_an_error(tmp_path):
    """A link to a slide that does not exist is the clearest `error`-severity
    finding, and it must set a non-zero exit so a caller can gate on it."""
    deck = new_deck(tmp_path, style="plain")
    doc = read_doc(deck)
    doc["slides"][0]["elements"][0]["link"] = "no-such-slide"
    write_doc(deck, doc, tmp_path)
    r = run("check", deck, expect=1)
    assert "broken-link" in r.stdout
    assert "no-such-slide" in r.stdout


@needs_chrome
def test_check_reports_text_overflow(tmp_path):
    """The defect measure() exists to pre-empt — caught after the fact instead,
    for the whole deck, in one pass."""
    deck = new_deck(tmp_path, style="plain")
    doc = read_doc(deck)
    el = doc["slides"][0]["elements"][0]
    el["html"] = "A very long headline that cannot possibly fit " * 6
    el["h"] = 60
    write_doc(deck, doc, tmp_path)
    r = run("check", deck)          # a warning, not an error — exit stays 0
    assert "text-overflow" in r.stdout


# --------------------------------------------------------------------------
# the vendored pair


def test_guide_and_runtime_are_pinned_together():
    guide = (SKILL / "reference" / "agents.md").read_text(encoding="utf-8")
    assert "VENDORED from https://bento.page/agents.md" in guide
    assert "Guide version" in guide
    assert RUNTIME.is_file()
    assert b'id="bento-doc"' in RUNTIME.read_bytes()


def test_runtime_ships_with_an_empty_doc_block():
    """If this ever ships non-empty, `new` would be copying someone's deck."""
    html = RUNTIME.read_text(encoding="utf-8")
    start = html.index(DOC_OPEN) + len(DOC_OPEN)
    assert html[start:html.index("</script>", start)].strip() == ""
