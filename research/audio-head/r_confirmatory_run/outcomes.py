"""Selected reserved vote projection, invoked only after the outcome-access claim.

This module never discovers files, decodes audio, or fits models. The caller owns
the once-only lock boundary; calling a projection does not authorize outcome
access. Only selected responseCorrect/responseTotal text is accumulated.
"""
from __future__ import annotations

import hashlib
import zipfile
from xml.parsers import expat

from r_confirmatory.structural_projection_v2 import (
    MAX_ENTRY_BYTES, MAX_DEPTH, MAX_ALLOWED_TEXT, READ_CHUNK_BYTES,
    ProjectionError, project_session, _split_name, _reject_declaration,
    _FOLDER_ID, _SAFE_ID,
)


class OutcomeError(ValueError):
    """Fixed integrity diagnostics without source values or paths."""

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


class _Ratings:
    def __init__(self, identities):
        self.identities, self.stack = set(identities), []
        self.namespace = None
        self.selected = self.opaque_depth = self.tier_depth = None
        self.tier_name = self.capture = self.capture_depth = None
        self.data_count = self.word_count = self.size = 0
        self.values = {identity: {} for identity in identities}

    def start(self, qualified, attrs):
        namespace, name = _split_name(qualified)
        if self.namespace is None:
            self.namespace = namespace
        self.stack.append(name)
        depth = len(self.stack)
        if depth > MAX_DEPTH:
            raise OutcomeError('nesting_limit')
        if self.opaque_depth is not None:
            return
        if self.capture is not None:
            raise OutcomeError('malformed_outcome_tier')
        if self.tier_depth is not None:
            if namespace != self.namespace:
                raise OutcomeError('namespace_ambiguity')
            if name == 'tierData' and depth == self.tier_depth + 1:
                self.data_count += 1
                if self.data_count != 1:
                    raise OutcomeError('malformed_outcome_tier')
            elif (name == 'tw' and self.stack[-2] == 'tierData'
                  and depth == self.tier_depth + 2):
                self.word_count += 1
                if self.word_count != 1:
                    raise OutcomeError('malformed_outcome_tier')
                self.capture, self.capture_depth, self.size = [], depth, 0
            else:
                raise OutcomeError('malformed_outcome_tier')
            return
        if self.stack == ['session', 'transcript', 'r']:
            identity = attrs.get('id')
            self.selected = identity if identity in self.identities else None
        if name == 'userTier':
            if self.selected is None:
                self.opaque_depth = depth
                return
            tier_name = attrs.get('name')
            if tier_name not in {'responseCorrect', 'responseTotal'}:
                self.opaque_depth = depth
                return
            if namespace != self.namespace:
                raise OutcomeError('namespace_ambiguity')
            for attribute in attrs:
                attr_namespace, attr_name = _split_name(attribute)
                if attr_name == 'name' and attr_namespace:
                    raise OutcomeError('namespace_ambiguity')
            if tier_name in self.values[self.selected]:
                raise OutcomeError('duplicate_outcome_tier')
            self.values[self.selected][tier_name] = None
            self.tier_name, self.tier_depth = tier_name, depth
            self.data_count = self.word_count = 0

    def text(self, value):
        if self.capture is not None:
            self.size += len(value)
            if self.size > MAX_ALLOWED_TEXT:
                raise OutcomeError('allowed_text_limit')
            self.capture.append(value)
        elif self.tier_depth is not None and value.strip():
            raise OutcomeError('malformed_outcome_tier')

    def end(self, qualified):
        depth = len(self.stack)
        if self.opaque_depth is not None:
            if depth == self.opaque_depth:
                self.opaque_depth = None
        elif self.capture is not None and depth == self.capture_depth:
            try:
                number = int(''.join(self.capture))
            except ValueError:
                raise OutcomeError('malformed_outcome_tier') from None
            self.values[self.selected][self.tier_name] = number
            self.capture = self.capture_depth = None
        elif depth == self.tier_depth:
            if self.data_count != 1 or self.word_count != 1:
                raise OutcomeError('malformed_outcome_tier')
            self.tier_name = self.tier_depth = None
        elif self.stack == ['session', 'transcript', 'r']:
            self.selected = None
        self.stack.pop()


def project_selected_outcomes(stream, folder, session, selected):
    """Two identical-byte passes: structural reconciliation, then selected votes."""
    try:
        if stream.tell() != 0:
            raise OutcomeError('stream_position_differs')
        if type(selected) is not list or not selected:
            raise OutcomeError('selected_structure_differs')
        first = _HashedStream(stream)
        structure = project_session(first, folder, session)
        records = {record['recordId']: record for record in structure['records']}
        identities = []
        fields = {'childId', 'tokenId', 'folder', 'session', 'recordId', 'ageYears',
                  'phones', 'startSeconds', 'endSeconds'}
        for token in selected:
            if (type(token) is not dict or not fields <= set(token)
                    or any(type(token[key]) is not str for key in
                           ('childId', 'tokenId', 'folder', 'session', 'recordId'))
                    or type(token['phones']) is not list
                    or any(type(token[key]) not in (int, float) for key in ('startSeconds', 'endSeconds'))):
                raise OutcomeError('selected_structure_differs')
            record = records.get(token['recordId'])
            if (record is None or token['recordId'] in identities
                    or token['childId'] != folder.rsplit('_', 1)[1]
                    or token['folder'] != folder or token['session'] != session
                    or token['tokenId'] != '/'.join((folder, session, token['recordId']))
                    or type(token['ageYears']) is not int or not 6 <= token['ageYears'] <= 12
                    or token['ageYears'] != structure['ageYears']
                    or record['targetMetadataStatus'] != 'resolved'
                    or any(token[key] != record[key] for key in ('phones', 'startSeconds', 'endSeconds'))):
                raise OutcomeError('selected_structure_differs')
            identities.append(token['recordId'])
        stream.seek(0)
        second = _HashedStream(stream)
        ratings = _Ratings(identities)
        parser = expat.ParserCreate(namespace_separator='|')
        parser.StartElementHandler, parser.EndElementHandler = ratings.start, ratings.end
        parser.CharacterDataHandler = ratings.text
        parser.StartDoctypeDeclHandler = parser.EntityDeclHandler = _reject_declaration
        parser.ExternalEntityRefHandler = parser.SkippedEntityHandler = _reject_declaration
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        total = 0
        while True:
            requested = min(READ_CHUNK_BYTES, MAX_ENTRY_BYTES - total + 1)
            chunk = second.read(requested)
            if not isinstance(chunk, bytes) or len(chunk) > requested:
                raise OutcomeError('invalid_stream')
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ENTRY_BYTES:
                raise OutcomeError('entry_bytes_limit')
            parser.Parse(chunk, False)
        parser.Parse(b'', True)
        if first.hash.digest() != second.hash.digest():
            raise OutcomeError('stream_bytes_changed')
        rows = []
        for token in selected:
            value = ratings.values[token['recordId']]
            row = {'childId': token['childId'], 'tokenId': token['tokenId']}
            if (value.get('responseCorrect', 0) < 0 or value.get('responseTotal', 1) < 1):
                raise OutcomeError('invalid_outcome_votes')
            if set(value) != {'responseCorrect', 'responseTotal'}:
                rows.append({**row, 'status': 'unavailable', 'reason': 'missing_outcome_tier'})
                continue
            k, n = value['responseCorrect'], value['responseTotal']
            if n < 1 or not 0 <= k <= n:
                raise OutcomeError('invalid_outcome_votes')
            rows.append({**row, 'status': 'available', 'positiveVotes': n-k, 'negativeVotes': k})
        return rows
    except OutcomeError:
        raise
    except ProjectionError as error:
        raise OutcomeError(error.code) from None
    except expat.ExpatError:
        raise OutcomeError('malformed_xml') from None
    except Exception:
        raise OutcomeError('outcome_projection_failed') from None


def project_archive_outcomes(archive_stream, selected):
    """Read only declared selected XML members from an already held archive."""
    try:
        if type(selected) is not list:
            raise OutcomeError('selected_structure_differs')
        groups, identities = {}, set()
        for token in selected:
            if (type(token) is not dict
                    or not {'folder', 'session', 'recordId', 'childId', 'tokenId'} <= set(token)
                    or any(type(token[name]) is not str for name in
                           ('folder', 'session', 'recordId', 'childId', 'tokenId'))
                    or len(token['folder']) > MAX_ALLOWED_TEXT or not _FOLDER_ID.fullmatch(token['folder'])
                    or any(len(token[name]) > MAX_ALLOWED_TEXT or not _SAFE_ID.fullmatch(token[name])
                           for name in ('session', 'recordId'))
                    or token['childId'] != token['folder'].rsplit('_', 1)[1]
                    or token['tokenId'] != '/'.join(token[name] for name in ('folder', 'session', 'recordId'))
                    or token['tokenId'] in identities):
                raise OutcomeError('selected_structure_differs')
            identities.add(token['tokenId'])
            groups.setdefault((token['folder'], token['session']), []).append(token)
        with zipfile.ZipFile(archive_stream) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise OutcomeError('duplicate_archive_member')
            rows = []
            for (folder, session), tokens in sorted(groups.items()):
                name = f'0phon/{folder}/{session}.xml'
                if name not in names:
                    raise OutcomeError('missing_archive_member')
                member = archive.getinfo(name)
                if member.is_dir() or member.flag_bits & 1:
                    raise OutcomeError('invalid_archive_member')
                if member.file_size > MAX_ENTRY_BYTES:
                    raise OutcomeError('entry_bytes_limit')
                with archive.open(member) as stream:
                    rows.extend(project_selected_outcomes(stream, folder, session, tokens))
        return sorted(rows, key=lambda row: (row['childId'], row['tokenId']))
    except OutcomeError:
        raise
    except Exception:
        raise OutcomeError('outcome_archive_failed') from None


def project_reserved_outcomes(profile):
    """Production-only reader for the claimed stage callback, after its lock.

    The stage must verify the declaration/profile and this source pin first.
    No alternate archive, external rating producer, or synthetic mode is used.
    """
    if type(profile) is not dict or profile.get('mode') != 'reserved_test':
        raise OutcomeError('reserved_profile_required')
    try:
        # Importing source definitions does not load models or access outcomes.
        from . import stages
        from .execution import ARCHIVE, _held_verified

        prepared = stages._json(stages._binding(profile['inputBindings']['preparedTokens']))
        tokens = [token for token in prepared['tokens'] if token['disposition'] == 'selected']
        membership = sorted(({'childId': token['childId'], 'tokenId': token['tokenId']}
                             for token in tokens), key=lambda row: (row['childId'], row['tokenId']))
        if (membership != profile['selectedTokens']
                or sorted(row['childId'] for row in prepared['children'])
                    != sorted(row['childId'] for row in profile['children'])):
            raise OutcomeError('prepared_selection_differs')
        with _held_verified(ARCHIVE) as source:
            return project_archive_outcomes(source, tokens)
    except OutcomeError:
        raise
    except Exception:
        raise OutcomeError('reserved_outcome_access_failed') from None
