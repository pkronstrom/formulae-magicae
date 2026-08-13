"""Pure helpers for the pr-voice-review-single-file skill.

The content block holds PR patches verbatim. A PR that touches any HTML,
JSX, or template file contains the literal bytes `</script`, which
terminate an inline script element regardless of its type attribute. These
tests are what stop a corrupted artifact shipping.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "pr-voice-review-single-file"
sys.path.insert(0, str(SKILL))

import render  # noqa: E402


def test_json_for_block_escapes_every_angle_bracket():
    payload = {"patch": "-  <script>alert(1)</script>\n+  ok"}
    out = render.json_for_block(payload)
    assert "</script" not in out, "unescaped </script would terminate the block"
    assert "<" not in out, "every < must be escaped, not just the dangerous ones"
    assert "\\u003c" in out


def test_json_for_block_round_trips_through_json_loads():
    """The escape must be a JSON escape, so no unescaping step is needed."""
    payload = {"patch": "</script><!-- hostile -->", "n": 3}
    assert json.loads(render.json_for_block(payload)) == payload


def test_json_for_block_is_pretty_printed():
    """singlefile 3: minified state is not a contract, it is a blob."""
    assert "\n" in render.json_for_block({"a": 1, "b": 2})


PATCH = """@@ -38,6 +38,7 @@ def resolve(path):
 def resolve(path):
-    for p in parents(path):
+    for p in parents(path):
+        if p.profile:
             return p
     return None
"""


def test_parse_patch_tracks_both_line_numbers():
    rows = render.parse_patch(PATCH)
    kinds = [r["kind"] for r in rows]
    assert kinds[0] == "hunk"
    ctx = next(r for r in rows if r["kind"] == "ctx")
    assert ctx["old"] == 38 and ctx["new"] == 38
    dele = next(r for r in rows if r["kind"] == "del")
    assert dele["old"] == 39 and dele["new"] is None
    adds = [r for r in rows if r["kind"] == "add"]
    assert [r["new"] for r in adds] == [39, 40]
    assert all(r["old"] is None for r in adds)


def test_parse_patch_keeps_text_without_the_marker_column():
    rows = render.parse_patch(PATCH)
    add = next(r for r in rows if r["kind"] == "add")
    assert add["text"] == "    for p in parents(path):"


def test_parse_patch_handles_hostile_content_as_plain_text():
    """No escaping here: the client builds rows with textContent."""
    rows = render.parse_patch("@@ -1,1 +1,1 @@\n+</script><img src=x onerror=alert(1)>\n")
    add = next(r for r in rows if r["kind"] == "add")
    assert add["text"] == "</script><img src=x onerror=alert(1)>"


def test_parse_patch_empty_returns_empty():
    assert render.parse_patch("") == []


def test_parse_patch_keeps_counting_through_a_stripped_blank_context_line():
    """A blank context line is ' '; stripped to '' it must still count.

    Skipping it would desynchronize both gutters, so every highlight below
    the first blank line in a file would point at the wrong code.
    """
    stripped = "@@ -1,4 +1,4 @@\n a\n\n b\n-old\n+new\n"
    rows = render.parse_patch(stripped)
    dele = next(r for r in rows if r["kind"] == "del")
    assert dele["old"] == 4, "line numbers drifted past the blank context line"
    assert [r["kind"] for r in rows] == ["hunk", "ctx", "ctx", "ctx", "del", "add"]


def test_parse_patch_multiple_hunks_resets_line_numbers():
    two = "@@ -1,2 +1,2 @@\n ctx\n@@ -80,2 +90,2 @@\n ctx2\n"
    rows = render.parse_patch(two)
    ctxs = [r for r in rows if r["kind"] == "ctx"]
    assert ctxs[0]["old"] == 1
    assert ctxs[1]["old"] == 80 and ctxs[1]["new"] == 90


def test_project_bytes_scales_with_word_count():
    """2.4 words/sec, 3.1 KB/sec of MP3, x1.33 for base64."""
    segs = [{"speech": " ".join(["word"] * 240), "notes": []}]
    assert 400_000 < render.project_bytes(segs, overhead=0) < 425_000


def test_project_bytes_counts_note_speech_too():
    one = [{"speech": "a b c", "notes": []}]
    two = [{"speech": "a b c", "notes": [{"speech": "d e f"}]}]
    assert render.project_bytes(two, overhead=0) > render.project_bytes(one, overhead=0)


def test_project_bytes_includes_non_audio_overhead():
    segs = [{"speech": "a", "notes": []}]
    assert render.project_bytes(segs, overhead=1_000_000) >= 1_000_000


def test_project_bytes_ignores_notes_without_speech():
    """A silent card carries no audio, so it must not inflate the estimate."""
    silent = [{"speech": "a b c", "notes": [{"text": "just a card"}]}]
    voiced = [{"speech": "a b c", "notes": []}]
    assert render.project_bytes(silent, overhead=0) == render.project_bytes(voiced, overhead=0)


def test_narration_estimate_reports_what_the_second_question_needs():
    """The audio question is asked with real numbers, not a guess."""
    segs = [{"speech": " ".join(["word"] * 240), "notes": []}]   # 240 words
    est = render.narration_estimate(segs, overhead=200_000)
    assert est["words"] == 240
    assert 95 < est["seconds"] < 105          # 240 / 2.4 words-per-second
    assert 5 < est["synth_seconds"] < 15      # ~11x realtime with the worker pool
    assert est["bytes"] > 200_000             # audio plus the overhead passed in
    assert est["chunks"] == 1


def test_narration_estimate_counts_chunks_not_just_words():
    segs = [{"speech": "a b c", "notes": [{"speech": "d e f"}, {"text": "silent"}]}]
    assert render.narration_estimate(segs, overhead=0)["chunks"] == 2


def test_narration_estimate_of_nothing_is_zero():
    est = render.narration_estimate([], overhead=1000)
    assert est["words"] == 0 and est["seconds"] == 0 and est["synth_seconds"] == 0
    assert est["bytes"] == 1000
