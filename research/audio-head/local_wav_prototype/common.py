"""Small stdlib boundary shared by the CLI, worker and generated tests."""
from contextlib import contextmanager
import array
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import wave

HERE = Path(__file__).resolve().parent
HEAD = HERE.parent
ROOT = HEAD.parents[1]
PHONES = ("B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z", "SH", "CH",
          "JH", "L", "R", "W", "Y", "HH", "TH", "DH", "NG")
VOWELS = frozenset("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())
MAX_WAV = 132096
SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
FORBIDDEN_INPUT_ROOTS = (HEAD / "outputs/percept-r-source",
                         HEAD / "outputs/r-confirmatory-execution-20261011-v1")


class Refused(ValueError):
    """A safe fixed error tag, suitable for the terminal receipt."""


def require(value, tag):
    if not value:
        raise Refused(tag)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def parse(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def bad_number(_):
        raise Refused("nonfinite_json")

    def number(text):
        value = float(text)
        require(math.isfinite(value), "nonfinite_json")
        return value

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_number, parse_float=number)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise Refused("invalid_json") from None


def regular(path, *, private=False):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve()
            and not any(p.is_symlink() for p in (path, *path.parents)), "unsafe_path")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid(), "unsafe_file")
    require(not private or stat.S_IMODE(info.st_mode) == 0o600, "private_file_mode")
    return info


def read(path, maximum, *, private=False):
    before = regular(path, private=private)
    require(before.st_size <= maximum, "file_too_large")
    with Path(path).open("rb") as stream:
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(data) == before.st_size and fields(before) == fields(after) == fields(Path(path).stat()), "file_changed")
    return data


def digest(path):
    # Only fixed source/model bindings use this function. Their frozen package
    # and HuggingFace cache paths may be symlinks; verify exact bytes each time.
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    payload = canonical(value) + b"\n"
    with Path(path).open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path), "sha256": sha(payload)}


def failure_details(error, phase):
    """Keep diagnostic locations without transcript-bearing messages or locals."""
    frames = []
    current = error.__traceback__
    while current is not None:
        code = current.tb_frame.f_code
        path = Path(code.co_filename)
        location = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
        frames.append({"file": location, "function": code.co_name, "line": current.tb_lineno})
        current = current.tb_next
    return {"phase": phase, "exceptionType": type(error).__name__, "frames": frames,
            "reason": str(error) if isinstance(error, Refused) else "execution_failed",
            "errno": error.errno if isinstance(error, OSError) else None,
            "exceptionMessagesAndLocalsRetained": False}


def validate_wav(data):
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
        raise Refused("malformed_wav") from None
    samples = array.array("h", pcm)
    import sys
    if sys.byteorder != "little":
        samples.byteswap()
    return {"sampleCount": count, "durationMilliseconds": count / 16,
            "rms": math.sqrt(sum((s / 32768) ** 2 for s in samples) / count),
            "peak": max(abs(s / 32768) for s in samples),
            "railSamples": sum(s in (-32768, 32767) for s in samples)}


def validate_prompt(prompt):
    require(type(prompt) is dict and set(prompt) == {"schemaVersion", "language", "transcript", "words", "targets"}
            and type(prompt["schemaVersion"]) is int and prompt["schemaVersion"] == 2
            and prompt["language"] == "en", "invalid_prompt_schema")
    require(type(prompt["words"]) is list and len(prompt["words"]) == 1, "single_word_required")
    word = prompt["words"][0]
    require(type(word) is dict and set(word) == {"text", "phones"}
            and type(word["text"]) is str and re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)*", word["text"])
            and len(word["text"]) <= 64 and prompt["transcript"] == word["text"], "invalid_expected_word")
    require(type(word["phones"]) is list and 1 <= len(word["phones"]) <= 512, "invalid_canonical_phones")
    for phone in word["phones"]:
        require(type(phone) is str and (phone in (*PHONES, "ZH")
                or re.fullmatch(r"(?:" + "|".join(VOWELS) + r")[012]?", phone)), "invalid_canonical_phone")
    require(type(prompt["targets"]) is list and 1 <= len(prompt["targets"]) <= 512, "invalid_targets")
    ids, positions = set(), set()
    for target in prompt["targets"]:
        require(type(target) is dict and set(target) == {"id", "wordIndex", "phoneIndex", "targetPhone"}, "invalid_target")
        require(type(target["id"]) is str and 1 <= len(target["id"]) <= 128
                and target["id"].isprintable() and target["id"] not in ids, "duplicate_or_invalid_target_id")
        require(type(target["wordIndex"]) is int and target["wordIndex"] == 0
                and type(target["phoneIndex"]) is int and 0 <= target["phoneIndex"] < len(word["phones"])
                and target["phoneIndex"] not in positions, "duplicate_or_invalid_target_position")
        require(target["targetPhone"] in PHONES, "unsupported_target")
        require(word["phones"][target["phoneIndex"]] == target["targetPhone"], "target_position_mismatch")
        ids.add(target["id"])
        positions.add(target["phoneIndex"])
    return prompt


def validate_age(age):
    require(age is None or (type(age) is int and 6 <= age <= 12), "known_child_age_6_to_12_required")


def allowed_input(path):
    resolved = Path(path).resolve()
    require(not any(resolved.is_relative_to(root) for root in FORBIDDEN_INPUT_ROOTS), "reserved_input_refused")


@contextmanager
def interruption_flag():
    stopped = {"requested": False}
    previous = {sig: signal.getsignal(sig) for sig in SIGNALS}
    def stop(_signum, _frame):
        stopped["requested"] = True
    try:
        for sig in SIGNALS:
            signal.signal(sig, stop)
        yield stopped
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def supervise(argv, *, cwd, env, stdin, timeout, stopped):
    """No output pipes; an uncollected leader retains its process identity.

    The only group kill occurs while our exact leader is still waitable. After a
    collected leader, a surviving group is UNKNOWN and is never signalled.
    """
    start = time.monotonic()
    try:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
    except OSError as error:
        return {"pid": None, "workerExitCode": None, "childExitCollected": False,
                "launchFailed": True, "launchError": failure_details(error, "worker_launch"),
                "timedOut": False, "cancelled": stopped["requested"], "groupKillSent": False,
                "cleanupConfirmed": True, "reason": "worker_launch_failed",
                "elapsedSeconds": time.monotonic() - start}
    timed_out = killed = False
    while True:
        remaining = timeout - (time.monotonic() - start)
        if stopped["requested"] or remaining <= 0:
            timed_out = remaining <= 0
            # No poll/wait has collected this leader. Even an exited zombie
            # reserves its PID, so this group cannot belong to a reused leader.
            try:
                os.killpg(child.pid, signal.SIGKILL)
                killed = True
            except ProcessLookupError:
                pass
            except PermissionError:
                return {"cleanupConfirmed": False, "reason": "group_signal_denied", "pid": child.pid,
                        "workerExitCode": None, "timedOut": timed_out, "cancelled": stopped["requested"]}
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return {"cleanupConfirmed": False, "reason": "child_exit_unconfirmed", "pid": child.pid,
                        "workerExitCode": None, "timedOut": timed_out, "cancelled": stopped["requested"]}
            break
        try:
            child.wait(timeout=min(0.05, remaining))
            break
        except subprocess.TimeoutExpired:
            pass
    reason = None
    try:
        os.killpg(child.pid, 0)
        reason = "group_survives_collected_leader"
    except ProcessLookupError:
        pass
    except PermissionError:
        reason = "group_absence_unconfirmed"
    return {"pid": child.pid, "workerExitCode": child.returncode, "childExitCollected": True,
            "timedOut": timed_out, "cancelled": stopped["requested"], "groupKillSent": killed,
            "cleanupConfirmed": reason is None, "reason": reason,
            "elapsedSeconds": time.monotonic() - start}


def cleanup(scratch):
    """Delete only this fresh owned temporary tree, after supervisor confirmation.

    Verify the entire bounded tree before deleting any file. Refuse symlinks,
    hardlinks and special files. Model-cache staging lives inside this same tree.
    """
    files, directories = [], []
    for directory, names, leaves in os.walk(scratch, followlinks=False):
        path = Path(directory)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and not path.is_symlink() and len(path.relative_to(scratch).parts) <= 8, "unsafe_cleanup_directory")
        directories.append(path)
        require(len(directories) <= 64, "cleanup_directory_bound")
        for name in names:
            require(not (path / name).is_symlink(), "cleanup_link")
        for name in leaves:
            leaf = path / name
            info = regular(leaf)
            require(info.st_size <= 400_000_000, "cleanup_file_bound")
            files.append((leaf, info, digest(leaf)))
            require(len(files) <= 128, "cleanup_inventory_bound")
    inventory = []
    for path, before, expected in files:
        now = regular(path)
        require((before.st_dev, before.st_ino) == (now.st_dev, now.st_ino)
                and digest(path) == expected, "cleanup_file_changed")
        path.unlink()
        inventory.append({"path": str(path.relative_to(scratch)), "bytes": before.st_size,
                          "sha256": expected, "removed": not path.exists()})
    for directory in reversed(directories):
        directory.rmdir()
    return inventory
