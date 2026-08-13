#!/usr/bin/env python3
"""Build index.md - the file an agent reads first.

Carries the metadata, the chapter outline, and one row per selected frame pairing a
timestamp with the line spoken at that moment, so a single read establishes what the
video contains and what is available to look at.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from transcript import format_timestamp, parse_vtt  # noqa: E402


def line_at(cues, time):
    for start, end, body in cues:
        if start <= time <= end:
            return body
    nearest = min(cues, key=lambda cue: abs(cue[0] - time), default=None)
    return nearest[2] if nearest else ""


def truncate(text, limit=110):
    text = text.replace("|", "\\|").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--frames", default="")
    parser.add_argument("--vtt", default="")
    parser.add_argument("--sheets", default="")
    args = parser.parse_args()

    meta = json.load(open(args.meta, encoding="utf-8"))
    frames = []
    if args.frames and os.path.exists(args.frames):
        frames = json.load(open(args.frames, encoding="utf-8"))
    cues = []
    if args.vtt and os.path.exists(args.vtt):
        cues = parse_vtt(open(args.vtt, encoding="utf-8").read())
    sheets = []
    if args.sheets and os.path.exists(args.sheets):
        sheets = json.load(open(args.sheets, encoding="utf-8"))

    url = meta.get("webpage_url", "")
    out = [f"# {meta.get('title', 'Untitled')}\n"]
    out.append(
        f"- **Channel:** {meta.get('channel') or meta.get('uploader') or 'unknown'}\n"
        f"- **Duration:** {format_timestamp(meta.get('duration') or 0)}\n"
        f"- **URL:** {url}\n"
        f"- **Transcript source:** {meta.get('transcript_source', 'unknown')}\n"
    )

    out.append("\n## How to read this\n")
    out.append(
        "1. Skim the frame table below.\n"
        "2. Look at `sheets/` — every selected frame, tiled and timestamped.\n"
        "3. Open individual files in `frames/` only where detail matters.\n"
        "4. `transcript.md` carries the full text with clickable timestamps.\n"
    )

    chapters = meta.get("chapters") or []
    if chapters:
        out.append("\n## Chapters\n")
        for chapter in chapters:
            stamp = format_timestamp(chapter.get("start_time") or 0)
            out.append(f"- **{stamp}** {chapter.get('title', '')}")
        out.append("")

    if sheets:
        out.append("\n## Contact sheets\n")
        for path in sheets:
            out.append(f"- `{os.path.relpath(path, os.path.dirname(args.meta))}`")
        out.append("")

    if frames:
        out.append("\n## Frames\n")
        out.append("| Time | Frame | Why | Said at that moment |")
        out.append("|---|---|---|---|")
        for entry in frames:
            stamp = format_timestamp(entry["time"])
            rel = os.path.relpath(entry["path"], os.path.dirname(args.meta))
            said = truncate(line_at(cues, entry["time"])) if cues else ""
            out.append(f"| {stamp} | `{rel}` | {entry['reason']} | {said} |")
        out.append("")

    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
