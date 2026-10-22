# Fixed 48-reference convention audit

The actual metadata audit completed successfully on October 13. All 48 previously opened pilot references were audited; no audio, archive, additional holdout, or model was opened. The original strict comparison remains inconclusive: zero evaluable pairs and undefined error rates.

| Annotation form | Items | Intervals | Observed geometry |
| --- | ---: | ---: | --- |
| Exactly empty string | 48 | 48 | All trailing; all overlap only empty word labels |
| `sp` | 38 | 83 | All interior; 82 overlap only empty word labels, one mixed |
| `sil` | 38 | 58 | 37 leading, 21 interior; 57 overlap only empty word labels, one mixed |
| ASCII whitespace only | 1 | 1 | Interior; overlaps a nonempty word label |

The 48 empty trailing intervals total 0.9707709750566886 seconds. The audit also counted 35 deviation-tagged intervals across 15 items and two invalid annotation-code intervals across two items. Categories can overlap. No uncertain `err` tags were counted.

These are label and interval observations, not acoustic silence judgments. In particular, the whitespace-only interval over a nonempty word label prevents a blanket assumption that all blank labels are silence. The two invalid codes are failures under the frozen grammar, not evidence that the corpus is corrupt.

The original corpus describes manual word/phone annotation based on forced alignment and distinguishes canonical and perceived phone annotations. Its published documentation does not establish the meaning of every blank interval. Historical MFA 1.0.0 code defines `sp` as optional silence and `sil` as nonoptional silence, but the corpus paper does not pin that exact version. These sources support investigating pause conventions; they do not independently establish what was spoken. [Corpus documentation](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/), [original paper, section 3.3](https://www.isca-archive.org/interspeech_2018/zhao18b_interspeech.pdf), [historical MFA dictionary source](https://raw.githubusercontent.com/MontrealCorpusTools/Montreal-Forced-Aligner/v1.0.0/aligner/dictionary.py).

Any subsequent interpreter experiment belongs to development on this already exposed pilot. Preserve the original result, report exclusions and coverage, and leave the 20 reserve speakers untouched. This audit supplies no learner feedback, child, clinical, or commercial validity.

Actual execution: root tool `7e4a1a`, exit 0, no child process; original monotonic start 272114.649167083 and report elapsed-before-write 0.075611958 seconds, within the original 180-second budget. The successful terminal follows the source/evidence/output post-write guards. Aggregate: `work/l2-reference-convention-audit-v1/AGGREGATE-v1.json`, 2,578 bytes, SHA-256 `c30ceebc9161ceee22c91673e15f3515bd8547e808e230a336f2a855ecc3a585`. Frozen source manifest: 394 bytes, SHA-256 `b8882f16fe35e21450f5af3dca6f8c5512c0f875bb608c51425372b21bc6b6da`. The aggregate retains `actualTerminalStillRequired=true`; this note records the separately observed terminal rather than treating file existence as completion.
