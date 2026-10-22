'use strict';

// Generated PCM and fake browser resources only; no sensors, playback, or network.
const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const recorderSource = fs.readFileSync(path.join(__dirname, '..', 'recorder.js'), 'utf8');
const workletSource = fs.readFileSync(path.join(__dirname, '..', 'audio-capture.js'), 'utf8');
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const flush = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };

function harness(options = {}) {
  const permission = deferred();
  const close = deferred();
  const render = deferred();
  const timers = new Map();
  const contexts = [];
  const nodes = [];
  const states = [];
  const errors = [];
  const complete = [];
  const tracks = [track(), track()];
  const stream = { getTracks: () => tracks };
  let serial = 0;
  let calls = 0;
  let requested;
  function track() {
    return { kind: 'audio', readyState: 'live', stopCalls: 0, hooks: new Map(),
      stop() { this.stopCalls += 1; if (options.throwStop) throw Error('stop'); this.readyState = 'ended'; },
      addEventListener(name, callback) { this.hooks.set(name, callback); },
      removeEventListener(name, callback) { if (this.hooks.get(name) === callback) this.hooks.delete(name); },
    };
  }
  function graphNode() { return { connected: [], disconnected: false, connect(node) { this.connected.push(node); }, disconnect() { this.disconnected = true; } }; }
  class Context {
    constructor() { this.sampleRate = options.rate || 16000; this.state = 'suspended'; this.destination = {}; this.audioWorklet = { addModule: async (url) => { assert.equal(url, 'audio-capture.js'); if (options.failModule) throw Error('module'); } }; contexts.push(this); }
    resume() { this.state = 'running'; return options.resumePromise || Promise.resolve(); }
    createMediaStreamSource() { const node = graphNode(); nodes.push(node); return node; }
    createBiquadFilter() { const node = { ...graphNode(), frequency: {}, Q: {} }; nodes.push(node); return node; }
    close() {
      this.closeCalls = (this.closeCalls || 0) + 1;
      if (options.closeReject) return Promise.reject(Error('close'));
      if (options.closePending) return close.promise.then(() => { this.state = 'closed'; });
      this.state = 'closed'; return Promise.resolve();
    }
  }
  class Worklet {
    constructor(context, name, config) {
      assert.equal(name, 'phrase-capture'); assert.equal(config.channelCount, 1);
      Object.assign(this, graphNode()); this.config = config;
      this.port = { onmessage: null, sent: [], closed: false, postMessage(data) { this.sent.push(data); }, close() { this.closed = true; } };
      nodes.push(this);
    }
  }
  class Offline {
    constructor(channels, length, rate) { this.length = length; this.sampleRate = rate; this.destination = {}; }
    createBuffer(channels, length, rate) { return { copyToChannel: (samples) => { assert.equal(samples.length, length); this.input = samples.slice(); }, length, rate }; }
    createBufferSource() { this.source = graphNode(); this.source.start = () => {}; return this.source; }
    startRendering() {
      const result = () => ({ numberOfChannels: 1, sampleRate: this.sampleRate, length: this.length,
        getChannelData: () => options.invalidRender ? new Float32Array(this.length).fill(NaN) : new Float32Array(this.length).fill(0.25),
      });
      return options.renderPending ? render.promise.then(result) : Promise.resolve(result());
    }
  }
  const window = { isSecureContext: true, navigator: { mediaDevices: { getUserMedia: (input) => { calls += 1; requested = input; return permission.promise; } } },
    AudioContext: Context, AudioWorkletNode: Worklet, OfflineAudioContext: Offline,
    setTimeout: (fn, delay) => { const id = ++serial; timers.set(id, { fn, delay }); return id; }, clearTimeout: (id) => timers.delete(id),
  };
  vm.runInNewContext(recorderSource, { window, ArrayBuffer, DataView, Uint8Array, Float32Array });
  const engine = window.PhraseRecorder.createRecorder({ onState: (s) => { states.push(s); if (options.throwObservers) throw Error('observer'); }, onError: (e) => { errors.push(e); if (options.throwObservers) throw Error('observer'); }, onComplete: (r) => { complete.push(r); if (options.throwObservers) throw Error('observer'); } });
  const worklet = () => nodes.find((node) => node instanceof Worklet);
  const packet = (length, value = 0.25) => {
    const max = (options.rate || 16000) * 4;
    const samples = new Float32Array(max); samples.fill(value, 0, length);
    return { type: 'data', buffer: samples.buffer, length, sampleRate: options.rate || 16000 };
  };
  const send = (data) => worklet().port.onmessage?.({ data });
  async function begin() { const started = engine.start(); permission.resolve(stream); await started; assert.equal(engine.getState().state, 'recording'); }
  async function finish(length = 1600) { const stopped = engine.stop(); send(packet(length)); await stopped; return complete[0]; }
  function fire(delay) { for (const [id, timer] of Array.from(timers)) if (timer.delay === delay) { timers.delete(id); timer.fn(); } }
  return { engine, permission, close, render, stream, tracks, contexts, nodes, states, errors, complete, timers, window, worklet, packet, send, begin, finish, fire, calls: () => calls, requested: () => requested };
}

function wavFacts(result) {
  const view = new DataView(result.buffer);
  const tag = (offset) => String.fromCharCode(...new Uint8Array(result.buffer, offset, 4));
  assert.equal(tag(0), 'RIFF'); assert.equal(tag(8), 'WAVE'); assert.equal(tag(12), 'fmt '); assert.equal(tag(36), 'data');
  assert.equal(view.getUint32(4, true), result.buffer.byteLength - 8); assert.equal(view.getUint32(16, true), 16);
  assert.equal(view.getUint16(20, true), 1); assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000); assert.equal(view.getUint32(28, true), 32000);
  assert.equal(view.getUint16(32, true), 2); assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), result.sampleCount * 2); assert.equal(result.durationSeconds, result.sampleCount / 16000);
}

test('module load is inert; Record owns exact audio-only permission and completes after cleanup', async () => {
  const h = harness(); assert.equal(h.calls(), 0); assert.equal(h.contexts.length, 0);
  await h.begin(); assert.equal(h.calls(), 1); assert.equal(h.requested().video, false); assert.equal(h.requested().audio.channelCount.ideal, 1);
  h.send({ type: 'level', frames: 800, peak: 0.35, sampleRate: 16000 });
  assert.equal(h.engine.getState().elapsedSeconds, 0.05); assert.equal(h.engine.getState().level, 0.35);
  const result = await h.finish(); wavFacts(result); assert.equal(result.sampleCount, 1600);
  assert.equal(h.engine.getState().state, 'idle'); assert.equal(h.engine.getState().elapsedSeconds, 0);
  assert.ok(h.tracks.every((track) => track.readyState === 'ended' && track.stopCalls === 1 && track.hooks.size === 0));
  assert.equal(h.contexts[0].state, 'closed'); assert.ok(h.nodes.every((node) => node.disconnected)); assert.ok(h.worklet().port.closed);
  assert.equal(h.worklet().port.onmessage, null); assert.equal(h.contexts[0].onstatechange, null); assert.equal(h.timers.size, 0);
});

test('denied permission reports only after context cleanup and permits a later explicit start', async () => {
  const h = harness(); const start = h.engine.start(); const error = new Error('denied'); error.name = 'NotAllowedError'; h.permission.reject(error);
  await start; assert.equal(h.errors.length, 1); assert.equal(h.errors[0].code, 'permission_denied'); assert.equal(h.errors[0].cleanupConfirmed, true);
  assert.equal(h.contexts[0].state, 'closed'); assert.equal(h.engine.getState().busy, false); assert.equal(h.complete.length, 0);
});

test('cancel during permission waits for a late grant, stops all tracks and rejects competing start', async () => {
  const h = harness(); const start = h.engine.start(); let settled = false; const cancel = h.engine.cancel().then((r) => { settled = true; return r; });
  await flush(); assert.equal(settled, false); assert.equal(h.engine.getState().state, 'cancelling'); assert.equal(h.engine.getState().cleanupConfirmed, false);
  await h.engine.start(); assert.equal(h.calls(), 1); assert.equal(h.contexts[0].state, 'closed');
  h.permission.resolve(h.stream); const receipt = await cancel; await start;
  assert.equal(receipt.cleanupConfirmed, true); assert.ok(h.tracks.every((track) => track.readyState === 'ended' && track.stopCalls === 1));
  assert.equal(h.nodes.length, 0); assert.equal(h.complete.length, 0); assert.equal(h.engine.getState().busy, false);
});

test('cancelled permission rejection settles with no denied-message or completion', async () => {
  const h = harness(); const start = h.engine.start(); const cancelled = h.engine.cancel(); h.permission.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' }));
  assert.equal((await cancelled).cleanupConfirmed, true); await start; assert.equal(h.errors.length, 0); assert.equal(h.complete.length, 0);
});

test('context close rejection retains blocked ownership and never delivers the recording', async () => {
  const h = harness({ closeReject: true }); await h.begin(); const receipt = await h.finish(16000);
  assert.equal(receipt, undefined); assert.equal(h.engine.getState().state, 'blocked'); assert.equal(h.engine.getState().cleanupConfirmed, false);
  assert.equal(h.errors[0].code, 'cleanup_unknown'); assert.equal(h.errors[0].cleanupConfirmed, false);
  await h.engine.start(); assert.equal(h.calls(), 1); assert.equal(h.complete.length, 0);
});

test('pending close gives no false receipt, then latches blocked after cleanup watchdog', async () => {
  const h = harness({ closePending: true }); await h.begin(); let settled = false;
  const stopped = h.engine.stop().then(() => { settled = true; }); h.send(h.packet(1600)); await flush();
  assert.equal(settled, false); assert.equal(h.engine.getState().state, 'finishing'); assert.equal(h.complete.length, 0);
  h.fire(2000); await flush(); assert.equal(h.engine.getState().state, 'blocked'); assert.equal(settled, false);
  h.close.resolve(); await stopped; assert.equal(h.complete.length, 0); assert.equal(h.engine.getState().state, 'blocked');
});

test('a throwing track stop is blocked even when the context closes', async () => {
  const h = harness({ throwStop: true }); await h.begin(); const receipt = await h.engine.cancel();
  assert.equal(receipt.cleanupConfirmed, false); assert.equal(h.engine.getState().state, 'blocked'); assert.equal(h.complete.length, 0);
});

test('data is bounded to four seconds and completion is unique; stale callbacks are ignored', async () => {
  const h = harness(); await h.begin(); const callback = h.worklet().port.onmessage;
  h.send(h.packet(64000)); await flush(); wavFacts(h.complete[0]); assert.equal(h.complete[0].durationSeconds, 4);
  callback({ data: h.packet(64000) }); callback({ data: { type: 'level', frames: 64000, peak: 1, sampleRate: 16000 } });
  assert.equal(h.complete.length, 1); assert.equal(h.engine.getState().elapsedSeconds, 0);
});

test('zero and short captures fail honestly without fabricated samples', async () => {
  for (const length of [0, 1, 1599]) {
    const h = harness(); await h.begin(); await h.finish(length);
    assert.equal(h.complete.length, 0); assert.equal(h.errors[0].code, 'too_short'); assert.equal(h.engine.getState().cleanupConfirmed, true);
  }
});

test('stall timer requests finish; missing worklet response becomes capture_timeout', async () => {
  const h = harness(); await h.begin(); h.fire(5000); assert.equal(h.engine.getState().state, 'finishing'); assert.deepEqual(h.worklet().port.sent, ['finish']);
  h.fire(2000); await flush(); assert.equal(h.errors[0].code, 'capture_timeout'); assert.equal(h.complete.length, 0);
  assert.equal(h.engine.getState().state, 'idle'); assert.equal(h.engine.getState().elapsedSeconds, 0);
});

test('a suspended graph asks for existing samples, rather than measuring wall-clock time', async () => {
  const h = harness(); await h.begin(); h.contexts[0].state = 'suspended'; h.contexts[0].onstatechange();
  assert.equal(h.engine.getState().state, 'finishing'); h.send(h.packet(1600)); await flush(); assert.equal(h.complete[0].durationSeconds, 0.1);
});

test('current invalid packets, reversed counts, wrong rates, nonfinite PCM and premature data are refused', async () => {
  const invalid = [
    (h) => ({ type: 'unknown' }),
    (h) => ({ type: 'level', frames: 1, peak: NaN, sampleRate: 16000 }),
    (h) => ({ type: 'level', frames: 64001, peak: 0.2, sampleRate: 16000 }),
    (h) => ({ type: 'level', frames: 2, peak: 0.2, sampleRate: 48000 }),
    (h) => ({ ...h.packet(1600), length: 64001 }),
    (h) => ({ ...h.packet(1600), length: 1.5 }),
    (h) => ({ ...h.packet(1600), buffer: new ArrayBuffer(64000 * 4 + 4) }),
    (h) => ({ ...h.packet(1600), buffer: new ArrayBuffer(0) }),
    (h) => ({ ...h.packet(1600), sampleRate: 48000 }),
    (h) => h.packet(1600, Infinity),
    (h) => ({ ...h.packet(1600), extra: true }),
  ];
  for (const packet of invalid) {
    const h = harness(); await h.begin(); const stopped = h.engine.stop(); h.send(packet(h)); await stopped;
    assert.equal(h.complete.length, 0); assert.equal(h.errors[0].code, 'invalid_audio');
  }
  for (const data of ['duplicate', 'backward', 'premature']) {
    const h = harness(); await h.begin();
    if (data === 'premature') h.send(h.packet(1600));
    else { h.send({ type: 'level', frames: 800, peak: 0.1, sampleRate: 16000 }); h.send({ type: 'level', frames: data === 'duplicate' ? 800 : 799, peak: 0.1, sampleRate: 16000 }); }
    await flush(); assert.equal(h.errors[0].code, 'invalid_audio'); assert.equal(h.complete.length, 0);
  }
});

test('48 kHz uses anti-alias filters and validated browser rendering to exact 16 kHz duration', async () => {
  const h = harness({ rate: 48000 }); await h.begin(); assert.equal(h.nodes.filter((n) => n.type === 'lowpass').length, 2);
  const result = await h.finish(4800); wavFacts(result); assert.equal(result.sampleCount, 1600); assert.equal(result.durationSeconds, 0.1);
});

test('cancellation during pending resampling waits for rendering, suppresses output, then releases busy state', async () => {
  const h = harness({ rate: 48000, renderPending: true }); await h.begin(); const stopped = h.engine.stop(); h.send(h.packet(4800)); await flush();
  let cancelled = false; const cancellation = h.engine.cancel().then((receipt) => { cancelled = true; return receipt; }); await flush();
  assert.equal(cancelled, false); assert.equal(h.engine.getState().state, 'cancelling'); await h.engine.start(); assert.equal(h.calls(), 1);
  h.render.resolve(); assert.equal((await cancellation).cleanupConfirmed, true); await stopped;
  assert.equal(h.complete.length, 0); assert.equal(h.engine.getState().state, 'idle');
});

test('nonfinite offline rendering fails; pure encoder rejects overlong or nonfinite inputs without truncation', async () => {
  const h = harness({ rate: 48000, invalidRender: true }); await h.begin(); await h.finish(4800);
  assert.equal(h.complete.length, 0); assert.equal(h.errors[0].code, 'invalid_audio');
  const api = h.window.PhraseRecorder;
  assert.throws(() => api.encodeWav(new Float32Array(64001)), /invalid_audio/);
  assert.throws(() => api.encodeWav(new Float32Array(1600).fill(NaN)), /invalid_audio/);
  assert.throws(() => api.encodeWav(new Float32Array(1599)), /invalid_audio/);
  const pcm = new Float32Array(1600); pcm[0] = -1; pcm[1] = 1;
  const buffer = api.encodeWav(pcm); const view = new DataView(buffer); assert.equal(view.getInt16(44, true), -32768); assert.equal(view.getInt16(46, true), 32767);
});

function workletHarness(rate = 48000, maxFrames = rate * 4) {
  const messages = [];
  let Processor;
  class Base { constructor() { this.port = { onmessage: null, postMessage: (packet, transfer) => messages.push({ packet, transfer }) }; } }
  vm.runInNewContext(workletSource, { sampleRate: rate, AudioWorkletProcessor: Base, Float32Array, registerProcessor: (name, value) => { assert.equal(name, 'phrase-capture'); Processor = value; } });
  const processor = new Processor({ processorOptions: { maxFrames } });
  return { processor, messages };
}

test('real worklet logic counts generated mono frames, writes silence, caps at four seconds and transfers once', () => {
  const { processor, messages } = workletHarness(); const input = new Float32Array(128).fill(0.4); const output = new Float32Array(128).fill(1);
  for (let i = 0; i < 1500; i += 1) processor.process([[input]], [[output]]);
  assert.ok(output.every((value) => value === 0)); assert.equal(processor.frames, 192000);
  const data = messages.filter((item) => item.packet.type === 'data'); assert.equal(data.length, 1);
  assert.equal(data[0].packet.length, 192000); assert.equal(data[0].packet.buffer.byteLength, 192000 * 4); assert.equal(data[0].transfer[0], data[0].packet.buffer);
  assert.equal(new Float32Array(data[0].packet.buffer)[191999], input[0]);
  processor.port.onmessage({ data: 'finish' }); processor.process([[input]], [[output]]); assert.equal(messages.filter((item) => item.packet.type === 'data').length, 1);
  const levels = messages.filter((item) => item.packet.type === 'level'); assert.ok(levels.length > 0); assert.equal(levels[0].packet.sampleRate, 48000); assert.equal(levels[0].packet.peak, input[0]);
});

test('worklet mixes actual channels and does not count absent input; malformed settings and PCM are errors', () => {
  const h = workletHarness(16000); const output = new Float32Array(128).fill(1);
  h.processor.process([[]], [[output]]); assert.equal(h.processor.frames, 0);
  h.processor.process([[new Float32Array(128).fill(0.5), new Float32Array(128).fill(-0.25)]], [[output]]);
  h.processor.port.onmessage({ data: 'finish' }); assert.equal(h.messages[0].packet.length, 128); assert.equal(new Float32Array(h.messages[0].packet.buffer)[0], 0.125);
  for (const args of [[16000, 64001], [192001, 768004]]) assert.equal(workletHarness(...args).messages[0].packet.type, 'error');
  const bad = workletHarness(); bad.processor.process([[new Float32Array(128).fill(NaN)]], [[output]]);
  assert.equal(bad.messages[0].packet.type, 'error'); assert.equal(bad.messages.filter((item) => item.packet.type === 'data').length, 0);
});


test('unsupported browsers and setup faults settle honestly without completion', async () => {
  const unsupported = harness(); unsupported.window.isSecureContext = false;
  await unsupported.engine.start(); assert.equal(unsupported.calls(), 0); assert.equal(unsupported.contexts.length, 0);
  assert.equal(unsupported.errors[0].code, 'unsupported'); assert.equal(unsupported.engine.getState().cleanupConfirmed, true);
  const module = harness({ failModule: true }); const started = module.engine.start(); module.permission.resolve(module.stream); await started;
  assert.equal(module.errors[0].code, 'capture_failed'); assert.ok(module.tracks.every((track) => track.readyState === 'ended'));
  assert.equal(module.contexts[0].state, 'closed'); assert.equal(module.complete.length, 0);
  const rate = harness({ rate: 192001 }); await rate.engine.start(); assert.equal(rate.calls(), 0);
  assert.equal(rate.errors[0].code, 'capture_failed'); assert.equal(rate.contexts[0].state, 'closed');
});

test('observer exceptions cannot interrupt capture cleanup or reject lifecycle methods', async () => {
  const h = harness({ throwObservers: true }); await h.begin(); await h.finish();
  assert.equal(h.complete.length, 1); assert.equal(h.engine.getState().state, 'idle'); assert.ok(h.tracks.every((track) => track.readyState === 'ended'));
});
