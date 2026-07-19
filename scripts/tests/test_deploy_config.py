"""Deploy config hygiene — Dockerfile / compose / docs (no Docker daemon required)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestDeployConfig(unittest.TestCase):
    def test_dockerfile_exists_and_is_env_driven(self):
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("python:3.12-slim", df)
        self.assertIn("ffmpeg", df)
        self.assertIn("webapp.server", df)
        self.assertIn("0.0.0.0", df)
        self.assertIn("ANOR_MOCK_MEDIA", df)
        # No hardcoded private fleet hosts or secrets
        for bad in (
            "dawes:",
            "nauvoo:",
            "ganymede:",
            "sk-",
            "API_KEY=",
            "password",
        ):
            self.assertNotIn(bad.lower(), df.lower() if bad != "API_KEY=" else df)
        # Healthcheck uses stdlib urllib, not curl
        self.assertIn("urllib.request", df)
        self.assertIn("/api/health", df)
        # Non-root runtime
        self.assertRegex(df, re.compile(r"^USER\s+anor\s*$", re.M))
        self.assertIn("10001", df)
        self.assertIn("useradd", df)
        self.assertIn("/app/outputs/videos", df)

    def test_compose_wires_endpoint_env_vars(self):
        raw = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for key in (
            "LLM_URL",
            "IMAGE_URL",
            "TTS_URL",
            "ANOR_MOCK_MEDIA",
            "LLM_API_KEY",
            "IMAGE_API_KEY",
            "TTS_API_KEY",
            "IMAGE_BACKEND",
            "host.docker.internal",
        ):
            self.assertIn(key, raw)
        # Secrets must not be literal values — only ${VAR} or empty default
        self.assertNotRegex(raw, r"LLM_API_KEY:\s*['\"]?[a-zA-Z0-9_\-]{16,}")
        self.assertIn("anor_videos", raw)
        self.assertIn("forked-history", raw)
        # Non-root (match Dockerfile uid)
        self.assertIn('user: "10001:10001"', raw)

    def test_dockerfile_user_comes_before_cmd(self):
        """USER must apply to CMD/HEALTHCHECK (no root by default)."""
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        user_i = df.rfind("\nUSER ")
        cmd_i = df.rfind("\nCMD ")
        self.assertGreater(user_i, 0)
        self.assertGreater(cmd_i, user_i)

    def test_dockerignore_excludes_secrets_and_outputs(self):
        di = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for needle in (".env", "outputs/", ".git", "content/drafts/"):
            self.assertIn(needle, di)

    def test_deploy_doc_present(self):
        doc = (ROOT / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("LLM_URL", doc)
        self.assertIn("ANOR_MOCK_MEDIA", doc)
        self.assertIn("docker compose", doc)
        self.assertIn("host.docker.internal", doc)
        self.assertIn("10001", doc)
        self.assertIn("non-root", doc.lower())
        # Guardrail language
        self.assertRegex(doc, re.compile(r"secret|never commit", re.I))

    def test_env_example_documents_urls(self):
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in ("LLM_URL=", "IMAGE_URL=", "TTS_URL=", "ANOR_MOCK_MEDIA"):
            self.assertIn(key, env)


if __name__ == "__main__":
    unittest.main()
