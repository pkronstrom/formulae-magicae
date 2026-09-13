# Project layout and provenance

One directory per physical thing under `~/Designs/<type>/<name>/` (root overridable with
`CAD_STUDIO_HOME`). The router only needs the relationships below to be findable;
specialist tools decide the actual filenames and formats. `list.sh` beside `SKILL.md`
reads the `Authoritative:` line and the newest changelog date (first entry — changelog is
newest-first) of every `design.md`, at any depth below the root.

```text
~/Designs/
  buildings/gazebo/
    design.md          brief, current level, authoritative file, provenance ledger, changelog
    gazebo.py          parametric source (build123d / Replicad .ts / FreeCAD .FCStd …)
    gazebo.step        exchange model
    drawings/          SVG/PDF orthographic views, sections
    outputs/           cut list, BOM, STL/3MF, GLB for scenes
    references/        photos, sketches, catalogue pages

  sites/yard/
    design.md
    site.py | scene.blend | scene.html
    references/        survey, photos, house footprint
    outputs/           renders, placement variants

  vehicles/van/
    design.md          the envelope (interior dims, wheel arches, door openings) is the KNOWN block
    van-envelope.py
    table-drawers/     a nested project whose brief cites ../design.md as its constraint
```

## design.md

Small, always current. Sections:

```markdown
# Gazebo

Authoritative: gazebo.py → gazebo.step
Derived: outputs/gazebo.glb (for yard scene, 2026-09-13; regenerate after edits)

## Brief
3 × 3 m, hip roof, 45×145 timber, no floor. Must clear the apple tree.

## Provenance
KNOWN     footprint 3000 × 3000 mm (user)
KNOWN     post height 2200 mm (user)
MEASURED  —
INFERRED  roof pitch ≈ 25° from the reference photo
ASSUMED   timber 45 × 145 mm (common stock; confirm before cut list)
DERIVED   rafter length 1830 mm

## Changelog                (newest first)
2026-09-13  first parametric model; GLB exported for yard placement
```

Provenance vocabulary:

- **KNOWN** — stated by the user.
- **MEASURED** — reliably extracted from reference data (scale bar, EXIF + known object).
- **INFERRED** — estimated from proportions in photos/sketches.
- **ASSUMED** — chosen because information is missing.
- **DERIVED** — computed from the above; inherits the weakest input's confidence.

A cut list, STL or other build output may rest only on KNOWN, MEASURED and explicitly
accepted ASSUMED values. An INFERRED value never feeds fabrication: before exporting, ask
the user to measure it (→ KNOWN) or accept it as an assumption (→ ASSUMED), and record the
promotion in the ledger.

## Cross-project references

Point, don't copy. The yard `design.md` lists `../../buildings/gazebo/outputs/gazebo.glb` with the
date it was exported; if the gazebo source changes later, the scene regenerates its
copy. The gazebo's own fabrication model never moves and is never edited from the scene
side.
