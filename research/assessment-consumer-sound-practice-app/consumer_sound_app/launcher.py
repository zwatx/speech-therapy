"""Explicit local engineering launcher; no model call before Check sound."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
MODULES=('assessment-consumer-app','assessment-mobile-admission','assessment-admission','assessment-desktop-journey',
    'assessment-reference-assets','assessment-recording-access','assessment-review-service','assessment-workbench','audio-head')
def parse_args(argv=None):
    parser=argparse.ArgumentParser(description='Run the separately reviewed local adult engineering preview.')
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--runtime-root',type=Path,required=True)
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--feature-source-sha256',required=True)
    parser.add_argument('--worker-artifact-dir',required=True)
    parser.add_argument('--worker-source-sha256',required=True)
    parser.add_argument('--worker-receipt-sha256',required=True)
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535 or args.port==8782:parser.error('Choose a separate port; the delivered app uses8782.')
    from .contract import hex64
    if not hex64(args.feature_source_sha256):parser.error('A reviewed feature SHA256 is required.')
    return args

def main(argv=None):
    args=parse_args(argv)
    sys.path[:0]=[str(ROOT/'research'/name) for name in MODULES]
    from .worker_artifact import WorkerArtifact
    artifact=WorkerArtifact.from_inputs({'artifactDirectory':args.worker_artifact_dir,'sourceSha256':args.worker_source_sha256,'receiptSha256':args.worker_receipt_sha256})
    worker=artifact.load_api()
    from consumer_app.feedback import FeedbackExecutor,source_snapshot
    from .sources import snapshot
    source_check=lambda:snapshot(worker,source_snapshot,args.feature_source_sha256,artifact)
    source_check() # Full closure validated before runtime, Catalog or listener construction.
    from consumer_app.catalog import Catalog
    from .server import Server
    catalog=Catalog();executor=FeedbackExecutor(args.runtime_root/'word')
    try:
        observer=artifact.observer(worker,args.runtime_root/'phone',args.cache_dir)
        with Server(executor,catalog,worker,observer,source_check,args.port) as server:
            print(f'Local adult engineering preview: {server.origin}/',flush=True)
            try:server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:pass
    finally:executor.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
