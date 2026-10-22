"""S01: Check scaffold departure dispatch with native doubles; no engine claims."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ScaffoldEntryTests(unittest.TestCase):
    def test_player_departure_dispatch_and_optional_packages(self):
        spec = importlib.util.spec_from_file_location(
            "scaffold", ROOT / "shared/skills/rblx-new-game/scripts/scaffold.py",
        )
        scaffold = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scaffold)
        fixture = (ROOT / "tests/fixtures/scaffold-server.luau").read_text()
        source = (
            "const start = function(game, require, task)\n" + scaffold.SERVER_ENTRY + "\nend\n"
            "const run = (function()\n" + fixture + "\nend)()\nrun(start)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scaffold-server.luau"
            path.write_text(source)
            result = subprocess.run(
                [str(ROOT / "tools/bin/lute"), "run", str(path)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("S01 pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
