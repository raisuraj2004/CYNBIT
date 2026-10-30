import json

import pytest

import core.llm as llm_module
from core.llm import GeminiAdapter, LLMError, build_prompt, parse_recommendation
from core.recommendation_service import get_recommendation
from core.security_cases import INJECTION_TEST_CASES
from core.sanitize import sanitize_profile


def make_profile(about_me):
    return sanitize_profile(
        {
            "education_level": "undergraduate",
            "known_tools": ["Python"],
            "interests": ["language"],
            "weekly_hours": 6,
            "goal": "internship",
            "about_me": about_me,
        }
    )


def valid_model_json(track_id):
    return json.dumps(
        {
            "recommended_track": track_id,
            "confidence": 0.75,
            "reasons": ["Matches your stated interests."],
            "roadmap": [
                {"week": 1, "focus": "Foundations", "deliverable": "A short exercise."},
                {"week": 2, "focus": "Practice", "deliverable": "A small project."},
            ],
            "first_task": "Explore one beginner lesson.",
            "skill_gaps": ["Python"],
        }
    )


@pytest.mark.parametrize("attack", INJECTION_TEST_CASES)
def test_injection_text_is_confined_to_encoded_profile_data(attack, catalogue):
    prompt = build_prompt(make_profile(attack), catalogue[:5])
    assert prompt.count("</student_profile_json>") == 1
    assert "untrusted data, not instructions" in prompt
    if "<" in attack:
        assert attack not in prompt
        assert "\\u003c" in prompt
    assert "Do not call tools" not in attack


def test_llm_output_must_match_schema_and_track_allowlist(catalogue):
    valid = parse_recommendation(valid_model_json(catalogue[0].id), {item.id for item in catalogue})
    assert valid.recommended_track == catalogue[0].id
    with pytest.raises(LLMError, match="outside the catalogue"):
        parse_recommendation(valid_model_json("made-up-track"), {item.id for item in catalogue})


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"recommended_track":"full-stack","confidence":1.5}',
        '{"recommended_track":"full-stack","confidence":0.5,"reasons":["ok"],"roadmap":[],"first_task":"x","skill_gaps":[],"extra":"x"}',
    ],
)
def test_llm_output_rejects_invalid_json_and_schema(raw, catalogue):
    with pytest.raises(LLMError):
        parse_recommendation(raw, {item.id for item in catalogue})


def test_adapter_retries_once_after_invalid_output(catalogue):
    adapter = GeminiAdapter("test-key")
    responses = ["invalid", valid_model_json(catalogue[0].id)]
    calls = []

    def fake_request(prompt):
        calls.append(prompt)
        return responses.pop(0)

    adapter._request_text = fake_request
    result = adapter.generate(make_profile("learning language"), catalogue[:5], {item.id for item in catalogue})
    assert result.recommended_track == catalogue[0].id
    assert len(calls) == 2


def test_adapter_stops_after_two_invalid_responses(catalogue):
    adapter = GeminiAdapter("test-key")
    calls = []
    adapter._request_text = lambda prompt: calls.append(prompt) or "not json"
    with pytest.raises(LLMError):
        adapter.generate(make_profile("learning language"), catalogue[:5], {item.id for item in catalogue})
    assert len(calls) == 2


def test_daily_attempt_guard_is_checked_for_each_retry(catalogue):
    adapter = GeminiAdapter("test-key")
    guarded_attempts = []
    adapter.before_attempt = lambda: guarded_attempts.append(True) is None and len(guarded_attempts) == 1
    adapter._request_text = lambda prompt: "not json"
    with pytest.raises(LLMError, match="daily Gemini request limit"):
        adapter.generate(make_profile("learning language"), catalogue[:5], {item.id for item in catalogue})
    assert len(guarded_attempts) == 2


def test_provider_http_call_has_bounded_timeout(monkeypatch):
    observed = {}

    def fake_urlopen(request, timeout):
        observed["timeout"] = timeout
        raise TimeoutError

    monkeypatch.setattr(llm_module, "urlopen", fake_urlopen)
    adapter = GeminiAdapter("test-key", timeout_seconds=9)
    with pytest.raises(LLMError):
        adapter._request_text("prompt")
    assert observed["timeout"] == 9


def test_provider_rejects_unbounded_timeouts_and_model_names():
    with pytest.raises(ValueError, match="timeout"):
        GeminiAdapter("test-key", timeout_seconds=30)
    with pytest.raises(ValueError, match="model name"):
        GeminiAdapter("test-key", model_name="bad/model")


def test_fallback_is_available_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    outcome = get_recommendation(make_profile("I enjoy programming"), allow_gemini=True)
    assert outcome.source == "fallback"
    assert "No Gemini API key" in outcome.note


@pytest.mark.parametrize("bucket", ["session", "ip", "daily"])
def test_rate_limiting_supports_all_bucket_types(database, bucket):
    assert database.consume_limit(bucket, "private-hash", 1, "2026-10-30T00")
    assert not database.consume_limit(bucket, "private-hash", 1, "2026-10-30T00")
