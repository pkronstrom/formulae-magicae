#!/usr/bin/env bash
# transcribe-media - transcript + key frames for a video.
#
# Thin glue. The decisions live in select_frames.py, transcript.py, index.py.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

URL=""
HEIGHT=""
BUDGET=0
WANT_FRAMES=1
FORCE_ASR=0
LANG_PREF="en"
OUT_MODE="project"
KEEP_VIDEO=0
FORCE=0
TITLE_OVERRIDE=""
RESOLVED_TITLE=""
RESOLVED_SERIES=""

die() { printf 'transcribe-media: %s\n' "$1" >&2; exit 1; }
say() { printf '%s\n' "$1" >&2; }

usage() {
  cat >&2 <<'EOF'
usage: transcribe.sh <url> [options]

  --height N        max video height for frames (default 720, 480 above 45min)
  --frames N        frame budget (default: 1.2 x minutes, clamped to 12..40)
  --no-frames       transcript only, skip the video download entirely
  --asr|--stt|--parakeet
                    force local transcription instead of using YouTube captions
  --lang CODE       caption language (default en)
  --title TEXT      override the title (aggregator links resolve theirs already)
  --out MODE        project (default) | library | obsidian | /explicit/path
  --keep-video      keep the downloaded video after extracting frames
  --force           re-process even if the output directory already exists
EOF
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --height) HEIGHT="${2:-}"; shift 2 ;;
    --frames) BUDGET="${2:-}"; shift 2 ;;
    --no-frames) WANT_FRAMES=0; shift ;;
    --asr|--stt|--parakeet) FORCE_ASR=1; shift ;;
    --lang) LANG_PREF="${2:-}"; shift 2 ;;
    --title) TITLE_OVERRIDE="${2:-}"; shift 2 ;;
    --out) OUT_MODE="${2:-}"; shift 2 ;;
    --keep-video) KEEP_VIDEO=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage ;;
    -*) die "unknown option: $1" ;;
    *) URL="$1"; shift ;;
  esac
done

[ -n "$URL" ] || usage
command -v yt-dlp >/dev/null || die "yt-dlp not found"
command -v ffmpeg >/dev/null || die "ffmpeg not found"

# ---------------------------------------------------------------- metadata

WORK="$(mktemp -d "${TMPDIR:-/tmp}/transcribe-media.XXXXXXXX")" \
  || die "could not create a work directory"

# Deliberately narrow: only ever remove a directory carrying the prefix this script
# created, so an empty or unexpected $WORK can never turn into a destructive rm.
cleanup() {
  case "$WORK" in
    */transcribe-media.????????)
      if [ -d "$WORK" ]; then rm -rf -- "$WORK"; fi
      ;;
  esac
}
trap cleanup EXIT

# Aggregator links (Pocket Casts and friends) are directories, not media: yt-dlp has
# no extractor for them. resolve.py finds the show's feed and the matching enclosure.
# It no-ops without touching the network for everything else.
"$PY" "$HERE/resolve.py" "$URL" > "$WORK/resolve.json" 2>/dev/null || true
eval "$(
  "$PY" - "$WORK/resolve.json" <<'PYEOF'
import json, shlex, sys
try:
    found = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    found = {}
if found.get("resolved"):
    print("URL=" + shlex.quote(found["url"]))
    print("RESOLVED_TITLE=" + shlex.quote(found.get("title", "")))
    print("RESOLVED_SERIES=" + shlex.quote(found.get("series", "")))
PYEOF
)"
if [ -n "$RESOLVED_TITLE" ] && [ -z "$TITLE_OVERRIDE" ]; then
  TITLE_OVERRIDE="$RESOLVED_TITLE"
  say "==> resolved via feed: $RESOLVED_SERIES — $RESOLVED_TITLE"
fi

say "==> fetching metadata"
yt-dlp --dump-single-json --skip-download "$URL" > "$WORK/raw.json" 2>"$WORK/err" \
  || { sed 's/^/    /' "$WORK/err" >&2; die "could not read that video (private, removed, or geo-blocked?)"; }

eval "$(
  "$PY" - "$WORK/raw.json" "$LANG_PREF" "$URL" "$TITLE_OVERRIDE" <<'PYEOF'
import json, re, sys, shlex

raw = json.load(open(sys.argv[1], encoding="utf-8"))
want = sys.argv[2]
given = sys.argv[3]
override = sys.argv[4] if len(sys.argv) > 4 else ""

def pick(track):
    if not track:
        return ""
    for code in (want, f"{want}-orig"):
        if code in track:
            return code
    for code in track:
        if code == want or code.startswith(f"{want}-"):
            return code
    return ""

manual = pick(raw.get("subtitles") or {})
auto = pick(raw.get("automatic_captions") or {})
# A direct media URL carries only an ID3 tag ("E1 MASTER V3"); a title resolved from
# the feed is the real one, so it wins for both display and the folder name.
title = override or raw.get("title") or "Untitled"
slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]

if manual:
    mode, lang = "manual", manual
elif auto:
    mode, lang = "auto", auto
else:
    mode, lang = "none", ""

# yt-dlp reaches ~1800 sites and the rest of this pipeline is source-agnostic, but
# deep links into a timestamp are not: each service spells them differently, and most
# cannot do it at all.
extractor = (raw.get("extractor_key") or "").lower()
page = raw.get("webpage_url") or given
if "youtube" in extractor:
    link = f"{page}{'&' if '?' in page else '?'}t={{t}}s"
elif "vimeo" in extractor:
    link = f"{page}#t={{t}}s"
else:
    link = ""

# Audio-only sources (podcasts, SoundCloud, bare mp3s) have nothing to screenshot.
# Direct-file extractors like ApplePodcasts report no formats at all, only a
# top-level vcodec, so both shapes have to be checked.
formats = raw.get("formats") or []
if formats:
    has_video = any(f.get("vcodec") not in (None, "none") for f in formats)
else:
    has_video = raw.get("vcodec") not in (None, "none")

# A resolved title means the extractor id came from an ID3 tag ("E1 MASTER V3") and is
# noise; the slug alone makes a better folder. Real extractor ids stay as prefixes
# because they are stable identifiers worth keeping.
# (No apostrophes in this heredoc: bash mis-parses them inside a command substitution.)
ident = re.sub(r"[^A-Za-z0-9_-]+", "-", str(raw.get("id") or "media")).strip("-")
dirname = slug if override else f"{ident}-{slug}"

out = {
    "ID": ident or "media",
    "DIRNAME": dirname or "media",
    "SLUG": slug or "video",
    "TITLE": title,
    "DURATION": str(int(raw.get("duration") or 0)),
    "LIVE": "1" if raw.get("is_live") or raw.get("live_status") in ("is_live", "is_upcoming") else "0",
    "SUB_MODE": mode,
    "SUB_LANG": lang,
    "EXTRACTOR": raw.get("extractor_key") or "unknown",
    "LINK_TEMPLATE": link,
    "HAS_VIDEO": "1" if has_video else "0",
}
for key, value in out.items():
    print(f"{key}={shlex.quote(value)}")
PYEOF
)"

[ "$LIVE" = "0" ] || die "live or upcoming stream - nothing to pull yet"

# Some extractors (podcast feeds especially) report no duration. It is recovered
# with ffprobe once a media file exists; until then the length-based guards are
# simply skipped.
if [ "$DURATION" -gt 10800 ] && [ "$FORCE" -eq 0 ]; then
  die "video is $((DURATION / 60)) minutes; re-run with --force if that is intended"
fi

case "$OUT_MODE" in
  project) BASE="$PWD/.media" ;;
  library) BASE="${TRANSCRIBE_MEDIA_LIBRARY:-$HOME/Videos/media-library}" ;;
  obsidian) BASE="${OBSIDIAN_VAULT:-$HOME/Documents/obsidian/Vault}/Media" ;;
  *) BASE="$OUT_MODE" ;;
esac
DIR="$BASE/$DIRNAME"

if [ -f "$DIR/index.md" ] && [ "$FORCE" -eq 0 ]; then
  say "==> already digested, reusing"
  printf '%s\n' "$DIR"
  exit 0
fi

mkdir -p "$DIR/frames" "$DIR/sheets"
say "==> $TITLE ($((DURATION / 60))m$((DURATION % 60))s, $EXTRACTOR)"

if [ "$WANT_FRAMES" -eq 1 ] && [ "$HAS_VIDEO" = "0" ]; then
  say "    audio-only source, skipping frames"
  WANT_FRAMES=0
fi

# ---------------------------------------------------------------- transcript

SOURCE="$SUB_MODE"
if [ "$FORCE_ASR" -eq 1 ] || [ "$SUB_MODE" = "none" ]; then
  SOURCE="asr"
fi

# Pick a local speech-to-text engine. $TRANSCRIBE_MEDIA_ASR pins one explicitly;
# otherwise the first available wins. All of these emit VTT, which is the only
# interface the rest of the pipeline cares about.
pick_engine() {
  if [ -n "${TRANSCRIBE_MEDIA_ASR:-}" ]; then
    printf '%s' "$TRANSCRIBE_MEDIA_ASR"
    return
  fi
  if command -v uvx >/dev/null; then
    printf 'parakeet'
    return
  fi
  if command -v whisper >/dev/null; then
    printf 'whisper'
    return
  fi
  printf 'none'
}

asr_instructions() {
  cat >&2 <<'EOF'
    Local transcription needs one of these:
      uv          (recommended)  brew install uv
                                 curl -LsSf https://astral.sh/uv/install.sh | sh
                  Nothing else to install - the engine and its model are fetched
                  on first use. Apple Silicon runs parakeet at ~72x realtime.
      whisper     pip install -U openai-whisper      (works anywhere, slower)
    Then re-run. Pin an engine with TRANSCRIBE_MEDIA_ASR=parakeet|mlx-whisper|whisper.
EOF
}

if [ "$SOURCE" = "asr" ]; then
  ENGINE="$(pick_engine)"
  if [ "$ENGINE" = "none" ]; then
    say "==> no captions available and no local transcription engine found"
    asr_instructions
    if [ "$WANT_FRAMES" -eq 0 ]; then
      die "nothing to produce without a transcript engine"
    fi
    say "    continuing with frames only"
    SOURCE="unavailable"
  fi
fi

if [ "$SOURCE" = "asr" ]; then
  say "==> no usable captions, transcribing locally ($ENGINE)"
  yt-dlp -q -f "ba[ext=m4a]/ba/b" -o "$WORK/audio.%(ext)s" "$URL" >/dev/null
  AUDIO="$(find "$WORK" -name 'audio.*' -maxdepth 1 | head -1)"
  [ -n "$AUDIO" ] || die "audio download failed"
  if [ "$DURATION" -eq 0 ]; then
    DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$AUDIO" \
      | cut -d. -f1)"
    DURATION="${DURATION:-0}"
    say "    duration recovered from file: $((DURATION / 60))m"
  fi

  # The model is a one-time multi-gigabyte download. Say so, or the first run looks
  # like a hang.
  HF_HUB="${HF_HOME:-$HOME/.cache/huggingface}/hub"
  case "$ENGINE" in
    parakeet)
      [ -d "$HF_HUB/models--mlx-community--parakeet-tdt-0.6b-v3" ] \
        || say "    first run: downloading the ~2.3 GB model, once"
      ;;
  esac

  case "$ENGINE" in
    parakeet)
      uvx --from parakeet-mlx parakeet-mlx "$AUDIO" \
        --output-format vtt --output-dir "$WORK" >/dev/null 2>"$WORK/asr.log" \
        && mv "$WORK/audio.vtt" "$WORK/asr.vtt"
      ;;
    mlx-whisper)
      uvx --from mlx-whisper mlx_whisper "$AUDIO" \
        --model "${TRANSCRIBE_MEDIA_WHISPER_MODEL:-mlx-community/whisper-large-v3-turbo}" \
        --output-format vtt --output-dir "$WORK" >/dev/null 2>"$WORK/asr.log" \
        && mv "$WORK/$(basename "${AUDIO%.*}").vtt" "$WORK/asr.vtt"
      ;;
    whisper)
      whisper "$AUDIO" --output_format vtt --output_dir "$WORK" \
        >/dev/null 2>"$WORK/asr.log" \
        && mv "$WORK/$(basename "${AUDIO%.*}").vtt" "$WORK/asr.vtt"
      ;;
    *)
      die "unknown transcription engine: $ENGINE"
      ;;
  esac

  if [ ! -f "$WORK/asr.vtt" ]; then
    say "==> $ENGINE failed:"
    tail -5 "$WORK/asr.log" >&2 2>/dev/null || true
    asr_instructions
    if [ "$WANT_FRAMES" -eq 0 ]; then die "transcription failed"; fi
    say "    continuing with frames only"
    SOURCE="unavailable"
  else
    cp "$WORK/asr.vtt" "$DIR/transcript.vtt"
    SOURCE="$ENGINE"
  fi
fi

if [ "$SOURCE" = "unavailable" ]; then
  : # no transcript; the frame stage still runs
elif [ "$SOURCE" != "parakeet" ] && [ "$SOURCE" != "mlx-whisper" ] \
     && [ "$SOURCE" != "whisper" ]; then
  say "==> fetching $SUB_MODE captions ($SUB_LANG)"
  # Exact language code only: a glob pulls translated tracks and earns a 429.
  if [ "$SUB_MODE" = "manual" ]; then
    yt-dlp -q --skip-download --write-subs --sub-lang "$SUB_LANG" \
      --sub-format vtt -o "$WORK/sub" "$URL" >/dev/null
  else
    yt-dlp -q --skip-download --write-auto-subs --sub-lang "$SUB_LANG" \
      --sub-format vtt -o "$WORK/sub" "$URL" >/dev/null
  fi
  FOUND="$(find "$WORK" -name 'sub*.vtt' -maxdepth 1 | head -1)"
  [ -n "$FOUND" ] || die "caption download produced nothing"
  cp "$FOUND" "$DIR/transcript.vtt"
fi

if [ -f "$DIR/transcript.vtt" ]; then
  "$PY" "$HERE/transcript.py" "$DIR/transcript.vtt" --link "$LINK_TEMPLATE" \
    --title "$TITLE" > "$DIR/transcript.md"
  say "    $(wc -w < "$DIR/transcript.md" | tr -d ' ') words"
fi

# ---------------------------------------------------------------- frames

SHEETS_JSON=""
if [ "$WANT_FRAMES" -eq 1 ]; then
  if [ -z "$HEIGHT" ]; then
    HEIGHT=720
    if [ "$DURATION" -gt 2700 ]; then HEIGHT=480; fi
  fi

  say "==> downloading video (<=${HEIGHT}p)"
  yt-dlp -q -f "bv[height<=$HEIGHT][ext=mp4]/bv[height<=$HEIGHT]/b[height<=$HEIGHT]" \
    -o "$WORK/video.%(ext)s" "$URL" >/dev/null
  VIDEO="$(find "$WORK" -name 'video.*' -maxdepth 1 | head -1)"
  [ -n "$VIDEO" ] || die "video download failed"
  if [ "$DURATION" -eq 0 ]; then
    DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO" \
      | cut -d. -f1)"
    [ -n "$DURATION" ] && [ "$DURATION" -gt 0 ] || die "could not determine duration"
  fi

  say "==> scoring visual change at 1fps"
  "$PY" -c "import json,sys; json.dump(json.load(open(sys.argv[1])).get('chapters') or [], open(sys.argv[2],'w'))" \
    "$WORK/raw.json" "$WORK/chapters.json"

  ffmpeg -v info -i "$VIDEO" -vf "fps=1,scale=320:-2,scdet=threshold=0" \
    -f null - 2>"$WORK/scores.txt" || true

  "$PY" "$HERE/select_frames.py" --duration "$DURATION" --budget "$BUDGET" \
    --chapters "$WORK/chapters.json" < "$WORK/scores.txt" > "$WORK/selection.json"

  say "==> extracting frames"
  while read -r TIME; do
    NAME="$(printf '%04d' "${TIME%.*}")"
    ffmpeg -v error -ss "$TIME" -i "$VIDEO" -frames:v 1 -q:v 2 \
      -y "$DIR/frames/$NAME.jpg" </dev/null
  done < <("$PY" -c "import json,sys; [print(e['time']) for e in json.load(open(sys.argv[1]))]" "$WORK/selection.json")

  "$PY" - "$WORK/selection.json" "$DIR" > "$DIR/frames.json" <<'PYEOF'
import json, os, sys
entries = json.load(open(sys.argv[1], encoding="utf-8"))
root = sys.argv[2]
out = []
for entry in entries:
    path = os.path.join(root, "frames", f"{int(entry['time']):04d}.jpg")
    if os.path.exists(path):
        entry["path"] = path
        out.append(entry)
json.dump(out, sys.stdout, indent=2)
PYEOF

  say "==> building contact sheets"
  if ! "$PY" "$HERE/sheets.py" --frames "$DIR/frames.json" --out-dir "$DIR/sheets" \
       > "$DIR/sheets.json" 2>"$WORK/sheeterr"; then
    sed 's/^/    /' "$WORK/sheeterr" >&2
    say "    sheets unavailable (Pillow missing?); frames are still in frames/"
    rm -f "$DIR/sheets.json"
  else
    SHEETS_JSON="$DIR/sheets.json"
  fi

  if [ "$KEEP_VIDEO" -eq 1 ]; then
    cp "$VIDEO" "$DIR/video.${VIDEO##*.}"
  fi
fi

# ---------------------------------------------------------------- index

"$PY" - "$WORK/raw.json" "$DIR/meta.json" "$URL" "$SOURCE" "$LINK_TEMPLATE" "$EXTRACTOR" "$DURATION" "$TITLE" "$RESOLVED_SERIES" <<'PYEOF'
import json, sys
raw = json.load(open(sys.argv[1], encoding="utf-8"))
keep = ("id", "title", "channel", "uploader", "duration", "chapters", "upload_date")
meta = {key: raw.get(key) for key in keep}
# May have been recovered with ffprobe when the extractor did not report it.
meta["duration"] = int(sys.argv[7]) or raw.get("duration")
meta["title"] = sys.argv[8] or raw.get("title")
meta["series"] = (len(sys.argv) > 9 and sys.argv[9]) or raw.get("series")
meta["webpage_url"] = raw.get("webpage_url") or sys.argv[3]
meta["transcript_source"] = sys.argv[4]
meta["link_template"] = sys.argv[5]
meta["extractor"] = sys.argv[6]
json.dump(meta, open(sys.argv[2], "w", encoding="utf-8"), indent=2)
PYEOF

"$PY" "$HERE/index.py" --meta "$DIR/meta.json" \
  --frames "$DIR/frames.json" --vtt "$DIR/transcript.vtt" \
  --sheets "$SHEETS_JSON" > "$DIR/index.md"

say "==> done"
printf '%s\n' "$DIR"
