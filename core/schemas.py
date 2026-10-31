"""Typed request, catalogue, and recommendation schemas."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config import (
    MAX_ABOUT_CHARS,
    MAX_FIRST_TASK_CHARS,
    MAX_INTEREST_CHARS,
    MAX_INTERESTS,
    MAX_KNOWN_ITEMS,
    MAX_RECOMMENDATION_REASONS,
    MAX_RECOMMENDATION_TEXT_CHARS,
    MIN_RECOMMENDATION_REASONS,
    MAX_ROADMAP_DELIVERABLE_CHARS,
    MAX_ROADMAP_FOCUS_CHARS,
    MAX_ROADMAP_ITEMS,
    MAX_ROADMAP_WEEKS,
    MIN_ROADMAP_ITEMS,
    MIN_ROADMAP_WEEK,
    MAX_SKILL_GAPS,
    MAX_TRACK_DESCRIPTION_CHARS,
    MAX_TRACK_DURATION_WEEKS,
    MAX_TRACK_KEYWORDS,
    MAX_TRACK_PREREQUISITES,
    MAX_TRACK_SKILLS,
    MAX_TRACK_TITLE_CHARS,
    MIN_TRACK_DURATION_WEEKS,
    MAX_WEEKLY_HOURS,
    MIN_CONFIDENCE,
    MIN_TEXT_LENGTH,
    MIN_WEEKLY_HOURS,
    MAX_CONFIDENCE,
)


class EducationLevel(str, Enum):
    SECONDARY = "secondary"
    DIPLOMA = "diploma"
    UNDERGRADUATE = "undergraduate"
    POSTGRADUATE = "postgraduate"


class Goal(str, Enum):
    INTERNSHIP = "internship"
    JOB = "job"
    UPSKILL = "upskill"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TrackProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    education_level: EducationLevel
    known_tools: list[str] = Field(default_factory=list, max_length=MAX_KNOWN_ITEMS)
    interests: list[str] = Field(default_factory=list, max_length=MAX_INTERESTS)
    weekly_hours: int = Field(ge=MIN_WEEKLY_HOURS, le=MAX_WEEKLY_HOURS)
    goal: Goal
    about_me: str = Field(max_length=MAX_ABOUT_CHARS)

    @model_validator(mode="after")
    def require_profile_signal(self) -> "TrackProfile":
        if not (self.known_tools or self.interests or self.about_me):
            raise ValueError(
                "Provide at least one known tool, interest, or background detail."
            )
        return self

    @field_validator("known_tools")
    @classmethod
    def validate_tool_names(cls, values: list[str]) -> list[str]:
        from core.sanitize import validate_tool_name

        return [validate_tool_name(value) for value in values]

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > MAX_INTEREST_CHARS for value in values):
            raise ValueError(
                f"Each interest must contain 1 to {MAX_INTEREST_CHARS} characters."
            )
        return values


class Track(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=MIN_TEXT_LENGTH, max_length=MAX_TRACK_TITLE_CHARS)
    description: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=MAX_TRACK_DESCRIPTION_CHARS,
    )
    prerequisites: list[str] = Field(max_length=MAX_TRACK_PREREQUISITES)
    skills: list[str] = Field(min_length=MIN_TEXT_LENGTH, max_length=MAX_TRACK_SKILLS)
    keywords: list[str] = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=MAX_TRACK_KEYWORDS,
    )
    difficulty: Difficulty
    typical_duration_weeks: int = Field(
        ge=MIN_TRACK_DURATION_WEEKS,
        le=MAX_TRACK_DURATION_WEEKS,
    )
    minimum_education: Literal[
        "any", "secondary", "diploma", "undergraduate", "postgraduate"
    ]
    recommended_hours_per_week: int = Field(
        ge=MIN_WEEKLY_HOURS,
        le=MAX_WEEKLY_HOURS,
    )
    goal_fit: list[Goal] = Field(min_length=MIN_TEXT_LENGTH)


class RoadmapItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    week: int = Field(ge=MIN_ROADMAP_WEEK, le=MAX_ROADMAP_WEEKS)
    focus: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=MAX_ROADMAP_FOCUS_CHARS,
    )
    deliverable: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=MAX_ROADMAP_DELIVERABLE_CHARS,
    )


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recommended_track: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    confidence: float = Field(ge=MIN_CONFIDENCE, le=MAX_CONFIDENCE)
    reasons: list[str] = Field(
        min_length=MIN_RECOMMENDATION_REASONS,
        max_length=MAX_RECOMMENDATION_REASONS,
    )
    roadmap: list[RoadmapItem] = Field(
        min_length=MIN_ROADMAP_ITEMS,
        max_length=MAX_ROADMAP_ITEMS,
    )
    first_task: str = Field(
        min_length=MIN_TEXT_LENGTH,
        max_length=MAX_FIRST_TASK_CHARS,
    )
    skill_gaps: list[str] = Field(max_length=MAX_SKILL_GAPS)

    @field_validator("reasons", "skill_gaps")
    @classmethod
    def validate_short_text(cls, values: list[str]) -> list[str]:
        if any(len(value) > MAX_RECOMMENDATION_TEXT_CHARS for value in values):
            raise ValueError(
                "Recommendation text must be "
                f"{MAX_RECOMMENDATION_TEXT_CHARS} characters or fewer."
            )
        return values


class RecommendationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Recommendation
    source: Literal["llm", "fallback"]
    model_name: str | None = None
    latency_ms: int = Field(ge=0)
    note: str | None = None
