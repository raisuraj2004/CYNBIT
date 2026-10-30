"""Evaluate synthetic labels, fallback validity, optional Gemini, and injection handling."""

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_GEMINI_MODEL, MAX_LLM_CALLS_PER_DAY
from core.db import Database
from core.fallback import recommend_fallback
from core.llm import GeminiAdapter, LLMError, build_prompt, parse_recommendation
from core.retrieval import load_tracks, score_tracks, top_candidates
from core.sanitize import sanitize_profile
from core.schemas import Recommendation, Track, TrackProfile
from core.security_cases import INJECTION_TEST_CASES

EVAL_PATH = Path(__file__).resolve().parent / "profiles.csv"
EDUCATION_LEVELS = {"secondary", "diploma", "undergraduate", "postgraduate"}
GOALS = {"internship", "job", "upskill"}


def load_profiles() -> list[tuple[str, TrackProfile, set[str]]]:
    """Read synthetic profiles and manually assigned acceptable track IDs."""
    profiles = []
    with EVAL_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["education_level"] not in EDUCATION_LEVELS or row["goal"] not in GOALS:
                raise ValueError(f"Invalid labels in synthetic profile {row['profile_id']}.")
            profile = sanitize_profile(
                {
                    "education_level": row["education_level"],
                    "known_tools": row["known_tools"].split("|") if row["known_tools"] else [],
                    "interests": row["interests"].split("|") if row["interests"] else [],
                    "weekly_hours": int(row["weekly_hours"]),
                    "goal": row["goal"],
                    "about_me": row["about_me"],
                }
            )
            labels = set(row["correct_tracks"].split("|"))
            profiles.append((row["profile_id"], profile, labels))
    if len(profiles) != 20:
        raise ValueError("Evaluation data must contain exactly 20 synthetic profiles.")
    return profiles


def accuracy(hits: int, total: int) -> str:
    return f"{100 * hits / total:.1f}%" if total else "n/a"


def run_injection_checks(tracks: list[Track]) -> tuple[int, int]:
    """Check delimiter confinement and invalid-track rejection for each attack."""
    passed = 0
    valid_ids = {track.id for track in tracks}
    for attack in INJECTION_TEST_CASES:
        profile = sanitize_profile(
            {
                "education_level": "undergraduate",
                "known_tools": [],
                "interests": ["security testing"],
                "weekly_hours": 6,
                "goal": "upskill",
                "about_me": attack,
            }
        )
        prompt = build_prompt(profile, tracks[:5])
        delimiter_safe = prompt.count("</student_profile_json>") == 1
        escaped_tags = "<" not in attack or attack not in prompt
        allowlist_safe = False
        invalid_result = {
            "recommended_track": "attacker-controlled-id",
            "confidence": 0.5,
            "reasons": ["No valid catalogue match."],
            "roadmap": [
                {"week": 1, "focus": "Test", "deliverable": "Test"},
                {"week": 2, "focus": "Test", "deliverable": "Test"},
            ],
            "first_task": "Test.",
            "skill_gaps": [],
        }
        try:
            parse_recommendation(json.dumps(invalid_result), valid_ids)
        except LLMError:
            allowlist_safe = True
        if delimiter_safe and escaped_tags and allowlist_safe:
            passed += 1
    return passed, len(INJECTION_TEST_CASES)


def run_evaluation(use_llm: bool) -> None:
    """Print measured metrics for fallback and optional live Gemini comparison."""
    profiles = load_profiles()
    tracks = load_tracks()
    track_ids = {track.id for track in tracks}
    fallback_hits_top1 = 0
    fallback_hits_top3 = 0
    fallback_valid = 0
    fallback_latencies: list[float] = []
    llm_hits_top1 = 0
    llm_hits_top3 = 0
    llm_valid = 0
    llm_latencies: list[float] = []
    llm_attempted = False

    adapter = None
    if use_llm:
        database = Database()
        adapter = GeminiAdapter.from_environment(
            before_attempt=lambda: database.consume_limit(
                "daily",
                "global",
                MAX_LLM_CALLS_PER_DAY,
                datetime.now(timezone.utc).date().isoformat(),
            )
        )

    for _, profile, labels in profiles:
        started = time.perf_counter()
        fallback = recommend_fallback(profile)
        fallback_latencies.append((time.perf_counter() - started) * 1000)
        ranked_ids = [track.id for track, _ in score_tracks(profile, tracks)]
        fallback_hits_top1 += fallback.recommended_track in labels
        fallback_hits_top3 += bool(set(ranked_ids[:3]) & labels)
        round_trip = Recommendation.model_validate_json(
            fallback.model_dump_json(),
            strict=True,
        )
        fallback_valid += round_trip.recommended_track in track_ids

        if adapter is not None:
            llm_attempted = True
            started = time.perf_counter()
            try:
                llm_result = adapter.generate(
                    profile,
                    top_candidates(profile, tracks),
                    track_ids,
                )
            except LLMError:
                llm_latencies.append((time.perf_counter() - started) * 1000)
            else:
                llm_latencies.append((time.perf_counter() - started) * 1000)
                llm_valid += 1
                llm_hits_top1 += llm_result.recommended_track in labels
                llm_ranked = [llm_result.recommended_track, *ranked_ids]
                llm_hits_top3 += bool(set(llm_ranked[:3]) & labels)

    total = len(profiles)
    print(f"Profiles: {total} synthetic")
    print(
        "Fallback retrieval: "
        f"top-1 accuracy {accuracy(fallback_hits_top1, total)}; "
        f"top-3 accuracy {accuracy(fallback_hits_top3, total)}; "
        f"JSON validity {accuracy(fallback_valid, total)}; "
        f"average latency {statistics.mean(fallback_latencies):.2f} ms"
    )
    if adapter is not None and llm_attempted:
        print(
            f"Gemini comparison ({adapter.model_name}): "
            f"top-1 accuracy {accuracy(llm_hits_top1, total)}; "
            f"top-3 accuracy {accuracy(llm_hits_top3, total)}; "
            f"JSON validity {accuracy(llm_valid, total)}; "
            f"average latency {statistics.mean(llm_latencies):.2f} ms"
        )
        print(
            "Fallback vs Gemini top-1 delta: "
            f"{100 * (llm_hits_top1 - fallback_hits_top1) / total:+.1f} percentage points"
        )
    elif not use_llm or adapter is None:
        print(
            "LLM comparison: not run; set --llm and GOOGLE_API_KEY to opt in to "
            f"the live {DEFAULT_GEMINI_MODEL} comparison."
        )
    injection_passed, injection_total = run_injection_checks(tracks)
    print(
        "Prompt-injection checks: "
        f"{injection_passed}/{injection_total} passed "
        f"({accuracy(injection_passed, injection_total)})"
    )
    if adapter is not None and llm_attempted:
        print(
            "LLM recommendation count may be below the dataset size if the daily "
            "attempt cap is reached or the provider fails."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Opt in to sending only the synthetic evaluation profiles to Gemini.",
    )
    run_evaluation(parser.parse_args().llm)
