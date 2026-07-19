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


if __name__ == "__main__":
    unittest.main()
