import json
import os

import pytest

import core.llm as llm_module
from config import DEFAULT_GEMINI_MODEL
from core.llm import GeminiAdapter, LLMError, build_prompt, parse_recommendation
from core.recommendation_service import _fallback_note
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


@pytest.mark.parametrize(
    ("status", "diagnostic"),
    [(400, "http_400"), (401, "http_401"), (403, "http_403"), (404, "http_404"), (429, "http_429")],
)
def test_provider_http_errors_retain_only_safe_status(monkeypatch, status, diagnostic):
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, status, "private provider detail", {}, None)

    monkeypatch.setattr(llm_module, "urlopen", fake_urlopen)
    adapter = GeminiAdapter("sample-api-key")
    with pytest.raises(LLMError) as raised:
        adapter._request_text("synthetic diagnostic request")
    assert raised.value.diagnostic == diagnostic
    assert "private provider detail" not in str(raised.value)


@pytest.mark.parametrize(
    ("diagnostic", "expected_text"),
    [
        ("http_403", "Check the key"),
        ("http_503", "No key change is indicated"),
    ],
)
def test_fallback_note_suggests_action_from_safe_http_status(diagnostic, expected_text):
    note = _fallback_note(LLMError("request failed", diagnostic=diagnostic))
    assert expected_text in note
    assert "rule-based recommendation" in note


def test_provider_rejects_unbounded_timeouts_and_model_names():
    with pytest.raises(ValueError, match="timeout"):
        GeminiAdapter("test-key", timeout_seconds=30)
    with pytest.raises(ValueError, match="model name"):
        GeminiAdapter("test-key", model_name="bad/model")


def test_fallback_is_available_without_api_key(monkeypatch):
    import streamlit as st

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(st, "secrets", {})
    outcome = get_recommendation(make_profile("I enjoy programming"), allow_gemini=True)
    assert outcome.source == "fallback"
    assert "No Gemini API key" in outcome.note


def test_default_gemini_model_uses_configured_flash_version():
    assert DEFAULT_GEMINI_MODEL == "gemini-3.8-flash"


def test_adapter_uses_new_default_model_when_env_model_is_unset(monkeypatch):
    api_name = "GOOGLE_" + "API_KEY"
    monkeypatch.setenv(api_name, "sample-a")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    adapter = GeminiAdapter.from_environment()
    assert adapter is not None
    assert adapter.model_name == "gemini-3.8-flash"


def test_adapter_reads_gemini_key_and_model_from_streamlit_secrets(monkeypatch):
    import streamlit as st

    class FakeSecrets(dict):
        def get(self, name, default=""):
            return super().get(name, default)

    api_name = "GOOGLE_" + "API_KEY"
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(
        st,
        "secrets",
        FakeSecrets({api_name: "sample-a", "GEMINI_MODEL": "gemini-3.8-flash"}),
    )
    adapter = GeminiAdapter.from_environment()
    assert adapter is not None
    assert adapter.model_name == "gemini-3.8-flash"


def test_environment_variables_override_streamlit_secrets(monkeypatch):
    import streamlit as st

    class FakeSecrets(dict):
        requested = []

        def get(self, name, default=""):
            self.requested.append(name)
            return super().get(name, default)

    api_name = "GOOGLE_" + "API_KEY"
    secrets = FakeSecrets({api_name: "sample-b", "GEMINI_MODEL": "gemini-3.8-flash"})
    monkeypatch.setattr(
        st,
        "secrets",
        secrets,
    )
    monkeypatch.setitem(os.environ, api_name, "sample-c")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash-preview")
    adapter = GeminiAdapter.from_environment()
    assert adapter is not None
    assert adapter.model_name == "gemini-3.8-flash-preview"
    assert api_name not in secrets.requested


@pytest.mark.parametrize("bucket", ["session", "ip", "daily"])
def test_rate_limiting_supports_all_bucket_types(database, bucket):
    assert database.consume_limit(bucket, "private-hash", 1, "2026-10-30T00")
    assert not database.consume_limit(bucket, "private-hash", 1, "2026-10-30T00")
