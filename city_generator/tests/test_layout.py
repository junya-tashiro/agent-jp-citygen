import copy
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from city_generator.layout import svg
from city_generator.planning import plan_city, fingerprint

ROOT=Path(__file__).resolve().parents[2]
NS={'s':'http://www.w3.org/2000/svg'}

class MapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        request=json.loads((ROOT/'examples/city/avenue_500.json').read_text())
        request['buildings']['count']=2
        cls.plan=plan_city(request)

    def test_map_is_offline_and_escapes_text(self):
        with patch('subprocess.run',side_effect=AssertionError('Map must not launch a process')):
            root=ET.fromstring(svg(self.plan,'A < B & C'))
        self.assertEqual(root.find('s:title',NS).text,'A < B & C')
        for layer in ('sites','sidewalks','carriageways','junctions','driveways','subways'):
            self.assertTrue(len(root.find(f'.//s:g[@id="{layer}"]',NS)))
        self.assertEqual(len(root.findall('.//s:g[@id="subways"]/s:polygon',NS)),2)
        self.assertFalse(root.findall('.//s:image',NS))

    def test_old_source_is_viewable_but_modified_plan_is_rejected(self):
        p=copy.deepcopy(self.plan);p['source_signature']='historical'
        p['fingerprint']=fingerprint({k:v for k,v in p.items() if k!='fingerprint'})
        ET.fromstring(svg(p))
        p['placements'][0]['position'][0]+=1
        with self.assertRaisesRegex(ValueError,'Plan changed'):svg(p)

    def test_labels_can_be_hidden_without_removing_sites(self):
        root=ET.fromstring(svg(self.plan,labels=False))
        sites=root.find('.//s:g[@id="sites"]',NS)
        self.assertTrue(sites.findall('s:polygon',NS))
        self.assertFalse(sites.findall('s:text',NS))

if __name__=='__main__':unittest.main()
