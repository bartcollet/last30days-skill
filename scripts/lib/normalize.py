"""Normalization of raw API data to canonical schema."""

from typing import Any, Dict, List, TypeVar, Union

from . import dates, schema

T = TypeVar("T", schema.RedditItem, schema.XItem, schema.WebSearchItem, schema.HackerNewsItem, schema.GitHubItem, schema.PolymarketItem)


def filter_by_date_range(
    items: List[T],
    from_date: str,
    to_date: str,
    require_date: bool = False,
) -> List[T]:
    """Hard filter: Remove items outside the date range.

    This is the safety net - even if the prompt lets old content through,
    this filter will exclude it.

    Args:
        items: List of items to filter
        from_date: Start date (YYYY-MM-DD) - exclude items before this
        to_date: End date (YYYY-MM-DD) - exclude items after this
        require_date: If True, also remove items with no date

    Returns:
        Filtered list with only items in range (or unknown dates if not required)
    """
    result = []
    for item in items:
        if item.date is None:
            if not require_date:
                result.append(item)  # Keep unknown dates (with scoring penalty)
            continue

        # Hard filter: if date is before from_date, exclude
        if item.date < from_date:
            continue  # DROP - too old

        # Hard filter: if date is after to_date, exclude (likely parsing error)
        if item.date > to_date:
            continue  # DROP - future date

        result.append(item)

    return result


def normalize_reddit_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.RedditItem]:
    """Normalize raw Reddit items to schema.

    Args:
        items: Raw Reddit items from API
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of RedditItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                score=eng_raw.get("score"),
                num_comments=eng_raw.get("num_comments"),
                upvote_ratio=eng_raw.get("upvote_ratio"),
            )

        # Parse comments
        top_comments = []
        for c in item.get("top_comments", []):
            top_comments.append(schema.Comment(
                score=c.get("score", 0),
                date=c.get("date"),
                author=c.get("author", ""),
                excerpt=c.get("excerpt", ""),
                url=c.get("url", ""),
            ))

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.RedditItem(
            id=item.get("id", ""),
            title=item.get("title", ""),
            url=item.get("url", ""),
            subreddit=item.get("subreddit", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            top_comments=top_comments,
            comment_insights=item.get("comment_insights", []),
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def normalize_x_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.XItem]:
    """Normalize raw X items to schema.

    Args:
        items: Raw X items from API
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of XItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                likes=eng_raw.get("likes"),
                reposts=eng_raw.get("reposts"),
                replies=eng_raw.get("replies"),
                quotes=eng_raw.get("quotes"),
            )

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.XItem(
            id=item.get("id", ""),
            text=item.get("text", ""),
            url=item.get("url", ""),
            author_handle=item.get("author_handle", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
            thread_replies=item.get("thread_replies", []),
            thread_insight=item.get("thread_insight", ""),
            is_thread_head=item.get("is_thread_head", False),
        ))

    return normalized


def normalize_hn_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.HackerNewsItem]:
    """Normalize raw Hacker News items to schema.

    Args:
        items: Raw HN items from hackernews.parse_hackernews_response
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of HackerNewsItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                points=eng_raw.get("points"),
                comments=eng_raw.get("comments"),
            )

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.HackerNewsItem(
            id=str(item.get("id", "")),
            title=item.get("title", ""),
            url=item.get("url", ""),
            hn_url=item.get("hn_url", ""),
            author=item.get("author", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            top_comments=item.get("top_comments", []),
            comment_insights=item.get("comment_insights", []),
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def normalize_github_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.GitHubItem]:
    """Normalize raw GitHub items to schema.

    Args:
        items: Raw GitHub items from github.parse_github_response
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of GitHubItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                reactions=eng_raw.get("reactions"),
                comments=eng_raw.get("comments"),
            )

        meta = item.get("metadata") or {}

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.GitHubItem(
            id=item.get("id", ""),
            title=item.get("title", ""),
            url=item.get("url", ""),
            author=item.get("author", ""),
            container=item.get("container", ""),
            snippet=item.get("snippet", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            is_pr=meta.get("is_pr", False),
            state=meta.get("state", ""),
            labels=meta.get("labels", []),
            top_comments=meta.get("top_comments", []),
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def normalize_polymarket_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.PolymarketItem]:
    """Normalize raw Polymarket items to schema.

    Builds Engagement from the event's volume/liquidity (real-money signal) and
    the top outcome's price (odds).

    Args:
        items: Raw Polymarket items from polymarket.parse_polymarket_response
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of PolymarketItem objects
    """
    normalized = []

    for item in items:
        outcome_prices = item.get("outcome_prices", []) or []

        # Engagement: volume (prefer monthly, fall back to 24h) + liquidity + top odds
        volume = item.get("volume1mo") or item.get("volume24hr")
        liquidity = item.get("liquidity")
        top_odds = None
        if outcome_prices:
            try:
                top_odds = float(outcome_prices[0][1])
            except (IndexError, TypeError, ValueError):
                top_odds = None

        engagement = None
        if volume is not None or liquidity is not None or top_odds is not None:
            engagement = schema.Engagement(
                volume=float(volume) if volume is not None else None,
                liquidity=float(liquidity) if liquidity is not None else None,
                odds=top_odds,
            )

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.PolymarketItem(
            id=str(item.get("event_id", "")),
            title=item.get("title", ""),
            url=item.get("url", ""),
            question=item.get("question", ""),
            outcome_prices=[tuple(p) for p in outcome_prices],
            outcomes_remaining=item.get("outcomes_remaining", 0),
            price_movement=item.get("price_movement"),
            end_date=item.get("end_date"),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def items_to_dicts(items: List) -> List[Dict[str, Any]]:
    """Convert schema items to dicts for JSON serialization."""
    return [item.to_dict() for item in items]
