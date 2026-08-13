#!/usr/bin/env bash
# One call that does every mechanical startup step, in parallel where possible.
# Replaces ~8 serial agent tool calls (~45s) with one (~3s).
#
#   bootstrap.sh <owner> <repo> <num> <session-dir>
#
# Starts (or reuses) the bridge server, fires /prepare, and reports environment
# status. /prepare runs server-side while the agent gets on with the browser and
# triage — never wait on it here; it lands as a `prepared` event.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TTS="${TTS_PATH:-}"
if [ -z "$TTS" ]; then
  TTS="$(command -v tts.sh 2>/dev/null || true)"
fi
if [ -z "$TTS" ] && [ -x "$HERE/../tts/tts.sh" ]; then
  TTS="$(cd "$HERE/../tts" && pwd)/tts.sh"
fi
[ -n "$TTS" ] && [ -x "$TTS" ] || TTS=""

if [ "${1:-}" = "--resolve-tts" ]; then
  printf '%s\n' "$TTS"
  exit 0
fi

OWNER="${1:?owner}"; REPO="${2:?repo}"; NUM="${3:?pr number}"; D="${4:?session dir}"
PORT="${PRV_PORT:-8765}"
# Narration keeps the default voice even when several agents are running. Two
# reasons: a walkthrough should not change voice partway through, and the audio
# cache is keyed on voice, so a rotating voice would miss every cached clip.
export TTS_ROTATE=off

mkdir -p "$D/audio"

# Reuse a live server only if it is the current version; otherwise replace it.
WANT="$(grep -o '"v": [0-9]*' "$HERE/server.py" | head -1 | grep -o '[0-9]*')"
GOT="$(curl -s --max-time 2 "127.0.0.1:$PORT/ping" | grep -o '"v": [0-9]*' | grep -o '[0-9]*')"
if [ -n "$GOT" ] && [ "$GOT" != "$WANT" ]; then
  [ -f "$D/server.pid" ] && kill "$(cat "$D/server.pid")" 2>/dev/null
  lsof -ti ":$PORT" 2>/dev/null | xargs -r kill 2>/dev/null
  sleep 1; GOT=""
fi
if [ -z "$GOT" ]; then
  if [ -n "$TTS" ]; then
    nohup python3 "$HERE/server.py" --port "$PORT" --audio-dir "$D/audio" \
      --pidfile "$D/server.pid" --tts "$TTS" --data-dir "$D" >"$D/server.log" 2>&1 &
  else
    nohup python3 "$HERE/server.py" --port "$PORT" --audio-dir "$D/audio" \
      --pidfile "$D/server.pid" --data-dir "$D" >"$D/server.log" 2>&1 &
  fi
  for _ in $(seq 1 40); do
    curl -s --max-time 1 "127.0.0.1:$PORT/ping" >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

# Fire intake immediately — this is the long pole and it runs server-side.
PREP="$(curl -s --max-time 5 -X POST "127.0.0.1:$PORT/prepare" \
  -d "{\"owner\":\"$OWNER\",\"repo\":\"$REPO\",\"num\":$NUM}")"

echo "server:  $(curl -s --max-time 2 "127.0.0.1:$PORT/ping")"
echo "prepare: $PREP"
if [ -n "$TTS" ]; then
  echo "tts:     $("$TTS" --check 2>&1 | head -1)"
else
  echo "tts:     unavailable (set TTS_PATH to an installed tts.sh for narration)"
fi
echo "gh:      $(gh auth status 2>&1 | grep -m1 'Logged in' || echo 'NOT AUTHENTICATED')"
echo "url:     https://github.com/$OWNER/$REPO/pull/$NUM/files"
echo "data:    $D"
echo
echo "Next: navigate the browser to the url above, then curl /wait for the 'prepared' event."
