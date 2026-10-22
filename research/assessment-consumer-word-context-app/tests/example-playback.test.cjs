// Actual asynchronous UI loader; generated responses/players, no network or audio.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8');
const http = source.slice(source.indexOf('  async function readCapped('), source.indexOf('  // ---------- catalog ----------'));
const playback = source.slice(source.indexOf('  function stopExample()'), source.indexOf('  // ---------- recording ----------'));
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; };
function setup() {
  const events = {}, calls = [], revoked = [], deadlines = new Map();
  const audio = { src: '', currentTime: 0, currentSrc: '', playCount: 0,
    addEventListener(k, fn) { events[k] = fn; },
    async play() { this.playCount++; if (this.fail) throw Error('decoder'); this.currentSrc = this.src; events.playing(); },
    pause() {}, load() {}, removeAttribute() { this.src = ''; this.currentSrc = ''; } };
  const ui = Object.fromEntries(['examplePlay', 'compareExample', 'brExample', 'exampleStatus'].map(k => [k, {}]));
  const c = { ui, exampleAudio: audio, MAX_AUDIO_BYTES: 132096, AbortController, Blob, Uint8Array,
    window: { setTimeout(fn) { const id = deadlines.size + 1; deadlines.set(id, fn); return id; }, clearTimeout(id) { deadlines.delete(id); } },
    URL: { createObjectURL() { return 'blob:unit-' + (calls.filter(x => x === 'blob').length + 1); }, revokeObjectURL(url) { revoked.push(url); } },
    capturing() { return false; }, stopTake() { calls.push('stopTake'); },
    render() { c.renderExample(); }, fetch: async (url, options) => { calls.push({ url, options }); return c.response(); } };
  c.URL.createObjectURL = () => { calls.push('blob'); return 'blob:unit-' + calls.filter(x => x === 'blob').length; };
  c.response = () => ({ type: 'basic', status: 200, redirected: false,
    headers: { get(k) { return k === 'Content-Type' ? 'audio/wav' : '4'; } }, body: null,
    async arrayBuffer() { return new Uint8Array([1,2,3,4]).buffer; } });
  vm.createContext(c);
  vm.runInContext('let exampleGen=0,exampleSource=null,exampleFetch=null,exampleBlobUrl=null; const playback={example:"idle",exampleMessage:""};' + http + playback + '\nfunction state(){return {gen:exampleGen,source:exampleSource,controller:exampleFetch,blob:exampleBlobUrl,status:playback.example,message:playback.exampleMessage};}', c);
  return { c, audio, calls, revoked, deadlines, events };
}
test('Play explicitly fetches a bounded full WAV, plays a blob, and Stop revokes it', async () => {
  const {c, audio, calls, revoked} = setup(); c.setExampleSource('/api/public-references/bread'); assert.equal(calls.length, 0);
  await c.toggleExample(); const req = calls.find(x => x.url);
  assert.equal(req.options.headers.Accept, 'audio/wav'); assert.equal(req.options.headers.Range, undefined);
  assert.equal(req.options.redirect, 'error'); assert.equal(audio.src, 'blob:unit-1'); assert.equal(c.state().status, 'playing');
  c.stopExample(); assert.equal(c.state().status, 'idle'); assert.equal(audio.src, ''); assert.deepEqual(revoked, ['blob:unit-1']);
});
test('Stop and word changes reject a delayed response even if transport ignores abort', async () => {
  for (const changeWord of [false, true]) {
    const {c, audio, calls} = setup(); const d = deferred(); c.fetch = () => d.promise;
    c.setExampleSource('/api/public-references/bread'); const pending = c.toggleExample();
    if (changeWord) c.setExampleSource('/api/public-references/door'); else c.stopExample();
    d.resolve(c.response()); await pending;
    assert.equal(audio.playCount, 0); assert.equal(calls.includes('blob'), false); assert.equal(c.state().status, 'idle');
    assert.equal(c.state().source, changeWord ? '/api/public-references/door' : '/api/public-references/bread');
  }
});
test('oversized declared body and streamed body both refuse playback', async () => {
  for (const streaming of [false, true]) {
    const {c, audio} = setup(); let cancelled = 0;
    c.response = () => ({type:'basic',status:200,redirected:false,
      headers:{get(k){return k==='Content-Type'?'audio/wav':streaming?null:'132097';}},
      body:{getReader(){return {async read(){return {done:false,value:new Uint8Array(132097)};},async cancel(){cancelled++;}};}}});
    c.setExampleSource('/api/public-references/bread'); await c.toggleExample();
    assert.equal(audio.playCount,0); assert.equal(c.state().status,'idle'); assert.match(c.state().message,/could not be played/);
    if(streaming)assert.equal(cancelled,1);
  }
});
test('failed transport type, redirect, HTTP status and MIME refuse playback and cancel body', async () => {
  for (const mutate of [r=>r.type='cors',r=>r.redirected=true,r=>r.status=403,r=>r.headers.get=()=> 'text/html']) {
    const {c,audio} = setup(); let cancelled=0; const res=c.response();res.body={async cancel(){cancelled++;}};mutate(res);c.response=()=>res;
    c.setExampleSource('/api/public-references/bread');await c.toggleExample();
    assert.equal(audio.playCount,0);assert.equal(cancelled,1);assert.equal(c.state().status,'idle');
  }
});
test('download deadline abort rejection settles the current UI without a blob', async () => {
  const {c,audio,deadlines} = setup();c.fetch=(_,o)=>new Promise((_,reject)=>o.signal.addEventListener('abort',()=>reject(Error('aborted'))));
  c.setExampleSource('/api/public-references/bread');const pending=c.toggleExample();deadlines.values().next().value();await pending;
  assert.equal(c.state().status,'idle');assert.match(c.state().message,/could not be played/);assert.equal(audio.playCount,0);assert.equal(deadlines.size,0);
});
test('decoder failure and natural completion release the object URL and media source', async () => {
  for(const fail of [true,false]){
    const {c,audio,revoked,events}=setup();audio.fail=fail;c.setExampleSource('/api/public-references/bread');await c.toggleExample();
    if(!fail)events.ended();assert.equal(c.state().status,'idle');assert.equal(audio.src,'');assert.deepEqual(revoked,['blob:unit-1']);
  }
});
test('late completion cannot overwrite a newer download controller or selected example', async () => {
  const {c}=setup();const first=deferred(),second=deferred();let n=0;c.fetch=()=>++n===1?first.promise:second.promise;
  c.setExampleSource('/api/public-references/bread');const p1=c.toggleExample();
  c.setExampleSource('/api/public-references/door');const p2=c.toggleExample();const current=c.state().controller;
  first.resolve(c.response());await p1;assert.equal(c.state().controller,current);assert.equal(c.state().source,'/api/public-references/door');
  second.resolve(c.response());await p2;assert.equal(c.state().status,'playing');assert.equal(c.state().controller,null);
});
