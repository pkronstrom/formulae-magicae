"""Render every narration chunk to base64 MP3 in one process.

Run under uv so Kokoro's deps resolve the same way tts.sh resolves them:

    uv run --no-project --quiet --with kokoro-onnx --with soundfile \
        python synth.py segments.json out.json MODEL VOICES

The point of the batch is the model load: it costs ~0.9 s and is paid once
here, against once per chunk when shelling out to tts.sh. Measured 9.3x
realtime batched, 3.8x per-chunk.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from multiprocessing import Process
from pathlib import Path

VOICE = "bm_lewis"
LANG = "en-gb"  # b-prefixed voices need en-gb phonemes, as in tts.sh
SPEED = 1.0


def plan_chunks(segments: list[dict]) -> list[tuple[str, str]]:
    """[(key, text)] for every chunk that has speech, keyed "segment:observation".

    Note indices count silent cards, because the client addresses
    observations by position and a gap in the audio map is how it knows a
    card is deliberately silent.
    """
    out = []
    for i, seg in enumerate(segments):
        if seg.get("speech", "").strip():
            out.append((f"{i}:0", seg["speech"]))
        for n, note in enumerate(seg.get("notes", []), start=1):
            if note.get("speech", "").strip():
                out.append((f"{i}:{n}", note["speech"]))
    return out


def encode_mp3(wav: Path) -> str:
    """WAV -> 24 kbps mono MP3 -> base64.

    MP3 over Opus for universal decode: Opus saves ~1 MB on a 12-minute
    walk but needs a codec-support branch for older Safari, which is a bad
    trade in a skill whose premise is minimal moving parts.
    """
    with tempfile.TemporaryDirectory() as d:
        mp3 = Path(d) / "out.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(wav),
             "-c:a", "libmp3lame", "-b:a", "24k", "-ac", "1", "-ar", "24000", str(mp3)],
            check=True,
        )
        return base64.b64encode(mp3.read_bytes()).decode("ascii")


CACHE = Path.home() / ".local/state/pr-voice-review/audio-cache"


def cache_key(text: str) -> str:
    """Voice settings are part of the key: change the voice, get new audio."""
    h = hashlib.sha256()
    h.update(f"{VOICE}|{SPEED}|{LANG}|24k|".encode())
    h.update(text.encode())
    return h.hexdigest()[:32]


def _render(share, model, voices, threads, out_json):
    """One worker: load Kokoro once, render its share, write {key: base64}."""
    import onnxruntime as ort  # noqa: I001
    import soundfile as sf  # noqa: I001
    from kokoro_onnx import Kokoro  # noqa: I001

    kokoro = Kokoro(model, voices)
    if threads:
        # Uncapped workers each try to take every core and thrash: measured
        # 4 workers at 9.0x against 9.7x for one. Capped, the same 4 reach
        # 11-13x. CoreML was tried and is slightly SLOWER — it supports 650 of
        # 2389 graph nodes, so the model splits into 109 partitions and the
        # boundary crossings cost more than the acceleration saves.
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        kokoro.sess = ort.InferenceSession(
            model, sess_options=opts, providers=["CPUExecutionProvider"]
        )
    out = {}
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "chunk.wav"
        for key, text in share:
            samples, sr = kokoro.create(text, voice=VOICE, speed=SPEED, lang=LANG)
            sf.write(str(wav), samples, sr)
            b64 = encode_mp3(wav)
            out[key] = b64
            # Publish atomically. Written in place, a crash or two workers
            # racing on identical narration leaves a half-written file that
            # every later build accepts as a hit and embeds as corrupt audio —
            # and nothing ever repairs it, because it is non-empty.
            final = CACHE / (cache_key(text) + ".b64")
            tmp_entry = final.with_suffix(".b64.part-%d" % os.getpid())
            tmp_entry.write_text(b64)
            os.replace(tmp_entry, final)
    Path(out_json).write_text(json.dumps(out))


def main() -> int:
    segments = json.loads(Path(sys.argv[1]).read_text())
    out_path = Path(sys.argv[2])
    model, voices = sys.argv[3], sys.argv[4]
    workers = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    CACHE.mkdir(parents=True, exist_ok=True)

    chunks = plan_chunks(segments)

    # Reuse anything whose text is unchanged. The staged build re-runs this on
    # every rewrite, and re-synthesizing prose nobody edited is the single
    # largest waste in the pipeline — far larger than the synthesis rate.
    audio, todo = {}, []
    for key, text in chunks:
        hit = CACHE / (cache_key(text) + ".b64")
        if hit.exists():
            audio[key] = hit.read_text()
            # Mark it used. tts.sh sweeps this shared directory on mtime — atime
            # is not refreshed by reads on APFS — so an entry reused on every
            # build would still be deleted 30 days after it was written.
            try:
                os.utime(hit, None)
            except OSError:
                pass
        else:
            todo.append((key, text))
    print(f"{len(audio)} cached, {len(todo)} to render", file=sys.stderr)

    if todo:
        workers = max(1, min(workers, len(todo)))
        threads = max(1, (os.cpu_count() or 4) // workers)
        with tempfile.TemporaryDirectory() as d:
            parts = [Path(d) / f"part-{i}.json" for i in range(workers)]
            procs = []
            for i in range(workers):
                share = todo[i::workers]
                if not share:
                    continue
                p = Process(target=_render, args=(share, model, voices, threads, str(parts[i])))
                p.start()
                procs.append((p, parts[i]))
            for p, _ in procs:
                p.join()
            failed = 0
            for p, part in procs:
                # Keep what the healthy workers produced. Returning early threw
                # their output away and made the next run pay for it again —
                # pointless, since each worker caches every clip as it goes.
                if p.exitcode != 0 or not part.exists():
                    failed += 1
                    print(f"worker failed with exit {p.exitcode}", file=sys.stderr)
                    continue
                audio.update(json.loads(part.read_text()))

    out_path.write_text(json.dumps(audio))
    missing = len(chunks) - len(audio)
    print(f"{len(audio)} chunks ready" + (f", {missing} MISSING" if missing else ""),
          file=sys.stderr)
    # Non-zero so the caller knows it is incomplete, but the file is written and
    # the cache is warm, so a re-run only renders what is actually missing.
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
