# MRPL2 access assessment

Checked September 27, 2026. **No usable corpus files were acquired.** MRPL2 is
a relevant manual-annotation lead, but immediate access is not established.

The [author repository](https://github.com/tweddan/MRPL2_Corpus) describes
4,500 utterances from 23 non-native English speakers with 14 first languages.
Its human annotations use Modern Received Pronunciation as the target dialect.
The described release contains mono WAV audio at 48 and 16 kHz, TextGrids,
word transcripts, and expected/produced phone-sequence master files. Some
participants recorded themselves; age ranges and train/development/test splits
were not established. This is not verified child SSD or American-English
error supervision.

The repository still identifies version 1.0. [Official DOI metadata for
version 1.1](https://api.datacite.org/dois/10.5281/zenodo.22690685) identifies
a September 10, 2026 release and CC BY 4.0. That declared license does not
establish that the files can be downloaded without approval.

| Source | Observed result | Consequence |
| --- | --- | --- |
| [Version 1.0 record](https://zenodo.org/records/20365865) | Public metadata, explicitly restricted files; login and access-request controls | Access approval is required for that release |
| [Version 1.1 record](https://zenodo.org/records/22690685) | Web tool could not retrieve the page | Latest file-access policy remains unknown |
| Concept record and normal Zenodo API requests | HTTP 403 with an unusual-network-traffic restriction | A network restriction, distinct from a corpus access policy |
| Author repository and DataCite metadata | Public descriptions and version/license metadata available | Supports this assessment, not an audio or annotation inventory |

No file URLs, archive sizes, actual label conventions, annotator agreement or
per-phone support were verified. Zenodo's displayed download data-volume
statistics are not archive sizes. No account, access request, correspondence,
alternate protected-data route, audio download or training occurred.

The [local evidence manifest](../../work/mrpl2-access-20260927/manifest.json)
binds three extracted observation records. These are labeled transcriptions
of observed facts, **not saved original HTTP response bytes**. Their hashes
attest the saved records only. The author-repository commit was
`5155d895fe8236261acb886935f399f7018307c5`. A repeat check in the subsequent
goal continuation confirmed the v1.0 restriction and the v1.1 retrieval failure.

Decision: retain MRPL2 as a conditional source and stop repeated access probes.
If official file access becomes available, inspect its exact version and terms,
establish the actual annotation contract and reserve speakers and prompts
before fitting. For now, continue with already permitted data; this access
limitation does not block every avenue of model improvement.
