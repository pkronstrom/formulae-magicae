"""Run the portable Share package/extraction regression suite."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/share/scripts/test_share.py"
spec = importlib.util.spec_from_file_location("share_regressions", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TestShare = module.ShareTests
