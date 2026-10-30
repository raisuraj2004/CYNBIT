"""BitElevate Path Finder Streamlit application."""

import hashlib
import html
import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import streamlit as st

from config import (
    DEFAULT_DB_PATH,
    MAX_LLM_CALLS_PER_DAY,
    MAX_REQUESTS_PER_HOUR,
    PROMPT_VERSION,
    RATE_LIMIT_WINDOW_SECONDS,
)
from core.db import Database
from core.recommendation_service import get_recommendation
from core.retrieval import load_tracks
from core.sanitize import sanitize_profile
from core.schemas import EducationLevel, Goal, RecommendationOutcome

logger = logging.getLogger("bitelelvate_path_finder")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@st.cache_resource(max_entries=1)
def get_database(path: str) -> Database:
    """Share a stateless repository object while keeping per-operation connections."""
    database = Database(Path(path))
    database.seed_tracks(load_tracks())
    return database


def log_event(event: str, **fields: str | int) -> None:
    """Write structured operational metadata without profile content."""
    logger.info(json.dumps({"event": event, **fields}, sort_keys=True))


def hashed_key(namespace: str, value: str) -> str:
    """Hash a session or network identifier before it reaches SQLite."""
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def show_recommendation(outcome: RecommendationOutcome) -> None:
    """Render validated output as escaped plain text, never raw HTML."""
    catalogue = {track.id: track for track in load_tracks()}
    recommendation = outcome.recommendation
    track = catalogue[recommendation.recommended_track]
    st.subheader(html.escape(track.title))
    st.caption(f"Recommendation source: {outcome.source} · Confidence: {recommendation.confidence:.0%}")
    if outcome.note:
        st.info(html.escape(outcome.note))
    st.markdown("**Why this may fit**")
    for reason in recommendation.reasons:
        st.text(f"• {html.escape(reason)}")
    st.markdown("**Short roadmap**")
    for item in recommendation.roadmap:
        st.text(f"Week {item.week}: {html.escape(item.focus)}")
        st.text(html.escape(item.deliverable))
    st.markdown("**First task**")
    st.text(html.escape(recommendation.first_task))
    if recommendation.skill_gaps:
        st.markdown("**Skills to build**")
        st.text(", ".join(html.escape(skill) for skill in recommendation.skill_gaps))


st.set_page_config(page_title="BitElevate Path Finder", page_icon="🧭", layout="centered")
st.title("BitElevate Path Finder")
st.write(
    "Describe where you are starting from and what you want to achieve. "
    "Get a suggested learning track, a short roadmap, and a first task."
)
st.caption(
    "Assessment proof of concept built with public information and a synthetic catalogue; "
    "it is not an official Cynbit recommendation service."
)
st.info(
    "Privacy: do not enter names, emails, or phone numbers. If Gemini processing is "
    "enabled and you opt in below, the sanitized profile (including your free-text answer) "
    "is sent to Google Gemini. Recommendation storage is separately opt-in. Hashed session "
    "and IP rate-limit counters are stored in SQLite even when recommendation storage is off."
)

database_path = os.environ.get("BIT_ELEVATE_DB_PATH", str(DEFAULT_DB_PATH))
database = get_database(database_path)
st.session_state.setdefault("session_token", secrets.token_urlsafe(32))
st.session_state.setdefault("latest_outcome", None)
st.session_state.setdefault("latest_recommendation_id", None)
st.session_state.setdefault("stored_recommendation_ids", [])

dont_store = st.toggle(
    "Don't store my recommendation or profile",
    value=True,
    help="When on, the recommendation and structured profile are not written to the recommendations table.",
)
if not dont_store:
    st.caption(
        "Turning this off is consent to store your structured profile (not free text), "
        "a SHA-256 input hash, the recommendation, and minimal model metadata."
    )

education_labels = {
    EducationLevel.SECONDARY: "Secondary school",
    EducationLevel.DIPLOMA: "Diploma",
    EducationLevel.UNDERGRADUATE: "Undergraduate",
    EducationLevel.POSTGRADUATE: "Postgraduate",
}

with st.form("path_finder_form"):
    education = st.selectbox(
        "Education level",
        options=list(EducationLevel),
        format_func=lambda value: education_labels[value],
    )
    known_tools = st.multiselect(
        "Languages / tools you know",
        options=[
            "Python",
            "JavaScript",
            "HTML",
            "CSS",
            "SQL",
            "Java",
            "C++",
            "Excel",
            "Linux",
            "Git",
            "Docker",
            "Figma",
            "pandas",
            "scikit-learn",
            "PyTorch",
            "Canva",
        ],
        accept_new_options=True,
        max_selections=20,
        help="You can type a language or tool not listed.",
    )
    interests_text = st.text_input(
        "Interests (comma-separated)",
        max_chars=800,
        help="Enter up to 10 interests; each interest can be up to 80 characters.",
    )
    weekly_hours = st.slider("Hours available each week", min_value=1, max_value=60, value=6)
    goal = st.selectbox(
        "Your goal",
        options=list(Goal),
        format_func=lambda value: value.value.title(),
    )
    about_me = st.text_area(
        "About me",
        max_chars=800,
        height=120,
        placeholder="Share your experience, strengths, and what you hope to learn.",
    )
    allow_gemini = st.checkbox(
        "I agree to send this profile to Gemini for this recommendation (only used when a key is configured)",
        value=False,
    )
    submitted = st.form_submit_button("Find my path", type="primary")

if submitted:
    try:
        profile = sanitize_profile(
            {
                "education_level": education.value,
                "known_tools": known_tools,
                "interests": [item.strip() for item in interests_text.split(",") if item.strip()],
                "weekly_hours": weekly_hours,
                "goal": goal.value,
                "about_me": about_me,
            }
        )
    except (TypeError, ValueError):
        st.error("Please check your entries: one or more fields are invalid or too long.")
        log_event("profile_validation_failed")
    else:
        now = datetime.now(timezone.utc)
        window_epoch = int(now.timestamp()) // RATE_LIMIT_WINDOW_SECONDS
        window_start = datetime.fromtimestamp(
            window_epoch * RATE_LIMIT_WINDOW_SECONDS,
            timezone.utc,
        ).isoformat()
        session_hash = hashed_key("session", st.session_state["session_token"])
        client_ip = getattr(st.context, "ip", None)
        ip_hash = hashed_key(
            "ip",
            client_ip if isinstance(client_ip, str) and client_ip else "unavailable",
        )
        try:
            session_allowed = database.consume_limit(
                "session", session_hash, MAX_REQUESTS_PER_HOUR, window_start
            )
            ip_allowed = database.consume_limit(
                "ip", ip_hash, MAX_REQUESTS_PER_HOUR, window_start
            )
        except sqlite3.Error as error:
            log_event("rate_limit_storage_failed", error_type=type(error).__name__)
            st.error("We couldn't check the request limit right now. Please try again later.")
            session_allowed = False
            ip_allowed = False

        if not session_allowed or not ip_allowed:
            st.warning("The request limit has been reached. Please try again in a little while.")
        else:
            def reserve_llm_attempt() -> bool:
                today = datetime.now(timezone.utc).date().isoformat()
                return database.consume_limit(
                    "daily", "global", MAX_LLM_CALLS_PER_DAY, today
                )

            try:
                outcome = get_recommendation(
                    profile,
                    allow_gemini=allow_gemini,
                    before_attempt=reserve_llm_attempt,
                )
            except (sqlite3.Error, OSError, ValueError) as error:
                log_event("recommendation_failed", error_type=type(error).__name__)
                st.error("We couldn't create a recommendation right now. Please try again.")
            else:
                st.session_state["latest_outcome"] = outcome.model_dump(mode="json")
                st.session_state["latest_recommendation_id"] = None
                if not dont_store:
                    try:
                        recommendation_id = database.save_recommendation(
                            profile,
                            outcome.recommendation,
                            source=outcome.source,
                            model_name=outcome.model_name,
                            prompt_version=PROMPT_VERSION,
                            latency_ms=outcome.latency_ms,
                        )
                    except sqlite3.Error as error:
                        log_event("recommendation_storage_failed", error_type=type(error).__name__)
                        st.warning(
                            "Your recommendation is ready, but we couldn't save it. "
                            "It is available for this session."
                        )
                    else:
                        st.session_state["latest_recommendation_id"] = recommendation_id
                        st.session_state["stored_recommendation_ids"].append(recommendation_id)
                        log_event("recommendation_stored", source=outcome.source)
                log_event("recommendation_created", source=outcome.source)

if st.session_state["latest_outcome"] is not None:
    outcome = RecommendationOutcome.model_validate(st.session_state["latest_outcome"])
    show_recommendation(outcome)

    recommendation_id = st.session_state["latest_recommendation_id"]
    if recommendation_id:
        st.caption(f"Saved recommendation ID: {recommendation_id}")
        with st.form("feedback_form"):
            rating_label = st.selectbox("Was this recommendation useful?", ["👍 Yes", "👎 No"])
            feedback_consent = st.checkbox(
                "I consent to save this rating with my recommendation ID."
            )
            feedback_submitted = st.form_submit_button("Send optional feedback")
        if feedback_submitted:
            rating = 1 if rating_label.startswith("👍") else -1
            try:
                saved = database.add_feedback(recommendation_id, rating, feedback_consent)
            except sqlite3.Error as error:
                log_event("feedback_storage_failed", error_type=type(error).__name__)
                st.error("We couldn't save feedback right now.")
            else:
                if saved:
                    st.success("Thank you. Your feedback was saved.")
                    log_event("feedback_saved", rating=rating)
                else:
                    st.info("Feedback was not stored because consent was not selected.")
    else:
        st.caption("This recommendation was not saved; optional feedback storage is unavailable.")

st.divider()
st.subheader("Delete a saved recommendation")
st.caption(
    "Enter the recommendation ID shown when it was saved. Deleting it also removes its feedback."
)
with st.form("delete_form"):
    delete_id = st.text_input("Recommendation ID")
    delete_submitted = st.form_submit_button("Delete saved data")
if delete_submitted:
    try:
        normalized_id = str(UUID(delete_id.strip()))
    except (ValueError, AttributeError):
        st.error("Enter a valid recommendation ID.")
    else:
        try:
            deleted = database.delete_recommendation(normalized_id)
        except sqlite3.Error as error:
            log_event("recommendation_delete_failed", error_type=type(error).__name__)
            st.error("We couldn't delete that recommendation right now.")
        else:
            if deleted:
                st.success("The recommendation and its feedback were deleted.")
                stored_ids = st.session_state["stored_recommendation_ids"]
                if normalized_id in stored_ids:
                    stored_ids.remove(normalized_id)
                if normalized_id == st.session_state["latest_recommendation_id"]:
                    st.session_state["latest_recommendation_id"] = None
                log_event("recommendation_deleted")
            else:
                st.info("No saved recommendation matched that ID.")
