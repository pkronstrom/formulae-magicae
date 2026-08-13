#!/usr/bin/env python3
"""ffmpeg scdet scores -> a budgeted set of frame timestamps.

Pure stdin/stdout filter. Reads the stderr of

    ffmpeg -i in.mp4 -vf "fps=1,scale=320:-2,scdet=threshold=0" -f null -

which emits one `lavfi.scd.score` / `lavfi.scd.time` pair per sampled second, and
picks which seconds are worth extracting.

Selection runs in four passes so that a busy passage cannot eat the whole budget and
a long static stretch is still represented:

  1. chapters  - at least one frame inside each chapter
  2. change    - highest-scoring seconds, up to 80% of budget
  3. coverage  - fill gaps longer than 3x the average spacing
  4. change    - spend whatever budget is left on the next-highest scores

Every accepted frame must sit at least `duration / (4 * budget)` from its neighbours.
"""

import argparse
import json
import re
import sys

SCORE = re.compile(r"lavfi\.scd\.score:\s*([0-9.]+).*?lavfi\.scd\.time:\s*([0-9.]+)")


def parse_scores(text):
    """Yield (time, score), skipping the first frame which always scores 0."""
    found = []
    for match in SCORE.finditer(text):
        score = float(match.group(1))
        time = float(match.group(2))
        found.append((time, score))
    return found


def default_budget(duration):
    return max(12, min(40, round(1.2 * duration / 60)))


class Selection:
    def __init__(self, duration, budget, spacing):
        self.duration = duration
        self.budget = budget
        self.spacing = spacing
        self.picked = []

    def fits(self, time):
        return all(abs(time - other) >= self.spacing for other, _, _ in self.picked)

    def full(self):
        return len(self.picked) >= self.budget

    def add(self, time, score, reason):
        self.picked.append((time, score, reason))

    def times(self):
        return sorted(time for time, _, _ in self.picked)


def pick_chapters(sel, scores, chapters):
    for chapter in chapters:
        if sel.full():
            return
        start = float(chapter.get("start_time") or 0)
        end = float(chapter.get("end_time") or sel.duration)
        inside = [(t, s) for t, s in scores if start <= t < end and sel.fits(t)]
        if not inside:
            continue
        time, score = max(inside, key=lambda pair: pair[1])
        sel.add(time, score, "chapter")


def pick_by_change(sel, scores, limit):
    for time, score in sorted(scores, key=lambda pair: pair[1], reverse=True):
        if len(sel.picked) >= limit:
            return
        if sel.fits(time):
            sel.add(time, score, "change")


def pick_coverage(sel, scores):
    """Fill any gap wider than 3x the average spacing."""
    max_gap = 3 * sel.duration / sel.budget
    while not sel.full():
        bounds = [0.0] + sel.times() + [sel.duration]
        widest = max(
            (
                (bounds[i + 1] - bounds[i], bounds[i], bounds[i + 1])
                for i in range(len(bounds) - 1)
            ),
            default=(0, 0, 0),
        )
        width, low, high = widest
        if width <= max_gap:
            return
        inside = [(t, s) for t, s in scores if low < t < high and sel.fits(t)]
        if not inside:
            return
        time, score = max(inside, key=lambda pair: pair[1])
        sel.add(time, score, "coverage")


def select(scores, duration, budget=None, chapters=()):
    budget = budget or default_budget(duration)
    sel = Selection(duration, budget, duration / (4 * budget))
    pick_chapters(sel, scores, chapters)
    pick_by_change(sel, scores, max(1, int(budget * 0.8)))
    pick_coverage(sel, scores)
    pick_by_change(sel, scores, budget)
    return sorted(sel.picked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--chapters", default="", help="JSON file of yt-dlp chapters")
    args = parser.parse_args()

    chapters = []
    if args.chapters:
        try:
            chapters = json.load(open(args.chapters, encoding="utf-8")) or []
        except (OSError, ValueError):
            chapters = []

    scores = parse_scores(sys.stdin.read())
    if not scores:
        sys.stderr.write("select_frames.py: no scdet scores on stdin\n")
        return 1

    picked = select(scores, args.duration, args.budget or None, chapters)
    json.dump(
        [{"time": t, "score": s, "reason": r} for t, s, r in picked],
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    sys.stderr.write(
        f"select_frames.py: {len(picked)} frames from {len(scores)} sampled seconds\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
