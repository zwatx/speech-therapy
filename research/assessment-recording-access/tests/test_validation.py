from copy import deepcopy
import struct
import unittest

from recording_access import VaultError, inspect_wav, validate_declaration
from recording_access.models import strict_json
from test_vault import pcm, declaration


class ValidationTests(unittest.TestCase):
    def test_pcm_format_frame_bound_and_complete_riff_are_enforced(self):
        raw = pcm()
        for changed in (raw + b'garbage', raw[:-1], b'x' * 132097,
                        raw[:22] + struct.pack('<H', 2) + raw[24:],
                        raw[:24] + struct.pack('<I', 44100) + raw[28:]):
            with self.subTest(length=len(changed)), self.assertRaises(VaultError):
                inspect_wav(changed)
        self.assertEqual(inspect_wav(raw)['frames'], 3200)

    def test_duplicate_nonfinite_large_surrogate_and_non_utf8_json_are_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'"\\ud800"',
                    b'\xff', b'1' * 129, b' ' * (8 * 1024 * 1024 + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(VaultError):
                strict_json(raw)

    def test_bool_integer_spoof_and_extra_missing_fields_cannot_enter_declarations(self):
        original = declaration(pcm())
        for key in ('schemaVersion', 'retainUntil'):
            changed = deepcopy(original)
            changed[key] = True
            with self.subTest(key=key), self.assertRaises(VaultError):
                validate_declaration(changed)
        changed = deepcopy(original)
        changed['subject']['ageYears'] = True
        with self.assertRaises(VaultError):
            validate_declaration(changed)
        for operation in ('extra', 'missing'):
            changed = deepcopy(original)
            if operation == 'extra':
                changed['verified'] = True
            else:
                del changed['permissions']['research']
            with self.assertRaises(VaultError):
                validate_declaration(changed)
