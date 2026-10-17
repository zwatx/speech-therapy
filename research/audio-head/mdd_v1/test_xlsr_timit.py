"""Generated, model-free challenger contract checks; no external files."""
import math
import unittest

from . import xlsr_timit as adapter


def posterior(ids):
    return [[0.0 if token == value else -math.inf for token in range(44)] for value in ids]


def metadata():
    return dict(
        config={'architectures': ['Wav2Vec2ForCTC'], 'model_type': 'wav2vec2',
                '_name_or_path': 'facebook/wav2vec2-xls-r-300m',
                'vocab_size': 44, 'pad_token_id': 41, 'bos_token_id': 1, 'eos_token_id': 2,
                'hidden_size': 1024, 'num_hidden_layers': 24, 'num_attention_heads': 16,
                'feat_extract_norm': 'layer', 'do_stable_layer_norm': True, 'add_adapter': False},
        vocab={token: i for i, token in enumerate(
            ['|', 'ɑ', 'æ', 'ə', 'aʊ', 'aɪ', 'b', 'ʧ', 'd', 'ð', 'ɾ', 'ɛ', 'ɝ',
             'eɪ', 'f', 'g', ' ', 'h', 'ɪ', 'i', 'ʤ', 'k', 'l', 'm', 'n', 'ŋ',
             'oʊ', 'ɔɪ', 'p', 'ɹ', 's', 'ʃ', 't', 'θ', 'ʊ', 'u', 'v', 'w', 'j',
             'z', '[UNK]', '[PAD]'])},
        added_tokens={'<s>': 42, '</s>': 43},
        tokenizer={'tokenizer_class': 'Wav2Vec2CTCTokenizer', 'pad_token': '[PAD]',
                   'unk_token': '[UNK]', 'bos_token': '<s>', 'eos_token': '</s>',
                   'word_delimiter_token': '|', 'do_lower_case': False},
        preprocessor={'sampling_rate': 16000, 'do_normalize': True,
                      'feature_extractor_type': 'Wav2Vec2FeatureExtractor', 'feature_size': 1,
                      'padding_side': 'right', 'padding_value': 0.0, 'return_attention_mask': True},
    )


class ChallengerTests(unittest.TestCase):
    def test_all_ids_and_separate_accounting(self):
        values = tuple(range(41)) + (42, 43)
        result = adapter.project_sequence(values)
        expected_tokens = metadata()['vocab'] | metadata()['added_tokens']
        self.assertEqual(result.native_ids, values)
        self.assertEqual(result.native_tokens, tuple(sorted(expected_tokens, key=expected_tokens.get)[i]
                                                    for i in values))
        self.assertEqual(len(result.phones), 41)
        self.assertEqual(result.unsupported_tokens, ('ɾ', '[UNK]', '<s>', '</s>'))
        self.assertEqual(result.phones.count('<unk>'), 4)
        self.assertEqual((result.delimiter_count, result.space_count), (1, 1))
        self.assertEqual(len(adapter.PHONE_BY_TOKEN), 37)
        self.assertEqual(set(adapter.PHONE_BY_TOKEN.values()), set(
            'AA AE AH AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW V W Y Z'.split()))
        self.assertEqual(adapter.MISSING_PHONES, ('AO', 'ZH'))

    def test_zero_is_delimiter_and_config_bos_eos_are_vowels(self):
        result = adapter.collapse_frames([0, 0, 1, 1, 2, 41, 2, 16, 16, 42, 43])
        self.assertEqual(result.native_ids, (0, 1, 2, 2, 16, 42, 43))
        self.assertEqual(result.phones, ('AA', 'AE', 'AE', '<unk>', '<unk>'))
        self.assertEqual(result.unsupported_tokens, ('<s>', '</s>'))
        self.assertEqual(adapter.collapse_frames([41, 41]).native_ids, ())
        self.assertEqual(adapter.collapse_frames([]).phones, ())

    def test_collapsed_input_is_never_collapsed_again(self):
        self.assertEqual(adapter.project_sequence([32, 32]).phones, ('T', 'T'))
        self.assertEqual(adapter.collapse_frames([32, 32]).phones, ('T',))
        self.assertEqual(adapter.collapse_frames([32, 41, 32]).phones, ('T', 'T'))

    def test_diphthongs_aliases_and_flap(self):
        result = adapter.project_sequence([4, 5, 13, 26, 27, 15, 7, 20, 10])
        self.assertEqual(result.native_tokens, ('aʊ', 'aɪ', 'eɪ', 'oʊ', 'ɔɪ', 'g', 'ʧ', 'ʤ', 'ɾ'))
        self.assertEqual(result.phones, ('AW', 'AY', 'EY', 'OW', 'OY', 'G', 'CH', 'JH', '<unk>'))
        self.assertEqual(result.unsupported_tokens, ('ɾ',))

    def test_full_vocabulary_greedy(self):
        frames = [0, 1, 1, 41, 1, 2, 40, 42, 43, 16]
        self.assertEqual(adapter.decode_greedy(posterior(frames)), adapter.collapse_frames(frames))
        # Unknown/special output columns participate in argmax without pruning.
        rows = [[math.log(1 / 44)] * 44]
        self.assertEqual(adapter.decode_greedy(rows).native_ids, (0,))
        self.assertAlmostEqual(sum(math.exp(x) for x in adapter.validate_log_probabilities(rows)[0]), 1)

    def test_empty_shaped_input_and_width_contract(self):
        class Matrix(list):
            shape = (0, 44)

        self.assertEqual(adapter.decode_greedy(Matrix()).phones, ())
        for matrix in ([], [[0]], [[0] + [-math.inf] * 42], [[0] + [-math.inf] * 44]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                adapter.decode_greedy(matrix)

    def test_invalid_ids(self):
        for values in ([True], [1.0], ['1'], [-1], [44], None, 1):
            for method in (adapter.project_sequence, adapter.collapse_frames):
                with self.subTest(values=values, method=method), self.assertRaises(ValueError):
                    method(values)
        with self.assertRaises(ValueError):
            adapter.project_sequence([41])

    def test_normalization_and_nonfinite_admission(self):
        for row in ([[0] * 44, [math.nan] + [-math.inf] * 43,
                     [math.inf] + [-math.inf] * 43, [-math.inf] * 44]):
            with self.subTest(row=row), self.assertRaises(ValueError):
                adapter.decode_greedy([row])
        row = [[0.001] + [-math.inf] * 43]
        with self.assertRaises(ValueError):
            adapter.decode_greedy(row)
        self.assertEqual(adapter.decode_greedy(row, normalization_tolerance=0.01).native_ids, (0,))

    def test_metadata_contract_and_mismatches(self):
        adapter.validate_metadata(**metadata())
        changes = [('config', 'pad_token_id', 0), ('config', 'vocab_size', 42),
                   ('config', 'bos_token_id', 42), ('config', 'eos_token_id', 43),
                   ('tokenizer', 'pad_token', '|'), ('tokenizer', 'word_delimiter_token', ' '),
                   ('preprocessor', 'do_normalize', False), ('preprocessor', 'sampling_rate', 8000),
                   ('vocab', 'ɑ', 42), ('vocab', 'ɑ', True), ('added_tokens', '<s>', 1)]
        for section, field, value in changes:
            document = metadata()
            document[section][field] = value
            with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                adapter.validate_metadata(**document)
        document = metadata()
        del document['preprocessor']['return_attention_mask']
        with self.assertRaises(ValueError):
            adapter.validate_metadata(**document)


if __name__ == '__main__':
    unittest.main()
