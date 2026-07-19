"""Keep PIPELINE.md aligned with public packs and hard guardrails."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "PIPELINE.md"
PUBLIC = ROOT / "scenarios" / "public"


class TestPipelineDocs(unittest.TestCase):
    def test_pipeline_md_exists(self):
        self.assertTrue(PIPELINE.is_file())

    def test_pipeline_lists_every_public_pack(self):
        doc = PIPELINE.read_text(encoding="utf-8")
        pack_ids = sorted(p.stem for p in PUBLIC.glob("ELO-*.json"))
        self.assertGreaterEqual(len(pack_ids), 4)
        for sid in pack_ids:
            self.assertIn(sid, doc, f"PIPELINE.md missing pack {sid}")

    def test_pipeline_states_guardrails(self):
        doc = PIPELINE.read_text(encoding="utf-8")
        for needle in (
            "LLM_URL",
            "IMAGE_URL",
            "TTS_URL",
            "scenarios/public",
            "MANDOS",
            "documented",
            "simulated",
            "draft",
            "ANOR_MOCK_MEDIA",
            "DEPLOY.md",
            "webapp/",
            "content/drafts",
            "Never",  # never auto-publish language appears nearby
        ):
            self.assertIn(needle, doc)

    def test_pipeline_mentions_human_gate_not_auto_publish(self):
        doc = PIPELINE.read_text(encoding="utf-8")
        self.assertRegex(
            doc,
            re.compile(r"human.?gate|Ryan", re.I),
        )
        self.assertRegex(
            doc,
            re.compile(r"auto-?publish|must not publish", re.I),
        )

    def test_no_secrets_in_pipeline_doc(self):
        doc = PIPELINE.read_text(encoding="utf-8")
        for bad in ("sk-", "BEGIN PRIVATE", "password="):
            self.assertNotIn(bad, doc)


if __name__ == "__main__":
    unittest.main()
