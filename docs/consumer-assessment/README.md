# Consumer assessment preparation

**Current app status, October 18:** the [current app gap audit](current-app-gap-audit-20261018.md)
checks implemented recording/word feedback/practice/recheck behavior against the
full requested product. The latest native layout refinement is verified and
installed in its dated checkpoint. Sound-specific corrective findings and clinical
diagnosis remain unqualified; the existing content/reference preparation does not
supply independent produced-phone truth. The full app goal remains unfinished.
The historical preparation entries below retain their original dates and scopes.

Prepared 2026-10-02 for children ages 6–12. These are reviewable engineering and research preparation materials, with pending qualified content/reference decisions. No clinical release, new study execution, participant collection, TEST access or reviewer outreach is declared.

- [Assessment v1 contract](assessment-v1.md): separate capture, speech presence, prompt match, research prediction, finding, participation and improvement.
- [Real compiled native-catalog audit](catalog-coverage.md), [complete JSON](catalog-coverage.json): 892 words / 2,398 entries; exact inventory and pronunciation variants.
- [Proposed engineering pack and pending SLP worksheet](proposed-engineering-pack.md), [machine-readable prompt records](proposed-engineering-pack.json).
- [New blind R confirmatory preparation](r-confirmatory-preparation.md): DRAFT / NOT DECLARED / NOT EXECUTED.
- [Full-DEV calibration preparation recipe](r-calibration-preparation.md): proposed comparator; no fitting or coefficients created.
- [New isolated evaluation code](../../research/audio-head/r_confirmatory/evaluate.py): synthetic-tested descriptive analysis with full terminal rosters and identical-token paired comparisons. It loads no model or corpus and makes no acceptance decision.
- [Reviewed preparation snapshot](../../work/assessment-continuation-20261002/reviewed-preparation-snapshot.json): exact code/document/receipt hashes after synthetic verification and an independent Astra review. This freezes a review snapshot, not a scientific study declaration.
- [New confirmation tooling addendum](r-confirmation-tooling-preparation.md): isolated supplied-metadata selection and calibration preparation, synthetic verification only; no reserved input or execution declaration.
- [Reviewed artifact-stage addendum](r-confirmation-artifact-stages.md): private prediction lock, consumed local outcome join and independent evaluation audit; 65 synthetic checks and a saved end-to-end demonstration. Preparation only.
- [Milestone decision handoff](milestone-decision-handoff.md): consolidated completion evidence, unresolved declaration/content decisions and the dependency sequence; preserves the existing controlled review workflow.
- [Annotation and data preparation](annotation-data-preparation.md): extends the existing handoff without inventing a second approval process.
- [Assessment validation workbench](assessment-validation-workbench-20261004.md): runnable local synthetic operator workflow, complete-attempt evidence/reporting and pending public-pack preparation; no real audio, authenticated review or learner findings.

Reproduce the metadata audit from the repository root on this Mac's Swift toolchain:

```sh
./docs/consumer-assessment/run-catalog-audit.sh
python3 docs/consumer-assessment/test-catalog-audit.py
```

It compiles the actual `PracticeLibrary.swift` and `PracticeVocabulary.swift` with the helper, enumerates the native `entries()` API, validates every dictionary target intersection and unique identity, and checks nine independent named oracle groups. No Swift regex parser, corpus/audio/checkpoint read, fitting or inference is involved. The three report/pack files are deterministic; compiled binary and verification receipts remain task-local in `work/assessment-milestone-20261002/materials/`. Optional first argument selects another output directory for byte comparison. The fixed count/inventory guards intentionally fail on catalog drift until scope is reviewed.

The verification runner also compares all three generated exports byte-for-byte and compiles three modified vocabulary copies in the task-local directory to verify fail-closed behavior for an unknown target, variant disagreement and a variant that removes the requested target. Production sources stay unchanged.
