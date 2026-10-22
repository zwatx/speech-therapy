"""Fixed verified public engineering catalog, independent of managed private copies."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
from reference_assets import validate_registry
from recording_access.models import strict_json
from workbench.domain import semantic_digest
from .models import CLAIMS, JourneyError

ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = ROOT / 'work/assessment-real-data-20261004/engineering-pack.json'
REGISTRY_PATH = ROOT / 'work/assessment-real-data-20261004/references/assets.json'
PACK_SHA = 'beafb00cbfe5578560549abd0ebd1fbbfba88218521f3c50cbab654d8a33ebd1'
REGISTRY_SHA = '01de20fb2759fc7605bcf20322749a9405961ce5f33f20acbbe73508f2e61564'


def read_owned(path, limit):
    """Read a known owned regular file once; callers supply closed inventory paths."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or before.st_size > limit:
            raise JourneyError('catalog_unavailable')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk: break
            raw.extend(chunk)
        after = os.fstat(fd)
        if len(raw) > limit or len(raw) != before.st_size or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise JourneyError('catalog_unavailable')
        return bytes(raw)
    finally: os.close(fd)


class Catalog:
    def __init__(self):
        registry_raw = read_owned(REGISTRY_PATH, 1024 * 1024)
        if hashlib.sha256(registry_raw).hexdigest() != REGISTRY_SHA: raise JourneyError('catalog_unavailable')
        registry = strict_json(registry_raw); validate_registry(registry, require_complete=True)
        pack = strict_json(read_owned(PACK_PATH, 1024 * 1024))
        if semantic_digest(pack) != PACK_SHA: raise JourneyError('catalog_unavailable')
        if pack.get('referenceRegistrySha256') != semantic_digest(registry) or len(pack.get('prompts', [])) != 15:
            raise JourneyError('catalog_unavailable')
        if any(pack.get(key) is not False for key in ('clinicalReferenceApproved', *CLAIMS)):
            raise JourneyError('catalog_unavailable')
        self.content_sha256 = semantic_digest(pack)
        self.assets = {record['sourceWord']: deepcopy(record) for record in registry['assets']}
        self.audio, self.images, self.prompts = {}, {}, []
        public = []
        for entry in pack['prompts']:
            decision, illustration, reference = entry['decision'], entry['illustration'], entry['reference']
            word = decision['sourceWord']; asset = self.assets[word]
            if semantic_digest(reference) != semantic_digest(asset): raise JourneyError('catalog_unavailable')
            expected = ROOT / 'research/assessment-engineering-content/illustrations' / (('yo-yo' if word == 'yoyo' else word) + '.svg')
            if illustration['sourcePath'] != str(expected.relative_to(ROOT)): raise JourneyError('catalog_unavailable')
            image = read_owned(expected, 512 * 1024)
            audio = read_owned(asset['wavPath'], 132096)
            if hashlib.sha256(image).hexdigest() != illustration['sha256'] or hashlib.sha256(audio).hexdigest() != asset['wavSha256']:
                raise JourneyError('catalog_unavailable')
            self.audio[word], self.images[word] = audio, image
            variant = decision['preferredVariantId']; index = decision['chosenOccurrenceIndexByVariant'][variant]
            supported = decision['modelSupport']['modelInventorySupported']
            self.prompts.append({'id': decision['promptId'], 'word': decision['word'], 'sourceWord': word,
                                 'targetPhone': decision['targetPhone'], 'variantId': variant,
                                 'phones': decision['phonesByVariant'][variant], 'occurrenceIndex': index, 'supported': supported})
            public.append({'id': decision['promptId'], 'word': decision['word'], 'sourceWord': word,
                           'targetPhone': decision['targetPhone'], 'variants': [{'id': key, 'phones': phones, 'occurrenceIndexes': decision['allTargetIndexesByVariant'][key]}
                               for key, phones in decision['phonesByVariant'].items()],
                           'selectedVariantId': variant, 'selectedOccurrenceIndex': index, 'supported': supported,
                           'imageUrl': '/illustrations/' + word + '.svg', 'publicReferenceUrl': '/api/public-references/' + word,
                           'reference': {key: asset[key] for key in ('author','licenseId','licenseUrl','sourcePageUrl','declaredVariety','speakerAgeKnown','clinicalReferenceApproved','changes','attribution')}})
        self.public = {'schemaVersion': 1, 'mode': 'engineering_examples', 'prompts': public, 'claimLimits': deepcopy(CLAIMS)}

    def projection(self): return deepcopy(self.public)
    def reference(self, word):
        if type(word) is not str or word not in self.audio: raise JourneyError('recording_unavailable')
        return self.audio[word]
    def illustration(self, word):
        if type(word) is not str or word not in self.images: raise JourneyError('catalog_unavailable')
        return self.images[word]
