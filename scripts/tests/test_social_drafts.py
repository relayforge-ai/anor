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

    def test_batch_004_present(self):
        b4 = DRAFTS / "batch-004"
        self.assertTrue(b4.is_dir())
        for name in (
            "ELO-004-historical.md",
            "ELO-004-stand_down.md",
            "ELO-004-negotiate_delay.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b4 / name).is_file(), f"missing {name}")

    def test_batch_005_present(self):
        b5 = DRAFTS / "batch-005"
        self.assertTrue(b5.is_dir())
        for name in (
            "ELO-005-historical.md",
            "ELO-005-restrain.md",
            "ELO-005-localize_only.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b5 / name).is_file(), f"missing {name}")

    def test_batch_006_present(self):
        b6 = DRAFTS / "batch-006"
        self.assertTrue(b6.is_dir())
        for name in (
            "ELO-006-historical.md",
            "ELO-006-force_corridors.md",
            "ELO-006-negotiate_withdraw.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b6 / name).is_file(), f"missing {name}")

    def test_batch_007_present(self):
        b7 = DRAFTS / "batch-007"
        self.assertTrue(b7.is_dir())
        for name in (
            "ELO-008-historical.md",
            "ELO-008-delay_longer.md",
            "ELO-008-postpone_month.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b7 / name).is_file(), f"missing {name}")

    def test_batch_008_present(self):
        b8 = DRAFTS / "batch-008"
        self.assertTrue(b8.is_dir())
        for name in (
            "ELO-010-historical.md",
            "ELO-010-scrub.md",
            "ELO-010-dense_air.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b8 / name).is_file(), f"missing {name}")

    def test_batch_009_present(self):
        b9 = DRAFTS / "batch-009"
        self.assertTrue(b9.is_dir())
        for name in (
            "ELO-013-surface_delay.md",
            "ELO-001-immediate_accept.md",
            "ELO-001-disinformation_trap.md",
            "ELO-003-recon.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b9 / name).is_file(), f"missing {name}")

    def test_batch_010_present(self):
        b10 = DRAFTS / "batch-010"
        self.assertTrue(b10.is_dir())
        for name in (
            "ELO-011-historical.md",
            "ELO-011-stand_firm.md",
            "ELO-011-limited_deal.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b10 / name).is_file(), f"missing {name}")

    def test_batch_011_present(self):
        b11 = DRAFTS / "batch-011"
        self.assertTrue(b11.is_dir())
        for name in (
            "ELO-012-historical.md",
            "ELO-012-break_contact.md",
            "ELO-012-commit_early.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b11 / name).is_file(), f"missing {name}")

    def test_batch_012_present(self):
        b12 = DRAFTS / "batch-012"
        self.assertTrue(b12.is_dir())
        for name in (
            "ELO-014-historical.md",
            "ELO-014-refuse_charge.md",
            "ELO-014-wide_turn.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b12 / name).is_file(), f"missing {name}")

    def test_batch_013_present(self):
        b13 = DRAFTS / "batch-013"
        self.assertTrue(b13.is_dir())
        for name in (
            "ELO-015-historical.md",
            "ELO-015-harsher_terms.md",
            "ELO-015-delay_for_orders.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b13 / name).is_file(), f"missing {name}")

    def test_batch_014_present(self):
        b14 = DRAFTS / "batch-014"
        self.assertTrue(b14.is_dir())
        for name in (
            "ELO-016-historical.md",
            "ELO-016-wait_confirm.md",
            "ELO-016-disperse.md",
            "postiz-drafts.json",
            "README.md",
        ):
            self.assertTrue((b14 / name).is_file(), f"missing {name}")

    def test_every_public_choice_has_a_draft_file(self):
        """Catalog social coverage: each public pack choice has an ELO-*-{choice} draft."""
        for pack_path in sorted(PUBLIC.glob("ELO-*.json")):
            data = json.loads(pack_path.read_text(encoding="utf-8"))
            sid = data.get("scenario_id") or pack_path.stem
            for choice in data.get("choices") or []:
                cid = choice.get("id")
                self.assertTrue(cid, f"{pack_path.name} choice missing id")
                hits = list(DRAFTS.glob(f"batch-*/{sid}-{cid}.md"))
                self.assertTrue(
                    hits,
                    f"missing social draft for {sid}-{cid} under content/drafts/batch-*/",
                )

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

    def test_batch_004_references_public_pack_only(self):
        pack = PUBLIC / "ELO-004.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-004").glob("ELO-004*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-004", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_005_references_public_pack_only(self):
        pack = PUBLIC / "ELO-005.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-005").glob("ELO-005*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-005", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_006_references_public_pack_only(self):
        pack = PUBLIC / "ELO-006.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-006").glob("ELO-006*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-006", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_007_references_public_pack_only(self):
        pack = PUBLIC / "ELO-008.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-007").glob("ELO-008*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-008", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_008_references_public_pack_only(self):
        pack = PUBLIC / "ELO-010.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-008").glob("ELO-010*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-010", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_009_references_public_packs_only(self):
        for path in (DRAFTS / "batch-009").glob("ELO-*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"ELO-0\d{2}")
            self.assertIn("scenarios/public/", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_010_references_public_pack_only(self):
        pack = PUBLIC / "ELO-011.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-010").glob("ELO-011*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-011", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_011_references_public_pack_only(self):
        pack = PUBLIC / "ELO-012.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-011").glob("ELO-012*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-012", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_012_references_public_pack_only(self):
        pack = PUBLIC / "ELO-014.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-012").glob("ELO-014*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-014", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_013_references_public_pack_only(self):
        pack = PUBLIC / "ELO-015.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-013").glob("ELO-015*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-015", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_batch_014_references_public_pack_only(self):
        pack = PUBLIC / "ELO-016.json"
        self.assertTrue(pack.is_file())
        for path in (DRAFTS / "batch-014").glob("ELO-016*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ELO-016", text)
            self.assertNotIn("mandos", text.lower())
            self.assertNotIn("master source", text.lower())

    def test_simulated_drafts_carry_label(self):
        labeled = [
            DRAFTS / "batch-002" / "ELO-007-surgical_strike.md",
            DRAFTS / "batch-002" / "ELO-007-invasion.md",
            DRAFTS / "batch-003" / "ELO-009-press_armor.md",
            DRAFTS / "batch-003" / "ELO-009-luftwaffe_only.md",
            DRAFTS / "batch-004" / "ELO-004-stand_down.md",
            DRAFTS / "batch-004" / "ELO-004-negotiate_delay.md",
            DRAFTS / "batch-005" / "ELO-005-restrain.md",
            DRAFTS / "batch-005" / "ELO-005-localize_only.md",
            DRAFTS / "batch-006" / "ELO-006-force_corridors.md",
            DRAFTS / "batch-006" / "ELO-006-negotiate_withdraw.md",
            DRAFTS / "batch-007" / "ELO-008-delay_longer.md",
            DRAFTS / "batch-007" / "ELO-008-postpone_month.md",
            DRAFTS / "batch-008" / "ELO-010-scrub.md",
            DRAFTS / "batch-008" / "ELO-010-dense_air.md",
            DRAFTS / "batch-009" / "ELO-013-surface_delay.md",
            DRAFTS / "batch-009" / "ELO-001-immediate_accept.md",
            DRAFTS / "batch-009" / "ELO-001-disinformation_trap.md",
            DRAFTS / "batch-009" / "ELO-003-recon.md",
            DRAFTS / "batch-010" / "ELO-011-stand_firm.md",
            DRAFTS / "batch-010" / "ELO-011-limited_deal.md",
            DRAFTS / "batch-011" / "ELO-012-break_contact.md",
            DRAFTS / "batch-011" / "ELO-012-commit_early.md",
            DRAFTS / "batch-012" / "ELO-014-refuse_charge.md",
            DRAFTS / "batch-012" / "ELO-014-wide_turn.md",
            DRAFTS / "batch-013" / "ELO-015-harsher_terms.md",
            DRAFTS / "batch-013" / "ELO-015-delay_for_orders.md",
            DRAFTS / "batch-014" / "ELO-016-wait_confirm.md",
            DRAFTS / "batch-014" / "ELO-016-disperse.md",
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
        """Reject secret-like material without false positives on English prose.

        OpenAI-style keys look like ``sk-`` + alnum and are not preceded by a
        letter (so ``risk-spreading`` never trips the scan).
        """
        openai_sk = re.compile(r"(?<![A-Za-z])sk-[A-Za-z0-9]{8,}")
        for path in DRAFTS.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".md", ".json", ".txt"}:
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            self.assertIsNone(
                openai_sk.search(raw),
                f"{path} may contain OpenAI-style sk- secret material",
            )
            for bad in ("API_KEY=", "BEGIN PRIVATE", "password="):
                self.assertNotIn(bad, raw, f"{path} may contain secret-like material")

    def test_secret_scan_allows_risk_hyphen_prose(self):
        """Regression: Midway batch once failed on the substring sk- inside risk-."""
        sample = "Concentration versus risk-spreading under incomplete intelligence."
        openai_sk = re.compile(r"(?<![A-Za-z])sk-[A-Za-z0-9]{8,}")
        self.assertIsNone(openai_sk.search(sample))
        self.assertIsNotNone(openai_sk.search("token sk-projABCDEF12 live"))


if __name__ == "__main__":
    unittest.main()
