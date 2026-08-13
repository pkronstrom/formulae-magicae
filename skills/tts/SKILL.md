---
name: tts
description: Say text out loud with a local neural voice (Kokoro TTS). Use when the user asks you to speak, narrate, read something aloud, talk them through something, or wants a voice-driven session rather than reading text.
---

# tts

Turns text into speech locally, with no API and no network after first-run setup.

`tts.sh` lives next to this file. Call it directly:

```bash
"$(dirname "$0")/tts.sh" "the text to say"
```

From an agent, resolve the installed skill directory through the host's skill catalog,
then use its absolute path:

```bash
"<skill-dir>/tts.sh" "Three things changed in the resolver."
echo "long text" | "<skill-dir>/tts.sh" -
```

## Prerequisites

`uv` (for the kokoro engine) and an audio player (`afplay` ships with macOS). Both
degrade: no uv → the system `say` voice; no player → text only. Never block on either.

## First run

Weights are not bundled. If they are missing, `tts.sh` says the text with the
system voice instead and prints a hint — it never blocks. To get the good voice:

```bash
tts.sh --setup          # fp16 build, ~205MB total
tts.sh --setup --full   # full-precision build, ~354MB total
```

Weights land in `~/.models/tts/kokoro/`. `tts.sh --check` reports which engine
would be used without saying anything.

**Ask the user before running `--setup`.** It is a several-hundred-megabyte
download to their home directory.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TTS_ENGINE` | `kokoro` | `kokoro` \| `say` \| `custom` |
| `TTS_VOICE` | `bm_lewis` | voice name for the active engine |
| `TTS_PRESET` | — | named profile: voice + speed together |
| `TTS_PRESETS` | `~/.config/tts/presets.conf` | preset definitions |
| `TTS_ROTATE` | `on` | `off` to keep the default voice for every session |
| `TTS_CMD` | — | required when engine is `custom`; gets text on stdin |
| `TTS_HOME` | `~/.models/tts` | where weights live |
| `TTS_SPEED` | `1.25` | kokoro speed multiplier |
| `TTS_LANG` | inferred | `en-gb` for `bm_*`/`bf_*` voices, else `en-us` |
| `TTS_CACHE` | `~/.local/state/pr-voice-review/audio-cache` | narration cache dir, or `off` |
| `TTS_DAEMON` | `on` | `off` to never use or spawn the warm daemon |
| `TTS_DAEMON_WORKERS` | `1` | parallel synths the daemon allows |
| `TTS_DAEMON_TTL` | `1800` | maximum daemon lifetime in seconds |

Kokoro ships 54 voices. The prefix encodes language and gender — `a` American,
`b` British, `e` Spanish, `f` French, `h` Hindi, `i` Italian, `j` Japanese,
`p` Portuguese, `z` Chinese; then `f` female, `m` male. British males are
`bm_daniel`, `bm_fable`, `bm_george`, `bm_lewis`. List them all with:

```bash
tts.sh --voices
```

`HAWK_`-prefixed names work as aliases. `custom` is the escape hatch: any command
that accepts text on stdin and produces audio drops in without changing this skill.

## Presets and per-session voices

The default voice is `bm_lewis` and stays that way. Presets are named alternatives
bundling a voice with its speed:

```bash
tts.sh --presets                     # list them, and show what is in use
tts.sh --preset calm "…"             # af_aoede at 1.10
tts.sh --voice af_bella "…"          # one-off, no preset
```

| Preset | Voice | |
|---|---|---|
| `default` | `bm_lewis` | British male, the standard |
| `heart` | `af_heart` | American female |
| `bella` | `af_bella` | American female |
| `calm` | `af_aoede` | slower, 1.10 |
| `whisper` | `af_nicole` | breathy, 1.15 |
| `jessica` | `af_jessica` | American female |

Override the table with `~/.config/tts/presets.conf` — one `name voice speed` per
line, plus a `pool` line naming the rotation voices. **Keep it there, not in
`tts.sh`**: package updates can replace the installed script, so settings edited into
the script do not survive. Keep personal settings in the configuration file.

### Rotation

When several agents speak at once, each gets its own voice, so you can tell them
apart by ear. The first session to speak takes `bm_lewis`; later ones claim unused
pool voices. A claim is released when that session exits, and the freed voice returns
to the pool. With more live sessions than voices, they share rather than fall silent.

An explicit `TTS_VOICE` or `--preset` always wins over rotation.

**Narration skills opt out.** `pr-voice-review` exports `TTS_ROTATE=off`, because a
walkthrough must not change voice partway through, and the audio cache is keyed on
voice — a rotating voice would miss every cached clip. `pr-voice-review-single-file`
pins `bm_lewis` in `synth.py` and never consults this script at all. Set
`TTS_ROTATE=off` in anything else that renders audio to keep.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | spoke — possibly via a fallback engine, which is reported on stderr |
| 3 | nothing could speak; the text was printed instead |
| 64 | usage error |

A fallback exits 0 deliberately. Callers are agents whose harness treats nonzero
as a failed step, and a fallback that actually spoke is not a failure.

## Caching

Synthesis costs ~2.4s of `uv` startup and model load before the first word, on
every call. Anything said twice only pays that once: clips are stored keyed on
the text plus the voice settings, so a repeat is playback only (measured 4.0s →
2.4s on a 2.4s clip — i.e. the whole overhead, gone).

The cache is **shared with the `pr-voice-review` skills** — same directory, same
key formula. Narration they rendered is a hit here and vice versa. Entries are
mp3 when `ffmpeg` is present, wav otherwise.

Entries unused for 30 days are swept. All three skills stamp an entry when they
reuse it, which is what makes that a real LRU: `atime` cannot be used for it,
because on APFS a read does not refresh `atime` even when it is months stale —
so an `atime` sweep would quietly delete clips you play every day. Nothing else
ever reclaims this directory; `~/.local/state` is an XDG convention macOS knows
nothing about, so without the sweep it grows forever.

Changing voice, speed or language changes the key, so old clips are missed
rather than played in the wrong voice. `tts.sh --check` reports the entry count.
To wipe it: `rm -rf ~/.local/state/pr-voice-review/audio-cache`.

`--again` still replays the single most recent utterance without touching the
cache, and is the cheaper path when you just want that one repeated.

## The warm daemon

`tts.sh` exits after every utterance, so each call reloads the model. `ttsd.py`
holds it instead: **1.38s → 0.47s** per novel sentence, and the CPU cost moves
off the caller entirely (3.65s → 0.03s).

It starts itself the first time a session actually speaks — that first sentence
is synthesized inline while the daemon warms in the background, so a session
that never speaks costs nothing. Every later sentence goes to the daemon. It is
shared across sessions, holds ~545MB (plus ~57MB for its `uv` wrapper), and
defaults to one worker.

Nothing about it is required. Socket missing, daemon wedged, no `uv`, no
`python3` — every failure lands back on inline synthesis, which is exactly what
the skill did before. There is no state to repair and nothing to restart by hand.

It shuts down on its own when any of these is true:

| | Rule |
|---|---|
| 1 | every session that registered with it has exited (checked every 60s) |
| 2 | nothing holds a lease and nothing has been spoken for 5 minutes |
| 3 | it has been alive for `TTS_DAEMON_TTL` (default 30 min), busy or not |

Rule 1 is the normal path — close your last session and it goes. Rule 2 catches
a daemon orphaned before any session registered.

Rule 3 is a **hard lifetime cap, not an idle timer**: no daemon outlives it,
however heavily it is being used. That bounds every leak path at once, including
any nobody thought of. In a long voice session it costs one inline synthesis
(~1.4s) per half hour, when the next sentence finds the daemon gone and starts a
fresh one. It drains before exiting, so a synthesis in flight is never cut off.

```bash
tts.sh --daemon-status   # pid, workers, uptime, idle, live sessions
tts.sh --daemon-stop     # shut it down now
TTS_DAEMON=off tts.sh "…"  # never use or spawn it
```

Sessions are identified by walking up to the `claude` process, so leases are
self-managing — no hook to install. Used from a plain terminal there is no
session to find, and the daemon simply lives by rules 2 and 3.

Its runtime state — socket, pidfile, lock, leases — lives in `$TMPDIR/tts/`,
not beside the cache. All of it names live PIDs and is meaningless after a
reboot, so it belongs where macOS reclaims it. The cache is the opposite: its
whole value is surviving between sessions, which is why it stays put and needs
a sweep of its own.

## Writing text that sounds good

This matters more than the voice does. Speech is not rendered prose.

- **Write for the ear.** Say "the resolve-config function", never spell out
  `resolve_config`. No code fences, no bullet syntax, no markdown.
- **Describe shape, not syntax.** "It moved validation out of the loop and into
  the constructor" beats reading a diff aloud.
- **Two to five sentences per call.** Long blocks cannot be interrupted usefully.
- **Signpost before enumerating.** "Three things changed here" tells the listener
  how long to wait.
- **Skip line numbers** unless the line number is itself the point.

## Interruption

`tts.sh` blocks while audio plays, so pressing Esc kills the call mid-sentence.
That is the interruption mechanism — there is no playback queue.

The warm daemon does not change this. It only synthesizes; playback stays in the
foreground of a blocking script, deliberately, because that is what makes Esc
work. Killing `tts.sh` mid-sentence never leaves the daemon in a bad state.
