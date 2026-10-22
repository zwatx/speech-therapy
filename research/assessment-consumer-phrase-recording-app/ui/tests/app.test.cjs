'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');

function setup(recorderFactory) {
  const nodes = new Map();
  const windowEvents = new Map();
  function node() {
    return { value: '', checked: false, hidden: true, textContent: '', disabled: true, files: [], children: [], listeners: {},
      addEventListener(name, callback) { this.listeners[name] = callback; }, pause() {}, load() {}, removeAttribute() {},
      append(...children) { this.children.push(...children); }, replaceChildren(...children) { this.children = children; } };
  }
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
      },
      createElement: node,
    },
    window: { addEventListener(name, callback) { windowEvents.set(name, callback); }, PhraseRecorder: recorderFactory ? { createRecorder: recorderFactory } : undefined },
    fetch: async () => { throw new Error('offline test'); },
    setTimeout: () => 1, clearTimeout() {}, URL: { revokeObjectURL() {}, createObjectURL: () => 'blob:test' },
    crypto: { randomUUID: () => '11111111-1111-4111-8111-111111111111' },
    Blob, Uint8Array, DataView, ArrayBuffer,
    btoa: (value) => Buffer.from(value, 'binary').toString('base64'),
  });
  context.testCatalog = { csrfToken: 'test', prompts: [{ id: 'test-word', kind: 'word', transcript: 'red', focus: 'R', cue: 'Listen.', soundID: 'r', position: 'beginning', modelSupported: true, supportedContexts: ['recognition', 'child-research'] }] };
  vm.runInContext(source, context);
  nodes.get('context').value = 'child-research';
  nodes.get('prompt-kind').value = 'word';
  nodes.get('phrase').value = 'test-word';
  return { context, nodes, windowEvents, run: (code) => vm.runInContext(code, context) };
}

function wav(seconds = 1, rate = 16000, channels = 1, bits = 16) {
  const dataBytes = Math.round(seconds * rate * channels * bits / 8);
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const text = (at, value) => [...value].forEach((char, i) => view.setUint8(at + i, char.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, channels, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * channels * bits / 8, true);
  view.setUint16(32, channels * bits / 8, true); view.setUint16(34, bits, true); text(36, 'data'); view.setUint32(40, dataBytes, true);
  return buffer;
}

test('accepts generated supported WAV duration boundaries', () => {
  const { context, run } = setup();
  for (const seconds of [0.1, 1, 4]) { context.audioBuffer = wav(seconds); assert.equal(run('inspectWav(audioBuffer)'), seconds); }
});

test('rejects unsupported formats, sizes, truncated and out-of-range WAV', () => {
  const { context, run } = setup();
  const invalid = [wav(0.09), wav(4.01), wav(1, 44100), wav(1, 16000, 2), wav(1, 16000, 1, 8), new ArrayBuffer(20)];
  const truncated = wav(); new DataView(truncated).setUint32(40, 999999, true); invalid.push(truncated);
  for (const buffer of invalid) { context.audioBuffer = buffer; assert.throws(() => run('inspectWav(audioBuffer)')); }
});

test('unknown age and absent consent keep analysis disabled', () => {
  const { run, nodes } = setup();
  run("state.catalog = testCatalog; state.capture = { used: false }; updateControls()");
  assert.equal(nodes.get('check').disabled, true);
  nodes.get('age').value = '6'; run('updateControls()'); assert.equal(nodes.get('check').disabled, true);
  nodes.get('consent').checked = true; run('updateControls()'); assert.equal(nodes.get('check').disabled, false);
  nodes.get('age').value = '13'; run('updateControls()'); assert.equal(nodes.get('check').disabled, true);
});

test('every new upload clears age and consent and creates one capture identity', async () => {
  const { run, nodes } = setup();
  nodes.get('age').value = '9'; nodes.get('consent').checked = true;
  nodes.get('audio-file').files = [{ name: 'generated.wav', size: wav().byteLength, arrayBuffer: async () => wav() }];
  await run('selectFile()');
  assert.equal(nodes.get('age').value, ''); assert.equal(nodes.get('consent').checked, false);
  assert.equal(run('state.capture.requestId'), '11111111-1111-4111-8111-111111111111');
  assert.equal(nodes.get('playback').hidden, false);
});

test('lost submission recovers by job lookup, retaining a consumed capture', async () => {
  const { run, nodes } = setup();
  run("state.catalog = testCatalog; state.capture = { used: false, requestId: '11111111-1111-4111-8111-111111111111', buffer: new ArrayBuffer(44) }");
  nodes.get('age').value = '8'; nodes.get('consent').checked = true; run('updateControls()');
  await run('startCheck()');
  assert.equal(run('state.active.jobId'), '11111111-1111-4111-8111-111111111111');
  assert.equal(run('state.capture.used'), true); assert.equal(nodes.get('check').disabled, true);
});

test('cancelled receipt with null result settles; cleanup unknown blocks successors', async () => {
  for (const status of ['cancelled', 'cleanup_unknown']) {
    const { context, run, nodes } = setup();
    context.fetch = async () => ({ ok: true, json: async () => ({ jobId: 'job', status, cleanupConfirmed: status === 'cancelled', result: null }) });
    run("state.active = { jobId: 'job', stale: true, generation: 0 }; state.capture = { used: false }; state.catalog = testCatalog;");
    await run('poll()');
    assert.equal(run('state.active === null'), status === 'cancelled');
    if (status === 'cleanup_unknown') { assert.equal(nodes.get('check').disabled, true); assert.match(nodes.get('check-status').textContent, /retained/); }
    assert.equal(nodes.get('result').hidden, true);
  }
});

test('stale completion never attaches to the changed selection', async () => {
  const { context, run, nodes } = setup();
  context.fetch = async () => ({ ok: true, json: async () => ({ jobId: 'job', status: 'complete', cleanupConfirmed: true, result: { cleanupConfirmed: true, message: 'old result' } }) });
  run("state.active = { jobId: 'job', stale: true, generation: 0 }; state.generation = 1");
  await run('poll()');
  assert.equal(nodes.get('result').hidden, true);
  assert.equal(run('state.active'), null);
});


test('cancelled without an explicit cleanup receipt stays blocked', async () => {
  const { context, run, nodes } = setup();
  context.fetch = async () => ({ ok: true, json: async () => ({ jobId: 'job', status: 'cancelled', result: null }) });
  run("state.active = { jobId: 'job', stale: true, generation: 0 }");
  await run('poll()');
  assert.equal(run('state.active.status'), 'cleanup_unknown');
  assert.equal(nodes.get('check').disabled, true);
});

test('computed but unavailable sound analysis is explicitly uncertain', () => {
  const { run, nodes } = setup();
  run("renderResult({ soundAnalysisAvailable: false, scoredOccurrences: 11, alignmentUnverified: true, phraseMatched: true, cleanupConfirmed: true })");
  assert.match(nodes.get('sound-result').textContent, /^Uncertain/);
  assert.match(nodes.get('alignment-note').textContent, /unverified/);
});

test('lost submission and early cancel 404 retry cancellation after job admission, never the check', async () => {
  const { context, run, nodes } = setup();
  const jobId = '11111111-1111-4111-8111-111111111111';
  const calls = [];
  let rejectSubmission;
  let cancels = 0;
  let status = 'processing';
  context.fetch = async (url) => {
    calls.push(url);
    if (url === '/api/check') return new Promise((resolve, reject) => { rejectSubmission = reject; });
    if (url === '/api/cancel') {
      cancels += 1;
      if (cancels === 1) return { status: 404, ok: false };
      return { status: 200, ok: true, json: async () => ({ jobId, status: 'cancelling' }) };
    }
    return { status: 200, ok: true, json: async () => ({ jobId, status, cleanupConfirmed: status === 'cancelled', result: null }) };
  };
  run("state.catalog = testCatalog; state.capture = { used: false, requestId: '11111111-1111-4111-8111-111111111111', buffer: new ArrayBuffer(44) }");
  nodes.get('age').value = '8'; nodes.get('consent').checked = true;
  const submission = run('startCheck()');
  run('invalidate()');
  rejectSubmission(new Error('lost 202'));
  await submission;
  assert.equal(cancels, 1);
  assert.equal(run('state.active.cancelAcknowledged'), false);
  await run('poll()');
  assert.equal(cancels, 2);
  assert.equal(run('state.active.cancelAcknowledged'), true);
  await run('poll()');
  assert.equal(cancels, 2, 'acknowledged cancellation must not loop');
  status = 'cancelled';
  await run('poll()');
  assert.equal(run('state.active'), null);
  assert.equal(calls.filter((url) => url === '/api/check').length, 1);
  assert.equal(nodes.get('result').hidden, true);
});

test('cancellation acknowledgement requires the matching job and recognized status', async () => {
  for (const response of [{ jobId: 'other-job', status: 'cancelling' }, { jobId: 'job', status: 'unexpected' }]) {
    const { context, run } = setup();
    context.fetch = async () => ({ status: 200, ok: true, json: async () => response });
    run("state.catalog = testCatalog; state.active = { jobId: 'job', cancelAcknowledged: false }");
    await run('requestCancel()');
    assert.equal(run('state.active.cancelAcknowledged'), false);
    assert.equal(run('state.active.cancelRequested'), true);
  }
});

// These explicit fake-engine tests check UI ownership only, not physical microphone behavior.
function setupRecording() {
  let callbacks;
  let finishCancel;
  const calls = { start: 0, stop: 0, cancel: 0 };
  const harness = setup((handlers) => {
    callbacks = handlers;
    return {
      start() { calls.start += 1; callbacks.onState({ state: 'requesting', elapsedSeconds: 0, level: 0 }); return Promise.resolve(); },
      stop() { calls.stop += 1; callbacks.onState({ state: 'finishing', elapsedSeconds: 1, level: 0 }); return Promise.resolve(); },
      cancel() { calls.cancel += 1; return new Promise((resolve) => { finishCancel = resolve; }); },
    };
  });
  harness.run('state.catalog = testCatalog; updateControls()');
  return { ...harness, calls, callbacks, finishCancel(receipt) { finishCancel(receipt); } };
}

test('recording starts only explicitly and clears old audio, age, consent and result', () => {
  const { context, run, nodes, calls } = setupRecording();
  const revoked = [];
  context.URL.revokeObjectURL = (url) => revoked.push(url);
  run('state.capture = { url: "blob:previous", used: false };');
  nodes.get('age').value = '12'; nodes.get('consent').checked = true; nodes.get('result').hidden = false;
  assert.equal(calls.start, 0);
  run('startRecording()');
  assert.equal(calls.start, 1);
  assert.equal(run('state.capture'), null);
  assert.equal(nodes.get('age').value, ''); assert.equal(nodes.get('consent').checked, false);
  assert.equal(nodes.get('result').hidden, true); assert.deepEqual(revoked, ['blob:previous']);
  assert.equal(nodes.get('check').disabled, true);
  assert.equal(nodes.get('stop-recording').disabled, true);
  assert.equal(nodes.get('discard-recording').disabled, false);
});

test('only actual engine sample time is shown; stop waits for cleanup before manual playback', () => {
  const { run, nodes, callbacks, calls } = setupRecording();
  run('startRecording()');
  callbacks.onState({ state: 'recording', elapsedSeconds: 0.375, level: 0.25 });
  assert.equal(nodes.get('record-time').textContent, '0.4');
  assert.equal(nodes.get('record-level').value, 0.25);
  assert.equal(nodes.get('stop-recording').disabled, false);
  run('stopRecording()');
  assert.equal(calls.stop, 1); assert.equal(run('state.capture'), null);
  callbacks.onState({ state: 'idle', elapsedSeconds: 0, level: 0 });
  assert.equal(nodes.get('record').disabled, true, 'idle before completion must not release the UI session');
  callbacks.onComplete({ buffer: wav(), sampleRate: 16000, sampleCount: 16000, durationSeconds: 1 });
  assert.equal(run('state.recording'), null);
  assert.equal(run('state.capture.used'), false);
  assert.equal(nodes.get('playback').hidden, false);
  assert.equal(nodes.get('check').disabled, true);
  assert.equal(run('state.active'), null, 'completion must never automatically submit');
});

test('recording completion is inspected and each new capture gets a new identity', () => {
  const { context, run, callbacks } = setupRecording();
  let identities = 0;
  context.crypto.randomUUID = () => `capture-${++identities}`;
  run('startRecording()'); callbacks.onComplete({ buffer: wav(1, 44100) });
  assert.equal(run('state.capture'), null); assert.equal(identities, 0);
  run('startRecording()'); callbacks.onComplete({ buffer: wav() });
  assert.equal(run('state.capture.requestId'), 'capture-1');
  run('startRecording()'); callbacks.onComplete({ buffer: wav() });
  assert.equal(run('state.capture.requestId'), 'capture-2');
});

test('discard and setting changes invalidate late capture completion', async () => {
  const { run, callbacks, finishCancel, calls } = setupRecording();
  run('startRecording()');
  const cancelling = run('invalidate()');
  assert.equal(calls.cancel, 1);
  callbacks.onComplete({ buffer: wav() });
  finishCancel({ cleanupConfirmed: true }); await cancelling;
  assert.equal(run('state.capture'), null);
  assert.equal(run('state.recording'), null);
});

test('choosing a file waits for microphone cleanup before reading or installing it', async () => {
  const { run, nodes, finishCancel, callbacks } = setupRecording();
  let reads = 0;
  nodes.get('audio-file').files = [{ name: 'replacement.wav', size: wav().byteLength, arrayBuffer: async () => { reads += 1; return wav(); } }];
  run('startRecording()');
  const loading = run('selectFile()');
  await Promise.resolve(); assert.equal(reads, 0); assert.equal(run('state.capture'), null);
  assert.equal(nodes.get('record').disabled, true); assert.equal(nodes.get('check').disabled, true);
  callbacks.onState({ state: 'idle', elapsedSeconds: 0, level: 0 });
  finishCancel({ cleanupConfirmed: true }); await loading;
  assert.equal(reads, 1); assert.match(nodes.get('file-status').textContent, /replacement.wav/);
  assert.equal(run('state.pendingFile'), null);
});

test('unconfirmed microphone cleanup keeps recording/check blocked and never reads a replacement', async () => {
  const { run, nodes, finishCancel } = setupRecording();
  let reads = 0;
  nodes.get('audio-file').files = [{ name: 'replacement.wav', size: wav().byteLength, arrayBuffer: async () => { reads += 1; return wav(); } }];
  run('startRecording()'); const loading = run('selectFile()');
  finishCancel({ cleanupConfirmed: false }); await loading;
  assert.equal(reads, 0); assert.equal(run('state.recording.phase'), 'blocked');
  assert.equal(nodes.get('record').disabled, true); assert.equal(nodes.get('check').disabled, true);
  assert.match(nodes.get('record-status').textContent, /could not be confirmed/);
});

test('a changed selection cannot install a file read that finishes late', async () => {
  const { run, nodes } = setupRecording();
  let finishRead;
  nodes.get('audio-file').files = [{ name: 'old.wav', size: wav().byteLength, arrayBuffer: () => new Promise((resolve) => { finishRead = resolve; }) }];
  const loading = run('selectFile()'); await Promise.resolve();
  run('invalidate()'); finishRead(wav()); await loading;
  assert.equal(run('state.capture'), null);
});

test('capture and service work exclude one another, including unresolved service cleanup', async () => {
  const { run, nodes, calls, callbacks } = setupRecording();
  run('state.active = { status: "cleanup_unknown" }; updateControls(); startRecording()');
  assert.equal(calls.start, 0); assert.equal(nodes.get('record').disabled, true);
  run('state.active = null; startRecording()');
  nodes.get('age').value = '8'; nodes.get('consent').checked = true;
  run('state.capture = { used: false }; updateControls()');
  assert.equal(nodes.get('check').disabled, true);
  await run('startCheck()'); assert.equal(run('state.active'), null);
  callbacks.onError({ code: 'cleanup_unknown', cleanupConfirmed: false });
  run('startRecording()'); assert.equal(calls.start, 1);
});

test('pagehide discards capture; BFCache restore stays blocked while permission cleanup is pending', async () => {
  const { run, nodes, callbacks, windowEvents, finishCancel, calls } = setupRecording();
  run('startRecording()'); windowEvents.get('pagehide')();
  assert.equal(calls.cancel, 1);
  windowEvents.get('pageshow')({ persisted: true });
  assert.equal(nodes.get('record').disabled, true); assert.equal(nodes.get('check').disabled, true);
  assert.match(nodes.get('record-status').textContent, /Waiting for microphone cleanup/);
  callbacks.onComplete({ buffer: wav() });
  finishCancel({ cleanupConfirmed: true }); await Promise.resolve();
  assert.equal(run('state.capture'), null);
});

function libraryPrompt(id, word, soundID = 'r', position = 'beginning', modelSupported = true) {
  return { id, transcript: word, focus: `${soundID.toUpperCase()} in ${word}`, cue: 'A cue about the selected sound.', kind: 'word', soundID, position, modelSupported, supportedContexts: modelSupported ? ['recognition', 'child-research'] : [], targetCount: 1 };
}

function setupLibrary() {
  const harness = setupRecording();
  harness.context.testCatalog.prompts = [
    libraryPrompt('red', 'red'), libraryPrompt('rain', 'rain'), libraryPrompt('ring', 'ring'),
    libraryPrompt('road', 'road'), libraryPrompt('room', 'room'), libraryPrompt('rose', 'rose'),
    libraryPrompt('red-end', 'red', 'd', 'end'), libraryPrompt('beige', 'beige', 'zh', 'end', false),
    { id: 'phrase', kind: 'phrase', transcript: 'My red ball', focus: 'R and L', cue: 'Say the whole phrase.', modelSupported: true, supportedContexts: ['child-research'], soundID: null, position: null, targetCount: 2 },
  ];
  harness.nodes.get('context').value = 'recognition';
  harness.nodes.get('phrase').value = 'red';
  harness.run('renderLibrary()');
  return harness;
}

test('library initialization defaults to recognition with blank age and unchecked consent', async () => {
  const { context, run, nodes } = setupLibrary();
  context.testCatalog.schemaVersion = 1;
  context.fetch = async () => ({ ok: true, json: async () => context.testCatalog });
  await run('initialize()');
  assert.equal(nodes.get('context').value, 'recognition');
  assert.equal(nodes.get('age').value, ''); assert.equal(nodes.get('consent').checked, false);
  assert.equal(nodes.get('age-field').hidden, true);
  assert.equal(nodes.get('prompt-kind').value, 'word');
});

test('recognition payload never fabricates child age and still requires explicit consent', async () => {
  const { context, run, nodes } = setupLibrary();
  const requests = [];
  context.audioBuffer = wav();
  run('installCapture(audioBuffer, "Generated word")');
  nodes.get('age').value = '8'; run('updateControls()');
  assert.equal(nodes.get('check').disabled, true);
  nodes.get('consent').checked = true; run('updateControls()');
  assert.equal(nodes.get('check').disabled, false);
  context.fetch = async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) });
    return { status: 202, json: async () => ({ jobId: requests[0].body.requestId, status: 'processing' }) };
  };
  await run('startCheck()');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.context, 'recognition');
  assert.equal(requests[0].body.ageYears, null);
  assert.equal(requests[0].body.promptId, 'red');
});

test('child research requires an actual supported age; context switch clears age and consent', () => {
  const { run, nodes } = setupLibrary();
  run('state.capture = { used: false }');
  nodes.get('context').value = 'child-research'; nodes.get('consent').checked = true;
  for (const age of ['', '5', '13', 'adult']) {
    nodes.get('age').value = age; run('updateControls()'); assert.equal(nodes.get('check').disabled, true);
  }
  nodes.get('age').value = '12'; run('updateControls()'); assert.equal(nodes.get('check').disabled, false);
  nodes.get('context').value = 'recognition'; nodes.get('context').listeners.change();
  assert.equal(nodes.get('age').value, ''); assert.equal(nodes.get('consent').checked, false);
  assert.equal(nodes.get('age-field').hidden, true);
});

test('practice-only sound groups and phrases in recognition context never enable a check', () => {
  const { run, nodes } = setupLibrary();
  run('state.capture = { used: false }'); nodes.get('consent').checked = true;
  for (const id of ['beige', 'phrase']) {
    nodes.get('phrase').value = id; run('showPhrase(); updateControls()');
    assert.equal(nodes.get('check').disabled, true);
    assert.equal(nodes.get('record').disabled, false, 'manual recording remains available');
    assert.equal(nodes.get('start-session').disabled, true, 'an unsupported selection cannot silently start another word review');
  }
  nodes.get('context').value = 'child-research'; nodes.get('age').value = '9';
  run('updateControls()'); assert.equal(nodes.get('check').disabled, false);
  nodes.get('phrase').value = 'beige'; run('updateControls()'); assert.equal(nodes.get('check').disabled, true);
});

test('library filters combine group, position and case-insensitive search without relabelling', () => {
  const { run, nodes } = setupLibrary();
  nodes.get('sound-filter').value = 'd'; nodes.get('position-filter').value = 'end'; nodes.get('word-search').value = 'RED';
  run('changeLibrary()');
  assert.deepEqual(Array.from(run('filteredPrompts().map(prompt => prompt.id)')), ['red-end']);
  assert.equal(nodes.get('phrase').value, 'red-end'); assert.equal(nodes.get('phrase-heading').textContent, 'red');
  nodes.get('word-search').value = 'no-match'; run('changeLibrary()');
  assert.equal(nodes.get('phrase').value, ''); assert.equal(nodes.get('record').disabled, true);
  assert.equal(nodes.get('start-session').disabled, true);
  nodes.get('prompt-kind').value = 'phrase'; run('changeLibrary()');
  assert.deepEqual(Array.from(run('filteredPrompts().map(prompt => prompt.id)')), ['phrase']);
  assert.equal(nodes.get('word-filters').hidden, true);
});

test('changing library invalidates old audio and cancels a pending recording', async () => {
  const { run, nodes, finishCancel, callbacks } = setupLibrary();
  run('startRecording()'); nodes.get('word-search').value = 'rain'; run('changeLibrary()');
  callbacks.onComplete({ buffer: wav() }); finishCancel({ cleanupConfirmed: true });
  await Promise.resolve(); assert.equal(run('state.capture'), null);
  assert.equal(nodes.get('phrase').value, 'rain');
});

test('recognition result copy never implies individual sounds were assessed', () => {
  const { run, nodes } = setupLibrary();
  run('renderResult({ kind: "recognized", phraseMatched: true, soundAnalysisAvailable: false, scoredOccurrences: 0, cleanupConfirmed: true }, "recognition")');
  assert.match(nodes.get('phrase-result').textContent, /matched the selected word/);
  assert.match(nodes.get('sound-result').textContent, /^Not assessed/);
  assert.match(nodes.get('alignment-note').textContent, /not a pronunciation grade/);
});

test('guided review chooses up to five unique supported words without automatic capture/check', () => {
  const { run, nodes, calls } = setupLibrary();
  run('startSession()');
  assert.deepEqual(Array.from(run('state.session.queue')), ['red', 'rain', 'ring', 'road', 'room']);
  assert.equal(run('state.session.phase'), 'assessment'); assert.equal(calls.start, 0);
  assert.equal(run('state.active'), null); assert.equal(nodes.get('context').disabled, true);
  assert.match(nodes.get('session-status').textContent, /Word 1 of 5/);
});

test('guided navigation waits for capture and service settlement, and ending discards late capture', async () => {
  const { run, nodes, calls, callbacks, finishCancel } = setupLibrary();
  run('startSession(); startRecording(); nextSessionWord()');
  assert.equal(run('state.session.index'), 0); assert.equal(nodes.get('next-word').disabled, true);
  run('endSession()'); assert.equal(run('state.session'), null); assert.equal(calls.cancel, 1);
  callbacks.onComplete({ buffer: wav() }); finishCancel({ cleanupConfirmed: true }); await Promise.resolve();
  assert.equal(run('state.capture'), null);
  run('startSession(); state.active = { status: "cleanup_unknown" }; nextSessionWord(); updateControls()');
  assert.equal(run('state.session.index'), 0); assert.equal(nodes.get('next-word').disabled, true);
});

test('review summary requires user-chosen practice words; recheck remains a separate explicit round', () => {
  const { run, nodes, calls } = setupLibrary();
  run('startSession(); for (let i = 0; i < 5; i++) nextSessionWord()');
  assert.equal(run('state.session.phase'), 'summary'); assert.equal(nodes.get('practice-selected').disabled, true);
  assert.equal(nodes.get('recording-workspace').hidden, true);
  const firstRow = nodes.get('session-summary').children[0];
  assert.equal(firstRow.children[2].textContent, 'Not checked.');
  const checkbox = firstRow.children[0]; checkbox.checked = true; checkbox.listeners.change();
  assert.equal(nodes.get('practice-selected').disabled, false);
  run('beginSessionRound("practice")');
  assert.deepEqual(Array.from(run('state.session.queue')), ['red']); assert.equal(run('state.session.phase'), 'practice');
  run('nextSessionWord()'); assert.equal(run('state.session.summaryFrom'), 'practice');
  assert.equal(nodes.get('recheck-selected').hidden, false);
  run('beginSessionRound("recheck")'); assert.equal(run('state.session.phase'), 'recheck');
  assert.equal(calls.start, 0); assert.equal(run('state.active'), null);
  run('nextSessionWord()'); assert.match(nodes.get('session-status').textContent, /do not establish improvement/);
});

test('only current settled result is stored in guided observations', async () => {
  const { context, run } = setupLibrary();
  run('startSession(); state.active = { jobId: "job", generation: state.generation, promptId: "red", context: "recognition", session: state.session, sessionPhase: "assessment" }');
  context.fetch = async () => ({ ok: true, json: async () => ({ jobId: 'job', status: 'complete', cleanupConfirmed: true, result: { kind: 'recognized', phraseMatched: true, cleanupConfirmed: true } }) });
  await run('poll()'); assert.equal(run('state.session.assessment.red'), 'Selected word recognized.');
  run('nextSessionWord(); state.active = { jobId: "job", stale: true, generation: state.generation, promptId: "rain", context: "recognition", session: state.session, sessionPhase: "assessment" }');
  await run('poll()'); assert.equal(run('state.session.assessment.rain'), undefined);
});
