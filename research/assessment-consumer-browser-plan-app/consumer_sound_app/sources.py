"""Complete local package and exact adult-context word dependency source map."""
from pathlib import Path
from . import contract as c
from .dependencies import research_dependencies
from .worker_artifact import ROOT,read_owned
HERE=Path(__file__).resolve().parents[1]
REQUIRED=frozenset(('pyproject.toml','consumer_sound_app/__init__.py','consumer_sound_app/contract.py','consumer_sound_app/worker_artifact.py',
    'consumer_sound_app/dependencies.py','consumer_sound_app/launcher.py','consumer_sound_app/server.py','consumer_sound_app/service.py','consumer_sound_app/sources.py',
    'ui/index.html','ui/app.js','ui/styles.css','ui/audio-capture.js','ui/visual-worker.js','ui/visual-runtime.js'))

def verify_inventory(rows,expected,root):
    c.need(type(rows) is list and len(rows)==len(expected),'invalid_source_inventory')
    c.need(all(c.exact(row,('path','bytes','sha256')) and type(row['path']) is str for row in rows),'invalid_source_inventory')
    c.need(set(row['path'] for row in rows)==set(expected),'invalid_source_inventory')
    for row in rows:
        c.need(type(row['bytes']) is int and 0<=row['bytes']<=1048576 and c.hex64(row['sha256']),'invalid_source_inventory')
        raw=read_owned(root/row['path'],1048576)
        c.need(len(raw)==row['bytes'] and c.sha(raw)==row['sha256'],'source_binding_failed')

def snapshot(worker,word_snapshot,expected_feature_sha256,artifact):
    c.need(HERE.resolve()==ROOT/'research/assessment-consumer-browser-plan-app','source_binding_failed')
    from consumer_app import feedback
    # The same module name exists in predecessors; never accept their callable or origin.
    c.need(feedback.MODULE.resolve()==ROOT/'research/assessment-consumer-browser-word-guess-app/consumer_app'
        and word_snapshot is feedback.source_snapshot,'source_binding_failed')
    manifest=c.strict_json(read_owned(HERE/'source-pins.json',65536))
    c.need(c.exact(manifest,('schemaVersion','owned','dependencies')) and type(manifest['schemaVersion']) is int and manifest['schemaVersion']==2,'invalid_source_inventory')
    c.need(c.hex64(expected_feature_sha256) and c.sha(c.canonical(manifest))==expected_feature_sha256,'source_binding_failed')
    verify_inventory(manifest['owned'],REQUIRED,HERE)
    verify_inventory(manifest['dependencies'],research_dependencies(),ROOT)
    artifact.verify();worker.snapshot(artifact.source_sha256);pins=worker.binding()
    return {'sources':{'featureSourceSha256':expected_feature_sha256,'workerSourceSha256':artifact.source_sha256,
        'workerReceiptSha256':artifact.receipt_sha256,'runtimePinsSha256':'908e50025533f9fa85bf1a4d3e89d30a9caa2b9f4883788b4188fedd5cb5751e',
        'contrastSpecSha256':pins['contrastSpecSha256'],'modelFileSha256':pins['modelFileSha256'],'vocabularyFileSha256':pins['vocabularyFileSha256'],
        'promptSha256':pins['promptSha256'],'resourcePolicySha256':c.sha(c.canonical(c.POLICY))},'wordBinding':word_snapshot()}
