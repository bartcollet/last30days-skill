"""HTTP utilities for last30days skill (stdlib only)."""

import gzip
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import zlib
from typing import Any, Dict, Optional
from urllib.parse import urlencode

DEFAULT_TIMEOUT = 30
DEBUG = os.environ.get("LAST30DAYS_DEBUG", "").lower() in ("1", "true", "yes")

# Build a robust SSL context that uses certifi when the system certs are missing.
# This fixes the common macOS issue where Python's default cert path doesn't exist.
_ssl_context: ssl.SSLContext | None = None

def _get_ssl_context() -> ssl.SSLContext:
    """Return a cached SSL context with working root certificates."""
    global _ssl_context
    if _ssl_context is not None:
        return _ssl_context

    ctx = ssl.create_default_context()
    # Test if the default context can actually verify anything
    paths = ssl.get_default_verify_paths()
    has_system_certs = (
        (paths.cafile and os.path.exists(paths.cafile))
        or (paths.capath and os.path.isdir(paths.capath))
    )
    if not has_system_certs:
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
            log("Using certifi certificates (system certs missing)")
        except ImportError:
            log("WARNING: No system certs and certifi not installed — SSL may fail")
    _ssl_context = ctx
    return _ssl_context


def log(msg: str):
    """Log debug message to stderr."""
    if DEBUG:
        sys.stderr.write(f"[DEBUG] {msg}\n")
        sys.stderr.flush()
MAX_RETRIES = 3
RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0  # cap exponential backoff so a flaky host can't stall for minutes
USER_AGENT = "last30days-skill/2.0 (Claude Code Skill)"

# A current-Chrome fingerprint. Reddit's public JSON/RSS endpoints return 403 to
# the generic urllib User-Agent + minimal header set, while matching browser
# requests succeed. Used for keyless Reddit fetches; the API clients keep their
# Bearer-auth header sets. (Idea-ported from upstream 4bae05e / 8d3a9e4.)
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def _decode_body(response) -> str:
    """Read an HTTP response body, transparently decompressing gzip/deflate.

    Browser-like requests advertise ``Accept-Encoding: gzip, deflate`` so hosts
    (Reddit in particular) may return a compressed body that plain
    ``.decode('utf-8')`` would choke on.
    """
    raw = response.read()
    encoding = (response.headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            pass
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)  # raw deflate, no header
            except zlib.error:
                pass
    return raw.decode("utf-8", errors="replace")


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff (1s, 2s, 4s, ...) capped at MAX_RETRY_DELAY.

    Linear backoff exhausts a small retry budget too quickly against a flaky
    resolver/edge; exponential gives the transient condition more room to clear
    without stalling indefinitely. (Idea-ported from upstream 5a2fe52.)
    """
    return min(RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)


class HTTPError(Exception):
    """HTTP request error with status code."""
    def __init__(self, message: str, status_code: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    """Make an HTTP request and return JSON response.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        headers: Optional headers dict
        json_data: Optional JSON body (for POST)
        timeout: Request timeout in seconds
        retries: Number of retries on failure

    Returns:
        Parsed JSON response

    Raises:
        HTTPError: On request failure
    """
    headers = headers or {}
    headers.setdefault("User-Agent", USER_AGENT)

    data = None
    if json_data is not None:
        data = json.dumps(json_data).encode('utf-8')
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    log(f"{method} {url}")
    if json_data:
        log(f"Payload keys: {list(json_data.keys())}")

    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_get_ssl_context()) as response:
                body = _decode_body(response)
                log(f"Response: {response.status} ({len(body)} bytes)")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = None
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                pass
            log(f"HTTP Error {e.code}: {e.reason}")
            if body:
                log(f"Error body: {body[:500]}")
            last_error = HTTPError(f"HTTP {e.code}: {e.reason}", e.code, body)

            # Don't retry client errors (4xx) except rate limits
            if 400 <= e.code < 500 and e.code != 429:
                raise last_error

            if attempt < retries - 1:
                time.sleep(_backoff_delay(attempt))
        except urllib.error.URLError as e:
            log(f"URL Error: {e.reason}")
            last_error = HTTPError(f"URL Error: {e.reason}")
            if attempt < retries - 1:
                time.sleep(_backoff_delay(attempt))
        except json.JSONDecodeError as e:
            log(f"JSON decode error: {e}")
            last_error = HTTPError(f"Invalid JSON response: {e}")
            raise last_error
        except (OSError, TimeoutError, ConnectionResetError) as e:
            # Handle socket-level errors (connection reset, timeout, etc.)
            log(f"Connection error: {type(e).__name__}: {e}")
            last_error = HTTPError(f"Connection error: {type(e).__name__}: {e}")
            if attempt < retries - 1:
                time.sleep(_backoff_delay(attempt))

    if last_error:
        raise last_error
    raise HTTPError("Request failed with no error details")


def get(url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Make a GET request."""
    return request("GET", url, headers=headers, **kwargs)


def post(url: str, json_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Make a POST request with JSON body."""
    return request("POST", url, headers=headers, json_data=json_data, **kwargs)


def get_reddit_json(path: str) -> Dict[str, Any]:
    """Fetch Reddit thread JSON.

    Args:
        path: Reddit path (e.g., /r/subreddit/comments/id/title)

    Returns:
        Parsed JSON response
    """
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path

    # Remove trailing slash and add .json
    path = path.rstrip('/')
    if not path.endswith('.json'):
        path = path + '.json'

    url = f"https://www.reddit.com{path}?raw_json=1"

    # Reddit 403s the generic UA; use a browser fingerprint (see BROWSER_HEADERS).
    headers = dict(BROWSER_HEADERS)
    headers["Accept"] = "application/json"

    return get(url, headers=headers)
