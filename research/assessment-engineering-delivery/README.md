# Engineering content and validation delivery

The owner accepts model engineering content decisions and schedules professional review after the finished product. The new content overlay implements that steering without rewriting historical pending preparation packets or implying professional approval.

`validate_content.py` compares all 15 decisions with the pinned pack, preserves its variants and positions, and checks the 13 original self-contained SVGs. `render_gallery.py` joins the public reference asset registry to the illustrations and neutral preview wording; it exposes no participant data or credentials. The local preview helper in the private delivery directory uses an explicit allowlist of the gallery and acquired public WAV references, never a directory server.

```sh
PYTHONPATH=research/content-review-preparation:research/assessment-workbench python3 research/assessment-engineering-delivery/validate_content.py
PYTHONPATH=research/content-review-preparation:research/assessment-workbench python3 research/assessment-engineering-delivery/render_gallery.py
python3 work/assessment-real-data-20261004/serve_gallery.py
```

Open `http://127.0.0.1:8776/` for the reference pack. It is a preview: assessment recording controls are elsewhere. Audio attribution and license links travel with each reference, including the selected derivative license. Acquired source labels and an engineering dictionary baseline do not establish that a recording realizes every dictionary variant. Actual speaker age remains unknown.

Use the separate reference acquisition, recording access and reference validation run guides for bytes, permissions and results. Private output files live under `work/assessment-real-data-20261004/`; preserve them privately. No mobile build, intended-child data collection, qualified ratings, clinical cue validation or reserved-study execution belongs to this delivery.
