import math
import unittest
from asset_library.subway_entrance.scripts.design import entrance_spec
from road_generator.core.subway import parse_subway_entrances


class SubwayDesignTests(unittest.TestCase):
    def test_stair_geometry_closes_at_bottom_landing(self):
        s=entrance_spec()
        self.assertAlmostEqual(s['stair_count']*s['stair_rise'],s['depth'])
        self.assertLess(.9+s['stair_count']*s['stair_run'],s['opening'][3])
        self.assertGreater(s['opening'][0],s['footprint'][0])
        self.assertLess(s['opening'][2],s['footprint'][2])
    def test_elevator_has_no_excavation(self):
        self.assertIsNone(entrance_spec('elevator')['opening'])
    def test_invalid_dimensions(self):
        for width in (True,float('nan'),float('inf'),0,-3,2,4.1):
            with self.subTest(width=width),self.assertRaises(ValueError):entrance_spec(width=width)
        with self.assertRaises(ValueError):entrance_spec('escalator')
    def test_labels_and_rotation_preserved(self):
        item=dict(id='a',position=[1,2],station_name='駅前',station_roman='Ekimae',rotation_degrees=180)
        parsed=parse_subway_entrances([item])[0]
        self.assertEqual(parsed['station_name'],item['station_name'])
        self.assertEqual(parsed['rotation_degrees'],180)
        self.assertEqual(parsed['exit_label'],'')
    def test_weathering_is_validated_and_preserved(self):
        base=dict(id='a',position=[1,2],station_name='中央')
        for value in (0,.18,1):
            self.assertEqual(parse_subway_entrances([dict(base,weathering=value)])[0]['weathering'],value)
        for value in (True,-.1,1.1,float('nan'),'old'):
            with self.subTest(value=value),self.assertRaises(ValueError):parse_subway_entrances([dict(base,weathering=value)])
    def test_invalid_context(self):
        base=dict(id='a',position=[1,2],station_name='中央')
        for delta in (dict(position=[float('nan'),0]),dict(position=[0]),dict(rotation_degrees=True),dict(station_name=' '),dict(station_roman=7),dict(variant='other')):
            with self.subTest(delta=delta),self.assertRaises(ValueError):parse_subway_entrances([dict(base,**delta)])
        with self.assertRaises(ValueError):parse_subway_entrances([base,base])
        with self.assertRaises(ValueError):parse_subway_entrances({})

if __name__=='__main__':unittest.main()
