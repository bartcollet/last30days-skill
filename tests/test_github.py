"""Tests for the GitHub source (parse + normalize + score + no-token), no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import github, normalize, score, schema

# search/issues envelope as produced by github.search_github().
_GH_ENVELOPE = {
    "items": [
        {
            "html_url": "https://github.com/anthropics/claude-code/issues/42",
            "title": "Add MCP server support",
            "body": "It would be great to support MCP servers natively.",
            "created_at": "2026-05-20T10:00:00Z",
            "comments": 30,
            "reactions": {"total_count": 55},
            "labels": [{"name": "enhancement"}],
            "state": "open",
            "user": {"login": "alice"},
        },
        {
            "html_url": "https://github.com/anthropics/claude-code/pull/43",
            "title": "Fix MCP reconnect bug",
            "body": "Reconnect logic was broken.",
            "created_at": "2026-05-22T10:00:00Z",
            "comments": 4,
            "reactions": {"total_count": 9},
            "labels": [],
            "state": "closed",
            "user": {"login": "bob"},
            "pull_request": {"url": "..."},
        },
    ],
    "context": {"core": "MCP", "from_date": "2026-05-08", "to_date": "2026-06-07", "count": 30},
}


class TestParseGitHub(unittest.TestCase):
    def test_parse_shape_and_container(self):
        items = github.parse_github_response(_GH_ENVELOPE)
        self.assertEqual(len(items), 2)
        repos = {i["container"] for i in items}
        self.assertEqual(repos, {"anthropics/claude-code"})
        first = items[0]
        for key in ("id", "title", "url", "date", "engagement", "metadata"):
            self.assertIn(key, first)

    def test_pr_vs_issue_detection(self):
        items = github.parse_github_response(_GH_ENVELOPE)
        by_title = {i["title"]: i for i in items}
        self.assertTrue(by_title["Fix MCP reconnect bug"]["metadata"]["is_pr"])
        self.assertFalse(by_title["Add MCP server support"]["metadata"]["is_pr"])

    def test_date_parsed_to_iso_day(self):
        items = github.parse_github_response(_GH_ENVELOPE)
        self.assertEqual(items[0]["date"], "2026-05-20")

    def test_no_token_returns_clean_empty_envelope(self):
        # Force no token; search_github must return an empty, error-tagged envelope
        # WITHOUT raising — the orchestrator treats this as a silent skip.
        orig = github._resolve_token
        github._resolve_token = lambda token=None: None
        try:
            env = github.search_github("anything", "2026-05-08", "2026-06-07", token=None)
        finally:
            github._resolve_token = orig
        self.assertEqual(env["items"], [])
        self.assertEqual(env.get("error"), "no token")


class TestNormalizeAndScoreGitHub(unittest.TestCase):
    def test_normalize_and_score(self):
        raw = github.parse_github_response(_GH_ENVELOPE)
        norm = normalize.normalize_github_items(raw, "2026-05-08", "2026-06-07")
        self.assertTrue(all(isinstance(i, schema.GitHubItem) for i in norm))
        scored = score.score_github_items(norm)
        self.assertTrue(all(0 <= i.score <= 100 for i in scored))

    def test_engagement_formula(self):
        high = schema.Engagement(reactions=100, comments=80)
        low = schema.Engagement(reactions=1, comments=1)
        self.assertGreater(
            score.compute_github_engagement_raw(high),
            score.compute_github_engagement_raw(low),
        )
        self.assertIsNone(score.compute_github_engagement_raw(schema.Engagement()))


if __name__ == "__main__":
    unittest.main()
