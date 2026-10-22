import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_ctc_parity import export_cases, synthetic_cases, validate_explicit_entries, verify_cases
from data import AUTHORITY, BLANK


class CtcParityTests(unittest.TestCase):
    def test_explicit_entries_require_complete_distinct_recording_grid(self):
        entries = [[run, "manifest.json", recording, f"{run}/{recording}.json"]
                   for run in ("wav2vec2", "wavlm") for recording in ("recording-a", "recording-b")]
        self.assertEqual(validate_explicit_entries(entries), ["recording-a", "recording-b"])
        for invalid in (entries[:-1], entries + [entries[0]],
                        [[row[0], "other-manifest.json" if i == 0 else row[1], *row[2:]]
                         for i, row in enumerate(entries)]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_explicit_entries(invalid)

    def test_explicit_export_binds_recording_id_to_verified_audio(self):
        run = {"checkpointSha256": "checkpoint", "encoder": {"kind": "wav2vec2-base"},
               "labelSource": "automatic-phone-alignment", "splitIdentityBasis": "speaker-disjoint-households-unknown",
               "vocabulary": [BLANK, "a"]}
        row = {"id": "recording-a", "audioSha256": "audio", "split": "test", "targetPhones": ["a"]}
        exported = {"schemaVersion": 1, "purpose": "engineering-inference", "calibrated": False,
                    "blankToken": BLANK, "audioSha256": "audio", "frames": [{BLANK: .4, "a": .6}],
                    **{key: run[key] for key in ("checkpointSha256", "encoder", "labelSource", "splitIdentityBasis")},
                    **AUTHORITY}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.json"
            path.write_text("{}")
            with (patch("check_ctc_parity.load_run", return_value=run),
                  patch("check_ctc_parity.load_manifest", return_value=({}, [row])),
                  patch("check_ctc_parity.read_json", return_value=exported)):
                cases, evidence = export_cases(Path(temporary), path, path, "recording-a")
                self.assertEqual(evidence["recordingId"], "recording-a")
                self.assertEqual(len(cases), 2)
                self.assertTrue(all("recording-a" in case["id"] for case in cases))
                with self.assertRaisesRegex(ValueError, "verified held-out recording"):
                    export_cases(Path(temporary), path, path, "recording-b")
                exported["calibrated"] = True
                with self.assertRaisesRegex(ValueError, "checkpoint provenance"):
                    export_cases(Path(temporary), path, path, "recording-a")

    def test_real_typescript_scorer_matches_torch_and_rejects_invalid_inputs(self):
        checks = verify_cases(synthetic_cases())
        self.assertEqual(len(checks), 14)
        self.assertEqual(sum(check.get("impossible", False) for check in checks), 2)
        self.assertEqual(sum(check.get("rejected", False) for check in checks), 4)
        self.assertLess(max(check.get("absoluteDifference", 0) for check in checks), 1e-8)

    def test_oracle_mismatch_and_nonfinite_results_fail(self):
        case = synthetic_cases()[0]
        for incorrect in (0.0, float("nan"), float("inf")):
            with self.subTest(oracle=incorrect), patch("check_ctc_parity.torch_log_probability", return_value=incorrect):
                with self.assertRaises(ValueError):
                    verify_cases([case])

    def test_rejection_case_cannot_pass_with_valid_input(self):
        case = copy.deepcopy(synthetic_cases()[0])
        case["expectRejection"] = True
        with self.assertRaisesRegex(ValueError, "Invalid input was accepted"):
            verify_cases([case])


if __name__ == "__main__":
    unittest.main()
