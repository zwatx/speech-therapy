"""Metadata-only exact-word/canonical-phone coverage of the 72 native demo prompts.

No audio, inference, performance estimates, phonetic equivalences or clinical
coverage thresholds. A matched row is one retained canonical position in the
current single-occurrence author-training cohort, not a verified production.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import string

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SWIFT = ROOT / 'apps/ios-learner/Sources/DirectPractice/PracticeLibrary.swift'
WORKSHEET = ROOT / 'docs/model/practice-content-review.md'
COHORT = HERE / 'outputs/multiphone-20260926/cohort.json'
COHORT_SHA = '33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'
MAPPING = tuple(zip(
    'b p m t d n k g f v s z sh ch j l r w y h th voiced-th ng zh'.split(),
    ('b','p','m','t','d','n','k','ɡ','f','v','s','z','ʃ','tʃ','dʒ','l','ɹ','w','j','h','θ','ð','ŋ','ʒ'),
    'B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG ZH'.split(), strict=True))
RULES = {
    'join': ['canonical targetPhone', 'normalized exact targetWord spelling'],
    'spellingNormalization': 'Strip surrounding ASCII space/tab/CR/LF; translate ASCII A-Z to a-z only.',
    'equivalences': 'None: preserve punctuation, hyphens, plurals, accents and internal whitespace.',
    'positions': 'Distinct (clipId, wordIndex, phoneIndex) canonical positions; intended app position is descriptive, not a join condition or verified.',
    'fullPopulation': 'All 14843 raw author-training cohort rows, including unsupported ZH; single occurrence of a target phone per retained clip.',
    'childPopulation': '6 <= metadata age <= 12; no rows for ages 2-5 or verified SSD labels.',
    'votes': 'Original five-rater counts in source category order 0,1,2; no thresholds or inferred labels.',
    'unsupported': 'Preserve ZH in coverage; trainingEligible=false is unchanged, even if a word matches.',
    'interpretation': 'Descriptive corpus overlap only; absence is not evidence of unpronounceability/untrainability, and presence does not establish adequacy or clinical suitability.',
}
FLAGS = {key: False for key in ('trainingPerformed','inferencePerformed','audioRead',
    'authorTestObjectsRead','modelPerformanceMeasured','positionPlacementVerified',
    'producedPhoneLabelsAvailable','clinicalUseEligible','learnerFeedbackEligible')}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    path = Path(path).absolute()
    return {'path': str(path), 'sha256': digest(path)}


def guard(pins):
    for name, item in pins.items():
        require(digest(item['path']) == item['sha256'], 'Changed input: '+name)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.partial')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    os.replace(temporary, path)


def normalize_word(value):
    require(isinstance(value, str) and bool(value), 'Missing word spelling')
    return value.strip(' \t\r\n').translate(str.maketrans(string.ascii_uppercase, string.ascii_lowercase))


def parse_swift(text):
    """Fail-closed parser for this pinned literal-only list, not general Swift."""
    prefix = 'static let sounds: [PracticeSound] = ['
    suffix = '\n  ]'
    require(text.count(prefix) == 1, 'Swift library declaration changed')
    body = text.split(prefix, 1)[1].split(suffix, 1)[0]
    require('position: PracticeTargetPosition = .beginning' in text and
            'PracticePrompt(id: "\\(id)-\\(position.rawValue)-\\(word)"' in text,
            'Swift default position or prompt ID construction changed')
    sound = re.compile(r'sound\(\s*"([^"\\]+)",\s*"([^"\\]+)",\s*"([^"\\]+)"\s*,\s*(?:position:\s*\.(beginning|middle|end),\s*)?words:\s*\[([^\]]*)\]\s*\)\s*,?', re.S)
    word = re.compile(r'\("([^"\\]+)",\s*"([^"\\]+)"\)\s*,?')
    cursor = 0; prompts = []; seen = []
    for block in sound.finditer(body):
        require(not body[cursor:block.start()].strip(), 'Unparsed Swift sound content')
        cursor = block.end()
        sound_id, symbol, _, position, words = block.groups()
        position = position or 'beginning'; seen.append((sound_id, symbol))
        offset = 0; count = 0
        for match in word.finditer(words):
            require(not words[offset:match.start()].strip(), 'Unparsed Swift prompt content')
            offset = match.end(); spelling = match.group(1); count += 1
            prompts.append({'promptId': f'{sound_id}-{position}-{spelling}', 'soundId': sound_id,
                'symbol': symbol, 'position': position, 'word': spelling})
        require(not words[offset:].strip() and count == 3, 'Each declared sound must contain exactly three literal words')
    require(not body[cursor:].strip() and seen == [(a,b) for a,b,_ in MAPPING] and
            len(prompts) == 72 and len({p['promptId'] for p in prompts}) == 72,
            'Swift 24-sound/72-prompt inventory differs')
    return prompts


def validate_worksheet(text, prompts, swift_sha):
    declared = re.search(r'Source SHA-256:\s*`([0-9a-f]{64})`', text)
    require(declared is not None and declared.group(1) == swift_sha,
            'Worksheet Swift source pin differs')
    rows = []
    for line in text.splitlines():
        if line.startswith('| `'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            require(len(cells) == 11 and cells[4] == 'Pending' and not any(cells[5:]),
                    'Worksheet has different review states or reviewer decisions')
            rows.append({'promptId':cells[0].strip('`'),'symbol':cells[1].strip('/'),
                         'position':cells[2],'word':cells[3]})
    require(rows == [{k:p[k] for k in ('promptId','symbol','position','word')} for p in prompts],
            'Worksheet prompt IDs, symbols, positions or spelling differ from Swift')


def prepare(output):
    output = Path(output)
    require(not output.exists(), 'Coverage output must be fresh')
    inputs = {'swift':pin(SWIFT),'worksheet':pin(WORKSHEET),'cohort':pin(COHORT),'source':pin(__file__)}
    require(inputs['cohort']['sha256'] == COHORT_SHA, 'Unexpected cohort digest')
    prompts = parse_swift(SWIFT.read_text())
    validate_worksheet(WORKSHEET.read_text(), prompts, inputs['swift']['sha256'])
    mapping = {sound:(symbol,phone) for sound,symbol,phone in MAPPING}
    for prompt in prompts:
        symbol, phone = mapping[prompt['soundId']]
        require(symbol == prompt['symbol'], 'Target mapping symbol mismatch')
        prompt.update(targetPhone=phone, normalizedWord=normalize_word(prompt['word']), reviewStatus='Pending')
    plan = {'schemaVersion':1,'complete':True,'scope':'native-demo-corpus-metadata-coverage',
            'rules':RULES,'mapping':[{'soundId':a,'symbol':b,'targetPhone':c} for a,b,c in MAPPING],
            'inputFiles':inputs,'prompts':prompts,'promptCount':72,**FLAGS}
    guard(inputs); output.mkdir(parents=True); write_json(output/'plan.json', plan)
    return {'planPath':str((output/'plan.json').absolute()),'planSha256':digest(output/'plan.json'),'prompts':72}


def validate_cohort(cohort):
    require(cohort['authorPartition'] == 'train' and cohort['authorTestObjectsDecoded'] is False and
            cohort['authorTestInferencePerformed'] is False and
            cohort['targetPhones'] == [c for _,_,c in MAPPING], 'Cohort scope or target inventory differs')
    clips = {c['id']:c for c in cohort['clips']}
    require(len(clips) == len(cohort['clips']), 'Duplicate cohort clips')
    ids = set(); positions = set()
    for row in cohort['rows']:
        key = (row['clipId'],row['wordIndex'],row['phoneIndex'])
        require(row['id'] not in ids and key not in positions, 'Duplicate cohort canonical position')
        ids.add(row['id']); positions.add(key)
        counts = row['raterCounts']
        require(len(counts)==3 and all(type(v) is int and v>=0 for v in counts) and sum(counts)==5,
                'Invalid original five-rater counts')
        clip = clips[row['clipId']]
        require(row['speakerId']==clip['speakerId'] and row['age']==clip['age'] and
                cohort['targetPhones'][row['targetId']]==row['targetPhone'] and
                row['trainingEligible']==(row['targetId'] in cohort['eligibleTargetIds']),
                'Cohort row/clip or eligibility binding differs')


def summarize(rows):
    return {'positions':len({(r['clipId'],r['wordIndex'],r['phoneIndex']) for r in rows}),
            'clips':len({r['clipId'] for r in rows}),'speakers':len({r['speakerId'] for r in rows}),
            'raterCounts':[sum(r['raterCounts'][i] for r in rows) for i in range(3)]}


def coverage(prompts, cohort):
    validate_cohort(cohort)
    lookup = {}
    for row_index,row in enumerate(cohort['rows']):
        lookup.setdefault((row['targetPhone'],normalize_word(row['targetWord'])),[]).append((row_index,row))
    supported = {cohort['targetPhones'][i] for i in cohort['eligibleTargetIds']}
    results = []
    for prompt in prompts:
        matched = lookup.get((prompt['targetPhone'],prompt['normalizedWord']),[])
        children = [(i,r) for i,r in matched if 6<=r['age']<=12]
        results.append({**prompt,'modelTargetSupported':prompt['targetPhone'] in supported,
            'allAges':summarize([r for _,r in matched]),'ages6to12':summarize([r for _,r in children]),
            'matchedRowIndices':[i for i,_ in matched],'matchedChildRowIndices':[i for i,_ in children],
            'matchedCanonicalPositions':[{'rowIndex':i,'rowId':r['id'],'clipId':r['clipId'],
                'speakerId':r['speakerId'],'age':r['age'],'wordIndex':r['wordIndex'],
                'phoneIndex':r['phoneIndex'],'targetWord':r['targetWord'],'raterCounts':r['raterCounts']}
                for i,r in matched]})
    return results


def run(plan_path, expected):
    plan_path = Path(plan_path)
    plan_bytes = plan_path.read_bytes()
    require(hashlib.sha256(plan_bytes).hexdigest()==expected, 'Plan digest differs')
    plan = json.loads(plan_bytes)
    inputs={**plan['inputFiles'],'plan':{'path':str(plan_path.absolute()),'sha256':expected}}
    guard(inputs)
    require(inputs['source']==pin(__file__) and inputs['cohort']['sha256']==COHORT_SHA and
            plan['complete'] is True and plan['promptCount']==72 and
            all(plan.get(k) is False for k in FLAGS), 'Plan source, cohort or metadata-only scope differs')
    require(plan['rules']==RULES and plan['mapping']==[{'soundId':a,'symbol':b,'targetPhone':c} for a,b,c in MAPPING],
            'Plan mapping or normalization rules differ')
    swift = Path(inputs['swift']['path']); worksheet = Path(inputs['worksheet']['path'])
    prompts = parse_swift(swift.read_text()); validate_worksheet(worksheet.read_text(),prompts,inputs['swift']['sha256'])
    require([{k:p[k] for k in ('promptId','soundId','symbol','position','word')} for p in plan['prompts']]==prompts,
            'Declared prompt snapshot differs')
    for p in plan['prompts']:
        require(p['normalizedWord']==normalize_word(p['word']) and
                p['targetPhone']==dict((a,c) for a,_,c in MAPPING)[p['soundId']], 'Declared join key differs')
    cohort = json.loads(Path(inputs['cohort']['path']).read_text())
    results = coverage(plan['prompts'],cohort)
    totals = {'promptPairs':len(results),'targetSounds':len(MAPPING),
        'matchedAllAgePromptPairs':sum(r['allAges']['positions']>0 for r in results),
        'matchedChildPromptPairs':sum(r['ages6to12']['positions']>0 for r in results),
        'unsupportedPromptPairs':[r['promptId'] for r in results if not r['modelTargetSupported']],
        'unmatchedAllAgePromptPairs':[r['promptId'] for r in results if not r['allAges']['positions']],
        'unmatchedChildPromptPairs':[r['promptId'] for r in results if not r['ages6to12']['positions']]}
    report = {'schemaVersion':1,'complete':True,'planPath':str(plan_path.absolute()),'planSha256':expected,
              'inputFiles':inputs,'rules':RULES,'summary':totals,'cohortSummary':cohort['labelSummary'],
              'populationTotals':{'allAges':summarize(cohort['rows']),
                  'ages6to12':summarize([r for r in cohort['rows'] if 6<=r['age']<=12])},
              'unsupportedTargetMetadata':[{'targetPhone':phone,'modelTargetSupported':False,
                  'allAges':summarize([r for r in cohort['rows'] if r['targetPhone']==phone]),
                  'ages6to12':summarize([r for r in cohort['rows'] if r['targetPhone']==phone and 6<=r['age']<=12])}
                  for target_id,phone in enumerate(cohort['targetPhones']) if target_id not in cohort['eligibleTargetIds']],
              'rows':results,**FLAGS}
    output = plan_path.parent/'report.json'; csv_path=plan_path.parent/'coverage.csv'
    require(not output.exists() and not csv_path.exists(), 'Coverage results already exist')
    stream=io.StringIO(); writer=csv.writer(stream)
    writer.writerow(['promptId','targetPhone','symbol','intendedPosition','word','modelTargetSupported',
                     'allPositions','allClips','allSpeakers','allVote0','allVote1','allVote2',
                     'childPositions','childClips','childSpeakers','childVote0','childVote1','childVote2'])
    for row in results:
        values=[row[k] for k in ('promptId','targetPhone','symbol','position','word','modelTargetSupported')]
        for population in ('allAges','ages6to12'):
            data=row[population]; values += [data[k] for k in ('positions','clips','speakers')]+data['raterCounts']
        writer.writerow(values)
    guard(inputs)
    csv_path.write_text(stream.getvalue()); report['coverageCsv']=pin(csv_path)
    guard({**inputs,'coverageCsv':report['coverageCsv']}); write_json(output,report)
    return {'reportPath':str(output.absolute()),'reportSha256':digest(output),'summary':totals}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('run');p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
    args=parser.parse_args()
    result=prepare(args.output) if args.command=='prepare' else run(args.plan,args.plan_sha256)
    print(json.dumps(result,indent=2))
