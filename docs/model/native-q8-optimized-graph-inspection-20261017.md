# Optimized graph inspection: failed export

The host-only inspection built successfully, but its first export failed its own
file validation. No old/new graph comparison was performed. The q8 model remains
withheld from learner feedback, and the earlier 22/24 preservation failure remains
unchanged.

One actual old-model session construction returned successfully. The exporter
reported release of the session, options, environment and library, with zero
inference or prediction calls. Its final result was failure, and the second model
was never attempted. The aggregate controller records zero **accepted** sessions;
the individual log establishes one actual construction. The saved graph is an
unadmitted failed artifact.

The exporter incorrectly requires the parent directory's link count to remain
unchanged while creating the output file. A separate synthetic filesystem check
showed the count increasing from two to three on file creation. This is a concrete
guard defect. The original receipt did not identify each failed predicate, so the
exact runtime failing predicate cannot be uniquely established.

The next diagnostic should correct only directory identity handling, preserve
strict immutable-file checks, and test the revised guard without a model first.
It needs a separate reviewed execution proposal; the failed export is not retried
or reclassified. No optimizer cause or numerical equivalence follows from this
checkpoint.

That separate [directory-only correction and six-case generated control](native-q8-directory-guard-verification-20261017.md)
has now passed. It used no model sessions or predictions and does not change this
failed export's status.

The independent [failed-export review](../../work/native-q8-optimized-graph-inspection-20261017/FAILED-EXPORT-REVIEW.md)
records the actual process closure, counts and limitations. All evidence is retained
under `work/native-q8-optimized-graph-inspection-20261017/`. This work used no
recordings, simulator operations, signing/account changes or recording uploads.
