"""X thread enrichment — fetch full conversation threads for high-engagement posts.

Follows the same pattern as reddit_enrich.py: threshold check → API fetch → parse → merge.
Uses xAI Responses API with x_search tool to retrieve thread context.
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional

from . import http

# Engagement thresholds for triggering thread enrichment
LIKES_THRESHOLD = 50
REPLIES_THRESHOLD = 10


def _log_error(msg: str):
    """Log error to stderr."""
    sys.stderr.write(f"[X ENRICH ERROR] {msg}\n")
    sys.stderr.flush()


XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"

THREAD_FETCH_PROMPT = """Look up this specific X post and its conversation thread: {url}

I need the REPLIES and CONVERSATION around this post. Focus on:
1. The most insightful or substantive replies (not just "great post!" or emoji reactions)
2. Whether this post is the HEAD of a thread (i.e., the author posted multiple connected tweets)
3. A brief synthesis of what the thread discussion reveals

Return ONLY valid JSON:
{{
  "thread_replies": [
    "Reply excerpt 1 (max 150 chars, attribute with @handle)",
    "Reply excerpt 2",
    "Reply excerpt 3"
  ],
  "thread_insight": "One-sentence synthesis of the thread discussion",
  "is_thread_head": true
}}

Rules:
- Return 3-5 top replies, ordered by insight value (not just likes)
- Each reply should be max 150 characters, prefixed with @handle
- thread_insight should be a single sentence capturing the key takeaway
- is_thread_head is true if the original author posted a multi-part thread
- If you cannot find the thread or replies, return empty arrays and empty strings
"""


def should_enrich(item: Dict[str, Any]) -> bool:
    """Check whether an X item meets the engagement threshold for enrichment.

    Triggers when likes >= 50 OR replies >= 10.

    Args:
        item: Normalised X item dict (with engagement sub-dict)

    Returns:
        True if item should be enriched
    """
    engagement = item.get("engagement")
    if not engagement:
        return False

    likes = engagement.get("likes") or 0
    replies = engagement.get("replies") or 0

    return likes >= LIKES_THRESHOLD or replies >= REPLIES_THRESHOLD


def fetch_thread(
    api_key: str,
    model: str,
    url: str,
    mock_response: Optional[Dict] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch thread context for an X post via xAI Responses API.

    Args:
        api_key: xAI API key
        model: xAI model to use
        url: URL of the X post
        mock_response: Mock response for testing

    Returns:
        Raw API response or None on failure
    """
    if mock_response is not None:
        return mock_response

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "tools": [{"type": "x_search"}],
        "input": [
            {
                "role": "user",
                "content": THREAD_FETCH_PROMPT.format(url=url),
            }
        ],
    }

    try:
        return http.post(XAI_RESPONSES_URL, payload, headers=headers, timeout=60)
    except http.HTTPError as e:
        _log_error(f"Thread fetch failed for {url}: {e}")
        return None
    except Exception as e:
        _log_error(f"Thread fetch error for {url}: {type(e).__name__}: {e}")
        return None


def parse_thread_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Parse xAI thread response into structured data.

    Args:
        response: Raw API response

    Returns:
        Dict with thread_replies, thread_insight, is_thread_head
    """
    empty = {"thread_replies": [], "thread_insight": "", "is_thread_head": False}

    if not response or "error" in response:
        return empty

    # Extract output text (same pattern as xai_x.py)
    output_text = ""
    if "output" in response:
        output = response["output"]
        if isinstance(output, str):
            output_text = output
        elif isinstance(output, list):
            for item in output:
                if isinstance(item, dict):
                    if item.get("type") == "message":
                        content = item.get("content", [])
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "output_text":
                                output_text = c.get("text", "")
                                break
                    elif "text" in item:
                        output_text = item["text"]
                elif isinstance(item, str):
                    output_text = item
                if output_text:
                    break

    if not output_text:
        return empty

    # Extract JSON
    json_match = re.search(r'\{[\s\S]*"thread_replies"[\s\S]*\}', output_text)
    if not json_match:
        return empty

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return empty

    # Validate and clean
    replies = data.get("thread_replies", [])
    if not isinstance(replies, list):
        replies = []
    # Truncate each reply to 150 chars
    replies = [str(r)[:150] for r in replies if r][:5]

    insight = str(data.get("thread_insight", ""))[:300]
    is_head = bool(data.get("is_thread_head", False))

    return {
        "thread_replies": replies,
        "thread_insight": insight,
        "is_thread_head": is_head,
    }


def enrich_x_item(
    item: Dict[str, Any],
    api_key: str,
    model: str,
    mock_response: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Enrich an X item with thread context.

    Orchestrates: fetch → parse → merge. Catches errors gracefully
    so the original item is returned on failure.

    Args:
        item: X item dict
        api_key: xAI API key
        model: xAI model to use
        mock_response: Mock response for testing

    Returns:
        Enriched item dict (or original on failure)
    """
    url = item.get("url", "")
    if not url:
        return item

    try:
        response = fetch_thread(api_key, model, url, mock_response)
        if not response:
            return item

        parsed = parse_thread_response(response)

        # Merge into item
        item["thread_replies"] = parsed["thread_replies"]
        item["thread_insight"] = parsed["thread_insight"]
        item["is_thread_head"] = parsed["is_thread_head"]

    except Exception as e:
        _log_error(f"Enrichment failed for {url}: {type(e).__name__}: {e}")

    return item
