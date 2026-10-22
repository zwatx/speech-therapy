import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test, { type TestContext } from "node:test";

import { withVerifiedCheckpoint } from "./model-cache.ts";

const bytes = Buffer.from("pinned model fixture");
const metadata = {
  "config.json": Buffer.from('{"model_type":"wav2vec2"}'),
  "preprocessor_config.json": Buffer.from('{"sampling_rate":16000}'),
  "vocab.json": Buffer.from('{"<pad>":0,"a":1}'),
};
const digest = (value: Uint8Array) => createHash("sha256").update(value).digest("hex");
const pin = {
  id: "fixture/acoustic-model",
  revision: "a".repeat(40),
  modelFile: "onnx/model_quantized.onnx",
  modelFileBytes: bytes.length,
  modelFileSha256: digest(bytes),
  configFileBytes: metadata["config.json"].length,
  configFileSha256: digest(metadata["config.json"]),
  preprocessorFileBytes: metadata["preprocessor_config.json"].length,
  preprocessorFileSha256: digest(metadata["preprocessor_config.json"]),
  vocabularyFileBytes: metadata["vocab.json"].length,
  vocabularyFileSha256: digest(metadata["vocab.json"]),
};

async function fixture(t: TestContext) {
  const cache = await mkdtemp(join(tmpdir(), "cadence-model-cache-test-"));
  t.after(() => rm(cache, { recursive: true, force: true }));
  const modelPath = join(cache, pin.id, pin.revision, pin.modelFile);
  await mkdir(dirname(modelPath), { recursive: true });
  for (const [file, contents] of Object.entries(metadata)) {
    await writeFile(join(cache, pin.id, pin.revision, file), contents);
  }
  return { cache, modelPath };
}

const noDownload: typeof fetch = async () => {
  assert.fail("A cached model must not be downloaded again.");
};

test("verified cached bytes are isolated from cache changes before runtime loading", async (t) => {
  const { cache, modelPath } = await fixture(t);
  await writeFile(modelPath, bytes);
  let snapshot: string | undefined;
  const loaded = await withVerifiedCheckpoint(cache, async (directory) => {
    snapshot = directory;
    await writeFile(modelPath, Buffer.alloc(bytes.length, 1));
    assert.deepEqual(await readFile(join(directory, pin.modelFile)), bytes);
    assert.equal((await stat(join(directory, pin.modelFile))).mode & 0o777, 0o400);
    return "runtime created";
  }, pin, noDownload);

  assert.equal(loaded, "runtime created");
  assert.ok(snapshot);
  await assert.rejects(stat(snapshot), { code: "ENOENT" });
});

test("same-length modified cache bytes fail before runtime construction without download", async (t) => {
  const { cache, modelPath } = await fixture(t);
  const corrupted = Buffer.from(bytes);
  corrupted[0] = (corrupted[0] ?? 0) ^ 1;
  await writeFile(modelPath, corrupted);
  let loads = 0;

  await assert.rejects(withVerifiedCheckpoint(cache, async () => { loads += 1; }, pin, noDownload),
    /SHA-256 integrity check/);
  assert.equal(loads, 0);
  assert.deepEqual(await readFile(modelPath), corrupted);
});

test("truncated cached model fails closed instead of silently repairing it", async (t) => {
  const { cache, modelPath } = await fixture(t);
  await writeFile(modelPath, bytes.subarray(0, -1));

  await assert.rejects(withVerifiedCheckpoint(cache, async () => assert.fail("Must not load"), pin, noDownload),
    /byte-length integrity check/);
});

test("a missing model is verified before atomic caching and is reused on the next load", async (t) => {
  const { cache, modelPath } = await fixture(t);
  let downloads = 0;
  const fetchModel: typeof fetch = async (input) => {
    downloads += 1;
    assert.equal(input, `https://huggingface.co/${pin.id}/resolve/${pin.revision}/${pin.modelFile}`);
    return new Response(bytes);
  };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await withVerifiedCheckpoint(cache, async (directory) => {
      assert.deepEqual(await readFile(join(directory, pin.modelFile)), bytes);
    }, pin, fetchModel);
  }
  assert.equal(downloads, 1);
  assert.deepEqual(await readFile(modelPath), bytes);
});

for (const [description, download] of [
  ["modified", Buffer.alloc(bytes.length, 1)],
  ["truncated", bytes.subarray(0, -1)],
  ["oversized", Buffer.concat([bytes, Buffer.from("extra")])],
] as const) {
  test(`a ${description} download is never cached or passed to the runtime`, async (t) => {
    const { cache, modelPath } = await fixture(t);
    const fetchModel: typeof fetch = async () => new Response(download);

    await assert.rejects(withVerifiedCheckpoint(cache, async () => assert.fail("Must not load"), pin, fetchModel),
      /pinned/);
    await assert.rejects(stat(modelPath), { code: "ENOENT" });
    assert.deepEqual(await readdir(dirname(modelPath)), []);
  });
}

test("private snapshot is removed when runtime construction fails", async (t) => {
  const { cache, modelPath } = await fixture(t);
  await writeFile(modelPath, bytes);
  let snapshot: string | undefined;

  await assert.rejects(withVerifiedCheckpoint(cache, async (directory) => {
    snapshot = directory;
    throw new Error("runtime could not initialize");
  }, pin, noDownload), /runtime could not initialize/);
  assert.ok(snapshot);
  await assert.rejects(stat(snapshot), { code: "ENOENT" });
});

for (const [filename, contents] of Object.entries(metadata)) {
  test(`same-length corrupted ${filename} fails closed before runtime construction`, async (t) => {
    const { cache, modelPath } = await fixture(t);
    await writeFile(modelPath, bytes);
    const metadataPath = join(cache, pin.id, pin.revision, filename);
    const corrupted = Buffer.from(contents);
    corrupted[0] = (corrupted[0] ?? 0) ^ 1;
    await writeFile(metadataPath, corrupted);
    await assert.rejects(
      withVerifiedCheckpoint(cache, async () => assert.fail("Must not load"), pin, noDownload),
      /SHA-256 integrity check/,
    );
    assert.deepEqual(await readFile(metadataPath), corrupted);
  });

  test(`truncated ${filename} fails closed before runtime construction`, async (t) => {
    const { cache, modelPath } = await fixture(t);
    await writeFile(modelPath, bytes);
    await writeFile(join(cache, pin.id, pin.revision, filename), contents.subarray(0, -1));
    await assert.rejects(
      withVerifiedCheckpoint(cache, async () => assert.fail("Must not load"), pin, noDownload),
      /byte-length integrity check/,
    );
  });
}

test("missing metadata is pinned before caching; the complete snapshot is then usable offline", async (t) => {
  const { cache, modelPath } = await fixture(t);
  await writeFile(modelPath, bytes);
  for (const filename of Object.keys(metadata)) await rm(join(cache, pin.id, pin.revision, filename));
  const downloaded: string[] = [];
  const fetchFile: typeof fetch = async (input) => {
    const filename = String(input).split("/").at(-1) as keyof typeof metadata;
    assert.equal(input, `https://huggingface.co/${pin.id}/resolve/${pin.revision}/${filename}`);
    assert.ok(filename in metadata, "The cached ONNX model must not be downloaded");
    downloaded.push(filename);
    return new Response(metadata[filename]);
  };
  await withVerifiedCheckpoint(cache, async () => undefined, pin, fetchFile);
  assert.deepEqual(downloaded, Object.keys(metadata));
  await withVerifiedCheckpoint(cache, async (directory) => {
    for (const [filename, contents] of Object.entries(metadata)) {
      await rm(join(cache, pin.id, pin.revision, filename));
      await writeFile(join(cache, pin.id, pin.revision, filename), Buffer.alloc(contents.length));
      assert.deepEqual(await readFile(join(directory, filename)), contents);
      assert.equal((await stat(join(directory, filename))).mode & 0o777, 0o400);
    }
    assert.deepEqual(await readFile(join(directory, pin.modelFile)), bytes);
  }, pin, noDownload);
});

test("a same-length corrupt metadata download is never cached or passed to the runtime", async (t) => {
  const { cache, modelPath } = await fixture(t);
  await writeFile(modelPath, bytes);
  const configPath = join(cache, pin.id, pin.revision, "config.json");
  await rm(configPath);
  await assert.rejects(
    withVerifiedCheckpoint(cache, async () => assert.fail("Must not load"), pin,
      async () => new Response(Buffer.alloc(metadata["config.json"].length))),
    /SHA-256 integrity check/,
  );
  await assert.rejects(stat(configPath), { code: "ENOENT" });
  assert.ok((await readdir(dirname(configPath))).every((name) => !name.includes(".download-")));
});
