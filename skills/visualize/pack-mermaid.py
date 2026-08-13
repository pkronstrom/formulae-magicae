#!/usr/bin/env python3
"""Compress or expand the Mermaid bundle inside template.html.

The bundle is ~3.56 MB of the template's ~3.95 MB. Stored as raw-deflate +
base64 it is 1.29 MB, which takes the whole file to ~1.68 MB — a 57% cut with
no cost over HTTP (measured: gzipped, the two forms are within 1% of each
other, because a server was already compressing the plain form).

The saving is entirely for delivery paths with no transport compression:
email, USB, chat upload, plain disk.

    pack-mermaid.py            # compress in place (no-op if already packed)
    pack-mermaid.py --unpack   # expand, to edit or upgrade Mermaid
    pack-mermaid.py --check    # report state and sizes, change nothing

Upgrading Mermaid: --unpack, replace the block contents, then pack again.

Base64 cannot contain '<', so the packed form also removes any chance of the
bundle terminating its own script element — a hazard the plain form lives with.
"""

import argparse
import base64
import pathlib
import re
import sys
import zlib

TEMPLATE = pathlib.Path(__file__).parent / "template.html"
PACKED_TYPE = "viz/deflate-b64"
OPEN_RE = re.compile(r'<script id="viz-mermaid"(?P<attrs>[^>]*)>')


def find_block(html):
    """Return (match, body_start, body_end, is_packed) for the Mermaid block."""
    m = OPEN_RE.search(html)
    if not m:
        sys.exit("pack-mermaid: no #viz-mermaid block in template.html")
    end = html.find("</script>", m.end())
    if end < 0:
        sys.exit("pack-mermaid: #viz-mermaid block is not closed")
    return m, m.end(), end, PACKED_TYPE in m.group("attrs")


def pack(html):
    m, start, end, is_packed = find_block(html)
    if is_packed:
        return html, False
    raw = html[start:end].encode()
    # Raw deflate (no zlib header/checksum) to match DecompressionStream's
    # "deflate-raw", which is the widely supported mode.
    payload = base64.b64encode(zlib.compress(raw, 9)[2:-4]).decode()
    return (
        html[: m.start()]
        + f'<script id="viz-mermaid" type="{PACKED_TYPE}">\n{payload}\n'
        + html[end:]
    ), True


def unpack(html):
    m, start, end, is_packed = find_block(html)
    if not is_packed:
        return html, False
    payload = html[start:end].strip()
    raw = zlib.decompress(base64.b64decode(payload), -15).decode()
    return html[: m.start()] + '<script id="viz-mermaid">' + raw + html[end:], True


def report(html, label):
    m, start, end, is_packed = find_block(html)
    print(
        f"{label:<10} block={end - start:>10,} chars  "
        f"file={len(html.encode()):>10,} bytes  "
        f"state={'packed' if is_packed else 'plain'}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--unpack", action="store_true", help="expand the bundle")
    g.add_argument("--check", action="store_true", help="report state, change nothing")
    args = ap.parse_args()

    html = TEMPLATE.read_text(encoding="utf-8")
    if args.check:
        report(html, "current")
        return

    report(html, "before")
    out, changed = (unpack if args.unpack else pack)(html)
    if not changed:
        print("no change: already in the requested state")
        return

    # Round-trip before writing. A corrupted template is far worse than a big one.
    check = (pack if args.unpack else unpack)(out)[0]
    if check != html:
        sys.exit("pack-mermaid: round-trip mismatch, refusing to write")

    TEMPLATE.write_text(out, encoding="utf-8")
    report(out, "after")


if __name__ == "__main__":
    main()
