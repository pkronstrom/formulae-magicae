"""Lean-to shed fixture: 2 × 3 m, four posts, two beams, five rafters, deck + roof sheets.
Builds real build123d boxes when the library is present, stub boxes otherwise (contract needs only bounding_box)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "skills" / "cad-construction-pdf" / "scripts"))
from contract import Design, Part

try:
    from build123d import Box, Location, Compound
    def box(dx, dy, dz, x=0, y=0, z=0):
        return Box(dx, dy, dz).moved(Location((x + dx / 2, y + dy / 2, z + dz / 2)))
except ImportError:
    class _V:
        def __init__(self, x, y, z): self.X, self.Y, self.Z = x, y, z
    class _BB:
        def __init__(self, lo, hi): self.min, self.max = _V(*lo), _V(*hi)
    class _Stub:
        def __init__(self, lo, hi): self.lo, self.hi = lo, hi
        def bounding_box(self): return _BB(self.lo, self.hi)
    def box(dx, dy, dz, x=0, y=0, z=0):
        return _Stub((x, y, z), (x + dx, y + dy, z + dz))


def design():
    d = Design("Lean-to shed", country="FI")
    W = d.param("width", 2000, "KNOWN")
    L = d.param("length", 3000, "KNOWN")
    Hf = d.param("front_height", 2400, "ASSUMED", note="standing height at the door")
    Hb = d.param("back_height", 2000, "ASSUMED")
    post = d.param("post_stock", "98x98 C24", "ASSUMED", stock=True)
    joist = d.param("joist_stock", "48x148 C24", "ASSUMED", stock=True)
    d.param("footprint_m2", W * L / 1e6, "KNOWN")

    # ground: gravel and piers (loose + hardware-ish)
    d.part(Part("gravel", None, kind="loose", stock="murske 0-32", unit="m3", qty=2, phase="ground", step=1))
    d.part(Part("pier", [box(240, 240, 400, x, y, -400) for x in (0, W - 240) for y in (0, L - 240)],
                kind="loose", stock="Leca pilariharkko P-240", unit="kpl", qty=8, phase="ground", step=3,
                notes="2 courses per pier, 4 piers"))
    # frame
    d.part(Part("post-front", [box(98, 98, Hf, x, 0, 0) for x in (0, W - 98)], kind="timber", stock=post, qty=2,
                length_mm=Hf, phase="frame", step=1))
    d.part(Part("post-back", [box(98, 98, Hb, x, L - 98, 0) for x in (0, W - 98)], kind="timber", stock=post, qty=2,
                length_mm=Hb, phase="frame", step=1))
    d.part(Part("beam", [box(W, 48, 148, 0, 0, Hf), box(W, 48, 148, 0, L - 48, Hb)], kind="timber", stock=joist,
                qty=2, length_mm=W, phase="frame", step=2))
    d.part(Part("joist", [box(48, L, 148, x, 0, 400) for x in range(0, W - 48 + 1, (W - 48) // 4)], kind="timber",
                stock=joist, qty=5, length_mm=L, phase="frame", step=3))
    d.part(Part("deck", [box(W, L, 22, 0, 0, 548)], kind="sheet", stock="22 mm lattialastulevy 600x2400", qty=6,
                w_mm=600, h_mm=2000, t_mm=22, phase="frame", step=4))
    # roof
    d.part(Part("rafter", [box(48, L + 200, 148, x, -100, Hf + 148) for x in range(0, W - 48 + 1, (W - 48) // 4)],
                kind="timber", stock=joist, qty=5, length_mm=L + 200, cut_a=83, cut_b=83, phase="roof", step=1,
                notes="7° fall front to back"))
    d.part(Part("batten", [box(W + 200, 32, 50, -100, y, Hf + 296) for y in range(0, L, 400)], kind="timber",
                stock="32x50 sahattu", qty=8, length_mm=W + 200, phase="roof", step=2))
    d.part(Part("pelti", [box(W + 200, L + 200, 1, -100, -100, Hf + 346)], kind="sheet", stock="pelti 1100x3300",
                qty=2, w_mm=1100, h_mm=3200, t_mm=0.5, phase="roof", step=3))
    d.part(Part("wool", None, kind="loose", stock="vuorivilla 100 mm", unit="m2", qty=6, phase="roof", step=4))
    d.part(Part("tape", None, kind="hardware", stock="höyrynsulkuteippi 25 m", qty=1, phase="roof", step=4))

    d.joint("A", "post to beam", (0, 0, Hf), (400, 300, 400), ["post-front", "beam"], "frame",
            [dict(type="M10x160 pultti", qty=2, washer=True, direction="läpi", tool="17 mm")],
            howto="Two bolts through post and beam, prikka both sides; tighten after plumbing.")
    d.joint("B", "rafter on beam", (2 * ((W - 48) // 4) + 24, 24, Hf + 148), (400, 500, 500), ["rafter", "beam"], "roof",
            [dict(type="kulmarauta 90x90", qty=2, washer=False, direction="molemmin puolin", tool="vasara"),
             dict(type="ankkurinaula 4.0x40", qty=16, washer=False, direction="", tool="")],
            howto="One bracket each side of the rafter, 8 nails per bracket.", views=["iso", "section", "front"])
    return d


if __name__ == "__main__":
    print(design().emit(HERE))
