#!/bin/sh
# Usage: assemble.sh <source.md> <output.html> <title>
#
# Escapes the markdown so it can live inside a raw-text <script> element,
# wraps it in the prelude, and appends the engine. Carries forward any
# existing #viz-marks block so user annotations survive regeneration.
set -eu

SRC=$1
OUT=$2
TITLE=$3
SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEMPLATE="$SKILL_DIR/template.html"
LINT="$SKILL_DIR/mermaid-lint.awk"

[ -f "$SRC" ] || { echo "assemble: no such source: $SRC" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "assemble: no template: $TEMPLATE" >&2; exit 1; }
[ -f "$LINT" ] || { echo "assemble: no linter: $LINT" >&2; exit 1; }

# docId keys the localStorage entry. Browsers may place every file:// page in
# ONE shared bucket, so this must be unique per document across the whole
# machine - a slug, or even <parent-dir>/<slug>, collides the moment two
# projects share a layout (docs/viz/plan.md is not rare). The absolute source
# path is the document's actual identity: unique by construction and stable
# across regeneration, which is what keeps annotations anchored.
SLUG=$(basename "$SRC" .md)
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$SRC")" && pwd)
DOC_ID="viz:$SRC_DIR/$SLUG"

# Carry forward existing marks if regenerating over a previous output.
MARKS=""
if [ -f "$OUT" ]; then
  MARKS=$(awk '/id="viz-marks"/{f=1;next} f&&/<\/script>/{exit} f{print}' "$OUT") || MARKS=""
fi
# A marks block carried forward from an older build has no `src` key, so the
# export could not tell the agent which file to edit. Backfill it.
case "$MARKS" in
  ""|*'"src"'*) ;;
  *) MARKS=$(printf '%s' "$MARKS" | sed "s|^[[:space:]]*{|{\"src\":\"$SRC_DIR/$SLUG.md\",|") ;;
esac

if [ -z "$MARKS" ]; then
  # `src` travels with the document so the exported feedback can tell the agent
  # which file to edit, not just what the user said.
  MARKS="{\"v\":1,\"docId\":\"$DOC_ID\",\"src\":\"$SRC_DIR/$SLUG.md\",\"savedAt\":0,\"marks\":[]}"
fi

TMP="$OUT.tmp.$$"
{
  printf '<!doctype html><meta charset="utf-8">\n'
  printf '<title>%s</title>\n' "$(printf '%s' "$TITLE" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g')"
  # Marks first: small and bounded, so `head -40` always reaches it
  # regardless of how long the markdown grows.
  printf '<script type="application/json" id="viz-marks">\n%s\n</script>\n' "$MARKS"
  printf '<script type="text/markdown" id="viz-src">\n'
  # mermaid-lint.awk escapes `;` and `#` in sequenceDiagram text (where they
  # end the statement) and reports the hazards it will not rewrite, on stderr.
  # It runs FIRST so the sed below still sees every `</script` it must escape.
  #
  # LC_ALL=C is not optional. macOS ships the one-true-awk, which in a UTF-8
  # locale fails on multibyte input ("towc: multibyte conversion failure") and
  # SILENTLY TRUNCATES the record — an em dash in a note cost the rest of the
  # line. Byte semantics are safe here precisely because every character this
  # pass looks for is ASCII, and a UTF-8 continuation byte can never collide
  # with one; the loop copies bytes through in order, so text is preserved.
  LC_ALL=C awk -f "$LINT" -v src="$SRC" "$SRC" \
    | sed -e 's|</script|<\\/script|g' -e 's|<!--|<\\!--|g'
  printf '\n</script>\n'
  cat "$TEMPLATE"
} > "$TMP"
mv "$TMP" "$OUT"
echo "$OUT"
