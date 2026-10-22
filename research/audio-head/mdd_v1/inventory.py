"""Broad English phone inventory v1; stress and narrow detail remain in manifests."""
import re

VERSION = 'arpabet39-ipa-v1'
PHONES = 'AA AE AH AO AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW V W Y Z ZH'.split()
PHONE_TO_ID = {phone: i + 1 for i, phone in enumerate(PHONES)}
ID_TO_PHONE = {i: p for p, i in PHONE_TO_ID.items()}
IPA = dict(zip(PHONES, 'ɑ æ ə ɔ aʊ aɪ b tʃ d ð ɛ ɝ eɪ f ɡ h ɪ i dʒ k l m n ŋ oʊ ɔɪ p ɹ s ʃ t θ ʊ u v w j z ʒ'.split()))
# Exact vocabulary-token mappings: no Unicode splitting or guessed fallback.
ESPEAK = {ipa: [phone] for phone, ipa in IPA.items()}
ESPEAK.update({
    'a': ['AA'], 'ɑː': ['AA'], 'ɒ': ['AA'], 'aː': ['AA'],
    'ʌ': ['AH'], 'ɐ': ['AH'], 'ɚ': ['ER'], 'ɜ': ['ER'], 'ɜː': ['ER'],
    'iː': ['IY'], 'uː': ['UW'], 'ɔː': ['AO'], 'e': ['EY'], 'eː': ['EY'],
    'o': ['OW'], 'oː': ['OW'], 'əʊ': ['OW'], 'oɪ': ['OY'], 'ᵻ': ['IH'],
    'r': ['R'], 'ɻ': ['R'], 'ɾ': ['T'], 'ɫ': ['L'], 'l̩': ['AH', 'L'],
    'n̩': ['AH', 'N'], 'əl': ['AH', 'L'], 'ɑːɹ': ['AA', 'R'],
    'ɔːɹ': ['AO', 'R'], 'oːɹ': ['OW', 'R'], 'ɛɹ': ['EH', 'R'],
    'ɪɹ': ['IH', 'R'], 'ʊɹ': ['UH', 'R'], 'iə': ['IY', 'AH'],
    'aɪɚ': ['AY', 'ER'], 'aɪə': ['AY', 'AH'], 'ju': ['Y', 'UW'],
    'eə': ['EH', 'AH'], 'ʊə': ['UH', 'AH'],
})


def normalize_arpabet(raw):
    phone = re.sub(r'[012]$', '', raw.upper())
    if phone not in PHONE_TO_ID:
        raise ValueError(f'Unmapped ARPAbet phone: {raw!r}')
    return phone


def map_espeak(tokens):
    """Unmapped predictions stay visible and count as PER errors."""
    phones, unmapped = [], []
    for token in tokens:
        if token in ESPEAK:
            phones.extend(ESPEAK[token])
        else:
            phones.append('<unk>')
            unmapped.append(token)
    return phones, unmapped

# JIBO extension leaves the round-2 inventory/espeak mapping unchanged.
JIBO_VERSION = 'arpabet39-jibo-ipa-v2'
JIBO_IPA = {ipa: [phone] for phone, ipa in IPA.items()}
JIBO_IPA.update({
    'e': ['EY'], 'o': ['OW'], 'g': ['G'], 'ʌ': ['AH'], 'ɐ': ['AH'], 'ɚ': ['ER'], 'ɜ': ['ER'],
    'ɫ': ['L'], 'ɾ': ['T'], 'ʧ': ['CH'], 'ʤ': ['JH'],
    'ɑ͡ɪ': ['AY'], 'a͡ɪ': ['AY'], 'e͡ɪ': ['EY'], 'o͡ʊ': ['OW'],
    'ɑ͡ʊ': ['AW'], 'a͡ʊ': ['AW'], 'ɔ͡ɪ': ['OY'],
    't͡ʃ': ['CH'], 'd͡ʒ': ['JH'], 'ɑɪ': ['AY'], 'ɑʊ': ['AW'],
})


def tokenize_jibo(text):
    """Longest explicit IPA match; length/nasality ignored only after known phones.

    Unknown symbols are returned and cause exclusion of the entire utterance.
    A dangling tiebar/diacritic is unknown; unsupported tied pairs are never
    interpreted as two independent known phones. Raw strings remain in manifest.
    """
    import unicodedata
    text = unicodedata.normalize('NFD', text).replace('\u035c', '\u0361')
    keys = sorted(JIBO_IPA, key=len, reverse=True)
    phones, unknown, i = [], [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        key = next((k for k in keys if text.startswith(k, i)), None)
        if key and i+len(key) < len(text) and text[i+len(key)] == '\u0361':
            key = None
        if key is None:
            end = i+3 if i+1 < len(text) and text[i+1] == '\u0361' else i+1
            while end < len(text) and unicodedata.combining(text[end]) and text[end] != '\u0361':
                end += 1
            unknown.append(unicodedata.normalize('NFC', text[i:end])); i = end
            continue
        phones.extend(JIBO_IPA[key]); i += len(key)
        while i < len(text) and text[i] in ('ː', '\u0303'):
            i += 1
    return phones, unknown
