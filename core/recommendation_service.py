"""Choose Gemini when explicitly enabled, otherwise use deterministic fallback."""

import time
from collections.abc import Callable

from core.fallback import recommend_fallback
from core.llm import GeminiAdapter, LLMError
from core.retrieval import load_tracks, top_candidates
from core.schemas import RecommendationOutcome, TrackProfile


def _fallback_note(error: LLMError) -> str:
    """Translate a safe diagnostic category into actionable, non-sensitive UI text."""
    diagnostics = {
        "http_400": "Gemini rejected the request (HTTP 400). Check the configured model and request settings.",
        "http_401": "Gemini rejected the API key (HTTP 401). Check that the key is current and valid.",
        "http_403": "Gemini denied access (HTTP 403). Check the key, API access, and project permissions.",
        "http_404": "Gemini could not find this model (HTTP 404). Check that the model is enabled for your API.",
        "http_429": "Gemini rate or quota limit reached (HTTP 429). Check your project quota and billing.",
        "http_500": "Gemini had a temporary server error (HTTP 500). Try again later.",
        "http_503": "Gemini is temporarily unavailable or overloaded (HTTP 503). No key change is indicated; try again shortly.",
        "invalid_output": "Gemini returned output that did not match the recommendation format.",
        "track_not_allowed": "Gemini returned a track outside the approved catalogue.",
        "daily_limit": "The daily Gemini request limit has been reached.",
        "request_timeout": "The Gemini request timed out. Check the connection and try again.",
        "dns_error": "Gemini's server name could not be resolved. Check your internet connection.",
        "tls_error": "A secure connection to Gemini could not be established. Check network or proxy settings.",
        "connection_error": "Gemini could not be reached. Check your internet connection or proxy settings.",
        "provider_invalid_json": "Gemini returned an unreadable response.",
        "provider_response_unreadable": "Gemini returned an incomplete response.",
    }
    return (
        f"{diagnostics.get(error.diagnostic, 'Gemini could not complete this request.')}"
        " A rule-based recommendation is shown instead."
    )


def get_recommendation(
    profile: TrackProfile,
    allow_gemini: bool,
    before_attempt: Callable[[], bool] | None = None,
) -> RecommendationOutcome:
    """Return a validated provider result or a deterministic fallback result."""
    started = time.monotonic()
    catalogue = load_tracks()
    adapter = GeminiAdapter.from_environment(before_attempt) if allow_gemini else None
    note: str | None = None

    if allow_gemini and adapter is not None:
        try:
            recommendation = adapter.generate(
                profile,
                top_candidates(profile, catalogue),
                {track.id for track in catalogue},
            )
            return RecommendationOutcome(
                recommendation=recommendation,
                source="llm",
                model_name=adapter.model_name,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        except LLMError as error:
            note = _fallback_note(error)
    elif allow_gemini:
        note = (
            "No Gemini API key was found in the app environment or Streamlit secrets; "
            "a rule-based recommendation is shown instead."
        )
    else:
        note = "Gemini processing was not enabled; a rule-based recommendation is shown instead."

    return RecommendationOutcome(
        recommendation=recommend_fallback(profile),
        source="fallback",
        model_name=None,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        note=note,
    )
