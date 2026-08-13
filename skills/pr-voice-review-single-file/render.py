"""Pure helpers: patch parsing, block-safe JSON, size projection.

Nothing here touches the filesystem, so every hostile-input case is cheap
to test. See docs/superpowers/specs/2026-08-11-pr-voice-review-single-file-design.md
"""

import json
import re

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

WORDS_PER_SECOND = 2.4
MP3_BYTES_PER_SECOND = 3100  # measured: 24 kbps mono, 24 kHz
BASE64_INFLATION = 4 / 3


def json_for_block(obj) -> str:
    """Pretty-printed JSON safe to embed in an inline <script> element.

    Escaping every `<` to its \\u003c unicode escape is the sanctioned
    technique from singlefile 3: it is still valid JSON, so json.loads
    decodes it with no unescaping step, and no value can terminate the
    block no matter what the PR contains.
    """
    return json.dumps(obj, indent=2, ensure_ascii=False).replace("<", "\\u003c")


def parse_patch(patch: str) -> list[dict]:
    """Unified diff text -> row dicts the client renders with textContent.

    Each row is {kind, old, new, text} where kind is hunk | ctx | add | del.
    Line numbers are what the reviewer sees in the gutter, and what a note's
    from/to range is matched against.
    """
    rows: list[dict] = []
    old = new = 0
    for line in patch.splitlines():
        m = _HUNK.match(line)
        if m:
            old, new = int(m.group(1)), int(m.group(2))
            rows.append({"kind": "hunk", "old": None, "new": None, "text": line})
            continue
        # An empty line is a blank CONTEXT line whose leading space was
        # stripped somewhere. Skipping it would desynchronize both counters
        # and silently misplace every highlight below it.
        marker, text = (line[0], line[1:]) if line else (" ", "")
        if marker == "+":
            rows.append({"kind": "add", "old": None, "new": new, "text": text})
            new += 1
        elif marker == "-":
            rows.append({"kind": "del", "old": old, "new": None, "text": text})
            old += 1
        elif marker == "\\":
            continue  # "\ No newline at end of file"
        else:
            rows.append({"kind": "ctx", "old": old, "new": new, "text": text})
            old += 1
            new += 1
    return rows


SYNTH_REALTIME = 11.0  # measured: worker pool, threads capped to cores/workers


def narration_estimate(segments: list[dict], overhead: int) -> dict:
    """What the audio question needs in order to be worth asking.

    The lens has to be settled before authoring, but audio is a cost decision
    and the cost is unknowable until the narration exists. Asking both up front
    made the second half a guess; this is what lets it be asked with numbers.

    `synth_seconds` is the cold case — anything already in the audio cache
    renders instantly, so it is an upper bound, never an estimate of a rebuild.
    """
    words = chunks = 0
    for seg in segments:
        if seg.get("speech", "").strip():
            words += len(seg["speech"].split())
            chunks += 1
        for note in seg.get("notes", []):
            if note.get("speech", "").strip():
                words += len(note["speech"].split())
                chunks += 1
    seconds = words / WORDS_PER_SECOND
    return {
        "words": words,
        "chunks": chunks,
        "seconds": round(seconds),
        "synth_seconds": round(seconds / SYNTH_REALTIME),
        "bytes": project_bytes(segments, overhead),
    }


def project_bytes(segments: list[dict], overhead: int) -> int:
    """Estimate the finished file's size before synthesizing anything.

    Gating on this rather than on the assembled file is what stops a
    forty-file PR from burning the entire Kokoro pass before being told it
    is over budget. `overhead` is the renderer plus rendered diff, both of
    which are already known when this is called.
    """
    words = 0
    for seg in segments:
        words += len(seg.get("speech", "").split())
        for note in seg.get("notes", []):
            words += len(note.get("speech", "").split())
    seconds = words / WORDS_PER_SECOND
    return int(seconds * MP3_BYTES_PER_SECOND * BASE64_INFLATION) + overhead
