---
name: bento-slides
description: Build a presentation as a single self-contained .bento.html deck — one file that is the document, the editor and the player at once, opens from a double-click, and can be mailed on. Use when the user wants slides, a deck, a talk, a keynote, a pitch, a readout, or a presentation; says "make me slides", "turn this into a deck", "build a presentation"; wants to edit or restyle an existing .bento.html; or has a document, notes, or a repo they want presented. Also use for a deck that must work offline with no accounts and no build step.
---

# Bento decks

One `.bento.html` file. It is the document, the editor and the player at once —
double-click it and it opens; mail it and it still opens; nothing is fetched at
runtime. This is the `/singlefile` contract applied to presentations.

You do not build the app. You write JSON into the one empty block inside a
vendored copy of it, using `bento.sh`.

**Read `reference/agents.md` before authoring.** It is the vendored schema
guide — element types, the chart subset, layout arithmetic, the rules that make
a deck feel designed. This file covers how to *work*; that one covers what to
*write*. Do not author from memory.
Its upstream install examples are informational, not the installation path of the
current host. Resolve and run `bento.sh` from this skill directory; when copying a
skill manually, preserve the entire directory rather than copying only `SKILL.md`.

## The one thing that goes wrong

Every `<` inside the document JSON must become the JSON escape `<`, or a
deck whose text happens to contain `</script>` truncates its own data block and
the file will not open. **Never hand-edit the block and never hand-escape.**
`bento.sh write` does it mechanically and refuses to write if the `</script`
count moves.

## 1. Intake — one or two questions

Normally exactly two:

1. What is the deck about?
2. What is the one thing the audience should leave with?

Plus a style pick from the six in `styles/styles.md` — offer them, with a
one-line reason for the one you would choose.

Infer length and audience and **state them as assumptions** rather than asking.
"I'll aim for 8 slides for an internal engineering audience — say if that's
wrong" beats two more questions.

More questions only when the subject is genuinely complex or the material is
contradictory. If the user points at a document, notes, or a repository, read
that instead of asking.

## 2. Create the deck

```bash
./bento.sh new "<Topic>" --style <name> [--dir <path>]
```

Copies the vendored runtime, slugs the topic to a safe basename, and injects a
minimal valid document carrying the preset's theme, fonts and font assets. It
refuses to overwrite an existing file — that is the user's work, not a build
artifact.

## 3. Author, then check in bulk

**Author first, check once.** Write the whole deck using the column arithmetic
in `reference/agents.md`, then run `validate()` (step 4) and fix what it
reports. Do not open a browser between every string.

The format is absolute pixels, so the height of a string at a given width and
font is **not knowable from the JSON** — but `validate()` measures every text
element against the real renderer in one pass and reports overflow with exact
numbers ("needs 342px but the box is 300px tall — it overflows by 42px (3
lines)"). That is the same answer a per-string measurement gives, for the whole
deck, in one round-trip instead of thirty.

**Reach for `measure()` only when a single string's fit drives the layout** —
a cover headline where 2 lines versus 3 changes where everything else sits, or
a caption you are sizing a photo around. There, knowing before you place beats
placing and repairing:

```js
window.bento.measure({ html: 'Long paragraph…', w: 600, fontSize: 28, lineHeight: 1.4 })
// → { height: 236, width: 600, lines: 6 }
```

Pass `h` too and you get `fits` and `overflow` back. It renders through the
real renderer, so the answer is what the slide will actually do.

**If no interactive browser is available, skip `measure()` entirely** — do not
spend turns trying to get one. `bento.sh check` needs only headless Chrome and
reports the same overflows after the fact. A browser you cannot reach is not a
reason to ship a deck unverified.

Then edit and write:

```bash
./bento.sh read  <deck> > doc.json     # existing document, unescaped
# …edit doc.json…
./bento.sh write <deck> doc.json       # validated, escaped, atomic
```

`read` **withholds `doc.assets`** — the embedded font, image and video base64.
A deck with two typefaces carries ~85 KB of it, which would otherwise flood
your context with payload you cannot usefully edit. `write` carries the
existing assets forward whenever the incoming document omits the key, so an
edit cycle never strands `doc.fonts` pointing at nothing. Pass `--with-assets`
on the rare occasion you need the bytes, and an explicit `"assets": {}` if you
really mean to clear them.

### Map material to feature — never default to bullets

The format's whole value is motion, morph, charts and interactivity. Bullets on
slides waste it and are the #1 failure mode.

| Material | Reach for |
|---|---|
| Numbers to compare | a `chart` element — never a table, never text |
| Comparison / spec / pricing grid | a `table` element |
| The same thing changing across slides | shared element ids + `transition: "morph"` |
| A point to drill into | a state slide (`stateOf` + element `link`) |
| A hero image | full-bleed + scrim rect + text, with ken-burns |
| A headline number | big text + `fx: {countUp: true}` |
| A sequence or flow | a connector with a `dash-march` loop |

Carry 2–4 stable ids through the deck so the furniture morphs in place instead
of popping on every slide. Morph is Bento's signature move and it is *almost
always missed*.

Also: one accent colour, at most two typefaces, 96 px side margins (right-most
x ≤ 1184), speaker notes on every slide, `role` on every text element
(`title|subtitle|body|kicker`) so the deck restyles cleanly, and the column
arithmetic from `reference/agents.md` rather than numbers you computed fresh.

**The preset's house rules in `styles/presets.json` override the generic advice
where they conflict.** `latex` does not get ken-burns just because a slide has
a photograph.

## 4. Verify cheap, then ask

```bash
./bento.sh check <deck>
```

**Run this after every write.** It takes about two seconds and needs no
browser window, no extension and no MCP — it boots the deck in headless Chrome,
runs the deck's own `validate()`, prints findings worst-first, and exits
non-zero if any are errors. If Chrome is missing it says so; open the deck and
run `window.bento.validate()` in the console yourself.

It keeps a Chrome profile at
`${XDG_CACHE_HOME:-~/.cache}/bento-slides/chrome-profile` (~33 MB) so repeat runs
stay under two seconds instead of paying cold-start every time. `XDG_CACHE_HOME` is
used only when it is non-empty and absolute; empty or relative values fall back to
`~/.cache`. Run `./bento.sh cache-path` to print the resolved location. Deleting it is
safe — the next run rebuilds it. The old hard-coded profile is not migrated or deleted.

Fix every finding above `info` and re-check until clean. It catches what the
runtime otherwise swallows in silence: unknown property names (a typo means
your styling just never applies), text overflowing its box measured against the
real renderer, elements off-canvas, entrances that can never run, `dash-march`
without a dashed stroke, broken `link` and `asset:` references, duplicate ids,
morph-key collisions, and chart options charts-lite does not implement.

`validate()` is not a substitute for looking. Then **ask** whether the user
wants a screenshot pass over every slide — it is slow, so it is opt-in. Either
way, open the file and hand back the path. The user looks last.

## 5. Editing an existing deck

```
inspect  →  (ask, if shared)  →  read  →  edit  →  write  →  check
```

**`inspect` first, always.** A deck with live collaboration switched on carries
its session keys in the document — `ownerPriv`, `writerPriv`, `invite`. That is
by design: the file is the invitation, so anything that receives it can join
the room and write to it. `read` prints the whole document, so using `read` to
*discover* whether a deck is shared has already spilled those keys into your
context and this transcript.

`inspect` reports whether keys are present **without emitting them** and exits
3 if they are. If they are, tell the user before anything else — they may not
know their deck is live, and only they can decide. Then `read --allow-shared`
if they agree. Removing the keys afterwards does not retract them; the remedy
is *Share → Rotate keys*.

Never regenerate the file, and never regenerate `docId` — it is the document's
identity. Fresh decks omit `docId` and `collab` entirely so the app mints them
on first open.

## Diagrams

**Native shapes and connectors are the default.** Nodes are ordinary `shape`
elements with `role`d text; edges are `line` or `path` elements carrying
`from`/`to: {el, side}`, whose ends follow those elements and re-route when they
move (`side: "auto"` picks the nearest border). Two things no embedded image
can match:

- **Progressive build** — give nodes the same ids across consecutive slides
  with `transition: "morph"` and the diagram assembles itself in front of the
  audience: three boxes, then a fourth arrives and the rest reflow into place.
- **Animated flow** — `fx.loop: {type: "dash-march", distance: 18, duration: 1.4}`
  on a connector with `strokeStyle: "dashed"` marches the stroke along the edge.
  It animates `strokeDashoffset`, so the dash pattern is **required**, not
  decorative: on a solid stroke the tween runs and there is nothing to see.

Native nodes also inherit the preset's palette and typeface. A Mermaid render
dropped into a `latex` deck looks like what it is — a screenshot from somewhere
else.

The ladder, in order of preference:

| Situation | Approach |
|---|---|
| Any diagram up to ~10 nodes | Native shapes + connectors; `measure()` sizes the labels |
| A Mermaid source already exists | Transpile it by hand — it is a handful of boxes on a 1088 px band, not a rendering problem |
| Genuinely intricate artwork | Embedded `svg` with inline `markup` |
| It deserves its own page | `/visualize`, which already exists in this repo — cross-reference, do not rebuild |
| Numeric data | The native `chart` element — never a diagram |

**No Mermaid render bridge exists and none should be built.** It would drag in
a Puppeteer-class dependency plus network on first run, in exchange for a
strictly worse artifact.

**On embedded SVG:** the runtime accepts `markup` up to 4 MB plus its own `css`
up to 128 KB, and takes `fx`/`morphId` — so it morphs as a *single unit*, never
internally, and does not restyle with the preset. No sanitizer is evident in
the runtime, so SVG from an untrusted source warrants the same caution as any
pasted code.

## Keeping the vendored copy current

```bash
./bento.sh refresh
```

Network-only; never run it implicitly. The runtime and the guide are **one
artifact in two files** — `agents.md` declares the shell version it matches —
so `refresh` fetches the signed release manifest, checks the runtime's sha256
against it, checks that the guide's declared version equals the manifest's, and
**replaces neither unless both arrive and agree**. Refreshing them
independently pairs a new shell with an old schema, and that failure is silent:
you author valid-looking JSON against a contract the runtime no longer honours.

Every run prints the pinned guide version to stderr so a mismatch is visible
rather than inferred. `styles/` is left alone — presets are pinned, not tracked.

## What this skill will not do

- **Typeset mathematics.** Text elements accept only `<b> <i> <br>`, so there is
  nowhere for `\frac{\partial L}{\partial \theta}` to go and no renderer exists.
  The `latex` preset is the *look*. For slide-level notation use Unicode
  (α, ∑, ≤, x²), which renders correctly in Latin Modern.
- **A Reaktor-branded preset.** Those faces are commercially licensed and this
  repository is public. A colours-only version would hit the silent font-fallback
  trap — looking right only on a machine that has the faces installed. Point the
  agent at brand assets case by case instead.
