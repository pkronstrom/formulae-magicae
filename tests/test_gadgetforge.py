import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1] / "skills/gadgetforge/scripts/forge.py"
HARDWARE = ("brief", "architecture", "feasibility", "contracts", "schematic",
            "arrangement", "routing", "enclosure")


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name) / "analog"
        self.run_forge("init", "--title", "Analog preamp", "--firmware", "none")

    def run_forge(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(FORGE), "--project", str(self.root), *args],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stderr or result.stdout)
        return result.stdout if ok else result.stderr

    def state(self):
        return {s["id"]: s for s in json.loads(self.run_forge("status", "--json"))}

    def brief(self):
        (self.root / "brief.md").write_text("Three knobs, no microcontroller.")
        (self.root / "concept.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        return ("--output", "brief=brief.md", "--output", "visual=concept.svg")

    def test_required_visual_and_revision_bound_review(self):
        outputs = self.brief()
        self.assertIn("visual", self.run_forge("capture", "brief", *outputs[:2], ok=False))
        self.run_forge("capture", "brief", *outputs)
        self.assertEqual(self.state()["brief"]["status"], "needs checks")
        self.record_session_decision("brief", ok=False)
        self.run_forge("evidence", "brief", "direction", "--result", "pass",
                       "--note", "Intent and scope recorded")
        self.assertEqual(self.state()["brief"]["status"], "awaiting review")
        self.assertEqual(self.state()["architecture"]["status"], "blocked")
        review = self.state()["brief"]["review"]
        status = self.run_forge("status")
        self.record_session_decision("brief")
        self.assertNotIn(review, status)
        self.assertEqual(self.state()["brief"]["status"], "accepted")
        self.assertEqual(self.state()["architecture"]["status"], "ready")
        self.run_forge("evidence", "brief", "direction", "--result", "pass",
                       "--note", "Scope rechecked against updated evidence")
        self.assertEqual(self.state()["brief"]["status"], "awaiting review")
        self.record_session_decision("brief")
        (self.root / "concept.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path/></svg>')
        self.assertEqual(self.state()["brief"]["status"], "stale")
        self.assertEqual(self.state()["architecture"]["status"], "blocked")
        self.record_session_decision("brief", ok=False)

    def record_session_decision(self, phase, *, ok=True):
        return self.run_forge("evidence", phase, "review", "--result", "pass",
                              "--note", "Fixture user agreed to the current candidate in chat", ok=ok)

    def test_existing_approvals_are_read(self):
        self.run_forge("capture", "brief", *self.brief())
        self.run_forge("evidence", "brief", "direction", "--result", "pass", "--note", "Scope checked")
        review = self.state()["brief"]["review"]
        path = self.root / ".gadgetforge/project.json"
        records = json.loads(path.read_text())
        records["approvals"][review] = {"phase": "brief", "by": "Fixture owner"}
        path.write_text(json.dumps(records))
        self.assertEqual(self.state()["brief"]["status"], "accepted")
        self.assertEqual(self.state()["architecture"]["status"], "ready")

    def test_analog_scope_and_stale_feedback(self):
        self.assertEqual(self.state()["firmware-handoff"]["status"], "not applicable")
        self.assertEqual(self.state()["firmware"]["status"], "not applicable")
        self.assertEqual(self.state()["physical"]["status"], "not applicable")
        outputs = self.brief()
        self.run_forge("capture", "brief", *outputs)
        self.run_forge("board")
        html = (self.root / "board.html").read_text()
        state = json.loads(html.split('id="app-data" type="application/json">', 1)[1].split("</script>", 1)[0])
        entry = {"id": "change-1", "phase": "brief", "basis": state["phases"][0]["basis"],
                 "kind": "change", "text": "Try a larger knob"}
        feedback = self.root / "feedback.json"
        feedback.write_text(json.dumps({"v": 1, "projectId": state["projectId"], "feedback": [entry]}))
        (self.root / "brief.md").write_text("Updated brief.")
        self.run_forge("capture", "brief", *outputs)
        self.run_forge("import-feedback", str(feedback))
        self.run_forge("import-feedback", str(feedback))
        records = json.loads(self.run_forge("feedback", "--json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "conflict")

    def accept_fixture(self, phase):
        entry = self.state()[phase]
        self.assertEqual(entry["status"], "ready")
        args = []
        for role in entry["requiredOutputs"]:
            name = f"{phase}-{role}" + (".svg" if role == "visual" else ".txt")
            (self.root / name).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>'
                                          if role == "visual" else phase)
            args.extend(("--output", f"{role}={name}"))
        self.run_forge("capture", phase, *args)
        for check in entry["requiredChecks"]:
            self.run_forge("evidence", phase, check, "--result", "pass",
                           "--note", "Simulated evidence for state-machine test")
        if entry["hasReview"]:
            self.record_session_decision(phase)
        self.assertEqual(self.state()[phase]["status"], "accepted")

    def test_analog_release_reopens_after_placement_changes(self):
        self.run_forge("configure", "--target", "package")
        for phase in (*HARDWARE, "release"):
            self.accept_fixture(phase)
        self.run_forge("configure", "--physical")
        self.assertEqual(self.state()["physical"]["status"], "ready")
        (self.root / "arrangement-board.txt").write_text("The connector moved.")
        states = self.state()
        self.assertEqual(states["schematic"]["status"], "accepted")
        for phase in ("arrangement", "routing", "enclosure", "release"):
            self.assertEqual(states[phase]["status"], "stale")
        self.assertEqual(states["physical"]["status"], "blocked")

    def test_pricing_evidence_is_independent_of_hardware(self):
        self.assertEqual(self.state()["pricing"]["status"], "not applicable")
        self.run_forge("configure", "--target", "delivery")
        self.assertEqual(self.state()["pricing"]["status"], "blocked")
        for phase in ("brief", "architecture", "pricing", "feasibility"):
            self.accept_fixture(phase)
        self.run_forge("board")
        html = (self.root / "board.html").read_text()
        data = json.loads(html.split('id="app-data" type="application/json">', 1)[1].split("</script>", 1)[0])
        estimate = next(p for p in data["phases"] if p["id"] == "pricing")
        self.assertEqual(estimate["status"], "accepted")
        self.assertTrue(estimate["previews"])
        (self.root / "pricing-estimate.txt").write_text("Revised freight estimate")
        self.assertEqual(self.state()["pricing"]["status"], "stale")
        self.assertEqual(self.state()["contracts"]["status"], "ready")
        self.run_forge("configure", "--no-pricing")
        self.assertEqual(self.state()["pricing"]["status"], "not applicable")
        self.run_forge("configure", "--target", "design", "--pricing")
        self.assertNotEqual(self.state()["pricing"]["status"], "not applicable")

    def test_hardware_release_can_precede_handoff_and_firmware(self):
        self.run_forge("configure", "--target", "delivery", "--firmware", "handoff")
        for phase in (*HARDWARE, "release"):
            self.accept_fixture(phase)
        self.assertEqual(self.state()["firmware-handoff"]["status"], "ready")
        self.run_forge("configure", "--firmware", "build")
        self.assertEqual(self.state()["release"]["status"], "accepted")
        self.accept_fixture("firmware-handoff")
        self.accept_fixture("firmware")
        (self.root / "firmware-firmware.txt").write_text("Revised firmware")
        self.assertEqual(self.state()["firmware"]["status"], "stale")
        self.assertEqual(self.state()["release"]["status"], "accepted")

    def test_factory_programming_requires_firmware_in_release(self):
        self.assertIn("firmware build", self.run_forge(
            "configure", "--target", "package", "--factory-programming", ok=False))
        self.run_forge("configure", "--target", "delivery", "--firmware", "build",
                       "--factory-programming")
        for phase in HARDWARE:
            self.accept_fixture(phase)
        self.assertEqual(self.state()["release"]["status"], "blocked")
        self.assertIn("firmware", self.state()["release"]["needs"])
        self.accept_fixture("firmware-handoff")
        self.assertEqual(self.state()["release"]["status"], "blocked")
        self.accept_fixture("firmware")
        self.accept_fixture("release")
        (self.root / "firmware-firmware.txt").write_text("Revised firmware")
        self.assertEqual(self.state()["release"]["status"], "stale")

    def test_refresh_preserves_pending_feedback(self):
        self.accept_fixture("brief")
        self.run_forge("board")
        path = self.root / "board.html"
        start = 'id="app-data" type="application/json">'
        original = path.read_text()
        data = json.loads(original.split(start, 1)[1].split("</script>", 1)[0])
        data["feedback"] = [{"id": "note", "phase": "brief", "kind": "change",
                             "basis": data["phases"][0]["basis"], "text": "Larger label"}]
        path.write_text(original.split(start, 1)[0] + start + json.dumps(data) + "</script>"
                        + original.split("</script>", 1)[1])
        self.assertIn("Import saved feedback", self.run_forge("board", ok=False))
        self.run_forge("import-feedback", str(path))
        self.run_forge("board")
        self.assertEqual(json.loads(self.run_forge("feedback", "--json"))[0]["status"], "pending")

    def test_recorded_demo_is_offline_and_independent_of_phase_acceptance(self):
        binary = b"fixture flash"
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==")
        (self.root / "flash.bin").write_bytes(binary)
        (self.root / "locked.png").write_bytes(png)
        demo = {"binary": "flash.bin", "target": "Uno proxy", "hardware": "Controller rev A",
                "sha256": hashlib.sha256(binary).hexdigest(),
                "frames": [{"caption": "Boot locked", "file": "locked.png",
                            "sha256": hashlib.sha256(png).hexdigest()}]}
        (self.root / ".gadgetforge/firmware-demo.json").write_text(json.dumps(demo))
        before = self.state()
        self.run_forge("board")
        html = (self.root / "board.html").read_text()
        data = json.loads(html.split('id="app-data" type="application/json">', 1)[1].split("</script>", 1)[0])
        phase = next(p for p in data["phases"] if p["id"] == "firmware")
        self.assertEqual(phase["status"], "not applicable")
        self.assertEqual(phase["demo"]["frames"][0]["src"], "data:image/png;base64," + base64.b64encode(png).decode())
        self.assertEqual(before, self.state())
        (self.root / "locked.png").write_bytes(b"changed")
        self.assertIn("frame changed", self.run_forge("board", ok=False))
        (self.root / "flash.bin").write_bytes(b"new build")
        self.assertIn("binary changed", self.run_forge("board", ok=False))
        self.assertEqual((self.root / "board.html").read_text(), html)


if __name__ == "__main__":
    unittest.main()
