"""Private input ownership and a single explicitly requested CLI job.

The HTTP layer receives only projections. The wait owner and cancellation use
one lock: no PID is signalled after wait has collected that exact child.
"""
from dataclasses import dataclass, field
import array
import base64
import binascii
import hashlib
import io
import json
import math
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import threading
import time
import uuid
import wave

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
PROTOTYPE = ROOT / "research/audio-head/local_wav_prototype"
PROTOTYPE_MANIFEST_SHA = "343fba5c967712c83518570876403b50e9bba93a64bce9feed6303710d5f0556"
MAX_JSON = 200_000
MAX_WAV = 132_096
PHONES = ("B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z", "SH", "CH",
          "JH", "L", "R", "W", "Y", "HH", "TH", "DH", "NG")
TERMINAL = {"cancelled", "complete", "failed", "cleanup_unknown"}
FLAGS = {
    "unverified-forced-canonical-location": "unverified_forced_canonical_location",
    "fewer-than-two-target-state-frames": "fewer_than_two_target_state_frames",
    "target-is-not-argmax-on-most-occupied-frames": "target_not_argmax_on_most_frames",
}


class SafeError(ValueError):
    def __init__(self, tag, status=400):
        super().__init__(tag)
        self.tag, self.status = tag, status


def require(value, tag, status=400):
    if not value:
        raise SafeError(tag, status)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def nonfinite(_):
        raise SafeError("invalid_json")

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)
        # Overflowing JSON floats are refused too; no nonfinite wire values.
        canonical(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as error:
        if isinstance(error, SafeError):
            raise
        raise SafeError("invalid_json") from None


def identifier(value, tag):
    try:
        require(type(value) is str and str(uuid.UUID(value)) == value, tag)
        return value
    except (ValueError, AttributeError):
        raise SafeError(tag) from None


def safe_path(path):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve()
            and not any(p.is_symlink() for p in (path, *path.parents)), "unsafe_path")
    return path


def read(path, maximum, *, private=False):
    path = safe_path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid(), "unsafe_file")
    require(not private or stat.S_IMODE(before.st_mode) == 0o600, "unsafe_file_mode")
    require(before.st_size <= maximum, "file_too_large")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(raw) == before.st_size and fields(before) == fields(after) == fields(path.stat()), "file_changed")
    return raw


def digest(path):
    # Frozen dependency bindings intentionally permit existing package symlinks,
    # exactly as the unchanged prototype does. Uploaded and app files do not.
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_bytes(path, raw):
    with Path(path).open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    save_bytes(path, canonical(value) + b"\n")


def validate_wav(data):
    # This is the original prototype's WAV gate, before any subprocess launch.
    require(type(data) is bytes and 44 <= len(data) <= MAX_WAV, "invalid_audio_size")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            require((source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
                    == (1, 2, 16000, "NONE"), "expected_mono_16khz_pcm16")
            count = source.getnframes()
            require(1600 <= count <= 64000, "duration_outside_0.1_to_4_seconds")
            pcm = source.readframes(count)
            require(len(pcm) == count * 2, "truncated_audio")
    except (wave.Error, EOFError):
        raise SafeError("malformed_wav") from None
    samples = array.array("h", pcm)
    if os.sys.byteorder != "little":
        samples.byteswap()
    return {"sampleCount": count, "durationMilliseconds": count / 16,
            "rms": math.sqrt(sum((s / 32768) ** 2 for s in samples) / count),
            "peak": max(abs(s / 32768) for s in samples),
            "railSamples": sum(s in (-32768, 32767) for s in samples)}


class SourceGuard:
    """Fail closed on incomplete app pins or changes to the frozen prototype."""
    def __init__(self, app=APP, root=ROOT, *, prototype_manifest_sha=PROTOTYPE_MANIFEST_SHA):
        self.app, self.root = safe_path(app), safe_path(root)
        self.prototype = self.root / "research/audio-head/local_wav_prototype"
        self.prototype_manifest_sha = prototype_manifest_sha
        self.manifest_raw = read(self.app / "source-pins.json", 512_000)
        self.manifest = parse(self.manifest_raw)
        self.check()

    def check(self):
        try:
            require(read(self.app / "source-pins.json", 512_000) == self.manifest_raw, "source_changed", 503)
            manifest = self.manifest
            require(type(manifest) is dict and set(manifest) == {"schemaVersion", "files", "prototypeSourceManifestSha256"}
                    and type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 1
                    and manifest["prototypeSourceManifestSha256"] == self.prototype_manifest_sha, "source_changed", 503)
            rows = manifest["files"]
            require(type(rows) is list and 1 <= len(rows) <= 128, "source_changed", 503)
            pinned = set()
            for row in rows:
                require(type(row) is dict and set(row) == {"path", "sha256"}, "source_changed", 503)
                path = Path(row["path"])
                require(not path.is_absolute() and ".." not in path.parts and str(path) == row["path"]
                        and row["path"] not in pinned and row["path"] != "source-pins.json", "source_changed", 503)
                require(sha(read(self.app / path, 4_000_000)) == row["sha256"], "source_changed", 503)
                pinned.add(row["path"])
            require({"phrase_app/__init__.py", "phrase_app/service.py", "phrase_app/server.py", "phrase_app/word_cli.py", "catalog.json",
                     "pyproject.toml", "README.md"} <= pinned, "source_changed", 503)
            found = set()
            expected_directories = {str(parent) for name in pinned for parent in Path(name).parents if str(parent) != "."}
            found_directories = set()
            for directory, names, files in os.walk(self.app, followlinks=False):
                require(not any((Path(directory) / name).is_symlink() for name in names), "source_changed", 503)
                found_directories.update(str((Path(directory) / name).relative_to(self.app)) for name in names)
                for name in files:
                    relative = str((Path(directory) / name).relative_to(self.app))
                    if relative != "source-pins.json":
                        found.add(relative)
            require(found == pinned and found_directories == expected_directories, "source_changed", 503)
            raw = read(self.prototype / "SOURCE-v4.json", 100_000)
            require(sha(raw) == self.prototype_manifest_sha, "source_changed", 503)
            prototype_rows = parse(raw)["files"]
            require(len(prototype_rows) == 12 and len({r["path"] for r in prototype_rows}) == 12, "source_changed", 503)
            for row in prototype_rows:
                path = self.root / row["path"]
                require(path.parent == self.prototype and sha(read(path, 100_000)) == row["sha256"], "source_changed", 503)
            config = parse(read(self.prototype / "pins.json", 64_000))
            sources = {str(self.root / name): value for name, value in config["sources"].items()}
            for name in ("rawContract", "occurrenceContract"):
                pin = config[name]
                sources[str(self.root / pin["path"])] = pin["sha256"]
            for path, expected in sources.items():
                require(digest(path) == expected, "source_changed", 503)
            raw_contract = parse(read(self.root / config["rawContract"]["path"], 100_000))
            head = self.prototype.parent
            sources.update({str(head / name): value for name, value in raw_contract["dependencySha256"].items()})
            for name in ("__init__.py", "common.py", "bindings.py", "cli.py", "worker.py", "pins.json", "phrase_admission.py", "phrase_cli.py"):
                sources[str(self.prototype / name)] = digest(self.prototype / name)
            for path, expected in sources.items():
                require(digest(path) == expected, "source_changed", 503)
            self.sources, self.config = sources, config
            self.seal = sha(self.manifest_raw)
        except (OSError, KeyError, TypeError, ValueError, RecursionError):
            raise SafeError("source_changed", 503) from None


def cleanup_owned(directory):
    """Validate a small owned tree before deletion; never chase links or caches."""
    directory = safe_path(directory)
    directories, files = [], []
    for current, names, leaves in os.walk(directory, followlinks=False):
        path = safe_path(current)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid(), "unsafe_cleanup")
        require(len(path.relative_to(directory).parts) <= 8, "unsafe_cleanup")
        directories.append(path)
        require(len(directories) <= 64 and not any((path / name).is_symlink() for name in names), "unsafe_cleanup")
        for name in leaves:
            leaf = path / name
            raw = read(leaf, 400_000_000)
            info = leaf.lstat()
            files.append((leaf, info.st_dev, info.st_ino, sha(raw)))
            require(len(files) <= 128, "unsafe_cleanup")
    for leaf, device, inode, expected in files:
        info = leaf.lstat()
        require((info.st_dev, info.st_ino) == (device, inode) and sha(read(leaf, 400_000_000)) == expected, "unsafe_cleanup")
        leaf.unlink()
    for path in reversed(directories):
        path.rmdir()


@dataclass
class Job:
    id: str
    capture: str
    prompt: dict
    age: int | None
    kind: str
    context: str
    directory: Path
    output: Path
    audio_sha: str
    prompt_sha: str
    metrics: dict
    sources: dict
    started: float = field(default_factory=time.monotonic)
    status: str = "processing"
    result: dict | None = None
    process: subprocess.Popen | None = None
    thread: threading.Thread | None = None
    cancel_requested: bool = False
    cancel_at: float | None = None
    outer_collected: bool = False
    outer_absent: bool = False
    unknown_latched: bool = False
    cleanup_confirmed: bool = False
    outer_launch_attempted: bool = False
    outer_launch_failed: bool = False
    inner_worker_count: int | None = None
    inner_collected_count: int | None = None
    inner_cleanup_confirmed: bool | None = None
    input_removed: bool = False
    output_removed: bool = False


class Service:
    def __init__(self, runtime_root, *, guard=None, output_parent=None, command_builder=None,
                 parent_budget=220, cancel_grace=10):
        self.guard = guard or SourceGuard()
        self.guard.check()  # Before allocating runtime or accepting a request.
        self.app = self.guard.app
        self.root = self.guard.root
        self.runtime = safe_path(runtime_root)
        self.output_parent = safe_path(output_parent) if output_parent is not None else None
        if self.output_parent is not None and self.output_parent.exists():
            info = self.output_parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) & 0o022 == 0, "unsafe_output_parent")
        require(not self.runtime.exists() and not self.runtime.is_symlink()
                and not self.runtime.is_relative_to(self.app)
                and not self.runtime.is_relative_to(self.root / "research/audio-head")
                and not self.app.is_relative_to(self.runtime), "fresh_runtime_required")
        require(self.runtime.parent.is_dir(), "runtime_parent_missing")
        catalog = parse(read(self.app / "catalog.json", 2_000_000))
        require(type(catalog) is dict and catalog.get("schemaVersion") == 1 and type(catalog.get("prompts")) is list, "invalid_catalog")
        self.prompts = {row["id"]: row for row in catalog["prompts"]}
        require(1 <= len(self.prompts) == len(catalog["prompts"]) <= 4096, "invalid_catalog")
        for row in self.prompts.values():
            kind = row.get("kind")
            require(kind in ("word", "phrase") and type(row.get("modelSupported")) is bool
                    and row.get("supportedContexts") == (["child-research"] if kind == "phrase" else
                        ["recognition", "child-research"] if row["modelSupported"] else []), "invalid_catalog")
            require(type(row.get("focus")) is str and type(row.get("cue")) is str
                    and type(row.get("prompt")) is dict and row["prompt"].get("schemaVersion") == 2
                    and type(row["prompt"].get("targets")) is list and bool(row["prompt"]["targets"]), "invalid_catalog")
            if kind == "word":
                prompt = row["prompt"]
                require(len(prompt["words"]) == 1 and prompt["transcript"] == prompt["words"][0]["text"]
                        and type(row.get("soundID")) is str and row.get("position") in ("beginning", "middle", "end"), "invalid_catalog")
                phones = prompt["words"][0]["phones"]
                targets = prompt["targets"]
                require(all(t["wordIndex"] == 0 and type(t["phoneIndex"]) is int
                        and 0 <= t["phoneIndex"] < len(phones) and phones[t["phoneIndex"]] == t["targetPhone"]
                        and t["targetPhone"] in (*PHONES, "ZH") for t in targets)
                        and len({t["phoneIndex"] for t in targets}) == len(targets)
                        and row["modelSupported"] is all(t["targetPhone"] in PHONES for t in targets), "invalid_catalog")
        word_rows = [row for row in self.prompts.values() if row["kind"] == "word"]
        self.library = {"wordEntries": len(word_rows),
            "distinctWords": len({row["prompt"]["transcript"] for row in word_rows}),
            "soundGroups": len({row["soundID"] for row in word_rows}),
            "modelSupportedWordEntries": sum(row["modelSupported"] for row in word_rows),
            "practiceOnlyWordEntries": sum(not row["modelSupported"] for row in word_rows)}
        require(catalog.get("library", self.library) == self.library, "invalid_catalog")
        self.runtime.mkdir(mode=0o700)
        self.csrf = secrets.token_urlsafe(32)
        self.jobs, self.captures = {}, set()
        self.current = None
        self.blocked = self.closed = False
        self.lock = threading.RLock()
        self.server_id = str(uuid.uuid4())
        self.command_builder = command_builder or self._command
        self.parent_budget, self.cancel_grace = parent_budget, cancel_grace

    def _command(self, job):
        script = (self.app / "phrase_app/word_cli.py" if job.kind == "word" else
                  self.root / "research/audio-head/local_wav_prototype/phrase_cli.py")
        age_args = ["--recognition-only"] if job.context == "recognition" else ["--age-years", str(job.age)]
        return [str(self.root / self.guard.config["python"]), "-B", str(script),
                "--wav", str(job.directory / "source.wav"), "--prompt-json", str(job.directory / "prompt.json"),
                *age_args, "--output", str(job.output)]

    def catalog(self):
        self.guard.check()
        return {"schemaVersion": 1, "prompts": [
            {"id": row["id"], "transcript": row["prompt"]["transcript"], "focus": row["focus"],
             "cue": row["cue"], "targetCount": len(row["prompt"]["targets"]),
             **{key: row[key] for key in ("kind", "soundID", "position", "modelSupported", "supportedContexts")}}
             for row in self.prompts.values()], "library": dict(self.library),
            "csrfToken": self.csrf, "maximumSeconds": 4, "minimumAge": 6, "maximumAge": 12, "researchOnly": True}

    def validate(self, request):
        require(type(request) is dict and set(request) == {"requestId", "promptId", "context", "ageYears", "consent", "audioBase64"}, "invalid_request")
        capture = identifier(request["requestId"], "invalid_request_id")
        require(type(request["promptId"]) is str and request["promptId"] in self.prompts, "unknown_prompt")
        require(request["context"] in ("recognition", "child-research"), "invalid_context")
        if request["context"] == "recognition":
            require(request["ageYears"] is None, "recognition_age_must_be_null")
        else:
            require(type(request["ageYears"]) is int and 6 <= request["ageYears"] <= 12, "known_child_age_6_to_12_required")
        row = self.prompts[request["promptId"]]
        require(row["modelSupported"], "practice_only_prompt")
        require(request["context"] in row["supportedContexts"], "prompt_context_unsupported")
        require(request["consent"] is True, "consent_required")
        encoded = request["audioBase64"]
        require(type(encoded) is str and len(encoded) <= 4 * ((MAX_WAV + 2) // 3), "invalid_audio_size")
        try:
            raw = base64.b64decode(encoded, validate=True)
            require(base64.b64encode(raw).decode() == encoded, "invalid_audio_encoding")
        except (ValueError, binascii.Error):
            raise SafeError("invalid_audio_encoding") from None
        metrics = validate_wav(raw)
        return capture, row, request["context"], request["ageYears"], raw, metrics

    def submit(self, request):
        capture, row, context, age, raw, metrics = self.validate(request)
        prompt = row["prompt"]
        self.guard.check()
        with self.lock:
            require(not self.closed and not self.blocked, "blocked", 409)
            require(capture not in self.captures, "capture_reused", 409)
            require(self.current is None, "busy", 409)
            require(len(self.jobs) < 256, "session_full", 409)
            # Capture identity also addresses its job: a lost 202 can be
            # recovered with GET, without resubmitting the check.
            job_id = capture
            directory = self.runtime / job_id
            output_parent = self.output_parent or self.root / ("research/audio-head/outputs/local-wav-prototype" if row["kind"] == "word" else "research/audio-head/outputs/local-phrase-prototype")
            safe_path(output_parent)
            if output_parent.exists():
                info = output_parent.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) & 0o022 == 0, "unsafe_output_parent")
            output = output_parent / ("ui-" + self.server_id + "-" + job_id)
            require(not output.exists() and not output.is_symlink(), "fresh_output_required", 409)
            directory.mkdir(mode=0o700)
            try:
                save_bytes(directory / "source.wav", raw)
                prompt_bytes = canonical(prompt) + b"\n"
                save_bytes(directory / "prompt.json", prompt_bytes)
                job = Job(job_id, capture, prompt, age, row["kind"], context, directory, output, sha(raw), sha(prompt_bytes), metrics, dict(self.guard.sources))
            except BaseException:
                cleanup_owned(directory)
                raise
            self.jobs[job_id] = job
            self.captures.add(capture)
            self.current = job
            job.thread = threading.Thread(target=self._run, args=(job,), daemon=True, name="phrase-owned-waiter")
            try:
                job.thread.start()
            except RuntimeError:
                self._settle_without_launch(job)
                raise SafeError("launch_failed", 503) from None
            return {"jobId": job.id, "status": "processing"}

    def _projection(self, job):
        return {"jobId": job.id, "status": job.status, "cleanupConfirmed": job.cleanup_confirmed, "result": job.result}

    def get(self, job_id):
        identifier(job_id, "invalid_job_id")
        self.guard.check()  # Cached results cease to be usable after source drift.
        with self.lock:
            require(job_id in self.jobs, "unknown_job", 404)
            return self._projection(self.jobs[job_id])

    def cancel(self, job_id):
        identifier(job_id, "invalid_job_id")
        with self.lock:
            require(job_id in self.jobs, "unknown_job", 404)
            job = self.jobs[job_id]
            if job.status not in TERMINAL:
                job.cancel_requested = True
                job.cancel_at = job.cancel_at or time.monotonic()
                job.status = "cancelling"
                # Same lock as Popen.wait below. returncode is set only by this
                # wait owner, so the exact leader remains waitable while sent.
                if job.process is not None and not job.outer_collected:
                    try:
                        os.kill(job.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        self._unknown(job)
            return {"jobId": job.id, "status": job.status}

    def _unknown(self, job):
        job.unknown_latched = True
        job.cleanup_confirmed = False
        self.blocked = True
        job.status, job.result = "cleanup_unknown", None
        self._audit(job, cleanup=False)

    def _audit(self, job, *, cleanup):
        # This deliberately contains no age, canonical prompt, filename, token,
        # vector or recognized speech. Unknown ownership retains borrowed trees.
        path = self.runtime / (job.id + ".json")
        value = {"schemaVersion": 1, **self._projection(job), "audioSha256": job.audio_sha,
                 "promptSha256": job.prompt_sha, "captureSha256": sha(job.capture.encode()),
                 "appSourceManifestSha256": self.guard.seal, "cleanupConfirmed": cleanup,
                 "outerLaunchAttempted": job.outer_launch_attempted, "outerLaunchFailed": job.outer_launch_failed,
                 "outerCollected": job.outer_collected, "outerGroupObservedAbsent": job.outer_absent,
                 "innerWorkerCount": job.inner_worker_count, "innerCollectedCount": job.inner_collected_count,
                 "innerCleanupConfirmed": job.inner_cleanup_confirmed,
                 "inputRemoved": job.input_removed, "outputRemoved": job.output_removed}
        if not path.exists():
            try:
                save(path, value)
            except OSError:
                self.blocked = True

    def _failure(self, job):
        return {"kind": "failed", "message": "The check did not produce a usable result.", "phraseMatched": False,
                "soundAnalysisAvailable": False, "scoredOccurrences": 0, "alignmentUnverified": False,
                "alignmentWarningCounts": {}, "elapsedSeconds": round(time.monotonic() - job.started, 3),
                "cleanupConfirmed": True, "researchOnly": True, "learnerFeedbackEligible": False, "clinicalUseEligible": False}

    def _settle_without_launch(self, job):
        # There are no borrowed inputs only when Popen itself failed, or this
        # job was cancelled before Popen. An unexpected output is not ours.
        with self.lock:
            if job.output.exists() or job.output.is_symlink():
                self._unknown(job)
                return
            try:
                cleanup_owned(job.directory)
            except (OSError, SafeError):
                self._unknown(job)
                return
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.cleanup_confirmed = True
            job.input_removed = True
            job.result = None if job.cancel_requested else self._failure(job)
            self.current = None
            self._audit(job, cleanup=True)
            job.prompt, job.age, job.metrics, job.sources = {}, None, {}, {}

    def _run(self, job):
        try:
            with self.lock:
                if job.cancel_requested:
                    self._settle_without_launch(job)
                    return
                self.guard.check()
                require(self.guard.sources == job.sources, "source_changed", 503)
                env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1",
                       "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
                try:
                    job.outer_launch_attempted = True
                    job.process = subprocess.Popen(self.command_builder(job), cwd=self.root, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except OSError:
                    job.outer_launch_failed = True
                    self._settle_without_launch(job)
                    return
            while True:
                with self.lock:
                    try:
                        job.process.wait(timeout=0.05)
                        job.outer_collected = True
                        break
                    except subprocess.TimeoutExpired:
                        now = time.monotonic()
                        if not job.cancel_requested and now - job.started > self.parent_budget:
                            self.cancel(job.id)
                        if job.cancel_at is not None and now - job.cancel_at > self.cancel_grace and not job.unknown_latched:
                            self._unknown(job)
                # Give cancellation a chance to obtain the ownership lock.
                time.sleep(0.01)
            try:
                os.killpg(job.process.pid, 0)
            except ProcessLookupError:
                job.outer_absent = True
            except OSError:
                pass
            if not job.outer_absent or job.unknown_latched:
                with self.lock:
                    self._unknown(job)
                return
            receipt = parse(read(job.output / "receipt.json", 2_000_000, private=True))
            self._validate_receipt_identity(job, receipt)
            self._validate_cleanup(receipt, job)
            job.inner_worker_count = len(receipt["workers"])
            job.inner_collected_count = sum(w["childExitCollected"] is True for w in receipt["workers"])
            job.inner_cleanup_confirmed = True
            # Binding/source failures suppress results but do not make an
            # independently confirmed cleanup unknown.
            try:
                result = self._accept(job, receipt)
            except (OSError, KeyError, TypeError, ValueError, RecursionError):
                result = self._failure(job)
            with self.lock:
                if job.unknown_latched:
                    return
                # Borrowed input and private CLI artifacts can finally go.
                cleanup_owned(job.output)
                job.output_removed = True
                cleanup_owned(job.directory)
                job.input_removed = True
                job.cleanup_confirmed = True
                job.status = "cancelled" if job.cancel_requested else ("failed" if result["kind"] == "failed" else "complete")
                job.result = None if job.cancel_requested else result
                self.current = None
                self._audit(job, cleanup=True)
                job.prompt, job.age, job.metrics, job.sources = {}, None, {}, {}
        except (OSError, KeyError, TypeError, ValueError, RuntimeError, RecursionError):
            with self.lock:
                if job.process is None:
                    self._settle_without_launch(job)
                else:
                    self._unknown(job)

    def _validate_cleanup(self, receipt, job):
        require(type(receipt) is dict, "inner_cleanup_unknown")
        require(receipt.get("cleanupConfirmed") is True and receipt.get("status") != "cleanup_unknown", "inner_cleanup_unknown")
        if job.kind == "word":
            self._validate_word_cleanup(job, receipt)
            return
        states, workers = receipt["workerLaunchStates"], receipt["workers"]
        require(type(states) is dict and set(states) == {"word", "shared"} and type(workers) is list, "inner_cleanup_unknown")
        attempted = [states[name] for name in ("word", "shared") if states[name] != "not_attempted"]
        require(len(attempted) == len(workers) and all(s in ("launched", "launch_failed") for s in attempted), "inner_cleanup_unknown")
        require(states["word"] != "not_attempted" or states["shared"] == "not_attempted", "inner_cleanup_unknown")
        for state, worker in zip(attempted, workers, strict=True):
            require(type(worker) is dict and worker.get("cleanupConfirmed") is True, "inner_cleanup_unknown")
            if state == "launch_failed":
                require(worker.get("launchFailed") is True and worker.get("pid") is None
                        and worker.get("workerExitCode") is None and worker.get("childExitCollected") is False, "inner_cleanup_unknown")
            else:
                require(type(worker.get("pid")) is int and worker["pid"] > 0
                        and worker.get("childExitCollected") is True and type(worker.get("workerExitCode")) is int
                        and type(worker.get("timedOut")) is bool and type(worker.get("cancelled")) is bool, "inner_cleanup_unknown")

    def _validate_receipt_identity(self, job, receipt):
        # Cleanup must come from this borrowed job, not a stale safe receipt.
        if job.kind == "word":
            self._validate_word_identity(job, receipt)
            return
        require(type(receipt) is dict and receipt.get("schemaVersion") == 1 and receipt.get("mode") == "phrase-v1"
                and receipt.get("audioSHA256") == job.audio_sha and type(receipt.get("ageYears")) is int
                and receipt["ageYears"] == job.age, "inner_cleanup_unknown")
        request = parse(read(job.output / "request.json", 512_000, private=True))
        require(type(request) is dict and request.get("mode") == "phrase-v1" and request.get("prompt") == job.prompt
                and type(request.get("ageYears")) is int and request["ageYears"] == job.age
                and request.get("originalAudioSHA256") == job.audio_sha and request.get("sources") == job.sources,
                "inner_cleanup_unknown")

    def _accept(self, job, receipt):
        if job.kind == "word":
            return self._accept_word(job, receipt)
        self.guard.check()
        require(self.guard.sources == job.sources, "result_binding_failed")
        require(receipt["schemaVersion"] == 1 and receipt["mode"] == "phrase-v1"
                and receipt["audioSHA256"] == job.audio_sha and type(receipt["ageYears"]) is int and receipt["ageYears"] == job.age
                and receipt["originalAudioUnchanged"] is True and receipt["sourcesUnchanged"] is True
                and receipt["researchOnly"] is True and receipt["learnerFeedbackEligible"] is False
                and receipt["clinicalUseEligible"] is False and receipt["requestedPhraseVerified"] is False, "result_binding_failed")
        require(sha(read(job.directory / "source.wav", MAX_WAV, private=True)) == job.audio_sha
                and sha(read(job.directory / "prompt.json", 512_000, private=True)) == job.prompt_sha, "result_binding_failed")
        request = parse(read(job.output / "request.json", 512_000, private=True))
        require(request["schemaVersion"] == 1 and request["mode"] == "phrase-v1" and request["prompt"] == job.prompt
                and type(request["ageYears"]) is int and request["ageYears"] == job.age
                and request["originalAudioSHA256"] == job.audio_sha and request["sources"] == job.sources
                and request["inputMetrics"] == job.metrics and request["context"] == "known-child-age"
                and request["researchOnly"] is True and request["learnerFeedbackEligible"] is False
                and request["clinicalUseEligible"] is False, "result_binding_failed")
        require(receipt["wordPolicySHA256"] == self.guard.config["wordPolicySha256"]
                and receipt["modelManifestSHA256"] == self.guard.config["wordModelManifest"]["sha256"], "result_binding_failed")
        status, reason = receipt["status"], receipt["reason"]
        require(status in ("abstain", "research_scores", "failed"), "result_binding_failed")
        decision = receipt["phraseAdmission"]
        matched = False
        if decision is not None:
            require(type(decision) is dict and decision["decisionSHA256"] == sha(canonical({k: v for k, v in decision.items() if k != "decisionSHA256"}))
                    and decision["baseWordPolicySHA256"] == self.guard.config["wordPolicySha256"]
                    and decision["method"] == "independent-asr-exact-phrase"
                    and decision["baseWordDecision"] == receipt["wordAdmission"]
                    and decision["evidenceSHA256"] == receipt["recognitionEvidenceSHA256"]
                    and decision["baseWordDecision"]["expectedWordSha256"] == sha(canonical(job.prompt["transcript"]))
                    and decision["requestedPhraseVerified"] is False and decision["recognitionRejectionIsArticulationError"] is False
                    and type(decision["admitted"]) is bool, "result_binding_failed")
            matched = decision["admitted"]
        states = receipt["workerLaunchStates"]
        if status != "failed":
            require(job.process.returncode == 0 and all(w.get("workerExitCode") == 0 and not w.get("timedOut")
                    and not w.get("cancelled") for w in receipt["workers"]), "result_binding_failed")
        performed = receipt["sharedPredictionPerformed"]
        require(type(performed) is bool, "result_binding_failed")
        targets, warning_counts, scored = receipt["targets"], {}, 0
        if states["shared"] == "not_attempted":
            require(performed is False and targets == [], "result_binding_failed")
        elif status != "failed":
            require(matched and states == {"word": "launched", "shared": "launched"}, "result_binding_failed")
            shared_raw = read(job.output / "shared-result.json", 2_000_000, private=True)
            shared = parse(shared_raw)
            expected_shared_job = {"schemaVersion": 1, "audio": str(job.output / "temporary/source.wav"),
                "audioSha256": job.audio_sha, "ageYears": job.age, "prompt": job.prompt,
                "supportedPhones": list(PHONES), "sources": job.sources,
                "wordAdmissionEvidenceSHA256": receipt["recognitionEvidenceSHA256"], "kind": "phrase-v1", "phraseAdmission": decision}
            require(sha(shared_raw) == receipt["sharedResultSHA256"] and shared["audioSha256"] == job.audio_sha
                    and shared["jobSha256"] == sha(canonical(expected_shared_job) + b"\n")
                    and shared["mode"] == "phrase-v1" and shared["phraseAdmissionEvidenceSHA256"] == receipt["recognitionEvidenceSHA256"]
                    and shared["targets"] == targets and shared["sharedPredictionPerformed"] is performed
                    and shared["status"] == status and shared["modelManifestSHA256"] == self.guard.config["sharedManifest"]["sha256"], "result_binding_failed")
            keys = ("id", "wordIndex", "phoneIndex", "targetPhone")
            require([[t[k] for k in keys] for t in targets] == [[t[k] for k in keys] for t in job.prompt["targets"]], "result_binding_failed")
            if performed:
                require(status == "research_scores" and sha(read(job.output / "features.npy", 400_000_000, private=True)) == shared["featureSHA256"], "result_binding_failed")
                for target in targets:
                    flags = target["diagnosticFlags"]
                    require(type(flags) is list and len(flags) == len(set(flags)) and set(flags) <= FLAGS.keys()
                            and "unverified-forced-canonical-location" in flags, "result_binding_failed")
                    probabilities = target["subjectiveCorpusRatingProbabilities"]
                    require(type(probabilities) is list and len(probabilities) == 3
                            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in probabilities)
                            and abs(sum(probabilities) - 1) < 0.001, "result_binding_failed")
                    scored += 1
                    for flag in flags:
                        tag = FLAGS[flag]
                        warning_counts[tag] = warning_counts.get(tag, 0) + 1
            else:
                require(all(t.get("subjectiveCorpusRatingProbabilities") is None for t in targets), "result_binding_failed")
        if status == "failed":
            return self._failure(job)
        if performed:
            kind, message = "uncertain", "The recognizer matched the phrase. Research sound estimates were computed at unverified sound locations, so they cannot judge pronunciation."
        elif reason == "requested_phrase_not_matched":
            require(not matched and states["shared"] == "not_attempted", "result_binding_failed")
            kind, message = "phrase_mismatch", "The recognizer did not match the whole phrase. This does not identify a pronunciation error."
        elif reason in ("silence", "speech_not_detected"):
            require(not matched and states["shared"] == "not_attempted", "result_binding_failed")
            kind, message = "silence", "The recording did not pass the speech evidence rule. No sound estimates were computed."
        elif reason == "clipping":
            require(not matched and states["shared"] == "not_attempted", "result_binding_failed")
            kind, message = "clipping", "The recording clipped. No sound estimates were computed."
        elif reason == "phone_evidence_missing":
            require(matched and states["shared"] == "launched", "result_binding_failed")
            kind, message = "phone_evidence_missing", "The phrase matched, but there was insufficient sound evidence. No sound estimates were computed."
        else:
            kind, message = "uncertain", "There was insufficient evidence for this attempt. Compare your recordings by listening."
        elapsed = receipt["elapsedSeconds"]
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed < 86_400, "result_binding_failed")
        self.guard.check()
        return {"kind": kind, "message": message, "phraseMatched": matched, "soundAnalysisAvailable": False,
                "scoredOccurrences": scored, "alignmentUnverified": performed, "alignmentWarningCounts": warning_counts,
                "elapsedSeconds": round(elapsed, 3), "cleanupConfirmed": True, "researchOnly": True,
                "learnerFeedbackEligible": False, "clinicalUseEligible": False}

    def _validate_word_identity(self, job, receipt):
        age_matches = lambda value: value is None if job.age is None else type(value) is int and value == job.age
        require(type(receipt) is dict and type(receipt.get("schemaVersion")) is int
                and receipt["schemaVersion"] == 1 and "mode" not in receipt and "workerLaunchStates" not in receipt
                and receipt.get("audioSHA256") == job.audio_sha and age_matches(receipt.get("ageYears"))
                and "ageYears" in receipt, "inner_cleanup_unknown")
        request = parse(read(job.output / "request.json", 512_000, private=True))
        require(type(request) is dict and type(request.get("schemaVersion")) is int
                and request["schemaVersion"] == 1 and "mode" not in request and request.get("prompt") == job.prompt
                and "ageYears" in request and age_matches(request["ageYears"])
                and request.get("context") == ("known-child-age" if job.age is not None else "recognition-only-age-unknown-or-adult")
                and request.get("originalAudioSHA256") == job.audio_sha and request.get("sources") == job.sources,
                "inner_cleanup_unknown")

    def _validate_word_cleanup(self, job, receipt):
        workers = receipt.get("workers")
        require(type(workers) is list and len(workers) <= (1 if job.context == "recognition" else 2), "inner_cleanup_unknown")
        phase = receipt.get("phase")
        decision = receipt.get("wordAdmission")
        if not workers:
            require(receipt.get("recognition") is None and decision is None
                    and receipt.get("sharedPredictionPerformed") is False and receipt.get("targets") == []
                    and "sharedResultSHA256" not in receipt
                    and phase in ("private_setup", "word_model_readiness")
                    and (receipt.get("status") == "failed" or
                         (phase == "private_setup" and receipt.get("status") == "abstain"
                          and receipt.get("reason") in ("silence", "clipping"))), "inner_cleanup_unknown")
        elif len(workers) == 1:
            require(phase in ("word_inference", "word_admission")
                    and (receipt.get("status") == "failed" or phase == "word_admission")
                    and receipt.get("sharedPredictionPerformed") is False and receipt.get("targets") == []
                    and "sharedResultSHA256" not in receipt, "inner_cleanup_unknown")
        else:
            require(job.context == "child-research" and phase == "shared_inference"
                    and type(decision) is dict and decision.get("admitted") is True
                    and workers[0].get("workerExitCode") == 0 and workers[0].get("childExitCollected") is True
                    and workers[0].get("timedOut") is False and workers[0].get("cancelled") is False
                    and workers[0].get("launchFailed", False) is False, "inner_cleanup_unknown")
        for worker in workers:
            require(type(worker) is dict and worker.get("cleanupConfirmed") is True, "inner_cleanup_unknown")
            if worker.get("launchFailed") is True:
                require(worker.get("pid") is None and worker.get("workerExitCode") is None
                        and worker.get("childExitCollected") is False
                        and receipt.get("status") == "failed", "inner_cleanup_unknown")
            else:
                require(worker.get("launchFailed", False) is False and type(worker.get("pid")) is int and worker["pid"] > 0
                        and worker.get("childExitCollected") is True and type(worker.get("workerExitCode")) is int
                        and type(worker.get("timedOut")) is bool and type(worker.get("cancelled")) is bool, "inner_cleanup_unknown")

    def _accept_word(self, job, receipt):
        self.guard.check()
        require(self.guard.sources == job.sources and receipt.get("originalAudioUnchanged") is True
                and receipt.get("sourcesUnchanged") is True and receipt.get("researchOnly") is True
                and receipt.get("learnerFeedbackEligible") is False and receipt.get("clinicalUseEligible") is False
                and receipt.get("requestedWordVerified") is False, "result_binding_failed")
        require(sha(read(job.directory / "source.wav", MAX_WAV, private=True)) == job.audio_sha
                and sha(read(job.directory / "prompt.json", 512_000, private=True)) == job.prompt_sha, "result_binding_failed")
        request = parse(read(job.output / "request.json", 512_000, private=True))
        require(request.get("inputMetrics") == job.metrics and request.get("researchOnly") is True
                and request.get("learnerFeedbackEligible") is False and request.get("clinicalUseEligible") is False
                and request.get("requestedWordVerified") is False, "result_binding_failed")
        require(receipt.get("wordPolicySHA256") == self.guard.config["wordPolicySha256"]
                and receipt.get("modelManifestSHA256") == self.guard.config["wordModelManifest"]["sha256"], "result_binding_failed")
        status, reason = receipt["status"], receipt["reason"]
        require(status in ("abstain", "recognition_only", "research_scores", "failed"), "result_binding_failed")
        decision = receipt.get("wordAdmission")
        matched = False
        if decision is not None:
            require(type(decision) is dict and set(decision) == {"admitted", "reason", "expectedWordSha256", "evidenceSha256",
                    "policySha256", "method", "requestedWordVerified", "recognitionRejectionIsArticulationError"}
                    and decision["method"] == "independent-asr-single-word"
                    and decision["policySha256"] == self.guard.config["wordPolicySha256"]
                    and decision["expectedWordSha256"] == sha(canonical(job.prompt["transcript"]))
                    and type(decision["evidenceSha256"]) is str and len(decision["evidenceSha256"]) == 64
                    and all(c in "0123456789abcdef" for c in decision["evidenceSha256"])
                    and decision["evidenceSha256"] == receipt.get("recognitionEvidenceSHA256")
                    and decision["requestedWordVerified"] is False and decision["recognitionRejectionIsArticulationError"] is False
                    and type(decision["admitted"]) is bool and len(receipt["workers"]) >= 1, "result_binding_failed")
            matched = decision["admitted"]
            require(decision["reason"] is None if matched else type(decision["reason"]) is str, "result_binding_failed")
        workers = receipt["workers"]
        if status != "failed":
            require(job.process.returncode == 0 and all(w.get("workerExitCode") == 0
                    and w.get("timedOut") is False and w.get("cancelled") is False for w in workers), "result_binding_failed")
        performed = receipt["sharedPredictionPerformed"]
        targets, warning_counts, scored = receipt["targets"], {}, 0
        require(type(performed) is bool and type(targets) is list, "result_binding_failed")
        if len(workers) < 2:
            require(performed is False and targets == [], "result_binding_failed")
        elif status != "failed":
            require(job.context == "child-research" and matched, "result_binding_failed")
            shared_raw = read(job.output / "shared-result.json", 2_000_000, private=True)
            shared = parse(shared_raw)
            expected_job = {"schemaVersion": 1, "audio": str(job.output / "temporary/source.wav"),
                "audioSha256": job.audio_sha, "ageYears": job.age, "prompt": job.prompt,
                "supportedPhones": list(PHONES), "sources": job.sources,
                "wordAdmissionEvidenceSHA256": receipt["recognitionEvidenceSHA256"]}
            require(sha(shared_raw) == receipt.get("sharedResultSHA256") and shared["audioSha256"] == job.audio_sha
                    and shared["jobSha256"] == sha(canonical(expected_job) + b"\n")
                    and "mode" not in shared and shared["targets"] == targets and shared["sharedPredictionPerformed"] is performed
                    and shared["status"] == status and shared["modelManifestSHA256"] == self.guard.config["sharedManifest"]["sha256"], "result_binding_failed")
            keys = ("id", "wordIndex", "phoneIndex", "targetPhone")
            require([[t[k] for k in keys] for t in targets] == [[t[k] for k in keys] for t in job.prompt["targets"]], "result_binding_failed")
            if performed:
                require(status == "research_scores" and sha(read(job.output / "features.npy", 400_000_000, private=True)) == shared["featureSHA256"], "result_binding_failed")
                for target in targets:
                    flags, probabilities = target["diagnosticFlags"], target["subjectiveCorpusRatingProbabilities"]
                    require(type(flags) is list and len(flags) == len(set(flags)) and set(flags) <= FLAGS.keys()
                            and "unverified-forced-canonical-location" in flags
                            and type(probabilities) is list and len(probabilities) == 3
                            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in probabilities)
                            and abs(sum(probabilities) - 1) < .001, "result_binding_failed")
                    scored += 1
                    for flag in flags:
                        tag = FLAGS[flag]
                        warning_counts[tag] = warning_counts.get(tag, 0) + 1
            else:
                require(all(t.get("subjectiveCorpusRatingProbabilities") is None for t in targets), "result_binding_failed")
        if status == "failed":
            return self._failure(job)
        if job.context == "recognition" and matched:
            require(status == "recognition_only" and reason == "known_child_age_required_for_shared_scores"
                    and len(workers) == 1, "result_binding_failed")
            kind, message = "recognized", "The recognizer matched the practice word. This is recognition evidence only; it does not judge pronunciation."
        elif performed:
            kind, message = "uncertain", "The recognizer matched the word. Research sound estimates were computed at unverified sound locations, so they cannot judge pronunciation."
        elif reason == "requested_word_not_matched":
            require(not matched and len(workers) == 1 and decision["reason"] == reason, "result_binding_failed")
            kind, message = "word_mismatch", "The recognizer did not match the practice word. This does not identify a pronunciation error."
        elif reason in ("silence", "speech_not_detected", "clipping"):
            require(not matched and len(workers) <= 1 and status == "abstain", "result_binding_failed")
            kind = "clipping" if reason == "clipping" else "silence"
            message = "The recording clipped. No sound estimates were computed." if kind == "clipping" else "The recording did not pass the speech evidence rule. No sound estimates were computed."
        elif reason == "phone_evidence_missing":
            require(matched and len(workers) == 2 and status == "abstain", "result_binding_failed")
            kind, message = "phone_evidence_missing", "The word matched, but there was insufficient sound evidence. No sound estimates were computed."
        else:
            require(not matched and len(workers) <= 1 and status == "abstain"
                    and decision is not None and decision["reason"] == reason, "result_binding_failed")
            kind, message = "uncertain", "There was insufficient evidence for this attempt. Compare your recordings by listening."
        elapsed = receipt["elapsedSeconds"]
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed < 86_400, "result_binding_failed")
        self.guard.check()
        return {"kind": kind, "message": message, "phraseMatched": matched, "soundAnalysisAvailable": False,
                "scoredOccurrences": scored, "alignmentUnverified": performed, "alignmentWarningCounts": warning_counts,
                "elapsedSeconds": round(elapsed, 3), "cleanupConfirmed": True, "researchOnly": True,
                "learnerFeedbackEligible": False, "clinicalUseEligible": False}

    def stop(self, grace=10):
        with self.lock:
            self.closed = True
            job = self.current
            if job is not None:
                self.cancel(job.id)
        if job is not None and job.thread is not None:
            job.thread.join(timeout=grace)
            if job.thread.is_alive():
                with self.lock:
                    self._unknown(job)
