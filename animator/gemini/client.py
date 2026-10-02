"""Shared plumbing for Gemini calls: retries and pulling binary output."""
from __future__ import annotations

import asyncio
import logging
import time

from google.genai import errors

from .settings import MAX_RETRIES, RETRY_DELAY_SEC

logger = logging.getLogger(__name__)


def is_retryable(exc: Exception) -> bool:
    """Rate limits (429) and server errors (5xx) are worth retrying."""
    return isinstance(exc, errors.APIError) and (exc.code == 429 or (exc.code or 0) >= 500)


def with_retry(call):
    """Run a blocking Gemini call, backing off on retryable errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call()
        except Exception as exc:
            if attempt == MAX_RETRIES or not is_retryable(exc):
                raise
            logger.warning("Gemini call failed (%s); retry %s/%s", exc, attempt, MAX_RETRIES)
            time.sleep(RETRY_DELAY_SEC * attempt)


async def with_retry_async(call):
    """Await a Gemini call made by `call()`, backing off on retryable errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await call()
        except Exception as exc:
            if attempt == MAX_RETRIES or not is_retryable(exc):
                raise
            logger.warning("Gemini call failed (%s); retry %s/%s", exc, attempt, MAX_RETRIES)
            await asyncio.sleep(RETRY_DELAY_SEC * attempt)


def first_inline_data(response, what: str) -> bytes:
    """Bytes of the first inline part (image or audio) in a response."""
    if response.candidates:
        for part in response.candidates[0].content.parts or []:
            if part.inline_data is not None:
                return part.inline_data.data
    raise RuntimeError(f"{what} returned no data. raw: {(response.text or '')[:500]}")
