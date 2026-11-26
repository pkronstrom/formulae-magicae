import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "skills/gadgetforge/scripts/pcb_spice.py"


class SpicePluginTest(unittest.TestCase):
    def test_check_compares_measured_values_with_limits(self):
        with tempfile.TemporaryDirectory() as sandbox:
            root = Path(sandbox)
            netlist = root / "filter.cir"
            netlist.write_text("Test fixture\n.end\n")
            report = root / "report.json"
            fake = root / "ngspice"
            fake.write_text(
                '#!/bin/sh\n'
                '[ "$1" = -n ] && [ "$2" = -b ] && [ -f "$3" ] || exit 9\n'
                'printf "gain = -2.5e+00   at= 1.0e+03\\n"\n'
            )
            fake.chmod(0o755)
            env = {**os.environ, "PATH": str(root)}
            for name, low, high, expected, code in (
                ("GAIN", "-3", "-2", "pass", 0),
                ("gain", "-2", "-1", "fail", 1),
                ("missing", "-3", "-2", "unknown", 2),
            ):
                with self.subTest(expected=expected):
                    command = [sys.executable, str(PLUGIN), str(netlist), "--report", str(report),
                               "--expect", name, low, high]
                    run = subprocess.run(command, text=True, capture_output=True, env=env)
                    self.assertEqual(run.returncode, code, run.stderr or run.stdout)
                    result = json.loads(report.read_text())
                    self.assertEqual(result["result"], expected)
                    self.assertEqual(result["measurements"][0]["value"],
                                     None if name == "missing" else -2.5)

    def test_requires_optional_ngspice_executable(self):
        with tempfile.TemporaryDirectory() as sandbox:
            root = Path(sandbox)
            netlist = root / "test.cir"
            netlist.write_text("Test fixture\n.end\n")
            report = root / "check.json"
            run = subprocess.run(
                [sys.executable, str(PLUGIN), str(netlist), "--report", str(report),
                 "--expect", "voltage", "0", "1"],
                capture_output=True, text=True, env={**os.environ, "PATH": str(root)},
            )
            self.assertEqual(run.returncode, 2)
            self.assertIn("ngspice was not found", run.stderr)
            self.assertFalse(report.exists())
