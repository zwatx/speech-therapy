import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

from speechocean_r_annotation_sample import (QUEUE_FIELDS, blinded_queue, load_recipe,
                                             private_directory, require_real_generated_path, select_sample,
                                             verify_selected_wavs, write_json)


class SelectionTests(unittest.TestCase):
    def test_locked_recipe_is_train_only_and_research_only(self):
        recipe = load_recipe()
        self.assertEqual(recipe["authorPartition"], "train")
        self.assertEqual(recipe["clipsPerStratum"], 10)
        self.assertTrue(recipe["distinctSpeakersAcrossSample"])
        self.assertTrue(all(recipe[key] is False for key in (
            "productionEligible", "calibrationEligible", "learnerFeedbackEligible",
            "clinicalUseEligible", "annotationComplete")))

    def test_sample_is_deterministic_and_rejects_speaker_reuse(self):
        recipe = load_recipe()
        rows = []
        for stratum_index, stratum in enumerate(recipe["strataOrder"]):
            for number in range(12):
                rows.append({"sourceId": f"{stratum_index:02d}{number:07d}",
                             "speakerId": "shared" if number == 0 else f"{stratum_index:02d}-{number:02d}",
                             "stratum": stratum})
        first = select_sample(rows, recipe)
        second = select_sample(list(reversed(rows)), recipe)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 40)
        self.assertEqual(len({row["speakerId"] for row in first}), 40)
        self.assertEqual({s: sum(row["stratum"] == s for row in first)
                          for s in recipe["strataOrder"]}, {s: 10 for s in recipe["strataOrder"]})
        with self.assertRaisesRegex(ValueError, "Duplicate candidate"):
            select_sample(rows + [rows[0]], recipe)


class BlindingTests(unittest.TestCase):
    def test_queue_has_only_opaque_id_and_target_fields(self):
        selected = [{"sourceId": "000010011", "speakerId": "0001", "age": 9,
                     "aggregateRScore": 0.4, "fiveRaterScores": [0, 0, 0, 0, 2],
                     "stratum": "child.belowCeiling", "targetPrompt": "SAY BEAR",
                     "targetWord": "BEAR", "wordIndexZeroBased": 1,
                     "phoneIndexWithinWordZeroBased": 2}]
        queue = blinded_queue(selected, b"q" * 32)
        item = queue["items"][0]
        self.assertEqual(set(item), QUEUE_FIELDS)
        self.assertEqual(len(item["reviewerId"]), 16)
        self.assertNotEqual(item["reviewerId"], selected[0]["sourceId"])
        encoded = json.dumps(queue)
        for forbidden in ("000010011", "speakerId", "age", "aggregateRScore", "fiveRaterScores", "wavSha256"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(queue, blinded_queue(selected, b"q" * 32))

    def test_generated_json_and_directory_are_private_on_create_and_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "generated"
            root.mkdir(mode=0o755)
            output = root / "internal-manifest.json"
            write_json(output, {"blindingKeyHex": "synthetic"})
            private_directory(root)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

            root.chmod(0o755)
            output.chmod(0o644)
            write_json(output, {"blindingKeyHex": "updated-synthetic"})
            private_directory(root)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(list(root.glob(".annotation-*.tmp")), [])

            link = root / "linked.json"
            link.symlink_to(output)
            with self.assertRaisesRegex(ValueError, "symlink"):
                write_json(link, {"unexpected": True})
            self.assertEqual(json.loads(output.read_text()),
                             {"blindingKeyHex": "updated-synthetic"})

            redirected = Path(directory) / "redirected"
            redirected.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                require_real_generated_path(redirected / "internal-manifest.json",
                                            Path(directory))


class SourceVerificationTests(unittest.TestCase):
    def test_changed_extracted_wav_is_rejected_against_pinned_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "speechocean762"
            wav = audio / "WAVE/SPEAKER0001/000010011.WAV"
            wav.parent.mkdir(parents=True)
            with wave.open(str(wav), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(np.zeros(16000, dtype="<i2").tobytes())
            mapping = audio / "train/wav.scp"
            mapping.parent.mkdir(parents=True)
            mapping.write_text("000010011 WAVE/SPEAKER0001/000010011.WAV\n" +
                               "".join(f"{i:09d} WAVE/SPEAKER0002/{i:09d}.WAV\n"
                                       for i in range(1, 2500)))
            archive = root / "audio.tar.gz"
            payload = wav.read_bytes()
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("speechocean762/WAVE/SPEAKER0001/000010011.WAV")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            selected = [{"sourceId": "000010011", "speakerId": "0001"}]
            with patch("speechocean_r_annotation_sample.ARCHIVE_SHA256",
                       hashlib.sha256(archive.read_bytes()).hexdigest()):
                self.assertEqual(len(verify_selected_wavs(selected, archive, audio)), 1)
                with wave.open(str(wav), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(16000)
                    output.writeframes(np.ones(16000, dtype="<i2").tobytes())
                with self.assertRaisesRegex(ValueError, "differs from pinned archive"):
                    verify_selected_wavs(selected, archive, audio)


if __name__ == "__main__":
    unittest.main()
