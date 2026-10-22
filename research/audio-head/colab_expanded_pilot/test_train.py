"""Unit tests for train.py helpers; no model download or GPU required."""
import io
import math
import unittest
import wave

import numpy as np
import torch

import train


def payload():
    """23 fit phones over two clips of speaker A (phone 5 repeated in c0) and a
    selection clip of speaker B holding two occurrences of phone 3."""
    clips = [{"id": f"c{k}", "wav": f"wav/c{k}.wav", "sampleCount": 16000, "frames": 49} for k in range(3)]
    rows = []

    def add(clip, speaker, target, window, counts=(3, 1, 1)):
        rows.append({"rowIndex": len(rows), "id": f"r{len(rows)}", "clipId": clip, "speakerId": speaker,
                     "age": 8, "targetId": target, "targetPhone": f"p{target}",
                     "raterCounts": list(counts), "window": list(window)})

    for target in range(23):
        add("c0" if target < 12 else "c1", "A", target, (target, target + 2))
    add("c0", "A", 5, (30, 34))
    add("c2", "B", 3, (0, 5))
    add("c2", "B", 3, (10, 15), (0, 2, 3))
    return {"rows": rows, "clips": clips, "fitRows": list(range(24)), "selectionRows": [24, 25]}


class ValidateRowsTest(unittest.TestCase):
    def validate(self, data):
        return train.validate_rows(data, with_splits=True, selection_rows=2)

    def test_repeated_targets_are_accepted_as_separate_rows(self):
        result = self.validate(payload())
        self.assertEqual(result["fit"], list(range(24)))
        self.assertEqual(result["sel"], [24, 25])
        self.assertEqual(sum(row["targetId"] == 5 for row in result["rows"]), 2)

    def test_global_row_ids_map_to_feature_positions_without_reordering(self):
        data = payload()
        ids = [500 + i * 7 for i in range(len(data["rows"]))]
        for row, global_id in zip(data["rows"], ids): row["rowIndex"] = global_id
        data["fitRows"] = ids[:24]
        data["selectionRows"] = ids[24:]
        result = self.validate(data)
        self.assertEqual(result["fit"], list(range(24)))
        self.assertEqual(result["sel"], [24, 25])
        self.assertEqual(result["rows"][24]["rowIndex"], ids[24])
        data["rows"][1]["rowIndex"] = ids[0]
        with self.assertRaises(train.StageError): self.validate(data)

    def test_speaker_shared_across_fit_and_selection_is_rejected(self):
        data = payload()
        for row in data["rows"][24:]:
            row["speakerId"] = "A"
        with self.assertRaisesRegex(train.StageError, "speakerId"):
            self.validate(data)

    def test_invalid_windows_and_soft_labels_are_rejected(self):
        cases = [("window", [4, 4]), ("window", [40, 50]), ("window", [-1, 3]),
                 ("raterCounts", [2, 2, 2]), ("raterCounts", [6, -1, 0]),
                 ("raterCounts", [5, 0]), ("raterCounts", [2.5, 2.5, 0])]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                data = payload()
                data["rows"][3][key] = value
                with self.assertRaises(train.StageError):
                    self.validate(data)


class ScoreTest(unittest.TestCase):
    def test_known_values_and_empty_phone_cells(self):
        logp = np.log([[0.5, 0.25, 0.25], [1 / 3, 1 / 3, 1 / 3], [0.25, 0.25, 0.5]])
        result = train.score(logp, [[5, 0, 0], [5, 0, 0], [0, 0, 5]], [0, 0, 2])
        ln2, ln3 = math.log(2), math.log(3)
        self.assertAlmostEqual(result["nll"], (2 * ln2 + ln3) / 3)
        self.assertAlmostEqual(result["macroPhoneNll"], ((ln2 + ln3) / 2 + ln2) / 2)
        self.assertAlmostEqual(result["brier"], (0.375 + 2 / 3 + 0.375) / 3)
        self.assertEqual(len(result["perPhone"]), 23)
        self.assertEqual(result["perPhone"][1], {"targetId": 1, "rows": 0, "votes": [0, 0, 0], "nll": None})
        self.assertEqual(result["perPhone"][0]["votes"], [10, 0, 0])


    def test_brier_averages_individual_rater_outcomes(self):
        result = train.score(np.log([[.2,.3,.5]]), [[1,2,2]], [0])
        expected = sum(weight * sum((p - float(k == outcome))**2 for k,p in enumerate([.2,.3,.5]))
                       for outcome,weight in enumerate([.2,.4,.4]))
        self.assertAlmostEqual(result["brier"], expected)


class EpochSelectionTest(unittest.TestCase):
    def test_ties_choose_earliest_and_epoch_zero_is_eligible(self):
        self.assertEqual(train.select_epoch([1.0, 0.5, 0.5, 0.7]), 1)
        self.assertEqual(train.select_epoch([0.3, 0.3, 0.4]), 0)

    def test_patience_counts_epochs_since_first_best(self):
        self.assertFalse(train.should_stop([1.0, 0.9, 0.9, 0.95, 0.92], 4))
        self.assertTrue(train.should_stop([1.0, 0.9, 0.9, 0.95, 0.92, 0.91], 4))


class PoolingTest(unittest.TestCase):
    def test_half_open_windows_and_repeated_phone_rows(self):
        hidden = torch.arange(12, dtype=torch.float32).view(6, 2)
        pooled = train.pool_windows(hidden, [(0, 2), (1, 4), (1, 4)])
        torch.testing.assert_close(pooled, torch.tensor([[1.0, 2.0], [4.0, 5.0], [4.0, 5.0]]))

        torch.manual_seed(0)
        head = train.MeanPoolPhoneRatingHead(feature_dim=train.FEATURE_DIM, num_phones=23,
                                             hidden_dim=128, dropout=0.1).eval()
        vectors = torch.randn(1, train.HIDDEN).repeat(3, 1)
        scalars = torch.randn(1, train.NUM_SCALARS).repeat(3, 1)
        mean, std = torch.randn(train.FEATURE_DIM), torch.rand(train.FEATURE_DIM) + 0.5
        logits = train.pooled_logits(head, vectors, scalars, mean, std, torch.tensor([7, 7, 2]))
        self.assertEqual(tuple(logits.shape), (3, 3))
        torch.testing.assert_close(logits[0], logits[1])
        self.assertFalse(torch.equal(logits[0], logits[2]))


class WavAndPathTest(unittest.TestCase):
    @staticmethod
    def wav_bytes(samples, channels=1, rate=16000):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(np.asarray(samples, dtype="<i2").tobytes())
        return buffer.getvalue()

    def test_pcm16_mono_scaling_and_rejections(self):
        audio = train.read_wav(self.wav_bytes([0, 16384, -32768]), 3)
        np.testing.assert_array_equal(audio, np.array([0.0, 0.5, -1.0], dtype=np.float32))
        bad = [(self.wav_bytes([0, 1, 2, 3], channels=2), 2), (self.wav_bytes([0, 1], rate=8000), 2),
               (self.wav_bytes([0, 1]), 3)]
        for data, count in bad:
            with self.subTest(count=count), self.assertRaises(train.StageError):
                train.read_wav(data, count)

    def test_unsafe_bundle_paths_are_rejected(self):
        for rel in ("../x.wav", "/abs.wav", "wav/../../x", "wav\\x.wav", "wav//x.wav", "", None):
            with self.subTest(rel=rel), self.assertRaises(train.StageError):
                train.safe_relpath(rel)
        self.assertEqual(train.safe_relpath("wav/c0.wav"), "wav/c0.wav")


if __name__ == "__main__":
    unittest.main()
