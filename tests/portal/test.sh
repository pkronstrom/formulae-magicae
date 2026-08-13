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

# --- Task 1: new ---
INC="$(sh "$P" new | sed -n 's/^incantation: //p')"
words="$(printf '%s' "$INC" | tr '-' ' ' | wc -w | tr -d ' ')"
eq "new produces a 3-word incantation" "$words" "3"

INC_EN="$(sh "$P" new --en | sed -n 's/^incantation: //p')"
first_en="$(printf '%s' "$INC_EN" | cut -d- -f1)"
if grep -qxF "$first_en" "$ROOT/skills/portal/wordlist.en.txt"; then ok "new --en draws from the bundled English wordlist"; else no "new --en draws from the bundled English wordlist"; fi

# --- Task 2: derivation (PBKDF2 golden values for "kettu-lokaali-piano", iter=600000) ---
eq "topic derivation"   "$(sh "$P" _topic  kettu-lokaali-piano)" "portal-7c056b4092c4cf5e"
eq "enc key derivation" "$(sh "$P" _enckey kettu-lokaali-piano)" "5a326e0aa128bcc5ab0aa15e8a8f29d7baaf1b5d25fd865e3b4eb7e32c6d0430"
eq "mac key derivation" "$(sh "$P" _mackey kettu-lokaali-piano)" "2678e0f913f99e04e3e8f414e901c219a565e1a575d3aafdb4abbd58b5593dd5"

# --- Task 2b: incantation normalization (spaces/case/hyphens -> one channel) ---
CANON="$(sh "$P" _topic 'banaani-polku-gorilla')"
eq "spaces normalize to the same topic"  "$(sh "$P" _topic 'banaani polku gorilla')"   "$CANON"
eq "mixed case normalizes to the same topic" "$(sh "$P" _topic 'Banaani-Polku-Gorilla')" "$CANON"
eq "padded/underscored normalizes too"   "$(sh "$P" _topic '  banaani_polku_gorilla ')" "$CANON"
eq "normalized keys match too" "$(sh "$P" _enckey 'banaani polku gorilla')" "$(sh "$P" _enckey 'banaani-polku-gorilla')"

# --- Task 3: crypto round-trip + rejection ---
PLAIN='{"id":"abc","from":"peter","ts":1,"text":"hei Esko"}'
WIRE="$(sh "$P" _encrypt kettu-lokaali-piano "$PLAIN")"
eq "decrypt with right incantation" "$(sh "$P" _decrypt kettu-lokaali-piano "$WIRE")" "$PLAIN"

if sh "$P" _decrypt vaara-sana-tassa "$WIRE" >/dev/null 2>&1; then no "wrong incantation rejected"; else ok "wrong incantation rejected"; fi

TAMP="$(printf '%s' "$WIRE" | sed 's/.$/X/')"
if sh "$P" _decrypt kettu-lokaali-piano "$TAMP" >/dev/null 2>&1; then no "tampered ciphertext rejected"; else ok "tampered ciphertext rejected"; fi

eq "wire format is v2 with 4 dot fields" "$(printf '%s' "$WIRE" | awk -F. '{print $1, NF}')" "v2 4"

# --- Task 4: send uses the active channel after open/bind (no incantation on send) ---
# send before any open has no active channel -> must error
if PORTAL_DRYRUN=1 sh "$P" send "x" --from peter >/dev/null 2>&1; then no "send without an open channel is rejected"; else ok "send without an open channel is rejected"; fi

# bind the channel once (the open-once model); afterwards send needs no incantation
sh "$P" _bind kettu-lokaali-piano >/dev/null
WIRE_OUT="$(PORTAL_DRYRUN=1 sh "$P" send "hello there" --from peter | sed -n 's/^wire: //p')"
DEC="$(sh "$P" _decrypt kettu-lokaali-piano "$WIRE_OUT")"
case "$DEC" in
    *'"from":"peter"'*) ok "send (active channel) payload carries from" ;;
    *) no "send (active channel) payload carries from"; echo "    got: $DEC" ;;
esac
case "$DEC" in
    *'"text":"hello there"'*) ok "send (active channel) payload carries text" ;;
    *) no "send (active channel) payload carries text"; echo "    got: $DEC" ;;
esac

# --channel targets a specific channel by its (non-secret) topic, without the incantation
KTOPIC="$(sh "$P" _topic kettu-lokaali-piano)"
WIRE_CH="$(PORTAL_DRYRUN=1 sh "$P" send "via handle" --from peter --channel "$KTOPIC" | sed -n 's/^wire: //p')"
case "$(sh "$P" _decrypt kettu-lokaali-piano "$WIRE_CH")" in
    *'"text":"via handle"'*) ok "send --channel <topic> targets the channel by handle" ;;
    *) no "send --channel <topic> targets the channel by handle" ;;
esac

# --to is a directed-message hint carried in the payload
WIRE_TO="$(PORTAL_DRYRUN=1 sh "$P" send "ping" --from peter --to esko | sed -n 's/^wire: //p')"
DEC_TO="$(sh "$P" _decrypt kettu-lokaali-piano "$WIRE_TO")"
case "$DEC_TO" in
    *'"to":"esko"'*) ok "send --to carries the directed-at handle" ;;
    *) no "send --to carries the directed-at handle"; echo "    got: $DEC_TO" ;;
esac
WIRE_NOTO="$(PORTAL_DRYRUN=1 sh "$P" send "ping" --from peter | sed -n 's/^wire: //p')"
case "$(sh "$P" _decrypt kettu-lokaali-piano "$WIRE_NOTO")" in
    *'"to":""'*) ok "send without --to leaves an empty directed-at field" ;;
    *) no "send without --to leaves an empty directed-at field" ;;
esac

# oversized message is rejected loudly (ntfy.sh silently truncates >~4000 bytes)
BIG="$(head -c 5000 /dev/zero | tr '\0' x)"
if PORTAL_DRYRUN=1 sh "$P" send "$BIG" --from peter >/dev/null 2>&1; then no "oversized message is rejected"; else ok "oversized message is rejected"; fi
# a comfortably-sized message is still accepted
if PORTAL_DRYRUN=1 sh "$P" send "a normal sentence" --from peter >/dev/null 2>&1; then ok "normal-size message is accepted"; else no "normal-size message is accepted"; fi

# --- Task 5: live loopback + own-echo skip (only with PORTAL_TEST_NET=1) ---
if [ "${PORTAL_TEST_NET:-0}" = "1" ]; then
    LINC="loopback-$(openssl rand -hex 4 | sed 's/\(..\)\(..\)\(..\)\(..\)/\1-\2-\3/')"
    LTOPIC="$(sh "$P" _topic "$LINC")"; LDIR="$TMPDIR/portal.$LTOPIC"
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
FDIR="${TMPDIR:-/tmp}/portal.$FTOPIC"
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
FINC2="fake-multi-$(openssl rand -hex 4)"; FTOPIC2="$(sh "$P" _topic "$FINC2")"; FDIR2="$TMPDIR/portal.$FTOPIC2"
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
