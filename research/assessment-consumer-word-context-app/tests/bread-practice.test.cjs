// Actual UI functions with generated in-memory state; no browser, audio or models.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8');
const catalog = JSON.parse(source.match(/const GUIDED_CANONICAL_CATALOG = (.*);/)[1]);
const block = source.slice(source.indexOf('  // A listening focus'), source.indexOf('  function renderGuided()'));
const compare = source.slice(source.indexOf('  function renderCompare()'), source.indexOf('  function renderSession()'));
function element() { return { hidden: false, disabled: false, textContent: '', dataset: {}, focus() { this.focused = true; } }; }
function setup() {
  const bread = catalog.find(p => p.id === 'r-middle-bread');
  const ui = Object.fromEntries(['brCue', 'brActions', 'brTake', 'brRecord', 'record', 'recordCancel', 'recordPanel', 'compare', 'compareHint', 'compareNote', 'takesClear'].map(k => [k, element()]));
  ui.recordCancel.hidden = true;
  const c = { app: { mode: 'free', guided: null, setupGen: 4, takes: [], age: null, optIn: false },
    ui, GUIDED_CANONICAL_CATALOG: catalog, prompt: structuredClone(bread), exampleSource: '/api/public-references/bread',
    isCapturing: false, playback: { takeId: null }, calls: [], canonicalJson: JSON.stringify,
    selectedPrompt() { return c.prompt; }, latestTake() { return c.app.takes.at(-1); },
    capturing() { return c.isCapturing; },
    toggleExample() { c.calls.push('example'); }, toggleTake(id) { c.calls.push(['take', id]); },
    onRecordClick() { c.calls.push('record'); c.isCapturing = true; c.ui.recordCancel.hidden = false; c.renderBrPractice(); },
    renderTryRow() {}, positionOf() { return 'middle'; } };
  ui.rows = [element(), element()];
  vm.createContext(c); vm.runInContext(block + compare, c);
  c.addTake = (id = 1) => { c.app.takes.push({ id, promptId: bread.id, setupGen: 4 }); c.renderBrPractice(); };
  return c;
}
test('cue is word based and needs neither age nor checking; actions need a current take', () => {
  const c = setup(); c.renderBrPractice();
  assert.equal(c.ui.brCue.hidden, false); assert.match(c.ui.brCue.textContent, /whole word/);
  assert.equal(c.ui.brActions.hidden, true);
  c.addTake(); assert.equal(c.ui.brActions.hidden, false); assert.equal(c.ui.brRecord.disabled, false);
  assert.equal(c.app.optIn, false); assert.equal(c.app.age, null);
});
test('wrong canonical word, guided practice and missing example all suppress the step', () => {
  for (const mutate of [c => c.prompt.id = 'r-beginning-rabbit', c => c.prompt.processingPrompt.words[0].phones[1] = 'W',
    c => c.app.mode = 'guided', c => c.app.guided = {}, c => c.exampleSource = null, c => c.prompt = null]) {
    const c = setup(); c.addTake(); mutate(c); c.renderBrPractice();
    assert.equal(c.ui.brCue.hidden, true); assert.equal(c.ui.brActions.hidden, true);
    c.onBrExample(); c.onBrTake(); c.onBrRecord(); assert.deepEqual(c.calls, []);
  }
});
test('stale context and guided-owned takes cannot be replayed or retried', () => {
  for (const mutate of [t => t.setupGen = 3, t => t.promptId = 'rabbit', t => t.guidedOwner = {}]) {
    const c = setup(); c.addTake(); mutate(c.app.takes[0]); c.renderBrPractice();
    assert.equal(c.ui.brActions.hidden, true); c.onBrTake(); c.onBrRecord(); assert.deepEqual(c.calls, []);
  }
  const c = setup(); c.addTake(); c.ui.brTake.dataset.take = '999'; c.onBrTake(); assert.deepEqual(c.calls, []);
});
test('replay owns the latest take and updates after ended, clear and replacement renders', () => {
  const c = setup(); c.addTake(1); c.onBrTake(); assert.deepEqual(c.calls, [['take', 1]]);
  c.playback.takeId = 1; c.renderCompare(); assert.equal(c.ui.brTake.textContent, 'Stop this try');
  c.playback.takeId = null; c.renderCompare(); assert.equal(c.ui.brTake.textContent, 'Play this try');
  c.addTake(2); c.onBrTake(); assert.deepEqual(c.calls.at(-1), ['take', 2]);
  c.app.takes = []; c.renderCompare(); assert.equal(c.ui.brActions.hidden, true); assert.equal(c.ui.brTake.dataset.take, '');
});
test('capture suppresses row and blocks all three shortcut handlers', () => {
  const c = setup(); c.addTake(); c.isCapturing = true; c.renderBrPractice();
  assert.equal(c.ui.brActions.hidden, true); c.onBrExample(); c.onBrTake(); c.onBrRecord(); assert.deepEqual(c.calls, []);
});
test('retry follows existing record guard and focuses the persistent named recorder', () => {
  const c = setup(); c.addTake(); c.ui.record.disabled = true; c.renderBrPractice();
  assert.equal(c.ui.brRecord.disabled, true); c.onBrRecord(); assert.deepEqual(c.calls, []);
  c.ui.record.disabled = false; c.renderBrPractice(); c.onBrRecord();
  assert.deepEqual(c.calls, ['record']); assert.equal(c.ui.recordPanel.focused, true); assert.equal(c.ui.brActions.hidden, true);
  c.ui.recordCancel.hidden = true; c.isCapturing = false; c.renderBrPractice();
  assert.equal(c.ui.recordPanel.focused, true);
});
