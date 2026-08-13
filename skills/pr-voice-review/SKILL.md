---
name: pr-voice-review
description: Walk the user through a pull request out loud, file by file, with the browser following along on GitHub's Files changed view. Use when the user wants a PR explained by voice, wants to review or understand a PR together, says "talk me through this PR", "read me this PR", or wants a spoken walkthrough of changes.
---

# pr-voice-review

Explains a pull request **out loud**, file by file, prioritized so important changes get
attention and boring ones get one line. The user browses a fully-prepared review at their
own pace; you speak wherever they are and answer what they ask.

## The API, inline — never read `overlay.js`

**Segment:** `{path, sha, tier, stat, role, speech, notes:[{from,to,text,speech}]}`
· `tier`: crucial|normal|skim|ignore · `role`: one sentence on the file's part in the PR
· omit `sha` for the overview · note `text` is md-lite: `` `code` ``, `**bold**`
· optional `svg` renders a chart.

**Narration is per observation, not per file.** `seg.speech` is the file's own
explanation; **each note carries its own `speech`** for the thing it points at. The
walk pauses between them — one chunk of audio, its lines lit in the diff, then a gate.
That is the unit the user advances through, so write one note per observation and
never pack two points into one. A note with no `speech` is a silent card (user
comments, Q&A).

### Writing the narration

**`seg.speech` must stand alone: what this file does, and why it is in this PR.**
Under `architect`, and under `focused` on a non-crucial file, it is the *only* thing
spoken about that file — so "This is the resolver." is a failure; that is a label, not
an explanation. Say what the file's job is in the system, where it sits in the flow,
then what this change does to that. Two to four sentences under `guided`, where notes
carry the detail; 60–90 words when it is carrying the whole file on its own.

**A small change in a large file needs the file explained first.** Six lines moved in
a nine-hundred-line file: the diff tells the reviewer *nothing* about what they are
looking at. When the change is small relative to the file, **open the file itself, not
just the patch** (`gh api "repos/$OWNER/$REPO/contents/<path>?ref=<head>" --jq .content
| base64 -d`, or read it from the checkout) and lead with what it is for. Then the
change lands somewhere. This is the single biggest gap in a walkthrough written from
patches alone.

**Budgets, because a listener cannot skim.** A `guided` beat is **≤ 40 words**
(~15 seconds); a file-level `speech` carrying a whole file on its own is **60–90**. An
answer or a dig-in result is **≤ 80 spoken**. Measured on a real
session, narration drifted to a mean of 88 words with one unbroken 329-word chunk —
over two minutes on a single gate. If it will not fit, it is two observations, not one
long one.

**Conclusion first.** The finding goes in the first sentence; the reasoning that
supports it comes after, and only if it earns its place. On paper a reader skips ahead
to the point. By ear they cannot, so a chunk that opens "let me start with the part I
got right" has already spent the listener's attention before saying anything.

**The card and the voice are not the same text.** The eye re-reads and skims; the ear
gets one pass. Put the precise detail — identifiers, exact line references, the careful
qualification — in `text`. Put the point in `speech`. Writing one string and using it
for both makes the card thin and the narration long.

**Translate, do not transliterate.** The rule against reading code aloud means *name
the concept*, not spell the token phonetically. "app dot env" and "NEXT underscore
PUBLIC" are worse than the identifiers they replace; say "the env file" and "the public
build variables". The exact name is already on the card in front of them.

| Call | Does |
|---|---|
| `__prv.fill(i, {role, notes, speech, text, from, to})` | merge ONE segment; keeps position and the user's own notes |
| `__prv.load(segs[, at])` | replace all; stays on the same path |
| `__prv.go(i[, c])` · `__prv.i` · `__prv.c` · `__prv.segments` | navigate / read state |
| `__prv.goBeat(i, c)` | move to one observation — no scroll when it is the same file |
| `__prv.addAnswer(i, q, text)` | fill the pending card a typed question created |
| `__prv.collectNotes()` | the user's own notes **plus any of yours they flagged**, each with `byUser` and `flag` |
| `__prv.flagged()` | just the flagged subset — the specific points they want you to dig into |
| `__prv.auto` | true = the page self-drives: plays, pauses, advances, highlights, and you do nothing. False = the user advances observation by observation, and it still speaks each one |
| `__prv.silent` | true = **nothing is spoken at all** — they are reading. Navigation, highlighting and the transcript all still work. Never speak over this, including answers: put them in the card and say so in the terminal |
| `__prv.setDepth(d)` · `__prv.depth` | `guided` \| `focused` \| `architect` — the narration lens. Set it once, before POSTing segments |
| `__prv.here()` | the block under the cursor: `{path, from, to, ni}` — what a typed comment or question is about |
| `__prv.setScript(on)` | the transcript pane (**T** on the bar): the current observation's text with each word lit as it is spoken. User-facing; you never need to call it |
| `__prv.setRate(r)` · `__prv.rate` | narration speed, cycling 1 / 1.25 / 1.5 / 1.75 / 2 on the **1×** button. Playback-only — nothing is re-synthesised, and the voice keeps its pitch |
| `__prv.finish()` | the page calls this itself on Done — swaps the bar for a completion card and returns `{files, comments, flagged}` |
| `__prv.setStatus(t)` | update the line inside that card while you wrap up |
| `__prv.unmount()` | remove the bar — only once the user is done with it |

**Never interrogate the page for state** — one call answers everything:
`curl -s 127.0.0.1:8765/status` → `{total, authored, voiced, rendered, renderedIdx,
chunks, renderedChunks, pendingIdx, synthPending, synthErrors, queuedEvents, warm}`.
Every response also carries **`pendingUser`** — unread input from the overlay. If it is
ever non-zero, `/drain` before doing anything else (see the event loop).
`chunks[i]` is how many gates file `i` has; `renderedChunks` holds the `"i:c"` keys
whose audio exists. The bar shows the user the same progress on its own
("⏳ preparing — 3 of 19 files ready"), so you never narrate setup.

**Events** from `/wait`: `position{i,c,played,why}` · `say{text,i,c,from,to}` · `comment{i,c,from,to,text}` ·
`repeat` · `stop` · `auto{on}` · `segmentready{i,chunks}` ·
`syntherror{i,c,why}` · `notrendered{i}` · `prepared{...}` · `persisted` · `end` ·
`TIMEOUT`.

## First-run setup — detect, offer, never assume

Check these when the session starts; each degrades gracefully, so **offer the fix once
and continue with the fallback** rather than blocking:

| Prerequisite | Detect | One-time fix (user does it) | Without it |
|---|---|---|---|
| Kokoro voice weights (~205MB) | `tts.sh --check` | `tts.sh --setup` — **ask before downloading** | macOS `say` voice |
| Browser extension | `window.__prv?.v` | chrome://extensions → enable **Developer mode** → **Load unpacked** → `<skill-dir>/extension` | paste `overlay.min.js` (~45s) or bookmarklet |
| **Stale extension** (installed but old) | `__prv.v` **less than** the version in `overlay.js` | chrome://extensions → **↻ reload** on the extension → reload the PR tab | old features only; do not paste over it — the stale script re-injects on next navigation |
| Bridge server | `curl -s 127.0.0.1:8765/ping` | none — you start it yourself (§1); needs only python3 stdlib | agent-side audio, slower stop/mute |
| `gh` authenticated | `gh auth status` | `gh auth login` | hard stop — say so |

Use the `extension` folder inside this installed skill. After any overlay version bump,
the fix is ↻ reload on the unpacked extension followed by a PR-tab reload.

## Division of labour

| | Owns | Speed |
|---|---|---|
| **page** (overlay) | navigation, highlighting, note cards, add/remove | instant |
| **you** | review content, voice, answers, digging, submission | round trips |
| **gh** | all diff/comment truth | network |

The user drives; you react. Never re-introduce an agent round trip on Next.

## 0. The lens — the one question you do ask

Before authoring, ask which lens to narrate through. It is the only question in this
skill, because it changes what you write, and it is **fixed for the session**:

> Which lens? **guided** — every point, gated at each, the close read ·
> **focused** — close read on the risky files, higher lens elsewhere ·
> **architect** — every file explained from the system level; you read the lines
> yourself and comment as you go. Default is focused.

Then `__prv.setDepth("guided" | "focused" | "architect")` **before** you POST segments.

**`architect` is not `guided` with the detail deleted.** It is the same file described
from higher up, and it is fully narrated — you still talk the reviewer through every
file, just at a different altitude. Get this wrong and the mode is useless: a
truncated intro tells them nothing they could not read from the filename.

| | guided says | architect says |
|---|---|---|
| unit | one observation, anchored to lines | one file, anchored to the system |
| content | what changed here and why it matters | what this file is for, where it sits in the flow, what this change does to that |
| the reviewer | follows along, listening | reads the lines themselves, listening for orientation |
| length | ≤ 40 words a beat, several beats | 60–90 words, once per file |

What varies:

| Lens | `seg.speech` | note cards (`text`) | `note.speech` |
|---|---|---|---|
| `guided` | the file's account of itself | every observation | **every file** |
| `focused` | same | every observation | **crucial files only** |
| `architect` | same, and it carries the whole file | **only what is worth stopping on — 0 to 3 a file** | **none** |

**Cards follow the altitude too.** Under `architect` the reviewer is skimming the diff
themselves; seven cards a file is the thing they were trying to escape. Raise only the
points a senior reviewer would actually stop on — a risk, a decision worth questioning,
something surprising. A file where nothing stands out gets **no cards at all**, and that
is a useful signal in itself. Under `guided` and `focused` the cards stay exhaustive,
because there the reviewer is following you rather than reading ahead.

The page enforces the filter as well, so a review cached from a `guided` session can be
re-walked at `architect` without re-authoring. But when you know the lens up front,
**skip writing `note.speech` you will not use** — that is the synthesis you save.

## 1. Start — no interrogation

Resolve the PR (argument, URL, or current branch); keep `OWNER`, `REPO`, `NUM`, and any
**scope** the URL carries (see §2 — a `/changes/<sha>` link is not the whole PR).
**Ask nothing else.** Auto-detect the rest:

- `window.__prv?.v` matches the version in `overlay.js` → overlay is live (extension or
  earlier session), cost zero.
- Browser tools work but no `__prv` → inject `overlay.min.js` once (~45s — mention it).
  Offer the extension for next time: `extension/` in this skill's dir, chrome://extensions
  → Developer mode → Load unpacked. `bookmarklet.txt` is the zero-install fallback
  (untested against GitHub CSP — verify the first time).
- No browser at all → terminal mode: print each file's anchor URL
  (`#diff-<sha256 of path>`); on request `open`/`xdg-open` them.

**One call starts everything.** Do this FIRST, before any other check — `/prepare`
runs server-side while you get on with the browser and triage:

```bash
"<skill dir>/bootstrap.sh" "$OWNER" "$REPO" "$NUM" "$D"
```

It reuses a live server of the right version or replaces a stale one, fires `/prepare`,
and reports tts/gh/browser status in one shot. Do not read `overlay.js` — the API you
need is the cheatsheet below.

<details><summary>manual equivalent</summary>

```bash
python3 "<skill dir>/server.py" --port 8765 --audio-dir "$D/audio" --pidfile "$D/server.pid" --tts "$TTS"
# the server owns: intake (/prepare), narration synthesis, segment storage, cache (/persist)
# it chimes (Tink) the moment the panel is navigable — `--chime ''` disables, `--chime PATH` swaps
```

</details> With the extension installed, the overlay
links to it automatically: audio then plays **in the page** (stop/mute/repeat instant)
and events arrive at the server instead of the in-page queue. **Leave it running** when
the review ends — see teardown.

Voice: resolve `tts.sh` from `$TTS_PATH`, then from `PATH`, then from the adjacent
`tts` skill when this is part of the complete Formulae Magicae bundle; otherwise use
text-only mode (announce it once). Set `TTS_PATH` to any executable compatible with
the Formulae Magicae `tts.sh` interface to provide narration to an isolated install.
Missing weights → offer `--setup`, never download unasked.

## 2. Intake — one fire-and-forget call; the server does the rest

```bash
curl -s -X POST 127.0.0.1:8765/prepare -d "{\"owner\":\"$OWNER\",\"repo\":\"$REPO\",\"num\":$NUM}"
```

**Scope it to whatever the reviewer is actually looking at.** A GitHub PR has more
than one diff view, and they show different file counts. Reviewing all nineteen files
when the page in front of them shows seven is not a smaller mistake than the reverse —
they will not be able to find what you are talking about.

| What they gave you | Scope to send |
|---|---|
| `…/pull/714` or `…/pull/714/files` | *(nothing — the whole PR)* |
| `…/pull/714/changes/<sha>` | `"scope": {"commit": "<sha>"}` — that one commit's diff |
| `…/pull/714/files/<a>..<b>` | `"scope": {"base": "<a>", "head": "<b>"}` |
| "just what changed since I last looked" | find their last review's `commit_id` (`gh api repos/O/R/pulls/N/reviews`) and send `{"base": "<that>", "head": "<head>"}` |

```bash
curl -s -X POST 127.0.0.1:8765/prepare \
  -d "{\"owner\":\"$OWNER\",\"repo\":\"$REPO\",\"num\":$NUM,\"scope\":{\"commit\":\"$SHA\"}}"
```

Scoping moves the **patches** as well as the file list, which is the part that matters:
on a commit view GitHub shows that commit's diff, so line numbers and observations drawn
from the PR's cumulative patch would point at lines the reviewer cannot see. The
`prepared` event reports `fileCount` and `scope` — **say the count out loud** ("seven
files in this commit"), because it is the reviewer's first check that you are looking at
the same thing they are. Scoped reviews cache separately, so the same PR at commit level
and whole-PR level never collide.

Returns immediately. The server runs the three `gh` calls, writes `pr.json` /
`inline.json` / `patches.json` into its data dir, computes every file's sha256 anchor,
and **checks the per-PR cache** (key: owner-repo-num-headsha, plus a scope tag when scoped). Completion arrives as a
`prepared` event on your normal `/wait` loop: file list with anchors and stats,
`cached` flag (true → segments and audio are already loaded — skip authoring entirely),
and the data paths. Use the setup gap for the voice/browser checks.

Read per-file patches from `patches.json` with `jq`, never refetch. (`--json comments`
is issue comments; `reviews` is summary bodies; per-line threads exist only in
`inline.json` — verified 2 vs 25 on a real PR.) Read the PR body — the "why" is rarely
in the diff. `patch` is absent for binaries and oversized files; say so when you hit one.

### The ticket, when there is one

**The PR says what; the ticket says why.** A PR body that only describes the change
leaves you reconstructing the problem from the diff, which is the one half of the
overview a listener cannot reconstruct for themselves. When the work came from Linear,
that half is already written down.

**Detect** while `/prepare` is still running. First hit wins:

| Order | Where | Pattern |
|---|---|---|
| 1 | PR body | a Linear issue URL — `linear.app/<org>/issue/<ID>/…` |
| 2 | PR body | a bare magic-word ID — `\b[A-Z][A-Z0-9]{1,9}-\d+\b` |
| 3 | `headRefName` in `pr.json` | Linear's branch convention, `user/abc-123-slug` |

The branch lowercases the ID, so match case-insensitively and uppercase it before
fetching.

**Fetch** only if a reference was found *and* Linear MCP is actually connected — load
`mcp__linear__get_issue` through ToolSearch, and if it is not there, **skip in
silence**. Take the title, the description, and acceptance criteria if the issue has
them.

**Then use it in exactly two places**, and nowhere else:

- **Segment 0's problem card** is written from the ticket rather than inferred from the
  diff. Cite it in one breath — "the ticket asks for…" — so the reviewer knows where the
  framing came from. The *fix* card still comes from the PR body and the diff: the
  ticket describes the goal, not the solution that was chosen.
- **The approach subagent** (§3) gets the ticket text as its definition of what was
  wanted.

**Do not ask.** No "shall I pull the ticket?" — the lens is still the only question this
skill asks. Do not give the ticket its own card either; it informs the narration, it
does not become a second thing to walk through.

**Every failure is silent.** No reference, no MCP, a 404, a wrong ID that resolves to
nothing — all of them fall back to today's behavior without a word to the user. A
walkthrough that opens by explaining what it could not fetch has spent the reviewer's
attention on your plumbing.

## 3. Prepare the review — progressively; the panel comes first

**Target: panel visible with all files and roles in under a minute; full notes stream in
behind it.** Authoring the deep notes is the dominant cost (measured in minutes) — never
make the user wait behind it.

**Cache is server-owned.** The `prepared` event's `cached: true` means the server
already restored segments and audio — the panel is live, narration ready, zero authoring.
Stale head sha → normal authoring, then persist again at wrap-up.

**Miss → three passes, shipping after each:**

1. **Structure** (~seconds): triage from stats, write only the overview + one `role`
   line per file. POST to `/segments` — the panel is now up, every file navigable,
   tiers and roles visible. Speak the overview. Read the **PR body** before writing it:
   the problem-and-fix story is the one thing you cannot reconstruct from stats, and it
   is what the overview leads with.
2. **First crucial file** (~30s): author its notes and speech yourself, POST
   `/segment/1`. The user can start walking immediately.
3. **Fan out the rest — in story order.** Slice by *reading order*, not arbitrarily:
   the first subagent gets segments 2–4 (what the user reaches next), the second 5–7,
   and so on. Dispatch the early slices first, and tell each to author its own files in
   order too. With more files than parallel capacity the tail waits — it should be the
   tail the user reaches last, never the next thing they click. Skim/ignore tiers go in
   one final slice; they are one line each and nobody is waiting on them.

   Spawn background subagents (they run in background by default) — one per 2–3 files,
   each given: the file paths, its slice of `patches.json`, the
   ear-writing rules, and this instruction:

   > Author notes and a `speech` script for each assigned file, then
   > `curl -s -X POST 127.0.0.1:8765/segment/<i> -d '<json>'` for each. Do not
   > touch the browser. Return only a one-line summary.

   `/segment/<i>` merges per-segment, so parallel writers never clobber each other;
   the server renders narration as each lands, and **the page pulls updates itself**
   (`autoRefresh`) — no browser round trip from you or them.

   Meanwhile **you stay on the event loop**: speaking, answering, digging. A `position`
   on a not-yet-authored file → author that one yourself immediately, out of order.

### The approach card — is this the simplest thing that works?

The walkthrough explains what the code does. It should also say, once, whether this was
the right *shape* of solution: proportionate to what was asked, or heavier than it
needed to be. A reviewer forming that judgement while listening is doing your job for
you.

**One more background subagent, dispatched with the pass-3 fan-out.** Hand it the ticket
text (§2) or the PR body when there is none, all of `patches.json`, and this brief:

> Judge the PR's approach against what was actually asked for. Question whether each
> piece needs to exist at all. Compare it to one or two concretely simpler alternatives.
> Watch for speculative abstraction, dead flexibility, reinvented standard library, and
> redundant defensive code. **If you cannot write down what the smaller version would
> actually be, you have no finding** — return the one-line proportionate verdict
> instead. Then POST one note to
> `curl -s -X POST 127.0.0.1:8765/segment/0 -d '<json>'`. Do not touch the browser.
> Return only a one-line summary.

`/segment/0` merges, so it lands beside the overview you already wrote rather than
replacing it, and the server renders its audio as it arrives.

**Verdict first, in the first sentence** — the conclusion-first rule is at its most
load-bearing here. A proportionate PR gets one line ("proportionate to the ask; nothing
to cut") and stops; that is a useful answer, not a wasted card. A negative verdict names
the simpler alternative concretely and lists what would come out.

**It arrives after you have spoken the overview, and you do not speak it.** The opening
overview is the only unsolicited narration in this skill (§5) and this card is not part
of it. One terminal line at a natural seam is the entire announcement — "approach card
is in: heavier than the ticket needs, two candidates to cut". They play it or read it
when they want it.

**A negative verdict is triage material.** Carry it into the wrap-up menu (§6) alongside
the flags: "this could be simpler" is a legitimate review comment, and just as
legitimately a *dig* or a *drop*.

**The risk worth naming:** a confident "this is over-engineered" about complexity that
is load-bearing is worse than saying nothing. That is what the "name the smaller
version or you have no finding" rule in the brief is for — keep it in.

**At wrap-up, persist** (fire-and-forget; server copies segments + audio to the cache):

```bash
curl -s -X POST 127.0.0.1:8765/persist -d "{\"cacheKey\":\"<from the prepared event>\"}"
```

Triage every file from stats into **crucial / normal / skim / ignore** — by risk, not
line count (six lines of auth outrank a 400-line rename).

Note budgets (quality per tier, applied during pass 3):

- **crucial + normal**: one or more notes per file, each with a line range when it has a
  natural anchor. Multiple observations = multiple notes, not one blob.
- **skim**: one line each, no patch read unless something looks off.
- **ignore**: the role line is the whole coverage.

**Segment 0 is the overview — no file selected.** It is the only part of the review
written for someone who does **not** already know this codebase, and it comes in two
halves. Get the first half wrong and the rest is a briefing for a stranger.

**First: the story, in plain language.** The opening two cards, in this order:

1. **The problem.** What was broken, missing, or painful *before* this PR — stated so
   someone who has never opened this repo follows it. What went wrong in the world,
   not which function returned the wrong value. **If you fetched a ticket (§2), this
   card is written from it** — that is what the ticket is for. Without one, infer the
   problem from the PR body and the diff as before.
2. **The fix.** The shape of the approach in a sentence or two: what it now does
   instead, and why that resolves the problem. The idea, not the file list.

**Write those two without a single file path, identifier, or symbol name.** That
constraint is the whole point — the moment you reach for `bootstrap-sfdb-master-data`
you have started briefing a colleague instead of explaining a change. Names come
immediately after, in the triage cards, where they belong. If the PR body explains the
why, lead with that; a PR that only says *what* is exactly where a reader needs you to
supply the *why* from the diff.

**Then: the triage**, for the reviewer they are about to become — which files carry the
risk, the accepted trade-offs, open review threads, and what to watch for. This is the
half that tends to swallow the whole overview; keep it below the story, never in front
of it.

When the shape warrants it, add a small hand-written inline `svg` sketch of the flow (a
few boxes and arrows — never a diagram library). Speak the whole thing as the opening
before any file.

**Order segments as a story, not a ranking.** Tier decides how much you say; the
*narrative* decides the sequence: start at the most abstract point — where the feature
enters (the UI a user touches, or the API surface) — then follow the call chain downward
(wiring → core logic → shared rules → persistence/sync), and end with the tests that
prove each layer. Each file's `role` line should read as the next sentence of that story.
A listener should always know *why this file follows the previous one*.

Print the plan table but **do not stop for approval** — Back and Next are the reordering
mechanism. If you cap coverage, say what you dropped.

Anchors, one shell call for all files:

```bash
jq -r '.files[].path' "$D/pr.json" | while read -r p; do
  printf '%s %s\n' "$(printf '%s' "$p" | shasum -a 256 | cut -d' ' -f1)" "$p"
done
```

## 4. Load and speak

**Server mode (preferred):** POST the segments from bash — the page pulls them itself
through the bridge, including after any tab reload:

```bash
curl -s -X POST 127.0.0.1:8765/segments --data @"$D/segments.json"
```

**Fallback (no bridge):** one browser call — `__prv.load([...])` — and incremental
`__prv.fill()` for later passes.

**Pre-rendered audio played by the page is the DEFAULT and only normal path.**
You speaking is a fallback for two cases only: an ad-hoc answer (a question, an aside),
or a `position` event that came back `played:false` *and* `/status` shows no pending
synthesis for it (i.e. the render genuinely failed). Never speak a segment merely
because its audio is not ready yet — the page retries and plays it the moment it lands,
and your voice arriving late on top of it is worse than a short silence.

**You never synthesize narration — the server does.** Put the ear-written script on
the segment (`speech`) and on each note (`note.speech`), then just POST; the server's
background workers render one `seg-<i>-<c>.mp3` per observation as texts arrive or
change, and the page retries briefly while a fresh one is still rendering. Your only
remaining `tts.sh` use is ad-hoc speech — Q&A answers and asides — via `--async`.
Audio lands in `$D/audio/` under `/tmp`, which the OS sweeps; the per-PR cache is
what persists it.

Speak the overview **once**, when the panel first comes up — the single time you narrate
without being asked, because the user started a voice review and this is it beginning.
After that the pre-rendered audio carries every word and you speak only when asked:

```bash
"$TTS" --async "Twelve files, three worth real attention. First: the resolver."
```

**Continue gates are the page's job now, not yours.** Splitting a long file across
line ranges is exactly what per-note `speech` does: each note is one chunk, its lines
light when that chunk starts, and the walk parks at the gate until the user advances
(or rolls straight on if they have autoplay on). You do not schedule highlights, you
do not `wait()` between chunks, and `playTimeline` is no longer the mechanism for
this — anchor the prose to notes and the page handles the rest.

Everything spoken is also printed in the terminal. Write for the ear (rules in the `tts`
skill): shape not syntax, 2–5 sentences, signpost lists.

## 5. React

**Server mode (preferred — check `/ping` first).** There are exactly **two** wait
commands. Copy them verbatim. **Never invent an `ms` value** — a made-up middling
number (30000, 60000) is the one mistake this loop keeps making, and it produces a
wake-up notification at the user every 30 seconds for the whole review.

```bash
# A. AUTHORING STILL PENDING — foreground, short tick, react instantly
curl -s "http://127.0.0.1:8765/wait?ms=1500"
#   TIMEOUT  -> author or synthesize exactly ONE file, then loop. Never more —
#               a user click must never wait behind a batch of authoring.
#   an event -> handle it FIRST; authoring resumes on the next tick.

# B. EVERYTHING AUTHORED — background push channel. NO ms. NO --max-time.
curl -s "http://127.0.0.1:8765/wait"               # run_in_background: true
```

Command B carries no number **by design**: the server's own default is the 60-minute
push window, so there is nothing for you to get wrong. Adding `ms` to it is always a
mistake; adding `--max-time` is worse, since curl would then cut the poll short and
re-wake on its own schedule.

**The background long-poll is the push channel.** Launch it and end your turn — you
are genuinely free, and the harness re-invokes you the moment the curl exits with an
event (or after an hour of quiet; just relaunch it, still with no `ms`). This is why no
MCP layer is needed: an MCP call would block a turn exactly like a foreground curl,
and the harness's background-task notification already delivers async wake-ups.

**Why the window size matters so much.** Every return — event *or* TIMEOUT — fires a
"background command completed" notification at the user. One an hour is invisible;
one every 30 seconds buries the session. The short tick belongs to the **foreground**
loop only, while authoring remains. On a TIMEOUT wake with nothing queued, re-arm and
say nothing — never narrate the tick.

**RE-ARM BEFORE YOU WORK, NOT AFTER.** This is the one ordering rule that matters.
You are only listening while a wait is in flight, and the obvious loop — wake, work,
re-arm — leaves the channel deaf for the whole stretch you are digging, answering, or
running greps. That is precisely when the user clicks things, and they end up asking
"did you get this?" about input that was buffered the entire time. So:

```
wake  ->  handle the event  ->  /drain the rest  ->  RE-ARM  ->  then do the work
```

Re-arming costs nothing: it is a background task, it runs while you work, and a burst
that lands mid-work simply wakes you again when you finish.

**Bursts are safe by construction** — `/wait` hands out one event and everything else
buffers in the server queue — with two rules:

1. **Exactly one wait in flight, ever.** Two concurrent waits would split a burst
   between them.
2. **Handle, then `/drain`, then re-arm.** Rapid-fire clicks get batched into one
   working turn instead of one wake per event, and FIFO order is preserved.

**Every JSON response carries `pendingUser`** — how many unread events came from the
overlay. This is the safety net for the window ordering cannot close: if *any* call you
make while working comes back with `pendingUser > 0`, the user did something and you
have not looked. `/drain` and handle it before carrying on. **Never end a turn with a
non-zero `pendingUser`** — that is the "did you get this?" failure, and it is now
detectable from every single response.

(`pendingEvents` alongside it is the raw queue depth, including your own
`segmentready`/`syntherror` traffic. Watch `pendingUser`; a 19-file publish makes the
raw count meaningless.)

Speech latency is scheduling, not synthesis: while authoring remains, stay on the
foreground short tick so clicks never queue behind a batch of work; once authored,
switch to the background long-poll and stop burning turns entirely. `position` events
carry `played`: when `true` the page already played the cached narration and you do
**nothing** except top up the audio window; when `false`, speak.

**Fallback (no server/extension):** loop on
`const q = __prv.drain(); q.length ? q : await __prv.wait(38000)` — **never pass wait()
more than 40s: the browser tool kills evaluate calls at 45s** (verified live).

| Event | Response |
|---|---|
| `position {i, c, played, why}` | **Do nothing. Never speak on a position event** — see the rule below. `why` says why nothing played: `muted` and `autoplay-off` are the user's own choices, `no-bridge` is the fallback path, and only `not-rendered` / `play-failed` are faults — and even those go to the **terminal**, one line, not to the voice. `c` is which observation they are parked on; you rarely need it, but it answers "what is this bit". |
| `say {text, i, c, from, to}` | The panel stops narration before sending, so you are free to speak. **Echo the question verbatim in the terminal**, answer (voice + terminal), the question already pinned itself as a pending card — fill it: `__prv.addAnswer(i, question, condensedAnswer)`. It carries the block they were on, so resolve "this"/"that" against `from`–`to` rather than guessing. |
| `comment {i, c, from, to, text}` | already stored as a card in the page — acknowledge in terminal only. **`from`/`to` is the block they were looking at**, and it is what the inline review comment gets filed against at wrap-up; null only on the overview or a file's intro. |
| `flag {i, ni, on, text}` | they marked one of **your** blocks as wanting more. `on:true` → **queue it** (see the backlog protocol below), acknowledge in one terminal line, and carry on. `on:false` → cleared, drop it from the queue. |
| `play` (or `repeat`) | the page plays it itself when audio exists; you only get this if it does not — speak live |
| `stop` | you rarely see this — the page calls `POST /stop` itself, which kills your playback too. If you do get it, `tts.sh --stop`. |
| `auto {on}` | **obsolete** — the page runs hands-free itself (plays, pauses, advances, highlights). Do nothing. |
| `syntherror {i, c, why}` | one observation's narration failed after retries — speak that chunk live (`--async`) and continue; the file's other gates are unaffected |
| `notrendered {i}` | GitHub lazy-loaded it — click the file in the sidebar tree, continue |
| `end` | **Start wrap-up immediately — never wait to be asked for a summary.** The panel has already replaced itself with a completion card, so the user is watching a status line that says you are working; leaving it there while you sit idle is the failure. Go straight to §6: settle outstanding flags, present the triage, submit. Keep `__prv.setStatus("…")` current as you go ("digging into 2 flagged points", "submitting 4 comments", "submitted ✓"). |
| `TIMEOUT` | say nothing, wait again |

### Never speak unless you were asked

**The pre-rendered audio is the narration. You are not.** `tts.sh` is for exactly one
thing: answering something the user just asked you — a typed question, or a request to
say something again. Nothing else.

**The one exception is the opening overview** (§4), spoken once when the panel first
comes up, because the user started a voice review and that is it beginning. It is
unsolicited by design and it is the *only* thing that is. After it, this rule is
absolute — including for every file, every note, and every `position` event.

In particular, **never narrate a `position` event.** Moving through the review is not a
request to be spoken to. `played:false` is not a fault to cover for: it usually means
`muted` or `autoplay-off`, which are the user *choosing silence*, and talking over that
choice is the worst thing this skill can do. Even a real `not-rendered` gets one line in
the terminal, never a live reading — the page retries on its own and the moment it
succeeds you would be talking over it.

This is not hypothetical. In one session the same overview was spoken three times,
once an hour apart, each triggered by nothing but the user clicking around the panel
with autoplay off.

**Respect `__prv.silent` before every utterance** — it means they chose to read, so an
answer goes to the card and the terminal, never to `tts.sh`. The terminal is always a second input —
anything typed there works exactly as if it came from the bar.

### The backlog: flags and comments are a queue, not an interrupt

A user walking a real PR flags things and types comments **while you are still
working**, several files ahead of where you have caught up. Chasing each one the
instant it lands is wrong twice over: it derails the walkthrough's story, and the
answer arrives while they are listening to something else, so two things compete for
the same attention.

**Resolve in the gaps, surface at the boundaries.**

1. **On arrival:** acknowledge in **one terminal line** — never speak it, never break
   the narration. `flagged()` is your queue; the page already stores it, so there is
   nothing for you to track.
2. **Work it in your dead time.** You re-arm the poll before working (see above), so
   the stretch between events is genuinely free. Dig there. Resolving early costs the
   user nothing — it is *talking over them* that costs, not thinking early.
3. **Update silently.** `fill(i, ...)` the deepened note. The card updates in place;
   they can press play on that block whenever they want to hear it.
4. **Report at a natural seam** — when they cross to a new file, or ask. One line:
   "two flags from `Dockerfile.dev` resolved — cards updated." Not the content;
   they will read or play it if they care.
5. **Never let the queue outlive the walk.** Anything still open at `end` is settled
   in wrap-up.

**Fan out only when it pays.** A flag usually leans on context you just built, and a
subagent starts cold — dispatching a single flag loses more than it saves. Spawn
`segment-author`-style subagents only when **3 or more** are queued **and** they span
different files, one per file, each handed the path, the line range, and the note text.
One or two, or several in the same file: do them yourself.

**Never skip the queue to answer.** A typed question (`say`) is different — that is the
user waiting on you right now. Answer it immediately, then return to the backlog.

**Whole-file deep dives arrive as questions now.** There is no "Dig in" button: it
overlapped the per-point flag, and every reviewer on a UX panel flagged the pair as one
intent split across two controls. A `say` like "go deeper on this file" or "what else
is in here?" is that request — treat it as a full-file pass and `fill()` the results.

**Fully hands-free:** Claude Code has native push-to-talk (`/voice`, 2.1.191+) — the
user holds space and speaks; it arrives as ordinary terminal input. Mention it once for
a long walkthrough. Nothing in this skill needs to change to support it.

## 6. Wrap-up

`__prv.collectNotes()` returns the user's surviving note cards (removals already
applied — the page owned that state, you never tracked it) **plus any of your blocks
they flagged**.

**Settle the backlog first.** `__prv.flagged()` lists every flagged point; anything you
never got room to dig into, do now. A flag the user set and never heard back on is the
one thing this walkthrough must not lose.

**Then sort what each one becomes — do not assume they are all review comments.**
A flag means "worth more attention", which is often but not always "worth telling the
author". Lay the list out and ask once, offering the whole menu rather than a yes/no:

> Six things outstanding — four you flagged, two you wrote.
> For each: **comment** on the PR · **dig** (I investigate and propose a fix) ·
> **drop**. Same for all, or shall I go through them?

- **comment** — becomes an inline review comment at its line range.
- **dig** — you investigate properly and come back with a diagnosis and a concrete
  proposed change. This is the one worth offering explicitly; a reviewer often flags
  something because they want it *understood*, not because they want the author
  chased. If it turns into a real fix, say plainly whether it belongs in this PR or a
  follow-up.
- **drop** — resolved during the walk, or decided not to matter. Say so; do not
  silently bin it.

Take a blanket answer if they give one. Their own typed comments default to **comment**
— they wrote them for the author — but a flag has no default, which is exactly why this
gets asked.

Show the collected notes, confirm, submit as **one** review:

```bash
gh api "repos/$OWNER/$REPO/pulls/$NUM/reviews" --input review.json
```

`event` is `COMMENT` unless the user explicitly says approve / request changes. Then a
spoken close and a written recap.

**Leave the panel to the user.** The completion card carries a **Close panel** button;
do not `unmount()` behind their back while they are still reading the cards or copying
something out. Set the status to its final state ("submitted — 4 comments on the PR")
and stop. Unmount only if they ask, or if you are starting a different review.

### Teardown — mostly, do nothing

**Do not kill the server at wrap-up.** Everything here cleans up after itself, and
killing it costs the next review a cold start — the exact thing the warm worker exists
to prevent.

| What | Size | Who cleans it |
|---|---|---|
| narration audio | small | the session dir lives under `/tmp`; the OS sweeps it (measured: already 0 B) |
| the kokoro workers | **~525 MB each, up to 3** | **the server**, 10 min after the last synthesis — and `warm_synth` respawns the pool on demand |
| the server itself | a few MB | itself, after 2 h idle |
| the per-PR cache | ~20 MB a review | itself: newest 20 entries, nothing over 30 days |
| the audio cache | a few MB | unbounded today — clips keyed by narration text |

**Narration is cached by its own text**, not by the review it belongs to. The per-PR cache
is keyed on the head sha, so one new commit invalidated every clip even though nearly all
the narration was word-for-word identical; now pushing a commit only re-renders the chunks
whose text actually changed. Measured on six chunks: 3.3 s cold, **0.00 s** cached.

Synthesis also runs a small pool (up to 3) rather than one process, with intra-op threads
capped to `cores / workers`. Uncapped workers are *slower* than a single one — each tries
to take every core — and CoreML is slower still, since it supports 650 of the model's 2389
nodes and the graph splits into 109 partitions.

The cache under `~/.local/state/pr-voice-review/` is **deliberately** persistent — it is
what makes re-opening a PR instant instead of a full re-author. Never clear it as
housekeeping. If the user asks how, tell them the path and let them delete it.

Kill the server only when the user asks, or when you need it on different settings (a
different port, `--tts`, or `--chime`): `kill "$(cat "$D/server.pid")"`.

## Failure handling

| Problem | Response |
|---|---|
| No audio | text-only, announce once |
| No browser | terminal mode with anchor URLs |
| Highlight returns `why: "diff markup changed"` | GitHub shipped new DOM — keep going without highlights, note it |
| `patch` missing | say so, move on |
| No `gh` auth / PR not found | stop and say what is needed |

## Maintenance

`overlay.js` is the single source; run `./build.sh` after editing it to regenerate
`overlay.min.js`, `extension/`, and `bookmarklet.txt`. Bump `PRV.v` on any API change.
