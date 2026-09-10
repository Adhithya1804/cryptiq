"""A thin, isolated wrapper around the official ``google-genai`` SDK.

Only what an explanation needs: a system instruction plus one bounded user
message in, one JSON string out, with a hard timeout, an output-token ceiling,
and a structured-output schema -- all from settings. The API key is read from
settings, handed to the SDK client, and never logged or returned.

This module is the *only* place in Cryptiq that imports the Gemini SDK. The
deterministic engine never imports this package; an explanation restates
findings, it never establishes them.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    """Raised for any failure talking to Gemini or reading its response.

    The message is always safe to surface; provider stack traces, request
    details and the API key never reach it.
    """


class GeminiClient:
    """Generates structured JSON with a single configured Gemini model."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sdk_client: object | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # Tests inject a fake exposing ``models.generate_content(...)``. In
        # production this stays ``None`` and a real client is built lazily so
        # importing this module never requires a key.
        self._sdk_client = sdk_client

    @property
    def model(self) -> str:
        return self._settings.gemini_model

    @property
    def prompt_temperature(self) -> float:
        return 0.2

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.gemini_api_key) or self._sdk_client is not None

    def _client(self) -> object:
        if self._sdk_client is not None:
            return self._sdk_client
        key = self._settings.gemini_api_key
        if not key:
            raise GeminiError("AI explanations are not configured.")
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise GeminiError("The AI explanation SDK is not installed.") from exc
        return genai.Client(api_key=key)

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        schema: type[BaseModel],
    ) -> str:
        """Return the model's raw JSON text, or raise :class:`GeminiError`.

        The caller re-validates the text against its own Pydantic model; this
        method only guarantees a non-empty string was produced.
        """
        client = self._client()
        try:
            from google.genai import errors, types
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise GeminiError("The AI explanation SDK is not installed.") from exc

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=self.prompt_temperature,
            max_output_tokens=self._settings.gemini_max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(
                timeout=self._settings.gemini_timeout_seconds * 1000
            ),
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_content,
                config=config,
            )
        except errors.APIError as exc:
            # ``code`` is the HTTP status; the body can echo request context, so
            # only the status is logged.
            logger.warning("Gemini API error (HTTP %s)", getattr(exc, "code", "?"))
            raise GeminiError("The explanation service returned an error.") from exc
        except GeminiError:
            raise
        except Exception as exc:  # network, timeout, transport
            logger.warning("Gemini request failed: %s", type(exc).__name__)
            raise GeminiError("The explanation service could not be reached.") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise GeminiError("The explanation service returned an empty response.")
        return text
