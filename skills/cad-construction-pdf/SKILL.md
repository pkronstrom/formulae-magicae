---
name: cad-construction-pdf
description: "Construction-ready plans for small timber builds — garden shed, A-frame cabin, gazebo, sauna, deck. Iterates the CAD model in stages with gates, then produces one booklet PDF: renders, dimensioned projections, joint details with fasteners, parts with cut angles, cut list, priced parts list for the user's country, and IKEA-style build phases with a render, dimensions, hardware and shopping list per phase. Use for /cad-construction-pdf, 'construction plans', 'build booklet', 'how do I build it', 'phased build', or when cad-studio reaches a timber build that must be built."
---

# Construction booklet for small timber builds

You run a short pipeline whose end product is one PDF a person can build from. Modelling
is delegated to the `cad-studio` skill (it discovers tools, keeps `design.md`, the
provenance ledger and the design folder); this skill adds the **contract** the model must
satisfy, the **gates** between stages, the **checks** at freeze, and the **generator**.
Nothing here is woodworking, structural or Blender knowledge — route to specialist skills
for that, and say what is not engineered.

```text
brief → shape → structure → joints → envelope → phases → freeze → booklet
```

Scripts beside this file (`scripts/`): `contract.py` (registration, derivations, checks),
`views.py` (build123d → PNG line views with world-mm dimensions), `render.py` (fills render
slots), `pages.py` + `book.py` (manifest → PDF). Venv needs `build123d matplotlib pyyaml`
— add `pyyaml` to an existing cad-studio venv with `uv pip install pyyaml`.

## 0. Enter

- New design → `cad-studio` steps 1–2 (path proposal, `list.sh`, reuse). Existing design →
  read `design.md` and, if present, `parts.csv`/`phases.yaml`: the pipeline resumes at the
  first stage whose gate is not met, never from conversation memory.
- Country from the brief (default FI, whose retailers answer scripts — see cad-studio's
  `references/sourcing-fi.md`). Other countries start with an empty price ledger.
- Say the plan in one line: which stages are left and what the booklet will contain.

## 1. Stages and gates

Every stage ends with a gate: a preview plus the numbers that stage is about. The user
says ok or edits a parameter; **never advance on your own**. Stages collapse when the user
skips ("just give me the shed"), gates still print.

| stage | edits | gate prints |
|---|---|---|
| shape | footprint, pitch, heights, openings | `overview-iso` + `elev-*`; clear widths, headroom, fit numbers |
| structure | members, spacing, stock sizes | member counts, stock lengths, waste per stock |
| joints | named joints, fasteners, how-to | `joint-*` sheets |
| envelope | floor/roof/wall build-ups, openings | m² per build-up vs. a plain box of the same floor area |
| phases | `phase`/`step` tags, `phases.yaml` (steps, `hides_below`, dims, batches, views) | parts per phase sum to total; unmatched ids |
| freeze | no more geometry | all checks; blocking failures → DRAFT |

The model registers everything through `contract.py` — parameters with provenance, parts
with their solids and phase/step tags, joints with fasteners — and `emit()` writes
`parts.csv` and `joints.json`. `references/contract.md` is the full contract (fields,
`kind` rules, ownership rules, checks). Read it before writing the first model line.

Iteration is a parameter edit → rerun from that stage → `render.py lines` → gate. One
changelog line in `design.md` per accepted change (cad-studio convention).

## 2. Phases are part of the model

`phases.yaml` is authored with the user, after the structure holds:

- weekends or days, in build order; prerequisites (deliveries, curing, weather); done-state
- ordered steps; a step that covers work below it (deck, pelti, cladding) is `hides_below: true`
  so the phase drawing shows the **reveal** state, not the finished one
- `dims`: the setting-out numbers for that weekend (pier centres, k600, batten pitch)
- `views`: default `iso · plan · front`; crucial phases list more (`rear-iso`, `section`, a camera)
- `batch`: which shopping trip; default is one timber delivery before framing, one hardware
  trip per phase

Fasteners live only on joints (type, size, qty, washer, direction, tool, how-to); per-phase
hardware tables and shopping aggregate from them. Ground work is a phase citing
`references/groundwork-fi.md`; hardware names come from `references/fastening-fi.md`. A
brick course, a flue läpivienti, a solar mount are ordinary parts (`loose`/`hardware`) whose
step text says "per kit instructions / pro" — never refuse a part type.

## 3. Prices

`prices.csv` is the only budget input, keyed by the same `stock` string the parts use.
Fill LIST rows with the retailer scripts cad-studio names; a quote the user got is QUOTE;
a number said in chat ("pelti 12 €/m²") becomes a USER row, which wins. Unpriced items are
shown as `—` and counted, never zero. Before pricing: any ASSUMED product spec gets one
lookup; every quantity total is sanity-checked against a plain box of the same floor area.

## 4. Freeze and booklet

```sh
python render.py <design folder> lines       # all slots → <design>/preview/ (model from design.md Authoritative:)
python book.py <design folder>               # book.yaml (generated on first run) → outputs/<name>.pdf
```

Checks (`contract.checks`) run inside `book.py`. Blocking — unmatched phase/step/joint ids,
any INFERRED parameter, a required field missing for its `kind` — build a **DRAFT** with a
watermark and a diagnostics page and no fabrication pages; say which check failed and why,
fix at the gate, rebuild. Advisory — unsourced ASSUMED stock, envelope ratio out of bound,
unpriced items — land in a red box on the assumptions page.

Default pages: cover · overview · elevations · joints · parts · cutlist · budget · phases ·
shopping · assumptions. Edit `book.yaml` to reorder, drop, or add `- image: path, title`.
A project keeps no layout code.

Render ladder, upgradable after freeze without touching pages: `lines` (default, seconds)
→ `shaded` (`render.py <design> shaded overview-iso phase-*`, Blender Workbench,
minutes) → `photo` (a scene skill renders the cover; drop it in as `preview/cover.png`).
Dimensioned views always stay `lines`.

Open the PDF, look at three pages (cover, one phase, the budget), then record
`outputs/<name>.pdf` under Derived in `design.md` with the date.

## What this skill refuses to become

A handbook. Joinery rules, member sizing, U-values, permits belong to specialist skills or
a builder; the booklet's disclaimer page says so. If a request needs knowledge that no
active skill has, say that and offer to find one rather than inventing it.
