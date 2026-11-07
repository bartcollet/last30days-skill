"""Reddit thread enrichment: comment count and top comments via Arctic Shift.

Reddit's own keyless endpoints are closed (see ``reddit_arctic``), so the fork
no longer contacts reddit.com here. Upvote scores are not available from a
trustworthy source and stay ``None``; the report shows them as unknown.
"""

import re
from typing import Any, Dict, List, Optional

from . import dates, reddit_arctic


def get_top_comments(comments: List[Dict], limit: int = 10) -> List[Dict[str, Any]]:
    """Get top comments sorted by score.

    Args:
        comments: List of comment dicts
        limit: Maximum number to return

    Returns:
        Top comments sorted by score
    """
    # Filter out deleted/removed
    valid = [c for c in comments if c.get("author") not in ("[deleted]", "[removed]")]

    # Sort by score descending
    sorted_comments = sorted(valid, key=lambda c: c.get("score", 0), reverse=True)

    return sorted_comments[:limit]


def extract_comment_insights(comments: List[Dict], limit: int = 7) -> List[str]:
    """Extract key insights from top comments.

    Uses simple heuristics to identify valuable comments:
    - Has substantive text
    - Contains actionable information
    - Not just agreement/disagreement

    Args:
        comments: Top comments
        limit: Max insights to extract

    Returns:
        List of insight strings
    """
    insights = []

    for comment in comments[:limit * 2]:  # Look at more comments than we need
        body = comment.get("body", "").strip()
        if not body or len(body) < 30:
            continue

        # Skip low-value patterns
        skip_patterns = [
            r'^(this|same|agreed|exactly|yep|nope|yes|no|thanks|thank you)\.?$',
            r'^lol|lmao|haha',
            r'^\[deleted\]',
            r'^\[removed\]',
        ]
        if any(re.match(p, body.lower()) for p in skip_patterns):
            continue

        # Truncate to first meaningful sentence or ~150 chars
        insight = body[:150]
        if len(body) > 150:
            # Try to find a sentence boundary
            for i, char in enumerate(insight):
                if char in '.!?' and i > 50:
                    insight = insight[:i+1]
                    break
            else:
                insight = insight.rstrip() + "..."

        insights.append(insight)
        if len(insights) >= limit:
            break

    return insights


def enrich_reddit_item(
    item: Dict[str, Any],
    mock_thread_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Enrich a Reddit item with comment count and top comments.

    Args:
        item: Reddit item dict
        mock_thread_data: ``{"post": ..., "comments": [...]}`` in
            ``reddit_arctic.fetch_thread`` shape, for tests and ``--mock``

    Returns:
        The item, enriched where data was available (never raises on a miss)
    """
    url = item.get("url", "")
    if mock_thread_data is not None:
        thread = mock_thread_data
    elif url:
        thread = reddit_arctic.fetch_thread(url)
    else:
        return item

    if not isinstance(thread, dict):
        return item
    post = thread.get("post") if isinstance(thread.get("post"), dict) else None
    comments = [c for c in (thread.get("comments") or []) if isinstance(c, dict)]

    if post:
        num_comments = post.get("num_comments")
        if isinstance(num_comments, int):
            eng = item.setdefault("engagement", {})
            # Arctic Shift's post score is captured at ingest and is stale, so
            # it is never used; see reddit_arctic module docstring.
            eng.setdefault("score", None)
            eng["num_comments"] = num_comments
            eng.setdefault("upvote_ratio", None)
        created_utc = post.get("created_utc")
        if created_utc:
            # Archive timestamp is authoritative; the OpenAI-reported date is a guess.
            item["date"] = dates.timestamp_to_date(created_utc)

    if comments:
        top_comments = get_top_comments(comments)
        item["top_comments"] = []
        for c in top_comments:
            permalink = c.get("permalink", "")
            comment_url = f"https://reddit.com{permalink}" if permalink else ""
            item["top_comments"].append({
                "score": c.get("score", 0),
                "date": dates.timestamp_to_date(c.get("created_utc")),
                "author": c.get("author", ""),
                "excerpt": c.get("body", "")[:200],
                "url": comment_url,
            })
        item["comment_insights"] = extract_comment_insights(top_comments)

    return item
