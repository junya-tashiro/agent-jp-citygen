import json
import math
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from road_generator.core.general import (
    centerlines, corner_fillet_radius, junction_arms, requires_general_geometry,
    required_straight_approach_length, straight_run_from_junction,
    t_stem_signal_support_location, validate_general_network,
)
from road_generator.core.geometry import Centerline, angle_between
from road_generator.core.planner import (
    LANE_WIDTH_M, MEDIAN_NARROW_WIDTH_M,
    approach_center_marking_lateral_m, approach_existing_lateral_m, approach_median_section,
    approach_road_half_width_m, extra_lane_factor,
    plan_crosswalks, plan_medians, plan_signal_sites, road_widths_at_node,
)
from road_generator.core.schema import load_network


class CenterlineTest(unittest.TestCase):
    def test_line_uses_arc_length_and_constant_tangent(self):
        path = Centerline((0, 0), (30, 40))
        self.assertAlmostEqual(path.length, 50.0, places=6)
        self.assertEqual(path.point_at_distance(25), (15.0, 20.0))
        self.assertAlmostEqual(angle_between(path.tangent_at_distance(0), (0.6, 0.8)), 0)

    def test_gentle_bezier_has_stable_offsets_and_distance_samples(self):
        path = Centerline((0, 0), (60, 0), (18, 8), (42, 8))
        samples = path.sample_interval(max_segment=1.0)
        self.assertGreater(path.length, 60.0)
        self.assertLess(max(math.dist(a.point, b.point) for a, b in zip(samples, samples[1:])), 1.01)
        for sample in samples:
            left = path.offset_point(sample.s, 3.25)
            self.assertAlmostEqual(math.dist(left, sample.point), 3.25, places=5)

    def test_projection_finds_an_interior_station(self):
        path = Centerline((0, 0), (20, 0), (6, 3), (14, 3))
        station, distance = path.project_point(path.point_at_distance(path.length * .4))
        self.assertAlmostEqual(station, path.length * .4, delta=.03)
        self.assertLess(distance, .01)

    def test_looping_bezier_reports_self_intersection(self):
        path = Centerline((0, 0), (10, 0), (18, 18), (-8, 18))
        self.assertTrue(path.has_self_intersection())


class RoadComponentSchemaTest(unittest.TestCase):
    def test_driveway_cutout_parses_and_forces_general_geometry(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [80, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "sidewalks": "both"}],
            "components": [{"id": "d", "type": "driveway_cutout",
                            "edge": "e", "side": "left", "station": 40}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(data, handle)
            handle.flush()
            network = load_network(Path(handle.name))
        self.assertEqual(network.components[0].station, 40.0)
        self.assertTrue(requires_general_geometry(network))

    def test_driveway_cutout_requires_a_sidewalk(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [80, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b"}],
            "components": [{"id": "d", "type": "driveway_cutout",
                            "edge": "e", "side": "left", "station": 40}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(data, handle)
            handle.flush()
            with self.assertRaisesRegex(ValueError, "requires sidewalks"):
                load_network(Path(handle.name))


class GeneralJunctionTest(unittest.TestCase):
    def test_nearby_extra_lane_approaches_stay_continuous(self):
        edge = SimpleNamespace(
            lanes_each_way=2, median=True, median_width="wide",
            approaches={"from": {"extra_inbound_lane": True},
                        "to": {"extra_inbound_lane": True}})
        self.assertEqual(extra_lane_factor(edge, 40.0, 80.0), 1.0)
        left = approach_median_section(edge, 0.0, 80.0)
        middle = approach_median_section(edge, 40.0, 80.0)
        right = approach_median_section(edge, 80.0, 80.0)
        self.assertAlmostEqual(left[0], LANE_WIDTH_M * 0.5)
        self.assertAlmostEqual(middle[0], 0.0)
        self.assertAlmostEqual(right[0], -LANE_WIDTH_M * 0.5)
        self.assertAlmostEqual(approach_median_section(edge, 29.9, 80.0)[0],
                               LANE_WIDTH_M * 0.5)
        self.assertAlmostEqual(approach_median_section(edge, 50.1, 80.0)[0],
                               -LANE_WIDTH_M * 0.5)
        self.assertEqual(left[1], MEDIAN_NARROW_WIDTH_M)
        self.assertEqual(middle[1], MEDIAN_NARROW_WIDTH_M)
        self.assertEqual(right[1], MEDIAN_NARROW_WIDTH_M)

    def test_corner_fillet_shrinks_only_when_tangent_would_overrun(self):
        self.assertAlmostEqual(corner_fillet_radius(90.0, 3.8), 3.8)
        self.assertAlmostEqual(
            corner_fillet_radius(80.0, 3.8),
            3.8 * math.tan(math.radians(40.0)))
        actual_allowance = 3.1768008646178436
        fitted_radius = corner_fillet_radius(80.0, actual_allowance)
        self.assertAlmostEqual(fitted_radius, 2.6656524338244965)
        self.assertAlmostEqual(
            fitted_radius / math.tan(math.radians(40.0)), actual_allowance)
        self.assertAlmostEqual(corner_fillet_radius(100.0, 3.8), 3.8)
        self.assertLess(corner_fillet_radius(89.9999, 3.8), 3.8)
        self.assertAlmostEqual(corner_fillet_radius(90.0001, 3.8), 3.8)

    def _load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_network(path)

    def test_extra_inbound_lane_cross_section_narrow_and_wide(self):
        def edge(width, median=True):
            return self._load({
                "nodes": [
                    {"id": "c", "type": "signalized_cross", "position": [0, 0],
                     "signal_phase": "all_red"},
                    {"id": "b", "type": "boundary", "position": [80, 0]},
                ],
                "edges": [{
                    "id": "e", "from": "c", "to": "b",
                    "lanes_each_way": 2, "median": median,
                    "median_width": width,
                    "approaches": {"from": {"extra_inbound_lane": True}},
                }],
            }).edges[0]
        narrow, wide = edge("narrow"), edge("wide")
        for item in (narrow, wide):
            self.assertEqual(approach_road_half_width_m(item, "from"), 8.125)
            center, width = approach_median_section(item, 0, 80)
            self.assertEqual(center, 1.625)
            self.assertAlmostEqual(width, 0.65)
            self.assertEqual(extra_lane_factor(item, 0, 80), 1.0)
            self.assertEqual(extra_lane_factor(item, 50, 80), 0.0)
        self.assertEqual(approach_existing_lateral_m(narrow, 0, 80, 6.5), 8.125)
        self.assertEqual(approach_existing_lateral_m(wide, 0, 80, 8.125), 8.125)
        self.assertEqual(approach_median_section(narrow, 80, 80), (0.0, 0.65))
        self.assertEqual(approach_median_section(wide, 80, 80), (0.0, 3.9))
        reserve = edge("narrow")
        reserve.approaches["from"] = {"_extra_inbound_lane_reserve": True}
        self.assertEqual(approach_road_half_width_m(reserve, "from"), 8.125)
        self.assertEqual(approach_existing_lateral_m(
            reserve, 0, 80, 6.5), 8.125)
        self.assertEqual(approach_median_section(reserve, 0, 80), (0.0, 3.9))
        undivided = edge("narrow", median=False)
        self.assertEqual(approach_road_half_width_m(undivided, "from"), 8.125)
        self.assertEqual(approach_existing_lateral_m(
            undivided, 0, 80, 6.5), 8.125)
        self.assertEqual(approach_center_marking_lateral_m(
            undivided, 0, 80), 1.625)
        self.assertEqual(approach_center_marking_lateral_m(
            undivided, 30, 80), 1.625)
        self.assertEqual(approach_center_marking_lateral_m(
            undivided, 50, 80), 0.0)

    def test_line_to_cubic_split_is_tangent_continuous(self):
        network = self._load({
            "roads": [{"id": "road", "lanes_each_way": 1,
                       "sidewalks": "both"}],
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "split", "type": "boundary", "position": [10, 0]},
                {"id": "b", "type": "boundary", "position": [100, 5]},
            ],
            "edges": [
                {"id": "approach", "road": "road", "from": "a", "to": "split",
                 "geometry": {"type": "line"}},
                {"id": "curve", "road": "road", "from": "split", "to": "b",
                 "geometry": {"type": "cubic_bezier",
                              "control_from": [35, 1], "control_to": [70, 5]}},
            ],
        })
        paths = centerlines(network)
        self.assertAlmostEqual(angle_between(
            paths["approach"].tangent_at_distance(paths["approach"].length),
            paths["curve"].tangent_at_distance(0.0)), 0.0, places=8)

    def test_eighty_degree_cross_has_angle_sorted_arms_and_two_road_groups(self):
        network = self._load({
            "roads": [
                {"id": "main", "lanes_each_way": 1, "sidewalks": "both"},
                {"id": "cross", "lanes_each_way": 1, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"], "signal_phase": "group_a_green"},
                {"id": "w", "type": "boundary", "position": [-30, 0]},
                {"id": "e", "type": "boundary", "position": [30, 0]},
                {"id": "s", "type": "boundary", "position": [-5.21, -29.54]},
                {"id": "n", "type": "boundary", "position": [5.21, 29.54]},
            ],
            "edges": [
                {"id": "w", "road": "main", "from": "c", "to": "w", "geometry": {"type": "line"}},
                {"id": "e", "road": "main", "from": "c", "to": "e", "geometry": {"type": "line"}},
                {"id": "s", "road": "cross", "from": "c", "to": "s", "geometry": {"type": "line"}},
                {"id": "n", "road": "cross", "from": "c", "to": "n", "geometry": {"type": "line"}},
            ],
        })
        paths = validate_general_network(network)
        arms = junction_arms(network, "c", paths)
        self.assertEqual(len(arms), 4)
        self.assertEqual({arm.road_id for arm in arms}, {"main", "cross"})

    def test_straight_approach_uses_perpendicular_width_and_split_line_chain(self):
        network = self._load({
            "roads": [
                {"id": "narrow", "lanes_each_way": 1, "sidewalks": "both"},
                {"id": "wide", "lanes_each_way": 3, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"],
                 "signal_phase": "group_a_green"},
                {"id": "wm", "type": "boundary", "position": [-12, 0]},
                {"id": "w", "type": "boundary", "position": [-40, 0]},
                {"id": "e", "type": "boundary", "position": [40, 0]},
                {"id": "s", "type": "boundary", "position": [0, -40]},
                {"id": "n", "type": "boundary", "position": [0, 40]},
            ],
            "edges": [
                {"id": "w0", "road": "narrow", "from": "c", "to": "wm", "geometry": {"type": "line"}},
                {"id": "w1", "road": "narrow", "from": "wm", "to": "w", "geometry": {"type": "line"}},
                {"id": "e", "road": "narrow", "from": "c", "to": "e", "geometry": {"type": "line"}},
                {"id": "s", "road": "wide", "from": "c", "to": "s", "geometry": {"type": "line"}},
                {"id": "n", "road": "wide", "from": "c", "to": "n", "geometry": {"type": "line"}},
            ],
        })
        paths = validate_general_network(network)
        arms = junction_arms(network, "c", paths)
        west = next(arm for arm in arms if arm.edge_id == "w0")
        south = next(arm for arm in arms if arm.edge_id == "s")
        self.assertAlmostEqual(required_straight_approach_length(west, arms), 27.10)
        self.assertAlmostEqual(required_straight_approach_length(south, arms), 20.60)
        self.assertAlmostEqual(straight_run_from_junction(network, west, paths), 40.0)

    def test_short_straight_approach_is_rejected(self):
        data = self._rotated_t_definition()
        next(item for item in data["nodes"] if item["id"] == "s")["position"] = [0, -18]
        with self.assertRaisesRegex(ValueError, "10m beyond the crosswalk"):
            validate_general_network(self._load(data))

    def test_rotated_wide_cross_keeps_both_widths_and_four_median_islands(self):
        def point(angle):
            radians = math.radians(angle)
            return [30 * math.cos(radians), 30 * math.sin(radians)]
        network = self._load({
            "roads": [
                {"id": "a", "lanes_each_way": 3, "sidewalks": "both"},
                {"id": "b", "lanes_each_way": 3, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"],
                 "signal_phase": "group_a_green"},
                *({"id": f"n{i}", "type": "boundary", "position": point(angle)}
                  for i, angle in enumerate((38, 218, 136, 316))),
            ],
            "edges": [
                {"id": "a0", "road": "a", "from": "c", "to": "n0",
                 "median": True, "geometry": {"type": "line"}},
                {"id": "a1", "road": "a", "from": "c", "to": "n1",
                 "median": True, "geometry": {"type": "line"}},
                {"id": "b0", "road": "b", "from": "c", "to": "n2",
                 "median": True, "geometry": {"type": "line"}},
                {"id": "b1", "road": "b", "from": "c", "to": "n3",
                 "median": True, "geometry": {"type": "line"}},
            ],
        })
        self.assertEqual(road_widths_at_node(network, "c"), (19.5, 19.5))
        medians = plan_medians(network, plan_crosswalks(network))
        self.assertEqual(len([item for item in medians if item.node_id == "c"]), 4)

    def test_seventy_nine_degree_cross_is_outside_the_supported_limit(self):
        data = {
            "roads": [
                {"id": "main", "lanes_each_way": 1, "sidewalks": "both"},
                {"id": "cross", "lanes_each_way": 1, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"],
                 "signal_phase": "group_a_green"},
                {"id": "w", "type": "boundary", "position": [-30, 0]},
                {"id": "e", "type": "boundary", "position": [30, 0]},
                {"id": "s", "type": "boundary", "position": [-5.727, -29.448]},
                {"id": "n", "type": "boundary", "position": [5.727, 29.448]},
            ],
            "edges": [
                {"id": "w", "road": "main", "from": "c", "to": "w",
                 "geometry": {"type": "line"}},
                {"id": "e", "road": "main", "from": "c", "to": "e",
                 "geometry": {"type": "line"}},
                {"id": "s", "road": "cross", "from": "c", "to": "s",
                 "geometry": {"type": "line"}},
                {"id": "n", "road": "cross", "from": "c", "to": "n",
                 "geometry": {"type": "line"}},
            ],
        }
        with self.assertRaisesRegex(ValueError, "unsupported intersection angle"):
            validate_general_network(self._load(data))

    def _rotated_t_definition(self):
        return {
            "roads": [
                {"id": "through", "lanes_each_way": 1, "sidewalks": "both"},
                {"id": "stem", "lanes_each_way": 1, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "t", "type": "signalized_t_junction", "position": [0, 0],
                 "crossings": ["east_west", "north_south"],
                 "signal_phase": "group_a_green"},
                {"id": "w", "type": "boundary", "position": [-29.544233, -5.209445]},
                {"id": "e", "type": "boundary", "position": [29.544233, 5.209445]},
                {"id": "s", "type": "boundary", "position": [0, -30]},
            ],
            "edges": [
                {"id": "west", "road": "through", "from": "t", "to": "w",
                 "geometry": {"type": "line"}},
                {"id": "east", "road": "through", "from": "t", "to": "e",
                 "geometry": {"type": "line"}},
                {"id": "south", "road": "stem", "from": "t", "to": "s",
                 "geometry": {"type": "line"}},
            ],
        }

    def test_rotated_t_through_road_remains_straight(self):
        validate_general_network(self._load(self._rotated_t_definition()))

    def test_t_stem_signal_uses_wide_through_road_edge(self):
        data = self._rotated_t_definition()
        next(road for road in data["roads"] if road["id"] == "through")["lanes_each_way"] = 2
        network = self._load(data)
        paths = validate_general_network(network)
        arms = junction_arms(network, "t", paths)
        stem = next(arm for arm in arms if arm.road_id == "stem")
        through = next(arm for arm in arms if arm.road_id == "through")
        site = next(item for item in plan_signal_sites(network)
                    if item.id == "t_south_vehicle")
        actual = t_stem_signal_support_location(
            network.nodes["t"].position, stem, through, site.location)
        open_direction = (-stem.outward[0], -stem.outward[1])
        normal = (-through.outward[1], through.outward[0])
        if normal[0] * open_direction[0] + normal[1] * open_direction[1] < 0:
            normal = (-normal[0], -normal[1])
        lateral = actual[0] * normal[0] + actual[1] * normal[1]
        self.assertAlmostEqual(lateral, 2 * 3.25 + 0.42, places=6)

    def test_t_through_road_cannot_change_angle_at_the_node(self):
        data = self._rotated_t_definition()
        next(item for item in data["nodes"] if item["id"] == "e")["position"] = [
            29.630650, 4.693034]  # 9 degrees, versus 10 westward.
        with self.assertRaisesRegex(ValueError, "must be straight through T junction"):
            validate_general_network(self._load(data))

    def test_curve_cannot_start_at_a_junction_even_with_continuous_tangents(self):
        data = self._rotated_t_definition()
        edges = {item["id"]: item for item in data["edges"]}
        edges["west"]["geometry"] = {
            "type": "cubic_bezier",
            "control_from": [-7.878463, -1.389185],
            "control_to": [-20.0, -3.2],
        }
        edges["east"]["geometry"] = {
            "type": "cubic_bezier",
            "control_from": [7.878463, 1.389185],
            "control_to": [20.0, 3.8],
        }
        with self.assertRaisesRegex(
                ValueError, "straight incident edges.*curves cannot pass"):
            validate_general_network(self._load(data))

    def test_through_road_may_bend_twenty_degrees(self):
        network = self._load({
            "roads": [
                {"id": "main", "lanes_each_way": 1, "sidewalks": "both"},
                {"id": "cross", "lanes_each_way": 1, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"], "signal_phase": "group_a_green"},
                {"id": "a", "type": "boundary", "position": [-30, -5.29]},
                {"id": "b", "type": "boundary", "position": [30, -5.29]},
                {"id": "d", "type": "boundary", "position": [0, -30]},
                {"id": "e", "type": "boundary", "position": [0, 30]},
            ],
            "edges": [
                {"id": "a", "road": "main", "from": "c", "to": "a", "geometry": {"type": "line"}},
                {"id": "b", "road": "main", "from": "c", "to": "b", "geometry": {"type": "line"}},
                {"id": "d", "road": "cross", "from": "c", "to": "d", "geometry": {"type": "line"}},
                {"id": "e", "road": "cross", "from": "c", "to": "e", "geometry": {"type": "line"}},
            ],
        })
        validate_general_network(network)

    def test_one_degree_centerline_rotation_is_small_and_uses_general_geometry(self):
        root = Path(__file__).resolve().parents[2]
        orthogonal = load_network(
            root / "road_generator/examples/general_geometry/"
            "comparison_cross_all_features_orthogonal.json")
        one_degree = load_network(
            root / "road_generator/examples/general_geometry/"
            "comparison_cross_all_features_1deg.json")
        self.assertTrue(requires_general_geometry(orthogonal))
        self.assertTrue(requires_general_geometry(one_degree))
        paths = validate_general_network(one_degree)
        north = paths["cross_2"]
        baseline = Centerline((0, 0), (0, 36))
        self.assertAlmostEqual(
            angle_between(north.tangent_at_distance(10),
                          baseline.tangent_at_distance(10)), 1.0, places=5)
        # This is a centreline/frame test only. Blender equipment continuity is
        # a separate regression concern and must not be inferred from it.
        angle = math.radians(1.0)
        for station, lateral in ((7.05, 3.32), (9.0, 3.70), (12.6, 6.25)):
            actual = north.offset_point(station, lateral)
            expected = baseline.offset_point(station, lateral)
            radius = math.hypot(station, lateral)
            displacement = math.dist(actual, expected)
            self.assertAlmostEqual(
                displacement, 2 * radius * math.sin(angle * 0.5), delta=2e-5)
            self.assertLess(displacement, 0.25)

    def test_explicit_lines_use_one_renderer_at_zero_and_sub_millimetre_angles(self):
        root = Path(__file__).resolve().parents[2]
        source = json.loads((
            root / "road_generator/examples/general_geometry/"
            "comparison_cross_all_features_orthogonal.json").read_text())
        for degrees in (0.0, 0.0001, 0.0002):
            data = json.loads(json.dumps(source))
            displacement = 36.0 * math.tan(math.radians(degrees))
            positions = {item["id"]: item["position"] for item in data["nodes"]}
            positions["x1"][0] = -displacement
            positions["x2"][0] = displacement
            with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
                json.dump(data, handle)
                handle.flush()
                network = load_network(Path(handle.name))
            self.assertTrue(requires_general_geometry(network))


if __name__ == "__main__":
    unittest.main()
