"""
Mock interview routes: question bank, feedback, and live STT over WebSocket.

WebSocket protocol  (/api/interview/ws/transcribe?token=<jwt>)
---------------------------------------------------------------
Client → Server
  binary          Audio frame (PCM16 LE mono 16 kHz | WAV | WebM, per config)
  {"type":"config","format":"pcm"|"wav"|"webm", ...}   optional, first message
  {"type":"end"}                                       finalize current utterance
  {"type":"reset"}                                     clear buffer without final
  {"type":"ping"}                                      keepalive

Server → Client
  {"type":"ready", ...}
  {"type":"partial","text":"...","full_text":"...","is_final":false,...}
  {"type":"final","text":"...","full_text":"...","is_final":true,...}
  {"type":"error","message":"..."}
  {"type":"pong"}
  {"type":"status","message":"..."}
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import wave
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, get_user_by_email
from app.models.models import User
from app.schemas.schemas import (
    InterviewFeedbackRequest,
    InterviewFeedbackResponse,
    InterviewQuestionsRequest,
)
from app.services.ai_optimizer import generate_interview_feedback, generate_interview_questions
from app.services.sarvam_stt import transcribe_audio

logger = logging.getLogger(__name__)
router = APIRouter()

# Cap concurrent live STT sessions per process (CPU protection)
_active_ws = 0
_active_ws_lock = asyncio.Lock()
_MAX_CONCURRENT_WS = 8


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


@router.post("/questions")
def interview_questions(
    request: InterviewQuestionsRequest,
    current_user: User = Depends(get_current_user),
):
    bank = generate_interview_questions(
        request.job_description,
        request.count,
        include_common=request.include_common,
    )
    # Keep `questions` for backward compatibility with the frontend
    return bank


@router.post("/feedback", response_model=InterviewFeedbackResponse)
def interview_feedback(
    request: InterviewFeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    if not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is required")
    result = generate_interview_feedback(request.job_description, request.transcript)
    return InterviewFeedbackResponse(**result)


@router.get("/stt/health")
def stt_health(current_user: User = Depends(get_current_user)):
    return {
        "ok": True,
        "engine": "sarvam",
        "recommended_format": "wav",
        "sample_rate": 16000,
        "ws_path": "/api/interview/ws/transcribe",
    }


@router.post("/stt/warmup")
def stt_warmup(current_user: User = Depends(get_current_user)):
    return {"ok": True, "message": "Sarvam API does not require warmup"}


@router.post("/stt/transcribe")
async def stt_transcribe_once(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """One-shot file transcription fallback."""
    data = await file.read()
    if not data or len(data) < 200:
        raise HTTPException(status_code=400, detail="Audio file is empty or too short")

    try:
        transcript = await transcribe_audio(data)
        return {"text": transcript}
    except Exception as e:
        logger.exception("One-shot transcription failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# WebSocket auth helper
# ---------------------------------------------------------------------------


def _user_from_token(token: str, db: Session) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
        email = payload.get("sub")
        if not email or not isinstance(email, str):
            return None
        return get_user_by_email(db, email)
    except JWTError:
        return None


async def _ws_send(ws: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Live transcription WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/transcribe")
async def ws_transcribe(
    websocket: WebSocket,
    token: str = Query(default=""),
    format: str = Query(default="pcm"),  # pcm | wav | webm
):
    """
    Near real-time transcription for mock interviews.

    Connect:
      ws://host/api/interview/ws/transcribe?token=<JWT>&format=pcm

    Preferred client path:
      - Capture mic with AudioWorklet / ScriptProcessor at 16 kHz mono
      - Stream raw PCM16 LE frames every ~100–250 ms
      - On stop, send {"type":"end"} and wait for {"type":"final"}

    Also supports:
      - format=wav  (complete short WAV blobs, e.g. from wavRecorder)
      - format=webm (MediaRecorder timeslices; higher latency due to ffmpeg)
    """
    global _active_ws

    # Origin check (browsers send Origin on WS handshake)
    origin = websocket.headers.get("origin") or ""
    allowed_origins = getattr(settings, "cors_origin_list", []) or []

    # Allow Vercel and local during development / production
    if settings.is_production and origin:
        is_allowed = (
            origin in allowed_origins
            or origin.endswith(".vercel.app")
            or origin.startswith("http://localhost")
        )
        if not is_allowed:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # Auth BEFORE accept when possible so bad tokens don't half-open the socket.
    # Query token is preferred; client may also send {"type":"auth","token":"..."} after open.
    db = next(get_db())
    try:
        user = _user_from_token(token, db) if token else None
    finally:
        db.close()

    await websocket.accept()

    if user is None and token:
        await _ws_send(
            websocket,
            {
                "type": "error",
                "message": "Session expired or invalid token. Log in again, then retry voice.",
            },
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Allow token via first text frame if not in query (avoids long-URL / proxy issues)
    if user is None:
        await _ws_send(
            websocket,
            {
                "type": "status",
                "message": "auth_required",
                "detail": 'Send {"type":"auth","token":"<jwt>"} or reconnect with ?token=',
            },
        )
        try:
            first = await asyncio.wait_for(websocket.receive(), timeout=10.0)
        except Exception:
            await _ws_send(
                websocket,
                {"type": "error", "message": "Unauthorized. Pass a valid JWT as ?token="},
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        auth_token = ""
        if first.get("text"):
            try:
                payload = json.loads(first["text"])
                if (payload.get("type") or "").lower() == "auth":
                    auth_token = str(payload.get("token") or "")
            except json.JSONDecodeError:
                auth_token = ""

        db = next(get_db())
        try:
            user = _user_from_token(auth_token, db)
        finally:
            db.close()

        if user is None:
            await _ws_send(
                websocket,
                {"type": "error", "message": "Unauthorized. Pass a valid JWT as ?token="},
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    async with _active_ws_lock:
        if _active_ws >= _MAX_CONCURRENT_WS:
            await _ws_send(
                websocket,
                {
                    "type": "error",
                    "message": "Too many concurrent transcription sessions. Try again shortly.",
                },
            )
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return
        _active_ws += 1

    fmt = (format or "pcm").lower().strip()

    audio_buffer = bytearray()

    try:
        await _ws_send(
            websocket,
            {
                "type": "ready",
                "message": 'Connected. Send audio bytes; send {"type":"end"} to finalize.',
                "format": fmt,
                "engine": "sarvam",
            },
        )

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # --- binary audio ---
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]
                if not chunk:
                    continue
                if len(chunk) > 512_000:
                    await _ws_send(
                        websocket,
                        {"type": "error", "message": "Audio frame too large (max 512 KB)"},
                    )
                    continue

                audio_buffer.extend(chunk)
                continue

            # --- text control ---
            text = message.get("text")
            if text is None:
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            msg_type = (data.get("type") or "").lower()

            if msg_type == "ping":
                await _ws_send(websocket, {"type": "pong"})
                continue

            if msg_type == "auth":
                continue

            if msg_type == "reset":
                audio_buffer.clear()
                await _ws_send(websocket, {"type": "status", "message": "buffer cleared"})
                continue

            if msg_type in {"end", "stop", "finalize"}:
                try:
                    if len(audio_buffer) == 0:
                        await _ws_send(
                            websocket,
                            {
                                "type": "final",
                                "text": "",
                                "is_final": True,
                                "message": "No speech detected",
                            },
                        )
                        continue

                    # Convert raw PCM16 buffer to WAV bytes
                    raw_pcm = bytes(audio_buffer)

                    wav_io = io.BytesIO()
                    with wave.open(wav_io, "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(16000)
                        wav_file.writeframes(raw_pcm)

                    audio_bytes = wav_io.getvalue()

                    # Call Sarvam AI
                    transcript = await transcribe_audio(audio_bytes, language_code="en-IN")

                    # Send final result to frontend
                    await websocket.send_json({"type": "final", "text": transcript or ""})

                    await websocket.send_json(
                        {"type": "status", "message": "transcription_complete"}
                    )

                    audio_buffer.clear()

                except Exception as e:
                    logger.error(f"Sarvam transcription failed: {e}", exc_info=True)
                    await websocket.send_json(
                        {"type": "error", "message": "Transcription failed. Please try again."}
                    )
                continue

            if msg_type == "close":
                break

    except WebSocketDisconnect:
        logger.debug("STT websocket disconnected")
    except Exception as e:
        logger.exception("STT websocket error: %s", e)
        await _ws_send(websocket, {"type": "error", "message": str(e)})
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        async with _active_ws_lock:
            _active_ws = max(0, _active_ws - 1)
