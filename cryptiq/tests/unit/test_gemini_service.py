"""Unit tests for the isolated Gemini explanation service and its SDK wrapper.

No network. The SDK is a fake object; the real ``GeminiClient`` and
``GeminiExplanationService`` code runs.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.config import Settings
from app.db.models.enums import Confidence, CryptographicRole, ReviewPriority
from app.integrations.gemini import GeminiClient, GeminiError
from app.services.gemini import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    GeminiExplanationPayload,
    GeminiExplanationService,
    build_input,
)

_VALID = json.dumps(
    {
        "summary": "s",
        "why_it_matters": "w",
        "evidence_explanation": "e",
        "migration_explanation": "m",
        "impact_explanation": "i",
        "limitations": [],
    }
)


class _Resp:
    def __init__(self, text):
        self.text = text


class _Sdk:
    def __init__(self, text=_VALID, exc=None):
        self.text, self.exc, self.calls = text, exc, []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.exc:
            raise self.exc
        return _Resp(self.text)


def _settings(**over) -> Settings:
    base = {
        "gemini_api_key": "unit-secret-key",
        "gemini_model": "gemini-2.5-flash",
        "gemini_timeout_seconds": 30,
        "gemini_max_output_tokens": 1500,
    }
    base.update(over)
    return Settings(_env_file=None, **base)


def _client(sdk: _Sdk) -> GeminiClient:
    return GeminiClient(_settings(), sdk_client=sdk)


# ------------------------------------------------------------------ client ---


def test_generate_structured_returns_raw_text() -> None:
    out = _client(_Sdk()).generate_structured(
        system_instruction="sys", user_content="body", schema=GeminiExplanationPayload
    )
    assert json.loads(out)["summary"] == "s"


def test_api_error_becomes_gemini_error_without_leaking_details(caplog) -> None:
    from google.genai import errors

    sdk = _Sdk(exc=errors.APIError(500, {"error": {"message": "internal detail"}}))
    with caplog.at_level(logging.WARNING), pytest.raises(GeminiError) as ei:
        _client(sdk).generate_structured(
            system_instruction="s", user_content="b", schema=GeminiExplanationPayload
        )
    assert "internal detail" not in str(ei.value)


def test_transport_error_becomes_gemini_error() -> None:
    with pytest.raises(GeminiError):
        _client(_Sdk(exc=TimeoutError("slow"))).generate_structured(
            system_instruction="s", user_content="b", schema=GeminiExplanationPayload
        )


def test_empty_response_is_an_error() -> None:
    with pytest.raises(GeminiError):
        _client(_Sdk(text="   ")).generate_structured(
            system_instruction="s", user_content="b", schema=GeminiExplanationPayload
        )


def test_api_key_is_never_logged(caplog) -> None:
    sdk = _Sdk(exc=RuntimeError("boom"))
    with caplog.at_level(logging.DEBUG), pytest.raises(GeminiError):
        _client(sdk).generate_structured(
            system_instruction="s", user_content="b", schema=GeminiExplanationPayload
        )
    assert "unit-secret-key" not in caplog.text


def test_client_not_configured_without_key_or_sdk() -> None:
    assert GeminiClient(_settings(gemini_api_key=None)).is_configured is False
    assert GeminiClient(_settings()).is_configured is True


# ------------------------------------------------------------------ service ---


class _Finding:
    """Minimal stand-in with the attributes ``build_input`` reads."""

    class _Ev:
        rule_id = "rsa-sign-1"
        source_excerpt = "X" * 5000  # deliberately over the cap

    def __init__(self):
        self.evidence = self._Ev()
        self.algorithm = "RSA"
        self.primitive = "asymmetric"
        self.library = "cryptography"
        self.api = "RSAPrivateKey.sign"
        self.operation = "sign"
        self.file_path = "src/signing.py"
        self.start_line = 4
        self.end_line = 5
        self.role = CryptographicRole.DIGITAL_SIGNATURE
        self.role_rationale = "calls .sign"
        self.confidence = Confidence.HIGH
        self.priority = ReviewPriority.HIGH
        self.priority_score = 70
        self.priority_reasons = ["signature scheme"]
        self.impact_nodes = []


class _Scan:
    class _Repo:
        owner = "pyca"
        name = "cryptography"

    repository = _Repo()


def test_build_input_is_bounded() -> None:
    packet = build_input(_Finding(), _Scan())
    assert packet.algorithm == "RSA"
    assert packet.file_path == "src/signing.py"
    assert len(packet.source_excerpt) <= 2000  # truncated
    dumped = packet.model_dump()
    # No field exists for arbitrary caller text or extra source files.
    assert "prompt" not in dumped and "files" not in dumped


def test_service_validates_and_returns_payload() -> None:
    sdk = _Sdk()
    svc = GeminiExplanationService(_client(sdk))
    out = svc.explain(build_input(_Finding(), _Scan()))
    assert isinstance(out, GeminiExplanationPayload)
    assert out.summary == "s"
    # The bounded packet, not repo source, was sent; system instruction is versioned.
    call = sdk.calls[0]
    assert PROMPT_VERSION in call["config"].system_instruction
    assert call["config"].system_instruction == SYSTEM_INSTRUCTION
    assert json.loads(call["contents"])["finding"]["algorithm"] == "RSA"


def test_service_rejects_malformed_model_output() -> None:
    svc = GeminiExplanationService(_client(_Sdk(text='{"summary": 123}')))
    with pytest.raises(GeminiError):
        svc.explain(build_input(_Finding(), _Scan()))


def test_prompt_version_is_stable_token() -> None:
    assert PROMPT_VERSION == "gemini-explanation-v1"
