"""render.py — fill render slots for a design folder.

    python render.py [<design folder>] lines [slot …]        # default: every slot; folder defaults to cwd
    python render.py [<design folder>] shaded [slot …]       # Blender Workbench from a GLB per slot (overview/phase/joint only)

Slots (preview/<slot>.png): overview-iso · elev-front|side|plan|rear · phase-<id>-<view> · phase-<id>-done ·
joint-<id>-<view> · part-<id>. Views: iso rear-iso front rear side plan section, or a [[x,y,z],[ux,uy,uz]] camera.
Slot list comes from phases.yaml / joints.json `views`; dimensioned slots (elev-*, phase-*) always use `lines`.
"""
import fnmatch, json, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from contract import Design, load_phases, visible, DEFAULT_VIEWS  # noqa: E402

AXES = {"front": ("X", "Z"), "rear": ("X", "Z"), "side": ("Y", "Z"), "plan": ("X", "Y")}
DIM_OFF = 120


def compound(parts):
    from build123d import Compound
    solids = [s for p in parts for s in p.solids()]
    return Compound(children=solids) if solids else None


def section_of(shape, x=None):
    """Keep the half with X ≤ x (default: bbox centre) so the `side` camera at +X sees the cut face."""
    from build123d import Box, Location
    b = shape.bounding_box()
    x = (b.min.X + b.max.X) / 2 if x is None else x
    size = max(b.size.X, b.size.Y, b.size.Z) * 3
    away = Box(size, size, size).moved(Location((x + size / 2, (b.min.Y + b.max.Y) / 2, (b.min.Z + b.max.Z) / 2)))
    return _solid(shape.cut(away))


def clip_to(shape, location, clip):
    from build123d import Box, Location
    box = Box(*clip).moved(Location(tuple(location)))
    return _solid(shape.intersect(box))


def _solid(result):
    """Boolean results may come back as a ShapeList; wrap into one Compound."""
    from build123d import Compound, ShapeList
    if isinstance(result, ShapeList):
        result = Compound(children=list(result))
    if result is None or not result.bounding_box().size.length:
        return None
    return result


def draw_dims(ax, view, dims, shape):
    from views import dim_h, dim_v
    if view not in AXES:
        return
    hx, vy = AXES[view]
    b = shape.bounding_box()
    lo = {"X": b.min.X, "Y": b.min.Y, "Z": b.min.Z}; hi = {"X": b.max.X, "Y": b.max.Y, "Z": b.max.Z}
    k = 0
    for d in dims:
        if d.get("view", "plan") != view:
            continue
        a = d["axis"].upper(); k += 1
        if a == hx:
            dim_h(ax, d["from"], d["to"], lo[vy], d.get("label", f"{d['to'] - d['from']:.0f}"), off=DIM_OFF * k)
        elif a == vy:
            dim_v(ax, hi[hx], d["from"], d["to"], d.get("label", f"{d['to'] - d['from']:.0f}"), off=DIM_OFF * k)


def overall_dims(view):
    """Extent dimensions for an elevation: the two world axes of the view."""
    hx, vy = AXES[view]
    return hx, vy


def render_lines(ax, shape, view, dims=(), extents=False):
    """Draw `shape` in `view` (name, 'section', or camera tuple) with optional dims / overall extents."""
    from views import draw, dim_h, dim_v
    if view == "section":
        shape = section_of(shape); view = "side"
    world = AXES.get(view) if isinstance(view, str) else None
    draw(ax, shape, view if isinstance(view, str) else tuple(view), world=world, lw=0.7)
    if world:
        draw_dims(ax, view, dims, shape)
        if extents:
            b = shape.bounding_box()
            lo = {"X": b.min.X, "Y": b.min.Y, "Z": b.min.Z}; hi = {"X": b.max.X, "Y": b.max.Y, "Z": b.max.Z}
            hx, vy = world
            dim_h(ax, lo[hx], hi[hx], lo[vy], f"{hi[hx] - lo[hx]:.0f}", off=DIM_OFF * (len(dims) + 1))
            dim_v(ax, hi[hx], lo[vy], hi[vy], f"{hi[vy] - lo[vy]:.0f}", off=DIM_OFF * (len(dims) + 1))


_SECTION = re.compile(r"(\d{2,3})\s*[x×]\s*(\d{2,3})")


def section_of_stock(p):
    """(thickness, depth) from the stock string, else from the solid's two smallest bbox dims."""
    m = _SECTION.search(p.stock or "")
    if m:
        a, b = int(m.group(1)), int(m.group(2)); return min(a, b), max(a, b)
    if p.solids():
        b = p.solids()[0].bounding_box(); d = sorted((b.size.X, b.size.Y, b.size.Z))
        return d[0], d[1]
    return 48, 98


def draw_part_schematic(ax, p):
    """Side view of a timber part as a quadrilateral: long edge = length_mm, ends cut at cut_a / cut_b to the long edge."""
    import math
    from views import dim_h, dim_v
    t, depth = section_of_stock(p); L = p.length_mm or 0
    a, b = math.radians(p.cut_a or 90), math.radians(p.cut_b or 90)
    # long edge along the bottom from (0,0) to (L,0); the top edge is shortened by depth/tan(angle) at each end
    da = depth / math.tan(a) if abs(math.tan(a)) > 1e-6 else 0
    db = depth / math.tan(b) if abs(math.tan(b)) > 1e-6 else 0
    xs = [0, L, L - db, da]; ys = [0, 0, depth, depth]
    ax.fill(xs, ys, facecolor="#f3ead8", edgecolor="black", lw=1.0)
    dim_h(ax, 0, L, 0, f"{L:.0f} (long edge)", off=depth * 0.8 + 40)
    dim_v(ax, L, 0, depth, f"{depth:g}", off=60)
    if (p.cut_a or 90) != 90:
        ax.text(da / 2, depth + 30, f"{p.cut_a:g}°", ha="center", va="bottom", fontsize=8)
    if (p.cut_b or 90) != 90:
        ax.text(L - db / 2, depth + 30, f"{p.cut_b:g}°", ha="center", va="bottom", fontsize=8)
    ax.set_xlim(-L * 0.05, L * 1.12); ax.set_ylim(-depth * 1.6 - 60, depth * 1.6 + 60)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"{p.name} — {p.stock} · {p.qty} pcs · {L:.0f} mm · section {t:g}×{depth:g} · cuts {p.cut_a:g}° / {p.cut_b:g}°", fontsize=9)


def slot_plan(design, phases):
    """Ordered list of (slot, kind, payload)."""
    slots = [("overview-iso", "all", dict(view="iso"))]
    slots += [(f"elev-{v}", "all", dict(view=v, extents=True)) for v in ("front", "side", "plan", "rear")]
    for ph in phases:
        for v in ph.get("views") or DEFAULT_VIEWS:
            name = v if isinstance(v, str) else "cam"
            slots.append((f"phase-{ph['id']}-{name}", "phase", dict(phase=ph["id"], view=v, dims=ph.get("dims", []))))
        slots.append((f"phase-{ph['id']}-done", "phase", dict(phase=ph["id"], view="iso", done=True)))
    for j in design.joints:
        for v in j.get("views") or ["iso", "section"]:
            name = v if isinstance(v, str) else "cam"
            slots.append((f"joint-{j['id']}-{name}", "joint", dict(joint=j, view=v)))
    for p in design.parts:
        if p.kind == "timber" and p.length_mm:
            slots.append((f"part-{p.id}", "part", dict(part=p)))
    return slots


def shape_for(design, phases, kind, payload):
    if kind == "all":
        return compound(design.parts)
    if kind == "phase":
        return compound(visible(design, phases, payload["phase"], done=payload.get("done", False)))
    if kind == "joint":
        j = payload["joint"]
        shp = compound([design.by_id(pid) for pid in j["parts"] if design.by_id(pid)])
        return clip_to(shp, j["location"], j["clip"]) if shp is not None else None
    if kind == "part":
        return payload["part"]


def render_slot_lines(design, phases, out, slot, kind, payload):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shape = shape_for(design, phases, kind, payload)
    if shape is None:
        print(f"  {slot}: nothing to draw", file=sys.stderr); return None
    small = kind == "part" or slot.endswith("-done")
    fig, ax = plt.subplots(figsize=(6, 4) if small else (11, 7.5), dpi=150)
    if kind == "part":
        draw_part_schematic(ax, payload["part"])
    elif kind == "joint":
        view = payload["view"]
        if view == "section":
            shape = section_of(shape); view = "side"     # through the middle of the clipped detail
            if shape is None:
                plt.close(fig); print(f"  {slot}: section is empty", file=sys.stderr); return None
        render_lines(ax, shape, view)
    else:
        render_lines(ax, shape, payload["view"], dims=payload.get("dims", []), extents=payload.get("extents", False))
    path = out / f"{slot}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white", pad_inches=0.15); plt.close(fig)
    return path


def render_slot_shaded(design, phases, out, slot, kind, payload):
    if kind in ("part",) or slot.startswith("elev-") or payload.get("view") == "section" or not isinstance(payload.get("view"), str):
        print(f"  {slot}: stays lines (dimensioned/section/part)", file=sys.stderr); return None
    from build123d import export_gltf
    shape = shape_for(design, phases, kind, payload)
    if shape is None:
        return None
    with tempfile.TemporaryDirectory() as td:
        glb = Path(td) / "slot.glb"
        export_gltf(shape, str(glb), binary=True)
        path = out / f"{slot}.png"
        r = subprocess.run(["blender", "-b", "--factory-startup", "-P", str(HERE / "shaded.py"), "--",
                            str(glb), str(path), payload["view"]], capture_output=True, text=True)
        if r.returncode != 0 or not path.exists():
            print(f"  {slot}: blender failed\n{r.stderr[-800:]}", file=sys.stderr); return None
    return path


def main(argv):
    args = [a for a in argv if a not in ("lines", "shaded")]
    backend = next((a for a in argv if a in ("lines", "shaded")), "lines")
    folder = Path(args[0]) if args and Path(args[0]).is_dir() else Path.cwd()
    patterns = args[1:] if args and Path(args[0]).is_dir() else args
    design = Design.from_model(folder)
    design.emit(folder)
    phases = load_phases(folder / "phases.yaml") if (folder / "phases.yaml").exists() else []
    out = folder / "preview"; out.mkdir(exist_ok=True)
    fn = render_slot_lines if backend == "lines" else render_slot_shaded
    done = 0
    for slot, kind, payload in slot_plan(design, phases):
        if patterns and not any(fnmatch.fnmatch(slot, pat) for pat in patterns):
            continue
        if fn(design, phases, out, slot, kind, payload):
            done += 1
    print(f"{done} slots → {out} ({backend})")


if __name__ == "__main__":
    main(sys.argv[1:])
