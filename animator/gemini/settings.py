"""Model defaults and retry settings for every Gemini call."""
import os

DEFAULT_TEXT_MODEL = "gemini-3.8-flash"
DEFAULT_REGION_MODEL = "gemini-3.1-flash-lite"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "Kore"

MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
RETRY_DELAY_SEC = float(os.getenv("GEMINI_RETRY_DELAY_SEC", "8"))
