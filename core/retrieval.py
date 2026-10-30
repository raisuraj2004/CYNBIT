"""TF-IDF lexical retrieval blended with interpretable profile rules."""

import math
import re
from collections import Counter
from pathlib import Path

import yaml

from config import (
    EDUCATION_GAP_SCORE,
    CATALOGUE_TRACK_COUNT,
    MAX_TRACK_CANDIDATES,
    NONMATCHING_GOAL_SCORE,
    RETRIEVAL_WEIGHTS,
    TRACKS_PATH,
)
from core.schemas import EducationLevel, Track, TrackProfile

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[+#.]|[a-z0-9])?")
_EDUCATION_RANK = {
    "secondary": 0,
    "diploma": 1,
    "undergraduate": 2,
    "postgraduate": 3,
}


def load_tracks(path: Path = TRACKS_PATH) -> list[Track]:
    """Load and validate the curated track catalogue."""
    with path.open("r", encoding="utf-8") as file:
        raw_tracks = yaml.safe_load(file)
    tracks = [Track.model_validate(item) for item in raw_tracks]
    if (
        len(tracks) != CATALOGUE_TRACK_COUNT
        or len({track.id for track in tracks}) != CATALOGUE_TRACK_COUNT
    ):
        raise ValueError(
            f"The catalogue must contain exactly {CATALOGUE_TRACK_COUNT} unique tracks."
        )
    return tracks


def _tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.casefold())


def _text_score(profile: TrackProfile, track: Track, idf: dict[str, float]) -> float:
    query = _tokens(" ".join([profile.about_me, *profile.interests]))
    document = _tokens(" ".join([track.title, track.description, *track.keywords, *track.skills]))
    if not query or not document:
        return 0.0
    q_counts = Counter(query)
    d_counts = Counter(document)
    common = set(q_counts) & set(d_counts)
    numerator = sum(q_counts[token] * d_counts[token] * idf.get(token, 1.0) ** 2 for token in common)
    q_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in q_counts.items()))
    d_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in d_counts.items()))
    return numerator / (q_norm * d_norm) if q_norm and d_norm else 0.0


def score_tracks(
    profile: TrackProfile,
    tracks: list[Track] | None = None,
) -> list[tuple[Track, float]]:
    """Score and sort every track against the structured and text profile."""
    catalogue = tracks if tracks is not None else load_tracks()
    documents = [
        set(_tokens(" ".join([track.title, track.description, *track.keywords, *track.skills])))
        for track in catalogue
    ]
    document_count = max(len(documents), 1)
    idf: dict[str, float] = {}
    for document in documents:
        for token in document:
            idf[token] = math.log(1 + document_count / (1 + sum(token in doc for doc in documents)))

    known_tokens = set(_tokens(" ".join(profile.known_tools)))
    interest_tokens = set(_tokens(" ".join(profile.interests)))
    scores: list[tuple[Track, float]] = []
    for track in catalogue:
        skill_tokens = set(_tokens(" ".join([*track.skills, *track.prerequisites])))
        keyword_tokens = set(_tokens(" ".join([track.title, *track.keywords])))
        skill_score = len(known_tokens & skill_tokens) / max(len(skill_tokens), 1)
        interest_score = len(interest_tokens & keyword_tokens) / max(len(interest_tokens), 1)
        goal_score = 1.0 if profile.goal in track.goal_fit else NONMATCHING_GOAL_SCORE
        education_score = (
            1.0
            if track.minimum_education == "any"
            or _EDUCATION_RANK[profile.education_level.value]
            >= _EDUCATION_RANK[track.minimum_education]
            else EDUCATION_GAP_SCORE
        )
        time_score = min(profile.weekly_hours / track.recommended_hours_per_week, 1.0)
        components = {
            "text": _text_score(profile, track, idf),
            "skills": skill_score,
            "interests": interest_score,
            "goal": goal_score,
            "education": education_score,
            "time": time_score,
        }
        score = sum(RETRIEVAL_WEIGHTS[key] * value for key, value in components.items())
        scores.append((track, score))
    return sorted(scores, key=lambda item: (-item[1], item[0].id))


def top_candidates(
    profile: TrackProfile,
    tracks: list[Track] | None = None,
    limit: int = MAX_TRACK_CANDIDATES,
) -> list[Track]:
    """Return no more than the configured maximum number of candidates."""
    if not 1 <= limit <= MAX_TRACK_CANDIDATES:
        raise ValueError("Candidate count is outside the configured limit.")
    return [track for track, _ in score_tracks(profile, tracks)[:limit]]


def normalize_profile(profile: TrackProfile) -> dict[str, object]:
    """Return canonical data for hashing; callers must not persist about_me."""
    return profile.model_dump(mode="json")
