# Presets — which one, and what it commits you to

Six presets. Each carries a palette, its typefaces as embedded woff2, and a
**house rules** string that `bento.sh` does not enforce and you must honour
while authoring. A preset that only set colours would produce a deck with the
right palette and the wrong instincts.

Pick by the room, not by the palette. Ask the user if it is genuinely unclear;
otherwise choose and say which you chose and why.

| Preset | Reach for it when | Avoid it when |
|---|---|---|
| `orbital` | Product launches, technical keynotes, anything with photography of hardware, space, or infrastructure. A dark room and a projector. | The deck will be printed, or read on paper. Dark decks waste toner and look grey. |
| `picnic` | Internal all-hands, culture decks, workshops, anything where energy matters more than gravitas. Loud on purpose. | Anything a customer signs. It reads as confident-but-unserious, which is right until it isn't. |
| `signal` | Strategy, opinion, a strong argument carried by words. Where you want the deck to feel like a magazine feature. | Data-dense material. The type wants room, and dense charts fight it. |
| `terra` | Client-facing, premium products, design and craft stories, anything photography-forward. The safest choice for an outside audience. | A fast, punchy internal update. The whitespace makes five slides feel like a considered fifteen. |
| `latex` | Research talks, technical deep-dives, anything where looking like a paper is the point. | A sales pitch. It signals rigour, and rigour is not persuasion. |
| `plain` | The deck will be restyled later, or dropped into someone else's template. Zero embedded bytes. | You want it to look finished. It is deliberately unopinionated. |

## What each preset ships

| Preset | Faces embedded | Bytes |
|---|---|---|
| `orbital` | Instrument Sans (variable), Space Mono 400/700 | ~50 KB |
| `picnic` | Instrument Sans (variable) | ~29 KB |
| `signal` | Fraunces 900, Instrument Sans | ~63 KB |
| `terra` | Fraunces 900, Instrument Sans | ~63 KB |
| `latex` | Latin Modern regular/bold/italic/bold-italic | ~189 KB |
| `plain` | none — system stacks only | 0 |

The first four themes are lifted verbatim from Bento's own gallery decks
(`bento.page/gallery/{orbital-dark-immersive,picnic-playful,signal-editorial-type,terra-premium-product}.bento.html`),
and their faces are the same subsetted bytes those decks carry. They are
professionally tuned; do not "improve" the palettes.

## Fonts belong to the document

A `fontFamily` naming a face the document does not carry **falls back
silently**. There is no warning, and it will usually look right to you, because
you are the one with the typeface installed — everyone else gets the fallback.
`bento.sh new` embeds every face its preset names, and the test suite asserts
that every family in a preset's `fonts` resolves to a key in `assets`.

The consequence for authoring: if you set `fontFamily` on an element, it must
name a family the preset ships or a full system stack. Never a bare family
name, and never a face you have not embedded. `window.bento.validate()` reports
this as `font-not-embedded`.

## `latex` and italics

The published guide describes `doc.fonts` entries as `{family, asset, weight}`.
The runtime also honours **`style`** — it builds
`@font-face{…font-style:${r.style ?? "normal"}}` — which is how the `latex`
preset ships true italic and bold-italic Latin Modern rather than letting the
browser synthesize a slanted roman. That matters for `Figure 1:` captions,
which the house rules set in italic.

## Presets are pinned, not tracked

`bento.sh refresh` re-pulls the runtime and the guide. It deliberately leaves
`styles/` alone. A preset is a design decision that the other presets and the
house rules are written against, so it changes when someone decides to change
it, not when upstream reworks a gallery deck.

## Licensing

| Face | Licence | File |
|---|---|---|
| Instrument Sans | OFL 1.1 | `fonts/LICENSE-OFL-InstrumentSans.txt` |
| Fraunces | OFL 1.1 | `fonts/LICENSE-OFL-Fraunces.txt` |
| Space Mono | OFL 1.1 | `fonts/LICENSE-OFL-SpaceMono.txt` |
| Latin Modern | GUST Font Licence (LPPL-derived) | `fonts/LICENSE-GUST-LatinModern.txt` |

Each licence travels verbatim with the fonts, which is what both licences
require. There is deliberately **no Reaktor preset**: those faces are
commercially licensed and this repository is public.
