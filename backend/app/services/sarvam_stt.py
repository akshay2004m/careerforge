"""
Sarvam AI Speech-to-Text service
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("careerforge.sarvam")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe_audio(audio_bytes: bytes, language_code: str = "en-IN") -> str:
    """
    Transcribe audio using Sarvam AI.
    Accepts raw audio bytes (wav/webm/pcm).
    Returns transcribed text.
    """
    if not settings.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set")

    headers = {
        "api-subscription-key": settings.SARVAM_API_KEY,
    }

    files = {
        "file": ("audio.wav", audio_bytes, "audio/wav"),
    }

    data = {
        "language_code": language_code,  # en-IN works well for Indian English
        "model": "saaras:v2",  # or latest model available
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            SARVAM_STT_URL,
            headers=headers,
            files=files,
            data=data,
        )

    if response.status_code != 200:
        logger.error(f"Sarvam STT failed: {response.status_code} - {response.text}")
        raise RuntimeError(f"Sarvam STT error: {response.text}")

    result = response.json()
    transcript = result.get("transcript") or result.get("text") or ""
    return transcript.strip()
