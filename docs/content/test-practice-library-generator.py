"""Focused source parser checks; run directly with Python 3."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "practice_generator", Path(__file__).with_name("generate-practice-library.py")
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PracticeLibraryGeneratorTests(unittest.TestCase):
    def test_annotation_does_not_shift_final_phone_or_leak_into_pronunciation(self):
        # Mirrors a real annotated CMUdict entry, not a selected practice word.
        dictionary = generator.parse_dictionary(
            b"# header\naalborg AO1 L B AO0 R G # place, danish\n"
            b"aalborg(2) AA1 L B AO0 R G\n"
        )
        variants = dictionary["aalborg"]
        self.assertEqual(variants, [
            ["AO", "L", "B", "AO", "R", "G"],
            ["AA", "L", "B", "AO", "R", "G"],
        ])
        for phones in variants:
            self.assertIn("g:end", generator.targets(phones))
            self.assertNotIn("g:middle", generator.targets(phones))
        self.assertEqual(set(dictionary), {"aalborg"})

    def test_source_hash_mismatch_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incorrect.dict"
            path.write_text("cat K AE1 T\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                generator.read_dictionary(path)

    def test_absent_word_is_rejected_without_fabricated_pronunciation(self):
        with self.assertRaisesRegex(ValueError, "absent from CMUdict"):
            generator.generate(["unlistedword"], {})


if __name__ == "__main__":
    unittest.main()
