---
name: pr-voice-review-single-file
description: Build a PR walkthrough as one self-contained HTML file — narrated, navigable, offline, no extension or server. Use for a PR review the user can keep, share, or read on a plane.
---

# pr-voice-review-single-file

Turns a pull request into **one `.html` file**. You gather, author, synthesize, assemble,
open it, and stop. The reviewer walks it at their own pace with nothing running. What
they flag comes back to you later, through the file.

## Which skill is this

| | `pr-voice-review` (sibling) | this one |
|---|---|---|
| needs | extension + bridge server + live agent | `gh`, and `ffmpeg`/Kokoro for voice |
| Q&A | live, while they walk | asynchronous, through the file |
| afterwards | nothing remains | an artifact you can mail |
| GitHub DOM | drives it | never touches it — renders the diff itself |

Reach for the sibling when they want to talk to you *while* reviewing. Reach for this one
when they want an artifact, have no extension installed, are offline, or the walkthrough
is for someone else.

## Authoring rules

Read [authoring-guidance.md](authoring-guidance.md) before authoring. It is bundled
with this skill and contains the complete narration, lens, triage, overview, story
ordering, and wrap-up rules. This skill is therefore self-contained when installed
without `pr-voice-review`; the sibling remains useful for live, conversational reviews.

## Two questions, each asked where it can be answered

**Do not combine these.** They are different kinds of decision: the lens changes *what
you write*, so it has to be settled before authoring; audio is a *cost*, and the cost is
unknowable until the narration exists. Asked together up front, the second half is a
guess for both of you.

**Question 1 — before anything else. The lens.**

> Which lens? **guided** — every point, gated at each · **focused** — close read on the
> risky files · **architect** — every file from the system level.

**Question 2 — after triage and authoring, before synthesis. Voice or silent.**
By then `render.narration_estimate` knows the real numbers, so quote them:

```python
est = render.narration_estimate(segs, overhead=len(shell_html))
```

> That is 41 files and about 14 minutes of narration — roughly 90 seconds to build,
> and 3.4 MB. Silent drops it to 380 KB and builds instantly. Voice, or silent?

Ask it every time, even when the numbers are small ("12 chunks, about 15 seconds") —
predictability is worth more than the saved prompt, and the reviewer may want silence
for reasons that have nothing to do with size.

**Skip question 2 entirely** when there is nothing to decide: Kokoro is missing (say so
once and build silent), or the projection is over budget (offer silent or a narrower
scope instead — that is not a preference, it is a limit).

**`synth_seconds` is the cold figure.** Anything already in the audio cache renders
instantly, so quoting it on a rebuild overstates the cost — say "most of this is cached"
when the run is a re-author rather than a first build.

## Build pipeline

Modules sit beside this file. `render.py` is pure, `build.py` does the file IO and the
`shell` command, `synth.py` is the only slow part. The API you need is quoted in the steps
below — reading the modules to find it is three minutes you do not have to spend.

```python
import sys; sys.path.insert(0, "<this skill's dir>")
import render, build
```

**1. Resolve and fetch.** PR from argument, URL, or current branch. **Start the fetch
before asking question 1** — it is the one part of the build that overlaps cleanly with
the reviewer's own thinking time.

```bash
gh api "repos/$OWNER/$REPO/pulls/$NUM" > "$D/pr.json"
gh api --paginate "repos/$OWNER/$REPO/pulls/$NUM/files" > "$D/files.json"
gh api --paginate "repos/$OWNER/$REPO/pulls/$NUM/comments" > "$D/inline.json"
```

Use the **scope rules** in `authoring-guidance.md` — which URL shape means which diff,
and that patches must be scoped along with the file list. There is no `/prepare` to
POST to, so resolve base and head yourself and pass them to `gh api`. Say the file count
out loud; it is the reviewer's first check that you are both looking at the same thing.

Read the PR body. The "why" is rarely in the diff, and the overview leads with it.

**2. Triage and structure — write `plan.json`.** Tier every file by risk, not line count.
Write the overview and one `role` line per file. Order as a story. `slice` groups the files
into one authoring agent each — two or three per slice, crucial files alone, **numbered in
reading order** so the first slice covers what the reviewer reaches first.

```json
{"pr": {"owner": "o", "repo": "r", "num": 716},
 "checkout": "/path/to/a/checkout",
 "audioPending": true,
 "overview": {"role": "**The problem:** … **The fix:** …",
              "speech": "…", "notes": [{"text": "…", "speech": "…"}]},
 "files": [{"path": "src/a.ts", "tier": "crucial", "role": "…", "slice": 1},
           {"path": "src/b.ts", "tier": "normal",  "role": "…", "slice": 2}]}
```

This file is nothing but the editorial decisions — every other field in the content block
is derived. **Do not hand-write an assembly script**, and do not read `render.py`,
`build.py` or `template.html` to work out how: everything you need is in this file, and
rediscovering it from source cost three minutes of a measured run.

**3. Ship the shell now — one command.**

```bash
python "<skill dir>/build.py" shell --plan "$D/plan.json" \
  --pr "$D/pr.json" --files "$D/files.json" \
  --out "$OUT" --slices "$D/slices"
```

It parses the patches, checks the plan covers exactly the fetched file list (a file you
forgot is a file the reviewer never hears about), writes the shell, and writes one brief
per slice into `$D/slices/NN.json` for step 4. `tier` is `crucial | normal | skim | ignore`;
`speech` and `notes` on the file segments start empty and are filled by the fan-out.

Then `open` it. Authoring and synthesis take minutes on a large PR; the reviewer starts
reading immediately, and can flag and comment from the first second. That is safe only
because of the block split below.

**Set `audioPending: True` on a voice build's shell, and drop it in step 7.** The shell
still speaks — silence would waste the window it exists to create — but with the flag the
browser voice is presented as a **stand-in**: a "preview voice" badge in the transport, a
banner saying the real narration is still rendering, and the current card drawn dashed.
Without the flag that same substitution is silent and unlabelled, which is what makes a
perfectly good build sound broken.

The stand-in picks the best voice the machine has rather than the default — en-GB first to
match the Kokoro voice, then premium/enhanced, then local. Never set the flag on a
genuinely silent build: there the browser voice is the product, not a placeholder.

**4. Author the notes.** One background subagent per slice file.

**Dispatch every one of them in a single message, and name the slice file — never paste a
patch into a prompt.** Both halves of that were measured on a 29-file PR: nine agents sent
as nine messages, each carrying its patches inline, took **3m12s of dispatch alone** for
~66 KB of prompt the model had to type out, against ~1m30s of actual authoring. The
largest prompt also arrived truncated, and told its own subagent to go find the rest.
Sent as one message with paths, the same fan-out dispatches in about twenty seconds and
every agent gets a complete patch.

Each prompt is short, and its bulk is the ear-writing rules, not the diff:

> Author narration for the files in `$D/slices/03.json` — read it first; it has each
> file's path, tier, role and full patch. A checkout is at `<checkout>` if you want
> surrounding context, but the patch is authoritative and the PR has already been fetched
> — do not run `gh` or re-derive the PR. Follow *Narration* in
> `<this skill's dir>/authoring-guidance.md`. Return only the segment JSON: `[{"path", "speech", "notes":
> [{"text", "speech", "from", "to"}]}]`.

That last clause matters: the one agent that ignored it spent 100 of its 124 seconds
re-running `gh pr view` and `git log` for data already sitting in its brief. They return
segment JSON keyed by path; you merge it into the plan's segments.

**5. Merge, estimate, then ask question 2 — before synthesizing.** The shell on disk is
the state; read it back rather than keeping a copy in your head.

```python
content = build.extract_block(out.read_text(), "review-content")
for seg in content["segments"]:                  # merge by path; None is the overview
    seg.update(authored.get(seg["path"], {}))
est = render.narration_estimate(content["segments"], overhead=out.stat().st_size)
```

Quote `est` and ask voice or silent (above). Over ~5 MB there is nothing to ask: say so
and offer silent or a narrower scope. Either way this happens *before* the Kokoro pass,
because discovering it afterwards wastes the most expensive step in the build.

**6. Render audio** (voice only).

```bash
uv run --no-project --quiet --with kokoro-onnx --with soundfile \
  python "<skill dir>/synth.py" segments.json audio.json \
  ~/.models/tts/kokoro/kokoro-v1.0.fp16.onnx ~/.models/tts/kokoro/voices-v1.0.bin
```

**7. Rewrite in place, and tell them to reload.**

```python
content["audio"] = json.load(open("audio.json"))
content.pop("audioPending", None)                 # the stand-in voice steps aside
build.write_review(out, content, template=None)   # None = preserve their feedback
```

Output path: `~/.local/state/pr-voice-review/<owner>-<repo>-<num>.html`. Report it and
its size — never write into the repo.

## Two blocks, two owners

```html
<script id="review-content"  type="application/json">   <!-- yours -->
<script id="review-feedback" type="application/json">   <!-- theirs -->
```

`build.write_review(..., template=None)` replaces **content only** and carries feedback
across verbatim. Regenerating the whole file destroys everything typed during the staged
window — that is a real bug this design already had once, and
`test_rewrite_preserves_feedback_typed_into_the_shell` is what keeps it dead.

Feedback items:

```json
{"id": "...", "kind": "comment|flag|question|answer", "i": 3, "c": 1,
 "path": "src/resolver.py", "from": 40, "to": 42, "text": "...",
 "replyTo": "f1", "at": 1786800000}
```

`kind` replaces the `byUser`/`flag` distinction `collectNotes()` carried in the sibling:
**comment** is their remark, **flag** marks one of *your* observations as wanting depth,
**question** expects an answer, **answer** is yours with `replyTo` set. `path`/`from`/`to`
are what an inline review comment gets filed against; null on the overview.

**Escaping is a requirement, not a check.** `render.json_for_block` escapes every `<`;
any PR touching HTML, JSX or a template carries the bytes that terminate a script element.
The renderer builds every diff row with `textContent`, never `innerHTML`.

## Audio, measured on this machine

| | realtime | 12 min of narration |
|---|---|---|
| `tts.sh` per chunk | 3.8× | ~190 s |
| one process, model loaded once | 9.0–9.3× | ~80 s |
| **3 workers, threads capped** | **~12×** | **~60 s** |
| **cache hit (text unchanged)** | **—** | **instant** |

Dropping the sibling's `server.py` drops its warm Kokoro worker, and the ~0.9 s model load
is **per chunk** — sixty short observations waste a minute re-loading it. That is why
synthesis batches.

**The cache matters more than the rate.** Chunks are keyed by a hash of their text plus
the voice settings, so a rebuild only renders what you actually rewrote. Measured on a
four-file PR: 9.1 s cold, **0.09 s** for an identical rebuild, 2.0 s after editing one
observation of twelve. Since the staged build re-runs synthesis on every rewrite, this is
the single largest saving available — far larger than the synthesis rate.

Two things measured and rejected, so nobody re-derives them:

- **CoreML is slower**, not faster. It supports 650 of the model's 2389 nodes, so the graph
  splits into 109 partitions and the boundary crossings cost more than the acceleration
  saves — 0.96× the CPU rate on Apple silicon.
- **Uncapped parallel workers are slower than one.** Each tries to take every core: four
  uncapped workers measured 9.0× against 9.7× for a single process. Capped to
  `cores / workers` they reach 11–13×. The gain is real but modest, ~1.3×.

MP3 24 kbps mono, 24 kHz: **3.1 KB/s**, ~3.0 MB inlined for a twelve-minute walk. Chosen
over Opus (2.0 MB) because Opus needs a codec-support branch for older Safari, and this
skill's premise is minimal moving parts. "Mailable" means the recipient saves it and opens
it in a browser — mail clients do not run JavaScript in a preview, whatever the codec.

No Kokoro and they asked for voice? Say so once, build silent, and the file falls back to
the browser's `speechSynthesis`. Never download weights unasked.

## The round trip back

They press **Copy for agent** and paste into your terminal — the primary path, because it
works from any copy of the file with no path to guess. Or they **Save** and you read it:

```python
fb = build.extract_block(Path(saved).read_text(), "review-feedback")
```

**Read the whole block, never `head -n`.** singlefile's "`head -60` shows the entire state"
is true of a small app; here the feedback sits below megabytes of base64.

Then answer the questions, dig where flagged, and submit **one** review:

```bash
gh api "repos/$OWNER/$REPO/pulls/$NUM/reviews" --input review.json
```

`event` is `COMMENT` unless they explicitly say approve or request changes. Write answers
back as `kind: "answer"` entries so the file holds the whole exchange.

## The optional listener — offer it once, never require it

`listen.sh` is a ten-line `nc` loop with no dependencies. When it is running, the
file's **Send** delivers the feedback straight to it instead of via the clipboard, so
you learn the reviewer is done without being told. **Everything works without it**, and
a file built with it degrades silently when it is not running.

Offer it once, when you build, and take no for an answer:

> Want me to leave a listener running so your feedback comes back automatically?
> It is optional — Copy for agent works either way.

```bash
"<skill dir>/listen.sh" 8799 "$D/inbox" &     # then poll "$D/inbox/latest.json"
```

Opting in means adding one key to the content block **before** assembling:

```python
content["listen"] = {"port": 8799}
```

Verified working from a `file://` page (opaque origin) into `127.0.0.1`: the reply
carries `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Private-Network: true`,
and the page posts `text/plain` so the request stays "simple" and never triggers a
preflight `OPTIONS` that a one-line `nc` loop could not answer.

Two honest costs. A file built with `listen` but opened with nothing running logs one
`ERR_CONNECTION_REFUSED` — caught in code, but the browser records the failed request
anyway; a file built without the key never probes and never logs it. And Chrome's
private-network rules keep tightening, so re-verify before relying on it.

**Do not bake `listen` into a file you are sending to someone else.** The port is theirs,
not yours, and it will never answer.

## Failure handling

| Problem | Response |
|---|---|
| Kokoro missing or weights absent | build silent, `speechSynthesis` fallback, say so once |
| ffmpeg missing | force silent and say why |
| `gh` unauthenticated or PR not found | stop and say what is needed |
| `patch` absent (binary, oversized) | stub row, move on |
| Projected size over ~5 MB | stop **before** synthesizing; offer silent or narrower scope |

## Definition of done

singlefile §7 applies in full, plus:

```bash
grep -c '</script' review.html    # must equal the real closing-tag count — 3 in the template
```

Opens from `file://`; a diff containing `</script>` renders intact; a comment containing
`</script>` survives save-and-reopen; **feedback entered before the step-7 rewrite survives
it**; audio plays only after the Start gesture; legible with audio off; usable at phone
width.

One console message is expected and is not yours: `Unsafe attempt to load URL file://…
'file:' URLs are treated as unique security origins.` Chrome emits it for any local page —
verified against a three-line control page with no audio and no resources. Anything else
in the console is real.

## Maintenance

`render.py` and `build.py` are covered by the repository's
`tests/test_prvsf_render.py` and `tests/test_prvsf_build.py`. The template's browser
behavior is not reachable from pytest — the tests assert its structure (no
`type="module"`, no external references, no `innerHTML` assignment, and the control
hooks exist), while the rest is covered by the hand-checklist above.
