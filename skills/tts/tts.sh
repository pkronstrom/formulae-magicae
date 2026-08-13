#!/usr/bin/env bash
# tts.sh — say text out loud with a local neural voice.
#
# Usage:
#   tts.sh "text to say"
#   echo "text" | tts.sh -
#   tts.sh --print "text"     # also echo the text to stdout
#   tts.sh --setup [--full]   # download the kokoro model weights
#   tts.sh --check            # report which engine would be used, say nothing
#   tts.sh --stop             # stop whatever this script is currently playing
#   tts.sh --async "text"     # start speaking and return immediately (stop with --stop)
#   tts.sh --daemon-status    # report the warm daemon's state
#   tts.sh --daemon-stop      # shut the warm daemon down
#
# Environment (HAWK_-prefixed names are accepted as aliases):
#   TTS_ENGINE   kokoro (default) | say | custom
#   TTS_VOICE    voice name passed to the engine (default: bm_lewis)
#   TTS_CMD      required when engine=custom; receives text on stdin
#   TTS_HOME     where weights live (default: ~/.models/tts)
#   TTS_SPEED    kokoro speed multiplier (default: 1.25)
#   TTS_LANG     phonemizer language (default: inferred from the voice prefix)
#   TTS_CACHE    narration cache dir, or "off" to disable
#                (default: ~/.local/state/pr-voice-review/audio-cache)
#   TTS_DAEMON   "off" to never use or spawn the warm daemon
#   TTS_DAEMON_WORKERS  parallel synths the daemon allows (default: 1)
#
# Exit codes:
#   0  the text was spoken (possibly by a fallback engine; see stderr)
#   3  nothing could speak; the text was printed instead
#   64 usage error
#
# Falling back exits 0 on purpose: callers are conversational agents whose
# harness treats any nonzero status as a failed step, and a fallback that
# actually spoke is not a failure. Degradation is reported on stderr.

set -uo pipefail

ENGINE="${TTS_ENGINE:-${HAWK_TTS_ENGINE:-kokoro}}"
TTS_HOME="${TTS_HOME:-${HAWK_TTS_HOME:-$HOME/.models/tts}}"
VOICE="${TTS_VOICE:-${HAWK_TTS_VOICE:-}}"
DEFAULT_VOICE="bm_lewis"
PRESET="${TTS_PRESET:-${HAWK_TTS_PRESET:-}}"
# Rotation gives concurrent agents distinct voices. Skills that render narration
# set this off: their artifacts must sound consistent, and the audio cache is
# keyed on voice, so a rotating voice would fragment it.
ROTATE="${TTS_ROTATE:-${HAWK_TTS_ROTATE:-on}}"
# Lives outside the skill on purpose: package updates overwrite tts.sh, so anything
# edited there would be lost on the next update.
PRESETS_FILE="${TTS_PRESETS:-${XDG_CONFIG_HOME:-$HOME/.config}/tts/presets.conf}"
CMD="${TTS_CMD:-${HAWK_TTS_CMD:-}}"
SPEED="${TTS_SPEED:-${HAWK_TTS_SPEED:-1.25}}"
LANG_CODE="${TTS_LANG:-${HAWK_TTS_LANG:-}}"
# Shared on purpose with the pr-voice-review skills: same directory, same key
# formula, so narration rendered there is a hit here and vice versa.
CACHE_DIR="${TTS_CACHE:-${HAWK_TTS_CACHE:-$HOME/.local/state/pr-voice-review/audio-cache}}"
DAEMON="${TTS_DAEMON:-${HAWK_TTS_DAEMON:-on}}"
DAEMON_WORKERS="${TTS_DAEMON_WORKERS:-${HAWK_TTS_DAEMON_WORKERS:-1}}"
DAEMON_TTL="${TTS_DAEMON_TTL:-${HAWK_TTS_DAEMON_TTL:-1800}}"
# Runtime state, not durable state: a socket, a pidfile, a lock and leases
# naming pids. All of it is meaningless after a reboot, so it belongs where the
# OS reclaims it — TMPDIR is macOS's XDG_RUNTIME_DIR. Safe against TMPDIR's own
# ~3-day purge because the daemon cannot outlive TTS_DAEMON_TTL. The audio cache
# deliberately does NOT live here; it has to survive between sessions.
STATE_DIR="${TTS_STATE:-${TMPDIR:-/tmp}/tts}"
SOCK="$STATE_DIR/daemon.sock"
PIDF="$STATE_DIR/daemon.pid"
LEASES="$STATE_DIR/leases"
VOICES_DIR="$STATE_DIR/voices"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KOKORO_DIR="$TTS_HOME/kokoro"
VOICES_FILE="$KOKORO_DIR/voices-v1.0.bin"
RELEASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

PRINT=0

die() { printf '%s\n' "$*" >&2; exit 64; }

# Prefer the fp16 build (177MB) over the full one (326MB); either works.
kokoro_model() {
  for f in "$KOKORO_DIR/kokoro-v1.0.fp16.onnx" "$KOKORO_DIR/kokoro-v1.0.onnx"; do
    [ -f "$f" ] && { printf '%s' "$f"; return 0; }
  done
  return 1
}

have_kokoro() { kokoro_model >/dev/null 2>&1 && [ -f "$VOICES_FILE" ]; }

player() {
  for p in afplay ffplay paplay aplay; do
    command -v "$p" >/dev/null 2>&1 && { printf '%s' "$p"; return 0; }
  done
  return 1
}

PIDFILE="${TMPDIR:-/tmp}/formulae-magicae-tts-playing.pid"
LASTWAV="${TMPDIR:-/tmp}/formulae-magicae-tts-last.wav"
ASYNC=0

# Sweep wavs orphaned by earlier async runs (they cannot self-clean — see the
# trap note in speak_kokoro). Older than 10 minutes = safely done playing.
cleanup_stale() {
  find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'speak.*' -mmin +10 -delete 2>/dev/null || true
  # Cache entries unused for a month, plus temps orphaned by an encode killed
  # mid-write. Nothing else ever reclaims this directory: ~/.local/state is an
  # XDG convention macOS knows nothing about, so it grows forever otherwise.
  # mtime, not atime, because every reader refreshes it on a hit — see cache_get.
  if [ "$CACHE_DIR" != "off" ] && [ -d "$CACHE_DIR" ]; then
    find "$CACHE_DIR" -maxdepth 1 -type f -mtime +30 -delete 2>/dev/null || true
    find "$CACHE_DIR" -maxdepth 1 -type f -name '.*' -mmin +60 -delete 2>/dev/null || true
  fi
}
cleanup_stale

# Plays in the background and records the PID, so --stop can interrupt it.
# Only ever kills a player this script started — never a stray afplay.
# With ASYNC=1 it returns as soon as playback starts, so the caller can keep
# working (prep the next file, watch for signals) while audio plays.
play_wav() {
  local wav="$1" p pid
  p="$(player)" || return 1
  case "$p" in
    afplay) afplay "$wav" & ;;
    ffplay) ffplay -nodisp -autoexit -loglevel quiet "$wav" & ;;
    paplay) paplay "$wav" & ;;
    aplay)  aplay -q "$wav" & ;;
  esac
  pid=$!
  printf '%s' "$pid" > "$PIDFILE"
  if [ "$ASYNC" = 1 ]; then
    disown "$pid" 2>/dev/null || true
    return 0
  fi
  wait "$pid"
  local rc=$?
  rm -f "$PIDFILE"
  # 129-143 = killed by a signal, i.e. --stop. That is a deliberate stop, not an error.
  [ "$rc" -ge 129 ] && [ "$rc" -le 143 ] && return 0
  return "$rc"
}

stop_playback() {
  [ -f "$PIDFILE" ] || { echo "nothing playing" >&2; return 0; }
  local pid; pid="$(cat "$PIDFILE" 2>/dev/null)"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null
  rm -f "$PIDFILE"
}

setup() {
  mkdir -p "$KOKORO_DIR"
  local model="kokoro-v1.0.fp16.onnx"
  [ "${1:-}" = "--full" ] && model="kokoro-v1.0.onnx"
  echo "Downloading $model and voices-v1.0.bin into $KOKORO_DIR ..." >&2
  curl -fL --progress-bar -o "$KOKORO_DIR/$model" "$RELEASE/$model" || die "download failed: $model"
  curl -fL --progress-bar -o "$VOICES_FILE" "$RELEASE/voices-v1.0.bin" || die "download failed: voices"
  echo "Done. $(du -sh "$KOKORO_DIR" | cut -f1) in $KOKORO_DIR" >&2
}

# Sets KVOICE/KLANG. Split out of synth_kokoro because the cache key has to
# cover the voice settings too — the same words in a different voice are a miss.
KVOICE=""
KLANG=""

# name voice speed. The last line names the rotation pool. A presets.conf in
# ~/.config/tts replaces this table wholesale.
BUILTIN_PRESETS="default bm_lewis 1.25
heart af_heart 1.25
bella af_bella 1.25
calm af_aoede 1.10
whisper af_nicole 1.15
jessica af_jessica 1.25
pool af_heart af_bella af_aoede af_nicole af_jessica"

preset_lines() {
  if [ -f "$PRESETS_FILE" ]; then
    sed -e 's/#.*//' "$PRESETS_FILE" | awk 'NF'
  else
    printf '%s\n' "$BUILTIN_PRESETS"
  fi
}

# An explicit TTS_VOICE/TTS_SPEED in the environment outranks the preset, so a
# one-off override still wins over a configured profile.
apply_preset() {
  [ -n "$PRESET" ] || return 0
  local line
  line="$(preset_lines | awk -v want="$PRESET" '$1 == want { print; exit }')"
  [ -n "$line" ] || die "unknown preset: $PRESET (see 'tts.sh --presets')"
  [ -n "${TTS_VOICE:-}" ] || VOICE="$(printf '%s\n' "$line" | awk '{print $2}')"
  [ -n "${TTS_SPEED:-}" ] || SPEED="$(printf '%s\n' "$line" | awk '{print $3}')"
}

pool_voices() {
  preset_lines | awk '$1 == "pool" { $1 = ""; print; exit }'
}

# Give each concurrent session its own voice, so two agents talking are told
# apart by ear. The first session to speak takes the default voice; later ones
# claim unused pool voices. Claims are released when the session exits.
assign_voice() {
  [ -z "$VOICE" ] || return 0
  [ "$ROTATE" != "off" ] || return 0
  local sid
  sid="$(session_pid)" || return 0
  mkdir -p "$VOICES_DIR" 2>/dev/null || return 0

  local claim
  for claim in "$VOICES_DIR"/*; do
    [ -e "$claim" ] || continue
    kill -0 "${claim##*/}" 2>/dev/null || rm -f "$claim"
  done

  if [ -s "$VOICES_DIR/$sid" ]; then
    VOICE="$(cat "$VOICES_DIR/$sid")"
    return 0
  fi

  local taken pick="" candidate
  taken=" $(cat "$VOICES_DIR"/* 2>/dev/null | tr '\n' ' ') "
  case "$taken" in
    *" $DEFAULT_VOICE "*) ;;
    *) pick="$DEFAULT_VOICE" ;;
  esac
  if [ -z "$pick" ]; then
    for candidate in $(pool_voices); do
      case "$taken" in
        *" $candidate "*) ;;
        *) pick="$candidate"; break ;;
      esac
    done
  fi
  # More live sessions than voices: sharing one is better than refusing to speak.
  [ -n "$pick" ] || pick="$DEFAULT_VOICE"

  printf '%s' "$pick" > "$VOICES_DIR/$sid" 2>/dev/null || true
  VOICE="$pick"
}

resolve_voice() {
  apply_preset
  assign_voice
  KVOICE="${VOICE:-$DEFAULT_VOICE}"
  KLANG="$LANG_CODE"
  # British voices (b-prefix) need en-gb phonemes; anything else defaults to en-us.
  if [ -z "$KLANG" ]; then
    case "$KVOICE" in b*) KLANG="en-gb" ;; *) KLANG="en-us" ;; esac
  fi
}

# ---- warm daemon ------------------------------------------------------------
# tts.sh exits after every utterance, so it pays uv startup plus a model load
# each time — ~2.4s before the first word. ttsd.py holds the model instead.
# Every function here fails soft: the daemon is an optimisation, and any
# problem with it must land on the inline path, never on the user.

# The session this call belongs to, found by walking up to the claude process.
# It is the lease identity, so a session that never speaks never registers one
# and never keeps the daemon alive.
session_pid() {
  local p="$PPID" n=0 comm
  while [ -n "$p" ] && [ "$p" -gt 1 ] 2>/dev/null && [ "$n" -lt 10 ]; do
    comm="$(ps -o comm= -p "$p" 2>/dev/null)"
    case "${comm##*/}" in claude*) printf '%s' "$p"; return 0 ;; esac
    p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"
    n=$((n + 1))
  done
  return 1
}

# pid + start time: a recycled pid must not read as a session still alive, or
# the daemon never reaches its all-sessions-gone rule.
write_lease() {
  local sp; sp="$(session_pid)" || return 0
  mkdir -p "$LEASES" 2>/dev/null || return 0
  ps -o lstart= -p "$sp" 2>/dev/null > "$LEASES/$sp" || rm -f "$LEASES/$sp"
  return 0
}

# Talking to a unix socket needs python3 (system one is enough — no kokoro
# here) or nc -U. Without either, the daemon is simply never used.
sock_send() {
  local payload="$1" timeout="${2:-120}"
  [ -S "$SOCK" ] || return 1
  if command -v python3 >/dev/null 2>&1; then
    SOCK="$SOCK" PAYLOAD="$payload" TIMEOUT="$timeout" python3 -c '
import json, os, socket, sys
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(float(os.environ["TIMEOUT"]))
    s.connect(os.environ["SOCK"])
    s.sendall((os.environ["PAYLOAD"] + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c:
            sys.exit(1)
        buf += c
    r = json.loads(buf)
    if not r.get("ok"):
        sys.exit(1)
    print(buf.decode().strip())
except Exception:
    sys.exit(1)
' 2>/dev/null
  else
    command -v nc >/dev/null 2>&1 || return 1
    printf '%s\n' "$payload" | nc -U "$SOCK" 2>/dev/null | head -1 | grep -q '"ok": *true'
  fi
}

# Builds and sends in one python3, rather than composing the payload in a
# separate call: that halves the interpreter spawns on the hot path, and the
# text never has to survive JSON-escaping in bash.
daemon_synth() {
  local out="$1" text="$2"
  [ "$DAEMON" = "off" ] && return 1
  [ -S "$SOCK" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  SOCK="$SOCK" OUT="$out" TEXT="$text" V="$KVOICE" S="$SPEED" L="$KLANG" python3 -c '
import json, os, socket, sys
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(os.environ["SOCK"])
    req = {"text": os.environ["TEXT"], "out": os.environ["OUT"],
           "voice": os.environ["V"], "speed": os.environ["S"],
           "lang": os.environ["L"]}
    s.sendall((json.dumps(req) + "\n").encode())
    f = s.makefile("rb")
    # Two deadlines. The ack proves the daemon is actually running rather than
    # stopped or wedged, and must arrive fast; the result may legitimately take
    # seconds for a long paragraph. One long timeout for both would make every
    # wedge cost the caller the full synthesis budget before falling back.
    s.settimeout(5)
    if not json.loads(f.readline() or "{}").get("ack"):
        sys.exit(1)
    s.settimeout(120)
    line = f.readline()
    sys.exit(0 if line and json.loads(line).get("ok") else 1)
except Exception:
    sys.exit(1)
' 2>/dev/null || return 1
  [ -s "$out" ]
}

daemon_running() {
  [ -f "$PIDF" ] || return 1
  local pid; pid="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# Runs only when the daemon failed us — a wedged process is exactly the case
# its own reaper thread cannot handle, and checking on every call would put a
# python3 spawn on the fast path for nothing.
reap_wedged_daemon() {
  daemon_running || { rm -f "$PIDF"; return 0; }
  sock_send '{"op": "status"}' 5 >/dev/null && return 0
  local pid; pid="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$pid" ] || return 0
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  sleep 1
  kill -0 "$pid" 2>/dev/null && { kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null; }
  rm -f "$PIDF" "$SOCK"
  return 0
}

spawn_daemon() {
  [ "$DAEMON" = "off" ] && return 0
  have_kokoro || return 0
  command -v uv >/dev/null 2>&1 || return 0
  [ -f "$HERE/ttsd.py" ] || return 0
  daemon_running && return 0
  mkdir -p "$STATE_DIR" 2>/dev/null || return 0
  MODEL="$(kokoro_model)" VOICES="$VOICES_FILE" TTS_STATE="$STATE_DIR" \
  TTS_DAEMON_WORKERS="$DAEMON_WORKERS" TTS_DAEMON_TTL="$DAEMON_TTL" \
  TTS_DAEMON_SWEEP="${TTS_DAEMON_SWEEP:-60}" \
  nohup uv run --no-project --quiet --with kokoro-onnx --with soundfile \
    python "$HERE/ttsd.py" >/dev/null 2>&1 &
  disown 2>/dev/null || true
  return 0
}

stop_daemon() {
  daemon_running || { echo "daemon not running" >&2; rm -f "$PIDF"; return 0; }
  local pid; pid="$(cat "$PIDF" 2>/dev/null)"
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  rm -f "$PIDF" "$SOCK"
  echo "stopped daemon $pid" >&2
}

# Daemon first, inline as the fallback. Both speak_kokoro and --out route
# through here, so the pre-render path gets the same speedup.
synth_kokoro() {
  local text="$1" wav="$2"
  resolve_voice
  if daemon_synth "$wav" "$text"; then
    write_lease
    return 0
  fi
  if [ "$DAEMON" != "off" ]; then
    reap_wedged_daemon
    spawn_daemon
    write_lease
  fi
  synth_inline "$text" "$wav"
}

synth_inline() {
  local text="$1" wav="$2"
  resolve_voice
  MODEL="$(kokoro_model)" VOICES="$VOICES_FILE" TEXT="$text" \
  KVOICE="$KVOICE" KSPEED="$SPEED" KLANG="$KLANG" OUT="$wav" \
  uv run --no-project --quiet --with kokoro-onnx --with soundfile python -c '
import os
from kokoro_onnx import Kokoro
import soundfile as sf
k = Kokoro(os.environ["MODEL"], os.environ["VOICES"])
samples, sr = k.create(os.environ["TEXT"], voice=os.environ["KVOICE"],
                       speed=float(os.environ["KSPEED"]), lang=os.environ["KLANG"])
sf.write(os.environ["OUT"], samples, sr)
' >/dev/null 2>&1 || return 1
  [ -s "$wav" ]
}

# ---- narration cache --------------------------------------------------------
# Synthesis costs ~2.5s of uv startup and model load before a single word comes
# out, every call. Anything said twice should only pay that once.

sha256_hex() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 | cut -d' ' -f1
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1
  else return 1; fi
}

# Byte-identical to audio_cache_key() in pr-voice-review's server.py — the "40k"
# is that skill's mp3 bitrate, kept in the string so the two agree. Change this
# and the two caches stop seeing each other's entries.
cache_key() {
  [ "$CACHE_DIR" = "off" ] && return 1
  printf '%s|%s|%s|40k|%s' "$KVOICE" "$SPEED" "$KLANG" "$1" | sha256_hex | cut -c1-32
}

# paplay and aplay are wav-only, so an mp3 entry is only a hit when the player
# that would actually open it can decode one.
plays_mp3() {
  case "$(player 2>/dev/null)" in afplay|ffplay) return 0 ;; *) return 1 ;; esac
}

# Touching on a hit is what makes the sweep an LRU. atime cannot be used for
# it: on APFS a read does not refresh atime even when it is 60 days stale
# (verified), so an -atime sweep really means "written 30 days ago" and would
# delete clips that are played every day.
cache_get() {
  local f
  for f in "$CACHE_DIR/$1.mp3" "$CACHE_DIR/$1.wav"; do
    [ -s "$f" ] || continue
    case "$f" in *.mp3) plays_mp3 || continue ;; esac
    touch "$f" 2>/dev/null || true
    printf '%s' "$f"; return 0
  done
  return 1
}

# mp3 when ffmpeg is around (~9x smaller, and it is what the PR skills read),
# wav otherwise. Published by rename: a half-written entry left under the real
# name is non-empty, so every later run would take it as a hit and play garbage.
cache_put() {
  local wav="$1" key="$2" tmp final
  mkdir -p "$CACHE_DIR" 2>/dev/null || return 0
  if command -v ffmpeg >/dev/null 2>&1; then
    # The .mp3 must be on the TEMP name too — ffmpeg infers the format from the
    # extension and fails outright on a bare .part suffix.
    tmp="$CACHE_DIR/.$key.$$.mp3"; final="$CACHE_DIR/$key.mp3"
    ffmpeg -y -loglevel error -i "$wav" -ac 1 -b:a 40k "$tmp" >/dev/null 2>&1 \
      || { rm -f "$tmp"; return 0; }
  else
    tmp="$CACHE_DIR/.$key.$$.wav"; final="$CACHE_DIR/$key.wav"
    cp -f "$wav" "$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
  fi
  if [ -s "$tmp" ]; then mv -f "$tmp" "$final" 2>/dev/null || rm -f "$tmp"; else rm -f "$tmp"; fi
  return 0
}

speak_kokoro() {
  local text="$1" tmp wav key hit
  resolve_voice
  key="$(cache_key "$text")" || key=""
  if [ -n "$key" ] && hit="$(cache_get "$key")"; then
    # LASTWAV may hold mp3 bytes under a .wav name; --again replays it through
    # the same player, which sniffs content and does not care about the suffix.
    cp -f "$hit" "$LASTWAV" 2>/dev/null || true
    play_wav "$hit"
    return $?
  fi
  # mktemp already creates the file; appending .wav would orphan the original, so
  # track and remove both.
  tmp="$(mktemp -t speak)"
  wav="$tmp.wav"
  # In async mode the function returns while afplay is still starting up, so a
  # RETURN trap would delete the wav before the player opens it — no sound, no
  # error. Async files are left behind and swept by cleanup_stale on later runs.
  if [ "$ASYNC" != 1 ]; then
    # shellcheck disable=SC2064
    trap "rm -f '$tmp' '$wav'" RETURN
  fi
  synth_kokoro "$text" "$wav" || return 1
  [ -n "$key" ] && cache_put "$wav" "$key"
  cp -f "$wav" "$LASTWAV" 2>/dev/null || true
  play_wav "$wav"
}

speak_say() {
  command -v say >/dev/null 2>&1 || return 1
  # A kokoro voice name (bm_lewis) is meaningless to `say`, so only pass the
  # voice through when `say` is the engine the caller actually asked for.
  local -a args=()
  [ -n "$VOICE" ] && [ "$ENGINE" = "say" ] && args=(-v "$VOICE")
  if [ "$ASYNC" = 1 ]; then
    say "${args[@]}" -- "$1" &
    printf '%s' "$!" > "$PIDFILE"
    disown 2>/dev/null || true
  else
    say "${args[@]}" -- "$1"
  fi
}

speak_custom() {
  [ -n "$CMD" ] || die "TTS_ENGINE=custom requires TTS_CMD"
  printf '%s' "$1" | eval "$CMD"
}

# ---- argument parsing -------------------------------------------------------

case "${1:-}" in
  --setup) shift; setup "$@"; exit 0 ;;
  --stop) stop_playback; exit 0 ;;
  --daemon-stop) stop_daemon; exit 0 ;;
  --daemon-status)
    if ! daemon_running; then echo "daemon: not running"; exit 0; fi
    sock_send '{"op": "status"}' 5 || echo "daemon: running but not answering (wedged)"
    exit 0 ;;
  -h|--help) sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  --check)
    if [ "$ENGINE" = "custom" ]; then echo "custom: ${CMD:-<unset>}"
    elif [ "$ENGINE" = "kokoro" ] && have_kokoro; then echo "kokoro: $(kokoro_model)"
    elif [ "$ENGINE" = "kokoro" ]; then echo "kokoro: weights missing, would fall back to say"
    else echo "$ENGINE"
    fi
    player >/dev/null 2>&1 || echo "warning: no audio player found"
    if [ "$CACHE_DIR" = "off" ]; then
      echo "cache: off"
    else
      n=$(find "$CACHE_DIR" -maxdepth 1 -type f \( -name '*.mp3' -o -name '*.wav' \) 2>/dev/null | wc -l | tr -d ' ')
      echo "cache: ${n:-0} clips in $CACHE_DIR"
    fi
    if [ "$DAEMON" = "off" ]; then
      echo "daemon: off"
    elif daemon_running; then
      echo "daemon: running (pid $(cat "$PIDF" 2>/dev/null), $DAEMON_WORKERS worker(s))"
    else
      echo "daemon: not running (starts on first speech)"
    fi
    exit 0 ;;
  --presets)
    if [ -f "$PRESETS_FILE" ]; then echo "from $PRESETS_FILE"; else echo "built in"; fi
    preset_lines | awk '$1 != "pool" { printf "  %-9s %-12s speed %s\n", $1, $2, $3 }'
    printf '  rotation pool:%s\n' "$(pool_voices)"
    echo "  in use now:   $(cat "$VOICES_DIR"/* 2>/dev/null | tr '\n' ' ')"
    exit 0 ;;
  --preset)
    shift; PRESET="${1:-}"; [ -n "$PRESET" ] || die "--preset needs a name"; shift ;;
  --voice)
    shift; VOICE="${1:-}"; [ -n "$VOICE" ] || die "--voice needs a name"
    TTS_VOICE="$VOICE"; shift ;;
  --voices)
    have_kokoro || die "no kokoro weights in $KOKORO_DIR — run 'tts.sh --setup'"
    MODEL="$(kokoro_model)" VOICES="$VOICES_FILE" \
    uv run --no-project --quiet --with kokoro-onnx python -c '
import os, collections
from kokoro_onnx import Kokoro
k = Kokoro(os.environ["MODEL"], os.environ["VOICES"])
g = collections.defaultdict(list)
for n in sorted(k.get_voices()):
    g[n[:2]].append(n)
for pre in sorted(g):
    print(pre + ": " + " ".join(g[pre]))
'
    exit 0 ;;
  --async) ASYNC=1; shift ;;
esac
case "${1:-}" in
  --print) PRINT=1; shift ;;
  --out)
    # Synthesize to FILE, play nothing. For pre-rendering a walkthrough's
    # narration at prep time so playback later skips synthesis entirely.
    OUT_FILE="${2:?--out needs a path}"; shift 2
    [ $# -ge 1 ] || die "usage: tts.sh --out FILE \"text\""
    if [ "$1" = "-" ]; then OUT_TEXT="$(cat)"; else OUT_TEXT="$*"; fi
    [ -n "${OUT_TEXT//[[:space:]]/}" ] || die "--out: empty text"
    have_kokoro || die "--out needs kokoro weights"
    synth_kokoro "$OUT_TEXT" "$OUT_FILE" || die "synthesis failed"
    printf '%s\n' "$OUT_FILE"; exit 0 ;;
  --play)
    # Play an existing wav (pre-rendered via --out). Respects --async and --stop.
    PLAY_FILE="${2:?--play needs a path}"
    [ -f "$PLAY_FILE" ] || die "no such file: $PLAY_FILE"
    cp -f "$PLAY_FILE" "$LASTWAV" 2>/dev/null || true
    play_wav "$PLAY_FILE"; exit $? ;;
  --again)
    # Replay the last synthesized utterance — no re-synthesis (2-4s saved).
    # Lives after the --async case so both "--again" and "--async --again" work.
    [ -f "$LASTWAV" ] || die "nothing to replay yet"
    stop_playback
    play_wav "$LASTWAV"; exit $? ;;
esac

[ $# -ge 1 ] || die "usage: tts.sh [--print] \"text\" | - ; see --help"

if [ "$1" = "-" ]; then TEXT="$(cat)"; else TEXT="$*"; fi
[ -n "${TEXT//[[:space:]]/}" ] || die "nothing to say"

[ "$PRINT" = 1 ] && printf '%s\n' "$TEXT"

# ---- dispatch ---------------------------------------------------------------

case "$ENGINE" in
  custom)
    speak_custom "$TEXT" && exit 0
    ;;
  say)
    speak_say "$TEXT" && exit 0
    ;;
  kokoro)
    if have_kokoro; then
      speak_kokoro "$TEXT" && exit 0
      echo "tts.sh: kokoro synthesis failed, falling back to 'say'" >&2
    else
      echo "tts.sh: kokoro weights not found in $KOKORO_DIR — run 'tts.sh --setup'" >&2
    fi
    speak_say "$TEXT" && exit 0
    ;;
  *)
    die "unknown TTS_ENGINE: $ENGINE"
    ;;
esac

# Nothing spoke.
[ "$PRINT" = 1 ] || printf '%s\n' "$TEXT"
exit 3
