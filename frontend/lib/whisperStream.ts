/**
 * Near real-time STT client for CareerForge mock interviews.
 *
 * Streams 16 kHz mono PCM16 LE over WebSocket to
 *   /api/interview/ws/transcribe?token=…&format=pcm
 * and surfaces partial + final transcripts.
 */

import { getApiBase } from "@/lib/api";

export type SttMessage =
  | {
      type: "ready";
      message?: string;
      model?: string;
      format?: string;
      sample_rate?: number;
      [key: string]: unknown;
    }
  | {
      type: "partial" | "final";
      text: string;
      full_text?: string;
      is_final?: boolean;
      confidence?: number | null;
      duration_s?: number;
      message?: string;
    }
  | { type: "error"; message: string }
  | { type: "status"; message: string; [key: string]: unknown }
  | { type: "pong" };

export type WhisperStreamHandlers = {
  onPartial?: (text: string, full: string) => void;
  onFinal?: (text: string, full: string) => void;
  onReady?: (info: SttMessage) => void;
  onError?: (message: string) => void;
  onStatus?: (message: string) => void;
  onLevel?: (rms: number) => void;
};

export type WhisperStreamSession = {
  readonly active: boolean;
  stop: () => Promise<string>;
  abort: () => void;
  getLevel: () => number;
};

const TARGET_RATE = 16_000;
// Larger frames = fewer WS messages; backend already buffers ~3s before partials
const FRAME_MS = 400;

/** Align loopback host with the page (localhost vs 127.0.0.1) to avoid rare browser WS quirks. */
function resolveHttpBase(): string {
  let base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
    getApiBase() ||
    "http://127.0.0.1:8000";

  if (typeof window !== "undefined") {
    try {
      const u = new URL(base);
      const pageHost = window.location.hostname;
      const loopback = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
      if (loopback.has(u.hostname) && loopback.has(pageHost) && u.hostname !== pageHost) {
        u.hostname = pageHost === "::1" ? "127.0.0.1" : pageHost;
        base = u.origin;
      }
    } catch {
      /* keep base */
    }
  }
  return base.replace(/\/$/, "");
}

function httpToWs(httpBase: string): string {
  if (httpBase.startsWith("https://")) return "wss://" + httpBase.slice(8);
  if (httpBase.startsWith("http://")) return "ws://" + httpBase.slice(7);
  return httpBase;
}

function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

function downsample(
  input: Float32Array,
  inputRate: number,
  outputRate: number
): Float32Array {
  if (inputRate === outputRate) return input;
  if (inputRate <= 0 || input.length === 0) return input;
  const ratio = inputRate / outputRate;
  const newLen = Math.max(1, Math.round(input.length / ratio));
  const out = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const t = src - i0;
    out[i] = input[i0] * (1 - t) + input[i1] * t;
  }
  return out;
}

async function preflightBackend(httpBase: string): Promise<void> {
  try {
    const res = await fetch(`${httpBase}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      throw new Error(`Backend health returned HTTP ${res.status}`);
    }
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    throw new Error(
      `Backend not reachable at ${httpBase} (${detail}). ` +
        `Start it with: cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
    );
  }
}

/**
 * Open a live transcription session.
 * Requires a logged-in JWT in localStorage (`token`).
 */
export async function startWhisperStream(
  handlers: WhisperStreamHandlers = {}
): Promise<WhisperStreamSession> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (!token) {
    throw new Error("Please log in to use voice transcription.");
  }

  if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone is not available in this browser.");
  }

  const httpBase = resolveHttpBase();
  await preflightBackend(httpBase);

  const wsUrl =
    `${httpToWs(httpBase)}/api/interview/ws/transcribe` +
    `?token=${encodeURIComponent(token)}&format=pcm`;

  // Connect WS first (fail fast before mic permission if network is wrong)
  const ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";

  let active = true;
  let level = 0;
  let finalText = "";
  let finalResolve: ((t: string) => void) | null = null;
  let readyInfo: SttMessage | null = null;

  const readyPromise = new Promise<void>((resolve, reject) => {
    const t = window.setTimeout(() => {
      reject(
        new Error(
          `STT WebSocket timed out waiting for server ready at ${httpToWs(httpBase)}. ` +
            `Is uvicorn running on the port in NEXT_PUBLIC_API_URL?`
        )
      );
    }, 15_000);

    const fail = (msg: string) => {
      window.clearTimeout(t);
      reject(new Error(msg));
    };

    ws.onopen = () => {
      // Also send auth as first text frame (fallback if query token was stripped by a proxy)
      try {
        ws.send(JSON.stringify({ type: "auth", token }));
        ws.send(JSON.stringify({ type: "config", format: "pcm", language: "en" }));
      } catch {
        /* ignore */
      }
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      let msg: SttMessage;
      try {
        msg = JSON.parse(ev.data) as SttMessage;
      } catch {
        return;
      }

      if (msg.type === "ready") {
        readyInfo = msg;
        window.clearTimeout(t);
        handlers.onReady?.(msg);
        resolve();
        return;
      }

      if (msg.type === "error") {
        // Fatal only before ready; after ready surface via handler
        if (!readyInfo) {
          fail(msg.message || "STT authentication/connection failed");
          try {
            ws.close();
          } catch {
            /* ignore */
          }
          return;
        }
        handlers.onError?.(msg.message || "Transcription error");
        return;
      }

      if (msg.type === "partial") {
        const text = msg.full_text || msg.text || "";
        handlers.onPartial?.(msg.text || text, text);
        return;
      }

      if (msg.type === "final") {
        const text = (msg.full_text || msg.text || "").trim();
        finalText = text;
        handlers.onFinal?.(msg.text || text, text);
        if (finalResolve) {
          finalResolve(text);
          finalResolve = null;
        }
        return;
      }

      if (msg.type === "status") {
        handlers.onStatus?.(msg.message || "");
        return;
      }
    };

    ws.onerror = () => {
      if (readyInfo) {
        handlers.onError?.("WebSocket error during transcription");
        return;
      }
      fail(
        `Cannot open STT WebSocket at ${httpToWs(httpBase)}/api/interview/ws/transcribe. ` +
          `Backend HTTP is checked at ${httpBase} — if health works but WS fails, restart uvicorn with: ` +
          `uvicorn app.main:app --reload --host 127.0.0.1 --port ${new URL(httpBase).port || "8000"}`
      );
    };

    ws.onclose = (ev) => {
      active = false;
      if (!readyInfo) {
        fail(
          `STT WebSocket closed before ready (code ${ev.code}${ev.reason ? `: ${ev.reason}` : ""}). ` +
            (ev.code === 1008
              ? "Auth failed — log out and log in again."
              : `Confirm backend is on ${httpBase}.`)
        );
        return;
      }
      if (finalResolve) {
        finalResolve(finalText);
        finalResolve = null;
      }
    };
  });

  try {
    await readyPromise;
  } catch (e) {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
    throw e;
  }

  // Mic only after WS is ready
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
  } catch (e) {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
    throw new Error(
      e instanceof Error
        ? `Microphone permission failed: ${e.message}`
        : "Microphone permission denied"
    );
  }

  let audioContext: AudioContext | null = null;
  let processor: ScriptProcessorNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let mute: GainNode | null = null;
  let sendBuffer: Float32Array[] = [];
  let sendSamples = 0;
  const samplesPerFrame = Math.floor((TARGET_RATE * FRAME_MS) / 1000);

  const cleanupMedia = () => {
    try {
      processor?.disconnect();
      source?.disconnect();
      mute?.disconnect();
    } catch {
      /* ignore */
    }
    processor = null;
    source = null;
    mute = null;
    if (audioContext && audioContext.state !== "closed") {
      void audioContext.close();
    }
    audioContext = null;
    stream.getTracks().forEach((tr) => tr.stop());
  };

  // Keep message handler for partial/final (already set); update close for mid-session
  const prevClose = ws.onclose;
  ws.onclose = (ev) => {
    active = false;
    cleanupMedia();
    if (typeof prevClose === "function") {
      try {
        prevClose.call(ws, ev);
      } catch {
        /* ignore */
      }
    }
    if (finalResolve) {
      finalResolve(finalText);
      finalResolve = null;
    }
  };

  audioContext = new AudioContext();
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }
  source = audioContext.createMediaStreamSource(stream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);
  mute = audioContext.createGain();
  mute.gain.value = 0;

  processor.onaudioprocess = (event) => {
    if (!active || ws.readyState !== WebSocket.OPEN) return;

    const input = event.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    level = Math.sqrt(sum / input.length);
    handlers.onLevel?.(level);

    const down = downsample(
      new Float32Array(input),
      audioContext!.sampleRate,
      TARGET_RATE
    );
    sendBuffer.push(down);
    sendSamples += down.length;

    while (sendSamples >= samplesPerFrame) {
      const frame = new Float32Array(samplesPerFrame);
      let offset = 0;
      while (offset < samplesPerFrame && sendBuffer.length) {
        const head = sendBuffer[0];
        const need = samplesPerFrame - offset;
        if (head.length <= need) {
          frame.set(head, offset);
          offset += head.length;
          sendSamples -= head.length;
          sendBuffer.shift();
        } else {
          frame.set(head.subarray(0, need), offset);
          sendBuffer[0] = head.subarray(need);
          sendSamples -= need;
          offset += need;
        }
      }
      try {
        ws.send(floatTo16BitPCM(frame));
      } catch {
        /* socket closing */
      }
    }
  };

  source.connect(processor);
  processor.connect(mute);
  mute.connect(audioContext.destination);

  const stop = async (): Promise<string> => {
    if (!active && !finalResolve) return finalText;
    active = false;

    if (ws.readyState === WebSocket.OPEN && sendSamples > 0) {
      const total = sendSamples;
      const rest = new Float32Array(total);
      let offset = 0;
      for (const c of sendBuffer) {
        rest.set(c, offset);
        offset += c.length;
      }
      sendBuffer = [];
      sendSamples = 0;
      if (total > TARGET_RATE * 0.05) {
        try {
          ws.send(floatTo16BitPCM(rest));
        } catch {
          /* ignore */
        }
      }
    }

    cleanupMedia();

    if (ws.readyState !== WebSocket.OPEN) {
      return finalText;
    }

    const result = await new Promise<string>((resolve) => {
      finalResolve = resolve;
      try {
        ws.send(JSON.stringify({ type: "end" }));
      } catch {
        resolve(finalText);
        return;
      }
      window.setTimeout(() => {
        if (finalResolve) {
          finalResolve(finalText);
          finalResolve = null;
        }
      }, 20_000);
    });

    try {
      ws.close(1000, "done");
    } catch {
      /* ignore */
    }
    return result;
  };

  const abort = () => {
    active = false;
    finalResolve = null;
    cleanupMedia();
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "reset" }));
        ws.close(1000, "abort");
      }
    } catch {
      /* ignore */
    }
  };

  return {
    get active() {
      return active;
    },
    stop,
    abort,
    getLevel: () => level,
  };
}
