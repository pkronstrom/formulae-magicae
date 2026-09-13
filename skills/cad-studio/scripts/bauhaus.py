#!/usr/bin/env python3
"""bauhaus.py — prices from bauhaus.fi without a browser.

The site itself serves a Vercel bot challenge (HTTP 429) to curl/WebFetch, but its search runs on Algolia with a
public search-only key embedded in every page; the Algolia REST API answers plain HTTPS in <1 s and each hit
carries the piece price and the unit price (€/m, €/m², €/kpl).

    bauhaus.py "48x198 mitallistettu"                 # search → table
    bauhaus.py "lattialastulevy 22" --json            # raw hits (name, sku, price, unit price, url, stock)
    bauhaus.py --category puutavara --hits 50         # filter by category path substring

If Algolia ever stops answering (key rotated: grep the page for "algoliaApiKey"), fall back to headless Chrome:
    bauhaus.py --chrome runkotolppa-c24-48-x-198-mm-mitallistettu
"""
import json, re, subprocess, sys, tempfile, html, urllib.request

APP, KEY = "PR1NXR88J1", "c03d0ab869371054066f25c42dd9b1ea"     # from bauhaus.fi page source, 2026-09-13
INDEX = "nordic_production_fi_products"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def search(query, hits=20, category=None):
    body = {"query": query, "hitsPerPage": hits}
    if category: body["filters"] = f'categories_without_path:"{category}"' if " " in category else None
    req = urllib.request.Request(f"https://{APP}-dsn.algolia.net/1/indexes/{INDEX}/query",
                                 data=json.dumps({k: v for k, v in body.items() if v}).encode(),
                                 headers={"X-Algolia-Application-Id": APP, "X-Algolia-API-Key": KEY, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    out = []
    for h in d.get("hits", []):
        p = (h.get("price") or {}).get("EUR", {})
        cats = h.get("categories_without_path") or []
        if category and not any(category.lower() in c.lower() for c in cats): continue
        out.append({"name": h.get("name"), "sku": h.get("sku"), "piece": p.get("group_0"),
                    "unit_price": p.get("group_0_unit_price"), "unit": (p.get("group_0_unit_price_formatted") or "").split("/")[-1] or None,
                    "in_stock": h.get("in_stock"), "url": h.get("url"), "categories": cats[:3]})
    return out

def chrome_product(slug_or_url):
    url = slug_or_url if slug_or_url.startswith("http") else "https://www.bauhaus.fi/" + slug_or_url.lstrip("/")
    prof = tempfile.mkdtemp(prefix="bauhaus-chrome-")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--user-data-dir={prof}", "--disable-gpu", "--no-first-run",
                             "--virtual-time-budget=15000", "--dump-dom", url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try: t, _ = proc.communicate(timeout=25)              # Chrome prints the DOM then keeps running; kill and keep stdout
    except subprocess.TimeoutExpired: proc.kill(); t, _ = proc.communicate()
    t = html.unescape(t)
    ld = re.search(r'<script type="application/ld\+json">(\{"@context":"https://schema.org","@type":"Product".*?\})</script>', t, re.S)
    d = json.loads(ld.group(1)) if ld else {}
    price = (d.get("offers") or {}).get("price")
    L = re.search(r'\\?"code\\?":\\?"lengthlist\\?".*?\\?"label\\?":\\?"(\d+) mm', t)
    L = int(L.group(1)) if L else None
    return {"name": d.get("name"), "sku": d.get("sku"), "piece": price, "length_mm": L,
            "unit_price": round(price / (L / 1000), 2) if price and L else None, "url": d.get("url")}

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    if a[0] == "--chrome": print(json.dumps(chrome_product(a[1]), ensure_ascii=False, indent=1)); sys.exit()
    q = next((x for x in a if not x.startswith("--") and (a.index(x) == 0 or a[a.index(x) - 1] not in ("--category", "--hits"))), "")
    cat = a[a.index("--category") + 1] if "--category" in a else None
    n = int(a[a.index("--hits") + 1]) if "--hits" in a else 20
    rows = search(q, n, cat)
    if "--json" in a: print(json.dumps(rows, ensure_ascii=False, indent=1)); sys.exit()
    for r in rows:
        up = f"{r['unit_price']:.2f} €/{r['unit']}" if r["unit_price"] else ""
        print(f"{(r['piece'] or 0):8.2f} €  {up:>14}  {(r['name'] or '')[:58]:58s} {r['sku']}  {'stock' if r['in_stock'] else '-'}")
