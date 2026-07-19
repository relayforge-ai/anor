"""Social draft hygiene — human-gate, draft-only, public packs, no secrets."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "content" / "drafts"
PUBLIC = ROOT / "scenarios" / "public"


class TestSocialDrafts(unittest.TestCase):
    def test_batch_002_present(self):
        b2 = DRAFTS / "batch-002"
        self.assertTrue(b2.is_dir())
        for name in (
            "ELO-007-historical.md",
            "ELO-007-surgical_strike.md",
            "ELO-007-invasion.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b2 / name).is_file(), f"missing {name}")

    def test_batch_003_present(self):
        b3 = DRAFTS / "batch-003"
        self.assertTrue(b3.is_dir())
        for name in (
            "ELO-009-historical.md",
            "ELO-009-press_armor.md",
            "ELO-009-luftwaffe_only.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b3 / name).is_file(), f"missing {name}")

    def test_postiz_payloads_are_draft_human_gate(self):
        for path in DRAFTS.glob("batch-*/postiz-drafts.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(data.get("human_gate"), path)
            self.assertEqual(data.get("status"), "draft", path)
            self.assertIn("needs_ryan", data)
            for post in data.get("posts") or []:
                iid = post.get("integration_id") or ""
                self.assertTrue(
                    iid.startswith("INTEGRATION_") or iid == "",
                    f"{path} post {post.get('id')} has non-placeholder integration_id",
                )
                # No auto-schedule timestamps that would imply publish
                self.assertNotIn("publishDate", post)
                self.assertNotIn("scheduleDate", post)

    def test_markdown_drafts_say_do_not_publish(self):
        # Content cut drafts only (ELO-*.md) — not status/README notes
        paths = list(DRAFTS.glob("batch-*/ELO-*.md"))
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("DRAFT", text.upper(), path)
            self.assertRegex(
                text,
                re.compile(r"do not publish", re.I),
                f"{path} must say do not publish",
            )

    def test_batch_002_references_public_pack_only(self):
        pack = PUBLIC / "ELO-007.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-002").glob("ELO-007*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-007", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_003_references_public_pack_only(self):
        pack = PUBLIC / "ELO-009.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-003").glob("ELO-009*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-009", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_simulated_drafts_carry_label(self):
        labeled = [
            DRAFTS / "batch-002" / "ELO-007-surgical_strike.md",
            DRAFTS / "batch-002" / "ELO-007-invasion.md",
            DRAFTS / "batch-003" / "ELO-009-press_armor.md",
            DRAFTS / "batch-003" / "ELO-009-luftwaffe_only.md",
        ]
        for path in labeled:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                "SIMULATED" in text.upper()
                or "DRAMATIZED" in text.upper()
                or "🧪" in text,
                f"{path.name} must label non-historical cut",
            )

    def test_no_secrets_in_draft_tree(self):
        for path in DRAFTS.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".md", ".json", ".txt"}:
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            for bad in ("sk-", "API_KEY=", "BEGIN PRIVATE", "password="):
                self.assertNotIn(bad, raw, f"{path} may contain secret-like material")


if __name__ == "__main__":
    unittest.main()
