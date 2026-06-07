"""Round-trip (to_dict/from_dict) tests for the new source dataclasses.

The cache layer serializes a Report to JSON and rebuilds it via from_dict, so
HN/GitHub/Polymarket items must survive a round-trip without loss.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import schema


class TestReportRoundTrip(unittest.TestCase):
    def _report(self):
        rep = schema.create_report("topic", "2026-05-08", "2026-06-07", "all")
        rep.hackernews = [schema.HackerNewsItem(
            id="1", title="HN story", url="https://e.com", hn_url="https://news.ycombinator.com/item?id=1",
            author="alice", date="2026-05-20", date_confidence="high",
            engagement=schema.Engagement(points=100, comments=50),
            comment_insights=["insight one"], relevance=0.9, why_relevant="why", score=80,
        )]
        rep.github = [schema.GitHubItem(
            id="GH1", title="Issue", url="https://github.com/a/b/issues/1", author="bob",
            container="a/b", snippet="body", date="2026-05-21", date_confidence="high",
            engagement=schema.Engagement(reactions=20, comments=10), is_pr=True, state="open",
            labels=["bug"], top_comments=[{"author": "x", "excerpt": "y", "score": 1}],
            relevance=0.8, why_relevant="why", score=70,
        )]
        rep.polymarket = [schema.PolymarketItem(
            id="ev1", title="Market", url="https://polymarket.com/event/ev1", question="Will X?",
            outcome_prices=[("Yes", 0.6), ("No", 0.4)], outcomes_remaining=0,
            price_movement="up 5% this week", end_date="2026-11-03", date="2026-05-22",
            date_confidence="high", engagement=schema.Engagement(volume=1000.0, liquidity=500.0, odds=0.6),
            relevance=0.7, why_relevant="why", score=60,
        )]
        return rep

    def test_round_trip_preserves_all_new_sources(self):
        rep = self._report()
        rt = schema.Report.from_dict(rep.to_dict())
        self.assertEqual(len(rt.hackernews), 1)
        self.assertEqual(len(rt.github), 1)
        self.assertEqual(len(rt.polymarket), 1)

    def test_round_trip_is_stable(self):
        rep = self._report()
        once = rep.to_dict()
        twice = schema.Report.from_dict(once).to_dict()
        self.assertEqual(once["hackernews"], twice["hackernews"])
        self.assertEqual(once["github"], twice["github"])
        self.assertEqual(once["polymarket"], twice["polymarket"])

    def test_field_fidelity(self):
        rt = schema.Report.from_dict(self._report().to_dict())
        self.assertEqual(rt.hackernews[0].engagement.points, 100)
        self.assertTrue(rt.github[0].is_pr)
        self.assertEqual(rt.github[0].container, "a/b")
        self.assertEqual(rt.polymarket[0].outcome_prices[0], ("Yes", 0.6))
        self.assertEqual(rt.polymarket[0].engagement.odds, 0.6)

    def test_existing_sources_serialize_unchanged_keys(self):
        # Reddit/X items must not gain new keys from the Engagement extension.
        rep = schema.create_report("t", "2026-05-08", "2026-06-07", "both")
        rep.reddit = [schema.RedditItem(
            id="R1", title="t", url="u", subreddit="s",
            engagement=schema.Engagement(score=10, num_comments=5, upvote_ratio=0.9),
        )]
        d = rep.to_dict()["reddit"][0]["engagement"]
        self.assertEqual(set(d.keys()), {"score", "num_comments", "upvote_ratio"})


if __name__ == "__main__":
    unittest.main()
