#!/usr/bin/env python3
"""pr-voice-review local bridge — stdlib only, 127.0.0.1 only.

Also owns narration synthesis: every `speech` field — the segment's and each
note's — is rendered by a background worker (shelling to tts.sh), so the agent
never spends a tool call on synthesis. One file per observation, appearing
atomically as seg-<i>-<c>.mp3 in the audio dir; <c> indexes the gates the walk
pauses between (see chunks_of).

Serves pre-rendered narration audio to the browser (via the extension's
service-worker proxy) and relays overlay events to the agent, replacing the
browser-tool long-poll with a cheap curl.

  GET  /ping              -> {"ok": true, "v": 26, "warm": bool, "synthPending": n, ...}
  GET  /audio/<name>      -> wav bytes from the --audio-dir (basenames only)
  POST /event             -> queue one JSON event from the overlay
  GET  /wait[?ms=3600000] -> long-poll: first queued event, else {"action":"TIMEOUT"}
                             defaults to 60 min, which is also the cap — each return
                             wakes the agent's harness, so short windows spam the user
  GET  /drain             -> all queued events, clearing the queue

Usage:  server.py --port 8765 --audio-dir /tmp/.../audio [--pidfile PATH]
"""
import argparse, hashlib, json, os, queue, select, shutil, signal, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

EVENTS: "queue.Queue[dict]" = queue.Queue()
AUDIO_DIR = "."
SEGMENTS: list = []
TTS = None
DATA_DIR = "."
CACHE_ROOT = os.path.expanduser("~/.local/state/pr-voice-review/cache")
# Audio keyed by the narration text rather than by the review it belongs to.
# The per-PR cache above is keyed on the head sha, so a single new commit
# invalidates every clip in the review even though almost all of the narration
# is word-for-word identical. This one survives that: pushing a commit only
# re-renders the chunks whose text actually changed.
AUDIO_CACHE = os.path.expanduser("~/.local/state/pr-voice-review/audio-cache")


def prepare_worker(owner, repo, num, scope=None):
    """All the mechanical intake: gh calls, anchors, cache restore. Ends by pushing
    a 'prepared' event — the agent finds out through its normal /wait loop.

    `scope` narrows the review to part of the PR, matching what the reviewer is
    actually looking at on GitHub:
        None                      the whole PR
        {"commit": sha}           just that commit  (/pull/N/changes/<sha>)
        {"base": a, "head": b}    a range           (/pull/N/files/a..b)
    Scoping has to move the PATCHES too, not just the file list: on a commit view
    GitHub shows that commit's diff, so narrating the PR's cumulative patch would
    describe lines the reviewer cannot see.
    """
    ev = {"action": "prepared", "ok": False}
    try:
        def gh(*args):
            r = subprocess.run(["gh", *args], capture_output=True, timeout=90, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:300])
            return r.stdout

        pr = gh("pr", "view", str(num), "--repo", f"{owner}/{repo}", "--json",
                "number,title,body,author,files,reviews,comments,url,headRefOid,headRefName")
        inline = gh("api", f"repos/{owner}/{repo}/pulls/{num}/comments", "--paginate")
        meta = json.loads(pr)

        scope = scope or {}
        tag = ""
        if scope.get("commit"):
            sc = scope["commit"]
            patches = json.dumps(json.loads(
                gh("api", f"repos/{owner}/{repo}/commits/{sc}")).get("files", []))
            tag = "c" + sc[:12]
        elif scope.get("base"):
            a, b = scope["base"], scope.get("head") or meta.get("headRefOid", "")
            patches = json.dumps(json.loads(
                gh("api", f"repos/{owner}/{repo}/compare/{a}...{b}")).get("files", []))
            tag = f"r{a[:8]}-{b[:8]}"
        else:
            patches = gh("api", f"repos/{owner}/{repo}/pulls/{num}/files", "--paginate")

        os.makedirs(DATA_DIR, exist_ok=True)
        for name, data in (("pr.json", pr), ("inline.json", inline), ("patches.json", patches)):
            with open(os.path.join(DATA_DIR, name), "w") as f:
                f.write(data)
        # The file list comes from the same place as the patches, so the count on
        # the panel always matches the count on the page.
        if tag:
            plist = json.loads(patches)
            files = [{"path": f["filename"],
                      "sha": hashlib.sha256(f["filename"].encode()).hexdigest(),
                      "additions": f.get("additions", 0), "deletions": f.get("deletions", 0)}
                     for f in plist]
        else:
            files = [{"path": f["path"], "sha": hashlib.sha256(f["path"].encode()).hexdigest(),
                      "additions": f["additions"], "deletions": f["deletions"]}
                     for f in meta.get("files", [])]
        # Scope belongs in the cache key: a 7-file commit review and the 19-file
        # whole-PR review of the same head are different reviews.
        key = f"{owner}-{repo}-{num}-{meta.get('headRefOid', '')[:12]}" + (f"-{tag}" if tag else "")
        cache = os.path.join(CACHE_ROOT, key)
        cached = os.path.isfile(os.path.join(cache, "segments.json"))
        global SEGMENTS
        HASHES.clear()
        try:
            for w in os.listdir(AUDIO_DIR):
                if w.startswith("seg-"):
                    os.remove(os.path.join(AUDIO_DIR, w))
        except OSError:
            pass
        if cached:
            with SEG_LOCK, open(os.path.join(cache, "segments.json")) as f:
                SEGMENTS = json.load(f)
            os.makedirs(AUDIO_DIR, exist_ok=True)
            for w in os.listdir(cache):
                if w[-4:] in (".wav", ".mp3"):
                    subprocess.run(["cp", os.path.join(cache, w), AUDIO_DIR], timeout=30)
            for i, seg in enumerate(SEGMENTS):     # restored audio is current
                ch = chunks_of(seg)
                # A cache written before gates holds one bare seg-<i> for the
                # whole file. If that file still collapses to a single chunk the
                # audio is exactly right, so adopt it under the chunked name —
                # tracked, and not re-synthesised beside itself. If it does not,
                # the old file narrates the whole file and cannot stand in for
                # any one gate, so it goes.
                for ext in (".mp3", ".wav"):
                    old = os.path.join(AUDIO_DIR, f"seg-{i}{ext}")
                    if not os.path.isfile(old):
                        continue
                    new = os.path.join(AUDIO_DIR, f"seg-{i}-0{ext}")
                    try:
                        if len(ch) == 1 and not os.path.exists(new):
                            os.replace(old, new)
                        else:
                            os.remove(old)
                    except OSError:
                        pass
                for c, k in enumerate(ch):
                    if os.path.isfile(os.path.join(AUDIO_DIR, f"seg-{i}-{c}.mp3")) or \
                       os.path.isfile(os.path.join(AUDIO_DIR, f"seg-{i}-{c}.wav")):
                        HASHES[(i, c)] = hashlib.sha256(k["text"].encode()).hexdigest()
        else:
            # Skeleton segments: the panel shows the full navigable file list
            # immediately; the agent's real POST replaces this with prose.
            with SEG_LOCK:
                SEGMENTS = [{"path": f["path"], "sha": f["sha"],
                             "stat": f"+{f['additions']} \u2212{f['deletions']}",
                             "notes": []} for f in files]
        chime()                                # panel is navigable now
        ev.update(ok=True, title=meta.get("title"), head=meta.get("headRefOid"),
                  cacheKey=key, cached=cached, files=files, scope=(scope or None),
                  fileCount=len(files),
                  inlineCount=len(json.loads(inline) or []),
                  dataDir=DATA_DIR)
    except Exception as e:
        ev["why"] = str(e)[:300]
    EVENTS.put(ev)


def persist_worker(key):
    try:
        # Never cache a half-rendered audio set: a later cache hit would look
        # complete forever. Wait for the synth queue to drain (bounded).
        deadline = time.time() + 300
        while SYNTH.qsize() + BUSY > 0 and time.time() < deadline:
            time.sleep(2)
        dst = os.path.join(CACHE_ROOT, os.path.basename(key))
        os.makedirs(dst, exist_ok=True)
        with SEG_LOCK:
            snap = list(SEGMENTS)
        with open(os.path.join(dst, "segments.json"), "w") as f:
            json.dump(snap, f)
        failed = 0
        for w in os.listdir(AUDIO_DIR):
            if w[-4:] in (".wav", ".mp3"):
                r = subprocess.run(["cp", os.path.join(AUDIO_DIR, w), dst], timeout=30)
                failed += 1 if r.returncode else 0
        EVENTS.put({"action": "persisted", "ok": failed == 0, "cacheKey": key,
                    "synthLeft": SYNTH.qsize(), "copyFailures": failed})
    except Exception as e:
        EVENTS.put({"action": "persisted", "ok": False, "why": str(e)[:200]})
SYNTH: "queue.Queue[tuple]" = queue.Queue()
HASHES: dict = {}
LAST_REQUEST = time.time()
PREPARING = threading.Lock()
SEG_LOCK = threading.Lock()
SYNTH_ERRORS: list = []
WARM = None                      # kept for the reaper's "anything alive?" check
WARM_LOCK = threading.Lock()
WARM_AVAILABLE = False
# Synthesis was serial: two synth_worker threads both blocked on one process.
# A small pool lets them actually overlap. Bounded low on purpose — the gain
# is ~1.3x and each worker holds ~525MB resident.
WARM_POOL: "queue.Queue" = queue.Queue()
WARM_PROCS: list = []
POOL_SIZE = max(1, min(3, (os.cpu_count() or 4) // 4))
# A clip is seconds of work; minutes means the worker is wedged, not busy.
SYNTH_TIMEOUT = 180
LAST_SYNTH = time.time()
BUSY = 0
CHIME = None
PLAYPID = None


def chime():
    """A short 'ready' sound. Fire-and-forget: never blocks, never fails loudly,
    never competes with narration (it is ~0.5s and fires before any speech)."""
    if not CHIME or not os.path.isfile(CHIME):
        return
    try:
        player = "afplay" if sys.platform == "darwin" else "paplay"
        subprocess.Popen([player, CHIME], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass
WORKER_SRC = """
import json, os, sys
import onnxruntime as ort
from kokoro_onnx import Kokoro
import soundfile as sf
k = Kokoro(os.environ["MODEL"], os.environ["VOICES"])
# Uncapped workers each try to take every core and thrash: measured four at
# 9.0x realtime against 9.7x for a single process. Capped to cores/workers
# they reach 11-13x. (CoreML was measured too and is slower - it supports
# 650 of the model's 2389 nodes, so the graph splits into 109 partitions.)
_t = int(os.environ.get("KOKORO_THREADS", "0"))
if _t:
    _so = ort.SessionOptions()
    _so.intra_op_num_threads = _t
    k.sess = ort.InferenceSession(os.environ["MODEL"], sess_options=_so,
                                  providers=["CPUExecutionProvider"])
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    try:
        j = json.loads(line)
        s, sr = k.create(j["text"], voice=j.get("voice", "bm_lewis"),
                         speed=float(j.get("speed", 1.25)), lang=j.get("lang", "en-gb"))
        sf.write(j["out"], s, sr)
        print(json.dumps({"ok": True}), flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "why": str(e)[:200]}), flush=True)
"""


def kokoro_paths():
    home = os.environ.get("TTS_HOME", os.path.expanduser("~/.models/tts"))
    for m in ("kokoro-v1.0.fp16.onnx", "kokoro-v1.0.onnx"):
        p = os.path.join(home, "kokoro", m)
        if os.path.isfile(p):
            return p, os.path.join(home, "kokoro", "voices-v1.0.bin")
    return None, None


def start_warm():
    """One long-lived kokoro process: ~1.5s uv/model overhead paid once, not per
    segment. Falls back to tts.sh if absent. Reaped when idle (it holds ~525MB
    resident) and respawned on demand by warm_synth."""
    global WARM, WARM_AVAILABLE
    model, voices = kokoro_paths()
    if not model or not os.path.isfile(voices):
        return
    threads = max(1, (os.cpu_count() or 4) // POOL_SIZE)
    env = dict(os.environ, MODEL=model, VOICES=voices, KOKORO_THREADS=str(threads))
    # Top up to POOL_SIZE rather than always adding it, so this doubles as the
    # repair path for a pool that lost a worker mid-review.
    need = POOL_SIZE - len([p for p in WARM_PROCS if p.poll() is None])
    for _ in range(max(0, need)):
        try:
            proc = subprocess.Popen(
                ["uv", "run", "--no-project", "--quiet", "--with", "kokoro-onnx",
                 "--with", "soundfile", "python", "-u", "-c", WORKER_SRC],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, env=env)
            if json.loads(proc.stdout.readline() or "{}").get("ready"):
                WARM_PROCS.append(proc)
                WARM_POOL.put(proc)
                WARM_AVAILABLE = True
            else:
                proc.terminate()
        except Exception:
            break
    WARM = WARM_PROCS[0] if WARM_PROCS else None


def discard_worker(p):
    """Drop a dead or wedged worker from the pool roster.

    Removing it from the queue is not enough: left in WARM_PROCS it keeps
    `any(alive)` true, so the respawn branch never fires and the slot is lost
    for the rest of the review — parallelism silently decaying 3 -> 2 -> 1.
    """
    try:
        p.terminate()
    except Exception:
        pass
    if p in WARM_PROCS:
        WARM_PROCS.remove(p)


def warm_synth(out, text):
    """Borrow one worker from the pool for the length of a single clip.

    The lock now only guards respawning, not synthesis itself — that is what
    lets the synth_worker threads actually overlap instead of queueing behind
    one process, which is how this used to behave.
    """
    global LAST_SYNTH
    with WARM_LOCK:
        # Re-warm on demand. The reaper frees the models between reviews, and
        # without this the next one would silently fall back to tts.sh and pay
        # the uv startup cost on every single segment.
        live = [p for p in WARM_PROCS if p.poll() is None]
        if len(live) < POOL_SIZE and WARM_AVAILABLE:
            # Drop corpses, keep survivors, and refill the gap. Rebuilding only
            # when every worker had died left the pool permanently degraded
            # after a single OOM kill.
            if not live:
                while not WARM_POOL.empty():
                    try:
                        WARM_POOL.get_nowait()
                    except Exception:
                        break
            del WARM_PROCS[:]
            WARM_PROCS.extend(live)
            start_warm()
        if not WARM_PROCS:
            return None                 # unavailable -> caller falls back

    try:
        proc = WARM_POOL.get(timeout=120)
    except Exception:
        return None
    if proc.poll() is not None:
        # Died while sitting in the queue. It has already left the queue by
        # being borrowed, but it must leave the roster too or the slot leaks.
        discard_worker(proc)
        return None                     # caller falls back to tts.sh
    LAST_SYNTH = time.time()

    try:
        proc.stdin.write(json.dumps({
            "out": out, "text": text,
            "voice": os.environ.get("TTS_VOICE", "bm_lewis"),
            "speed": os.environ.get("TTS_SPEED", "1.25"),
            "lang": os.environ.get("TTS_LANG", "en-gb")}) + "\n")
        proc.stdin.flush()

        # Bounded read. Only the borrow was bounded before, so a worker that
        # hung rather than crashed blocked this thread forever: BUSY never
        # decremented, the queue stopped draining, and the reaper — which
        # guards on SYNTH.qsize() + BUSY — never freed the models either.
        ready, _, _ = select.select([proc.stdout], [], [], SYNTH_TIMEOUT)
        if not ready:
            discard_worker(proc)
            proc = None
            return None                 # caller falls back to tts.sh
        line = proc.stdout.readline()
        if not line:                    # EOF: the worker died mid-request
            discard_worker(proc)
            proc = None
            return None
        resp = json.loads(line or "{}")
        if resp.get("ok"):
            return True
        return resp.get("why", "worker error")     # string = failure + reason
    except Exception:
        discard_worker(proc)
        proc = None
        return None
    finally:
        # A dead worker must not go back in the pool, or every borrower after
        # it inherits the failure.
        if proc is not None and proc.poll() is None:
            WARM_POOL.put(proc)

# Cache hygiene: ~/.local/state is the ONE path the OS never sweeps, so the server
# owns its bound — newest 20 entries, nothing older than 30 days.
def prune_cache(keep=20, max_age_days=30):
    try:
        if not os.path.isdir(CACHE_ROOT):
            return
        entries = sorted((os.path.join(CACHE_ROOT, e) for e in os.listdir(CACHE_ROOT)),
                         key=os.path.getmtime, reverse=True)
        cutoff = time.time() - max_age_days * 86400
        for i, p in enumerate(entries):
            if i >= keep or os.path.getmtime(p) < cutoff:
                subprocess.run(["rm", "-rf", p], timeout=30)
    except Exception:
        pass

# The model is the expensive part, not the server. Hand back the ~525MB a few
# minutes after the last synthesis, but leave the server up: it costs a few MB,
# keeps the panel connected, and warm_synth respawns the worker on demand. Tearing
# the whole thing down at wrap-up instead would make the NEXT review pay a cold
# start, which is the cost this worker exists to avoid.
def warm_reaper(max_idle=600):
    global WARM
    while True:
        time.sleep(60)
        if not WARM_PROCS or time.time() - LAST_SYNTH < max_idle:
            continue
        if SYNTH.qsize() + BUSY:            # never reap mid-batch
            continue
        with WARM_LOCK:
            if WARM_PROCS and SYNTH.qsize() + BUSY == 0:
                for proc in WARM_PROCS:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                del WARM_PROCS[:]
                while not WARM_POOL.empty():
                    try:
                        WARM_POOL.get_nowait()
                    except Exception:
                        break
                WARM = None


# A crashed agent session must not orphan this process forever.
def idle_watchdog(max_idle=2 * 3600):
    while True:
        time.sleep(300)
        if time.time() - LAST_REQUEST > max_idle:
            os._exit(0)


def audio_cache_key(text):
    h = hashlib.sha256()
    h.update("{}|{}|{}|40k|".format(
        os.environ.get("TTS_VOICE", "bm_lewis"),
        os.environ.get("TTS_SPEED", "1.25"),
        os.environ.get("TTS_LANG", "en-gb")).encode())
    h.update(text.encode())
    return h.hexdigest()[:32]


def synth_worker():
    global BUSY
    while True:
        i, c, text = SYNTH.get()
        BUSY += 1
        try:
            # Skip stale jobs: the text was re-authored after this was queued.
            h = hashlib.sha256(text.encode()).hexdigest()
            if HASHES.get((i, c)) != h:
                continue
            out = os.path.join(AUDIO_DIR, f"seg-{i}-{c}.wav")
            # Cache hit: this exact narration has been spoken before, so copy
            # the clip into place and skip synthesis entirely.
            ck = os.path.join(AUDIO_CACHE, audio_cache_key(text) + ".mp3")
            if os.path.isfile(ck) and os.path.getsize(ck) > 0:
                try:
                    # Mark it used. tts.sh sweeps this shared directory on
                    # mtime — atime is not refreshed by reads on APFS — so
                    # narration reused in every review would still be deleted
                    # 30 days after it was first written.
                    try:
                        os.utime(ck, None)
                    except OSError:
                        pass
                    dst = out[:-4] + ".mp3"
                    shutil.copyfile(ck, dst + ".part")
                    if HASHES.get((i, c)) == hashlib.sha256(text.encode()).hexdigest():
                        os.replace(dst + ".part", dst)
                        EVENTS.put({"action": "segmentready", "i": i, "cached": True})
                    else:
                        os.remove(dst + ".part")
                    continue
                except Exception:
                    pass    # a bad cache entry must never block a real render
            # tmp MUST end in .wav — soundfile infers format from the extension
            # (a .part suffix fails instantly; that bug silently killed whole
            # batches before errors were surfaced). Hidden subdir keeps tmps out
            # of /audio/ and /persist while os.replace stays atomic (same fs).
            tmpdir = os.path.join(AUDIO_DIR, ".tmp")
            os.makedirs(tmpdir, exist_ok=True)
            tmp = os.path.join(tmpdir, f"seg-{i}-{c}-{h[:8]}.wav")
            why = None
            for attempt in range(3):
                ok = warm_synth(tmp, text)  # True | error-string | None
                if isinstance(ok, str):
                    why, ok = ok, False
                if ok is None:              # warm unavailable -> tts.sh, retried
                    try:
                        r = subprocess.run([TTS, "--out", tmp, text],
                                           capture_output=True, timeout=120, text=True)
                        ok = r.returncode == 0
                        if not ok:
                            why = (r.stderr or "").strip()[-200:] or f"rc={r.returncode}"
                    except Exception as e:
                        ok, why = False, str(e)[:200]
                if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    # Compress before publishing: raw wav is ~2-3MB per segment and
                    # crosses the extension message bridge as base64 (~4MB), which is
                    # slow and unreliable. mp3 is ~9x smaller and plays identically.
                    mp3 = tmp[:-4] + ".mp3"
                    try:
                        enc = subprocess.run(
                            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                             "-ac", "1", "-b:a", "40k", mp3],
                            capture_output=True, timeout=60)
                        if enc.returncode == 0 and os.path.getsize(mp3) > 0:
                            os.remove(tmp)
                            tmp = mp3
                            out = out[:-4] + ".mp3"
                    except Exception:
                        pass
                    # Publish only if this text is STILL current — an old job must
                    # never overwrite a newer narration.
                    if HASHES.get((i, c)) == h:
                        if out.endswith(".mp3"):
                            try:
                                os.makedirs(AUDIO_CACHE, exist_ok=True)
                                # Via a temp file, so a concurrent reader never
                                # picks up a half-copied clip and caches it
                                # permanently as a valid hit.
                                ck_final = os.path.join(
                                    AUDIO_CACHE, audio_cache_key(text) + ".mp3")
                                ck_tmp = ck_final + ".part-%d" % os.getpid()
                                shutil.copyfile(tmp, ck_tmp)
                                os.replace(ck_tmp, ck_final)
                            except Exception:
                                pass    # caching is an optimisation, never a failure
                        os.replace(tmp, out)
                    else:
                        os.remove(tmp)
                    why = None
                    break
                why = why or "empty output"
                time.sleep(3 * (attempt + 1))
            if why is not None:
                SYNTH_ERRORS.append({"i": i, "c": c, "why": why})
                del SYNTH_ERRORS[:-10]
                EVENTS.put({"action": "syntherror", "i": i, "c": c, "why": why})
        finally:
            BUSY -= 1
            SYNTH.task_done()


def chunks_of(seg):
    """Narration split into the units the walk pauses between — one per observation.

    A chunk is what plays before a continue gate, so the boundaries have to be
    where the pointer moves: each note that carries its own `speech` becomes a
    chunk anchored to its line range, with `seg.speech` (if present) leading as
    the file's intro. Reviews authored before notes carried speech still work —
    they collapse to a single chunk of the whole narration, which is exactly the
    old one-gate-per-file behaviour.

    The overlay derives the identical list from the same fields, so neither side
    has to publish a manifest for the other.
    """
    seg = seg or {}
    intro = (seg.get("speech") or "").strip()
    spoken = [n for n in (seg.get("notes") or [])
              if isinstance(n, dict) and (n.get("speech") or "").strip()]
    if not spoken:
        return [{"text": intro, "from": None, "to": None}] if intro else []
    out = [{"text": intro, "from": None, "to": None}] if intro else []
    out += [{"text": n["speech"].strip(), "from": n.get("from"), "to": n.get("to")}
            for n in spoken]
    return out


def player_cmd(path_, rate=1.0, at=0.0):
    """How to play one narration file at `rate`, starting `at` seconds in.

    Speeding up must not raise the pitch — varispeed turns Lewis into a chipmunk
    (measured: a 440 Hz tone comes back at 880 Hz doubled that way, while
    ffmpeg's atempo returns it at 440 Hz in half the time). So anything off 1x
    goes through ffplay's atempo filter, which is a proper time stretch. atempo
    handles 0.5-2.0 in one pass, which covers the offered range.

    `at` is how pause/resume works: resuming re-launches from the offset rather
    than suspending the player. SIGSTOP does pause afplay, but it never finishes
    afterwards — measured, a 3s remainder still had not exited 15s later, because
    its audio queue does not recover. Seeking is deterministic, and mp3 frame
    granularity (~26ms) is well below anything audible as a jump.
    """
    mac = sys.platform == "darwin"
    seek = ["-ss", f"{at:g}"] if at > 0.05 else []
    plain = abs(rate - 1.0) < 0.01
    # ffplay for everything, including plain 1x playback. Not about features —
    # about latency. Measured on the same file: afplay runs 1219ms longer than the
    # audio, ffplay 305ms, and nearly all of that is device setup BEFORE any sound.
    # The page starts its transcript walk when this call returns, so afplay left
    # the highlighted word more than a second ahead of the voice.
    if shutil.which("ffplay"):
        return (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"] + seek +
                ([] if plain else ["-af", f"atempo={rate:g}"]) + [path_], "ffplay")
    # No ffplay: afplay cannot seek, so a resume restarts the observation, and a
    # non-1x rate shifts pitch. Degradations, not silence.
    if mac:
        return (["afplay", path_] if plain
                else ["afplay", "-r", f"{rate:g}", "-q", "1", path_], "afplay")
    return (["paplay", path_], "paplay")


# How long each player takes to open the audio device — measured, shaded low so
# the transcript lags a hair rather than leading. Seeing a word before you hear
# it is far more obviously wrong than seeing it a moment after.
PLAYER_LEAD = {"ffplay": 0.27, "afplay": 1.10, "paplay": 0.20}


def player_pid():
    if not PLAYPID or not os.path.isfile(PLAYPID):
        return None
    try:
        with open(PLAYPID) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def kill_player():
    """Silence whatever the server is currently playing.

    /play calls this before starting the next gate: skipping ahead mid-sentence
    has to REPLACE the voice, not add a second one. `tts.sh --stop` cannot do it
    — it only kills players it started itself, deliberately, so it never touches
    a stray afplay. This is the only thing that stops a /play.
    """
    pid = player_pid()
    if pid is not None:
        try:
            # A SIGSTOPped player would leave SIGTERM pending instead of dying,
            # so wake it first — navigating away from a paused gate must not
            # leave a suspended process behind.
            os.kill(pid, signal.SIGCONT)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        if PLAYPID:
            os.remove(PLAYPID)
    except OSError:
        pass


def drop_audio(i, c):
    for ext in (".wav", ".mp3"):
        try:
            os.remove(os.path.join(AUDIO_DIR, f"seg-{i}-{c}{ext}"))
        except OSError:
            pass


def enqueue_chunk(i, c, text):
    h = hashlib.sha256(text.encode()).hexdigest()
    if HASHES.get((i, c)) == h:
        return
    HASHES[(i, c)] = h
    # Whatever is on disk narrates the OLD text. /status reads readiness straight
    # off the filesystem and /play serves whatever it finds, so leaving it there
    # speaks stale narration over the rewritten note until synthesis catches up.
    # A briefly silent gate beats a briefly wrong one.
    drop_audio(i, c)
    SYNTH.put((i, c, text))


def enqueue_segment(i, seg):
    if not TTS:
        return 0
    os.makedirs(AUDIO_DIR, exist_ok=True)
    ch = chunks_of(seg)
    for c, k in enumerate(ch):
        enqueue_chunk(i, c, k["text"])
    # A re-authored file can end up with fewer chunks than last time. Scan for
    # what is actually there rather than probing a fixed window ahead — a file
    # that shrinks by more than the window would otherwise leave audio behind
    # that /status keeps advertising and persist_worker copies into the cache.
    prefix = f"seg-{i}-"
    for f in (os.listdir(AUDIO_DIR) if os.path.isdir(AUDIO_DIR) else []):
        if not f.startswith(prefix) or f[-4:] not in (".wav", ".mp3"):
            continue
        tail = f[len(prefix):-4]
        if tail.isdigit() and int(tail) >= len(ch):
            HASHES.pop((i, int(tail)), None)
            try:
                os.remove(os.path.join(AUDIO_DIR, f))
            except OSError:
                pass
    return len(ch)


def enqueue_synthesis(segments):
    if not TTS:
        return
    os.makedirs(AUDIO_DIR, exist_ok=True)
    for i, seg in enumerate(segments):
        enqueue_segment(i, seg)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def parse_request(self):
        global LAST_REQUEST
        LAST_REQUEST = time.time()
        return super().parse_request()

    def _json(self, obj, code=200):
        # Stamp the unread-event count onto every dict response. The agent is
        # only listening while a /wait is armed, and it is unarmed for exactly
        # the stretch it is busy working — which is when the user is most likely
        # to click something. Piggybacking the depth means ANY call it makes in
        # that window ("I'll publish this note", "let me check status") tells it
        # input is waiting, instead of the input sitting unseen until someone
        # asks "did you get this?".
        if isinstance(obj, dict) and "pendingEvents" not in obj:
            # pendingUser counts only what came FROM the overlay. The agent's own
            # segmentready/syntherror events also sit in this queue, and on a
            # 19-file publish they would read as 19 "unread" items and drown the
            # one signal that matters: the user did something.
            with EVENTS.mutex:
                queued = list(EVENTS.queue)
            obj = dict(obj, pendingEvents=len(queued),
                       pendingUser=sum(1 for e in queued
                                       if isinstance(e, dict) and e.get("src") == "user"))
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/ping":
            return self._json({"ok": True, "v": 26, "warm": WARM is not None and WARM.poll() is None, "synthPending": SYNTH.qsize() + BUSY, "synthErrors": len(SYNTH_ERRORS), "lastError": (SYNTH_ERRORS[-1] if SYNTH_ERRORS else None)})
        if u.path == "/status":
            with SEG_LOCK:
                total = len(SEGMENTS)
                authored = sum(1 for s in SEGMENTS if (s.get("notes") or []))
                voiced = sum(1 for s in SEGMENTS if chunks_of(s))
                pending = [i for i, s in enumerate(SEGMENTS) if not (s.get("notes") or [])]
                want = {i: len(chunks_of(s)) for i, s in enumerate(SEGMENTS)}
            # Audio on disk is seg-<i>-<c>.ext. Bare seg-<i>.ext only ever comes
            # from a pre-gates cache and is resolved at restore, never here.
            done = set()
            for f in (os.listdir(AUDIO_DIR) if os.path.isdir(AUDIO_DIR) else []):
                if not f.startswith("seg-") or f[-4:] not in (".wav", ".mp3"):
                    continue
                bits = f[4:-4].split("-")
                if len(bits) == 2 and all(b.isdigit() for b in bits):
                    done.add((int(bits[0]), int(bits[1])))
            # A file counts as rendered only once every one of its gates can play.
            ridx = sorted(i for i, n in want.items()
                          if n and all((i, c) in done for c in range(n)))
            rendered = len(ridx)
            return self._json({
                "total": total, "authored": authored, "voiced": voiced,
                "rendered": rendered, "renderedIdx": ridx[:40], "pendingIdx": pending[:12],
                "chunks": [want.get(i, 0) for i in range(total)],
                "renderedChunks": [f"{i}:{c}" for i, c in sorted(done)][:400],
                "synthPending": SYNTH.qsize() + BUSY,
                "synthErrors": len(SYNTH_ERRORS),
                "queuedEvents": EVENTS.qsize(), "warm": WARM is not None and WARM.poll() is None})
        if u.path == "/segments":
            with SEG_LOCK:
                snap = list(SEGMENTS)
            return self._json(snap) if snap else self._json({"ok": False}, 404)
        if u.path == "/drain":
            out = []
            while not EVENTS.empty():
                try: out.append(EVENTS.get_nowait())
                except queue.Empty: break
            return self._json(out)
        if u.path == "/wait":
            # Default long, not short: every TIMEOUT return wakes the agent's
            # harness with a "background command completed" notification, so a
            # 25s default turned a quiet review into ~144 wake-ups an hour; at
            # the 60 min default it is one, and an event still returns the
            # instant it arrives — the window only bounds SILENCE. A
            # bare /wait is the background push channel it is normally used as;
            # callers that want a work-scheduling tick pass ms explicitly.
            #
            # Only two windows are meaningful here: a sub-second tick that
            # interleaves authoring with user clicks, and the long push wait.
            # Nothing legitimate sits between them, but an agent left to pick a
            # number reliably invents one (30000, 60000) and spams the user for
            # the whole review. Snap that middle band up to the push window —
            # waiting for events is what the caller meant either way, and no
            # work in this design is scheduled off a 30s tick.
            try:
                ms = int(parse_qs(u.query).get("ms", ["3600000"])[0])
            except ValueError:
                ms = 3600000
            if 5000 < ms < 3600000:
                ms = 3600000
            ms = min(max(ms, 100), 3600000)
            try:
                return self._json(EVENTS.get(timeout=ms / 1000))
            except queue.Empty:
                return self._json({"action": "TIMEOUT"})
        if u.path.startswith("/audio/"):
            name = os.path.basename(u.path[len("/audio/"):])   # no traversal
            p = os.path.join(AUDIO_DIR, name)
            if not os.path.isfile(p):                       # prefer mp3, accept wav
                alt = p[:-4] + (".mp3" if p.endswith(".wav") else ".wav")
                if os.path.isfile(alt):
                    p = alt
                else:
                    return self._json({"ok": False, "why": "no such audio"}, 404)
            with open(p, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg" if p.endswith(".mp3") else "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({"ok": False}, 404)

    def do_POST(self):
        global SEGMENTS
        path = urlparse(self.path).path
        if path == "/play":
            # The page cannot play audio itself: GitHub's CSP media-src forbids
            # blob: and data:, so every in-page source is blocked. Same machine
            # though — so the server just plays it through the speakers and hands
            # back the duration for highlight timing and autoplay chaining.
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or "{}")
                i, c = int(req.get("i", -1)), int(req.get("c", 0))
                rate = min(3.0, max(0.5, float(req.get("rate", 1) or 1)))
                at = max(0.0, float(req.get("at", 0) or 0))
            except (ValueError, TypeError, json.JSONDecodeError):
                return self._json({"ok": False, "why": "bad index"}, 400)
            # Chunked layout only. Bare seg-<i> from a pre-gates cache is adopted
            # or discarded at restore time, so anything left here is authoritative.
            path_ = next((p for ext in (".mp3", ".wav")
                          for p in [os.path.join(AUDIO_DIR, f"seg-{i}-{c}{ext}")]
                          if os.path.isfile(p)), None)
            if not path_:
                return self._json({"ok": False, "why": "not rendered", "i": i, "c": c}, 404)
            dur = 0.0
            try:
                pr = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nw=1:nk=1", path_], capture_output=True, text=True, timeout=10)
                dur = float((pr.stdout or "0").strip() or 0)
            except Exception:
                pass
            try:
                if TTS:
                    subprocess.run([TTS, "--stop"], capture_output=True, timeout=5)
                kill_player()          # one voice at a time
                cmd, player = player_cmd(path_, rate, at)
                pp = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
                with open(PLAYPID, "w") as f:
                    f.write(str(pp.pid))
            except Exception as e:
                return self._json({"ok": False, "why": str(e)[:150]}, 500)
            # Report wall-clock play time REMAINING, not file length — the page
            # times the word walk and the autoplay chain off this, and both a
            # resume offset and a 2x rate shorten it.
            return self._json({"ok": True, "i": i, "c": c, "rate": rate, "at": at,
                               "duration": max(0.1, (dur - at) / (rate or 1)),
                               "full": dur, "player": player,
                               # seconds before sound actually starts — the page
                               # delays its word walk by this much
                               "lead": PLAYER_LEAD.get(player, 0.25)})
        if path == "/stop":
            # Kills agent-side playback without waking the agent. This is what makes
            # the Stop button instant even while the agent (not the page) is speaking.
            try:
                if TTS:
                    subprocess.run([TTS, "--stop"], capture_output=True, timeout=10)
                kill_player()
            except Exception:
                pass
            return self._json({"ok": True})
        if path == "/prepare":
            n = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(n))
                if not PREPARING.acquire(blocking=False):
                    return self._json({"ok": False, "why": "prepare already running"}, 429)
                def run():
                    try: prepare_worker(req["owner"], req["repo"], req["num"],
                                        req.get("scope"))
                    finally: PREPARING.release()
                threading.Thread(target=run, daemon=True).start()
                return self._json({"ok": True, "started": True})
            except (json.JSONDecodeError, KeyError):
                return self._json({"ok": False, "why": "need owner/repo/num"}, 400)
        if path == "/persist":
            n = int(self.headers.get("Content-Length", 0))
            try:
                key = json.loads(self.rfile.read(n))["cacheKey"]
            except (json.JSONDecodeError, KeyError):
                return self._json({"ok": False, "why": "need cacheKey"}, 400)
            threading.Thread(target=persist_worker, args=(key,), daemon=True).start()
            return self._json({"ok": True, "started": True})
        if path.startswith("/segment/"):
            # Per-segment merge: lets N parallel authors write concurrently without
            # clobbering each other or the whole-array POST.
            try:
                i = int(path.rsplit("/", 1)[1])
                n = int(self.headers.get("Content-Length", 0))
                patch = json.loads(self.rfile.read(n))
            except (ValueError, json.JSONDecodeError):
                return self._json({"ok": False, "why": "bad index or json"}, 400)
            with SEG_LOCK:
                if not (0 <= i < len(SEGMENTS)):
                    return self._json({"ok": False, "why": "index out of range"}, 404)
                SEGMENTS[i].update(patch)
                seg = dict(SEGMENTS[i])
            n_ch = enqueue_segment(i, seg)
            EVENTS.put({"action": "segmentready", "i": i, "path": seg.get("path"),
                        "chunks": n_ch})
            return self._json({"ok": True, "i": i, "chunks": n_ch})
        if path == "/segments":
            n = int(self.headers.get("Content-Length", 0))
            try:
                incoming = json.loads(self.rfile.read(n))
                with SEG_LOCK:
                    SEGMENTS = incoming
                enqueue_synthesis(incoming)
                return self._json({"ok": True, "count": len(SEGMENTS),
                                   "chunks": sum(len(chunks_of(s)) for s in incoming),
                                   "synthQueued": SYNTH.qsize()})
            except json.JSONDecodeError:
                return self._json({"ok": False}, 400)
        if path != "/event":
            return self._json({"ok": False}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            ev = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "why": "bad json"}, 400)
        ev.setdefault("at", int(time.time() * 1000))
        ev["src"] = "user"        # came from the overlay; counted by pendingUser
        # position events coalesce here too — mirror of the overlay queue rule
        if ev.get("action") == "position":
            drained, kept = [], []
            while not EVENTS.empty():
                try: drained.append(EVENTS.get_nowait())
                except queue.Empty: break
            kept = [e for e in drained if e.get("action") != "position"]
            for e in kept: EVENTS.put(e)
        EVENTS.put(ev)
        self._json({"ok": True})


def main():
    global AUDIO_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--audio-dir", default=".")
    ap.add_argument("--pidfile")
    ap.add_argument("--tts", help="path to tts.sh; enables server-side narration synthesis")
    ap.add_argument("--data-dir", help="where /prepare writes pr.json etc (default: audio dir parent)")
    ap.add_argument("--chime", default="/System/Library/Sounds/Tink.aiff",
                    help="sound played when the panel becomes usable; '' disables")
    a = ap.parse_args()
    AUDIO_DIR = a.audio_dir
    global PLAYPID
    PLAYPID = os.path.join(a.audio_dir, ".playing.pid")
    global DATA_DIR
    DATA_DIR = a.data_dir or os.path.dirname(os.path.abspath(AUDIO_DIR))
    global TTS, CHIME
    TTS = a.tts
    CHIME = a.chime or None
    if TTS:
        start_warm()
        for _ in range(2):
            threading.Thread(target=synth_worker, daemon=True).start()
    threading.Thread(target=idle_watchdog, daemon=True).start()
    threading.Thread(target=warm_reaper, daemon=True).start()
    prune_cache()
    # sweep tmp wavs from any earlier killed synthesis
    try:
        tmpdir = os.path.join(AUDIO_DIR, ".tmp")
        for f in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, f))
    except OSError:
        pass
    if a.pidfile:
        with open(a.pidfile, "w") as f:
            f.write(str(os.getpid()))
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"pr-voice-review bridge on 127.0.0.1:{a.port}, audio={AUDIO_DIR}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
