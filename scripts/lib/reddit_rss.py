"""Keyless Reddit discovery via public RSS/Atom feeds.

Reddit's ``/search/.json`` endpoints now return HTTP 403 (shreddit anti-bot),
even with a browser User-Agent. The RSS/Atom feeds still serve HTTP 200 with no
API key, so this module uses them as the free fallback for the Phase-2
subreddit-targeted supplemental search.

This is a deliberately narrow idea-port of upstream 8d3a9e4: the fork's primary
Reddit discovery is OpenAI web_search, so we only need the subreddit-targeted
feed (``/r/{sub}/search.rss``), not the full tiered discovery orchestrator.
Output dicts match ``openai_reddit.search_subreddits`` so callers are unaffected.
RSS entries carry no engagement score; ``relevance`` is a fixed supplemental
default and engagement is backfilled later by shreddit enrichment.
"""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from . import http

ATOM = "{http://www.w3.org/2005/Atom}"
FEED_TIMEOUT = 15

# stdlib ElementTree is used (the fork is stdlib-only; certifi is its sole
# third-party dep, so defusedxml isn't available). XXE and billion-laughs both
# require a DTD, so we reject any feed declaring one before parsing. Reddit's
# Atom feeds never carry a DOCTYPE/ENTITY, so this is a safe, dependency-free
# guard against a malicious or MITM'd response.
_DTD_MARKER = re.compile(r"<!(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def _log(msg: str) -> None:
    sys.stderr.write(f"[RedditRSS] {msg}\n")
    sys.stderr.flush()


def _iso_to_date(value: Optional[str]) -> Optional[str]:
    """Parse an ISO-8601 timestamp (e.g. 2026-05-20T18:48:31+00:00) to YYYY-MM-DD."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip()).date().isoformat()
    except (ValueError, TypeError):
        return None


def _subreddit_from(category: str, url: str, fallback: str) -> str:
    """Derive subreddit name from the entry category, the URL, or the queried sub."""
    if category:
        return category
    parts = url.split("/r/", 1)
    if len(parts) == 2:
        return parts[1].split("/", 1)[0]
    return fallback


def parse_feed(xml_text: str, sub: str = "", start_index: int = 0) -> List[Dict[str, Any]]:
    """Parse an Atom feed string into fork-shaped item dicts. Never raises.

    Args:
        xml_text: Atom/RSS feed body
        sub: subreddit the feed was queried from (fallback for the name field)
        start_index: offset for the RS{n} id counter (so merged feeds stay unique)

    Returns:
        List of item dicts matching openai_reddit.search_subreddits output.
    """
    if not xml_text:
        return []
    if _DTD_MARKER.search(xml_text):
        _log("feed declares a DTD/ENTITY; rejecting (XXE/entity-expansion guard)")
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        _log(f"feed parse error: {e}")
        return []

    items: List[Dict[str, Any]] = []
    for entry in root.iter(f"{ATOM}entry"):
        link_el = entry.find(f"{ATOM}link")
        url = link_el.get("href", "").strip() if link_el is not None else ""
        if not url or "/comments/" not in url:
            continue

        title_el = entry.find(f"{ATOM}title")
        title = (title_el.text or "").strip() if title_el is not None else ""

        cat_el = entry.find(f"{ATOM}category")
        category = cat_el.get("term", "").strip() if cat_el is not None else ""
        subreddit = _subreddit_from(category, url, sub).removeprefix("r/")

        updated_el = entry.find(f"{ATOM}updated")
        updated = (updated_el.text or "").strip() if updated_el is not None else ""

        items.append({
            "id": f"RS{start_index + len(items) + 1}",
            "title": title,
            "url": url,
            "subreddit": subreddit,
            "date": _iso_to_date(updated),
            "why_relevant": f"Found in r/{subreddit or sub} RSS search",
            "relevance": 0.6,  # supplemental; slightly below .json default (0.65)
        })

    return items


def search_subreddits_rss(
    subreddits: List[str],
    topic: str,
    count_per: int = 5,
) -> List[Dict[str, Any]]:
    """Keyless RSS replacement for openai_reddit.search_subreddits.

    Searches each subreddit's public ``search.rss`` feed (no API key). Used as
    the fallback when the ``/search/.json`` endpoint returns 403.

    Args:
        subreddits: subreddit names (with or without the r/ prefix)
        topic: search query (caller should pass the core subject, not the
            verbose query)
        count_per: soft cap on items kept per subreddit

    Returns:
        List of fork-shaped item dicts (deduped by URL). Empty on total failure.
    """
    q = quote_plus(topic)
    all_items: List[Dict[str, Any]] = []
    seen: set = set()

    for raw_sub in subreddits:
        sub = raw_sub.removeprefix("r/").strip()
        if not sub:
            continue
        url = (
            f"https://www.reddit.com/r/{sub}/search.rss"
            f"?q={q}&restrict_sr=on&sort=new&t=month"
        )
        text = http.get_text(url, timeout=FEED_TIMEOUT, accept="application/atom+xml")
        if not text:
            _log(f"RSS search returned nothing for r/{sub}")
            continue

        kept = 0
        for item in parse_feed(text, sub=sub, start_index=len(all_items)):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            all_items.append(item)
            kept += 1
            if kept >= count_per:
                break

    return all_items
