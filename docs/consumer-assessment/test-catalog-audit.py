#!/usr/bin/env python3
"""Exercise actual compiled catalog, deterministic output and fail-closed drift guards."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work/assessment-milestone-20261002/materials"
LIBRARY = ROOT / "apps/ios-learner/Sources/DirectPractice/PracticeLibrary.swift"
VOCABULARY = ROOT / "apps/ios-learner/Sources/DirectPractice/PracticeVocabulary.swift"
HELPER = ROOT / "docs/consumer-assessment/catalog-audit.swift"
REPORT = ROOT / "docs/consumer-assessment/catalog-coverage.json"


def command(args):
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    return result


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def mutation(name, source, old, new, expected):
    check(source.count(old) == 1, f"Mutation fixture drift: {name}")
    destination = WORK / f"{name}.swift"
    destination.write_text(source.replace(old, new))
    binary = WORK / f"{name}-audit"
    compiled = command(["swiftc", str(LIBRARY), str(destination), str(HELPER), "-o", str(binary)])
    check(compiled.returncode == 0, f"Compile failed: {name}: {compiled.stderr}")
    attempted = command([str(binary), str(ROOT), str(WORK / f"{name}-output")])
    check(attempted.returncode != 0 and expected in attempted.stderr,
          f"Guard failed: {name}: {attempted.stdout} {attempted.stderr}")
    return {"name": name, "status": "pass", "expectedFailure": expected}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [LIBRARY, VOCABULARY]}
    results = []
    first = command([str(ROOT / "docs/consumer-assessment/run-catalog-audit.sh")])
    check(first.returncode == 0, first.stderr)
    results.append({"name": "real compiled native catalog and nine oracle groups", "status": "pass", "observed": first.stdout.strip()})
    second_dir = WORK / "determinism"
    second = command([str(WORK / "catalog-audit"), str(ROOT), str(second_dir)])
    check(second.returncode == 0, second.stderr)
    for name in ["catalog-coverage.json", "catalog-coverage.md", "proposed-engineering-pack.json"]:
        check((ROOT / "docs/consumer-assessment" / name).read_bytes() == (second_dir / name).read_bytes(), f"Nondeterministic {name}")
    results.append({"name": "three deterministic byte-identical exports", "status": "pass"})
    report = json.loads(REPORT.read_text())
    check(report["modelInventorySupportedEntries"] == 2375 and report["unsupportedZHEntries"] == 23, "Inventory counts")
    check(report["entryVariantPositionMemberships"] == 2637 and report["allPronunciationTargetOccurrences"] == 2644, "Membership vs repeated occurrences")
    check(report["entriesWithRepeatedTargetInAnyVariant"] == 166 and report["entriesWithMultipleSelectedPositionOccurrences"] == 7, "Repeated-target coverage")
    check(report["wordsWithMultipleDictionaryVariants"] == 85 and report["entriesWithSelectedIndexesDifferingAcrossVariants"] == 28, "Variant coverage")
    catalog = {row["id"]: row for row in report["catalog"]}
    check(catalog["n-middle-banana"]["selectedPositionIndexesByVariant"] == [[2, 4]], "Exported banana occurrence indexes")
    check(catalog["zh-middle-treasure"]["modelTargetID"] is None, "ZH must export null model ID")
    results.append({"name": "pinned expanded counts and exported independent examples", "status": "pass"})
    text = VOCABULARY.read_text()
    results.append(mutation("unknown-target", text, '"d:end h:middle"', '"d:end h:middle fake:middle"', "Dictionary target mismatch for ahead"))
    results.append(mutation("variant-disagreement", text, '"vase", "vase", "V EY S/V AA Z", "v:beginning"', '"vase", "vase", "V EY S/V AA Z", "v:beginning s:end"', "Catalog size drift"))
    results.append(mutation("dictionary-variant-removes-target", text, '"banana", "banana", "B AH N AE N AH"', '"banana", "banana", "B AH N AE N AH/B AH L AE L AH"', "Dictionary target mismatch for banana"))
    check(all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in originals.items()), "Production source changed during test")
    results.append({"name": "production sources preserved", "status": "pass"})
    receipt = {"status": "pass", "checks": results, "sourceHashes": {str(p.relative_to(ROOT)): digest for p, digest in originals.items()}, "limits": "Metadata-only Swift catalog; no audio, corpus, features, checkpoint, fitting, inference or TEST reads"}
    (WORK / "audit-test-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"PASS: {len(results)} verification groups, including three compiled fail-closed mutation cases")


if __name__ == "__main__":
    main()
