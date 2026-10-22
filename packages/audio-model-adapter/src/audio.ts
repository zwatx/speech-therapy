export interface NormalizedAudio {
  readonly samples: Float32Array;
  readonly sampleRateHertz: 16_000;
}

export function validateNormalizedAudio(audio: NormalizedAudio): void {
  if (audio.sampleRateHertz !== 16_000) {
    throw new TypeError("The acoustic baseline requires 16 kHz audio.");
  }
  const durationSeconds = audio.samples.length / audio.sampleRateHertz;
  if (durationSeconds < 0.15 || durationSeconds > 5) {
    throw new TypeError("Audio duration must be between 150 ms and 5 seconds.");
  }
  for (const sample of audio.samples) {
    if (!Number.isFinite(sample) || sample < -1 || sample > 1) {
      throw new TypeError("Audio samples must be finite and normalized.");
    }
  }
}
