"""robots.txt + sitemap.xml for freemium discovery (no browser)."""

from __future__ import annotations

import os
import sys
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.server import (  # noqa: E402
    Handler,
    build_robots_txt,
    build_sitemap_xml,
    public_base_url,
)


class TestSeoBuilders(unittest.TestCase):
    def test_robots_disallows_api_and_points_sitemap(self):
        txt = build_robots_txt("https://example.test")
        self.assertIn("User-agent: *", txt)
        self.assertIn("Disallow: /api/", txt)
        self.assertIn("Disallow: /media/", txt)
        self.assertIn("Allow: /", txt)
        self.assertIn("Sitemap: https://example.test/sitemap.xml", txt)

    def test_sitemap_includes_core_and_pack_links(self):
        catalog = {
            "videos": [
                {"id": "ELO-003-historical"},
                {"id": "ELO-013-launch"},
            ]
        }
        scenarios = [
            {"scenario_id": "ELO-003"},
            {"scenario_id": "ELO-013"},
        ]
        xml = build_sitemap_xml(
            "https://example.test", catalog=catalog, scenarios=scenarios
        )
        self.assertIn("https://example.test/", xml)
        self.assertIn("https://example.test/#/library", xml)
        self.assertIn("https://example.test/#/pricing", xml)
        self.assertIn("https://example.test/#/studio/ELO-003", xml)
        self.assertIn("https://example.test/#/watch/ELO-003-historical", xml)
        # Well-formed XML
        root = ET.fromstring(xml)
        self.assertTrue(root.tag.endswith("urlset"))
        locs = [
            el.text
            for el in root.iter()
            if el.tag.endswith("loc") and el.text
        ]
        self.assertGreaterEqual(len(locs), 6)

    def test_sitemap_skips_path_traversal_ids(self):
        xml = build_sitemap_xml(
            "https://example.test",
            catalog={"videos": [{"id": "../etc/passwd"}, {"id": "ok-ep"}]},
            scenarios=[{"scenario_id": "ELO-003"}, {"scenario_id": "../x"}],
        )
        self.assertNotIn("../", xml)
        self.assertIn("#/watch/ok-ep", xml)
        self.assertIn("#/studio/ELO-003", xml)

    def test_public_base_url_prefers_env(self):
        prev = os.environ.get("ANOR_PUBLIC_URL")
        os.environ["ANOR_PUBLIC_URL"] = "https://forked.example/"
        try:
            self.assertEqual(public_base_url(), "https://forked.example")
        finally:
            if prev is None:
                os.environ.pop("ANOR_PUBLIC_URL", None)
            else:
                os.environ["ANOR_PUBLIC_URL"] = prev


class TestSeoHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_robots_endpoint(self):
        with urllib.request.urlopen(self.base + "/robots.txt", timeout=5) as r:
            body = r.read().decode("utf-8")
            self.assertEqual(r.status, 200)
            self.assertIn("text/plain", r.headers.get("Content-Type", ""))
            self.assertIn("Sitemap:", body)
            self.assertIn("Disallow: /api/", body)

    def test_sitemap_endpoint(self):
        with urllib.request.urlopen(self.base + "/sitemap.xml", timeout=5) as r:
            body = r.read().decode("utf-8")
            self.assertEqual(r.status, 200)
            ctype = r.headers.get("Content-Type", "")
            self.assertTrue("xml" in ctype)
            self.assertIn("<urlset", body)
            self.assertIn("#/library", body)
            self.assertIn("#/studio/", body)
            # Live catalog packs appear
            self.assertIn("ELO-", body)
            ET.fromstring(body)


if __name__ == "__main__":
    unittest.main()
