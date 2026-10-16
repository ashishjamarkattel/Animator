"""Checks a user's own Gemini API key before a video is started with it."""

from __future__ import annotations

import logging

from google import genai
from google.genai import errors

from ..cli import resolve_model
from ..gemini.settings import DEFAULT_TEXT_MODEL

log = logging.getLogger(__name__)

REJECTED = "Gemini rejected your API key. Check it, or create a new one at aistudio.google.com/apikey."


class KeyCheckFailed(Exception):
    """The key can't be used; the message is shown to the user as is."""


def check_key(api_key: str) -> None:
    """Raises KeyCheckFailed only when Gemini says the key itself is bad. Looking up a model costs nothing.

    Any other failure (a model name the key can't see, a network blip) is logged and let through:
    the video then starts, and if Gemini really is unusable it fails with its actual reason.
    """
    try:
        genai.Client(api_key=api_key).models.get(model=resolve_model(None, DEFAULT_TEXT_MODEL))
    except errors.ClientError as exc:
        # a bad or revoked key: 400 API_KEY_INVALID, or 401/403
        if exc.code in (401, 403) or (exc.code == 400 and "api key" in str(exc).lower()):
            raise KeyCheckFailed(REJECTED) from exc
        log.warning("Gemini key check inconclusive (%s %s); starting anyway", exc.code, exc.status)
    except Exception as exc:
        log.warning("Gemini key check inconclusive (%s); starting anyway", type(exc).__name__)
