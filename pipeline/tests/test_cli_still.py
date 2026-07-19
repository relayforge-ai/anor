"""CLI ``still`` subcommand — mock media only (no live GPU)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestCliStill(unittest.TestCase):
    def test_still_from_prompt_mock(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "s.png"
            env = os.environ.copy()
            env["ANOR_MOCK_MEDIA"] = "1"
            env["PYTHONPATH"] = str(ROOT)
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pipeline.cli",
                    "still",
                    "--prompt",
                    "archival map table",
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            data = json.loads(r.stdout)
            self.assertTrue(Path(data["out_png"]).is_file())
            self.assertEqual(data["backend"], "mock")
            self.assertGreater(Path(data["out_png"]).stat().st_size, 20)

    def test_still_from_scenario_choice(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "elo.png"
            env = os.environ.copy()
            env["ANOR_MOCK_MEDIA"] = "1"
            env["PYTHONPATH"] = str(ROOT)
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pipeline.cli",
                    "still",
                    "--scenario",
                    "ELO-013",
                    "--choice",
                    "historical",
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            data = json.loads(r.stdout)
            self.assertTrue(Path(data["out_png"]).is_file())
            self.assertIn("prompt_preview", data)

    def test_still_requires_prompt_or_scenario(self):
        env = os.environ.copy()
        env["ANOR_MOCK_MEDIA"] = "1"
        env["PYTHONPATH"] = str(ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "pipeline.cli", "still"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_still_ken_burns_mock(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "kb.png"
            env = os.environ.copy()
            env["ANOR_MOCK_MEDIA"] = "1"
            env["ANOR_VIDEO_WIDTH"] = "320"
            env["ANOR_VIDEO_HEIGHT"] = "180"
            env["PYTHONPATH"] = str(ROOT)
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pipeline.cli",
                    "still",
                    "--prompt",
                    "test still",
                    "--out",
                    str(out),
                    "--ken-burns",
                    "--ken-burns-seconds",
                    "0.8",
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            data = json.loads(r.stdout)
            self.assertTrue(Path(data["out_mp4"]).is_file())
            self.assertGreater(Path(data["out_mp4"]).stat().st_size, 200)


if __name__ == "__main__":
    unittest.main()
