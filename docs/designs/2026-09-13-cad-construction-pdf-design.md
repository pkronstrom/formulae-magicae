# cad-construction-pdf: construction-ready booklets for small timber builds

Date: 2026-09-13. New skill `skills/cad-construction-pdf/`, built on `skills/cad-studio/`.
Status: approved in brainstorm; revised after codex sol review (8 findings folded in).

## Problem

The a-frame-cabin run (session c95bb762) produced a 21-page booklet — cover render,
dimensioned elevations, joint sheet, parts with cut angles, nesting, cut list, list-vs-budget
prices, envelope build-ups, seven phase pages with reveal renders, fastening schedule,
shopping batches. All of it was bespoke: a 200-line `book.py`, hand-picked phase renders,
`phases.md` prose disconnected from the cut list, ~15 turns of hand-patched prices re-derived
in three places, and the fastening layer ("which bolt, where, prikka or not, which screws,
which way") added last because nothing asked for it. A garden shed would start from zero.

The skill makes that booklet the repeatable end product: a staged iteration with gates, a
small artifact contract the model must satisfy, a page manifest instead of layout code, a
price ledger, and mechanical checks for the mistakes that were caught by the user last time.

## Boundary with cad-studio

- `cad-construction-pdf` owns the whole journey: brief → staged iteration → freeze → booklet.
  It delegates *modelling* to `cad-studio` (tool discovery, build123d, `design.md`, ledger,
  previews via `views.py`) and adds the contract, the gates, the checks and the generator.
- `cad-studio` gets one route line: construction-ready plans / booklet / phased build /
  "how do I build it" → `cad-construction-pdf`. Either name lands in the same pipeline.
- Scope: small timber structures (sheds, A-frames, gazebos, saunas, decks). No specialist
  knowledge is *encoded* for structural sizing, permits, masonry, electrics, plumbing, flues,
  solar — but the contract never blocks a part type: a brick course, a flue läpivienti or a
  solar mount is a `parts.csv` row with `kind`/`material` set and no cut angles, and the
  phase text says "per kit instructions / pro". A fixed disclaimer page states what is not
  engineered.

## Pipeline

```text
brief → shape → structure → joints → envelope → phases → freeze → booklet
```

| stage | what changes | gate (printed every time, user says ok or edits) |
|---|---|---|
| shape | footprint, pitch, heights, openings | one preview; clear widths / headroom / fit numbers |
| structure | members, spacing, stock sizes | member count, stock lengths, waste per stock size |
| joints | named joints, fasteners | joint detail sheet |
| envelope | floor/roof/wall build-ups, openings | m² per build-up vs. a box of the same floor area |
| phases | phase.step tags, steps, reveal flags, dims, batches | parts per phase sum to total; unmatched ids |
| freeze | no more geometry edits | all checks (below) pass or are shown |

- Stages collapse when the user skips ("just give me the shed"); gates still print.
- Never advances on its own. An edit after freeze reruns from the affected stage forward
  and rebuilds the booklet; one changelog line in `design.md` per accepted change.
- Ground work is a phase with generic country practice (Finnish routa text in the skill's
  `references/`), not a geotechnical design.

## Contract (design folder, alongside cad-studio's files)

The model script does not write tables; it **registers** parameters and parts through the
skill's `contract.py`, and everything tabular or visual derives from that registration.
This is what lets a generic renderer select solids by part id.

```python
from contract import Design, Part
d = Design("A-frame cabin", country="FI")
d.param("width", 3900, "ASSUMED", note="4.5 m stock")           # provenance on every input
d.param("pitch", 64, "KNOWN")
d.part(Part("rafter-L", solid, kind="timber", stock="48x198 C24", qty=8,
            cut_a=64, cut_b=26, phase="frame", step=1))
d.part(Part("deck", solid, kind="sheet", stock="22 mm lattialastulevy 600x2400", qty=12,
            phase="floor", step=4))
d.joint("B", title="apex gussets", location=(0, 0, 4289), clip=(600, 400, 500),
        parts=["rafter-L", "rafter-R", "gusset"], phase="frame",
        fasteners=[dict(type="5x40 screw", qty=24, washer=False, direction="both faces")])
d.emit()   # → parts.csv, joints.json, ledger block for design.md
```

Files in the design folder:

```text
parts.csv      emitted: id, name, kind, material, stock, length_mm, w_mm, h_mm, t_mm, qty,
               cut_a, cut_b, phase, step, notes  (dims from the solid's bounding box)
joints.json    emitted: id, title, location, clip, parts, phase, fasteners, howto, views?
phases.yaml    authored: ordered phases, each: id, title, weekend, prerequisites,
               steps (ordered list; text, hides_below?), dims, done_state, batch, views?
prices.csv     authored/filled: stock, unit (m|kpl|m2|pkt), price, currency, pack_qty,
               source, date, kind (LIST|QUOTE|USER)
book.yaml      page manifest
design.md      cad-studio's: brief, ledger (emitted block), derived files, changelog
```

Rules that make it unambiguous:

- `kind` is a **closed set** with defined behaviour: `timber` (stock + length, cut angles,
  cut list), `sheet` (stock + w/h/t, nesting), `hardware` (qty, hardware table), `loose`
  (qty + unit: bricks, wool packs, gravel m³), `service` (qty: delivery, rental). Anything
  unusual is one of these with free-text `material`/`stock` — a brick course is `loose`,
  a solar mount is `hardware`, a läpivienti kit is `hardware`, a pro's visit is `service`.
- `step` is the 1-based index into that phase's `steps` list in `phases.yaml`; visibility
  is inclusive; phases are ordered as listed.
- **Fasteners have one owner: joints.** `joints.json` carries usage (type, qty per joint
  instance, count of instances from `parts` qty); hardware totals per phase and in shopping
  are aggregated from joints plus explicit `kind=hardware` parts (non-joint hardware:
  anchors, hinges). No fastener is entered twice.
- **Prices key on `stock`.** The same string a part uses is the row key in `prices.csv`;
  precedence USER > QUOTE > LIST, newest wins within a kind. `unit` + `pack_qty` say how
  it is sold (m, kpl, m², pkt of 5.65 m²); the shopping derivation converts part
  quantities to purchasable units (packs and pieces round up; metres/m² are cut to size). Unmatched stock → unpriced (counted).
- Params carry provenance; a `stock` string that is ASSUMED is declared as
  `d.param("rafter_stock", "48x198 C24", "ASSUMED")` so check 4 can key it to a price row.

Derived, never authored:

- **Phase render** — solids of parts with phase order ≤ N and, within phase N, step ≤ the
  last step that is not `hides_below` (the reveal: floor frame without deck, battens without
  pelti), plus a small "phase complete" thumbnail. `dims` drawn in world mm on the named
  view via `views.py`.
- **Phase page text** — steps; hardware table (aggregated as above); joint thumbnails for
  joints with that phase; buy-before list from the batch.
- **Cut list** — per stock, per phase, totals; **nesting** for `sheet` parts: greedy strip
  nesting of the part's w×h into the stock sheet size parsed from `stock`, grain ignored in
  v1 (stated on the page).
- **Shopping** — parts × prices grouped by `batch`. Default batches: one timber delivery
  before the first framing phase, one hardware-store trip per phase; `batch` overrides.
- **Budget** — LIST column and "your variant" column (QUOTE/USER); unpriced items `—`.

## Booklet

`book.yaml` lists page types; each is a function over the contract files. Default list,
generated at freeze, editable by the user (reorder, drop, `- image: path, title` for custom):

```text
cover · overview · elevations · joints · parts · cutlist · budget · phases · shopping · assumptions
```

- `overview`: iso + facts box + contents. `elevations`: front/side/plan/rear, dimensioned.
- `joints`: one sheet per joint: views, fastener table, how-to. `parts`: one row per timber
  part with outline, length, angles, qty; sheet nesting. `cutlist`, `budget`, `shopping` as
  derived above. `phases`: one page per phase: reveal views in a row (wrap), dims, steps,
  hardware, joint thumbnails, buy-before. `assumptions`: ledger, open issues, disclaimer,
  and the checks box.
- Landscape A4, matplotlib, no LaTeX/cairo — `cad-studio/scripts/booklet.py` grows into
  the generator (it already does image pages and markdown tables). A project keeps no
  layout code; `book.py` per project disappears.

## Renders

Slots are named by role: `cover`, `overview-iso`, `elev-front`, `phase-2-plan`,
`joint-B-section`. A page never knows which backend filled a slot.

| backend | source | time | when |
|---|---|---|---|
| `lines` | `views.py` on the build123d model | seconds | every iteration; default for all slots |
| `shaded` | Blender Workbench/Eevee batch from the GLB, fixed camera per slot | minutes | after freeze on request; overview and phases |
| `photo` | Cycles scene via a scene skill (materials, site) | once | cover only, on request |

`render.py <backend> [slots…]` refills slots; dimensioned views always stay `lines`. Extra
views per phase/joint come from their `views` lists (`iso`, `plan`, `front`, `side`, `rear`,
`rear-iso`, `section`, or a `[pos, up]` camera).

## Pricing

`prices.csv` is the only budget input. Rows come from retailer scripts
(`cad-studio/references/sourcing-fi.md`: byggmax GraphQL, bauhaus Algolia → LIST), a quote
the user obtained (QUOTE), or a number stated in chat (USER, overrides LIST for that item).
Country from the brief; FI has scripts, others start with an empty ledger. Every row keeps
`source, date`.

## Checks at freeze (mechanical, all listed on the assumptions page)

Blocking — the PDF builds only as a `DRAFT` (watermark on every page, diagnostics page
first, no cut list/parts/shopping pages):

1. every `phase`/`step` in the registration exists in `phases.yaml` and every phase has
   parts; every joint's `parts` exist
2. any param with provenance INFERRED — cad-studio's rule "promote to KNOWN or ASSUMED
   before fabrication", enforced on the whole design rather than by tracing dataflow
3. a required field missing for its `kind` (timber without length, sheet without w/h/t)

Advisory — booklet builds, red checks box on the assumptions page:

4. every ASSUMED `stock` param has a `prices.csv` row or is flagged as unsourced
5. envelope m² per build-up vs. a plain box of the same floor area (ratio bound; the
   71 vs 63 m² wool catch)
6. every fastener `type` and every part `stock` has a price row; unpriced count and list

The skill reports which check failed and why, then stops at the gate.

## Testing

- Fixture: a 2 × 3 m lean-to shed (~20 parts, 3 phases, 2 joints) in the skill's `tests/`,
  built end-to-end to a PDF in seconds; asserts page count, slot files, check results.
- Migration: the a-frame-cabin design is brought onto the contract (parts tagged, joints
  exported, phases.yaml from phases.md, prices.csv from cutlist/envelope tables) as the
  real-world proof; its `book.py` and `cover_page.py` are retired once the manifest
  reproduces the booklet.

## Out of scope

Structural calcs and sign-off, permit logic, joinery/handbook knowledge (specialist skills),
a live viewer, per-design git, non-build123d kernels in v1 (the contract is kernel-neutral;
`views.py` is not).

## Consequences for files

- New `skills/cad-construction-pdf/`: `SKILL.md`, `references/` (contract, ground-work FI,
  fastening vocabulary FI), `scripts/` (`contract.py` validation + derivations, `render.py`,
  `book.py` manifest generator), `tests/lean-to/`.
- `skills/cad-studio/SKILL.md`: route line; "one document" output points here.
- `skills/cad-studio/scripts/booklet.py`: page types move to or are imported by the new
  generator (one owner; decided at plan time).
- `hawk-package.yaml`: register the skill.
- Dependency: the design venv (build123d, matplotlib) has no YAML parser today; the skill's
  bootstrap adds PyYAML to it, or the authored files switch to TOML (`tomllib`, stdlib).
  Decided at plan time; the contract's field names do not change either way.
