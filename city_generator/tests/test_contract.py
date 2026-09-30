import copy,json,unittest
from pathlib import Path
from city_generator.planning import plan_city,validate_plan
from city_generator.roads import compile_roads
from city_generator.geometry import overlap,rectangle
ROOT=Path(__file__).resolve().parents[2]
class Contract(unittest.TestCase):
 def request(self):
  r=json.loads((ROOT/'examples/city/central_200.json').read_text());r['buildings']['count']=6;return r
 def test_reproducible_and_unsignalized(self):
  a=plan_city(self.request());b=plan_city(self.request());self.assertEqual(a,b);self.assertTrue(validate_plan(a)['valid']);self.assertTrue(any(n['type']=='stop_cross' for n in a['network']['nodes']))
 def test_gui_document_round_trip(self):
  x=compile_roads(self.request());self.assertEqual(x['network'],compile_roads({'document':x['document']})['network'])
 def test_reject_signal_request_on_arterial(self):
  r=self.request();r['junctions']=[{'at':[0,0],'style':{'signal_control':'unsignalized'}}]
  with self.assertRaises(ValueError):plan_city(r)
 def test_reject_bad_radius(self):
  r=self.request();r['roads']=[{'points':[[-80,0],[0,0],[0,80]]}];r['junctions']=[]
  with self.assertRaises(ValueError):plan_city(r)
 def test_tampered_plan(self):
  p=plan_city(self.request());p['placements'][0]['position'][0]+=1
  with self.assertRaisesRegex(ValueError,'Plan changed'):validate_plan(p)
 def test_explicit_collision(self):
  r=self.request();r['placements']=[{'id':str(i),'key':'building_23','edge':'avenue_edge_1_1','station':30,'side':'left'} for i in range(2)]
  with self.assertRaises(ValueError):plan_city(r)
 def test_forged_derived_position(self):
  from city_generator.planning import fingerprint
  p=plan_city(self.request());p['placements'][0]['position'][0]+=10
  p['fingerprint']=fingerprint({k:v for k,v in p.items() if k!='fingerprint'})
  with self.assertRaisesRegex(ValueError,'Derived placement'):validate_plan(p)
 def test_empty_roads(self):
  r=self.request();r['roads']=[];r['junctions']=[]
  with self.assertRaises(ValueError):plan_city(r)
 def test_unknown_option(self):
  r=self.request();r['buildingz']={}
  with self.assertRaises(ValueError):plan_city(r)
 def test_curved_sites(self):
  r=json.loads((ROOT/'examples/city/curved_300.json').read_text());r['buildings']['count']=4
  p=plan_city(r);self.assertEqual(p['summary']['buildings'],4);self.assertTrue(validate_plan(p)['valid'])
 def test_curved_parking_and_legacy(self):
  r=json.loads((ROOT/'examples/city/curved_300.json').read_text());r['buildings']['count']=1
  r['placements']=[{'id':'legacy','key':'building_06','edge':'curve_edge_1_1','station':35,'side':'right'}, {'id':'coin','type':'coin_parking','width':18,'depth':24,'edge':'curve_edge_2_1','station':32,'side':'left'}]
  p=plan_city(r);self.assertTrue(validate_plan(p)['valid']);self.assertEqual(p['summary']['coin_parking'],1)
 def test_occupancy(self):
  a=rectangle([0,0,10,10]);self.assertTrue(overlap(a,rectangle([9,9,12,12])));self.assertFalse(overlap(a,rectangle([10,0,12,12])))
if __name__=='__main__':unittest.main()
