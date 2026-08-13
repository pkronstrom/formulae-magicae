---
name: transcribe-media
description: YouTube and video transcripts plus key frames — pull a video, YouTube link, talk, or podcast into context as a timestamped transcript with screenshots, so you know what it showed and not just what it said. USE WHENEVER THE USER PASTES A YOUTUBE OR VIDEO URL — including a bare link with no instructions at all, which always means "pull this and tell me what is in it". Also use when asked what a video or YouTube video covers, to summarize or transcribe a talk, tutorial, or podcast, or to get the diagrams, UIs, graphs, or on-screen code out of a video. Handles YouTube, TED, Apple Podcasts, conference sites, and any other site yt-dlp supports.
---

# transcribe-media

Turns a video into a folder you can read: a timestamped transcript, a budgeted set of
key frames, and contact sheets that let you see the whole video for a few thousand
tokens.

**A bare URL is a request.** If the user pastes a video link and says nothing else,
run this skill, then tell them what the video contains — do not ask what they want
first, and do not just describe the link.

Resolve this skill's installed directory through the host's skill catalog, then run:

```bash
"<skill-dir>/transcribe.sh" "https://www.youtube.com/watch?v=..."
```

It prints the output directory. A default run takes about 35 seconds for a 20-minute
video and writes:

```
.media/<id>-<slug>/
  index.md          # read this first
  transcript.md     # deduped, [mm:ss]-anchored, clickable timestamps
  transcript.vtt    # raw
  meta.json
  frames/0552.jpg   # full resolution, named by timestamp
  sheets/grid_01.jpg
```

## Reading protocol

Follow this order. It is the difference between a few thousand tokens and forty
thousand.

1. **Read `index.md`.** Metadata, chapter outline, and one row per frame pairing a
   timestamp with the line spoken at that moment.
2. **Read the contact sheets.** Nine timestamped frames per image — three sheets
   usually cover an entire video.
3. **Read individual files in `frames/` only where detail matters** — a diagram you
   need to explain, code on screen, a UI you are reproducing.
4. **Read `transcript.md`** for the words, or grep it for a specific claim.

Do not read every frame in `frames/`. The sheets exist so you do not have to.

## Options

| Flag | Effect |
|---|---|
| `--no-frames` | transcript only, no video download (~4s) |
| `--frames N` | frame budget (default `1.2 × minutes`, clamped to 12–40) |
| `--height N` | max video height (default 720; 480 above 45 min) |
| `--asr`, `--stt`, `--parakeet` | force local transcription instead of YouTube captions |
| `--lang CODE` | caption language (default `en`) |
| `--out MODE` | `project` (default), `library`, `obsidian`, or an explicit path |
| `--keep-video` | keep the video file (deleted after extraction otherwise) |
| `--force` | re-process a video that was already digested |

`--out library` writes to `$TRANSCRIBE_MEDIA_LIBRARY` (default `~/Videos/media-library`),
so the same URL resolves instantly from any project.

`--out obsidian` writes to `$OBSIDIAN_VAULT/Media` (default vault
`~/Documents/obsidian/Vault`), one folder per item. That is the agreed home for
transcripts — use it whenever the user asks for a transcript "to Obsidian" or "to the
vault", without asking where.

Re-running an already-digested URL reuses the existing directory and downloads
nothing.

## Requirements

Everything ships inside this skill directory, including `app_template.html` for the
HTML summary — nothing is fetched at build time. External tools:

| Tool | Needed for | If missing |
|---|---|---|
| `yt-dlp` | everything | hard failure |
| `ffmpeg` + `ffprobe` | frames, duration recovery | hard failure |
| `python3` | all processing | hard failure |
| Pillow | contact sheets | frames still extracted, no sheets |
| `uv`/`uvx` | local transcription | falls back, see below |

macOS: `brew install yt-dlp ffmpeg uv`.

### Local transcription

Only reached when a video has no captions, or when `--asr` is passed. The first
available engine wins; `TRANSCRIBE_MEDIA_ASR` pins one explicitly.

| Engine | Install | Notes |
|---|---|---|
| `parakeet` (default) | `brew install uv` | Apple Silicon, ~72× realtime. Verified. |
| `mlx-whisper` | `brew install uv` | Apple Silicon. Verified at 8m23s in 15.9s. |
| `whisper` | `pip install -U openai-whisper` | Any platform, slower. Code path present, not verified here. |

With `uv` installed there is nothing else to do — the engine and its model download on
first use. **parakeet's model is ~2.3 GB and downloads once**; the script says so
before it starts, since otherwise the first run looks like a hang. Override the whisper
model with `TRANSCRIBE_MEDIA_WHISPER_MODEL` (default `whisper-large-v3-turbo`; use
`mlx-community/whisper-tiny` for a fast, rough pass).

**If no engine is available** the run does not die: it prints install instructions and
continues with frames only, so you still get the visual half. It only fails outright
when `--no-frames` leaves nothing to produce.

## How frames get chosen

Scene-cut detection does not work on screencasts, animated explainers, or talks —
measured against an 18:40 video, it found seven cuts at a low threshold and none at
normal ones, because this content evolves gradually rather than cutting.

So the video is resampled to 1 fps and consecutive *seconds* are compared. Selection
then runs against a budget rather than a threshold, in four passes: one frame per
chapter, then the highest-scoring seconds up to 80% of budget, then a coverage pass
filling any gap longer than three times the average spacing, then the remaining
budget on the next-highest scores. Every frame sits at least `duration / (4 × budget)`
from its neighbours, so one busy passage cannot consume everything.

The `reason` column in `index.md` tells you which pass chose a frame.

## Transcripts

Preference order: human captions, then auto-generated captions, then local ASR via
parakeet-mlx. Videos with no captions fall back automatically; `--asr` forces it.

Local transcription runs at roughly 72× realtime and chunks long audio internally, so
it needs no special handling. Measured: a 6-hour podcast episode transcribed to 48,000
words in 4m20s including the download. It often produces cleaner text than YouTube's
auto-captions, since it punctuates properly and does not repeat.

**No speaker labels.** parakeet-mlx does not do diarization, so a two-person interview
comes back as continuous prose with no `SPEAKER_00` markers to rename. Real diarization
would mean pyannote or WhisperX — a gated model, an HF token, and a much heavier
dependency. Instead, paragraphs break on silences longer than 1.2 s rather than on a
fixed clock, so turns usually land on their own paragraph and the text reads naturally.
`--gap` tunes this.

## Naming the speakers

Even without diarization, never leave people anonymous in anything you write. Work out
who is talking and use their actual names:

1. `meta.json` usually names them outright — `channel` or `series` gives the host
   ("The Shawn Ryan Show" → Shawn Ryan), and the `title` names the guest
   ("#95 Joe McMoneagle - CIA's Project Stargate" → Joe McMoneagle).
2. The opening minute confirms it: hosts introduce themselves and their guest by name.
3. Use those names in summaries, section text, and quoted passages — "McMoneagle
   describes…", not "the guest describes…".

Attribute only where the transcript makes the speaker unambiguous — a question followed
by an answer, or a self-identification. Where turns are genuinely unclear, write around
it rather than guessing; a confidently wrong attribution is worse than none. Do not
rewrite `transcript.md` to insert speaker labels you inferred, since that turns a
verbatim record into an edited one.

## Stage 3: the HTML summary (opt-in)

Only when the user asks for something shareable. After looking at the sheets, write a
sections file and render it:

```bash
cat > /tmp/sections.json <<'JSON'
{
  "summary": "One paragraph on what the video covers.",
  "sections": [
    {"title": "The cost function", "time": 352,
     "frame": "frames/0352.jpg", "text": "What happens here and why it matters."}
  ]
}
JSON
"<skill-dir>/summary.py" --dir <output-dir> --sections /tmp/sections.json
```

`--sections` is optional — without it you get the transcript alone, which is the right
shape for a podcast. `--out` overrides the destination.

The result is one self-contained file that works offline and that the reader can mark
up:

- **The summary is the page**; the full transcript sits below it in a collapsed
  `<details>`, so a six-hour interview opens as one screen of text.
- **Select any passage to highlight it** and attach a note. Click a highlight to edit
  or remove it. Highlights work in the summary and the transcript alike.
- **Save** writes the annotations back into the file itself — silently in place on
  Chrome and Edge after one file picker, as a download elsewhere. **Copy notes** puts
  every highlight and note on the clipboard as timestamped markdown.
- Annotations also autosave to `localStorage`, and whichever copy is newer wins on
  open, so a file someone sends you arrives with their notes intact.

Embedded frames are sized to fit a 5 MB total budget, shared out between however many
frames the summary uses: a handful of frames stay at 1600px and high quality, two dozen
step down as needed. Frames are the reason the artifact exists, so quality is only
traded away when the count demands it. Measured: 6 frames → 1.0 MB, 23 frames → 2.5 MB.

Write **honest** section text. Look at the frames and the transcript first; the whole
point of the artifact is that someone can trust it without rewatching.

## Other services

Nothing here is YouTube-specific: yt-dlp does the extraction and ffmpeg cuts the
frames, so roughly 1800 sites work. Verified on TED (subtitles in several languages,
11 video formats). Three differences to expect:

- **Deep links** into a timestamp only work where the service supports them (YouTube,
  Vimeo). Elsewhere `transcript.md` shows plain timestamps.
- **Audio-only sources** — podcasts, SoundCloud, a bare MP3 — are detected and the
  frame stage is skipped automatically. You get a transcript.
- **Captions are rarer off YouTube**, so the parakeet fallback carries more of the
  load. It handles that fine.

### Aggregator links

Pocket Casts, Overcast, Castro, Player.fm and similar are *directories* — yt-dlp has no
extractor for them, because the audio lives on the show's own feed. `resolve.py` handles
that automatically in three hops:

```
aggregator page  ->  show's RSS feed  ->  the <enclosure> whose title matches
```

Feed discovery tries the page's `<link rel=alternate>`, then any feed-shaped URL on the
page, then the iTunes Search API (free, no key, covers essentially every podcast).
Episodes are matched by title, so the resolved item is the one you asked for and not a
neighbour in the feed.

This also fixes naming: a direct MP3 carries only an ID3 tag, so an episode would
otherwise land in a folder called `E1 MASTER V3`. The feed title wins, giving
`s2e39-ibogaine-inquiries-part-i-remember-the-name` and a real `series` in `meta.json`.
`--title` overrides manually.

Run it standalone to see what a link resolves to:

```bash
"<skill-dir>/resolve.py" "<aggregator url>"
```

Verified on Pocket Casts. Non-aggregator URLs are returned untouched with no network
call, so it is safe on every URL. Spotify-only shows cannot work — that audio is DRMed
and not in any feed.

Extractors break independently of this skill. Vimeo currently fails upstream with
`Failed to fetch macos OAuth token: 401` — that is yt-dlp's problem, not a bug here.
`yt-dlp -U` is the first thing to try when one site stops working.

## Failure modes

- **Live or upcoming streams** are refused — there is nothing to digest yet.
- **Videos over 3 hours** stop and ask for `--force`. Check with the user first;
  it means a large download.
- **Private, removed, age-restricted, or geo-blocked** videos fail with that stated.
- **Caption languages must be exact.** Never pass a glob like `en.*` — it pulls
  machine-translated tracks and earns an HTTP 429.
- **No Pillow** means no contact sheets. Frames are still extracted; fall back to
  reading them individually, sparingly.

## Files

`transcribe.sh` is glue. The decisions live in `select_frames.py` (budget, spacing,
coverage), `transcript.py` (VTT normalization and rolling-duplicate removal),
`index.py`, `sheets.py`, and `summary.py`. The first two are pure stdin→stdout
filters with unit tests.
