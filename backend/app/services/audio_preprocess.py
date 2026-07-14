"""
Fast audio preprocessing for short interview chunks.

Strategy (speed-first, quality-good-enough):
  1) Already-clean client WAV (16 kHz mono PCM) → pure-Python trim + peak normalize (~ms)
  2) Other formats → lightweight ffmpeg convert only (no heavy dynaudnorm / multi-pass silence)

Heavy filters like dynaudnorm are intentionally avoided — they dominated latency.
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from functools import lru_cache


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _write_temp(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _safe_unlink(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


def _is_pcm_wav_16k_mono(audio_bytes: bytes) -> bool:
    """True if bytes look like 16-bit PCM WAV @ 16 kHz mono (what our frontend sends)."""
    if len(audio_bytes) < 44:
        return False
    if audio_bytes[0:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return False
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            return (
                wf.getnchannels() == 1
                and wf.getsampwidth() == 2
                and wf.getframerate() == 16000
                and wf.getcomptype() == "NONE"
            )
    except Exception:
        return False


def preprocess_with_ffmpeg_fast(audio_bytes: bytes, input_suffix: str = ".wav") -> bytes | None:
    """
    Minimal ffmpeg path: mono 16 kHz PCM only.
    No dynaudnorm / multi-pass silenceremove (those were the bottleneck).
    """
    ff = ffmpeg_path()
    if not ff:
        return None

    in_path = _write_temp(
        audio_bytes, input_suffix if input_suffix.startswith(".") else f".{input_suffix}"
    )
    out_path = in_path + ".out.wav"

    # Light highpass only; volume normalize with volume= filter is cheap
    cmd = [
        ff,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        in_path,
        "-af",
        "highpass=f=80,volume=1.5",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        "-threads",
        "1",
        out_path,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=8, check=False)
        if proc.returncode != 0 or not os.path.exists(out_path):
            return None
        out = _read_file(out_path)
        if len(out) < 1500:
            return None
        return out
    except Exception as e:
        print(f"ffmpeg fast preprocess exception: {e}")
        return None
    finally:
        _safe_unlink(in_path, out_path)


def preprocess_wav_python(audio_bytes: bytes) -> bytes | None:
    """
    Pure-Python peak-normalize + edge silence trim for PCM WAV.
    Optimized for short 16 kHz mono interview segments (typically < 1s of work).
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth != 2 or n_frames == 0:
            return None

        total_samples = n_frames * n_channels
        try:
            unpacked = struct.unpack("<" + "h" * total_samples, raw[: total_samples * 2])
        except struct.error:
            return None

        if n_channels > 1:
            samples = [
                int(sum(unpacked[i : i + n_channels]) / n_channels)
                for i in range(0, len(unpacked), n_channels)
            ]
        else:
            samples = list(unpacked)

        target_rate = 16000
        if framerate != target_rate and framerate > 0:
            ratio = framerate / target_rate
            new_len = max(1, int(len(samples) / ratio))
            samples = [
                int(
                    samples[min(int(i * ratio), len(samples) - 1)] * (1 - (i * ratio % 1))
                    + samples[min(int(i * ratio) + 1, len(samples) - 1)] * (i * ratio % 1)
                )
                for i in range(new_len)
            ]
            framerate = target_rate

        if not samples:
            return None

        # Fast edge trim
        thresh = 350
        start = 0
        end = len(samples) - 1
        while start < len(samples) and abs(samples[start]) < thresh:
            start += 1
        while end > start and abs(samples[end]) < thresh:
            end -= 1

        pad = int(framerate * 0.03)
        start = max(0, start - pad)
        end = min(len(samples) - 1, end + pad)
        samples = samples[start : end + 1]
        if len(samples) < int(framerate * 0.15):
            return None

        peak = max((abs(s) for s in samples), default=0)
        if peak > 0:
            gain = min(0.90 * 32767.0 / peak, 8.0)
            samples = [int(max(-32767, min(32767, s * gain))) for s in samples]

        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        return out.getvalue()
    except Exception as e:
        print(f"python wav preprocess failed: {e}")
        return None


def preprocess_audio(audio_bytes: bytes, filename: str = "audio.wav") -> tuple[bytes, str, dict]:
    """
    Fast preprocess for Whisper.

    Returns: (processed_bytes, filename, meta)
    """
    meta = {
        "engine": "none",
        "original_size": len(audio_bytes or b""),
        "processed_size": len(audio_bytes or b""),
    }

    if not audio_bytes or len(audio_bytes) < 500:
        return audio_bytes, filename, meta

    ext = os.path.splitext(filename)[1].lower() or ".wav"
    if ext not in {".wav", ".webm", ".ogg", ".mp3", ".mp4", ".m4a", ".mpeg", ".mpga", ".flac"}:
        ext = ".wav"

    # Fast path: client already sends 16 kHz mono PCM WAV — skip ffmpeg entirely
    if _is_pcm_wav_16k_mono(audio_bytes):
        cleaned = preprocess_wav_python(audio_bytes)
        if cleaned:
            meta["engine"] = "python-fast"
            meta["processed_size"] = len(cleaned)
            return cleaned, "audio_clean.wav", meta
        # Even raw is fine for Whisper if already 16k mono
        meta["engine"] = "passthrough"
        return audio_bytes, "audio.wav", meta

    # Any WAV: pure python first
    if audio_bytes[:4] == b"RIFF" and len(audio_bytes) > 12 and audio_bytes[8:12] == b"WAVE":
        cleaned = preprocess_wav_python(audio_bytes)
        if cleaned:
            meta["engine"] = "python"
            meta["processed_size"] = len(cleaned)
            return cleaned, "audio_clean.wav", meta

    # Non-WAV / failed python: lightweight ffmpeg convert only
    cleaned = preprocess_with_ffmpeg_fast(audio_bytes, input_suffix=ext)
    if cleaned:
        meta["engine"] = "ffmpeg-fast"
        meta["processed_size"] = len(cleaned)
        return cleaned, "audio_clean.wav", meta

    return audio_bytes, filename, meta
