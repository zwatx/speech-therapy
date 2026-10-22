"""Bounded selected orthography projection and the unchanged study cut recipe.

Outcome text and attributes are opaque. Two passes must see identical bytes;
the caller must additionally bind the archive/source before and after use.
"""
from __future__ import annotations

import hashlib
from xml.parsers import expat

from r_confirmatory.structural_projection_v2 import (
    MAX_ENTRY_BYTES, MAX_DEPTH, MAX_ALLOWED_TEXT, READ_CHUNK_BYTES,
    ProjectionError, project_session, _split_name, _reject_declaration,
)


class RequestError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _HashedStream:
    def __init__(self, stream):
        self.stream, self.hash = stream, hashlib.sha256()

    def read(self, size):
        value = self.stream.read(size)
        if isinstance(value, bytes):
            self.hash.update(value)
        return value


def build_prompt(token, word_parts):
    """No inferred word, phone, occurrence, padding, or selection replacement."""
    if not isinstance(word_parts, list) or not all(isinstance(w, str) for w in word_parts):
        raise RequestError('unusable_orthography')
    label = '_'.join(' '.join(word_parts).split())
    if not label or len(label) > 64 or not label.isprintable():
        raise RequestError('unusable_orthography')
    phones = token['phones']
    if phones.count('R') != 1 or any(p.startswith('ER') for p in phones):
        raise RequestError('selected_occurrence_differs')
    return {'schemaVersion': 2, 'language': 'en', 'transcript': label,
            'words': [{'text': label, 'phones': list(phones)}],
            'targets': [{'id': token['tokenId'], 'wordIndex': 0,
                         'phoneIndex': phones.index('R'), 'targetPhone': 'R'}]}


def cut_arguments(ffmpeg, source, token, destination):
    return [str(ffmpeg), '-nostdin', '-v', 'error', '-n',
            '-ss', f"{token['startSeconds']:.6f}",
            '-to', f"{token['endSeconds']:.6f}", '-i', str(source),
            '-map', '0:a:0', '-ac', '1', '-ar', '16000',
            '-c:a', 'pcm_s16le', str(destination)]


class _Words:
    def __init__(self, identities):
        self.identities, self.stack = set(identities), []
        self.namespace = None
        self.selected = None
        self.opaque_depth = None
        self.container = 0
        self.capture = None
        self.size = 0
        self.words = {}

    def start(self, qualified, attrs):
        ns, name = _split_name(qualified)
        if self.namespace is None:
            self.namespace = ns
        self.stack.append(name)
        depth = len(self.stack)
        if depth > MAX_DEPTH:
            raise RequestError('nesting_limit')
        if self.opaque_depth is not None:
            return
        if name in {'userTier', 'userTiers'}:
            # No inspection of outcome tier names, attributes, or values.
            self.opaque_depth = depth
            return
        if self.capture is not None:
            raise RequestError('invalid_orthography_structure')
        if self.stack == ['session', 'transcript', 'r']:
            self.selected = attrs.get('id') if attrs.get('id') in self.identities else None
            self.container = 0
        if self.selected is None:
            return
        if name in {'r', 'orthography', 'w'} and ns != self.namespace:
            raise RequestError('namespace_ambiguity')
        if name == 'orthography':
            if self.stack != ['session', 'transcript', 'r', 'orthography']:
                raise RequestError('invalid_orthography_structure')
            self.container += 1
            if self.container != 1:
                raise RequestError('duplicate_orthography')
            self.words[self.selected] = []
        elif name == 'w':
            if self.stack != ['session', 'transcript', 'r', 'orthography', 'w']:
                raise RequestError('invalid_orthography_structure')
            self.capture, self.size = [], 0
        elif 'orthography' in self.stack:
            raise RequestError('invalid_orthography_structure')

    def text(self, text):
        if self.capture is not None:
            self.size += len(text)
            if self.size > MAX_ALLOWED_TEXT:
                raise RequestError('allowed_text_limit')
            self.capture.append(text)
        elif (self.selected is not None and self.opaque_depth is None
              and self.stack[-1:] == ['orthography'] and text.strip()):
            raise RequestError('invalid_orthography_structure')

    def end(self, qualified):
        if self.opaque_depth is not None:
            if len(self.stack) == self.opaque_depth:
                self.opaque_depth = None
        elif self.capture is not None and self.stack[-1] == 'w':
            self.words[self.selected].append(''.join(self.capture))
            self.capture = None
        elif self.stack == ['session', 'transcript', 'r']:
            self.selected = None
        self.stack.pop()


def project_selected_requests(stream, folder, session, age_years, selected):
    """Project only declared selected words; verify all selected structure first.

    Missing or unusable word text is a terminal token failure. Unsafe XML or a
    changed stream invalidates the projection, without exposing source snippets.
    """
    try:
        if stream.tell() != 0:
            raise RequestError('stream_position_differs')
        first = _HashedStream(stream)
        structure = project_session(first, folder, session)
        if type(age_years) is not int or structure['ageYears'] != age_years:
            raise RequestError('selected_structure_differs')
        if not isinstance(selected, list):
            raise RequestError('invalid_selected_records')
        records = {r['recordId']: r for r in structure['records']}
        identities = []
        for token in selected:
            record = records.get(token['recordId'])
            if (record is None or token['recordId'] in identities
                or token['tokenId'] != '/'.join((folder, session, token['recordId']))
                or record['targetMetadataStatus'] != 'resolved'
                or any(token[k] != record[k] for k in ('phones', 'startSeconds', 'endSeconds'))):
                raise RequestError('selected_structure_differs')
            identities.append(token['recordId'])
        stream.seek(0)
        second = _HashedStream(stream)
        words = _Words(identities)
        parser = expat.ParserCreate(namespace_separator='|')
        parser.StartElementHandler, parser.EndElementHandler = words.start, words.end
        parser.CharacterDataHandler = words.text
        parser.StartDoctypeDeclHandler = parser.EntityDeclHandler = _reject_declaration
        parser.ExternalEntityRefHandler = parser.SkippedEntityHandler = _reject_declaration
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        total = 0
        while True:
            requested = min(READ_CHUNK_BYTES, MAX_ENTRY_BYTES-total+1)
            chunk = second.read(requested)
            if not isinstance(chunk, bytes) or len(chunk) > requested:
                raise RequestError('invalid_stream')
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ENTRY_BYTES:
                raise RequestError('entry_bytes_limit')
            parser.Parse(chunk, False)
        parser.Parse(b'', True)
        if first.hash.digest() != second.hash.digest():
            raise RequestError('stream_bytes_changed')
        output = []
        for token in selected:
            row = {'tokenId': token['tokenId'], 'sourceXMLSha256': first.hash.hexdigest()}
            try:
                row['prompt'] = build_prompt(token, words.words.get(token['recordId'], []))
                row['status'] = 'prepared'
            except RequestError as error:
                row.update(status='failed', failureCode=error.code)
            output.append(row)
        return output
    except RequestError:
        raise
    except ProjectionError as error:
        raise RequestError(error.code) from None
    except expat.ExpatError:
        raise RequestError('malformed_xml') from None
    except Exception:
        raise RequestError('projection_failed') from None
