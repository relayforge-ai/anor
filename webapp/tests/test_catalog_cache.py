"""Built catalog payload cache tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")
os.environ["ANOR_CATALOG_CACHE_S"] = "60"

import webapp.server as server_mod  # noqa: E402


class TestCatalogCache(unittest.TestCase):
    def setUp(self):
        server_mod.clear_catalog_cache()
        os.environ["ANOR_CATALOG_CACHE_S"] = "60"

    def tearDown(self):
        server_mod.clear_catalog_cache()
        os.environ.pop("ANOR_CATALOG_CACHE_S", None)

    def test_build_catalog_has_available_flags(self):
        cat = server_mod.build_catalog_payload()
        self.assertIn("videos", cat)
        self.assertGreaterEqual(len(cat["videos"]), 1)
        for v in cat["videos"]:
            self.assertIn("available", v)
            self.assertIsInstance(v["available"], bool)

    def test_catalog_available_row_includes_deliverable_metrics(self):
        """When MP4 + build.json exist, catalog surfaces bytes + duration_s."""
        import json

        server_mod.clear_catalog_cache()
        videos_root = server_mod.VIDEOS
        raw = server_mod._read_json(server_mod.CATALOG)
        sample = next(
            (
                v
                for v in raw.get("videos") or []
                if isinstance(v, dict) and isinstance(v.get("file"), str)
            ),
            None,
        )
        self.assertIsNotNone(sample)
        rel = sample["file"]
        target = server_mod.safe_join(videos_root, rel)
        self.assertIsNotNone(target)
        out_dir = target.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        created_mp4 = False
        if not target.is_file():
            target.write_bytes(b"\x00" * 4096)
            created_mp4 = True
        build = out_dir / "build.json"
        prev_build = build.read_text(encoding="utf-8") if build.is_file() else None
        build.write_text(
            json.dumps(
                {
                    "out_mp4_bytes": 215701,
                    "duration_s": 60.79,
                    "cache": {
                        "still_hits": 0,
                        "tts_hits": 0,
                        "clip_hits": 0,
                        "segments": 3,
                    },
                }
            ),
            encoding="utf-8",
        )

        def _restore():
            if prev_build is None:
                build.unlink(missing_ok=True)
            else:
                build.write_text(prev_build, encoding="utf-8")
            if created_mp4:
                target.unlink(missing_ok=True)
            server_mod.clear_catalog_cache()

        self.addCleanup(_restore)
        server_mod.clear_catalog_cache()
        cat = server_mod.build_catalog_payload()
        row = next(
            (
                v
                for v in cat["videos"]
                if v.get("scenario_id") == sample["scenario_id"]
                and v.get("choice_id") == sample["choice_id"]
            ),
            None,
        )
        self.assertIsNotNone(row)
        self.assertTrue(row.get("available"))
        self.assertEqual(row.get("bytes"), 215701)
        self.assertEqual(row.get("duration_s"), 60.79)

    def test_catalog_covers_every_public_pack_choice(self):
        """Library/media-strip need a catalog row per public choice id."""
        import json

        cat = json.loads((ROOT / "webapp" / "data" / "catalog.json").read_text())
        by_pack: dict[str, set[str]] = {}
        for v in cat.get("videos") or []:
            by_pack.setdefault(v["scenario_id"], set()).add(v["choice_id"])

        public = ROOT / "scenarios" / "public"
        for path in sorted(public.glob("ELO-*.json")):
            pack = json.loads(path.read_text(encoding="utf-8"))
            sid = pack["scenario_id"]
            want = {c["id"] for c in pack.get("choices") or []}
            have = by_pack.get(sid) or set()
            self.assertTrue(
                want.issubset(have),
                f"{sid} missing catalog choices: {sorted(want - have)}",
            )

    def test_second_build_skips_file_stats(self):
        server_mod.clear_catalog_cache()
        # First build populates cache
        cat1 = server_mod.build_catalog_payload()
        # Second should not call Path.is_file if cache hits — patch is_file on Path
        with patch.object(Path, "is_file", side_effect=AssertionError("should not re-stat")):
            cat2 = server_mod.build_catalog_payload()
        self.assertEqual(cat1, cat2)

    def test_cache_disabled_rebuilds(self):
        os.environ["ANOR_CATALOG_CACHE_S"] = "0"
        server_mod.clear_catalog_cache()
        calls = {"n": 0}
        real_is_file = Path.is_file

        def counting_is_file(self):  # noqa: ANN001
            calls["n"] += 1
            return real_is_file(self)

        with patch.object(Path, "is_file", counting_is_file):
            server_mod.build_catalog_payload()
            n1 = calls["n"]
            server_mod.build_catalog_payload()
            n2 = calls["n"]
        self.assertGreater(n1, 0)
        self.assertGreater(n2, n1)

    def test_clear_catalog_cache_forces_rebuild(self):
        server_mod.clear_catalog_cache()
        server_mod.build_catalog_payload()
        server_mod.clear_catalog_cache()
        with patch.object(Path, "is_file", side_effect=AssertionError("rebuilt")):
            with self.assertRaises(AssertionError):
                server_mod.build_catalog_payload()

    def test_job_complete_invalidates_catalog_cache(self):
        """Successful render must clear catalog cache so available flags refresh."""
        import time
        from unittest.mock import MagicMock
        from webapp.jobs import VideoJobQueue

        server_mod.clear_catalog_cache()
        server_mod.build_catalog_payload()  # warm cache
        self.assertIsNotNone(server_mod._catalog_cache)

        q = VideoJobQueue()
        mock_result = MagicMock()
        mock_result.out_mp4 = Path("ELO-001-historical.mp4")
        mock_result.segments = []
        mock_result.mock_media = True

        with patch("webapp.jobs.check_render_dependencies", return_value=(True, "ok")):
            with patch("webapp.jobs.acquire_render_lock", return_value=(None, None)):
                with patch("webapp.jobs.release_render_lock"):
                    with patch(
                        "pipeline.video_pipeline.render_video",
                        return_value=mock_result,
                    ):
                        job, _ = q.enqueue(
                            "ELO-001",
                            "historical",
                            use_llm=False,
                            owner_key="t",
                            force=True,  # exercise worker + cache invalidate
                        )
                        deadline = time.time() + 5
                        final = None
                        while time.time() < deadline:
                            final = q.get(job.id)
                            if final and final.status in (
                                "completed",
                                "failed",
                                "cancelled",
                                "timed_out",
                            ):
                                break
                            time.sleep(0.02)
                        self.assertIsNotNone(final)
                        self.assertEqual(final.status, "completed", final.to_public())
        self.assertIsNone(server_mod._catalog_cache)


if __name__ == "__main__":
    unittest.main()
