"""Real decoder/Vision smoke on generated non-human video; no speech evidence.
Requires an existing ffmpeg and a previously built visual-speech executable.
Writes generated test artifacts only to the explicitly supplied output directory.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

package = pathlib.Path(__file__).resolve().parent
out = pathlib.Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
clip = out / "generated-black.mov"
features = out / "no-face.ndjson"
if clip.exists() or features.exists():
    raise SystemExit("Choose a new smoke output directory; existing evidence is not overwritten")
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=black:s=320x240:r=30:d=1", "-an", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", str(clip)], check=True)
binary = package / ".build/debug/visual-speech"
base = [str(binary), "--input", str(clip), "--output", str(features),
        "--provenance", str(package / "fixtures/no-face-provenance.json"),
        "--audio-timebase", str(package / "fixtures/no-face-timebase.json")]
run = subprocess.run(base, capture_output=True, text=True, check=True)
records = [json.loads(line) for line in features.read_text().splitlines()]
header, summary = records[0], records[-1]
frames = records[1:-1]
assert header["sourceSHA256"] == hashlib.sha256(clip.read_bytes()).hexdigest()
assert header["depth"] is None and header["audioAlignmentVerified"] is False
assert header["provenance"]["ageDomain"] == "unknown"
assert summary == {"type": "summary", "decodedFrames": 30, "sampledFrames": 10,
                   "geometryFrames": 0, "processingFailures": 0, "complete": True}
assert len(frames) == 10
for i, frame in enumerate(frames):
    assert frame["status"] == "no-face" and frame["faceCount"] == 0
    for missing in ["features", "depth", "teeth", "tongue", "speechCorrectness", "motionBlur", "mouthOcclusion"]:
        assert frame[missing] is None
    assert abs(frame["videoPTSSeconds"] - i / 10) < 1e-8
    assert abs(frame["audioTimeSeconds"] - (i / 10 - 0.1)) < 1e-8
assert frames[0]["audioSampleIndex"] is None
assert frames[1]["audioSampleIndex"] == 0
# Existing artifacts must survive rejected runs byte-for-byte.
before = features.read_bytes()
assert subprocess.run(base, capture_output=True).returncode != 0
assert features.read_bytes() == before
bad = out / "invalid.mov"
bad.write_bytes(b"not a media file")
failed_output = out / "must-not-exist.ndjson"
bad_args = base.copy()
bad_args[2] = str(bad)
bad_args[4] = str(failed_output)
assert subprocess.run(bad_args, capture_output=True).returncode != 0
assert not failed_output.exists()
missing_clock = base[:-2]
missing_clock[4] = str(failed_output)
assert subprocess.run(missing_clock, capture_output=True).returncode != 0
assert not failed_output.exists()
anamorphic = out / "generated-anamorphic.mov"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=black:s=320x240:r=30:d=1", "-vf", "setsar=4/3", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(anamorphic)], check=True)
anamorphic_args = bad_args.copy()
anamorphic_args[2] = str(anamorphic)
rejected_aspect = subprocess.run(anamorphic_args, capture_output=True, text=True)
assert rejected_aspect.returncode != 0 and "Non-square" in rejected_aspect.stderr
assert not failed_output.exists()
assert not list(out.glob(".visual-speech-*.tmp"))
report = {"status": "passed", "fixture": "generated solid black; no person, audio, or depth",
          "checks": ["real video decoding", "real Vision no-face path", "30-to-10 FPS sampling",
                     "signed declared audio timebase", "null unmeasured modalities", "source SHA256",
                     "existing output preservation", "corrupt media rejection", "missing clock rejection",
                     "real anamorphic movie rejection"],
          "summary": summary, "stdout": run.stdout.strip()}
(out / "smoke-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
