"""Unit tests for exponential-backoff HTTP retry helper."""

from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.clients import PipelineError, with_exponential_backoff  # noqa: E402


class TestExponentialBackoff(unittest.TestCase):
    def test_succeeds_first_try(self):
        sleeps: list[float] = []
        result = with_exponential_backoff(
            lambda: 42,
            max_retries=3,
            base_delay_s=0.1,
            sleep_fn=sleeps.append,
            label="test",
        )
        self.assertEqual(result, 42)
        self.assertEqual(sleeps, [])

    def test_retries_then_succeeds(self):
        calls = {"n": 0}
        sleeps: list[float] = []

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError("temporary")
            return "ok"

        out = with_exponential_backoff(
            flaky,
            max_retries=3,
            base_delay_s=0.01,
            max_delay_s=1.0,
            jitter=0.0,
            sleep_fn=sleeps.append,
            label="flaky",
        )
        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(len(sleeps), 2)
        # exponential: 0.01, 0.02
        self.assertAlmostEqual(sleeps[0], 0.01, places=5)
        self.assertAlmostEqual(sleeps[1], 0.02, places=5)

    def test_does_not_retry_non_retryable_http(self):
        sleeps: list[float] = []

        def bad_request():
            raise urllib.error.HTTPError(
                "http://x", 400, "Bad", hdrs=None, fp=MagicMock(read=lambda: b"nope")
            )

        with self.assertRaises(PipelineError) as ctx:
            with_exponential_backoff(
                bad_request,
                max_retries=5,
                base_delay_s=0.01,
                jitter=0.0,
                sleep_fn=sleeps.append,
                label="bad",
            )
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(sleeps, [])

    def test_retries_429_then_gives_up(self):
        sleeps: list[float] = []
        calls = {"n": 0}

        def always_429():
            calls["n"] += 1
            fp = MagicMock()
            fp.read = lambda: b"slow down"
            raise urllib.error.HTTPError("http://x", 429, "Too Many", hdrs=None, fp=fp)

        with self.assertRaises(PipelineError) as ctx:
            with_exponential_backoff(
                always_429,
                max_retries=2,
                base_delay_s=0.01,
                max_delay_s=1.0,
                jitter=0.0,
                sleep_fn=sleeps.append,
                label="ratelimit",
            )
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(calls["n"], 3)  # initial + 2 retries
        self.assertEqual(len(sleeps), 2)

    def test_pipeline_error_retryable_flag(self):
        calls = {"n": 0}
        sleeps: list[float] = []

        def once():
            calls["n"] += 1
            if calls["n"] == 1:
                raise PipelineError("transient", retryable=True)
            return "done"

        out = with_exponential_backoff(
            once,
            max_retries=2,
            base_delay_s=0.01,
            jitter=0.0,
            sleep_fn=sleeps.append,
            label="pe",
        )
        self.assertEqual(out, "done")
        self.assertEqual(len(sleeps), 1)


if __name__ == "__main__":
    unittest.main()
