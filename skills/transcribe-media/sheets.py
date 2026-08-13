#!/usr/bin/env python3
"""Tile extracted frames into labelled 3x3 contact sheets.

This ffmpeg build has no drawtext filter (no libfreetype), so labels are drawn with
Pillow. Each cell carries its timestamp, because the whole point of a sheet is being
able to say "look at 05:52" and then read that frame at full resolution.
"""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
COLS = 3
ROWS = 3
CELL_WIDTH = 480
LABEL_HEIGHT = 26
PAD = 6


def load_font(size):
    for path in FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def format_timestamp(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_sheet(entries, font, cell_size):
    cell_w, cell_h = cell_size
    sheet_w = COLS * (cell_w + PAD) + PAD
    sheet_h = ROWS * (cell_h + LABEL_HEIGHT + PAD) + PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 27))
    draw = ImageDraw.Draw(sheet)

    for index, entry in enumerate(entries):
        col = index % COLS
        row = index // COLS
        x = PAD + col * (cell_w + PAD)
        y = PAD + row * (cell_h + LABEL_HEIGHT + PAD)
        with Image.open(entry["path"]) as frame:
            frame = frame.convert("RGB")
            frame.thumbnail((cell_w, cell_h))
            offset_x = x + (cell_w - frame.width) // 2
            offset_y = y + (cell_h - frame.height) // 2
            sheet.paste(frame, (offset_x, offset_y))
        label = f"{format_timestamp(entry['time'])}  ({entry['reason']})"
        draw.text((x + 2, y + cell_h + 4), label, fill=(235, 235, 235), font=font)
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", required=True, help="frames.json")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    entries = json.load(open(args.frames, encoding="utf-8"))
    entries = [e for e in entries if e.get("path") and os.path.exists(e["path"])]
    if not entries:
        sys.stderr.write("sheets.py: no frames to tile\n")
        return 1

    with Image.open(entries[0]["path"]) as first:
        ratio = first.height / first.width
    cell_size = (CELL_WIDTH, int(CELL_WIDTH * ratio))

    os.makedirs(args.out_dir, exist_ok=True)
    font = load_font(18)
    per_sheet = COLS * ROWS
    written = []
    for number, start in enumerate(range(0, len(entries), per_sheet), start=1):
        chunk = entries[start : start + per_sheet]
        path = os.path.join(args.out_dir, f"grid_{number:02d}.jpg")
        build_sheet(chunk, font, cell_size).save(path, quality=85)
        written.append(path)

    json.dump(written, sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.stderr.write(f"sheets.py: {len(written)} sheets from {len(entries)} frames\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
