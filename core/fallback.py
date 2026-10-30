"""Deterministic recommendation generation from catalogue retrieval scores."""

from config import (
    FALLBACK_CONFIDENCE_BASE,
    FALLBACK_CONFIDENCE_MAX,
    FALLBACK_CONFIDENCE_MIN,
    FALLBACK_ROADMAP_WEEKS,
    FIRST_TASK_QUESTION_COUNT,
    FIRST_TASK_MINUTES,
    MAX_FALLBACK_SKILL_GAPS,
    MAX_SKILLS_IN_REASON,
)
from core.retrieval import score_tracks
from core.schemas import Recommendation, RoadmapItem, TrackProfile


def recommend_fallback(profile: TrackProfile) -> Recommendation:
    """Create a valid recommendation without external services or credentials."""
    ranked = score_tracks(profile)
    track, score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = max(0.0, score - runner_up_score)
    confidence = min(
        FALLBACK_CONFIDENCE_MAX,
        max(FALLBACK_CONFIDENCE_MIN, FALLBACK_CONFIDENCE_BASE + margin),
    )

    skills = track.skills
    roadmap = [
        RoadmapItem(
            week=1,
            focus=f"Build foundations in {skills[0]}",
            deliverable=f"A short practice exercise demonstrating {skills[0]}.",
        ),
        RoadmapItem(
            week=2,
            focus=f"Practice {skills[min(1, len(skills) - 1)]}",
            deliverable=f"A small project using {skills[min(1, len(skills) - 1)]}.",
        ),
        RoadmapItem(
            week=FALLBACK_ROADMAP_WEEKS,
            focus=f"Combine core {track.title} skills",
            deliverable=f"A portfolio-ready {track.title} mini-project.",
        ),
    ]
    known = {value.casefold() for value in profile.known_tools}
    gaps = [
        skill
        for skill in track.skills
        if skill.casefold() not in known
    ][:MAX_FALLBACK_SKILL_GAPS]
    reasons = [
        f"Your stated interests and background align with {track.title}.",
        f"This track focuses on {', '.join(track.skills[:MAX_SKILLS_IN_REASON])}.",
        f"The estimated {track.typical_duration_weeks}-week duration can be paced around your weekly availability.",
    ]
    return Recommendation(
        recommended_track=track.id,
        confidence=confidence,
        reasons=reasons,
        roadmap=roadmap,
        first_task=(
            f"Spend {FIRST_TASK_MINUTES} minutes exploring {track.skills[0]} "
            f"and write down {FIRST_TASK_QUESTION_COUNT} questions you want to answer."
        ),
        skill_gaps=gaps,
    )
