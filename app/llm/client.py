"""Groq client — Phase 5.

Uses httpx (already a dependency) against Groq's OpenAI-compatible
chat-completions endpoint with response_format json_object. No groq
SDK was added: httpx + the settings already in config.py are enough,
and one fewer dependency is one fewer thing to maintain.

The client never touches the database and never executes SQL: it
takes text in and returns a validated LLMParsedUpdate (or raises
GroqError / LLMParseError). All ownership checks and writes live in
services/site_update_service.py.

Errors are deliberately split so the service can record the right
failure reason:
  * GroqError        — no key configured, HTTP error, timeout, or any
                       transport failure talking to Groq.
  * LLMParseError    — Groq answered, but the body was not JSON, or
                       the JSON failed LLMParsedUpdate validation
                       (malformed JSON, unknown action type, invalid
                       quantity/status/category, ...).
"""
import json

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.schemas import LLMParsedUpdate

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
# Generous but bounded: a site update must not hang a request forever.
# Raised 30 -> 60s on 2026-11-25: live Groq calls measured ~30s+
# through this dev machine's egress proxy; normal hosting has no proxy
# and answers in seconds, so 60s is a safe production ceiling.
REQUEST_TIMEOUT_SECONDS = 60.0


class GroqError(Exception):
    """Groq is not configured, unreachable, or returned an HTTP error."""


class LLMParseError(Exception):
    """Groq answered, but its output was not valid structured JSON."""


class GroqClient:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None):
        self._settings = settings
        # http_client is injectable so tests can pass a MockTransport
        # client; production code passes nothing and gets a real client.
        self._http_client = http_client

    def parse_site_update(self, system_prompt: str, user_prompt: str) -> LLMParsedUpdate:
        """Call Groq and return the validated structured output."""
        if not self._settings.groq_configured:
            raise GroqError(
                "The LLM is not configured: set GROQ_API_KEY to use site updates."
            )
        payload = {
            "model": self._settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        client = self._http_client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        close_client = self._http_client is None
        try:
            try:
                response = client.post(
                    GROQ_CHAT_COMPLETIONS_URL, json=payload, headers=headers
                )
            except httpx.HTTPError as exc:
                raise GroqError(
                    f"Could not reach the LLM service: {exc.__class__.__name__}."
                ) from exc
            if response.status_code != 200:
                raise GroqError(
                    f"The LLM service returned HTTP {response.status_code}."
                )
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMParseError(
                    "The LLM returned a response that could not be read."
                ) from exc
            return parse_llm_response(content)
        finally:
            if close_client:
                client.close()


def parse_llm_response(content: str) -> LLMParsedUpdate:
    """Parse + validate one raw LLM content string.

    Kept as a free function so tests (and the service) can exercise
    parsing without any HTTP call.
    """
    if not isinstance(content, str) or not content.strip():
        raise LLMParseError("The LLM returned an empty response.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMParseError(
            "The LLM returned output that was not valid JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMParseError("The LLM returned JSON that was not an object.")
    try:
        return LLMParsedUpdate.model_validate(data)
    except ValidationError as exc:
        # Summarise, don't dump the raw model output: the first error
        # is usually enough for a human to see what went wrong.
        first = exc.errors()[0]
        location = ".".join(str(p) for p in first["loc"])
        raise LLMParseError(
            f"The LLM output failed validation at {location}: {first['msg']}."
        ) from exc


def parse_site_update_with_client(
    settings: Settings,
    user_prompt: str,
    http_client: httpx.Client | None = None,
) -> LLMParsedUpdate:
    """Convenience wrapper used by the service layer."""
    return GroqClient(settings, http_client).parse_site_update(
        SYSTEM_PROMPT, user_prompt
    )
