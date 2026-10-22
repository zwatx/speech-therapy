'use strict';

(function (root) {
  const RATE = 16000;
  const MIN_SAMPLES = 1600;
  const MAX_SAMPLES = 64000;
  const FINISH_WAIT_MS = 2000;
  const CLEANUP_WAIT_MS = 2000;
  const isObject = (value) => value !== null && typeof value === 'object';
  const validRate = (rate) => Number.isInteger(rate) && rate >= 8000 && rate <= 192000;
  const finiteSamples = (samples) => samples instanceof Float32Array && samples.every(Number.isFinite);
  const keysAre = (value, keys) => isObject(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));

  function encodeWav(pcm) {
    if (!finiteSamples(pcm) || pcm.length < MIN_SAMPLES || pcm.length > MAX_SAMPLES) throw new Error('invalid_audio');
    const buffer = new ArrayBuffer(44 + pcm.length * 2);
    const view = new DataView(buffer);
    const tag = (offset, value) => Array.from(value).forEach((letter, index) => view.setUint8(offset + index, letter.charCodeAt(0)));
    tag(0, 'RIFF'); view.setUint32(4, 36 + pcm.length * 2, true); tag(8, 'WAVE'); tag(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, RATE, true); view.setUint32(28, RATE * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); tag(36, 'data'); view.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i += 1) {
      const value = Math.max(-1, Math.min(1, pcm[i]));
      view.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
    }
    return buffer;
  }

  async function encodeSamples(samples, rate) {
    if (!validRate(rate) || !finiteSamples(samples) || samples.length > rate * 4) throw new Error('invalid_audio');
    const count = Math.floor(samples.length * RATE / rate);
    if (count < MIN_SAMPLES) throw new Error('too_short');
    if (count > MAX_SAMPLES) throw new Error('invalid_audio');
    let pcm = samples.slice();
    if (rate !== RATE) {
      const offline = new root.OfflineAudioContext(1, count, RATE);
      const buffer = offline.createBuffer(1, samples.length, rate);
      buffer.copyToChannel(samples, 0);
      const source = offline.createBufferSource();
      source.buffer = buffer;
      try {
        source.connect(offline.destination);
        source.start(0);
        const rendered = await offline.startRendering();
        if (rendered.numberOfChannels !== 1 || rendered.sampleRate !== RATE || rendered.length !== count) throw new Error('invalid_audio');
        pcm = rendered.getChannelData(0).slice();
        if (pcm.length !== count) throw new Error('invalid_audio');
      } finally {
        source.disconnect();
      }
    }
    return { buffer: encodeWav(pcm), sampleCount: pcm.length, sampleRate: RATE, durationSeconds: pcm.length / RATE };
  }

  function createRecorder({ onState = () => {}, onComplete = () => {}, onError = () => {} } = {}) {
    let owner = null;
    let state = 'idle';
    let elapsedSeconds = 0;
    let level = 0;
    const getState = () => ({ state, elapsedSeconds, level, cleanupConfirmed: state === 'idle', busy: owner !== null || state !== 'idle' });
    // UI observers cannot interrupt ownership or cleanup bookkeeping.
    const notify = (callback, value) => { try { callback(value); } catch { /* observer failure */ } };
    const emit = () => notify(onState, getState());
    function setState(next) { state = next; level = 0; emit(); }
    function cleanupUnknown(cap) {
      cap.cleanupFailed = true;
      if (owner !== cap) return;
      state = 'blocked'; level = 0; emit();
      if (!cap.cleanupReported) { cap.cleanupReported = true; notify(onError, { code: 'cleanup_unknown', cleanupConfirmed: false }); }
    }

    // Ownership remains on cap until each pending operation and resource settles.
    function releaseGraph(cap) {
      for (const timer of cap.timers) root.clearTimeout(timer);
      cap.timers.clear();
      for (const [track, handler] of cap.trackHooks) {
        try { track.removeEventListener('ended', handler); } catch { cap.cleanupFailed = true; }
      }
      cap.trackHooks = [];
      if (cap.context) cap.context.onstatechange = null;
      if (cap.node) {
        cap.node.port.onmessage = null;
        try { cap.node.port.close(); } catch { cap.cleanupFailed = true; }
        cap.node = null;
      }
      for (const node of cap.nodes) {
        try { node.disconnect(); } catch { cap.cleanupFailed = true; }
      }
      cap.nodes = [];
      if (cap.stream) {
        try {
          for (const track of cap.stream.getTracks()) {
            try { track.stop(); } catch { cap.cleanupFailed = true; }
            if (track.readyState !== 'ended') cap.cleanupFailed = true;
          }
        } catch { cap.cleanupFailed = true; }
        if (!cap.cleanupFailed) cap.stream = null;
      }
      if (!cap.closePromise) {
        const context = cap.context;
        if (!context) cap.closePromise = Promise.resolve(true);
        else {
          const timer = root.setTimeout(() => cleanupUnknown(cap), CLEANUP_WAIT_MS);
          try {
            cap.closePromise = Promise.resolve(context.close()).then(() => {
              if (context.state !== 'closed') cap.cleanupFailed = true;
              else cap.context = null;
              return !cap.cleanupFailed;
            }, () => { cap.cleanupFailed = true; return false; }).finally(() => root.clearTimeout(timer));
          } catch {
            root.clearTimeout(timer); cap.cleanupFailed = true; cap.closePromise = Promise.resolve(false);
          }
        }
      }
      return cap.closePromise;
    }

    async function settle(cap) {
      releaseGraph(cap);
      await cap.setup.catch(() => {});
      const closed = await releaseGraph(cap); // Includes a late permission grant.
      if (!closed || cap.cleanupFailed) { cleanupUnknown(cap); return { cleanupConfirmed: false }; }
      let result = null;
      if (!cap.cancelled && !cap.error && cap.samples) {
        try { result = await encodeSamples(cap.samples, cap.rate); }
        catch (error) { cap.error = error.message === 'too_short' ? 'too_short' : 'invalid_audio'; }
      }
      cap.samples = null;
      if (owner !== cap) return { cleanupConfirmed: false };
      if (cap.cancelled && result) new Uint8Array(result.buffer).fill(0);
      const error = cap.cancelled ? null : cap.error;
      owner = null; state = 'idle'; elapsedSeconds = 0; level = 0;
      emit();
      if (error) notify(onError, { code: error, cleanupConfirmed: true });
      else if (!cap.cancelled && result) notify(onComplete, result);
      return { cleanupConfirmed: true };
    }
    function beginSettlement(cap) {
      if (!cap.settlement) {
        cap.settlement = settle(cap);
        cap.settlement.then((receipt) => {
          for (const resolve of cap.stopWaiters || []) resolve(receipt);
          cap.stopWaiters = [];
        });
      }
      return cap.settlement;
    }
    function fail(cap, code) {
      if (owner !== cap || cap.cancelled || cap.terminal) return;
      cap.terminal = true; cap.error = code;
      setState('finishing');
      beginSettlement(cap);
    }
    function finish(cap) {
      if (owner !== cap || cap.cancelled || cap.terminal || cap.finishRequested || state !== 'recording') return;
      cap.finishRequested = true;
      setState('finishing');
      try { cap.node.port.postMessage('finish'); }
      catch { fail(cap, 'capture_failed'); return; }
      cap.timers.add(root.setTimeout(() => fail(cap, 'capture_timeout'), FINISH_WAIT_MS));
    }
    function message(cap, msg) {
      if (owner !== cap || cap.cancelled || cap.terminal) return;
      if (msg?.type === 'level') {
        if (!keysAre(msg, ['type', 'frames', 'peak', 'sampleRate']) || msg.sampleRate !== cap.rate || !Number.isInteger(msg.frames) || msg.frames <= cap.lastFrames || msg.frames > cap.maxFrames || !Number.isFinite(msg.peak) || msg.peak < 0) { fail(cap, 'invalid_audio'); return; }
        cap.lastFrames = msg.frames;
        elapsedSeconds = msg.frames / cap.rate;
        level = cap.finishRequested ? 0 : msg.peak;
        emit();
      } else if (msg?.type === 'data') {
        if (!keysAre(msg, ['type', 'buffer', 'length', 'sampleRate']) || !(msg.buffer instanceof ArrayBuffer) || msg.sampleRate !== cap.rate || !Number.isInteger(msg.length) || msg.length < cap.lastFrames || msg.length < 0 || msg.length > cap.maxFrames || msg.buffer.byteLength !== cap.maxFrames * 4 || (!cap.finishRequested && msg.length !== cap.maxFrames)) { fail(cap, 'invalid_audio'); return; }
        const samples = new Float32Array(msg.buffer, 0, msg.length);
        if (!finiteSamples(samples)) { fail(cap, 'invalid_audio'); return; }
        cap.samples = samples.slice(); cap.terminal = true;
        elapsedSeconds = msg.length / cap.rate;
        setState('finishing');
        beginSettlement(cap);
      } else if (keysAre(msg, ['type', 'code']) && msg.type === 'error' && msg.code === 'invalid_audio') fail(cap, 'invalid_audio');
      else fail(cap, 'invalid_audio');
    }

    async function setup(cap) {
      cap.stream = await root.navigator.mediaDevices.getUserMedia({
        audio: { channelCount: { ideal: 1 }, echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false,
      });
      if (cap.cancelled) return;
      const tracks = cap.stream.getTracks();
      if (!tracks.length || tracks.some((track) => track.kind !== 'audio' || track.readyState !== 'live')) throw new Error('capture_failed');
      if (!await cap.resumePromise) throw new Error('capture_failed');
      if (cap.cancelled) return;
      await cap.context.audioWorklet.addModule('audio-capture.js');
      if (cap.cancelled) return;
      if (cap.context.state !== 'running') throw new Error('capture_failed');
      const source = cap.context.createMediaStreamSource(cap.stream);
      cap.nodes.push(source);
      let tail = source;
      // Browser resampling kernel plus a fourth-order low pass before downsampling.
      if (cap.rate > RATE) for (const q of [0.5412, 1.3066]) {
        const filter = cap.context.createBiquadFilter();
        filter.type = 'lowpass'; filter.frequency.value = 7200; filter.Q.value = q;
        cap.nodes.push(filter); tail.connect(filter); tail = filter;
      }
      const node = new root.AudioWorkletNode(cap.context, 'phrase-capture', {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit',
        processorOptions: { maxFrames: cap.maxFrames },
      });
      cap.node = node; cap.nodes.push(node);
      node.port.onmessage = (event) => message(cap, event.data);
      tail.connect(node); node.connect(cap.context.destination);
      for (const track of tracks) {
        const handler = () => finish(cap);
        track.addEventListener('ended', handler); cap.trackHooks.push([track, handler]);
      }
      cap.context.onstatechange = () => { if (cap.context?.state !== 'running') finish(cap); };
      cap.timers.add(root.setTimeout(() => finish(cap), 5000));
    }

    async function start() {
      if (owner || state !== 'idle') return getState();
      if (!root.isSecureContext || !root.navigator?.mediaDevices?.getUserMedia || !root.AudioContext || !root.AudioWorkletNode || !root.OfflineAudioContext) {
        notify(onError, { code: 'unsupported', cleanupConfirmed: true }); return getState();
      }
      const cap = { cancelled: false, terminal: false, error: null, context: null, stream: null, node: null, nodes: [], trackHooks: [], timers: new Set(), closePromise: null, settlement: null, lastFrames: 0, samples: null, cleanupFailed: false };
      owner = cap; state = 'requesting'; elapsedSeconds = 0; level = 0;
      try {
        // Both calls occur synchronously in the caller's explicit Record gesture.
        cap.context = new root.AudioContext({ latencyHint: 'interactive' });
        cap.resumePromise = Promise.resolve(cap.context.resume()).then(() => true, () => false);
        cap.rate = cap.context.sampleRate;
        if (!validRate(cap.rate)) throw new Error('capture_failed');
        cap.maxFrames = cap.rate * 4;
        cap.setup = setup(cap);
      } catch { cap.setup = Promise.reject(new Error('capture_failed')); }
      // Attach rejection handling before callbacks can cancel this attempt.
      const started = cap.setup.then(() => {
        if (!cap.cancelled && !cap.terminal) setState('recording');
      }, (error) => {
        const code = ['NotAllowedError', 'SecurityError'].includes(error.name) ? 'permission_denied'
          : ['NotFoundError', 'OverconstrainedError', 'NotReadableError', 'AbortError'].includes(error.name) ? 'microphone_unavailable' : 'capture_failed';
        fail(cap, code);
      });
      emit();
      await started;
      if (cap.settlement) await cap.settlement;
      return getState();
    }
    function stop() {
      if (!owner) return Promise.resolve({ cleanupConfirmed: state === 'idle' });
      const cap = owner;
      finish(cap);
      if (state === 'requesting') return cancel();
      // Data receipt starts settlement; wait without creating a competing terminal path.
      return cap.settlement || new Promise((resolve) => {
        cap.stopWaiters ||= [];
        cap.stopWaiters.push(resolve);
      });
    }
    function cancel() {
      if (!owner) return Promise.resolve({ cleanupConfirmed: state === 'idle' });
      const cap = owner;
      cap.cancelled = true; cap.samples = null;
      if (state !== 'blocked') setState('cancelling');
      return beginSettlement(cap);
    }
    return { start, stop, cancel, getState };
  }
  root.PhraseRecorder = Object.freeze({ createRecorder, encodeWav });
})(window);
