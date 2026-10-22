"""Fixed local sources and model bytes; no discovery or acquisition."""
from pathlib import Path
from common import HEAD, HERE, ROOT, digest, parse, read, require, sha


def configuration():
    return parse(read(HERE / "pins.json", 64000))


def guard(pins):
    for path, expected in pins.items():
        require(digest(Path(path)) == expected, "source_or_model_changed")


def source_bindings(config):
    pins = {str(ROOT / name): value for name, value in config["sources"].items()}
    for name in ("rawContract", "occurrenceContract"):
        pin = config[name]
        pins[str(ROOT / pin["path"])] = pin["sha256"]
    guard(pins)
    raw = parse(read(ROOT / config["rawContract"]["path"], 100000))
    # Preserve the frozen package paths, including pre-existing package symlinks.
    pins.update({str(HEAD / name): value for name, value in raw["dependencySha256"].items()})
    for name in ("__init__.py", "common.py", "bindings.py", "cli.py", "worker.py", "pins.json",
                 "phrase_admission.py", "phrase_cli.py"):
        pins[str(HERE / name)] = digest(HERE / name)
    guard(pins)
    return pins


def model_bindings(config, *, shared):
    key = "sharedManifest" if shared else "wordModelManifest"
    pin = config[key]
    path = ROOT / pin["path"]
    payload = read(path, 100000)
    require(sha(payload) == pin["sha256"], "model_manifest_changed")
    manifest = parse(payload)
    pins = {str(path): pin["sha256"]}
    if shared:
        require(set(manifest["files"]) == {"scalar.pt", "compact.pt", "projection.pt", "provenance.json"}, "shared_file_set")
        pins.update({str(path.parent / name): value for name, value in manifest["files"].items()})
        raw = parse(read(ROOT / config["rawContract"]["path"], 100000))
        pins.update({str(ROOT / config["phoneticSnapshot"] / name): value
                     for name, value in raw["phoneticCheckpoint"]["artifactSha256"].items()})
    else:
        for row in manifest["files"]:
            name = Path(row["relativePath"])
            require(not name.is_absolute() and ".." not in name.parts, "model_member_path")
            pins[str(path.parent / name)] = row["sha256"]
    guard(pins)
    return pins
