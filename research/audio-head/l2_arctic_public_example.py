"""Acquire and verify the one public manual annotation example; no audio or fits."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
from l2_arctic_annotations import ARPABET, VOWELS, parse_annotations, require

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE/'../../docs/model/l2-arctic-public-example-protocol.md'
SOURCES = {
    'homepage.html': 'https://psi.engr.tamu.edu/l2-arctic-corpus/',
    'documentation.html': 'https://psi.engr.tamu.edu/l2-arctic-corpus-docs/',
    'lxc_arctic_a0018.TextGrid': 'https://psi.engr.tamu.edu/wp-content/uploads/2018/03/lxc_arctic_a0018.txt',
    'license.html': 'https://creativecommons.org/licenses/by-nc/4.0/legalcode.en',
    'praat-format.html': 'https://www.fon.hum.uva.nl/praat/manual/TextGrid_file_formats.html',
}
MAX_RESPONSE = 250_000
FLAGS = dict(audioDownloaded=False, corpusArchiveDownloaded=False, registrationPerformed=False,
             trainingPerformed=False, evaluationPerformed=False, trainingEligible=False,
             evaluationEligible=False, learnerFeedbackEligible=False, clinicalUseEligible=False)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def guard(pin):
    require(binding(pin['path']) == {k:pin[k] for k in ('path', 'sha256')}, 'Bound artifact changed: '+pin['path'])


def read_bound(pin):
    guard(pin)
    return json.loads(Path(pin['path']).read_text())


def write_new(path, value):
    with path.open('x') as stream:
        path.chmod(0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    return binding(path)


def source_bindings():
    result = {name:binding(HERE/name) for name in ('l2_arctic_annotations.py', 'l2_arctic_public_example.py',
              'test_l2_arctic_annotations.py', 'test_l2_arctic_public_example.py')}
    result['protocol'] = binding(PROTOCOL)
    return result


def declare(output):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'), 'Fresh ignored output required')
    plan = dict(schemaVersion=1, sourceBindings=source_bindings(), sources=SOURCES, maxResponseBytes=MAX_RESPONSE,
        maxTotalBytes=MAX_RESPONSE*len(SOURCES), purpose='public-annotation-schema-only', python=sys.version,
        sourceReleaseVersion=None, speakerAge=None, acquisitionPerformed=False, **FLAGS)
    output.mkdir(parents=True, mode=0o700)
    return write_new(output/'plan.json', plan)


def load_plan(path, sha):
    plan = read_bound(dict(path=str(Path(path).resolve()), sha256=sha))
    require(plan['sources'] == SOURCES and plan['sourceBindings'] == source_bindings()
            and plan['maxResponseBytes'] == MAX_RESPONSE and plan['maxTotalBytes'] == MAX_RESPONSE*len(SOURCES)
            and plan['python'] == sys.version and plan['purpose'] == 'public-annotation-schema-only'
            and plan['sourceReleaseVersion'] is None and plan['speakerAge'] is None
            and plan['acquisitionPerformed'] is False and all(plan[k] == v for k,v in FLAGS.items()), 'Plan differs')
    return plan


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before, after = urllib.parse.urlparse(req.full_url), urllib.parse.urlparse(newurl)
        require(after.scheme == 'https' and after.hostname == before.hostname, 'Redirect leaves approved HTTPS host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    require(url in SOURCES.values(), 'Only declared public URLs may be fetched')
    request = urllib.request.Request(url, headers={'User-Agent':'Cadence-annotation-schema-check/1.0'})
    with urllib.request.build_opener(SameHostRedirect()).open(request, timeout=20) as response:
        require(response.status == 200, 'Expected successful public response')
        size = response.headers.get('Content-Length')
        require(size is None or 0 <= int(size) <= MAX_RESPONSE, 'Response exceeds declared byte budget')
        body = response.read(MAX_RESPONSE+1)
        require(0 < len(body) <= MAX_RESPONSE, 'Response exceeds declared byte budget or is empty')
        content_type = response.headers.get_content_type()
        require(content_type == ('text/plain' if url == SOURCES['lxc_arctic_a0018.TextGrid'] else 'text/html'),
                'Unexpected response type (possibly access/login page)')
        return body, dict(url=url, finalUrl=response.url, contentType=content_type, bytes=len(body),
            retrievedAtUTC=datetime.now(timezone.utc).isoformat(), etag=response.headers.get('ETag'),
            lastModified=response.headers.get('Last-Modified'))


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def visible(data):
    parser = VisibleText(); parser.feed(data.decode('utf-8'))
    return ' '.join(' '.join(parser.parts).split())


def verify_source_context(files):
    homepage = visible(files['homepage.html'])
    require('LXC, arctic_a0018' in homepage and 'manual annotations' in homepage
            and 'CC BY-NC 4.0' in homepage and 'Your Name' in homepage and 'Your Email' in homepage,
            'Public manual-example, access or license context changed')
    docs = visible(files['documentation.html'])
    require(all(term in docs for term in ('CPL,PPL,s', 'CPL,err,s', 'sil,PPL,a', 'CPL,sil,d', '/annotation', '/textgrid')),
            'Official annotation contract changed')
    require('Attribution-NonCommercial 4.0 International' in visible(files['license.html']), 'Unexpected license document')
    require('TextGrid file formats' in visible(files['praat-format.html']), 'Unexpected format document')


def summarize(parsed):
    records = parsed['records']
    counts = Counter(r['event'] for r in records)
    supported = sorted(ARPABET - VOWELS - {'ZH'})
    per_phone = {p:dict(unchanged=0, substitution=0, deletion=0) for p in supported}
    for row in records:
        if row['canonical'] and row['canonical']['phone'] in per_phone:
            per_phone[row['canonical']['phone']][row['event']] += 1
    substitutions = [dict(start=r['start'], end=r['end'], rawLabel=r['rawLabel'],
                          canonical=r['canonical'], perceived=r['perceived'])
                     for r in records if r['event'] == 'substitution']
    return dict(phoneIntervals=len(records), eventCounts={k:counts[k] for k in
        ('unchanged','substitution','insertion','deletion','nonlexical')}, substitutions=substitutions,
        tierIntervals={t['name']:len(t['intervals']) for t in parsed['grid']['tiers']},
        supportedConsonantCoverage=per_phone, observedUncertainIdentities=sum(bool(r['perceived'] and r['perceived']['uncertain']) for r in records),
        observedDeviations=sum(bool(r['perceived'] and r['perceived']['deviation']) for r in records),
        sourceReleaseVersion=None, speakerId='LXC', speakerAge=None, utteranceId='arctic_a0018',
        waveformTimingVerified=False, auxiliaryTiersCountedAsErrors=False, **FLAGS)


def check_example(summary):
    require(summary['tierIntervals'] == {'words':7, 'phones':16, 'IPA':7}
            and summary['eventCounts'] == dict(unchanged=10, substitution=3, insertion=0, deletion=0, nonlexical=3)
            and [(r['start'],r['end'],r['rawLabel']) for r in summary['substitutions']] ==
                [(.2,.28,'R,AH0,s'),(.44,.53,'Z,S,s'),(.94,1.01,'JH,CH,s')], 'Public example changed from inspected schema')


def run(path, sha):
    path = Path(path).resolve(); plan=load_plan(path,sha); root=path.parent; source_dir=root/'source'
    require(not source_dir.exists() and not (root/'report.json').exists(), 'No restart or overwrite')
    source_dir.mkdir(mode=0o700); artifacts={}; bodies={}; total=0
    try:
        for name,url in SOURCES.items():
            body,metadata=fetch(url); total += len(body)
            require(total <= plan['maxTotalBytes'], 'Total acquisition byte budget exceeded')
            target=source_dir/name
            with target.open('xb') as stream: stream.write(body)
            target.chmod(0o600)
            artifacts[name]=dict(**binding(target), **metadata); bodies[name]=body
        verify_source_context(bodies)
        parsed=parse_annotations(bodies['lxc_arctic_a0018.TextGrid']); summary=summarize(parsed); check_example(summary)
        parsed_pin=write_new(root/'annotations.json',parsed)
        attribution=write_new(root/'attribution.json',dict(creators='Guanlong Zhao, Sinem Sonsaat, Alif Silpachai, Ivana Lucic, Evgeny Chukharev-Hudilainen, John Levis, Ricardo Gutierrez-Osuna',
            title='L2-ARCTIC: A Non-native English Speech Corpus', year=2018, doi='10.21437/Interspeech.2018-1110',
            source=SOURCES['homepage.html'], sample=SOURCES['lxc_arctic_a0018.TextGrid'], license='CC BY-NC 4.0',
            licenseUrl=SOURCES['license.html'], modifications='Original fetched bytes unchanged. Derived JSON interprets annotations and adds provenance, word overlaps and exclusion flags.',
            commercialUsePermissionEstablished=False, sourceReleaseVersion=None))
        load_plan(path,sha)
        for pin in [*artifacts.values(),parsed_pin,attribution]: guard(pin)
        return write_new(root/'report.json',dict(complete=True, plan=dict(path=str(path),sha256=sha),
            sources=artifacts, annotations=parsed_pin, attribution=attribution, summary=summary,
            totalDownloadedBytes=total, purpose=plan['purpose'], **FLAGS))
    except Exception as error:
        write_new(root/'failure.json',dict(complete=False,error=f'{type(error).__name__}: {error}',
                  sourceArtifacts=artifacts,totalDownloadedBytes=total)); raise


def verify(path,sha):
    report=read_bound(dict(path=str(Path(path).resolve()),sha256=sha)); plan=load_plan(**dict(path=report['plan']['path'],sha=report['plan']['sha256']))
    require(report['complete'] is True and report['purpose'] == plan['purpose'] and all(report[k] == v for k,v in FLAGS.items())
            and set(report['sources']) == set(SOURCES), 'Invalid report scope')
    bodies={}; total=0
    for name,url in SOURCES.items():
        pin=report['sources'][name]; guard(pin); body=Path(pin['path']).read_bytes(); total+=len(body)
        require(pin['url'] == url and pin['bytes'] == len(body) <= MAX_RESPONSE
                and urllib.parse.urlparse(pin['finalUrl']).scheme == 'https'
                and urllib.parse.urlparse(pin['finalUrl']).hostname == urllib.parse.urlparse(url).hostname,
                'Invalid source provenance')
        bodies[name]=body
    require(total == report['totalDownloadedBytes'] <= plan['maxTotalBytes'], 'Acquisition byte total differs')
    verify_source_context(bodies)
    parsed=parse_annotations(bodies['lxc_arctic_a0018.TextGrid']); summary=summarize(parsed); check_example(summary)
    require(read_bound(report['annotations']) == parsed and report['summary'] == summary, 'Derived annotations differ from source')
    attribution=read_bound(report['attribution'])
    require(attribution['license'] == 'CC BY-NC 4.0' and attribution['sample'] == SOURCES['lxc_arctic_a0018.TextGrid']
            and attribution['commercialUsePermissionEstablished'] is False, 'Attribution differs')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command', choices=['declare','run','verify'])
    parser.add_argument('--output',type=Path); parser.add_argument('--plan',type=Path); parser.add_argument('--plan-sha256')
    parser.add_argument('--report',type=Path); parser.add_argument('--report-sha256'); args=parser.parse_args()
    if args.command == 'declare': result=declare(args.output)
    elif args.command == 'run': result=run(args.plan,args.plan_sha256)
    else:
        report=verify(args.report,args.report_sha256); result=dict(verified=True,summary=report['summary'])
    print(json.dumps(result,indent=2))
