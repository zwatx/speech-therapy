// Optional visual aid only. Caller owns camera consent, stream and mirror.
// No microphone, track ownership, uploads, storage, identity or speech scoring.
const MANIFEST_SHA = 'ac02f689b9ec4a105f4d0e6aa4093698d3ffbf430acc4d1849426c7f0bb3ecf1';
const INIT_MS = 15000;
const FRAME_MS = 1500;
const CAPTURE_MS = 1000;
const CLOSE_MS = 500;
const INTERVAL_MS = 200;
const MAX_AGE_MS = 500;
const EMPTY = { outline: [], bounds: null, aperture: null };

export class LocalVisualRuntime {
  constructor() { this.generation = 0; this.session = null; this.pendingCleanup = Promise.resolve({ cleanupConfirmed: true, networkBlockedCount: 0 }); }

  async start(video, callback) {
    const generation = ++this.generation;
    const previous = this.session; this.session = null;
    await this.dispose(previous);
    await this.pendingCleanup;
    if (generation !== this.generation) throw new Error('cancelled');
    if (!video || typeof callback !== 'function' || !Number.isFinite(video.videoWidth) ||
        video.videoWidth <= 0 || video.videoHeight <= 0 || typeof createImageBitmap !== 'function' ||
        typeof Worker !== 'function' || document.visibilityState === 'hidden') throw new Error('visual_unavailable');
    const session = { generation, video, callback, worker: null, ready: false, settled: false,
      inFlight: false, frameId: 0, frameTimestamp: 0, pumpTimer: null, deadline: null,
      closing: false, cleanup: null, blocked: 0 };
    this.session = session;
    const promise = new Promise((resolve, reject) => { session.resolve = resolve; session.reject = reject; });
    session.onHidden = () => { if (document.visibilityState === 'hidden') this.fail(session, 'backgrounded'); };
    document.addEventListener('visibilitychange', session.onHidden);
    try {
      this.notify(session, { status: 'initializing', ...EMPTY });
      if (!this.current(session)) return promise;
      session.worker = new Worker('/visual-worker.js');
      session.worker.onerror = () => this.fail(session, 'worker_failed');
      session.worker.onmessage = ({ data }) => this.receive(session, data);
      session.deadline = setTimeout(() => this.fail(session, 'initialization_timeout'), INIT_MS);
      session.worker.postMessage({ type: 'init', generation });
    } catch (_) { this.fail(session, 'initialization_failed'); }
    return promise;
  }

  current(session) { return this.session === session && session.generation === this.generation && !session.closing; }

  notify(session, value) {
    if (!this.current(session)) return;
    try { session.callback({ ...value, networkBlockedCount: session.blocked, researchOnly: true,
      coordinateSpace: 'unmirrored_image', pronunciationFeedbackEligible: false }); }
    catch (_) { this.stop(); }
  }

  receive(session, data) {
    if (!this.current(session) || !data || data.generation !== session.generation) return;
    if (!Number.isInteger(data.networkBlockedCount) || data.networkBlockedCount < 0 || data.networkBlockedCount > 1000) return this.fail(session, 'invalid_result');
    session.blocked = data.networkBlockedCount;
    if (data.type === 'ready') {
      if (session.ready || data.manifestSha256 !== MANIFEST_SHA) return this.fail(session, 'invalid_result');
      clearTimeout(session.deadline); session.deadline = null;
      session.ready = true; session.settled = true; session.resolve();
      this.notify(session, { status: 'ready', ...EMPTY }); this.schedule(session); return;
    }
    if (data.type === 'failed') return this.fail(session, 'inference_failed');
    if (data.type !== 'result' || !session.ready || !session.inFlight || data.id !== session.frameId ||
        data.timestamp !== session.frameTimestamp) return this.fail(session, 'invalid_result');
    clearTimeout(session.deadline); session.deadline = null; session.inFlight = false;
    if (!['tracking', 'no_face', 'multiple_faces'].includes(data.status) || !Array.isArray(data.outline) ||
        data.outline.length > 100 || !Number.isFinite(data.elapsedMilliseconds) || data.elapsedMilliseconds < 0) return this.fail(session, 'invalid_result');
    const valid = (value) => Number.isFinite(value) && value >= 0 && value <= 1;
    if (data.status === 'tracking') {
      if (!data.outline.length || data.outline.some((line) => !line || !['x1', 'y1', 'x2', 'y2'].every((key) => valid(line[key]))) ||
          !data.bounds || !['x', 'y', 'width', 'height'].every((key) => valid(data.bounds[key])) ||
          data.bounds.width <= 0 || data.bounds.height <= 0 || !Number.isFinite(data.aperture) || data.aperture < 0 || data.aperture > 2) return this.fail(session, 'invalid_result');
    } else if (data.outline.length || data.bounds !== null || data.aperture !== null) return this.fail(session, 'invalid_result');
    if (performance.now() - data.timestamp > MAX_AGE_MS) this.notify(session, { status: 'unavailable', reason: 'stale_observation', ...EMPTY });
    else this.notify(session, { status: data.status, outline: data.outline, bounds: data.bounds, aperture: data.aperture });
    this.schedule(session);
  }

  schedule(session) {
    if (this.current(session)) session.pumpTimer = setTimeout(() => this.capture(session), INTERVAL_MS);
  }

  async capture(session) {
    if (!this.current(session) || session.inFlight) return;
    if (document.visibilityState === 'hidden') return this.fail(session, 'backgrounded');
    const video = session.video;
    if (video.readyState < 2 || video.videoWidth <= 0 || video.videoHeight <= 0) return this.fail(session, 'video_unavailable');
    const scale = Math.min(1, 640 / video.videoWidth, 480 / video.videoHeight);
    const width = Math.max(1, Math.floor(video.videoWidth * scale));
    const height = Math.max(1, Math.floor(video.videoHeight * scale));
    session.inFlight = true; session.frameTimestamp = performance.now();
    session.deadline = setTimeout(() => this.fail(session, 'frame_capture_timeout'), CAPTURE_MS);
    let frame = null;
    try {
      frame = await createImageBitmap(video, { resizeWidth: width, resizeHeight: height, resizeQuality: 'low' });
      if (!this.current(session)) { frame.close(); return; }
      clearTimeout(session.deadline);
      session.deadline = setTimeout(() => this.fail(session, 'inference_timeout'), FRAME_MS);
      session.frameId += 1;
      session.worker.postMessage({ type: 'frame', generation: session.generation, id: session.frameId,
        timestamp: session.frameTimestamp, frame }, [frame]);
      frame = null; // Ownership transferred. Worker closes it in its finally.
    } catch (_) { if (frame) frame.close(); this.fail(session, 'frame_capture_failed'); }
  }

  fail(session, reason) {
    if (!this.current(session)) return;
    const callback = session.callback;
    this.session = null; this.generation += 1;
    this.dispose(session);
    // Invalidate failed ownership before user code can start a new generation.
    try { callback({ status: 'failed', reason, ...EMPTY, networkBlockedCount: session.blocked,
      researchOnly: true, coordinateSpace: 'unmirrored_image', pronunciationFeedbackEligible: false }); } catch (_) { /* failed session already stopped */ }
  }

  stop() {
    this.generation += 1;
    const session = this.session; this.session = null;
    return this.dispose(session);
  }

  dispose(session) {
    if (!session) return this.pendingCleanup;
    if (session.cleanup) return session.cleanup;
    session.closing = true;
    clearTimeout(session.deadline); clearTimeout(session.pumpTimer);
    document.removeEventListener('visibilitychange', session.onHidden);
    session.video = null; session.callback = null;
    if (!session.settled) { session.settled = true; session.reject(new Error('cancelled')); }
    session.cleanup = new Promise((resolve) => {
      const worker = session.worker; session.worker = null;
      if (!worker) { resolve({ cleanupConfirmed: true, networkBlockedCount: session.blocked }); return; }
      let finished = false;
      const finish = (confirmed) => {
        if (finished) return;
        finished = true; clearTimeout(timer); worker.onmessage = null; worker.onerror = null; worker.terminate();
        resolve({ cleanupConfirmed: confirmed, networkBlockedCount: session.blocked });
      };
      const timer = setTimeout(() => finish(false), CLOSE_MS);
      worker.onmessage = ({ data }) => {
        if (data?.type === 'closed' && data.generation === session.generation && Number.isInteger(data.networkBlockedCount) && data.networkBlockedCount >= 0 && data.networkBlockedCount <= 1000) {
          session.blocked = data.networkBlockedCount; finish(true);
        }
      };
      worker.onerror = () => finish(false);
      try { worker.postMessage({ type: 'close', generation: session.generation }); } catch (_) { finish(false); }
    });
    this.pendingCleanup = Promise.all([this.pendingCleanup, session.cleanup]).then(([previous, current]) => ({
      cleanupConfirmed: previous.cleanupConfirmed && current.cleanupConfirmed,
      networkBlockedCount: Math.min(1000, previous.networkBlockedCount + current.networkBlockedCount),
    }));
    return session.cleanup;
  }
}
