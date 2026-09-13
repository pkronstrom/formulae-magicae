"""views.py — build123d shape → PNG line views with matplotlib. No cairo, no viewer app.

    import sys; sys.path.insert(0, "<cad-studio>/scripts"); from views import render_views, draw
    render_views(shape, "preview", dpi=220)            # preview/{iso,front,side,plan,rear,rear-iso}.png
    fig, ax = plt.subplots(); draw(ax, shape, "front", world=("X", "Z"))   # plotted mm == world mm → dims line up

Traps this encodes (each cost a round-trip when first met):
  - Shape.project_to_viewport() takes a camera POSITION; a unit vector lands inside the model. Use FAR.
  - Plot visible edges only; hidden lines of a repeated frame are unreadable.
  - The projection is centred on the shape: world=("X","Z") shifts plotted coords back to world mm.
  - Clipped solids yield zero-length edges → skip length < 0.5 and wrap position_at().
  - qlmanage crops PNGs square; cairosvg needs libcairo. Hence matplotlib.
Axes convention: X across, Y along, Z up.
"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from build123d import Compound

FAR = 40000
VIEWS = {  # name → (camera position, up, world axes for dimensioning or None)
    "iso":      ((FAR, -FAR*1.3, FAR*0.7), (0, 0, 1), None),
    "rear-iso": ((-FAR, FAR*1.3, FAR*0.7), (0, 0, 1), None),
    "front":    ((0, -FAR, 0), (0, 0, 1), ("X", "Z")),
    "rear":     ((0, FAR, 0),  (0, 0, 1), ("X", "Z")),
    "side":     ((FAR, 0, 0),  (0, 0, 1), ("Y", "Z")),
    "plan":     ((0, 0, FAR),  (0, 1, 0), ("X", "Y")),
}

def draw(ax, shape, view, hidden=False, lw=0.9, world=None):
    """Draw `shape` into `ax` from VIEWS[view] (or a (pos, up) tuple). Returns nothing; ax is equal-aspect, axes off."""
    pos, up, w = VIEWS[view] if isinstance(view, str) else (view[0], view[1], None)
    world = world if world is not None else w
    vis, hid = shape.project_to_viewport(pos, viewport_up=up)
    ox = oy = 0.0
    if world:
        vb, wb = Compound(children=list(vis)).bounding_box(), shape.bounding_box()
        wc = {a: (getattr(wb.min, a) + getattr(wb.max, a)) / 2 for a in world}
        ox = wc[world[0]] - (vb.min.X + vb.max.X) / 2
        oy = wc[world[1]] - (vb.min.Y + vb.max.Y) / 2
    def plot(edges, **kw):
        for e in edges:
            if e.length < 0.5:
                continue
            try:
                pts = [e.position_at(i / 12) for i in range(13)]
            except Exception:
                continue
            ax.plot([q.X + ox for q in pts], [q.Y + oy for q in pts], **kw)
    plot(vis.edges(), color="black", lw=lw)
    if hidden:
        plot(hid.edges(), color="grey", lw=0.4, ls=(0, (3, 3)))
    ax.set_aspect("equal"); ax.axis("off")

def render_views(shape, outdir, names=("iso", "front", "side", "plan"), dpi=220, figsize=(16, 12)):
    import os; os.makedirs(outdir, exist_ok=True)
    out = []
    for name in names:
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        draw(ax, shape, name, lw=0.7)
        path = f"{outdir}/{name}.png"
        fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig); out.append(path)
    return out

def dim_h(ax, x0, x1, y, text, off=60):
    """Horizontal dimension line below y (off>0) with extension lines."""
    ax.annotate("", (x0, y - off), (x1, y - off), arrowprops=dict(arrowstyle="<->", lw=0.8, shrinkA=0, shrinkB=0), annotation_clip=False)
    for x in (x0, x1): ax.plot([x, x], [y, y - off - 20], color="grey", lw=0.4)
    ax.text((x0 + x1) / 2, y - off - 25, text, ha="center", va="top", fontsize=8)

def dim_v(ax, x, y0, y1, text, off=60):
    ax.annotate("", (x + off, y0), (x + off, y1), arrowprops=dict(arrowstyle="<->", lw=0.8, shrinkA=0, shrinkB=0), annotation_clip=False)
    for y in (y0, y1): ax.plot([x, x + off + 20], [y, y], color="grey", lw=0.4)
    ax.text(x + off + 25, (y0 + y1) / 2, text, ha="left", va="center", fontsize=8, rotation=90)
