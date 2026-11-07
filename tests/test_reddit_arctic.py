"""Tests for the 2026-11 Reddit rework.

Reddit closed its keyless routes (.json 403, RSS ends 2026-11-13, Data API
closed to new apps), so:
- comment enrichment comes from the Arctic Shift archive (reddit_arctic.py)
- the Phase 2 subreddit drill-down runs through OpenAI web_search
- nothing in the fork contacts reddit.com directly any more
"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from lib import http, openai_reddit, reddit_arctic, reddit_enrich

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
THREAD_URL = "https://www.reddit.com/r/SEO/comments/1xa06r0/im_convinced/"


def _responses_payload(items):
    """Wrap items in the OpenAI Responses-API shape parse_reddit_response reads."""
    return {
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps({"items": items})}],
        }]
    }


# --------------------------------------------------------------------------- #
# reddit_arctic
# --------------------------------------------------------------------------- #
class TestExtractPostId(unittest.TestCase):
    def test_thread_url(self):
        self.assertEqual(reddit_arctic.extract_post_id(THREAD_URL), "1xa06r0")

    def test_non_reddit(self):
        self.assertIsNone(reddit_arctic.extract_post_id("https://example.com/r/x/comments/abc/"))

    def test_no_comments_segment(self):
        self.assertIsNone(reddit_arctic.extract_post_id("https://www.reddit.com/r/SEO/"))


class TestIsBot(unittest.TestCase):
    def test_bots(self):
        for name in ("AutoModerator", "RemindMeBot", "WikiTextBot", "summary-bot", "link_bot"):
            self.assertTrue(reddit_arctic.is_bot(name), name)

    def test_humans(self):
        for name in ("Talbot", "abbot", "seo_pro", "", "Bot_lover"):
            self.assertFalse(reddit_arctic.is_bot(name), name)


class TestFetchThread(unittest.TestCase):
    def _fake_get(self, comments, posts):
        def fake(url, **kwargs):
            self.urls.append(url)
            if "comments/search" in url:
                return {"data": comments}
            return {"data": posts}
        return fake

    def setUp(self):
        self.urls = []

    def test_parses_and_filters(self):
        comments = [
            {"id": "a", "author": "AutoModerator", "body": "Rules reminder", "score": 1,
             "created_utc": 1792500000, "permalink": "/r/SEO/comments/1xa06r0/x/a/"},
            {"id": "b", "author": "seo_pro", "body": "This is confirmation bias.", "score": 3,
             "created_utc": 1792500100, "permalink": "/r/SEO/comments/1xa06r0/x/b/"},
            {"id": "c", "author": "gone", "body": "[deleted]", "score": 9,
             "created_utc": 1792500200, "permalink": "/r/SEO/comments/1xa06r0/x/c/"},
        ]
        posts = [{"id": "1xa06r0", "num_comments": 46, "created_utc": 1792424220}]
        with mock.patch("lib.reddit_arctic.http.get", side_effect=self._fake_get(comments, posts)):
            out = reddit_arctic.fetch_thread(THREAD_URL)
        self.assertEqual([c["author"] for c in out["comments"]], ["seo_pro"])
        self.assertEqual(out["post"]["num_comments"], 46)
        self.assertTrue(all("arctic-shift.photon-reddit.com" in u for u in self.urls))
        self.assertTrue(all("link_id=1xa06r0" in u or "ids=1xa06r0" in u for u in self.urls))
        # Arctic Shift 400s on fields=...permalink; it must be rebuilt from id.
        self.assertFalse(any("permalink" in u for u in self.urls))
        self.assertEqual(out["comments"][0]["permalink"], "/r/SEO/comments/1xa06r0/comment/b/")

    def test_overload_retries_once_then_gives_up(self):
        calls = []

        def fake(url, **kwargs):
            calls.append(url)
            return {"data": None, "error": "Timeout. Maybe slow down a bit"}

        with mock.patch("lib.reddit_arctic.http.get", side_effect=fake), \
             mock.patch("lib.reddit_arctic.time.sleep"):
            out = reddit_arctic.fetch_thread(THREAD_URL)
        self.assertEqual(out, {"post": None, "comments": []})
        self.assertEqual(len(calls), 4)  # comments x2 + posts x2

    def test_http_error_is_empty_not_raised(self):
        with mock.patch("lib.reddit_arctic.http.get",
                        side_effect=http.HTTPError("HTTP 503", 503)):
            out = reddit_arctic.fetch_thread(THREAD_URL)
        self.assertEqual(out, {"post": None, "comments": []})

    def test_bad_url_makes_no_request(self):
        with mock.patch("lib.reddit_arctic.http.get") as g:
            out = reddit_arctic.fetch_thread("https://example.com/")
        g.assert_not_called()
        self.assertEqual(out["comments"], [])


# --------------------------------------------------------------------------- #
# reddit_enrich
# --------------------------------------------------------------------------- #
class TestEnrich(unittest.TestCase):
    def test_mock_fixture_enriches(self):
        with open(os.path.join(FIXTURES, "arctic_thread_sample.json")) as f:
            mock_thread = json.load(f)
        item = {"id": "R1", "url": THREAD_URL, "date": None}
        out = reddit_enrich.enrich_reddit_item(item, mock_thread)
        self.assertEqual(out["engagement"]["num_comments"], 156)
        self.assertIsNone(out["engagement"]["score"])  # stale archive score never used
        self.assertTrue(out["top_comments"])
        self.assertTrue(out["comment_insights"])
        scores = [c["score"] for c in out["top_comments"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(out["top_comments"][0]["url"].startswith("https://reddit.com/r/"))
        self.assertIsNotNone(out["date"])

    def test_archive_miss_keeps_item(self):
        item = {"id": "R1", "url": THREAD_URL, "date": "2026-10-20"}
        with mock.patch("lib.reddit_arctic.fetch_thread",
                        return_value={"post": None, "comments": []}):
            out = reddit_enrich.enrich_reddit_item(item)
        self.assertNotIn("top_comments", out)
        self.assertEqual(out["date"], "2026-10-20")

    def test_bad_mock_shape_is_ignored(self):
        item = {"id": "R1", "url": THREAD_URL}
        out = reddit_enrich.enrich_reddit_item(item, mock_thread_data=["not", "a", "dict"])
        self.assertNotIn("top_comments", out)

    def test_no_reddit_com_request(self):
        """Enrichment must never hit reddit.com itself."""
        seen = []

        def fake_get(url, **kwargs):
            seen.append(url)
            return {"data": []}

        with mock.patch("lib.reddit_arctic.http.get", side_effect=fake_get):
            reddit_enrich.enrich_reddit_item({"id": "R1", "url": THREAD_URL})
        self.assertTrue(seen)
        self.assertFalse(any("www.reddit.com" in u for u in seen))


# --------------------------------------------------------------------------- #
# Phase 2 subreddit drill-down via OpenAI web_search
# --------------------------------------------------------------------------- #
class TestSubredditDrilldown(unittest.TestCase):
    ARGS = (["r/SEO", "bard", "seo"], "AI overview citations", "2026-10-08", "2026-11-07")

    def test_no_key_no_call(self):
        with mock.patch("lib.openai_reddit.http.post") as p:
            self.assertEqual(openai_reddit.search_subreddits(*self.ARGS), [])
        p.assert_not_called()

    def test_single_web_search_call_scoped_to_reddit(self):
        captured = []

        def fake_post(url, payload, **kwargs):
            captured.append(payload)
            return {"output": []}

        with mock.patch("lib.openai_reddit.http.post", side_effect=fake_post):
            openai_reddit.search_subreddits(*self.ARGS, api_key="k", model="gpt-test")
        self.assertEqual(len(captured), 1)
        payload = captured[0]
        self.assertEqual(payload["tools"][0]["filters"]["allowed_domains"], ["reddit.com"])
        self.assertIn("r/SEO, r/bard", payload["input"])  # deduped case-insensitively
        self.assertIn("2026-10-08", payload["input"])

    def test_filters_to_requested_subs_and_caps(self):
        items = [
            {"title": "a", "url": "https://www.reddit.com/r/SEO/comments/a1/a/", "subreddit": "SEO", "relevance": 0.9},
            {"title": "b", "url": "https://www.reddit.com/r/seo/comments/b2/b/", "subreddit": "seo", "relevance": 0.5},
            {"title": "c", "url": "https://www.reddit.com/r/SEO/comments/c3/c/", "subreddit": "SEO", "relevance": 0.8},
            {"title": "d", "url": "https://www.reddit.com/r/marketing/comments/d4/d/", "subreddit": "marketing", "relevance": 0.9},
            {"title": "e", "url": "https://www.reddit.com/r/Bard/comments/e5/e/", "subreddit": "Bard", "relevance": 0.7},
        ]
        out = openai_reddit.search_subreddits(
            *self.ARGS, count_per=2, mock_response=_responses_payload(items))
        self.assertEqual([i["title"] for i in out], ["a", "b", "e"])
        self.assertEqual([i["id"] for i in out], ["RS1", "RS2", "RS3"])
        self.assertTrue(all(i["relevance"] <= 0.65 for i in out))
        self.assertEqual(out[2]["subreddit"], "bard")

    def test_http_error_returns_empty(self):
        with mock.patch("lib.openai_reddit.http.post",
                        side_effect=http.HTTPError("HTTP 500", 500, "boom")):
            out = openai_reddit.search_subreddits(*self.ARGS, api_key="k", model="gpt-test")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
