"""cad-construction-pdf: the contract core (stdlib) on the lean-to fixture; render/book parts skip without build123d."""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "cad-construction-pdf" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "lean-to"
sys.path.insert(0, str(SCRIPTS))
import contract  # noqa: E402
from contract import Design, Part  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    for f in ("design.md", "leanto.py", "phases.yaml", "prices.csv"):
        shutil.copy(FIXTURE / f, tmp_path / f)
    return tmp_path


@pytest.fixture
def design(folder):
    d = Design.from_model(folder)
    d.emit(folder)
    return d


@pytest.fixture
def phases(folder):
    return contract.load_phases(folder / "phases.yaml")


@pytest.fixture
def prices(folder):
    return contract.load_prices(folder / "prices.csv")


def test_emit_and_load_round_trip(folder, design):
    loaded = Design.load(folder)
    assert [p.id for p in loaded.parts] == [p.id for p in design.parts]
    deck = loaded.by_id("deck")
    assert (deck.kind, deck.w_mm, deck.h_mm, deck.t_mm, deck.qty) == ("sheet", 600, 2000, 22, 6)
    assert loaded.by_id("rafter").cut_a == 83
    assert loaded.params["post_stock"]["stock"] is True
    assert len(loaded.joints) == 2 and loaded.joints[1]["views"] == ["iso", "section", "front"]


def test_dims_come_from_the_solid_when_not_given():
    class BB:
        class min: X, Y, Z = 0, 0, 0
        class max: X, Y, Z = 48, 3200, 148
    class S:
        def bounding_box(self): return BB
    p = Part("r", S(), kind="timber", stock="48x148", phase="f")
    assert p.length_mm == 3200 and p.cut_a == 90 and p.unit == "m"


def test_reveal_hides_the_deck_but_done_shows_it(design, phases):
    ids = {p.id for p in contract.visible(design, phases, "frame")}
    assert "joist" in ids and "pier" in ids and "deck" not in ids and "rafter" not in ids
    assert "deck" in {p.id for p in contract.visible(design, phases, "frame", done=True)}
    roof = {p.id for p in contract.visible(design, phases, "roof")}
    assert "deck" in roof and "batten" in roof and "pelti" not in roof


def test_fasteners_counted_once_per_joint_instance(design, phases):
    hw = contract.hardware(design, phases)
    frame = {r["type"]: r["qty"] for r in hw["frame"]}
    assert frame == {"M10x160 pultti": 4}  # 2 per joint × 2 front posts
    roof = {r["type"]: r["qty"] for r in hw["roof"]}
    assert roof["kulmarauta 90x90"] == 10 and roof["ankkurinaula 4.0x40"] == 80  # 5 rafters
    assert roof["höyrynsulkuteippi 25 m"] == 1  # explicit hardware part, once
    assert contract.hardware_totals(design, phases)["M10x160 pultti"] == 4


def test_cutlist_metres_per_stock(design, phases):
    rows, metres = contract.cutlist(design, phases)
    assert metres["98x98 C24"] == pytest.approx(2 * 2.4 + 2 * 2.0)
    assert metres["48x148 C24"] == pytest.approx(2 * 2.0 + 5 * 3.0 + 5 * 3.2)
    assert [r["id"] for r in rows if r["stock"] == "48x148 C24"] == ["beam", "joist", "rafter"]


def test_nesting_counts_sheets():
    d = Design("n")
    d.parts.append(Part("g", None, kind="sheet", stock="15 mm havuvaneri 1220x2440", qty=6, w_mm=700, h_mm=500, t_mm=15, phase="x"))
    n = contract.nesting(d)["15 mm havuvaneri 1220x2440"]
    assert n["sheet"] == (1220, 2440) and n["sheets"] == 1 and len(n["placements"]) == 6 and not n["unfit"]
    d.parts.append(Part("big", None, kind="sheet", stock="15 mm havuvaneri 1220x2440", qty=1, w_mm=3000, h_mm=100, t_mm=15, phase="x"))
    assert contract.nesting(d)["15 mm havuvaneri 1220x2440"]["unfit"] == ["big"]


def test_budget_keeps_list_and_variant_columns(design, phases, prices):
    b = contract.budget(design, prices, contract.hardware_totals(design, phases))
    rows = {r["stock"]: r for r in b["rows"]}
    joist = rows["48x148 C24"]
    assert joist["list_price"] == 3.49 and joist["var_price"] == 2.40 and joist["var_kind"] == "QUOTE"
    pelti = rows["pelti 1100x3300"]                      # sheet priced per m2, USER overrides LIST
    assert pelti["buy_unit"] == "m2" and pelti["buy"] == pytest.approx(2 * 1.1 * 3.2)
    assert pelti["list_price"] == 14.50 and pelti["var_price"] == 12.00 and pelti["var_kind"] == "USER"
    wool = rows["vuorivilla 100 mm"]                     # 6 m² at 5.65 m²/pkt → 2 pkt
    assert wool["buy"] == 2 and wool["buy_unit"] == "pkt" and wool["list_total"] == pytest.approx(59.80)
    assert rows["murske 0-32"]["var_total"] == 70.0 and rows["murske 0-32"]["list_total"] is None
    assert b["unpriced"] == ["ankkurinaula 4.0x40", "höyrynsulkuteippi 25 m"]
    assert b["total_var"] < b["total_list"]


def test_fractional_loose_quantities_survive_reload(tmp_path):
    d = Design("f"); d.parts.append(Part("g", None, kind="loose", stock="murske 0-32", unit="m3", qty=0.5, phase="x"))
    d.emit(tmp_path)
    assert Design.load(tmp_path).by_id("g").qty == 0.5


def test_sheet_area_sums_per_part_when_priced_per_m2():
    d = Design("s")
    d.parts.append(Part("a", None, kind="sheet", stock="pelti", qty=2, w_mm=1000, h_mm=2000, t_mm=1, phase="x"))
    d.parts.append(Part("b", None, kind="sheet", stock="pelti", qty=1, w_mm=500, h_mm=500, t_mm=1, phase="x"))
    prices = [dict(stock="pelti", unit="m2", price=10.0, currency="EUR", pack_qty=1.0, source="", date="", kind="LIST")]
    row = contract.budget(d, prices)["rows"][0]
    assert row["buy"] == pytest.approx(4.25) and row["list_total"] == pytest.approx(42.5)


def test_step_zero_is_blocking(design, phases, prices):
    design.parts.append(Part("early", None, kind="timber", stock="x", length_mm=1, phase="roof", step=0))
    cs = contract.checks(design, phases, prices)
    assert not cs[0].ok and "early" in cs[0].message


def test_unit_mismatch_is_unpriced_not_zero():
    d = Design("u"); d.parts.append(Part("p", None, kind="timber", stock="48x148 C24", qty=2, length_mm=3000, phase="f"))
    prices = [dict(stock="48x148 C24", unit="kpl", price=9.0, currency="EUR", pack_qty=1.0, source="", date="", kind="LIST")]
    b = contract.budget(d, prices)
    assert b["unpriced"] == ["48x148 C24"] and b["total_list"] == 0


def test_shopping_puts_all_timber_in_the_first_timber_phase(design, phases, prices):
    s = contract.shopping(design, phases, prices)
    batches = {b: e["phases"] for b, e in s.items()}
    assert batches == {1: ["ground"], 2: ["frame"], 3: ["roof"]}
    frame_stocks = {r["stock"] for r in s[2]["rows"]}
    assert "32x50 sahattu" in frame_stocks and "M10x160 pultti" in frame_stocks   # roof timber bought with the frame delivery
    roof_stocks = {r["stock"] for r in s[3]["rows"]}
    assert "kulmarauta 90x90" in roof_stocks and "32x50 sahattu" not in roof_stocks


def test_checks_pass_on_the_fixture_except_unpriced(design, phases, prices):
    cs = contract.checks(design, phases, prices)
    assert [c.ok for c in cs] == [True, True, True, True, True, False]
    assert not contract.blocking_failures(cs)
    assert "ankkurinaula" in cs[5].message


def test_checks_block_on_bad_references_inferred_and_missing_fields(design, phases, prices):
    design.parts.append(Part("ghost", None, kind="timber", stock="x", length_mm=1, phase="nowhere"))
    design.parts.append(Part("late", None, kind="timber", stock="x", length_mm=1, phase="roof", step=9))
    design.parts.append(Part("nolen", None, kind="timber", stock="x", phase="roof"))
    design.parts.append(Part("rock", None, kind="loose", stock="x", phase="roof"))  # no unit
    design.param("pitch", 7, "INFERRED")
    design.joints[0]["parts"].append("missing")
    cs = contract.checks(design, phases, prices)
    b = contract.blocking_failures(cs)
    assert [c.id for c in b] == [1, 2, 3]
    assert "ghost" in cs[0].message and "late" in cs[0].message and "missing" in cs[0].message
    assert "pitch" in cs[1].message
    assert "nolen" in cs[2].message and "rock" in cs[2].message


def test_check4_flags_assumed_stock_without_price(design, phases, prices):
    cs = contract.checks(design, phases, [r for r in prices if r["stock"] != "98x98 C24"])
    assert cs[3].ok is False and "post_stock" in cs[3].message


def test_check5_flags_implausible_area(design, phases, prices):
    design.by_id("wool").qty = 60  # 10× the 6 m² floor
    cs = contract.checks(design, phases, prices)
    assert cs[4].ok is False and "10.0×" in cs[4].message


def test_model_path_from_design_md(folder):
    assert Design.model_path(folder).name == "leanto.py"


# ---- end to end, only where build123d + matplotlib exist
needs_cad = pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None or importlib.util.find_spec("matplotlib") is None,
    reason="build123d/matplotlib not installed",
)


@needs_cad
def test_render_and_book_end_to_end(folder):
    r = subprocess.run([sys.executable, str(SCRIPTS / "render.py"), str(folder), "lines"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    prev = folder / "preview"
    for slot in ("overview-iso", "elev-front", "elev-plan", "phase-frame-plan", "phase-frame-section",
                 "phase-frame-done", "joint-B-section", "part-rafter"):
        assert (prev / f"{slot}.png").stat().st_size > 2000, slot
    r = subprocess.run([sys.executable, str(SCRIPTS / "book.py"), str(folder)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    pdf = folder / "outputs" / "lean-to-shed.pdf"
    assert pdf.exists() and (folder / "book.yaml").exists()
    assert "DRAFT" not in r.stdout
