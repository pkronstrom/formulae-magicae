#!/usr/bin/env python3
"""Resolve a podcast-aggregator URL to the episode's real media URL.

Aggregators like Pocket Casts are only directories — the audio lives on the show's own
RSS feed. yt-dlp has no extractor for them, but every podcast feed is public, so the
episode can be found in three hops:

    aggregator page  ->  show's RSS feed  ->  the <enclosure> whose title matches

Feed discovery tries the page's own `<link rel=alternate>` first, then any feed-shaped
URL on the page, then the iTunes Search API (free, no key, covers ~every podcast).

Prints JSON on stdout. When the URL is not a known aggregator it echoes the input back
with `"resolved": false` and makes no network calls, so it is safe to run on every URL.

    resolve.py <url>
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

# Directory sites with no yt-dlp extractor, where the page names an episode that
# actually lives on someone else's feed.
AGGREGATORS = (
    "pocketcasts.com",
    "pca.st",
    "overcast.fm",
    "castro.fm",
    "player.fm",
    "podcastaddict.com",
    "podcasts.google.com",
    "castbox.fm",
    "podchaser.com",
    "listennotes.com",
)

AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TIMEOUT = 30


def fetch(url, limit=4_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(limit).decode("utf-8", "replace")


def meta_tag(html, prop):
    pattern = (
        r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]*'
        r'content=["\'](.*?)["\']'
    )
    match = re.search(pattern, html, re.I | re.S)
    if not match:
        pattern = (
            r'<meta[^>]+content=["\'](.*?)["\'][^>]*'
            r'(?:property|name)=["\']' + re.escape(prop) + r'["\']'
        )
        match = re.search(pattern, html, re.I | re.S)
    return unescape(match.group(1)) if match else ""


def unescape(text):
    import html as html_module

    return html_module.unescape(text or "").strip()


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def similarity(a, b):
    """Containment first, then token overlap — episode titles differ by a prefix."""
    left, right = normalize(a), normalize(b)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    first, second = set(left.split()), set(right.split())
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def feed_candidates(html, url):
    found = []

    for match in re.finditer(r"<link[^>]+>", html, re.I):
        tag = match.group(0)
        if "application/rss+xml" in tag.lower() or "application/atom" in tag.lower():
            href = re.search(r'href=["\'](.*?)["\']', tag, re.I)
            if href:
                found.append(urllib.parse.urljoin(url, unescape(href.group(1))))

    for match in re.finditer(r'https?://[^"\'<>\\ ]+', html):
        candidate = match.group(0)
        if re.search(r"(rss|feed)", candidate, re.I) and not candidate.endswith(
            (".js", ".css", ".png", ".jpg", ".webp", ".mp3")
        ):
            found.append(candidate)

    seen = set()
    return [f for f in found if not (f in seen or seen.add(f))]


def show_name(html, url):
    """Best guess at the show, for the iTunes lookup."""
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    for index, part in enumerate(parts):
        if part in ("podcast", "podcasts", "show", "p") and index + 1 < len(parts):
            nxt = parts[index + 1]
            if not re.fullmatch(r"[0-9a-f-]{20,}", nxt):
                return nxt.replace("-", " ")
    return meta_tag(html, "og:site_name") or ""


def itunes_feed(name):
    if not name:
        return []
    query = urllib.parse.urlencode({"term": name, "entity": "podcast", "limit": 5})
    try:
        payload = json.loads(fetch(f"https://itunes.apple.com/search?{query}"))
    except Exception:
        return []
    out = []
    for entry in payload.get("results", []):
        if entry.get("feedUrl"):
            out.append((entry["feedUrl"], entry.get("collectionName", "")))
    return out


def match_in_feed(feed_url, episode_title):
    try:
        xml = fetch(feed_url)
    except Exception:
        return None

    series = ""
    head = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", xml, re.S)
    if head:
        series = unescape(head.group(1))

    best = None
    for item in re.findall(r"<item[ >].*?</item>", xml, re.S):
        title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
        enclosure = re.search(r"<enclosure[^>]+url=[\"'](.*?)[\"']", item, re.S)
        if not title or not enclosure:
            continue
        score = similarity(episode_title, unescape(title.group(1)))
        if best is None or score > best[0]:
            duration = re.search(r"<itunes:duration>(.*?)</itunes:duration>", item, re.S)
            best = (
                score,
                {
                    "url": unescape(enclosure.group(1)),
                    "title": unescape(title.group(1)),
                    "series": series,
                    "duration": unescape(duration.group(1)) if duration else "",
                },
            )
    if best and best[0] >= 0.45:
        return best[1]
    return None


def resolve(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not any(host == a or host.endswith("." + a) for a in AGGREGATORS):
        return {"url": url, "resolved": False, "reason": "not an aggregator"}

    try:
        html = fetch(url)
    except Exception as error:
        return {"url": url, "resolved": False, "reason": f"page fetch failed: {error}"}

    episode = meta_tag(html, "og:title") or meta_tag(html, "twitter:title")
    if not episode:
        return {"url": url, "resolved": False, "reason": "no episode title on page"}

    for feed in feed_candidates(html, url)[:5]:
        hit = match_in_feed(feed, episode)
        if hit:
            hit["resolved"] = True
            hit["via"] = feed
            return hit

    for feed, name in itunes_feed(show_name(html, url)):
        hit = match_in_feed(feed, episode)
        if hit:
            hit["resolved"] = True
            hit["via"] = feed
            hit["series"] = hit["series"] or name
            return hit

    return {
        "url": url,
        "resolved": False,
        "reason": f"no feed match for {episode!r}",
        "title": episode,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    args = parser.parse_args()
    result = resolve(args.url)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
