import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data import AUTHORITY, BLANK, digest, load_manifest, load_pcm, make_fixtures, read_json, write_json
from import_arctic import Downloader, import_corpus
from arctic_profiles import PROFILES, validate_profile_selection
from labels import parse_alignment
from pipeline import edit_distance, load_head, train


class PublicSpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = make_fixtures(self.root / "fixtures")
        original = read_json(self.path)
        items, files, selected = [], {}, []
        for split, speaker in zip(("train", "calibration", "test"), ("bdl", "rms", "slt")):
            item = copy.deepcopy(next(row for row in original["items"] if row["split"] == split))
            directory = self.path.parent / speaker
            directory.mkdir()
            utterance = "arctic_a0001"
            audio = directory / f"{utterance}.wav"
            audio.write_bytes((self.path.parent / item["audioPath"]).read_bytes())
            duration = len(load_pcm(audio)) / 16000
            alignment = audio.with_suffix(".lab")
            alignment.write_text(f"#\n{duration:.8f} 125 aa\n")
            item.pop("producedPhones")
            item.update({"pseudoPhones": ["aa"], "householdHash": None,
                         "id": f"cmu-{speaker}-{utterance}", "audioPath": f"{speaker}/{audio.name}",
                         "speakerHash": digest(f"cmu-arctic-speaker:{speaker}".encode()),
                         "alignmentPath": f"{speaker}/{alignment.name}", "alignmentSha256": digest(alignment.read_bytes())})
            items.append(item)
            selected.append({"speaker": speaker, "utterance": utterance, "split": split})
            for p in (audio, alignment):
                files[f"{speaker}/{p.name}"] = {"sha256": digest(p.read_bytes())}
        lock = self.path.parent / "source-lock.json"
        write_json(lock, {"corpus": "cmu-arctic-0.95", "labelSource": "automatic-phone-alignment", "files": files, "selected": selected})
        self.manifest = {"schemaVersion": 2, "purpose": "public-speech-engineering",
                         "labelSource": "automatic-phone-alignment", "splitIdentityBasis": "speaker-disjoint-households-unknown",
                         "sourceLockSha256": digest(lock.read_bytes()), "vocabulary": [BLANK, "aa"], "items": items, **AUTHORITY}

    def validate(self):
        write_json(self.path, self.manifest)
        return load_manifest(self.path)

    def test_automatic_alignment_is_distinct_from_produced_phones(self):
        _, rows = self.validate()
        self.assertEqual(rows[0]["targetPhones"], ["aa"])
        self.assertNotIn("producedPhones", rows[0])
        self.manifest["labelSource"] = "produced-phones"
        with self.assertRaisesRegex(ValueError, "automatic labels"):
            self.validate()

    def test_unknown_households_cannot_be_fabricated(self):
        self.manifest["items"][0]["householdHash"] = "1" * 64
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.validate()

    def test_speaker_leakage_still_rejected(self):
        self.manifest["items"][-1]["speakerHash"] = self.manifest["items"][0]["speakerHash"]
        with self.assertRaisesRegex(ValueError, "differs from source lock"):
            self.validate()

    def test_split_and_speaker_relabel_cannot_hide_corpus_leakage(self):
        self.manifest["items"][0]["split"] = "test"
        self.manifest["items"][0]["speakerHash"] = digest(b"wrong-per-recording-identity")
        with self.assertRaisesRegex(ValueError, "differs from source lock"):
            self.validate()

    def test_alignment_must_pair_with_the_same_locked_recording(self):
        self.manifest["items"][0]["alignmentPath"] = self.manifest["items"][-1]["alignmentPath"]
        with self.assertRaisesRegex(ValueError, "differs from source lock"):
            self.validate()

    def test_label_and_lock_tampering_rejected(self):
        self.manifest["vocabulary"].append("b")
        self.manifest["items"][0]["pseudoPhones"] = ["b"]
        with self.assertRaisesRegex(ValueError, "differ from source alignment"):
            self.validate()
        self.manifest["items"][0]["pseudoPhones"] = ["aa"]
        self.manifest["sourceLockSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source-lock SHA-256"):
            self.validate()

    def test_modified_alignment_file_rejected(self):
        item = self.manifest["items"][0]
        (self.path.parent / item["alignmentPath"]).write_text("#\n0.1 125 aa\n")
        with self.assertRaisesRegex(ValueError, "Alignment SHA-256"):
            self.validate()

    def test_alignment_parser_rejects_invalid_boundaries_and_tokens(self):
        for body in [b"#\n0.2 125 aa\n0.1 125 b\n", b"#\nNaN 125 aa\n", b"#\n1 125 unknown\n", b"#\n0.1 125 aa\n"]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_alignment(body, 1)

    def test_download_budget_and_allowlist_fail_before_network(self):
        with patch("urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "budget"):
                Downloader(10).fetch("bdl", "COPYING", 11)
            with self.assertRaisesRegex(ValueError, "Unapproved"):
                Downloader().fetch("bdl", "../../secret", 100)
            request.assert_not_called()

    def test_expansion_requires_a_locked_holdout_before_network(self):
        with patch("urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "previously recorded holdout"):
                import_corpus(self.root / "expanded", profile="four-speaker-v1")
            request.assert_not_called()
            self.assertFalse((self.root / "expanded").exists())

    def test_profile_locks_counts_speakers_and_disjoint_prompt_ranges(self):
        selected = [{"speaker": speaker, "split": split, "utterance": f"arctic_a{i:04d}"}
                    for speaker, (split, first, _, count) in PROFILES["four-speaker-v1"].items()
                    for i in range(first, first + count)]
        validate_profile_selection(selected, "four-speaker-v1")
        for changed in (selected[:-1], [*selected, selected[0]],
                        [{**selected[0], "utterance": "arctic_a0101"}, *selected[1:]],
                        [{**selected[0], "split": "test"}, *selected[1:]]):
            with self.subTest(changed=changed[0]), self.assertRaises(ValueError):
                validate_profile_selection(changed, "four-speaker-v1")

    def test_token_edit_rate_math(self):
        self.assertEqual(edit_distance(["aa", "b", "aa"], ["aa", "aa"]), 1)
        self.assertEqual(edit_distance(["aa"], ["b", "aa"]), 1)
        self.assertEqual(edit_distance(["aa"], ["b"]), 1)
        self.assertEqual(edit_distance(["aa"], []), 1)

    def test_label_provenance_survives_training_and_cannot_be_promoted(self):
        self.validate()
        # Use the tiny deterministic feature extractor only as a mocked test dependency.
        from encoders import SpectralEncoder
        with patch("pipeline.load_encoder", return_value=SpectralEncoder()):
            report = train(self.path, self.root / "run", "wav2vec2-base", self.root / "cache", steps=2)
        self.assertEqual(report["labelSource"], "automatic-phone-alignment")
        self.assertEqual(report["splitIdentityBasis"], "speaker-disjoint-households-unknown")
        self.assertIs(report["productionEligible"], False)
        checkpoint = self.root / "run" / "checkpoint.json"
        changed = read_json(checkpoint)
        changed["labelSource"] = "produced-phones"
        write_json(checkpoint, changed)
        with self.assertRaisesRegex(ValueError, "automatic-label"):
            load_head(checkpoint.parent)


if __name__ == "__main__":
    unittest.main()
