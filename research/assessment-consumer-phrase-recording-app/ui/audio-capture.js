'use strict';

// Actual render-thread samples only. The destination receives silence.
class PhraseCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const frames = options?.processorOptions?.maxFrames;
    const valid = Number.isInteger(sampleRate) && sampleRate >= 8000 && sampleRate <= 192000 && frames === sampleRate * 4;
    this.samples = new Float32Array(valid ? frames : 0);
    this.frames = 0;
    this.peak = 0;
    this.lastLevel = 0;
    this.sent = false;
    this.port.onmessage = (event) => {
      if (event.data === 'finish') this.finish();
      else this.fail();
    };
    if (!valid) this.fail();
  }

  fail() {
    if (this.sent) return;
    this.sent = true;
    this.samples = null;
    this.port.postMessage({ type: 'error', code: 'invalid_audio' });
  }

  finish() {
    if (this.sent) return;
    this.sent = true;
    const buffer = this.samples.buffer;
    this.samples = null;
    this.port.postMessage({ type: 'data', buffer, length: this.frames, sampleRate }, [buffer]);
  }

  process(inputs, outputs) {
    for (const output of outputs) for (const channel of output) channel.fill(0);
    if (this.sent) return false;
    const channels = inputs[0];
    if (!channels?.length) return true;
    if (channels.length > 32 || !channels.every((channel) => channel instanceof Float32Array && channel.length === channels[0].length)) {
      this.fail();
      return false;
    }
    const count = Math.min(channels[0].length, this.samples.length - this.frames);
    for (let i = 0; i < count; i += 1) {
      let value = 0;
      for (const channel of channels) {
        if (!Number.isFinite(channel[i])) { this.fail(); return false; }
        value += channel[i] / channels.length;
      }
      if (!Number.isFinite(value)) { this.fail(); return false; }
      this.samples[this.frames + i] = value;
      this.peak = Math.max(this.peak, Math.abs(value));
    }
    this.frames += count;
    if (this.frames === this.samples.length) { this.finish(); return false; }
    if (this.frames - this.lastLevel >= Math.round(sampleRate * 0.05)) {
      this.port.postMessage({ type: 'level', frames: this.frames, peak: this.peak, sampleRate });
      this.lastLevel = this.frames;
      this.peak = 0;
    }
    return true;
  }
}
registerProcessor('phrase-capture', PhraseCapture);
