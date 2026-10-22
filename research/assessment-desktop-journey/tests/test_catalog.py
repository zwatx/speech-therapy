import json
import unittest
from unittest.mock import patch
from journey.catalog import Catalog, PACK_PATH, read_owned
from journey.models import JourneyError

class CatalogTests(unittest.TestCase):
    def test_actual_catalog_has_all_prompts_variants_references_and_neutral_flags(self):
        catalog=Catalog();public=catalog.projection()
        self.assertEqual(len(public['prompts']),15);self.assertEqual(len(catalog.audio),13)
        rabbit=next(p for p in public['prompts'] if p['sourceWord']=='rabbit')
        self.assertEqual(len(rabbit['variants']),2)
        banana=next(p for p in public['prompts'] if p['sourceWord']=='banana')
        self.assertEqual(banana['variants'][0]['occurrenceIndexes'],[2,4]);self.assertEqual(banana['selectedOccurrenceIndex'],2)
        self.assertTrue(all(p['reference']['speakerAgeKnown'] is False for p in public['prompts']))
        self.assertTrue(all(flag is False for flag in public['claimLimits'].values()))
        self.assertNotIn('wavPath',str(public));self.assertNotIn('sourceEvidencePath',str(public))
        public['prompts'][0]['variants'][0]['phones'].append('LEAK')
        self.assertNotIn('LEAK',str(catalog.projection()))
        with self.assertRaises(JourneyError):catalog.reference('../private')
    def test_changed_engineering_pack_is_rejected_before_metadata_paths(self):
        def modified(path,limit):
            raw=read_owned(path,limit)
            if path==PACK_PATH:
                value=json.loads(raw);value['prompts'][0]['illustration']['sourcePath']='/private/not-readable'
                return json.dumps(value).encode()
            return raw
        with patch('journey.catalog.read_owned',side_effect=modified):
            with self.assertRaises(JourneyError):Catalog()
