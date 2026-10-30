"""Normalize student input and reject invalid or oversized fields."""

import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from config import MAX_ABOUT_CHARS, MAX_TOOL_NAME_CHARS
from core.schemas import TrackProfile

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_TOOL_NAME_ALLOWLIST = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9 .+#/_-]{{0,{MAX_TOOL_NAME_CHARS - 1}}}$"
)


def sanitize_text(value: str) -> str:
    """Normalize Unicode and replace control characters with spaces."""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(_CONTROL_CHARS.sub(" ", normalized).split())


def validate_tool_name(value: str) -> str:
    """Apply the bounded character allowlist for a tool or language name."""
    if not _TOOL_NAME_ALLOWLIST.fullmatch(value):
        raise ValueError("Use only letters, numbers, spaces, and . + # / _ - in tool names.")
    return value


def sanitize_profile(raw: dict[str, Any]) -> TrackProfile:
    """Sanitize untrusted form values before Pydantic validation."""
    if not isinstance(raw, dict):
        raise TypeError("Profile must be an object.")
    raw_about = raw.get("about_me", "")
    if isinstance(raw_about, str) and len(raw_about) > MAX_ABOUT_CHARS:
        raise ValueError(f"About me must be {MAX_ABOUT_CHARS} characters or fewer.")

    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            cleaned[key] = sanitize_text(value)
        elif isinstance(value, list):
            cleaned[key] = [
                sanitize_text(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    try:
        return TrackProfile.model_validate(cleaned)
    except ValidationError:
        raise
