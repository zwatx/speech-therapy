import assert from "node:assert/strict";
import { mkdtemp,readFile,writeFile,rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { runBatch,validatePlan } from "./multiphone_consistency_ctc.ts";
import { OPTIONS } from "./multiphone_research_ctc.ts";
import { phonemeCtcBaselineManifest as checkpoint } from "../../packages/audio-model-adapter/src/manifest.ts";
import { sha256 } from "./multiphone_ctc_cache.ts";
function wav(){const b=Buffer.alloc(3244);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);
 b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);
 b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b;}
async function fixture(root:string){const audioPath=join(root,'noisy.wav'),payload=wav();await writeFile(audioPath,payload);
 const audioSha256=sha256(payload);const plan={schemaVersion:1,authorPartition:'train',partition:'innerFitRows+innerValidationRows',fold:0,
 phase:'noise20db',sourcePlanSha256:'a'.repeat(64),ctcCheckpoint:checkpoint,
 sessionOptions:{executionMode:OPTIONS.executionMode,interOpNumThreads:1,intraOpNumThreads:2},
 inputFiles:{'audio/000000001':{path:audioPath,sha256:audioSha256}},
 entries:[{id:'000000001',clipId:'000000001',audioPath,audioSha256,sampleCount:1600}]};
 const path=join(root,'batch.json');await writeFile(path,JSON.stringify(plan));return {plan,path,sha:sha256(await readFile(path))};}
test('fixed inner scope, checkpoint, duplicate clip and duration validation',async()=>{
 const root=await mkdtemp(join(tmpdir(),'consistency-scope-'));try{const {plan}=await fixture(root);validatePlan(plan);
 assert.throws(()=>validatePlan({...plan,fold:1}),/scope/);
 assert.throws(()=>validatePlan({...plan,partition:'outerHoldoutRows'}),/scope/);
 assert.throws(()=>validatePlan({...plan,entries:[...plan.entries,...plan.entries]}),/scope/);
 const x=structuredClone(plan);x.entries[0]!.sampleCount=1;assert.throws(()=>validatePlan(x),/duration/);
 }finally{await rm(root,{recursive:true,force:true});}});
test('one shared mock runtime writes complete bound full392 cache and rejects reuse',async()=>{
 const root=await mkdtemp(join(tmpdir(),'consistency-batch-'));try{const {path,sha}=await fixture(root);let loads=0,forwards=0,disposed=false;
 const result=await runBatch(path,sha,join(root,'ctc'),async()=>{loads++;return {async infer(){forwards++;return {data:new Float32Array(1568),dims:[1,4,392]};},async dispose(){disposed=true;}};});
 assert.equal(loads,1);assert.equal(forwards,1);assert.equal(disposed,true);assert.equal(result.complete,true);
 const entry=result.entries['000000001'] as {path:string;sha256:string};
 assert.equal(sha256(await readFile(join(root,'ctc',entry.path))),entry.sha256);
 await assert.rejects(runBatch(path,sha,join(root,'ctc')),/EEXIST/);
 }finally{await rm(root,{recursive:true,force:true});}});
test('late waveform mutation or swallowed network attempt cannot publish complete cache',async()=>{
 for(const mode of ['mutation','network']){const root=await mkdtemp(join(tmpdir(),'consistency-fail-'));try{
 const {path,sha,plan}=await fixture(root);
 await assert.rejects(runBatch(path,sha,join(root,'ctc'),async()=>({async infer(){
 if(mode==='mutation')await writeFile(plan.entries[0]!.audioPath,'changed');else await fetch('https://invalid.example').catch(()=>{});
 return {data:new Float32Array(1568),dims:[1,4,392]};},async dispose(){}})),mode==='mutation'?/artifact changed/:/network/);
 await assert.rejects(readFile(join(root,'ctc/index.json')),/ENOENT/);
 }finally{await rm(root,{recursive:true,force:true});}}});
