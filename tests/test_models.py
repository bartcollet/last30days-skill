"""Tests for models module."""

import sys
import tempfile
import unittest
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import cache, models


class CacheIsolatedTestCase(unittest.TestCase):
    """Base case that redirects the persistent model-selection cache to a
    temp file per test.

    ``models.select_openai_model`` / ``select_xai_model`` short-circuit on
    ``cache.MODEL_CACHE_FILE`` (default ``~/.cache/last30days/model_selection.json``).
    Without isolation, a real `/last30days` run (or another test) that cached
    e.g. ``gpt-4.1`` poisons the auto-selection assertions here, making them
    flaky. Redirecting the cache also stops tests from clobbering the user's
    real cache.
    """

    def setUp(self):
        super().setUp()
        self._orig_cache_file = cache.MODEL_CACHE_FILE
        self._tmpdir = tempfile.TemporaryDirectory()
        cache.MODEL_CACHE_FILE = Path(self._tmpdir.name) / "model_selection.json"

    def tearDown(self):
        cache.MODEL_CACHE_FILE = self._orig_cache_file
        self._tmpdir.cleanup()
        super().tearDown()


class TestParseVersion(unittest.TestCase):
    def test_simple_version(self):
        result = models.parse_version("gpt-5")
        self.assertEqual(result, (5,))

    def test_minor_version(self):
        result = models.parse_version("gpt-5.2")
        self.assertEqual(result, (5, 2))

    def test_patch_version(self):
        result = models.parse_version("gpt-5.2.1")
        self.assertEqual(result, (5, 2, 1))

    def test_no_version(self):
        result = models.parse_version("custom-model")
        self.assertIsNone(result)


class TestIsMainlineOpenAIModel(unittest.TestCase):
    def test_gpt5_is_mainline(self):
        self.assertTrue(models.is_mainline_openai_model("gpt-5"))

    def test_gpt52_is_mainline(self):
        self.assertTrue(models.is_mainline_openai_model("gpt-5.2"))

    def test_gpt5_mini_is_not_mainline(self):
        self.assertFalse(models.is_mainline_openai_model("gpt-5-mini"))

    def test_gpt4_is_not_mainline(self):
        self.assertFalse(models.is_mainline_openai_model("gpt-4"))


class TestSelectOpenAIModel(CacheIsolatedTestCase):
    def test_pinned_policy(self):
        result = models.select_openai_model(
            "fake-key",
            policy="pinned",
            pin="gpt-5.1"
        )
        self.assertEqual(result, "gpt-5.1")

    def test_auto_with_mock_models(self):
        mock_models = [
            {"id": "gpt-5.2", "created": 1704067200},
            {"id": "gpt-5.1", "created": 1701388800},
            {"id": "gpt-5", "created": 1698710400},
        ]
        result = models.select_openai_model(
            "fake-key",
            policy="auto",
            mock_models=mock_models
        )
        self.assertEqual(result, "gpt-5.2")

    def test_auto_filters_variants(self):
        mock_models = [
            {"id": "gpt-5.2", "created": 1704067200},
            {"id": "gpt-5-mini", "created": 1704067200},
            {"id": "gpt-5.1", "created": 1701388800},
        ]
        result = models.select_openai_model(
            "fake-key",
            policy="auto",
            mock_models=mock_models
        )
        self.assertEqual(result, "gpt-5.2")


class TestSelectXAIModel(CacheIsolatedTestCase):
    def test_latest_policy(self):
        result = models.select_xai_model(
            "fake-key",
            policy="latest"
        )
        # Track the alias map rather than a hardcoded string so this doesn't
        # drift every time the required x_search model changes.
        self.assertEqual(result, models.XAI_ALIASES["latest"])

    def test_stable_policy(self):
        # Cache is isolated per-test via CacheIsolatedTestCase.
        result = models.select_xai_model(
            "fake-key",
            policy="stable"
        )
        self.assertEqual(result, models.XAI_ALIASES["stable"])

    def test_pinned_policy(self):
        result = models.select_xai_model(
            "fake-key",
            policy="pinned",
            pin="grok-3"
        )
        self.assertEqual(result, "grok-3")


class TestGetModels(CacheIsolatedTestCase):
    def test_no_keys_returns_none(self):
        config = {}
        result = models.get_models(config)
        self.assertIsNone(result["openai"])
        self.assertIsNone(result["xai"])

    def test_openai_key_only(self):
        config = {"OPENAI_API_KEY": "sk-test"}
        mock_models = [{"id": "gpt-5.2", "created": 1704067200}]
        result = models.get_models(config, mock_openai_models=mock_models)
        self.assertEqual(result["openai"], "gpt-5.2")
        self.assertIsNone(result["xai"])

    def test_both_keys(self):
        config = {
            "OPENAI_API_KEY": "sk-test",
            "XAI_API_KEY": "xai-test",
        }
        mock_openai = [{"id": "gpt-5.2", "created": 1704067200}]
        mock_xai = [{"id": "grok-4-latest", "created": 1704067200}]
        result = models.get_models(config, mock_openai, mock_xai)
        self.assertEqual(result["openai"], "gpt-5.2")
        # Default xAI policy is "latest", which resolves via the alias map.
        self.assertEqual(result["xai"], models.XAI_ALIASES["latest"])


if __name__ == "__main__":
    unittest.main()
