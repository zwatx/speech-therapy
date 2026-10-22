'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');

function setup() {
  const nodes = new Map();
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, { value: '', checked: false, hidden: true, textContent: '', disabled: true, files: [], addEventListener() {}, pause() {}, load() {}, removeAttribute() {}, append() {} });
        return nodes.get(id);
      },
      createElement() { return {}; },
    },
    window: { addEventListener() {} },
    fetch: async () => { throw new Error('offline test'); },
    setTimeout: () => 1, clearTimeout() {}, URL: { revokeObjectURL() {}, createObjectURL: () => 'blob:test' },
    crypto: { randomUUID: () => '11111111-1111-4111-8111-111111111111' },
    Blob, Uint8Array, DataView, ArrayBuffer,
    btoa: (value) => Buffer.from(value, 'binary').toString('base64'),
  });
  vm.runInContext(source, context);
  return { context, nodes, run: (code) => vm.runInContext(code, context) };
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
  run("state.catalog = {}; state.capture = { used: false }; updateControls()");
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
  run("state.catalog = { csrfToken: 'test' }; state.capture = { used: false, requestId: '11111111-1111-4111-8111-111111111111', buffer: new ArrayBuffer(44) }");
  nodes.get('age').value = '8'; nodes.get('consent').checked = true; run('updateControls()');
  await run('startCheck()');
  assert.equal(run('state.active.jobId'), '11111111-1111-4111-8111-111111111111');
  assert.equal(run('state.capture.used'), true); assert.equal(nodes.get('check').disabled, true);
});

test('cancelled receipt with null result settles; cleanup unknown blocks successors', async () => {
  for (const status of ['cancelled', 'cleanup_unknown']) {
    const { context, run, nodes } = setup();
    context.fetch = async () => ({ ok: true, json: async () => ({ jobId: 'job', status, cleanupConfirmed: status === 'cancelled', result: null }) });
    run("state.active = { jobId: 'job', stale: true, generation: 0 }; state.capture = { used: false }; state.catalog = {};");
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
  run("state.catalog = { csrfToken: 'test' }; state.capture = { used: false, requestId: '11111111-1111-4111-8111-111111111111', buffer: new ArrayBuffer(44) }");
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
    run("state.catalog = { csrfToken: 'test' }; state.active = { jobId: 'job', cancelAcknowledged: false }");
    await run('requestCancel()');
    assert.equal(run('state.active.cancelAcknowledged'), false);
    assert.equal(run('state.active.cancelRequested'), true);
  }
});
