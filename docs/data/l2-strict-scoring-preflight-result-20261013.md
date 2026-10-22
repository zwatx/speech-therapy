# Fixed48 scoring preflight — October 13, 2026

The first scoring launch stopped before creating its execution directory, launching a worker or reading annotations. It produced no accuracy result. All 48 prior predictions remained locked and the manual references were unopened at that failure. The later separately reviewed V2 comparison has now completed; see the [actual result](l2-strict-scoring-result-20261013.md). Its 48 references were all unscorable and no accuracy rate was defined.

The failure is a source-manifest adapter mismatch. The frozen strict metric manifest includes five provenance fields alongside schema and files; the generic package helper accepts only schema and files. The actual launch rejected this mismatch rather than silently dropping the provenance. A narrow successor will validate the complete exact manifest and all seven pinned source rows, preserving the metric, mapping, parser, cohort and predictions.

Actual launch exit: 1, terminal `c31856` (no continuing session). The independent preflight negative check returned exit 0, terminal `a644e6`: original tool-start/source bindings current, the known enclosing parent absent, execution directory absent, worker not launched and annotations not read. It makes no full current model/runtime claim. The private negative is `work/l2-pilot-scoring-draft-v1/ROOT-PREFLIGHT-NEGATIVE-v1.json`, 976 bytes, SHA256 `63c59d0b17035d0f8582977a8639fa6fde867cb78c6f308a08f93061285e7b66`.

The failed source and actual start are preserved. The successor must complete source review and actual collection before a score is reported. No scientific policy, mapping or threshold will be changed on the basis of this preflight failure.
