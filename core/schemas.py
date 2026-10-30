"""Typed request, catalogue, and recommendation schemas."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import MAX_ABOUT_CHARS, MAX_INTERESTS, MAX_KNOWN_ITEMS


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
    weekly_hours: int = Field(ge=1, le=60)
    goal: Goal
    about_me: str = Field(max_length=MAX_ABOUT_CHARS)

    @field_validator("known_tools")
    @classmethod
    def validate_tool_names(cls, values: list[str]) -> list[str]:
        from core.sanitize import validate_tool_name

        return [validate_tool_name(value) for value in values]

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 80 for value in values):
            raise ValueError("Each interest must contain 1 to 80 characters.")
        return values


class Track(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    prerequisites: list[str] = Field(max_length=20)
    skills: list[str] = Field(min_length=1, max_length=20)
    keywords: list[str] = Field(min_length=1, max_length=30)
    difficulty: Difficulty
    typical_duration_weeks: int = Field(ge=1, le=104)
    minimum_education: Literal[
        "any", "secondary", "diploma", "undergraduate", "postgraduate"
    ]
    recommended_hours_per_week: int = Field(ge=1, le=60)
    goal_fit: list[Goal] = Field(min_length=1)


class RoadmapItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    week: int = Field(ge=1, le=52)
    focus: str = Field(min_length=1, max_length=120)
    deliverable: str = Field(min_length=1, max_length=240)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recommended_track: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(min_length=1, max_length=5)
    roadmap: list[RoadmapItem] = Field(min_length=2, max_length=6)
    first_task: str = Field(min_length=1, max_length=300)
    skill_gaps: list[str] = Field(max_length=10)

    @field_validator("reasons", "skill_gaps")
    @classmethod
    def validate_short_text(cls, values: list[str]) -> list[str]:
        if any(len(value) > 240 for value in values):
            raise ValueError("Recommendation text must be 240 characters or fewer.")
        return values
