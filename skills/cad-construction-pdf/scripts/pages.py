"""pages.py — landscape-A4 PDF page primitives with matplotlib (no LaTeX, no cairo). book.py composes the booklet from these.

    from pages import build
    build([
      ("title", dict(title="A-frame cabin", subtitle="…", image="preview/iso.png", facts="Footprint 4.0 × 4.2 m\\n…")),
      ("image", "drawings/elevations.png", "2 · Elevations", "note under the image"),
      ("images", ["preview/plan.png", "preview/rear.png"], "3 · Plan and rear"),
      ("tables", "outputs/cutlist.md", "8 · Cut list"),         # every markdown table under its heading
      ("text", "phases.md", "13 · Phases", 2),                  # markdown-ish text in N columns
    ], "outputs/booklet.pdf")

Tables: markdown `| a | b |` rows → ax.table; row height from wrapped line count; numeric cells right-aligned.
"""
import re, textwrap
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from pathlib import Path

A4L = (11.69, 8.27)
NUM = re.compile(r"[\d.,]+( m| kpl| sheet| lot| m²| pss)?")

def _title(fig, text): fig.text(0.05, 0.95, text, fontsize=16, weight="bold", va="top")
title = _title

def watermark(fig, text="DRAFT"):
    fig.text(0.5, 0.5, text, fontsize=110, color="red", alpha=0.12, ha="center", va="center", rotation=30, weight="bold")

def image_row(fig, paths, y, h, captions=None, x0=0.03, x1=0.97, gap=0.015):
    """Images side by side between x0..x1 at height h (figure fraction), bottom at y. Missing files are skipped."""
    paths = [p for p in paths if p and Path(p).exists()]
    if not paths:
        return
    n = len(paths); w = ((x1 - x0) - gap * (n - 1)) / n
    for i, p in enumerate(paths):
        ax = fig.add_axes([x0 + i * (w + gap), y, w, h]); ax.imshow(plt.imread(str(p)), interpolation="none"); ax.axis("off")
        if captions and i < len(captions) and captions[i]:
            ax.set_title(captions[i], fontsize=8, color="dimgray")

def text_block(fig, x, y, lines, size=8, mono=False, spacing=1.3):
    fig.text(x, y, "\n".join(lines), fontsize=size, va="top", family="monospace" if mono else None, linespacing=spacing)

def wrap_lines(text, width):
    out = []
    for para in str(text).splitlines() or [""]:
        out += textwrap.wrap(para, width, subsequent_indent="  " if para.lstrip().startswith(("-", "•")) else "") or [""]
    return out

LINE = 0.022   # figure-fraction height of one text line at fontsize ~7

def table_height(header, rows, wrap=70):
    """Figure-fraction height a table needs; use it to size the axes before calling table()."""
    rows = [[textwrap.fill(c, wrap) for c in r] for r in rows]
    return sum(LINE * max(c.count("\n") + 1 for c in r) + 0.008 for r in [header] + rows)

def table(ax, header, rows, widths=None, fontsize=7.5, ax_height=None):
    """Draw a table filling `ax`; `ax_height` (figure fraction) makes row heights absolute."""
    wrap = 70 if len(header) <= 4 else 44
    rows = [[textwrap.fill(c, wrap) for c in r] for r in rows]
    tbl = ax.table(cellText=rows, colLabels=header, loc="upper left", cellLoc="left", colLoc="left", colWidths=widths)
    tbl.auto_set_font_size(False); tbl.set_fontsize(fontsize)
    nlines = [1] + [max(c.count("\n") + 1 for c in r) for r in rows]
    scale = 1 / ax_height if ax_height else 1
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#bbbbbb"); cell.set_height((LINE * nlines[r] + 0.008) * scale)
        txt = cell.get_text().get_text().strip()
        if r == 0: cell.set_text_props(weight="bold"); cell.set_facecolor("#eeeeee")
        elif NUM.fullmatch(txt): cell.get_text().set_ha("right")
        if r == len(rows) and txt.lower().startswith("total"): cell.set_text_props(weight="bold")
    return tbl

def md_tables(md):
    """Yield (heading, header, rows) for every markdown table, keyed by the nearest heading above it."""
    heading, rows = "", []
    def flush():
        nonlocal rows
        if len(rows) > 1: yield heading, rows[0], rows[1:]
        rows = []
    for line in md.splitlines() + [""]:
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            rows.append([c.strip().replace("**", "") for c in line.strip().strip("|").split("|")])
            continue
        yield from flush()
        if line.startswith("#"): heading = line.strip("# ").strip()

def md_lines(md, width):
    out = []
    for line in md.splitlines():
        if line.startswith("# "): continue
        if line.startswith("## "): out += ["", line[3:].upper()]; continue
        out += textwrap.wrap(line, width, subsequent_indent="  " if line.startswith("- ") else "") or [""]
    return out

def build(pages, out_pdf):
    with PdfPages(out_pdf) as pdf:
        for kind, *args in pages:
            fig = plt.figure(figsize=A4L)
            if kind == "title":
                d = args[0]
                fig.text(0.05, 0.93, d["title"], fontsize=22, weight="bold", va="top")
                fig.text(0.05, 0.87, d.get("subtitle", ""), fontsize=10, color="dimgray", va="top")
                if d.get("image"):
                    ax = fig.add_axes([0.02, 0.08, 0.6, 0.75]); ax.imshow(plt.imread(d["image"]), interpolation="none"); ax.axis("off")
                fig.text(0.64, 0.80, d.get("facts", ""), fontsize=8.5, va="top", family="monospace", linespacing=1.4)
            elif kind == "image":
                path, title, *note = args; _title(fig, title)
                ax = fig.add_axes([0.03, 0.05, 0.94, 0.85]); ax.imshow(plt.imread(path), interpolation="none"); ax.axis("off")
                if note: fig.text(0.05, 0.03, note[0], fontsize=8, color="dimgray")
            elif kind == "images":
                paths, title = args[0], args[1]; _title(fig, title); n = len(paths)
                for i, p in enumerate(paths):
                    ax = fig.add_axes([0.03 + i * 0.94 / n, 0.05, 0.94 / n - 0.02, 0.85]); ax.imshow(plt.imread(p), interpolation="none"); ax.axis("off")
            elif kind == "tables":
                src, title, *note = args; _title(fig, title)
                if note: fig.text(0.05, 0.905, note[0], fontsize=8, color="dimgray", va="top")
                y = 0.86
                for heading, header, rows in md_tables(Path(src).read_text()):
                    h = table_height(header, rows, 70 if len(header) <= 4 else 44)
                    if y - h < 0.03:                       # page full → continue on a new page
                        pdf.savefig(fig); plt.close(fig); fig = plt.figure(figsize=A4L); _title(fig, title + " (cont.)"); y = 0.86
                    fig.text(0.05, y, heading, fontsize=10, weight="bold", va="top"); y -= 0.03
                    ax = fig.add_axes([0.05, y - h, 0.90, h]); ax.axis("off"); table(ax, header, rows, ax_height=h)
                    y -= h + 0.035
            elif kind == "text":
                src, title, *cols = args; _title(fig, title); ncol = cols[0] if cols else 1
                lines = md_lines(Path(src).read_text(), 80 if ncol == 2 else 150)
                per = (len(lines) + ncol - 1) // ncol
                for k in range(ncol):
                    fig.text(0.05 + k * 0.48, 0.90, "\n".join(lines[k * per:(k + 1) * per]), fontsize=7, va="top", linespacing=1.28)
            pdf.savefig(fig); plt.close(fig)
    return out_pdf
