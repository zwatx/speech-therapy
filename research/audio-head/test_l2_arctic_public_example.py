"""Bounded acquisition and offline replay using explicit synthetic HTTP fixtures."""
import copy
from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import l2_arctic_public_example as subject
from test_l2_arctic_annotations import grid


def example():
    # Observed public-example labels/times, reconstructed solely for synthetic IO tests.
    bounds=[0,.04,.11,.2,.28,.34,.44,.53,.64,.8,.85,.94,1.01,1.16,1.44,1.6,1.6214965986394558]
    labels=['sil','DH','EH1','R,AH0,s','W','AH1','Z,S,s','AH0','CH','EY1','N','JH,CH,s','N','AW1','sp','']
    phones=list(zip(bounds,bounds[1:],labels))
    words=[(0,.04,''),(.04,.28,'there'),(.28,.53,'was'),(.53,.64,'a'),(.64,1.01,'change'),(1.01,1.44,'now'),(1.44,bounds[-1],'')]
    ipa=[(0,.2,''),(.2,.28,'ɹ,ə,s'),(.28,.44,''),(.44,.53,'z,s,s'),(.53,.94,''),(.94,1.01,'dʒ,tʃ,s'),(1.01,bounds[-1],'')]
    return grid([('words',words),('phones',phones),('IPA',ipa)],end=bounds[-1])


def bodies():
    return {'homepage.html':b'LXC, arctic_a0018 manual annotations CC BY-NC 4.0 Your Name Your Email',
            'documentation.html':b'CPL,PPL,s CPL,err,s sil,PPL,a CPL,sil,d /annotation /textgrid',
            'license.html':b'Attribution-NonCommercial 4.0 International',
            'praat-format.html':b'TextGrid file formats','lxc_arctic_a0018.TextGrid':example()}


class Response(io.BytesIO):
    def __init__(self,body,content_type='text/plain',length=None):
        super().__init__(body);self.status=200;self.url=subject.SOURCES['lxc_arctic_a0018.TextGrid']
        self.headers=Message();self.headers['Content-Type']=content_type
        if length is not None:self.headers['Content-Length']=str(length)


class AcquisitionTests(unittest.TestCase):
    def test_http_size_content_and_url_allowlist(self):
        url=subject.SOURCES['lxc_arctic_a0018.TextGrid']
        for response in (Response(b'x',length=subject.MAX_RESPONSE+1),Response(b'x'*(subject.MAX_RESPONSE+1)),
                         Response(b'<html>login</html>','text/html'),Response(b'')):
            with patch.object(subject.urllib.request,'build_opener') as mock:
                mock.return_value.open.return_value=response
                with self.assertRaises(ValueError):subject.fetch(url)
        with patch.object(subject.urllib.request,'build_opener') as mock:
            mock.return_value.open.return_value=Response(b'valid',length=5)
            value,metadata=subject.fetch(url);self.assertEqual(value,b'valid');self.assertEqual(metadata['bytes'],5)
        with self.assertRaises(ValueError):subject.fetch('https://example.com/private')

    def test_redirect_cannot_leave_host_or_https(self):
        handler=subject.SameHostRedirect();request=urllib.request.Request(subject.SOURCES['homepage.html'])
        for target in ('http://psi.engr.tamu.edu/login','https://example.com/data'):
            with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'redirect',{},target)

    def test_source_context_requires_public_manual_example_not_automatic_alignment(self):
        files=bodies();subject.verify_source_context(files)
        for name in ('homepage.html','documentation.html','license.html','praat-format.html'):
            changed={**files,name:b'automatic-only or login page'}
            with self.assertRaises(ValueError):subject.verify_source_context(changed)
        self.assertEqual(subject.visible(b'<script>manual annotations</script><p>visible</p>'),'visible')

    def test_sample_replay_and_scope_are_bound_without_network(self):
        with tempfile.TemporaryDirectory(dir=subject.HERE/'outputs') as directory:
            output=Path(directory)/'sample';plan=subject.declare(output)
            files=bodies()
            def mocked_fetch(url):
                name=next(n for n,u in subject.SOURCES.items() if u==url);body=files[name]
                return body,dict(url=url,finalUrl=url,bytes=len(body),contentType='text/plain' if name.endswith('TextGrid') else 'text/html',retrievedAtUTC='synthetic')
            with patch.object(subject,'fetch',side_effect=mocked_fetch) as mock:
                pin=subject.run(plan['path'],plan['sha256']);self.assertEqual(mock.call_count,5)
            with patch.object(subject,'fetch',side_effect=AssertionError('Offline verifier must not fetch')):
                report=subject.verify(pin['path'],pin['sha256'])
            self.assertEqual(report['summary']['eventCounts']['substitution'],3)
            self.assertEqual(len(report['summary']['supportedConsonantCoverage']),23)
            self.assertFalse(report['summary']['trainingEligible'])
            with self.assertRaises(ValueError):subject.run(plan['path'],plan['sha256'])
            # Rehashing a corrupted derived artifact cannot evade reconstruction.
            parsed=subject.read_bound(report['annotations']);parsed['records'][3]['perceived']['phone']='R'
            Path(report['annotations']['path']).write_text(json.dumps(parsed))
            report['annotations']=subject.binding(report['annotations']['path'])
            Path(pin['path']).write_text(json.dumps(report));modified=subject.binding(pin['path'])
            with self.assertRaises(ValueError):subject.verify(modified['path'],modified['sha256'])

    def test_failed_retrieval_preserves_partial_evidence_and_cannot_restart(self):
        with tempfile.TemporaryDirectory(dir=subject.HERE/'outputs') as directory:
            output=Path(directory)/'sample';plan=subject.declare(output)
            with patch.object(subject,'fetch',side_effect=ValueError('Unavailable public source')):
                with self.assertRaises(ValueError):subject.run(plan['path'],plan['sha256'])
            self.assertTrue((output/'failure.json').exists());self.assertFalse((output/'report.json').exists())
            with self.assertRaises(ValueError):subject.run(plan['path'],plan['sha256'])
            with self.assertRaises(ValueError):subject.declare(output)


if __name__=='__main__':unittest.main()
