/**
 * Capture microphone audio as high-quality 16 kHz mono WAV for Whisper.
 * Includes client-side peak normalize + silence trim before encoding.
 */

const TARGET_SAMPLE_RATE = 16000;

function mergeFloat32(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

function resampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === TARGET_SAMPLE_RATE) return input;
  if (inputRate <= 0 || input.length === 0) return input;

  const ratio = inputRate / TARGET_SAMPLE_RATE;
  const newLength = Math.max(1, Math.round(input.length / ratio));
  const result = new Float32Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const srcIndex = i * ratio;
    const i0 = Math.floor(srcIndex);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const t = srcIndex - i0;
    result[i] = input[i0] * (1 - t) + input[i1] * t;
  }
  return result;
}

/** High-pass-ish DC remove + soft noise gate + peak normalize + edge silence trim. */
function preprocessPcm(samples: Float32Array): Float32Array {
  if (samples.length === 0) return samples;

  // Remove DC offset
  let mean = 0;
  for (let i = 0; i < samples.length; i++) mean += samples[i];
  mean /= samples.length;

  const centered = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) centered[i] = samples[i] - mean;

  // Soft noise gate: attenuate very quiet samples
  const gate = 0.012;
  for (let i = 0; i < centered.length; i++) {
    const a = Math.abs(centered[i]);
    if (a < gate) centered[i] *= a / gate;
  }

  // Trim leading/trailing silence
  const thresh = 0.02;
  let start = 0;
  let end = centered.length - 1;
  while (start < centered.length && Math.abs(centered[start]) < thresh) start++;
  while (end > start && Math.abs(centered[end]) < thresh) end--;

  const pad = Math.floor(TARGET_SAMPLE_RATE * 0.05); // 50ms pad
  start = Math.max(0, start - pad);
  end = Math.min(centered.length - 1, end + pad);

  const trimmed = centered.subarray(start, end + 1);
  if (trimmed.length < TARGET_SAMPLE_RATE * 0.2) {
    return new Float32Array(0);
  }

  // Peak normalize to ~0.92
  let peak = 0;
  for (let i = 0; i < trimmed.length; i++) {
    const a = Math.abs(trimmed[i]);
    if (a > peak) peak = a;
  }
  if (peak < 0.008) return new Float32Array(0);

  const gain = Math.min(0.92 / peak, 8);
  const out = new Float32Array(trimmed.length);
  for (let i = 0; i < trimmed.length; i++) {
    out[i] = Math.max(-1, Math.min(1, trimmed[i] * gain));
  }
  return out;
}

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export type WavSegmentRecorder = {
  captureSegment: (durationMs: number) => Promise<Blob>;
  getLevel: () => number;
  stop: () => void;
};

export async function createWavSegmentRecorder(
  stream: MediaStream
): Promise<WavSegmentRecorder> {
  // Prefer 48k capture then downsample cleanly to 16k (better than low native rates)
  const audioContext = new AudioContext();
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  const source = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;

  const bufferSize = 4096;
  const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);

  let collecting = false;
  let chunks: Float32Array[] = [];
  let level = 0;

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    level = Math.sqrt(sum / input.length);

    if (collecting) {
      chunks.push(new Float32Array(input));
    }
  };

  source.connect(analyser);
  analyser.connect(processor);
  const mute = audioContext.createGain();
  mute.gain.value = 0;
  processor.connect(mute);
  mute.connect(audioContext.destination);

  const captureSegment = (durationMs: number): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      if (audioContext.state === "closed") {
        reject(new Error("Audio context closed"));
        return;
      }

      chunks = [];
      collecting = true;

      window.setTimeout(() => {
        collecting = false;
        try {
          const merged = mergeFloat32(chunks);
          const resampled = resampleTo16k(merged, audioContext.sampleRate);
          const pcm = preprocessPcm(resampled);

          if (pcm.length < TARGET_SAMPLE_RATE * 0.25) {
            resolve(new Blob([], { type: "audio/wav" }));
            return;
          }

          resolve(encodeWav(pcm, TARGET_SAMPLE_RATE));
        } catch (e) {
          reject(e);
        }
      }, durationMs);
    });
  };

  const stop = () => {
    collecting = false;
    try {
      processor.disconnect();
      analyser.disconnect();
      source.disconnect();
      mute.disconnect();
    } catch {
      /* ignore */
    }
    void audioContext.close();
  };

  return {
    captureSegment,
    getLevel: () => level,
    stop,
  };
}
