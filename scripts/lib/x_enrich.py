"""X thread enrichment — fetch full conversation threads for high-engagement posts."""

import json
import re
import sys
from typing import Any, Dict, Optional

from . import http

LIKES_THRESHOLD = 50
REPLIES_THRESHOLD = 10

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"

THREAD_PROMPT = """Find the full conversation thread for this X post: {url}

I need:
1. Is this post the START of a thread (i.e., the author posted multiple connected tweets)?
2. The top 3-5 most insightful REPLIES to this post (from other users)
3. A one-sentence summary of what the thread discussion is about

Return JSON:
{{
  "is_thread_head": true/false,
  "thread_insight": "One sentence summary of the discussion",
  "replies": [
    "Reply excerpt 1 (max 200 chars)",
    "Reply excerpt 2",
    "Reply excerpt 3"
  ]
}}"""


def _log_info(msg: str):
    """Log info to stderr."""
    sys.stderr.write(f"[X-ENRICH] {msg}\n")
    sys.stderr.flush()


def _log_error(msg: str):
    """Log error to stderr."""
    sys.stderr.write(f"[X-ENRICH ERROR] {msg}\n")
    sys.stderr.flush()


def should_enrich(item: Dict) -> bool:
    """Check if an X item meets the threshold for thread enrichment.

    Triggers when likes >= 50 OR replies >= 10.
    """
    eng = item.get("engagement")
    if not eng or not isinstance(eng, dict):
        return False

    likes = eng.get("likes") or 0
    replies = eng.get("replies") or 0

    return likes >= LIKES_THRESHOLD or replies >= REPLIES_THRESHOLD


def fetch_thread(
    api_key: str,
    model: str,
    url: str,
    mock_response: Optional[Dict] = None,
) -> Optional[Dict]:
    """Fetch thread context for an X post via xAI Responses API.

    Args:
        api_key: xAI API key
        model: Model to use (must be grok-4 family for x_search)
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
        "input": THREAD_PROMPT.format(url=url),
    }

    try:
        return http.post(XAI_RESPONSES_URL, payload, headers=headers, timeout=60)
    except http.HTTPError as e:
        _log_error(f"Thread fetch failed for {url}: {e}")
        return None
    except Exception as e:
        _log_error(f"Thread fetch error for {url}: {e}")
        return None


def parse_thread_response(response: Dict) -> Dict:
    """Parse xAI response to extract thread data.

    Args:
        response: Raw API response

    Returns:
        Dict with thread_replies, thread_insight, is_thread_head
    """
    empty = {"thread_replies": [], "thread_insight": "", "is_thread_head": False}

    if not response:
        return empty

    # Check for API errors — xAI always includes "error": null on success
    if response.get("error") is not None and response["error"]:
        error = response["error"]
        err_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        _log_error(f"xAI API error: {err_msg}")
        return empty

    # Extract output text
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

    # Extract JSON from response
    json_match = re.search(r'\{[\s\S]*"replies"[\s\S]*\}', output_text)
    if not json_match:
        json_match = re.search(r'\{[\s\S]*"thread_insight"[\s\S]*\}', output_text)

    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                "thread_replies": data.get("replies", [])[:5],
                "thread_insight": str(data.get("thread_insight", "")).strip(),
                "is_thread_head": bool(data.get("is_thread_head", False)),
            }
        except json.JSONDecodeError:
            pass

    return empty


def enrich_x_item(
    item: Dict,
    api_key: str,
    model: str,
    mock_response: Optional[Dict] = None,
) -> Dict:
    """Enrich an X item with thread context.

    Args:
        item: Raw X item dict
        api_key: xAI API key
        model: Model to use
        mock_response: Mock response for testing

    Returns:
        Enriched item dict (original fields + thread fields)
    """
    url = item.get("url", "")
    if not url:
        return item

    _log_info(f"Fetching thread for {url}")

    response = fetch_thread(api_key, model, url, mock_response=mock_response)
    if not response:
        return item

    thread_data = parse_thread_response(response)

    # Merge thread data into item
    item["thread_replies"] = thread_data["thread_replies"]
    item["thread_insight"] = thread_data["thread_insight"]
    item["is_thread_head"] = thread_data["is_thread_head"]

    reply_count = len(thread_data["thread_replies"])
    if reply_count > 0:
        _log_info(f"  Got {reply_count} replies + insight")
    else:
        _log_info(f"  No thread replies found")

    return item
