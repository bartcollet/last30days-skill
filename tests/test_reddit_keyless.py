"""Tests for the keyless Reddit fallback (RSS discovery + shreddit comments).

Ported alongside reddit_rss.py / reddit_shreddit.py when Reddit's .json paths
went 403. Covers the parsers, the DTD/XXE guard, http.get_text, and the
fallback wiring in openai_reddit.search_subreddits + reddit_enrich.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from lib import http, openai_reddit, reddit_enrich, reddit_rss, reddit_shreddit


ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Best Rust web frameworks in 2026</title>
    <link href="https://www.reddit.com/r/rust/comments/abc123/best_rust_web_frameworks/"/>
    <category term="rust"/>
    <updated>2026-05-20T18:48:31+00:00</updated>
    <author><name>/u/someone</name></author>
  </entry>
  <entry>
    <title>Not a thread, just a user page</title>
    <link href="https://www.reddit.com/user/foo"/>
    <updated>2026-05-21T10:00:00+00:00</updated>
  </entry>
</feed>"""

DTD_FEED = """<?xml version="1.0"?>
<!DOCTYPE feed [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
  <link href="https://www.reddit.com/r/x/comments/y/z/"/>
</entry></feed>"""

SHREDDIT_HTML = """
<shreddit-comment-tree total-comments="156">
<shreddit-comment score="42" author="alice" created="2026-05-20T10:00:00+00:00"
  permalink="/r/rust/comments/abc123/x/c1/" thingId="t1_aaa">
  <div id="t1_aaa-post-rtjson-content"><p>This is a substantive comment about
  the topic with more than enough length to pass the insight filter.</p></div>
</shreddit-comment>
<shreddit-comment score="100" author="bob" created="2026-05-21T10:00:00+00:00"
  permalink="/r/rust/comments/abc123/x/c2/" thingId="t1_bbb">
  <div id="t1_bbb-post-rtjson-content"><p>Another insightful and lengthy comment
  that should be captured and ranked above the lower-scored one.</p></div>
</shreddit-comment>
<shreddit-comment score="5" author="[deleted]" thingId="t1_ccc">
  <div id="t1_ccc-post-rtjson-content"><p>removed content here</p></div>
</shreddit-comment>
</shreddit-comment-tree>
"""


# --------------------------------------------------------------------------- #
# reddit_rss
# --------------------------------------------------------------------------- #
class TestRssParse(unittest.TestCase):
    def test_parse_feed_extracts_comment_threads_only(self):
        items = reddit_rss.parse_feed(ATOM_FEED, sub="rust")
        self.assertEqual(len(items), 1)  # user page dropped (no /comments/)
        it = items[0]
        self.assertEqual(it["subreddit"], "rust")
        self.assertEqual(it["date"], "2026-05-20")
        self.assertIn("/comments/", it["url"])
        self.assertTrue(it["id"].startswith("RS"))
        self.assertEqual(it["relevance"], 0.6)

    def test_dtd_feed_is_rejected(self):
        # XXE / billion-laughs guard: anything with a DTD is refused.
        self.assertEqual(reddit_rss.parse_feed(DTD_FEED, sub="x"), [])

    def test_garbage_returns_empty(self):
        self.assertEqual(reddit_rss.parse_feed("not xml at all", sub="x"), [])
        self.assertEqual(reddit_rss.parse_feed("", sub="x"), [])

    def test_search_subreddits_rss_dedupes(self):
        with mock.patch("lib.http.get_text", return_value=ATOM_FEED):
            items = reddit_rss.search_subreddits_rss(["r/rust", "rust"], "web frameworks")
        # Same feed for both subs -> URL dedupe keeps one.
        self.assertEqual(len(items), 1)

    def test_search_subreddits_rss_handles_fetch_failure(self):
        with mock.patch("lib.http.get_text", return_value=None):
            self.assertEqual(reddit_rss.search_subreddits_rss(["rust"], "x"), [])


# --------------------------------------------------------------------------- #
# reddit_shreddit
# --------------------------------------------------------------------------- #
class TestShreddit(unittest.TestCase):
    def test_extract_post_ref(self):
        ref = reddit_shreddit.extract_post_ref(
            "https://www.reddit.com/r/rust/comments/abc123/title/"
        )
        self.assertEqual(ref, ("rust", "abc123"))
        self.assertIsNone(reddit_shreddit.extract_post_ref("https://example.com/x"))

    def test_parse_comments_sorts_and_filters(self):
        comments = reddit_shreddit.parse_comments(SHREDDIT_HTML)
        self.assertEqual(len(comments), 2)  # [deleted] dropped
        self.assertEqual(comments[0]["author"], "bob")   # 100 > 42
        self.assertEqual(comments[0]["score"], 100)
        self.assertEqual(comments[1]["author"], "alice")
        self.assertTrue(comments[0]["url"].startswith("https://reddit.com/r/rust/"))

    def test_does_not_match_comment_tree_tag(self):
        # The <shreddit-comment-tree> wrapper must not be parsed as a comment.
        only_tree = '<shreddit-comment-tree total-comments="3"></shreddit-comment-tree>'
        self.assertEqual(reddit_shreddit.parse_comments(only_tree), [])

    def test_fetch_comments_success(self):
        with mock.patch("lib.http.get_text", return_value=SHREDDIT_HTML):
            out = reddit_shreddit.fetch_comments(
                "https://www.reddit.com/r/rust/comments/abc123/t/"
            )
        self.assertEqual(out["num_comments"], 156)
        self.assertEqual(len(out["top_comments"]), 2)
        self.assertTrue(out["comment_insights"])

    def test_fetch_comments_failure_returns_empty(self):
        with mock.patch("lib.http.get_text", return_value=None):
            out = reddit_shreddit.fetch_comments(
                "https://www.reddit.com/r/rust/comments/abc123/t/"
            )
        self.assertEqual(out["top_comments"], [])
        self.assertIsNone(out["num_comments"])


# --------------------------------------------------------------------------- #
# http.get_text
# --------------------------------------------------------------------------- #
class TestGetText(unittest.TestCase):
    def test_returns_text_on_success(self):
        class _Resp:
            headers = {}
            def read(self): return b"hello world"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch("lib.http.urllib.request.urlopen", return_value=_Resp()):
            self.assertEqual(http.get_text("https://example.com"), "hello world")

    def test_returns_none_on_404(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch("lib.http.urllib.request.urlopen", side_effect=err):
            self.assertIsNone(http.get_text("https://example.com", retries=1))


# --------------------------------------------------------------------------- #
# Fallback wiring
# --------------------------------------------------------------------------- #
class TestFallbackWiring(unittest.TestCase):
    def test_search_subreddits_falls_back_to_rss_on_403(self):
        err = http.HTTPError("HTTP 403: Blocked", 403)
        with mock.patch("lib.openai_reddit.http.get", side_effect=err), \
             mock.patch("lib.http.get_text", return_value=ATOM_FEED):
            items = openai_reddit.search_subreddits(
                ["rust"], "web frameworks", "2026-05-01", "2026-05-31"
            )
        # .json 403'd; RSS fallback recovered the thread.
        self.assertEqual(len(items), 1)
        self.assertIn("/comments/", items[0]["url"])

    def test_enrich_falls_back_to_shreddit_when_json_empty(self):
        canned = {
            "top_comments": [{"score": 100, "date": "2026-05-21", "author": "bob",
                              "excerpt": "great point", "url": "https://reddit.com/x"}],
            "comment_insights": ["great point about the topic"],
            "num_comments": 156,
        }
        item = {"url": "https://www.reddit.com/r/rust/comments/abc123/t/", "title": "t"}
        with mock.patch("lib.reddit_enrich.fetch_thread_data", return_value=None), \
             mock.patch("lib.reddit_shreddit.fetch_comments", return_value=canned):
            out = reddit_enrich.enrich_reddit_item(item)
        self.assertEqual(len(out["top_comments"]), 1)
        self.assertEqual(out["comment_insights"], ["great point about the topic"])
        self.assertEqual(out["engagement"]["num_comments"], 156)

    def test_enrich_skips_shreddit_in_mock_mode(self):
        # With mock_thread_data supplied, no live shreddit call should fire.
        item = {"url": "https://www.reddit.com/r/rust/comments/abc123/t/"}
        with mock.patch("lib.reddit_shreddit.fetch_comments") as fc:
            reddit_enrich.enrich_reddit_item(item, mock_thread_data={"bad": "shape"})
            fc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
