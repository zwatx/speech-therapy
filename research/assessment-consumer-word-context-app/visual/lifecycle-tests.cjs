// Explicit unit seams: actual owned JS, fake SDK/worker outputs, zero models/sensors.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const base = __dirname;
const workerSource = fs.readFileSync(path.join(base, '../ui/visual-worker.js'), 'utf8');
const runtimeSource = fs.readFileSync(path.join(base, '../ui/visual-runtime.js'), 'utf8');
const manifest = fs.readFileSync(path.join(base, 'asset-manifest.json'));
const model = fs.readFileSync(path.join(base, 'face_landmarker.task'));
let passed = 0;
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
async function check(name, test) { await test(); passed++; console.log('PASS UNIT ' + name); }

function workerHarness(result = { faceLandmarks: [] }) {
  const posts = []; let nativeCalls = 0; let detections = 0; let frameClosed = 0; let taskClosed = 0;
  const self = { location: { origin: 'http://127.0.0.1:8782' },
    importScripts() { throw Error('unit loader must not execute'); },
    fetch: async (url) => { nativeCalls++; return new Response(url.endsWith('asset-manifest.json') ? manifest : model); },
    postMessage: (value) => posts.push(value), close() {},
    WebSocket: class {}, EventSource: class {}, navigator: {},
  };
  const fakeSDK = { FaceLandmarker: { FACE_LANDMARKS_LIPS: [{ start: 13, end: 14 }],
    async createFromOptions(fileset, options) {
      assert.equal(fileset, 'unit_fileset'); assert.equal(options.baseOptions.delegate, 'CPU');
      assert.equal(options.numFaces, 2); assert.equal(options.outputFaceBlendshapes, false);
      return { detectForVideo() { detections++; return result; }, close() {
        taskClosed++; self.fetch('https://odml.pa.googleapis.com/v1/log', { method: 'POST', body: 'UNIT' }).catch(() => {});
      } };
    } }, FilesetResolver: { async forVisionTasks(value) { assert.equal(value, '/visual/wasm'); return 'unit_fileset'; } } };
  const context = { self, URL, Response, Uint8Array, Map, Set, Number, Math, Error, TypeError,
    crypto: webcrypto, performance: { now: () => 220 }, testImport: async () => fakeSDK };
  vm.runInNewContext(workerSource.replace("await import('/visual/vision_bundle.mjs')", 'await testImport()'), context);
  return { self, posts, async init() { await self.onmessage({ data: { type: 'init', generation: 1 } }); },
    async frame(timestamp = 200) { await self.onmessage({ data: { type: 'frame', generation: 1, id: 1, timestamp,
      frame: { width: 320, height: 240, close() { frameClosed++; } } } }); },
    get nativeCalls() { return nativeCalls; }, get detections() { return detections; },
    get frameClosed() { return frameClosed; }, get taskClosed() { return taskClosed; } };
}
function points() { return Array.from({ length: 478 }, (_, i) => ({ x: .2 + (i % 17) * .03, y: .1 + Math.floor(i / 17) * .025 })); }
function runtimeHarness() {
  let now = 0; let nextId = 0; const timers = new Map(); const workers = [];
  const listeners = new Map(); let pendingBitmap = null; let bitmapClosed = 0; let sizes = [];
  class FakeWorker {
    constructor(url) { assert.equal(url, '/visual-worker.js'); workers.push(this); this.messages = []; this.terminated = false; this.autoClose = true; }
    postMessage(message) {
      this.messages.push(message);
      if (message.type === 'init') this.generation = message.generation;
      if (message.type === 'close' && this.autoClose) this.emit({ type: 'closed', generation: this.generation, networkBlockedCount: 3 });
    }
    emit(data) { this.onmessage?.({ data }); }
    ready() { this.emit({ type: 'ready', generation: this.generation, networkBlockedCount: 0, manifestSha256: 'ac02f689b9ec4a105f4d0e6aa4093698d3ffbf430acc4d1849426c7f0bb3ecf1' }); }
    terminate() { this.terminated = true; }
  }
  const document = { visibilityState: 'visible', addEventListener(name, fn) { listeners.set(fn, name); }, removeEventListener(name, fn) { listeners.delete(fn); } };
  const context = { document, Worker: FakeWorker, Promise, Number, Math, Error,
    performance: { now: () => now },
    setTimeout: (fn, delay) => { const id = ++nextId; timers.set(id, { fn, at: now + delay }); return id; },
    clearTimeout: (id) => timers.delete(id),
    createImageBitmap: async (video, options) => { sizes.push(options); if (pendingBitmap) return pendingBitmap;
      return { width: options.resizeWidth, height: options.resizeHeight, close() { bitmapClosed++; } }; },
  };
  vm.runInNewContext(runtimeSource.replace('export class LocalVisualRuntime', 'class LocalVisualRuntime') + '\nglobalThis.Runtime = LocalVisualRuntime;', context);
  const runtime = new context.Runtime(); const events = [];
  const video = { videoWidth: 1920, videoHeight: 1080, readyState: 2 };
  return { runtime, events, video, workers, document, listeners,
    async start() { const promise = runtime.start(video, (event) => events.push(event)); await flush(); workers.at(-1).ready(); await promise; },
    async advance(delta) { now += delta; for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.fn(); } await flush(); },
    bitmapDelay() { let resolve; pendingBitmap = new Promise((r) => { resolve = r; }); return () => resolve({ width: 640, height: 360, close() { bitmapClosed++; } }); },
    get bitmapClosed() { return bitmapClosed; }, get sizes() { return sizes; },
    hide() { document.visibilityState = 'hidden'; for (const fn of [...listeners.keys()]) fn(); },
  };
}

(async () => {
  await check('worker guarded bootstrap and bound manifest', async () => { const h = workerHarness(); await h.init(); assert.equal(h.posts.at(-1).type, 'ready'); assert.equal(h.nativeCalls, 2); });
  await check('worker blocks remote/query/POST before network', async () => {
    const h = workerHarness(); const before = h.nativeCalls;
    for (const [url, options] of [['https://odml.pa.googleapis.com/v1/log', {}], ['/visual/asset-manifest.json?q=1', {}], ['/visual/asset-manifest.json', { method: 'POST' }]]) await assert.rejects(h.self.fetch(url, options));
    assert.equal(h.nativeCalls, before); assert.throws(() => new h.self.WebSocket('wss://example.invalid')); });
  await check('worker no-face result closes frame', async () => { const h = workerHarness(); await h.init(); await h.frame(); assert.equal(h.posts.at(-1).status, 'no_face'); assert.equal(h.frameClosed, 1); });
  await check('worker multiple-face result contains no geometry', async () => { const h = workerHarness({ faceLandmarks: [points(), points()] }); await h.init(); await h.frame(); assert.equal(h.posts.at(-1).status, 'multiple_faces'); assert.equal(h.posts.at(-1).bounds, null); });
  await check('worker finite tracking projects outline and descriptive ratio only', async () => { const h = workerHarness({ faceLandmarks: [points()] }); await h.init(); await h.frame(); assert.equal(h.posts.at(-1).status, 'tracking'); assert.ok(Number.isFinite(h.posts.at(-1).aperture)); assert.equal(h.posts.at(-1).outline.length, 1); });
  await check('worker invalid geometry and overrate fail closed', async () => { const p = points(); p[13].x = NaN; const h = workerHarness({ faceLandmarks: [p] }); await h.init(); await h.frame(); assert.equal(h.posts.at(-1).type, 'failed'); await h.frame(201); assert.equal(h.detections, 1); assert.equal(h.frameClosed, 2); });
  await check('worker close rejects SDK unit metrics before I/O', async () => { const h = workerHarness(); await h.init(); const before = h.nativeCalls; await h.self.onmessage({ data: { type: 'close', generation: 1 } }); assert.equal(h.taskClosed, 1); assert.equal(h.nativeCalls, before); assert.equal(h.posts.at(-1).networkBlockedCount, 1); });
  await check('runtime ready and stop releases worker without camera ownership', async () => { const h = runtimeHarness(); await h.start(); const cleanup = await h.runtime.stop(); assert.equal(cleanup.cleanupConfirmed, true); assert.equal(cleanup.networkBlockedCount, 3); assert.ok(h.workers[0].terminated); assert.equal(h.listeners.size, 0); });
  await check('runtime caps dimensions and admits one in-flight frame', async () => { const h = runtimeHarness(); await h.start(); await h.advance(200); assert.equal(h.sizes[0].resizeWidth, 640); assert.equal(h.sizes[0].resizeHeight, 360); await h.advance(400); assert.equal(h.sizes.length, 1); await h.runtime.stop(); });
  await check('runtime cancellation closes late bitmap and ignores late result', async () => { const h = runtimeHarness(); await h.start(); const release = h.bitmapDelay(); await h.advance(200); await h.runtime.stop(); const before = h.events.length; release(); await flush(); assert.equal(h.bitmapClosed, 1); h.workers[0].emit({ type: 'result' }); assert.equal(h.events.length, before); });
  await check('runtime background closes worker and clears geometry', async () => { const h = runtimeHarness(); await h.start(); h.hide(); await flush(); assert.ok(h.workers[0].terminated); assert.equal(h.events.at(-1).reason, 'backgrounded'); assert.equal(h.events.at(-1).outline.length, 0); });
  await check('runtime timeout terminates unresponsive worker', async () => { const h = runtimeHarness(); await h.start(); h.workers[0].autoClose = false; const closing = h.runtime.stop(); await h.advance(500); assert.equal((await closing).cleanupConfirmed, false); assert.ok(h.workers[0].terminated); });
  await check('runtime stale observations never publish tracking geometry', async () => { const h = runtimeHarness(); await h.start(); await h.advance(200); const m = h.workers[0].messages.at(-1); await h.advance(600); h.workers[0].emit({ type: 'result', generation: m.generation, id: m.id, timestamp: m.timestamp, networkBlockedCount: 0, status: 'no_face', outline: [], bounds: null, aperture: null, elapsedMilliseconds: 2 }); assert.equal(h.events.at(-1).reason, 'stale_observation'); await h.runtime.stop(); });
  await check('runtime initialization cancellation cannot recreate worker', async () => { const h = runtimeHarness(); const started = h.runtime.start(h.video, (event) => h.events.push(event)); await flush(); const refused = assert.rejects(started, /cancelled/); await h.runtime.stop(); await refused; h.workers[0].ready(); assert.ok(h.workers[0].terminated); assert.equal(h.events.filter((event) => event.status === 'ready').length, 0); });
  await check('runtime repeated stop waits for detached cleanup', async () => { const h = runtimeHarness(); await h.start(); h.workers[0].autoClose = false; const first = h.runtime.stop(); let secondDone = false; const second = h.runtime.stop().then((value) => { secondDone = true; return value; }); await flush(); assert.equal(secondDone, false); await h.advance(500); assert.equal((await first).cleanupConfirmed, false); assert.equal((await second).cleanupConfirmed, false); });
  await check('runtime restart waits for detached cleanup', async () => { const h = runtimeHarness(); await h.start(); h.workers[0].autoClose = false; const first = h.runtime.stop(); const next = h.runtime.start(h.video, (event) => h.events.push(event)); await flush(); assert.equal(h.workers.length, 1); await h.advance(500); await first; await flush(); assert.equal(h.workers.length, 2); h.workers[1].ready(); await next; await h.runtime.stop(); });
  await check('runtime callback restart survives old failure continuation', async () => { const h = runtimeHarness(); let next; const first = h.runtime.start(h.video, (event) => { h.events.push(event); if (event.status === 'failed') next = h.runtime.start(h.video, (value) => h.events.push(value)); }); await flush(); h.workers[0].ready(); await first; h.workers[0].onerror(); await flush(); assert.equal(h.workers.length, 2); h.workers[1].ready(); await next; assert.equal(h.events.at(-1).status, 'ready'); await h.runtime.stop(); });
  console.log(JSON.stringify({ mode: 'injected_unit_seams', passed, modelsExecuted: 0, hardwareUsed: false }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
