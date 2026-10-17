"""Model-free research adapter for one pinned XLS-R/TIMIT challenger.

No weight loading or waveform processing. Decode native IDs before projecting
phones; the model config's BOS/EOS IDs 1/2 are phones, not removable specials.
"""
from dataclasses import dataclass

from .prefix_decode import _integer, _validated, greedy_decode

MODEL_ID = 'vitouphy/wav2vec2-xls-r-300m-timit-phoneme'
REVISION = 'efb7ae9b88f13db0d42eac8cedbba19739e2a278'
BLANK_ID = 41
NATIVE_TOKENS = (
    '|', 'ɑ', 'æ', 'ə', 'aʊ', 'aɪ', 'b', 'ʧ', 'd', 'ð', 'ɾ', 'ɛ', 'ɝ',
    'eɪ', 'f', 'g', ' ', 'h', 'ɪ', 'i', 'ʤ', 'k', 'l', 'm', 'n', 'ŋ',
    'oʊ', 'ɔɪ', 'p', 'ɹ', 's', 'ʃ', 't', 'θ', 'ʊ', 'u', 'v', 'w', 'j',
    'z', '[UNK]', '[PAD]', '<s>', '</s>',
)
VOCAB_SIZE = len(NATIVE_TOKENS)
MISSING_PHONES = ('AO', 'ZH')
# Exact token aliases only; notably flap ɾ is not folded into T or D.
PHONE_BY_TOKEN = dict(zip(
    'ɑ æ ə aʊ aɪ b ʧ d ð ɛ ɝ eɪ f g h ɪ i ʤ k l m n ŋ oʊ ɔɪ p ɹ s ʃ t θ ʊ u v w j z'.split(),
    'AA AE AH AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW V W Y Z'.split(),
))


@dataclass(frozen=True)
class Projection:
    native_ids: tuple[int, ...]
    native_tokens: tuple[str, ...]
    phones: tuple[str, ...]
    unsupported_tokens: tuple[str, ...]
    delimiter_count: int
    space_count: int


def _ids(values, *, allow_blank):
    try:
        result = tuple(_integer(value, 'native ID') for value in values)
    except TypeError as error:
        raise ValueError('native IDs must be an iterable of integers') from error
    if any(value < 0 or value >= VOCAB_SIZE or (value == BLANK_ID and not allow_blank)
           for value in result):
        raise ValueError('native IDs must index the 44-token vocabulary; collapsed IDs exclude blank')
    return result


def project_sequence(native_ids):
    """Project already-collapsed IDs; adjacent repeated phones remain repeated.

    Only delimiter ID 0 and space ID 16 are omitted from phone scoring. Flap,
    unknown and added specials each contribute <unk> and an unsupported token.
    """
    ids = _ids(native_ids, allow_blank=False)
    tokens = tuple(NATIVE_TOKENS[value] for value in ids)
    phones, unsupported = [], []
    for value, token in zip(ids, tokens):
        if value in (0, 16):
            continue
        phone = PHONE_BY_TOKEN.get(token)
        phones.append(phone if phone is not None else '<unk>')
        if phone is None:
            unsupported.append(token)
    return Projection(ids, tokens, tuple(phones), tuple(unsupported), ids.count(0), ids.count(16))


def collapse_frames(frame_ids):
    """CTC-collapse frame IDs with blank 41, then project the native sequence."""
    frames = _ids(frame_ids, allow_blank=True)
    collapsed, previous = [], None
    for value in frames:
        if value != previous and value != BLANK_ID:
            collapsed.append(value)
        previous = value
    return project_sequence(collapsed)


def validate_log_probabilities(log_probs, *, normalization_tolerance=1e-5):
    """Admit normalized T-by-44 natural-log posteriors without renormalizing.

    An empty plain sequence has unknown width and is rejected. A shaped (0,44)
    matrix is admitted without needing an array-library dependency.
    """
    rows, _ = _validated(log_probs, BLANK_ID, normalization_tolerance)
    shape = getattr(log_probs, 'shape', None)
    width = len(rows[0]) if rows else (shape[1] if shape is not None else None)
    if width != VOCAB_SIZE:
        raise ValueError('challenger log probabilities must have exactly 44 columns')
    return rows


def decode_greedy(log_probs, *, normalization_tolerance=1e-5):
    """Decode the full native vocabulary using the shared independent helper."""
    rows = validate_log_probabilities(log_probs, normalization_tolerance=normalization_tolerance)
    ids = greedy_decode(rows, blank_id=BLANK_ID, normalization_tolerance=normalization_tolerance)
    return project_sequence(ids)


def validate_metadata(*, config, vocab, added_tokens, tokenizer, preprocessor):
    """Check provided public metadata against the pinned adapter contract.

    This checks interpretation fields, not artifact identity or weight bytes;
    callers must separately verify revision and source hashes. Unrelated model
    settings are left to the official runtime. No metadata files are loaded here.
    """
    contracts = (
        (config, {'architectures': ['Wav2Vec2ForCTC'], 'model_type': 'wav2vec2',
                  '_name_or_path': 'facebook/wav2vec2-xls-r-300m',
                  'vocab_size': 44, 'pad_token_id': 41, 'bos_token_id': 1,
                  'eos_token_id': 2, 'hidden_size': 1024, 'num_hidden_layers': 24,
                  'num_attention_heads': 16, 'feat_extract_norm': 'layer',
                  'do_stable_layer_norm': True, 'add_adapter': False}),
        (tokenizer, {'tokenizer_class': 'Wav2Vec2CTCTokenizer', 'pad_token': '[PAD]',
                     'unk_token': '[UNK]', 'bos_token': '<s>', 'eos_token': '</s>',
                     'word_delimiter_token': '|', 'do_lower_case': False}),
        (preprocessor, {'sampling_rate': 16000, 'do_normalize': True,
                        'feature_extractor_type': 'Wav2Vec2FeatureExtractor',
                        'feature_size': 1, 'padding_side': 'right',
                        'padding_value': 0.0, 'return_attention_mask': True}),
    )
    for actual, expected in contracts:
        if not isinstance(actual, dict):
            raise ValueError('metadata must be dictionaries')
        for key, value in expected.items():
            if key not in actual or type(actual[key]) is not type(value) or actual[key] != value:
                raise ValueError(f'metadata contract mismatch: {key}')
    for actual, expected in ((vocab, {token: i for i, token in enumerate(NATIVE_TOKENS[:42])}),
                             (added_tokens, {'<s>': 42, '</s>': 43})):
        if (not isinstance(actual, dict) or actual != expected
                or any(type(value) is not int for value in actual.values())):
            raise ValueError('metadata vocabulary contract mismatch')
