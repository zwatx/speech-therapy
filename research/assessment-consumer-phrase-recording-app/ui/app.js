'use strict';

const ui = Object.fromEntries([
  'load-status', 'practice-body', 'phrase', 'phrase-heading', 'phrase-focus', 'phrase-cue',
  'audio-file', 'file-status', 'playback', 'audio', 'clear', 'age', 'consent', 'check',
  'cancel', 'refresh-status', 'check-form', 'check-status', 'result', 'result-message', 'phrase-result',
  'sound-result', 'alignment-note', 'cleanup-result', 'record', 'stop-recording',
  'discard-recording', 'record-status', 'record-progress', 'record-time', 'record-level',
  'prompt-kind', 'word-filters', 'sound-filter', 'position-filter', 'word-search', 'prompt-list-label',
  'library-count', 'prompt-availability', 'context', 'context-note', 'age-field', 'start-session',
  'guided-session', 'session-heading', 'session-status', 'session-summary', 'next-word',
  'end-session', 'practice-selected', 'recheck-selected', 'recording-workspace', 'session-intro',
].map((id) => [id, document.getElementById(id)]));

const state = { catalog: null, capture: null, generation: 0, active: null, polling: false, timer: null, leaving: false, recording: null, pendingFile: null, session: null };
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
  if (state.recording) return 'Finish recording and microphone cleanup before checking.';
  if (state.pendingFile) return 'Waiting for the selected recording to be ready.';
  if (!state.capture) return 'Choose a supported recording to begin.';
  if (state.capture.used) return 'This recording has already been submitted. Choose a new recording for another check.';
  const prompt = selectedPrompt();
  if (!prompt?.modelSupported) return 'This selection is for recording and listening practice only. No model check is available.';
  if (!prompt.supportedContexts.includes(ui.context.value)) return 'Phrase checking is available only in child sound research for a known age of 6–12. You can still record and listen.';
  if (ui.context.value === 'child-research' && !validAge()) return 'Choose the real age, 6–12, to enable child sound research. You can listen without it.';
  if (!ui.consent.checked) return 'Agree to local checking to enable Check.';
  return 'Ready when you are. Checking begins only when you choose Check this recording.';
}

function canCheck() {
  return Boolean(state.catalog && state.capture && !state.capture.used && contextReady() && ui.consent.checked && !state.active && !state.recording && !state.pendingFile && !state.leaving && state.session?.phase !== 'summary');
}

function updateControls(message) {
  const active = state.active;
  ui.check.disabled = !canCheck();
  const recording = state.recording;
  const phase = recording?.phase;
  ui.record.hidden = Boolean(recording);
  ui.record.disabled = !state.catalog || !selectedPrompt() || !recorder || state.session?.phase === 'summary' || Boolean(active || recording || state.pendingFile || state.leaving);
  ui['stop-recording'].hidden = !recording || !['recording', 'finishing'].includes(phase);
  ui['stop-recording'].disabled = phase !== 'recording';
  ui['discard-recording'].hidden = !recording || phase === 'blocked';
  ui['discard-recording'].disabled = !recording || phase === 'cancelling' || phase === 'blocked';
  ui['record-progress'].hidden = !recording || !['recording', 'finishing'].includes(phase);
  ui.clear.disabled = !state.capture && !ui['audio-file'].value && !active && !recording && !state.pendingFile && ui.result.hidden;
  ui.cancel.hidden = !active || !active.jobId || active.cancelRequested || active.status === 'cleanup_unknown';
  ui['refresh-status'].hidden = !active?.jobId || !active.statusUnavailable;
  ui['age-field'].hidden = ui.context.value !== 'child-research';
  updateSessionControls();
  const checkMessage = message !== undefined ? message : !active ? readiness() : null;
  if (checkMessage !== null && ui['check-status'].textContent !== checkMessage) ui['check-status'].textContent = checkMessage;
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
  const cleanup = cancelRecording();
  state.pendingFile = null;
  updateControls();
  return cleanup;
}

function selectedPrompt() {
  return state.catalog?.prompts?.find((item) => item.id === ui.phrase.value);
}

function contextReady() {
  const prompt = selectedPrompt();
  return Boolean(prompt?.modelSupported && prompt.supportedContexts.includes(ui.context.value)
    && (ui.context.value === 'recognition' || ui.context.value === 'child-research' && validAge()));
}

function filteredPrompts() {
  const query = ui['word-search'].value.trim().toLocaleLowerCase();
  return (state.catalog?.prompts || []).filter((prompt) => {
    if (prompt.kind !== ui['prompt-kind'].value) return false;
    if (prompt.kind === 'phrase') return true;
    return (!ui['sound-filter'].value || prompt.soundID === ui['sound-filter'].value)
      && (!ui['position-filter'].value || prompt.position === ui['position-filter'].value)
      && (!query || prompt.transcript.toLocaleLowerCase().includes(query));
  });
}

function showPhrase() {
  const prompt = selectedPrompt();
  ui['phrase-heading'].textContent = prompt?.transcript || 'No words in this selection';
  ui['phrase-focus'].textContent = prompt?.focus || '';
  ui['phrase-cue'].textContent = prompt?.cue || 'Try a different sound group, position, or search.';
  ui['prompt-availability'].textContent = !prompt ? '' : !prompt.modelSupported
    ? 'Recording and listening practice only. This sound group has no supported model check.'
    : !prompt.supportedContexts.includes(ui.context.value)
      ? 'Record and listen, or choose child sound research with a genuine age of 6–12 to check this phrase.'
      : ui.context.value === 'recognition' ? 'Recognition checks only whether this word was matched; it does not assess individual sounds.'
        : 'Child research results for individual sounds remain uncertain.';
}

function clearLocalRecording() {
  invalidate();
  stopPlayback();
  state.capture = null;
  ui['audio-file'].value = '';
  ui.age.value = '';
  ui.consent.checked = false;
  ui['file-status'].textContent = 'No recording chosen.';
}

function renderLibrary() {
  const prompts = filteredPrompts();
  const selected = prompts.some((prompt) => prompt.id === ui.phrase.value) ? ui.phrase.value : prompts[0]?.id || '';
  ui.phrase.replaceChildren();
  for (const prompt of prompts) {
    const option = document.createElement('option');
    option.value = prompt.id;
    option.textContent = prompt.kind === 'word'
      ? `${prompt.transcript} · ${prompt.soundID.toUpperCase()} · ${prompt.position}${prompt.modelSupported ? '' : ' · practice only'}`
      : prompt.transcript;
    ui.phrase.append(option);
  }
  ui.phrase.value = selected;
  ui['word-filters'].hidden = ui['prompt-kind'].value !== 'word';
  ui['prompt-list-label'].textContent = ui['prompt-kind'].value === 'word' ? 'Choose a word' : 'Choose a phrase';
  ui['library-count'].textContent = `${prompts.length.toLocaleString()} ${ui['prompt-kind'].value === 'word' ? 'word entries' : 'phrases'} in this selection`;
  showPhrase();
  updateControls();
}

function changeLibrary() {
  if (state.session) return;
  clearLocalRecording();
  renderLibrary();
}

function reviewCandidates() {
  const selected = selectedPrompt();
  if (!selected || selected.kind !== 'word' || !selected.modelSupported || !selected.supportedContexts.includes(ui.context.value)) return [];
  const prompts = filteredPrompts().filter((prompt) => prompt.kind === 'word' && prompt.modelSupported && prompt.supportedContexts.includes(ui.context.value));
  const index = Math.max(0, prompts.findIndex((prompt) => prompt.id === ui.phrase.value));
  const ordered = [...prompts.slice(index), ...prompts.slice(0, index)];
  const seen = new Set();
  return ordered.filter((prompt) => {
    const word = prompt.transcript.toLocaleLowerCase();
    if (seen.has(word)) return false;
    seen.add(word); return true;
  }).slice(0, 5).map((prompt) => prompt.id);
}

function updateSessionControls() {
  const session = state.session;
  const unsettled = Boolean(state.active || state.recording || state.pendingFile || state.leaving);
  for (const id of ['prompt-kind', 'sound-filter', 'position-filter', 'word-search', 'phrase', 'context']) ui[id].disabled = Boolean(session);
  ui['start-session'].disabled = Boolean(session) || unsettled || reviewCandidates().length === 0;
  ui['session-intro'].hidden = Boolean(session) || ui['prompt-kind'].value === 'phrase';
  ui['guided-session'].hidden = !session;
  ui['recording-workspace'].hidden = session?.phase === 'summary';
  ui['next-word'].hidden = !session || session.phase === 'summary';
  ui['next-word'].disabled = unsettled;
  ui['practice-selected'].hidden = !session || session.phase !== 'summary' || session.summaryFrom !== 'assessment';
  ui['practice-selected'].disabled = unsettled || !session?.selected.size;
  ui['recheck-selected'].hidden = !session || session.phase !== 'summary' || session.summaryFrom !== 'practice';
  ui['recheck-selected'].disabled = unsettled || !session?.selected.size;
  if (session && session.phase !== 'summary') {
    ui['next-word'].textContent = session.index === session.queue.length - 1 ? 'Finish this round' : 'Next word';
  }
}

function renderSession() {
  const session = state.session;
  if (!session) { updateControls(); return; }
  const names = { assessment: 'Word review', practice: 'Practice your chosen words', recheck: 'A fresh word check' };
  ui['session-heading'].textContent = session.phase === 'summary' ? `${names[session.summaryFrom]} · complete` : names[session.phase];
  ui['session-summary'].hidden = session.phase !== 'summary';
  if (session.phase !== 'summary') {
    ui['session-status'].textContent = `Word ${session.index + 1} of ${session.queue.length}: ${selectedPrompt()?.transcript || ''}. ${session.phase === 'practice' ? 'Record and listen as often as you like. Choose Next when you are ready.' : 'Record, listen, and choose Check if you want. You can also move on without a check.'}`;
  } else {
    ui['session-status'].textContent = session.summaryFrom === 'assessment'
      ? 'Select the words you would like to practice. Recognition results are observations, not sound grades.'
      : session.summaryFrom === 'practice' ? 'Your practice round is complete. You can make fresh recordings for a separate recheck.'
        : 'Recheck complete. Each result describes one recording; differences do not establish improvement.';
    ui['session-summary'].replaceChildren();
    for (const id of session.queue) {
      const prompt = state.catalog.prompts.find((item) => item.id === id);
      const row = document.createElement('div'); row.className = 'session-choice';
      const label = document.createElement('label'); label.textContent = prompt.transcript;
      if (session.summaryFrom === 'assessment') {
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.id = `practice-${id}`;
        checkbox.checked = session.selected.has(id); label.htmlFor = checkbox.id;
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) session.selected.add(id); else session.selected.delete(id);
          updateSessionControls();
        });
        row.append(checkbox);
      } else {
        row.append(document.createElement('span'));
      }
      const detail = document.createElement('p'); detail.className = 'quiet small';
      detail.textContent = session.summaryFrom === 'practice' ? 'Practice round visited.'
        : (session.summaryFrom === 'recheck' ? session.recheck : session.assessment)[id] || 'Not checked.';
      row.append(label, detail); ui['session-summary'].append(row);
    }
  }
  updateControls();
}

function selectSessionWord() {
  clearLocalRecording();
  ui.phrase.value = state.session.queue[state.session.index];
  showPhrase();
  renderSession();
}

function startSession() {
  if (state.session || state.active || state.recording || state.pendingFile || state.leaving) return;
  const queue = reviewCandidates();
  if (!queue.length) return;
  state.session = { phase: 'assessment', queue, index: 0, assessment: {}, recheck: {}, selected: new Set() };
  selectSessionWord();
}

function nextSessionWord() {
  const session = state.session;
  if (!session || session.phase === 'summary' || state.active || state.recording || state.pendingFile || state.leaving) return;
  if (session.index + 1 < session.queue.length) { session.index += 1; selectSessionWord(); }
  else {
    clearLocalRecording(); session.summaryFrom = session.phase; session.phase = 'summary'; renderSession();
  }
}

function beginSessionRound(phase) {
  const session = state.session;
  if (!session || session.phase !== 'summary' || !session.selected.size || state.active || state.recording || state.pendingFile || state.leaving) return;
  if (phase === 'practice' && session.summaryFrom !== 'assessment' || phase === 'recheck' && session.summaryFrom !== 'practice') return;
  session.queue = [...session.selected]; session.index = 0; session.phase = phase;
  selectSessionWord();
}

function endSession() {
  clearLocalRecording(); state.session = null; renderLibrary();
}

function rememberSessionResult(active, result) {
  const session = state.session;
  if (!session || session !== active.session || !['assessment', 'recheck'].includes(session.phase) || session.phase !== active.sessionPhase || session.queue[session.index] !== active.promptId) return;
  const label = result.phraseMatched === true ? 'Selected word recognized.'
    : ['word_mismatch', 'phrase_mismatch'].includes(result.kind) ? 'Selected word was not matched.' : 'Recognition was uncertain.';
  session[session.phase][active.promptId] = label;
}

// The recorder is created once: a cleanup failure cannot be bypassed with a new instance.
const recorder = window.PhraseRecorder?.createRecorder({
  onState(snapshot) {
    const recording = state.recording;
    if (!recording) return;
    const phaseChanged = recording.phase !== snapshot.state;
    if (snapshot.state !== 'idle') recording.phase = snapshot.state;
    ui['record-time'].textContent = Number.isFinite(snapshot.elapsedSeconds) ? snapshot.elapsedSeconds.toFixed(1) : '0.0';
    ui['record-level'].value = Number.isFinite(snapshot.level) ? Math.max(0, Math.min(1, snapshot.level)) : 0;
    const messages = {
      requesting: 'Waiting for microphone permission. You can discard this request.',
      recording: 'Recording. Say the selected word or phrase, then choose Stop and keep.',
      finishing: 'Finishing the recording and confirming microphone cleanup…',
      cancelling: 'Discarding. Waiting for microphone cleanup to finish…',
      blocked: 'Microphone cleanup could not be confirmed. Recording and checking are blocked.',
    };
    const message = messages[snapshot.state];
    // Sample updates must not repeatedly announce an unchanged live status.
    if (message && ui['record-status'].textContent !== message) ui['record-status'].textContent = message;
    if (phaseChanged) updateControls();
  },
  onComplete(recorded) {
    const recording = state.recording;
    if (!recording) return;
    state.recording = null;
    ui['record-status'].textContent = 'Recording finished. Microphone cleanup confirmed.';
    if (!recording.cancelRequested && recording.generation === state.generation && !state.leaving) {
      try {
        installCapture(recorded.buffer, 'Your recording');
      } catch {
        ui['file-status'].textContent = 'The recording was not a supported WAV. Record again or choose a supported file.';
      }
    }
    updateControls();
  },
  onError(error) {
    if (!state.recording) return;
    const messages = {
      unsupported: 'Recording is unavailable in this browser. You can choose a supported WAV file.',
      permission_denied: 'Microphone permission was not granted. Choose Record to try again, or choose a WAV file.',
      microphone_unavailable: 'The microphone is unavailable. Check its connection, or choose a WAV file.',
      capture_failed: 'The recording could not finish. Choose Record to try again, or choose a WAV file.',
      invalid_audio: 'The microphone did not provide usable audio. Choose Record to try again.',
      too_short: 'The recording was shorter than 0.1 seconds. Choose Record to try again.',
      capture_timeout: 'Audio capture stopped responding. No recording was kept. Choose Record to try again.',
    };
    if (error.cleanupConfirmed === true) {
      state.recording = null;
      ui['record-status'].textContent = messages[error.code] || 'Recording failed. Microphone cleanup confirmed; you can try again.';
    } else {
      state.recording.phase = 'blocked';
      ui['record-status'].textContent = 'Microphone cleanup could not be confirmed. Recording and checking are blocked.';
    }
    updateControls();
  },
});

function installCapture(buffer, label) {
  const seconds = inspectWav(buffer);
  const requestId = crypto.randomUUID();
  const url = URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }));
  state.capture = { requestId, buffer, url, used: false };
  ui.audio.src = url;
  ui.playback.hidden = false;
  ui['file-status'].textContent = `${label} · ${seconds.toFixed(2)} seconds · Ready to listen.`;
}

function startRecording() {
  if (!recorder || !state.catalog || !selectedPrompt() || state.session?.phase === 'summary' || state.active || state.recording || state.pendingFile || state.leaving) return;
  invalidate();
  stopPlayback();
  state.capture = null;
  ui['audio-file'].value = '';
  ui.age.value = '';
  ui.consent.checked = false;
  state.recording = { generation: state.generation, phase: 'requesting', cancelRequested: false, cancelPromise: null };
  ui['file-status'].textContent = 'No recording kept yet.';
  updateControls();
  // Engine owns all errors and cleanup receipts; permission starts only in this click handler.
  recorder.start();
}

function stopRecording() {
  if (state.recording?.phase !== 'recording') return;
  state.recording.phase = 'finishing';
  updateControls();
  recorder.stop();
}

function cancelRecording() {
  const recording = state.recording;
  if (!recording) return Promise.resolve(true);
  if (recording.cancelPromise) return recording.cancelPromise;
  recording.cancelRequested = true;
  if (recording.phase !== 'blocked') recording.phase = 'cancelling';
  ui['record-status'].textContent = recording.phase === 'blocked'
    ? 'Microphone cleanup could not be confirmed. Recording and checking are blocked.'
    : 'Discarding. Waiting for microphone cleanup to finish…';
  updateControls();
  recording.cancelPromise = recorder.cancel().then((receipt) => {
    if (state.recording !== recording) return receipt.cleanupConfirmed === true;
    if (receipt.cleanupConfirmed === true) {
      state.recording = null;
      ui['record-status'].textContent = 'Recording discarded. Microphone cleanup confirmed.';
    } else {
      recording.phase = 'blocked';
      ui['record-status'].textContent = 'Microphone cleanup could not be confirmed. Recording and checking are blocked.';
    }
    updateControls();
    return receipt.cleanupConfirmed === true;
  });
  return recording.cancelPromise;
}

async function selectFile() {
  const cleanup = invalidate();
  stopPlayback();
  state.capture = null;
  const generation = state.generation;
  ui.age.value = '';
  ui.consent.checked = false;
  const file = ui['audio-file'].files[0];
  ui['file-status'].textContent = file ? (state.recording ? 'Waiting for microphone cleanup before opening the WAV file…' : 'Checking the WAV format…') : 'No recording chosen.';
  state.pendingFile = file ? generation : null;
  updateControls();
  if (!file) return;
  try {
    const cleanupConfirmed = await cleanup;
    if (generation !== state.generation || state.leaving) return;
    if (!cleanupConfirmed) {
      ui['file-status'].textContent = 'Microphone cleanup could not be confirmed. The selected file has not been opened.';
      return;
    }
    if (file.size > MAX_WAV_BYTES) throw new Error('size');
    const buffer = await file.arrayBuffer();
    if (generation !== state.generation || state.leaving) return;
    installCapture(buffer, file.name);
  } catch (error) {
    if (generation !== state.generation) return;
    ui['file-status'].textContent = error.message === 'duration'
      ? 'Choose a recording between 0.1 and 4 seconds long.'
      : 'This file is not supported. Choose a mono, 16 kHz, 16-bit PCM WAV of 0.1–4 seconds (up to 132,096 bytes).';
  } finally {
    if (state.pendingFile === generation) state.pendingFile = null;
    updateControls();
  }
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
    prompt_context_unsupported: 'This selection does not support that type of check. You can still record and listen.',
    practice_only_prompt: 'This sound group supports recording and listening practice only.',
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
  const active = { promptId: ui.phrase.value, context: ui.context.value, session: state.session, sessionPhase: state.session?.phase, generation: state.generation, requestId: capture.requestId, jobId: null, stale: false, cancelRequested: false, cancelAcknowledged: false, status: 'submitting', statusUnavailable: false };
  state.active = active;
  ui.result.hidden = true;
  updateControls('Sending this recording to the local service…');
  try {
    const response = await post('/api/check', {
      requestId: capture.requestId, promptId: active.promptId, context: active.context, ageYears: active.context === 'recognition' ? null : Number(ui.age.value), consent: true, audioBase64: base64(capture.buffer),
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

function renderResult(result, context = ui.context.value) {
  ui.result.hidden = false;
  ui['result-message'].textContent = result.message || 'The check finished.';
  const recognitionOnly = context === 'recognition';
  const material = selectedPrompt()?.kind === 'word' ? 'word' : 'phrase';
  ui['phrase-result'].textContent = recognitionOnly
    ? result.phraseMatched ? 'The recognizer matched the selected word.' : result.kind === 'word_mismatch' ? 'The recognizer did not match the selected word. This does not identify a sound error.' : 'The recognizer could not establish a word match from this recording.'
    : result.phraseMatched
    ? `The check matched the selected ${material}.`
    : ['phrase_mismatch', 'word_mismatch'].includes(result.kind) ? `The check did not match the selected ${material}. This does not tell us which sound was different.`
      : `A ${material} match could not be established from this recording.`;
  ui['sound-result'].textContent = recognitionOnly
    ? 'Not assessed. Word recognition does not judge individual sounds.'
    : result.soundAnalysisAvailable || result.scoredOccurrences > 0
    ? 'Uncertain. Sound analysis was computed, but it cannot tell you whether individual sounds were correct.'
    : 'No usable individual sound result is available for this recording.';
  ui['alignment-note'].textContent = recognitionOnly
    ? 'This is a word recognition observation, not a pronunciation grade or evidence of improvement.'
    : result.alignmentUnverified
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
      if (!active.stale && active.generation === state.generation && data.result) renderResult(data.result, active.context);
      updateControls('Processing and cleanup could not be confirmed. Private check files are retained on this computer, and further checks are blocked.');
      return;
    }
    if (SETTLED.has(data.status)) {
      if (!active.stale && active.generation === state.generation && data.result) {
        renderResult(data.result, active.context); rememberSessionResult(active, data.result);
      }
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

ui.record.addEventListener('click', startRecording);
ui['stop-recording'].addEventListener('click', stopRecording);
ui['discard-recording'].addEventListener('click', invalidate);
ui.phrase.addEventListener('change', () => { clearLocalRecording(); showPhrase(); updateControls(); });
for (const id of ['prompt-kind', 'sound-filter', 'position-filter']) ui[id].addEventListener('change', changeLibrary);
ui['word-search'].addEventListener('input', changeLibrary);
ui.context.addEventListener('change', () => { invalidate(); ui.age.value = ''; ui.consent.checked = false; showPhrase(); updateControls(); });
ui['start-session'].addEventListener('click', startSession);
ui['next-word'].addEventListener('click', nextSessionWord);
ui['end-session'].addEventListener('click', endSession);
ui['practice-selected'].addEventListener('click', () => beginSessionRound('practice'));
ui['recheck-selected'].addEventListener('click', () => beginSessionRound('recheck'));
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
  state.pendingFile = null;
  cancelRecording();
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
    if (!catalog.prompts.every((prompt) => ['word', 'phrase'].includes(prompt.kind) && typeof prompt.modelSupported === 'boolean' && Array.isArray(prompt.supportedContexts) && (prompt.kind !== 'word' || typeof prompt.soundID === 'string' && ['beginning', 'middle', 'end'].includes(prompt.position)))) throw new Error('catalog');
    const groups = [...new Set(catalog.prompts.filter((prompt) => prompt.kind === 'word').map((prompt) => prompt.soundID))].sort();
    for (const group of groups) {
      const option = document.createElement('option'); option.value = group; option.textContent = group.toUpperCase(); ui['sound-filter'].append(option);
    }
    ui.context.value = 'recognition';
    ui['prompt-kind'].value = 'word';
    renderLibrary();
    ui['load-status'].hidden = true;
    ui['practice-body'].hidden = false;
    if (!recorder) ui['record-status'].textContent = 'Recording is unavailable in this browser. You can choose a supported WAV file.';
    updateControls();
  } catch {
    ui['load-status'].textContent = 'The local phrase service is unavailable. Reload this page once the service is running.';
  }
}
initialize();
