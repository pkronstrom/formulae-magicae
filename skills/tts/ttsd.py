"""Long-lived Kokoro process, shared by every tts.sh call on this machine.

tts.sh is one-shot: it exits after each utterance, so every call pays uv
startup plus an ONNX model load — ~2.4s before the first word. This holds the
model so that cost is paid once per machine instead of once per sentence.

Launched in the background by tts.sh, never by hand:

    uv run --no-project --quiet --with kokoro-onnx --with soundfile \
        python ttsd.py

Reads MODEL/VOICES from the environment. Speaks line-delimited JSON over a
unix socket — the same wire format pr-voice-review/server.py already uses for
its own warm workers:

    {"text": ..., "out": ..., "voice": ..., "speed": ..., "lang": ...} -> {"ok": true}
    {"op": "status"} -> {"ok": true, "workers": n, "idle": s, "leases": [...]}

It does not play anything. tts.sh keeps playback in the foreground of a
blocking script, which is what lets Esc kill a sentence mid-word.
"""

import fcntl
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

STATE = Path(os.environ.get("TTS_STATE") or (
    Path(os.environ.get("TMPDIR") or "/tmp") / "tts"))
SOCK = STATE / "daemon.sock"
LOCK = STATE / "daemon.lock"
PIDF = STATE / "daemon.pid"
LEASES = STATE / "leases"

SWEEP = int(os.environ.get("TTS_DAEMON_SWEEP") or 60)   # lease check interval
IDLE_NO_LEASE = 300  # exit after 5 min if nothing holds a lease
# Maximum process lifetime, not an idle timer. An idle timer lets a daemon that
# is used every few minutes live for days; this bounds every leak path at once,
# including any not thought of here. The cost is one inline synthesis (~1.4s)
# per TTL in a continuously busy session.
MAX_LIFE = int(os.environ.get("TTS_DAEMON_TTL") or 1800)

POOL: "queue.Queue" = queue.Queue()
LAST = time.time()
SAW_LEASE = False
STARTED = time.time()
WORKERS = 0
INFLIGHT = 0
INFLIGHT_LOCK = threading.Lock()


def ps_started(pid):
    """Process start time, or None if the pid is gone.

    Paired with the pid in a lease file so a recycled pid is not read as a
    session that is still alive — the daemon would then never hit its
    all-sessions-gone rule and would sit until the 30 minute backstop.
    """
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def live_leases():
    """Live lease pids, deleting any whose process is gone or was recycled."""
    live = []
    try:
        entries = list(LEASES.iterdir())
    except OSError:
        return live
    for f in entries:
        # Every lease is handled in isolation. A file that disappears between
        # the listing and the read is normal — a session ending is exactly that
        # race — and an escaping exception here would kill the reaper thread,
        # leaving a daemon that nothing can ever shut down.
        try:
            pid = int(f.name)
            want = f.read_text().strip()
            now = ps_started(pid)
            if now is not None and (not want or want == now):
                live.append(pid)
                continue
        except ValueError:
            continue
        except OSError:
            continue
        try:
            f.unlink()
        except OSError:
            pass
    return live


def reaper():
    """Three exit rules, checked once a sweep.

    os._exit rather than sys.exit: a synthesis thread stuck in native code is
    not a daemon thread, and interpreter shutdown would block on it forever.
    """
    global SAW_LEASE
    while True:
        time.sleep(SWEEP)
        try:
            idle = time.time() - LAST
            live = live_leases()
        except Exception:
            # Belt and braces over the per-lease guard: whatever goes wrong in
            # a sweep, the next one still runs. A dead reaper is an immortal
            # daemon, which is the one outcome this file exists to prevent.
            continue
        if live:
            SAW_LEASE = True
        # 1. every session that ever registered is gone
        if SAW_LEASE and not live:
            os._exit(0)
        # 2. nothing holds a lease and nobody has spoken for 5 min. Catches a
        #    daemon orphaned by a tts.sh killed right after it spawned one, and
        #    bare-terminal use where no session ever registers.
        if not live and idle >= IDLE_NO_LEASE:
            os._exit(0)
        # 3. hard lifetime cap. Drains first: killing a synthesis in flight
        #    would leave its client waiting out the full result timeout, which
        #    is the wedge behaviour this design already went out of its way to
        #    avoid. In flight is ~0 almost always, since a clip is sub-second
        #    and this is checked once a minute.
        if time.time() - STARTED >= MAX_LIFE and INFLIGHT == 0:
            os._exit(0)


def make_kokoro(model, voices, threads):
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    k = Kokoro(model, voices)
    if threads:
        # Uncapped workers each try to take every core and thrash: measured
        # four at 9.0x realtime against 9.7x for one. Capped to cores/workers
        # they reach 11-13x. Only applied above one worker, since a lone
        # instance is fastest with everything.
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        k.sess = ort.InferenceSession(model, sess_options=so,
                                      providers=["CPUExecutionProvider"])
    return k


def handle(conn):
    global LAST, INFLIGHT
    import soundfile as sf

    try:
        conn.settimeout(120)
        f = conn.makefile("rwb")
        line = f.readline()
        if not line:
            return
        req = json.loads(line)

        if req.get("op") == "status":
            resp = {"ok": True, "pid": os.getpid(), "workers": WORKERS,
                    "uptime": round(time.time() - STARTED),
                    "expires_in": max(0, round(STARTED + MAX_LIFE - time.time())),
                    "idle": round(time.time() - LAST),
                    "inflight": INFLIGHT,
                    "leases": live_leases()}
        else:
            # Ack before synthesizing. A stopped or wedged process still
            # completes connect() — the kernel accepts into the backlog — so
            # without this the client cannot tell "working on it" from "never
            # coming back", and pays its full read timeout to find out.
            f.write(b'{"ack": true}\n')
            f.flush()
            LAST = time.time()
            with INFLIGHT_LOCK:
                INFLIGHT += 1
            k = POOL.get()
            try:
                samples, sr = k.create(req["text"], voice=req.get("voice", "bm_lewis"),
                                       speed=float(req.get("speed", 1.25)),
                                       lang=req.get("lang", "en-gb"))
                sf.write(req["out"], samples, sr)
                resp = {"ok": True}
            except Exception as e:
                resp = {"ok": False, "why": str(e)[:200]}
            finally:
                POOL.put(k)
                LAST = time.time()
                with INFLIGHT_LOCK:
                    INFLIGHT -= 1

        f.write((json.dumps(resp) + "\n").encode())
        f.flush()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    global WORKERS

    model = os.environ.get("MODEL")
    voices = os.environ.get("VOICES")
    if not model or not voices or not os.path.isfile(model):
        return 1

    STATE.mkdir(parents=True, exist_ok=True)
    LEASES.mkdir(parents=True, exist_ok=True)

    # Own process group, so tts.sh can kill the whole tree. Under `uv run` the
    # model is held by this child, not by uv, and killing only the pid would
    # orphan whichever of the two was not named.
    try:
        os.setsid()
    except OSError:
        pass

    # One daemon per machine. The lock is held for the process lifetime, so a
    # second launch loses the race and exits rather than leaving a second
    # ~525MB process behind.
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0

    # A socket file outlives a kill -9. Left in place, every later bind() fails
    # and the skill degrades to inline synthesis permanently and silently — so
    # unlink it, inside the lock, before binding.
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        SOCK.unlink()
    except FileNotFoundError:
        pass
    srv.bind(str(SOCK))
    srv.listen(16)
    os.chmod(SOCK, 0o600)

    WORKERS = max(1, min(4, int(os.environ.get("TTS_DAEMON_WORKERS") or 1)))
    # A single instance is fastest uncapped; only split cores once there are
    # several instances competing for them.
    threads = 0 if WORKERS == 1 else max(1, (os.cpu_count() or 4) // WORKERS)
    for _ in range(WORKERS):
        POOL.put(make_kokoro(model, voices, threads))

    PIDF.write_text(str(os.getpid()))
    threading.Thread(target=reaper, daemon=True).start()

    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            continue
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    raise SystemExit(main())
