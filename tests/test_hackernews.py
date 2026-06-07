"""Tests for the Hacker News source (parse + normalize + score), no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import hackernews, normalize, score, schema

# created_at_i for 2026-05-20 UTC, derived from the module's own helper so the
# fixture and the parser agree regardless of timezone.
_TS_2026_05_20 = hackernews._date_to_unix("2026-05-20")

# Minimal Algolia-shaped fixture.
_ALGOLIA_FIXTURE = {
    "hits": [
        {
            "objectID": "111",
            "title": "Claude Code as a daily driver",
            "url": "https://example.com/claude",
            "author": "alice",
            "points": 420,
            "num_comments": 200,
            "created_at_i": _TS_2026_05_20,
        },
        {
            "objectID": "222",
            "title": "Show HN: a banana bread recipe app",
            "url": "https://example.com/bread",
            "author": "bob",
            "points": 5,
            "num_comments": 1,
            "created_at_i": _TS_2026_05_20,
        },
    ]
}


class TestParseHackerNews(unittest.TestCase):
    def test_parse_shape(self):
        items = hackernews.parse_hackernews_response(_ALGOLIA_FIXTURE, query="Claude Code")
        self.assertTrue(items)
        it = items[0]
        for key in ("id", "title", "hn_url", "engagement", "relevance", "date"):
            self.assertIn(key, it)
        self.assertEqual(it["engagement"]["points"], 420)
        self.assertEqual(it["date"], "2026-05-20")
        self.assertTrue(it["hn_url"].startswith("https://news.ycombinator.com/item?id="))

    def test_prefix_filter_drops_unrelated_show_hn(self):
        # The bread "Show HN" shares no query token with "Claude Code".
        items = hackernews.parse_hackernews_response(_ALGOLIA_FIXTURE, query="Claude Code")
        titles = [i["title"] for i in items]
        self.assertIn("Claude Code as a daily driver", titles)
        self.assertNotIn("Show HN: a banana bread recipe app", titles)

    def test_relevance_is_heuristic_float(self):
        items = hackernews.parse_hackernews_response(_ALGOLIA_FIXTURE, query="Claude Code")
        self.assertIsInstance(items[0]["relevance"], float)
        self.assertLessEqual(items[0]["relevance"], 1.0)


class TestNormalizeAndScoreHN(unittest.TestCase):
    def test_normalize_and_score(self):
        raw = hackernews.parse_hackernews_response(_ALGOLIA_FIXTURE, query="Claude Code")
        norm = normalize.normalize_hn_items(raw, "2026-05-08", "2026-06-07")
        self.assertTrue(all(isinstance(i, schema.HackerNewsItem) for i in norm))
        scored = score.score_hn_items(norm)
        self.assertTrue(all(0 <= i.score <= 100 for i in scored))

    def test_date_filter_drops_out_of_range(self):
        raw = hackernews.parse_hackernews_response(_ALGOLIA_FIXTURE, query="Claude Code")
        norm = normalize.normalize_hn_items(raw, "2026-05-08", "2026-06-07")
        # Tighten range so the 2026-05-20 item falls outside.
        kept = normalize.filter_by_date_range(norm, "2026-06-01", "2026-06-07")
        self.assertEqual(kept, [])

    def test_engagement_formula_orders_by_points(self):
        high = schema.Engagement(points=500, comments=300)
        low = schema.Engagement(points=2, comments=1)
        self.assertGreater(
            score.compute_hn_engagement_raw(high),
            score.compute_hn_engagement_raw(low),
        )
        self.assertIsNone(score.compute_hn_engagement_raw(schema.Engagement()))


if __name__ == "__main__":
    unittest.main()
