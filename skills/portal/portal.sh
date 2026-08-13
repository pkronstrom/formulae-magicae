#!/bin/sh
# portal.sh — thin wrapper for end-to-end-encrypted agent-to-agent chat over ntfy.
#
# A channel is identified by a 3-word incantation (same wordlists as the summon
# skill). The incantation is run through PBKDF2-HMAC-SHA256 to derive the ntfy topic
# plus two keys (so the relay can't cheaply brute-force the spoken secret); every
# message is then AES-256-CBC encrypted and HMAC-SHA256 authenticated (encrypt-then-
# MAC), so ntfy only ever relays ciphertext on a topic nobody can guess.
#
# The incantation is spoken to the script ONCE, at `open`: it derives the keys,
# stores them (derived keys only, never the words; umask 077) in the channel's
# $TMPDIR dir, and marks that channel "active". Afterwards send/read/wait/close
# need no incantation — they act on the active channel (or an explicit, non-secret
# --channel <topic>). This keeps the spoken secret out of the argv of every call.
#
# This script NEVER deletes anything. The channel dir (keys, inbox) lives under
# $TMPDIR and is reaped by the OS; `close` only stops the background streamer.
#
# Subcommands:
#   new [--fi|--en]                       generate an incantation to share out-of-band
#   open <incantation>                    bind the channel + stream it into a session inbox (BLOCKS; run in background)
#   send <text> [--from <name>] [--to <name>] [--channel <topic>]   publish one message to the active (or named) channel
#   read [--channel <topic>]              print inbox lines new since the last read
#   wait [--channel <topic>]              block until a new inbox line appears, print it, exit
#   close [--channel <topic>]             stop the background streamer (does not delete anything)
#
# Local mode (same machine — a shared plaintext bus, no relay/crypto/streamer):
#   send <text> --local [--to <name>]     post to the local bus (broadcast, or to one session)
#   read --local / wait --local           read/await local messages (your own are skipped)
#   who                                   list local session names you can reach
#   whoami                                this session's local name (auto magical; PORTAL_NAME overrides)
set -eu
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WORDLIST_DIR="$SCRIPT_DIR"
NTFY_BASE="${PORTAL_NTFY_BASE:-https://ntfy.sh}"
STATE_ROOT="${TMPDIR:-/tmp}"
# ntfy.sh silently truncates message bodies above ~4000 bytes (still returning HTTP
# 200), which would corrupt the ciphertext so the receiver drops it — a send that
# looks successful but never arrives. Reject oversized messages loudly instead. Raise
# only if you self-host ntfy with a larger message-size-limit.
PORTAL_MAX_WIRE="${PORTAL_MAX_WIRE:-3900}"
# A background streamer (do_open) must never outlive its launcher — an un-closed one
# used to reparent to init and respawn curl forever (found 18-day-old orphans). Two
# tunables back the self-cleanup in do_open: how often curl returns so the loop can
# re-check its liveness guards, and a hard cap after which a streamer stops regardless.
PORTAL_POLL_MAX="${PORTAL_POLL_MAX:-300}"            # seconds: curl --max-time per connection
PORTAL_MAX_LIFETIME="${PORTAL_MAX_LIFETIME:-43200}"  # seconds: 12h hard cap on one streamer

# --- local mode: one shared plaintext bus for agents on THIS machine ------------
# Same user, same host -> same trust domain, so no relay, no encryption, no streamer.
# Sessions are told apart by a unique magical name (override with PORTAL_NAME).
LOCAL_DIR="$STATE_ROOT/portal-local"
BUS="$LOCAL_DIR/bus.log"
ROSTER="$LOCAL_DIR/roster"
MAGIC_ADJ="ember frost moon silver dusk raven thorn gilt shadow opal amber slate jade onyx ivory cobalt"
MAGIC_NOUN="fox whistle thistle lantern sparrow willow quill cinder bramble heron marsh wisp drake reed vale glimmer"

die() { echo "status: error"; echo "error: $*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not found"; }

# Accept the incantation however it was spoken/typed — spaces or hyphens, any case
# ("banaani polku gorilla" == "Banaani-Polku-Gorilla") — and fold it to the canonical
# lowercase word-word-word form before deriving anything. WITHOUT this, the same words
# said two ways hash to two different channels. (Same normalization as the summon skill.)
normalize_incantation() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ._-' '-' | sed -e 's/^-*//' -e 's/-*$//'
}

# Derive topic + keys with PBKDF2-HMAC-SHA256 (RFC 2898), NOT a bare SHA-256. The ntfy
# topic is visible to the relay, so a bare hash lets it brute-force the ~3-word spoken
# secret offline (seconds). PBKDF2 makes EACH guess cost PORTAL_ITER iterations, turning
# that into days+. `openssl enc -pbkdf2 ... -P` prints the derived key and behaves
# identically on stock-macOS LibreSSL and OpenSSL 3 (verified). Domain-separated salts
# keep topic/enc/mac independent. Cost is paid ONCE per open (keys are cached), not per
# message. Changing PORTAL_ITER changes the channel — both sides must match.
PORTAL_ITER=600000
SALT_TOPIC=706f7274616c5f74   # "portal_t"
SALT_ENC=706f7274616c5f65     # "portal_e"
SALT_MAC=706f7274616c5f6d     # "portal_m"
pbkdf2_hex() { # $1=normalized incantation  $2=salt(hex) -> 64 lowercase hex chars
    # Feed the incantation via stdin, NOT `-pass pass:$1`: command-line args are visible
    # to any same-user process (ps / /proc/<pid>/cmdline), and this is the root secret.
    # `-pass stdin` reads one line and strips its trailing newline, deriving the byte-
    # identical key (verified), so the wire format and golden test values are unchanged.
    k="$(printf '%s' "$1" | openssl enc -aes-256-cbc -pbkdf2 -iter "$PORTAL_ITER" -md sha256 -pass stdin -S "$2" -P 2>/dev/null | sed -n 's/^key=//p' | tr 'A-F' 'a-f')"
    [ -n "$k" ] || die "openssl PBKDF2 unavailable (need OpenSSL 1.1+/LibreSSL with 'enc -pbkdf2 -P')"
    printf '%s' "$k"
}
topic_for()   { printf 'portal-%s' "$(pbkdf2_hex "$(normalize_incantation "$1")" "$SALT_TOPIC" | cut -c1-16)"; }
enc_key_for() { pbkdf2_hex "$(normalize_incantation "$1")" "$SALT_ENC"; }
mac_key_for() { pbkdf2_hex "$(normalize_incantation "$1")" "$SALT_MAC"; }
dir_for()       { printf '%s/portal.%s' "$STATE_ROOT" "$(topic_for "$1")"; }
dir_for_topic() { printf '%s/portal.%s' "$STATE_ROOT" "$1"; }
# Per-session, so two sessions on one host don't clobber each other's active channel.
active_file() { printf '%s/portal.active.%s' "$STATE_ROOT" "$(session_id)"; }

# The active channel lets send/read/wait/close run without re-typing the
# incantation. resolve_topic prefers an explicit --channel handle (the topic,
# which is NOT secret), else falls back to the last-opened (active) channel.
resolve_topic() {
    if [ -n "${1:-}" ]; then printf '%s' "$1"; return 0; fi
    t="$(cat "$(active_file)" 2>/dev/null || true)"
    [ -n "$t" ] || die "no active portal — open one first, or pass --channel <topic>"
    printf '%s' "$t"
}

# Establish a channel from its incantation: persist the DERIVED keys (never the
# incantation itself) and mark it active. Writing files only — no deletion.
bind_channel() { # $1=incantation -> echoes the topic
    inc="$1"; topic="$(topic_for "$inc")"; d="$(dir_for_topic "$topic")"
    mkdir -p "$d"
    { printf 'enc %s\n' "$(enc_key_for "$inc")"
      printf 'mac %s\n' "$(mac_key_for "$inc")"
      printf 'topic %s\n' "$topic"; } > "$d/keys"
    printf '%s' "$topic" > "$(active_file)"
    printf '%s' "$topic"
}

load_keys() { # $1=channel dir -> sets ek, mk
    [ -f "$1/keys" ] || die "channel not open (no keys) — run: open <incantation> first"
    ek="$(awk '$1=="enc"{print $2}' "$1/keys")"
    mk="$(awk '$1=="mac"{print $2}' "$1/keys")"
}

# A stable id for THIS Claude session, so a session skips only the echoes of its own
# sends — not messages from another session sharing the same channel dir on this
# machine. ntfy delivers your own published message back to you; without this, every
# send would bounce into your own inbox. Per-session (not per-channel) on purpose.
session_id() { printf '%s' "${CLAUDE_CODE_SESSION_ID:-default}" | tr -c 'a-zA-Z0-9-' '_'; }

pick_word() { r="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"; sed -n "$(( (r % $1) + 1 ))p" "$2"; }
gen_incantation() {
    wl="$1"
    [ -f "$wl" ] || die "wordlist missing: $wl"
    n="$(wc -l < "$wl" | tr -d ' ')"
    [ "$n" -gt 0 ] || die "wordlist is empty: $wl"
    printf '%s-%s-%s' "$(pick_word "$n" "$wl")" "$(pick_word "$n" "$wl")" "$(pick_word "$n" "$wl")"
}

b64()   { openssl base64 -A; }
unb64() { openssl base64 -d -A; }
# NOTE: the key is the 64-char ASCII hex digest used verbatim as the HMAC string
# key (64 bytes = HMAC-SHA256's block size, carrying the full 256 bits of entropy).
# This is intentional and portable across OpenSSL/LibreSSL. Do NOT "improve" it to
# `-macopt hexkey:` — that interprets the key as raw bytes and changes every MAC,
# breaking the v1 wire format and the golden test values.
hmac_hex() { openssl dgst -sha256 -hmac "$1" | awk '{print $NF}'; }

encrypt_with() { # $1=enc_key $2=mac_key $3=plaintext -> v2.<iv_hex>.<ct_b64>.<mac_hex>
    iv="$(openssl rand -hex 16)"
    ct="$(printf '%s' "$3" | openssl enc -aes-256-cbc -K "$1" -iv "$iv" | b64)"
    mac="$(printf '%s%s' "$iv" "$ct" | hmac_hex "$2")"
    printf 'v2.%s.%s.%s' "$iv" "$ct" "$mac"
}
encrypt_msg() { encrypt_with "$(enc_key_for "$1")" "$(mac_key_for "$1")" "$2"; }  # stateless (for _encrypt / tests)

decrypt_with() { # $1=enc_key $2=mac_key $3=wire -> plaintext on stdout; return 1 on any failure
    case "$3" in v2.*.*.*) ;; *) return 1 ;; esac
    rest="${3#v2.}"; iv="${rest%%.*}"; rest="${rest#*.}"; ct="${rest%%.*}"; mac="${rest#*.}"
    want="$(printf '%s%s' "$iv" "$ct" | hmac_hex "$2")"
    [ "$want" = "$mac" ] || return 1
    printf '%s' "$ct" | unb64 | openssl enc -d -aes-256-cbc -K "$1" -iv "$iv" 2>/dev/null
}
decrypt_msg() { decrypt_with "$(enc_key_for "$1")" "$(mac_key_for "$1")" "$2"; }  # stateless (for _decrypt / tests)

json_escape() { printf '%s' "$1" | tr '\n\r\t' '   ' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

do_send() { # $1=channel(optional topic) $2=text $3=from(optional) $4=to(optional directed-hint)
    need openssl
    ch="${1:-}"; text="$2"; from="${3:-$(id -un)}"; to="${4:-}"
    topic="$(resolve_topic "$ch")"; d="$(dir_for_topic "$topic")"
    load_keys "$d"
    mid="$(openssl rand -hex 8)"; ts="$(date +%s)"
    # `to` is a routing/display hint only — every room member shares the key and
    # can read it. text stays the LAST field so msg_text's "}$ anchor holds.
    plaintext="$(printf '{"id":"%s","from":"%s","to":"%s","ts":%s,"text":"%s"}' \
        "$mid" "$(json_escape "$from")" "$(json_escape "$to")" "$ts" "$(json_escape "$text")")"
    wire="$(encrypt_with "$ek" "$mk" "$plaintext")"
    wlen="$(printf '%s' "$wire" | wc -c | tr -d ' ')"
    [ "$wlen" -le "$PORTAL_MAX_WIRE" ] || die "message too long: ${wlen}-byte wire exceeds PORTAL_MAX_WIRE=$PORTAL_MAX_WIRE. ntfy.sh silently truncates above ~4000 bytes, which would corrupt the ciphertext and the message would vanish on the other end. Shorten the text (or raise PORTAL_MAX_WIRE only if your relay allows larger messages)."
    if [ "${PORTAL_DRYRUN:-0}" = "1" ]; then echo "status: dryrun"; echo "wire: $wire"; return 0; fi
    need curl
    # Record this id as our own send so our streamer skips its ntfy echo (see session_id).
    printf '%s\n' "$mid" >> "$d/sent.$(session_id).ids"
    code="$(printf '%s' "$wire" | curl -s --data-binary @- "$NTFY_BASE/$topic" -o /dev/null -w '%{http_code}')"
    [ "$code" = "200" ] || die "publish failed (http $code)"
    echo "status: sent"
    echo "to_topic: $topic"
}

json_field() { sed -n "s/.*\"$1\":\"\\([^\"]*\\)\".*/\\1/p"; }
json_unescape() { sed -e 's/\\"/"/g' -e 's/\\\\/\\/g'; }
# Extract the trailing "text" field from one of our plaintext JSON lines (stdin).
# text is always the last field, so the greedy capture anchored on the final "}
# is exact even when the text itself contains } or (escaped) quotes.
msg_text() { sed -n 's/.*"text":"\(.*\)"}$/\1/p' | json_unescape; }

do_open() { # $1=incantation — bind the channel, then BLOCK streaming; run in background
    need openssl; need curl
    inc="$1"; topic="$(bind_channel "$inc")"; d="$(dir_for_topic "$topic")"
    load_keys "$d"   # ek, mk from the cached keys bind wrote — PBKDF2 paid once, not per message
    inbox="$d/inbox.log"; seen="$d/seen.ids"; ownsent="$d/sent.$(session_id).ids"
    : >> "$inbox"; : >> "$seen"; : >> "$ownsent"
    printf '%s\n' "$$" >> "$d/listeners.$(session_id)"   # per-session, so close only stops OUR streamers
    { echo "status: open"; echo "topic: $topic"; echo "inbox: $inbox"; } >&2
    # Never outlive our launcher. Three backstops: (1) a signal trap kills our curl child
    # on close/term; (2) if we get reparented to init the session died without calling
    # close, so stop; (3) a hard max-lifetime cap. curl's --max-time bounds each connection
    # so the loop re-checks (2) and (3) every PORTAL_POLL_MAX seconds (it reconnects with
    # ?since=<last.id>, so no messages are missed) instead of blocking on the stream forever.
    trap 'pkill -P $$ 2>/dev/null; exit 0' TERM INT HUP
    start_ppid="$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')"
    deadline=$(( $(date +%s) + PORTAL_MAX_LIFETIME ))
    while :; do
        [ "$start_ppid" != 1 ] && [ "$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')" = 1 ] && break
        [ "$(date +%s)" -ge "$deadline" ] && break
        url="$NTFY_BASE/$topic/json"
        last="$(cat "$d/last.id" 2>/dev/null || true)"
        [ -n "$last" ] && url="$url?since=$last"
        curl -sN --max-time "$PORTAL_POLL_MAX" "$url" 2>/dev/null | while IFS= read -r line; do
            case "$line" in *'"event":"message"'*) ;; *) continue ;; esac
            nid="$(printf '%s' "$line" | json_field id)"
            [ -n "$nid" ] && printf '%s' "$nid" > "$d/last.id"
            blob="$(printf '%s' "$line" | sed -n 's/.*"message":"\(v2\.[^"]*\)".*/\1/p')"
            [ -n "$blob" ] || continue
            pt="$(decrypt_with "$ek" "$mk" "$blob")" || continue
            mid="$(printf '%s' "$pt" | json_field id)"
            # skip our own echo (we published it), then dedup repeats
            [ -n "$mid" ] && grep -qxF "$mid" "$ownsent" 2>/dev/null && continue
            [ -n "$mid" ] && grep -qxF "$mid" "$seen" 2>/dev/null && continue
            [ -n "$mid" ] && printf '%s\n' "$mid" >> "$seen"
            # Strip tabs/newlines from the (attacker-controllable) decrypted fields: an
            # authorized peer could otherwise embed a literal tab to shift the inbox's
            # tab-separated columns, or a newline to inject a whole fake inbox line. Mirrors
            # the send-side json_escape, which already neutralizes these for honest senders.
            from="$(printf '%s' "$pt" | json_field from | tr '\t\n\r' '   ')"
            to="$(printf '%s' "$pt" | json_field to | tr '\t\n\r' '   ')"
            txt="$(printf '%s' "$pt" | msg_text | tr '\t\n\r' '   ')"
            # inbox columns: epoch \t from \t to \t text  (to is empty if undirected)
            printf '%s\t%s\t%s\t%s\n' "$(date +%s)" "$from" "$to" "$txt" >> "$inbox"
        done
        sleep 2
    done
    pkill -P $$ 2>/dev/null || true   # we broke out (orphaned or max lifetime): sweep any curl child
}

do_read() { # $1=channel(optional) — print inbox lines new since last read
    topic="$(resolve_topic "${1:-}")"; d="$(dir_for_topic "$topic")"; inbox="$d/inbox.log"
    [ -f "$inbox" ] || die "no portal inbox for that channel (is it open?)"
    off="$d/read.offset"; n="$(cat "$off" 2>/dev/null || echo 0)"
    total="$(wc -l < "$inbox" | tr -d ' ')"
    # If the inbox was recreated/truncated (e.g. TMPDIR reaped, channel reopened),
    # a stale offset could exceed the line count and silently hide everything.
    [ "$n" -gt "$total" ] && n=0
    [ "$total" -gt "$n" ] && sed -n "$((n+1)),\$p" "$inbox"
    printf '%s' "$total" > "$off"
}

do_wait() { # $1=channel(optional) — block until there is unread, print ALL unread, advance the cursor, exit
    topic="$(resolve_topic "${1:-}")"; d="$(dir_for_topic "$topic")"; inbox="$d/inbox.log"
    [ -f "$inbox" ] || die "no portal inbox for that channel (is it open?)"
    # Share read's cursor so a wake delivers everything unread — including messages
    # that arrived in a re-arm gap or while no wait was armed. Nothing is ever skipped.
    off="$d/read.offset"; n="$(cat "$off" 2>/dev/null || echo 0)"
    total="$(wc -l < "$inbox" | tr -d ' ')"
    [ "$n" -gt "$total" ] && n=0   # stale-offset guard (inbox recreated/truncated)
    while [ "$total" -le "$n" ]; do
        sleep 2
        total="$(wc -l < "$inbox" | tr -d ' ')"
        [ "$n" -gt "$total" ] && n=0
    done
    sed -n "$((n+1)),\$p" "$inbox"
    printf '%s' "$total" > "$off"
}

do_close() { # $1=channel(optional) — stop THIS session's streamers for the channel (deletes nothing)
    need openssl
    topic="$(resolve_topic "${1:-}")"; d="$(dir_for_topic "$topic")"; lf="$d/listeners.$(session_id)"
    # Each `open` in THIS session appended its pid here, so kill every one (and its curl
    # child) — catches stray/duplicate streamers a single listener.pid would miss. It is
    # per-session, so closing does NOT tear down another session that shares the channel.
    if [ -f "$lf" ]; then
        while IFS= read -r pid; do
            [ -n "$pid" ] || continue
            pkill -P "$pid" 2>/dev/null || true   # the streaming curl is a child of $pid
            kill "$pid" 2>/dev/null || true
        done < "$lf"
    fi
    # NOTE: intentionally leaves the channel dir (keys, inbox, listeners) in place —
    # this script never deletes anything; the OS reaps $TMPDIR. Stale pids are harmless
    # (kill of a dead pid is a no-op).
    echo "status: closed"
}

# --- local mode helpers ---------------------------------------------------------
# A stable, unique-ish magical name for this session (override with PORTAL_NAME, e.g.
# a purpose-based name the agent picks). Derived from the session id so it's stable.
session_name() {
    [ -n "${PORTAL_NAME:-}" ] && { printf '%s' "$PORTAL_NAME"; return 0; }
    h="$(printf '%s' "$(session_id)" | openssl dgst -sha256 | awk '{print $NF}')"
    ai=$(( 0x$(printf '%s' "$h" | cut -c1-2) % 16 )); ni=$(( 0x$(printf '%s' "$h" | cut -c3-4) % 16 ))
    adj="$(printf '%s\n' $MAGIC_ADJ | sed -n "$((ai+1))p")"
    noun="$(printf '%s\n' $MAGIC_NOUN | sed -n "$((ni+1))p")"
    printf '%s-%s' "$adj" "$noun"
}

local_register() { # announce this session on the roster (sid -> name), once
    mkdir -p "$LOCAL_DIR"; : >> "$ROSTER"
    sid="$(session_id)"
    grep -q "^$sid	" "$ROSTER" 2>/dev/null || printf '%s\t%s\n' "$sid" "$(session_name)" >> "$ROSTER"
}

do_local_send() { # $1=text $2=to(optional name; empty = broadcast)
    need openssl
    text="$1"; to="${2:-}"
    mkdir -p "$LOCAL_DIR"; : >> "$BUS"; local_register
    # plaintext line: ts \t sid \t from \t to \t text  (tabs/newlines in text flattened)
    safe="$(printf '%s' "$text" | tr '\n\r\t' '   ')"
    printf '%s\t%s\t%s\t%s\t%s\n' "$(date +%s)" "$(session_id)" "$(session_name)" "$to" "$safe" >> "$BUS"
    echo "status: sent-local"
    echo "as: $(session_name)"
    [ -n "$to" ] && echo "to: $to" || echo "to: (broadcast)"
}

# print bus lines new since this session's cursor, dropping our own (by sid),
# reformatted as the standard inbox columns: ts \t from \t to \t text
_local_drain() { # stdout = new foreign lines; advances cursor; returns 0 even if empty
    mysid="$(session_id)"; cur="$LOCAL_DIR/cursor.$mysid"
    n="$(cat "$cur" 2>/dev/null || echo 0)"; total="$(wc -l < "$BUS" | tr -d ' ')"
    [ "$n" -gt "$total" ] && n=0
    [ "$total" -gt "$n" ] && sed -n "$((n+1)),\$p" "$BUS" | awk -F'\t' -v me="$mysid" 'BEGIN{OFS="\t"} $2!=me {print $1,$3,$4,$5}'
    printf '%s' "$total" > "$cur"
}

do_local_read() {
    mkdir -p "$LOCAL_DIR"; : >> "$BUS"; local_register
    _local_drain
}

do_local_wait() {
    mkdir -p "$LOCAL_DIR"; : >> "$BUS"; local_register
    while :; do
        out="$(_local_drain)"
        [ -n "$out" ] && { printf '%s\n' "$out"; return 0; }
        sleep 2
    done
}

do_who() {
    [ -f "$ROSTER" ] || { echo "no local sessions yet"; return 0; }
    echo "local sessions reachable on this machine:"
    awk -F'\t' '{print "  " $2}' "$ROSTER" | sort -u
}

do_new() {
    lang=fi
    case "${1:-}" in --en) lang=en ;; --fi|"") lang=fi ;; *) die "usage: portal.sh new [--fi|--en]" ;; esac
    inc="$(gen_incantation "$WORDLIST_DIR/wordlist.$lang.txt")"
    echo "status: ok"
    echo "incantation: $inc"
}

# --- dispatch ---
cmd="${1:-}"; [ "$#" -gt 0 ] && shift || true
case "$cmd" in
    new) do_new "${1:-}" ;;
    send)
        [ "$#" -ge 1 ] || die "usage: portal.sh send <text> [--from <name>] [--to <name>] [--channel <topic>] [--local]"
        s_text="$1"; shift
        s_from=""; s_to=""; s_ch=""; s_local=0
        while [ "$#" -gt 0 ]; do
            case "$1" in
                --from)    s_from="${2:-}"; shift 2 ;;
                --to)      s_to="${2:-}"; shift 2 ;;
                --channel) s_ch="${2:-}"; shift 2 ;;
                --local)   s_local=1; shift ;;
                *)         die "unknown send option: $1 (use --from / --to / --channel / --local)" ;;
            esac
        done
        if [ "$s_local" = 1 ]; then
            [ -n "$s_from" ] && PORTAL_NAME="$s_from"   # --from overrides this session's local name
            do_local_send "$s_text" "$s_to"
        else
            do_send "$s_ch" "$s_text" "$s_from" "$s_to"
        fi ;;
    open) [ "$#" -ge 1 ] || die "usage: portal.sh open <incantation>"; do_open "$1" ;;
    read)
        loc=0; ch=""
        while [ "$#" -gt 0 ]; do case "$1" in
            --local) loc=1; shift ;; --channel) ch="${2:-}"; shift 2 ;;
            *) die "usage: portal.sh read [--channel <topic>] [--local]" ;;
        esac; done
        if [ "$loc" = 1 ]; then do_local_read; else do_read "$ch"; fi ;;
    wait)
        loc=0; ch=""
        while [ "$#" -gt 0 ]; do case "$1" in
            --local) loc=1; shift ;; --channel) ch="${2:-}"; shift 2 ;;
            *) die "usage: portal.sh wait [--channel <topic>] [--local]" ;;
        esac; done
        if [ "$loc" = 1 ]; then do_local_wait; else do_wait "$ch"; fi ;;
    close) ch=""; case "${1:-}" in "") ;; --channel) ch="${2:-}" ;; *) die "usage: portal.sh close [--channel <topic>]" ;; esac; do_close "$ch" ;;
    who)    need openssl; do_who ;;
    whoami) need openssl; printf '%s\n' "$(session_name)" ;;
    _bind) [ "$#" -ge 1 ] || die "usage: _bind <inc>"; need openssl; bind_channel "$1" >/dev/null; echo "status: bound" ;;
    _topic)  [ "$#" -ge 1 ] || die "usage: _topic <inc>";  need openssl; topic_for "$1" ;;
    _enckey) [ "$#" -ge 1 ] || die "usage: _enckey <inc>"; need openssl; enc_key_for "$1" ;;
    _mackey) [ "$#" -ge 1 ] || die "usage: _mackey <inc>"; need openssl; mac_key_for "$1" ;;
    _encrypt) [ "$#" -ge 2 ] || die "usage: _encrypt <inc> <plaintext>"; need openssl; encrypt_msg "$1" "$2" ;;
    _decrypt) [ "$#" -ge 2 ] || die "usage: _decrypt <inc> <wire>"; need openssl; decrypt_msg "$1" "$2" ;;
    _msgtext) [ "$#" -ge 1 ] || die "usage: _msgtext <plaintext-json>"; printf '%s' "$1" | msg_text ;;
    *)   die "unknown command: ${cmd:-(none)}" ;;
esac
