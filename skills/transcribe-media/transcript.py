#!/usr/bin/env python3
"""VTT -> timestamped markdown.

Pure stdin/stdout filter. Handles both YouTube captions (which repeat the previous
cue's tail on every line) and parakeet-mlx output (which does not).
"""

import argparse
import re
import sys

TAG = re.compile(r"<[^>]*>")
CUE = re.compile(
    r"((?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{3})"
)


def parse_timestamp(text):
    """Parse HH:MM:SS.mmm or MM:SS.mmm.

    yt-dlp and parakeet always write the hour field; mlx-whisper drops it on short
    files, and a parser that assumes three components silently yields no cues at all.
    """
    parts = text.replace(",", ".").split(":")
    seconds = float(parts[-1])
    if len(parts) > 1:
        seconds += int(parts[-2]) * 60
    if len(parts) > 2:
        seconds += int(parts[-3]) * 3600
    return seconds


def format_timestamp(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_vtt(text):
    """Yield (start, end, text) for every cue."""
    cues = []
    start = end = None
    lines = []

    def flush():
        if start is None:
            return
        body = " ".join(lines).strip()
        if body:
            cues.append((start, end, body))

    for raw in text.splitlines():
        line = raw.strip()
        match = CUE.search(line)
        if match:
            flush()
            start = parse_timestamp(match.group(1))
            end = parse_timestamp(match.group(2))
            lines = []
            continue
        if not line:
            flush()
            start = end = None
            lines = []
            continue
        if start is None:
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        cleaned = TAG.sub("", line).replace("&nbsp;", " ").strip()
        if cleaned:
            lines.append(cleaned)
    flush()
    return cues


def dedupe(cues):
    """Strip rolling repetition.

    YouTube auto-captions restate the previous cue's trailing words. For each cue we
    find the longest suffix of what we have already emitted that is also a prefix of
    the incoming cue, and keep only the remainder.
    """
    emitted = []
    result = []
    for start, end, body in cues:
        words = body.split()
        if not words:
            continue
        overlap = 0
        limit = min(len(emitted), len(words))
        for size in range(limit, 0, -1):
            if [w.lower() for w in emitted[-size:]] == [
                w.lower() for w in words[:size]
            ]:
                overlap = size
                break
        fresh = words[overlap:]
        if not fresh:
            continue
        emitted.extend(fresh)
        result.append((start, end, " ".join(fresh)))
    return result


def paragraphs(cues, window, gap=1.2, floor=12.0):
    """Merge cues into readable blocks.

    A block ends at a silence longer than `gap` — which is where a speaker actually
    finishes a thought, so paragraphs land on natural breaks instead of on a stopwatch
    — or at `window` seconds, whichever comes first. `floor` stops rapid back-and-forth
    from shattering into one-line fragments.
    """
    blocks = []
    current = []
    anchor = None
    previous_end = None

    for start, end, body in cues:
        if anchor is None:
            anchor = start
        elif (
            start - previous_end >= gap
            and previous_end - anchor >= floor
        ):
            blocks.append((anchor, " ".join(current)))
            current = []
            anchor = start
        current.append(body)
        previous_end = end
        if end - anchor >= window:
            blocks.append((anchor, " ".join(current)))
            current = []
            anchor = None

    if current:
        blocks.append((anchor or 0.0, " ".join(current)))
    return blocks


def render(blocks, link_template, title):
    out = []
    if title:
        out.append(f"# {title}\n")
    for start, body in blocks:
        stamp = format_timestamp(start)
        # Not every service supports deep links into a timestamp; those get plain text.
        if link_template:
            out.append(
                f"**[{stamp}]({link_template.format(t=int(start))})** {body}\n"
            )
        else:
            out.append(f"**[{stamp}]** {body}\n")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vtt", nargs="?", help="VTT file (default: stdin)")
    parser.add_argument(
        "--link", default="", help="deep-link template containing {t}, e.g. 'URL?t={t}s'"
    )
    parser.add_argument("--title", default="", help="title for the H1")
    parser.add_argument(
        "--window", type=float, default=30.0, help="maximum paragraph length in seconds"
    )
    parser.add_argument(
        "--gap", type=float, default=1.2, help="silence that ends a paragraph"
    )
    args = parser.parse_args()

    raw = open(args.vtt, encoding="utf-8").read() if args.vtt else sys.stdin.read()
    cues = dedupe(parse_vtt(raw))
    if not cues:
        sys.stderr.write("transcript.py: no cues found\n")
        return 1
    sys.stdout.write(
        render(paragraphs(cues, args.window, args.gap), args.link, args.title)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
