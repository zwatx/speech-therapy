"""Audit saved artifacts without rerunning reporting model inference."""
import json

import numpy as np
from sklearn.metrics import average_precision_score
import torch
from threadpoolctl import threadpool_limits

from .jibo import RUN as STAGE_C
from .gop import labels
from .stage_d import RUN, check_identity, load_group, rows_by_group, save_json, sha
from .stage_d_features import FEATURE_NAMES
from .stage_d_models import CANDIDATES, predict_raw, platt_logits
from .stage_d_metrics import ranking, summarize


def verify():
    check_identity()
    torch.set_num_threads(4)
    selection = json.loads((RUN/'selection.json').read_text())
    result = json.loads((RUN/'evaluation-result.json').read_text())
    groups = rows_by_group()
    checks = []
    assert selection['l2_fit_count'] == selection['reporting_fit_count'] == 0
    assert selection['identity_sha256'] == sha(RUN/'identity.json')
    assert json.loads((RUN/'evaluation-started.json').read_text())['selection_sha256'] == sha(RUN/'selection.json')
    assert selection['selected'] == max(CANDIDATES,key=lambda n:selection['candidates'][n]['calibration']['AP'])
    assert selection['platt']['weights'][1] > 0
    assert selection['combined_fit_seconds'] <= 1800
    charge = 0.
    for name in CANDIDATES:
        receipt = json.loads((RUN/f'fit-{name}.json').read_text())
        assert receipt['status'] == 'complete'
        model_path = RUN/('mlp.pt' if name == 'mlp' else f'{name}.joblib')
        assert receipt['model_sha256'] == sha(model_path)
        assert receipt['fit_seconds'] == selection['candidates'][name]['fit_seconds']
        charge += receipt['fit_seconds']
    assert charge == selection['combined_fit_seconds']
    assert selection['candidates']['mlp']['epochs'] == 20
    checks.append('three retained models, immutable receipts, fixed MLP epochs, selection, positive Platt and cumulative budget')
    for name, rows in groups.items():
        x, records = load_group(name)
        expected = {(r['id'],i,r['canonical'][i],y) for r in rows for i,y in labels(r).items()}
        keys = {(r['id'],r['index'],r['phone'],r['error']) for r in records}
        assert len(records) == len(keys) == len(expected) and keys == expected
        assert x.shape == (len(records),168) and np.isfinite(x).all()
        summary = json.loads((RUN/f'{name}-summary.json').read_text())
        assert summary['utterances'] == len(rows)
        assert summary['excluded_fractional'] == sum(len(r['canonical'])-len(labels(r)) for r in rows)
        assert summary['phones'] == len(records) and summary['errors'] == sum(r['error'] for r in records)
        assert not summary['excluded']
        if name == 'train':
            mean = np.asarray(selection['scaling']['mean'])
            scale = np.asarray(selection['scaling']['scale'])
            np.testing.assert_allclose(mean,x.mean(0),atol=1e-10,rtol=1e-10)
            expected_scale = x.std(0)
            expected_scale[expected_scale < 1e-8] = 1.
            np.testing.assert_allclose(scale,expected_scale,atol=1e-10,rtol=1e-10)
        elif name == 'calibration':
            yc = np.asarray([r['error'] for r in records])
            assert sorted({r['speaker'] for r in records}) == selection['calibration_speakers']
            for candidate in CANDIDATES:
                raw = np.asarray(json.loads((RUN/f'calibration-{candidate}-predictions.json').read_text()))
                with threadpool_limits(limits=4):
                    replay = predict_raw(candidate,x,selection['scaling'])
                np.testing.assert_allclose(raw,replay,atol=1e-10,rtol=1e-10)
                assert ranking(yc,raw) == selection['candidates'][candidate]['calibration']
                np.testing.assert_allclose(average_precision_score(yc,raw),ranking(yc,raw)['AP'],atol=1e-12)
            selected_raw = np.asarray(json.loads((RUN/f'calibration-{selection["selected"]}-predictions.json').read_text()))
            saved = json.loads((RUN/'predictions-calibration.json').read_text())
            np.testing.assert_allclose([r['logit'] for r in saved],platt_logits(selected_raw,selection['platt']),atol=1e-10)
        if name in ('calibration','speech_children','l2'):
            old = json.loads((STAGE_C/f'detection-{name}-phones.json').read_text())
            assert keys == {(r['id'],r['index'],r['phone'],r['error']) for r in old}
            lookup = {(r['id'],r['index']):r for r in old}
            for i, record in enumerate(records):
                canonical_column = FEATURE_NAMES.index('log_ratio_'+record['phone'])
                actual = np.delete(x[i,:40],canonical_column).max()
                np.testing.assert_allclose(actual,lookup[(record['id'],record['index'])]['gop'],atol=1e-4,rtol=1e-6)
                assert x[i,FEATURE_NAMES.index('blind_disagreement')] == lookup[(record['id'],record['index'])]['disagreement']
        if name in ('speech_children','l2'):
            saved = json.loads((RUN/f'predictions-{name}.json').read_text())
            assert [(r['id'],r['index'],r['error']) for r in saved] == [(r['id'],r['index'],r['error']) for r in records]
            metrics = summarize(saved,[r['logit'] for r in saved],selection['threshold'])
            for key,value in metrics.items():
                assert value == result[name][key], (name,key)
            np.testing.assert_allclose(average_precision_score([r['error'] for r in saved],[r['logit'] for r in saved]),
                                       result[name]['AP'],atol=1e-12)
            ci = result[name]['bootstrap_95']
            assert ci['requested'] == 2000 and ci['valid']+ci['excluded_no_error'] == 2000
            assert ci['speakers'] == len({r['speaker'] for r in records})
            for key in ('AP','recall_at_precision_0_9'):
                assert 0 <= ci[key][0] <= ci[key][1] <= 1
            assert result[name]['coverage_curve'][-1]['phones'] == len(records)
            if name == 'l2':
                assert np.all(x[:,FEATURE_NAMES.index('word_metadata_present')] == 0)
    checks += ['all2500 official train utterances; exact label masks, phone keys, finite168features and train-only scaling',
               'all three calibration predictions replay, AP independently matches sklearn',
               'Stage C keys, GOP maxima and blind disagreement match on all three existing groups',
               'saved reporting metrics/counts/curves/per-phone/ECE replay without model inference; AP independently matches sklearn',
               '2000speaker bootstrap metadata/bounds and full verdict denominators']
    output = dict(status='pass',checks=checks,reporting_model_inference_repeated=False,
                  combined_fit_seconds=charge)
    save_json(RUN/'verification.json',output)
    print(json.dumps(output,indent=2),flush=True)


if __name__ == '__main__':
    verify()
