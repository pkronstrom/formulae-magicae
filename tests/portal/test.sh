#!/bin/sh
# portal.sh test suite. Run: sh tests/portal/test.sh
# Lives outside skills/ so it is never bundled with the plugin or synced into a tool's skills dir.
# Network loopback test runs only when PORTAL_TEST_NET=1.
set -eu
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$HERE/../.." && pwd)"
P="$ROOT/skills/portal/portal.sh"
# Isolate all portal state (active pointer, channel dirs) under a per-run TMPDIR so
# tests don't see leftovers from previous runs or real usage. We delete nothing —
# the OS reaps it (consistent with the skill's own no-rm policy).
export TMPDIR="${TMPDIR:-/tmp}/portal-test-$$"
mkdir -p "$TMPDIR"
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   - $1"; }
no()  { fail=$((fail+1)); echo "NOT  - $1"; }
eq()  { if [ "$2" = "$3" ]; then ok "$1"; else no "$1"; echo "    expected: [$3]"; echo "    got:      [$2]"; fi; }

STATE="$(sh "$P" _statedir)"

# --- Task 1: new (fi 6 words = 52.1 bits, en 5 words = 51.7 bits) ---
INC="$(sh "$P" new | sed -n 's/^incantation: //p')"
words="$(printf '%s' "$INC" | tr '-' ' ' | wc -w | tr -d ' ')"
eq "new produces a 6-word Finnish incantation" "$words" "6"

INC_EN="$(sh "$P" new --en | sed -n 's/^incantation: //p')"
eq "new --en produces a 5-word incantation" "$(printf '%s' "$INC_EN" | tr '-' ' ' | wc -w | tr -d ' ')" "5"
first_en="$(printf '%s' "$INC_EN" | cut -d- -f1)"
if grep -qxF "$first_en" "$ROOT/skills/portal/wordlist.en.txt"; then ok "new --en draws from the bundled English wordlist"; else no "new --en draws from the bundled English wordlist"; fi

# --- Task 2: derivation (PBKDF2 golden values, iter=600000; cross-checked with
# python3 hashlib.pbkdf2_hmac('sha256', inc, b'portal_t'|'portal_e'|'portal_m', 600000)) ---
K=kettu-aasi-piano-banaani-polku-gorilla
eq "topic derivation"   "$(sh "$P" _topic  $K)" "portal-c04a35eeea7d6c64"
eq "enc key derivation" "$(sh "$P" _enckey $K)" "3a45733d5168be7b3945b60e73a7f4b58a7ae8be13c5daf716ea137879c04328"
eq "mac key derivation" "$(sh "$P" _mackey $K)" "39aaa5bcc4a54bdae4005f38223cf38d48ea76ab4e07090d99e93f01f4766d37"

# --- Task 2a: weak (old 3-word) incantations are rejected on open/bind ---
OUT="$(sh "$P" _bind kettu-aasi-piano 2>&1 || true)"
case "$OUT" in *"at least 5"*) ok "3-word incantation is rejected with a clear message" ;; *) no "3-word incantation is rejected with a clear message"; echo "    got: $OUT" ;; esac
OUT="$(sh "$P" open kettu-aasi-piano 2>&1 || true)"
case "$OUT" in *"at least 5"*) ok "open rejects a 3-word incantation before streaming" ;; *) no "open rejects a 3-word incantation before streaming"; echo "    got: $OUT" ;; esac

# --- Task 2b: incantation normalization (spaces/case/hyphens -> one channel) ---
CANON="$(sh "$P" _topic 'banaani-polku-gorilla')"
eq "spaces normalize to the same topic"  "$(sh "$P" _topic 'banaani polku gorilla')"   "$CANON"
eq "mixed case normalizes to the same topic" "$(sh "$P" _topic 'Banaani-Polku-Gorilla')" "$CANON"
eq "padded/underscored normalizes too"   "$(sh "$P" _topic '  banaani_polku_gorilla ')" "$CANON"
eq "normalized keys match too" "$(sh "$P" _enckey 'banaani polku gorilla')" "$(sh "$P" _enckey 'banaani-polku-gorilla')"

# --- Task 3: crypto round-trip + rejection ---
PLAIN='{"id":"abc","from":"peter","ts":1,"text":"hei Esko"}'
WIRE="$(sh "$P" _encrypt $K "$PLAIN")"
eq "decrypt with right incantation" "$(sh "$P" _decrypt $K "$WIRE")" "$PLAIN"

if sh "$P" _decrypt vaara-sana-tassa "$WIRE" >/dev/null 2>&1; then no "wrong incantation rejected"; else ok "wrong incantation rejected"; fi

TAMP="$(printf '%s' "$WIRE" | sed 's/.$/X/')"
if sh "$P" _decrypt $K "$TAMP" >/dev/null 2>&1; then no "tampered ciphertext rejected"; else ok "tampered ciphertext rejected"; fi

eq "wire format is v3 with 4 dot fields" "$(printf '%s' "$WIRE" | awk -F. '{print $1, NF}')" "v3 4"
W2="$(sh "$P" _encrypt $K "$PLAIN")"
if [ "$W2" != "$WIRE" ]; then ok "random IV: same plaintext encrypts differently"; else no "random IV: same plaintext encrypts differently"; fi
V2="v2.${WIRE#v3.}"
if sh "$P" _decrypt $K "$V2" >/dev/null 2>&1; then no "v2 wire is rejected"; else ok "v2 wire is rejected"; fi

# HMAC is computed without putting the key on argv; it must equal openssl's -hmac.
MK="$(sh "$P" _mackey $K)"
IVCT="$(printf '%s' "$WIRE" | cut -d. -f2,3 | tr -d .)"
eq "shell HMAC matches openssl dgst -hmac" "$(printf '%s' "$WIRE" | cut -d. -f4)" "$(printf '%s' "$IVCT" | openssl dgst -sha256 -hmac "$MK" | awk '{print $NF}')"

# LibreSSL <-> OpenSSL 3 interop (macOS ships LibreSSL at /usr/bin/openssl)
if [ -x /usr/bin/openssl ] && [ "$(command -v openssl)" != /usr/bin/openssl ]; then
    WL="$(PATH=/usr/bin:/bin sh "$P" _encrypt $K "$PLAIN")"
    eq "system openssl -> PATH openssl interop" "$(sh "$P" _decrypt $K "$WL")" "$PLAIN"
    eq "PATH openssl -> system openssl interop" "$(PATH=/usr/bin:/bin sh "$P" _decrypt $K "$WIRE")" "$PLAIN"
fi

# --- Task 3b: keys never appear in any child process's argv ---
# Shim every external tool the crypto path runs; each logs its argv, then execs the real one.
SHIM="$TMPDIR/shim"; mkdir -p "$SHIM"; ARGLOG="$TMPDIR/argv.log"; : > "$ARGLOG"
for t in openssl awk sed tr cut cat od wc date curl; do
    real="$(command -v "$t" 2>/dev/null)" || continue
    printf '#!/bin/sh\nprintf "%%s\\n" "%s $*" >> "%s"\nexec "%s" "$@"\n' "$t" "$ARGLOG" "$real" > "$SHIM/$t"
    chmod +x "$SHIM/$t"
done
EK="$(sh "$P" _enckey $K)"
PATH="$SHIM:$PATH" CLAUDE_CODE_SESSION_ID=argv-probe sh "$P" _bind $K >/dev/null
AW="$(PATH="$SHIM:$PATH" CLAUDE_CODE_SESSION_ID=argv-probe PORTAL_DRYRUN=1 sh "$P" send "argv probe" --from peter | sed -n 's/^wire: //p')"
PATH="$SHIM:$PATH" sh "$P" _decrypt $K "$AW" >/dev/null
if [ -s "$ARGLOG" ] && grep -q 'openssl enc' "$ARGLOG"; then ok "argv shim captured the openssl calls"; else no "argv shim captured the openssl calls"; fi
if grep -qe "$EK" -e "$MK" "$ARGLOG"; then no "enc/mac keys never appear in argv"; grep -e "$EK" -e "$MK" "$ARGLOG" | head -3; else ok "enc/mac keys never appear in argv"; fi
if grep -q 'kettu-aasi' "$ARGLOG"; then no "incantation never appears in a child's argv"; else ok "incantation never appears in a child's argv"; fi

# --- Task 4: send uses the active channel after open/bind (no incantation on send) ---
# send before any open has no active channel -> must error
if PORTAL_DRYRUN=1 sh "$P" send "x" --from peter >/dev/null 2>&1; then no "send without an open channel is rejected"; else ok "send without an open channel is rejected"; fi

# bind the channel once (the open-once model); afterwards send needs no incantation
sh "$P" _bind $K >/dev/null
WIRE_OUT="$(PORTAL_DRYRUN=1 sh "$P" send "hello there" --from peter | sed -n 's/^wire: //p')"
DEC="$(sh "$P" _decrypt $K "$WIRE_OUT")"
case "$DEC" in
    *'"from":"peter"'*) ok "send (active channel) payload carries from" ;;
    *) no "send (active channel) payload carries from"; echo "    got: $DEC" ;;
esac
case "$DEC" in
    *'"text":"hello there"'*) ok "send (active channel) payload carries text" ;;
    *) no "send (active channel) payload carries text"; echo "    got: $DEC" ;;
esac

# --channel targets a specific channel by its (non-secret) topic, without the incantation
KTOPIC="$(sh "$P" _topic $K)"
WIRE_CH="$(PORTAL_DRYRUN=1 sh "$P" send "via handle" --from peter --channel "$KTOPIC" | sed -n 's/^wire: //p')"
case "$(sh "$P" _decrypt $K "$WIRE_CH")" in
    *'"text":"via handle"'*) ok "send --channel <topic> targets the channel by handle" ;;
    *) no "send --channel <topic> targets the channel by handle" ;;
esac

# --to is a directed-message hint carried in the payload
WIRE_TO="$(PORTAL_DRYRUN=1 sh "$P" send "ping" --from peter --to esko | sed -n 's/^wire: //p')"
DEC_TO="$(sh "$P" _decrypt $K "$WIRE_TO")"
case "$DEC_TO" in
    *'"to":"esko"'*) ok "send --to carries the directed-at handle" ;;
    *) no "send --to carries the directed-at handle"; echo "    got: $DEC_TO" ;;
esac
WIRE_NOTO="$(PORTAL_DRYRUN=1 sh "$P" send "ping" --from peter | sed -n 's/^wire: //p')"
case "$(sh "$P" _decrypt $K "$WIRE_NOTO")" in
    *'"to":""'*) ok "send without --to leaves an empty directed-at field" ;;
    *) no "send without --to leaves an empty directed-at field" ;;
esac

# oversized message is rejected loudly (ntfy.sh silently truncates >~4000 bytes)
BIG="$(head -c 5000 /dev/zero | tr '\0' x)"
if PORTAL_DRYRUN=1 sh "$P" send "$BIG" --from peter >/dev/null 2>&1; then no "oversized message is rejected"; else ok "oversized message is rejected"; fi
# a comfortably-sized message is still accepted
if PORTAL_DRYRUN=1 sh "$P" send "a normal sentence" --from peter >/dev/null 2>&1; then ok "normal-size message is accepted"; else no "normal-size message is accepted"; fi

# --- Task 4b: state dir is private and ownership-checked ---
eq "state dir lives under TMPDIR/portal" "$STATE" "$TMPDIR/portal"
eq "state dir is mode 0700" "$(ls -ld "$STATE" | cut -c1-10)" "drwx------"
if [ "$(id -u)" != 0 ]; then
    OUT="$(PORTAL_STATE_DIR=/ sh "$P" read 2>&1 || true)"
    case "$OUT" in *"not owned by you"*) ok "refuses a state dir owned by another user" ;; *) no "refuses a state dir owned by another user"; echo "    got: $OUT" ;; esac
fi
ln -s "$STATE" "$TMPDIR/linked"
OUT="$(PORTAL_STATE_DIR="$TMPDIR/linked" sh "$P" read 2>&1 || true)"
case "$OUT" in *"symlink"*) ok "refuses a symlinked state dir" ;; *) no "refuses a symlinked state dir"; echo "    got: $OUT" ;; esac
OUT="$(env -u TMPDIR -u XDG_RUNTIME_DIR -u PORTAL_STATE_DIR HOME="$TMPDIR/home" sh "$P" _statedir)"
eq "no TMPDIR/XDG -> falls back to \$HOME/.cache/portal, not /tmp" "$OUT" "$TMPDIR/home/.cache/portal"

# --- Task 5: live loopback + own-echo skip (only with PORTAL_TEST_NET=1) ---
if [ "${PORTAL_TEST_NET:-0}" = "1" ]; then
    LINC="loopback-$(openssl rand -hex 4 | sed 's/\(..\)\(..\)\(..\)\(..\)/\1-\2-\3-\4/')"
    LTOPIC="$(sh "$P" _topic "$LINC")"; LDIR="$STATE/portal.$LTOPIC"
    SID_ME="sid-me-$$"; SID_OTHER="sid-other-$$"
    # streamer runs as session SID_ME
    CLAUDE_CODE_SESSION_ID="$SID_ME" sh "$P" open "$LINC" >/dev/null 2>&1 &
    OPID=$!
    sleep 3
    # a message from ANOTHER session (its active channel is its own now, so address by --channel)
    CLAUDE_CODE_SESSION_ID="$SID_OTHER" sh "$P" send 'reply {ok} say "hi"' --from tester --to esko --channel "$LTOPIC" >/dev/null
    # our OWN send (same session as the streamer) must NOT echo into our inbox
    CLAUDE_CODE_SESSION_ID="$SID_ME" sh "$P" send 'this is my own echo' --from me --channel "$LTOPIC" >/dev/null
    got=""
    i=0
    while [ "$i" -lt 12 ]; do
        if grep -q 'reply {ok} say "hi"' "$LDIR/inbox.log" 2>/dev/null; then got="yes"; break; fi
        i=$((i+1)); sleep 1
    done
    sleep 2  # give the own-echo every chance to (wrongly) show up
    if grep -q 'this is my own echo' "$LDIR/inbox.log" 2>/dev/null; then ownecho="yes"; else ownecho="no"; fi
    # foreign line should still carry the --to esko hint in its 'to' column
    if grep -q "	esko	" "$LDIR/inbox.log" 2>/dev/null; then tohint="yes"; else tohint="no"; fi
    CLAUDE_CODE_SESSION_ID="$SID_ME" sh "$P" close >/dev/null 2>&1 || true
    kill "$OPID" 2>/dev/null || true
    eq "foreign message arrives decrypted in inbox" "$got" "yes"
    eq "directed --to hint lands in the inbox line" "$tohint" "yes"
    eq "own send is NOT echoed back into our inbox" "$ownecho" "no"
else
    ok "skipped network loopback (set PORTAL_TEST_NET=1 to run it)"
fi

# --- Task 6: read/wait/close against a hand-seeded inbox, addressed by --channel (no network) ---
# Unique fake channel per run -> fresh dir, no stale read.offset, and nothing to clean up
# (the test deletes NOTHING; the OS reaps $TMPDIR).
FINC="fake-$(openssl rand -hex 4)-channel"
FTOPIC="$(sh "$P" _topic "$FINC")"
FDIR="$STATE/portal.$FTOPIC"
mkdir -p "$FDIR"; : > "$FDIR/inbox.log"
printf '1700000000\tesko\t\tfirst\n' >> "$FDIR/inbox.log"
eq "read returns new line"        "$(sh "$P" read --channel "$FTOPIC")" "$(printf '1700000000\tesko\t\tfirst')"
eq "read returns nothing second time" "$(sh "$P" read --channel "$FTOPIC")" ""
printf '1700000001\tesko\t\tsecond\n' >> "$FDIR/inbox.log"
eq "read returns only the new line" "$(sh "$P" read --channel "$FTOPIC")" "$(printf '1700000001\tesko\t\tsecond')"
( sleep 1; printf '1700000002\tesko\t\tthird\n' >> "$FDIR/inbox.log" ) &
eq "wait blocks then returns the appended line" "$(sh "$P" wait --channel "$FTOPIC")" "$(printf '1700000002\tesko\t\tthird')"
sh "$P" close --channel "$FTOPIC" >/dev/null 2>&1; ok "close exits cleanly (idempotent)"

# close kills ALL of THIS session's registered streamers (per-session, multi-streamer robustness)
FINC2="fake-multi-$(openssl rand -hex 4)"; FTOPIC2="$(sh "$P" _topic "$FINC2")"; FDIR2="$STATE/portal.$FTOPIC2"
CSID="close-test-$$"; mkdir -p "$FDIR2"
sleep 30 & MP1=$!; sleep 30 & MP2=$!
printf '%s\n%s\n' "$MP1" "$MP2" > "$FDIR2/listeners.$CSID"
CLAUDE_CODE_SESSION_ID="$CSID" sh "$P" close --channel "$FTOPIC2" >/dev/null 2>&1
sleep 1
if kill -0 "$MP1" 2>/dev/null || kill -0 "$MP2" 2>/dev/null; then
    no "close kills every registered streamer (this session)"; kill "$MP1" "$MP2" 2>/dev/null || true
else
    ok "close kills every registered streamer (this session)"
fi

# --- Task 6b: inbox text extraction survives quotes and braces (offline) ---
PT='{"id":"x","from":"a","ts":1,"text":"reply {ok} say \"hi\""}'
eq "msg_text extracts text with quotes and braces" "$(sh "$P" _msgtext "$PT")" 'reply {ok} say "hi"'
PT2='{"id":"y","from":"b","ts":2,"text":"trailing brace}"}'
eq "msg_text handles text ending in a brace" "$(sh "$P" _msgtext "$PT2")" 'trailing brace}'

# --- Task 7: local mode (shared bus, no crypto, sid echo-skip, addressing) ---
A_SID="loc-a-$$"; B_SID="loc-b-$$"
A_NAME="$(CLAUDE_CODE_SESSION_ID=$A_SID sh "$P" whoami)"
B_NAME="$(CLAUDE_CODE_SESSION_ID=$B_SID sh "$P" whoami)"
if [ -n "$A_NAME" ] && [ "$A_NAME" != "$B_NAME" ]; then ok "sessions get distinct magical local names"; else no "sessions get distinct magical local names"; fi
CLAUDE_CODE_SESSION_ID=$A_SID sh "$P" send "broadcast hi" --local >/dev/null
CLAUDE_CODE_SESSION_ID=$B_SID sh "$P" send "for A only" --local --to "$A_NAME" >/dev/null
B_VIEW="$(CLAUDE_CODE_SESSION_ID=$B_SID sh "$P" read --local)"
case "$B_VIEW" in *"broadcast hi"*) ok "local: B sees A's broadcast" ;; *) no "local: B sees A's broadcast"; echo "    got: $B_VIEW" ;; esac
case "$B_VIEW" in *"for A only"*) no "local: B must NOT see its own send" ;; *) ok "local: own send is skipped (echo-skip by sid)" ;; esac
A_VIEW="$(CLAUDE_CODE_SESSION_ID=$A_SID sh "$P" read --local)"
case "$A_VIEW" in *"	$A_NAME	for A only"*) ok "local: directed --to lands addressed to the target" ;; *) no "local: directed --to lands addressed to the target"; echo "    got: $A_VIEW" ;; esac
WHO="$(sh "$P" who)"
case "$WHO" in *"$A_NAME"*) a_in=1 ;; *) a_in=0 ;; esac
case "$WHO" in *"$B_NAME"*) b_in=1 ;; *) b_in=0 ;; esac
if [ "$a_in" = 1 ] && [ "$b_in" = 1 ]; then ok "local: who lists both sessions"; else no "local: who lists both sessions"; fi

echo "---"
echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
