#!/usr/bin/env python3
"""Turn an AgentShield JSON report into a short worklist for the agent.

Drops rule families that are noise for a personal harness (counted, never
silently), splits what you wrote from what a plugin shipped, and never prints
evidence for secret findings.

Usage: triage.py <scan.json> [<scan.json> ...]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

# (title prefix, why it is noise here). Keep this list short and earned:
# add an entry only after checking real findings, never to make a grade go up.
NOISE = [
    ("Missing prompt defense:", "checks for app system-prompt hardening; skills and agents are not public chatbots"),
    ("Agent definition effective size", "length is a style choice, not a security property"),
    ("Agent has no model specified", "inherits the session model by design"),
    ("No Stop hooks", "a workflow preference, not a vulnerability"),
    ("has no description", "informational"),
]
ORDER = ["critical", "high", "medium", "low", "info"]


def origin(path: str) -> str:
    return "plugin" if "/plugins/cache/" in f"/{path}" else "yours"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    dropped = defaultdict(int)
    kept = defaultdict(list)
    for report in sys.argv[1:]:
        data = json.loads(Path(report).read_text())
        root = Path(data.get("targetPath", report)).name
        print(f"{root}: grade {data['score']['grade']} ({data['score']['numericScore']}), "
              f"{data['summary']['totalFindings']} raw findings, {data['summary']['filesScanned']} files")
        for f in data["findings"]:
            noise = next(((prefix, why) for prefix, why in NOISE if prefix in f["title"]), None)
            if noise:
                dropped[noise] += 1
                continue
            secret = f["category"] in {"secrets", "exposure"}
            evidence = "[secret, not shown]" if secret else (f.get("evidence") or "").replace("\n", " ")[:100]
            kept[(f["severity"], f["title"])].append(
                (origin(f["file"]), f"{root}/{f['file']}:{f.get('line') or ''}", evidence, f.get("fix") or ""))

    print("\n## Dropped as noise")
    for (title, reason), count in sorted(dropped.items(), key=lambda x: -x[1]):
        print(f"- {count} × {title.rstrip(':')}: {reason}")

    print("\n## To triage (yours first)")
    for (severity, title), hits in sorted(kept.items(), key=lambda x: (ORDER.index(x[0][0]), x[0][1])):
        hits.sort(key=lambda h: h[0] != "yours")
        mine = sum(h[0] == "yours" for h in hits)
        print(f"\n### [{severity}] {title} — {mine} yours, {len(hits) - mine} plugin")
        for who, where, evidence, _ in hits[:5]:
            print(f"- ({who}) {where}  {evidence}")
        if len(hits) > 5:
            print(f"- … {len(hits) - 5} more")
        fix = hits[0][3]
        if isinstance(fix, dict):
            fix = fix.get("description", "")
        if fix:
            print(f"  scanner's fix: {str(fix)[:160]}")


if __name__ == "__main__":
    main()
