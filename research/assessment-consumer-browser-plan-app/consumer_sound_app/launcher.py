"""Explicit local engineering launcher; no model call before Check sound."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
MODULES=('assessment-consumer-browser-word-guess-app','assessment-mobile-admission','assessment-admission','assessment-desktop-journey',
    'assessment-reference-assets','assessment-recording-access','assessment-review-service','assessment-workbench','audio-head')
def parse_args(argv=None):
    parser=argparse.ArgumentParser(description='Run the reviewed unified local practice successor.')
    parser.add_argument('--port',type=int,default=8805)
    parser.add_argument('--runtime-root',type=Path)
    parser.add_argument('--cache-dir',type=Path)
    parser.add_argument('--feature-source-sha256',required=True)
    parser.add_argument('--worker-artifact-dir',required=True)
    parser.add_argument('--worker-source-sha256',required=True)
    parser.add_argument('--worker-receipt-sha256',required=True)
    parser.add_argument('--check',action='store_true',help='Verify reviewed source metadata without runtime or listener creation.')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535 or args.port in (8782,8788,8789,8791,8793,8795,8797,8803):parser.error('Choose a separate port; delivered app ports are reserved.')
    if not args.check and (args.runtime_root is None or args.cache_dir is None):parser.error('An explicit separate runtime root and reviewed cache directory are required to launch.')
    from .contract import hex64
    if not hex64(args.feature_source_sha256):parser.error('A reviewed feature SHA256 is required.')
    return args

def main(argv=None):
    args=parse_args(argv)
    package=Path(__file__).resolve().parents[1]
    if package!=ROOT/'research/assessment-consumer-browser-plan-app':raise ValueError('wrong_successor_package')
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]),*(str(ROOT/'research'/name) for name in MODULES)]
    from .worker_artifact import WorkerArtifact
    artifact=WorkerArtifact.from_inputs({'artifactDirectory':args.worker_artifact_dir,'sourceSha256':args.worker_source_sha256,'receiptSha256':args.worker_receipt_sha256})
    worker=artifact.load_api()
    from consumer_app.feedback import FeedbackExecutor,source_snapshot
    from .sources import snapshot
    source_check=lambda:snapshot(worker,source_snapshot,args.feature_source_sha256,artifact)
    source_check() # Full closure validated before runtime, Catalog or listener construction.
    if args.check:
        print('Unified successor source metadata verified.',flush=True)
        return 0
    from consumer_app.catalog import Catalog
    from .server import Server
    catalog=Catalog();executor=FeedbackExecutor(args.runtime_root/'word')
    try:
        observer=artifact.observer(worker,args.runtime_root/'phone',args.cache_dir)
        with Server(executor,catalog,worker,observer,source_check,args.port) as server:
            print(f'Browser guided-practice successor: {server.origin}',flush=True)
            try:server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:pass
    finally:executor.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
