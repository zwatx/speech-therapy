"""Invented XML verifies study request identity without any corpus access."""
import io
import unittest
from r_confirmatory_run.requests import project_selected_requests, build_prompt, cut_arguments, RequestError


class RequestTests(unittest.TestCase):
    def test_selected_word_projection_reconciles_frozen_structure_and_original_occurrence(self):
        xml=b'<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1"><orthography><w>red</w><w>barn</w></orthography><segment start="1.25" end="2.5" unit="s"/><userTier name="ARPABET Target"><tierData><tw>B</tw><tw>AA1</tw><tw>R</tw><tw>N</tw></tierData></userTier><userTier name="rating"><tierData><tw>PRIVATE_SENTINEL</tw></tierData></userTier></r></transcript></session>'
        expected=[{'tokenId':'Synthetic_7/s1/r1','recordId':'r1','phones':['B','AA1','R','N'],'startSeconds':1.25,'endSeconds':2.5}]
        requests=project_selected_requests(io.BytesIO(xml),'Synthetic_7','s1',9,expected)
        self.assertEqual(requests[0]['prompt'],{'schemaVersion':2,'language':'en','transcript':'red_barn','words':[{'text':'red_barn','phones':['B','AA1','R','N']}],'targets':[{'id':'Synthetic_7/s1/r1','wordIndex':0,'phoneIndex':2,'targetPhone':'R'}]})
        self.assertNotIn('PRIVATE_SENTINEL',repr(requests))

    def test_missing_and_unusable_words_preserve_selected_identity(self):
        token={'tokenId':'Synthetic_7/s1/r1','recordId':'r1','phones':['R'], 'startSeconds':0.,'endSeconds':1.}
        for words in ('', '<orthography><w> </w></orthography>', '<orthography><w>'+('x'*65)+'</w></orthography>'):
            xml=('<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1">'+words+'<segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier></r></transcript></session>').encode()
            rows=project_selected_requests(io.BytesIO(xml),'Synthetic_7','s1',9,[token])
            self.assertEqual(rows[0]['status'],'failed')
            self.assertEqual(rows[0]['tokenId'],token['tokenId'])
            self.assertEqual(rows[0]['failureCode'],'unusable_orthography')

    def test_cut_preserves_input_seek_six_decimals_and_pcm_recipe(self):
        token={'startSeconds':1.23456789,'endSeconds':2.98765432}
        self.assertEqual(cut_arguments('/ffmpeg','/source',token,'/clip.wav'),
                         ['/ffmpeg','-nostdin','-v','error','-n','-ss','1.234568','-to','2.987654','-i','/source','-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le','/clip.wav'])

    def test_projection_rejects_structure_drift_duplicate_words_and_changed_stream(self):
        token={'tokenId':'Synthetic_7/s1/r1','recordId':'r1','phones':['R'], 'startSeconds':0.,'endSeconds':1.}
        prefix='<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1">'
        suffix='<segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier></r></transcript></session>'
        xml=(prefix+'<orthography><w>red</w></orthography>'+suffix).encode()
        for changed in ({**token,'endSeconds':2.}, {**token,'phones':['B','R']}):
            with self.assertRaisesRegex(RequestError,'selected_structure_differs'):
                project_selected_requests(io.BytesIO(xml),'Synthetic_7','s1',9,[changed])
        for words in ('<orthography><w>red</w></orthography>'*2,'<orthography><w><x>red</x></w></orthography>','<orthography xmlns="other"><w>red</w></orthography>'):
            with self.assertRaises(RequestError):
                project_selected_requests(io.BytesIO((prefix+words+suffix).encode()),'Synthetic_7','s1',9,[token])
        class Changing(io.BytesIO):
            def seek(self,*args):
                super().seek(0)
                self.write(xml.replace(b'red',b'bad'))
                return super().seek(*args)
        with self.assertRaisesRegex(RequestError,'stream_bytes_changed'):
            project_selected_requests(Changing(xml),'Synthetic_7','s1',9,[token])

    def test_outcome_mutation_cannot_change_prompt_and_unselected_words_are_ignored(self):
        token={'tokenId':'Synthetic_7/s1/r1','recordId':'r1','phones':['R'], 'startSeconds':0.,'endSeconds':1.}
        template='<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1"><orthography><w>red</w></orthography><segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier><userTier name="anything"><tw secret="%s">%s</tw></userTier></r></transcript></session>'
        a=project_selected_requests(io.BytesIO((template%('111','secret-one')).encode()),'Synthetic_7','s1',9,[token])
        b=project_selected_requests(io.BytesIO((template%('222','secret-two')).encode()),'Synthetic_7','s1',9,[token])
        self.assertEqual(a[0]['prompt'],b[0]['prompt'])
        self.assertNotIn('secret',repr(a)+repr(b))
