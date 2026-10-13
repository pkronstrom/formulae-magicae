#!/usr/bin/env python3
"""Print what a review will actually run, through which providers, and what the
metered slots are likely to cost — before anything is dispatched.

Usage:
  preflight.py --roster "codex:gpt-6.1-sol@high,claude:sonnet,pi:z-ai/glm-5.2" \
               [--diff /tmp/review-diff.patch] [--json]

Prices come from OpenRouter's live model list, cached for a day. A hardcoded
price table goes stale silently and is then quoted with total confidence, which
is the one failure mode a cost estimate must not have.
"""
import argparse, json, os, time, urllib.request
from pathlib import Path

CACHE = Path(os.path.expanduser("~/.cache/review-work/or-models.json"))
CACHE_TTL = 86400

# Which budget a slot draws on. A dollar figure alone is misleading across
# these: only `metered` is cash.
POOL = {"codex": "account-dependent", "agy": "account-dependent", "claude": "account-dependent",
        "pi": "metered", "or": "metered", "openrouter": "metered"}


def prices():
    """{model_id: (in_$/tok, out_$/tok)} from OpenRouter, cached for a day."""
    data = None
    try:
        if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_TTL:
            data = json.loads(CACHE.read_text())
        else:
            with urllib.request.urlopen(
                    "https://openrouter.ai/api/v1/models", timeout=20) as r:
                data = json.load(r)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data))
    except Exception:
        if CACHE.exists():
            data = json.loads(CACHE.read_text())   # stale beats nothing
    if not data:
        return {}
    out = {}
    for m in data.get("data", []):
        p = m.get("pricing") or {}
        try:
            out[m["id"]] = (float(p.get("prompt", 0)), float(p.get("completion", 0)))
        except (TypeError, ValueError):
            continue
    return out


def estimate(model, tool, diff_bytes, px):
    """Rough token profile -> dollars. Returns (cost_or_None, note_or_None)."""
    slug = model.lstrip("~").split("@")[0]
    if POOL.get(tool) != "metered":
        return None, POOL.get(tool, "unknown")
    pin, pout = px.get(slug, (None, None))
    if pin is None:
        return None, "unpriced slug"
    # The diff plus prompt and schema is the floor. `pi` has file tools and
    # reads around the repo, which becomes most of its input; `or` cannot look
    # past the diff, so its input is the diff and nothing else.
    tok_in = 2000 + diff_bytes / 3.5
    if tool == "pi":
        tok_in *= 3
    tok_out = 3000
    return tok_in * pin + tok_out * pout, None


def parse_roster(spec):
    slots = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        tool, _, model = part.partition(":")
        slots.append((tool.strip(), model.strip() or "(default)"))
    return slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", required=True)
    ap.add_argument("--diff")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    diff_bytes = Path(a.diff).stat().st_size if a.diff and Path(a.diff).exists() else 0
    px = prices()
    rows, total, unpriced = [], 0.0, False
    for tool, model in parse_roster(a.roster):
        cost, note = estimate(model, tool, diff_bytes, px)
        if cost is not None:
            total += cost
        elif POOL.get(tool) == "metered":
            unpriced = True
        rows.append({"backend": tool, "model": model,
                     "pool": POOL.get(tool, "unknown"),
                     "cost_usd": cost, "note": note})

    if a.json:
        print(json.dumps({"slots": rows, "metered_total_usd": round(total, 4),
                          "diff_bytes": diff_bytes}, indent=2))
        return

    print(f"\nReview plan - {len(rows)} agents, diff {diff_bytes/1024:.1f} KB\n")
    print(f"  {'backend':<9} {'model':<36} {'pool':<10} est. cost")
    print("  " + "-" * 70)
    for r in rows:
        c = (f"${r['cost_usd']:.3f}" if r["cost_usd"] is not None
             else ("-" if r["pool"] != "metered" else f"? ({r['note']})"))
        print(f"  {r['backend']:<9} {r['model']:<36} {r['pool']:<10} {c}")
    metered = [r for r in rows if r["pool"] == "metered"]
    print()
    if metered:
        print(f"  {len(metered)} slot(s) via OpenRouter - real cash, est. "
              f"${total:.3f} total{' (+unpriced slugs)' if unpriced else ''}")
    print("  Native-slot billing depends on the account: subscription, credits, or API usage.")
    print("  Estimates only: actual spend depends on how much the agent reads.\n")


if __name__ == "__main__":
    main()
