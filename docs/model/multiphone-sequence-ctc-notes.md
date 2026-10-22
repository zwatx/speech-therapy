# Sequence-level CTC evidence: rationale and limits

Primary-source reading and local code audit, September 27, 2026.

## Published basis

Cao et al. (Interspeech 2024) compare the complete canonical sequence likelihood
with a set of alternative sequences sharing its left and right context. Their
AF-SD variant allows one substitution or deletion; AF-SDI additionally permits
insertions. Section 3.3 also forms features from canonical likelihood and
canonical/alternative likelihood ratios. This motivates testing sequence
evidence without committing to one forced alignment. Their experiments use a
39-phone English recognizer, whereas our cached decoder has 388 nonspecial
tokens, some representing variants or merged sounds. Their reported results
are not transferable performance estimates for Cadence.
[Paper, sections 3.2–3.3](https://www.isca-archive.org/interspeech_2024/cao24b_interspeech.pdf)

Parikh et al. (Interspeech 2025) study restrictions on possible substitutions
and discuss the computational cost of unrestricted alternatives. We will not
import a hand-selected confusion map or treat such a map as acceptable
pronunciation guidance. Instead, the numerical preflight keeps all existing
nonspecial decoder tokens and tests whether shared calculations make that
finite set practical.
[Paper, section 2.3](https://www.isca-archive.org/interspeech_2025/parikh25_interspeech.pdf)

Li et al. (BEA 2026) propose changes to CTC context modeling and training to
address sparse, temporally unstable outputs. That is a separate intervention:
the current preflight keeps the recognizer and its cached outputs fixed. A
correct likelihood calculation cannot establish that those outputs accurately
represent children's speech.
[Author abstract and paper](https://aclanthology.org/2026.bea-1.3/)

The original authors' repository now separates its 2024 code from a 2026
extension with a normalization term. No upstream code is copied or executed
here; our implementation is independently checked against exhaustive paths and
PyTorch's CTC loss. We do not claim to reproduce the extension.
[Author repository](https://github.com/frank613/CTC-based-GOP)

## What differs from the completed experiments

`multiphone_local_features.py` forces the canonical token sequence through a
maximum-probability CTC path, then calculates thirteen statistics around its
occupied target states. The utterance-wide score is a maximum over paths.
`multiphone_competitor_study.py` adds twenty-four consonant posterior means
inside those same forced intervals. Neither sums complete-sequence probability
over all valid CTC paths for each possible replacement or deletion.

The existing cache contains 2,495 author-training recordings, 515,038 frames
and 807,579,584 bytes of full 392-token log probabilities. This is a metadata
inventory, not a new quality assessment. A numerical preflight needs no new
recording, encoder inference, download, corpus access or GPU session.

## Independent implementation

For a canonical sequence and a chosen slot, enumerate the distinct collapsed
sequences obtained by replacing that slot with each candidate token, plus the
sequence obtained by removing it. CTC collapse rules still distinguish adjacent
repeated labels unless a blank separates them. Candidate paths retain the
original full-vocabulary probabilities; omitted special-token mass is never
renormalized into the allowed candidates.

The implementation shares the canonical prefix and suffix dynamic-programming
tables. A replacement path is counted according to the last frame occupying
the replacement state. A deletion path is counted according to the first
frame of the next canonical label. These disjoint events avoid counting one
path twice. Neighbor equality controls the skip transitions. Deleting the
last token sums the left-prefix terminal states; deleting the only token gives
the all-blank path. All sums run in float64 log space.

The restricted denominator sums those distinct sequence probabilities. Its
canonical log share is a property of that explicitly limited hypothesis set,
not a calibrated probability that a sound was correct. A single decoder token
need not equal a single produced phoneme. There is no insertion model, accepted
allophone inventory, independent timing truth, SSD diagnosis or distortion
label. An impossible canonical path or undefined denominator must remain
explicit; it is not replaced with a confident score.

## Next decision

Run the [fixed numerical preflight](multiphone-sequence-ctc-preflight-protocol.md)
before selecting training features. It asks whether the calculation is exact,
reproducible and practical on the retained inputs. Only after that passes
should a new fixed model comparison test whether these signals improve
speaker-separated rating prediction. Successful numerical verification is not
evidence of better pronunciation assessment.
