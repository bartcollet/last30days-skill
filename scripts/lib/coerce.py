"""Defensive numeric coercion for LLM/API-supplied fields (stdlib only).

Search backends (xAI, OpenAI web_search, Bird) occasionally return non-numeric
values where a number is expected: ``"relevance": "high"``, ``"likes": "1.2k"``,
``"replies": None``. A bare ``float(...)`` / ``int(...)`` raises ValueError and,
because the conversion sits inside the per-item parse loop, takes down the whole
batch — every item silently lost. These helpers coerce best-effort and fall back
instead of raising.
"""

import re
from typing import Any, Optional


def coerce_relevance(value: Any, default: float = 0.5) -> float:
    """Coerce a relevance score to a float clamped to [0.0, 1.0].

    Accepts ints/floats and numeric strings (incl. a leading number inside a
    longer string). Falls back to ``default`` on anything non-numeric.
    """
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = _extract_leading_number(value)
        if score is None:
            score = default
    return min(1.0, max(0.0, score))


def coerce_int(value: Any) -> Optional[int]:
    """Coerce an engagement count to an int, or None when not coercible.

    Handles plain numbers, numeric strings, and abbreviated counts like
    "1.2k" / "3M" that social APIs sometimes hand back.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass; treat as no-data
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    return _parse_abbreviated_count(value)


_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def _parse_abbreviated_count(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "").lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmb])?$", text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        number *= _MULTIPLIERS[suffix]
    return int(number)


def _extract_leading_number(value: Any) -> Optional[float]:
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None
