# cad-construction-pdf — implementation plan

Spec: `2026-09-13-cad-construction-pdf-design.md`. One session, sequential chunks, each
ends with its check run. Full end-to-end runs use a venv with build123d + matplotlib +
pyyaml (the a-frame venv, `~/Designs/buildings/a-frame-cabin/.venv`, plus `pyyaml`);
repo tests under system `python3 -m pytest` cover the pure-Python core with stub solids and
`importorskip` the rest.

## Decisions taken here (spec left them to plan time)

- **YAML**: PyYAML, imported lazily in `contract.load_phases()`; core is stdlib-only so the
  repo tests run without it. The skill's bootstrap line adds pyyaml to the design venv.
- **One owner for drawing/booklet code, no sibling imports** (repo rule: plugins are
  standalone; `tests/test_repository.py`): `cad-studio/scripts/views.py` and `booklet.py`
  **move** into `cad-construction-pdf/scripts/` (`views.py`, `pages.py`). cad-studio keeps
  `bauhaus.py` and refers to this skill *by name*: preview PNGs "via the
  cad-construction-pdf skill's views.py when active, else a dimension table"; "one
  document" and "timber build" outputs route here.
- **Model entry point**: the model module exposes `def design() -> Design`. `render.py`
  and `book.py` take the design folder (default: cwd), resolve the model from the
  `Authoritative:` line of `design.md`, import it by path and call `design()`.
  `cabin.py`-style top-level scripts wrap their body in that function.
- **Units**: `Part.unit` (timber `m`, sheet/hardware/service `kpl`, loose `kpl|m2|m3|pkt`)
  is emitted; a price row's `unit` must be `m`, `kpl`, `m2`, `m3` or `pkt`, and `pack_qty`
  says how much of the *part's* unit one purchasable unit holds (a wool `pkt` of 5.65 m²).
  Timber `m` = Σ length_mm × qty / 1000; sheet `m2` = w×h×qty; mismatched units → unpriced.
- **Budget** returns per stock: quantity, purchasable units, LIST price, variant price
  (QUOTE/USER if present), both totals; the page shows both columns.
- **Slots** are enumerated from `phases.yaml`/`joints.json` `views` lists. `section` clips
  the compound with a plane through the joint location (joints) or the model centre
  (phases) and draws the `side` view; a `[[x,y,z],[ux,uy,uz]]` entry is passed to
  `views.draw` as a camera tuple.
- **Solid duck type**: contract needs only `.bounding_box()` with `.min/.max/.size` (build123d
  shape API); tests use a stub. `render.py` needs real build123d shapes.
- **`shaded` backend v1**: export the slot's filtered compound to GLB (build123d
  `export_gltf`), run `blender -b --factory-startup -P shaded.py -- glb out.png view` with
  Workbench engine, fixed camera per named view. Dimensioned views refuse `shaded`.
  `photo` is not a script: the skill routes to a scene skill and the result is dropped in
  as `preview/cover.png`.

## Chunks

### 1 — Skill skeleton and routing
Files: `skills/cad-construction-pdf/SKILL.md`, `references/contract.md` (the file/field
tables from the spec, the `kind` rules, the checks), `references/groundwork-fi.md`
(routa practice text that phases can cite), `references/fastening-fi.md` (hardware
vocabulary: kulmarauta, prikka, ruuvi sizes, kansiruuvi vs. terassiruuvi — names only, no
engineering), `LICENSE` (copy); catalog: `hawk-package.yaml`, `.claude-plugin/marketplace.json`,
`README.md` table row + install command, `tests/test_repository.py` `EXPECTED_SKILLS`;
`cad-studio/SKILL.md` route line + "one document"/"timber build" → here, preview by name.
Check: `python3 -m pytest tests/test_repository.py -q`.

### 2 — Lean-to fixture (before the code that consumes it)
`tests/fixtures/lean-to/`: `design.md` (Authoritative: leanto.py), `leanto.py` (2 × 3 m
lean-to: 4 posts, 2 beams, 5 rafters, deck sheets, roof sheets, gravel as `loose m3`, wool
as `loose m2` priced per `pkt`, bricks `loose kpl`; 3 phases: ground, frame, roof; 2 joints:
post-beam, rafter-beam; one phase with `views: [iso, plan, section]`), `phases.yaml`,
`prices.csv` (LIST rows + one USER override), expected slot list. Solids are build123d
boxes when available, else stubs — the module builds either.

### 3 — `scripts/contract.py`
`Design(name, country)`, `.param(name, value, provenance, note=, stock=False)`,
`.part(Part(...))`, `.joint(...)`, `.emit(folder)` → `parts.csv`, `joints.json`,
`## Provenance` block text for `design.md`. `load_phases(path)`, `load_prices(path)`.
Derivations (pure functions over the loaded data): `visible_parts(design, phases, N)`
(reveal rule), `cutlist(design, phases)`, `hardware(design, phases)` (joint aggregation +
hardware parts), `nesting(design)` (greedy strip), `budget(design, prices)` (precedence,
unit conversion, unpriced list), `shopping(design, phases, prices)` (batches),
`checks(design, phases, prices)` → list of `(id, blocking, ok, message)`.
Check: `tests/test_cad_construction_pdf.py` with stub solids: emit round-trip, reveal
filter (deck hidden), fastener aggregation (no double count), price precedence and pack
rounding, nesting count, each check's fail and pass case.

### 4 — `scripts/render.py`
`render.py [<design>] <backend> [slot…]`, default all slots for `lines`: `overview-iso`,
`elev-{front,side,plan,rear}`, `phase-<id>-<view>` (reveal state + dims), `phase-<id>-done`
thumbnail, `joint-<id>-<view>` (clipped by `clip` box, using views.py's clipped-solid
trap handling), `part-<id>` outlines for timber parts. `shaded.py` Blender script beside
it. Slot files under `<design>/preview/`.
Check: run on the lean-to fixture in the venv; every expected slot file exists and is
non-trivial (>2 KB); open the phase PNGs and look at them once.

### 5 — `scripts/book.py` + `scripts/pages.py`
`book.py <design folder>` reads `book.yaml` (generated with the default list on first run),
builds `outputs/<name>.pdf`. Page functions: cover, overview, elevations, joints, parts,
cutlist, budget, phases, shopping, assumptions, image. Blocking check failure → DRAFT
watermark on every page, diagnostics page first, fabrication pages skipped.
Check: fixture PDF builds; `pdfinfo` page count matches manifest; rasterise 3 pages and
look; a fixture with an INFERRED param builds as DRAFT with the expected page count.

### 6 — A-frame migration (proof)
In `~/Designs/buildings/a-frame-cabin/`: wrap `cabin.py` into `design()` with params and
`Part` registration (phase/step tags per the existing phases.md), joints from the joint
sheet code, `phases.yaml` from `phases.md`, `prices.csv` from cutlist/envelope tables +
the user's stated prices as USER rows. Run render + book; compare against the 21-page
booklet; retire `book.py`/`cover_page.py` once equivalent; changelog line in `design.md`.
Check: booklet builds without DRAFT; phase pages show reveal state and dims; budget totals
within rounding of the previous booklet's numbers (differences explained).

### 7 — Review and commit
codex review on the diff (`/rev1`), fix, commit per chunk or as one commit series.
