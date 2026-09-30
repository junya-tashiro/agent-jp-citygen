"""Regression checks for subdivision-independent street design."""
import json
from pathlib import Path
import tempfile
import unittest
from road_generator.core.schema import load_network
from road_generator.core.streets import street_stations, sidewalk_footprint
from road_generator.core.planner import plan_street_trees, plan_crosswalks


class StreetContinuityTests(unittest.TestCase):
    def network(self,split=False,reverse=False):
        nodes=[{'id':'a','type':'boundary','position':[0,0]},
               {'id':'z','type':'boundary','position':[100,0]}]
        edges=[{'id':'original','from':'a','to':'z'}]
        if split:
            nodes.append({'id':'middle','type':'boundary','position':[37,0]})
            edges=[{'id':'new_b','from':'a','to':'middle'},
                   {'id':'new_a','from':'middle','to':'z'}]
        if reverse:
            edges=[dict(e,**{'from':e['to'],'to':e['from']}) for e in reversed(edges)]
        for e in edges:e.update(road='avenue',planting={'random':True,'style':'clipped_hedge'},
                               street_trees={'random':True},street_lights=False)
        data={'nodes':nodes,'roads':[{'id':'avenue','sidewalks':'both'}],'edges':edges}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'road.json';path.write_text(json.dumps(data))
            return load_network(path)

    def test_anchors_survive_split_reversal_and_array_order(self):
        def anchors(network):
            from road_generator.core.geometry import Centerline
            frames=street_stations(network)
            result=[]
            for e in network.edges:
                path=Centerline.from_edge(network,e)
                for s,i in frames[e.id].positions(0,path.length,10,17,.1):
                    result.append((i,tuple(round(v,6) for v in path.point_at_distance(s))))
            return sorted(result)
        self.assertEqual(anchors(self.network()),anchors(self.network(True)))
        self.assertEqual(anchors(self.network()),anchors(self.network(True,True)))

    def test_random_design_is_shared_by_logical_road(self):
        original=self.network().edges[0]
        for edge in self.network(True).edges:
            self.assertEqual(edge.street_trees,original.street_trees)
            self.assertEqual(edge.planting,original.planting)

    def test_tree_instances_survive_split(self):
        def trees(network):
            return sorted((p.id,p.species,p.seed,tuple(round(v,5) for v in p.location))
                          for p in plan_street_trees(network,plan_crosswalks(network)))
        self.assertEqual(trees(self.network()),trees(self.network(True)))

    def test_width_tracks_edge_configuration(self):
        from dataclasses import replace
        edge=self.network().edges[0]
        self.assertAlmostEqual(sidewalk_footprint(edge),3.8)
        self.assertAlmostEqual(sidewalk_footprint(replace(edge,median=True)),7.4)

if __name__=='__main__':unittest.main()
