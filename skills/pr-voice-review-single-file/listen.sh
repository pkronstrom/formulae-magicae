#!/bin/sh
# Optional listener for pr-voice-review-single-file.
#
# The walkthrough works with nothing running — this only removes the
# copy-and-paste step. When it is up, the file's Send button POSTs the feedback
# straight here and the agent picks it up without being asked.
#
#   usage:  listen.sh [port] [dir]
#   writes: <dir>/latest.json   — the most recent feedback block, body only
#           <dir>/req-N.http    — the raw request, kept for debugging
#
# No python, no node, no dependencies: nc ships with macOS and every Linux.
#
# Why the response looks like that: a file:// page is an opaque origin, so the
# browser needs Allow-Origin to read the reply, and Chrome's private-network
# rules want Allow-Private-Network for a request into 127.0.0.1. The page posts
# text/plain, which is a "simple" request — anything else triggers a preflight
# OPTIONS that a one-line nc loop cannot answer.
set -eu

PORT="${1:-8799}"
DIR="${2:-.}"
mkdir -p "$DIR"

RESP='HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Private-Network: true\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok'

echo "pr-voice-review listening on 127.0.0.1:$PORT -> $DIR/latest.json" >&2
n=0
while :; do
  n=$((n + 1))
  raw="$DIR/req-$n.http"
  printf "$RESP" | nc -l 127.0.0.1 "$PORT" > "$raw" || continue

  # ONLY a POST carries feedback. The page also GETs /ping on every open to see
  # whether anything is listening, and treating that as feedback overwrote
  # latest.json with an empty body — so simply reopening the walkthrough
  # destroyed feedback that had already been delivered.
  head -1 "$raw" | grep -q '^POST ' || continue

  # Headers end at the first blank line; strip CR so the blank line matches.
  # Written via a temp file so a reader never sees a half-written payload.
  tr -d '\r' < "$raw" | sed '1,/^$/d' > "$DIR/.latest.part"
  if [ -s "$DIR/.latest.part" ]; then
    mv "$DIR/.latest.part" "$DIR/latest.json"
    echo "received $(wc -c < "$DIR/latest.json" | tr -d ' ') bytes -> $DIR/latest.json" >&2
  else
    rm -f "$DIR/.latest.part"
  fi
done
