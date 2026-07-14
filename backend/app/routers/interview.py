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
import json
import logging
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
from app.services.faster_whisper_stream import (
    StreamingSession,
    model_info,
    transcribe_bytes,
    warmup_model,
)

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
    """Check whether faster-whisper + ffmpeg are available (does not force load)."""
    info = model_info()
    return {
        "ok": True,
        "engine": "faster-whisper",
        **info,
        "recommended_format": "pcm",
        "sample_rate": 16000,
        "ws_path": "/api/interview/ws/transcribe",
    }


@router.post("/stt/warmup")
def stt_warmup(current_user: User = Depends(get_current_user)):
    """Load the Whisper model into memory (first call can take a while)."""
    try:
        info = warmup_model()
        return {"ok": True, "message": "Model loaded", **info}
    except Exception as e:
        logger.exception("Whisper warmup failed")
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/stt/transcribe")
async def stt_transcribe_once(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """One-shot file transcription fallback (complete WebM/WAV/MP3)."""
    data = await file.read()
    if not data or len(data) < 200:
        raise HTTPException(status_code=400, detail="Audio file is empty or too short")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25 MB)")

    try:
        result = await asyncio.to_thread(
            transcribe_bytes, data, file.filename or "audio.webm"
        )
        return result
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
    if settings.is_production and origin and origin not in settings.cors_origin_list:
        # Reject before accept → clean HTTP-level failure
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
                "detail": "Send {\"type\":\"auth\",\"token\":\"<jwt>\"} or reconnect with ?token=",
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
    if fmt not in {"pcm", "wav", "webm", "ogg", "mp3", "m4a"}:
        fmt = "pcm"

    session = StreamingSession(format=fmt)  # type: ignore[arg-type]
    model_ready = False
    warm_task: asyncio.Task | None = None

    try:
        # Send ready immediately — do NOT block handshake on model download/load.
        # Model loads lazily on first audio (or optional client {"type":"warmup"}).
        await _ws_send(
            websocket,
            {
                "type": "ready",
                "message": "Connected. Stream audio; send {\"type\":\"end\"} to finalize.",
                "format": fmt,
                "sample_rate": 16000,
                "channels": 1,
                "encoding": "pcm_s16le" if fmt == "pcm" else fmt,
                "engine": "faster-whisper",
                "model_loaded": model_info().get("loaded", False),
                **model_info(),
            },
        )

        # Warm in background so first partial is faster
        async def _bg_warm() -> None:
            nonlocal model_ready
            try:
                await asyncio.to_thread(warmup_model)
                model_ready = True
                await _ws_send(
                    websocket,
                    {"type": "status", "message": "model_ready", **model_info()},
                )
            except Exception as e:
                logger.exception("Background Whisper warmup failed")
                await _ws_send(
                    websocket,
                    {"type": "error", "message": f"STT engine failed to load: {e}"},
                )

        warm_task = asyncio.create_task(_bg_warm())

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # --- binary audio ---
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]
                if not chunk:
                    continue
                # Soft size guard per frame (2s of PCM16 mono ~ 64 KB; webm can be larger)
                if len(chunk) > 512_000:
                    await _ws_send(
                        websocket,
                        {"type": "error", "message": "Audio frame too large (max 512 KB)"},
                    )
                    continue

                # Ensure model is loaded before first decode
                if not model_ready:
                    try:
                        if warm_task is not None:
                            await warm_task
                        else:
                            await asyncio.to_thread(warmup_model)
                        model_ready = True
                    except Exception as e:
                        await _ws_send(
                            websocket,
                            {"type": "error", "message": f"STT engine unavailable: {e}"},
                        )
                        continue

                try:
                    result = await session.add_audio(chunk)
                except Exception as e:
                    logger.warning("chunk process error: %s", e)
                    await _ws_send(
                        websocket,
                        {"type": "error", "message": f"Audio decode failed: {e}"},
                    )
                    continue

                if result:
                    await _ws_send(websocket, result.to_dict())
                continue

            # --- text control ---
            text = message.get("text")
            if text is None:
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                await _ws_send(
                    websocket,
                    {"type": "error", "message": "Invalid JSON control message"},
                )
                continue

            msg_type = (data.get("type") or "").lower()

            if msg_type == "ping":
                await _ws_send(websocket, {"type": "pong"})
                continue

            # Already authenticated via query or pre-ready handshake
            if msg_type == "auth":
                continue

            if msg_type == "warmup":
                if not model_ready:
                    try:
                        if warm_task is not None:
                            await warm_task
                        else:
                            await asyncio.to_thread(warmup_model)
                        model_ready = True
                    except Exception as e:
                        await _ws_send(
                            websocket,
                            {"type": "error", "message": f"STT engine unavailable: {e}"},
                        )
                else:
                    await _ws_send(
                        websocket,
                        {"type": "status", "message": "model_ready", **model_info()},
                    )
                continue

            if msg_type == "config":
                new_fmt = (data.get("format") or fmt).lower()
                if new_fmt in {"pcm", "wav", "webm", "ogg", "mp3", "m4a"}:
                    session.format = new_fmt  # type: ignore[assignment]
                    fmt = new_fmt
                if data.get("language"):
                    session.language = str(data["language"])[:8]
                if data.get("prompt"):
                    session.initial_prompt = str(data["prompt"])[:800]
                await _ws_send(
                    websocket,
                    {
                        "type": "status",
                        "message": "config updated",
                        "format": session.format,
                        "language": session.language,
                    },
                )
                continue

            if msg_type == "reset":
                session.reset()
                await _ws_send(
                    websocket, {"type": "status", "message": "buffer cleared"}
                )
                continue

            if msg_type in {"end", "stop", "finalize"}:
                try:
                    final = await session.finalize()
                except Exception as e:
                    logger.exception("finalize failed")
                    await _ws_send(
                        websocket,
                        {"type": "error", "message": f"Final transcription failed: {e}"},
                    )
                    continue

                if final:
                    await _ws_send(websocket, final.to_dict())
                else:
                    await _ws_send(
                        websocket,
                        {
                            "type": "final",
                            "text": "",
                            "full_text": "",
                            "is_final": True,
                            "message": "No speech detected",
                        },
                    )
                continue

            if msg_type == "close":
                break

            await _ws_send(
                websocket,
                {
                    "type": "error",
                    "message": f"Unknown control type: {msg_type}",
                },
            )

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
        if warm_task is not None and not warm_task.done():
            warm_task.cancel()
        session.close()
        async with _active_ws_lock:
            _active_ws = max(0, _active_ws - 1)
