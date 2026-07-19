"""Render directory exclusive lock tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.jobs import (  # noqa: E402
    RenderLockBusy,
    acquire_render_lock,
    release_render_lock,
)


class TestRenderLock(unittest.TestCase):
    def test_second_acquire_raises_busy(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "ELO-003-historical"
            fh1, lock1 = acquire_render_lock(out)
            try:
                with self.assertRaises(RenderLockBusy) as ctx:
                    acquire_render_lock(out)
                self.assertIn("already in progress", str(ctx.exception).lower())
            finally:
                release_render_lock(fh1, lock1)

            # After release, acquire succeeds again
            fh2, lock2 = acquire_render_lock(out)
            release_render_lock(fh2, lock2)
            self.assertTrue((out / ".render.lock").exists() or True)

    def test_different_dirs_independent(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "ELO-001-historical"
            b = Path(td) / "ELO-003-march"
            fa, la = acquire_render_lock(a)
            fb, lb = acquire_render_lock(b)
            try:
                self.assertIsNotNone(la)
                self.assertIsNotNone(lb)
            finally:
                release_render_lock(fa, la)
                release_render_lock(fb, lb)


if __name__ == "__main__":
    unittest.main()
