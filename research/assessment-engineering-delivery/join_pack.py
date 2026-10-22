"""Materialize the checked engineering decisions and source-bound asset associations."""
import hashlib
import json
from pathlib import Path
from content_review.private_io import read_private, write_private
from content_review.packet import strict_json
from reference_assets import validate_registry
from workbench.domain import semantic_digest
from validate_content import validate, CONTENT, ROOT

WORK = ROOT / 'work/assessment-real-data-20261004'

def join():
    validate()
    decisions_raw = (CONTENT / 'content-decisions.json').read_bytes()
    images_raw = (CONTENT / 'illustrations.json').read_bytes()
    decisions = strict_json(decisions_raw)
    illustrations = strict_json(images_raw)
    registry_raw = read_private(str(WORK / 'references/assets.json'))
    registry = strict_json(registry_raw)
    validate_registry(registry, require_complete=True)
    assets = {a['sourceWord']:a for a in registry['assets']}
    images = {a['word']:a for a in illustrations['illustrations']}
    prompts = []
    for decision in decisions['decisions']:
        image = images[decision['word']]
        path = CONTENT / image['path']
        prompts.append({'decision':decision, 'illustration':{
            **image, 'sourcePath':str(path.relative_to(ROOT)),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},
            'reference': assets[decision['sourceWord']]})
    joined = {'schemaVersion':1, 'kind':'source-bound-engineering-assessment-pack',
              'sourcePackSha256':decisions['sourcePackSha256'],
              'decisionsSha256':hashlib.sha256(decisions_raw).hexdigest(),
              'illustrationsRegistrySha256':hashlib.sha256(images_raw).hexdigest(),
              'referenceRegistrySha256':semantic_digest(registry),
              'modelEngineeringReview':'accepted',
              'professionalReview':'deferred_until_finished_product',
              'referenceSpeakerAge':'unknown', 'clinicalReferenceApproved':False,
              'learnerFeedbackEligible':False, 'clinicalUseEligible':False, 'productionUseEligible':False,
              'prompts':prompts}
    write_private(str(WORK / 'engineering-pack.json'), (json.dumps(joined, indent=2, allow_nan=False)+'\n').encode())
    return {'prompts':len(prompts), 'sourceWords':len(assets), 'packSha256':semantic_digest(joined)}

if __name__=='__main__':
    print(json.dumps(join(),sort_keys=True))
