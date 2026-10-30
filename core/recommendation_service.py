"""Choose Gemini when explicitly enabled, otherwise use deterministic fallback."""

import time
from collections.abc import Callable

from core.fallback import recommend_fallback
from core.llm import GeminiAdapter, LLMError
from core.retrieval import load_tracks, top_candidates
from core.schemas import RecommendationOutcome, TrackProfile


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
        except LLMError:
            note = "Gemini was unavailable or returned invalid output; a rule-based recommendation is shown instead."
    elif allow_gemini:
        note = "No Gemini API key is configured; a rule-based recommendation is shown instead."
    else:
        note = "Gemini processing was not enabled; a rule-based recommendation is shown instead."

    return RecommendationOutcome(
        recommendation=recommend_fallback(profile),
        source="fallback",
        model_name=None,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        note=note,
    )
