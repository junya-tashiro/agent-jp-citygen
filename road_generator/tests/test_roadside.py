"""Regression checks for roadside fixtures across approach/width boundaries."""
from dataclasses import replace
import math
import unittest

from road_generator.core.geometry import Centerline
from road_generator.core.roadside import roadside_site
from road_generator.core.schema import Edge


class RoadsideSiteTests(unittest.TestCase):
    def setUp(self):
        self.edge = Edge('approach', 'a', 'b', 'local', 30, 2, 'both',
                         approaches={'from': {'extra_inbound_lane': True}})
        self.path = Centerline((0, 0), (100, 0))

    def test_full_taper_and_normal_sections_on_both_sides(self):
        for station, width in ((20, 8.125), (40, 7.3125), (60, 6.5)):
            for side in (-1, 1):
                with self.subTest(station=station, side=side):
                    point, tangent, edge, local = roadside_site(
                        [(self.edge, 'a')], {'approach': self.path}, station, side, .3)
                    self.assertAlmostEqual(point[0], station)
                    self.assertAlmostEqual(point[1], side * (width + .3))
                    self.assertEqual(tangent, (1, 0))

    def test_reversed_traversal_preserves_physical_site_and_facing(self):
        for station in (20, 40, 60):
            for side in (-1, 1):
                forward = roadside_site([(self.edge, 'a')], {'approach': self.path},
                                        station, side, .3)
                reverse = roadside_site([(self.edge, 'b')], {'approach': self.path},
                                        100-station, -side, .3)
                self.assertEqual(forward[0], reverse[0])
                self.assertEqual(reverse[1], (-1, 0))
                self.assertEqual(forward[3], reverse[3])

    def test_uses_supporting_edge_width_after_split(self):
        second = replace(self.edge, id='second', start='b', end='c',
                         lanes_each_way=3, approaches={})
        paths = {'approach': self.path, 'second': Centerline((100,0), (200,0))}
        point, _, edge, local = roadside_site(
            [(self.edge,'a'),(second,'b')], paths, 140, 1, .3)
        self.assertEqual(edge.id, 'second')
        self.assertEqual(local, 40)
        self.assertAlmostEqual(point[1], 10.05)

    def test_wide_median_does_not_add_a_second_widening(self):
        edge = replace(self.edge, median=True, median_width='wide')
        point, _, _, _ = roadside_site([(edge,'a')], {'approach':self.path}, 20, 1, .3)
        self.assertAlmostEqual(point[1], 8.425)

    def test_curved_rotated_approach_uses_local_normal(self):
        path = Centerline((0,0),(70,70),(40,0),(70,40))
        point,tangent,_,_ = roadside_site([(self.edge,'a')], {'approach':path},20,1,.3)
        centre = path.point_at_distance(20)
        delta = (point[0]-centre[0],point[1]-centre[1])
        self.assertAlmostEqual(math.hypot(*delta),8.425)
        self.assertAlmostEqual(delta[0]*tangent[0]+delta[1]*tangent[1],0)
