"""Local synthetic workbench commands. Run from research/assessment-workbench."""
import argparse
import json
import os
from pathlib import Path

from .demo import make_manifest, make_predictions, example_answer
from .domain import ValidationError
from .store import Store, parse_json, verify_export


def exercise(path):
    store = Store.create(path, make_manifest())
    for prompt in store.manifest['prompts']:
        store.record_content_review(prompt['id'], {'decision': 'accepted', 'reviewerId': 'invented-operator',
            'notes': 'Invented workflow decision; no content or clinical approval.', 'reference': None})
    for role in ('reviewer-a', 'reviewer-b'):
        for attempt, item in zip(store.manifest['attempts'], store.snapshot(role)['items']):
            store.submit_review(role, item['itemId'], example_answer(attempt['id'], role))
        store.seal_reviews(role)
    predictions = make_predictions(store.manifest)
    store.save_prediction_lock(predictions['payload'], predictions['expectedSha256'])
    item = next(row for row in store.snapshot('adjudicator')['items'] if row['attemptId'] == 'attempt-10')
    store.adjudicate('attempt-10', {'target': 'altered', 'notes': 'Invented explicit adjudication; originals retained.',
        'reviewedOriginals': [item['reviewA']['sha256'], item['reviewB']['sha256']]})
    return store


def main():
    parser = argparse.ArgumentParser(description='Local invented-data assessment workbench. No recording collection.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('create-demo', 'exercise-demo', 'prepare-content', 'export'):
        command = sub.add_parser(name)
        command.add_argument('project', type=Path)
        if name == 'export':
            command.add_argument('output', type=Path)
    serve = sub.add_parser('serve')
    serve.add_argument('project', type=Path)
    serve.add_argument('--port', type=int, default=8770)
    verify = sub.add_parser('verify-export')
    verify.add_argument('input', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command in ('create-demo', 'exercise-demo'):
            store = Store.create(args.project, make_manifest()) if args.command == 'create-demo' else exercise(args.project)
            print(json.dumps({'created': True, 'synthetic': True, 'revision': store.revision,
                              'attempts': len(store.manifest['attempts'])}))
        elif args.command == 'prepare-content':
            from .content import prepare_content_manifest
            pack = Path(__file__).resolve().parents[3] / 'docs/consumer-assessment/proposed-engineering-pack.json'
            store = Store.create(args.project, prepare_content_manifest(pack.read_bytes()))
            print(json.dumps({'created': True, 'mode': 'preparation', 'prompts': len(store.manifest['prompts']), 'participants': 0, 'attempts': 0, 'qualifiedReviewEstablished': False}))
        elif args.command == 'serve':
            from .server import make_server
            server = make_server(Store.open(args.project), args.port)
            print(f'Invented-data workbench: http://127.0.0.1:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        elif args.command == 'export':
            bundle = Store.open(args.project).export_bundle()
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(bundle, stream, ensure_ascii=True, allow_nan=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            print(json.dumps(verify_export(bundle)))
        elif args.command == 'verify-export':
            if args.input.stat().st_size > 32 * 1024 * 1024:
                raise ValidationError('export_too_large')
            print(json.dumps(verify_export(parse_json(args.input.read_bytes()))))
    except (ValidationError, OSError) as exc:
        code = exc.code if isinstance(exc, ValidationError) else 'local_operation_failed'
        parser.exit(1, f'Error: {code}\n')


if __name__ == '__main__':
    main()
