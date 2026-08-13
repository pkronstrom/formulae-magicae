#!/usr/bin/env python3
"""Stage 3: render a self-contained, annotatable HTML summary.

Takes a sections file written by the agent after it has looked at the contact sheets,
embeds the referenced frames as base64, and appends the full transcript inside a
collapsed section. The result is one file that works offline, and that the reader can
highlight, annotate, and save in place.

  {
    "summary": "one paragraph overview",
    "sections": [
      {"title": "...", "time": 352, "frame": "frames/0352.jpg", "text": "..."}
    ]
  }

`--sections` is optional: without it you get the transcript on its own, which is the
useful shape for a podcast.
"""

import argparse
import base64
import json
import mimetypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from transcript import dedupe, format_timestamp, paragraphs, parse_vtt  # noqa: E402

TEMPLATE_PATH = "app_template.html"


TOTAL_BUDGET = 5_000_000

# Tried best-first. Frames are worth real bytes — they are the reason the artifact
# exists — so quality is only traded away when the frame count demands it.
LADDER = [(1600, 90), (1280, 86), (1000, 80), (800, 72), (640, 65)]


def encode(path, width, quality):
    import io

    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        if image.width > width:
            height = round(image.height * width / image.width)
            image = image.resize((width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()


def embed(path, allowance):
    """Inline a frame at the best quality that fits its share of the budget.

    base64 costs 4 bytes per 3, which the allowance already accounts for.
    """
    try:
        chosen = None
        for width, quality in LADDER:
            data = encode(path, width, quality)
            chosen = data
            if len(data) <= allowance:
                break
        data = chosen
        kind = "image/jpeg"
    except Exception:  # Pillow missing or an unreadable image: inline as-is.
        kind = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as handle:
            data = handle.read()
    return f"data:{kind};base64,{base64.b64encode(data).decode('ascii')}"


def frame_allowance(directory, spec, transcript_bytes):
    """Bytes each frame may occupy, once the text has taken its share."""
    wanted = 0
    for entry in spec.get("sections", []):
        frame = entry.get("frame")
        if not frame:
            continue
        path = frame if os.path.isabs(frame) else os.path.join(directory, frame)
        if os.path.exists(path):
            wanted += 1
    if not wanted:
        return 0
    # Template and text overhead first; the remainder is split evenly, then
    # de-rated by 4/3 because base64 inflates whatever we encode.
    spare = TOTAL_BUDGET - transcript_bytes - 60_000
    return max(40_000, int(spare / wanted * 0.75))


def build_blocks(directory, spec, allowance):
    blocks = []

    lede = spec.get("summary", "")
    if lede:
        blocks.append({"id": "lede", "kind": "lede", "text": lede})

    for number, entry in enumerate(spec.get("sections", []), start=1):
        block = {
            "id": f"s{number}",
            "kind": "section",
            "title": entry.get("title", ""),
            "text": entry.get("text", ""),
            "time": entry.get("time"),
        }
        frame = entry.get("frame")
        if frame:
            path = frame if os.path.isabs(frame) else os.path.join(directory, frame)
            if os.path.exists(path):
                block["frame"] = embed(path, allowance)
            else:
                sys.stderr.write(f"summary.py: missing frame {path}\n")
        blocks.append(block)

    vtt = os.path.join(directory, "transcript.vtt")
    if os.path.exists(vtt):
        cues = dedupe(parse_vtt(open(vtt, encoding="utf-8").read()))
        for start, text in paragraphs(cues, 30.0):
            blocks.append(
                {
                    "id": f"t{int(start)}",
                    "kind": "transcript",
                    "time": start,
                    "text": text,
                }
            )
    return blocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="output directory of a run")
    parser.add_argument("--sections", default="", help="sections JSON (optional)")
    parser.add_argument("--out", default="", help="output path (default <dir>/summary.html)")
    args = parser.parse_args()

    meta = json.load(open(os.path.join(args.dir, "meta.json"), encoding="utf-8"))
    spec = {}
    if args.sections:
        spec = json.load(open(args.sections, encoding="utf-8"))

    vtt_path = os.path.join(args.dir, "transcript.vtt")
    transcript_bytes = os.path.getsize(vtt_path) if os.path.exists(vtt_path) else 0
    blocks = build_blocks(
        args.dir, spec, frame_allowance(args.dir, spec, transcript_bytes)
    )
    if not blocks:
        sys.stderr.write("summary.py: nothing to render\n")
        return 1

    state = {
        "v": 1,
        "savedAt": 0,
        "meta": {
            "id": meta.get("id") or "media",
            "title": meta.get("title") or "Untitled",
            "channel": meta.get("channel") or meta.get("uploader") or meta.get("series") or "",
            "duration": format_timestamp(meta.get("duration") or 0),
            "url": meta.get("webpage_url") or "",
            "linkTemplate": meta.get("link_template") or "",
            "source": meta.get("transcript_source") or "",
        },
        "blocks": blocks,
        "annotations": [],
    }

    template = open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_PATH),
        encoding="utf-8",
    ).read()

    # Escaping "<" keeps any text in the state from terminating the data block.
    payload = json.dumps(state, indent=2, ensure_ascii=False).replace("<", "\\u003c")
    document = template.replace("__TITLE__", state["meta"]["title"]).replace(
        "__DATA__", payload
    )

    out = args.out or os.path.join(args.dir, "summary.html")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(document)

    frames = sum(1 for b in blocks if b.get("frame"))
    sys.stderr.write(
        f"summary.py: {len(blocks)} blocks, {frames} frames, "
        f"{os.path.getsize(out) / 1024:.0f} KB\n"
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
