"""Check the independently authored overlay against the pinned source pack."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from content_review.packet import compile_packet, load_pack_bytes

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'research/assessment-engineering-content'

def validate():
    packet = compile_packet(load_pack_bytes())
    decisions = json.loads((CONTENT / 'content-decisions.json').read_bytes())
    registry = json.loads((CONTENT / 'illustrations.json').read_bytes())
    assert decisions['sourcePackSha256'] == registry['sourcePackSha256'] == packet['sourcePackSha256']
    assert decisions['professionalReview'] == 'deferred_until_finished_product'
    assert decisions['professionalReviewRequiredForEngineeringPrototyping'] is False
    assert decisions['modelEngineeringReview'] == 'accepted'
    assert all(v is False for v in decisions['claimLimits'].values())
    by_id = {d['promptId']: d for d in decisions['decisions']}
    assert len(by_id) == len(decisions['decisions']) == 15
    assert set(by_id) == {p['id'] for p in packet['prompts']}
    for p in packet['prompts']:
        d = by_id[p['id']]
        assert d['professionalReview'] == 'deferred_until_finished_product'
        assert d['acceptedVariantIds'] == [v['id'] for v in p['variants']]
        for v in p['variants']:
            key = v['id']
            assert d['phonesByVariant'][key] == v['phones']
            assert d['allTargetIndexesByVariant'][key] == v['allTargetIndexes']
            assert d['selectedPositionIndexesByVariant'][key] == v['selectedPositionIndexes']
            assert type(d['chosenOccurrenceIndexByVariant'][key]) is int
            assert d['chosenOccurrenceIndexByVariant'][key] == v['selectedPositionIndexes'][0]
    allowed = {'svg', 'title', 'desc', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'}
    words = set()
    for item in registry['illustrations']:
        assert item['origin'] == 'generated_original_for_project' and item['thirdPartyAssetsUsed'] is False
        assert item['professionalReview'] == 'deferred_until_finished_product'
        words.add(item['word'])
        relative = Path(item['path'])
        assert relative.parts[0] == 'illustrations' and len(relative.parts) == 2 and relative.suffix == '.svg'
        svg = ET.fromstring((CONTENT / relative).read_bytes())
        assert svg.get('viewBox') == '0 0 240 200'
        tags = []
        for element in svg.iter():
            tag = element.tag.removeprefix('{http://www.w3.org/2000/svg}')
            assert tag in allowed, tag
            tags.append(tag)
            for name, value in element.attrib.items():
                assert not name.casefold().startswith('on') and 'href' not in name.casefold()
                assert 'url(' not in value.casefold() and 'http:' not in value.casefold() and 'https:' not in value.casefold()
        assert 'title' in tags and 'desc' in tags
    assert len(registry['illustrations']) == len(words) == 13
    assert words == {p['word'] for p in packet['prompts']}
    return {'prompts': len(by_id), 'illustrations':len(words), 'sourcePackSha256':packet['sourcePackSha256'], 'professionalReview':'deferred_until_finished_product'}

if __name__ == '__main__':
    print(json.dumps(validate(), sort_keys=True))
