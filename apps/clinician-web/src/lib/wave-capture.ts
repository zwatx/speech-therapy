import type { LearnerAttemptStatus } from "@speech-therapy/contracts";

export type AudioCaptureReasonCode =
  | "audio-clipping"
  | "audio-too-quiet"
  | "utterance-too-short"
  | "utterance-too-long";

export interface WaveCaptureEvidence {
  readonly durationMilliseconds: number;
  readonly sampleRateHertz: 16_000;
  readonly rmsDbfs: number;
  readonly peakAmplitude: number;
  readonly reasonCodes: readonly AudioCaptureReasonCode[];
  readonly status: LearnerAttemptStatus;
}

export interface DecodedWaveCapture {
  readonly evidence: WaveCaptureEvidence;
  readonly audio: {
    readonly samples: Float32Array;
    readonly sampleRateHertz: 16_000;
  };
}

function ascii(view: DataView, offset: number, length: number): string {
  let result = "";
  for (let index = 0; index < length; index += 1) {
    result += String.fromCharCode(view.getUint8(offset + index));
  }
  return result;
}

export function decodePcm16Wave(bytes: ArrayBuffer): DecodedWaveCapture {
  if (bytes.byteLength < 44) throw new TypeError("The WAVE capture is incomplete.");
  const view = new DataView(bytes);
  if (ascii(view, 0, 4) !== "RIFF" || ascii(view, 8, 4) !== "WAVE") {
    throw new TypeError("The capture must be a RIFF WAVE file.");
  }
  const declaredRiffBytes = view.getUint32(4, true) + 8;
  if (declaredRiffBytes !== bytes.byteLength) {
    throw new TypeError("The WAVE container length is inconsistent.");
  }

  let formatOffset: number | undefined;
  let formatLength = 0;
  let dataOffset: number | undefined;
  let dataLength = 0;
  let offset = 12;
  while (offset + 8 <= bytes.byteLength) {
    const chunkId = ascii(view, offset, 4);
    const chunkLength = view.getUint32(offset + 4, true);
    const contentOffset = offset + 8;
    if (contentOffset + chunkLength > bytes.byteLength) {
      throw new TypeError("A WAVE chunk extends beyond the container.");
    }
    if (chunkId === "fmt " && formatOffset === undefined) {
      formatOffset = contentOffset;
      formatLength = chunkLength;
    } else if (chunkId === "data" && dataOffset === undefined) {
      dataOffset = contentOffset;
      dataLength = chunkLength;
    }
    offset = contentOffset + chunkLength + (chunkLength % 2);
  }
  if (formatOffset === undefined || dataOffset === undefined || formatLength < 16) {
    throw new TypeError("The WAVE capture is missing required chunks.");
  }
  const audioFormat = view.getUint16(formatOffset, true);
  const channelCount = view.getUint16(formatOffset + 2, true);
  const sampleRate = view.getUint32(formatOffset + 4, true);
  const byteRate = view.getUint32(formatOffset + 8, true);
  const blockAlign = view.getUint16(formatOffset + 12, true);
  const bitsPerSample = view.getUint16(formatOffset + 14, true);
  if (
    audioFormat !== 1 ||
    channelCount !== 1 ||
    sampleRate !== 16_000 ||
    byteRate !== 32_000 ||
    blockAlign !== 2 ||
    bitsPerSample !== 16 ||
    dataLength === 0 ||
    dataLength % 2 !== 0
  ) {
    throw new TypeError("The capture must be mono 16 kHz PCM16 WAVE audio.");
  }

  const sampleCount = dataLength / 2;
  const durationMilliseconds = Math.round((sampleCount / sampleRate) * 1_000);
  let sumOfSquares = 0;
  let peakAmplitude = 0;
  let clippingSamples = 0;
  const samples = new Float32Array(sampleCount);
  for (let index = 0; index < sampleCount; index += 1) {
    const sample = view.getInt16(dataOffset + index * 2, true) / 32_768;
    samples[index] = sample;
    const amplitude = Math.abs(sample);
    sumOfSquares += sample * sample;
    peakAmplitude = Math.max(peakAmplitude, amplitude);
    if (amplitude >= 0.99) clippingSamples += 1;
  }
  const rms = Math.sqrt(sumOfSquares / sampleCount);
  const rmsDbfs = rms === 0 ? -160 : Math.max(-160, 20 * Math.log10(rms));
  const reasonCodes: AudioCaptureReasonCode[] = [];
  if (durationMilliseconds < 450) reasonCodes.push("utterance-too-short");
  if (durationMilliseconds > 4_000) reasonCodes.push("utterance-too-long");
  if (rmsDbfs < -48) reasonCodes.push("audio-too-quiet");
  if (clippingSamples / sampleCount > 0.01) reasonCodes.push("audio-clipping");
  return {
    evidence: {
      durationMilliseconds,
      sampleRateHertz: 16_000,
      rmsDbfs,
      peakAmplitude,
      reasonCodes,
      status: reasonCodes.length === 0 ? "accepted-silent" : "retry-capture",
    },
    audio: { samples, sampleRateHertz: 16_000 },
  };
}

export function inspectPcm16Wave(bytes: ArrayBuffer): WaveCaptureEvidence {
  return decodePcm16Wave(bytes).evidence;
}
