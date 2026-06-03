"""Tests for the 2026-06 robustness hardening pass.

Covers:
- coerce.py defensive numeric coercion
- http.py browser headers, gzip/deflate decode, exponential backoff
- get_reddit_json / search_subreddits browser fingerprint + removeprefix
- xai_x.parse_x_response raising on unparseable 200 (not on genuine empty)
- parse_*_response tolerating weird relevance/engagement values
- bird_x._run_bird_search retrying once on non-JSON stdout
"""

import gzip
import os
import sys
import unittest
import zlib
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from lib import bird_x, coerce, http, openai_reddit, xai_x


class _FakeResponse:
    """Minimal context-manager stand-in for an http.client response."""

    def __init__(self, body: bytes, headers=None, status=200):
        self._body = body
        self.headers = headers or {}
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Headers(dict):
    """dict with the .get(name) call urllib responses expose (case kept simple)."""


# --------------------------------------------------------------------------- #
# coerce.py
# --------------------------------------------------------------------------- #
class TestCoerceRelevance(unittest.TestCase):
    def test_passthrough_float(self):
        self.assertEqual(coerce.coerce_relevance(0.8), 0.8)

    def test_clamps_high(self):
        self.assertEqual(coerce.coerce_relevance(5), 1.0)

    def test_clamps_low(self):
        self.assertEqual(coerce.coerce_relevance(-3), 0.0)

    def test_numeric_string(self):
        self.assertEqual(coerce.coerce_relevance("0.65"), 0.65)

    def test_leading_number_in_string(self):
        self.assertEqual(coerce.coerce_relevance("0.9 (very relevant)"), 0.9)

    def test_non_numeric_falls_back(self):
        self.assertEqual(coerce.coerce_relevance("high"), 0.5)

    def test_none_falls_back(self):
        self.assertEqual(coerce.coerce_relevance(None), 0.5)

    def test_custom_default(self):
        self.assertEqual(coerce.coerce_relevance("nonsense", default=0.7), 0.7)


class TestCoerceInt(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(coerce.coerce_int(None))

    def test_int(self):
        self.assertEqual(coerce.coerce_int(42), 42)

    def test_float(self):
        self.assertEqual(coerce.coerce_int(42.9), 42)

    def test_numeric_string(self):
        self.assertEqual(coerce.coerce_int("1234"), 1234)

    def test_comma_string(self):
        self.assertEqual(coerce.coerce_int("1,234"), 1234)

    def test_abbreviated_k(self):
        self.assertEqual(coerce.coerce_int("1.2k"), 1200)

    def test_abbreviated_m(self):
        self.assertEqual(coerce.coerce_int("3M"), 3_000_000)

    def test_garbage(self):
        self.assertIsNone(coerce.coerce_int("lots"))

    def test_bool_is_no_data(self):
        self.assertIsNone(coerce.coerce_int(True))


# --------------------------------------------------------------------------- #
# http.py
# --------------------------------------------------------------------------- #
class TestDecodeBody(unittest.TestCase):
    def test_plain(self):
        resp = _FakeResponse(b'{"ok": 1}', _Headers())
        self.assertEqual(http._decode_body(resp), '{"ok": 1}')

    def test_gzip(self):
        resp = _FakeResponse(gzip.compress(b'{"ok": 1}'), _Headers({"Content-Encoding": "gzip"}))
        self.assertEqual(http._decode_body(resp), '{"ok": 1}')

    def test_deflate(self):
        resp = _FakeResponse(zlib.compress(b'{"ok": 1}'), _Headers({"Content-Encoding": "deflate"}))
        self.assertEqual(http._decode_body(resp), '{"ok": 1}')


class TestBackoff(unittest.TestCase):
    def test_exponential(self):
        self.assertEqual(http._backoff_delay(0), 1.0)
        self.assertEqual(http._backoff_delay(1), 2.0)
        self.assertEqual(http._backoff_delay(2), 4.0)

    def test_capped(self):
        self.assertLessEqual(http._backoff_delay(20), http.MAX_RETRY_DELAY)


class TestBrowserHeaders(unittest.TestCase):
    def test_browser_headers_present(self):
        self.assertIn("Mozilla/5.0", http.BROWSER_HEADERS["User-Agent"])
        self.assertIn("Accept-Language", http.BROWSER_HEADERS)

    def test_get_reddit_json_uses_browser_ua(self):
        captured = {}

        def fake_urlopen(req, **kwargs):
            captured["ua"] = req.get_header("User-agent")
            return _FakeResponse(b'[{"data": {"children": []}}]', _Headers())

        with mock.patch("lib.http.urllib.request.urlopen", side_effect=fake_urlopen):
            http.get_reddit_json("/r/test/comments/abc/title")

        self.assertIn("Mozilla/5.0", captured["ua"])


# --------------------------------------------------------------------------- #
# Reddit: removeprefix
# --------------------------------------------------------------------------- #
class TestSubredditNamePreserved(unittest.TestCase):
    def test_search_subreddits_does_not_mangle_name(self):
        captured = {}

        def fake_get(url, headers=None, **kwargs):
            captured["url"] = url
            return {"data": {"children": []}}

        with mock.patch("lib.openai_reddit.http.get", side_effect=fake_get):
            openai_reddit.search_subreddits(["r/rust"], "memory safety", "2026-01-01", "2026-01-31")

        # "rust" must survive; lstrip("r/") would have produced "ust".
        self.assertIn("/r/rust/", captured["url"])
        self.assertNotIn("/r/ust/", captured["url"])

    def test_parse_response_preserves_subreddit(self):
        resp = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"items": [{"title": "t", "url": "https://www.reddit.com/r/rust/comments/x/t/", "subreddit": "r/rust", "relevance": 0.8}]}',
                        }
                    ],
                }
            ]
        }
        items = openai_reddit.parse_reddit_response(resp)
        self.assertEqual(items[0]["subreddit"], "rust")


# --------------------------------------------------------------------------- #
# xAI parse: raise vs genuine-empty
# --------------------------------------------------------------------------- #
def _xai_text_response(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


class TestXaiParseRaises(unittest.TestCase):
    def test_no_output_text_raises(self):
        with self.assertRaises(http.HTTPError):
            xai_x.parse_x_response({"output": []})

    def test_invalid_json_raises(self):
        with self.assertRaises(http.HTTPError):
            xai_x.parse_x_response(_xai_text_response('{"items": [bad json'))

    def test_no_items_json_raises(self):
        with self.assertRaises(http.HTTPError):
            xai_x.parse_x_response(_xai_text_response("Sorry, I could not complete that."))

    def test_explicit_error_returns_empty(self):
        self.assertEqual(xai_x.parse_x_response({"error": "rate limited"}), [])

    def test_genuine_empty_items_returns_empty(self):
        self.assertEqual(xai_x.parse_x_response(_xai_text_response('{"items": []}')), [])

    def test_weird_relevance_and_engagement_tolerated(self):
        text = (
            '{"items": [{"url": "https://x.com/u/status/1", "text": "hi", '
            '"relevance": "high", "engagement": {"likes": "1.2k", "replies": "n/a"}}]}'
        )
        items = xai_x.parse_x_response(_xai_text_response(text))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["relevance"], 0.5)  # "high" -> default
        self.assertEqual(items[0]["engagement"]["likes"], 1200)
        self.assertIsNone(items[0]["engagement"]["replies"])


# --------------------------------------------------------------------------- #
# bird_x: retry on non-JSON stdout + coercion
# --------------------------------------------------------------------------- #
class _Completed:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class TestBirdRetry(unittest.TestCase):
    def test_retries_once_on_non_json(self):
        responses = [
            _Completed("<html>rate limited</html>"),
            _Completed('[{"id": "1", "text": "ok", "author": {"username": "a"}}]'),
        ]
        with mock.patch("lib.bird_x.subprocess.run", side_effect=responses) as run, \
             mock.patch("lib.bird_x.time.sleep"):
            result = bird_x._run_bird_search("query", 10, 30)
        self.assertEqual(run.call_count, 2)
        self.assertIsInstance(result, list)

    def test_gives_up_after_retry(self):
        responses = [_Completed("<html>"), _Completed("<html>still")]
        with mock.patch("lib.bird_x.subprocess.run", side_effect=responses), \
             mock.patch("lib.bird_x.time.sleep"):
            result = bird_x._run_bird_search("query", 10, 30)
        self.assertIn("error", result)

    def test_parse_coerces_abbreviated_engagement(self):
        resp = [{"id": "1", "text": "t", "author": {"username": "a"}, "likeCount": "2.5k"}]
        items = bird_x.parse_bird_response(resp)
        self.assertEqual(items[0]["engagement"]["likes"], 2500)


if __name__ == "__main__":
    unittest.main()
