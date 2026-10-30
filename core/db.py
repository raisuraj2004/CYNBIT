"""SQLite persistence with parameterized statements and explicit consent writes."""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import DEFAULT_DB_PATH, SCHEMA_PATH
from core.schemas import Recommendation, Track, TrackProfile


def canonical_input_hash(profile: TrackProfile) -> str:
    """Hash canonical normalized input without persisting its free text."""
    serialized = json.dumps(
        profile.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class Database:
    """Small SQLite repository; each operation gets a foreign-key-enabled connection."""

    def __init__(self, path: Path | None = None) -> None:
        configured_path = os.environ.get("BIT_ELEVATE_DB_PATH")
        self.path = path or (Path(configured_path) if configured_path else DEFAULT_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create missing tables and indexes from the plain SQL schema."""
        with self._connect() as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    def seed_tracks(self, tracks: list[Track]) -> None:
        """Idempotently load tracks and normalized skill vocabulary."""
        with self._connect() as connection:
            for track in tracks:
                connection.execute(
                    """
                    INSERT INTO tracks (
                        id, title, description, difficulty, typical_duration_weeks,
                        minimum_education, recommended_hours_per_week, goal_fit_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        difficulty = excluded.difficulty,
                        typical_duration_weeks = excluded.typical_duration_weeks,
                        minimum_education = excluded.minimum_education,
                        recommended_hours_per_week = excluded.recommended_hours_per_week,
                        goal_fit_json = excluded.goal_fit_json
                    """,
                    (
                        track.id,
                        track.title,
                        track.description,
                        track.difficulty.value,
                        track.typical_duration_weeks,
                        track.minimum_education,
                        track.recommended_hours_per_week,
                        json.dumps([goal.value for goal in track.goal_fit]),
                    ),
                )
                connection.execute("DELETE FROM track_skills WHERE track_id = ?", (track.id,))
                connection.executemany(
                    """
                    INSERT INTO track_skills (track_id, skill, category)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (track.id, skill, "skill")
                        for skill in track.skills
                    ]
                    + [
                        (track.id, skill, "prerequisite")
                        for skill in track.prerequisites
                    ]
                    + [
                        (track.id, keyword, "keyword")
                        for keyword in track.keywords
                    ],
                )

    def save_recommendation(
        self,
        profile: TrackProfile,
        recommendation: Recommendation,
        source: str,
        model_name: str | None,
        prompt_version: str,
        latency_ms: int,
    ) -> str:
        """Persist only structured, non-identifying profile fields and a hash."""
        recommendation_id = str(uuid.uuid4())
        structured_profile = {
            "education_level": profile.education_level.value,
            "known_tools": profile.known_tools,
            "interests": profile.interests,
            "weekly_hours": profile.weekly_hours,
            "goal": profile.goal.value,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO recommendations (
                    id, created_at, input_hash, profile_json, recommended_track_id,
                    confidence, source, model_name, prompt_version, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    datetime.now(timezone.utc).isoformat(),
                    canonical_input_hash(profile),
                    json.dumps(structured_profile, ensure_ascii=True, sort_keys=True),
                    recommendation.recommended_track,
                    recommendation.confidence,
                    source,
                    model_name,
                    prompt_version,
                    latency_ms,
                ),
            )
        return recommendation_id

    def add_feedback(self, recommendation_id: str, rating: int, consent: bool) -> bool:
        """Store optional feedback only when the student explicitly consents."""
        if not consent:
            return False
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (id, recommendation_id, created_at, rating, consent)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    recommendation_id,
                    datetime.now(timezone.utc).isoformat(),
                    rating,
                    1,
                ),
            )
        return True

    def delete_recommendation(self, recommendation_id: str) -> bool:
        """Delete a recommendation by UUID; associated feedback is cascade-deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM recommendations WHERE id = ?",
                (recommendation_id,),
            )
        return cursor.rowcount == 1

    def consume_limit(
        self,
        bucket_type: str,
        bucket_key: str,
        limit: int,
        window_start: str,
    ) -> bool:
        """Atomically consume one request in a fixed session, IP, or daily window."""
        if bucket_type not in {"session", "ip", "daily"} or limit < 1:
            raise ValueError("Invalid rate-limit parameters.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT window_start, request_count
                FROM rate_limits
                WHERE bucket_type = ? AND bucket_key = ?
                """,
                (bucket_type, bucket_key),
            ).fetchone()
            current_count = row["request_count"] if row and row["window_start"] == window_start else 0
            if current_count >= limit:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO rate_limits (bucket_type, bucket_key, window_start, request_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(bucket_type, bucket_key) DO UPDATE SET
                    window_start = excluded.window_start,
                    request_count = CASE
                        WHEN rate_limits.window_start = excluded.window_start
                        THEN rate_limits.request_count + 1
                        ELSE 1
                    END
                """,
                (bucket_type, bucket_key, window_start),
            )
        return True

    def track_count(self) -> int:
        """Return the number of seeded tracks."""
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()
        return int(row["count"])

