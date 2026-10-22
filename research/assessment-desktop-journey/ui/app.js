'use strict';

(function () {
  const POLL_MS = 1000;
  const FALLBACK_TEXT = 'This example could not be confirmed. Practice is still available.';

  const STATUS_LABEL = {
    pending: 'Checking',
    available: 'Completed',
    unavailable: 'No result',
    cancelled: 'Cancelled',
    interrupted: 'Interrupted',
    suppressed: 'Withheld',
    forgotten: 'Forgotten',
  };

  const STATUS_TEXT = {
    pending: 'The example recording is being processed.',
    available: 'Research processing finished for this example recording. This does not say whether the word was said correctly.',
    unavailable: FALLBACK_TEXT,
    cancelled: 'Cancelled before it finished. Practice is still available.',
    interrupted: 'The check stopped before it finished. Practice is still available.',
    suppressed: 'The outcome is withheld in this build. Practice is still available.',
    forgotten: 'Forgotten when private history was cleared.',
  };

  // Plain wording for the reason codes this interface expects. Any other code
  // shows FALLBACK_TEXT; codes are never displayed raw.
  const UNSUPPORTED_TEXT = "The research model in this build does not cover this word's target sound, so the check ended without a result. Practice is still available.";
  const NO_SPEECH_TEXT = 'Speech could not be confirmed in this example recording. Practice is still available.';
  const NOT_CONFIRMED_WORD_TEXT = 'This example could not be confirmed as the chosen word. Practice is still available.';
  const REASON_TEXT = {
    unsupported_target: UNSUPPORTED_TEXT,
    unsupported_inventory: UNSUPPORTED_TEXT,
    unavailable_unsupported_inventory: UNSUPPORTED_TEXT,
    no_speech: NO_SPEECH_TEXT,
    speech_not_detected: NO_SPEECH_TEXT,
    word_not_confirmed: NOT_CONFIRMED_WORD_TEXT,
    word_mismatch: NOT_CONFIRMED_WORD_TEXT,
    requested_word_not_matched: NOT_CONFIRMED_WORD_TEXT,
    single_word_required: 'This check needs one word. Practice is still available.',
    recognition_uncertain: NOT_CONFIRMED_WORD_TEXT,
    speech_not_confirmed: NO_SPEECH_TEXT,
    silence: 'The example recording was too quiet for this check. Practice is still available.',
    clipping: 'The example recording was clipped. Practice is still available.',
    recording_unavailable: 'This recording is not available for this check. Practice is still available.',
    authorization_changed: STATUS_TEXT.suppressed,
    retention_expired: STATUS_TEXT.suppressed,
    prompt_match_unverified: NOT_CONFIRMED_WORD_TEXT,
    item_unavailable: 'This example recording is not available right now. Practice is still available.',
    user_cancelled: STATUS_TEXT.cancelled,
    cancelled_by_user: STATUS_TEXT.cancelled,
    cancelled: STATUS_TEXT.cancelled,
    history_cleared: STATUS_TEXT.forgotten,
    interrupted: STATUS_TEXT.interrupted,
    server_restarted: STATUS_TEXT.interrupted,
    timeout: STATUS_TEXT.interrupted,
    claim_limits: STATUS_TEXT.suppressed,
  };

  const POSITION = { beginning: 'beginning', middle: 'middle', end: 'ending' };

  const app = {
    prompts: [],
    promptById: new Map(),
    selectedId: null,
    catalogState: 'loading', // loading | ready | empty | error
    session: null,
    sessionState: 'loading', // loading | ready | error
    authGen: 0,
    authTransition: false,
    privateOpen: false,
    priv: null,
    privState: 'idle', // idle | loading | ready | error
    privGen: 0,
    stateSeq: 0,
    current: null,
    poll: null,
    pollGen: 0,
    pollFailed: false,
    cancelledIds: new Set(),
    itemChoice: new Map(),
    busy: { login: false, logout: false, start: false, cancel: false, practice: false, clear: false, export: false },
    checkMessage: '',
    historyMessage: '',
    confirmClear: false,
    localPracticeCount: 0,
  };

  const ui = {};
  const dyn = { select: null, runButton: null, itemNote: null };
  const players = [];
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const timeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  let currentSignature = '';
  let authLossTask = null;

  // ---------- small helpers ----------

  const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const str = (v) => (typeof v === 'string' ? v : '');
  const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const authed = () => Boolean(!app.authTransition && app.session && app.session.authenticated);
  const selectedPrompt = () => app.promptById.get(app.selectedId) || null;
  const camel = (id) => id.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    if (props) {
      for (const key of Object.keys(props)) {
        const value = props[key];
        if (value === null || value === undefined || value === false) continue;
        if (key === 'text') node.textContent = String(value);
        else if (key === 'class') node.className = value;
        else if (key === 'value') node.value = value;
        else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value === true ? '' : String(value));
      }
    }
    appendAll(node, children);
    return node;
  }

  // Native replaceChildren converts optional null children into visible text.
  function replaceAll(node, ...children) {
    node.replaceChildren();
    appendAll(node, children);
  }

  function appendAll(node, children) {
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      if (Array.isArray(child)) appendAll(node, child);
      else node.append(child instanceof Node ? child : String(child));
    }
  }

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const b = window.crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }

  // Same-origin path from a closed backend route; anything else is dropped.
  function safePath(value) {
    if (typeof value !== 'string' || !/^\/(?![/\\])/.test(value) || /[\s\\]/.test(value)) return null;
    try {
      const url = new URL(value, window.location.origin);
      return url.origin === window.location.origin ? url.pathname + url.search : null;
    } catch (_) {
      return null;
    }
  }

  // Only used for license and source page anchors.
  function safeExternal(value) {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function extLink(href, label) {
    return el('a', { href, target: '_blank', rel: 'noopener noreferrer' },
      label, el('span', { class: 'visually-hidden', text: ' (opens in a new tab)' }));
  }

  function fact(term, detail) {
    return [el('dt', { text: term }), el('dd', null, detail)];
  }

  function positionOf(id) {
    const token = String(id).split('-').find((part) => has(POSITION, part));
    return token ? POSITION[token] : '';
  }

  function promptLabel(prompt) {
    const pos = positionOf(prompt.id);
    return pos ? `${prompt.word} · ${pos} sound` : prompt.word;
  }

  function formatTime(value) {
    const t = Date.parse(value);
    return Number.isFinite(t) ? timeFormat.format(new Date(t)) : '';
  }

  function announce(message) {
    ui.announcer.textContent = '';
    window.setTimeout(() => { ui.announcer.textContent = message; }, 50);
  }

  function reveal(node, focusTarget) {
    node.scrollIntoView({ behavior: reduceMotion.matches ? 'auto' : 'smooth', block: 'start' });
    if (focusTarget) focusTarget.focus({ preventScroll: true });
  }

  // ---------- HTTP ----------

  async function api(path, options) {
    const opts = options || {};
    const method = opts.method || 'GET';
    const init = {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: opts.signal,
    };
    if (method === 'POST') {
      init.headers['Content-Type'] = 'application/json';
      if (app.session && app.session.csrfToken) init.headers['X-Journey-CSRF'] = app.session.csrfToken;
      init.body = JSON.stringify(opts.body || {});
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (err) {
      if (err && err.name === 'AbortError') throw err;
      return { ok: false, status: 0, data: null };
    }
    let data = null;
    try {
      const text = await res.text();
      if (text) data = JSON.parse(text);
    } catch (err) {
      if (err && err.name === 'AbortError') throw err;
      data = null;
    }
    return { ok: res.ok, status: res.status, data };
  }

  const isAuthLoss = (r) => r.status === 401 || r.status === 403;

  // ---------- normalisers ----------

  function normalizeReference(r) {
    if (!isObj(r)) return null;
    let changes = '';
    if (typeof r.changes === 'string') changes = r.changes;
    else if (Array.isArray(r.changes)) changes = r.changes.filter((c) => typeof c === 'string').join('; ');
    return {
      author: str(r.author),
      licenseId: str(r.licenseId),
      licenseUrl: safeExternal(r.licenseUrl),
      sourcePageUrl: safeExternal(r.sourcePageUrl),
      declaredVariety: str(r.declaredVariety),
      speakerAgeKnown: r.speakerAgeKnown === true,
      clinicalReferenceApproved: r.clinicalReferenceApproved === true,
      changes,
      attribution: str(r.attribution),
    };
  }

  function normalizePrompt(p) {
    if (!isObj(p) || typeof p.id !== 'string' || !p.id || typeof p.word !== 'string' || !p.word) return null;
    const variants = Array.isArray(p.variants)
      ? p.variants.filter(isObj).map((v) => ({
        id: str(v.id),
        phones: Array.isArray(v.phones) ? v.phones.filter((x) => typeof x === 'string') : [],
      }))
      : [];
    const sourceWord = str(p.sourceWord) || p.word;
    return {
      id: p.id,
      word: p.word,
      sourceWord,
      targetPhone: str(p.targetPhone),
      variants,
      selectedVariantId: str(p.selectedVariantId),
      selectedOccurrenceIndex: Number.isInteger(p.selectedOccurrenceIndex) ? p.selectedOccurrenceIndex : null,
      supported: p.supported === true,
      imageUrl: safePath(p.imageUrl) || safePath(`/illustrations/${encodeURIComponent(sourceWord)}.svg`),
      publicReferenceUrl: safePath(p.publicReferenceUrl),
      reference: normalizeReference(p.reference),
    };
  }

  function normalizeCatalog(d) {
    if (!isObj(d) || d.schemaVersion !== 1 || !Array.isArray(d.prompts)) return null;
    const seen = new Set();
    const prompts = [];
    for (const raw of d.prompts) {
      const p = normalizePrompt(raw);
      if (p && !seen.has(p.id)) {
        seen.add(p.id);
        prompts.push(p);
      }
    }
    return prompts;
  }

  function normalizeItem(i) {
    if (!isObj(i) || typeof i.id !== 'string' || !i.id) return null;
    if (i.kind !== 'public_reference' && i.kind !== 'invented_fixture') return null;
    return {
      id: i.id,
      label: str(i.label) || 'Unnamed example',
      kind: i.kind,
      sourceWord: str(i.sourceWord),
      available: i.available === true,
    };
  }

  function normalizeRow(r) {
    if (!isObj(r) || typeof r.id !== 'string' || !r.id || typeof r.status !== 'string') return null;
    const repeatOf = typeof r.repeatOf === 'string' && r.repeatOf ? r.repeatOf : null;
    return {
      id: r.id,
      promptId: str(r.promptId),
      itemId: typeof r.itemId === 'string' && r.itemId ? r.itemId : null,
      status: r.status,
      reason: typeof r.reason === 'string' && r.reason ? r.reason : null,
      createdAt: typeof r.createdAt === 'number' && Number.isFinite(r.createdAt) ? new Date(r.createdAt * 1000).toISOString() : str(r.createdAt),
      repeatOf,
      isReplay: Boolean(repeatOf) || r.replay === true,
      result: has(r, 'result') ? r.result : null,
    };
  }

  function count(v) {
    return Number.isInteger(v) && v >= 0 ? v : null;
  }

  function normalizeState(d) {
    if (!isObj(d) || d.schemaVersion !== 1) return null;
    const p = isObj(d.participation) ? d.participation : null;
    return {
      accountId: str(d.accountId),
      inventory: Array.isArray(d.inventory) ? d.inventory.map(normalizeItem).filter(Boolean) : [],
      history: Array.isArray(d.history) ? d.history.map(normalizeRow).filter(Boolean) : [],
      participation: p ? {
        planned: count(p.planned),
        started: count(p.started),
        terminal: count(p.terminal),
        manualPractice: count(p.manualPractice),
        replays: count(p.replays),
      } : null,
    };
  }

  // A result counts as completed only when it is well formed and says so.
  function researchCompleted(result) {
    return isObj(result) && result.status === 'processed' &&
      isObj(result.research) && result.research.status === 'processed' &&
      isObj(result.claimLimits) && ['learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible'].every((key) => result.claimLimits[key] === false);
  }

  function describeRow(row) {
    let status = row.status;
    if (status === 'pending' && app.cancelledIds.has(row.id)) status = 'cancelled';
    if (!has(STATUS_LABEL, status)) {
      return { status: 'unknown', label: 'Not confirmed', text: FALLBACK_TEXT, terminal: true };
    }
    if (status === 'available') {
      if (!researchCompleted(row.result)) {
        return { status: 'unconfirmed', label: 'Not confirmed', text: FALLBACK_TEXT, terminal: true };
      }
      return { status, label: STATUS_LABEL.available, text: STATUS_TEXT.available, terminal: true };
    }
    let text = STATUS_TEXT[status];
    if (row.reason && status !== 'pending') {
      text = has(REASON_TEXT, row.reason) ? REASON_TEXT[row.reason] : FALLBACK_TEXT;
    }
    return { status, label: STATUS_LABEL[status], text, terminal: status !== 'pending' };
  }

  // ---------- audio ----------

  function createPlayer(text) {
    const audio = new Audio();
    audio.preload = 'none';
    audio.hidden = true;
    audio.setAttribute('aria-hidden', 'true');
    document.body.append(audio);
    let mediaGeneration = 0;
    let mediaAbort = null;
    let objectUrl = null;
    const player = { button: null, status: null, src: null, loaded: false, state: 'idle', msg: '' };

    function paint() {
      if (player.button) {
        const active = player.state === 'loading' || player.state === 'playing';
        player.button.textContent = active ? text.stop : text.play;
        player.button.disabled = !player.src;
      }
      if (player.status) player.status.textContent = player.src ? player.msg : text.none;
    }

    function set(state, msg) {
      player.state = state;
      player.msg = msg || '';
      paint();
    }

    async function toggle() {
      if (!player.src) return;
      if (player.state === 'loading' || player.state === 'playing') {
        player.stop();
        return;
      }
      for (const other of players) if (other !== player) other.stop();
      // Private media is authorized again for every playback, including after an external pause.
      if (player.src.startsWith('/api/references/')) player.stop();
      const generation = ++mediaGeneration;
      set('loading', text.loading);
      try {
        if (!player.loaded) {
          mediaAbort = new AbortController();
          const headers = { Accept: 'audio/wav' };
          const privateMedia = player.src.startsWith('/api/references/');
          if (privateMedia && app.session && app.session.csrfToken) headers['X-Journey-CSRF'] = app.session.csrfToken;
          const response = await fetch(player.src, { credentials: 'same-origin', cache: 'no-store', headers, signal: mediaAbort.signal });
          if (generation !== mediaGeneration) return;
          if (privateMedia && isAuthLoss(response)) {
            handleAuthLoss();
            return;
          }
          if (!response.ok || !response.headers.get('Content-Type')?.startsWith('audio/wav')) throw new Error('media_unavailable');
          const blob = await response.blob();
          if (generation !== mediaGeneration) return;
          if (blob.size < 44 || blob.size > 132096) throw new Error('media_unavailable');
          objectUrl = URL.createObjectURL(blob);
          audio.src = objectUrl;
          player.loaded = true;
        }
        await audio.play();
      } catch (err) {
        if (generation !== mediaGeneration || (err && err.name === 'AbortError')) return;
        player.stop();
        set('error', text.error);
      }
    }

    audio.addEventListener('playing', () => set('playing', ''));
    audio.addEventListener('waiting', () => { if (player.state === 'playing') set('loading', text.loading); });
    audio.addEventListener('ended', () => player.stop());
    audio.addEventListener('pause', () => {
      if (player.loaded && player.src && player.src.startsWith('/api/references/')) player.stop();
      else if (player.state === 'loading' || player.state === 'playing') set('idle', '');
    });
    audio.addEventListener('error', () => {
      if (!player.loaded) return;
      player.stop();
      set('error', text.error);
    });

    player.attach = (button, status) => {
      player.button = button;
      player.status = status;
      button.addEventListener('click', toggle);
      paint();
    };
    player.stop = () => {
      mediaGeneration += 1;
      if (mediaAbort) mediaAbort.abort();
      mediaAbort = null;
      player.loaded = false;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
      set('idle', '');
    };
    player.setSource = (src) => {
      if (src === player.src) {
        paint();
        return;
      }
      player.stop();
      player.src = src || null;
      player.loaded = false;
      audio.removeAttribute('src');
      audio.load();
      set('idle', '');
    };

    players.push(player);
    return player;
  }

  const publicPlayer = createPlayer({
    play: 'Play example',
    stop: 'Stop',
    loading: 'Loading the example…',
    error: 'The example could not be played. You can still practice the word.',
    none: 'No example recording is available for this word. You can still practice it.',
  });

  const privatePlayer = createPlayer({
    play: 'Play this example',
    stop: 'Stop',
    loading: 'Loading the example…',
    error: 'This example could not be played.',
    none: '',
  });

  // ---------- catalog and public practice ----------

  async function loadCatalog() {
    const fromRetry = document.activeElement === ui.catalogRetry;
    app.catalogState = 'loading';
    renderWords();
    renderPractice();
    const r = await api('/api/catalog');
    const prompts = r.ok ? normalizeCatalog(r.data) : null;
    if (!prompts) {
      app.catalogState = 'error';
    } else {
      app.prompts = prompts;
      app.promptById = new Map(prompts.map((p) => [p.id, p]));
      app.catalogState = prompts.length ? 'ready' : 'empty';
      if (!app.promptById.has(app.selectedId)) app.selectedId = prompts.length ? prompts[0].id : null;
    }
    renderWords();
    renderPractice();
    if (fromRetry) {
      const target = app.catalogState === 'ready' ? ui.wordList.querySelector('button.word-row') : ui.catalogRetry;
      if (target && !target.hidden) target.focus();
    }
    if (authed() && app.priv) {
      resumeForSelected();
      renderPrivate();
    }
  }

  function renderWords() {
    const status = ui.wordStatus;
    ui.catalogRetry.hidden = app.catalogState !== 'error';
    if (app.catalogState !== 'ready') {
      ui.wordList.hidden = true;
      replaceAll(ui.wordList, );
      status.hidden = false;
      status.textContent = {
        loading: 'Loading words…',
        error: 'Words could not be loaded.',
        empty: 'No words are available right now.',
      }[app.catalogState];
      return;
    }
    status.hidden = true;
    status.textContent = '';
    replaceAll(ui.wordList, ...app.prompts.map((p) => {
      const pos = positionOf(p.id);
      return el('li', null,
        el('button', {
          type: 'button',
          class: 'word-row',
          'data-prompt': p.id,
          'aria-current': p.id === app.selectedId ? 'true' : null,
          onclick: () => selectPrompt(p.id),
        },
        el('span', { class: 'word-row-word', text: p.word }),
        pos ? el('span', { class: 'word-row-pos', text: `${pos} sound` }) : null));
    }));
    ui.wordList.hidden = false;
  }

  function onWordListKey(event) {
    const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    const buttons = Array.from(ui.wordList.querySelectorAll('button.word-row'));
    const index = buttons.indexOf(document.activeElement);
    if (index === -1) return;
    event.preventDefault();
    let next = index;
    if (event.key === 'ArrowDown') next = Math.min(buttons.length - 1, index + 1);
    if (event.key === 'ArrowUp') next = Math.max(0, index - 1);
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = buttons.length - 1;
    buttons[next].focus();
  }

  function selectPrompt(id) {
    const prompt = app.promptById.get(id);
    if (!prompt || id === app.selectedId) return;
    app.selectedId = id;
    publicPlayer.stop();
    privatePlayer.stop();
    stopPoll();
    app.current = null;
    app.pollFailed = false;
    app.checkMessage = '';
    ui.practiceStatus.textContent = '';
    for (const button of ui.wordList.querySelectorAll('button.word-row')) {
      if (button.dataset.prompt === id) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    }
    renderPractice();
    if (authed() && app.priv) {
      resumeForSelected();
      renderPrivate();
    }
    announce(`Showing ${promptLabel(prompt)}.`);
  }

  function renderPractice() {
    const p = selectedPrompt();
    if (!p) {
      ui.practiceBody.hidden = true;
      ui.practiceEmpty.hidden = false;
      ui.practiceMessage.textContent = {
        loading: 'Loading…',
        error: 'Practice words could not be loaded. Use Try again in the word list.',
        empty: 'No words are available right now.',
      }[app.catalogState] || '';
      publicPlayer.setSource(null);
      return;
    }
    ui.practiceEmpty.hidden = true;
    ui.practiceBody.hidden = false;
    ui.wordHeading.textContent = p.word;
    const pos = positionOf(p.id);
    ui.wordPosition.textContent = pos ? `${pos.charAt(0).toUpperCase()}${pos.slice(1)} sound` : '';
    ui.wordPosition.hidden = !pos;

    if (p.imageUrl) {
      ui.picture.alt = `Picture of ${p.word}`;
      ui.picture.hidden = false;
      ui.pictureMissing.hidden = true;
      if (ui.picture.getAttribute('src') !== p.imageUrl) ui.picture.setAttribute('src', p.imageUrl);
    } else {
      ui.picture.removeAttribute('src');
      ui.picture.hidden = true;
      ui.pictureMissing.hidden = false;
    }

    publicPlayer.setSource(p.publicReferenceUrl);
    renderReference(p);
    renderPracticeControls();
  }

  function renderReference(p) {
    const r = p.reference;
    if (!r) {
      replaceAll(ui.referenceDetails, ...fact('Details', 'Not available for this example.'));
      return;
    }
    const license = r.licenseUrl
      ? extLink(r.licenseUrl, r.licenseId || 'License terms')
      : (r.licenseId || 'Not stated');
    const rows = [
      ...fact('Recorded by', r.author || 'Not stated'),
      ...fact('License', license),
      ...fact('Source', r.sourcePageUrl ? extLink(r.sourcePageUrl, 'Original recording page') : 'Not stated'),
      ...fact('Changes', r.changes || 'None stated'),
      ...fact('Speaker age', r.speakerAgeKnown ? 'See the source page' : 'Not known'),
      ...fact('Accent or variety', r.declaredVariety || 'Not stated'),
      ...fact('Use', r.clinicalReferenceApproved
        ? 'Engineering example.'
        : 'Engineering example. Not a clinically approved reference.'),
    ];
    if (r.attribution) rows.push(...fact('Attribution', r.attribution));
    replaceAll(ui.referenceDetails, ...rows);
  }

  function renderPracticeControls() {
    ui.practised.disabled = app.busy.practice;
    ui.practised.textContent = app.busy.practice ? 'Saving…' : 'I practiced this word';
    const n = app.localPracticeCount;
    if (authed()) {
      const total = app.priv && app.priv.participation ? app.priv.participation.manualPractice : null;
      ui.practiceCount.textContent = total === null
        ? 'Practice marks are saved to your private record.'
        : `Practice marks in your private record: ${total}. This counts taking part, not progress.`;
    } else if (n === 0) {
      ui.practiceCount.textContent = 'Practice marks are counted on this page only and are not saved.';
    } else {
      ui.practiceCount.textContent = `Marked ${n} ${n === 1 ? 'time' : 'times'} on this page. This session-only count is not saved and resets when the page reloads.`;
    }
  }

  async function markPractised() {
    const p = selectedPrompt();
    if (!p || app.busy.practice) return;
    if (!authed()) {
      app.localPracticeCount += 1;
      ui.practiceStatus.textContent = 'Marked as practiced.';
      renderPracticeControls();
      announce(`Marked as practiced. ${app.localPracticeCount} on this page.`);
      return;
    }
    app.busy.practice = true;
    ui.practiceStatus.textContent = '';
    renderPracticeControls();
    const gen = app.privGen;
    const cur = app.current;
    const attemptId = cur && cur.promptId === p.id && describeRow(cur).terminal && cur.status !== 'forgotten'
      ? cur.id : null;
    const r = await api('/api/practice', {
      method: 'POST',
      body: { idempotencyKey: uuid(), promptId: p.id, attemptId },
    });
    if (gen !== app.privGen) return;
    app.busy.practice = false;
    renderPracticeControls();
    if (isAuthLoss(r)) {
      handleAuthLoss();
      return;
    }
    const message = r.ok
      ? 'Practice saved to your private record.'
      : 'This practice could not be saved. You can keep practicing.';
    ui.practiceStatus.textContent = message;
    announce(message);
    if (r.ok) loadState();
  }

  function focusPractice() {
    reveal(ui.practice, ui.play.disabled ? ui.practised : ui.play);
  }

  // ---------- session ----------

  async function refreshSession(generation = ++app.authGen) {
    const r = await api('/api/session');
    if (generation !== app.authGen) return null;
    const d = r.data;
    if (r.ok && isObj(d) && typeof d.authenticated === 'boolean' && typeof d.csrfToken === 'string' && d.csrfToken) {
      app.session = { authenticated: d.authenticated, csrfToken: d.csrfToken, accountId: str(d.accountId) };
      app.sessionState = 'ready';
    } else {
      app.session = null;
      app.sessionState = 'error';
    }
    return app.session;
  }

  function accountName() {
    return (app.session && app.session.accountId) || (app.priv && app.priv.accountId) || 'engineering account';
  }

  function setNotice(message) {
    ui.privateNotice.textContent = message;
    ui.privateNotice.hidden = !message;
  }

  function showSigninError(message) {
    ui.signinError.textContent = message;
    ui.signinError.hidden = !message;
  }

  function renderAccount() {
    const signedIn = authed();
    ui.account.hidden = !signedIn;
    ui.accountName.textContent = signedIn ? `Signed in as ${accountName()}` : '';
    ui.logout.disabled = app.busy.logout;
    ui.openPrivate.textContent = signedIn ? 'Private checks' : 'Open private checks';
    ui.openPrivate.setAttribute('aria-expanded', String(app.privateOpen));
    ui.private.hidden = !app.privateOpen;
    ui.signin.hidden = signedIn;
    ui.privateBody.hidden = !signedIn;
    ui.sessionError.hidden = signedIn || app.sessionState !== 'error';
    ui.signinSubmit.disabled = app.authTransition || app.busy.login || app.sessionState !== 'ready';
    ui.signinSubmit.textContent = app.busy.login ? 'Signing in…' : 'Sign in';
  }

  function onOpenPrivate() {
    if (authed()) {
      app.privateOpen = true;
      renderAccount();
      reveal(ui.private, ui.privateHeading);
      return;
    }
    app.privateOpen = !app.privateOpen;
    renderAccount();
    if (app.privateOpen) reveal(ui.private, ui.signinSubmit.disabled ? ui.privateHeading : ui.accountId);
  }

  async function onSignin(event) {
    event.preventDefault();
    if (app.busy.login || app.authTransition) return;
    const accountId = ui.accountId.value.trim();
    if (!accountId || !ui.password.value) {
      showSigninError('Enter your account and password.');
      (accountId ? ui.password : ui.accountId).focus();
      return;
    }
    app.busy.login = true;
    app.authTransition = true;
    const generation = ++app.authGen;
    clearPrivate();
    showSigninError('');
    renderAccount();
    let r = { ok: false, status: 0 };
    if (app.session || await refreshSession(generation)) {
      r = await api('/api/login', { method: 'POST', body: { accountId, password: ui.password.value } });
    }
    ui.password.value = '';
    if (generation !== app.authGen) return;
    app.busy.login = false;

    if (r.ok) {
      await refreshSession(generation);
      if (generation !== app.authGen) return;
      app.authTransition = false;
      clearPrivate();
      if (authed()) {
        setNotice('');
        app.privateOpen = true;
        renderAccount();
        renderPracticeControls();
        ui.privateHeading.focus();
        announce('Signed in.');
        loadState();
        return;
      }
      showSigninError('Sign-in did not complete. Try again.');
    } else if (r.status === 401 || r.status === 403) {
      showSigninError('That account and password were not accepted.');
      await refreshSession(generation);
    } else if (r.status === 429) {
      showSigninError('Too many attempts. Wait a little, then try again.');
    } else {
      showSigninError('Sign-in is not available right now. Practice still works.');
    }
    if (generation !== app.authGen) return;
    app.authTransition = false;
    clearPrivate();
    renderAccount();
    ui.password.focus();
  }

  async function logout() {
    if (app.busy.logout || app.authTransition) return;
    app.busy.logout = true;
    app.authTransition = true;
    const generation = ++app.authGen;
    clearPrivate();
    renderAccount();
    await api('/api/logout', { method: 'POST', body: {} });
    await refreshSession(generation);
    if (generation !== app.authGen) return;
    app.authTransition = false;
    clearPrivate();
    app.busy.logout = false;
    if (authed()) {
      setNotice('Sign-out did not complete. Try again.');
      loadState();
    } else {
      setNotice('You are signed out. Practice continues.');
      announce('Signed out. Practice continues.');
    }
    renderPrivate();
    ui.openPrivate.focus();
  }

  // Clears every rendered and held private value and stops any polling.
  function clearPrivate() {
    app.privGen += 1;
    app.stateSeq += 1;
    stopPoll();
    privatePlayer.setSource(null);
    app.priv = null;
    app.privState = 'idle';
    app.current = null;
    app.pollFailed = false;
    app.cancelledIds.clear();
    app.itemChoice.clear();
    app.confirmClear = false;
    app.checkMessage = '';
    app.historyMessage = '';
    for (const key of Object.keys(app.busy)) {
      if (key !== 'login' && key !== 'logout') app.busy[key] = false;
    }
    ui.practiceStatus.textContent = '';
    clearPrivateDom();
    renderPracticeControls();
  }

  function clearPrivateDom() {
    for (const node of [ui.privateStatus, ui.checkPanel, ui.currentCheck, ui.participation, ui.history]) {
      node.replaceChildren();
    }
    dyn.select = null;
    dyn.runButton = null;
    dyn.itemNote = null;
    currentSignature = '';
  }

  // A 401/403 from a private route ends the private view. The token may have
  // rotated, so the session is fetched again before deciding what to show.
  function handleAuthLoss() {
    if (authLossTask) return authLossTask;
    if (app.authTransition) return Promise.resolve();
    app.authTransition = true;
    const generation = ++app.authGen;
    authLossTask = (async () => {
      clearPrivate();
      renderPrivate();
      await refreshSession(generation);
      if (generation !== app.authGen) return;
      app.authTransition = false;
      clearPrivate();
      if (authed()) {
        loadState({ recovering: true });
      } else {
        setNotice('Your private session has ended. Sign in again to continue. Practice still works.');
        announce('Your private session has ended.');
      }
      renderPrivate();
    })().finally(() => { authLossTask = null; });
    return authLossTask;
  }

  async function retrySession() {
    if (app.authTransition) return;
    app.authTransition = true;
    const generation = ++app.authGen;
    clearPrivate();
    renderPrivate();
    await refreshSession(generation);
    if (generation !== app.authGen) return;
    app.authTransition = false;
    clearPrivate();
    if (authed()) {
      app.privateOpen = true;
      loadState();
    }
    renderPrivate();
  }

  // ---------- private state ----------

  async function loadState(options) {
    if (!authed()) return;
    const recovering = Boolean(options && options.recovering);
    const gen = app.privGen;
    const seq = ++app.stateSeq;
    if (!app.priv) {
      app.privState = 'loading';
      renderPrivate();
    }
    const r = await api('/api/state');
    if (gen !== app.privGen || seq !== app.stateSeq) return;
    if (isAuthLoss(r)) {
      if (recovering) {
        clearPrivate();
        app.privState = 'error';
        renderPrivate();
      } else {
        handleAuthLoss();
      }
      return;
    }
    const s = r.ok ? normalizeState(r.data) : null;
    if (!s) {
      app.privState = 'error';
      renderPrivate();
      return;
    }
    app.priv = s;
    app.privState = 'ready';
    resumeForSelected();
    renderPrivate();
  }

  function timeValue(row) {
    const t = Date.parse(row.createdAt);
    return Number.isFinite(t) ? t : -Infinity;
  }

  function newestFirst(rows) {
    return rows
      .map((row, index) => [row, index])
      .sort((a, b) => (timeValue(b[0]) - timeValue(a[0])) || (a[1] - b[1]))
      .map((pair) => pair[0]);
  }

  function isLivePending(row) {
    return Boolean(row) && row.status === 'pending' && !app.cancelledIds.has(row.id);
  }

  // Shows the latest check for the selected word and resumes polling if it is
  // still pending on the server.
  function resumeForSelected() {
    if (!app.priv || !app.selectedId) return;
    const cur = app.current;
    if (cur && cur.promptId === app.selectedId) {
      if (app.poll) return;
      const fresh = app.priv.history.find((row) => row.id === cur.id);
      if (fresh && !(fresh.status === 'pending' && app.cancelledIds.has(fresh.id))) {
        app.current = fresh;
        if (fresh.status !== 'pending') app.pollFailed = false;
      }
      if (isLivePending(app.current) && !app.pollFailed) startPoll(app.current.id, POLL_MS);
      return;
    }
    const latest = newestFirst(app.priv.history)
      .find((row) => row.promptId === app.selectedId && row.status !== 'forgotten');
    app.current = latest || null;
    app.pollFailed = false;
    if (isLivePending(latest)) startPoll(latest.id, 0);
  }

  function startPoll(attemptId, delay) {
    stopPoll();
    const gen = app.pollGen;
    const privGen = app.privGen;
    const poll = { controller: new AbortController(), timer: 0 };
    app.poll = poll;
    app.pollFailed = false;

    const tick = async () => {
      if (gen !== app.pollGen || privGen !== app.privGen) return;
      let r;
      try {
        r = await api(`/api/attempts/${encodeURIComponent(attemptId)}`, { signal: poll.controller.signal });
      } catch (_) {
        return;
      }
      if (gen !== app.pollGen || privGen !== app.privGen) return;
      if (isAuthLoss(r)) {
        app.poll = null;
        handleAuthLoss();
        return;
      }
      const row = r.ok ? normalizeRow(r.data) : null;
      if (!row || row.id !== attemptId) {
        app.poll = null;
        app.pollFailed = true;
        renderCurrent();
        syncCheckControls();
        return;
      }
      app.current = row;
      if (row.status === 'pending') {
        poll.timer = window.setTimeout(tick, POLL_MS);
        renderCurrent();
        syncCheckControls();
        return;
      }
      app.poll = null;
      renderCurrent();
      syncCheckControls();
      const d = describeRow(row);
      announce(`${d.label}. ${d.text}`);
      loadState();
    };

    poll.timer = window.setTimeout(tick, delay);
  }

  function stopPoll() {
    app.pollGen += 1;
    if (app.poll) {
      window.clearTimeout(app.poll.timer);
      app.poll.controller.abort();
      app.poll = null;
    }
  }

  // ---------- private actions ----------

  async function startCheck(promptId, itemId, repeatOf) {
    if (!authed() || app.busy.start) return;
    if (isLivePending(app.current)) {
      app.checkMessage = 'Wait for the current check to finish, or cancel it.';
      renderCurrent();
      return;
    }
    if (!itemId) {
      app.checkMessage = 'Choose an example first.';
      renderCurrent();
      return;
    }
    app.busy.start = true;
    app.checkMessage = '';
    stopPoll();
    syncCheckControls();
    renderCurrent();
    const gen = app.privGen;
    const r = await api('/api/assessments', {
      method: 'POST',
      body: { idempotencyKey: uuid(), promptId, itemId, repeatOf: repeatOf || null },
    });
    if (gen !== app.privGen) return;
    app.busy.start = false;
    if (isAuthLoss(r)) {
      handleAuthLoss();
      return;
    }
    const d = r.data;
    if (!r.ok || !isObj(d) || typeof d.attemptId !== 'string' || !d.attemptId) {
      app.checkMessage = 'The check could not be started. Practice is still available.';
      syncCheckControls();
      renderCurrent();
      return;
    }
    if (promptId !== app.selectedId) {
      syncCheckControls();
      loadState();
      return;
    }
    app.current = {
      id: d.attemptId,
      promptId,
      itemId,
      status: 'pending',
      reason: null,
      createdAt: new Date().toISOString(),
      repeatOf: repeatOf || null,
      isReplay: Boolean(repeatOf),
      result: null,
    };
    syncCheckControls();
    renderCurrent();
    const heading = document.getElementById('current-heading');
    if (heading) heading.focus();
    announce(repeatOf ? 'Replay check started.' : 'Check started.');
    startPoll(d.attemptId, POLL_MS);
    loadState();
  }

  async function cancelCheck() {
    const cur = app.current;
    if (!authed() || !isLivePending(cur) || app.busy.cancel) return;
    app.busy.cancel = true;
    app.checkMessage = '';
    renderCurrent();
    const gen = app.privGen;
    const r = await api('/api/cancel', { method: 'POST', body: { idempotencyKey: uuid(), attemptId: cur.id } });
    if (gen !== app.privGen) return;
    app.busy.cancel = false;
    if (isAuthLoss(r)) {
      handleAuthLoss();
      return;
    }
    const stillCurrent = app.current && app.current.id === cur.id && app.selectedId === cur.promptId;
    if (!r.ok) {
      if (!stillCurrent) { loadState(); return; }
      app.checkMessage = 'The check could not be cancelled. It may still finish.';
      renderCurrent();
      return;
    }
    app.cancelledIds.add(cur.id);
    if (!stillCurrent) { syncCheckControls(); loadState(); return; }
    stopPoll();
    const row = normalizeRow(r.data);
    app.current = row && row.id === cur.id && row.status !== 'pending'
      ? row
      : Object.assign({}, cur, { status: 'cancelled', reason: null, result: null });
    renderCurrent();
    syncCheckControls();
    announce('Check cancelled.');
    loadState();
  }

  async function clearHistory() {
    if (!authed() || app.busy.clear) return;
    app.busy.clear = true;
    app.historyMessage = '';
    stopPoll();
    renderHistory();
    renderCurrent();
    syncCheckControls();
    const gen = app.privGen;
    const r = await api('/api/history/clear', { method: 'POST', body: { idempotencyKey: uuid() } });
    if (gen !== app.privGen) return;
    app.busy.clear = false;
    app.confirmClear = false;
    if (isAuthLoss(r)) {
      handleAuthLoss();
      return;
    }
    if (!r.ok) {
      app.historyMessage = 'Private history could not be cleared. Try again.';
      renderPrivate();
      focusKey('clear');
      loadState();
      return;
    }
    // Drop any in-flight private request tied to the cleared history.
    app.privGen += 1;
    app.stateSeq += 1;
    privatePlayer.setSource(null);
    app.priv = null;
    app.privState = 'loading';
    app.current = null;
    app.pollFailed = false;
    app.cancelledIds.clear();
    for (const key of ['start', 'cancel', 'practice', 'export']) app.busy[key] = false;
    app.historyMessage = 'Derived outcomes cleared. Minimal attempt and replay records and participation counts are kept. Public example recordings are not affected.';
    renderPrivate();
    renderPracticeControls();
    const heading = document.getElementById('history-heading');
    if (heading) heading.focus();
    announce(app.historyMessage);
    loadState();
  }

  async function exportRecords() {
    if (!authed() || app.busy.export) return;
    app.busy.export = true;
    app.historyMessage = '';
    renderHistory();
    const gen = app.privGen;
    let res = null;
    let blob = null;
    try {
      res = await fetch('/api/export', { credentials: 'same-origin', cache: 'no-store' });
      if (res.ok) blob = await res.blob();
    } catch (_) {
      res = null;
    }
    if (gen !== app.privGen) return;
    app.busy.export = false;
    if (res && (res.status === 401 || res.status === 403)) {
      handleAuthLoss();
      return;
    }
    if (!blob) {
      app.historyMessage = 'Your records could not be downloaded. Try again.';
    } else {
      const url = URL.createObjectURL(blob);
      const link = el('a', { href: url, download: 'speech-practice-private-records.json', hidden: true });
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      app.historyMessage = 'Download started.';
    }
    renderHistory();
    focusKey('export');
  }

  // ---------- private rendering ----------

  function captureFocus() {
    const active = document.activeElement;
    if (!active || !ui.privateBody.contains(active)) return null;
    return active.getAttribute('data-key') || '';
  }

  function focusKey(key) {
    const escaped = key && window.CSS && CSS.escape ? CSS.escape(key) : key;
    const target = key ? ui.privateBody.querySelector(`[data-key="${escaped}"]`) : null;
    if (target && !target.disabled) {
      target.focus({ preventScroll: true });
      return true;
    }
    return false;
  }

  function restoreFocus(key) {
    if (key === null) return;
    const active = document.activeElement;
    if (active && active !== document.body && ui.privateBody.contains(active)) return;
    if (focusKey(key)) return;
    const fallback = document.getElementById('current-heading') || ui.privateHeading;
    fallback.focus({ preventScroll: true });
  }

  function renderPrivate() {
    renderAccount();
    renderPracticeControls();
    if (!authed()) {
      clearPrivateDom();
      return;
    }
    const key = captureFocus();
    const s = app.priv;
    if (!s) {
      clearPrivateDom();
      replaceAll(ui.privateStatus, app.privState === 'error'
        ? el('p', { class: 'notice' }, 'Private checks could not be loaded. Practice still works. ',
          el('button', { type: 'button', class: 'link-button', 'data-key': 'state-retry', onclick: () => loadState(), text: 'Try again' }))
        : el('p', { class: 'quiet', role: 'status', text: 'Loading private checks…' }));
      restoreFocus(key);
      return;
    }
    replaceAll(ui.privateStatus, app.privState === 'error'
      ? el('p', { class: 'notice' }, 'Private checks could not be refreshed. ',
        el('button', { type: 'button', class: 'link-button', 'data-key': 'state-retry', onclick: () => loadState(), text: 'Try again' }))
      : '');
    renderCheckPanel();
    renderCurrent(true);
    renderParticipation();
    renderHistory();
    restoreFocus(key);
  }

  function chosenItemId(prompt) {
    const items = app.priv ? app.priv.inventory : [];
    const stored = app.itemChoice.get(prompt.id);
    if (stored && items.some((i) => i.id === stored && i.available)) return stored;
    const match = items.find((i) => i.kind === 'public_reference' && i.available && i.sourceWord === prompt.sourceWord);
    return match ? match.id : '';
  }

  function itemById(id) {
    return app.priv ? app.priv.inventory.find((i) => i.id === id) || null : null;
  }

  function itemLabel(id) {
    const item = id ? itemById(id) : null;
    return item ? item.label : 'Example no longer listed';
  }

  function itemDescription(item, prompt) {
    if (!item) return 'Choose an existing example recording to check.';
    const parts = [];
    if (item.kind === 'invented_fixture') {
      parts.push('Invented non-speech example. It is not a recording of anyone saying a word.');
    } else {
      parts.push(`Registered example recording${item.sourceWord ? ` of “${item.sourceWord}”` : ''}. Speaker age not known.`);
      if (item.sourceWord && item.sourceWord !== prompt.sourceWord) {
        parts.push('This is a different word from the one selected; use it to see how a mismatched example is handled.');
      }
    }
    if (!item.available) parts.push('Not available right now.');
    return parts.join(' ');
  }

  function updateItemSelection(prompt) {
    if (!dyn.select) return;
    const id = dyn.select.value;
    dyn.itemNote.textContent = itemDescription(itemById(id), prompt);
    privatePlayer.setSource(id ? safePath(`/api/references/${encodeURIComponent(id)}`) : null);
    syncCheckControls();
  }

  function syncCheckControls() {
    if (!dyn.runButton) return;
    const blocked = app.busy.start || app.busy.clear || isLivePending(app.current);
    dyn.runButton.disabled = blocked || !dyn.select || !dyn.select.value;
    dyn.runButton.textContent = app.busy.start ? 'Starting…' : 'Run check';
  }

  function optionFor(item) {
    return el('option', {
      value: item.id,
      disabled: !item.available,
      text: item.available ? item.label : `${item.label} (unavailable)`,
    });
  }

  function renderCheckPanel() {
    const p = selectedPrompt();
    const s = app.priv;
    if (!p || !s) {
      replaceAll(ui.checkPanel, );
      dyn.select = null;
      dyn.runButton = null;
      privatePlayer.setSource(null);
      return;
    }
    const refs = s.inventory.filter((i) => i.kind === 'public_reference');
    const fixtures = s.inventory.filter((i) => i.kind === 'invented_fixture');
    const select = el('select', { id: 'check-item', 'data-key': 'item', 'aria-describedby': 'check-item-note' },
      el('option', { value: '', text: 'Choose an example' }),
      refs.length ? el('optgroup', { label: 'Registered example recordings' }, refs.map(optionFor)) : null,
      fixtures.length ? el('optgroup', { label: 'Invented non-speech examples' }, fixtures.map(optionFor)) : null);
    select.value = chosenItemId(p);
    select.addEventListener('change', () => {
      app.itemChoice.set(p.id, select.value);
      app.checkMessage = '';
      updateItemSelection(p);
      renderCurrent();
    });

    const runButton = el('button', {
      type: 'button',
      class: 'button primary',
      'data-key': 'run',
      onclick: () => startCheck(p.id, select.value, null),
      text: 'Run check',
    });
    const playButton = el('button', { type: 'button', class: 'button', 'data-key': 'play-item' });
    const playStatus = el('p', { class: 'quiet status-line', role: 'status' });
    const itemNote = el('p', { id: 'check-item-note', class: 'quiet small' });

    const variant = p.variants.find((v) => v.id === p.selectedVariantId) || p.variants[0] || null;
    const occurrence = variant && p.selectedOccurrenceIndex !== null && p.selectedOccurrenceIndex < variant.phones.length
      ? `Sound ${p.selectedOccurrenceIndex + 1} of ${variant.phones.length}`
      : 'Not stated';

    replaceAll(ui.checkPanel, 
      el('h3', { class: 'minor', text: `Check an example for ${promptLabel(p)}` }),
      el('p', { text: 'A check sends an existing example recording through the research model. It does not use a microphone, does not record a child, and is not a new attempt at the word.' }),
      p.supported ? null : el('p', { class: 'notice', text: "The research model in this build does not cover this word's target sound, so a check will end without a result. Practice is not affected." }),
      el('div', { class: 'field field-wide' },
        el('label', { for: 'check-item', text: 'Example recording' }),
        select,
        itemNote),
      el('div', { class: 'actions' }, runButton, playButton),
      playStatus,
      el('div', { class: 'not-offered' },
        el('button', { type: 'button', class: 'button', disabled: true, 'aria-describedby': 'not-offered-note', text: 'Record a new attempt' }),
        el('p', { id: 'not-offered-note', class: 'quiet small', text: 'Not offered. Recording new speech and planned reassessment are not part of this build.' })),
      el('details', { class: 'tech' },
        el('summary', { text: 'Engineering details for this word' }),
        el('dl', { class: 'facts' },
          fact('Prompt', p.id),
          fact('Target sound code', p.targetPhone || 'Not stated'),
          fact('Dictionary form', variant && variant.phones.length ? variant.phones.join(' ') : 'Not stated'),
          fact('Selected position', occurrence),
          fact('Other dictionary forms', String(Math.max(0, p.variants.length - 1))),
          fact('Model coverage', p.supported ? 'Covered for engineering checks' : 'Not covered in this build'),
          fact('Meaning', 'The dictionary form is the intended target only, not what any speaker said.'))),
    );

    dyn.select = select;
    dyn.runButton = runButton;
    dyn.itemNote = itemNote;
    privatePlayer.attach(playButton, playStatus);
    updateItemSelection(p);
  }

  function renderCurrent(force) {
    if (!authed() || !app.priv) return;
    const cur = app.current;
    const d = cur ? describeRow(cur) : null;
    const signature = JSON.stringify([
      cur && cur.id, d && d.label, d && d.text, cur && cur.itemId, app.selectedId,
      app.busy.cancel, app.busy.start, app.busy.clear, app.pollFailed, app.checkMessage,
    ]);
    if (!force && signature === currentSignature) return;
    currentSignature = signature;
    const key = captureFocus();

    const nodes = [el('h3', { id: 'current-heading', class: 'minor', tabindex: '-1', text: 'Latest check for this word' })];
    if (!cur) {
      nodes.push(el('p', { class: 'quiet', text: 'No checks for this word yet.' }));
    } else {
      const time = formatTime(cur.createdAt);
      nodes.push(el('div', { class: 'outcome' },
        el('p', { class: 'outcome-status' },
          el('strong', { text: d.label }),
          time ? el('time', { class: 'quiet', datetime: cur.createdAt, text: time }) : null),
        el('p', { text: d.text }),
        el('p', { class: 'quiet small', text: `Example: ${itemLabel(cur.itemId)}` }),
        cur.isReplay ? el('p', { class: 'quiet small', text: 'Replay of an earlier check using the same example recording.' }) : null));

      if (isLivePending(cur)) {
        nodes.push(el('div', { class: 'actions' },
          el('button', {
            type: 'button',
            class: 'button',
            'data-key': 'cancel',
            disabled: app.busy.cancel,
            onclick: cancelCheck,
            text: app.busy.cancel ? 'Cancelling…' : 'Cancel check',
          })));
        if (app.pollFailed) {
          nodes.push(el('p', { class: 'notice' }, 'No update could be fetched for this check. Practice is still available. ',
            el('button', {
              type: 'button',
              class: 'link-button',
              'data-key': 'poll-retry',
              onclick: () => { startPoll(cur.id, 0); renderCurrent(); },
              text: 'Check for an update',
            })));
        }
      } else if (cur.status !== 'forgotten' && cur.itemId) {
        const blocked = app.busy.start || app.busy.clear;
        nodes.push(el('div', { class: 'actions' },
          el('button', {
            type: 'button',
            class: 'button',
            'data-key': 'replay',
            disabled: blocked,
            'aria-describedby': 'replay-note',
            onclick: () => startCheck(cur.promptId, cur.itemId, cur.id),
            text: 'Replay check',
          })),
        el('p', { id: 'replay-note', class: 'quiet small', text: 'Runs the same example recording again to check that processing is repeatable. It is not a new recording and does not show improvement.' }));
      }

      nodes.push(el('p', { class: 'small' }, 'Practice is still available. ',
        el('button', { type: 'button', class: 'link-button', 'data-key': 'to-practice', onclick: focusPractice, text: 'Back to practice' })));
    }
    if (app.checkMessage) nodes.push(el('p', { class: 'error', role: 'alert', text: app.checkMessage }));

    replaceAll(ui.currentCheck, ...nodes);
    restoreFocus(key);
  }

  function renderParticipation() {
    const part = app.priv && app.priv.participation;
    if (!part) {
      replaceAll(ui.participation, );
      return;
    }
    const rows = [
      ['Checks planned', part.planned],
      ['Checks started', part.started],
      ['Checks finished', part.terminal],
      ['Replay checks', part.replays],
      ['Practice marks', part.manualPractice],
    ].filter((row) => row[1] !== null);
    replaceAll(ui.participation, 
      el('h3', { class: 'minor', text: 'Taking part' }),
      el('dl', { class: 'counts' }, rows.map(([term, value]) =>
        el('div', null, el('dt', { text: term }), el('dd', { text: String(value) })))),
      el('p', { class: 'quiet small', text: 'These count taking part. They do not measure speech or improvement. A check can finish without starting if its example cannot be processed.' }),
    );
  }

  function historyRow(row) {
    const d = describeRow(row);
    const prompt = app.promptById.get(row.promptId);
    const time = formatTime(row.createdAt);
    const canReplay = d.terminal && row.status !== 'forgotten' && row.itemId && prompt;
    const meta = [time, itemLabel(row.itemId), row.isReplay ? 'Replay of an earlier check' : ''].filter(Boolean).join(' · ');
    return el('li', { class: 'history-row' },
      el('div', { class: 'history-text' },
        el('p', { class: 'history-main' },
          el('span', { class: 'history-word', text: prompt ? promptLabel(prompt) : 'Word no longer listed' }),
          el('span', { class: 'history-status', text: d.label })),
        el('p', { class: 'quiet small', text: meta }),
        el('p', { class: 'small', text: d.text })),
      canReplay
        ? el('button', {
          type: 'button',
          class: 'link-button',
          'data-key': `replay-${row.id}`,
          disabled: app.busy.start || app.busy.clear || isLivePending(app.current),
          'aria-label': `Replay check: ${prompt.word}, ${time || 'earlier check'}`,
          onclick: () => {
            if (row.promptId !== app.selectedId) selectPrompt(row.promptId);
            startCheck(row.promptId, row.itemId, row.id);
          },
          text: 'Replay check',
        })
        : null);
  }

  function renderHistory() {
    if (!app.priv) {
      replaceAll(ui.history, );
      return;
    }
    const key = captureFocus();
    const rows = newestFirst(app.priv.history);
    const confirm = app.confirmClear
      ? el('div', {
        id: 'clear-confirm',
        class: 'confirm',
        role: 'group',
        'aria-labelledby': 'clear-confirm-text',
        onkeydown: (event) => {
          if (event.key === 'Escape') {
            app.confirmClear = false;
            renderHistory();
            focusKey('clear');
          }
        },
      },
      el('p', { id: 'clear-confirm-text', text: 'Clear your private check history? Derived outcomes will be deleted. Minimal attempt and replay records and participation counts are kept. Public example recordings are not affected, and this is not secure erasure.' }),
      el('div', { class: 'actions' },
        el('button', {
          type: 'button',
          class: 'button primary',
          'data-key': 'clear-confirm',
          disabled: app.busy.clear,
          onclick: clearHistory,
          text: app.busy.clear ? 'Clearing…' : 'Clear history',
        }),
        el('button', {
          type: 'button',
          class: 'button',
          'data-key': 'clear-keep',
          disabled: app.busy.clear,
          onclick: () => { app.confirmClear = false; renderHistory(); focusKey('clear'); },
          text: 'Keep history',
        })))
      : null;

    replaceAll(ui.history, 
      el('h3', { id: 'history-heading', class: 'minor', tabindex: '-1', text: 'Private history' }),
      el('p', { class: 'quiet small', text: 'Every check is listed with its outcome. There are no scores.' }),
      rows.length
        ? el('ol', { class: 'history-list' }, rows.map(historyRow))
        : el('p', { class: 'quiet', text: 'No private checks yet.' }),
      el('div', { class: 'actions history-tools' },
        el('button', {
          type: 'button',
          class: 'button small',
          'data-key': 'export',
          disabled: app.busy.export,
          onclick: exportRecords,
          text: app.busy.export ? 'Preparing…' : 'Download my records',
        }),
        el('button', {
          type: 'button',
          class: 'button small',
          'data-key': 'clear',
          'aria-expanded': String(app.confirmClear),
          'aria-controls': app.confirmClear ? 'clear-confirm' : null,
          disabled: app.busy.clear,
          onclick: () => {
            app.confirmClear = true;
            app.historyMessage = '';
            renderHistory();
            focusKey('clear-keep');
          },
          text: 'Clear private history…',
        })),
      confirm,
      app.historyMessage ? el('p', { class: 'status-line', role: 'status', text: app.historyMessage }) : null,
    );
    restoreFocus(key);
  }

  // ---------- boot ----------

  async function boot() {
    for (const id of [
      'word-status', 'word-list', 'catalog-retry', 'practice', 'practice-empty', 'practice-message',
      'practice-body', 'word-heading', 'word-position', 'picture', 'picture-missing', 'play', 'play-status',
      'practised', 'practice-status', 'practice-count', 'reference-details', 'open-private', 'account',
      'account-name', 'logout', 'private', 'private-heading', 'private-notice', 'signin', 'signin-form',
      'account-id', 'password', 'signin-submit', 'signin-error', 'session-error', 'session-retry',
      'private-body', 'private-status', 'check-panel', 'current-check', 'participation', 'history', 'announcer',
    ]) {
      ui[camel(id)] = document.getElementById(id);
    }

    publicPlayer.attach(ui.play, ui.playStatus);
    ui.picture.addEventListener('error', () => {
      if (!ui.picture.getAttribute('src')) return;
      ui.picture.hidden = true;
      ui.pictureMissing.hidden = false;
    });
    ui.picture.addEventListener('load', () => {
      ui.picture.hidden = false;
      ui.pictureMissing.hidden = true;
    });
    ui.wordList.addEventListener('keydown', onWordListKey);
    ui.catalogRetry.addEventListener('click', loadCatalog);
    ui.practised.addEventListener('click', markPractised);
    ui.openPrivate.addEventListener('click', onOpenPrivate);
    ui.signinForm.addEventListener('submit', onSignin);
    ui.logout.addEventListener('click', logout);
    ui.sessionRetry.addEventListener('click', retrySession);

    renderPracticeControls();
    renderAccount();
    loadCatalog();
    await refreshSession();
    if (authed()) {
      app.privateOpen = true;
      loadState();
    }
    renderAccount();
    renderPracticeControls();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
