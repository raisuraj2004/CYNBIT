import json
import sqlite3

import pytest

from core.db import canonical_input_hash
from core.fallback import recommend_fallback
from core.retrieval import score_tracks, top_candidates
from core.sanitize import sanitize_profile


def valid_profile(**overrides):
    data = {
        "education_level": "undergraduate",
        "known_tools": ["Python", "pandas"],
        "interests": ["data analysis", "statistics"],
        "weekly_hours": 8,
        "goal": "internship",
        "about_me": "I enjoy exploring data and finding patterns.",
    }
    data.update(overrides)
    return sanitize_profile(data)


def test_sanitization_normalizes_and_removes_control_characters():
    profile = valid_profile(about_me="Python\x00\tand  data\r\nanalysis")
    assert profile.about_me == "Python and data analysis"
    assert profile.known_tools == ["Python", "pandas"]


def test_oversized_input_is_rejected_before_sanitization():
    with pytest.raises(ValueError, match="800 characters"):
        valid_profile(about_me="x" * 801)


def test_tool_name_allowlist_rejects_markup():
    with pytest.raises(ValueError, match="tool names"):
        valid_profile(known_tools=["<script>alert(1)</script>"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"weekly_hours": 0},
        {"weekly_hours": 61},
        {"education_level": "graduate"},
        {"goal": "get_rich"},
        {"unexpected": "field"},
    ],
)
def test_profile_schema_rejects_invalid_values(overrides):
    with pytest.raises(ValueError):
        valid_profile(**overrides)


def test_profile_requires_at_least_one_personalization_signal():
    with pytest.raises(ValueError, match="at least one known tool"):
        valid_profile(known_tools=[], interests=[], about_me="")


def test_catalogue_has_all_sixteen_unique_tracks(catalogue):
    assert len(catalogue) == 16
    assert len({track.id for track in catalogue}) == 16


def test_retrieval_ranks_relevant_data_track_and_limits_candidates(catalogue):
    profile = valid_profile()
    ranked = score_tracks(profile, catalogue)
    assert ranked[0][0].id in {"data-science", "data-analytics", "machine-learning"}
    assert len(top_candidates(profile, catalogue)) == 5


def test_retrieval_rejects_unbounded_candidate_count():
    with pytest.raises(ValueError, match="configured limit"):
        top_candidates(valid_profile(), limit=16)


def test_fallback_is_valid_deterministic_and_catalogue_bounded():
    profile = valid_profile()
    first = recommend_fallback(profile)
    second = recommend_fallback(profile)
    assert first == second
    assert first.recommended_track in {track.id for track, _ in score_tracks(profile)}
    assert first.confidence >= 0
    assert len(first.roadmap) >= 2
    assert first.first_task


def test_fallback_recommendation_changes_for_distinct_profile_signals():
    web_profile = valid_profile(
        known_tools=["JavaScript", "HTML", "CSS"],
        interests=["web development", "frontend", "APIs"],
        about_me="I want to build websites and backend APIs.",
    )
    design_profile = valid_profile(
        known_tools=["Figma"],
        interests=["user research", "wireframes", "prototypes"],
        about_me="I want to design usable interfaces and prototypes.",
    )
    data_profile = valid_profile(
        known_tools=["Python", "pandas", "scikit-learn"],
        interests=["machine learning", "statistics"],
        about_me="I want to train predictive models and analyze data.",
    )

    recommendations = {
        recommend_fallback(profile).recommended_track
        for profile in (web_profile, design_profile, data_profile)
    }

    assert recommendations == {"full-stack", "ui-ux", "machine-learning"}


def test_db_parameterization_and_free_text_exclusion(database, tmp_path):
    free_text = "'; DROP TABLE tracks; --"
    profile = valid_profile(
        about_me=free_text,
        known_tools=["5555555555"],
        interests=["Alice Smith"],
    )
    recommendation = recommend_fallback(profile)
    recommendation_id = database.save_recommendation(
        profile,
        recommendation,
        source="fallback",
        model_name=None,
        prompt_version="1.0",
        latency_ms=3,
    )
    with sqlite3.connect(database.path) as connection:
        row = connection.execute(
            "SELECT profile_json, input_hash FROM recommendations WHERE id = ?",
            (recommendation_id,),
        ).fetchone()
        track_count = connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    assert row is not None
    assert free_text not in row[0]
    assert "about_me" not in json.loads(row[0])
    assert "known_tools" not in json.loads(row[0])
    assert "interests" not in json.loads(row[0])
    assert "5555555555" not in row[0]
    assert "Alice Smith" not in row[0]
    assert len(row[1]) == 64
    assert track_count == 16
    assert canonical_input_hash(profile) == row[1]


def test_check_constraints_reject_invalid_persistence(database):
    profile = valid_profile()
    recommendation = recommend_fallback(profile)
    with pytest.raises(sqlite3.IntegrityError):
        database.save_recommendation(
            profile,
            recommendation,
            source="made-up",
            model_name=None,
            prompt_version="1.0",
            latency_ms=0,
        )


def test_rate_limit_is_atomic_and_resets_for_new_window(database):
    assert database.consume_limit("session", "hash", 2, "2026-10-30T22")
    assert database.consume_limit("session", "hash", 2, "2026-10-30T22")
    assert not database.consume_limit("session", "hash", 2, "2026-10-30T22")
    assert database.consume_limit("session", "hash", 2, "2026-10-30T23")


def test_rate_limit_hashes_expire_after_retention_period(database):
    assert database.consume_limit("ip", "old-hash", 2, "2026-10-27T00:00:00+00:00")
    assert database.consume_limit("ip", "new-hash", 2, "2026-10-30T00:00:00+00:00")
    with sqlite3.connect(database.path) as connection:
        rows = connection.execute(
            "SELECT bucket_key FROM rate_limits WHERE bucket_type = ?",
            ("ip",),
        ).fetchall()
    assert rows == [("new-hash",)]


def test_feedback_requires_consent_and_deletes_with_recommendation(database):
    profile = valid_profile()
    recommendation_id = database.save_recommendation(
        profile,
        recommend_fallback(profile),
        source="fallback",
        model_name=None,
        prompt_version="1.0",
        latency_ms=0,
    )
    assert not database.add_feedback(recommendation_id, 1, consent=False)
    assert database.add_feedback(recommendation_id, -1, consent=True)
    assert database.delete_recommendation(recommendation_id)
    assert not database.delete_recommendation(recommendation_id)
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 0
