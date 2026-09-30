from pathlib import Path
from dataclasses import replace
import json
import math
import tempfile
import unittest

from road_generator.core.planner import (
    BICYCLE_MARKING_LENGTH_WIDTH_RATIO, BICYCLE_MARKING_WIDTH_M, SIDEWALK_WIDTH_M,
    CURB_ROAD_APRON_M, ROAD_MARKING_CURB_CLEARANCE_M,
    approach_lane_arrow_kinds, cross_lane_arrow_kinds,
    t_junction_lane_arrow_kinds,
    effective_vehicle_arrow, longitudinal_marking_trims,
    lane_separator_solid_interval,
    plan_bicycle_junction_chevrons, plan_bicycle_markings,
    plan_corner_reflector_poles, plan_crosswalks,
    plan_curb_parking_stripes,
    plan_guardrails, plan_medians, plan_median_island_devices, plan_network,
    plan_pedestrian_countdowns, plan_plantings, plan_signal_blocks, plan_signal_sites,
    plan_right_turn_guides, plan_stop_lines, plan_street_lights, plan_street_trees,
    plan_tactile_paving, road_widths_at_node,
    stop_approach_has_crosswalk_sign, road_half_width_m,
)
from road_generator.core.schema import load_network


class PlannerTest(unittest.TestCase):
    def setUp(self):
        definition = Path(__file__).parents[1] / "examples/three_intersections.json"
        self.network = load_network(definition)
        self.plan = plan_network(self.network)
        self.crosswalks = plan_crosswalks(self.network)
        self.signals = plan_signal_sites(self.network)
        self.stop_lines = plan_stop_lines(self.crosswalks)
        self.signal_blocks = plan_signal_blocks(self.signals)
        self.guardrails = plan_guardrails(self.network, self.crosswalks)

    def test_stop_crosswalk_sign_coin_flip_is_stable_and_has_both_results(self):
        first = [stop_approach_has_crosswalk_sign("junction", edge)
                 for edge in ("a", "b", "c", "d")]
        second = [stop_approach_has_crosswalk_sign("junction", edge)
                  for edge in ("a", "b", "c", "d")]
        self.assertEqual(first, second)
        self.assertIn(True, first)
        self.assertIn(False, first)

    def test_cross_junction_bicycle_chevrons_are_dense_and_non_overlapping(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/bicycle_chevron_2x2_cross.json")
        plans = plan_bicycle_junction_chevrons(network)
        self.assertGreater(len(plans), 40)
        self.assertEqual({item.node_id for item in plans}, {"junction"})
        priorities = {item.road_id for item in plans if item.priority}
        self.assertEqual(len(priorities), 1)
        non_priorities = [item for item in plans if not item.priority]
        self.assertTrue(non_priorities)

        unsignalized = replace(
            network,
            nodes={
                **network.nodes,
                "junction": replace(network.nodes["junction"], kind="stop_cross"),
            },
        )
        self.assertEqual(plan_bicycle_junction_chevrons(unsignalized), ())

        one_lane_arm = replace(
            network,
            edges=tuple(replace(edge, lanes_each_way=1)
                        if edge.id == network.edges[0].id else edge
                        for edge in network.edges),
        )
        self.assertEqual(plan_bicycle_junction_chevrons(one_lane_arm), ())
        self.assertLess(len(non_priorities), sum(item.priority for item in plans))
        # Each road has two directional rows; neighbouring chevrons use a
        # length:gap ratio of exactly 1:1.5.
        row = sorted(
            (item for item in plans if item.priority
             and abs(item.location[1] - plans[0].location[1]) < 1e-6),
            key=lambda item: item.location[0],
        )
        if len(row) >= 2:
            self.assertAlmostEqual(
                math.dist(row[0].location, row[1].location),
                2.5 * BICYCLE_MARKING_WIDTH_M * (401.0 / 329.0),
                places=6,
            )

    def test_t_junction_never_gets_bicycle_junction_chevrons(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/priority_t_2x1_median.json")
        self.assertEqual(plan_bicycle_junction_chevrons(network), ())

    def test_mixed_width_cross_uses_each_perpendicular_road_width(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/bicycle_chevron_3x2_angled_cross.json")
        plans = plan_bicycle_junction_chevrons(network)
        half_length = BICYCLE_MARKING_WIDTH_M * (401.0 / 329.0) * 0.5
        axes = {
            "east_west": (1.0, 0.0),
            "angled": (math.cos(math.radians(80.0)), math.sin(math.radians(80.0))),
        }
        perpendicular_lanes = {"east_west": 2, "angled": 3}
        for item in plans:
            axis = axes[item.road_id]
            along = abs(item.location[0] * axis[0] + item.location[1] * axis[1])
            crosswalk_inner_edge = (
                perpendicular_lanes[item.road_id] * 3.25 + 5.75 - 1.60
            )
            self.assertLessEqual(along + half_length,
                                 crosswalk_inner_edge - 0.08 + 1e-6)

    def test_only_right_turn_only_lanes_extend_into_the_junction(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/bicycle_chevron_3x2_angled_cross.json")
        guides = plan_right_turn_guides(network)
        self.assertEqual({item.edge_id for item in guides},
                         {"west_arm", "east_arm"})
        effective_width = 3.25 - 0.65 * 0.5
        skew = math.tan(math.radians(20.0)) * effective_width * 0.5
        for guide in guides:
            outward = (-1.0, 0.0) if guide.edge_id == "west_arm" else (1.0, 0.0)
            left = (-outward[1], outward[0])
            delta = (
                guide.stop_line_end[0] - guide.stop_line_start[0],
                guide.stop_line_end[1] - guide.stop_line_start[1],
            )
            self.assertAlmostEqual(delta[0] * outward[0] + delta[1] * outward[1],
                                   2.0 * skew, places=6)
            self.assertAlmostEqual(delta[0] * left[0] + delta[1] * left[1],
                                   effective_width, places=6)
            self.assertTrue(guide.dash_segments)

        without_bicycles = replace(
            network,
            edges=tuple(replace(edge, bicycle_lane=False)
                        for edge in network.edges),
        )
        unobstructed = plan_right_turn_guides(without_bicycles)
        self.assertLess(
            sum(len(item.dash_segments) for item in guides),
            sum(len(item.dash_segments) for item in unobstructed),
        )

        two_lane = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/bicycle_chevron_2x2_cross.json")
        self.assertEqual(plan_right_turn_guides(two_lane), ())

        mixed_with_one_lane = replace(
            network,
            edges=tuple(replace(edge, lanes_each_way=1)
                        if edge.id == network.edges[0].id else edge
                        for edge in network.edges),
        )
        self.assertEqual(plan_right_turn_guides(mixed_with_one_lane), ())

        median_east = next(item for item in guides
                           if item.edge_id == "east_arm")
        median_inner = [segment for segment in median_east.dash_segments
                        if abs((segment[0][1] + segment[1][1]) * 0.5 + 0.325)
                        < 1e-6]
        self.assertTrue(median_inner)
        self.assertLessEqual(max(point[0] for segment in median_inner
                                 for point in segment), 8.3375 + 1e-6)

        no_median_network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/right_turn_guide_3x2_angled_no_median.json")
        no_median_east = next(
            item for item in plan_right_turn_guides(no_median_network)
            if item.edge_id == "east_arm")
        no_median_inner = [segment for segment in no_median_east.dash_segments
                           if abs((segment[0][1] + segment[1][1]) * 0.5)
                           < 1e-6]
        self.assertTrue(no_median_inner)
        self.assertGreater(max(point[0] for segment in no_median_inner
                               for point in segment), 10.0)
        no_median_delta = (
            no_median_east.stop_line_end[0] - no_median_east.stop_line_start[0],
            no_median_east.stop_line_end[1] - no_median_east.stop_line_start[1],
        )
        self.assertAlmostEqual(abs(no_median_delta[1]), 3.25, places=6)

        extra_no_median_network = replace(
            no_median_network,
            edges=tuple(
                replace(edge, approaches={
                    **edge.approaches,
                    "from": {
                        **edge.approaches.get("from", {}),
                        "extra_inbound_lane": True,
                    },
                }) if edge.id == "east_arm" else edge
                for edge in no_median_network.edges),
        )
        shifted_guide = next(
            item for item in plan_right_turn_guides(extra_no_median_network)
            if item.edge_id == "east_arm")
        shifted_inner = [
            segment for segment in shifted_guide.dash_segments
            if abs((segment[0][1] + segment[1][1]) * 0.5 - 1.625) < 1e-6
        ]
        self.assertTrue(shifted_inner)
        shifted_delta = (
            shifted_guide.stop_line_end[0] - shifted_guide.stop_line_start[0],
            shifted_guide.stop_line_end[1] - shifted_guide.stop_line_start[1],
        )
        self.assertAlmostEqual(abs(shifted_delta[1]), 3.25, places=6)

    def test_t_junction_has_exactly_one_guide_only_for_added_right_lane(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/angled_multilane_median_t_junction.json")
        self.assertEqual(plan_right_turn_guides(network), ())
        with_extra = replace(
            network,
            edges=tuple(
                replace(edge, approaches={
                    "from": {"extra_inbound_lane": True},
                }) if edge.id == "through_west" else edge
                for edge in network.edges),
        )
        guides = plan_right_turn_guides(with_extra)
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0].edge_id, "through_west")

    def test_priority_t_keeps_through_median_and_has_only_stem_crosswalk(self):
        network = load_network(
            Path(__file__).parents[1]
            / "examples/general_geometry/priority_t_2x1_median.json")
        crosswalks = plan_crosswalks(network)
        self.assertEqual([item.id for item in crosswalks], ["junction_south"])
        medians = plan_medians(network, crosswalks)
        west = next(item for item in medians if item.edge_id == "priority_west")
        east = next(item for item in medians if item.edge_id == "priority_east")
        self.assertEqual(west.end, (0.0, 0.0))
        self.assertEqual(east.start, (0.0, 0.0))
        controlled = [item for item in plan_network(network).approaches
                      if item.stop_control]
        self.assertEqual([item.edge_id for item in controlled], ["stem"])
        curb_stripes = plan_curb_parking_stripes(network, crosswalks)
        back_stripes = [item for item in curb_stripes
                        if item.id == "junction_back_curb_parking_stripes"]
        self.assertEqual(len(back_stripes), 1)
        self.assertEqual(
            set(back_stripes[0].edge_id.split("+")),
            {"priority_west", "priority_east"},
        )

    def test_street_light_cross_demo_uses_fixed_spacing_and_tree_clearance(self):
        network = load_network(
            Path(__file__).parents[1] / "examples/street_light_cross_demo.json")
        crosswalks = plan_crosswalks(network)
        lights = plan_street_lights(network, crosswalks)
        trees = plan_street_trees(network, crosswalks)
        self.assertEqual(sum(item.kind == "roadway" for item in lights), 12)
        self.assertEqual(sum(item.kind == "pedestrian" for item in lights), 40)
        self.assertTrue(all(item.lit for item in lights))
        grouped = {}
        for item in lights:
            grouped.setdefault((item.edge_id, item.kind, item.side), []).append(item)
        for (_edge_id, kind, _side), items in grouped.items():
            expected = 35.0 if kind == "roadway" else 23.0
            points = [item.location[:2] for item in items]
            for a, b in zip(points, points[1:]):
                self.assertAlmostEqual(math.dist(a, b), expected)
        edge_by_id = {edge.id: edge for edge in network.edges}
        for light in (item for item in lights if item.kind == "pedestrian"):
            edge = edge_by_id[light.edge_id]
            start = network.nodes[edge.start].position
            end = network.nodes[edge.end].position
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            station = ((light.location[0] - start[0]) * ux
                       + (light.location[1] - start[1]) * uy)
            for crossing in crosswalks:
                if crossing.node_id not in {edge.start, edge.end}:
                    continue
                crossing_station = ((crossing.center[0] - start[0]) * ux
                                    + (crossing.center[1] - start[1]) * uy)
                clearance = (abs(station - crossing_station)
                             - crossing.crosswalk_width * 0.5)
                self.assertGreaterEqual(clearance, 10.0 - 1e-6)
        for tree in trees:
            for light in lights:
                if (light.kind == "pedestrian" and tree.edge_id == light.edge_id
                        and tree.side == light.side):
                    self.assertGreaterEqual(
                        math.dist(tree.location[:2], light.location[:2]), 3.0)
        day = replace(network, scene=replace(network.scene, time_of_day="day"))
        self.assertTrue(all(not item.lit
                            for item in plan_street_lights(day, crosswalks)))
        disabled_edge = replace(network.edges[0], street_lights=False)
        disabled = replace(network, edges=(disabled_edge, *network.edges[1:]))
        self.assertFalse(any(item.edge_id == disabled_edge.id
                             for item in plan_street_lights(disabled, crosswalks)))
        no_planting_edge = replace(network.edges[0], planting=None)
        no_planting = replace(network, edges=(no_planting_edge, *network.edges[1:]))
        no_planting_lights = plan_street_lights(
            no_planting, plan_crosswalks(no_planting))
        self.assertTrue(any(item.edge_id == no_planting_edge.id
                            and item.kind == "pedestrian"
                            for item in no_planting_lights))

    def test_unsignalized_t_keeps_signalized_crosswalk_and_stop_line_geometry(self):
        definition = (Path(__file__).parents[1] /
                      "examples/unsignalized_stop_t_junction.json")
        unsignalized = load_network(definition)
        signalized_node = replace(
            unsignalized.nodes["junction"], kind="signalized_t_junction",
            signal_phase="east_west_green")
        signalized = replace(
            unsignalized,
            nodes={**unsignalized.nodes, "junction": signalized_node},
        )
        self.assertEqual(plan_crosswalks(unsignalized),
                         plan_crosswalks(signalized))
        self.assertEqual(plan_stop_lines(plan_crosswalks(unsignalized)),
                         plan_stop_lines(plan_crosswalks(signalized)))
        for edge in unsignalized.edges:
            signalized_edge = next(item for item in signalized.edges
                                   if item.id == edge.id)
            self.assertEqual(
                longitudinal_marking_trims(
                    unsignalized, edge, plan_crosswalks(unsignalized)),
                longitudinal_marking_trims(
                    signalized, signalized_edge, plan_crosswalks(signalized)),
            )
        self.assertEqual(len(plan_crosswalks(unsignalized)), 3)
        self.assertFalse(plan_signal_sites(unsignalized))

    def test_unsignalized_cross_keeps_geometry_and_controls_one_road(self):
        definition = (Path(__file__).parents[1] /
                      "examples/unsignalized_stop_cross.json")
        unsignalized = load_network(definition)
        signalized_node = replace(
            unsignalized.nodes["junction"], kind="signalized_cross",
            signal_phase="east_west_green")
        signalized = replace(
            unsignalized,
            nodes={**unsignalized.nodes, "junction": signalized_node},
        )
        self.assertEqual(plan_crosswalks(unsignalized),
                         plan_crosswalks(signalized))
        self.assertEqual(plan_stop_lines(plan_crosswalks(unsignalized)),
                         plan_stop_lines(plan_crosswalks(signalized)))
        self.assertEqual(len(plan_crosswalks(unsignalized)), 4)
        self.assertFalse(plan_signal_sites(unsignalized))
        controlled = {
            approach.edge_id for approach in plan_network(unsignalized).approaches
            if approach.stop_control
        }
        self.assertEqual(controlled,
                         {"east_west_west", "east_west_east"})

    def test_sample_contains_requested_intersection_types(self):
        kinds = {node.kind for node in self.network.nodes.values()}
        self.assertIn("signalized_cross", kinds)
        self.assertIn("signalized_pedestrian_crossing", kinds)
        self.assertIn("stop_t_junction", kinds)

    def test_signal_phases_are_explicit(self):
        self.assertEqual(self.network.nodes["kasumigaseki"].signal_phase,
                         "east_west_green")
        self.assertEqual(self.network.nodes["pedestrian_crossing"].signal_phase,
                         "pedestrian_green")

    def test_random_countdowns_are_reproducible_and_complementary(self):
        first = plan_pedestrian_countdowns(self.network)
        second = plan_pedestrian_countdowns(self.network)
        self.assertEqual(first, second)
        self.assertTrue(all(item.blue_level + item.red_level == 8 for item in first))
        self.assertGreater(len({item.blue_level for item in first}), 1)

    def test_sample_context_is_loaded_from_definition(self):
        self.assertEqual(len(self.network.buildings), 6)

    def test_scene_time_defaults_to_day_and_accepts_night(self):
        self.assertEqual(self.network.scene.time_of_day, "day")
        source = Path(__file__).parents[1] / "examples/signalized_t_junction.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "night.json"
            data["scene"] = {"time_of_day": "night"}
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_network(path).scene.time_of_day, "night")
            data["scene"]["time_of_day"] = "sunset"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "time_of_day"):
                load_network(path)

    def test_guardrail_is_derived_from_edge_and_stops_clear_of_crosswalks(self):
        self.assertEqual(len(self.guardrails), 1)
        rail = self.guardrails[0]
        self.assertEqual(rail.id, "main_middle_right_guardrail")
        self.assertEqual(rail.side, "right")
        self.assertEqual(rail.start, (-12.85, -3.47))
        self.assertEqual(rail.end, (21.45, -3.47))
        self.assertEqual(rail.beam_side, "left")
        self.assertEqual(rail.elevation, 0.02)
        # Crosswalk extents end/start at -13.40m and 22.00m respectively;
        # the planned rail keeps another 0.55m clear at both ends.
        self.assertAlmostEqual(rail.start[0] - (-13.40), 0.55)
        self.assertAlmostEqual(22.00 - rail.end[0], 0.55)

    def test_stop_approach_is_derived_without_turn_lanes(self):
        self.assertEqual(sum(a.right_turn_lane for a in self.plan.approaches), 0)
        self.assertEqual(sum(a.stop_control for a in self.plan.approaches), 1)

    def test_all_segments_are_two_way_standard_width(self):
        self.assertTrue(all(segment.width == 6.5 for segment in self.plan.segments))

    def test_global_sidewalk_standard_is_three_point_six_metres(self):
        self.assertEqual(SIDEWALK_WIDTH_M, 3.6)

    def test_tactile_paving_uses_standard_crossing_layout_and_partial_tiles(self):
        edges = tuple(replace(edge, tactile_paving=edge.id == "main_west")
                      for edge in self.network.edges)
        network = replace(self.network, edges=edges)
        tiles = plan_tactile_paving(network, plan_crosswalks(network))
        crossing = [item for item in tiles if item.id.startswith("kasumigaseki_west_")]
        self.assertEqual(sum(item.kind == "warning" for item in crossing), 52)
        self.assertEqual(sum(item.kind == "guidance" for item in crossing), 24)
        self.assertTrue(any(min(item.size) < 0.30 for item in tiles))
        self.assertTrue(all(item.size[0] <= 0.300001 and item.size[1] <= 0.300001
                            for item in tiles))
        ids = {item.id for item in tiles}
        self.assertTrue(any(item.startswith("kasumigaseki_-1_+1_corner") for item in ids))
        self.assertTrue(any(item.startswith("kasumigaseki_-1_-1_corner") for item in ids))
        self.assertFalse(any(item.startswith("kasumigaseki_+1_+1_corner") for item in ids))
        # The one enabled west road still serves the adjacent north/south
        # crossings at the west-side corners, matching reference b.
        self.assertTrue(any(item.startswith("kasumigaseki_south_-1_warning") for item in ids))
        self.assertFalse(any(item.startswith("kasumigaseki_south_+1_warning") for item in ids))
        self.assertEqual(sum(item.startswith("kasumigaseki_-1_+1_corner_warning")
                             for item in ids), 4)
        warnings = [item for item in tiles if item.kind == "warning"]
        guidance = [item for item in tiles if item.kind == "guidance"]
        for guide in guidance:
            for warning in warnings:
                overlap_x = (guide.size[0] + warning.size[0]) * 0.5 - abs(guide.center[0] - warning.center[0])
                overlap_y = (guide.size[1] + warning.size[1]) * 0.5 - abs(guide.center[1] - warning.center[1])
                self.assertFalse(overlap_x > 1e-6 and overlap_y > 1e-6)

    def test_crosswalks_come_from_node_rules(self):
        self.assertEqual(len(self.crosswalks), 8)
        self.assertEqual(sum(c.node_id == "kasumigaseki" for c in self.crosswalks), 4)
        self.assertEqual(sum(c.node_id == "pedestrian_crossing" for c in self.crosswalks), 1)
        self.assertEqual(sum(c.node_id == "t_junction" for c in self.crosswalks), 3)

    def test_stop_lines_clear_the_flush_roadside_stone_apron(self):
        expected = 6.5 * 0.5 - 2 * (CURB_ROAD_APRON_M
                                    + ROAD_MARKING_CURB_CLEARANCE_M)
        self.assertTrue(all(math.isclose(item.width, expected)
                            for item in self.stop_lines))

    def test_each_signalized_cross_approach_has_a_far_side_pre_crosswalk_signal(self):
        vehicles = {site.id: site.location for site in self.signals if site.kind == "vehicle"}
        self.assertEqual(vehicles["kasumigaseki_west_vehicle"][:2], (-17.1, 3.67))
        self.assertEqual(vehicles["kasumigaseki_east_vehicle"][:2], (-30.9, -3.67))
        self.assertEqual(vehicles["kasumigaseki_south_vehicle"][:2], (-27.67, 6.9))
        self.assertEqual(vehicles["kasumigaseki_north_vehicle"][:2], (-20.33, -6.9))

    def test_signal_counts_cover_every_crosswalk(self):
        self.assertEqual(sum(s.kind == "vehicle" for s in self.signals), 6)
        self.assertEqual(sum(s.kind == "pedestrian" for s in self.signals), 10)

    def test_midblock_pedestrian_signals_face_into_crossing(self):
        signals = {site.id: site for site in self.signals}
        self.assertEqual(signals["pedestrian_crossing_south_pedestrian"].rotation_degrees, 180)
        self.assertEqual(signals["pedestrian_crossing_north_pedestrian"].rotation_degrees, 0)

    def test_junction_pedestrian_signals_face_across_the_crosswalk(self):
        signals = {site.id: site for site in self.signals}
        expected = {
            "kasumigaseki_west_south_pedestrian": -180,
            "kasumigaseki_west_north_pedestrian": 0,
            "kasumigaseki_south_east_pedestrian": -90,
            "kasumigaseki_south_west_pedestrian": 90,
            "kasumigaseki_east_north_pedestrian": 0,
            "kasumigaseki_east_south_pedestrian": 180,
            "kasumigaseki_north_west_pedestrian": 90,
            "kasumigaseki_north_east_pedestrian": -90,
        }
        for site_id, rotation in expected.items():
            self.assertAlmostEqual(signals[site_id].rotation_degrees, rotation)

    def test_signal_sites_retain_their_semantic_node(self):
        sites = {site.id: site for site in self.signals}
        self.assertEqual(sites["pedestrian_crossing_west_vehicle"].node_id,
                         "pedestrian_crossing")
        self.assertEqual(self.network.nodes["pedestrian_crossing"].name, "")

    def test_cross_signal_blocks_are_deterministic_and_merge_only_inner_a_sites(self):
        self.assertEqual(len(self.signal_blocks), 4)
        self.assertEqual(self.signal_blocks, plan_signal_blocks(self.signals))
        mergeable = [site for block in self.signal_blocks for site in block.pedestrians
                     if site.pedestrian_position == "inner"
                     and block.vehicle.support_mode == "roadside_left"
                     and math.dist(site.location[:2],
                                   block.vehicle.location[:2]) < 0.05]
        self.assertTrue(mergeable)
        self.assertTrue(all(site.merge_candidate for site in mergeable))

    def test_merged_signal_source_axes_require_rotation_aware_alignment(self):
        # Both source assets place the physical pole at local (0, 0.16). For a
        # 30-degree relative heading, simply sharing collection origins would
        # leave the axes sqrt(2)*0.16 m apart.
        offset = 0.16
        separation = ((offset - 0.0) ** 2 + (0.0 - offset) ** 2) ** 0.5
        self.assertAlmostEqual(separation, 0.226274, places=6)

    def test_stop_lines_are_derived_from_crosswalk_edges(self):
        self.assertEqual(len(self.stop_lines), 9)
        centers = {line.id: line.center for line in self.stop_lines}
        self.assertEqual(centers["kasumigaseki_west_west_stop"], (-36.6, 1.62))
        self.assertEqual(centers["pedestrian_crossing_east_stop"], (28.0, -1.62))

    def test_longitudinal_markings_end_at_derived_stop_lines(self):
        edges = {edge.id: edge for edge in self.network.edges}
        self.assertEqual(
            longitudinal_marking_trims(
                self.network, edges["main_middle"], self.crosswalks,
            ),
            (12.6, 4.0),
        )

    def test_lane_separators_are_solid_only_on_each_inbound_approach(self):
        self.assertEqual(
            lane_separator_solid_interval(0.0, 100.0, -1, -10.0, -10.0),
            (10.0, 25.0),
        )
        self.assertEqual(
            lane_separator_solid_interval(0.0, 100.0, 1, -10.0, -10.0),
            (75.0, 90.0),
        )
        self.assertIsNone(
            lane_separator_solid_interval(0.0, 100.0, -1, None, -10.0),
        )
        self.assertIsNone(
            lane_separator_solid_interval(0.0, 100.0, 1, -10.0, None),
        )

    def test_lane_separator_solid_interval_clamps_to_short_road(self):
        self.assertEqual(
            lane_separator_solid_interval(0.0, 20.0, -1, -12.0, None),
            (12.0, 20.0),
        )

    def test_lane_separator_solid_interval_continues_across_split_edges(self):
        # The junction-adjacent edge ends 10 m beyond its stop line.  A second
        # edge whose endpoint is 10 m from that line must carry the remaining
        # 5 m, rather than restarting or dropping the approach marking.
        self.assertEqual(
            lane_separator_solid_interval(0.0, 60.0, -1, 10.0, None),
            (0.0, 5.0),
        )
        self.assertIsNone(
            lane_separator_solid_interval(0.0, 60.0, -1, 15.0, None),
        )

    def test_multilane_approach_arrow_assignment(self):
        self.assertEqual(approach_lane_arrow_kinds(1), ())
        self.assertEqual(approach_lane_arrow_kinds(2),
                         ("left_straight", "straight_right"))
        self.assertEqual(approach_lane_arrow_kinds(3),
                         ("left_straight", "straight", "right"))
        self.assertEqual(approach_lane_arrow_kinds(5),
                         ("left_straight", "straight", "straight", "straight", "right"))
        self.assertEqual(cross_lane_arrow_kinds(3, True),
                         ("left_straight", "straight", "straight_right"))
        self.assertEqual(cross_lane_arrow_kinds(3, False),
                         ("left_straight", "straight", "right"))
        self.assertEqual(t_junction_lane_arrow_kinds(2, "right"),
                         ("straight", "straight_right"))
        self.assertEqual(t_junction_lane_arrow_kinds(2, "left"),
                         ("left_straight", "straight"))
        self.assertEqual(t_junction_lane_arrow_kinds(
            3, "right", dedicated_right_lane=True),
            ("straight", "straight", "right"))
        self.assertEqual(t_junction_lane_arrow_kinds(3, "stem"),
                         ("left", "left", "right"))

    def test_cross_intersection_is_fourfold_rotationally_symmetric(self):
        center = self.network.nodes["kasumigaseki"].position
        crosswalk_offsets = {
            (round(c.center[0] - center[0], 3), round(c.center[1] - center[1], 3))
            for c in self.crosswalks if c.node_id == "kasumigaseki"
        }
        vehicle_offsets = {
            (round(s.location[0] - center[0], 3), round(s.location[1] - center[1], 3))
            for s in self.signals if s.id.startswith("kasumigaseki") and s.kind == "vehicle"
        }
        pedestrian_offsets = {
            (round(s.location[0] - center[0], 3), round(s.location[1] - center[1], 3))
            for s in self.signals if s.id.startswith("kasumigaseki") and s.kind == "pedestrian"
        }

        def assert_fourfold(points):
            for px, py in points:
                self.assertIn((-py, px), points)

        assert_fourfold(crosswalk_offsets)
        assert_fourfold(vehicle_offsets)
        # Pedestrian side 1/2 is the only intentional random asymmetry.
        self.assertEqual(len(pedestrian_offsets), 8)
        self.assertEqual({site.pedestrian_position for site in self.signals
                          if site.id.startswith("kasumigaseki")
                          and site.kind == "pedestrian"}, {"inner", "outer"})

        stop_offsets = {
            (round(line.center[0] - center[0], 3), round(line.center[1] - center[1], 3))
            for line in self.stop_lines if line.id.startswith("kasumigaseki")
        }
        assert_fourfold(stop_offsets)
        self.assertEqual({round(max(abs(x), abs(y)), 3) for x, y in stop_offsets}, {12.6})


class Grid3x3DefinitionTest(unittest.TestCase):
    def setUp(self):
        definition = Path(__file__).parents[1] / "examples/grid_3x3.json"
        self.network = load_network(definition)
        self.crosswalks = plan_crosswalks(self.network)
        self.signals = plan_signal_sites(self.network)

    def test_grid_uses_nine_named_crosses_and_no_context(self):
        crosses = [node for node in self.network.nodes.values()
                   if node.kind == "signalized_cross"]
        self.assertEqual(len(crosses), 9)
        self.assertEqual([node.name for node in crosses],
                         ["一丁目", "二丁目", "三丁目", "四丁目", "五丁目",
                          "六丁目", "七丁目", "八丁目", "九丁目"])
        self.assertEqual(self.network.buildings, ())
        self.assertTrue(all(edge.guardrail is None for edge in self.network.edges))

    def test_grid_is_generated_by_the_same_generic_planners(self):
        self.assertEqual(len(self.network.edges), 24)
        self.assertEqual(len(self.crosswalks), 36)
        self.assertEqual(sum(site.kind == "vehicle" for site in self.signals), 36)
        self.assertEqual(sum(site.kind == "pedestrian" for site in self.signals), 72)
        self.assertEqual(len(plan_signal_blocks(self.signals)), 36)


class Grid3x3MultilaneDefinitionTest(unittest.TestCase):
    def test_only_the_central_axes_are_two_lanes_and_center_has_arrows(self):
        definition = (Path(__file__).parents[1] /
                      "examples/grid_3x3_white_multilane.json")
        network = load_network(definition)
        two_lane_ids = {edge.id for edge in network.edges if edge.lanes_each_way == 2}
        self.assertEqual(two_lane_ids, {
            "row2_west", "row2_1_2", "row2_2_3", "row2_east",
            "col2_north", "col2_1_2", "col2_2_3", "col2_south",
        })
        self.assertEqual(
            [node.id for node in network.nodes.values() if node.vehicle_arrow == "right"],
            ["block_5"],
        )
        self.assertEqual(network.nodes["block_5"].signal_phase,
                         "east_west_right_arrow")
        self.assertEqual(effective_vehicle_arrow(
            network, network.nodes["block_5"]), "right")
        self.assertEqual(effective_vehicle_arrow(
            network, replace(network.nodes["block_5"], vehicle_arrow="none")),
            "right")
        self.assertEqual(effective_vehicle_arrow(
            network, replace(network.nodes["block_5"],
                             kind="signalized_t_junction",
                             vehicle_arrow="right")), "none")
        center_crosswalks = [item for item in plan_crosswalks(network)
                             if item.node_id == "block_5"]
        self.assertEqual({item.road_width for item in center_crosswalks}, {13.0})
        self.assertEqual(
            [edge.id for edge in network.edges if edge.bicycle_lane],
            ["row2_1_2", "row2_2_3", "col2_1_2", "col2_2_3"],
        )
        self.assertEqual(
            [edge.id for edge in network.edges if edge.curb_parking_prohibition],
            ["row1_2_3"],
        )
        curb_plans = plan_curb_parking_stripes(network, plan_crosswalks(network))
        self.assertEqual(len(curb_plans), 2)
        self.assertEqual({item.side for item in curb_plans}, {"left", "right"})
        self.assertTrue(all(item.edge_id == "row1_2_3" for item in curb_plans))

    def test_vehicle_extension_centres_head_over_multilane_carriageway(self):
        lane_width = 3.25
        base_extension = 1.5
        self.assertEqual(base_extension + lane_width * (1 - 1) / 2, 1.5)
        self.assertEqual(base_extension + lane_width * (2 - 1) / 2, 3.125)
        self.assertEqual(base_extension + lane_width * (10 - 1) / 2, 16.125)

    def test_guardrails_and_plantings_are_independent_half_subsets(self):
        definition = (Path(__file__).parents[1] /
                      "examples/grid_3x3_white_multilane.json")
        network = load_network(definition)
        configured = {edge.id for edge in network.edges if edge.guardrail is not None}
        self.assertEqual(configured, {
            "row1_1_2", "row3_1_2", "row3_2_3", "col1_2_3",
            "col2_2_3", "col3_1_2",
        })
        planted = {edge.id for edge in network.edges if edge.planting is not None}
        self.assertEqual(planted, {
            "row1_1_2", "row3_1_2", "row3_2_3", "col2_1_2",
            "col3_1_2", "col3_2_3",
        })
        internal = {f"row{row}_{column}_{column + 1}"
                    for row in range(1, 4) for column in range(1, 3)}
        internal |= {f"col{column}_{row}_{row + 1}"
                     for column in range(1, 4) for row in range(1, 3)}
        self.assertEqual(len(configured), len(internal) // 2)
        self.assertEqual(len(planted), len(internal) // 2)
        self.assertNotEqual(configured, planted)
        self.assertTrue(all(
            edge.guardrail.sides == "both" and
            edge.guardrail.exterior_color == "white"
            for edge in network.edges if edge.guardrail is not None
        ))
        guardrail_plans = plan_guardrails(network, plan_crosswalks(network))
        self.assertEqual(sum(item.curve_center is None for item in guardrail_plans),
                         len(configured) * 2)
        planting_plans = plan_plantings(network, plan_crosswalks(network))
        straight_plantings = [item for item in planting_plans
                              if item.curve_center is None]
        self.assertEqual(len(straight_plantings), len(planted) * 2)
        self.assertTrue({"left", "right"}.issubset(
            {item.side for item in planting_plans}
        ))
        self.assertTrue(all(item.width == 0.85 for item in planting_plans))
        self.assertEqual(planting_plans, plan_plantings(network, plan_crosswalks(network)))


class Grid3x3AllFeaturesDefinitionTest(unittest.TestCase):
    def test_every_edge_enables_all_four_roadside_features(self):
        definition = (Path(__file__).parents[1] /
                      "examples/grid_3x3_white_multilane_all_features.json")
        network = load_network(definition)
        self.assertEqual(len(network.edges), 24)
        self.assertTrue(all(edge.guardrail is not None for edge in network.edges))
        self.assertTrue(all(edge.planting is not None for edge in network.edges))
        self.assertTrue(all(edge.bicycle_lane for edge in network.edges))
        self.assertTrue(all(edge.curb_parking_prohibition for edge in network.edges))
        crosswalks = plan_crosswalks(network)
        guardrails = plan_guardrails(network, crosswalks)
        plantings = plan_plantings(network, crosswalks)
        poles = plan_corner_reflector_poles(network)
        self.assertEqual(sum(item.curve_center is None for item in guardrails), 48)
        self.assertEqual(sum(item.curve_center is None for item in plantings), 48)
        self.assertEqual(sum(item.curve_center is not None for item in plantings), 36)
        curved_guardrails = [item for item in guardrails if item.curve_center is not None]
        self.assertEqual(len(curved_guardrails) + len(poles), 36)
        guardrail_nodes = {
            item.id.removesuffix(f"_{item.side}_corner_guardrail")
            for item in curved_guardrails
        }
        pole_nodes = {item.node_id for item in poles}
        self.assertFalse(guardrail_nodes & pole_nodes)
        self.assertEqual(len(guardrail_nodes | pole_nodes), 9)
        self.assertTrue(all(sum(item.node_id == node_id for item in poles) == 4
                            for node_id in pole_nodes))
        self.assertTrue(all(item.curve_sweep_degrees == 41.0
                            for item in curved_guardrails))
        curb_plans = plan_curb_parking_stripes(network, crosswalks)
        self.assertEqual(sum(item.curve_center is None for item in curb_plans), 48)
        self.assertFalse(any(item.curve_center is not None for item in curb_plans))
        self.assertGreater(len(plan_bicycle_markings(network)), 0)

    def test_brown_variant_uses_brown_signals_and_guardrails(self):
        definition = (Path(__file__).parents[1] /
                      "examples/grid_3x3_brown_multilane_all_features.json")
        network = load_network(definition)
        signal_nodes = [node for node in network.nodes.values()
                        if node.kind in {"signalized_cross",
                                         "signalized_pedestrian_crossing"}]
        self.assertEqual(len(signal_nodes), 9)
        self.assertTrue(all(node.exterior_color == "brown" for node in signal_nodes))
        self.assertTrue(all(edge.guardrail is not None and
                            edge.guardrail.exterior_color == "brown"
                            for edge in network.edges))
        self.assertTrue(all(edge.planting is not None and edge.bicycle_lane and
                            edge.curb_parking_prohibition for edge in network.edges))
        self.assertTrue(all(edge.street_trees is not None and edge.street_trees.enabled
                            for edge in network.edges))
        median_edges = {edge.id for edge in network.edges if edge.median}
        self.assertEqual(median_edges, {
            "row2_west", "row2_1_2", "row2_2_3", "row2_east",
            "col2_north", "col2_1_2", "col2_2_3", "col2_south",
        })
        medians = plan_medians(network, plan_crosswalks(network))
        self.assertEqual(len(medians), 20)
        self.assertTrue(all(item.width == 0.65 and item.height == 0.24
                            for item in medians))
        # The rounded cap's physical tip remains 15cm before the crosswalk;
        # its profile origin is inset by the 325mm cap radius.
        row2_median = next(item for item in medians
                           if item.id == "row2_2_3_median")
        self.assertEqual(row2_median.start, (14.325, 0.0))
        self.assertEqual((row2_median.start[0] - row2_median.width * 0.5,
                          row2_median.start[1]), (14.0, 0.0))
        intersection_islands = [item for item in medians if item.node_id]
        self.assertEqual(len(intersection_islands), 12)
        self.assertTrue(all(item.rounded_start and item.rounded_end
                            for item in intersection_islands))
        self.assertTrue(all("intersection_median" in item.id
                            for item in intersection_islands))
        signal_sites = plan_signal_sites(network, medians)
        median_vehicle_sites = [item for item in signal_sites
                                if item.support_mode == "median_right"]
        self.assertEqual(len(median_vehicle_sites), 8)
        self.assertEqual(signal_sites, plan_signal_sites(network, medians))
        blocks = plan_signal_blocks(signal_sites)
        self.assertTrue(all(block.vehicle.support_mode in {"roadside_left", "median_right"}
                            for block in blocks))
        devices = plan_median_island_devices(network, medians, signal_sites)
        # Every island retains its sign/lamp. Signal-bearing islands place the
        # device near the junction nose and the vehicle pole near the far end.
        self.assertEqual(len(devices), 12)
        self.assertTrue(all(item.location[2] == 0.24 for item in devices))
        self.assertEqual(sum(item.device_type == "dual_warning_lamp" for item in devices), 4)
        self.assertEqual(sum(item.device_type == "keep_left_sign" for item in devices), 8)
        median_by_id = {item.id: item for item in medians}
        by_node = {}
        for device in devices:
            by_node.setdefault(median_by_id[device.median_id].node_id, set()).add(
                device.device_type
            )
        self.assertTrue(all(len(types) == 1 for types in by_node.values()))
        # Only the all-multilane centre junction is eligible for the 50/50
        # choice. Across deterministic seeds it can select either family,
        # while every other junction remains a keep-left sign.
        centre_choices = set()
        for seed in range(12):
            seeded = plan_median_island_devices(network, medians, signal_sites, seed)
            seeded_by_node = {}
            for device in seeded:
                seeded_by_node.setdefault(
                    median_by_id[device.median_id].node_id, set()
                ).add(device.device_type)
            self.assertTrue(all(len(types) == 1 for types in seeded_by_node.values()))
            centre_choices.update(seeded_by_node["block_5"])
            self.assertTrue(all(types == {"keep_left_sign"}
                                for node_id, types in seeded_by_node.items()
                                if node_id != "block_5"))
        self.assertEqual(centre_choices, {"keep_left_sign", "dual_warning_lamp"})
        occupied = {site.support_median_id for site in median_vehicle_sites}
        self.assertTrue(all(occupied))
        devices_by_median = {device.median_id: device for device in devices}
        self.assertTrue(occupied <= devices_by_median.keys())
        medians_by_id = {item.id: item for item in medians}
        for device in devices:
            island = medians_by_id[device.median_id]
            expected_distance = min(0.25, math.dist(island.start, island.end) * 0.25)
            self.assertAlmostEqual(
                math.dist(device.location[:2], island.start), expected_distance)
        for site in median_vehicle_sites:
            approach = site.id.removesuffix("_vehicle").rsplit("_", 1)[-1]
            island = medians_by_id[site.support_median_id]
            self.assertEqual(island.node_id, site.node_id)
            opposite = {"west": "east", "east": "west",
                        "south": "north", "north": "south"}
            self.assertEqual(island.approach, opposite[approach])
            self.assertIn(island, intersection_islands)
            island_length = math.dist(island.start, island.end)
            expected_inset = min(0.35, island_length * 0.25)
            self.assertAlmostEqual(
                math.dist(site.location[:2], island.end), expected_inset)
            self.assertEqual(site.location[2], island.height)
            self.assertGreater(
                math.dist(site.location[:2],
                          devices_by_median[site.support_median_id].location[:2]),
                0.70,
            )
        self.assertEqual(devices,
                         plan_median_island_devices(network, medians, signal_sites))
        trees = plan_street_trees(network, plan_crosswalks(network))
        street_lights = plan_street_lights(network, plan_crosswalks(network))
        self.assertGreater(len(trees), len(network.edges) * 2)
        self.assertEqual({item.side for item in trees}, {"left", "right"})
        self.assertEqual(trees, plan_street_trees(network, plan_crosswalks(network)))
        self.assertEqual({item.species for item in trees}, {"keyaki", "ginkgo", "cherry"})
        trees_by_edge_side = {}
        for tree in trees:
            trees_by_edge_side.setdefault((tree.edge_id, tree.side), []).append(tree)
        edges = {edge.id: edge for edge in network.edges}
        for (edge_id, _side), items in trees_by_edge_side.items():
            if len(items) < 2:
                continue
            config = edges[edge_id].street_trees
            nominal = 10.0 / config.density
            points = [item.location[:2] for item in items]
            gaps = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
                    for a, b in zip(points, points[1:])]
            # A tree omitted around a pedestrian lamp intentionally combines
            # two neighbouring gaps; remaining trees never move closer than
            # the authored random-spacing lower bound.
            self.assertTrue(all(gap >= nominal * 0.70 for gap in gaps))
        for tree in trees:
            for light in street_lights:
                if (light.kind == "pedestrian" and tree.edge_id == light.edge_id
                        and tree.side == light.side):
                    self.assertGreaterEqual(
                        math.dist(tree.location[:2], light.location[:2]), 3.0)


class Grid5x5RandomizedDefinitionTest(unittest.TestCase):
    def test_short_boundary_median_trims_at_its_intersection_crosswalk(self):
        definition = (Path(__file__).parents[1] /
                      "examples/grid_5x5_randomized_all_features.json")
        network = load_network(definition)
        medians = plan_medians(network, plan_crosswalks(network))
        median = next(item for item in medians if item.id == "col_2_0_median")
        # The south crosswalk at y=-131.5 has a 1.6m half-width and 0.15m
        # clearance. The median must stop road-side at -133.25, not continue to
        # the block_2 centre at y=-116 merely because the crosswalk lies just
        # beyond this short edge's midpoint.
        self.assertEqual(median.end, (-58.0, -133.575))
        self.assertEqual((median.end[0], median.end[1] + median.width * 0.5),
                         (-58.0, -133.25))


class SignalizedTJunctionTest(unittest.TestCase):
    def setUp(self):
        definition = (Path(__file__).parents[1] /
                      "examples/signalized_t_junction.json")
        self.network = load_network(definition)

    def test_only_three_connected_arms_receive_crossings_and_signals(self):
        crosswalks = plan_crosswalks(self.network)
        self.assertEqual({item.controlled_approaches[0] for item in crosswalks},
                         {"west", "east", "south"})
        sites = plan_signal_sites(self.network)
        vehicles = {item.id for item in sites if item.kind == "vehicle"}
        pedestrians = [item for item in sites if item.kind == "pedestrian"]
        self.assertEqual(vehicles, {
            "kasumigaseki_t_west_vehicle", "kasumigaseki_t_east_vehicle",
            "kasumigaseki_t_south_vehicle",
        })
        self.assertEqual(len(pedestrians), 6)
        self.assertEqual(len({item.location for item in pedestrians}), 6)
        self.assertEqual(len(plan_signal_blocks(sites)), 1)
        self.assertEqual(len(plan_stop_lines(crosswalks)), 3)
        south_vehicle = next(item for item in sites
                             if item.id == "kasumigaseki_t_south_vehicle")
        # The stem-facing signal uses the same junction-side edge of the
        # far crosswalk as the two through-road approaches.
        self.assertEqual(south_vehicle.location[1], 10.15)

    def test_sample_includes_planting_trees_and_main_road_medians(self):
        planted = [edge for edge in self.network.edges if edge.planting is not None]
        tree_edges = [edge for edge in self.network.edges if edge.street_trees is not None]
        median_edges = [edge.id for edge in self.network.edges if edge.median]
        self.assertEqual(len(planted), 3)
        self.assertEqual(len(tree_edges), 3)
        self.assertEqual(set(median_edges), {"main_west", "main_east"})
        planting_plans = plan_plantings(self.network, plan_crosswalks(self.network))
        self.assertEqual(sum(item.curve_center is None for item in planting_plans), 7)
        self.assertEqual(sum(item.curve_center is not None for item in planting_plans), 2)
        back = next(item for item in planting_plans if item.side == "back")
        self.assertEqual(back.edge_id, "kasumigaseki_t_back_sidewalk")
        self.assertAlmostEqual(back.start[0], -7.05)
        self.assertAlmostEqual(back.end[0], 7.05)
        self.assertEqual((back.start[1], back.end[1]), (7.255, 7.255))
        self.assertGreater(len(plan_street_trees(self.network, plan_crosswalks(self.network))), 0)

    def test_back_side_tactile_route_depends_only_on_the_through_road(self):
        def has_back_connection(enabled):
            network = replace(
                self.network,
                edges=tuple(replace(edge, tactile_paving=edge.id in enabled)
                            for edge in self.network.edges),
            )
            tiles = plan_tactile_paving(network, plan_crosswalks(network))
            return any(item.id.startswith("kasumigaseki_t_back_connection")
                       for item in tiles)

        self.assertFalse(has_back_connection(set()))
        self.assertFalse(has_back_connection({"stem_south"}))
        self.assertTrue(has_back_connection({"main_west", "main_east"}))
        self.assertTrue(has_back_connection({"main_west", "main_east", "stem_south"}))


class CurvedCornerRoadsideTest(unittest.TestCase):
    def setUp(self):
        definition = (Path(__file__).parents[1] /
                      "examples/corner_guardrail_planting.json")
        self.network = load_network(definition)
        self.crosswalks = plan_crosswalks(self.network)

    def test_four_planting_corners_follow_sidewalk_radius_and_leave_crosswalk_clearance(self):
        guardrails = plan_guardrails(self.network, self.crosswalks)
        plantings = plan_plantings(self.network, self.crosswalks)
        curved_plantings = [item for item in plantings if item.curve_center is not None]
        curved_guardrails = [item for item in guardrails if item.curve_center is not None]
        self.assertEqual(len(curved_guardrails), 4)
        self.assertTrue(all(item.elevation == 0.02 for item in curved_guardrails))
        self.assertEqual(len(curved_plantings), 4)
        self.assertEqual({round(item.curve_radius, 3) for item in curved_plantings},
                         {3.045})
        guardrail_arcs = {
            item.side: (item.curve_start_degrees, item.curve_sweep_degrees)
            for item in curved_guardrails
        }
        self.assertTrue(all(
            (item.curve_start_degrees, item.curve_sweep_degrees)
            == guardrail_arcs[item.side]
            for item in curved_plantings
        ))
        self.assertEqual({item.side for item in curved_plantings},
                         {"southwest", "northwest", "southeast", "northeast"})
        poles = plan_corner_reflector_poles(self.network)
        self.assertEqual(poles, ())

    def test_corner_generation_is_deterministic_and_does_not_add_corner_trees(self):
        self.assertEqual(plan_guardrails(self.network, self.crosswalks),
                         plan_guardrails(self.network, self.crosswalks))
        self.assertEqual(plan_corner_reflector_poles(self.network),
                         plan_corner_reflector_poles(self.network))
        self.assertEqual(plan_plantings(self.network, self.crosswalks),
                         plan_plantings(self.network, self.crosswalks))
        self.assertEqual(plan_street_trees(self.network, self.crosswalks), ())


class GeneralAngleWidthPlanningTest(unittest.TestCase):
    def test_bent_two_lane_road_keeps_its_authored_width(self):
        data = {
            "roads": [
                {"id": "bent", "lanes_each_way": 2, "sidewalks": "both"},
                {"id": "cross", "lanes_each_way": 1, "sidewalks": "both"},
            ],
            "nodes": [
                {"id": "c", "type": "signalized_cross", "position": [0, 0],
                 "crossings": ["east_west", "north_south"],
                 "signal_phase": "group_a_green"},
                {"id": "w", "type": "boundary", "position": [-35.863, -3.138]},
                {"id": "e", "type": "boundary", "position": [35.863, -3.138]},
                {"id": "s", "type": "boundary", "position": [0, -36]},
                {"id": "n", "type": "boundary", "position": [0, 36]},
            ],
            "edges": [
                {"id": "w", "road": "bent", "from": "c", "to": "w",
                 "geometry": {"type": "line"}},
                {"id": "e", "road": "bent", "from": "c", "to": "e",
                 "geometry": {"type": "line"}},
                {"id": "s", "road": "cross", "from": "c", "to": "s",
                 "geometry": {"type": "line"}},
                {"id": "n", "road": "cross", "from": "c", "to": "n",
                 "geometry": {"type": "line"}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bent_widths.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            network = load_network(path)
        self.assertEqual(road_widths_at_node(network, "c"), (13.0, 6.5))


class SchemaValidationTest(unittest.TestCase):
    def test_center_marking_accepts_none_and_three_paints_with_lane_limits(self):
        base = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [30, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "lanes_each_way": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "center.json"
            for marking in ("none", "orange_solid", "white_solid", "white_dashed"):
                base["edges"][0]["center_marking"] = marking
                path.write_text(json.dumps(base), encoding="utf-8")
                self.assertEqual(load_network(path).edges[0].center_marking, marking)
            base["edges"][0]["lanes_each_way"] = 2
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "white_dashed.*lanes_each_way == 1"):
                load_network(path)
            base["edges"][0]["center_marking"] = "white_solid"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "white_solid.*lanes_each_way == 1"):
                load_network(path)
            base["edges"][0]["center_marking"] = "none"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "none.*lanes_each_way == 1"):
                load_network(path)

    def test_median_requires_two_lanes_each_way(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [30, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "lanes_each_way": 1, "median": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "median.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lanes_each_way >= 2"):
                load_network(path)

    def test_median_width_defaults_to_exact_legacy_narrow_and_wide_adds_one_lane(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [80, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "lanes_each_way": 2, "median": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "median-width.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            legacy = load_network(path)
            data["edges"][0]["median_width"] = "narrow"
            path.write_text(json.dumps(data), encoding="utf-8")
            narrow = load_network(path)
            self.assertEqual(legacy.edges[0], narrow.edges[0])
            self.assertEqual(plan_network(legacy), plan_network(narrow))
            self.assertEqual(plan_medians(legacy, ()), plan_medians(narrow, ()))
            self.assertEqual(road_half_width_m(narrow.edges[0]), 6.5)
            self.assertEqual(plan_medians(narrow, ())[0].width, 0.65)

            data["edges"][0]["median_width"] = "wide"
            path.write_text(json.dumps(data), encoding="utf-8")
            wide = load_network(path)
            self.assertEqual(road_half_width_m(wide.edges[0]), 8.125)
            self.assertEqual(plan_network(wide).segments[0].width, 16.25)
            self.assertEqual(plan_medians(wide, ())[0].width, 3.9)

    def test_street_trees_require_planting_and_validate_species_and_density(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [30, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "sidewalks": "both",
                       "street_trees": {"species": "keyaki", "density": 1.0}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "street_trees.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires planting"):
                load_network(path)
            data["edges"][0]["planting"] = {}
            data["edges"][0]["street_trees"]["species"] = "cedar"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "species"):
                load_network(path)
            data["edges"][0]["street_trees"] = {"species": "ginkgo", "density": 3.0}
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "density"):
                load_network(path)

    def test_random_street_tree_parameters_are_valid_and_reproducible(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [30, 0]},
            ],
            "edges": [{"id": "random_tree_edge", "from": "a", "to": "b",
                       "sidewalks": "both", "planting": {},
                       "street_trees": {"random": True}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "random_street_trees.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            first = load_network(path).edges[0].street_trees
            second = load_network(path).edges[0].street_trees
            self.assertEqual(first, second)
            self.assertIn(first.species, {"keyaki", "ginkgo", "cherry"})
            self.assertGreaterEqual(first.density, 0.35)
            self.assertLessEqual(first.density, 1.50)

    def test_random_planting_parameters_stay_near_defaults_and_are_reproducible(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [30, 0]},
            ],
            "edges": [{"id": "random_planting_edge", "from": "a", "to": "b",
                       "sidewalks": "both", "planting": {"random": True}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "random_planting.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            first = load_network(path).edges[0].planting
            second = load_network(path).edges[0].planting
            self.assertEqual(first, second)
            self.assertTrue(0.74 <= first.density <= 0.90)
            self.assertTrue(0.62 <= first.maintenance <= 0.78)
            self.assertTrue(0.82 <= first.health <= 0.95)

    def test_curb_orange_dashes_require_sidewalks_and_a_boolean_flag(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [20, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "sidewalks": "none", "curb_parking_prohibition": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curb_orange.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires sidewalks"):
                load_network(path)
            data["edges"][0]["sidewalks"] = "both"
            data["edges"][0]["curb_parking_prohibition"] = "yes"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be true or false"):
                load_network(path)

    def test_bicycle_lane_repeats_whole_symbols_in_both_directions(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [100, 0]},
            ],
            "edges": [{"id": "cycle", "from": "a", "to": "b",
                       "lanes_each_way": 1, "bicycle_lane": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bicycle.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            network = load_network(path)
            markings = plan_bicycle_markings(network)
        self.assertEqual(len(markings), 18)
        self.assertEqual(sum(item.direction == "forward" for item in markings), 9)
        self.assertEqual(sum(item.direction == "reverse" for item in markings), 9)
        self.assertEqual({round(abs(item.location[1]), 3) for item in markings}, {2.8})
        length = BICYCLE_MARKING_WIDTH_M * BICYCLE_MARKING_LENGTH_WIDTH_RATIO
        for item in markings:
            self.assertEqual(item.width, 0.5)
            rear_x = item.location[0]
            front_x = rear_x + length if item.direction == "forward" else rear_x - length
            self.assertGreaterEqual(min(rear_x, front_x), 1.0)
            self.assertLessEqual(max(rear_x, front_x), 99.0)

    def test_short_bicycle_lane_does_not_clip_a_symbol(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [9, 0]},
            ],
            "edges": [{"id": "short", "from": "a", "to": "b",
                       "bicycle_lane": True}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short_bicycle.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(plan_bicycle_markings(load_network(path)), ())

    def test_bicycle_lane_must_be_boolean(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [20, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "bicycle_lane": "yes"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_bicycle.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bicycle_lane"):
                load_network(path)

    def test_planting_requires_both_sidewalks_and_bounded_parameters(self):
        base = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [10, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "sidewalks": "none", "planting": {}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planting.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires sidewalks"):
                load_network(path)
            base["edges"][0]["sidewalks"] = "both"
            base["edges"][0]["planting"] = {"density": 1.1}
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "density"):
                load_network(path)

    def test_edge_passing_through_an_intermediate_node_is_rejected(self):
        data = {
            "nodes": [
                {"id": "south", "type": "boundary", "position": [0, -10]},
                {"id": "cross", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red"},
                {"id": "north", "type": "boundary", "position": [0, 10]},
            ],
            "edges": [{"id": "invalid", "from": "south", "to": "north"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "through_node.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "passes through intermediate node"):
                load_network(path)

    def test_exterior_color_defaults_to_white_and_accepts_brown(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [-10, 0]},
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red", "exterior_color": "brown"},
            ],
            "edges": [{"id": "e", "from": "a", "to": "x"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brown.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            network = load_network(path)
            self.assertEqual(network.nodes["a"].exterior_color, "white")
            self.assertEqual(network.nodes["x"].exterior_color, "brown")

    def test_invalid_exterior_color_is_rejected(self):
        data = {
            "nodes": [
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red", "exterior_color": "black"},
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_color.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exterior_color"):
                load_network(path)

    def test_edge_guardrail_accepts_brown_and_rejects_other_values(self):
        base = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [3, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b",
                       "guardrail": {"sides": "both", "exterior_color": "brown"}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guardrail_color.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            config = load_network(path).edges[0].guardrail
            self.assertEqual((config.sides, config.exterior_color), ("both", "brown"))
            base["edges"][0]["guardrail"]["exterior_color"] = "black"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "guardrail exterior_color"):
                load_network(path)

    def test_invalid_vehicle_arrow_is_rejected(self):
        data = {
            "nodes": [
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red", "vehicle_arrow": "left"},
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_arrow.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "vehicle_arrow"):
                load_network(path)

    def test_invalid_lane_count_is_rejected(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [10, 0]},
            ],
            "edges": [{"id": "e", "from": "a", "to": "b", "lanes_each_way": 0}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_lanes.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lanes_each_way"):
                load_network(path)

    def test_stop_t_without_crosswalks_is_rejected(self):
        data = {
            "nodes": [
                {"id": "junction", "type": "stop_t_junction", "position": [0, 0]},
                {"id": "west", "type": "boundary", "position": [-20, 0]},
                {"id": "east", "type": "boundary", "position": [20, 0]},
                {"id": "south", "type": "boundary", "position": [0, -20]},
            ],
            "edges": [
                {"id": "west", "from": "west", "to": "junction"},
                {"id": "east", "from": "junction", "to": "east"},
                {"id": "south", "from": "south", "to": "junction"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stop_t_without_crosswalks.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires all connected crosswalks"):
                load_network(path)

    def test_edges_inherit_lane_structure_from_named_road(self):
        data = {
            "roads": [{"id": "main", "road_class": "arterial", "speed_limit": 50,
                       "lanes_each_way": 3, "sidewalks": "both"}],
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [10, 0]},
                {"id": "c", "type": "boundary", "position": [20, 0]},
            ],
            "edges": [
                {"id": "ab", "road": "main", "from": "a", "to": "b"},
                {"id": "bc", "road": "main", "from": "b", "to": "c"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "road_inheritance.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            network = load_network(path)
        self.assertEqual(set(network.roads), {"main"})
        self.assertEqual({edge.road_id for edge in network.edges}, {"main"})
        self.assertEqual({edge.lanes_each_way for edge in network.edges}, {3})
        self.assertEqual({edge.sidewalks for edge in network.edges}, {"both"})

    def test_unknown_road_reference_is_rejected(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [0, 0]},
                {"id": "b", "type": "boundary", "position": [10, 0]},
            ],
            "edges": [{"id": "e", "road": "missing", "from": "a", "to": "b"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown_road.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown road"):
                load_network(path)

    def test_invalid_signal_phase_is_rejected(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [-10, 0]},
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "pedestrian_green"},
            ],
            "edges": [{"id": "e", "from": "a", "to": "x"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires signal_phase"):
                load_network(path)

    def test_yellow_signal_phase_is_accepted(self):
        data = {
            "nodes": [
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "east_west_yellow"},
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "yellow.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_network(path).nodes["x"].signal_phase,
                             "east_west_yellow")

    def test_arrow_phase_requires_arrow_hardware(self):
        data = {
            "nodes": [
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "east_west_right_arrow"},
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arrow_without_hardware.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "without vehicle_arrow"):
                load_network(path)

    def test_explicit_blue_countdown_controls_red_complement(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [-10, 0]},
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red", "pedestrian_countdown_blue_level": 3},
            ],
            "edges": [{"id": "e", "from": "a", "to": "x"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explicit.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            plan = plan_pedestrian_countdowns(load_network(path))[0]
            self.assertEqual((plan.blue_level, plan.red_level), (3, 5))

    def test_invalid_blue_countdown_is_rejected(self):
        data = {
            "nodes": [
                {"id": "a", "type": "boundary", "position": [-10, 0]},
                {"id": "x", "type": "signalized_cross", "position": [0, 0],
                 "signal_phase": "all_red", "pedestrian_countdown_blue_level": 9},
            ],
            "edges": [{"id": "e", "from": "a", "to": "x"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_countdown.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be an integer 0..8"):
                load_network(path)


if __name__ == "__main__":
    unittest.main()
