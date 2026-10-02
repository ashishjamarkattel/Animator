"""STEP 3: speak a scene's beats as one take and time each beat in it."""
from __future__ import annotations

from typing import List, Tuple

from google import genai
from google.genai import types

from .beat_timing import locate_beats, pcm_to_wav
from .client import first_inline_data, with_retry
from .settings import DEFAULT_TTS_MODEL, DEFAULT_VOICE


def synthesize_pcm(google_client: genai.Client, text: str, model: str, voice: str) -> bytes:
    """Raw speech: mono 16-bit PCM at 24kHz."""
    response = with_retry(lambda: google_client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    ))
    return first_inline_data(response, "Narration synthesis")


def generate_beat_narration(
    google_client: genai.Client,
    beats: List[str],
    *,
    model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_VOICE,
) -> Tuple[bytes, List[List[float]]]:
    """Synthesize a scene's beats as one take and locate each beat in it.

    Returns (wav_bytes, windows) where windows[i] is the [start, end] in
    seconds of beat i inside the WAV, so drawing can be locked to speech.
    One request per scene keeps the voice natural and stays inside TTS rate
    limits; beat boundaries are recovered from the pauses between sentences.
    """
    pcm = synthesize_pcm(google_client, " ".join(text.strip() for text in beats), model, voice)
    return pcm_to_wav(pcm), locate_beats(pcm, beats)
