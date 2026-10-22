"""Small public-interface checks for audio preprocessing, CTC decoding and gradients."""
import tempfile
from pathlib import Path
import unittest
import wave

import numpy as np
import torch

from .runtime import read_audio, collapse
from .train_ctc import LSTMCTC


class RuntimeTests(unittest.TestCase):
    def test_ctc_blank_separates_repetitions(self):
        self.assertEqual(collapse([0, 1, 1, 0, 1, 2, 2, 0], {1: 'T', 2: 'S'}), ['T', 'T', 'S'])

    def test_audio_resampling_and_channel_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'clip.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(np.zeros(8000, dtype='<i2').tobytes())
            audio = read_audio(path)
            self.assertEqual(len(audio), 16000)
            self.assertEqual(audio.dtype, np.float32)
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(np.zeros(3200, dtype='<i2').tobytes())
            with self.assertRaises(ValueError):
                read_audio(path)

    def test_lstm_ctc_real_gradient_is_finite(self):
        torch.set_num_threads(2)
        torch.manual_seed(17)
        model = LSTMCTC()
        logits = model(torch.randn(20, 768))
        self.assertEqual(tuple(logits.shape), (20, 40))
        loss = torch.nn.CTCLoss()(logits.log_softmax(-1).unsqueeze(1),
                                 torch.tensor([1, 1, 2]), torch.tensor([20]), torch.tensor([3]))
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertGreater(model.head.weight.grad.abs().sum().item(), 0)
        self.assertTrue(torch.isfinite(model.lstm.weight_ih_l0.grad).all())

class SelectionGuardTests(unittest.TestCase):
    def test_completed_l2_evaluation_cannot_be_repeated(self):
        from unittest.mock import patch
        from . import train_ctc
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(train_ctc, 'OUTPUT', Path(folder)):
                (Path(folder)/'selected-result.json').write_text('{}')
                with self.assertRaises(FileExistsError):
                    train_ctc.select()


if __name__ == '__main__':
    unittest.main()
