"""Assemble the review file, and read the reviewer's feedback back out.

Two blocks, two owners:
  review-content   agent-owned, replaced wholesale on every rewrite
  review-feedback  user-owned, copied across a rewrite verbatim

`shell` is the CLI half: it turns a plan (the editorial decisions — order,
tier, role, overview) plus the raw `gh api` output into the shell file and
the per-slice briefs the authoring fan-out reads. Everything it does was
previously hand-written as a throwaway script on every single run, which
cost three minutes of reading this module to rediscover its own API.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import render

CONTENT_ID = "review-content"
FEEDBACK_ID = "review-feedback"
EMPTY_FEEDBACK = {"v": 1, "items": []}


def _block_re(block_id: str) -> re.Pattern:
    return re.compile(
        rf'(<script id="{re.escape(block_id)}" type="application/json">\n)'
        r"(.*?)"
        r"(\n</script>)",
        re.S,
    )


def extract_block(html: str, block_id: str):
    """Return the parsed block, or None if it is not there.

    Delimiter to delimiter — never `head -n`. This block can sit below
    megabytes of base64 audio, and a truncated read means answering the
    reviewer from partial feedback, which looks like working software.
    """
    m = _block_re(block_id).search(html)
    if not m:
        return None
    return json.loads(m.group(2))


def replace_block(html: str, block_id: str, obj) -> str:
    """Swap one block's contents, leaving every other byte of the file alone."""
    body = render.json_for_block(obj)
    return _block_re(block_id).sub(lambda m: m.group(1) + body + m.group(3), html, count=1)


def write_review(out: Path, content: dict, template: Path | None) -> None:
    """Write the review file, preserving any feedback already in it.

    `template=None` means rewriting a file that already exists — the staged
    build's second pass. The feedback block is read from the file on disk
    and written back verbatim, because the reviewer has been able to flag
    and comment since the shell opened.
    """
    out = Path(out)
    if template is not None:
        html = Path(template).read_text(encoding="utf-8")
        feedback = EMPTY_FEEDBACK
    else:
        html = out.read_text(encoding="utf-8")
        feedback = extract_block(html, FEEDBACK_ID) or EMPTY_FEEDBACK
    html = replace_block(html, CONTENT_ID, content)
    html = replace_block(html, FEEDBACK_ID, feedback)
    out.write_text(html, encoding="utf-8")


SLICE_SIZE = 3  # when the plan does not group the files itself


def shell_content(plan: dict, pr: dict, files_raw: list[dict]) -> dict:
    """Plan + `gh api` output -> the content block, or die saying what is missing.

    The plan covering exactly the fetched file list is checked here rather
    than trusted: a file present in the PR and absent from the plan is a
    file the reviewer never hears about, and nothing downstream notices.
    """
    by_path = {f["filename"]: f for f in files_raw}
    planned = [f["path"] for f in plan["files"]]
    missing = [p for p in by_path if p not in set(planned)]
    unknown = [p for p in planned if p not in by_path]
    if missing or unknown:
        raise SystemExit(
            f"plan does not match the PR\n"
            f"  in the PR, not in the plan: {missing}\n"
            f"  in the plan, not in the PR: {unknown}"
        )

    files = [
        {
            "path": f["path"],
            "sha": by_path[f["path"]].get("sha", ""),
            "tier": f["tier"],
            "stat": {
                "additions": by_path[f["path"]].get("additions", 0),
                "deletions": by_path[f["path"]].get("deletions", 0),
            },
            "rows": render.parse_patch(by_path[f["path"]].get("patch", "")),
        }
        for f in plan["files"]
    ]

    overview = plan["overview"]
    segments = [
        {
            "path": None,
            "role": overview["role"],
            "speech": overview.get("speech", ""),
            "notes": overview.get("notes", []),
        }
    ]
    segments += [
        {"path": f["path"], "tier": f["tier"], "role": f["role"], "speech": "", "notes": []}
        for f in plan["files"]
    ]

    content = {
        "pr": {
            "owner": plan["pr"]["owner"],
            "repo": plan["pr"]["repo"],
            "num": plan["pr"]["num"],
            "title": pr["title"],
            "url": pr["html_url"],
            "headSha": pr["head"]["sha"],
        },
        "files": files,
        "segments": segments,
        "audio": {},
    }
    if plan.get("audioPending"):
        content["audioPending"] = True
    if plan.get("listen"):
        content["listen"] = plan["listen"]
    return content


def write_slices(plan: dict, files_raw: list[dict], out_dir: Path) -> list[Path]:
    """One brief per authoring agent, on disk, patches included.

    The dispatch prompt names one of these paths instead of carrying the
    patches inline. Inlining cost three minutes of serial prompt-writing on
    a 29-file PR, and truncated the largest file on the way through — the
    subagent was told to go and find the rest itself.
    """
    by_path = {f["filename"]: f for f in files_raw}
    groups: dict = {}
    for i, f in enumerate(plan["files"]):
        groups.setdefault(f.get("slice", i // SLICE_SIZE + 1), []).append(f)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for n, (label, members) in enumerate(groups.items(), start=1):
        brief = {
            "slice": label,
            "pr": plan["pr"],
            "checkout": plan.get("checkout"),
            "files": [
                {
                    "path": f["path"],
                    "tier": f["tier"],
                    "role": f["role"],
                    "stat": {
                        "additions": by_path[f["path"]].get("additions", 0),
                        "deletions": by_path[f["path"]].get("deletions", 0),
                    },
                    "patch": by_path[f["path"]].get("patch", ""),
                }
                for f in members
            ],
        }
        p = out_dir / f"{n:02d}.json"
        p.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(p)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shell", help="plan + gh output -> shell file + slice briefs")
    s.add_argument("--plan", required=True, type=Path)
    s.add_argument("--pr", required=True, type=Path, help="gh api .../pulls/N")
    s.add_argument("--files", required=True, type=Path, help="gh api .../pulls/N/files")
    s.add_argument("--out", required=True, type=Path)
    s.add_argument("--template", type=Path, default=Path(__file__).parent / "template.html")
    s.add_argument("--slices", type=Path, help="directory for the per-agent briefs")
    a = ap.parse_args(argv)

    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    pr = json.loads(a.pr.read_text(encoding="utf-8"))
    files_raw = json.loads(a.files.read_text(encoding="utf-8"))

    content = shell_content(plan, pr, files_raw)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    write_review(a.out, content, template=a.template)
    print(f"wrote {a.out} ({a.out.stat().st_size} bytes, {len(content['files'])} files)")

    slices = a.slices or a.plan.parent / "slices"
    for p in write_slices(plan, files_raw, slices):
        n = len(json.loads(p.read_text())["files"])
        print(f"  slice {p} ({n} file{'s' if n != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
