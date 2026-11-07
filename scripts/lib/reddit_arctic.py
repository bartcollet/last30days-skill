"""Reddit comment enrichment via the Arctic Shift archive (keyless, public API).

Why this exists: Reddit closed every unauthenticated route the fork used to
read threads directly. ``{thread}.json`` 403s, RSS ends on 2026-11-13, and the
official Data API stopped taking new applications on 2026-10-31. Scraping
Reddit's HTML with a spoofed browser fingerprint is bot-check circumvention, so
the fork does not do it.

Arctic Shift (https://arctic-shift.photon-reddit.com) is a community archive
with a documented public JSON API. It returns a thread's comments with author,
body, score and permalink, plus post metadata.

Data caveats (verified 2026-11-07):
- Post ``score`` is captured seconds after posting and rarely refreshed, so it
  is NOT used as engagement (a 47-comment thread showed 7 points).
- Post ``num_comments`` is current, so it is used.
- Comment scores are captured later and are good enough to rank comments.

Best-effort by design: any failure (rate limit, timeout, archive gone) returns
an empty result and the thread is kept without comments.
"""

import re
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse

from . import http

BASE_URL = "https://arctic-shift.photon-reddit.com/api"
REQUEST_TIMEOUT = 15
COMMENT_LIMIT = 100
RATE_LIMIT_PAUSE = 2.0

# ``permalink`` appears in full responses but is rejected as a ``fields`` value
# (HTTP 400 "'permalink' is not a valid field"), so it is rebuilt from ``id``.
COMMENT_FIELDS = "id,author,body,score,created_utc"
POST_FIELDS = "id,num_comments,created_utc"

_POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)", re.IGNORECASE)
_SUB_RE = re.compile(r"/r/([^/]+)/comments/", re.IGNORECASE)
_BOT_NAMES = {"automoderator", "remindmebot", "savevideo", "sneakpeekbot"}
# Bot-style suffixes: CamelCaseBot, some-bot, some_bot. Lowercase "bot" endings
# on ordinary names (Talbot, abbot) are deliberately not matched.
_BOT_SUFFIX_RE = re.compile(r"(?:[a-z0-9]Bot|[-_][Bb]ot)$")


def _log(msg: str) -> None:
    sys.stderr.write(f"[REDDIT-ARCTIC] {msg}\n")
    sys.stderr.flush()


def extract_post_id(url: str) -> Optional[str]:
    """Return the base-36 post id from a reddit.com thread URL, or None."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if "reddit.com" not in (parsed.netloc or ""):
        return None
    m = _POST_ID_RE.search(parsed.path or "")
    return m.group(1).lower() if m else None


def is_bot(author: str) -> bool:
    """True for AutoModerator-style accounts whose replies are never insights."""
    if not author:
        return False
    return author.lower() in _BOT_NAMES or bool(_BOT_SUFFIX_RE.search(author))


def _get(endpoint: str, params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """GET an Arctic Shift endpoint; return its ``data`` list or None.

    Arctic Shift signals overload as HTTP 200 with ``{"data": null, "error":
    "Timeout. Maybe slow down a bit"}``, so one paused retry covers that case.
    """
    url = f"{BASE_URL}/{endpoint}?{urlencode(params)}"
    for attempt in range(2):
        try:
            resp = http.get(url, timeout=REQUEST_TIMEOUT, retries=1)
        except http.HTTPError as e:
            _log(f"{endpoint} failed: {e}")
            if e.status_code == 429 and attempt == 0:
                time.sleep(RATE_LIMIT_PAUSE)
                continue
            return None
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, list):
            return data
        err = resp.get("error") if isinstance(resp, dict) else None
        _log(f"{endpoint} returned no data: {err}")
        if err and attempt == 0:
            time.sleep(RATE_LIMIT_PAUSE)
            continue
        return None
    return None


def fetch_thread(url: str) -> Dict[str, Any]:
    """Fetch post metadata and comments for a Reddit thread from Arctic Shift.

    Returns ``{"post": dict | None, "comments": [dict, ...]}``. Comment dicts use
    the keys ``reddit_enrich`` expects: score, created_utc, author, body,
    permalink. Bots and deleted/removed comments are dropped.
    """
    result: Dict[str, Any] = {"post": None, "comments": []}
    post_id = extract_post_id(url)
    if not post_id:
        return result

    raw_comments = _get(
        "comments/search",
        {"link_id": post_id, "limit": COMMENT_LIMIT, "fields": COMMENT_FIELDS},
    )
    sub_m = _SUB_RE.search(urlparse(url).path or "")
    sub = sub_m.group(1) if sub_m else None

    for c in raw_comments or []:
        if not isinstance(c, dict):
            continue
        author = str(c.get("author") or "")
        body = str(c.get("body") or "").strip()
        if not body or body in ("[deleted]", "[removed]") or is_bot(author):
            continue
        result["comments"].append({
            "score": c.get("score") if isinstance(c.get("score"), int) else 0,
            "created_utc": c.get("created_utc"),
            "author": author or "[deleted]",
            "body": body[:300],
            "permalink": (
                f"/r/{sub}/comments/{post_id}/comment/{c['id']}/"
                if sub and c.get("id") else ""
            ),
        })

    posts = _get("posts/ids", {"ids": post_id, "fields": POST_FIELDS})
    if posts and isinstance(posts[0], dict):
        result["post"] = posts[0]

    return result
