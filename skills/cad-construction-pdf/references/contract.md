# The contract

What the model registers, what is emitted, what is authored, what is derived. Everything
the booklet shows comes from these files; nothing is typed into a layout script.

## Registration (in the model module, `def design() -> Design`)

```python
import sys; sys.path.insert(0, "<cad-construction-pdf>/scripts")
from contract import Design, Part

def design():
    d = Design("Lean-to shed", country="FI")
    W = d.param("width", 2000, "KNOWN")                       # value returned, provenance recorded
    d.param("post_stock", "98x98 C24", "ASSUMED", stock=True) # stock params key into prices.csv
    ...build solids with build123d...
    d.part(Part("post", [post_at(x, y) for x, y in corners], kind="timber", stock="98x98 C24",
                qty=4, length_mm=2200, phase="frame", step=1))  # a list of solids = the instances
    d.joint("A", "post to beam", location=(0, 0, 2200), clip=(400, 300, 300),
            parts=["post", "beam"], phase="frame",
            fasteners=[dict(type="M10x120 bolt", qty=2, washer=True, direction="through", tool="19 mm")],
            howto="Two bolts through post and beam, prikka both sides, tighten after plumbing.")
    return d
```

- `param(name, value, provenance, note="", stock=False)` — provenance is one of
  KNOWN / MEASURED / INFERRED / ASSUMED. INFERRED blocks freeze: promote it (measure → KNOWN,
  accept → ASSUMED) first. `stock=True` marks a product spec so check 4 can key it to a
  price row.
- `Part(id, solid, kind, stock, qty, phase, step, length_mm=None, cut_a=None, cut_b=None,
  material="", notes="", unit=None, w_mm/h_mm/t_mm=None)` — dims not given are taken
  from `solid.bounding_box()`. `solid` may be a build123d shape or a list of shapes (one
  per instance). `unit` defaults per kind (timber `m`, sheet/hardware/service `kpl`);
  `loose` parts must state it (`kpl`, `m2`, `m3`, `pkt`).
- `joint(id, title, location, clip, parts, phase, fasteners, howto="", views=None)`.
- `emit(folder)` → `parts.csv`, `joints.json`, `params.json`, and returns the
  `## Provenance` block for `design.md`. `render.py` calls it, so the files are always
  current after a render.

## `kind` — closed set, each with defined behaviour

| kind | required | goes to |
|---|---|---|
| `timber` | stock, length_mm (cut_a/cut_b, default 90) | cut list per stock, parts sheet outlines |
| `sheet` | stock, w_mm, h_mm, t_mm | nesting into the stock sheet size parsed from `stock` (e.g. `… 1220x2440`) |
| `hardware` | qty | hardware table, shopping (non-joint hardware: anchors, hinges, kits) |
| `loose` | qty, `unit` (kpl, m2, m3, pkt) | shopping (wool, gravel, bricks) |
| `service` | qty | shopping (delivery, rental, a pro's visit) |

Free text goes in `material`, `stock`, `notes`. A brick course is `loose`; a solar mount
or a flue läpivienti is `hardware`; a saha delivery is `service`.

## Emitted files

```text
parts.csv    id, name, kind, material, stock, unit, length_mm, w_mm, h_mm, t_mm, qty, cut_a, cut_b, phase, step, notes
joints.json  [{id, title, location, clip, parts, phase, fasteners[{type, qty, washer, direction, tool}], howto, views}]
params.json  {name, country, params: {name: {value, provenance, note, stock}}}
```

## Authored files

```yaml
# phases.yaml — ordered; ids are what parts.csv `phase` refers to; `step` is the 1-based index into steps
- id: ground
  title: Ground and piers
  weekend: 1
  prerequisites: [gravel delivered, dry weekend]
  steps:
    - text: Strip topsoil 0.5 m beyond the footprint; 300 mm murske in two lifts, compacted.
    - text: Set out pier centres with string lines; check diagonals.
    - text: Cast footings, then two courses of Leca on mortar; tops level.
  dims:
    - {view: plan, axis: x, from: 0, to: 2000, label: "2000 c/c"}
  done_state: Level pier tops, water runs away. Cure a week.
  batch: 1
  views: [iso, plan]              # default [iso, plan, front]
- id: floor
  ...
  steps:
    - text: Joists at k600 between the rims.
    - text: Screw the 22 mm deck.
      hides_below: true           # phase drawing shows the state before this step
```

```text
prices.csv   stock, unit (m|kpl|m2|pkt|m3), price, currency, pack_qty, source, date, kind (LIST|QUOTE|USER)
book.yaml    title + ordered page list (generated with defaults on first book.py run)
```

## Ownership rules

- Fasteners: only on joints. A joint's `qty` is per instance; instances = the qty of the
  first part in `parts`. Hardware totals = Σ joints + explicit `kind=hardware` parts.
- Prices: key = exact `stock` string. Precedence USER > QUOTE > LIST; newest date wins
  within a kind. A price row's `unit` must equal the part's unit, or be `pkt` (then
  `pack_qty` = how much of the part's unit one pack holds, e.g. 5.65 m²), or be `m2` for a
  sheet part (Σ w × h × qty over the parts using that stock). Packs and pieces round up; m, m² and m³ are sold cut to size and stay exact. Anything else → unpriced, never zero.
- Visibility for phase N = parts with phase order < N, plus phase N parts whose `step` ≤
  the last step of N that is not `hides_below`. The "done" thumbnail shows all of N.
- Sheet nesting: greedy strip nesting, grain ignored (the page says so).

## Checks at freeze

| # | blocking | check |
|---|---|---|
| 1 | yes | every part `phase` exists in phases.yaml and 1 ≤ `step` ≤ len(steps); every phase has parts; every joint's parts exist |
| 2 | yes | no parameter is INFERRED |
| 3 | yes | required fields present for the part's `kind` |
| 4 | no | every ASSUMED `stock=True` param has a price row |
| 5 | no | no `m2` stock exceeds 4 × the floor area (`footprint_m2` param, else the plan bbox) |
| 6 | no | every part `stock` and fastener `type` has a price row; unpriced list |

Blocking failure → DRAFT booklet (watermark, diagnostics page, no cut list / parts /
shopping pages). Advisory → red box on the assumptions page.

## Render slots (`preview/<slot>.png`)

`cover`, `overview-iso`, `elev-front|side|plan|rear`, `phase-<id>-<view>`, `phase-<id>-done`,
`joint-<id>-<view>`, `part-<id>`. Views: `iso rear-iso front rear side plan section` or a
`[[x,y,z],[ux,uy,uz]]` camera. Backends: `lines` (all slots), `shaded` (overview, phase,
joint), `photo` (cover, produced by a scene skill). Dimensioned slots are always `lines`.
