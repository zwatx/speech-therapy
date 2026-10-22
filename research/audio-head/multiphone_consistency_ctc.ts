/** Fixed inner-split q8 batch cache; shares the explicit research runtime loader. */
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { loadRuntime, OPTIONS, type Runtime } from "./multiphone_research_ctc.ts";
import { phonemeCtcBaselineManifest as checkpoint } from "../../packages/audio-model-adapter/src/manifest.ts";
import { convolutionFrames, logProbabilityBytes, readPcm16, sha256 } from "./multiphone_ctc_cache.ts";
interface Pin { path: string; sha256: string; }
interface Entry { id: string; clipId: string; audioPath: string; audioSha256: string; sampleCount: number; }
interface Plan { schemaVersion: number; authorPartition: string; partition: string; fold: number;
  phase: string; sourcePlanSha256: string; inputFiles: Record<string, Pin>; entries: Entry[];
  ctcCheckpoint: typeof checkpoint; sessionOptions: typeof OPTIONS; }
function requireCondition(ok: unknown, message: string): asserts ok { if (!ok) throw new Error(message); }
async function digest(path: string) {
  const h = createHash("sha256"); for await (const part of createReadStream(path)) h.update(part); return h.digest("hex");
}
async function guard(pins: Record<string, Pin>) {
  const seen = new Map<string, string>();
  for (const pin of Object.values(pins)) {
    if (!seen.has(pin.path)) seen.set(pin.path, await digest(pin.path));
    requireCondition(seen.get(pin.path) === pin.sha256, "Consistency CTC source or artifact changed");
  }
}
export function validatePlan(plan: Plan) {
  requireCondition(plan.schemaVersion === 1 && plan.authorPartition === "train" && plan.fold === 0 &&
    plan.partition === "innerFitRows+innerValidationRows" && ["parity", "noise20db"].includes(plan.phase) &&
    /^[a-f0-9]{64}$/.test(plan.sourcePlanSha256) && plan.entries.length > 0 && plan.entries.length <= 1996 &&
    (plan.phase !== "parity" || plan.entries.length <= 4) &&
    new Set(plan.entries.map(e => e.id)).size === plan.entries.length &&
    new Set(plan.entries.map(e => e.clipId)).size === plan.entries.length &&
    Object.keys(plan.sessionOptions).length === Object.keys(OPTIONS).length &&
    Object.entries(OPTIONS).every(([k,v]) => plan.sessionOptions[k as keyof typeof OPTIONS] === v) &&
    Object.keys(plan.ctcCheckpoint).length === Object.keys(checkpoint).length &&
    Object.entries(checkpoint).every(([k,v]) => JSON.stringify(plan.ctcCheckpoint[k as keyof typeof checkpoint]) === JSON.stringify(v)),
    "Invalid fixed inner CTC scope/checkpoint");
  for (const e of plan.entries) requireCondition(/^\d{9}$/.test(e.id) && e.id === e.clipId &&
    Number.isInteger(e.sampleCount) && e.sampleCount >= 1600 && e.sampleCount <= 480000 &&
    plan.inputFiles["audio/"+e.id]?.path === e.audioPath && plan.inputFiles["audio/"+e.id]?.sha256 === e.audioSha256,
    "CTC audio identity or duration differs");
}
export async function runBatch(planPath: string, expectedSha: string, output: string,
                               loader: () => Promise<Runtime> = loadRuntime) {
  const payload = await readFile(planPath);
  requireCondition(sha256(payload) === expectedSha, "Caller-pinned CTC manifest differs");
  const plan: Plan = JSON.parse(payload.toString("utf8")); validatePlan(plan);
  requireCondition(resolve(output).startsWith(resolve(dirname(planPath)) + "/"), "CTC output must remain within prepared run");
  const pins = {...plan.inputFiles, batchPlan:{path:planPath,sha256:expectedSha}};
  await guard(pins);
  await mkdir(output, {mode:0o700}); // Fresh only: incomplete caches are evidence, never silently reused.
  const previousFetch = globalThis.fetch; let fetchAttempts = 0, runtime: Runtime | undefined;
  globalThis.fetch = async () => { fetchAttempts++; throw new Error("Network forbidden for consistency features"); };
  const entries: Record<string, unknown> = {}, started = performance.now();
  try {
    runtime = await loader();
    for (const entry of plan.entries) {
      const samples = readPcm16(await readFile(entry.audioPath), entry.audioSha256);
      requireCondition(samples.length === entry.sampleCount, "Paired waveform sample count differs");
      const begin=performance.now(), logits=await runtime.infer(samples);
      requireCondition(logits.dims[1] === convolutionFrames(samples.length), "Paired CTC geometry differs");
      const bytes=logProbabilityBytes(logits.data,logits.dims), name=entry.id+".f32";
      await writeFile(join(output,name),bytes,{flag:"wx",mode:0o600});
      const record={...entry,path:name,sha256:sha256(bytes),frames:logits.dims[1],inferenceSeconds:(performance.now()-begin)/1000};
      entries[entry.id]=record;
      await writeFile(join(output,entry.id+".json"),JSON.stringify(record)+"\n",{flag:"wx",mode:0o600});
      pins["posterior/"+entry.id]={path:join(output,name),sha256:record.sha256};
      pins["entry/"+entry.id]={path:join(output,entry.id+".json"),sha256:await digest(join(output,entry.id+".json"))};
      if(Object.keys(entries).length%50===0) console.log(`CTC ${Object.keys(entries).length}/${plan.entries.length}`);
    }
    await guard(pins);
    requireCondition(fetchAttempts===0 && Object.keys(entries).length===plan.entries.length,"CTC coverage/network check failed");
    const report={complete:true,sourcePlanSha256:plan.sourcePlanSha256,batchPlanSha256:expectedSha,phase:plan.phase,
      checkpoint,sessionOptions:OPTIONS,entries,fetchAttempts,node:process.version,elapsedSeconds:(performance.now()-started)/1000};
    await writeFile(join(output,"index.json"),JSON.stringify(report,null,2)+"\n",{flag:"wx",mode:0o600});
    return report;
  } finally { await runtime?.dispose(); globalThis.fetch=previousFetch; }
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const [plan,sha,out]=process.argv.slice(2); requireCondition(plan&&sha&&out,"Usage: node multiphone_consistency_ctc.ts PLAN SHA OUTPUT");
  runBatch(resolve(plan),sha,resolve(out)).then(()=>console.log("Completed fixed consistency CTC cache"))
    .catch(error=>{console.error(error);process.exitCode=1;});
}
