#!/usr/bin/env bash
# Generates the derived browser artifacts from overlay.js. Run after editing it.
#
#   overlay.min.js   comment-stripped — the paste-injection fallback
#   extension/       tiny MV3 Chrome extension: chrome://extensions → Developer mode
#                    → Load unpacked → this folder. Auto-injects on every PR page;
#                    injection cost drops to zero. The preferred install.
#   bookmarklet.txt  zero-install fallback: save as a bookmark URL, click once per
#                    page. NOTE: untested against GitHub's CSP — verify before
#                    recommending.
#
# overlay.js stays the single source of truth; never edit the outputs.

set -euo pipefail
cd "$(dirname "$0")"
[ -f overlay.js ] || { echo "overlay.js not found" >&2; exit 1; }

# Conservative strip: whole-line comments and indentation only. A broken overlay is
# far worse than a big one.
sed -e 's|^[[:space:]]*//.*$||' -e 's|^[[:space:]]*||' overlay.js | grep -v '^$' > overlay.min.js

mkdir -p extension
cp overlay.js extension/content.js
cp extension-src/bridge.js extension-src/background.js extension/ 2>/dev/null || true
VERSION="$(grep -m1 -o 'PRV\.v = [0-9]*' overlay.js | grep -o '[0-9]*' || echo 1)"
if [ -f extension-src/manifest.json ]; then
  sed "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}.0\"/" extension-src/manifest.json > extension/manifest.json
  SKIP_MANIFEST=1
fi
[ -z "${SKIP_MANIFEST:-}" ] && cat > extension/manifest.json <<EOF
{
  "manifest_version": 3,
  "name": "pr-voice-review overlay",
  "version": "${VERSION}.0",
  "description": "Walkthrough control bar for pr-voice-review. Runs only on GitHub PR pages.",
  "content_scripts": [{
    "matches": ["https://github.com/*/pull/*"],
    "js": ["content.js"],
    "run_at": "document_idle",
    "world": "MAIN"
  }]
}
EOF

# Bookmarklet: the minified overlay behind a javascript: URL.
python3 - <<'PY' > bookmarklet.txt
import urllib.parse
src = open("overlay.min.js").read()
print("javascript:" + urllib.parse.quote(src, safe="(){};,.=>&|!+-*/%'\"[]:?<>_$ "))
PY

printf '%-18s %7s bytes\n' overlay.js "$(wc -c < overlay.js)" \
  overlay.min.js "$(wc -c < overlay.min.js)" \
  extension/ "$(du -sk extension | cut -f1)K" \
  bookmarklet.txt "$(wc -c < bookmarklet.txt)"
