'use strict';

// Assessment validation workbench — static operator UI.
// Every value returned by the server is rendered through text nodes or
// attribute setters; nothing from the API is ever parsed as HTML.

(() => {
  // ---------- Constants ----------

  const ROLES = [
    { id: 'coordinator', label: 'Coordinator' },
    { id: 'reviewer-a', label: 'Reviewer A' },
    { id: 'reviewer-b', label: 'Reviewer B' },
    { id: 'adjudicator', label: 'Adjudicator' },
  ];
  const ROLE_IDS = ROLES.map((r) => r.id);
  const REVIEWER_IDS = ['reviewer-a', 'reviewer-b'];

  const ANSWER_FIELDS = [
    { key: 'speech', legend: 'Speech', question: 'Is speech present?',
      options: ['present', 'absent', 'uncertain', 'unavailable'] },
    { key: 'promptMatch', legend: 'Prompt match', question: 'Does the speech match the prompted word?',
      options: ['matched', 'mismatched', 'uncertain', 'unavailable'] },
    { key: 'occurrence', legend: 'Occurrence', question: 'Can the marked target occurrence be located?',
      options: ['resolved', 'ambiguous', 'unavailable'] },
    { key: 'target', legend: 'Target', question: 'How was the target phone realised?',
      options: ['expected', 'altered', 'omitted', 'indeterminate', 'unscorable'] },
    { key: 'quality', legend: 'Quality', question: 'Is the material usable for review?',
      options: ['usable', 'limited', 'unusable'] },
  ];
  const TARGET_OPTIONS = ANSWER_FIELDS.find((f) => f.key === 'target').options;
  const SCORABLE_TARGETS = ['expected', 'altered', 'omitted'];
  // Applied only when a reviewer explicitly presses the button for an item with no recording.
  const UNAVAILABLE_FILL = {
    speech: 'unavailable', promptMatch: 'unavailable', occurrence: 'unavailable',
    target: 'unscorable', quality: 'unusable',
  };

  const CONTENT_DECISIONS = [
    { value: 'accepted', label: 'Accepted for engineering use' },
    { value: 'revise', label: 'Needs revision' },
    { value: 'pending', label: 'Pending' },
  ];
  const RIGHTS = ['allowed', 'unknown', 'denied'];

  const NOTES_MAX = 2000;
  const SAFE_ID_MAX = 128; // matches the backend safe-ID limit
  const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
  const HEX64 = /^[0-9a-f]{64}$/;

  const LABELS = {
    taskSha256: 'Task',
    policySha256: 'Policy',
    promptSha256: 'Prompt',
    permissionSha256: 'Permissions',
  };

  // Plain words shown before fixed codes. Unknown codes fall back to a readable form of the code itself.
  const CODE_TEXT = {
    engineering_ready: 'Engineering ready',
    abstain: 'Abstains',
    processed_unverified: 'Processed, unverified',
    recording_absent: 'No recording',
    terminal_failed: 'Attempt failed',
    terminal_skipped: 'Attempt skipped',
    terminal_rejected: 'Attempt rejected',
    terminal_cancelled: 'Attempt cancelled',
    model_unavailable: 'No processed prediction',
    speech_not_confirmed: 'Speech not confirmed present by both reviewers',
    prompt_not_matched: 'Prompt match not confirmed by both reviewers',
    occurrence_not_resolved: 'Target occurrence not resolved by both reviewers',
    occurrence_not_selected: 'No target occurrence selected for this attempt',
    quality_not_usable: 'Quality not usable for both reviewers',
    target_unscorable: 'Target not scorable',
    review_permission_denied: 'Review permission denied',
    research_permission_denied: 'Research permission denied',
    age_out_of_scope: 'Age outside the 6–12 scope',
    identity_linkage_unknown: 'Identity linkage unknown',
    household_unknown: 'Household unknown',
    unsupported_target: 'Target sound not in the model inventory',
    infeasible: 'Not possible with the current groups',
    feasible: 'Possible in principle (nothing is assigned)',
    fewer_than_three_joint_components: 'fewer than three separable groups',
  };

  const COVERAGE_TEXT = {
    recordingsPresent: 'Attempts with recording metadata',
    predictionsProcessed: 'Attempts with a processed prediction',
    engineeringReady: 'Attempts engineering ready',
    reviewACount: 'Attempts with a Reviewer A original',
    reviewBCount: 'Attempts with a Reviewer B original',
    pairedOriginalReviews: 'Attempts with both originals',
    adjudicated: 'Attempts adjudicated',
    participantsAttempted: 'Participants with at least one attempt',
    participantAgesKnown: 'Participants with a known age',
    participantHouseholdsKnown: 'Participants with a known household',
  };

  const FLAG_TEXT = {
    synthetic: 'Synthetic data',
    learnerFeedbackEligible: 'Learner feedback',
    clinicalUseEligible: 'Clinical use',
    productionUseEligible: 'Production use',
    qualifiedReviewEstablished: 'Qualified review',
    independentAuthenticationEstablished: 'Independent authentication',
    authenticationEstablished: 'Authentication of predictions',
    modelAccuracyEstablished: 'Model accuracy',
    clinicalValidityEstablished: 'Clinical validity',
    meaningfulImprovementEstablished: 'Meaningful improvement',
    predictionMeaning: 'Prediction meaning',
  };

  const STATUS_TEXT = {
    400: 'The server rejected the request as invalid.',
    404: 'The server does not provide this endpoint.',
    409: 'This conflicts with an existing record. Records are append-only and cannot be replaced.',
    413: 'The request was too large for the local server.',
  };

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ---------- App state ----------

  const app = {
    role: 'coordinator',
    state: null,
    status: 'idle', // idle | loading | refreshing | ready | error
    error: null,
    seq: 0,
    controller: null,
    ui: freshUi(),
  };

  function freshUi() {
    return {
      selectedItem: null,
      selectedAttempt: null,
      rosterFilter: 'all',
      expanded: new Set(),
      drafts: {},
      demo: null,
      sealedHere: false,
      focusId: null,
      pending: false,
    };
  }

  // ---------- Small helpers ----------

  const $ = (sel) => document.querySelector(sel);
  const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const arr = (v) => (Array.isArray(v) ? v : []);
  const str = (v) => (v === null || v === undefined ? '' : String(v));
  const isCount = (v) => typeof v === 'number' && Number.isFinite(v);

  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (v === true) el.setAttribute(k, '');
        else el.setAttribute(k, String(v));
      }
    }
    appendAll(el, children);
    return el;
  }

  function appendAll(el, children) {
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
  }

  function nil(text) {
    return h('span', { class: 'nil' }, text);
  }

  function humanize(code) {
    const words = str(code).replace(/[_-]+/g, ' ').trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : '';
  }

  function plain(code) {
    const c = str(code);
    return Object.prototype.hasOwnProperty.call(CODE_TEXT, c) ? CODE_TEXT[c] : humanize(c);
  }

  // Plain words first; the fixed code stays beside them for audit.
  function codeView(code) {
    const c = str(code);
    if (!c) return nil('Not reported');
    return h('span', { class: 'coded' }, plain(c), ' ', h('code', { class: 'chip' }, c));
  }

  function reasonList(codes, emptyText) {
    const list = arr(codes).map(str).filter(Boolean);
    if (!list.length) return nil(emptyText);
    return h('ul', { class: 'reason-list' }, list.map((c) => h('li', null, codeView(c))));
  }

  function codeList(list, emptyText) {
    const items = arr(list).map(str).filter(Boolean);
    if (!items.length) return nil(emptyText);
    return items.map((c, i) => [i ? ', ' : '', h('code', null, c)]);
  }

  function label(key) {
    if (Object.prototype.hasOwnProperty.call(LABELS, key)) return LABELS[key];
    const words = String(key)
      .replace(/_/g, ' ')
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .toLowerCase()
      .trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : String(key);
  }

  function roleName(id) {
    const r = ROLES.find((x) => x.id === id);
    return r ? r.label : str(id);
  }

  function fmtNum(n) {
    if (!Number.isFinite(n)) return String(n);
    return Number.isInteger(n) ? String(n) : n.toFixed(3);
  }

  function pct(n, d) {
    return d > 0 ? `${((n / d) * 100).toFixed(1)}%` : 'no denominator';
  }

  function rateView(rate, n) {
    if (!isCount(rate)) return nil('Not defined: no pairs to compare');
    const share = `${(rate * 100).toFixed(1)}%`;
    return Number.isInteger(n) && n > 0 ? `${share} (${Math.round(rate * n)} of ${n})` : share;
  }

  function signed(x) {
    if (!isCount(x)) return '—';
    if (Math.abs(x) < 0.005) return '0.00';
    return `${x > 0 ? '+' : '−'}${Math.abs(x).toFixed(2)}`;
  }

  function hashView(sha, full) {
    const s = str(sha);
    if (!s) return nil('Not recorded');
    if (full || s.length <= 16) return h('code', { class: 'hash' }, s);
    return h('code', { class: 'hash', title: s }, `${s.slice(0, 12)}…`,
      h('span', { class: 'sr-only' }, ` full digest ${s}`));
  }

  function phonesView(phones, highlight) {
    const marks = arr(highlight);
    return h('span', { class: 'phones' }, arr(phones).map((p, i) => {
      const target = marks.includes(i);
      return h('span', { class: target ? 'ph ph-target' : 'ph' }, str(p),
        target ? h('span', { class: 'sr-only' }, ' (target occurrence)') : null);
    }));
  }

  function answerOf(rec) {
    if (!isObj(rec)) return null;
    return isObj(rec.answer) ? rec.answer : rec;
  }
  function targetOf(rec) {
    const a = answerOf(rec);
    return a && typeof a.target === 'string' ? a.target : null;
  }
  function shaOf(rec) {
    return isObj(rec) && typeof rec.sha256 === 'string' ? rec.sha256 : null;
  }
  function disagrees(a) {
    const ta = targetOf(a.reviewA);
    const tb = targetOf(a.reviewB);
    return Boolean(ta && tb && ta !== tb);
  }
  function admissionStatus(a) {
    return isObj(a.admission) && typeof a.admission.status === 'string' ? a.admission.status : null;
  }
  function sealText(v) {
    if (v === true) return 'Sealed';
    if (v === false) return 'Not sealed';
    return 'Not reported';
  }
  function eligibilityText(v) {
    if (v === false) return 'Not eligible';
    if (v === undefined) return nil('Not reported');
    // The contract pins these false; anything else is shown as the raw value, never as a claim.
    return h('span', null, 'Unexpected value ', h('code', null, safeJson(v)));
  }
  function isFraction(v) {
    return isObj(v) && isCount(v.numerator) && isCount(v.denominator);
  }

  function safeJson(v) {
    try { return JSON.stringify(v, null, 2); } catch (_) { return '[unprintable]'; }
  }

  function more(summaryText, ...body) {
    return h('details', { class: 'more' }, h('summary', null, summaryText), h('div', { class: 'more-body' }, ...body));
  }

  function rawDetails(summaryText, value) {
    return h('details', { class: 'raw-json' }, h('summary', null, summaryText), h('pre', { class: 'raw' }, safeJson(value)));
  }

  // ---------- API ----------

  class ApiError extends Error {
    constructor(code, status) {
      super(code);
      this.name = 'ApiError';
      this.code = code;
      this.status = status;
    }
  }

  async function request(path, { method = 'GET', body, signal } = {}) {
    const init = {
      method,
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (err) {
      if (err && err.name === 'AbortError') throw err;
      throw new ApiError('network_unavailable', 0);
    }
    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (_) {
        throw new ApiError(res.ok ? 'invalid_response' : `http_${res.status}`, res.status);
      }
    }
    if (!res.ok || (isObj(data) && data.ok === false)) {
      const code = isObj(data) && typeof data.error === 'string' ? data.error : `http_${res.status}`;
      throw new ApiError(code, res.status);
    }
    return { data, text };
  }

  async function api(path, opts) {
    return (await request(path, opts)).data;
  }

  function describeError(err) {
    const code = err && typeof err.code === 'string' ? err.code : 'unexpected_error';
    let message;
    if (code === 'network_unavailable') message = 'The local server could not be reached. Check that it is running, then retry.';
    else if (code === 'invalid_response') message = 'The server sent a response that could not be read.';
    else if (err && STATUS_TEXT[err.status]) message = STATUS_TEXT[err.status];
    else message = 'The request did not complete.';
    return { code, message };
  }

  function errorNodes(err) {
    const { code, message } = describeError(err);
    return [message, ' ', h('span', { class: 'muted' }, '(code '), h('code', null, code), h('span', { class: 'muted' }, ')')];
  }

  // ---------- Feedback ----------

  function flash(text, isError) {
    const box = $('#flash');
    box.classList.add('is-visible');
    box.classList.toggle('is-error', Boolean(isError));
    $('#flash-text').textContent = text;
    $('#flash-dismiss').hidden = false;
  }
  function clearFlash() {
    $('#flash').classList.remove('is-visible', 'is-error');
    $('#flash-text').textContent = '';
    $('#flash-dismiss').hidden = true;
  }

  function formMsg() {
    return h('p', { class: 'form-msg', role: 'alert' });
  }
  function setMsg(el, nodesOrText, kind) {
    el.className = `form-msg ${kind || 'error'}`;
    el.replaceChildren();
    appendAll(el, [nodesOrText]);
  }

  function setBusy(btn, busy, busyText) {
    if (!btn) return;
    if (busy) {
      btn.dataset.label = btn.textContent;
      btn.textContent = busyText || 'Working…';
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
    } else {
      if (btn.dataset.label) btn.textContent = btn.dataset.label;
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
    }
  }

  // POST helper. Returns the response body on success, null on failure (message shown inline).
  async function post(path, body, { button, msg, busyText, success }) {
    const operationUi = app.ui;
    if (operationUi.pending) return null;
    operationUi.pending = true;
    setBusy(button, true, busyText || 'Saving…');
    if (msg) msg.replaceChildren();
    try {
      const res = await api(path, { method: 'POST', body });
      if (app.ui !== operationUi) return null;
      const rev = isObj(res) && Number.isInteger(res.revision) ? ` Revision ${res.revision}.` : '';
      flash(`${success}${rev}`);
      return res || {};
    } catch (err) {
      if (app.ui !== operationUi) return null;
      if (msg) setMsg(msg, errorNodes(err));
      else flash(describeError(err).message, true);
      return null;
    } finally {
      operationUi.pending = false;
      if (app.ui === operationUi) setBusy(button, false);
    }
  }

  function confirmAction({ title, body, confirmLabel }) {
    const dlg = $('#confirm');
    if (typeof dlg.showModal !== 'function') {
      return Promise.resolve(window.confirm(`${title}\n\n${arr(body).join('\n\n')}`));
    }
    return new Promise((resolve) => {
      $('#confirm-title').textContent = title;
      $('#confirm-body').replaceChildren(...arr(body).map((p) => h('p', null, p)));
      const ok = $('#confirm-ok');
      const cancel = $('#confirm-cancel');
      ok.textContent = confirmLabel || 'Confirm';
      let result = false;
      const onOk = () => { result = true; dlg.close(); };
      const onCancel = () => { dlg.close(); };
      const onClose = () => {
        ok.removeEventListener('click', onOk);
        cancel.removeEventListener('click', onCancel);
        dlg.removeEventListener('close', onClose);
        resolve(result);
      };
      ok.addEventListener('click', onOk);
      cancel.addEventListener('click', onCancel);
      dlg.addEventListener('close', onClose);
      dlg.showModal();
      cancel.focus();
    });
  }

  function scrollBehavior() {
    return reducedMotion.matches ? 'auto' : 'smooth';
  }

  // ---------- Routing and loading ----------

  function roleFromHash() {
    const m = /^#role=([a-z-]+)$/.exec(window.location.hash);
    return m && ROLE_IDS.includes(m[1]) ? m[1] : null;
  }

  function goRole(role) {
    window.location.hash = `role=${role}`;
  }

  function switchRole(role) {
    const dialog = $('#confirm');
    if (dialog.open) dialog.close();
    if (app.controller) app.controller.abort();
    app.role = role;
    app.state = null; // never carry one role's payload into another view
    app.error = null;
    app.ui = freshUi();
    clearFlash();
    load({ focusView: true });
  }

  async function load({ focusView } = {}) {
    const seq = ++app.seq;
    if (app.controller) app.controller.abort();
    const controller = new AbortController();
    app.controller = controller;
    const role = app.role;

    if (app.state) {
      app.status = 'refreshing';
      const indicator = document.getElementById('refresh-state');
      if (indicator) indicator.textContent = 'Refreshing…';
    } else {
      app.status = 'loading';
      render();
    }

    try {
      const data = await api(`/api/state?role=${encodeURIComponent(role)}`, { signal: controller.signal });
      if (seq !== app.seq) return;
      if (!isObj(data)) throw new ApiError('invalid_response', 200);
      app.state = data;
      app.status = 'ready';
      app.error = null;
    } catch (err) {
      if ((err && err.name === 'AbortError') || seq !== app.seq) return;
      app.status = 'error';
      app.error = err;
    }
    render();
    if (focusView && !app.ui.focusId) focusEl('view-title');
  }

  function focusEl(id) {
    const el = document.getElementById(id);
    if (el) el.focus();
  }

  // ---------- Frame rendering ----------

  function render() {
    updateNav();
    updateProjectLine();
    const main = $('#main');
    main.setAttribute('aria-busy', app.status === 'loading' ? 'true' : 'false');
    main.replaceChildren(buildView());
    if (app.ui.focusId) {
      const id = app.ui.focusId;
      app.ui.focusId = null;
      focusEl(id);
    }
  }

  function updateNav() {
    document.querySelectorAll('.roles a[data-role]').forEach((a) => {
      if (a.dataset.role === app.role) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    document.title = `${roleName(app.role)} · Assessment validation workbench`;
  }

  function updateProjectLine() {
    const line = $('#project-line');
    const p = app.state && isObj(app.state.project) ? app.state.project : null;
    if (!p) { line.replaceChildren(); return; }
    const task = isObj(p.task) ? p.task : {};
    const parts = [];
    if (p.title) parts.push(h('span', null, str(p.title)));
    if (p.mode) parts.push(h('span', null, `${plain(p.mode)} mode`));
    if (task.id) {
      parts.push(h('span', null, 'Task ', h('code', null, str(task.id)),
        str(task.version) ? [', version ', h('code', null, str(task.version))] : null));
    }
    if (task.definitionSource) parts.push(h('span', null, `Definition source: ${plain(task.definitionSource).toLowerCase()}`));
    const nodes = [];
    parts.forEach((n, i) => {
      if (i) nodes.push(h('span', { class: 'sep', 'aria-hidden': 'true' }, '·'));
      nodes.push(n);
    });
    line.replaceChildren(...nodes);
  }

  function buildView() {
    const roleLabel = roleName(app.role);
    if (!app.state) {
      if (app.status === 'error' && app.role === 'adjudicator' && app.error && app.error.status === 409) {
        return h('div', { class: 'state-panel' },
          h('h2', { id: 'view-title', tabindex: '-1' }, 'Waiting for both batches to be sealed'),
          h('p', null, 'Adjudication opens after Reviewer A and Reviewer B have each sealed their batch. Nothing needs doing here yet.'),
          h('p', { class: 'muted small' }, 'Server code ', h('code', null, describeError(app.error).code)),
          h('div', { class: 'actions' },
            h('button', { type: 'button', class: 'btn', onclick: () => load({ focusView: true }) }, 'Check again')));
      }
      if (app.status === 'error') {
        return h('div', { class: 'state-panel', role: 'alert' },
          h('h2', { id: 'view-title', tabindex: '-1' }, `Could not load the ${roleLabel} view`),
          h('p', null, errorNodes(app.error)),
          h('div', { class: 'actions' },
            h('button', { type: 'button', class: 'btn btn-primary', onclick: () => load({ focusView: true }) }, 'Retry')));
      }
      return h('div', { class: 'state-panel' },
        h('h2', { id: 'view-title', tabindex: '-1' }, `Loading ${roleLabel} view…`),
        h('p', null, 'Reading local records from the workbench server.'));
    }
    if (app.role === 'coordinator') return renderCoordinator(app.state);
    if (REVIEWER_IDS.includes(app.role)) return renderReviewer(app.state);
    return renderAdjudicator(app.state);
  }

  function viewHead(title, desc) {
    return h('div', { class: 'view-head' },
      h('div', null,
        h('h2', { class: 'view-title', id: 'view-title', tabindex: '-1' }, title),
        desc ? h('p', { class: 'view-desc' }, desc) : null),
      h('div', { class: 'view-tools' },
        h('span', { class: 'refresh-state', id: 'refresh-state', 'aria-live': 'polite' }, ''),
        h('button', { type: 'button', class: 'btn', onclick: () => load() }, 'Refresh')));
  }

  function staleBanner() {
    if (app.status !== 'error' || !app.error) return null;
    return h('div', { class: 'banner banner-error', role: 'alert' },
      'Could not refresh. Showing the last records loaded. ', errorNodes(app.error));
  }

  function section(id, n, title, lede, ...body) {
    return h('section', { class: 'section', id, 'aria-labelledby': `${id}-h` },
      h('header', { class: n ? 'section-head' : 'section-head unnumbered' },
        n ? h('span', { class: 'step-n', 'aria-hidden': 'true' }, String(n)) : null,
        h('h2', { id: `${id}-h`, tabindex: '-1' }, n ? h('span', { class: 'sr-only' }, `Step ${n}: `) : null, title),
        lede ? h('p', { class: 'lede' }, lede) : null),
      ...body);
  }

  function replaceSection(id, builder) {
    const old = document.getElementById(id);
    if (old && app.state) old.replaceWith(builder(app.state));
  }

  function tableWrap(table, labelText) {
    return h('div', { class: 'table-wrap', role: 'region', 'aria-label': labelText, tabindex: '0' }, table);
  }

  function th(text, cls) {
    return h('th', { scope: 'col', class: cls || null }, text);
  }

  // ---------- Coordinator ----------

  function contentIndex(list) {
    const entries = Array.isArray(list) ? list : (isObj(list) ? arr(list.history) : []);
    const currentMap = isObj(list) && isObj(list.current) ? list.current : null;
    const map = new Map();
    for (const entry of entries) {
      if (!isObj(entry)) continue;
      const rec = isObj(entry.record) ? entry.record : entry;
      const pid = str(entry.promptId !== undefined ? entry.promptId : rec.promptId);
      if (!pid) continue;
      if (!map.has(pid)) map.set(pid, []);
      map.get(pid).push({ entry, rec });
    }
    const out = new Map();
    const ids = new Set([...map.keys(), ...(currentMap ? Object.keys(currentMap) : [])]);
    for (const pid of ids) {
      const items = map.get(pid) || [];
      let current = null;
      if (currentMap && isObj(currentMap[pid])) {
        const e = currentMap[pid];
        current = { entry: e, rec: isObj(e.record) ? e.record : e };
      } else {
        current = items.find((i) => i.entry.current === true) || items[items.length - 1] || null;
      }
      const history = items.filter((i) => i !== current && i.entry !== (current && current.entry));
      out.set(pid, { current, history });
    }
    return out;
  }

  function coordinatorModel(s) {
    const prompts = arr(s.prompts).filter(isObj);
    const report = isObj(s.report) ? s.report : {};
    const admissionMap = isObj(report.admissionByAttemptId) ? report.admissionByAttemptId : {};
    // Attempts normally carry their own admission; fall back to the report map only when absent.
    const attempts = arr(s.attempts).filter(isObj).map((a) => (
      isObj(a.admission) || !isObj(admissionMap[str(a.id)]) ? a : { ...a, admission: admissionMap[str(a.id)] }));
    const content = contentIndex(s.contentReviews);
    const seals = isObj(s.seals) ? s.seals : {};
    const accepted = prompts.filter((p) => {
      const c = content.get(str(p.id));
      return c && c.current && c.current.rec.decision === 'accepted';
    }).length;
    return {
      prompts, attempts, content, seals, report,
      accepted,
      bothSealed: seals['reviewer-a'] === true && seals['reviewer-b'] === true,
      aCount: attempts.filter((a) => a.reviewA).length,
      bCount: attempts.filter((a) => a.reviewB).length,
      paired: attempts.filter((a) => a.reviewA && a.reviewB).length,
      disagreements: attempts.filter(disagrees),
      adjudicated: attempts.filter((a) => a.adjudication).length,
      lock: isObj(s.predictionLock) ? s.predictionLock : null,
    };
  }

  // Attempts are numbered 1..N in manifest order everywhere in the coordinator view.
  function attemptIndex(s) {
    const numbers = new Map();
    const words = new Map();
    arr(s.attempts).filter(isObj).forEach((a, i) => {
      numbers.set(str(a.id), i + 1);
      words.set(str(a.id), str(a.word));
    });
    return { numbers, words, total: numbers.size };
  }

  function attemptRef(id, idx) {
    const n = idx.numbers.get(str(id));
    return h('span', { class: 'attempt-ref' }, n ? h('span', { class: 'att-no' }, String(n)) : null, h('code', null, str(id)));
  }

  function attemptNumbers(ids, idx) {
    const list = arr(ids).map(str);
    if (!list.length) return nil('No attempts');
    const nums = list.map((id) => idx.numbers.get(id));
    if (!nums.every(Boolean)) return codeList(list, 'No attempts');
    return h('span', { class: 'num-list' }, `No. ${nums.join(', ')}`);
  }

  function renderCoordinator(s) {
    const m = coordinatorModel(s);
    const n = m.attempts.length;
    const agreement = isObj(m.report.agreement) ? m.report.agreement : null;
    const steps = [
      { id: 'sec-content', n: 1, title: 'Content review',
        status: `${m.accepted} of ${m.prompts.length} prompts accepted`,
        done: m.prompts.length > 0 && m.accepted === m.prompts.length },
      { id: 'sec-reviews', n: 2, title: 'Original reviews',
        status: `A ${m.aCount} of ${n} · B ${m.bCount} of ${n}`,
        done: n > 0 && m.aCount === n && m.bCount === n },
      { id: 'sec-seals', n: 3, title: 'Seals',
        status: `A ${sealText(m.seals['reviewer-a']).toLowerCase()} · B ${sealText(m.seals['reviewer-b']).toLowerCase()}`,
        done: m.bothSealed },
      { id: 'sec-lock', n: 4, title: 'Prediction lock',
        status: m.lock ? 'Locked' : 'Not locked', done: Boolean(m.lock) },
      { id: 'sec-adjudication', n: 5, title: 'Adjudication',
        status: m.bothSealed
          ? `${m.disagreements.length} ${m.disagreements.length === 1 ? 'target differs' : 'targets differ'} · ${m.adjudicated} adjudicated`
          : 'Waiting for both seals',
        done: m.bothSealed && m.disagreements.every((a) => a.adjudication) },
      { id: 'sec-report', n: 6, title: 'Report and export',
        status: agreement && agreement.available === false ? 'Agreement waiting for seals' : 'Recomputed each load',
        done: false },
      { id: 'sec-withdraw', n: null, title: 'Withdrawal', status: 'Example action', done: false },
    ];

    return h('div', null,
      viewHead('Coordinator',
        'Work through the sequence in order. Each action appends a record; nothing is edited in place.'),
      staleBanner(),
      h('div', { class: 'layout-coord' },
        renderRail(steps),
        h('div', { class: 'content' },
          contentSection(s),
          reviewsSection(s),
          sealsSection(s),
          lockSection(s),
          adjudicationSummarySection(s),
          reportSection(s),
          withdrawSection(s))));
  }

  function renderRail(steps) {
    return h('nav', { class: 'rail', 'aria-label': 'Operator sequence' },
      h('p', { class: 'rail-title' }, 'Operator sequence'),
      h('ol', null, steps.map((st) => h('li', null,
        h('button', {
          type: 'button',
          onclick: () => {
            const target = document.getElementById(st.id);
            if (!target) return;
            target.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
            const heading = document.getElementById(`${st.id}-h`);
            if (heading) heading.focus({ preventScroll: true });
          },
        },
        h('span', { class: 'rail-n', 'aria-hidden': 'true' }, st.n ? String(st.n) : '–'),
        h('span', { class: 'rail-name' }, st.title),
        h('span', { class: st.done ? 'rail-status done' : 'rail-status' },
          st.done ? h('span', { 'aria-hidden': 'true' }, '✓ ') : null,
          st.done ? h('span', { class: 'sr-only' }, 'Complete. ') : null,
          st.status))))));
  }

  // --- 1. Content review

  function contentSection(s) {
    const m = coordinatorModel(s);
    const rows = m.prompts.map((p) => {
      const c = m.content.get(str(p.id));
      const source = isObj(p.source) ? p.source : {};
      return h('tr', null,
        h('td', null, h('code', null, str(p.id)),
          str(p.version) ? h('div', { class: 'muted small' }, 'version ', str(p.version)) : null),
        h('td', null, h('span', { class: 'stack' }, h('div', null, str(p.word)),
          p.lexicalGroup ? h('div', { class: 'muted small' }, 'group ', str(p.lexicalGroup)) : null)),
        h('td', null, h('code', null, str(p.targetPhone)),
          p.language ? h('div', { class: 'muted small' }, str(p.language)) : null),
        h('td', null, arr(p.variants).filter(isObj).map((v) => h('div', { class: 'variant' },
          h('span', { class: 'variant-id' }, str(v.id)),
          phonesView(v.phones, v.occurrenceIndexes)))),
        h('td', null, h('div', null, source.kind ? plain(source.kind) : nil('Not reported')),
          source.sha256 ? hashView(source.sha256) : null),
        h('td', null, h('span', { class: 'pill' }, p.engineeringStatus ? plain(p.engineeringStatus) : 'Not reported')),
        h('td', null, contentCell(c)));
    });

    const table = h('table', null,
      h('caption', { class: 'sr-only' }, 'Prompts with manifest metadata and current content review'),
      h('thead', null, h('tr', null,
        ['Prompt', 'Word', 'Target', 'Variants (all target occurrences)', 'Source', 'Manifest status', 'Current content review']
          .map((t) => th(t)))),
      h('tbody', null, rows.length ? rows
        : h('tr', null, h('td', { colspan: '7', class: 'empty-cell' }, 'The manifest lists no prompts.'))));

    return section('sec-content', 1, 'Content review',
      'Engineering review of prompt content for this workbench. It is not clinical approval. The manifest prompt is never changed; reviews are appended and the latest is current.',
      tableWrap(table, 'Prompts'),
      h('p', { class: 'subnote roster-note' },
        'Variants mark every known occurrence of the target in the prompt definition, not the occurrence chosen for an attempt. Each attempt selects exactly one occurrence or none; an attempt with no selected occurrence always abstains, whatever any adjudication records.'),
      contentForm(m.prompts));
  }

  function decisionText(code) {
    const d = CONTENT_DECISIONS.find((x) => x.value === code);
    return d ? d.label : plain(code);
  }

  function referenceLine(ref) {
    return ['Reference ', h('code', null, str(ref.id)),
      str(ref.version) ? [', version ', h('code', null, str(ref.version))] : null,
      ` · rights ${str(ref.rights) || 'not reported'} · `, hashView(ref.sha256)];
  }

  function contentCell(c) {
    if (!c || !c.current) return nil('No content review recorded');
    const rec = c.current.rec;
    const ref = isObj(rec.reference) ? rec.reference : null;
    return h('div', null,
      h('div', null,
        h('span', { class: rec.decision === 'accepted' ? 'pill pill-accent' : 'pill' }, rec.decision ? decisionText(rec.decision) : 'Not reported'),
        rec.reviewerId ? h('span', { class: 'muted small' }, ` by ${str(rec.reviewerId)}`) : null),
      rec.notes ? h('div', { class: 'small' }, str(rec.notes)) : null,
      ref ? h('div', { class: 'small muted' }, referenceLine(ref))
        : h('div', { class: 'small muted' }, 'No reference attached'),
      c.history.length ? h('details', { class: 'history' },
        h('summary', null, `Earlier records (${c.history.length})`),
        h('ol', null, c.history.map(({ rec: r }) => h('li', null,
          h('strong', null, decisionText(r.decision)),
          r.reviewerId ? ` by ${str(r.reviewerId)}` : '',
          r.notes ? ` — ${str(r.notes)}` : '',
          isObj(r.reference) ? h('span', { class: 'muted' }, ' · ', referenceLine(r.reference)) : ''))))
        : null);
  }

  function contentForm(prompts) {
    const msg = formMsg();
    const promptSel = h('select', { id: 'cr-prompt', required: true },
      h('option', { value: '' }, 'Choose a prompt'),
      prompts.map((p) => h('option', { value: str(p.id) }, `${str(p.word)} · ${str(p.targetPhone)} · ${str(p.id)}`)));
    const decision = choiceGroup({ name: 'cr-decision', legend: 'Decision', options: CONTENT_DECISIONS });
    const reviewer = h('input', { type: 'text', id: 'cr-reviewer', autocomplete: 'off', spellcheck: 'false', maxlength: String(SAFE_ID_MAX), 'aria-describedby': 'cr-reviewer-hint' });
    const notes = h('textarea', { id: 'cr-notes', rows: '3', maxlength: String(NOTES_MAX) });

    const includeRef = h('input', { type: 'checkbox', id: 'cr-ref-include' });
    const refId = h('input', { type: 'text', id: 'cr-ref-id', autocomplete: 'off', spellcheck: 'false', maxlength: String(SAFE_ID_MAX) });
    const refVersion = h('input', { type: 'text', id: 'cr-ref-version', autocomplete: 'off', spellcheck: 'false', maxlength: String(SAFE_ID_MAX) });
    const refSha = h('input', { type: 'text', id: 'cr-ref-sha', class: 'mono-input', autocomplete: 'off', spellcheck: 'false', maxlength: '64', 'aria-describedby': 'cr-ref-sha-hint' });
    const rights = choiceGroup({ name: 'cr-ref-rights', legend: 'Rights', options: RIGHTS.map((r) => ({ value: r, label: r })) });
    const refSet = h('fieldset', { class: 'ref-block', id: 'cr-ref', disabled: true },
      h('legend', { class: 'sr-only' }, 'Reference record'),
      h('div', { class: 'field' }, h('label', { for: 'cr-ref-id' }, 'Reference ID'), refId),
      h('div', { class: 'field' }, h('label', { for: 'cr-ref-version' }, 'Reference version'), refVersion),
      h('div', { class: 'field' }, h('label', { for: 'cr-ref-sha' }, 'Reference SHA-256'),
        h('p', { class: 'hint', id: 'cr-ref-sha-hint' }, '64 lowercase hexadecimal characters.'), refSha),
      rights);
    includeRef.addEventListener('change', () => { refSet.disabled = !includeRef.checked; });

    const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, 'Append content review');

    const form = h('form', { class: 'form', id: 'content-form', novalidate: true, 'aria-labelledby': 'cr-title' },
      h('h3', { class: 'form-title', id: 'cr-title' }, 'Record an engineering content review'),
      h('p', { class: 'form-intro' }, 'Choose a prompt and a decision. Notes and a reference record are optional; attach a reference only if you have its ID, version, digest and rights status.'),
      h('div', { class: 'form-cols' },
        h('div', null,
          h('div', { class: 'field' }, h('label', { for: 'cr-prompt' }, 'Prompt'), promptSel),
          decision,
          h('div', { class: 'field' }, h('label', { for: 'cr-reviewer' }, 'Content reviewer ID'),
            h('p', { class: 'hint', id: 'cr-reviewer-hint' }, `Up to ${SAFE_ID_MAX} letters, digits, dots, dashes or underscores, starting with a letter or digit. A local label, not a verified identity.`),
            reviewer),
          h('div', { class: 'field' }, h('label', { for: 'cr-notes' }, 'Notes ', h('span', { class: 'optional' }, '(optional)')), notes)),
        h('div', null,
          h('div', { class: 'field' }, h('label', { class: 'check', for: 'cr-ref-include' }, includeRef, 'Attach a reference record')),
          refSet)),
      h('div', { class: 'actions' }, submit, h('p', { class: 'hint' }, 'Appends a record. Earlier records stay in history.')),
      msg);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      [promptSel, reviewer, refId, refVersion, refSha].forEach((el) => el.removeAttribute('aria-invalid'));
      form.querySelectorAll('.choices.invalid').forEach((el) => el.classList.remove('invalid'));
      const problems = [];
      let firstBad = null;
      const bad = (el, text) => { problems.push(text); if (el.setAttribute) el.setAttribute('aria-invalid', 'true'); if (!firstBad) firstBad = el; };

      const promptId = promptSel.value;
      if (!promptId) bad(promptSel, 'choose a prompt');
      const dec = checkedValue(form, 'cr-decision');
      if (!dec) { problems.push('choose a decision'); decision.classList.add('invalid'); if (!firstBad) firstBad = decision.querySelector('input'); }
      const reviewerId = reviewer.value.trim();
      if (!SAFE_ID.test(reviewerId)) bad(reviewer, `enter a content reviewer ID of up to ${SAFE_ID_MAX} letters, digits, dots, dashes or underscores`);

      let reference = null;
      if (includeRef.checked) {
        const rid = refId.value.trim();
        const rver = refVersion.value.trim();
        const rsha = refSha.value.trim();
        const rr = checkedValue(form, 'cr-ref-rights');
        if (!rid) bad(refId, 'enter a reference ID');
        if (!rver) bad(refVersion, 'enter a reference version');
        if (!HEX64.test(rsha)) bad(refSha, 'enter a 64-character lowercase hex reference digest');
        if (!rr) { problems.push('choose reference rights'); rights.classList.add('invalid'); if (!firstBad) firstBad = rights.querySelector('input'); }
        reference = { id: rid, version: rver, sha256: rsha, rights: rr };
      }

      if (problems.length) {
        setMsg(msg, `Before appending: ${problems.join('; ')}.`);
        if (firstBad && firstBad.focus) firstBad.focus();
        return;
      }

      const res = await post('/api/content-reviews',
        { promptId, record: { decision: dec, reviewerId, notes: notes.value, reference } },
        { button: submit, msg, busyText: 'Appending…', success: `Content review appended for ${promptId}.` });
      if (res) {
        app.ui.focusId = 'sec-content-h';
        await load();
      }
    });

    return form;
  }

  function checkedValue(root, name) {
    const el = root.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value : null;
  }

  function choiceGroup({ name, legend, hint, options, value, disabled }) {
    const hintId = hint ? `${name}-hint` : null;
    return h('fieldset', { class: 'choices', 'aria-describedby': hintId, disabled: Boolean(disabled) },
      h('legend', null, legend),
      hint ? h('p', { class: 'hint', id: hintId }, hint) : null,
      h('div', { class: 'choice-row' }, options.map((o) => h('label', { class: 'choice' },
        h('input', { type: 'radio', name, value: o.value, checked: value === o.value }),
        h('span', { class: 'choice-label' }, o.label)))));
  }

  // --- 2. Original reviews (roster)

  const ROSTER_FILTERS = [
    { id: 'all', label: 'All attempts', test: () => true },
    { id: 'abstain', label: 'Abstaining', test: (a) => admissionStatus(a) === 'abstain' },
    { id: 'ready', label: 'Engineering ready', test: (a) => admissionStatus(a) === 'engineering_ready' },
    { id: 'missing', label: 'Missing an original review', test: (a) => !a.reviewA || !a.reviewB },
    { id: 'disagree', label: 'Target disagreement', test: disagrees },
  ];
  const ROSTER_COLS = 9;

  function reviewsSection(s) {
    const m = coordinatorModel(s);
    const attempts = m.attempts;
    const filterSel = h('select', { id: 'roster-filter' },
      ROSTER_FILTERS.map((f) => h('option', { value: f.id, selected: app.ui.rosterFilter === f.id }, f.label)));
    const count = h('p', { class: 'muted small', 'aria-live': 'polite' });
    const tbody = h('tbody');

    const fill = () => {
      const f = ROSTER_FILTERS.find((x) => x.id === app.ui.rosterFilter) || ROSTER_FILTERS[0];
      const rows = [];
      let shown = 0;
      attempts.forEach((a, i) => {
        if (!f.test(a)) return;
        shown += 1;
        rows.push(...rosterRows(a, i));
      });
      if (!shown) {
        rows.push(h('tr', null, h('td', { colspan: String(ROSTER_COLS), class: 'empty-cell' },
          attempts.length ? 'No attempts match this filter.' : 'The manifest lists no attempts.')));
      }
      tbody.replaceChildren(...rows);
      count.textContent = `Showing ${shown} of ${attempts.length} attempts, numbered 1–${attempts.length} in manifest order. Every imported attempt is listed; none are dropped.`;
    };
    filterSel.addEventListener('change', () => { app.ui.rosterFilter = filterSel.value; fill(); });
    fill();

    const table = h('table', null,
      h('caption', { class: 'sr-only' }, 'Attempt roster with original reviews and admission'),
      h('thead', null, h('tr', null,
        th('No.', 'num'),
        ['Attempt', 'Prompt', 'Participant · split', 'Terminal', 'Recording for review', 'Original targets', 'Adjudication', 'Admission']
          .map((t) => th(t)))),
      tbody);

    return section('sec-reviews', 2, 'Original reviews',
      'Each attempt with both original reviews and its admission decision. Reviewers work in their own views; open an attempt to see full answers, digests and every admission reason.',
      h('div', { class: 'summary-line' },
        h('span', null, 'Reviewer A ', h('b', null, `${m.aCount}`), ` of ${attempts.length}`),
        h('span', null, 'Reviewer B ', h('b', null, `${m.bCount}`), ` of ${attempts.length}`),
        h('span', null, 'Both originals ', h('b', null, `${m.paired}`), ` of ${attempts.length}`)),
      h('div', { class: 'actions' },
        h('label', { for: 'roster-filter', class: 'small' }, 'Show'),
        filterSel, count),
      h('div', { class: 'spacer-8' }),
      tableWrap(table, 'Attempt roster'),
      h('p', { class: 'subnote roster-note' },
        '“Recording for review” follows current review permission and withdrawals. The report’s recording metadata count includes every recording record, whether or not it may be reviewed.'));
  }

  function reviewCellLine(tag, rec) {
    const t = targetOf(rec);
    return h('div', null, h('span', { class: 'muted' }, `${tag} `),
      rec ? (t || 'submitted') : nil('—'),
      rec ? null : h('span', { class: 'sr-only' }, 'not submitted'));
  }

  function reasonSummary(codes) {
    const list = arr(codes).map(str).filter(Boolean);
    if (!list.length) return null;
    const rest = list.length - 2;
    return h('div', { class: 'small muted reason-summary' },
      list.slice(0, 2).map(plain).join('; '),
      rest > 0 ? `; ${rest} more in details` : '');
  }

  function rosterRows(a, i) {
    const detailId = `att-detail-${i}`;
    const expanded = app.ui.expanded.has(i);
    const adm = isObj(a.admission) ? a.admission : {};
    const status = admissionStatus(a);
    const detail = h('tr', { id: detailId, class: 'detail-row', hidden: !expanded },
      h('td', { colspan: String(ROSTER_COLS) }, expanded ? attemptDetail(a) : null));
    const toggle = h('button', { type: 'button', class: 'row-toggle', 'aria-expanded': expanded ? 'true' : 'false', 'aria-controls': detailId },
      h('span', { class: 'sr-only' }, `Details for attempt ${i + 1}, `), h('code', null, str(a.id)));
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        app.ui.expanded.add(i);
        if (!detail.firstChild.firstChild) detail.firstChild.append(attemptDetail(a));
      } else {
        app.ui.expanded.delete(i);
      }
      detail.hidden = !open;
    });

    const row = h('tr', null,
      h('td', { class: 'num att-no-cell' }, String(i + 1)),
      h('td', null, toggle),
      h('td', null, h('div', null, str(a.word)), h('div', { class: 'muted small' }, h('code', null, str(a.targetPhone)), ' · ', str(a.promptId))),
      h('td', null, h('code', null, str(a.participantId)), h('div', { class: 'muted small' }, a.split ? plain(a.split) : 'Split not reported')),
      h('td', null, a.terminal ? plain(a.terminal) : nil('Not reported')),
      h('td', null, a.recordingAvailable === true ? 'Available' : nil('Not available')),
      h('td', null, reviewCellLine('A', a.reviewA), reviewCellLine('B', a.reviewB),
        disagrees(a) ? h('span', { class: 'pill' }, 'targets differ') : null),
      h('td', null, a.adjudication ? (targetOf(a.adjudication) || 'recorded') : nil('—')),
      h('td', null,
        status ? h('span', { class: status === 'engineering_ready' ? 'pill pill-accent' : 'pill' }, plain(status)) : nil('Not reported'),
        reasonSummary(adm.reasons)));
    return [row, detail];
  }

  function answerDl(rec) {
    const ans = answerOf(rec);
    if (!ans) return h('p', { class: 'nil' }, 'Not submitted');
    return h('dl', null,
      ANSWER_FIELDS.map((f) => [h('dt', null, f.legend), h('dd', null, str(ans[f.key]) || '—')]),
      h('dt', null, 'Notes'), h('dd', null, ans.notes ? str(ans.notes) : nil('No notes')),
      h('dt', null, 'SHA-256'), h('dd', null, hashView(shaOf(rec), true)));
  }

  function attemptDetail(a) {
    const adm = isObj(a.admission) ? a.admission : {};
    const ctx = isObj(adm.historicalContext) ? adm.historicalContext : null;
    const adj = answerOf(a.adjudication);
    return h('div', null,
      h('div', { class: 'detail-grid' },
        h('div', null, h('h4', null, 'Admission'),
          h('dl', null,
            h('dt', null, 'Status'), h('dd', null, adm.status ? codeView(adm.status) : nil('Not reported')),
            h('dt', null, 'Reasons'), h('dd', null, reasonList(adm.reasons, 'No abstention reasons')),
            h('dt', null, 'Current restrictions'), h('dd', null, reasonList(adm.currentRestrictions, 'No current restrictions')),
            h('dt', null, 'Learner feedback'), h('dd', null, eligibilityText(adm.learnerFeedbackEligible)),
            h('dt', null, 'Clinical use'), h('dd', null, eligibilityText(adm.clinicalUseEligible)),
            h('dt', null, 'Production use'), h('dd', null, eligibilityText(adm.productionUseEligible)))),
        h('div', null, h('h4', null, 'Reviewer A original'), answerDl(a.reviewA)),
        h('div', null, h('h4', null, 'Reviewer B original'), answerDl(a.reviewB)),
        h('div', null, h('h4', null, 'Adjudication'),
          adj ? h('dl', null,
            h('dt', null, 'Target'), h('dd', null, str(adj.target)),
            h('dt', null, 'Rationale'), h('dd', null, str(adj.notes)),
            h('dt', null, 'Cited originals'), h('dd', null, arr(adj.reviewedOriginals).map((x) => h('div', null, hashView(x)))),
            h('dt', null, 'SHA-256'), h('dd', null, hashView(shaOf(a.adjudication), true)))
            : h('p', { class: 'nil' }, 'No adjudication recorded')),
        ctx ? h('div', null, h('h4', null, 'Pinned context at import'),
          h('dl', null, Object.keys(ctx).map((k) => [h('dt', null, label(k)), h('dd', null, hashView(ctx[k]))])))
          : null),
      rawDetails('Raw attempt record', a));
  }

  // --- 3. Seals

  function sealsSection(s) {
    const seals = isObj(s.seals) ? s.seals : {};
    const table = h('table', { class: 'kv' },
      h('tbody', null, REVIEWER_IDS.map((id) => h('tr', null,
        h('th', { scope: 'row' }, roleName(id)),
        h('td', null, h('span', { class: seals[id] === true ? 'pill pill-accent' : 'pill' }, sealText(seals[id])))))));
    return section('sec-seals', 3, 'Seals',
      'Each reviewer seals their own batch from their view once every item has an answer. Sealing is final. Agreement, comparison and adjudication wait for both seals.',
      table,
      h('div', { class: 'actions' },
        h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => goRole('reviewer-a') }, 'Open Reviewer A view'),
        h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => goRole('reviewer-b') }, 'Open Reviewer B view')));
  }

  // --- 4. Prediction lock

  function modelRows(model) {
    const known = ['id', 'version', 'manifestSha256', 'preprocessingSha256', 'meaning'];
    const row = (name, value) => h('tr', null, h('th', { scope: 'row' }, name), h('td', null, value));
    return [
      row('Model ID', model.id !== undefined ? h('code', null, str(model.id)) : nil('Not reported')),
      row('Model version', model.version !== undefined ? h('code', null, str(model.version)) : nil('Not reported')),
      row('Manifest SHA-256', hashView(model.manifestSha256, true)),
      row('Preprocessing SHA-256', hashView(model.preprocessingSha256, true)),
      row('Prediction meaning', codeView(model.meaning)),
      Object.keys(model).filter((k) => !known.includes(k))
        .map((k) => row(label(k), h('code', null, typeof model[k] === 'string' ? model[k] : safeJson(model[k])))),
    ];
  }

  function lockSection(s) {
    const m = coordinatorModel(s);
    const lock = m.lock;
    let body;
    if (lock) {
      const model = isObj(lock.model) ? lock.model : {};
      body = h('div', null,
        h('p', { class: 'prose' }, h('span', { class: 'pill pill-accent' }, 'Locked'),
          ' Predictions are frozen. The lock cannot be replaced.'),
        h('div', { class: 'spacer-8' }),
        h('table', { class: 'kv' }, h('tbody', null,
          h('tr', null, h('th', { scope: 'row' }, 'Payload digest'), h('td', null, hashView(lock.sha256, true))),
          modelRows(model))),
        h('p', { class: 'prose small muted' },
          'The digest identifies the locked payload content. It is not evidence of when the predictions were produced or by whom.'));
    } else {
      const msg = formMsg();
      const loadBtn = h('button', { type: 'button', class: 'btn' }, app.ui.demo ? 'Reload invented demo predictions' : 'Load invented demo predictions');
      loadBtn.addEventListener('click', async () => {
        const operationUi = app.ui;
        if (operationUi.pending) return;
        operationUi.pending = true;
        setBusy(loadBtn, true, 'Loading…');
        msg.replaceChildren();
        try {
          const data = await api('/api/demo-predictions');
          if (app.ui !== operationUi) return;
          const digest = isObj(data) ? (data.sha256 || data.expectedSha256 || data.digest) : null;
          if (!isObj(data) || !isObj(data.payload) || typeof digest !== 'string') throw new ApiError('invalid_response', 200);
          app.ui.demo = { payload: data.payload, sha256: digest, synthetic: data.synthetic === true };
          app.ui.pending = false;
          replaceSection('sec-lock', lockSection);
          focusEl('demo-preview-h');
          return;
        } catch (err) {
          if (app.ui === operationUi) setMsg(msg, errorNodes(err));
        } finally {
          operationUi.pending = false;
          if (app.ui === operationUi) setBusy(loadBtn, false);
        }
      });
      body = h('div', null,
        h('p', { class: 'prose' }, 'No predictions are locked. Lock before reference comparison: the report compares predictions only after both seals and the lock.'),
        h('p', { class: 'prose' }, 'This demo has no model and runs no inference. The server supplies an invented, complete payload covering every attempt, including those with no recording.'),
        h('div', { class: 'spacer-8' }),
        h('div', { class: 'actions' }, loadBtn),
        msg,
        app.ui.demo ? demoPreview(app.ui.demo, m.attempts) : null);
    }
    return section('sec-lock', 4, 'Prediction lock', null, body);
  }

  function demoPreview(demo, attempts) {
    const payload = demo.payload;
    const model = isObj(payload.model) ? payload.model : {};
    const rows = arr(payload.rows).filter(isObj);
    const statusCounts = {};
    rows.forEach((r) => { const k = str(r.status) || 'missing'; statusCounts[k] = (statusCounts[k] || 0) + 1; });
    const rowIds = new Set(rows.map((r) => str(r.attemptId)));
    const rosterIds = attempts.map((a) => str(a.id));
    const covered = rosterIds.filter((id) => rowIds.has(id)).length;
    const extra = [...rowIds].filter((id) => !rosterIds.includes(id)).length;

    const msg = formMsg();
    const lockBtn = h('button', { type: 'button', class: 'btn btn-primary', disabled: !demo.synthetic }, 'Lock these predictions…');
    lockBtn.addEventListener('click', async () => {
      const operationUi = app.ui;
      const ok = await confirmAction({
        title: 'Lock invented predictions?',
        body: [
          'The lock is written once and cannot be replaced or removed.',
          `The server recomputes the digest of the payload it receives and refuses the lock unless it equals ${demo.sha256}.`,
          'That is a consistency check between this payload and this digest only. It does not show the predictions are authentic or when they were made.',
        ],
        confirmLabel: 'Lock predictions',
      });
      if (!ok || app.ui !== operationUi) return;
      const res = await post('/api/prediction-lock',
        { payload: demo.payload, expectedSha256: demo.sha256 },
        { button: lockBtn, msg, busyText: 'Locking…', success: 'Predictions locked.' });
      if (res) {
        app.ui.demo = null;
        app.ui.focusId = 'sec-lock-h';
        await load();
      }
    });

    return h('div', { class: 'demo-preview', 'aria-labelledby': 'demo-preview-h', role: 'group' },
      h('h3', { class: 'subhead', id: 'demo-preview-h', tabindex: '-1' }, 'Invented payload ready to lock'),
      demo.synthetic ? h('p', { class: 'subnote' }, 'Marked synthetic by the server. Nothing has been locked yet.')
        : h('p', { class: 'form-msg error' }, 'The response was not marked synthetic, so it is not offered for locking.'),
      h('table', { class: 'kv' }, h('tbody', null,
        modelRows(model),
        h('tr', null, h('th', { scope: 'row' }, 'Rows'), h('td', null, String(rows.length))),
        h('tr', null, h('th', { scope: 'row' }, 'Rows by status'), h('td', null,
          Object.keys(statusCounts).map((k) => h('span', { class: 'chip' }, `${plain(k)} ${statusCounts[k]}`)))),
        h('tr', null, h('th', { scope: 'row' }, 'Roster coverage'), h('td', null,
          `${covered} of ${rosterIds.length} attempts have a row`, extra ? ` · ${extra} rows not in roster` : '')),
        h('tr', null, h('th', { scope: 'row' }, 'Expected digest'), h('td', null, hashView(demo.sha256, true))))),
      h('div', { class: 'spacer-8' }),
      h('div', { class: 'actions' }, lockBtn,
        h('p', { class: 'hint' }, 'Sends this payload and digest unchanged.')),
      msg);
  }

  // --- 5. Adjudication summary

  function adjudicationSummarySection(s) {
    const m = coordinatorModel(s);
    const idx = attemptIndex(s);
    const relevant = m.attempts.filter((a) => disagrees(a) || a.adjudication);
    const table = h('table', null,
      h('caption', { class: 'sr-only' }, 'Attempts with target disagreement or adjudication'),
      h('thead', null, h('tr', null, ['Attempt', 'Word', 'Reviewer A target', 'Reviewer B target', 'Adjudicated target']
        .map((t) => th(t)))),
      h('tbody', null, relevant.length ? relevant.map((a) => h('tr', null,
        h('td', null, attemptRef(a.id, idx)),
        h('td', null, str(a.word)),
        h('td', null, targetOf(a.reviewA) || '—'),
        h('td', null, targetOf(a.reviewB) || '—'),
        h('td', null, a.adjudication ? (targetOf(a.adjudication) || 'recorded')
          : nil(m.bothSealed ? 'Awaiting adjudication' : 'Opens after both seals'))))
        : h('tr', null, h('td', { colspan: '5', class: 'empty-cell' },
          m.paired ? 'No target disagreements or adjudications among paired originals.' : 'No paired original reviews yet.'))));
    return section('sec-adjudication', 5, 'Adjudication',
      'Attempts whose two original targets differ come first: an adjudicator records a target decision with a rationale, citing both sealed originals. A separate target decision may also be recorded where the originals agree. It resolves the target judgment only; it cannot resolve an ambiguous occurrence or the speech, prompt-match, quality or other admission gates. Originals are kept unchanged.',
      h('div', { class: 'summary-line' },
        h('span', null, 'Both originals ', h('b', null, String(m.paired))),
        h('span', null, 'Targets differ ', h('b', null, String(m.disagreements.length))),
        h('span', null, 'Adjudications recorded ', h('b', null, String(m.adjudicated)))),
      m.bothSealed ? null : h('p', { class: 'callout' }, h('strong', null, 'Waiting for both batches. '),
        'The adjudicator sees originals only after Reviewer A and Reviewer B have both sealed. Differences listed here are for planning.'),
      tableWrap(table, 'Adjudication status'),
      h('div', { class: 'spacer-8' }),
      h('div', { class: 'actions' },
        h('button', { type: 'button', class: 'btn btn-quiet', onclick: () => goRole('adjudicator') }, 'Open Adjudicator view')));
  }

  // --- 6. Report and export

  const REPORT_KEYS = ['denominators', 'coverage', 'admissionByAttemptId', 'reasonCounts', 'agreement',
    'referenceComparison', 'repeatability', 'byAge', 'byTarget', 'bySplit', 'flags'];

  function reportSection(s) {
    const r = isObj(s.report) ? s.report : null;
    const idx = attemptIndex(s);
    const blocks = [];
    if (!r) {
      blocks.push(h('p', { class: 'nil' }, 'The server returned no report.'));
    } else {
      blocks.push(basicsBlock(r), limitsBlock(r), reasonsBlock(r.reasonCounts, r.denominators),
        agreementBlock(r.agreement, r.denominators), referenceBlock(r.referenceComparison, idx),
        repeatBlock(r.repeatability, idx), strataBlock(r));
    }
    blocks.push(splitBlock(s.splitDiagnostics, idx));
    if (r) blocks.push(rawReportBlock(r));
    blocks.push(exportBlock());

    return section('sec-report', 6, 'Report and export',
      'Recomputed by the server from the manifest and appended records on every load. Headline counts are shown first; open the detail panels for per-attempt and per-group tables.',
      ...blocks);
  }

  function subhead(text) {
    return h('h3', { class: 'subhead' }, text);
  }

  function reportBlock(...children) {
    return h('div', { class: 'report-block' }, ...children);
  }

  function countSpan(n, noun) {
    return h('span', null, h('b', null, isCount(n) ? fmtNum(n) : '—'), ` ${noun}`);
  }

  function terminalText(tc) {
    if (!isObj(tc)) return nil('Not reported');
    const keys = Object.keys(tc);
    if (!keys.length) return nil('No outcomes');
    return keys.map((k, i) => [i ? ' · ' : '', h('span', { class: tc[k] ? null : 'muted' }, `${plain(k)} ${fmtNum(tc[k])}`)]);
  }

  function basicsBlock(r) {
    const d = isObj(r.denominators) ? r.denominators : {};
    const cov = isObj(r.coverage) ? r.coverage : {};
    const covKeys = Object.keys(cov).filter((k) => isFraction(cov[k]));
    const headline = ['attempts', 'participants', 'householdsKnown', 'terminalCounts'];
    const extra = Object.keys(d).filter((k) => !headline.includes(k) && !(k in cov) && isCount(d[k]));
    const table = h('table', { class: 'kv coverage' },
      h('caption', { class: 'sr-only' }, 'Coverage, each with its own numerator and denominator'),
      h('thead', null, h('tr', null, th('Measure'), th('Count', 'num'), th('Denominator', 'num'), th('Share', 'num'))),
      h('tbody', null,
        covKeys.map((k) => h('tr', null,
          h('th', { scope: 'row' }, COVERAGE_TEXT[k] || label(k)),
          h('td', { class: 'num' }, fmtNum(cov[k].numerator)),
          h('td', { class: 'num' }, fmtNum(cov[k].denominator)),
          h('td', { class: 'num' }, pct(cov[k].numerator, cov[k].denominator)))),
        extra.map((k) => h('tr', null,
          h('th', { scope: 'row' }, COVERAGE_TEXT[k] || label(k)),
          h('td', { class: 'num' }, fmtNum(d[k])), h('td', { class: 'num' }, '—'), h('td', { class: 'num' }, '—')))));
    return reportBlock(
      subhead('Denominators and coverage'),
      h('p', { class: 'subnote' }, 'Every imported attempt is counted and each line shows its own denominator. These counts describe the workflow; they are not model or reviewer accuracy.'),
      h('p', { class: 'summary-line' },
        countSpan(d.attempts, 'attempts'), countSpan(d.participants, 'participants'), countSpan(d.householdsKnown, 'known households')),
      h('p', { class: 'small terminal-line' }, h('span', { class: 'muted' }, 'Terminal outcomes: '), terminalText(d.terminalCounts)),
      covKeys.length || extra.length ? tableWrap(table, 'Coverage') : h('p', { class: 'nil' }, 'No coverage figures in this report.'));
  }

  function flagValue(key, v) {
    if (typeof v === 'boolean') {
      if (/Eligible$/.test(key)) return v ? h('span', null, 'Unexpected value ', h('code', null, 'true')) : 'Not eligible';
      if (/Established$/.test(key)) return v ? h('span', null, 'Unexpected value ', h('code', null, 'true')) : 'Not established';
      return v ? 'Yes' : 'No';
    }
    if (typeof v === 'string') return codeView(v);
    return h('code', null, safeJson(v));
  }

  function limitsBlock(r) {
    const rows = new Map();
    const add = (src, all) => {
      if (!isObj(src)) return;
      Object.keys(src).forEach((k) => {
        if ((all || k in FLAG_TEXT) && !rows.has(k) && !isObj(src[k]) && !Array.isArray(src[k])) rows.set(k, src[k]);
      });
    };
    add(r.flags, true);
    add(r.referenceComparison, false);
    add(r.repeatability, false);
    if (!rows.size) return null;
    return reportBlock(
      subhead('Scope limits'),
      h('p', { class: 'subnote' }, 'What this synthetic report does not establish. Nothing here is eligible for learner, clinical or production use.'),
      h('table', { class: 'kv limits' }, h('tbody', null, [...rows.keys()].map((k) => h('tr', null,
        h('th', { scope: 'row' }, FLAG_TEXT[k] || label(k)),
        h('td', null, flagValue(k, rows.get(k))))))));
  }

  function reasonsBlock(rc, d) {
    const out = [subhead('Admission reasons')];
    if (!isObj(rc)) {
      out.push(h('p', { class: 'nil' }, 'Not included in this report.'));
      return reportBlock(out);
    }
    const keys = Object.keys(rc).sort((a, b) => (rc[b] - rc[a]) || a.localeCompare(b));
    const den = isObj(d) ? d : {};
    const abstaining = isCount(den.attempts) && isCount(den.engineeringReady) ? den.attempts - den.engineeringReady : null;
    out.push(h('p', { class: 'subnote' },
      abstaining !== null ? `${abstaining} of ${den.attempts} attempts abstain. ` : '',
      'One attempt can carry several reasons, so reason counts can exceed the number of attempts. Each attempt’s own reasons are in the roster (step 2).'));
    if (!keys.length) {
      out.push(h('p', { class: 'nil' }, 'No admission reasons recorded.'));
      return reportBlock(out);
    }
    out.push(more(`Reason counts (${keys.length} kinds)`,
      tableWrap(h('table', { class: 'kv' },
        h('caption', { class: 'sr-only' }, 'Admission reason counts'),
        h('thead', null, h('tr', null, th('Reason'), th('Code'), th('Attempts', 'num'))),
        h('tbody', null, keys.map((k) => h('tr', null,
          h('th', { scope: 'row' }, plain(k)),
          h('td', null, h('code', { class: 'chip' }, k)),
          h('td', { class: 'num' }, isCount(rc[k]) ? fmtNum(rc[k]) : str(rc[k])))))),
      'Admission reason counts')));
    return reportBlock(out);
  }

  function agreementBlock(ag, d) {
    const den = isObj(d) ? d : {};
    const out = [subhead('Reviewer agreement on target'),
      h('p', { class: 'subnote' }, 'Original Reviewer A and Reviewer B targets only; adjudications are not counted. Agreement between two local demo reviewers is not accuracy and not qualified review.')];
    if (!isObj(ag)) {
      out.push(h('p', { class: 'nil' }, 'Not included in this report.'));
      return reportBlock(out);
    }
    if (ag.available === false) {
      out.push(h('p', { class: 'callout' }, h('strong', null, 'Waiting for both batches. '),
        'Agreement is computed only after Reviewer A and Reviewer B have each sealed their batch.',
        isCount(den.attempts) ? ` Original reviews so far: Reviewer A ${fmtNum(den.reviewACount)} of ${fmtNum(den.attempts)}, Reviewer B ${fmtNum(den.reviewBCount)} of ${fmtNum(den.attempts)}.` : ''));
      return reportBlock(out);
    }
    const paired = isCount(ag.pairedCount) ? ag.pairedCount : null;
    const sp = isFraction(ag.scorablePairs) ? ag.scorablePairs : null;
    const row = (name, value) => h('tr', null, h('th', { scope: 'row' }, name), h('td', null, value));
    out.push(h('table', { class: 'kv' }, h('tbody', null,
      row('Paired original reviews', paired === null ? nil('Not reported')
        : `${fmtNum(paired)}${isCount(den.attempts) ? ` of ${fmtNum(den.attempts)} attempts` : ''}`),
      row('Same target, all pairs', rateView(ag.exactAgreement, paired)),
      row('Scorable pairs (expected, altered or omitted)', sp ? `${fmtNum(sp.numerator)} of ${fmtNum(sp.denominator)} pairs` : nil('Not reported')),
      'exactScorableAgreement' in ag ? row('Same target, scorable pairs', rateView(ag.exactScorableAgreement, sp ? sp.numerator : null)) : null,
      row('Cohen’s kappa, scorable pairs', isCount(ag.kappa) ? ag.kappa.toFixed(3) : nil('Not defined for the current scorable pairs')),
      'excludedUncertainOrUnscorable' in ag ? row('Pairs kept out of kappa (indeterminate or unscorable)', fmtNum(ag.excludedUncertainOrUnscorable)) : null)));
    if ('confusion' in ag) out.push(more('Target-by-target counts', confusionView(ag.categories, ag.confusion)));
    if (ag.basis) out.push(h('p', { class: 'code-note' }, 'Basis ', h('code', null, str(ag.basis))));
    return reportBlock(out);
  }

  function confusionView(categories, confusion) {
    const cats = arr(categories).map(str);
    const caption = h('caption', null, 'Rows: Reviewer A original target. Columns: Reviewer B original target. Highlighted diagonal cells agree.');
    let rowsKeys;
    let colKeys;
    let cell;
    if (Array.isArray(confusion) && cats.length && confusion.every(Array.isArray)) {
      rowsKeys = cats; colKeys = cats;
      cell = (ri, ci) => confusion[ri] ? confusion[ri][ci] : undefined;
    } else if (isObj(confusion) && Object.values(confusion).every(isObj)) {
      rowsKeys = cats.length ? cats.filter((c) => c in confusion).concat(Object.keys(confusion).filter((k) => !cats.includes(k))) : Object.keys(confusion);
      const colSet = new Set(cats);
      Object.values(confusion).forEach((row) => Object.keys(row).forEach((k) => colSet.add(k)));
      colKeys = [...colSet];
      cell = (ri, ci) => confusion[rowsKeys[ri]][colKeys[ci]];
    } else {
      return h('pre', { class: 'raw' }, safeJson(confusion));
    }
    if (!rowsKeys.length) return h('p', { class: 'nil' }, 'No paired targets yet.');
    return tableWrap(h('table', { class: 'matrix kv' }, caption,
      h('thead', null, h('tr', null, th(h('span', { class: 'sr-only' }, 'Reviewer A target')),
        colKeys.map((c) => th(`B: ${c}`, 'num')))),
      h('tbody', null, rowsKeys.map((r, ri) => h('tr', null,
        h('th', { scope: 'row' }, `A: ${r}`),
        colKeys.map((c, ci) => {
          const v = cell(ri, ci);
          return h('td', { class: r === c ? 'diag' : null }, v === undefined ? '0' : (isCount(v) ? fmtNum(v) : str(v)));
        }))))), 'Target-by-target counts');
  }

  function targetCell(t, emptyText) {
    return typeof t === 'string' && t ? t : nil(emptyText);
  }

  function referenceBlock(rc, idx) {
    const out = [subhead('Predictions beside engineering reference'),
      h('p', { class: 'subnote' }, 'Locked predictions shown next to the engineering reference target for each attempt. This does not establish model accuracy, clinical validity or the authenticity of the predictions.')];
    if (!isObj(rc)) {
      out.push(h('p', { class: 'nil' }, 'Not included in this report.'));
      return reportBlock(out);
    }
    if (rc.available === false) {
      out.push(h('div', { class: 'callout' }, h('p', null, h('strong', null, 'Not available yet. '),
        'This comparison opens after both reviewer batches are sealed and predictions are locked.'),
        arr(rc.reasons).length ? h('div', { class: 'spacer-8' }) : null,
        arr(rc.reasons).length ? reasonList(rc.reasons, '') : null));
      return reportBlock(out);
    }
    const rows = arr(rc.rows).filter(isObj);
    const withRef = rows.filter((x) => typeof x.engineeringReferenceTarget === 'string').length;
    const processed = rows.filter((x) => x.predictionStatus === 'processed').length;
    const both = rows.filter((x) => typeof x.engineeringReferenceTarget === 'string' && x.predictionStatus === 'processed').length;
    out.push(h('p', { class: 'summary-line' },
      countSpan(rows.length, 'rows'),
      countSpan(withRef, 'with an engineering reference'),
      countSpan(processed, 'with a processed prediction'),
      countSpan(both, 'with both')));
    if (rows.length) {
      const table = h('table', null,
        h('caption', { class: 'sr-only' }, 'Per-attempt predictions beside original, adjudicated and engineering reference targets'),
        h('thead', null, h('tr', null, th('Attempt'), th('Word'), th('Reviewer A'), th('Reviewer B'), th('Adjudicated'),
          th('Engineering reference'), th('Prediction'), th('Class probabilities'), th('Admission'))),
        h('tbody', null, rows.map((x) => {
          const differ = typeof x.reviewATarget === 'string' && typeof x.reviewBTarget === 'string' && x.reviewATarget !== x.reviewBTarget;
          const adm = isObj(x.admission) ? x.admission : {};
          return h('tr', null,
            h('td', null, attemptRef(x.attemptId, idx)),
            h('td', null, idx.words.get(str(x.attemptId)) || nil('—')),
            h('td', null, targetCell(x.reviewATarget, 'Not reviewed')),
            h('td', null, targetCell(x.reviewBTarget, 'Not reviewed'), differ ? h('div', null, h('span', { class: 'pill' }, 'targets differ')) : null),
            h('td', null, targetCell(x.adjudicatedTarget, differ ? 'Awaiting adjudication' : '—')),
            h('td', null, targetCell(x.engineeringReferenceTarget, 'No reference')),
            h('td', null, x.predictionStatus ? plain(x.predictionStatus) : nil('Not reported')),
            h('td', null, Array.isArray(x.probabilities)
              ? h('span', { class: 'probs' }, x.probabilities.map((p) => (isCount(p) ? p.toFixed(2) : '?')).join(' · '))
              : nil('—')),
            h('td', null, adm.status ? plain(adm.status) : nil('Not reported')));
        })));
      out.push(more(`Per-attempt comparison (${rows.length} rows)`,
        h('p', { class: 'subnote' }, 'Probabilities are the locked payload’s subjective corpus classes, in payload order. Admission reasons for each attempt are in the roster.'),
        tableWrap(table, 'Per-attempt comparison')));
    }
    if (rc.meaning) out.push(h('p', { class: 'code-note' }, 'Meaning ', h('code', null, str(rc.meaning))));
    return reportBlock(out);
  }

  function transitionText(t) {
    if (!isObj(t)) return nil('Not reviewed');
    return h('span', null, str(t.from) || '—', h('span', { 'aria-hidden': 'true' }, ' → '), h('span', { class: 'sr-only' }, ' then '), str(t.to) || '—');
  }

  function repeatBlock(rep, idx) {
    const out = [subhead('Planned repeats'),
      h('p', { class: 'subnote' }, 'Declared planned repeats only; retries are excluded and no pair is selected for a favourable result. Differences are descriptive and do not show improvement.')];
    if (!isObj(rep)) {
      out.push(h('p', { class: 'nil' }, 'Not included in this report.'));
      return reportBlock(out);
    }
    out.push(h('p', { class: 'summary-line' },
      countSpan(rep.declaredPairs, 'declared pairs'),
      countSpan(rep.comparablePairs, 'comparable'),
      'retryAttemptsExcluded' in rep ? countSpan(rep.retryAttemptsExcluded, 'retry attempts excluded') : null,
      'meaningfulImprovementEstablished' in rep
        ? h('span', null, 'Meaningful improvement: ', h('b', null, flagValue('meaningfulImprovementEstablished', rep.meaningfulImprovementEstablished)))
        : null));
    const pairs = arr(rep.pairs).filter(isObj);
    if (!pairs.length) {
      out.push(h('p', { class: 'nil' }, 'No planned repeats are declared.'));
    } else {
      const table = h('table', null,
        h('caption', { class: 'sr-only' }, 'Declared planned-repeat pairs'),
        h('thead', null, h('tr', null, th('Original'), th('Repeat'), th('Same condition'), th('Comparable'),
          th('Reviewer A target'), th('Reviewer B target'), th('Probability change (repeat − original)'), th('Not comparable because'))),
        h('tbody', null, pairs.map((p) => {
          const tr = isObj(p.originalTargetTransitions) ? p.originalTargetTransitions : {};
          return h('tr', null,
            h('td', null, attemptRef(p.fromAttemptId, idx)),
            h('td', null, attemptRef(p.toAttemptId, idx)),
            h('td', null, p.conditionMatch === true ? 'Yes' : (p.conditionMatch === false ? 'No' : nil('Not reported'))),
            h('td', null, p.comparable === true ? 'Yes' : (p.comparable === false ? 'No' : nil('Not reported'))),
            h('td', null, transitionText(tr['reviewer-a'])),
            h('td', null, transitionText(tr['reviewer-b'])),
            h('td', null, Array.isArray(p.probabilityDifferences)
              ? h('span', { class: 'probs' }, p.probabilityDifferences.map(signed).join(' · '))
              : nil('No prediction pair')),
            h('td', null, reasonList(p.reasons, '—')));
        })));
      out.push(more(`Pair details (${pairs.length})`, tableWrap(table, 'Planned-repeat pairs')));
    }
    const notes = [['Basis', rep.comparisonBasis], ['Difference meaning', rep.probabilityDifferenceMeaning]].filter(([, v]) => v);
    notes.forEach(([name, v]) => out.push(h('p', { class: 'code-note' }, `${name} `, h('code', null, str(v)))));
    return reportBlock(out);
  }

  const STRATA = [
    { key: 'byAge', title: 'By age', group: 'Age',
      fmt: (v) => (isCount(v) ? `${v} years` : nil('Age unknown')) },
    { key: 'byTarget', title: 'By target sound', group: 'Target', fmt: (v) => h('code', null, str(v)) },
    { key: 'bySplit', title: 'By split', group: 'Split', fmt: (v) => (v ? plain(v) : nil('Not reported')) },
  ];
  const STRATA_COLS = [
    ['attempts', 'Attempts'], ['participants', 'Participants'], ['recordingsPresent', 'Recording metadata'],
    ['predictionsProcessed', 'Predictions processed'], ['reviewACount', 'Reviewer A originals'],
    ['reviewBCount', 'Reviewer B originals'], ['engineeringReady', 'Engineering ready'],
  ];

  function strataTable(spec, list, total) {
    const rows = spec.key === 'byAge'
      ? list.slice().sort((a, b) => (isCount(a.value) ? a.value : Infinity) - (isCount(b.value) ? b.value : Infinity))
      : list;
    const sum = rows.reduce((acc, x) => acc + (isCount(x.attempts) ? x.attempts : 0), 0);
    return h('div', null,
      tableWrap(h('table', null,
        h('caption', { class: 'sr-only' }, `Report counts ${spec.title.toLowerCase()}`),
        h('thead', null, h('tr', null, th(spec.group), STRATA_COLS.map(([, t]) => th(t, 'num')), th('Terminal outcomes'))),
        h('tbody', null, rows.map((x) => h('tr', null,
          h('th', { scope: 'row' }, spec.fmt(x.value)),
          STRATA_COLS.map(([k]) => h('td', { class: 'num' }, isCount(x[k]) ? fmtNum(x[k]) : '—')),
          h('td', { class: 'small' }, terminalText(x.terminalCounts)))))),
      `Report counts ${spec.title.toLowerCase()}`),
      isCount(total) ? h('p', { class: 'code-note' }, `Groups account for ${sum} of ${total} attempts.`) : null);
  }

  function strataBlock(r) {
    const total = isObj(r.denominators) ? r.denominators.attempts : null;
    const present = STRATA.filter((spec) => Array.isArray(r[spec.key]));
    if (!present.length) return null;
    return reportBlock(
      subhead('Breakdowns'),
      h('p', { class: 'subnote' }, 'The same counts split by age, target sound and declared split. Groups cover every attempt.'),
      present.map((spec) => {
        const list = r[spec.key].filter(isObj);
        return more(`${spec.title} (${list.length} groups)`,
          list.length ? strataTable(spec, list, total) : h('p', { class: 'nil' }, 'No groups.'));
      }));
  }

  const SPLIT_DIMENSIONS = [
    { key: 'participants', title: 'Participants' },
    { key: 'households', title: 'Households' },
    { key: 'lexicalGroups', title: 'Lexical groups' },
  ];

  function splitsText(list) {
    const items = arr(list).map(plain).filter(Boolean);
    return items.length ? items.join(', ') : 'no split';
  }

  function groupTable(dim, d, idx) {
    const groups = arr(d.groups).filter(isObj);
    const leakIds = new Set(arr(d.leakageGroups).filter(isObj).map((g) => str(g.id)));
    return [h('h4', { class: 'subhead' }, dim.title),
      groups.length ? tableWrap(h('table', null,
        h('caption', { class: 'sr-only' }, `${dim.title} groups and their splits`),
        h('thead', null, h('tr', null, th('Group'), th('Splits'), th('Attempts', 'num'), th('Attempt numbers'))),
        h('tbody', null, groups.map((g) => h('tr', null,
          h('th', { scope: 'row' }, h('code', null, str(g.id))),
          h('td', null, splitsText(g.splits), leakIds.has(str(g.id)) ? [' ', h('span', { class: 'pill' }, 'spans splits')] : null),
          h('td', { class: 'num' }, String(arr(g.attemptIds).length)),
          h('td', null, attemptNumbers(g.attemptIds, idx)))))),
      `${dim.title} groups`) : h('p', { class: 'nil' }, 'No groups declared.')];
  }

  function jointTable(joint, idx) {
    const comps = arr(joint.components).filter(isObj);
    return [h('h4', { class: 'subhead' }, 'Joint components'),
      comps.length ? tableWrap(h('table', null,
        h('caption', { class: 'sr-only' }, 'Connected components linking participants, households and lexical groups'),
        h('thead', null, h('tr', null, th('Component'), th('Attempts'), th('Participants'), th('Households'), th('Lexical groups'), th('Splits'))),
        h('tbody', null, comps.map((c) => h('tr', null,
          h('th', { scope: 'row' }, h('code', null, str(c.id))),
          h('td', null, `${arr(c.attemptIds).length} · `, attemptNumbers(c.attemptIds, idx)),
          h('td', null, codeList(c.participantIds, 'None declared')),
          h('td', null, codeList(c.householdIds, 'None declared')),
          h('td', null, codeList(c.lexicalGroups, 'None declared')),
          h('td', null, splitsText(c.splits)))))),
      'Joint components') : h('p', { class: 'nil' }, 'No components reported.')];
  }

  function splitBlock(sd, idx) {
    const out = [subhead('Split diagnostics'),
      h('p', { class: 'subnote' }, 'Diagnostics only, from declared metadata. Leakage and isolation are reported; the workbench never assigns, rebalances or samples splits.')];
    if (!isObj(sd)) {
      out.push(h('p', { class: 'nil' }, 'The server returned no split diagnostics.'));
      return reportBlock(out);
    }
    const lines = [];
    SPLIT_DIMENSIONS.forEach((dim) => {
      const d = isObj(sd[dim.key]) ? sd[dim.key] : null;
      if (!d) return;
      const groups = arr(d.groups).filter(isObj);
      const leaks = arr(d.leakageGroups).filter(isObj);
      lines.push(h('li', null, h('strong', null, `${dim.title}: `),
        leaks.length
          ? [`${leaks.length} of ${groups.length} groups span more than one split — `,
            leaks.map((g, i) => [i ? '; ' : '', h('code', null, str(g.id)), ` (${splitsText(g.splits)})`]), '.']
          : `no group spans more than one split (${groups.length} groups).`));
    });
    const iso = isObj(sd.unknownIsolation) ? sd.unknownIsolation : null;
    if (iso) {
      const pids = arr(iso.participantIds);
      const hids = arr(iso.householdParticipantIds);
      lines.push(h('li', null, h('strong', null, 'Unknown linkage: '),
        pids.length ? ['identity linkage unknown for ', codeList(pids, '')] : 'identity linkage declared for every participant',
        '; ',
        hids.length ? ['household unknown for ', codeList(hids, '')] : 'household declared for every participant',
        '.',
        iso.isolationEstablished === false ? ' Isolation from these participants is not established.' : null));
    }
    const joint = isObj(sd.joint) ? sd.joint : null;
    if (joint) {
      const n = joint.componentCount;
      const leaking = joint.leakingComponents;
      lines.push(h('li', null, h('strong', null, 'Joint grouping: '),
        isCount(n) ? `${n} connected component${n === 1 ? '' : 's'} across participants, households and lexical groups` : 'components not reported',
        isCount(leaking) ? `; ${leaking} span${leaking === 1 ? 's' : ''} more than one split. ` : '. ',
        joint.threeWayIsolation ? ['Separating into three splits: ', plain(joint.threeWayIsolation).toLowerCase(),
          joint.reason ? ` — ${plain(joint.reason)}` : '', '.'] : null,
        joint.unknownLinkageMayMergeComponents === true ? ' Unknown linkage could merge components further.' : null));
    }
    out.push(lines.length ? h('ul', { class: 'plain-list diag-list' }, lines) : h('p', { class: 'nil' }, 'No diagnostics reported.'));

    const tables = SPLIT_DIMENSIONS.filter((dim) => isObj(sd[dim.key])).map((dim) => groupTable(dim, sd[dim.key], idx));
    if (joint) tables.push(jointTable(joint, idx));
    if (tables.length) out.push(more('Group membership tables', tables));

    const codes = [];
    if (iso && iso.meaning) codes.push(['Isolation basis', iso.meaning]);
    if (joint && joint.threeWayIsolation) codes.push(['Three-way isolation', joint.threeWayIsolation]);
    if (joint && joint.reason) codes.push(['Reason', joint.reason]);
    if (codes.length) {
      out.push(h('p', { class: 'code-note' }, codes.map(([name, v], i) => [i ? ' · ' : '', `${name} `, h('code', null, str(v))])));
    }
    out.push(rawDetails('Split diagnostics data (JSON, for audit)', sd));
    return reportBlock(out);
  }

  function rawReportBlock(r) {
    const unknown = Object.keys(r).filter((k) => !REPORT_KEYS.includes(k));
    return reportBlock(
      subhead('Audit data'),
      unknown.length ? h('p', { class: 'subnote' }, 'This report also contains fields not summarised above: ',
        codeList(unknown, ''), '. They are included in the full report data.') : null,
      rawDetails('Full report data (JSON), including admission for every attempt', r));
  }

  function exportBlock() {
    const msg = formMsg();
    const btn = h('button', { type: 'button', class: 'btn btn-primary' }, 'Download export (JSON)');
    btn.addEventListener('click', () => {
      // Let the browser handle the server's attachment response directly.
      const a = h('a', { href: '/api/export', download: 'assessment-workbench-export.json', hidden: true });
      document.body.append(a);
      a.click();
      a.remove();
      setMsg(msg, 'Export requested. Check your browser’s downloads. If it fails, use the export command in the run guide.', 'info');
    });
    return reportBlock(
      subhead('Export'),
      h('p', { class: 'subnote' }, 'Synthetic demo export from the coordinator view: the immutable source manifest, every appended event and the recomputed report. "Coordinator" is a local view label, not an authenticated identity.'),
      h('div', { class: 'actions' }, btn),
      msg);
  }

  // --- Withdrawal

  function withdrawSection(s) {
    const m = coordinatorModel(s);
    const participants = [...new Set(m.attempts.map((a) => str(a.participantId)).filter(Boolean))].sort();
    const withdrawn = new Set(m.attempts
      .filter((a) => isObj(a.admission) && arr(a.admission.currentRestrictions).some((c) => /withdraw/i.test(str(c))))
      .map((a) => str(a.participantId)));

    const msg = formMsg();
    const sel = h('select', { id: 'wd-participant' },
      h('option', { value: '' }, 'Choose a participant'),
      participants.map((p) => h('option', { value: p }, withdrawn.has(p) ? `${p} (currently withdrawn)` : p)));
    const reason = h('input', { type: 'text', id: 'wd-reason', autocomplete: 'off', maxlength: '200', value: 'synthetic-demo-withdrawal' });
    const submit = h('button', { type: 'submit', class: 'btn' }, 'Withdraw participant…');

    const form = h('form', { class: 'form', novalidate: true, 'aria-labelledby': 'wd-title' },
      h('h3', { class: 'form-title', id: 'wd-title' }, 'Withdraw a synthetic participant'),
      h('p', { class: 'form-intro' }, 'Appends a withdrawal. It blocks current review access and admission for every attempt by that participant. Earlier records stay intact in history.'),
      h('div', { class: 'form-cols' },
        h('div', { class: 'field' }, h('label', { for: 'wd-participant' }, 'Participant'), sel),
        h('div', { class: 'field' }, h('label', { for: 'wd-reason' }, 'Reason'),
          h('p', { class: 'hint', id: 'wd-reason-hint' }, 'Prefilled with an example; edit if needed.'), reason)),
      h('div', { class: 'actions' }, submit),
      msg);
    reason.setAttribute('aria-describedby', 'wd-reason-hint');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      sel.removeAttribute('aria-invalid');
      reason.removeAttribute('aria-invalid');
      const pid = sel.value;
      const why = reason.value.trim();
      if (!pid) { sel.setAttribute('aria-invalid', 'true'); setMsg(msg, 'Choose a participant.'); sel.focus(); return; }
      if (!why) { reason.setAttribute('aria-invalid', 'true'); setMsg(msg, 'Enter a reason.'); reason.focus(); return; }
      const operationUi = app.ui;
      const ok = await confirmAction({
        title: `Withdraw ${pid}?`,
        body: [
          'This appends a withdrawal record. It cannot be removed from the log.',
          'Review access and admission for this participant will be blocked from now on. Existing records remain in history and in the export.',
        ],
        confirmLabel: 'Append withdrawal',
      });
      if (!ok || app.ui !== operationUi) return;
      const res = await post('/api/withdraw', { participantId: pid, reason: why },
        { button: submit, msg, busyText: 'Appending…', success: `Withdrawal appended for ${pid}.` });
      if (res) {
        app.ui.focusId = 'sec-withdraw-h';
        await load();
      }
    });

    return section('sec-withdraw', null, 'Withdrawal',
      withdrawn.size ? `Currently withdrawn: ${[...withdrawn].sort().join(', ')}.` : 'No participant is currently withdrawn.',
      form);
  }

  // ---------- Reviewer ----------

  function renderReviewer(s) {
    const reviewerId = app.role; // the only identifier this view ever sends
    const roleLabel = roleName(reviewerId);
    const items = arr(s.items).filter((it) => isObj(it) && typeof it.itemId === 'string');
    const savedCount = items.filter((it) => it.review).length;
    // Only this reviewer's own seal is read; the projection carries no other reviewer's state.
    const sealed = typeof s.sealed === 'boolean' ? s.sealed : (app.ui.sealedHere ? true : null);

    const head = viewHead(roleLabel,
      'A local demo role. This view shows only your own items and answers: no participants, splits, sources, scores or the other reviewer’s work. It does not imply clinical qualification.');
    const sealedBanner = sealed === true
      ? h('div', { class: 'banner' }, h('strong', null, 'Batch sealed. '), 'Your answers are final and shown read-only.')
      : null;

    if (!items.length) {
      return h('div', null, head, staleBanner(), sealedBanner,
        h('div', { class: 'state-panel' },
          h('h2', null, 'No items to review'),
          h('p', null, 'Nothing is assigned to this view. Restricted attempts remain in the project’s complete roster.')));
    }

    if (!items.some((it) => it.itemId === app.ui.selectedItem)) {
      const firstOpen = items.find((it) => !it.review);
      app.ui.selectedItem = (firstOpen || items[0]).itemId;
    }
    const index = items.findIndex((it) => it.itemId === app.ui.selectedItem);
    const item = items[index];

    const queue = h('aside', { class: 'queue', 'aria-labelledby': 'queue-h' },
      h('div', { class: 'queue-head' },
        h('h3', { id: 'queue-h' }, 'Your items'),
        h('span', { class: 'muted' }, `${savedCount} of ${items.length} saved`)),
      h('ol', null, items.map((it, i) => {
        const p = isObj(it.prompt) ? it.prompt : {};
        const state = it.review ? 'Saved' : (sealed === true ? 'Not answered' : 'Open');
        return h('li', null, h('button', {
          type: 'button',
          class: 'queue-item',
          'aria-current': it.itemId === app.ui.selectedItem ? 'true' : null,
          onclick: () => { app.ui.selectedItem = it.itemId; app.ui.focusId = 'item-heading'; render(); },
        },
        h('span', { class: 'queue-n' }, String(i + 1)),
        h('span', { class: 'queue-word' }, str(p.word)),
        h('span', { class: it.review ? 'queue-state done' : 'queue-state' }, state),
        h('span', { class: 'queue-sub' }, str(p.targetPhone), it.recordingAvailable ? '' : ' · no recording')));
      })),
      sealBox(reviewerId, roleLabel, items.length, savedCount, sealed));

    return h('div', null, head, staleBanner(), sealedBanner,
      h('div', { class: 'layout-split' }, queue, itemPanel(item, index, items.length, reviewerId, sealed)));
  }

  function sealBox(reviewerId, roleLabel, total, saved, sealed) {
    const msg = formMsg();
    const complete = total > 0 && saved === total;
    const btn = h('button', { type: 'button', class: 'btn btn-primary', disabled: !complete }, 'Seal my reviews…');
    btn.addEventListener('click', async () => {
      const operationUi = app.ui;
      const ok = await confirmAction({
        title: `Seal ${roleLabel}’s batch?`,
        body: [
          `All ${total} items have saved answers. Sealing is final: no further answers can be added to this batch.`,
          'Comparison with the other reviewer and adjudication can begin only after both batches are sealed.',
        ],
        confirmLabel: 'Seal batch',
      });
      if (!ok || app.ui !== operationUi) return;
      const res = await post('/api/seal', { reviewerId },
        { button: btn, msg, busyText: 'Sealing…', success: `${roleLabel} batch sealed.` });
      if (res) {
        app.ui.sealedHere = true;
        app.ui.focusId = 'seal-h';
        await load();
      }
    });
    let statusText;
    if (sealed === true) statusText = 'Sealed. Answers in this batch are final. Comparison waits until the other batch is also sealed.';
    else if (complete) statusText = 'Every item has an answer. Seal when you are done.';
    else statusText = `Save an answer for every item to enable sealing (${total - saved} remaining).`;
    const fill = h('span');
    fill.style.width = `${(saved / Math.max(total, 1)) * 100}%`; // CSSOM, permitted under the page CSP
    return h('div', { class: 'seal-box' },
      h('h3', { id: 'seal-h', tabindex: '-1' }, 'Seal batch'),
      h('div', { class: 'progress', role: 'progressbar', 'aria-label': 'Items saved', 'aria-valuemin': '0', 'aria-valuemax': String(total), 'aria-valuenow': String(saved) },
        fill),
      h('p', null, statusText),
      sealed === null ? h('p', { class: 'muted small' }, 'This view does not report seal status; the server refuses a second seal.') : null,
      h('div', { class: 'actions' }, sealed === true ? h('span', { class: 'pill pill-accent' }, 'Sealed') : btn),
      msg);
  }

  function recordingNote(item) {
    if (item.recordingAvailable === true) {
      return h('div', { class: 'recording-note', role: 'note' },
        h('strong', null, item.synthetic === false ? 'No playback in this workbench. ' : 'Synthetic fixture. '),
        'A recording record exists for this item, but no audio file exists and nothing can be played. Answers here exercise the review workflow only.');
    }
    return h('div', { class: 'recording-note', role: 'note' },
      h('strong', null, 'No recording available. '),
      'This item has no recording you can review. The reason is not shown in this view. Record it with the unavailable answers.');
  }

  function itemPanel(item, index, total, reviewerId, sealed) {
    const p = isObj(item.prompt) ? item.prompt : {};
    const occ = Number.isInteger(p.occurrenceIndex) ? p.occurrenceIndex : null;
    let body;
    if (item.review) body = savedAnswer(item.review);
    else if (sealed === true) {
      body = h('p', { class: 'callout' }, h('strong', null, 'Batch sealed. '),
        'No answer was saved for this item before sealing, and none can be added now.');
    } else body = reviewForm(item, reviewerId, index);
    return h('section', { class: 'panel', 'aria-labelledby': 'item-heading' },
      h('div', { class: 'panel-head' },
        h('h3', { id: 'item-heading', tabindex: '-1' }, `Item ${index + 1} of ${total}`),
        h('div', { class: 'meta' }, 'Opaque item ID ', h('code', null, item.itemId))),
      h('dl', { class: 'prompt-facts' },
        h('dt', null, 'Word'), h('dd', null, h('span', { class: 'prompt-word' }, str(p.word))),
        h('dt', null, 'Target phone'), h('dd', null, h('code', null, str(p.targetPhone))),
        h('dt', null, 'Variant'), h('dd', null, h('code', null, str(p.variantId))),
        h('dt', null, 'Phones'), h('dd', null, phonesView(p.phones, occ === null ? [] : [occ])),
        h('dt', null, 'Target occurrence'), h('dd', null, occ === null ? nil('Not specified for this item') : `index ${occ} (zero-based)`)),
      recordingNote(item),
      body);
  }

  function savedAnswer(rec) {
    const ans = answerOf(rec) || {};
    return h('div', null,
      h('h4', { class: 'subhead' }, 'Your saved answer'),
      h('p', { class: 'subnote' }, 'Saved answers are immutable and cannot be edited or replaced.'),
      h('table', { class: 'kv' }, h('tbody', null,
        ANSWER_FIELDS.map((f) => h('tr', null, h('th', { scope: 'row' }, f.legend), h('td', null, str(ans[f.key]) || '—'))),
        h('tr', null, h('th', { scope: 'row' }, 'Notes'), h('td', null, ans.notes ? str(ans.notes) : nil('No notes'))),
        shaOf(rec) ? h('tr', null, h('th', { scope: 'row' }, 'Record SHA-256'), h('td', null, hashView(shaOf(rec), true))) : null)));
  }

  function readAnswer(form) {
    const out = {};
    ANSWER_FIELDS.forEach((f) => { out[f.key] = checkedValue(form, `rv-${f.key}`); });
    out.notes = form.querySelector('#rv-notes').value;
    return out;
  }

  function reviewForm(item, reviewerId, index) {
    const key = item.itemId;
    const draft = app.ui.drafts[key] || {};
    const msg = formMsg();
    const groups = ANSWER_FIELDS.map((f) => choiceGroup({
      name: `rv-${f.key}`,
      legend: f.legend,
      hint: f.question,
      options: f.options.map((o) => ({ value: o, label: o })),
      value: draft[f.key],
    }));
    const notes = h('textarea', { id: 'rv-notes', rows: '3', maxlength: String(NOTES_MAX), 'aria-describedby': 'rv-notes-count' }, str(draft.notes));
    const counter = h('span', { class: 'counter', id: 'rv-notes-count' }, `${str(draft.notes).length} / ${NOTES_MAX} characters`);
    const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, 'Save final answer');

    const fillBtn = item.recordingAvailable === true ? null
      : h('button', { type: 'button', class: 'btn' }, 'Fill unavailable answers');

    const form = h('form', { novalidate: true, 'aria-label': 'Review answer' },
      h('p', { class: 'answers-intro' }, 'All five answers are required. Nothing is preselected.'),
      fillBtn ? h('div', { class: 'actions' }, fillBtn,
        h('p', { class: 'hint' }, 'Sets speech, prompt match and occurrence to unavailable, target to unscorable and quality to unusable. Check, then save.')) : null,
      fillBtn ? h('div', { class: 'spacer-8' }) : null,
      groups,
      h('div', { class: 'field' },
        h('label', { for: 'rv-notes' }, 'Notes ', h('span', { class: 'optional' }, '(optional)')),
        notes, counter),
      h('div', { class: 'actions' }, submit, h('p', { class: 'hint' }, 'Saving is final for this item.')),
      msg);

    const syncDraft = () => {
      app.ui.drafts[key] = readAnswer(form);
      counter.textContent = `${notes.value.length} / ${NOTES_MAX} characters`;
    };
    form.addEventListener('input', syncDraft);
    form.addEventListener('change', (e) => {
      syncDraft();
      const fs = e.target.closest && e.target.closest('.choices');
      if (fs) fs.classList.remove('invalid');
    });

    if (fillBtn) {
      fillBtn.addEventListener('click', () => {
        Object.keys(UNAVAILABLE_FILL).forEach((k) => {
          const input = form.querySelector(`input[name="rv-${k}"][value="${UNAVAILABLE_FILL[k]}"]`);
          if (input) input.checked = true;
        });
        form.querySelectorAll('.choices.invalid').forEach((el) => el.classList.remove('invalid'));
        syncDraft();
        setMsg(msg, 'Unavailable answers filled in. Nothing is saved until you press Save final answer.', 'info');
      });
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const ans = readAnswer(form);
      const missing = [];
      ANSWER_FIELDS.forEach((f, i) => {
        groups[i].classList.toggle('invalid', !ans[f.key]);
        if (!ans[f.key]) missing.push(f);
      });
      if (missing.length) {
        setMsg(msg, `Choose an answer for: ${missing.map((f) => f.legend).join(', ')}.`);
        const first = groups[ANSWER_FIELDS.indexOf(missing[0])].querySelector('input');
        if (first) first.focus();
        return;
      }
      if (ans.notes.length > NOTES_MAX) {
        setMsg(msg, `Notes must be ${NOTES_MAX} characters or fewer.`);
        notes.focus();
        return;
      }
      const answer = {
        speech: ans.speech,
        promptMatch: ans.promptMatch,
        occurrence: ans.occurrence,
        target: ans.target,
        quality: ans.quality,
        notes: ans.notes,
      };
      const res = await post('/api/reviews', { reviewerId, itemId: item.itemId, answer },
        { button: submit, msg, busyText: 'Saving…', success: `Item ${index + 1} saved.` });
      if (res) {
        delete app.ui.drafts[key];
        const items = arr(app.state && app.state.items).filter(isObj);
        const after = items.slice(index + 1).concat(items.slice(0, index));
        const next = after.find((it) => !it.review && it.itemId !== key);
        app.ui.selectedItem = next ? next.itemId : key;
        app.ui.focusId = 'item-heading';
        await load();
      }
    });

    return form;
  }

  // ---------- Adjudicator ----------

  function renderAdjudicator(s) {
    const seals = isObj(s.seals) ? s.seals : {};
    const bothSealed = seals['reviewer-a'] === true && seals['reviewer-b'] === true;
    const items = arr(s.items).filter((it) => isObj(it) && it.attemptId !== undefined);
    const head = viewHead('Adjudicator',
      'Prioritise attempts whose sealed original targets differ. A separate target decision may also be recorded where they agree. Originals are retained unchanged; your record is appended separately.');

    const sealLine = h('p', { class: 'summary-line' },
      h('span', null, 'Reviewer A ', h('b', null, sealText(seals['reviewer-a']).toLowerCase())),
      h('span', null, 'Reviewer B ', h('b', null, sealText(seals['reviewer-b']).toLowerCase())));

    // Before both seals the server returns an empty item list with seal status; that is a wait, not an empty case.
    if (!items.length) {
      const waitingOn = REVIEWER_IDS.filter((id) => seals[id] !== true).map(roleName);
      return h('div', null, head, staleBanner(), sealLine,
        h('div', { class: 'state-panel' },
          bothSealed
            ? [h('h2', null, 'No items to adjudicate'), h('p', null, 'Both batches are sealed, but the server returned no paired originals for adjudication.')]
            : [h('h2', null, 'Waiting for both batches to be sealed'),
              h('p', null, `Adjudication opens after Reviewer A and Reviewer B have each sealed their batch. Still waiting on ${waitingOn.join(' and ')}.`),
              h('p', null, 'Nothing needs doing here yet. Sealed originals will appear in this view.')],
          h('div', { class: 'actions' },
            h('button', { type: 'button', class: 'btn', onclick: () => load() }, 'Check again'))));
    }

    if (!items.some((it) => str(it.attemptId) === app.ui.selectedAttempt)) {
      const first = items.find((it) => !it.adjudication && targetStatus(it).needs)
        || items.find((it) => !it.adjudication) || items[0];
      app.ui.selectedAttempt = str(first.attemptId);
    }
    const index = items.findIndex((it) => str(it.attemptId) === app.ui.selectedAttempt);
    const item = items[index];
    const differing = items.filter((it) => targetStatus(it).differs);
    const open = differing.filter((it) => !it.adjudication).length;
    const done = items.filter((it) => it.adjudication).length;

    const queue = h('aside', { class: 'queue', 'aria-labelledby': 'adj-queue-h' },
      h('div', { class: 'queue-head' },
        h('h3', { id: 'adj-queue-h' }, 'Sealed originals'),
        h('span', { class: 'muted' }, `${differing.length} differ · ${done} recorded`)),
      h('p', { class: 'small muted queue-note' },
        open ? `${open} target disagreement${open === 1 ? '' : 's'} still need${open === 1 ? 's' : ''} a decision.` : 'Every target disagreement has a recorded decision.',
        ' Agreeing attempts may also be adjudicated.'),
      h('ol', null, items.map((it, i) => {
        const p = isObj(it.prompt) ? it.prompt : {};
        const ta = targetOf(it.reviewA);
        const tb = targetOf(it.reviewB);
        const st = targetStatus(it);
        return h('li', null, h('button', {
          type: 'button',
          class: 'queue-item',
          'aria-current': str(it.attemptId) === app.ui.selectedAttempt ? 'true' : null,
          onclick: () => { app.ui.selectedAttempt = str(it.attemptId); app.ui.focusId = 'adj-heading'; render(); },
        },
        h('span', { class: 'queue-n' }, String(i + 1)),
        h('span', { class: 'queue-word' }, str(p.word)),
        h('span', { class: it.adjudication ? 'queue-state done' : (st.differs ? 'queue-state attn' : 'queue-state') },
          `${st.differs ? 'Differs' : 'Agrees'}${it.adjudication ? ' · recorded' : ''}`),
        h('span', { class: 'queue-sub' }, `${str(p.targetPhone)} · A ${ta || '—'} · B ${tb || '—'}`)));
      })));

    return h('div', null, head, staleBanner(), sealLine,
      h('div', { class: 'layout-split' }, queue, adjudicationPanel(item, index, items.length)));
  }

  function targetStatus(item) {
    const ta = targetOf(item.reviewA);
    const tb = targetOf(item.reviewB);
    if (ta && tb && ta !== tb) {
      return { differs: true, needs: true,
        node: h('p', { class: 'callout callout-accent' }, h('strong', null, 'Targets differ. '),
          `Reviewer A chose “${ta}”; Reviewer B chose “${tb}”. Choose an adjudicated target and give a rationale.`) };
    }
    if (ta && tb && !SCORABLE_TARGETS.includes(ta)) {
      return { differs: false, needs: true,
        node: h('p', { class: 'callout' }, h('strong', null, `Both originals are “${ta}”. `),
          'You may record a separate target decision. It resolves the target judgment only; the occurrence, speech, prompt-match and quality answers keep their original result.') };
    }
    if (ta && tb) {
      return { differs: false, needs: false,
        node: h('p', { class: 'callout' }, h('strong', null, 'Targets agree. '),
          `Both reviewers chose “${ta}”. Adjudication is not required; a separate target decision may still be recorded below.`) };
    }
    return { differs: false, needs: true,
      node: h('p', { class: 'callout' }, h('strong', null, 'Original targets incomplete. '), 'Both sealed originals are needed before adjudication.') };
  }

  function adjudicationPanel(item, index, total) {
    const p = isObj(item.prompt) ? item.prompt : {};
    const a = answerOf(item.reviewA) || {};
    const b = answerOf(item.reviewB) || {};
    const shaA = shaOf(item.reviewA);
    const shaB = shaOf(item.reviewB);
    const st = targetStatus(item);
    const rows = ANSWER_FIELDS.map((f) => {
      const differs = str(a[f.key]) !== str(b[f.key]);
      return h('tr', null,
        h('th', { scope: 'row', class: differs ? 'differs' : null }, f.legend,
          differs ? h('span', { class: 'diff-mark' }, 'differs') : null),
        h('td', { class: differs ? 'differs' : null }, str(a[f.key]) || '—'),
        h('td', { class: differs ? 'differs' : null }, str(b[f.key]) || '—'));
    });
    const compare = h('table', { class: 'compare' },
      h('caption', { class: 'sr-only' }, 'Sealed original answers side by side'),
      h('thead', null, h('tr', null, th('Answer'), th('Reviewer A original'), th('Reviewer B original'))),
      h('tbody', null, rows,
        h('tr', null, h('th', { scope: 'row' }, 'Notes'),
          h('td', null, a.notes ? str(a.notes) : nil('No notes')),
          h('td', null, b.notes ? str(b.notes) : nil('No notes'))),
        h('tr', null, h('th', { scope: 'row' }, 'Record SHA-256'),
          h('td', null, hashView(shaA, true)), h('td', null, hashView(shaB, true)))));

    let action;
    if (item.adjudication) action = savedAdjudication(item.adjudication);
    else if (st.needs) action = adjudicationForm(item, shaA, shaB);
    else {
      const key = `adj:${str(item.attemptId)}`;
      action = h('details', { class: 'more', open: Boolean(app.ui.drafts[key]) },
        h('summary', null, 'Optional: record a separate target decision'),
        h('div', { class: 'more-body' }, adjudicationForm(item, shaA, shaB)));
    }

    return h('section', { class: 'panel', 'aria-labelledby': 'adj-heading' },
      h('div', { class: 'panel-head' },
        h('h3', { id: 'adj-heading', tabindex: '-1' }, `Attempt ${index + 1} of ${total}`),
        h('div', { class: 'meta' }, 'Attempt ', h('code', null, str(item.attemptId)))),
      h('dl', { class: 'prompt-facts' },
        h('dt', null, 'Word'), h('dd', null, h('span', { class: 'prompt-word' }, str(p.word))),
        h('dt', null, 'Target phone'), h('dd', null, h('code', null, str(p.targetPhone))),
        h('dt', null, 'Variant'), h('dd', null, h('code', null, str(p.variantId))),
        h('dt', null, 'Phones'), h('dd', null, phonesView(p.phones, Number.isInteger(p.occurrenceIndex) ? [p.occurrenceIndex] : [])),
        h('dt', null, 'Target occurrence'), h('dd', null, Number.isInteger(p.occurrenceIndex) ? `index ${p.occurrenceIndex} (zero-based)` : nil('Unresolved occurrence'))),
      item.adjudication ? null : st.node,
      Number.isInteger(p.occurrenceIndex) ? null
        : h('p', { class: 'callout' }, h('strong', null, 'No target occurrence selected. '),
          'This attempt always abstains. A target decision can still be recorded, but it does not make the attempt eligible.'),
      tableWrap(compare, 'Original reviews'),
      action);
  }

  function savedAdjudication(rec) {
    const ans = answerOf(rec) || {};
    return h('div', null,
      h('h4', { class: 'subhead' }, 'Recorded adjudication'),
      h('p', { class: 'subnote' }, 'Appended separately. Both originals above remain unchanged.'),
      h('table', { class: 'kv' }, h('tbody', null,
        h('tr', null, h('th', { scope: 'row' }, 'Target'), h('td', null, str(ans.target))),
        h('tr', null, h('th', { scope: 'row' }, 'Rationale'), h('td', null, str(ans.notes))),
        h('tr', null, h('th', { scope: 'row' }, 'Cited originals'), h('td', null, arr(ans.reviewedOriginals).map((x) => h('div', null, hashView(x, true))))),
        shaOf(rec) ? h('tr', null, h('th', { scope: 'row' }, 'Record SHA-256'), h('td', null, hashView(shaOf(rec), true))) : null)));
  }

  function adjudicationForm(item, shaA, shaB) {
    const key = `adj:${str(item.attemptId)}`;
    const draft = app.ui.drafts[key] || {};
    if (!shaA || !shaB) {
      return h('p', { class: 'form-msg error' }, 'Both sealed original reviews and their digests are needed before this attempt can be adjudicated.');
    }
    const msg = formMsg();
    const target = choiceGroup({
      name: 'adj-target', legend: 'Adjudicated target', hint: 'Resolves the target judgment only. It cannot resolve an ambiguous occurrence or the speech, prompt-match, quality or other admission gates.',
      options: TARGET_OPTIONS.map((o) => ({ value: o, label: o })), value: draft.target,
    });
    const notes = h('textarea', { id: 'adj-notes', rows: '4', maxlength: String(NOTES_MAX), 'aria-describedby': 'adj-notes-hint' }, str(draft.notes));
    const confirmBox = h('input', { type: 'checkbox', id: 'adj-confirm', checked: draft.confirmed === true });
    const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, 'Record adjudication');

    const form = h('form', { class: 'form', novalidate: true, 'aria-labelledby': 'adj-form-h' },
      h('h4', { class: 'form-title', id: 'adj-form-h' }, 'Record adjudication'),
      target,
      h('div', { class: 'field' },
        h('label', { for: 'adj-notes' }, 'Rationale'),
        h('p', { class: 'hint', id: 'adj-notes-hint' }, `Required. Up to ${NOTES_MAX} characters.`),
        notes),
      h('p', { class: 'field-label' }, 'Cited originals'),
      h('dl', { class: 'cited' },
        h('dt', null, 'Reviewer A'), h('dd', null, hashView(shaA, true)),
        h('dt', null, 'Reviewer B'), h('dd', null, hashView(shaB, true))),
      h('div', { class: 'field' },
        h('label', { class: 'check', for: 'adj-confirm' }, confirmBox, 'I have reviewed both sealed originals shown above.')),
      h('div', { class: 'actions' }, submit, h('p', { class: 'hint' }, 'Recording is final for this attempt.')),
      msg);

    const sync = () => {
      app.ui.drafts[key] = { target: checkedValue(form, 'adj-target'), notes: notes.value, confirmed: confirmBox.checked };
    };
    form.addEventListener('input', sync);
    form.addEventListener('change', () => { sync(); target.classList.remove('invalid'); });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      notes.removeAttribute('aria-invalid');
      const t = checkedValue(form, 'adj-target');
      const problems = [];
      let first = null;
      if (!t) { problems.push('choose a target'); target.classList.add('invalid'); first = target.querySelector('input'); }
      if (!notes.value.trim()) { problems.push('enter a rationale'); notes.setAttribute('aria-invalid', 'true'); if (!first) first = notes; }
      if (!confirmBox.checked) { problems.push('confirm you reviewed both originals'); if (!first) first = confirmBox; }
      if (problems.length) {
        setMsg(msg, `Before recording: ${problems.join('; ')}.`);
        if (first) first.focus();
        return;
      }
      const res = await post('/api/adjudications',
        { attemptId: item.attemptId, answer: { target: t, notes: notes.value, reviewedOriginals: [shaA, shaB] } },
        { button: submit, msg, busyText: 'Recording…', success: `Adjudication recorded for ${str(item.attemptId)}.` });
      if (res) {
        delete app.ui.drafts[key];
        app.ui.focusId = 'adj-heading';
        await load();
      }
    });
    return form;
  }

  // ---------- Boot ----------

  function init() {
    $('#flash-dismiss').addEventListener('click', clearFlash);
    $('#flash-dismiss').hidden = true;
    $('#skip-link').addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.getElementById('view-title') || $('#main');
      target.focus();
    });
    window.addEventListener('hashchange', () => {
      const role = roleFromHash();
      if (!role) {
        history.replaceState(null, '', `#role=${app.role}`);
        return;
      }
      if (role !== app.role) switchRole(role);
    });
    const initial = roleFromHash();
    if (!initial) history.replaceState(null, '', '#role=coordinator');
    app.role = initial || 'coordinator';
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
