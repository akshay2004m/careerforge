"""
faster-whisper streaming STT for CareerForge mock interviews.

RTX 4050 profile
----------------
  model:        medium.en  (English interviews; override via WHISPER_MODEL)
  device:       cuda when available, else cpu
  compute_type: float16 on GPU, int8 on CPU

Anti-repetition streaming design
--------------------------------
  1. Rolling PCM window only (last ~5s) — never re-decode the whole answer.
  2. condition_on_previous_text=False always (stops "I am Akshay…" loops).
  3. Commit window text on silence / when window slides; live = committed + window.
  4. Do not call Whisper during silence (stops growth on pauses).
  5. finalize() re-decodes only the remaining window + merges committed (higher beam).
  6. Post-process: collapse repeated sentences / phrases.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ensure_cuda_dll_path() -> list[str]:
    """
    Prepend pip-installed NVIDIA CUDA 12 DLL dirs to PATH (Windows).

    Packages: nvidia-cublas-cu12, nvidia-cuda-runtime-cu12, nvidia-cudnn-cu12, …
    Without this, ctranslate2 fails with: Library cublas64_12.dll is not found.
    """
    added: list[str] = []
    try:
        import site
        from pathlib import Path

        candidates: list[Path] = []
        for sp in site.getsitepackages() + (
            [site.getusersitepackages()] if site.getusersitepackages() else []
        ):
            nvidia_root = Path(sp) / "nvidia"
            if not nvidia_root.is_dir():
                continue
            for sub in (
                "cublas",
                "cuda_runtime",
                "cudnn",
                "cuda_nvrtc",
                "cufft",
                "curand",
                "cusolver",
                "cusparse",
            ):
                bin_dir = nvidia_root / sub / "bin"
                if bin_dir.is_dir():
                    candidates.append(bin_dir)

        if not candidates:
            return added

        path_now = os.environ.get("PATH", "")
        parts = path_now.split(os.pathsep) if path_now else []
        # Prepend in reverse so cublas ends up first among nvidia bins
        for d in reversed(candidates):
            s = str(d)
            if s not in parts:
                parts.insert(0, s)
                added.append(s)
        os.environ["PATH"] = os.pathsep.join(parts)

        # Windows: also add DLL directories for the current process (Python 3.8+)
        if hasattr(os, "add_dll_directory"):
            for s in added:
                try:
                    os.add_dll_directory(s)
                except (OSError, FileNotFoundError):
                    pass

        if added:
            logger.info("Added %d NVIDIA CUDA DLL dir(s) to PATH", len(added))
    except Exception as e:
        logger.debug("CUDA DLL path setup skipped: %s", e)
    return added


# Run as early as possible (before ctranslate2 loads CUDA libs)
_ensure_cuda_dll_path()

# ---------------------------------------------------------------------------
# Interview prompt — SHORT. Long prompts leak into transcripts ("Indian English accent").
# Used only on finalize / first decode, never as ongoing condition text.
# ---------------------------------------------------------------------------

INTERVIEW_PROMPT = (
    "Job interview. The candidate introduces themselves and answers technical questions. "
    "Common names: Akshay, Nellore, Hyderabad, Bengaluru, Chennai, Mumbai. "
    "Vocabulary: Python, React, JavaScript, TypeScript, API, REST, SQL, Docker, AWS, "
    "Kubernetes, system design, authentication, database, microservice, full-stack, "
    "backend, frontend, machine learning, data science, resume, experience, project."
)

SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2
# 16 kHz mono s16le ≈ 32_000 bytes/s
BYTES_PER_SECOND = SAMPLE_RATE * BYTES_PER_SAMPLE

# Rolling window: ONLY this much recent audio is ever sent to Whisper
# 8s gives Whisper more context per decode → much better accuracy for names/accents
ROLLING_WINDOW_SECONDS = 8.0
ROLLING_WINDOW_BYTES = int(BYTES_PER_SECOND * ROLLING_WINDOW_SECONDS)
# Need this much audio before first / next decode
MIN_DECODE_SECONDS = 1.5
MIN_DECODE_BYTES = int(BYTES_PER_SECOND * MIN_DECODE_SECONDS)
# Min *new* audio between live decodes (stops thrashing)
DECODE_STRIDE_SECONDS = 1.5
DECODE_STRIDE_BYTES = int(BYTES_PER_SECOND * DECODE_STRIDE_SECONDS)
# Silence: after this many consecutive low-RMS chunks, commit window + clear buffer
SILENCE_COMMIT_SECONDS = 1.1
SILENCE_COMMIT_BYTES = int(BYTES_PER_SECOND * SILENCE_COMMIT_SECONDS)
MIN_FINAL_SECONDS = 0.4
# Energy gates (int16 RMS)
SILENCE_RMS = 320
SPEECH_RMS = 480
# Text gates
MIN_PARTIAL_CHARS = 6
MIN_PARTIAL_WORDS = 2
MIN_FINAL_CHARS = 2

# Mild highpass only — lowpass kills consonants
_VOICE_AF = "highpass=f=80,volume=1.5"

_HALLUCINATION_RE = re.compile(
    r"^\s*("
    r"thank you\.?|thanks for watching\.?|subscribe\.?|please subscribe\.?|"
    r"music|\[music\]|\(music\)|you\s*|bye\.?|cheers!?|"
    r"the speaker may have an indian english accent\.?|"
    r"this is a professional technical job interview.*|"
    r"technical interview answer\.?|"
    r"uh+|um+|ah+|hmm+|yeah\.?|yes\.?|no\.?|ok\.?|okay\.?|"
    r"say hi\.?|hello\.?|hi\.?|easy\.?"
    r")\s*$",
    re.I,
)

_PROMPT_LEAK_RE = re.compile(
    r"(the speaker may have an indian english accent|"
    r"this is a professional technical job interview|"
    r"technical interview answer|"
    r"common terms:|"
    r"vocabulary:)",
    re.I,
)


# ---------------------------------------------------------------------------
# Device / model
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_model = None
_model_meta: dict[str, Any] = {}


@lru_cache(maxsize=1)
def ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")


def cuda_available() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count() or 0) > 0
    except Exception as e:
        logger.error(f"CUDA check (ctranslate2) failed: {str(e)}", exc_info=True)
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception as e:
        logger.error(f"CUDA check (torch) failed: {str(e)}", exc_info=True)
        return False


def resolve_runtime() -> dict[str, str]:
    """Resolve model/device/compute from settings + hardware (RTX 4050 defaults)."""
    want_device = (settings.WHISPER_DEVICE or "auto").strip().lower()
    want_compute = (settings.WHISPER_COMPUTE_TYPE or "auto").strip().lower()
    model_size = (settings.WHISPER_MODEL or "medium.en").strip()
    has_cuda = cuda_available()

    if want_device in {"auto", "", "cuda"}:
        device = "cuda" if has_cuda else "cpu"
        if want_device == "cuda" and not has_cuda:
            logger.warning("WHISPER_DEVICE=cuda but no GPU found — using CPU")
    else:
        device = "cpu"

    if want_compute in {"auto", ""}:
        compute_type = "float16" if device == "cuda" else "int8"
    else:
        compute_type = want_compute
        if device == "cuda" and compute_type == "int8":
            compute_type = "float16"
        if device == "cpu" and compute_type == "float16":
            compute_type = "int8"

    # Auto CPU fallback: medium is heavy without GPU
    if (
        device == "cpu"
        and model_size in {"medium", "medium.en", "large-v2", "large-v3", "large"}
        and (settings.WHISPER_DEVICE or "auto").strip().lower() in {"auto", ""}
    ):
        logger.info("CPU mode: using small.en instead of %s", model_size)
        model_size = "small.en"

    return {"model": model_size, "device": device, "compute_type": compute_type}


def model_info() -> dict[str, Any]:
    runtime = (
        {
            "model": _model_meta.get("path", settings.WHISPER_MODEL),
            "device": _model_meta.get("device_resolved", settings.WHISPER_DEVICE),
            "compute_type": _model_meta.get("compute_type_resolved", settings.WHISPER_COMPUTE_TYPE),
        }
        if _model is not None
        else resolve_runtime()
    )
    return {
        "model": runtime.get("model"),
        "device": runtime.get("device"),
        "compute_type": runtime.get("compute_type"),
        "loaded": _model is not None,
        "cuda_available": cuda_available(),
        "ffmpeg": bool(ffmpeg_path()),
        **{k: v for k, v in _model_meta.items() if k in ("path", "device_resolved", "gpu_name")},
    }


def _is_cuda_runtime_error(err: BaseException) -> bool:
    """True for missing cuBLAS/cuDNN/CUDA driver errors at inference time."""
    msg = str(err).lower()
    needles = (
        "cublas",
        "cudnn",
        "cuda",
        "cublas64",
        "cudnn64",
        "nvrtc",
        "cannot be loaded",
        "library cublas",
        "no kernel image",
        "invalid device function",
        "cuda error",
    )
    return any(n in msg for n in needles)


def _build_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=settings.WHISPER_DOWNLOAD_DIR or None,
        cpu_threads=settings.WHISPER_CPU_THREADS or 0,
        num_workers=1,
    )


def _probe_cuda_inference(model) -> None:
    """
    Model construction can succeed even when cublas64_12.dll is missing.
    Run a tiny silent WAV through transcribe to force-load cuBLAS.
    """
    import struct
    import wave

    # ~0.4 s of near-silence @ 16 kHz mono
    n = 6400
    pcm = struct.pack("<" + "h" * n, *([0] * n))
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16_000)
            wf.writeframes(pcm)
        segments, _info = model.transcribe(
            path,
            language="en",
            beam_size=1,
            vad_filter=False,
            temperature=0.0,
        )
        # Force generator consumption (inference runs here)
        _ = list(segments)
    finally:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _load_cpu_fallback(model_size: str, reason: str):
    """Load CPU/int8 model (prefer small.en if medium was requested)."""
    global _model, _model_meta
    compute_type = "int8"
    device = "cpu"
    if model_size in {"medium", "medium.en", "large-v2", "large-v3", "large"}:
        # medium on CPU is very slow for live captions
        logger.warning(
            "Falling back to CPU: using small.en instead of %s (%s)",
            model_size,
            reason,
        )
        model_size = "small.en"
    else:
        logger.warning("Falling back to CPU/int8 (%s)", reason)

    print(f"[STT] CUDA unusable ({reason}). Loading {model_size} on CPU (int8)…")
    _model = _build_whisper_model(model_size, device, compute_type)
    _model_meta = {
        "path": model_size,
        "device_resolved": device,
        "compute_type_resolved": compute_type,
        "gpu_name": None,
        "fallback_reason": reason[:300],
    }
    print(f"[STT] Model loaded on CPU: {model_size} (int8)")
    logger.info("faster-whisper ready (CPU fallback): %s", _model_meta)
    return _model


def get_whisper_model():
    """Lazy-load singleton WhisperModel (CUDA float16 on RTX 4050 when available)."""
    global _model, _model_meta
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from e

        runtime = resolve_runtime()
        model_size = runtime["model"]
        device = runtime["device"]
        compute_type = runtime["compute_type"]

        # Explicit force-CPU via env (set WHISPER_DEVICE=cpu)
        if (settings.WHISPER_DEVICE or "").strip().lower() == "cpu":
            device = "cpu"
            compute_type = "int8"

        gpu_name = None
        if device == "cuda":
            try:
                import torch

                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
            except Exception as e:
                logger.error(f"Failed to get CUDA device name: {str(e)}", exc_info=True)
                gpu_name = "cuda:0"

        msg = f"[STT] Loading faster-whisper: {model_size} on {device.upper()} ({compute_type})" + (
            f" — {gpu_name}" if gpu_name else ""
        )
        print(msg)
        logger.info(msg)

        if device == "cpu":
            _model = _build_whisper_model(model_size, "cpu", "int8")
            _model_meta = {
                "path": model_size,
                "device_resolved": "cpu",
                "compute_type_resolved": "int8",
                "gpu_name": None,
            }
            print(f"[STT] Model loaded on CPU: {model_size} (int8)")
            return _model

        # --- CUDA path with real inference probe (catches missing cublas64_12.dll) ---
        try:
            candidate = _build_whisper_model(model_size, device, compute_type)
            print("[STT] Probing CUDA inference (cuBLAS)…")
            _probe_cuda_inference(candidate)
            _model = candidate
            _model_meta = {
                "path": model_size,
                "device_resolved": device,
                "compute_type_resolved": compute_type,
                "gpu_name": gpu_name,
            }
            print(f"[STT] Model loaded on {device.upper()}: {model_size} ({compute_type})")
            logger.info("faster-whisper ready: %s", _model_meta)
            return _model
        except Exception as primary_err:
            reason = str(primary_err)
            if _is_cuda_runtime_error(primary_err) or device == "cuda":
                return _load_cpu_fallback(model_size, reason)
            raise


def force_cpu_model(reason: str = "runtime CUDA failure") -> Any:
    """Drop CUDA model and reload on CPU (thread-safe). Used after mid-session cublas errors."""
    global _model, _model_meta
    with _model_lock:
        prev = (_model_meta.get("path") if _model_meta else None) or (
            settings.WHISPER_MODEL or "medium.en"
        )
        _model = None
        _model_meta = {}
        return _load_cpu_fallback(str(prev), reason)


def warmup_model() -> dict[str, Any]:
    get_whisper_model()
    return model_info()


# ---------------------------------------------------------------------------
# Audio: WebM/… → 16 kHz mono WAV (ffmpeg-python pipes)
# ---------------------------------------------------------------------------


def convert_to_wav(audio_bytes: bytes, input_format: str = "webm") -> bytes:
    """
    Convert browser audio to clean 16 kHz mono PCM WAV.

        ffmpeg -i pipe:0 -af highpass=f=200,lowpass=f=3000,volume=2.0
               -acodec pcm_s16le -ac 1 -ar 16000 pipe:1
    """
    if not audio_bytes or len(audio_bytes) < 64:
        return audio_bytes or b""

    fmt = (input_format or "webm").lower().lstrip(".")
    if fmt == "wave":
        fmt = "wav"

    # Raw PCM from our frontend — wrap as WAV (no re-encode needed)
    if fmt == "pcm":
        return _pcm_to_wav(audio_bytes if len(audio_bytes) % 2 == 0 else audio_bytes[:-1])

    try:
        import ffmpeg as ffmpeg_py
    except ImportError:
        return _ffmpeg_cli_convert(audio_bytes, fmt)

    if not ffmpeg_path():
        print("FFmpeg conversion error: ffmpeg binary not on PATH")
        return audio_bytes

    try:
        # Already WAV with RIFF header — still run through voice filters
        in_fmt = (
            "wav"
            if (fmt == "wav" or (audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"))
            else fmt
        )

        process = (
            ffmpeg_py.input("pipe:0", format=in_fmt)
            .output(
                "pipe:1",
                format="wav",
                acodec="pcm_s16le",
                ac=1,
                ar="16000",
                af=_VOICE_AF,
                loglevel="error",
            )
            .overwrite_output()
            .run(
                input=audio_bytes,
                capture_stdout=True,
                capture_stderr=True,
                quiet=True,
            )
        )
        out = process[0]
        return out if out else audio_bytes
    except Exception as e:
        print(f"FFmpeg conversion error: {e}")
        logger.warning("FFmpeg conversion error: %s", e)
        try:
            return _ffmpeg_cli_convert(audio_bytes, fmt)
        except Exception as e2:
            print(f"FFmpeg CLI fallback error: {e2}")
            return audio_bytes


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16_000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _ffmpeg_cli_convert(audio_bytes: bytes, fmt: str) -> bytes:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg not found on PATH")

    in_path = out_path = None
    try:
        fd, in_path = tempfile.mkstemp(suffix=f".{fmt}")
        os.close(fd)
        with open(in_path, "wb") as f:
            f.write(audio_bytes)
        fd2, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd2)
        import subprocess

        proc = subprocess.run(
            [
                ff,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                in_path,
                "-af",
                _VOICE_AF,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                out_path,
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[:400])
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def dedupe_repeated_phrases(text: str) -> str:
    """
    Collapse repetition loops like:
      "I am Akshay. I am Akshay. I am Akshay have done..."
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip())

    # Exact consecutive sentence / clause repeats
    parts = re.split(r"(?<=[.!?])\s+|\s*[;]\s*", text)
    cleaned: list[str] = []
    prev_norm = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        norm = re.sub(r"[^a-z0-9\s]", "", p.lower()).strip()
        if norm and norm == prev_norm:
            continue
        # Also skip if this chunk is fully contained in previous (bleeding)
        if prev_norm and norm in prev_norm and len(norm) > 12:
            continue
        if prev_norm and prev_norm in norm and len(prev_norm) > 12:
            # Prefer longer version; replace last
            cleaned[-1] = p
            prev_norm = norm
            continue
        cleaned.append(p)
        prev_norm = norm
    text = " ".join(cleaned)

    # Collapse immediate repeated word sequences (up to 6-grams), twice
    for n in range(6, 1, -1):
        pattern = re.compile(
            rf"\b((?:\w+\s+){{{n - 1}}}\w+)(?:\s+\1){{1,}}\b",
            re.I,
        )
        text = pattern.sub(r"\1", text)

    # Single-word triple+
    text = re.sub(r"\b(\w+)(?:\s+\1){2,}\b", r"\1", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def clean_transcript(text: str, *, is_final: bool = False) -> str:
    """Normalize text and drop Whisper hallucinations / prompt leaks / loops."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip())
    text = _PROMPT_LEAK_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-")
    if not text:
        return ""
    if _HALLUCINATION_RE.match(text):
        return ""
    text = dedupe_repeated_phrases(text)
    words = [w for w in text.split() if w]
    if not is_final:
        if len(text) < MIN_PARTIAL_CHARS or len(words) < MIN_PARTIAL_WORDS:
            return ""
    elif len(text) < MIN_FINAL_CHARS:
        return ""
    return text.strip()


def merge_committed_and_window(committed: str, window: str) -> str:
    """
    Join locked-in text + current rolling-window text without doubling.
    """
    committed = (committed or "").strip()
    window = (window or "").strip()
    if not committed:
        return window
    if not window:
        return committed

    c_low = committed.lower()
    w_low = window.lower()
    # Window already contains committed (rare)
    if w_low.startswith(c_low) or c_low in w_low:
        return dedupe_repeated_phrases(window if len(window) >= len(committed) else committed)

    # Overlap suffix/prefix (window re-heard end of committed)
    max_k = min(len(committed), len(window), 80)
    for k in range(max_k, 8, -1):
        if c_low.endswith(w_low[:k]):
            return dedupe_repeated_phrases(committed + " " + window[k:]).strip()
        if w_low.startswith(c_low[-k:]):
            return dedupe_repeated_phrases(committed + " " + window[k:]).strip()

    # If window is almost entirely already in committed, ignore
    w_words = w_low.split()
    if len(w_words) >= 3:
        # count how many bigrams already present
        hits = 0
        total = 0
        for i in range(len(w_words) - 1):
            bg = f"{w_words[i]} {w_words[i + 1]}"
            total += 1
            if bg in c_low:
                hits += 1
        if total and hits / total > 0.7:
            return committed

    return dedupe_repeated_phrases(f"{committed} {window}")


def pcm_rms(pcm: bytes) -> float:
    """RMS of int16 mono PCM (last ~0.5s for silence checks)."""
    import struct

    if len(pcm) < 4:
        return 0.0
    n = len(pcm) // 2
    tail = min(n, int(SAMPLE_RATE * 0.5))
    start = (n - tail) * 2
    samples = struct.unpack("<" + "h" * tail, pcm[start : start + tail * 2])
    acc = 0.0
    for s in samples:
        acc += float(s) * float(s)
    return (acc / tail) ** 0.5


def pcm_duration_s(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    return len(pcm) / float(BYTES_PER_SECOND)


# ---------------------------------------------------------------------------
# Core engine — rolling window (anti-repetition)
# ---------------------------------------------------------------------------


class FasterWhisperStreaming:
    """
    Near real-time captions without repetition loops.

    - ``audio_buffer``: only the last ~5s of PCM (rolling)
    - ``committed_text``: finalized segments (silence / window slide)
    - ``window_text``: latest transcription of the rolling buffer only
    - Live caption = merge(committed, window)
    - condition_on_previous_text=False always
    """

    def __init__(
        self,
        *,
        format: Literal["pcm", "wav", "webm", "ogg", "mp3", "m4a"] = "webm",
        language: str = "en",
        initial_prompt: str = INTERVIEW_PROMPT,
    ) -> None:
        self.model = None
        self.format = format
        self.language = language
        self.initial_prompt = initial_prompt

        self.audio_buffer = b""
        self.committed_text = ""
        self.window_text = ""
        self.last_transcript = ""  # full display text (committed + window)
        self._bytes_since_decode = 0
        self._silent_bytes = 0
        self._transcribing = False

    def process_audio_chunk(self, audio_chunk: bytes) -> dict[str, Any]:
        try:
            if not audio_chunk:
                return {"type": "none", "text": self.last_transcript}

            pcm_piece = self._chunk_to_pcm(audio_chunk)
            if not pcm_piece:
                return {"type": "none", "text": self.last_transcript}

            self.audio_buffer += pcm_piece
            self._bytes_since_decode += len(pcm_piece)

            # --- Rolling window: discard old audio (stops full-history re-decode) ---
            if len(self.audio_buffer) > ROLLING_WINDOW_BYTES:
                # Promote current window text into committed before dropping audio
                self._commit_window_text()
                self.audio_buffer = self.audio_buffer[-ROLLING_WINDOW_BYTES:]
                # Keep a little stride credit so we don't immediately re-decode
                self._bytes_since_decode = min(self._bytes_since_decode, DECODE_STRIDE_BYTES // 2)

            chunk_rms = pcm_rms(pcm_piece)
            # --- Silence: do NOT grow transcript; optionally commit & clear ---
            if chunk_rms < SILENCE_RMS:
                self._silent_bytes += len(pcm_piece)
                if self._silent_bytes >= SILENCE_COMMIT_BYTES:
                    changed = self._commit_window_text()
                    # Clear rolling buffer on pause so we don't re-transcribe old speech
                    self.audio_buffer = b""
                    self.window_text = ""
                    self._bytes_since_decode = 0
                    self._silent_bytes = 0
                    self.last_transcript = dedupe_repeated_phrases(self.committed_text)
                    if changed:
                        return {
                            "type": "partial",
                            "text": self.last_transcript,
                            "full_text": self.last_transcript,
                            "is_final": False,
                        }
                return {"type": "none", "text": self.last_transcript}

            self._silent_bytes = 0

            # Need enough speech energy in the whole window
            if pcm_rms(self.audio_buffer) < SPEECH_RMS:
                return {"type": "none", "text": self.last_transcript}

            if len(self.audio_buffer) < MIN_DECODE_BYTES:
                return {"type": "none", "text": self.last_transcript}
            if self._bytes_since_decode < DECODE_STRIDE_BYTES and self.window_text:
                return {"type": "none", "text": self.last_transcript}
            if self._transcribing:
                return {"type": "none", "text": self.last_transcript}

            # --- Decode ONLY the rolling window ---
            self._transcribing = True
            try:
                window = self._transcribe_pcm(self.audio_buffer, is_final=False)
            finally:
                self._transcribing = False

            self._bytes_since_decode = 0

            if not window:
                return {"type": "none", "text": self.last_transcript}

            # Don't replace a good window with near-identical / shorter noise
            if self.window_text:
                if window == self.window_text:
                    return {"type": "none", "text": self.last_transcript}
                # Reject if new window is mostly a prefix repeat of old
                if (
                    window.lower() in self.window_text.lower()
                    and len(window) < len(self.window_text) * 0.9
                ):
                    return {"type": "none", "text": self.last_transcript}

            self.window_text = window
            full = merge_committed_and_window(self.committed_text, self.window_text)
            full = dedupe_repeated_phrases(full)
            if full == self.last_transcript:
                return {"type": "none", "text": self.last_transcript}

            self.last_transcript = full
            return {
                "type": "partial",
                "text": full,
                "full_text": full,
                "is_final": False,
                "duration_s": round(pcm_duration_s(self.audio_buffer), 3),
            }

        except Exception as e:
            print(f"faster-whisper error: {e}")
            logger.exception("faster-whisper error")
            return {"type": "error", "text": str(e), "message": str(e)}

    def finalize(self) -> dict[str, Any]:
        """
        User clicked Stop: decode remaining rolling buffer with higher beam,
        merge into committed, heavy dedupe, reset.
        """
        try:
            import time

            for _ in range(50):
                if not self._transcribing:
                    break
                time.sleep(0.05)

            final_window = ""
            if self.audio_buffer and pcm_duration_s(self.audio_buffer) >= MIN_FINAL_SECONDS:
                if pcm_rms(self.audio_buffer) >= SILENCE_RMS:
                    self._transcribing = True
                    try:
                        final_window = self._transcribe_pcm(self.audio_buffer, is_final=True)
                    finally:
                        self._transcribing = False

            if final_window:
                self.window_text = final_window
            self._commit_window_text()
            text = dedupe_repeated_phrases(
                clean_transcript(self.committed_text, is_final=True)
                or clean_transcript(self.last_transcript, is_final=True)
            )
            self.reset()
            return {
                "type": "final",
                "text": text or "",
                "full_text": text or "",
                "is_final": True,
                "message": None if text else "No speech detected",
            }
        except Exception as e:
            print(f"faster-whisper error: {e}")
            text = self.last_transcript
            self.reset()
            return {
                "type": "error",
                "text": str(e),
                "full_text": text,
                "is_final": True,
                "message": str(e),
            }

    def reset(self) -> None:
        self.audio_buffer = b""
        self.committed_text = ""
        self.window_text = ""
        self.last_transcript = ""
        self._bytes_since_decode = 0
        self._silent_bytes = 0
        self._transcribing = False

    def close(self) -> None:
        self.reset()

    # --- internals ----------------------------------------------------------

    def _commit_window_text(self) -> bool:
        """Lock current window text into committed; return True if committed grew."""
        w = (self.window_text or "").strip()
        if not w:
            return False
        before = self.committed_text
        self.committed_text = merge_committed_and_window(self.committed_text, w)
        self.committed_text = dedupe_repeated_phrases(self.committed_text)
        self.window_text = ""
        self.last_transcript = self.committed_text
        return self.committed_text != before

    def _chunk_to_pcm(self, audio_chunk: bytes) -> bytes:
        if self.format == "pcm":
            return audio_chunk if len(audio_chunk) % 2 == 0 else audio_chunk[:-1]

        if self.format == "wav" or (audio_chunk[:4] == b"RIFF" and audio_chunk[8:12] == b"WAVE"):
            try:
                return _wav_to_pcm(audio_chunk)
            except Exception as e:
                logger.error(f"WAV parsing error during fast path: {str(e)}", exc_info=True)
                wav = convert_to_wav(audio_chunk, "wav")
                if wav[:4] == b"RIFF":
                    try:
                        return _wav_to_pcm(wav)
                    except Exception as e2:
                        logger.error(
                            f"WAV to PCM conversion failed after ffmpeg fallback: {str(e2)}",
                            exc_info=True,
                        )
                        return b""
                return b""

        wav = convert_to_wav(audio_chunk, self.format)
        if wav[:4] == b"RIFF":
            try:
                return _wav_to_pcm(wav)
            except Exception as e:
                logger.error(f"Final WAV to PCM conversion failed: {str(e)}", exc_info=True)
                return b""
        return b""

    def _transcribe_pcm(self, pcm: bytes, *, is_final: bool) -> str:
        """
        Transcribe a short PCM slice.
        Always: condition_on_previous_text=False (critical anti-loop fix).
        """
        self.model = get_whisper_model()
        if not pcm or len(pcm) < int(BYTES_PER_SECOND * 0.35):
            return ""

        wav_bytes = _pcm_to_wav(pcm if len(pcm) % 2 == 0 else pcm[:-1])
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                tmp_path = tmp.name

            on_gpu = (_model_meta.get("device_resolved") or "cpu") == "cuda"
            if is_final:
                beam = max(1, int(settings.WHISPER_BEAM_SIZE or (5 if on_gpu else 3)))
                best_of = min(5, max(1, beam))
            else:
                # beam=2 on GPU gives much better accuracy for names/accents
                # with negligible latency cost on RTX 4050
                beam = 2 if on_gpu else 1
                best_of = 1

            # Always provide the interview prompt so Whisper knows the vocabulary
            # (names, tech terms). This is the #1 fix for "Akshay" → "Shai" errors.
            use_prompt = self.initial_prompt

            def _run(model):
                segments, _info = model.transcribe(
                    tmp_path,
                    language=self.language or "en",
                    task="transcribe",
                    beam_size=beam,
                    best_of=best_of,
                    patience=1.0,
                    temperature=0.0,
                    # Critical: False stops prompt / prior text from being repeated
                    condition_on_previous_text=False,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=700 if is_final else 500,
                        speech_pad_ms=200,
                        threshold=0.5,
                    ),
                    # Reject no-speech / low-confidence junk harder
                    no_speech_threshold=0.6 if is_final else 0.55,
                    compression_ratio_threshold=2.2,
                    log_prob_threshold=-0.8,
                    initial_prompt=use_prompt,
                    word_timestamps=False,
                    without_timestamps=True,
                )
                parts: list[str] = []
                for seg in segments:
                    # Drop segments Whisper itself marks as likely non-speech
                    if getattr(seg, "no_speech_prob", 0) and float(seg.no_speech_prob) > 0.7:
                        continue
                    t = (seg.text or "").strip()
                    if t:
                        parts.append(t)
                return " ".join(parts).strip()

            try:
                raw = _run(self.model)
            except Exception as infer_err:
                if _is_cuda_runtime_error(infer_err):
                    print(f"[STT] CUDA inference failed ({infer_err}). Switching to CPU…")
                    self.model = force_cpu_model(str(infer_err))
                    raw = _run(self.model)
                else:
                    raise

            return clean_transcript(raw, is_final=is_final)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    import io
    import wave

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
    if width != 2:
        raise ValueError(f"unsupported width {width}")
    if channels > 1:
        import struct

        n = len(frames) // 2
        samples = struct.unpack("<" + "h" * n, frames)
        mono = [int(sum(samples[i : i + channels]) / channels) for i in range(0, n, channels)]
        frames = struct.pack("<" + "h" * len(mono), *mono)
    if rate != 16_000 and rate > 0:
        # crude downsample
        import struct

        n = len(frames) // 2
        samples = struct.unpack("<" + "h" * n, frames)
        ratio = rate / 16_000
        new_n = max(1, int(n / ratio))
        out = []
        for i in range(new_n):
            src = i * ratio
            i0 = int(src)
            i1 = min(i0 + 1, n - 1)
            t = src - i0
            out.append(int(samples[i0] * (1 - t) + samples[i1] * t))
        frames = struct.pack("<" + "h" * len(out), *out)
    return frames


# ---------------------------------------------------------------------------
# Async WebSocket adapter (used by routers/interview.py)
# ---------------------------------------------------------------------------


@dataclass
class TranscriptResult:
    kind: Literal["partial", "final"]
    text: str
    full_text: str
    is_final: bool
    confidence: Optional[float] = None
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "text": self.text,
            "full_text": self.full_text,
            "is_final": self.is_final,
            "confidence": self.confidence,
            "duration_s": round(self.duration_s, 3),
        }


class StreamingSession:
    """
    Thin async wrapper around FasterWhisperStreaming for the WebSocket route.

    Maps engine events:
      partial / final(live) → WebSocket partial  (caption still updating)
      finalize()            → WebSocket final
      none                  → None (don't send)
    """

    def __init__(
        self,
        format: Literal["pcm", "wav", "webm", "ogg", "mp3", "m4a"] = "pcm",
        language: str = "en",
        initial_prompt: str = INTERVIEW_PROMPT,
    ) -> None:
        self.format = format
        self.language = language
        self.initial_prompt = initial_prompt
        self._engine = FasterWhisperStreaming(
            format=format,
            language=language,
            initial_prompt=initial_prompt,
        )
        self._closed = False

    def reset(self) -> None:
        self._engine.reset()

    def close(self) -> None:
        self._closed = True
        self._engine.close()

    async def add_audio(self, data: bytes) -> Optional[TranscriptResult]:
        if self._closed or not data:
            return None
        result = await asyncio.to_thread(self._engine.process_audio_chunk, data)
        rtype = (result.get("type") or "none").lower()
        if rtype in {"none", "skip", "silence"}:
            return None
        if rtype == "error":
            raise RuntimeError(result.get("message") or result.get("text") or "STT error")
        text = (result.get("text") or result.get("full_text") or "").strip()
        if not text:
            return None
        # Live updates: full rolling transcript of the utterance so far
        return TranscriptResult(
            kind="partial",
            text=text,
            full_text=text,
            is_final=False,
            duration_s=float(result.get("duration_s") or 0),
        )

    async def finalize(self) -> Optional[TranscriptResult]:
        if self._closed:
            return None
        result = await asyncio.to_thread(self._engine.finalize)
        text = (result.get("text") or result.get("full_text") or "").strip()
        if result.get("type") == "error" and not text:
            raise RuntimeError(result.get("message") or result.get("text") or "STT error")
        if not text:
            return None
        return TranscriptResult(
            kind="final",
            text=text,
            full_text=text,
            is_final=True,
            duration_s=float(result.get("duration_s") or 0),
        )


# ---------------------------------------------------------------------------
# HTTP one-shot
# ---------------------------------------------------------------------------


def transcribe_bytes(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    *,
    language: str = "en",
) -> dict[str, Any]:
    ext = os.path.splitext(filename)[1].lower().lstrip(".") or "webm"
    if ext == "wave":
        ext = "wav"
    fmt = ext if ext in {"pcm", "wav", "webm", "ogg", "mp3", "m4a"} else "webm"
    engine = FasterWhisperStreaming(format=fmt, language=language)  # type: ignore[arg-type]
    engine.process_audio_chunk(audio_bytes)
    out = engine.finalize()
    out["model"] = model_info()
    return out
