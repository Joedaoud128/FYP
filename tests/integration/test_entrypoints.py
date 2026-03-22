from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestEntrypoints(unittest.TestCase):
    def test_phase4_bridge_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "ok_script.py"
            target.write_text("print('ok')\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "phase4_bridge.py"),
                    str(target),
                    "--python",
                    sys.executable,
                    "--max-iterations",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(PROJECT_ROOT),
            )

            self.assertEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["mode"], "phase4-bridge")
            self.assertTrue(payload["success"])

    def test_phase5_debug_mode_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "ok_script.py"
            target.write_text("print('ok')\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "ESIBaiAgent.py"),
                    "--fix",
                    str(target),
                    "--python",
                    sys.executable,
                    "--max-iterations",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(PROJECT_ROOT),
            )

            self.assertEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["mode"], "debug")
            self.assertTrue(payload["success"])


if __name__ == "__main__":
    unittest.main()
