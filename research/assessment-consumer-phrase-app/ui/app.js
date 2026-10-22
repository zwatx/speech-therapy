'use strict';

const ui = Object.fromEntries([
  'load-status', 'practice-body', 'phrase', 'phrase-heading', 'phrase-focus', 'phrase-cue',
  'audio-file', 'file-status', 'playback', 'audio', 'clear', 'age', 'consent', 'check',
  'cancel', 'refresh-status', 'check-form', 'check-status', 'result', 'result-message', 'phrase-result',
  'sound-result', 'alignment-note', 'cleanup-result',
].map((id) => [id, document.getElementById(id)]));

const state = { catalog: null, capture: null, generation: 0, active: null, polling: false, timer: null, leaving: false };
const MAX_WAV_BYTES = 132096;
const SETTLED = new Set(['complete', 'failed', 'cancelled']);

// Inspect the original WAV; never reinterpret or resample unsupported audio.
function inspectWav(buffer) {
  if (buffer.byteLength < 44 || buffer.byteLength > MAX_WAV_BYTES) throw new Error('size');
  const view = new DataView(buffer);
  const tag = (offset) => String.fromCharCode(...new Uint8Array(buffer, offset, 4));
  if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE' || view.getUint32(4, true) + 8 !== buffer.byteLength) throw new Error('format');
  let format = null;
  let samples = null;
  for (let offset = 12; offset + 8 <= buffer.byteLength;) {
    const size = view.getUint32(offset + 4, true);
    const end = offset + 8 + size;
    if (end > buffer.byteLength) throw new Error('format');
    if (tag(offset) === 'fmt ') {
      if (format || size < 16) throw new Error('format');
      format = {
        encoding: view.getUint16(offset + 8, true), channels: view.getUint16(offset + 10, true),
        rate: view.getUint32(offset + 12, true), bytesPerSecond: view.getUint32(offset + 16, true),
        alignment: view.getUint16(offset + 20, true), bits: view.getUint16(offset + 22, true),
      };
    }
    if (tag(offset) === 'data') {
      if (samples !== null) throw new Error('format');
      samples = size;
    }
    offset = end + (size % 2);
  }
  if (!format || samples === null || format.encoding !== 1 || format.channels !== 1 || format.rate !== 16000 || format.bits !== 16 || format.bytesPerSecond !== 32000 || format.alignment !== 2 || samples % 2) throw new Error('format');
  const seconds = samples / 32000;
  if (seconds < 0.1 || seconds > 4) throw new Error('duration');
  return seconds;
}

function base64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return btoa(binary);
}

function validAge() {
  return /^[6-9]$|^1[0-2]$/.test(ui.age.value);
}

function readiness() {
  if (!state.capture) return 'Choose a supported recording to begin.';
  if (state.capture.used) return 'This recording has already been submitted. Choose a new recording for another check.';
  if (!validAge()) return 'Choose the real age, 6–12, to enable checking. You can listen without it.';
  if (!ui.consent.checked) return 'Agree to local checking to enable Check.';
  return 'Ready when you are. Checking begins only when you choose Check this recording.';
}

function canCheck() {
  return Boolean(state.catalog && state.capture && !state.capture.used && validAge() && ui.consent.checked && !state.active);
}

function updateControls(message) {
  const active = state.active;
  ui.check.disabled = !canCheck();
  ui.clear.disabled = !state.capture && !ui['audio-file'].value && !active && ui.result.hidden;
  ui.cancel.hidden = !active || !active.jobId || active.cancelRequested || active.status === 'cleanup_unknown';
  ui['refresh-status'].hidden = !active?.jobId || !active.statusUnavailable;
  if (message !== undefined) ui['check-status'].textContent = message;
  else if (!active) ui['check-status'].textContent = readiness();
}

function stopPlayback() {
  ui.audio.pause();
  ui.audio.removeAttribute('src');
  ui.audio.load();
  if (state.capture?.url) URL.revokeObjectURL(state.capture.url);
  ui.playback.hidden = true;
}

function invalidate() {
  state.generation += 1;
  ui.result.hidden = true;
  if (state.active) {
    state.active.stale = true;
    requestCancel();
  }
  updateControls();
}

function showPhrase() {
  const prompt = state.catalog.prompts.find((item) => item.id === ui.phrase.value);
  ui['phrase-heading'].textContent = prompt.transcript;
  ui['phrase-focus'].textContent = prompt.focus;
  ui['phrase-cue'].textContent = prompt.cue;
}

async function selectFile() {
  invalidate();
  stopPlayback();
  state.capture = null;
  const generation = state.generation;
  ui.age.value = '';
  ui.consent.checked = false;
  const file = ui['audio-file'].files[0];
  ui['file-status'].textContent = file ? 'Checking the WAV format…' : 'No recording chosen.';
  updateControls();
  if (!file) return;
  try {
    if (file.size > MAX_WAV_BYTES) throw new Error('size');
    const buffer = await file.arrayBuffer();
    const seconds = inspectWav(buffer);
    if (generation !== state.generation) return;
    const url = URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }));
    state.capture = { requestId: crypto.randomUUID(), buffer, url, used: false };
    ui.audio.src = url;
    ui.playback.hidden = false;
    ui['file-status'].textContent = `${file.name} · ${seconds.toFixed(2)} seconds · Ready to listen.`;
  } catch (error) {
    if (generation !== state.generation) return;
    ui['file-status'].textContent = error.message === 'duration'
      ? 'Choose a recording between 0.1 and 4 seconds long.'
      : 'This file is not supported. Choose a mono, 16 kHz, 16-bit PCM WAV of 0.1–4 seconds (up to 132,096 bytes).';
  }
  updateControls();
}

async function post(path, body, keepalive = false) {
  return fetch(path, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.catalog.csrfToken },
    body: JSON.stringify(body), keepalive,
  });
}

function serviceError(tag) {
  const messages = {
    busy: 'The local service is busy. This recording was not checked. Choose a new recording after the other check finishes.',
    blocked: 'The service cannot confirm cleanup from an earlier check. Further checking is paused.',
    cleanup_unknown: 'The service cannot confirm cleanup. Further checking is paused.',
    capture_reused: 'This recording has already been submitted. Choose a new recording for another check.',
    source_changed: 'The local research source changed. Checking is unavailable until the service is repaired.',
    source_unavailable: 'The local research source is unavailable. Checking cannot begin.',
  };
  return messages[tag] || 'The local service could not accept this recording. Check the file format, age, and consent before choosing a new recording.';
}

function schedulePoll() {
  clearTimeout(state.timer);
  if (state.active?.jobId && !state.leaving) state.timer = setTimeout(poll, 1000);
}

async function startCheck() {
  if (!canCheck()) return;
  const capture = state.capture;
  capture.used = true;
  const active = { generation: state.generation, requestId: capture.requestId, jobId: null, stale: false, cancelRequested: false, cancelAcknowledged: false, status: 'submitting', statusUnavailable: false };
  state.active = active;
  ui.result.hidden = true;
  updateControls('Sending this recording to the local service…');
  try {
    const response = await post('/api/check', {
      requestId: capture.requestId, promptId: ui.phrase.value, ageYears: Number(ui.age.value), consent: true, audioBase64: base64(capture.buffer),
    });
    const data = await response.json();
    if (state.active !== active) return;
    if (response.status !== 202) {
      // Only an explicit rejection establishes that this request was not started.
      if (response.status >= 400 && response.status < 500 || response.status === 503) {
        state.active = null;
        updateControls(serviceError(data.error));
        return;
      }
      throw new Error('unknown_submission');
    }
    if (typeof data.jobId !== 'string' || !/^[0-9a-f-]{36}$/i.test(data.jobId)) throw new Error('unknown_submission');
    if (data.jobId !== active.requestId) throw new Error('unknown_submission');
    active.jobId = data.jobId;
    active.status = 'processing';
    if (active.stale || active.cancelRequested || state.leaving) await requestCancel();
    else updateControls('Checking this recording… This may take a little while.');
    schedulePoll();
  } catch {
    if (state.active !== active) return;
    active.jobId = active.requestId;
    active.status = 'submission_unknown';
    updateControls('The service response was lost. Looking up this check without submitting the recording again…');
    if (active.stale || active.cancelRequested || state.leaving) await requestCancel();
    schedulePoll();
  }
}

async function requestCancel() {
  const active = state.active;
  if (!active) return;
  active.stale = true;
  active.cancelRequested = true;
  ui.result.hidden = true;
  updateControls('Cancellation requested. Waiting for the service to confirm that checking and cleanup have finished.');
  if (!active.jobId || active.cancelInFlight || active.cancelAcknowledged) return;
  active.cancelInFlight = true;
  try {
    const response = await post('/api/cancel', { jobId: active.jobId }, state.leaving);
    if (response.status !== 200) throw new Error('cancel');
    const data = await response.json();
    if (state.active !== active) return;
    if (data.jobId !== active.jobId || !['cancelling', 'cancelled', 'complete', 'cleanup_unknown'].includes(data.status)) throw new Error('cancel');
    active.cancelAcknowledged = true;
    active.status = data.status;
    // Poll the job receipt even if cancel says complete; only it establishes cleanup.
    if (data.status === 'cleanup_unknown') updateControls('Processing and cleanup could not be confirmed. Private check files are retained on this computer, and further checks are blocked.');
  } catch {
    if (state.active !== active) return;
    updateControls('Cancellation could not be confirmed. Still checking the service status; further checks remain blocked.');
  } finally {
    active.cancelInFlight = false;
    schedulePoll();
  }
}

function renderResult(result) {
  ui.result.hidden = false;
  ui['result-message'].textContent = result.message || 'The check finished.';
  ui['phrase-result'].textContent = result.phraseMatched
    ? 'The check matched the chosen phrase.'
    : result.kind === 'phrase_mismatch' ? 'The check did not match the chosen phrase. This does not tell us which sound was different.'
      : 'A phrase match could not be established from this recording.';
  ui['sound-result'].textContent = result.soundAnalysisAvailable || result.scoredOccurrences > 0
    ? 'Uncertain. Sound analysis was computed, but it cannot tell you whether individual sounds were correct.'
    : 'No usable individual sound result is available for this recording.';
  ui['alignment-note'].textContent = result.alignmentUnverified
    ? 'The sound locations are unverified. A phrase match does not verify the timing or pronunciation of any individual sound.'
    : 'This research check does not provide sound corrections or a pronunciation grade.';
  ui['cleanup-result'].textContent = result.cleanupConfirmed
    ? 'The service confirmed cleanup of its temporary check files. Your recording stays in this tab until you clear it or leave.'
    : 'Cleanup could not be confirmed. A temporary copy may remain on this computer; further checks are blocked.';
}

async function poll() {
  const active = state.active;
  if (!active?.jobId || state.polling || state.leaving) return;
  clearTimeout(state.timer);
  state.polling = true;
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(active.jobId)}`, { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error('status');
    const data = await response.json();
    if (state.active !== active) return;
    if (data.jobId !== active.jobId || !['processing', 'cancelling', 'cancelled', 'complete', 'failed', 'cleanup_unknown'].includes(data.status)) throw new Error('status');
    active.statusUnavailable = false;
    active.status = data.status;
    // Cancelled jobs have no result; all settlement needs the explicit cleanup receipt.
    const cleanupConfirmed = data.cleanupConfirmed === true && (!data.result || data.result.cleanupConfirmed === true);
    if (data.status === 'cleanup_unknown' || SETTLED.has(data.status) && !cleanupConfirmed) {
      active.status = 'cleanup_unknown';
      active.statusUnavailable = true;
      if (!active.stale && active.generation === state.generation && data.result) renderResult(data.result);
      updateControls('Processing and cleanup could not be confirmed. Private check files are retained on this computer, and further checks are blocked.');
      return;
    }
    if (SETTLED.has(data.status)) {
      if (!active.stale && active.generation === state.generation && data.result) renderResult(data.result);
      state.active = null;
      updateControls(data.status === 'cancelled' || active.stale
        ? 'The service has finished and confirmed cleanup. Choose a new recording when you are ready.'
        : 'Check finished. You can listen again, or choose a new recording for another check.');
      return;
    }
    // An early cancellation may reach the service before an ambiguous submission is admitted.
    // Preserve that intent and retry only cancellation once the job is known to exist.
    if (data.status === 'processing' && active.cancelRequested && !active.cancelAcknowledged) {
      await requestCancel();
      return;
    }
    updateControls(active.cancelRequested || data.status === 'cancelling'
      ? 'Cancellation requested. Waiting for the service to confirm that checking and cleanup have finished.'
      : 'Checking this recording… This may take a little while.');
    schedulePoll();
  } catch {
    if (state.active !== active) return;
    active.statusUnavailable = true;
    updateControls('The service status is unavailable. The check may still be running. Further checks are blocked; choose Check service status to reconnect.');
  } finally {
    state.polling = false;
  }
}

ui.phrase.addEventListener('change', () => { invalidate(); showPhrase(); });
ui.age.addEventListener('change', invalidate);
ui.consent.addEventListener('change', invalidate);
ui['audio-file'].addEventListener('change', selectFile);
ui['check-form'].addEventListener('submit', (event) => { event.preventDefault(); startCheck(); });
ui.cancel.addEventListener('click', requestCancel);
ui['refresh-status'].addEventListener('click', () => { updateControls('Checking the service status…'); poll(); });
ui.clear.addEventListener('click', () => {
  invalidate(); stopPlayback(); state.capture = null; ui['audio-file'].value = '';
  ui['file-status'].textContent = 'Recording cleared from this tab.'; updateControls();
});
ui.audio.addEventListener('error', () => {
  if (state.capture) ui['file-status'].textContent = 'This browser could not play the recording. The WAV format was checked, but playback is unavailable.';
});
window.addEventListener('pagehide', () => {
  state.leaving = true;
  state.generation += 1;
  clearTimeout(state.timer);
  stopPlayback();
  state.capture = null;
  ui['audio-file'].value = '';
  ui.result.hidden = true;
  ui['file-status'].textContent = 'Recording cleared from this tab.';
  if (state.active) {
    state.active.stale = true;
    state.active.cancelRequested = true;
    if (state.active.jobId) post('/api/cancel', { jobId: state.active.jobId }, true).catch(() => {});
  }
});
window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  state.leaving = false;
  updateControls(state.active ? 'Reconnecting to confirm the earlier check and cleanup have finished…' : undefined);
  schedulePoll();
});

async function initialize() {
  try {
    const response = await fetch('/api/catalog', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error('catalog');
    const catalog = await response.json();
    if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.prompts) || !catalog.prompts.length || typeof catalog.csrfToken !== 'string') throw new Error('catalog');
    if (!catalog.prompts.every((prompt) => ['id', 'transcript', 'focus', 'cue'].every((key) => typeof prompt[key] === 'string'))) throw new Error('catalog');
    state.catalog = catalog;
    for (const prompt of catalog.prompts) {
      const option = document.createElement('option'); option.value = prompt.id; option.textContent = prompt.transcript; ui.phrase.append(option);
    }
    showPhrase();
    ui['load-status'].hidden = true;
    ui['practice-body'].hidden = false;
    updateControls();
  } catch {
    ui['load-status'].textContent = 'The local phrase service is unavailable. Reload this page once the service is running.';
  }
}
initialize();
