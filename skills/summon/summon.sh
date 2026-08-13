#!/bin/sh
# summon.sh — thin wrapper around `croc` for the Summon skill.
#
# croc does the real work (E2E encryption, NAT traversal, folder zipping,
# integrity). This wrapper only adds: a spoken 3-word incantation, a clipboard
# share line, and a receive that stages into a temp dir and hands the path back.
# It transfers any file or folder and does NOT care what the contents are.
#
# The incantation is 3 words from a bundled wordlist via /dev/urandom (the model
# never picks them), passed to croc as CROC_SECRET so the code is pure words with
# no number. Two wordlists ship: Finnish (default, easy for Finnish colleagues
# over voice) and English; `receive` normalizes whatever words it is handed, so
# the language flag only matters when sending.
#
# `send --strong` swaps the spoken 3-word code for a high-entropy hex secret. Use
# it ONLY when the secret travels inside an already-encrypted channel (e.g. relayed
# through a portal) and no human ever reads it aloud — there words buy memorability
# you don't need, and entropy is what matters.
#
# `send` serves until the peer connects, then exits. Run it in the background
# (the agent's background shell); it ends when that shell / the session ends.
#
# `receive` downloads into a fresh temp dir and prints its path. Placement is the
# agent's job — it moves/opens the files wherever the user wants, with its own
# tools. This script never writes to your working directory and never deletes
# anything; temp dirs under $TMPDIR are reaped by the OS.
#
# Subcommands (an optional --fi/--en/--lang flag may precede send args):
#   send [--en] [--strong] <path>      serve a file/folder (blocks until received)
#   send-text [--en] [--strong] <text> serve a chunk of text/context
#   receive <incantation>              download into a temp dir; print path + contents
#
# Output is simple `key: value` lines. `send` writes them to stderr (unbuffered,
# so they show immediately while it keeps serving); `receive` writes to stdout.

set -eu
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# WORDLIST is chosen per language by the dispatcher (wordlist.fi.txt / wordlist.en.txt).

die() { echo "status: error"; echo "error: $*"; exit 1; }
need_croc() { command -v croc >/dev/null 2>&1 || die "croc not found. Install with: brew install croc"; }
mktempdir() { mktemp -d "${TMPDIR:-/tmp}/summon.XXXXXX"; }
# How long a `send` keeps serving before giving up. A served-but-never-received croc that
# outlives its launcher busy-loops on relay reconnect at ~100% CPU forever, so cap it.
SUMMON_SEND_TIMEOUT="${SUMMON_SEND_TIMEOUT:-3600}"

pick_word() { r="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"; sed -n "$(( (r % $1) + 1 ))p" "$WORDLIST"; }

# Accept the incantation however it was spoken/typed — spaces, hyphens, mixed
# case — and fold it back to the lowercase `word-word-word` form croc expects.
normalize_incantation() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ._-' '-' | sed -e 's/^-*//' -e 's/-*$//'
}

gen_incantation() {
    [ -f "$WORDLIST" ] || die "wordlist missing: $WORDLIST"
    n="$(wc -l < "$WORDLIST" | tr -d ' ')"
    [ "$n" -gt 0 ] || die "wordlist is empty"
    printf '%s-%s-%s' "$(pick_word "$n")" "$(pick_word "$n")" "$(pick_word "$n")"
}

# A 128-bit hex secret for --strong, drawn the same way (od + /dev/urandom) as the
# wordlist picks — no new dependency. Hex on purpose: `normalize_incantation`
# lowercases the received code, and hex survives that round-trip unchanged where
# mixed-case base64 would be corrupted.
gen_strong() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

# --- send (blocks while serving; run it in the background) ------------------
do_send() {
    need_croc
    src="$1"
    [ -e "$src" ] || die "no such path: $src"
    name="$(basename "$src")"
    # On stderr in both modes: this process blocks on croc and never returns to
    # flush a block-buffered stdout pipe, but stderr is unbuffered — so the agent's
    # background reader sees the incantation immediately while croc serves.
    if [ "${STRONG:-no}" = yes ]; then
        # Strong mode: a high-entropy secret meant to ride inside an already-
        # encrypted channel. No clipboard / share line — a human never handles it.
        code="$(gen_strong)"
        {
            echo "status: serving"
            echo "incantation: $code"
            echo "name: $name"
            echo "mode: strong — relay this secret through the encrypted channel, never aloud"
        } >&2
    else
        code="$(gen_incantation)"
        share="Summon this: $code  ($name) — receive with: croc $code"
        clip="no"
        command -v pbcopy >/dev/null 2>&1 && printf '%s' "$share" | pbcopy && clip="yes"
        {
            echo "status: serving"
            echo "incantation: $code"
            echo "name: $name"
            echo "clipboard: $clip"
            echo "share_line: $share"
        } >&2
    fi
    # Serve in the background and supervise it, so croc never outlives its launcher.
    # An orphaned `croc send` (receiver never came, parent died) busy-loops on relay
    # reconnect at ~100% CPU forever — guard three ways: a signal trap, an orphaned-to-
    # init check (the launcher/session died), and a hard SUMMON_SEND_TIMEOUT cap.
    CROC_SECRET="$code" croc --yes send "$src" >&2 &
    croc_pid=$!
    trap 'kill "$croc_pid" 2>/dev/null; exit 0' TERM INT HUP
    start_ppid="$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')"
    deadline=$(( $(date +%s) + SUMMON_SEND_TIMEOUT ))
    while kill -0 "$croc_pid" 2>/dev/null; do
        [ "$start_ppid" != 1 ] && [ "$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')" = 1 ] && { kill "$croc_pid" 2>/dev/null || true; break; }
        [ "$(date +%s)" -ge "$deadline" ] && { kill "$croc_pid" 2>/dev/null || true; { echo "status: timeout"; echo "note: no peer connected within ${SUMMON_SEND_TIMEOUT}s — stopped serving"; } >&2; break; }
        sleep 2
    done
    trap - TERM INT HUP
    wait "$croc_pid" 2>/dev/null || true
}

do_send_text() {
    need_croc
    tmp="$(mktempdir)"
    printf '%s' "$1" > "$tmp/message.md"
    do_send "$tmp/message.md"
}

# --- receive (stage into a temp dir; hand the path to the agent) ------------
do_receive() {
    need_croc
    q="$(mktempdir)"
    code="$(normalize_incantation "$1")"
    [ -n "$code" ] || die "empty incantation"
    if ! out="$(CROC_SECRET="$code" croc --yes --overwrite --out "$q" 2>&1)"; then
        die "transfer failed: $out"
    fi
    echo "status: ok"
    echo "received_into: $q"
    echo "origin: not verified — croc encrypts the transfer but does not prove who sent it"
    weird="$(find "$q" ! -type d ! -type f 2>/dev/null | head -n1)"
    [ -n "$weird" ] && echo "warning: contains a symlink or special file — inspect before using"
    echo "contents:"
    (cd "$q" && find . -mindepth 1 | sed 's|^\./|  |')
}

# --- dispatch --------------------------------------------------------------
cmd="${1:-}"; [ "$#" -gt 0 ] && shift || true

# Optional leading flags for send/send-text: --fi/--en/--lang pick the incantation
# wordlist; --strong swaps the spoken 3-word code for a high-entropy secret. They
# may come in any order before the positional arg. receive needs no flags (it
# normalizes whatever code it is handed). Finnish is the default wordlist.
lang=fi
STRONG=no
while [ "$#" -gt 0 ]; do
    case "$1" in
        --lang)   shift; lang="${1:-fi}" ;;
        --lang=*) lang="${1#--lang=}" ;;
        --fi)     lang=fi ;;
        --en)     lang=en ;;
        --strong) STRONG=yes ;;
        --)       shift; break ;;
        *)        break ;;
    esac
    shift
done
case "$lang" in
    fi) WORDLIST="$SCRIPT_DIR/wordlist.fi.txt" ;;
    en) WORDLIST="$SCRIPT_DIR/wordlist.en.txt" ;;
    *)  die "unknown language: $lang (use fi or en)" ;;
esac

case "$cmd" in
    send)       [ "$#" -ge 1 ] || die "usage: summon.sh send <path>"; do_send "$1" ;;
    send-text)  [ "$#" -ge 1 ] || die "usage: summon.sh send-text <text>"; do_send_text "$1" ;;
    receive)    [ "$#" -ge 1 ] || die "usage: summon.sh receive <incantation>"; do_receive "$1" ;;
    *)          die "unknown command: ${cmd:-(none)}. Use send|send-text|receive" ;;
esac
