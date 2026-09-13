"""book.py — build the construction booklet from a design folder's contract files and preview/ slots.

    python book.py [<design folder>]        # reads book.yaml (written with the defaults on first run) → outputs/<slug>.pdf

Blocking check failures build a DRAFT: watermark on every page, a diagnostics page first, and no parts/cutlist/budget/shopping pages.
"""
import re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matplotlib; matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
import contract as C  # noqa: E402
from pages import A4L, title, table, table_height, watermark, image_row, text_block, wrap_lines  # noqa: E402

DEFAULT_PAGES = ["cover", "overview", "elevations", "joints", "parts", "cutlist", "budget", "phases", "shopping", "assumptions"]
FABRICATION = {"parts", "cutlist", "budget", "shopping"}
DISCLAIMER = ("Joint and member sizes in this booklet are general practice, not engineered: no load calculations were made. "
              "Check them with a builder or engineer, and the permit situation with your kunta, before buying or building.")


class Book:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.d = C.Design.load(self.folder)
        self.phases = C.load_phases(self.folder / "phases.yaml") if (self.folder / "phases.yaml").exists() else []
        self.prices = C.load_prices(self.folder / "prices.csv")
        self.checks = C.checks(self.d, self.phases, self.prices)
        self.draft = bool(C.blocking_failures(self.checks))
        self.prev = self.folder / "preview"
        self.n = 0
        self.hw = C.hardware(self.d, self.phases)
        self.budget = C.budget(self.d, self.prices, C.hardware_totals(self.d, self.phases))
        self.shopping = C.shopping(self.d, self.phases, self.prices)

    def slot(self, name):
        p = self.prev / f"{name}.png"
        return p if p.exists() else None

    # ---- page frame
    def page(self, heading=None):
        self.n += 1
        fig = plt.figure(figsize=A4L)
        if heading:
            title(fig, f"{self.n} · {heading}")
        if self.draft:
            watermark(fig)
        fig.text(0.97, 0.02, f"{self.d.name} · {self.n}", fontsize=7, color="grey", ha="right")
        return fig

    def save(self, fig):
        self.pdf.savefig(fig); plt.close(fig)

    # ---- pages
    def cover(self):
        fig = self.page()
        img = self.slot("cover") or self.slot("overview-iso")
        fig.text(0.05, 0.93, self.d.name, fontsize=24, weight="bold", va="top")
        fig.text(0.05, 0.87, f"Construction booklet · {date.today().isoformat()} · {self.d.country}", fontsize=10, color="dimgray", va="top")
        if img:
            ax = fig.add_axes([0.02, 0.08, 0.62, 0.74]); ax.imshow(plt.imread(str(img)), interpolation="none"); ax.axis("off")
        facts = [f"{n:<14}{p['value']}" for n, p in self.d.params.items() if p["provenance"] in ("KNOWN", "MEASURED")][:8]
        facts += ["", f"Phases        {len(self.phases)}", f"Timber parts  {sum(p.qty for p in self.d.parts if p.kind == 'timber')}",
                  f"Budget        {self.budget['total_list']:.0f} € list / {self.budget['total_var']:.0f} € your prices"]
        if self.draft:
            facts += ["", "DRAFT — blocking checks failed; see the first page."]
        text_block(fig, 0.66, 0.80, facts, size=9, mono=True, spacing=1.5)
        self.save(fig)

    def overview(self):
        fig = self.page("Overview")
        image_row(fig, [self.slot("overview-iso")], 0.08, 0.80, x0=0.03, x1=0.62)
        lines = ["CONTENTS"] + [f"  {k}" for k in self.manifest["pages"]] + ["", "PARAMETERS"]
        lines += [f"  {p['provenance']:<9}{n} = {p['value']}" for n, p in self.d.params.items()]
        text_block(fig, 0.65, 0.88, lines, size=8, mono=True, spacing=1.45)
        self.save(fig)

    def elevations(self):
        fig = self.page("Elevations and plan — mm")
        image_row(fig, [self.slot("elev-front"), self.slot("elev-side")], 0.50, 0.40, captions=["front", "side"])
        image_row(fig, [self.slot("elev-plan"), self.slot("elev-rear")], 0.05, 0.40, captions=["plan", "rear"])
        self.save(fig)

    def joints(self):
        for j in self.d.joints:
            fig = self.page(f"Joint {j['id']} — {j['title']}  (phase {j['phase']})")
            views = [self.slot(f"joint-{j['id']}-{v if isinstance(v, str) else 'cam'}") for v in j.get("views", [])]
            image_row(fig, views, 0.50, 0.38, captions=[v if isinstance(v, str) else "camera" for v in j.get("views", [])])
            n = C.joint_instances(self.d, j)
            header = ["fastener", "per joint", f"× {n} joints", "washer", "direction", "tool"]
            rows = [[f["type"], str(f.get("qty", 1)), str(f.get("qty", 1) * n), "prikka" if f.get("washer") else "—", f.get("direction", ""), f.get("tool", "")] for f in j["fasteners"]]
            h = table_height(header, rows)
            ax = fig.add_axes([0.05, 0.44 - h, 0.90, h]); ax.axis("off"); table(ax, header, rows, [0.30, 0.10, 0.12, 0.10, 0.20, 0.18], ax_height=h)
            text_block(fig, 0.05, 0.40 - h, wrap_lines("Parts: " + ", ".join(j["parts"]) + "\n" + j.get("howto", ""), 150), size=8.5)
            self.save(fig)

    def parts(self):
        parts = [p for p in self.d.parts if p.kind == "timber" and self.slot(f"part-{p.id}")]
        per = 6
        for i in range(0, len(parts), per):
            fig = self.page("Parts — cut lengths and angles" + (" (cont.)" if i else ""))
            chunk = parts[i:i + per]
            for k, p in enumerate(chunk):
                ax = fig.add_axes([0.03 + (k % 2) * 0.48, 0.62 - (k // 2) * 0.29, 0.46, 0.26]); ax.imshow(plt.imread(str(self.slot(f"part-{p.id}"))), interpolation="none"); ax.axis("off")
            fig.text(0.05, 0.03, "Angles are measured to the long edge. Mirror pairs are noted in the cut list.", fontsize=8, color="dimgray")
            self.save(fig)
        nest = C.nesting(self.d)
        if any(v["sheet"] for v in nest.values()):
            fig = self.page("Sheet nesting — greedy strips, grain ignored")
            stocks = [s for s, v in nest.items() if v["sheet"]]
            for k, stock in enumerate(stocks[:4]):
                v = nest[stock]; W, H = v["sheet"]
                ax = fig.add_axes([0.05 + (k % 2) * 0.48, 0.50 - (k // 2) * 0.44, 0.42, 0.38])
                sheets = max(v["sheets"], 1)
                for pl in v["placements"]:
                    ox = (pl["sheet"] - 1) * (W * 1.08)
                    ax.add_patch(Rectangle((ox + pl["x"], pl["y"]), pl["w"], pl["h"], fill=False, lw=0.6))
                    ax.text(ox + pl["x"] + pl["w"] / 2, pl["y"] + pl["h"] / 2, pl["id"], ha="center", va="center", fontsize=6)
                for s in range(sheets):
                    ax.add_patch(Rectangle((s * W * 1.08, 0), W, H, fill=False, lw=1.2, ec="black"))
                ax.set_xlim(-50, sheets * W * 1.08); ax.set_ylim(-50, H + 50); ax.set_aspect("equal"); ax.axis("off")
                ax.set_title(f"{stock} — {v['sheets']} sheet(s) of {W}×{H}" + (f"; does not fit: {', '.join(v['unfit'])}" if v["unfit"] else ""), fontsize=8)
            self.save(fig)

    def _tables_page(self, heading, blocks, note=None):
        """blocks: [(subheading, header, rows, widths)]; paginates by row so no table runs off the page."""
        fig = self.page(heading); y = 0.88
        if note:
            fig.text(0.05, 0.905, note, fontsize=8, color="dimgray", va="top"); y = 0.86
        for sub, header, rows, widths in blocks:
            if not rows:
                continue
            wrap = 70 if len(header) <= 4 else 40
            rows = list(rows); first = True
            while rows:
                if y < 0.20:                                   # not enough room for a heading + a few rows
                    self.save(fig); fig = self.page(heading + " (cont.)"); y = 0.88
                # take as many rows as fit
                n = len(rows)
                while n > 1 and table_height(header, rows[:n], wrap) > y - 0.06:
                    n -= 1
                chunk = rows[:n]; h = table_height(header, chunk, wrap)
                fig.text(0.05, y, sub + ("" if first else " (cont.)"), fontsize=10, weight="bold", va="top"); y -= 0.03
                ax = fig.add_axes([0.05, y - h, 0.90, h]); ax.axis("off"); table(ax, header, chunk, widths, ax_height=h)
                y -= h + 0.035; rows = rows[n:]; first = False
        self.save(fig)

    def cutlist(self):
        rows, metres = C.cutlist(self.d, self.phases)
        blocks = []
        for stock in sorted(metres):
            r = [[x["id"], x["name"], f"{x['length_mm']:.0f}", str(x["qty"]), f"{x['cut_a']:g}° / {x['cut_b']:g}°", x["phase"]] for x in rows if x["stock"] == stock]
            r.append(["total", "", "", str(sum(x["qty"] for x in rows if x["stock"] == stock)), f"{metres[stock]:.1f} m", ""])
            blocks.append((stock, ["id", "part", "length mm", "qty", "cuts", "phase"], r, [0.16, 0.30, 0.12, 0.08, 0.18, 0.16]))
        sheets = [[p.id, p.stock, f"{p.w_mm:.0f} × {p.h_mm:.0f} × {p.t_mm:g}", str(p.qty), p.phase] for p in self.d.parts if p.kind == "sheet"]
        blocks.append(("Sheets", ["id", "stock", "w × h × t mm", "qty", "phase"], sheets, [0.16, 0.40, 0.20, 0.08, 0.16]))
        loose = [[p.id, p.stock, f"{p.qty:g} {p.unit or ''}", p.phase, p.notes] for p in self.d.parts if p.kind in ("loose", "service")]
        blocks.append(("Loose materials and services", ["id", "stock", "qty", "phase", "notes"], loose, [0.14, 0.30, 0.12, 0.12, 0.32]))
        hw = [[t, str(n)] for t, n in sorted(C.hardware_totals(self.d, self.phases).items())]
        blocks.append(("Hardware totals", ["item", "qty"], hw, [0.70, 0.30]))
        self._tables_page("Cut list, sheets, loose materials, hardware", blocks)

    def budget_page(self):
        b = self.budget
        rows = [[r["stock"], f"{r['qty']:g} {r['unit']}", f"{r['buy']:g} {r['buy_unit']}" if r["buy"] is not None else "—",
                 f"{r['list_price']:.2f}" if r["list_price"] is not None else "—", f"{r['list_total']:.0f}" if r["list_total"] is not None else "—",
                 f"{r['var_price']:.2f} ({r['var_kind']})" if r["var_price"] is not None else "—", f"{r['var_total']:.0f}" if r["var_total"] is not None else "—", r["source"]]
                for r in b["rows"]]
        rows.append(["total", "", "", "", f"{b['total_list']:.0f}", "", f"{b['total_var']:.0f}", ""])
        note = ("List = newest LIST row per stock; your prices = USER or QUOTE rows where present, else the list price. ±20–25 %. "
                + (f"Unpriced ({len(b['unpriced'])}): " + ", ".join(b["unpriced"]) if b["unpriced"] else "Every stock has a price."))
        self._tables_page("Budget — list vs. your prices (€)", [("", ["stock", "needed", "buy", "€/unit list", "€ list", "€/unit yours", "€ yours", "source"], rows,
                                                                  [0.24, 0.10, 0.10, 0.09, 0.08, 0.13, 0.08, 0.18])], note=note)

    def phases_pages(self):
        for ph in self.phases:
            fig = self.page(f"Phase {ph['id']} — {ph['title']}" + (f"  (weekend {ph['weekend']})" if ph.get("weekend") else ""))
            views = ph.get("views") or C.DEFAULT_VIEWS
            paths = [self.slot(f"phase-{ph['id']}-{v if isinstance(v, str) else 'cam'}") for v in views]
            image_row(fig, paths, 0.50, 0.40, captions=[v if isinstance(v, str) else "camera" for v in views], x1=0.80)
            image_row(fig, [self.slot(f"phase-{ph['id']}-done")], 0.66, 0.24, captions=["phase complete"], x0=0.81, x1=0.98)
            jt = [self.slot(f"joint-{j['id']}-iso") for j in self.d.joints if j["phase"] == ph["id"]]
            if jt:
                image_row(fig, jt[:2], 0.50, 0.14, captions=[f"joint {j['id']}" for j in self.d.joints if j["phase"] == ph["id"]][:2], x0=0.81, x1=0.98)
            lines = []
            if ph.get("prerequisites"):
                lines += wrap_lines("Before: " + "; ".join(ph["prerequisites"]), 95) + [""]
            for i, s in enumerate(ph["steps"], 1):
                lines += wrap_lines(f"{i}. {s['text']}" + ("  [covers the work below]" if s.get("hides_below") else ""), 95)
            if ph.get("done_state"):
                lines += [""] + wrap_lines("Done when: " + ph["done_state"], 95)
            text_block(fig, 0.05, 0.47, lines, size=8)
            hw = self.hw.get(ph["id"], [])
            if hw:
                header = ["hardware", "qty", "where", "how"]
                rows = [[r["type"], str(r["qty"]), r["source"], (("prikka · " if r["washer"] else "") + r["direction"] + (f" · {r['tool']}" if r["tool"] else "")).strip(" ·")] for r in hw]
                h = min(table_height(header, rows, 40), 0.42)
                ax = fig.add_axes([0.56, 0.47 - h, 0.41, h]); ax.axis("off"); table(ax, header, rows, [0.34, 0.10, 0.20, 0.36], fontsize=6.5, ax_height=h)
            batch = next((b for b, e in self.shopping.items() if ph["id"] in e["phases"]), None)
            if batch is not None and not self.draft:
                buy = [r for r in self.shopping[batch]["rows"] if r["phase"] == ph["id"]]
                buy_lines = [f"Buy before (trip {batch}): " + "; ".join(f"{r['stock']} {r['buy']:g} {r['buy_unit']}" if r["buy"] is not None else f"{r['stock']} {r['qty']:g} {r['unit']}" for r in buy)]
                text_block(fig, 0.05, 0.10, wrap_lines(buy_lines[0], 190), size=7.5)
            self.save(fig)

    def shopping_page(self):
        blocks = []
        for b, e in sorted(self.shopping.items()):
            rows = [[r["stock"], f"{r['buy']:g} {r['buy_unit']}" if r["buy"] is not None else f"{r['qty']:g} {r['unit']}", r["phase"],
                     f"{r['var_total']:.0f}" if r["var_total"] is not None else (f"{r['list_total']:.0f}" if r["list_total"] is not None else "—")] for r in e["rows"]]
            rows.append(["total", "", "", f"{e['total_var']:.0f}"])
            blocks.append((f"Trip {b} — before phase {e['phases'][0]}" + (f" (also {', '.join(e['phases'][1:])})" if len(e["phases"]) > 1 else ""),
                           ["stock", "buy", "for phase", "€ yours"], rows, [0.46, 0.18, 0.18, 0.18]))
        self._tables_page("Shopping — trips and batches", blocks,
                          note="All timber goes with the first framing delivery; one hardware-store trip per phase unless phases.yaml sets `batch`.")

    def assumptions(self):
        fig = self.page("Assumptions, checks, disclaimer")
        text_block(fig, 0.05, 0.88, self.d.load_provenance_lines() if hasattr(self.d, "load_provenance_lines") else self.d.provenance_block().splitlines(), size=7.5, mono=True)
        fails = [c for c in self.checks if not c.ok]
        ax = fig.add_axes([0.52, 0.45, 0.45, 0.43]); ax.axis("off")
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=True, fc="#fdecea" if fails else "#eef8ee", ec="red" if fails else "green", lw=1))
        lines = ["CHECKS"] + [f"{'✗' if not c.ok else '✓'} {c.id}{' (blocking)' if c.blocking and not c.ok else ''}: " + c.message for c in self.checks]
        ax.text(0.02, 0.97, "\n".join(l for line in lines for l in wrap_lines(line, 70)), transform=ax.transAxes, fontsize=7, va="top", family="monospace")
        text_block(fig, 0.05, 0.12, wrap_lines(DISCLAIMER, 170), size=8)
        self.save(fig)

    def diagnostics(self):
        fig = self.page("DRAFT — blocking checks failed")
        lines = []
        for c in C.blocking_failures(self.checks):
            lines += wrap_lines(f"check {c.id}: {c.message}", 150) + [""]
        lines += ["Fix these at the gate and rebuild. Parts, cut list, budget and shopping pages are withheld until they pass."]
        text_block(fig, 0.05, 0.88, lines, size=9)
        self.save(fig)

    def image(self, spec):
        fig = self.page(spec.get("title", ""))
        p = self.folder / spec["image"]
        if p.exists():
            ax = fig.add_axes([0.03, 0.05, 0.94, 0.85]); ax.imshow(plt.imread(str(p)), interpolation="none"); ax.axis("off")
        self.save(fig)

    # ---- build
    def build(self):
        bp = self.folder / "book.yaml"
        import yaml
        if bp.exists():
            self.manifest = yaml.safe_load(bp.read_text())
        else:
            self.manifest = dict(title=self.d.name, pages=list(DEFAULT_PAGES))
            bp.write_text(yaml.safe_dump(self.manifest, sort_keys=False, allow_unicode=True))
        out = self.folder / "outputs"; out.mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", self.d.name.lower()).strip("-")
        pdf_path = out / f"{slug}.pdf"
        fn = dict(cover=self.cover, overview=self.overview, elevations=self.elevations, joints=self.joints, parts=self.parts,
                  cutlist=self.cutlist, budget=self.budget_page, phases=self.phases_pages, shopping=self.shopping_page, assumptions=self.assumptions)
        with PdfPages(pdf_path) as self.pdf:
            if self.draft:
                self.diagnostics()
            for page in self.manifest["pages"]:
                if isinstance(page, dict):
                    self.image(page); continue
                if page in FABRICATION and self.draft:
                    continue
                if page not in fn:
                    print(f"unknown page type {page!r}, skipped", file=sys.stderr); continue
                fn[page]()
        status = "DRAFT" if self.draft else "ok"
        print(f"{pdf_path} — {self.n} pages, {status}")
        for c in self.checks:
            if not c.ok:
                print(f"  check {c.id}{' BLOCKING' if c.blocking else ''}: {c.message}")
        return pdf_path


if __name__ == "__main__":
    Book(sys.argv[1] if len(sys.argv) > 1 else ".").build()
