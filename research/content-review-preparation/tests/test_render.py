from html.parser import HTMLParser
import unittest

from content_review.packet import compile_packet, load_pack_bytes, PacketError
from content_review.render import render_packet


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.prompts = []
        self.tables = 0
        self.external = []
        self.scripts = 0
        self.ids = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'article' and a.get('class') == 'prompt':
            self.prompts.append(a.get('id'))
        if tag == 'table' and a.get('class') == 'phones':
            self.tables += 1
        if tag == 'script':
            self.scripts += 1
        for key in ('src', 'href'):
            if key in a and not a[key].startswith('#'):
                self.external.append(a[key])


class RenderTests(unittest.TestCase):
    def test_exact_prompt_and_variant_coverage_without_external_assets(self):
        packet = compile_packet(load_pack_bytes())
        page = render_packet(packet)
        structure = Structure()
        structure.feed(page)
        self.assertEqual(len(structure.prompts), 15)
        self.assertEqual(structure.tables, 17)
        self.assertEqual(len(structure.ids), len(set(structure.ids)))
        self.assertEqual((structure.external, structure.scripts), ([], 0))
        self.assertIn('Neither is chosen here', page)
        self.assertIn('All professional review pending', page)
        self.assertIn('Not in current inventory', page)
        self.assertIn('yoyo', page)
        for prompt in packet['prompts']:
            self.assertIn(prompt['id'], page)
        self.assertEqual(page, render_packet(packet))

    def test_claim_spoof_fails_before_render(self):
        packet = compile_packet(load_pack_bytes())
        packet['claimLimits']['qualifiedApprovalEstablished'] = True
        with self.assertRaises(PacketError):
            render_packet(packet)


if __name__ == '__main__':
    unittest.main()
