'use strict';
// Classic owned worker: upstream ESM is imported only after guards are installed.
// UMD WASM loaders need classic importScripts to publish ModuleFactory.
const MANIFEST_SHA = 'ac02f689b9ec4a105f4d0e6aa4093698d3ffbf430acc4d1849426c7f0bb3ecf1';
const INVENTORY = new Set([
  '/visual/asset-manifest.json', '/visual/vision_bundle.mjs',
  '/visual/wasm/vision_wasm_internal.js', '/visual/wasm/vision_wasm_internal.wasm',
  '/visual/wasm/vision_wasm_nosimd_internal.js', '/visual/wasm/vision_wasm_nosimd_internal.wasm',
  '/visual/face_landmarker.task',
]);
const nativeFetch = self.fetch.bind(self);
const nativeImportScripts = self.importScripts.bind(self);
let blocked = 0;
let inventory = new Map();
let task = null;
let generation = null;
let closing = false;
let lastTimestamp = -Infinity;
const deny = () => { blocked = Math.min(1000, blocked + 1); throw new TypeError('visual_network_blocked'); };
function allowed(value, method = 'GET') {
  if (typeof value !== 'string' || method !== 'GET') return deny();
  const url = new URL(value, self.location.origin);
  if ((value !== url.href && value !== url.pathname) || url.origin !== self.location.origin ||
      url.search || url.hash || url.username || url.password || !INVENTORY.has(url.pathname)) return deny();
  return url;
}
async function digest(raw) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw)), (v) => v.toString(16).padStart(2, '0')).join('');
}
async function boundedBody(response, limit) {
  if (!response.ok || response.redirected || !response.body) throw new Error('asset_unavailable');
  const reader = response.body.getReader(); let size = 0; const chunks = [];
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error('asset_size');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); }
  const raw = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { raw.set(chunk, offset); offset += chunk.byteLength; }
  return raw;
}
self.fetch = async function (input, options = {}) {
  const url = allowed(input, options.method || 'GET');
  if (options.body !== undefined && options.body !== null) return deny();
  if (options.credentials && !['omit', 'same-origin'].includes(options.credentials)) return deny();
  if (options.redirect && options.redirect !== 'error') return deny();
  const asset = inventory.get(url.pathname);
  const limit = url.pathname === '/visual/asset-manifest.json' ? 16000 : asset?.bytes;
  if (!Number.isInteger(limit) || limit <= 0 || limit > 12000000) throw new Error('asset_unavailable');
  const response = await nativeFetch(url.href, { method: 'GET', credentials: 'omit', redirect: 'error', cache: 'no-store', signal: options.signal });
  if (response.url && response.url !== url.href) throw new Error('asset_redirect');
  const raw = await boundedBody(response, limit);
  const expected = url.pathname === '/visual/asset-manifest.json' ? MANIFEST_SHA : asset.sha256;
  if (await digest(raw) !== expected || (asset && raw.length !== asset.bytes)) throw new Error('asset_binding');
  return new Response(raw, { status: 200, headers: { 'Content-Type': asset?.mediaType || 'application/json' } });
};
// WASM loader fallback may use XHR. Permit only closed local GETs, never payloads.
if (self.XMLHttpRequest) {
  const NativeXHR = self.XMLHttpRequest;
  self.XMLHttpRequest = class extends NativeXHR {
    open(method, value, async = true) { const url = allowed(value, method); super.open('GET', url.href, async); }
    send(body) { if (body !== undefined && body !== null) return deny(); super.send(null); }
    set withCredentials(value) { if (value) return deny(); super.withCredentials = false; }
    get withCredentials() { return false; }
  };
}
for (const name of ['WebSocket', 'EventSource', 'WebTransport', 'RTCPeerConnection']) {
  if (name in self) self[name] = class { constructor() { deny(); } };
}
if (self.navigator && 'sendBeacon' in self.navigator) {
  Object.defineProperty(self.navigator, 'sendBeacon', { value: () => deny() });
}
self.importScripts = (...urls) => {
  if (urls.length !== 1) return deny();
  const url = allowed(urls[0]);
  if (!['/visual/wasm/vision_wasm_internal.js', '/visual/wasm/vision_wasm_nosimd_internal.js'].includes(url.pathname)) return deny();
  nativeImportScripts(url.href);
};
function emit(value) { self.postMessage({ ...value, generation, networkBlockedCount: blocked }); }
function fail(reason, id = null) { emit({ type: 'failed', id, reason }); }
function project(result, width, height, lips) {
  if (!result || !Array.isArray(result.faceLandmarks) || result.faceLandmarks.length > 2) throw new Error('invalid_result');
  if (result.faceLandmarks.length === 0) return { status: 'no_face', outline: [], bounds: null, aperture: null };
  if (result.faceLandmarks.length !== 1) return { status: 'multiple_faces', outline: [], bounds: null, aperture: null };
  const points = result.faceLandmarks[0];
  if (!Array.isArray(points) || points.length !== 478 || points.some((p) => !p || !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1)) throw new Error('invalid_result');
  const outline = lips.map(({ start, end }) => ({ x1: points[start].x, y1: points[start].y, x2: points[end].x, y2: points[end].y }));
  const x = Math.min(...points.map((p) => p.x)); const y = Math.min(...points.map((p) => p.y));
  const bounds = { x, y, width: Math.max(...points.map((p) => p.x)) - x, height: Math.max(...points.map((p) => p.y)) - y };
  const distance = (a, b) => Math.hypot((points[a].x - points[b].x) * width, (points[a].y - points[b].y) * height);
  const denominator = distance(61, 291);
  const aperture = denominator >= 1 ? distance(13, 14) / denominator : null;
  if (!outline.length || outline.length > 100 || bounds.width <= 0 || bounds.height <= 0 || aperture === null || !Number.isFinite(aperture) || aperture > 2) throw new Error('invalid_result');
  return { status: 'tracking', outline, bounds, aperture };
}
let lips = [];
async function initialize(message) {
  if (generation !== null || !Number.isSafeInteger(message.generation)) return fail('invalid_message');
  generation = message.generation;
  try {
    const response = await self.fetch('/visual/asset-manifest.json'); const manifest = await response.json();
    if (manifest.schemaVersion !== 1 || manifest.packageVersion !== '1.0.1' || !Array.isArray(manifest.assets)) throw new Error('asset_binding');
    inventory = new Map(manifest.assets.filter((a) => INVENTORY.has(a.route)).map((a) => [a.route, a]));
    if (inventory.size !== 6) throw new Error('asset_binding');
    const { FaceLandmarker, FilesetResolver } = await import('/visual/vision_bundle.mjs');
    if (closing) return;
    const model = new Uint8Array(await (await self.fetch('/visual/face_landmarker.task')).arrayBuffer());
    if (closing) return;
    const fileset = await FilesetResolver.forVisionTasks('/visual/wasm');
    if (closing) return;
    task = await FaceLandmarker.createFromOptions(fileset, { baseOptions: { modelAssetBuffer: model, delegate: 'CPU' }, runningMode: 'VIDEO', numFaces: 2, minFaceDetectionConfidence: 0.5, minFacePresenceConfidence: 0.5, minTrackingConfidence: 0.5, outputFaceBlendshapes: false, outputFacialTransformationMatrixes: false });
    if (closing) { task.close(); task = null; return; }
    lips = FaceLandmarker.FACE_LANDMARKS_LIPS;
    if (!Array.isArray(lips) || lips.length > 100) throw new Error('invalid_result');
    emit({ type: 'ready', manifestSha256: MANIFEST_SHA });
  } catch (_) { if (!closing) fail('initialization_failed'); }
}
self.onmessage = async ({ data }) => {
  const frame = data?.frame;
  try {
    if (!data || typeof data !== 'object') throw new Error('invalid_message');
    if (data.type === 'init') { await initialize(data); return; }
    if (data.generation !== generation) throw new Error('stale_generation');
    if (data.type === 'close') {
      closing = true;
      if (task) { task.close(); task = null; }
      inventory.clear(); lips = [];
      // Upstream close queues an async metrics fetch. Guards reject it before I/O.
      await Promise.resolve();
      emit({ type: 'closed' }); self.close(); return;
    }
    if (data.type !== 'frame' || closing || !task || !Number.isSafeInteger(data.id) ||
        !Number.isFinite(data.timestamp) || data.timestamp < lastTimestamp + 200 ||
        !frame || !Number.isInteger(frame.width) || !Number.isInteger(frame.height) ||
        frame.width <= 0 || frame.width > 640 || frame.height <= 0 || frame.height > 480) throw new Error('invalid_message');
    lastTimestamp = data.timestamp;
    const started = performance.now();
    const value = project(task.detectForVideo(frame, data.timestamp), frame.width, frame.height, lips);
    emit({ type: 'result', id: data.id, timestamp: data.timestamp, elapsedMilliseconds: performance.now() - started, ...value });
  } catch (_) { if (!closing) fail('inference_failed', Number.isSafeInteger(data?.id) ? data.id : null); }
  finally { if (frame && typeof frame.close === 'function') frame.close(); }
};
