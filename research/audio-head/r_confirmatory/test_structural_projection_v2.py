"""Invented XML only: annotation records reconcile without widening eligibility."""
import io
import unittest

from r_confirmatory.structural_projection_v2 import ProjectionError, project_session

AGE = '<participant id="CHI"><age>P9Y</age></participant>'
SEGMENT = '<segment start="0" end="1" unit="s"/>'
TARGET = '<userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier>'
RECORD = '<r id="r1">' + SEGMENT + TARGET + '</r>'


def document(age=AGE, records=RECORD):
    return ('<session><participants>' + age + '</participants><transcript>' + records + '</transcript></session>').encode()


class AnnotationProjectionTests(unittest.TestCase):
    def test_missing_target_annotation_and_resolved_record_both_reconcile(self):
        annotation = '<r id="annotation.1">' + SEGMENT + '</r>'
        result = project_session(io.BytesIO(document(records=annotation + RECORD)), "Synthetic_7", "s1")
        self.assertEqual(result['records'], [
            {'recordId': 'annotation.1', 'startSeconds': 0.0, 'endSeconds': 1.0,
             'phones': [], 'targetMetadataStatus': 'missing_target_tier'},
            {'recordId': 'r1', 'startSeconds': 0.0, 'endSeconds': 1.0,
             'phones': ['R'], 'targetMetadataStatus': 'resolved'},
        ])
        self.assertEqual(result['counts'], {'records': 2, 'phones': 1})

    def test_empty_tier_data_is_annotation_but_empty_tw_is_literal_resolved_phone(self):
        empty_tier = RECORD.replace('r1', 'empty.tier').replace('<tw>R</tw>', '')
        empty_tw = RECORD.replace('r1', 'empty.tw').replace('<tw>R</tw>', '<tw/>')
        whitespace_tw = RECORD.replace('r1', 'space.tw').replace('<tw>R</tw>', '<tw> R </tw>')
        result = project_session(io.BytesIO(document(records=empty_tier + empty_tw + whitespace_tw)), "Synthetic_7", "s1")
        self.assertEqual([(r['recordId'], r['targetMetadataStatus'], r['phones']) for r in result['records']], [
            ('empty.tier', 'empty_target_tier', []),
            ('empty.tw', 'resolved', ['']),
            ('space.tw', 'resolved', [' R ']),
        ])
        self.assertEqual(result['counts'], {'records': 3, 'phones': 2})

    def test_malformed_target_and_incomplete_annotation_are_still_failures(self):
        cases = [
            ('<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"/></r>', 'malformed_target_metadata'),
            ('<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tw>R</tw></userTier></r>', 'invalid_target_structure'),
            ('<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData><tw>R<private>SECRET</private></tw></tierData></userTier></r>', 'invalid_target_structure'),
            ('<r id="r1">' + SEGMENT + TARGET + TARGET + '</r>', 'duplicate_target_tier'),
            ('<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData/><tierData/></userTier></r>', 'invalid_target_structure'),
            ('<r id="annotation.1"/>', 'missing_segment'),
            ('<r id="annotation.1"><segment start="NaN" end="1" unit="s"/></r>', 'invalid_segment'),
            ('<r>' + SEGMENT + '</r>', 'invalid_record_id'),
        ]
        for index, (records, code) in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(document(records=records)), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)

    def test_nonwhitespace_target_text_outside_tw_is_malformed_not_empty_annotation(self):
        tiers = [
            '<userTier name="ARPABET Target"><tierData>R</tierData></userTier>',
            '<userTier name="ARPABET Target"><tierData>R<tw>R</tw></tierData></userTier>',
            '<userTier name="ARPABET Target"><tierData><tw>R</tw>R</tierData></userTier>',
            '<userTier name="ARPABET Target">R<tierData/></userTier>',
            '<userTier name="ARPABET Target"><tierData/><![CDATA[R]]></userTier>',
        ]
        for tier in tiers:
            with self.subTest(tier=tiers.index(tier)):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(document(records='<r id="r1">' + SEGMENT + tier + '</r>')), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, 'malformed_target_metadata')
        whitespace = '<userTier name="ARPABET Target"> \n<tierData> \n </tierData> \t </userTier>'
        result = project_session(io.BytesIO(document(records='<r id="r1">' + SEGMENT + whitespace + '</r>')), "Synthetic_7", "s1")
        self.assertEqual(result['records'][0]['targetMetadataStatus'], 'empty_target_tier')
        self.assertEqual(result['records'][0]['phones'], [])

    def test_ignored_tier_mutations_are_invariant_for_each_target_metadata_status(self):
        variants = [
            ('<r id="r1">' + SEGMENT + '</r>', 'missing_target_tier'),
            (RECORD.replace('<tw>R</tw>', ''), 'empty_target_tier'),
            (RECORD, 'resolved'),
        ]
        for records, status in variants:
            with self.subTest(status=status):
                baseline = project_session(io.BytesIO(document(records=records)), "Synthetic_7", "s1")
                for value in ('PRIVATE_SENTINEL', 'NaN', '9999999999999999999999999'):
                    extra = '<userTier name="responseCorrect" value="' + value + '"><tierData><tw>' + value + '</tw><r id="' + value + '"><segment start="NaN"/></r><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier></tierData></userTier><orthography><w>' + value + '</w></orthography>'
                    mutated = project_session(io.BytesIO(document(records=records.replace('</r>', extra + '</r>'))), "Synthetic_7", "s1")
                    self.assertEqual(mutated, baseline)
                    self.assertEqual(mutated['records'][0]['targetMetadataStatus'], status)
                    self.assertNotIn('PRIVATE_SENTINEL', repr(mutated))


# These public-seam regressions were copied from the immutable v1 tests. Only
# the new status field and deliberately revised missing-target contract differ.
class BaselineProjectionRegressionTests(unittest.TestCase):
    def test_projects_completed_age_and_all_records_from_binary_stream(self):
        xml = b'''<session><participants><participant id="CHI"><age>P9Y3M</age>
        </participant></participants><transcript><r id="r1">
        <segment start="1.25" end="2.5" unit="s"/>
        <userTier name="ARPABET Target"><tierData><tw>B</tw><tw>AA1</tw></tierData></userTier>
        </r></transcript></session>'''
        result = project_session(io.BytesIO(xml), "Synthetic_7", "session_1")
        self.assertEqual(result["ageYears"], 9)
        self.assertEqual(result["records"], [{"recordId": "r1", "startSeconds": 1.25,
            "endSeconds": 2.5, "phones": ["B", "AA1"], "targetMetadataStatus": "resolved"}])
        self.assertEqual(result["counts"], {"records": 1, "phones": 2})

    def test_namespaced_wrapper_and_ignored_outcome_mutations_have_same_projection(self):
        template = '<session xmlns="urn:synthetic"><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r2"><segment start="0" end="1" unit="s"/><userTiers><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier><userTier name="responseCorrect" private="{value}"><tierData><tw>{value}</tw></tierData></userTier></userTiers><orthography><w>{value}</w></orthography></r></transcript></session>'
        first = project_session(io.BytesIO(template.format(value="SENTINEL_ONE").encode()), "Synthetic_7", "s1")
        second = project_session(io.BytesIO(template.format(value="TOTALLY_DIFFERENT_PRIVATE_VALUE").encode()), "Synthetic_7", "s1")
        self.assertEqual(first, second)
        self.assertEqual(first["records"][0]["phones"], ["R"])
        self.assertNotIn("SENTINEL", repr(first))
        self.assertEqual(first["flags"], {
            "coResidentXML": True, "outcomeValuesExtracted": False,
            "outcomeValuesInterpreted": False, "outcomeValuesRetained": False,
            "outcomeValuesLogged": False, "outcomeValuesExposed": False})

    def test_duplicate_target_tier_fails_with_fixed_code_without_private_values(self):
        xml = b'<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1"><segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R</tw></tierData></userTier><userTier name="ARPABET Target"><tierData><tw>PRIVATE_SENTINEL</tw></tierData></userTier></r></transcript></session>'
        with self.assertRaises(ProjectionError) as caught:
            project_session(io.BytesIO(xml), "Synthetic_7", "s1")
        self.assertEqual(caught.exception.code, "duplicate_target_tier")
        self.assertEqual(str(caught.exception), "duplicate_target_tier")

    def test_nested_target_markup_is_unresolved_structure(self):
        xml = b'<session><participants><participant id="CHI"><age>P9Y</age></participant></participants><transcript><r id="r1"><segment start="0" end="1" unit="s"/><userTier name="ARPABET Target"><tierData><tw>R<private>SECRET</private></tw></tierData></userTier></r></transcript></session>'
        with self.assertRaises(ProjectionError) as caught:
            project_session(io.BytesIO(xml), "Synthetic_7", "s1")
        self.assertEqual(caught.exception.code, "invalid_target_structure")

    def test_ambiguous_or_missing_structure_fails_closed(self):
        examples = [
            (document(age=AGE + AGE), "duplicate_chi_participant"),
            (document(age='<participant id="CHI"><age>P9Y</age><age>P9Y</age></participant>'), "duplicate_chi_age"),
            (document(records='<r id="r1">' + SEGMENT + SEGMENT + TARGET + '</r>'), "duplicate_segment"),
            (document(records=RECORD + RECORD), "duplicate_record_id"),
            (document(records='<r id="r1">' + TARGET + '</r>'), "missing_segment"),
            (document(age='<participant id="CHI"/>'), "missing_chi_age"),
            (document(age=''), "missing_chi_age"),
            (document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"/>' + '</r>'), "malformed_target_metadata"),
            (document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData/><tierData/></userTier></r>'), "invalid_target_structure"),
            (document(records='<r id="r1">' + SEGMENT + '<userTiers>' + TARGET + '</userTiers><userTiers/></r>'), "invalid_target_structure"),
            (document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tw>R</tw></userTier></r>'), "invalid_target_structure"),
            (document(records='<r id="r1">' + SEGMENT + '<r id="nested">' + SEGMENT + TARGET + '</r>' + TARGET + '</r>'), "invalid_record_structure"),
        ]
        for xml, code in examples:
            with self.subTest(code=code, index=examples.index((xml, code))):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(xml), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)

    def test_invalid_allowlisted_values_and_namespaces_have_fixed_errors(self):
        examples = [
            (document(age='<participant id="CHI"><age>P9Y12M</age></participant>'), "invalid_age"),
            (document(age='<participant id="CHI"><age>P9M</age></participant>'), "invalid_age"),
            (document(age='<participant id="CHI"><age>P-9Y</age></participant>'), "invalid_age"),
            (document(age='<participant id="CHI"><age>P9Y3M2Dgarbage</age></participant>'), "invalid_age"),
            (document(records=RECORD.replace('start="0"', 'start="NaN"')), "invalid_segment"),
            (document(records=RECORD.replace('end="1"', 'end="Infinity"')), "invalid_segment"),
            (document(records=RECORD.replace('start="0"', 'start="-1"')), "invalid_segment"),
            (document(records=RECORD.replace('end="1"', 'end="0"')), "invalid_segment"),
            (document(records=RECORD.replace('unit="s"', 'unit="ms"')), "invalid_segment"),
            (document(records=RECORD.replace('start="0"', '')), "invalid_segment"),
            (document(records=RECORD.replace('id="r1"', 'id="../PRIVATE_SENTINEL"')), "invalid_record_id"),
            (document(records=RECORD.replace('id="r1"', '')), "invalid_record_id"),
            (document(records=RECORD.replace('<r ', '<r xmlns="urn:other" ')), "namespace_ambiguity"),
            (document(records=RECORD.replace('id="r1"', 'xmlns:x="urn:other" x:id="r1"')), "namespace_ambiguity"),
        ]
        for index, (xml, code) in enumerate(examples):
            with self.subTest(index=index, code=code):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(xml), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)
        for folder, session in [("Synthetic_07", "s1"), ("Synthetic_0", "s1"), ("../Synthetic_7", "s1"), ("Synthetic_7", "../s1"), ("Sÿnthetic_7", "s1")]:
            with self.subTest(folder=folder, session=session):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(document()), folder, session)
                self.assertEqual(caught.exception.code, "invalid_identity")

    def test_forbidden_xml_declarations_and_malformed_streams_fail_without_snippets(self):
        examples = [
            (b'<!DOCTYPE session><session/>', "forbidden_xml_declaration"),
            (b'<!DOCTYPE session [<!ENTITY secret "PRIVATE_SENTINEL">]><session>' + AGE.encode() + b'&secret;</session>', "forbidden_xml_declaration"),
            (b'<!DOCTYPE session SYSTEM "file:///PRIVATE_SENTINEL"><session/>', "forbidden_xml_declaration"),
            (b'<!DOCTYPE session [<!ENTITY x SYSTEM "https://invalid.example/PRIVATE_SENTINEL">]><session>&x;</session>', "forbidden_xml_declaration"),
            (document()[:-1], "malformed_xml"),
            (b'<session>PRIVATE_SENTINEL</other>', "malformed_xml"),
            (document() + b'<session/>', "malformed_xml"),
            (b'\xff', "malformed_xml"),
            (b'<session>&unknown;</session>', "malformed_xml"),
        ]
        for index, (xml, code) in enumerate(examples):
            with self.subTest(index=index):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(xml), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)
        with self.assertRaises(ProjectionError) as caught:
            project_session(io.StringIO(document().decode()), "Synthetic_7", "s1")
        self.assertEqual(caught.exception.code, "invalid_stream")

    def test_fixed_resource_ceilings_accept_boundary_and_reject_overflow(self):
        phones = '<tw>R</tw>' * 512
        result = project_session(io.BytesIO(document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData>' + phones + '</tierData></userTier></r>')), "Synthetic_7", "s1")
        self.assertEqual(result["counts"], {"records": 1, "phones": 512})
        target_text = '<tw>' + 'R' * 4096 + '</tw>'
        result = project_session(io.BytesIO(document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData>' + target_text + '</tierData></userTier></r>')), "Synthetic_7", "s1")
        self.assertEqual(len(result["records"][0]["phones"][0]), 4096)
        deep = document(records='').replace(b'</session>', ('<ignored>' * 127 + '</ignored>' * 127 + '</session>').encode())
        self.assertEqual(project_session(io.BytesIO(deep), "Synthetic_7", "s1")["counts"]["records"], 0)
        many = ''.join(RECORD.replace('r1', 'r' + str(i)) for i in range(20000))
        self.assertEqual(project_session(io.BytesIO(document(records=many)), "Synthetic_7", "s1")["counts"]["records"], 20000)
        prefix = ('<session><participants>' + AGE + '</participants><transcript/><ignored>').encode()
        suffix = b'</ignored></session>'
        exact_size = prefix + b'X' * (16 * 1024 * 1024 - len(prefix) - len(suffix)) + suffix
        self.assertEqual(project_session(io.BytesIO(exact_size), "Synthetic_7", "s1")["counts"]["records"], 0)
        examples = [
            (exact_size + b' ', "entry_bytes_limit"),
            (document(records='').replace(b'</session>', ('<ignored>' * 128 + '</ignored>' * 128 + '</session>').encode()), "nesting_limit"),
            (document(records=many + RECORD.replace('r1', 'r20000')), "record_limit"),
            (document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData>' + phones + '<tw>R</tw></tierData></userTier></r>'), "phone_limit"),
            (document(records='<r id="r1">' + SEGMENT + '<userTier name="ARPABET Target"><tierData>' + target_text.replace('R' * 4096, 'R' * 4097) + '</tierData></userTier></r>'), "allowed_text_limit"),
            (document(age='<participant id="CHI"><age>P' + '9' * 4096 + 'Y</age></participant>'), "allowed_text_limit"),
            (document(records=RECORD.replace('id="r1"', 'id="' + 'r' * 4097 + '"')), "allowed_text_limit"),
        ]
        for index, (xml, code) in enumerate(examples):
            with self.subTest(index=index, code=code):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(xml), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)

    def test_short_binary_reads_and_entry_limit_probe_remain_bounded(self):
        class Chunked(io.BytesIO):
            def __init__(self, data, cap):
                super().__init__(data)
                self.cap = cap
                self.requests = []
                self.bytes_read = 0

            def read(self, size):
                self.requests.append(size)
                value = super().read(min(size, self.cap))
                self.bytes_read += len(value)
                return value

        xml = document(age='<participant id="CHI"><age>P9Y3M2D</age></participant>', records=RECORD.replace('<tw>R</tw>', '<tw>R</tw><tw>ER0</tw>'))
        reader = Chunked(xml, 1)
        result = project_session(reader, "Synthetic_7", "s1")
        self.assertEqual(result["ageYears"], 9)
        self.assertEqual(result["records"][0]["phones"], ["R", "ER0"])
        self.assertEqual(reader.bytes_read, len(xml))
        self.assertTrue(all(0 < size <= 65536 for size in reader.requests))
        prefix = ('<session><participants>' + AGE + '</participants><transcript/><ignored>').encode()
        beyond = prefix + b'X' * (16 * 1024 * 1024 + 65536) + b'</ignored></session>'
        reader = Chunked(beyond, 65536)
        with self.assertRaises(ProjectionError) as caught:
            project_session(reader, "Synthetic_7", "s1")
        self.assertEqual(caught.exception.code, "entry_bytes_limit")
        self.assertEqual(reader.bytes_read, 16 * 1024 * 1024 + 1)
        self.assertEqual(reader.requests[-1], 1)

    def test_preserves_target_text_and_every_record_without_eligibility_filtering(self):
        records = [
            RECORD,
            RECORD.replace('r1', 'r2').replace('<tw>R</tw>', '<tw>B</tw>'),
            RECORD.replace('r1', 'r3').replace('<tw>R</tw>', '<tw>R</tw><tw>R</tw>'),
            RECORD.replace('r1', 'r4').replace('<tw>R</tw>', '<tw>ER0</tw>'),
            RECORD.replace('r1', 'r5').replace('<tw>R</tw>', '<tw> R </tw>'),
            RECORD.replace('r1', 'r6').replace('<tw>R</tw>', ''),
        ]
        result = project_session(io.BytesIO(document(records=''.join(records))), "Synthetic_7", "s1")
        self.assertEqual([r["recordId"] for r in result["records"]], ["r1", "r2", "r3", "r4", "r5", "r6"])
        self.assertEqual([r["phones"] for r in result["records"]], [["R"], ["B"], ["R", "R"], ["ER0"], [" R "], []])
        self.assertEqual(result["counts"], {"records": 6, "phones": 6})

    def test_opaque_tier_values_are_not_validated_as_structural_attributes(self):
        outcome = '<userTier name="responseCorrect"><tierData><segment start="' + 'PRIVATE_SENTINEL' * 400 + '" end="NaN" unit="bad"/><participant id="CHI"><age>INVALID_PRIVATE_AGE</age></participant><tw>INVALID_PRIVATE_NUMBER</tw></tierData></userTier>'
        mutated = document(records=RECORD.replace('</r>', outcome + '</r>'))
        baseline = project_session(io.BytesIO(document()), "Synthetic_7", "s1")
        self.assertEqual(project_session(io.BytesIO(mutated), "Synthetic_7", "s1"), baseline)

    def test_projection_requires_documented_session_and_record_containers(self):
        examples = [
            (document().replace(b'<session>', b'<unknown>').replace(b'</session>', b'</unknown>'), "invalid_root"),
            (('<session>' + AGE + '<transcript>' + RECORD + '</transcript></session>').encode(), "invalid_participant_structure"),
            (('<session><participants>' + AGE + '</participants><records>' + RECORD + '</records></session>').encode(), "invalid_record_structure"),
            (document(records='<unknown>' + RECORD + '</unknown>'), "invalid_record_structure"),
            (document(records='<u id="r1"/>'), "invalid_record_structure"),
            (document(age='<unknown>' + AGE + '</unknown>'), "invalid_participant_structure"),
            (document(age='<participant id="CHI"><unknown><age>P9Y</age></unknown></participant>'), "invalid_age"),
            (document().replace(b'</participants>', b'</participants><participants/>'), "invalid_session_structure"),
            (document().replace(b'</transcript>', b'</transcript><transcript/>'), "invalid_session_structure"),
            (('<session><participants>' + AGE + '</participants></session>').encode(), "missing_session_structure"),
        ]
        for index, (xml, code) in enumerate(examples):
            with self.subTest(index=index, code=code):
                with self.assertRaises(ProjectionError) as caught:
                    project_session(io.BytesIO(xml), "Synthetic_7", "s1")
                self.assertEqual(caught.exception.code, code)

    def test_record_and_session_like_markup_inside_other_tier_is_opaque(self):
        extra = '<userTier name="responseCorrect"><tierData><r id="PRIVATE_SENTINEL"><segment start="NaN"/></r><session><participants><participant id="CHI"><age>BAD</age></participant></participants></session></tierData></userTier>'
        baseline = project_session(io.BytesIO(document()), "Synthetic_7", "s1")
        mutation = document(records=RECORD.replace('</r>', extra + '</r>'))
        self.assertEqual(project_session(io.BytesIO(mutation), "Synthetic_7", "s1"), baseline)

    def test_safe_dot_identities_preserve_the_closed_selector_contract(self):
        result = project_session(io.BytesIO(document(records=RECORD.replace('r1', 'record.1'))), "Synthetic.study_7", "session.1")
        self.assertEqual(result["records"][0]["recordId"], "record.1")
        for folder, session in [("..", "session.1"), ("Synthetic.study_7", ".."), ("Synthetic.study_7", ".")]:
            with self.assertRaises(ProjectionError) as caught:
                project_session(io.BytesIO(document()), folder, session)
            self.assertEqual(caught.exception.code, "invalid_identity")


if __name__ == '__main__':
    unittest.main()
