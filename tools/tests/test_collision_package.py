"""C01: Verify Collisions lifecycle logic with native doubles; no engine claims.

Stop when assignment, stale events, tag removal and teardown pass together.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CollisionPackageTests(unittest.TestCase):
    def test_collision_tracking_lifecycle(self):
        source = (ROOT / "packages/ServerScriptService/Modules/Collisions.luau").read_text()
        fixture = (ROOT / "tests/fixtures/collisions.luau").read_text()
        script = (
            "const factory = function(game, typeof)\n" + source + "\nend\n"
            "const run = (function()\n" + fixture + "\nend)()\nrun(factory)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collisions.luau"
            path.write_text(script)
            result = subprocess.run(
                [str(ROOT / "tools/bin/lute"), "run", str(path)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("C01 pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
