"""Invented archives verify exact-member access and terminal metadata execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from r_confirmatory.metadata_stage_v2 import metadata_inventory, declare_metadata, run_metadata


def fixture(root):
    archive = root / 'synthetic.zip'
    xml = b'<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1"><segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier><userTier name="rating"><tierData><tw>PRIVATE_SENTINEL</tw></tierData></userTier></r></transcript></session>'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('0phon/Synthetic_7/s1.xml', xml)
        z.writestr('0phon/Synthetic_7/s1.wav', b'NOT_AN_AUDIO_FILE')
    split = {'dev': ['2'], 'test': ['7'], 'folders': {'dev': ['Synthetic_2'], 'test': ['Synthetic_7']}, 'sessions': {'dev': 0, 'test': 1}}
    inventory = {'folders': ['Synthetic_7'], 'sessions': {'Synthetic_7': [{'session': 's1', 'media': 'ignored', 'kind': 'ignored'}]}}
    for key, obj in [('split', split), ('sessions', inventory)]:
        (root / (key + '.json')).write_text(json.dumps(obj))
    bindings = {k: {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in [('archive',archive),('split',root/'split.json'),('sessions',root/'sessions.json')]}
    here = Path(__file__).parent
    from r_confirmatory.metadata_stage_v2 import SOURCE_PATHS
    sources = {k: {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in SOURCE_PATHS.items()}
    return bindings, sources


class MetadataStageTests(unittest.TestCase):
    def test_inventory_requires_complete_exact_session_set(self):
        split = {'dev':['2'],'test':['7'],'folders':{'dev':[], 'test':['Synthetic_7']},'sessions':{'test':1}}
        inv = {'folders':['Synthetic_7'],'sessions':{'Synthetic_7':[{'session':'s1'}]}}
        self.assertEqual(metadata_inventory(split,inv,['0phon/Synthetic_7/s1.xml'],1), ['0phon/Synthetic_7/s1.xml'])
        for names in [[],['0phon/Synthetic_7/s1.xml']*2,['0phon/Synthetic_7/s1.xml','0phon/Synthetic_7/unlisted.xml']]:
            with self.assertRaises(ValueError): metadata_inventory(split,inv,names,1)

    def test_declared_projection_selects_without_opening_media_and_refuses_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindings,sources=fixture(root)
            declaration=declare_metadata(bindings,sources,root/'stage',expected_children=1)
            opened=[]
            original=zipfile.ZipFile.open
            def observed(z,name,*args,**kwargs):
                opened.append(name)
                return original(z,name,*args,**kwargs)
            with patch.object(zipfile.ZipFile,'open',observed):
                result=run_metadata(root/'stage',declaration['sha256'])
            self.assertEqual(opened,['0phon/Synthetic_7/s1.xml'])
            receipt=json.loads(Path(result['receiptPath']).read_text())
            selection=json.loads(Path(result['selectionPath']).read_text())
            self.assertEqual(selection['counts']['selectedTokens'],1)
            self.assertEqual(receipt['openedMembers'],['0phon/Synthetic_7/s1.xml'])
            self.assertFalse(receipt['testAudioMembersOpened'])
            self.assertTrue(receipt['testStructuralMetadataRead'])
            self.assertNotIn('PRIVATE_SENTINEL', repr(receipt)+repr(selection))
            with self.assertRaises(FileExistsError): run_metadata(root/'stage',declaration['sha256'])

    def test_unannotated_records_are_explicit_and_never_enter_capped_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindings,sources=fixture(root)
            archive=Path(bindings['archive']['path'])
            with zipfile.ZipFile(archive) as z:
                xml=z.read('0phon/Synthetic_7/s1.xml')
            extra=b'<r id="missing"><segment start="1" end="2" unit="s"/></r><r id="empty"><segment start="2" end="3" unit="s"/><userTier name="ARPABET Target"><tierData/></userTier></r>'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('0phon/Synthetic_7/s1.xml',xml.replace(b'</transcript>',extra+b'</transcript>'))
            bindings['archive']['sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
            declaration=declare_metadata(bindings,sources,root/'stage',expected_children=1)
            result=run_metadata(root/'stage',declaration['sha256'])
            receipt=json.loads(Path(result['receiptPath']).read_text())
            self.assertEqual(receipt['recordReconciliation']['totals'],{'structuralRecords':3,'selectorInputRecords':1,'annotationIneligibleRecords':2,'missingTargetTierRecords':1,'emptyTargetTierRecords':1})
            self.assertEqual(len(receipt['recordReconciliation']['children']),1)
            structural=json.loads((root/'stage/projection/structural-input.json').read_text())
            self.assertEqual(len(structural['tokens']),3)
            self.assertEqual({r['targetMetadataStatus'] for r in structural['tokens']},{'resolved','missing_target_tier','empty_target_tier'})
            selection=json.loads(Path(result['selectionPath']).read_text())
            self.assertEqual(selection['counts']['selectedTokens'],1)

    def test_child_without_annotated_targets_remains_in_full_denominator(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindings,sources=fixture(root)
            archive=Path(bindings['archive']['path'])
            with zipfile.ZipFile(archive) as z:xml=z.read('0phon/Synthetic_7/s1.xml')
            target=b'<userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier>'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('0phon/Synthetic_7/s1.xml',xml.replace(target,b''))
            bindings['archive']['sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
            declaration=declare_metadata(bindings,sources,root/'stage',expected_children=1)
            result=run_metadata(root/'stage',declaration['sha256'])
            receipt=json.loads(Path(result['receiptPath']).read_text())
            selection=json.loads(Path(result['selectionPath']).read_text())
            self.assertEqual(receipt['recordReconciliation']['children'][0]['annotationIneligibleRecords'],1)
            self.assertEqual(selection['counts']['fullChildDenominator'],1)
            self.assertEqual(selection['children'][0]['selectedTokenIds'],[])
            self.assertEqual(selection['children'][0]['reason'],'no_eligible_tokens')

    def test_archive_replacement_during_projection_rejects_success(self):
        from r_confirmatory.structural_projection_v2 import project_session
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindings,sources=fixture(root)
            declaration=declare_metadata(bindings,sources,root/'stage',expected_children=1)
            def changed(*args):
                result=project_session(*args)
                archive=Path(bindings['archive']['path'])
                replacement=root/'replacement.zip'
                replacement.write_bytes(archive.read_bytes())
                replacement.replace(archive)
                return result
            with patch('r_confirmatory.structural_projection_v2.project_session',changed):
                with self.assertRaises(ValueError): run_metadata(root/'stage',declaration['sha256'])
            self.assertFalse((root/'stage'/'projection'/'receipt.json').exists())
            self.assertTrue((root/'stage'/'projection'/'failure.json').exists())

    def test_binding_tamper_fails_before_projection_and_is_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindings,sources=fixture(root)
            declaration=declare_metadata(bindings,sources,root/'stage',expected_children=1)
            Path(bindings['sessions']['path']).write_text('changed')
            with self.assertRaises(ValueError): run_metadata(root/'stage',declaration['sha256'])
            receipt=json.loads((root/'stage'/'projection'/'failure.json').read_text())
            self.assertEqual(receipt['errorCode'],'metadata_execution_failed')
            self.assertNotIn('changed',repr(receipt))
            with self.assertRaises(FileExistsError): run_metadata(root/'stage',declaration['sha256'])
