"""Package only declared author-training recordings for a fixed lexical pilot."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

HERE = Path(__file__).resolve().parents[1]
BASE = HERE / 'outputs/multiphone-20260927'
OUT = BASE / 'colab-expanded-pilot-v1'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path, expected=None):
    if expected is not None:
        assert sha(path) == expected, str(path)
    return json.loads(Path(path).read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def group(word):
    return int.from_bytes(hashlib.sha256(('cadence-lexical-holdout-v1\0' + word.upper()).encode()).digest(), 'big') % 5


def main():
    assert not OUT.exists(), 'Fresh payload required'
    planpath = BASE / 'lexical-expanded-heads-v1/plan.json'
    plan = read(planpath, '8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c')
    job = next(j for j in plan['jobs'] if j['id'] == 'child-only-scalars-s0-w0')
    cohortpin = plan['inputs']['cohort']
    cohort = read(cohortpin['path'], cohortpin['sha256'])
    assert cohort['authorPartition'] == 'train' and not cohort['authorTestObjectsDecoded']
    rows = cohort['rows']
    clips = {c['id']: c for c in cohort['clips']}
    featureplanpath = BASE / 'position-phonetic-v1/plan.json'
    featureplan = read(featureplanpath, 'b3f1884a54b1fa25777eb9578155b9923eed9ce61ff1762e05301f6211c7f29c')
    featurepath = BASE / 'position-phonetic-v1/report.json'
    feature = read(featurepath, '80a0dd901f026deebd74ea9fb66d234f14e80ca44d03ab8c0816e0d8494341be')
    fp = feature['matrices']['combined']
    assert sha(fp['path']) == fp['sha256']
    features = np.load(fp['path'], allow_pickle=False)
    assert features.dtype == np.float32 and features.shape == (28227, 1037) and np.isfinite(features).all()
    geometry = {r['rowIndex']: r for c in featureplan['clips'] for r in c['rows']}
    grids = {c['id']: c['frames'] for c in featureplan['clips']}
    splits = read(HERE / 'outputs/multiphone-20260926/splits.json',
                  'b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf')
    oldpin = plan['inputs']['originalCohort']
    old = read(oldpin['path'], oldpin['sha256'])
    split = splits['folds'][0]
    speaker_sets = {name: {old['rows'][i]['speakerId'] for i in split[key]}
                    for name, key in [('fit', 'innerFitRows'), ('selection', 'innerValidationRows'),
                                      ('outer', 'outerHoldoutRows')]}
    expected_fit = [i for i, r in enumerate(rows) if r['speakerId'] in speaker_sets['fit']
                    and 6 <= r['age'] <= 12 and
                    all(group(w['text']) != 0 for w in clips[r['clipId']]['words'])]
    assert job['fitRows'] == expected_fit
    fit, selection = job['fitRows'], job['selectionRows']
    outer = [i for i in job['outerRows'] if 6 <= rows[i]['age'] <= 12 and rows[i]['legacyRowIndex'] is not None]
    assert len(fit) == 1997 and len(selection) == 150 and outer
    for name, ids in [('fit', fit), ('selection', selection), ('outer', outer)]:
        assert len(ids) == len(set(ids))
        assert all(rows[i]['speakerId'] in speaker_sets[name] for i in ids)
        assert all(6 <= rows[i]['age'] <= 12 for i in ids)
        if name != 'outer':
            assert all(all(group(w['text']) != 0 for w in clips[rows[i]['clipId']]['words']) for i in ids)
        else:
            assert all(group(rows[i]['targetWord']) == 0 for i in ids)
    assert all(rows[i]['legacyRowIndex'] is not None for i in selection)
    assert set(rows[i]['targetId'] for i in fit) == set(range(23))
    OUT.mkdir(parents=True)
    (OUT / 'wav').mkdir()

    def package(ids):
        rr = []
        for i in ids:
            r = rows[i]; g = geometry[i]
            assert r['id'] == g['id'] and r['targetId'] == g['targetId']
            rr.append(dict({k: r[k] for k in ('id', 'clipId', 'speakerId', 'age', 'targetId', 'targetPhone', 'raterCounts')},
                           rowIndex=i, window=g['estimatedPoolingWindowFrames']))
        cc = []
        for cid in sorted({r['clipId'] for r in rr}):
            c = clips[cid]
            assert sha(c['audioPath']) == c['audioSha256']
            dest = OUT / 'wav' / (cid + '.wav')
            shutil.copyfile(c['audioPath'], dest)
            cc.append(dict(id=cid, wav='wav/' + cid + '.wav', sampleCount=c['sampleCount'], frames=grids[cid]))
        return dict(rows=rr, clips=cc)

    training = package(fit + selection)
    training.update(fitRows=fit, selectionRows=selection)
    write(OUT / 'train.json', training)
    write(OUT / 'outer.json', package(outer))
    np.save(OUT / 'features.npy', features[fit + selection], allow_pickle=False)
    np.save(OUT / 'outer_features.npy', features[outer], allow_pickle=False)
    provenance = {str(p): sha(p) for p in [planpath, Path(cohortpin['path']), featureplanpath,
                                          featurepath, Path(fp['path']), Path(__file__)]}
    manifest = dict(schema=1, seed=17, modelId=featureplan['recipe']['modelId'],
                    revision=featureplan['recipe']['revision'], modelFiles=featureplan['recipe']['artifactSha256'],
                    files={str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()},
                    provenance=provenance, job='child-only-s0-w0',
                    recipe=dict(cachedEpochs=20, patience=4, headLR=.0003, encoderLR=.000001,
                                continuationEpochs=2, clipsPerUpdate=4, seed=17,
                                maxComputeUnits=5, monthlyComputeUnitAllowance=300),
                    authorPartition='train', authorTestRead=False, learnerFeedbackEligible=False,
                    promotionEligible=False, independentFinalValidation=False)
    write(OUT / 'manifest.json', manifest)
    summary = dict(fitRows=len(fit), selectionRows=len(selection), outerOriginalChildRows=len(outer),
                   clips=len(list((OUT/'wav').iterdir())), bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
                   perPartition={name: dict(speakers=len({rows[i]['speakerId'] for i in ids}),
                     phones=sorted({rows[i]['targetPhone'] for i in ids}),
                     votes=np.sum([rows[i]['raterCounts'] for i in ids], axis=0).tolist())
                     for name, ids in [('fit', fit), ('selection', selection), ('outer', outer)]},
                   manifestSha256=sha(OUT/'manifest.json'))
    write(OUT / 'preparation.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
