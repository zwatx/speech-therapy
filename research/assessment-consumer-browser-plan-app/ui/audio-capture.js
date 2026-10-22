'use strict';

// Bounded mono capture for the practice recorder. Runs on the audio rendering
// thread. Keeps at most processorOptions.maxFrames samples in one buffer
// allocated up front, and hands that buffer to the page exactly once: when the
// page asks to finish, or when the buffer is full.

const MAX_FRAMES = 192000 * 4;
const LEVEL_INTERVAL_SECONDS = 0.05;

class BoundedCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const requested = options && options.processorOptions ? options.processorOptions.maxFrames : 0;
    const capacity = Number.isInteger(requested) && requested > 0 && requested <= MAX_FRAMES ? requested : 0;
    this.samples = new Float32Array(capacity);
    this.length = 0;
    this.sent = false;
    this.peak = 0;
    this.sinceLevel = 0;
    this.levelFrames = Math.max(128, Math.round(sampleRate * LEVEL_INTERVAL_SECONDS));
    this.port.onmessage = (event) => {
      if (event.data === 'finish') this.finish();
    };
    if (capacity === 0) this.finish();
  }

  finish() {
    if (this.sent) return;
    this.sent = true;
    const buffer = this.samples.buffer;
    this.port.postMessage({ type: 'data', buffer, length: this.length, sampleRate }, [buffer]);
    this.samples = null;
  }

  process(inputs) {
    if (this.sent) return false;
    const channels = inputs[0];
    if (channels && channels.length > 0) {
      const count = Math.min(channels[0].length, this.samples.length - this.length);
      const scale = 1 / channels.length;
      for (let i = 0; i < count; i += 1) {
        let value = 0;
        for (let c = 0; c < channels.length; c += 1) value += channels[c][i];
        value *= scale;
        if (value > 1) value = 1;
        else if (value < -1) value = -1;
        else if (value !== value) value = 0;
        this.samples[this.length + i] = value;
        const magnitude = value < 0 ? -value : value;
        if (magnitude > this.peak) this.peak = magnitude;
      }
      this.length += count;
      this.sinceLevel += count;
    }
    if (this.length >= this.samples.length) {
      this.finish();
      return false;
    }
    if (this.sinceLevel >= this.levelFrames) {
      this.port.postMessage({ type: 'level', peak: this.peak, frames: this.length });
      this.peak = 0;
      this.sinceLevel = 0;
    }
    return true;
  }
}

registerProcessor('bounded-capture', BoundedCapture);
