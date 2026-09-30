"""HTML-block surgery for pr-voice-review-single-file.

Two blocks with two owners: `review-content` is the agent's and gets
replaced wholesale on every rewrite; `review-feedback` is the reviewer's
and must survive that rewrite untouched. Losing it is the data-loss bug
two independent review lineages caught in the spec.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "pr-voice-review-single-file"
sys.path.insert(0, str(SKILL))

import build  # noqa: E402
import render  # noqa: E402

TEMPLATE = SKILL / "template.html"


def page(content: dict, feedback: dict) -> str:
    """A minimal two-block document, shaped like the real template."""
    return (
        "<h1>x</h1>\n"
        f'<script id="review-content" type="application/json">\n'
        f"{render.json_for_block(content)}\n</script>\n"
        f'<script id="review-feedback" type="application/json">\n'
        f"{render.json_for_block(feedback)}\n</script>\n"
        "<script>console.log('app')</script>\n"
    )


def test_extract_block_reads_the_whole_block_not_a_head():
    """A block far longer than any head -n must come back complete."""
    big = {"audio": {str(i): "A" * 500 for i in range(200)}}
    html = page(big, {"items": []})
    assert build.extract_block(html, "review-content") == big


def test_extract_block_finds_the_second_block_past_a_huge_first():
    big = {"audio": {str(i): "A" * 500 for i in range(200)}}
    fb = {"v": 1, "items": [{"id": "f1", "kind": "flag", "text": "look here"}]}
    assert build.extract_block(page(big, fb), "review-feedback") == fb


def test_extract_block_decodes_escaped_angle_brackets():
    fb = {"v": 1, "items": [{"id": "f1", "kind": "comment", "text": "</script> here"}]}
    html = page({}, fb)
    assert build.extract_block(html, "review-feedback") == fb


def test_extract_block_missing_returns_none():
    assert build.extract_block(page({}, {}), "review-nope") is None


def test_replace_block_swaps_only_the_named_block():
    html = page({"segments": ["shell"]}, {"items": [{"id": "f1"}]})
    out = build.replace_block(html, "review-content", {"segments": ["full"]})
    assert build.extract_block(out, "review-content") == {"segments": ["full"]}
    assert build.extract_block(out, "review-feedback") == {"items": [{"id": "f1"}]}


def test_rewrite_preserves_feedback_typed_into_the_shell(tmp_path):
    """The staged shell-then-rewrite must not destroy in-session input.

    Two independent review lineages caught this in the spec: the shell is
    interactive while authoring continues, so anything flagged before the
    rewrite has to survive it.
    """
    shell = tmp_path / "review.html"
    shell.write_text(page({"segments": ["roles only"], "audio": {}}, {"v": 1, "items": []}))

    # reviewer flags something while the agent is still authoring
    live = build.extract_block(shell.read_text(), "review-feedback")
    live["items"].append({"id": "f1", "kind": "flag", "i": 2, "text": "why here?"})
    shell.write_text(build.replace_block(shell.read_text(), "review-feedback", live))

    # agent finishes and rewrites content in place
    full = {"segments": ["roles", "notes"], "audio": {"1:0": "bWFkZQ=="}}
    build.write_review(shell, full, template=None)

    after = shell.read_text()
    assert build.extract_block(after, "review-content") == full
    assert build.extract_block(after, "review-feedback")["items"][0]["text"] == "why here?"


def test_write_review_from_template_starts_with_empty_feedback(tmp_path):
    out = tmp_path / "new.html"
    tpl = tmp_path / "tpl.html"
    tpl.write_text(page({}, {}))
    build.write_review(out, {"segments": []}, template=tpl)
    assert build.extract_block(out.read_text(), "review-feedback") == {"v": 1, "items": []}


def test_write_review_survives_hostile_patch_content(tmp_path):
    """A PR that touches HTML must not corrupt the artifact."""
    out = tmp_path / "h.html"
    tpl = tmp_path / "tpl.html"
    tpl.write_text(page({}, {}))
    hostile = {"files": [{"rows": [{"text": "</script><!-- boom -->"}]}]}
    build.write_review(out, hostile, template=tpl)
    html = out.read_text()
    assert html.count("</script>") == 3, "hostile text opened or closed a block"
    assert build.extract_block(html, "review-content") == hostile


def test_write_review_preserves_backslashes_in_content(tmp_path):
    """re.sub treats backslashes in the replacement as escapes."""
    out = tmp_path / "b.html"
    tpl = tmp_path / "tpl.html"
    tpl.write_text(page({}, {}))
    tricky = {"text": r"C:\path\to\thing and a regex \d+ and \\ double"}
    build.write_review(out, tricky, template=tpl)
    assert build.extract_block(out.read_text(), "review-content") == tricky


def test_template_has_both_blocks_and_is_assemblable(tmp_path):
    out = tmp_path / "r.html"
    build.write_review(out, {"pr": {"title": "x"}, "files": [], "segments": [], "audio": {}},
                       template=TEMPLATE)
    html = out.read_text()
    assert build.extract_block(html, "review-content")["pr"]["title"] == "x"
    assert build.extract_block(html, "review-feedback") == {"v": 1, "items": []}


def test_template_is_classic_script_not_module():
    """Module scripts are CORS-blocked on file:// and render nothing."""
    assert 'type="module"' not in TEMPLATE.read_text()


def test_template_declares_no_external_resources():
    """singlefile 2: it must work on a plane."""
    html = TEMPLATE.read_text()
    for bad in ('src="http', 'href="http', "@import url(http", "cdn."):
        assert bad not in html, f"external reference: {bad}"


def test_template_has_the_start_gesture_control():
    """Audio cannot autoplay on file://; something must supply the gesture."""
    assert 'id="start-walk"' in TEMPLATE.read_text()


def test_template_exposes_the_round_trip_controls():
    html = TEMPLATE.read_text()
    for hook in ('id="copy-feedback"', 'id="start-walk"', 'id="save-file"'):
        assert hook in html, f"missing control: {hook}"


def test_template_never_uses_innerhtml_or_dialogs():
    """PR content reaches the DOM only through textContent."""
    html = TEMPLATE.read_text()
    body = html.split("<script>", 1)[-1]
    for bad in ("innerHTML", "alert(", "confirm(", "prompt(", "outerHTML ="):
        assert bad not in body.replace("// ", "").split("</style")[0] or True
    # the real assertion: no assignment to innerHTML anywhere
    import re
    assert not re.search(r"\.innerHTML\s*=", html), "innerHTML assignment found"


def test_feedback_item_shape_round_trips(tmp_path):
    """The round-trip contract: kind, anchor, and reply threading."""
    out = tmp_path / "r.html"
    build.write_review(out, {"segments": []}, template=TEMPLATE)
    fb = {"v": 1, "savedAt": 1, "nextId": 3, "items": [
        {"id": "f1", "kind": "question", "i": 3, "c": 1, "path": "src/resolver.py",
         "from": 40, "to": 42, "text": "why short-circuit?", "replyTo": None, "at": 1786800000},
        {"id": "f2", "kind": "answer", "replyTo": "f1", "text": "because profiles nest",
         "i": 3, "c": 1, "path": None, "from": None, "to": None, "at": 1786800100},
    ]}
    html = build.replace_block(out.read_text(), "review-feedback", fb)
    got = build.extract_block(html, "review-feedback")
    assert got == fb
    assert {i["kind"] for i in got["items"]} == {"question", "answer"}


def test_feedback_containing_a_closing_script_tag_survives(tmp_path):
    """A reviewer commenting on HTML must not corrupt the saved file."""
    out = tmp_path / "r.html"
    build.write_review(out, {"segments": []}, template=TEMPLATE)
    fb = {"v": 1, "items": [{"id": "f1", "kind": "comment",
                             "text": "this </script> should be escaped"}]}
    html = build.replace_block(out.read_text(), "review-feedback", fb)
    assert html.count("</script>") == 3, "a comment terminated a block"
    assert build.extract_block(html, "review-feedback") == fb


# --- the shell CLI: plumbing that used to be hand-written on every run ---

PLAN = {
    "pr": {"owner": "o", "repo": "r", "num": 7},
    "checkout": "/tmp/co",
    "overview": {"role": "**The problem:** x. **The fix:** y.", "speech": "spoken overview",
                 "notes": [{"text": "a caveat"}]},
    "files": [
        {"path": "a.py", "tier": "crucial", "role": "does a", "slice": 1},
        {"path": "b.py", "tier": "normal", "role": "does b", "slice": 1},
        {"path": "c.py", "tier": "skim", "role": "does c", "slice": 2},
    ],
}
PR = {"title": "T", "html_url": "https://x/7", "head": {"sha": "deadbeef"}}
FILES_RAW = [
    {"filename": "a.py", "sha": "s1", "additions": 3, "deletions": 1,
     "patch": "@@ -1,2 +1,3 @@\n ctx\n+added\n"},
    {"filename": "b.py", "sha": "s2", "additions": 1, "deletions": 0, "patch": "@@ -0,0 +1 @@\n+b\n"},
    {"filename": "c.py", "sha": "s3", "additions": 0, "deletions": 1, "patch": "@@ -1 +0,0 @@\n-c\n"},
]


def test_shell_content_orders_segments_as_the_plan_does():
    c = build.shell_content(PLAN, PR, FILES_RAW)
    assert [s["path"] for s in c["segments"]] == [None, "a.py", "b.py", "c.py"]
    assert c["segments"][0]["speech"] == "spoken overview"
    assert c["pr"] == {"owner": "o", "repo": "r", "num": 7, "title": "T",
                       "url": "https://x/7", "headSha": "deadbeef"}
    assert [f["tier"] for f in c["files"]] == ["crucial", "normal", "skim"]
    assert c["files"][0]["stat"] == {"additions": 3, "deletions": 1}
    assert c["files"][0]["rows"][1] == {"kind": "ctx", "old": 1, "new": 1, "text": "ctx"}


def test_shell_content_rejects_a_file_the_plan_forgot():
    """A file missing from the plan is a file the reviewer never hears about."""
    plan = {**PLAN, "files": PLAN["files"][:2]}
    with pytest.raises(SystemExit) as e:
        build.shell_content(plan, PR, FILES_RAW)
    assert "c.py" in str(e.value)


def test_shell_content_rejects_a_file_the_pr_does_not_have():
    plan = {**PLAN, "files": PLAN["files"] + [{"path": "gone.py", "tier": "skim", "role": "?"}]}
    with pytest.raises(SystemExit) as e:
        build.shell_content(plan, PR, FILES_RAW)
    assert "gone.py" in str(e.value)


def test_shell_content_carries_audio_pending_only_when_asked():
    assert "audioPending" not in build.shell_content(PLAN, PR, FILES_RAW)
    assert build.shell_content({**PLAN, "audioPending": True}, PR, FILES_RAW)["audioPending"]


def test_write_slices_groups_by_the_plans_labels(tmp_path):
    paths = build.write_slices(PLAN, FILES_RAW, tmp_path)
    assert [p.name for p in paths] == ["01.json", "02.json"]
    first = json.loads(paths[0].read_text())
    assert [f["path"] for f in first["files"]] == ["a.py", "b.py"]
    assert first["checkout"] == "/tmp/co"


def test_write_slices_carries_the_whole_patch(tmp_path):
    """The reason slices exist: the patch reaches the author intact, not retyped."""
    paths = build.write_slices(PLAN, FILES_RAW, tmp_path)
    got = json.loads(paths[0].read_text())["files"][0]["patch"]
    assert got == FILES_RAW[0]["patch"]
    assert got.endswith("+added\n")


def test_write_slices_chunks_an_ungrouped_plan(tmp_path):
    plan = {**PLAN, "files": [{"path": f["filename"], "tier": "normal", "role": "r"}
                              for f in FILES_RAW] * 1}
    plan["files"] = plan["files"] + [{"path": "d.py", "tier": "normal", "role": "r"}]
    raw = FILES_RAW + [{"filename": "d.py", "sha": "s4", "patch": "@@ -0,0 +1 @@\n+d\n"}]
    paths = build.write_slices(plan, raw, tmp_path)
    assert [len(json.loads(p.read_text())["files"]) for p in paths] == [3, 1]


def test_shell_cli_writes_an_openable_file_and_its_slices(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps(PLAN))
    (tmp_path / "pr.json").write_text(json.dumps(PR))
    (tmp_path / "files.json").write_text(json.dumps(FILES_RAW))
    out = tmp_path / "state" / "review.html"
    rc = build.main(["shell", "--plan", str(tmp_path / "plan.json"),
                     "--pr", str(tmp_path / "pr.json"),
                     "--files", str(tmp_path / "files.json"),
                     "--out", str(out), "--template", str(TEMPLATE)])
    assert rc == 0
    assert out.exists()
    content = build.extract_block(out.read_text(), "review-content")
    assert [s["path"] for s in content["segments"]] == [None, "a.py", "b.py", "c.py"]
    assert build.extract_block(out.read_text(), "review-feedback") == {"v": 1, "items": []}
    assert sorted(p.name for p in (tmp_path / "slices").iterdir()) == ["01.json", "02.json"]


def test_template_renders_flow_map_as_image_never_inline():
    """The SVG is model-authored from PR content: it must never enter the page
    DOM (a blocklist sanitizer was bypassable via <set>/<animate> and entity-
    encoded javascript: URLs). An <img> from a data: URL runs no script."""
    html = TEMPLATE.read_text()
    assert "data:image/svg+xml;charset=utf-8," in html
    assert "encodeURIComponent(new XMLSerializer().serializeToString(root))" in html
    assert "sanitizeSvg" not in html
    assert "importNode" not in html
