"""GitHub Issues/PRs search via the public GitHub Search API.

Uses api.github.com/search/issues for issue/PR discovery and per-item comment
enrichment. Auth via GITHUB_TOKEN env var or `gh auth token` subprocess
fallback. The search endpoint requires authentication, so with no token the
source cleanly returns nothing (the orchestrator treats that as a silent skip,
not an error).

Fork-native adaptation of the upstream module: keyword-search path only
(person/project/star-fanout modes dropped — no caller in this fork). Uses a
local tty-gated logger, reuses openai_reddit._extract_core_subject for query
cleanup, and scores relevance via the shared heuristic
relevance.token_overlap_relevance (no LLM call, so GitHub stays cost-free).
"""

import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from . import dates
from .relevance import token_overlap_relevance

SEARCH_URL = "https://api.github.com/search/issues"

DEPTH_LIMITS = {
    "quick": 15,
    "default": 30,
    "deep": 60,
}

ENRICH_LIMITS = {
    "quick": 3,
    "default": 5,
    "deep": 8,
}

USER_AGENT = "last30days/3.0 (research tool)"


def _log(msg: str):
    """Tty-gated stderr logger (keeps automated/piped runs quiet)."""
    if sys.stderr.isatty():
        sys.stderr.write(f"[GitHub] {msg}\n")
        sys.stderr.flush()


def _extract_core_subject(topic: str) -> str:
    """Clean the raw topic into a core subject for the GitHub query.

    Reuses the fork's existing Reddit core-subject extractor (lazy import to
    avoid pulling the openai client at module load). Falls back to the raw
    topic if anything goes wrong.
    """
    try:
        from .openai_reddit import _extract_core_subject as _reddit_core
        core = _reddit_core(topic)
        return core or topic
    except Exception:
        return topic


def _resolve_token(token: Optional[str] = None) -> Optional[str]:
    """Resolve GitHub auth token from argument, env, or gh CLI."""
    if token:
        return token
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token
    # Fallback: try gh CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def resolve_token(token: Optional[str] = None) -> Optional[str]:
    """Public alias for ``_resolve_token``.

    The pipeline calls this once before ``search_github`` and
    ``enrich_with_comments`` so the ``gh auth token`` subprocess fallback only
    fires once per query when ``GITHUB_TOKEN`` is unset, instead of twice.
    """
    return _resolve_token(token)


def _fetch_json(
    url: str,
    token: Optional[str] = None,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """Fetch JSON from GitHub API. Returns None on failure."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            _log(f"403 rate limited or forbidden: {url}")
            return None
        if e.code == 422:
            _log(f"422 unprocessable: {url}")
            return None
        _log(f"HTTP {e.code}: {e.reason}")
        return None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        _log(f"Network error: {e}")
        return None
    except json.JSONDecodeError as e:
        _log(f"JSON decode error: {e}")
        return None


def _parse_repo_from_url(html_url: str) -> str:
    """Extract 'owner/repo' from a GitHub issue/PR URL."""
    parts = html_url.replace("https://github.com/", "").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""


def _parse_date(iso_str: Optional[str]) -> Optional[str]:
    """Parse a GitHub ISO 8601 datetime string and return YYYY-MM-DD.

    Returns None for non-date input. GitHub's API always emits ISO 8601
    (e.g. "2026-02-26T16:00:00Z"), but we defer to dates.parse_date() so
    garbage input gets rejected instead of silently sliced.
    """
    dt = dates.parse_date(iso_str)
    return dt.strftime("%Y-%m-%d") if dt else None


def _compute_relevance(
    query: str,
    title: str,
    rank_index: int,
    reactions: int,
    comments: int,
) -> float:
    """Blend text relevance with engagement signals."""
    rank_score = max(0.3, 1.0 - (rank_index * 0.02))
    engagement_boost = min(0.2, math.log1p(reactions + comments) / 20)

    if query:
        content_score = token_overlap_relevance(query, title)
        relevance = min(1.0, 0.6 * rank_score + 0.4 * content_score + engagement_boost)
    else:
        relevance = min(1.0, rank_score * 0.7 + engagement_boost + 0.1)

    return round(relevance, 2)


def search_github(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Search GitHub Issues and PRs (HTTP fetch only).

    Returns a raw envelope: ``{"items": [raw GitHub API items], "context":
    {core, from_date, to_date, count}}``. Normalization, date filtering, and
    sorting happen in ``parse_github_response``; comment enrichment in
    ``enrich_with_comments``.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        token: Optional GitHub token (falls back to env/gh CLI)

    Returns:
        Dict envelope. Empty ``items`` list on any failure.
    """
    count = DEPTH_LIMITS.get(depth, DEPTH_LIMITS["default"])
    core = _extract_core_subject(topic)
    resolved_token = _resolve_token(token)
    if not resolved_token:
        _log("No GitHub token available (set GITHUB_TOKEN or install gh CLI)")
        return {
            "items": [],
            "error": "no token",
            "context": {
                "core": core,
                "from_date": from_date,
                "to_date": to_date,
                "count": count,
            },
        }
    _log(f"Searching for '{core}' (raw: '{topic}', since {from_date}, count={count})")

    # Build search query with date filter
    q = f"{core} created:>{from_date}"
    params = {
        "q": q,
        "sort": "reactions",
        "order": "desc",
        "per_page": str(min(count, 100)),
    }
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"

    data = _fetch_json(url, token=resolved_token, timeout=30)
    if not data:
        return {"items": [], "context": {"core": core, "from_date": from_date,
                                          "to_date": to_date, "count": count}}

    raw_items = data.get("items", [])
    _log(f"Found {len(raw_items)} issues/PRs")

    return {
        "items": raw_items,
        "context": {
            "core": core,
            "from_date": from_date,
            "to_date": to_date,
            "count": count,
        },
    }


def parse_github_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize a ``search_github`` envelope into the skill's item shape.

    Pure function: no I/O, no token, no enrichment. Applies the date filter
    using the search context and sorts by relevance.
    """
    if not isinstance(response, dict):
        return []
    raw_items = response.get("items") or []
    if not isinstance(raw_items, list):
        return []
    context = response.get("context") or {}
    core = context.get("core") or ""
    from_date = context.get("from_date") or ""
    to_date = context.get("to_date") or ""
    count = context.get("count") or DEPTH_LIMITS["default"]

    items: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_items[:count]):
        html_url = item.get("html_url", "")
        repo = _parse_repo_from_url(html_url)
        title = item.get("title", "")
        body_text = item.get("body") or ""
        reactions_total = item.get("reactions", {}).get("total_count", 0) if isinstance(item.get("reactions"), dict) else 0
        comment_count = item.get("comments", 0)
        labels = [
            lbl.get("name", "") for lbl in (item.get("labels") or [])
            if isinstance(lbl, dict)
        ]
        state = item.get("state", "")
        is_pr = "pull_request" in item
        author = item.get("user", {}).get("login", "") if isinstance(item.get("user"), dict) else ""

        relevance = _compute_relevance(core, title, i, reactions_total, comment_count)

        items.append({
            "id": f"GH{i + 1}",
            "title": title,
            "url": html_url,
            "date": _parse_date(item.get("created_at")),
            "author": author,
            "source": "github",
            "score": reactions_total,
            "container": repo,
            "snippet": body_text[:300] if body_text else "",
            "relevance": relevance,
            "why_relevant": f"GitHub {'PR' if is_pr else 'issue'}: {title[:60]}",
            "engagement": {
                "reactions": reactions_total,
                "comments": comment_count,
            },
            "metadata": {
                "labels": labels,
                "state": state,
                "comment_count": comment_count,
                "reactions": reactions_total,
                "is_pr": is_pr,
            },
        })

    # Date filter
    if from_date and to_date:
        items = [
            item for item in items
            if item.get("date") is None or (from_date <= item["date"] <= to_date)
        ]

    items.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return items


def enrich_with_comments(
    items: List[Dict[str, Any]],
    depth: str = "default",
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch top comments for top-K items by reactions and attach to metadata.

    Mutates and returns ``items``. Resolves ``token`` via env/gh CLI when not
    supplied, matching ``search_github``'s fallback chain.
    """
    if not items:
        return items
    resolved_token = _resolve_token(token)
    if not resolved_token:
        _log("No GitHub token available for comment enrichment")
        return items
    return _enrich_top_items(items, depth, resolved_token)


def _enrich_top_items(
    items: List[Dict[str, Any]],
    depth: str,
    token: str,
) -> List[Dict[str, Any]]:
    """Fetch comments for top N items by reactions."""
    if not items:
        return items

    limit = ENRICH_LIMITS.get(depth, ENRICH_LIMITS["default"])

    by_reactions = sorted(
        range(len(items)),
        key=lambda i: items[i].get("score", 0),
        reverse=True,
    )
    to_enrich = by_reactions[:limit]

    _log(f"Enriching top {len(to_enrich)} items with comments")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                _fetch_item_comments,
                items[idx]["url"],
                token,
            ): idx
            for idx in to_enrich
        }

        for future in as_completed(futures):
            idx = futures[future]
            try:
                comments = future.result(timeout=15)
                items[idx]["metadata"]["top_comments"] = comments
            except (KeyError, TypeError, OSError) as exc:
                _log(f"Comment enrichment failed for {items[idx].get('url', '?')}: {type(exc).__name__}: {exc}")
                items[idx]["metadata"]["top_comments"] = []

    return items


def _fetch_item_comments(
    issue_url: str,
    token: str,
    max_comments: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch comments for a GitHub issue/PR.

    Args:
        issue_url: HTML URL like https://github.com/owner/repo/issues/123
        token: GitHub auth token
        max_comments: Max comments to return

    Returns:
        List of comment dicts with score, excerpt, author.
    """
    path = issue_url.replace("https://github.com/", "")
    path = path.replace("/pull/", "/issues/")
    api_url = f"https://api.github.com/repos/{path}/comments?per_page={max_comments}&sort=reactions&direction=desc"

    data = _fetch_json(api_url, token=token, timeout=15)
    if not data or not isinstance(data, list):
        return []

    comments = []
    for c in data[:max_comments]:
        body = c.get("body") or ""
        excerpt = body[:300] + "..." if len(body) > 300 else body
        reactions = c.get("reactions", {})
        reaction_count = reactions.get("total_count", 0) if isinstance(reactions, dict) else 0
        author = c.get("user", {}).get("login", "") if isinstance(c.get("user"), dict) else ""

        comments.append({
            "score": reaction_count,
            "excerpt": excerpt,
            "author": author,
        })

    return comments
