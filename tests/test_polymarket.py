"""Tests for the Polymarket source (parse + filters + normalize + score), no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import polymarket, normalize, score, schema


def _event(title, *, closed=False, active=True, liq=50000.0, vol=100000.0,
           outcomes='["Yes", "No"]', prices='["0.6", "0.4"]'):
    return {
        "id": title.replace(" ", "-"),
        "title": title,
        "slug": title.replace(" ", "-").lower(),
        "closed": closed,
        "active": active,
        "updatedAt": "2026-05-20T00:00:00Z",
        "liquidity": liq,
        "volume1mo": vol,
        "markets": [{
            "closed": closed,
            "active": active,
            "liquidity": liq,
            "volume": vol,
            "question": title + "?",
            "outcomes": outcomes,
            "outcomePrices": prices,
            "endDate": "2026-11-03T00:00:00Z",
        }],
    }


class TestParsePolymarket(unittest.TestCase):
    def test_parse_relevant_event(self):
        resp = {"events": [_event("2026 election control of Senate")], "_cap": 15}
        items = polymarket.parse_polymarket_response(resp, topic="2026 election")
        self.assertEqual(len(items), 1)
        it = items[0]
        for key in ("event_id", "title", "url", "outcome_prices", "liquidity", "relevance"):
            self.assertIn(key, it)

    def test_closed_event_filtered(self):
        resp = {"events": [_event("2026 election thing", closed=True)], "_cap": 15}
        items = polymarket.parse_polymarket_response(resp, topic="2026 election")
        self.assertEqual(items, [])

    def test_common_word_noise_dropped(self):
        # Topic "Mill.com recycler" vs an unrelated "Meek Mill" market: the
        # single shared token "mill" must not survive the per-item floor.
        resp = {"events": [_event("Will Meek Mill release an album in 2026")], "_cap": 15}
        items = polymarket.parse_polymarket_response(resp, topic="Mill.com food recycler startup")
        self.assertEqual(items, [])

    def test_drop_all_when_nothing_on_topic(self):
        # A wholly unrelated high-liquidity market for a specific topic returns nothing.
        resp = {"events": [_event("Will Bitcoin hit 200k")], "_cap": 15}
        items = polymarket.parse_polymarket_response(resp, topic="kubernetes operator pattern")
        self.assertEqual(items, [])

    def test_passes_topic_filter_guard(self):
        self.assertTrue(polymarket._passes_topic_filter("kanye west", "Will Kanye West tweet"))
        # "west" alone is a noise word -> should not rescue an NFC West market.
        self.assertFalse(polymarket._passes_topic_filter("kanye west", "Who wins the NFC West"))


class TestShortenQuestion(unittest.TestCase):
    def test_clean_entity_market(self):
        self.assertEqual(
            polymarket._shorten_question("Will Arizona win the 2026 NCAA Tournament?"),
            "Arizona",
        )
        self.assertEqual(
            polymarket._shorten_question("Will the Lakers win the title?"),
            "Lakers",
        )

    def test_enumerated_market_keeps_distinguisher(self):
        # Sibling sub-markets differ only by the number — the label must NOT
        # collapse to a bare article ("the"); the number must survive.
        a = polymarket._shorten_question(
            "Will the Republican Party hold 47 or fewer Senate seats after the 2026 midterm elections?")
        b = polymarket._shorten_question(
            "Will the Republican Party hold exactly 51 Senate seats after the 2026 midterm elections?")
        self.assertNotEqual(a, b)
        self.assertIn("47", a)
        self.assertIn("51", b)

    def test_no_bare_stopword_label(self):
        for q in ("Will there be another government shutdown?",
                  "Will the Republican Party hold 49 Senate seats?"):
            label = polymarket._shorten_question(q)
            self.assertNotIn(label.lower(), polymarket._GENERIC_LABEL_TOKENS)


class TestNormalizeAndScorePolymarket(unittest.TestCase):
    def test_normalize_and_score(self):
        resp = {"events": [_event("2026 election control of Senate")], "_cap": 15}
        raw = polymarket.parse_polymarket_response(resp, topic="2026 election")
        norm = normalize.normalize_polymarket_items(raw, "2026-05-08", "2026-06-07")
        self.assertTrue(all(isinstance(i, schema.PolymarketItem) for i in norm))
        self.assertIsNotNone(norm[0].engagement)
        self.assertIsNotNone(norm[0].engagement.volume)
        scored = score.score_polymarket_items(norm)
        self.assertTrue(all(0 <= i.score <= 100 for i in scored))

    def test_engagement_formula(self):
        high = schema.Engagement(volume=1_000_000.0, liquidity=500_000.0)
        low = schema.Engagement(volume=100.0, liquidity=50.0)
        self.assertGreater(
            score.compute_polymarket_engagement_raw(high),
            score.compute_polymarket_engagement_raw(low),
        )
        self.assertIsNone(score.compute_polymarket_engagement_raw(schema.Engagement()))


if __name__ == "__main__":
    unittest.main()
