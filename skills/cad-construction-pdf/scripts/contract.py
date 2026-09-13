"""contract.py — what a model registers, what is derived, what is checked. Stdlib only.

    from contract import Design, Part
    d = Design("Lean-to", country="FI")
    W = d.param("width", 2000, "KNOWN")
    d.part(Part("post", solid, kind="timber", stock="98x98 C24", qty=4, length_mm=2200, phase="frame", step=1))
    d.joint("A", "post to beam", (0, 0, 2200), (400, 300, 300), ["post", "beam"], "frame",
            [dict(type="M10x120 bolt", qty=2, washer=True, direction="through", tool="17 mm")], howto="…")
    d.emit(folder)                      # parts.csv, joints.json, params.json; returns the ## Provenance block

    d = Design.load(folder)             # same object without solids (book.py); Design.from_model(folder) with solids (render.py)
    phases = load_phases(folder / "phases.yaml"); prices = load_prices(folder / "prices.csv")
    visible(d, phases, "floor") · cutlist · hardware · nesting · budget · shopping · checks

Solids are duck-typed: anything with .bounding_box() → .min/.max with .X/.Y/.Z (build123d), or None.
"""
import csv, json, math, re, importlib.util, sys
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

PROVENANCE = ("KNOWN", "MEASURED", "INFERRED", "ASSUMED")
KINDS = ("timber", "sheet", "hardware", "loose", "service")
DEFAULT_UNIT = {"timber": "m", "sheet": "kpl", "hardware": "kpl", "service": "kpl"}
PRICE_UNITS = ("m", "kpl", "m2", "m3", "pkt")
PRICE_KINDS = ("LIST", "QUOTE", "USER")
DEFAULT_VIEWS = ["iso", "plan", "front"]
JOINT_VIEWS = ["iso", "section"]
PART_COLUMNS = ["id", "name", "kind", "material", "stock", "unit", "length_mm", "w_mm", "h_mm", "t_mm",
                "qty", "cut_a", "cut_b", "phase", "step", "notes"]


def _bbox(solid):
    """(dx, dy, dz) in mm of a solid or a list of solids, None if not measurable."""
    if solid is None:
        return None
    if isinstance(solid, (list, tuple)):
        solid = solid[0] if solid else None
        if solid is None:
            return None
    try:
        b = solid.bounding_box()
        return (b.max.X - b.min.X, b.max.Y - b.min.Y, b.max.Z - b.min.Z)
    except Exception:
        return None


@dataclass
class Part:
    id: str
    solid: object = None
    kind: str = "timber"
    stock: str = ""
    qty: float = 1
    phase: str = ""
    step: int = 1
    length_mm: float | None = None
    w_mm: float | None = None
    h_mm: float | None = None
    t_mm: float | None = None
    cut_a: float | None = None
    cut_b: float | None = None
    material: str = ""
    notes: str = ""
    unit: str | None = None
    name: str | None = None
    positions: list | None = None

    def __post_init__(self):
        self.name = self.name or self.id
        if self.unit is None:
            self.unit = DEFAULT_UNIT.get(self.kind)
        dims = _bbox(self.solid)
        if dims:
            d = sorted(dims, reverse=True)
            if self.kind == "timber" and self.length_mm is None:
                self.length_mm = round(d[0])
            if self.kind == "sheet":
                self.w_mm = self.w_mm if self.w_mm is not None else round(d[0])
                self.h_mm = self.h_mm if self.h_mm is not None else round(d[1])
                self.t_mm = self.t_mm if self.t_mm is not None else round(d[2], 1)
        if self.kind == "timber":
            self.cut_a = 90 if self.cut_a is None else self.cut_a
            self.cut_b = 90 if self.cut_b is None else self.cut_b

    def row(self):
        return {c: ("" if getattr(self, c) is None else getattr(self, c)) for c in PART_COLUMNS}

    def solids(self):
        if self.solid is None:
            return []
        return list(self.solid) if isinstance(self.solid, (list, tuple)) else [self.solid]


class Design:
    def __init__(self, name, country="FI"):
        self.name, self.country = name, country
        self.params, self.parts, self.joints = {}, [], []

    # ---- registration
    def param(self, name, value, provenance, note="", stock=False):
        if provenance not in PROVENANCE:
            raise ValueError(f"param {name}: provenance must be one of {PROVENANCE}")
        self.params[name] = dict(value=value, provenance=provenance, note=note, stock=bool(stock))
        return value

    def part(self, p: Part):
        if any(q.id == p.id for q in self.parts):
            raise ValueError(f"duplicate part id {p.id}")
        self.parts.append(p)
        return p

    def joint(self, id, title, location, clip, parts, phase, fasteners, howto="", views=None):
        self.joints.append(dict(id=id, title=title, location=list(location), clip=list(clip), parts=list(parts),
                                phase=phase, fasteners=[dict(f) for f in fasteners], howto=howto,
                                views=list(views) if views else JOINT_VIEWS))
        return self.joints[-1]

    def by_id(self, pid):
        return next((p for p in self.parts if p.id == pid), None)

    # ---- persistence
    def emit(self, folder):
        folder = Path(folder)
        with open(folder / "parts.csv", "w", newline="") as f:
            w = csv.DictWriter(f, PART_COLUMNS); w.writeheader()
            for p in self.parts:
                w.writerow(p.row())
        (folder / "joints.json").write_text(json.dumps(self.joints, indent=1, ensure_ascii=False) + "\n")
        (folder / "params.json").write_text(json.dumps(dict(name=self.name, country=self.country, params=self.params),
                                                       indent=1, ensure_ascii=False) + "\n")
        return self.provenance_block()

    def provenance_block(self):
        lines = ["## Provenance"]
        for prov in PROVENANCE:
            for n, p in self.params.items():
                if p["provenance"] == prov:
                    note = f"  ({p['note']})" if p["note"] else ""
                    lines.append(f"{prov:<9} {n} = {p['value']}{note}")
        return "\n".join(lines)

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        meta = json.loads((folder / "params.json").read_text()) if (folder / "params.json").exists() else {}
        d = cls(meta.get("name", folder.name), meta.get("country", "FI"))
        d.params = meta.get("params", {})
        with open(folder / "parts.csv", newline="") as f:
            for r in csv.DictReader(f):
                kw = {k: r[k] for k in PART_COLUMNS if k in r}
                for k in ("length_mm", "w_mm", "h_mm", "t_mm", "cut_a", "cut_b"):
                    kw[k] = float(kw[k]) if kw.get(k) not in ("", None) else None
                q = float(kw["qty"] or 1); kw["qty"] = int(q) if q.is_integer() else q
                kw["step"] = int(float(kw["step"] or 1))
                kw["unit"] = kw["unit"] or None
                d.parts.append(Part(**kw))
        jp = folder / "joints.json"
        d.joints = json.loads(jp.read_text()) if jp.exists() else []
        return d

    @staticmethod
    def model_path(folder):
        """The model module named on the `Authoritative:` line of design.md."""
        folder = Path(folder)
        m = re.search(r"(?m)^Authoritative:\s*([^\s→(]+\.py)", (folder / "design.md").read_text())
        if not m:
            raise FileNotFoundError(f"{folder}/design.md has no 'Authoritative: <model>.py' line")
        return folder / m.group(1)

    @classmethod
    def from_model(cls, folder):
        """Import the model module and call its design() — the live object with solids."""
        path = cls.model_path(folder)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec); sys.modules[path.stem] = mod
        spec.loader.exec_module(mod)
        return mod.design()

    # ---- geometry helpers
    def footprint_m2(self):
        if "footprint_m2" in self.params:
            return float(self.params["footprint_m2"]["value"])
        xs, ys = [], []
        for p in self.parts:
            for s in p.solids():
                try:
                    b = s.bounding_box(); xs += [b.min.X, b.max.X]; ys += [b.min.Y, b.max.Y]
                except Exception:
                    pass
        if not xs:
            return None
        return (max(xs) - min(xs)) * (max(ys) - min(ys)) / 1e6


# ---- authored files
def load_phases(path):
    path = Path(path)
    if path.suffix == ".json":
        phases = json.loads(path.read_text())
    else:
        import yaml  # lazy: the core stays stdlib-only
        phases = yaml.safe_load(path.read_text())
    for ph in phases:
        ph.setdefault("steps", []); ph.setdefault("dims", []); ph.setdefault("views", list(DEFAULT_VIEWS))
        ph.setdefault("prerequisites", []); ph.setdefault("done_state", ""); ph.setdefault("batch", None)
        for s in ph["steps"]:
            s.setdefault("hides_below", False)
    return phases


def load_prices(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["price"] = float(r["price"]) if r.get("price") not in ("", None) else None
        r["pack_qty"] = float(r["pack_qty"]) if r.get("pack_qty") not in ("", None) else 1.0
        r["currency"] = r.get("currency") or "EUR"
        r["kind"] = (r.get("kind") or "LIST").upper()
    return rows


# ---- derivations
def phase_order(phases):
    return {ph["id"]: i for i, ph in enumerate(phases)}


def reveal_step(phase):
    """Last step index (1-based) of the phase that is not hides_below; 0 if the first step already hides."""
    n = 0
    for i, s in enumerate(phase["steps"], 1):
        if s.get("hides_below"):
            break
        n = i
    return n


def visible(design, phases, phase_id, done=False):
    """Parts visible in phase `phase_id`'s drawing: earlier phases fully, this phase up to the reveal step."""
    order = phase_order(phases); n = order[phase_id]
    ph = phases[n]; cut = len(ph["steps"]) if done else reveal_step(ph)
    out = []
    for p in design.parts:
        o = order.get(p.phase)
        if o is None:
            continue
        if o < n or (o == n and p.step <= cut):
            out.append(p)
    return out


def cutlist(design, phases):
    """Timber rows (stock, phase, id, name, length_mm, qty, cut_a, cut_b) in phase order, plus metres per stock."""
    order = phase_order(phases)
    rows = sorted((p for p in design.parts if p.kind == "timber"),
                  key=lambda p: (p.stock, order.get(p.phase, 99), p.step, p.id))
    metres = {}
    for p in rows:
        metres[p.stock] = metres.get(p.stock, 0) + (p.length_mm or 0) * p.qty / 1000
    return [dict(stock=p.stock, phase=p.phase, id=p.id, name=p.name, length_mm=p.length_mm, qty=p.qty,
                 cut_a=p.cut_a, cut_b=p.cut_b) for p in rows], metres


def joint_instances(design, joint):
    first = design.by_id(joint["parts"][0]) if joint["parts"] else None
    return first.qty if first else 1


def hardware(design, phases):
    """Per phase: fastener usages from joints (qty × instances) plus explicit hardware parts."""
    order = phase_order(phases); out = {}
    for j in design.joints:
        n = joint_instances(design, j)
        for f in j["fasteners"]:
            out.setdefault(j["phase"], []).append(dict(type=f["type"], qty=f.get("qty", 1) * n, washer=f.get("washer", False),
                                                       direction=f.get("direction", ""), tool=f.get("tool", ""),
                                                       source=f"joint {j['id']}", howto=j.get("howto", "")))
    for p in design.parts:
        if p.kind == "hardware":
            out.setdefault(p.phase, []).append(dict(type=p.stock or p.name, qty=p.qty, washer=False, direction="",
                                                    tool="", source=f"part {p.id}", howto=p.notes))
    return {ph["id"]: out.get(ph["id"], []) for ph in phases} | {k: v for k, v in out.items() if k not in order}


def hardware_totals(design, phases):
    tot = {}
    for rows in hardware(design, phases).values():
        for r in rows:
            tot[r["type"]] = tot.get(r["type"], 0) + r["qty"]
    return tot


_SHEET = re.compile(r"(\d{3,4})\s*[x×]\s*(\d{3,4})(?!\d)")


def sheet_size(stock):
    """Last WxH (both ≥ 100) in the stock string, e.g. '15 mm havuvaneri 1220x2440' → (1220, 2440)."""
    m = _SHEET.findall(stock)
    return (int(m[-1][0]), int(m[-1][1])) if m else None


def nesting(design):
    """Greedy strip nesting per sheet stock. Returns {stock: dict(sheet=(W,H), sheets=n, placements=[...], parts=[...])}."""
    out = {}
    for p in design.parts:
        if p.kind != "sheet" or not p.w_mm or not p.h_mm:
            continue
        out.setdefault(p.stock, []).append(p)
    result = {}
    for stock, parts in out.items():
        size = sheet_size(stock)
        if not size:
            result[stock] = dict(sheet=None, sheets=None, placements=[], parts=[p.id for p in parts]); continue
        W, H = size
        pieces = []
        for p in parts:
            for k in range(p.qty):
                a, b = p.w_mm, p.h_mm
                fits = (max(a, b) <= max(W, H)) and (min(a, b) <= min(W, H))
                pieces.append((p.id, a, b, fits))
        pieces.sort(key=lambda t: -(t[1] * t[2]))
        sheets, placements, unfit = 0, [], []
        strips = []  # [sheet, y, height, x_used]
        for pid, a, b, fits in pieces:
            if not fits:
                unfit.append(pid); continue
            placed = False
            for st in strips:                      # existing strip, either orientation
                for w, h in ((a, b), (b, a)):
                    if h <= st[2] and st[3] + w <= W:
                        placements.append(dict(sheet=st[0], x=st[3], y=st[1], w=w, h=h, id=pid)); st[3] += w; placed = True; break
                if placed:
                    break
            if placed:
                continue
            # new strip: orientation that packs more per strip, then the lower strip
            opts = [(w, h) for w, h in ((a, b), (b, a)) if w <= W and h <= H]
            w, h = max(opts, key=lambda o: (W // o[0], -o[1]))
            y_used = sum(st[2] for st in strips if st[0] == sheets)
            if sheets == 0 or y_used + h > H:
                sheets += 1; y_used = 0
            strips.append([sheets, y_used, h, w])
            placements.append(dict(sheet=sheets, x=0, y=y_used, w=w, h=h, id=pid))
        result[stock] = dict(sheet=(W, H), sheets=sheets, placements=placements, parts=[p.id for p in parts], unfit=unfit)
    return result


def quantities(design):
    """Per stock: (unit, qty) in the part's unit — timber m, sheet kpl, others as declared."""
    q = {}
    for p in design.parts:
        if not p.stock:
            continue
        unit = p.unit or "kpl"
        amount = (p.length_mm or 0) * p.qty / 1000 if p.kind == "timber" else p.qty
        cur = q.setdefault(p.stock, dict(unit=unit, qty=0.0, kind=p.kind, area_m2=0.0))
        if cur["unit"] != unit:
            cur["mixed"] = True
        cur["qty"] += amount
        if p.kind == "sheet" and p.w_mm and p.h_mm:
            cur["area_m2"] += p.w_mm * p.h_mm * p.qty / 1e6
    return q


def price_rows(stock, prices):
    """(list_row, variant_row) — newest LIST, and newest USER else newest QUOTE."""
    rows = [r for r in prices if r["stock"] == stock and r["price"] is not None]
    def newest(kind):
        c = [r for r in rows if r["kind"] == kind]
        return max(c, key=lambda r: r.get("date") or "") if c else None
    return newest("LIST"), newest("USER") or newest("QUOTE")


def purchasable(qty, unit, row, area_m2=None):
    """(units to buy, unit label) for a part quantity against a price row, or None when units don't convert.
    Packs and pieces round up; metres and m² are sold cut to size and stay exact."""
    ru, k = row["unit"], row["pack_qty"] or 1.0
    if ru == "pkt":
        return math.ceil(qty / k - 1e-9), "pkt"
    if ru == unit:
        return (qty if ru in ("m", "m2", "m3") else math.ceil(qty - 1e-9)), ru
    if ru == "m2" and unit == "kpl" and area_m2:
        return area_m2, "m2"
    return None


def budget(design, prices, fastener_totals=None):
    """Rows per stock with LIST and variant columns; totals; unpriced list."""
    q = quantities(design)
    for t, n in (fastener_totals or {}).items():
        q.setdefault(t, dict(unit="kpl", qty=0.0, kind="hardware", area_m2=0.0))["qty"] += n
    rows, unpriced = [], []
    tot_list = tot_var = 0.0
    for stock, info in sorted(q.items()):
        lr, vr = price_rows(stock, prices)
        row = dict(stock=stock, unit=info["unit"], qty=round(info["qty"], 2), buy=None, buy_unit=None,
                   list_price=None, list_total=None, var_price=None, var_total=None, var_kind=None, source="")
        for r, key in ((lr, "list"), (vr, "var")):
            if not r:
                continue
            conv = purchasable(info["qty"], info["unit"], r, info.get("area_m2"))
            if conv is None:
                continue
            n, u = conv
            row["buy"], row["buy_unit"] = round(n, 2), u
            row[f"{key}_price"] = r["price"]; row[f"{key}_total"] = round(n * r["price"], 2)
            row["source"] = row["source"] or f"{r.get('source','')} {r.get('date','')}".strip()
            if key == "var":
                row["var_kind"] = r["kind"]
        if row["list_total"] is None and row["var_total"] is None:
            unpriced.append(stock)
        tot_list += row["list_total"] if row["list_total"] is not None else (row["var_total"] or 0)
        tot_var += row["var_total"] if row["var_total"] is not None else (row["list_total"] or 0)
        rows.append(row)
    return dict(rows=rows, total_list=round(tot_list, 2), total_var=round(tot_var, 2), unpriced=unpriced)


def default_batches(design, phases):
    """Phase → batch. One timber delivery before the first phase with timber; one trip per other phase."""
    first_timber = next((ph["id"] for ph in phases if any(p.kind == "timber" and p.phase == ph["id"] for p in design.parts)), None)
    batches, n = {}, 0
    for ph in phases:
        if ph.get("batch") is not None:
            batches[ph["id"]] = ph["batch"]; continue
        n += 1; batches[ph["id"]] = n
    return batches, first_timber


def shopping(design, phases, prices):
    """Batches: {batch: dict(phases=[...], rows=[budget-like rows with phase])}. Timber of all phases goes to the first timber phase's batch."""
    batches, first_timber = default_batches(design, phases)
    hw = hardware(design, phases)
    per_phase = {}
    for p in design.parts:
        if not p.stock:
            continue
        target = first_timber if (p.kind == "timber" and first_timber) else p.phase
        d = per_phase.setdefault(target, Design(design.name, design.country))
        d.parts.append(p)
    out = {}
    for ph in phases:
        pid = ph["id"]; b = batches[pid]
        d = per_phase.get(pid, Design(design.name, design.country))
        ft = {r["type"]: 0 for r in hw.get(pid, []) if r["source"].startswith("joint")}
        for r in hw.get(pid, []):
            if r["source"].startswith("joint"):
                ft[r["type"]] += r["qty"]
        bd = budget(d, prices, ft)
        entry = out.setdefault(b, dict(phases=[], rows=[], total_list=0.0, total_var=0.0, unpriced=[]))
        entry["phases"].append(pid)
        for r in bd["rows"]:
            entry["rows"].append(r | dict(phase=pid))
        entry["total_list"] = round(entry["total_list"] + bd["total_list"], 2)
        entry["total_var"] = round(entry["total_var"] + bd["total_var"], 2)
        entry["unpriced"] += bd["unpriced"]
    return out


# ---- checks
@dataclass
class Check:
    id: int
    blocking: bool
    ok: bool
    message: str


def checks(design, phases, prices):
    out = []
    order = phase_order(phases); steps = {ph["id"]: len(ph["steps"]) for ph in phases}
    bad = [f"{p.id}: phase '{p.phase}' unknown" for p in design.parts if p.phase not in order]
    bad += [f"{p.id}: step {p.step} outside 1..{steps[p.phase]} of '{p.phase}'" for p in design.parts if p.phase in order and not 1 <= p.step <= steps[p.phase]]
    bad += [f"phase '{ph['id']}' has no parts" for ph in phases if not any(p.phase == ph["id"] for p in design.parts)]
    ids = {p.id for p in design.parts}
    bad += [f"joint {j['id']}: part '{pid}' unknown" for j in design.joints for pid in j["parts"] if pid not in ids]
    bad += [f"joint {j['id']}: phase '{j['phase']}' unknown" for j in design.joints if j["phase"] not in order]
    out.append(Check(1, True, not bad, "phase/step/joint references resolve" if not bad else "; ".join(bad)))
    inf = [n for n, p in design.params.items() if p["provenance"] == "INFERRED"]
    out.append(Check(2, True, not inf, "no INFERRED parameters" if not inf else "INFERRED: " + ", ".join(inf) + " — measure (KNOWN) or accept (ASSUMED) first"))
    miss = []
    for p in design.parts:
        if p.kind not in KINDS:
            miss.append(f"{p.id}: kind '{p.kind}' not in {KINDS}"); continue
        need = {"timber": ["stock", "length_mm"], "sheet": ["stock", "w_mm", "h_mm", "t_mm"], "loose": ["unit"]}.get(p.kind, [])
        for f in need:
            if getattr(p, f) in (None, ""):
                miss.append(f"{p.id} ({p.kind}): {f} missing")
    out.append(Check(3, True, not miss, "required fields present" if not miss else "; ".join(miss)))
    used = {p.stock for p in design.parts}
    uns = [n for n, p in design.params.items() if p["stock"] and p["provenance"] == "ASSUMED" and str(p["value"]) in used
           and price_rows(str(p["value"]), prices) == (None, None)]
    out.append(Check(4, False, not uns, "ASSUMED stock has price rows" if not uns else "ASSUMED stock without a price row: " + ", ".join(uns)))
    fp = design.footprint_m2(); q = quantities(design); over = []
    if fp:
        for stock, info in q.items():
            if info["unit"] == "m2" and info["qty"] > 4 * fp:
                over.append(f"{stock}: {info['qty']:.0f} m² is {info['qty']/fp:.1f}× the {fp:.1f} m² floor")
    ok5 = f"m² quantities plausible for {fp:.1f} m² floor" if fp else "no footprint to compare against"
    out.append(Check(5, False, not over, ok5 if not over else "; ".join(over)))
    b = budget(design, prices, hardware_totals(design, phases))
    out.append(Check(6, False, not b["unpriced"], "every stock priced" if not b["unpriced"] else f"{len(b['unpriced'])} unpriced: " + ", ".join(b["unpriced"])))
    return out


def blocking_failures(checks_):
    return [c for c in checks_ if c.blocking and not c.ok]
