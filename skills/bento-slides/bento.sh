#!/bin/sh
# bento.sh — create, inspect, read and write Bento slide decks.
#
#   new "<Topic>" [--style <name>] [--dir <path>]   create a deck from the vendored runtime
#   inspect <deck>                                  non-secret metadata; the safe preflight
#   read <deck> [--allow-shared] [--with-assets]    document JSON to stdout, assets withheld
#   write <deck> <doc.json>                         replace the document, escaping mechanically
#   check <deck>                                    run validate() in headless Chrome
#   cache-path                                      print the reusable Chrome profile path
#   refresh                                         re-pull runtime + guide as a matched pair
#
# The escaping rule (every `<` in the document JSON becomes the six-character
# JSON escape `<`) is the reason this script exists. As an instruction an
# agent follows by hand it is untestable and fails silently: a deck whose text
# happens to contain `</script>` truncates its own data block, and the file
# will not open. Here it is mechanical, and the test suite covers it.
#
# Bento's own save path applies the same rule — the runtime does
# `.replace(/</g,"\\u003c")` when it rewrites the block — so a deck edited in
# the app comes back with the invariant this script expects.
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export BENTO_SKILL_DIR="$SKILL_DIR"

command -v python3 >/dev/null 2>&1 || {
    echo "bento: python3 is required but not on PATH" >&2; exit 1; }

# The pinned pair goes to stderr on every run, so a runtime/guide mismatch is
# visible rather than inferred. stdout stays clean for `read`.
GUIDE="$SKILL_DIR/reference/agents.md"
if [ -f "$GUIDE" ]; then
    _gv=$(sed -n 's/.*Guide version `\([^`]*\)`.*/\1/p' "$GUIDE" | head -1)
    _gd=$(sed -n 's/.*Fetched  *: *\([0-9-]*\).*/\1/p' "$GUIDE" | head -1)
    echo "bento: guide ${_gv:-unknown}, fetched ${_gd:-unknown}" >&2
fi

exec python3 - "$@" <<'PYEOF'
"""bento.sh internals. Argument handling and every operation on a deck file."""
import base64
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL = Path(os.environ["BENTO_SKILL_DIR"])
RUNTIME = SKILL / "runtime" / "Bento_Slides.bento.html"
GUIDE = SKILL / "reference" / "agents.md"
PRESETS = SKILL / "styles" / "presets.json"
FONTS = SKILL / "styles" / "fonts"

MANIFEST_URL = "https://bento.page/releases/slides/manifest.json"
GUIDE_URL = "https://bento.page/agents.md"

# The document block, and only it. Non-greedy is safe precisely because the
# escaping invariant guarantees the body can never contain `</script`.
DOC_BLOCK = re.compile(
    r'(<script\b[^>]*\bid="bento-doc"[^>]*>)(.*?)(</script>)', re.S)
OPEN_TAG = re.compile(r'<script\b[^>]*\bid="bento-doc"[^>]*>')
CLOSE_COUNT = re.compile(r'</script', re.I)

# Serialization is canonical so that read -> write is byte-stable. The leading
# and trailing space match what Bento's own save path emits.
DUMP = dict(indent=2, ensure_ascii=False, sort_keys=False)


def die(msg, code=1):
    print(f"bento: {msg}", file=sys.stderr)
    raise SystemExit(code)


def escape(text):
    """Every `<` becomes the JSON escape \\u003c. Structural JSON never contains
    `<`, so this only ever rewrites the inside of strings, and any parser hands
    back a plain `<`."""
    return text.replace("<", "\\u003c")


def serialize(doc):
    return escape(json.dumps(doc, **DUMP))


def load_deck(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        die(f"cannot read {path}: {e}")


def doc_of(html, path):
    blocks = OPEN_TAG.findall(html)
    if len(blocks) != 1:
        die(f"{path}: expected exactly one #bento-doc block, found {len(blocks)} "
            "— this is not a Bento deck")
    body = DOC_BLOCK.search(html).group(2).strip()
    if not body:
        die(f"{path}: the #bento-doc block is empty. This is a blank Bento shell, "
            "not a deck — use `bento.sh new` to start one")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        die(f"{path}: the document block is not valid JSON: {e}")


def collab_keys(doc):
    """Which live-session key names a document carries. Never their values."""
    collab = doc.get("collab") or {}
    if not isinstance(collab, dict):
        return []
    return [k for k in ("ownerPriv", "writerPriv", "invite") if collab.get(k)]


def atomic_write(target, text):
    """Write via a temporary file in the same directory, then rename. An
    interruption leaves the original deck intact rather than a half-written one."""
    target = Path(target)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".bento-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if target.exists():
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def inject(html, doc, path):
    """Replace the document block. Every precondition is checked before the file
    is touched — the `</script` count guard alone catches none of these."""
    if not isinstance(doc, dict):
        die("the document must be a JSON object")
    fmt = doc.get("format")
    if fmt != "bento/slides":
        die(f"document format is {fmt!r}, not 'bento/slides'. Bento has other "
            "document formats and rewriting one with the Slides contract "
            "corrupts it in a way no later check notices")
    if len(OPEN_TAG.findall(html)) != 1:
        die(f"{path}: expected exactly one #bento-doc block")

    before = len(CLOSE_COUNT.findall(html))
    body = serialize(doc)
    # A function replacement, so `<` in the body is inserted literally
    # rather than being read as a backreference escape.
    out = DOC_BLOCK.sub(
        lambda m: f"{m.group(1)} {body} {m.group(3)}", html, count=1)
    after = len(CLOSE_COUNT.findall(out))
    if after != before:
        die(f"refusing to write: the injection changed the </script count "
            f"({before} -> {after}). The escaping did not hold")
    return out


def slug(topic):
    """The raw topic reaches the filesystem otherwise: a `/`, a leading dash, a
    control character or 200 characters produce a nested, unparseable or
    invalid path."""
    norm = unicodedata.normalize("NFKD", topic)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    out = re.sub(r"[^A-Za-z0-9._-]+", "-", norm)
    out = re.sub(r"-{2,}", "-", out).strip("-._")
    out = out[:64].strip("-._")
    return out or "deck"


def load_presets():
    try:
        return json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        die(f"cannot load {PRESETS}: {e}")


def font_assets(preset, name):
    """Resolve a preset's font files into `doc.fonts` + `doc.assets`. A
    fontFamily naming a face the document does not carry falls back silently,
    so a missing blob is fatal here rather than a surprise on someone else's
    machine."""
    fonts, assets = [], {}
    for f in preset.get("fonts", []):
        blob = FONTS / f["file"]
        if not blob.is_file():
            die(f"preset {name!r} names {f['file']}, which is not in {FONTS}")
        b64 = blob.read_text(encoding="utf-8").strip()
        try:
            base64.b64decode(b64, validate=True)
        except Exception:
            die(f"{blob} is not valid base64")
        assets[f["asset"]] = f"data:font/woff2;base64,{b64}"
        entry = {"family": f["family"], "asset": f["asset"], "weight": f["weight"]}
        # `style` is honoured by the runtime (@font-face{...font-style:${r.style
        # ?? "normal"}}) though the published guide lists only family/asset/weight.
        if f.get("style"):
            entry["style"] = f["style"]
        fonts.append(entry)
    return fonts, assets


# --------------------------------------------------------------------------
# subcommands


def cmd_new(argv):
    if not argv:
        die('new: give me a topic, e.g. new "Q3 Roadmap" --style signal', 2)
    topic, argv = argv[0], argv[1:]
    style, dest = "plain", "."
    while argv:
        flag, argv = argv[0], argv[1:]
        if flag in ("--style", "--dir"):
            if not argv:
                die(f"new: {flag} needs a value", 2)
            if flag == "--style":
                style = argv[0]
            else:
                dest = argv[0]
            argv = argv[1:]
        else:
            die(f"new: unexpected argument: {flag}", 2)

    presets = load_presets()
    if style not in presets:
        die(f"unknown style {style!r}. Available: {', '.join(sorted(presets))}", 2)
    if not RUNTIME.is_file():
        die(f"no vendored runtime at {RUNTIME} — run `bento.sh refresh`")
    dest = Path(dest)
    if not dest.is_dir():
        die(f"new: no such directory: {dest}", 2)

    target = dest / f"{slug(topic)}.bento.html"
    if target.exists():
        die(f"{target} already exists. That is your work, not a build artifact — "
            "move it or pick another topic")

    preset = presets[style]
    fonts, assets = font_assets(preset, style)
    theme = dict(preset["theme"])
    doc = {
        "format": "bento/slides",
        "version": 1,
        "title": topic,
        "size": {"width": 1280, "height": 720},
        "theme": theme,
        "slides": [{
            "id": "s1",
            "background": theme["background"],
            "transition": "none",
            "notes": "",
            "elements": [{
                "id": "title", "type": "text", "role": "title",
                "x": 96, "y": 260, "w": 1088, "h": 200,
                "rotation": 0, "opacity": 1,
                "html": topic,
                "fontSize": 88, "fontFamily": theme["fontFamily"],
                "fontWeight": 800, "color": theme["color"],
                "align": "left", "valign": "top", "lineHeight": 1.1,
            }],
        }],
    }
    # `fonts` and `assets` are omitted entirely when a preset uses system
    # stacks — an empty `fonts` array would be a claim the deck does not make.
    if fonts:
        doc["fonts"] = fonts
        doc["assets"] = assets
    # docId and collab are deliberately absent: the app mints them on first open.

    html = RUNTIME.read_text(encoding="utf-8")
    atomic_write(target, inject(html, doc, str(target)))
    print(target)
    print(f"bento: style {style} — {preset['look']}", file=sys.stderr)
    return 0


def cmd_inspect(argv):
    if len(argv) != 1:
        die("inspect: which deck?", 2)
    path = argv[0]
    doc = doc_of(load_deck(path), path)
    keys = collab_keys(doc)
    size = doc.get("size") or {}
    out = {
        "file": path,
        "format": doc.get("format"),
        "version": doc.get("version"),
        "title": doc.get("title"),
        "slides": len(doc.get("slides") or []),
        "size": f"{size.get('width')}x{size.get('height')}",
        "fonts": [f.get("family") for f in (doc.get("fonts") or [])],
        "hasDocId": bool(doc.get("docId")),
        "shared": bool(keys),
        "collabKeys": keys,      # names only, never values
    }
    for k, v in out.items():
        print(f"{k:12} {v}")
    if keys:
        print(
            "\nThis deck carries live-session keys. Anything that receives the file\n"
            "or its JSON can join that session and write to it — the file is the\n"
            "invitation. Tell the user before reading it; only they can decide.\n"
            "Removing the keys afterwards does not retract them: the remedy is\n"
            "Share -> Rotate keys. To read anyway: bento.sh read --allow-shared",
            file=sys.stderr)
        return 3
    return 0


def cmd_read(argv):
    if not argv:
        die("read: which deck?", 2)
    path, argv = argv[0], argv[1:]
    allow = with_assets = False
    while argv:
        if argv[0] == "--allow-shared":
            allow, argv = True, argv[1:]
        elif argv[0] == "--with-assets":
            with_assets, argv = True, argv[1:]
        else:
            die(f"read: unexpected argument: {argv[0]}", 2)

    doc = doc_of(load_deck(path), path)
    keys = collab_keys(doc)
    if keys and not allow:
        die(f"{path} carries live-session keys ({', '.join(keys)}) and printing it "
            "would spill them into this transcript. Run `bento.sh inspect` and ask "
            "the user first; then `read --allow-shared` if they agree.", 3)

    # `assets` is embedded base64 — fonts, images, video. On a deck with two
    # typefaces that is ~70 KB of payload nobody editing slides needs to see,
    # and it drowns the document it is attached to. Withhold it by default;
    # `write` carries it forward untouched when the incoming doc omits it.
    assets = doc.get("assets") or {}
    if assets and not with_assets:
        doc = {k: v for k, v in doc.items() if k != "assets"}
        total = sum(len(v) for v in assets.values() if isinstance(v, str))
        print(f"bento: withheld {len(assets)} asset(s), {total // 1024} KB "
              f"({', '.join(sorted(assets)[:4])}"
              f"{'…' if len(assets) > 4 else ''}). They are preserved on write; "
              "pass --with-assets if you actually need the bytes.", file=sys.stderr)
    print(json.dumps(doc, **DUMP))
    return 0


def cmd_write(argv):
    if len(argv) != 2:
        die("write: need <deck> and <doc.json>", 2)
    deck, docfile = argv
    try:
        raw = Path(docfile).read_text(encoding="utf-8")
    except OSError as e:
        die(f"cannot read {docfile}: {e}")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"{docfile} is not valid JSON: {e}. Malformed output must never "
            "reach the deck")
    html = load_deck(deck)

    # `read` withholds assets, so a document that came back through it has no
    # `assets` key. Carry the deck's own across rather than deleting the fonts
    # every edit — which would strand `doc.fonts` pointing at nothing and fall
    # back silently. An explicit `"assets": {}` still clears them.
    if "assets" not in doc:
        existing = doc_of(html, deck).get("assets")
        if existing:
            doc["assets"] = existing
            print(f"bento: carried {len(existing)} existing asset(s) forward",
                  file=sys.stderr)

    missing = [f.get("asset") for f in (doc.get("fonts") or [])
               if f.get("asset") not in (doc.get("assets") or {})]
    if missing:
        die(f"doc.fonts names {', '.join(map(str, missing))}, which {'is' if len(missing) == 1 else 'are'} "
            "not in doc.assets. The face would fall back silently and look right "
            "only on a machine that has it installed")

    atomic_write(deck, inject(html, doc, deck))
    slides = len(doc.get("slides") or [])
    print(f"bento: wrote {slides} slide{'' if slides == 1 else 's'} to {deck}",
          file=sys.stderr)
    return 0


CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]

# Injected into a throwaway copy of the deck. `validate()` only exists once the
# runtime has booted, so poll for it and POST the result back to the server that
# served the page.
#
# The result deliberately does NOT come back via --dump-dom. That reads the DOM
# once the page is "done", and pairing it with --virtual-time-budget deadlocks
# against the runtime's async boot — Chrome never exits and the check times out
# with the deck perfectly healthy. Posting the answer out means the page tells
# us when it is ready, in real time, and we stop waiting the moment it does.
PROBE = """
<script>
(async () => {
  const t0 = Date.now(), out = {};
  try {
    while (!window.bento?.validate && Date.now() - t0 < 30000)
      await new Promise(r => setTimeout(r, 100));
    out.booted = !!window.bento;
    if (!window.bento?.validate) { out.error = 'the runtime did not boot'; }
    else {
      const v = window.bento.validate();
      out.ok = v.ok;
      out.counts = v.counts;
      out.slides = window.bento.doc?.slides?.length;
      out.findings = v.findings.map(f => ({
        code: f.code, severity: f.severity, message: f.message,
        slide: f.slide, element: f.element, path: f.path }));
    }
  } catch (e) { out.error = String(e); }
  await fetch('/__result', { method: 'POST', body: JSON.stringify(out) })
          .catch(() => {});
})();
</script>
"""


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.sep in c:
            if os.path.isfile(c):
                return c
        else:
            found = shutil.which(c)
            if found:
                return found
    return None


def chrome_profile_path():
    """Use XDG cache only when it is an absolute, non-empty path."""
    configured = os.environ.get("XDG_CACHE_HOME", "")
    base = Path(configured).expanduser() if configured else None
    if not base or not base.is_absolute():
        base = Path.home() / ".cache"
    return base / "bento-slides" / "chrome-profile"


def cmd_cache_path(argv):
    if argv:
        die("cache-path: takes no arguments", 2)
    print(chrome_profile_path())
    return 0


def cmd_check(argv):
    """Run the deck's own validate() without an interactive browser.

    validate() lives in the runtime, so it needs a real engine — but it does not
    need a visible window, an extension, or a driver MCP. Headless Chrome plus
    --dump-dom is enough, and it is the difference between verification being a
    routine step and being unreachable."""
    if len(argv) != 1:
        die("check: which deck?", 2)
    deck = Path(argv[0])
    if not deck.is_file():
        die(f"check: no such file: {deck}")
    chrome = find_chrome()
    if not chrome:
        die("check: no Chrome/Chromium found. Open the deck yourself and run "
            "window.bento.validate() in the console")

    html = deck.read_text(encoding="utf-8")
    if "</body>" in html:
        probed = html.replace("</body>", PROBE + "</body>", 1)
    else:
        probed = html + PROBE

    # A stable profile directory, because a cold profile costs seconds on every
    # run and this is meant to be cheap enough to use after every write.
    profile = chrome_profile_path()
    profile.mkdir(parents=True, exist_ok=True)

    # Served over loopback rather than opened as file://. The runtime asks the
    # browser for storage on boot, and a file:// page is refused it — the deck
    # then never finishes booting and Chrome never returns. A real origin, even
    # an ephemeral one, boots normally. Verified: identical deck, file:// hangs
    # past 120s, http://127.0.0.1 answers in seconds.
    # Served over loopback rather than opened as file://. The runtime asks the
    # browser for storage on boot, and a file:// page is refused it.
    answer = {}
    done = threading.Event()

    class Handler(SimpleHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                answer.update(json.loads(self.rfile.read(n) or b"{}"))
            except json.JSONDecodeError:
                answer["error"] = "the deck sent back something unparseable"
            self.send_response(204)
            self.end_headers()
            done.set()

        def log_message(self, *a):
            pass

    tmpdir = tempfile.mkdtemp(prefix="bento-check-")
    httpd = proc = None
    try:
        (Path(tmpdir) / "check.bento.html").write_text(probed, encoding="utf-8")
        httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=tmpdir))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{httpd.server_address[1]}/check.bento.html"

        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             f"--user-data-dir={profile}", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not done.wait(timeout=120):
            die("check: the deck never reported back within 120s. Open it in a "
                "browser to see why it will not boot")
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    res = answer
    if res.get("error"):
        die(f"check: {res['error']}")

    findings = res.get("findings") or []
    counts = res.get("counts") or {}
    real = [f for f in findings if f.get("severity") != "info"]
    for f in sorted(real, key=lambda f: f.get("severity") != "error"):
        where = " ".join(str(f[k]) for k in ("slide", "element") if f.get(k))
        print(f"[{f.get('severity')}] {f.get('code')}  {where}\n    {f.get('message')}")
    info = len(findings) - len(real)
    print(f"\n{res.get('slides')} slides — "
          f"{counts.get('error', 0)} error(s), {counts.get('warning', 0)} warning(s), "
          f"{info} info", file=sys.stderr)
    if not real:
        print("bento: clean. Now look at it — validate() checks what is "
              "checkable, not whether the deck is any good.", file=sys.stderr)
    return 1 if counts.get("error") else 0


def _fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "formulae-magicae/bento-slides"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def cmd_refresh(argv):
    if argv:
        die("refresh: takes no arguments", 2)
    print("bento: fetching manifest, runtime and guide…", file=sys.stderr)
    try:
        manifest = json.loads(_fetch(MANIFEST_URL))
        release = json.loads(manifest["payload"])
        guide_text = _fetch(GUIDE_URL)
        runtime = _fetch(release["url"], binary=True)
    except Exception as e:
        die(f"refresh failed, nothing replaced: {e}")

    # The runtime and the guide are one artifact in two files. Replace neither
    # unless both arrive and agree, or a new shell gets paired with an old
    # schema and the failure is silent.
    rt_version = release.get("version")
    m = re.search(r"Guide version `([^`]+)`", guide_text)
    guide_version = m.group(1) if m else None
    if not guide_version:
        die("the fetched guide declares no version; refusing to replace either file")
    if guide_version != rt_version:
        die(f"version mismatch: runtime {rt_version}, guide {guide_version}. "
            "Refusing to pair a new shell with an old schema — try again later")

    digest = hashlib.sha256(runtime).hexdigest()
    if digest != release.get("sha256"):
        die(f"checksum mismatch: manifest says {release.get('sha256')}, "
            f"download is {digest}. Nothing replaced")
    if b'id="bento-doc"' not in runtime:
        die("the download is not a Bento shell (no #bento-doc block); nothing replaced")

    old = None
    if GUIDE.is_file():
        old = re.search(r"Guide version `([^`]+)`", GUIDE.read_text(encoding="utf-8"))
        old = old.group(1) if old else None

    header = (
        "<!--\n"
        "  VENDORED from https://bento.page/agents.md — do not edit by hand.\n"
        f"  Guide version : {guide_version}\n"
        "  Document format: bento/slides (v1)\n"
        f"  Fetched        : {release.get('at', '')[:10]}\n"
        f"  Runtime sha256 : {digest}\n"
        "  Paired runtime : runtime/Bento_Slides.bento.html\n"
        "  Refresh with   : ./bento.sh refresh  (fetches guide + runtime as a matched pair)\n"
        "-->\n\n"
    )
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    GUIDE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(RUNTIME, runtime.decode("utf-8"))
    atomic_write(GUIDE, header + guide_text)

    print(f"bento: {old or 'nothing'} -> {guide_version} "
          f"({len(runtime)} bytes, sha256 {digest[:12]}…)", file=sys.stderr)
    print("bento: styles/ was left alone — presets are pinned, not tracked.",
          file=sys.stderr)
    if release.get("notes"):
        print("\n" + release["notes"], file=sys.stderr)
    return 0


COMMANDS = {"new": cmd_new, "inspect": cmd_inspect, "read": cmd_read,
            "write": cmd_write, "check": cmd_check, "cache-path": cmd_cache_path,
            "refresh": cmd_refresh}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip(), file=sys.stderr)
        print("\nsubcommands: " + ", ".join(COMMANDS), file=sys.stderr)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        die(f"unknown subcommand: {cmd} (try --help)", 2)
    return COMMANDS[cmd](rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PYEOF
