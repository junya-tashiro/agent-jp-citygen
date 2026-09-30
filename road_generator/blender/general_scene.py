"""Generic renderer for arbitrary-angle and gently curved road centrelines."""

from pathlib import Path
from dataclasses import replace
import heapq
import math
import os
import random
import time
import zlib

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from road_generator.core.general import (
    JUNCTION_KINDS,
    arm_groups, corner_fillet_radius, junction_arms, point_from_node,
    t_stem_signal_support_location, validate_general_network,
)
from road_generator.core.geometry import add, mul, normalized
from road_generator.core.roadside import roadside_site
from road_generator.core.streets import street_stations, sidewalk_width, sidewalk_footprint, seed_for
from road_generator.core.planner import (
    BICYCLE_MARKING_WIDTH_M, CURB_BLOCK_JOINT_M, CURB_BLOCK_LENGTH_M,
    CURB_ROAD_APRON_M, CURB_TOP_Z_M, CURB_WIDTH_M, GUARDRAIL_BASE_Z_M,
    JUNCTION_CENTER_MARKING_WIDTH_M, LANE_WIDTH_M,
    CROSSWALK_OFFSET_FROM_ROAD_EDGE_M, PLANTING_INSTANCE_Z_M,
    PEDESTRIAN_STREET_LIGHT_CROSSWALK_CLEARANCE_M,
    PEDESTRIAN_STREET_LIGHT_SPACING_M, ROADWAY_STREET_LIGHT_SPACING_M,
    STREET_LIGHT_JUNCTION_ADVANCE_FRACTION, STREET_LIGHT_TREE_CLEARANCE_M,
    STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M,
    SIDEWALK_CORNER_RADIUS_M, SIDEWALK_WIDTH_M, SIDEWALK_TOP_Z_M, SIGNAL_BASE_Z_M,
    PlantingPlan, ROAD_MARKING_CURB_CLEARANCE_M, ROAD_TOP_Z_M, TactileTilePlan,
    plan_bicycle_junction_chevrons, plan_bicycle_markings, plan_crosswalks,
    plan_guardrails, plan_plantings,
    plan_median_island_devices, plan_medians, plan_pedestrian_countdowns,
    plan_signal_blocks, plan_signal_sites, effective_vehicle_arrow,
    approach_lane_arrow_kinds, cross_lane_arrow_kinds,
    t_junction_lane_arrow_kinds,
    lane_separator_solid_interval,
    plan_right_turn_guides, plan_street_trees, plan_network,
    stop_approach_has_crosswalk_sign, road_half_width_m,
    carriageway_lateral_m, approach_existing_lateral_m,
    approach_center_marking_lateral_m, approach_median_section, approach_outward_shift_m,
    EXTRA_INBOUND_LANE_LINK_M,
    extra_lane_factor, has_extra_inbound_lane, has_extra_inbound_reserve,
    has_extra_inbound_section,
)
from .direct_assets import (
    bicycle_blue_chevron_instance, bicycle_marking_deformed,
    bicycle_marking_instance, cached_asset_instance,
    create_dual_warning_lamp, create_fire_hydrant_cover, create_fire_hydrant_sign,
    create_keep_left_sign, create_road_sign,
    create_road_sign_stack,
    guardrail_instance, lane_use_arrow_instance,
    pedestrian_instance, planting_instance, prewarm_cached_asset, street_light_instance,
    street_tree_instance, vehicle_instance, prewarm_street_light_components,
)
from .primitives import (
    ORANGE_PAINT_CENTER_Z_M, ROAD_PAINT_BEVEL_M, ROAD_PAINT_CENTER_Z_M,
    ROAD_PAINT_THICKNESS_M,
    cube, extruded_polygons, material, road_marking_material, strip,
    weathered_material,
)
from .scene import (
    _asphalt_material, _intersection_corner_pavement, _rounded_corner,
    _raised_median, _sidewalk_pair, _tactile_paving_mesh,
    _sidewalk_brick_palette, _sidewalk_brick_polygon,
    _road_crosswalk_diamond, _stacked_stop_marking, _vehicle_horizontal_extension,
)


PEDESTRIAN_STREET_LIGHT_MIN_SPACING_M = 20.0
DRIVEWAY_CUTOUT_FLAT_WIDTH_M = 6.4
DRIVEWAY_CUTOUT_TRANSITION_M = 0.4
DRIVEWAY_CUTOUT_HALF_EXTENT_M = (
    DRIVEWAY_CUTOUT_FLAT_WIDTH_M * 0.5 + DRIVEWAY_CUTOUT_TRANSITION_M)


def _deduplicate_pedestrian_street_lights(items):
    """Remove same-side pedestrian lights that crowd an adjacent edge.

    GUI-authored roads are split around junction approaches. Each split edge
    lays out its own end-filled sequence, so two otherwise valid sequences can
    put poles almost on top of one another at their shared boundary. Opposite
    sidewalks are intentionally independent even when the road is under 20 m
    wide.
    """
    kept = []
    minimum_sq = PEDESTRIAN_STREET_LIGHT_MIN_SPACING_M ** 2
    for item in items:
        if item[3] != "pedestrian":
            kept.append(item)
            continue
        _light_id, _edge_id, side, _kind, location, _rotation, _lit = item
        if any(
            candidate[3] == "pedestrian" and candidate[2] == side
            and ((location[0] - candidate[4][0]) ** 2
                 + (location[1] - candidate[4][1]) ** 2) <= minimum_sq
            for candidate in kept
        ):
            continue
        kept.append(item)
    return kept


def _clip_polygon_half_plane(points, plane):
    """Clip XY points to the positive side of an oriented line."""
    if plane is None:
        return list(points)
    origin, normal = plane
    result = []
    previous = points[-1]
    previous_distance = ((previous[0] - origin[0]) * normal[0]
                         + (previous[1] - origin[1]) * normal[1])
    for current in points:
        current_distance = ((current[0] - origin[0]) * normal[0]
                            + (current[1] - origin[1]) * normal[1])
        if current_distance >= -1e-8:
            if previous_distance < -1e-8:
                factor = previous_distance / (previous_distance - current_distance)
                result.append((
                    previous[0] + (current[0] - previous[0]) * factor,
                    previous[1] + (current[1] - previous[1]) * factor))
            result.append(current)
        elif previous_distance >= -1e-8:
            factor = previous_distance / (previous_distance - current_distance)
            result.append((
                previous[0] + (current[0] - previous[0]) * factor,
                previous[1] + (current[1] - previous[1]) * factor))
        previous, previous_distance = current, current_distance
    return result


def _subtract_convex_polygon(points, cutter):
    """Return convex pieces of ``points`` outside a convex XY cutter."""
    if len(points) < 3 or len(cutter) < 3:
        return [list(points)]
    signed_area = sum(
        point[0] * cutter[(index + 1) % len(cutter)][1]
        - cutter[(index + 1) % len(cutter)][0] * point[1]
        for index, point in enumerate(cutter))
    oriented = list(cutter if signed_area >= 0.0 else reversed(cutter))
    remaining = list(points)
    result = []
    for origin, target in zip(oriented, oriented[1:] + oriented[:1]):
        direction = (target[0] - origin[0], target[1] - origin[1])
        inside_plane = (origin, (-direction[1], direction[0]))
        outside_plane = (origin, (direction[1], -direction[0]))
        outside = _clip_polygon_half_plane(remaining, outside_plane)
        if len(outside) >= 3:
            result.append(outside)
        remaining = _clip_polygon_half_plane(remaining, inside_plane)
        if len(remaining) < 3:
            break
    return result


def _mesh_strip(name, samples, left_offset, right_offset, z, mat, thickness=0.0,
                clip_planes=(), cutout_polygons=()):
    if clip_planes or cutout_polygons:
        vertices, faces = [], []
        for first_sample, second_sample in zip(samples, samples[1:]):
            polygon = []
            for sample, offset in (
                    (first_sample, right_offset),
                    (second_sample, right_offset),
                    (second_sample, left_offset),
                    (first_sample, left_offset)):
                lateral = offset(sample.s) if callable(offset) else offset
                normal = (-sample.tangent[1], sample.tangent[0])
                polygon.append((sample.point[0] + normal[0] * lateral,
                                sample.point[1] + normal[1] * lateral))
            for plane in clip_planes:
                polygon = _clip_polygon_half_plane(polygon, plane)
                if len(polygon) < 3:
                    break
            polygons = [polygon] if len(polygon) >= 3 else []
            for cutter in cutout_polygons:
                polygons = [piece for candidate in polygons
                            for piece in _subtract_convex_polygon(candidate, cutter)]
            for polygon in polygons:
                top_start = len(vertices)
                vertices.extend((x, y, z) for x, y in polygon)
                faces.append(tuple(range(top_start, top_start + len(polygon))))
                if thickness:
                    bottom_start = len(vertices)
                    vertices.extend((x, y, z - thickness) for x, y in polygon)
                    faces.append(tuple(reversed(range(
                        bottom_start, bottom_start + len(polygon)))))
                    for index in range(len(polygon)):
                        nxt = (index + 1) % len(polygon)
                        faces.append((top_start + index, top_start + nxt,
                                      bottom_start + nxt, bottom_start + index))
        mesh = bpy.data.meshes.new(name + " mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        return obj
    top = []
    for sample in samples:
        left = left_offset(sample.s) if callable(left_offset) else left_offset
        right = right_offset(sample.s) if callable(right_offset) else right_offset
        nx, ny = -sample.tangent[1], sample.tangent[0]
        top.extend(((sample.point[0] + nx * left, sample.point[1] + ny * left, z),
                    (sample.point[0] + nx * right, sample.point[1] + ny * right, z)))
    vertices = list(top)
    faces = []
    for i in range(len(samples) - 1):
        a = i * 2
        faces.append((a, a + 2, a + 3, a + 1))
    if thickness:
        bottom_start = len(vertices)
        vertices.extend((x, y, z - thickness) for x, y, _ in top)
        for i in range(len(samples) - 1):
            a, b = i * 2, bottom_start + i * 2
            faces.extend(((b, b + 1, b + 3, b + 2),
                          (a, b, b + 2, a + 2), (a + 1, a + 3, b + 3, b + 1)))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


from road_generator.core.offset_path import ApproachOffsetPath as _ApproachOffsetPath


def _sidewalk_brick_path_band(name, path, start, end, band_min, band_max,
                              materials, clip_planes=(), cutout_polygons=(), street_frame=None):
    """Build the 200x400 mm weave along a curved path as one compact mesh."""
    if not materials or end - start <= 1e-6 or band_max - band_min <= 1e-6:
        return None
    unit, cell, inset = 0.20, 0.40, 0.0015
    seed = zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF
    rng = random.Random(seed)
    vertices, faces, material_indices = [], [], []

    def add_brick(s0, s1, lateral0, lateral1, material_index):
        if street_frame is not None:
            s0,s1=sorted(((s0-street_frame.offset)*street_frame.direction,
                          (s1-street_frame.offset)*street_frame.direction))
            lateral0,lateral1=sorted((lateral0*street_frame.direction,lateral1*street_frame.direction))
        s0, s1 = max(start, s0 + inset), min(end, s1 - inset)
        lateral0, lateral1 = max(band_min, lateral0 + inset), min(band_max, lateral1 - inset)
        if s1 <= s0 or lateral1 <= lateral0:
            return
        points = tuple(path.offset_point(
            station, lateral)
            for station, lateral in (
                (s0, lateral0), (s1, lateral0),
                (s1, lateral1), (s0, lateral1)))
        polygons = [list(points)]
        for plane in clip_planes:
            polygons = [_clip_polygon_half_plane(polygon, plane)
                        for polygon in polygons]
            polygons = [polygon for polygon in polygons if len(polygon) >= 3]
        for cutter in cutout_polygons:
            polygons = [piece for candidate in polygons
                        for piece in _subtract_convex_polygon(candidate, cutter)]
        for polygon in polygons:
            area2 = abs(sum(
                point[0] * polygon[(index + 1) % len(polygon)][1]
                - polygon[(index + 1) % len(polygon)][0] * point[1]
                for index, point in enumerate(polygon)))
            if area2 <= 1e-7:
                continue
            first = len(vertices)
            vertices.extend((*point, SIDEWALK_TOP_Z_M + 0.0005)
                            for point in polygon)
            faces.append(tuple(range(first, first + len(polygon))))
            material_indices.append(material_index)

    logical_start,logical_end = sorted((street_frame.at(start),street_frame.at(end))) if street_frame else (start,end)
    logical_min,logical_max = sorted((band_min*street_frame.direction,band_max*street_frame.direction)) if street_frame else (band_min,band_max)
    for column in range(math.floor(logical_start / cell), math.ceil(logical_end / cell)):
        for row in range(math.floor(logical_min / cell), math.ceil(logical_max / cell)):
            if street_frame:
                rng.seed(seed_for(street_frame.identity,column,row,'paving'))
            s0, lateral0 = column * cell, row * cell
            bricks = (((s0, s0 + cell, lateral0, lateral0 + unit),
                       (s0, s0 + cell, lateral0 + unit, lateral0 + cell))
                      if (column + row) % 2 == 0 else
                      ((s0, s0 + unit, lateral0, lateral0 + cell),
                       (s0 + unit, s0 + cell, lateral0, lateral0 + cell)))
            for brick in bricks:
                add_brick(*brick, rng.randrange(len(materials)))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    for face, material_index in zip(mesh.polygons, material_indices):
        face.material_index = material_index
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj["asset_kind"] = "sidewalk_brick_surface"
    obj["brick_count"] = len(faces)
    obj["deterministic_random_seed"] = seed
    solidify = obj.modifiers.new("Brick thickness", "SOLIDIFY")
    solidify.thickness = 0.012
    solidify.offset = -1.0
    bevel = obj.modifiers.new("Soft rounded brick edges", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    bevel.affect = "EDGES"
    return obj


def _polygon(name, points, z, mat):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata([(x, y, z) for x, y in points], [], [tuple(range(len(points)))])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _append_box(vertices, faces, center, along, across, z0, z1,
                top_start=None, top_end=None):
    """Append one oriented cuboid to a shared batch mesh."""
    cx, cy = center
    ax, ay = along
    bx, by = across
    first = len(vertices)
    corners = (
        (cx - ax - bx, cy - ay - by), (cx + ax - bx, cy + ay - by),
        (cx + ax + bx, cy + ay + by), (cx - ax + bx, cy - ay + by),
    )
    vertices.extend((x, y, z0) for x, y in corners)
    start_z = z1 if top_start is None else top_start
    end_z = z1 if top_end is None else top_end
    vertices.extend(((corners[0][0], corners[0][1], start_z),
                     (corners[1][0], corners[1][1], end_z),
                     (corners[2][0], corners[2][1], end_z),
                     (corners[3][0], corners[3][1], start_z)))
    faces.extend(tuple(first + i for i in face) for face in (
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ))


def _mesh_object(name, vertices, faces, mat, bevel=0.0):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if bevel:
        modifier = obj.modifiers.new("Rounded unit edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def _raised_median_along_path(name, path, start, end, width, height, mat,
                              rounded_start=False, rounded_end=False,
                              cap_depth=0.325):
    """Build a continuous raised median following a curved centreline."""
    samples = path.sample_interval(start, end, max_segment=0.45)
    radius = width * 0.5
    left = []
    right = []
    for sample in samples:
        normal = (-sample.tangent[1], sample.tangent[0])
        left.append((sample.point[0] + normal[0] * radius,
                     sample.point[1] + normal[1] * radius))
        right.append((sample.point[0] - normal[0] * radius,
                      sample.point[1] - normal[1] * radius))
    outline = list(left)
    cap_segments = 16
    if rounded_end:
        sample = samples[-1]
        heading = math.atan2(sample.tangent[1], sample.tangent[0])
        if abs(cap_depth - radius) <= 1e-12:
            outline.extend((sample.point[0] + math.cos(heading + math.pi / 2
                                                       - math.pi * i / cap_segments) * radius,
                            sample.point[1] + math.sin(heading + math.pi / 2
                                                       - math.pi * i / cap_segments) * radius)
                           for i in range(1, cap_segments + 1))
        else:
            outline.extend((sample.point[0]
                        + math.cos(heading) * math.sin(math.pi * i / cap_segments) * cap_depth
                        + math.cos(heading + math.pi / 2) * math.cos(math.pi * i / cap_segments) * radius,
                        sample.point[1]
                        + math.sin(heading) * math.sin(math.pi * i / cap_segments) * cap_depth
                        + math.sin(heading + math.pi / 2) * math.cos(math.pi * i / cap_segments) * radius)
                           for i in range(1, cap_segments + 1))
    outline.extend(reversed(right))
    if rounded_start:
        sample = samples[0]
        heading = math.atan2(sample.tangent[1], sample.tangent[0])
        if abs(cap_depth - radius) <= 1e-12:
            outline.extend((sample.point[0] + math.cos(heading - math.pi / 2
                                                       - math.pi * i / cap_segments) * radius,
                            sample.point[1] + math.sin(heading - math.pi / 2
                                                       - math.pi * i / cap_segments) * radius)
                           for i in range(1, cap_segments + 1))
        else:
            outline.extend((sample.point[0]
                        - math.cos(heading) * math.sin(math.pi * i / cap_segments) * cap_depth
                        - math.cos(heading + math.pi / 2) * math.cos(math.pi * i / cap_segments) * radius,
                        sample.point[1]
                        - math.sin(heading) * math.sin(math.pi * i / cap_segments) * cap_depth
                        - math.sin(heading + math.pi / 2) * math.cos(math.pi * i / cap_segments) * radius)
                           for i in range(1, cap_segments + 1))
    count = len(outline)
    vertices = [(x, y, z) for z in (0.0, height) for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces.extend((i, (i + 1) % count, count + (i + 1) % count, count + i)
                 for i in range(count))
    obj = _mesh_object(name, vertices, faces, mat,
                       min(0.035, height * 0.25, radius * 0.25))
    obj["follows_curved_centerline"] = True
    obj["median_width_m"] = width
    return obj


def _raised_variable_median(name, path, edge, start, end, height, mat,
                            rounded_start=True, rounded_end=True,
                            cap_depth=0.325):
    """Raised median whose centre and width vary through an approach taper."""
    samples = path.sample_interval(start, end, max_segment=0.35)
    left, right = [], []
    for sample in samples:
        lateral, width = approach_median_section(
            edge, sample.s, path.length)
        normal = (-sample.tangent[1], sample.tangent[0])
        center = (sample.point[0] + normal[0] * lateral,
                  sample.point[1] + normal[1] * lateral)
        radius = width * 0.5
        left.append((center[0] + normal[0] * radius,
                     center[1] + normal[1] * radius))
        right.append((center[0] - normal[0] * radius,
                      center[1] - normal[1] * radius))
    outline = list(left)
    cap_segments = 16
    if rounded_end:
        sample = samples[-1]
        lateral, width = approach_median_section(edge, sample.s, path.length)
        tangent, normal = sample.tangent, (-sample.tangent[1], sample.tangent[0])
        center = (sample.point[0] + normal[0] * lateral,
                  sample.point[1] + normal[1] * lateral)
        radius = width * 0.5
        outline.extend((center[0] + tangent[0] * math.sin(math.pi * i / cap_segments) * cap_depth
                        + normal[0] * math.cos(math.pi * i / cap_segments) * radius,
                        center[1] + tangent[1] * math.sin(math.pi * i / cap_segments) * cap_depth
                        + normal[1] * math.cos(math.pi * i / cap_segments) * radius)
                       for i in range(1, cap_segments + 1))
    outline.extend(reversed(right))
    if rounded_start:
        sample = samples[0]
        lateral, width = approach_median_section(edge, sample.s, path.length)
        tangent, normal = sample.tangent, (-sample.tangent[1], sample.tangent[0])
        center = (sample.point[0] + normal[0] * lateral,
                  sample.point[1] + normal[1] * lateral)
        radius = width * 0.5
        outline.extend((center[0] - tangent[0] * math.sin(math.pi * i / cap_segments) * cap_depth
                        - normal[0] * math.cos(math.pi * i / cap_segments) * radius,
                        center[1] - tangent[1] * math.sin(math.pi * i / cap_segments) * cap_depth
                        - normal[1] * math.cos(math.pi * i / cap_segments) * radius)
                       for i in range(1, cap_segments + 1))
    count = len(outline)
    vertices = [(x, y, z) for z in (0.0, height) for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces.extend((i, (i + 1) % count, count + (i + 1) % count, count + i)
                 for i in range(count))
    obj = _mesh_object(name, vertices, faces, mat, min(0.035, height * 0.25))
    obj["variable_approach_section"] = True
    return obj


def _curb_top_profiles(start, end, lowered_sections, intervals=None):
    """Return per-block endpoint heights for flush sections and 400mm ramps."""
    count = max(1, round((end - start) / CURB_BLOCK_LENGTH_M))
    pitch = (end - start) / count
    def height_at(station):
        height = CURB_TOP_Z_M
        for center, flat_width in lowered_sections:
            distance = abs(station - center)
            flat_half = flat_width * 0.5
            if distance <= flat_half:
                candidate = SIDEWALK_TOP_Z_M
            elif distance < flat_half + DRIVEWAY_CUTOUT_TRANSITION_M:
                factor = ((distance - flat_half)
                          / DRIVEWAY_CUTOUT_TRANSITION_M)
                candidate = (SIDEWALK_TOP_Z_M
                             + (CURB_TOP_Z_M - SIDEWALK_TOP_Z_M) * factor)
            else:
                continue
            height = min(height, candidate)
        return height
    return [(height_at(a), height_at(b)) for a,b in
            (intervals if intervals is not None else
             [(start+i*pitch,start+(i+1)*pitch) for i in range(count)])]


def _curb_blocks_along_path(name, path, start, end, lateral, curb_material,
                            road_reference=None, lowered_crossing_distances=(),
                            lowered_driveway_distances=(), logical_offset=0.0):
    """Mature 400 mm kerb vocabulary following a path as rigid short units."""
    length = end - start
    intervals = tuple(_dash_intervals(start,end,CURB_BLOCK_LENGTH_M,0,logical_offset))
    count = len(intervals)
    raised_vertices, raised_faces = [], []
    apron_vertices, apron_faces = [], []
    foundation_vertices, foundation_faces = [], []
    top_profiles = _curb_top_profiles(
        start, end,
        tuple((distance, 3.2) for distance in lowered_crossing_distances)
        + tuple((distance, DRIVEWAY_CUTOUT_FLAT_WIDTH_M)
                for distance in lowered_driveway_distances), intervals=intervals)
    for index, (a,b) in enumerate(intervals):
        a += CURB_BLOCK_JOINT_M * .5
        b -= CURB_BLOCK_JOINT_M * .5
        p0 = path.offset_point(a, lateral)
        p1 = path.offset_point(b, lateral)
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        segment_length = math.hypot(dx, dy)
        if segment_length <= 1e-6:
            continue
        ux, uy = dx / segment_length, dy / segment_length
        nx, ny = -uy, ux
        center = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
        _append_box(raised_vertices, raised_faces, center,
                    (ux * segment_length * 0.5, uy * segment_length * 0.5),
                    (nx * CURB_WIDTH_M * 0.5, ny * CURB_WIDTH_M * 0.5),
                    0.0, CURB_TOP_Z_M,
                    top_start=top_profiles[index][0],
                    top_end=top_profiles[index][1])
        if road_reference is None:
            road_sign = -1.0 if lateral > 0 else 1.0
        else:
            to_road = (road_reference[0] - center[0],
                       road_reference[1] - center[1])
            road_sign = 1.0 if to_road[0] * nx + to_road[1] * ny >= 0 else -1.0
        apron_center = (center[0] + nx * road_sign *
                        (CURB_WIDTH_M + CURB_ROAD_APRON_M) * 0.5,
                        center[1] + ny * road_sign *
                        (CURB_WIDTH_M + CURB_ROAD_APRON_M) * 0.5)
        _append_box(apron_vertices, apron_faces, apron_center,
                    (ux * segment_length * 0.5, uy * segment_length * 0.5),
                    (nx * CURB_ROAD_APRON_M * 0.5,
                     ny * CURB_ROAD_APRON_M * 0.5), -0.025, 0.0015)
        _append_box(foundation_vertices, foundation_faces, center,
                    (ux * segment_length * 0.5, uy * segment_length * 0.5),
                    (nx * (CURB_WIDTH_M + CURB_ROAD_APRON_M) * 0.5,
                     ny * (CURB_WIDTH_M + CURB_ROAD_APRON_M) * 0.5),
                    -0.026, -0.002)
    raised = _mesh_object(name + " blocks", raised_vertices, raised_faces,
                          curb_material, 0.01)
    raised["block_nominal_length_m"] = CURB_BLOCK_LENGTH_M
    raised["block_count"] = count
    raised["lowered_crossing_count"] = len(lowered_crossing_distances)
    raised["lowered_driveway_count"] = len(lowered_driveway_distances)
    raised["driveway_flat_width_m"] = DRIVEWAY_CUTOUT_FLAT_WIDTH_M
    _mesh_object(name + " flush road-level blocks", apron_vertices,
                 apron_faces, curb_material, 0.00075)
    foundation = _mesh_object(name + " buried foundation", foundation_vertices,
                              foundation_faces, curb_material)
    foundation["buried_below_road_surface"] = True
    return raised


def _rotated_crosswalk(name, center, outward, road_width, span, mat):
    """Use the legacy 450/450 mm zebra rhythm in an arbitrary arm frame."""
    stripe = gap = 0.45
    count = max(4, round((road_width + gap) / (stripe + gap)))
    actual_gap = (road_width - count * stripe) / (count - 1)
    first = -road_width * 0.5 + stripe * 0.5
    across = (-outward[1], outward[0])
    half_along = (outward[0] * span * 0.5, outward[1] * span * 0.5)
    half_across = (across[0] * stripe * 0.5, across[1] * stripe * 0.5)
    polygons = []
    for index in range(count):
        offset = first + index * (stripe + actual_gap)
        p = add(center, mul(across, offset))
        polygons.append(tuple(
            (p[0] + half_along[0] * along_sign + half_across[0] * across_sign,
             p[1] + half_along[1] * along_sign + half_across[1] * across_sign)
            for along_sign, across_sign in ((-1, -1), (1, -1),
                                            (1, 1), (-1, 1))))
    obj = extruded_polygons(name + " stripes", polygons, 0.0,
                            ROAD_PAINT_THICKNESS_M, mat, ROAD_PAINT_BEVEL_M)
    obj["stripe_count"] = count
    return obj


def _rotated_stop_line(name, center, outward, width, mat):
    obj = cube(name, (*center, ROAD_PAINT_CENTER_Z_M),
               (0.30, width, ROAD_PAINT_THICKNESS_M), mat, ROAD_PAINT_BEVEL_M)
    obj.rotation_euler[2] = math.atan2(outward[1], outward[0])


def _curb_paint_on_blocks(name, curb_row, path, paint_start, paint_end, mat,
                          logical_offset=0.0, logical_direction=1):
    """Use the generated stone tops for both straight and path-based curbs."""
    if curb_row is None:
        return
    vertices, faces = [], []
    painted_count = 0
    stone_vertices = curb_row.data.vertices
    matrix = curb_row.matrix_world
    for index in range(0, len(stone_vertices), 8):
        # Both curb builders batch eight vertices per stone, with the top
        # four last. Read their real ends and heights instead of making a
        # second block grid from the paint span or the road's nominal pitch.
        top = [matrix @ stone_vertices[index + i].co for i in (4, 5, 6, 7)]
        p0 = (top[0] + top[3]) * 0.5
        p1 = (top[1] + top[2]) * 0.5
        a, b = sorted((path.project_point(p0.xy)[0], path.project_point(p1.xy)[0]))
        logical_midpoint = logical_direction * (logical_offset + (a + b) * 0.5)
        if math.floor(logical_midpoint / 1.2 + 1e-9) % 2:
            continue
        if a < paint_start - 1e-5 or b > paint_end + 1e-5:
            continue
        dx, dy = p1.x - p0.x, p1.y - p0.y
        segment_length = math.hypot(dx, dy)
        if segment_length <= 1e-6:
            continue
        center = ((p0.x + p1.x) * 0.5, (p0.y + p1.y) * 0.5)
        _append_box(
            vertices, faces, center, (dx * 0.5, dy * 0.5),
            (-dy / segment_length * (CURB_WIDTH_M - 0.02) * 0.5,
             dx / segment_length * (CURB_WIDTH_M - 0.02) * 0.5),
            min(p0.z, p1.z), max(p0.z, p1.z) + 0.002,
            top_start=p0.z + 0.002, top_end=p1.z + 0.002,
        )
        painted_count += 1
    if vertices:
        obj = _mesh_object(name + " painted blocks", vertices, faces, mat, 0.01)
        obj["painted_curb_block_count"] = painted_count
        obj["source_curb"] = curb_row.name
        obj["lowered_driveway_count"] = curb_row.get("lowered_driveway_count", 0)
        return obj


def _tile_corners(tile):
    angle = math.radians(tile.rotation_degrees)
    along = (math.cos(angle), math.sin(angle))
    across = (-along[1], along[0])
    if tile.guidance_axis == "y":
        along, across = across, (-across[1], across[0])
    ha, hb = tile.size[0] * 0.5, tile.size[1] * 0.5
    if tile.guidance_axis == "y":
        ha, hb = tile.size[1] * 0.5, tile.size[0] * 0.5
    return tuple((tile.center[0] + along[0] * ha * sa + across[0] * hb * sb,
                  tile.center[1] + along[1] * ha * sa + across[1] * hb * sb)
                 for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1)))


def _tiles_overlap(a, b, tolerance=1e-5):
    ca, cb = _tile_corners(a), _tile_corners(b)
    for corners in (ca, cb):
        for p, q in zip(corners, corners[1:] + corners[:1]):
            axis = (-(q[1] - p[1]), q[0] - p[0])
            pa = [point[0] * axis[0] + point[1] * axis[1] for point in ca]
            pb = [point[0] * axis[0] + point[1] * axis[1] for point in cb]
            if max(pa) <= min(pb) + tolerance or max(pb) <= min(pa) + tolerance:
                return False
    return True


def _trim_continuous_tactile_joints(plans):
    """Resolve cross-edge seams without dropping either 300mm product."""
    result = list(plans)
    cell_size = 0.60
    grid = {}
    for index, tile in enumerate(result):
        if tile.kind != "guidance" or not tile.route_key:
            continue
        cell = (math.floor(tile.center[0] / cell_size),
                math.floor(tile.center[1] / cell_size))
        neighbors = [other for x in range(cell[0] - 1, cell[0] + 2)
                     for y in range(cell[1] - 1, cell[1] + 2)
                     for other in grid.get((x, y), ())]
        for other_index in neighbors:
            other = result[other_index]
            if (other.route_key != tile.route_key
                    or not _tiles_overlap(result[index], other,
                                          tolerance=1e-9)):
                continue
            # Only the longitudinal size changes. Binary-searching both
            # products together preserves their rigid orientations and leaves
            # the same negligible triangular seam as an ordinary curve joint.
            maximum = min(result[index].size[0], other.size[0])
            low, high = 0.0, maximum
            for _ in range(32):
                candidate = (low + high) * 0.5
                a = replace(result[index], size=(candidate,
                                                  result[index].size[1]))
                b = replace(other, size=(candidate, other.size[1]))
                if _tiles_overlap(a, b, tolerance=1e-9):
                    high = candidate
                else:
                    low = candidate
            safe = low * (1.0 - 1e-7)
            result[index] = replace(
                result[index], size=(min(result[index].size[0], safe),
                                     result[index].size[1]))
            result[other_index] = replace(
                other, size=(min(other.size[0], safe), other.size[1]))
        grid.setdefault(cell, []).append(index)
    return tuple(result)


def _non_overlapping_tactile(plans):
    """Warning tiles win; clip guidance length without overlapping or bending."""
    cell_size = 0.60
    def cells(item):
        corners = _tile_corners(item)
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        return tuple((x, y)
                     for x in range(math.floor(min(xs) / cell_size),
                                    math.floor(max(xs) / cell_size) + 1)
                     for y in range(math.floor(min(ys) / cell_size),
                                    math.floor(max(ys) / cell_size) + 1))

    def nearby(grid, item):
        result = []
        seen = set()
        for cell in cells(item):
            for other in grid.get(cell, ()):
                marker = id(other)
                if marker not in seen:
                    seen.add(marker)
                    result.append(other)
        return result

    def index(grid, item):
        for cell in cells(item):
            grid.setdefault(cell, []).append(item)

    warnings = []
    warning_grid = {}
    # Oblique warning fields meet as rigid 300 mm products. Keep a stable
    # maximal non-overlapping set and leave the unavoidable triangular seam;
    # never hide one product below another.
    for item in sorted((item for item in plans if item.kind == "warning"),
                       key=lambda item: item.id):
        if not any(_tiles_overlap(item, other)
                   for other in nearby(warning_grid, item)):
            warnings.append(item)
            index(warning_grid, item)
    accepted = list(warnings)
    # Guidance routes can contain many thousands of 300 mm products on a
    # district-scale scene. Comparing every new tile with every accepted tile
    # is quadratic and made an otherwise small scene take several minutes.
    # A fixed spatial index preserves the exact SAT overlap test while limiting
    # candidates to products occupying the same nearby cells.
    guidance_grid = {}
    def route_id(item):
        if item.route_key:
            return item.route_key
        base = item.id.rsplit("_part_", 1)[0]
        return base.rsplit("_", 2)[0]

    for tile in (item for item in plans if item.kind == "guidance"):
        angle = math.radians(tile.rotation_degrees)
        along = (math.cos(angle), math.sin(angle))
        across = (-along[1], along[0])
        along_size, across_size = tile.size
        intervals = [(-along_size * 0.5, along_size * 0.5)]
        for warning in nearby(warning_grid, tile):
            projections_along = []
            projections_across = []
            for corner in _tile_corners(warning):
                dx, dy = corner[0] - tile.center[0], corner[1] - tile.center[1]
                projections_along.append(dx * along[0] + dy * along[1])
                projections_across.append(dx * across[0] + dy * across[1])
            if (max(projections_across) <= -across_size * 0.5 + 1e-5
                    or min(projections_across) >= across_size * 0.5 - 1e-5):
                continue
            cut_start, cut_end = min(projections_along), max(projections_along)
            next_intervals = []
            for start, end in intervals:
                if cut_end <= start + 1e-5 or cut_start >= end - 1e-5:
                    next_intervals.append((start, end))
                    continue
                if cut_start - start >= 0.01:
                    next_intervals.append((start, cut_start))
                if end - cut_end >= 0.01:
                    next_intervals.append((cut_end, end))
            intervals = next_intervals
        for part, (start, end) in enumerate(intervals):
            midpoint = (start + end) * 0.5
            piece = TactileTilePlan(
                f"{tile.id}_part_{part}", tile.kind,
                (tile.center[0] + along[0] * midpoint,
                 tile.center[1] + along[1] * midpoint),
                (end - start, across_size), tile.guidance_axis,
                tile.rotation_degrees, tile.route_key,
            )
            # Corner runs are already ended with a physical wedge. This final
            # guard catches only accidental guidance/guidance intrusion.
            if not any(route_id(other) != route_id(piece)
                       and _tiles_overlap(piece, other)
                       for other in nearby(guidance_grid, piece)):
                accepted.append(piece)
                index(guidance_grid, piece)
    return tuple(accepted)


def _map_chord_point_to_path(network, edge, path, point):
    """Carry a mature straight-edge plan into the centreline's local frame."""
    start = network.nodes[edge.start].position
    end = network.nodes[edge.end].position
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    rx, ry = point[0] - start[0], point[1] - start[1]
    fraction = max(0.0, min(1.0, (rx * ux + ry * uy) / length))
    lateral = rx * nx + ry * ny
    station = fraction * path.length
    return path.offset_point(station, lateral), station


def _tactile_tiles_along_path(plans, name, path, start, end, lateral,
                              kind="guidance", rows=1, allow_empty=False,
                              route_key=""):
    """Plan rigid 300 mm tiles; shared detailed prototypes render them later."""
    tile = 0.30
    # Measure the route on its actual lateral offset, not on the road
    # centreline. Outer curves are longer and require more products; inner
    # curves require fewer. A dense station lookup keeps this generic for both
    # Bezier centrelines and sampled corner polylines.
    lookup_count = max(1, math.ceil((end - start) / 0.10))
    lookup = []
    offset_distances = [0.0]
    for index in range(lookup_count + 1):
        station = start + (end - start) * index / lookup_count
        point = path.offset_point(station, lateral)
        lookup.append((station, point))
        if index:
            offset_distances.append(
                offset_distances[-1] + math.dist(lookup[-2][1], point))
    offset_length = offset_distances[-1]
    # Explicit half-up rounding with a numerical cushion keeps an exact
    # cardinal run and its infinitesimally rotated equivalent on the same
    # physical tile count; Python's bankers-rounding changed four corners at
    # precisely N+0.5 tiles.
    rounded_count = math.floor(offset_length / tile + 0.500001)
    count = rounded_count if allow_empty else max(1, rounded_count)
    if count == 0:
        return
    pitch = offset_length / count
    samples = []
    for index in range(count):
        target = (index + 0.5) * pitch
        lookup_index = next(
            item for item in range(len(offset_distances) - 1)
            if target <= offset_distances[item + 1] + 1e-9)
        span = offset_distances[lookup_index + 1] - offset_distances[lookup_index]
        factor = ((target - offset_distances[lookup_index]) / max(span, 1e-9))
        station = (lookup[lookup_index][0]
                   + (lookup[lookup_index + 1][0] - lookup[lookup_index][0])
                   * factor)
        # Orient each rigid product from the sampled route itself.  An
        # _ApproachOffsetPath moves the sidewalk laterally while an extra
        # inbound lane opens; its underlying road-centre tangent therefore
        # does not describe the actual guidance line.  The same sampled chord
        # also works for ordinary Bezier curves and stays consistent with the
        # arc-length lookup used for tile spacing.
        chord_start = lookup[lookup_index][1]
        chord_end = lookup[lookup_index + 1][1]
        chord_length = math.dist(chord_start, chord_end)
        tangent = ((chord_end[0] - chord_start[0]) / max(chord_length, 1e-9),
                   (chord_end[1] - chord_start[1]) / max(chord_length, 1e-9))
        normal = (-tangent[1], tangent[0])
        point = path.offset_point(station, lateral)
        rotation = math.degrees(math.atan2(tangent[1], tangent[0]))
        samples.append((point, tangent, normal, rotation))
    along_sizes = [pitch] * len(samples)
    for index in range(len(samples) - 1):
        point, tangent, _, rotation = samples[index]
        other_point, other_tangent, _, other_rotation = samples[index + 1]
        turn = abs(tangent[0] * other_tangent[1]
                   - tangent[1] * other_tangent[0])
        if turn == 0.0:
            continue
        distance = math.dist(point, other_point)
        low, high = 0.0, distance * 1.5
        # Find the largest equal rigid product length whose two oriented
        # rectangles do not overlap. This leaves only a numerical seam at one
        # corner while preserving exact 300 mm straight-road products.
        for _ in range(32):
            candidate = (low + high) * 0.5
            a = TactileTilePlan("a", kind, point,
                                (candidate, tile), "x", rotation)
            b = TactileTilePlan("b", kind, other_point,
                                (candidate, tile), "x", other_rotation)
            if _tiles_overlap(a, b, tolerance=1e-9):
                high = candidate
            else:
                low = candidate
        safe_length = low * (1.0 - 1e-7)
        along_sizes[index] = min(along_sizes[index], safe_length)
        along_sizes[index + 1] = min(along_sizes[index + 1], safe_length)
    for index, (point, tangent, normal, rotation) in enumerate(samples):
        along_size = along_sizes[index]
        for row in range(rows):
            row_offset = (row - (rows - 1) * 0.5) * tile
            center = (point[0] + normal[0] * row_offset,
                      point[1] + normal[1] * row_offset)
            plans.append(TactileTilePlan(
                f"{name}_{index}_{row}", kind, center,
                (along_size, tile), "x", rotation,
                route_key,
            ))


def _cubic_points(p0, c0, c1, p1, steps=12):
    result = []
    for index in range(steps + 1):
        t = index / steps
        u = 1.0 - t
        result.append((u ** 3 * p0[0] + 3 * u * u * t * c0[0]
                       + 3 * u * t * t * c1[0] + t ** 3 * p1[0],
                       u ** 3 * p0[1] + 3 * u * u * t * c0[1]
                       + 3 * u * t * t * c1[1] + t ** 3 * p1[1]))
    return result


def _line_intersection(p, u, q, v):
    denominator = u[0] * v[1] - u[1] * v[0]
    if abs(denominator) < 1e-10:
        return None
    qmp = (q[0] - p[0], q[1] - p[1])
    factor = (qmp[0] * v[1] - qmp[1] * v[0]) / denominator
    return (p[0] + u[0] * factor, p[1] + u[1] * factor)


class _PolylinePath:
    """Small arc-length adapter used for already sampled junction kerb curves."""

    def __init__(self, points):
        self.points = tuple(points)
        self.distances = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.distances.append(self.distances[-1] + math.hypot(
                b[0] - a[0], b[1] - a[1]))
        self.length = self.distances[-1]

    def _segment(self, station):
        station = max(0.0, min(self.length, station))
        for index in range(len(self.distances) - 1):
            if station <= self.distances[index + 1] + 1e-9:
                span = self.distances[index + 1] - self.distances[index]
                return index, (station - self.distances[index]) / max(span, 1e-9)
        return len(self.points) - 2, 1.0

    def tangent_at_distance(self, station):
        index, _ = self._segment(station)
        a, b = self.points[index], self.points[index + 1]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)

    def project_point(self, point):
        best_station, best_distance = 0.0, float("inf")
        for index, (a, b) in enumerate(zip(self.points, self.points[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            span_sq = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((point[0] - a[0]) * dx
                                  + (point[1] - a[1]) * dy) / max(span_sq, 1e-12)))
            distance = math.hypot(point[0] - a[0] - t * dx,
                                  point[1] - a[1] - t * dy)
            if distance < best_distance:
                best_station = self.distances[index] + t * math.sqrt(span_sq)
                best_distance = distance
        return best_station, best_distance

    def offset_point(self, station, lateral):
        index, factor = self._segment(station)
        a, b = self.points[index], self.points[index + 1]
        point = (a[0] + (b[0] - a[0]) * factor,
                 a[1] + (b[1] - a[1]) * factor)
        tangent = self.tangent_at_distance(station)
        return (point[0] - tangent[1] * lateral,
                point[1] + tangent[0] * lateral)


def _sidewalk_width_for_edge(edge):
    """Return pavement width without changing any road-side datum."""
    return sidewalk_width(edge)


def _sidewalk_footprint_for_edge(edge):
    return sidewalk_footprint(edge)


def _sidewalk_extension_cutout(network, edge, endpoint, side, paths):
    """Return the adjoining finite sidewalk polygon when this arm loses."""
    node_id = edge.start if endpoint == "start" else edge.end
    if network.nodes[node_id].kind not in JUNCTION_KINDS:
        return None
    arms = junction_arms(network, node_id, paths)
    arm = next(item for item in arms if item.edge_id == edge.id)
    # Path-left becomes arm-right when the edge terminates at the junction.
    local_side = side if endpoint == "start" else -side
    signed_candidates = []
    for candidate in arms:
        if candidate.edge_id == edge.id:
            continue
        signed = (candidate.angle - arm.angle + 180.0) % 360.0 - 180.0
        if (local_side > 0 and signed > 1e-6
                or local_side < 0 and signed < -1e-6):
            signed_candidates.append((abs(signed), candidate, signed))
    if not signed_candidates:
        return None
    gap, neighbor, signed = min(signed_candidates, key=lambda item: item[0])
    if gap > 150.0:
        return None
    neighbor_edge = next(item for item in network.edges
                         if item.id == neighbor.edge_id)
    if not neighbor_edge.median or neighbor_edge.sidewalks != "both":
        return None

    current_key = (arm.width, abs(arm.outward[0]), abs(arm.outward[1]), edge.id)
    neighbor_key = (neighbor.width, abs(neighbor.outward[0]), abs(neighbor.outward[1]),
                    neighbor_edge.id)
    if current_key >= neighbor_key:
        return None
    center = network.nodes[node_id].position
    neighbor_side = -1.0 if signed > 0.0 else 1.0
    standard_offset = neighbor_side * (
        neighbor.width * 0.5 + CURB_WIDTH_M)
    wide_offset = neighbor_side * (
        neighbor.width * 0.5 + _sidewalk_footprint_for_edge(neighbor_edge))
    near = _arm_trim(neighbor, arms)
    far = near + max(item.length for item in paths.values()) + 10.0
    return (
        point_from_node(center, neighbor, near, standard_offset),
        point_from_node(center, neighbor, far, standard_offset),
        point_from_node(center, neighbor, far, wide_offset),
        point_from_node(center, neighbor, near, wide_offset),
    )


def _sidewalk_extension_connector(network, edge, endpoint, side, paths):
    """Bridge a wide arm to an adjoining standard-width sidewalk outer line."""
    node_id = edge.start if endpoint == "start" else edge.end
    if network.nodes[node_id].kind not in JUNCTION_KINDS:
        return None
    arms = junction_arms(network, node_id, paths)
    arm = next(item for item in arms if item.edge_id == edge.id)
    local_side = side if endpoint == "start" else -side
    candidates = []
    for candidate in arms:
        if candidate.edge_id == edge.id:
            continue
        signed = (candidate.angle - arm.angle + 180.0) % 360.0 - 180.0
        if (local_side > 0 and signed > 1e-6
                or local_side < 0 and signed < -1e-6):
            candidates.append((abs(signed), candidate, signed))
    if not candidates:
        return None
    gap, neighbor, signed = min(candidates, key=lambda item: item[0])
    if gap > 150.0:
        return None
    neighbor_edge = next(item for item in network.edges
                         if item.id == neighbor.edge_id)
    if neighbor_edge.median or neighbor_edge.sidewalks != "both":
        return None
    center = network.nodes[node_id].position
    neighbor_side = -1.0 if signed > 0.0 else 1.0
    neighbor_footprint = SIDEWALK_CORNER_RADIUS_M
    neighbor_outer_offset = neighbor_side * (
        neighbor.width * 0.5 + neighbor_footprint)
    neighbor_outer = point_from_node(
        center, neighbor, 0.0,
        neighbor_outer_offset)
    trim = _arm_trim(arm, arms)
    standard_offset = local_side * (
        arm.width * 0.5 + SIDEWALK_CORNER_RADIUS_M)
    wide_offset = local_side * (
        arm.width * 0.5 + _sidewalk_footprint_for_edge(edge))
    standard_start = point_from_node(center, arm, trim, standard_offset)
    wide_start = point_from_node(center, arm, trim, wide_offset)
    standard_joint = _line_intersection(
        standard_start, arm.outward, neighbor_outer, neighbor.outward)
    wide_joint = _line_intersection(
        wide_start, arm.outward, neighbor_outer, neighbor.outward)
    if standard_joint is None or wide_joint is None:
        return None
    # Only add the portion between the mature endpoint and the junction. A
    # joint farther outward is already covered by the constant-width strip.
    standard_distance = ((standard_joint[0] - center[0]) * arm.outward[0]
                         + (standard_joint[1] - center[1]) * arm.outward[1])
    wide_distance = ((wide_joint[0] - center[0]) * arm.outward[0]
                     + (wide_joint[1] - center[1]) * arm.outward[1])
    if min(standard_distance, wide_distance) >= trim - 1e-6:
        return None
    connector = (standard_start, wide_start, wide_joint, standard_joint)
    return (connector,)


def _trim_interval(network, edge, path):
    paths = {edge.id: path}

    def trim(node_id):
        if network.nodes[node_id].kind not in JUNCTION_KINDS:
            return 0.0
        # For the supported near-orthogonal range, the distance to the tangent
        # point is the half-width of the crossing road plus the mature 3.8 m
        # corner radius.  Select the widest approximately perpendicular arm.
        all_paths = validate_general_network(network)
        arm = next(item for item in junction_arms(network, node_id, all_paths)
                   if item.edge_id == edge.id)
        others = junction_arms(network, node_id, all_paths)
        perpendicular = [item.width * 0.5 for item in others
                         if 60.0 <= abs((item.angle - arm.angle + 180) % 360 - 180) <= 120.0]
        return max(perpendicular, default=arm.width * 0.5) + SIDEWALK_CORNER_RADIUS_M

    start = trim(edge.start)
    end = path.length - trim(edge.end)
    if end <= start + 0.5:
        raise ValueError(f"Edge {edge.id!r} is too short for intersection approaches")
    return start, end


def _arm_perpendicular_half_width(arm, arms):
    values = [item.width * 0.5 for item in arms
              if 60.0 <= abs((item.angle - arm.angle + 180) % 360 - 180) <= 120.0]
    return max(values, default=arm.width * 0.5)


def _arm_trim(arm, arms):
    return _arm_perpendicular_half_width(arm, arms) + SIDEWALK_CORNER_RADIUS_M


def _arm_crosswalk_distance(arm, arms):
    return (_arm_perpendicular_half_width(arm, arms)
            + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M)


def _sample_offset_interval(path, start, end, offset, max_segment=0.8):
    samples = path.sample_interval(start, end, max_segment)
    result = []
    for item in samples:
        if isinstance(path, _ApproachOffsetPath):
            point = path.offset_point(item.s, offset)
        else:
            normal = (-item.tangent[1], item.tangent[0])
            point = add(item.point, mul(normal, offset))
        result.append(type(item)(item.s, point, item.tangent))
    return tuple(result)


def _dash_intervals(start, end, dash=3.0, gap=3.0, phase=0.0):
    """Yield a periodic dash pattern in a shared logical-road station frame."""
    cycle = dash + gap
    cursor = math.floor((start + phase) / cycle) * cycle - phase
    while cursor < end - 0.05:
        painted_start = max(start, cursor)
        painted_end = min(end, cursor + dash)
        if painted_end > painted_start + 0.05:
            yield painted_start, painted_end
        cursor += cycle


def _arm_selected(node, arm, groups):
    phase = node.signal_phase
    group_index = next((i for i, group in enumerate(groups) if arm in group), 0)
    # Preserve old files by mapping their geographic names to the group whose
    # arm is most horizontal/vertical. New samples may use group_a/group_b.
    if phase.startswith("group_a"):
        active = group_index == 0
    elif phase.startswith("group_b"):
        active = group_index == 1
    else:
        wants_horizontal = phase.startswith("east_west")
        group_horizontal = sum(abs(item.outward[0]) for item in groups[group_index]) >= sum(
            abs(item.outward[1]) for item in groups[group_index])
        active = wants_horizontal == group_horizontal
    return active


def _arm_active(node, arm, groups):
    phase = node.signal_phase
    if phase == "all_red" or not _arm_selected(node, arm, groups):
        return "red"
    if phase.endswith("right_arrow"):
        return "red"
    if phase.endswith("yellow"):
        return "yellow"
    return "green"


def _pedestrian_arm_selected(node, rotation_degrees, arms, groups):
    """Whether the road parallel to this pedestrian crossing has right of way."""
    angle = math.radians(rotation_degrees)
    walking = (math.sin(angle), math.cos(angle))
    parallel_arm = max(
        arms,
        key=lambda item: abs(item.outward[0] * walking[0]
                             + item.outward[1] * walking[1]),
    )
    return _arm_selected(node, parallel_arm, groups)


def build_general_scene(root: Path, network):
    started = time.perf_counter()
    checkpoint = started
    def profile(label):
        nonlocal checkpoint
        now = time.perf_counter()
        if os.environ.get("ROAD_GENERATOR_PROFILE") == "1":
            print(f"PROFILE_GENERAL_{label}_SECONDS={now - checkpoint:.6f}")
        checkpoint = now
    paths = validate_general_network(network)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.data.collections.new("Generated General Road Network")
    bpy.context.scene.collection.children.link(collection)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[collection.name]

    asphalt = _asphalt_material()
    sidewalk = weathered_material("Sidewalk concrete", (0.28, 0.29, 0.27),
                                  (0.47, 0.48, 0.44), 0.88, 8.0, "concrete")
    sidewalk_bricks = _sidewalk_brick_palette()
    curb = weathered_material("Curb concrete", (0.36, 0.37, 0.34),
                              (0.58, 0.58, 0.53), 0.82, 12.0, "concrete")
    median_concrete = weathered_material(
        "Median concrete", (0.31, 0.32, 0.30),
        (0.53, 0.53, 0.49), 0.86, 14.0, "concrete")
    white = road_marking_material("Road marking white thermoplastic", (0.56, 0.56, 0.50),
                                  (0.91, 0.89, 0.79), (0.16, 0.17, 0.16))
    orange = road_marking_material("General orange thermoplastic", (0.56, 0.20, 0.018),
                                   (0.95, 0.43, 0.035), (0.14, 0.10, 0.055), 0.70)
    bicycle_blue = road_marking_material(
        "Bicycle lane blue thermoplastic", (0.035, 0.245, 0.390),
        (0.275, 0.694, 0.882), (0.035, 0.075, 0.090), 0.76)
    tactile = weathered_material("Tactile paving yellow", (0.58, 0.39, 0.018),
                                 (0.98, 0.72, 0.055), 0.83, 18.0)
    ground = weathered_material("Urban ground", (0.12, 0.105, 0.075),
                                (0.20, 0.17, 0.12), 0.96, 3.0)
    tactile_plans = []
    tactile_route_terminals = []
    crossing_tactile_sides = {}
    compatibility_crosswalks = plan_crosswalks(network)
    stop_controlled_approaches = {
        (approach.edge_id, approach.node_id)
        for approach in plan_network(network).approaches
        if approach.stop_control
    }
    compatibility_medians = plan_medians(network, compatibility_crosswalks)
    compatibility_signals = plan_signal_sites(network, compatibility_medians)
    compatibility_blocks = plan_signal_blocks(compatibility_signals)
    signal_block_by_pedestrian = {
        site.id: block for block in compatibility_blocks
        for site in block.pedestrians
    }
    countdown_by_node = {
        item.node_id: item for item in plan_pedestrian_countdowns(network)
    }
    planned_guardrails = plan_guardrails(network, compatibility_crosswalks)
    planned_plantings = plan_plantings(network, compatibility_crosswalks)
    planned_bicycles = plan_bicycle_markings(network)
    planned_trees = plan_street_trees(network, compatibility_crosswalks)
    street_light_specs = []
    for edge in network.edges:
        if not edge.street_lights:
            continue
        if edge.median:
            street_light_specs.append(("roadway", network.scene.time_of_day == "night"))
        if edge.sidewalks == "both":
            street_light_specs.append(("pedestrian", network.scene.time_of_day == "night"))
    prewarm_street_light_components(street_light_specs)
    median_devices = plan_median_island_devices(
        network, compatibility_medians, compatibility_signals)
    device_types = {item.device_type for item in median_devices}
    if "keep_left_sign" in device_types:
        prewarm_cached_asset(
            ("median island device", "procedural_keep_left"),
            lambda: create_keep_left_sign("Procedural Keep Left Prototype"),
        )
    if "dual_warning_lamp" in device_types:
        prewarm_cached_asset(
            ("median island device", "dual_warning_lamp"),
            lambda: create_dual_warning_lamp("Dual Warning Lamp Prototype"),
        )
    plantings_by_edge = {}
    corner_plantings = {}
    for item in planned_plantings:
        if item.curve_center is None:
            plantings_by_edge.setdefault(item.edge_id, {})[item.side] = item
        else:
            for node in network.nodes.values():
                if item.id == f"{node.id}_{item.side}_corner_planting":
                    corner_plantings[(node.id, item.side)] = item
                    break
    corner_guardrails = {}
    for item in planned_guardrails:
        if item.curve_center is not None:
            for node in network.nodes.values():
                if item.id == f"{node.id}_{item.side}_corner_guardrail":
                    corner_guardrails[(node.id, item.side)] = item
                    break

    bounds = [node.position for node in network.nodes.values()]
    for edge in network.edges:
        bounds.extend(item.point for item in paths[edge.id].sample_interval(max_segment=2.0))
    from road_generator.core.subway import subway_context_bounds
    bounds.extend(subway_context_bounds(network))
    xs, ys = [p[0] for p in bounds], [p[1] for p in bounds]
    cube("Surrounding terrain", ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, -0.17),
         (max(xs) - min(xs) + 24, max(ys) - min(ys) + 24, 0.25), ground)
    profile("SETUP")

    crossing_centers_by_edge = {edge.id: [] for edge in network.edges}
    general_street_lights = []
    rendered_back_planting_ids = set()
    for node in network.nodes.values():
        if node.kind not in JUNCTION_KINDS:
            continue
        node_arms = junction_arms(network, node.id, paths)
        for arm in node_arms:
            if (node.kind == "priority_t_junction"
                    and (arm.edge_id, node.id) not in stop_controlled_approaches):
                continue
            crossing_centers_by_edge[arm.edge_id].append(point_from_node(
                node.position, arm, _arm_crosswalk_distance(arm, node_arms)))

    # UI-authored roads insert a straight approach edge before a junction.
    # A crosswalk can lie farther from the junction than that approach edge,
    # so roadside features on the preceding edge must also observe it. Walk
    # the same logical road through any number of split nodes instead of
    # assuming that only the edge directly attached to the junction matters.
    road_adjacency = {}
    for candidate in network.edges:
        road_adjacency.setdefault((candidate.road_id, candidate.start), []).append(candidate)
        road_adjacency.setdefault((candidate.road_id, candidate.end), []).append(candidate)

    # A GUI road can be split at curve anchors, approaches and junctions.
    # Assign every edge a coordinate in one road-wide station frame so no
    # repeating feature restarts merely because an internal edge begins.
    street_frames = street_stations(network, paths)
    dash_phase_by_edge = {key: frame.offset*frame.direction + (3.0 if frame.direction<0 else 0.0)
                          for key,frame in street_frames.items()}

    def point_on_road_from_node(first_edge, node_id, distance, lateral_from_outward):
        """Follow one logical road across editor-created split edges."""
        current_edge, current_node = first_edge, node_id
        remaining = distance
        visited = set()
        while True:
            if current_edge.id in visited:
                break
            visited.add(current_edge.id)
            path = paths[current_edge.id]
            forward = current_edge.start == current_node
            if remaining <= path.length + 1e-7:
                station = remaining if forward else path.length - remaining
                tangent = path.tangent_at_distance(station)
                outward = tangent if forward else (-tangent[0], -tangent[1])
                path_lateral = (lateral_from_outward if forward
                                else -lateral_from_outward)
                return path.offset_point(station, path_lateral), outward
            remaining -= path.length
            next_node = (current_edge.end if forward else current_edge.start)
            if network.nodes[next_node].kind in JUNCTION_KINDS:
                break
            candidates = [candidate for candidate in road_adjacency.get(
                (current_edge.road_id, next_node), ())
                          if candidate.id not in visited]
            if len(candidates) != 1:
                break
            current_edge, current_node = candidates[0], next_node
        raise ValueError(
            f"Road {first_edge.road_id!r} needs {distance:.1f} m from "
            f"junction {node_id!r} for a crosswalk diamond")

    def nearest_road_junction(edge, endpoint):
        queue = [(0.0, endpoint, edge.id)]
        best = {}
        while queue:
            distance_to_node, node_id, incoming_edge_id = heapq.heappop(queue)
            if distance_to_node >= best.get(node_id, float("inf")):
                continue
            best[node_id] = distance_to_node
            node = network.nodes[node_id]
            if node.kind in JUNCTION_KINDS:
                arms = junction_arms(network, node_id, paths)
                arm = next((item for item in arms
                            if item.edge_id == incoming_edge_id), None)
                if arm is not None:
                    return distance_to_node, arm, arms
            for candidate in road_adjacency.get((edge.road_id, node_id), ()):
                if candidate.id == incoming_edge_id:
                    continue
                other = candidate.end if candidate.start == node_id else candidate.start
                heapq.heappush(
                    queue, (distance_to_node + paths[candidate.id].length,
                            other, candidate.id))
        return None

    def feature_interval(edge, path, clearance):
        def endpoint_trim(node_id):
            nearest = nearest_road_junction(edge, node_id)
            if nearest is None:
                return 0.0
            distance_to_junction, arm, arms = nearest
            node = network.nodes[arm.node_id]
            same_road_arms = [candidate for candidate in arms
                              if candidate.road_id == arm.road_id]
            if (node.kind == "priority_t_junction" and arm.road_id
                    and len(same_road_arms) == 2):
                required = _arm_trim(arm, arms) - distance_to_junction
            else:
                required = (_arm_crosswalk_distance(arm, arms) + 1.60
                            + clearance - distance_to_junction)
            return max(0.0, required)
        return endpoint_trim(edge.start), path.length - endpoint_trim(edge.end)

    driveway_by_edge_side = {}
    def driveway_continuation(edge, node_id):
        if network.nodes[node_id].kind in JUNCTION_KINDS:
            return None
        candidates = [candidate for candidate in
                      road_adjacency.get((edge.road_id, node_id), ())
                      if candidate.id != edge.id]
        return candidates[0] if len(candidates) == 1 else None

    def add_driveway_entry(component, edge, side_name, station):
        key = (edge.id, side_name)
        existing = driveway_by_edge_side.setdefault(key, [])
        if any(abs(station - other_station)
               < DRIVEWAY_CUTOUT_HALF_EXTENT_M * 2.0 - 1e-6
               and other.id != component.id
               for other, other_station in existing):
            raise ValueError(
                f"Component {component.id!r} overlaps another driveway cutout")
        if not any(other.id == component.id for other, _station in existing):
            existing.append((component, station))

    for component in network.components:
        edge = next(item for item in network.edges
                    if item.id == component.edge_id)
        base_path = paths[edge.id]
        path = (_ApproachOffsetPath(base_path, edge)
                if any(has_extra_inbound_section(edge, endpoint)
                       for endpoint in ("from", "to")) else base_path)
        safe_start, safe_end = feature_interval(edge, path, 10.0)
        start_continuation = driveway_continuation(edge, edge.start)
        end_continuation = driveway_continuation(edge, edge.end)
        start_ok = (component.station
                    >= safe_start + DRIVEWAY_CUTOUT_HALF_EXTENT_M
                    or (safe_start <= 1e-6 and start_continuation is not None
                        and component.station >= 0.0))
        end_ok = (component.station
                  <= safe_end - DRIVEWAY_CUTOUT_HALF_EXTENT_M
                  or (safe_end >= path.length - 1e-6
                      and end_continuation is not None
                      and component.station <= path.length))
        if not (start_ok and end_ok):
            raise ValueError(
                f"Component {component.id!r} is too close to an intersection "
                "or road endpoint")
        add_driveway_entry(component, edge, component.side, component.station)
        for endpoint, continuation, distance_to_node in (
                ("start", start_continuation, component.station),
                ("end", end_continuation, path.length - component.station)):
            if (continuation is None
                    or distance_to_node >= DRIVEWAY_CUTOUT_HALF_EXTENT_M):
                continue
            continuation_path = paths[continuation.id]
            virtual_station = (-distance_to_node
                               if continuation.start == getattr(edge, endpoint)
                               else continuation_path.length + distance_to_node)
            base_tangent = path.tangent_at_distance(
                0.0 if endpoint == "start" else path.length)
            neighbor_tangent = continuation_path.tangent_at_distance(
                0.0 if continuation.start == getattr(edge, endpoint)
                else continuation_path.length)
            same_direction = (base_tangent[0] * neighbor_tangent[0]
                              + base_tangent[1] * neighbor_tangent[1]) >= 0.0
            virtual_side = (component.side if same_direction else
                            ("right" if component.side == "left" else "left"))
            add_driveway_entry(component, continuation, virtual_side,
                                virtual_station)
    for entries in driveway_by_edge_side.values():
        entries.sort(key=lambda item: item[1])

    driveway_fixture_clearances = []
    for (edge_id, side_name), entries in driveway_by_edge_side.items():
        edge = next(item for item in network.edges if item.id == edge_id)
        base_path = paths[edge.id]
        path = (_ApproachOffsetPath(base_path, edge)
                if any(has_extra_inbound_section(edge, endpoint)
                       for endpoint in ("from", "to")) else base_path)
        side = 1 if side_name == "left" else -1
        lateral = side * (road_half_width_m(edge)
                          + STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M)
        for component, station in entries:
            driveway_fixture_clearances.append((
                component.id, edge_id, side_name,
                path.offset_point(station, lateral),
                DRIVEWAY_CUTOUT_HALF_EXTENT_M + 1.5))

    def point_clear_of_driveways(point):
        return all((point[0] - center[0]) ** 2 + (point[1] - center[1]) ** 2
                   >= clearance ** 2
                   for _id, _edge_id, _side, center, clearance
                   in driveway_fixture_clearances)

    def driveway_stations(edge_id, side):
        side_name = "left" if side > 0 else "right"
        return tuple(station for _component, station
                     in driveway_by_edge_side.get((edge_id, side_name), ()))

    def interval_hits_driveway(edge_id, side, interval_start, interval_end,
                               clearance=0.0):
        return any(
            interval_start < station + DRIVEWAY_CUTOUT_HALF_EXTENT_M + clearance
            and interval_end > station - DRIVEWAY_CUTOUT_HALF_EXTENT_M - clearance
            for station in driveway_stations(edge_id, side))

    def intervals_clear_of_driveways(edge_id, side, interval_start,
                                     interval_end, clearance=0.0):
        intervals = [(interval_start, interval_end)]
        for station in driveway_stations(edge_id, side):
            cut_start = station - DRIVEWAY_CUTOUT_HALF_EXTENT_M - clearance
            cut_end = station + DRIVEWAY_CUTOUT_HALF_EXTENT_M + clearance
            next_intervals = []
            for start, end in intervals:
                if cut_end <= start or cut_start >= end:
                    next_intervals.append((start, end))
                    continue
                if cut_start > start + 1e-6:
                    next_intervals.append((start, cut_start))
                if cut_end < end - 1e-6:
                    next_intervals.append((cut_end, end))
            intervals = next_intervals
        return tuple(interval for interval in intervals
                     if interval[1] - interval[0] > 0.5)

    for edge in network.edges:
        base_path = paths[edge.id]
        has_extra_lane = any(has_extra_inbound_section(edge, endpoint)
                             for endpoint in ("from", "to"))
        path = (_ApproachOffsetPath(base_path, edge)
                if has_extra_lane else base_path)
        road_half = road_half_width_m(edge)
        _mesh_strip(f"{edge.id} asphalt", path.sample_interval(max_segment=0.8),
                    (lambda station: road_half + approach_outward_shift_m(
                        edge, station, path.length)),
                    (lambda station: -road_half - approach_outward_shift_m(
                        edge, station, path.length)),
                    0.0, asphalt, 0.08)
        start, end = _trim_interval(network, edge, path)

        def marking_trim(node_id):
            if network.nodes[node_id].kind not in JUNCTION_KINDS:
                return 0.0
            node = network.nodes[node_id]
            if node.kind == "priority_t_junction":
                same_road_arms = [candidate for candidate in network.edges
                                  if node_id in {candidate.start, candidate.end}
                                  and candidate.road_id == edge.road_id]
                if edge.road_id and len(same_road_arms) == 2:
                    return 0.0
            arms = junction_arms(network, node_id, paths)
            arm = next(item for item in arms if item.edge_id == edge.id)
            return _arm_crosswalk_distance(arm, arms) + 3.6

        marking_start = marking_trim(edge.start)
        marking_end = path.length - marking_trim(edge.end)

        def endpoint_stop_line_distance(endpoint):
            nearest = nearest_road_junction(edge, endpoint)
            if nearest is None:
                return None
            distance_to_junction, arm, arms = nearest
            node = network.nodes[arm.node_id]
            if (node.kind == "priority_t_junction"
                    and (arm.edge_id, node.id)
                    not in stop_controlled_approaches):
                return None
            stop_line_from_junction = _arm_crosswalk_distance(arm, arms) + 3.6
            return distance_to_junction - stop_line_from_junction

        start_stop_line_distance = endpoint_stop_line_distance(edge.start)
        end_stop_line_distance = endpoint_stop_line_distance(edge.end)

        guard_start, guard_end = feature_interval(edge, path, 0.55)
        # Soil, shrubs and guardrails share one authoritative longitudinal
        # roadside envelope. Asset-internal foliage placement handles leaf
        # clearance without shortening the visible soil bed.
        planting_start, planting_end = feature_interval(edge, path, 0.55)
        curb_rows = {}
        is_line = edge.geometry is None or edge.geometry.kind == "line"
        sidewalk_width = _sidewalk_width_for_edge(edge)
        sidewalk_footprint = _sidewalk_footprint_for_edge(edge)
        if (edge.sidewalks == "both" and is_line and not has_extra_lane
                and not edge.median):
            straight_curb_rows = []
            _sidewalk_pair(
                edge.id, path.point_at_distance(start), path.point_at_distance(end),
                road_half * 2, sidewalk_width, sidewalk, curb,
                plantings_by_edge.get(edge.id), curb_rows=straight_curb_rows,
                crosswalks=compatibility_crosswalks,
                crossing_centers=crossing_centers_by_edge[edge.id],
                brick_materials=sidewalk_bricks,
                driveways_by_side={
                    "left": driveway_stations(edge.id, 1),
                    "right": driveway_stations(edge.id, -1),
                },
            )
            curb_rows = dict(zip((-1, 1), straight_curb_rows))
        elif edge.sidewalks == "both":
            for side in (-1, 1):
                inner = side * (road_half + 0.14)
                # Match the straight branch's nominal width plus its 0.2m
                # property-side corner allowance.  Median roads extend only
                # this outer edge; the inner edge and all equipment stay tied
                # to the unchanged carriageway datum.
                widened_outer = road_half + sidewalk_footprint
                side_name = "left" if side > 0 else "right"
                planting = (plantings_by_edge.get(edge.id) or {}).get(side_name)
                outer = side * widened_outer
                full_band = (min(inner, outer), max(inner, outer))
                segment_specs = [(start, end, (full_band,))]
                if planting is not None:
                    # PlantingPlan is expressed in the unmodified road frame.
                    # Keep the band coordinates in that frame too; the taper
                    # path applies the outward shift exactly once when meshes
                    # are emitted.  Mapping through ``path`` here would bake
                    # the shift into the band and then apply it a second time,
                    # leaving a visible empty strip beside the soil bed.
                    mapped, station = _map_chord_point_to_path(
                        network, edge, base_path, planting.start)
                    centre = base_path.point_at_distance(station)
                    tangent = base_path.tangent_at_distance(station)
                    normal = (-tangent[1], tangent[0])
                    bed_lateral = ((mapped[0] - centre[0]) * normal[0]
                                   + (mapped[1] - centre[1]) * normal[1])
                    bed_min = bed_lateral - planting.width * 0.5
                    bed_max = bed_lateral + planting.width * 0.5
                    walk_min, walk_max = full_band
                    planting_bands = (
                        (walk_min, min(walk_max, bed_min)),
                        (max(walk_min, bed_max), walk_max),
                    )
                    bed_start = max(start, planting_start)
                    bed_end = min(end, planting_end)
                    segment_specs = [
                        (start, bed_start, (full_band,)),
                        (bed_start, bed_end, planting_bands),
                        (bed_end, end, (full_band,)),
                    ]
                for segment_index, (segment_start, segment_end, bands) in enumerate(segment_specs):
                    if segment_end - segment_start <= 1e-6:
                        continue
                    for band_index, (band_min, band_max) in enumerate(bands):
                        if band_max - band_min <= 1e-6:
                            continue
                        rendered_bands = ((band_min, band_max, False),)
                        if edge.median:
                            standard_edge = side * (
                                road_half + SIDEWALK_CORNER_RADIUS_M)
                            base_min, base_max = sorted((inner, standard_edge))
                            extension_min, extension_max = sorted((standard_edge, outer))
                            rendered_bands = tuple(item for item in (
                                (max(band_min, base_min),
                                 min(band_max, base_max), False),
                                (max(band_min, extension_min),
                                 min(band_max, extension_max), True),
                            ) if item[1] - item[0] > 1e-6)
                        for split_index, (split_min, split_max,
                                          is_extension) in enumerate(rendered_bands):
                            split_start, split_end = segment_start, segment_end
                            cutout_polygons = ()
                            if edge.median:
                                cutout_polygons = tuple(filter(None, (
                                    _sidewalk_extension_cutout(
                                        network, edge, "start", side, paths),
                                    _sidewalk_extension_cutout(
                                        network, edge, "end", side, paths),
                                )))
                            if split_end - split_start <= 1e-6:
                                continue
                            label = (f"{edge.id} {side_name} sidewalk "
                                     f"{segment_index}-{band_index}-{split_index}")
                            _mesh_strip(
                                label,
                                path.sample_interval(split_start, split_end, 0.8),
                                (lambda station, value=split_max:
                                 approach_existing_lateral_m(
                                     edge, station, path.length, value)),
                                (lambda station, value=split_min:
                                 approach_existing_lateral_m(
                                     edge, station, path.length, value)),
                                SIDEWALK_TOP_Z_M - (0.012 if sidewalk_bricks else 0.0),
                                sidewalk, 0.18, cutout_polygons=cutout_polygons)
                            _sidewalk_brick_path_band(
                                label + " brick paving", path,
                                split_start, split_end, split_min, split_max,
                                sidewalk_bricks,
                                cutout_polygons=cutout_polygons,
                                street_frame=street_frames[edge.id])
                if planting is not None:
                    for driveway_index, station in enumerate(
                            driveway_stations(edge.id, side)):
                        fill_start = max(bed_start,
                                         station - DRIVEWAY_CUTOUT_HALF_EXTENT_M)
                        fill_end = min(bed_end,
                                       station + DRIVEWAY_CUTOUT_HALF_EXTENT_M)
                        if fill_end - fill_start <= 1e-6:
                            continue
                        label = (f"{edge.id} {side_name} driveway fill "
                                 f"{driveway_index}")
                        _mesh_strip(
                            label, path.sample_interval(fill_start, fill_end, 0.8),
                            (lambda sample, value=bed_max:
                             approach_existing_lateral_m(
                                 edge, sample, path.length, value)),
                            (lambda sample, value=bed_min:
                             approach_existing_lateral_m(
                                 edge, sample, path.length, value)),
                            SIDEWALK_TOP_Z_M - (
                                0.012 if sidewalk_bricks else 0.0),
                            sidewalk, 0.18)
                        _sidewalk_brick_path_band(
                            label + " brick paving", path, fill_start, fill_end,
                            bed_min, bed_max, sidewalk_bricks, street_frame=street_frames[edge.id])
                if edge.median:
                    for endpoint in ("start", "end"):
                        connectors = _sidewalk_extension_connector(
                            network, edge, endpoint, side, paths)
                        for connector_index, connector in enumerate(connectors or ()):
                            connector_name = (
                                f"{edge.id} {side_name} {endpoint} wide sidewalk "
                                f"connector {connector_index}")
                            _polygon(
                                connector_name, connector,
                                SIDEWALK_TOP_Z_M - (
                                    0.012 if sidewalk_bricks else 0.0),
                                sidewalk)
                            _sidewalk_brick_polygon(
                                connector_name + " brick paving", connector,
                                sidewalk_bricks)
                curb_name = f"{edge.id} {'left' if side > 0 else 'right'} curb"
                lateral = side * (road_half + CURB_WIDTH_M * 0.5)
                lowered_crossings = tuple(
                    path.project_point(center)[0]
                    for center in crossing_centers_by_edge[edge.id])
                lowered_driveways = driveway_stations(edge.id, side)
                curb_rows[side] = _curb_blocks_along_path(curb_name, path, start, end,
                                        lateral, curb,
                                        lowered_crossing_distances=lowered_crossings,
                                        lowered_driveway_distances=lowered_driveways,
                                        logical_offset=street_frames[edge.id].offset*street_frames[edge.id].direction)
        center_mat = orange if edge.center_marking == "orange_solid" else white
        dash_phase = dash_phase_by_edge.get(edge.id, 0.0)
        if not edge.median and edge.center_marking != "none":
            intervals = (_dash_intervals(
                marking_start, marking_end, 3.0, 3.0, dash_phase)
                if edge.center_marking == "white_dashed"
                else ((marking_start, marking_end),))
            for index, (a, b) in enumerate(intervals):
                if b <= a + 0.05:
                    continue
                samples = path.sample_interval(a, b, 0.8)
                _mesh_strip(f"{edge.id} center marking {index}",
                            samples,
                            lambda station: approach_center_marking_lateral_m(
                                edge, station, path.length) + 0.075,
                            lambda station: approach_center_marking_lateral_m(
                                edge, station, path.length) - 0.075,
                            (ORANGE_PAINT_CENTER_Z_M
                             if edge.center_marking == "orange_solid"
                             else ROAD_PAINT_CENTER_Z_M), center_mat)

        for lane in range(1, edge.lanes_each_way):
            for side in (-1, 1):
                offset = carriageway_lateral_m(edge, side * lane * LANE_WIDTH_M)
                solid = lane_separator_solid_interval(
                    0.0, path.length, side,
                    start_stop_line_distance, end_stop_line_distance,
                )
                if solid is not None:
                    solid = (max(marking_start, solid[0]),
                             min(marking_end, solid[1]))
                    if solid[1] <= solid[0] + 0.05:
                        solid = None
                for index, (a, b) in enumerate(
                        _dash_intervals(marking_start, marking_end,
                                        phase=dash_phase)):
                    if solid is not None:
                        # Preserve the established station-based dash phase on
                        # the portion outside the solid approach interval.
                        if b <= solid[0] or a >= solid[1]:
                            pass
                        elif a < solid[0]:
                            b = solid[0]
                        elif b > solid[1]:
                            a = solid[1]
                        else:
                            continue
                    if b <= a + 0.05:
                        continue
                    samples = _sample_offset_interval(path, a, b, offset)
                    _mesh_strip(f"{edge.id} lane {side} {lane} {index}", samples,
                                0.06, -0.06, ROAD_PAINT_CENTER_Z_M, white)
                if solid is not None and solid[1] > solid[0] + 0.05:
                    samples = _sample_offset_interval(
                        path, solid[0], solid[1], offset)
                    _mesh_strip(
                        f"{edge.id} lane {side} {lane} solid approach",
                        samples, 0.06, -0.06,
                        ROAD_PAINT_CENTER_Z_M, white,
                    )
        for endpoint, side in (("from", -1), ("to", 1)):
            if not has_extra_inbound_lane(edge, endpoint):
                continue
            linked = (path.length < EXTRA_INBOUND_LANE_LINK_M
                      and has_extra_inbound_section(edge, "from")
                      and has_extra_inbound_section(edge, "to"))
            if linked:
                midpoint = path.length * 0.5
                # The centre divider changes side within its 20m transition,
                # but both directions still need their added-lane separator
                # up to the hand-off point.  Ending at the transition edges
                # leaves a conspicuous 20m-plus unmarked gap on a 140m link.
                interval = ((marking_start, midpoint)
                            if endpoint == "from" else
                            (midpoint, marking_end))
            else:
                interval = ((marking_start, min(path.length, 50.0))
                            if endpoint == "from" else
                            (max(0.0, path.length - 50.0), marking_end))
            if interval[1] <= interval[0] + 0.05:
                continue
            solid = ((interval[0], min(interval[1], interval[0] + 15.0))
                     if endpoint == "from" else
                     (max(interval[0], interval[1] - 15.0), interval[1]))

            def new_boundary(station, side=side):
                # A wide median gives up its inner 3.25 m while its outer edge
                # stays fixed.  The new lane therefore runs straight; only
                # the median edge tapers away.  A narrow median has no such
                # reserve and retains the symmetric road-widening taper.
                factor = extra_lane_factor(edge, station, path.length)
                return side * LANE_WIDTH_M * 0.5 * (
                    1.0 if edge.median_width == "wide" and factor > 1e-9
                    else factor)

            for index, (a, b) in enumerate(_dash_intervals(*interval)):
                if b <= solid[0] or a >= solid[1]:
                    pass
                elif a < solid[0]:
                    b = solid[0]
                elif b > solid[1]:
                    a = solid[1]
                else:
                    continue
                if b > a + 0.05:
                    _mesh_strip(
                        f"{edge.id} {endpoint} added lane divider {index}",
                        path.sample_interval(a, b, 0.8),
                        lambda station: new_boundary(station) + 0.06,
                        lambda station: new_boundary(station) - 0.06,
                        ROAD_PAINT_CENTER_Z_M, white)
            _mesh_strip(
                f"{edge.id} {endpoint} added lane divider solid approach",
                path.sample_interval(*solid, max_segment=0.8),
                lambda station: new_boundary(station) + 0.06,
                lambda station: new_boundary(station) - 0.06,
                ROAD_PAINT_CENTER_Z_M, white)

        for endpoint, stop_station, side, travel_sign in (
                (edge.start, marking_start, -1, -1.0),
                (edge.end, marking_end, 1, 1.0)):
            # Only the edge directly touching the junction owns its arrows.
            # The 10 m enforced straight approach comfortably contains each
            # five-metre asset and keeps it undeformed even before a curve.
            endpoint_key = "from" if endpoint == edge.start else "to"
            extra_here = has_extra_inbound_lane(edge, endpoint_key)
            arrow_kinds = approach_lane_arrow_kinds(
                edge.lanes_each_way + (1 if extra_here else 0))
            node = network.nodes[endpoint]
            if node.kind == "signalized_t_junction":
                node_arms = junction_arms(network, endpoint, paths)
                this_arm = next(item for item in node_arms
                                if item.edge_id == edge.id)
                same_road = [item for item in node_arms
                             if item.road_id == this_arm.road_id]
                if this_arm.road_id and len(same_road) == 2:
                    stem = next(item for item in node_arms
                                if item.road_id != this_arm.road_id)
                    inbound = (-this_arm.outward[0], -this_arm.outward[1])
                    stem_cross = (inbound[0] * stem.outward[1]
                                  - inbound[1] * stem.outward[0])
                    lane_count = edge.lanes_each_way + (1 if extra_here else 0)
                    arrow_kinds = t_junction_lane_arrow_kinds(
                        lane_count,
                        "right" if stem_cross < 0.0 else "left",
                        dedicated_right_lane=extra_here,
                    )
                else:
                    # The stem has no straight continuation. Split its lanes
                    # into left-only and right-only groups; for an odd count
                    # the centre lane belongs to the left-turn group.
                    lane_count = edge.lanes_each_way
                    arrow_kinds = t_junction_lane_arrow_kinds(
                        lane_count, "stem")
            elif node.kind == "signalized_cross":
                node_arms = junction_arms(network, endpoint, paths)
                has_single_lane_road = any(
                    next(candidate for candidate in network.edges
                         if candidate.id == item.edge_id).lanes_each_way == 1
                    for item in node_arms)
                arrow_kinds = cross_lane_arrow_kinds(
                    edge.lanes_each_way + (1 if extra_here else 0),
                    has_single_lane_road,
                )
            if marking_trim(endpoint) <= 1e-6 or not arrow_kinds:
                continue
            tip_station = stop_station - travel_sign * 2.0
            if not 0.0 <= tip_station <= path.length:
                continue
            tangent = path.tangent_at_distance(tip_station)
            travel = mul(tangent, travel_sign)
            rotation = math.degrees(math.atan2(travel[1], travel[0])) - 90.0
            for lane_index, kind in enumerate(arrow_kinds):
                if extra_here:
                    lateral = side * (
                        edge.lanes_each_way - lane_index) * LANE_WIDTH_M
                else:
                    lateral = carriageway_lateral_m(edge, side * (
                        edge.lanes_each_way - lane_index - 0.5) * LANE_WIDTH_M)
                    if has_extra_inbound_reserve(edge, endpoint_key):
                        lateral = approach_existing_lateral_m(
                            edge, tip_station, path.length, lateral)
                # ``lateral`` is already the final lane-centre coordinate.
                # The approach facade is for existing roadside objects and
                # would apply the narrow-median outward shift a second time.
                location = base_path.offset_point(tip_station, lateral)
                lane_use_arrow_instance(
                    f"{edge.id} {endpoint} lane {lane_index + 1} {kind} arrow",
                    (*location, 0.0), rotation, kind, white,
                )
        if edge.curb_parking_prohibition and edge.sidewalks == "both":
            for side in (-1, 1):
                _curb_paint_on_blocks(
                    f"{edge.id} parking curb {side}", curb_rows.get(side), path,
                    max(start, guard_start), min(end, guard_end), orange,
                    logical_offset=street_frames[edge.id].offset * street_frames[edge.id].direction,
                    logical_direction=street_frames[edge.id].direction,
                )
        if edge.tactile_paving and edge.sidewalks == "both":
            for side in (-1, 1):
                # The extra 0.20m in the curved sidewalk mesh is the mature
                # outer footprint/corner allowance, not usable sidewalk width.
                # Guidance blocks retain their established station 0.60m in
                # from the nominal 3.60m sidewalk edge.
                offset = side * (road_half + SIDEWALK_WIDTH_M - 0.6)
                _tactile_tiles_along_path(
                    tactile_plans, f"{edge.id} tactile route {side}", path,
                    start, end, offset, "guidance",
                    route_key=f"{edge.road_id or edge.id}:{side}")

        # General-angle features use the same arm-aware intervals as the
        # junction renderer.  The mature planner classifies an edge as merely
        # horizontal/vertical, which trims the wrong end of oblique approach
        # edges and can put roadside assets through a crosswalk.
        if edge.guardrail is not None and edge.guardrail.sides != 'none' and guard_end - guard_start > 0.5:
            sides = (-1, 1) if edge.guardrail.sides == "both" else \
                ((1,) if edge.guardrail.sides == "left" else (-1,))
            for side in sides:
                lateral = side * (road_half + 0.22)
                clear_runs = intervals_clear_of_driveways(
                    edge.id, side, guard_start, guard_end, clearance=0.15)
                from .direct_assets import guardrail_path_instance
                for run_index,(run_start,run_end) in enumerate(clear_runs):
                    guardrail_path_instance(
                        f'{edge.id} {side} continuous fence {run_index}',
                        path,run_start,run_end,lateral,edge.guardrail.exterior_color,
                        'right' if side>0 else 'left',
                        GUARDRAIL_BASE_Z_M if edge.sidewalks=='both' else ROAD_TOP_Z_M,
                        street_frames[edge.id],
                        (run_start>.01 or network.nodes[edge.start].kind in JUNCTION_KINDS or len(road_adjacency[(edge.road_id,edge.start)])!=2,
                         run_end<path.length-.01 or network.nodes[edge.end].kind in JUNCTION_KINDS or len(road_adjacency[(edge.road_id,edge.end)])!=2))
        if edge.planting is not None and planting_end - planting_start > 0.5:
            planting_width = 0.85
            for side in (-1, 1):
                lateral = side * (road_half + 0.33 + planting_width * 0.5)
                seed = seed_for(street_frames[edge.id].identity,side*street_frames[edge.id].direction,edge.planting.seed or 0)
                clear_runs = intervals_clear_of_driveways(
                    edge.id, side, planting_start, planting_end, clearance=0.45)
                module_serial = 0
                for run_start, run_end in clear_runs:
                    for a,b,module_index in street_frames[edge.id].spans(run_start,run_end,5.0):
                        module_serial += 1
                        planting_instance(
                            f"{edge.id} {'left' if side > 0 else 'right'} planting module {module_serial:02d}",
                            path.offset_point(a, lateral), path.offset_point(b, lateral),
                            planting_width, edge.planting.density,
                            edge.planting.maintenance, edge.planting.health,
                            seed_for(seed,module_index), PLANTING_INSTANCE_Z_M,
                            style=edge.planting.style,
                        )
        if edge.street_lights:
            lit = network.scene.time_of_day == "night"

            def priority_through_endpoint(node_id):
                node = network.nodes[node_id]
                if node.kind != "priority_t_junction" or not edge.road_id:
                    return False
                return sum(
                    candidate.road_id == edge.road_id
                    for candidate in network.edges
                    if node_id in {candidate.start, candidate.end}
                ) == 2

            light_start, light_end = guard_start, guard_end
            pedestrian_light_start, pedestrian_light_end = feature_interval(
                edge, path,
                PEDESTRIAN_STREET_LIGHT_CROSSWALK_CLEARANCE_M)
            if priority_through_endpoint(edge.start):
                light_start = 0.0
                pedestrian_light_start = 0.0
            if priority_through_endpoint(edge.end):
                light_end = path.length
                pedestrian_light_end = path.length
            def stations(interval_start, interval_end, spacing, fill_to_ends=False):
                return tuple(s for s,index in street_frames[edge.id].positions(
                    interval_start,interval_end,spacing))

            if edge.median:
                for index, station in enumerate(stations(
                        light_start, light_end,
                        ROADWAY_STREET_LIGHT_SPACING_M), 1):
                    tangent = path.tangent_at_distance(station)
                    heading = math.degrees(math.atan2(tangent[1], tangent[0]))
                    median_lateral, _median_width = approach_median_section(
                        edge, station, path.length)
                    location = (*base_path.offset_point(
                        station, median_lateral), 0.24)
                    general_street_lights.append((
                        f"{edge.id}_roadway_street_light_{index:02d}",
                        edge.id, "center", "roadway", location,
                        heading + 90.0, lit,
                    ))
            if edge.sidewalks == "both":
                planting_width = 0.85
                for side in (-1, 1):
                    side_name = "left" if side > 0 else "right"
                    lateral = side * (road_half + 0.33 + planting_width * 0.5)
                    for index, station in enumerate(stations(
                            pedestrian_light_start,
                            pedestrian_light_end,
                            PEDESTRIAN_STREET_LIGHT_SPACING_M,
                            fill_to_ends=True), 1):
                        if interval_hits_driveway(
                                edge.id, side, station, station, clearance=0.75):
                            continue
                        tangent = path.tangent_at_distance(station)
                        heading = math.degrees(math.atan2(tangent[1], tangent[0]))
                        base_z = (PLANTING_INSTANCE_Z_M + 0.06
                                  if edge.planting is not None
                                  else SIDEWALK_TOP_Z_M)
                        location = (*path.offset_point(station, lateral), base_z)
                        general_street_lights.append((
                            f"{edge.id}_{side_name}_pedestrian_street_light_{index:02d}",
                            edge.id, side_name, "pedestrian", location,
                            heading, lit,
                        ))

    general_street_lights = _deduplicate_pedestrian_street_lights(
        general_street_lights)
    roadside_sign_points = []

    # Hydrant signs are planned once per authored road rather than once per
    # split edge.  This keeps GUI-created junction approach edges from
    # multiplying what is semantically one roadside facility.
    hydrant_roads = {}
    for edge in network.edges:
        if edge.sidewalks == "both":
            hydrant_roads.setdefault(edge.road_id or edge.id, []).append(edge)
    for road_id, road_edges in sorted(hydrant_roads.items()):
        full_length = sum(paths[edge.id].length for edge in road_edges)
        if full_length < 40.0:
            continue
        spans = []
        available_total = 0.0
        for edge in road_edges:
            base_path = paths[edge.id]
            path = (_ApproachOffsetPath(base_path, edge)
                    if any(has_extra_inbound_section(edge, endpoint)
                           for endpoint in ("from", "to")) else base_path)
            start, end = feature_interval(edge, path, 10.0)
            if network.nodes[edge.start].kind == "boundary":
                start = max(start, 5.0)
            if network.nodes[edge.end].kind == "boundary":
                end = min(end, path.length - 5.0)
            if end - start < 1.0:
                continue
            spans.append((available_total, available_total + end - start,
                          edge, path, start, end))
            available_total += end - start
        if available_total < 1.0:
            continue
        count = 1 if full_length < 180.0 else math.ceil(full_length / 140.0)
        count = min(count, max(1, int(available_total // 20.0)))
        rng = random.Random(zlib.crc32(
            f"{road_id}:fire_hydrants".encode("utf-8")) & 0x7FFFFFFF)
        cell = available_total / count
        targets = []
        for index in range(count):
            center = (index + 0.5) * cell
            jitter = rng.uniform(-min(20.0, cell * 0.20),
                                 min(20.0, cell * 0.20))
            targets.append(max(index * cell + 0.5,
                               min((index + 1) * cell - 0.5,
                                   center + jitter)))
        for index, target in enumerate(targets, 1):
            cumulative_start, _cumulative_end, edge, path, start, end = next(
                span for span in spans if span[0] - 1e-6 <= target <= span[1] + 1e-6)
            station = start + target - cumulative_start
            side = rng.choice((-1, 1))
            if interval_hits_driveway(
                    edge.id, side, station, station, clearance=1.5):
                alternate = -side
                if interval_hits_driveway(
                        edge.id, alternate, station, station, clearance=1.5):
                    continue
                side = alternate
            lateral = side * (road_half_width_m(edge)
                              + STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M)
            point = path.offset_point(station, lateral)
            tangent = path.tangent_at_distance(station)
            heading = math.degrees(math.atan2(tangent[1], tangent[0]))
            # The sign face normal is local Y and the frame extends from its
            # post along local -X.  Select the quarter turn from the sidewalk
            # side, so the double-sided face remains parallel to the road while
            # the frame always projects from the post toward the carriageway.
            rotation = heading + side * 90.0
            # Put the underground cover in the clear pedestrian band beyond
            # the optional 0.85 m planting strip. Trees and light poles occupy
            # that separate planting band, so an equal road station is not a
            # ground-level collision and needs no longitudinal avoidance.
            cover_deltas = [-4.5, -3.5, -2.5, -1.5, 1.5, 2.5, 3.5, 4.5]
            rng.shuffle(cover_deltas)
            cover_lateral = side * (road_half_width_m(edge) + 1.60)
            valid_deltas = [delta for delta in cover_deltas
                            if start <= station + delta <= end
                            and not interval_hits_driveway(
                                edge.id, side, station + delta,
                                station + delta, clearance=0.75)]
            if not valid_deltas:
                continue
            instance = cached_asset_instance(
                ("fire_hydrant_sign",),
                lambda: create_fire_hydrant_sign("Fire Hydrant Sign Prototype"),
                f"{road_id} fire hydrant sign {index:02d}",
                (*point, SIDEWALK_TOP_Z_M), rotation,
            )
            cover_delta = valid_deltas[0]
            hydrant_station = max(start, min(end, station + cover_delta))
            hydrant_point = path.offset_point(hydrant_station, cover_lateral)
            cover_instance = cached_asset_instance(
                ("fire_hydrant_cover",),
                lambda: create_fire_hydrant_cover("Fire Hydrant Cover Prototype"),
                f"{road_id} fire hydrant cover {index:02d}",
                (*hydrant_point, SIDEWALK_TOP_Z_M + 0.002), heading,
            )
            cover_instance["road_id"] = road_id
            cover_instance["edge_id"] = edge.id
            cover_instance["paired_sign"] = instance.name
            cover_instance["sign_distance_m"] = abs(hydrant_station - station)
            cover_instance["road_edge_offset_m"] = 1.60
            instance["road_id"] = road_id
            instance["edge_id"] = edge.id
            instance["hydrant_site"] = (*hydrant_point,
                                         SIDEWALK_TOP_Z_M + 0.002)
            instance["paired_cover"] = cover_instance.name
            instance["hydrant_distance_m"] = abs(hydrant_station - station)
            roadside_sign_points.append(point)

    # A curb-painted logical span between two junctions receives exactly one
    # parking prohibition sign when its centreline is at least 50 m long. GUI
    # roads can contain synthetic boundary nodes around approach tapers, so
    # follow same-road edges through those nodes instead of testing one edge.
    fixture_points = [item[4] for item in general_street_lights]
    fixture_points.extend(item.location for item in planned_trees)
    fixture_points.extend(roadside_sign_points)
    clearance_sq = 3.0 ** 2
    parking_spans = []
    visited_parking_chains = set()
    for first_edge in network.edges:
        if not first_edge.curb_parking_prohibition:
            continue
        for first_node in (first_edge.start, first_edge.end):
            if network.nodes[first_node].kind not in JUNCTION_KINDS:
                continue
            chain = []
            chain_edge_ids = set()
            edge = first_edge
            from_node = first_node
            while True:
                if edge.id in chain_edge_ids:
                    chain = []
                    break
                chain_edge_ids.add(edge.id)
                chain.append((edge, from_node))
                next_node = edge.end if edge.start == from_node else edge.start
                if network.nodes[next_node].kind in JUNCTION_KINDS:
                    break
                if not edge.road_id:
                    chain = []
                    break
                continuations = [candidate for candidate in road_adjacency.get(
                    (edge.road_id, next_node), ())
                    if candidate.id != edge.id
                    and candidate.curb_parking_prohibition]
                if len(continuations) != 1:
                    chain = []
                    break
                edge, from_node = continuations[0], next_node
            if not chain or next_node == first_node:
                continue
            chain_key = frozenset(item.id for item, _node in chain)
            if chain_key in visited_parking_chains:
                continue
            visited_parking_chains.add(chain_key)

            span_length = sum(paths[item.id].length for item, _node in chain)
            parking_spans.append((first_node, next_node, chain, span_length))

    for first_node, last_node, chain, span_length in parking_spans:
        if span_length < 50.0:
            continue
        first_edge = chain[0][0]
        last_edge = chain[-1][0]

        def junction_clearance(node_id, edge_id):
            arms = junction_arms(network, node_id, paths)
            arm = next(item for item in arms if item.edge_id == edge_id)
            return _arm_crosswalk_distance(arm, arms) + 1.60 + 10.0

        start = junction_clearance(first_node, first_edge.id)
        end = span_length - junction_clearance(last_node, last_edge.id)
        if end <= start:
            continue
        for side in (-1, 1):
            side_name = "right" if side < 0 else "left"
            rng = random.Random(zlib.crc32(
                f"{first_edge.road_id or first_edge.id}:{first_node}:{last_node}:"
                f"parking-prohibition-sign:{side_name}".encode("utf-8")
            ) & 0x7FFFFFFF)
            candidates = []
            for _attempt in range(16):
                station = rng.uniform(start, end)
                point, tangent, site_edge, local_station = roadside_site(
                    chain, paths, station, side, STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M)
                candidates.append((point, station, tangent, site_edge, local_station))
            point, station, tangent, site_edge, local_station = next((candidate for candidate in candidates
                                   if all((candidate[0][0] - fixture[0]) ** 2
                                          + (candidate[0][1] - fixture[1]) ** 2
                                          >= clearance_sq
                                          for fixture in fixture_points)
                                   and point_clear_of_driveways(candidate[0])),
                                  candidates[0])
            if not point_clear_of_driveways(point):
                continue
            heading = math.degrees(math.atan2(tangent[1], tangent[0]))
            # The asset front is local -Y. On the left sidewalk traffic runs
            # with the path; on the right it runs against it.
            rotation = heading - side * 90.0
            instance = cached_asset_instance(
                ("road_sign", "駐車禁止"),
                lambda: create_road_sign(
                    "駐車禁止", "Parking Prohibition Prototype"),
                f"{first_edge.road_id or first_edge.id} {first_node}-{last_node} "
                f"{side_name} parking prohibition sign",
                (*point, SIDEWALK_TOP_Z_M), rotation,
            )
            instance["road_id"] = first_edge.road_id or first_edge.id
            instance["edge_ids"] = ",".join(item.id for item, _node in chain)
            instance["junction_from"] = first_node
            instance["junction_to"] = last_node
            instance["road_side"] = side_name
            instance["automatic_from_curb_parking_prohibition"] = True
            instance["junction_span_length_m"] = span_length
            instance["edge_id"] = site_edge.id
            instance["edge_station_m"] = local_station
            instance["road_edge_setback_m"] = STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M
            fixture_points.append(point)

    profile("EDGES")
    # Generic junction surface, corners, crossings and signals.
    for node in network.nodes.values():
        if node.kind not in JUNCTION_KINDS:
            continue
        arms = junction_arms(network, node.id, paths)
        groups = arm_groups(arms)
        center = node.position
        asphalt_points = []
        for index, arm in enumerate(arms):
            nxt = arms[(index + 1) % len(arms)]
            if (nxt.angle - arm.angle) % 360.0 > 150.0:
                continue
            arm_boundary = add(center, mul(arm.left, arm.width * 0.5))
            next_boundary = add(center, mul(nxt.left, -nxt.width * 0.5))
            point = _line_intersection(
                arm_boundary, arm.outward, next_boundary, nxt.outward)
            if point is not None:
                asphalt_points.append(point)
        # This core is exactly the legacy carriageway-width square at 90°;
        # corner pavement objects continuously fill from it to each fillet.
        if len(asphalt_points) < 3:
            for arm in arms:
                trim = _arm_trim(arm, arms)
                asphalt_points.extend((
                    point_from_node(center, arm, trim, -arm.width / 2),
                    point_from_node(center, arm, trim, arm.width / 2),
                ))
        asphalt_points.sort(key=lambda p: math.atan2(p[1] - center[1], p[0] - center[0]))
        _polygon(f"{node.id} general intersection asphalt", asphalt_points, 0.0, asphalt)

        if node.kind in {"stop_cross", "stop_t_junction"}:
            for arm in arms:
                length = LANE_WIDTH_M * 0.25
                marking_center = add(center, mul(arm.outward, length * 0.5))
                obj = cube(
                    f"{node.id} {arm.id} center arm marking",
                    (*marking_center, ROAD_PAINT_CENTER_Z_M),
                    (length, JUNCTION_CENTER_MARKING_WIDTH_M,
                     ROAD_PAINT_THICKNESS_M), white, ROAD_PAINT_BEVEL_M,
                )
                obj.rotation_euler[2] = math.atan2(
                    arm.outward[1], arm.outward[0])

        if node.kind in {"signalized_t_junction", "stop_t_junction",
                         "priority_t_junction"} and len(arms) == 3:
            # The >150 degree arm gap is not an oversized corner: it denotes
            # the missing road. Bridge the two through-road sidewalks across
            # it as one straight/oblique slab derived from the actual arm
            # frames, so this remains valid when the through road rotates.
            open_pair = next(
                ((arm, arms[(index + 1) % len(arms)])
                 for index, arm in enumerate(arms)
                 if (arms[(index + 1) % len(arms)].angle - arm.angle) % 360.0
                 > 150.0), None)
            if open_pair is not None:
                back_a, back_b = open_pair
                open_gap = (back_b.angle - back_a.angle) % 360.0
                missing_angle = math.radians(back_a.angle + open_gap * 0.5)
                missing_direction = (math.cos(missing_angle),
                                     math.sin(missing_angle))

                def back_side_sign(back_arm):
                    # Select the lateral side pointing into the open gap.
                    candidate = back_arm.left
                    return (1.0 if candidate[0] * missing_direction[0]
                            + candidate[1] * missing_direction[1] >= 0.0 else -1.0)

                signs = (back_side_sign(back_a), back_side_sign(back_b))
                back_planting = next(
                    (item for item in planned_plantings
                     if item.edge_id == f"{node.id}_back_sidewalk"), None)
                back_widths = tuple(_sidewalk_footprint_for_edge(
                    next(e for e in network.edges if e.id == arm.edge_id))
                    for arm in (back_a, back_b))
                back_sidewalk_footprint = min(back_widths)
                bands = ((0.0, 0.33),
                         (0.33 + back_planting.width, back_sidewalk_footprint)) \
                    if back_planting is not None else ((0.0, back_sidewalk_footprint),)

                def back_point(back_arm, sign, offset):
                    return point_from_node(
                        center, back_arm, _arm_trim(back_arm, arms),
                        sign * (back_arm.width * 0.5 + offset))

                for band_index, (inner_offset, outer_offset) in enumerate(bands):
                    if outer_offset <= inner_offset:
                        continue
                    inner_a = back_point(back_a, signs[0], inner_offset)
                    inner_b = back_point(back_b, signs[1], inner_offset)
                    outer_b = back_point(back_b, signs[1],
                        back_widths[1] if outer_offset == back_sidewalk_footprint else outer_offset)
                    outer_a = back_point(back_a, signs[0],
                        back_widths[0] if outer_offset == back_sidewalk_footprint else outer_offset)
                    _polygon(
                        f"{node.id} back sidewalk {band_index}",
                        (inner_a, inner_b, outer_b, outer_a),
                        SIDEWALK_TOP_Z_M - (0.012 if sidewalk_bricks else 0.0),
                        sidewalk)
                    _sidewalk_brick_polygon(
                        f"{node.id} back sidewalk {band_index} brick paving",
                        (inner_a, inner_b, outer_b, outer_a), sidewalk_bricks)
                if back_planting is not None:
                    planting_offset = 0.33 + back_planting.width * 0.5
                    planting_instance(
                        back_planting.id,
                        back_point(back_a, signs[0], planting_offset),
                        back_point(back_b, signs[1], planting_offset),
                        back_planting.width, back_planting.density,
                        back_planting.maintenance, back_planting.health,
                        back_planting.seed, back_planting.elevation,
                        style=back_planting.style,
                    )
                    rendered_back_planting_ids.add(back_planting.id)

                # Edge-side fences stop before the junction. Complete the
                # continuous fence across a T junction's missing arm when both
                # adjoining through-road edges request a fence on this side.
                # Use the same actual arm-frame endpoints as the back sidewalk,
                # so orthogonal and oblique T junctions share one construction.
                back_edges = []
                for back_arm, sign in zip((back_a, back_b), signs):
                    edge = next(item for item in network.edges
                                if item.id == back_arm.edge_id)
                    side = (
                        "left" if ((back_arm.endpoint == "from") == (sign > 0.0))
                        else "right"
                    )
                    config = edge.guardrail
                    if (config is None or config.sides == "none"
                            or config.sides not in {"both", side}):
                        back_edges = []
                        break
                    back_edges.append((edge, config))
                if len(back_edges) == 2:
                    guardrail_offset = 0.22
                    guardrail_start = back_point(
                        back_a, signs[0], guardrail_offset)
                    guardrail_end = back_point(
                        back_b, signs[1], guardrail_offset)
                    direction = normalized((
                        guardrail_end[0] - guardrail_start[0],
                        guardrail_end[1] - guardrail_start[1],
                    ))
                    left = (-direction[1], direction[0])
                    midpoint = (
                        (guardrail_start[0] + guardrail_end[0]) * 0.5,
                        (guardrail_start[1] + guardrail_end[1]) * 0.5,
                    )
                    toward_road = (center[0] - midpoint[0],
                                   center[1] - midpoint[1])
                    beam_side = ("left" if left[0] * toward_road[0]
                                 + left[1] * toward_road[1] >= 0.0 else "right")
                    guardrail_instance(
                        f"{node.id} back sidewalk guardrail",
                        guardrail_start, guardrail_end,
                        back_edges[0][1].exterior_color,
                        beam_side, GUARDRAIL_BASE_Z_M,
                    )
                curb_path = _PolylinePath((
                    back_point(back_a, signs[0], CURB_WIDTH_M * 0.5),
                    back_point(back_b, signs[1], CURB_WIDTH_M * 0.5),
                ))
                back_curb = _curb_blocks_along_path(
                    f"{node.id} back sidewalk curb", curb_path,
                    0.0, curb_path.length, 0.0, curb,
                    road_reference=center)
                through_edges = tuple(
                    next(item for item in network.edges
                         if item.id == back_arm.edge_id)
                    for back_arm in open_pair)
                # The two through-road edges are one uninterrupted kerb on the
                # back side of a T junction.  Continue the parking-prohibition
                # block paint over the same bridge instead of stopping it at
                # each edge's junction trim.
                if all(item.sidewalks == "both"
                       and item.curb_parking_prohibition
                       for item in through_edges):
                    _curb_paint_on_blocks(
                        f"{node.id} back sidewalk parking curb", back_curb,
                        curb_path, 0.0, curb_path.length, orange,
                    )
                if all(item.tactile_paving for item in through_edges):
                    tactile_path = _PolylinePath((
                        back_point(back_a, signs[0], SIDEWALK_WIDTH_M - 0.6),
                        back_point(back_b, signs[1], SIDEWALK_WIDTH_M - 0.6),
                    ))
                    _tactile_tiles_along_path(
                        tactile_plans, f"{node.id} back tactile",
                        tactile_path, 0.0, tactile_path.length, 0.0,
                        "guidance")

        for index, arm in enumerate(arms):
            nxt = arms[(index + 1) % len(arms)]
            gap = (nxt.angle - arm.angle) % 360.0
            if gap > 150.0:  # open back side of a T junction
                continue
            trim_a = _arm_trim(arm, arms)
            trim_b = _arm_trim(nxt, arms)
            curb_a = point_from_node(center, arm, trim_a, arm.width / 2 + 0.14)
            outer_a = point_from_node(center, arm, trim_a,
                                      arm.width / 2 + SIDEWALK_WIDTH_M)
            curb_b = point_from_node(center, nxt, trim_b, -nxt.width / 2 - 0.14)
            outer_b = point_from_node(center, nxt, trim_b,
                                      -nxt.width / 2 - SIDEWALK_WIDTH_M)
            handle = min(5.0, min(trim_a, trim_b) * 0.52)
            inner = _cubic_points(
                curb_a, add(curb_a, mul(arm.outward, -handle)),
                add(curb_b, mul(nxt.outward, -handle)), curb_b,
            )
            outer = _cubic_points(
                outer_b, add(outer_b, mul(nxt.outward, -handle)),
                add(outer_a, mul(arm.outward, -handle)), outer_a,
            )
            arm_edge = next(item for item in network.edges if item.id == arm.edge_id)
            next_edge = next(item for item in network.edges if item.id == nxt.edge_id)
            linear_corner = all(
                edge.geometry is None or edge.geometry.kind == "line"
                for edge in (arm_edge, next_edge)
            )
            if linear_corner:
                # Measure from the *actual intersection of the two kerb
                # boundary lines*.  That intersection shifts when the roads
                # cease to be perpendicular; using the legacy 3.8 m trim as
                # the tangent allowance makes an acute fillet overrun both
                # straight kerbs.
                kerb_line_a = add(center, mul(arm.left, arm.width * 0.5))
                kerb_line_b = add(center, mul(nxt.left, -nxt.width * 0.5))
                kerb_intersection = _line_intersection(
                    kerb_line_a, arm.outward, kerb_line_b, nxt.outward)
                straight_road_a = point_from_node(
                    center, arm, trim_a, arm.width * 0.5)
                straight_road_b = point_from_node(
                    center, nxt, trim_b, -nxt.width * 0.5)
                tangent_allowance_a = (
                    (straight_road_a[0] - kerb_intersection[0]) * arm.outward[0]
                    + (straight_road_a[1] - kerb_intersection[1]) * arm.outward[1])
                tangent_allowance_b = (
                    (straight_road_b[0] - kerb_intersection[0]) * nxt.outward[0]
                    + (straight_road_b[1] - kerb_intersection[1]) * nxt.outward[1])
                # At an acute corner shrink to the largest tangent circle that
                # fits.  At an obtuse corner retain 3.8 m and fill the genuine
                # residual with the straight connectors below.
                radius = corner_fillet_radius(
                    gap, min(tangent_allowance_a, tangent_allowance_b))
                arm_line = add(center, mul(
                    arm.left, arm.width * 0.5 + radius))
                next_line = add(center, mul(
                    nxt.left, -(nxt.width * 0.5 + radius)))
                fillet_center = _line_intersection(
                    arm_line, arm.outward, next_line, nxt.outward)
                if fillet_center is not None:
                    sweep = 180.0 - gap
                    start_angle = nxt.angle + 90.0
                    end_angle = start_angle + sweep
                    # The arc points inward from its property-side centre, so
                    # its midpoint has the opposite quadrant. Label corners
                    # from the fillet centre itself to retain legacy seeds.
                    qx = 1 if fillet_center[0] >= center[0] else -1
                    qy = 1 if fillet_center[1] >= center[1] else -1
                    label = ({(-1, -1): "southwest", (-1, 1): "northwest",
                              (1, -1): "southeast", (1, 1): "northeast"}[(qx, qy)])
                    planting = corner_plantings.get((node.id, label))
                    if node.kind == "priority_t_junction":
                        planting = None
                    if planting is not None:
                        planting = PlantingPlan(
                            planting.id, planting.edge_id, planting.side,
                            fillet_center, fillet_center, planting.width,
                            planting.density, planting.maintenance,
                            planting.health, planting.seed, planting.elevation,
                            fillet_center,
                            radius - 0.33 - planting.width * 0.5,
                            start_angle + sweep * 0.25, sweep * 0.5,
                            style=planting.style,
                        )
                    _intersection_corner_pavement(
                        f"{node.id} corner {index} road pavement",
                        fillet_center, start_angle, end_angle, radius, asphalt,
                        kerb_intersection)
                    _rounded_corner(
                        f"{node.id} corner {index}", fillet_center,
                        start_angle, end_angle, radius, sidewalk, curb, planting,
                        sidewalk_bricks)

                    def radial_point(angle_degrees, point_radius):
                        angle_radians = math.radians(angle_degrees)
                        return (fillet_center[0] + math.cos(angle_radians) * point_radius,
                                fillet_center[1] + math.sin(angle_radians) * point_radius)

                    # Join the preferred-radius arc to the mature straight
                    # endpoint on obtuse corners.  These short returns carry
                    # only pavement, kerb and tactile paving.
                    # Match the mature junction footprint: 3.6 m nominal
                    # sidewalk plus the 0.2 m outer-edge/corner allowance.
                    # Using only the nominal width produces a visible inward
                    # step at the straight-to-fillet connection.
                    connector_sidewalk_width = max(
                        SIDEWALK_WIDTH_M, SIDEWALK_CORNER_RADIUS_M)
                    connector_specs = (
                        (point_from_node(center, arm, trim_a, arm.width * 0.5),
                         point_from_node(center, arm, trim_a,
                                         arm.width * 0.5 + connector_sidewalk_width),
                         radial_point(end_angle, radius),
                         radial_point(end_angle, max(
                             0.0, radius - connector_sidewalk_width))),
                        (point_from_node(center, nxt, trim_b, -nxt.width * 0.5),
                         point_from_node(center, nxt, trim_b,
                                         -nxt.width * 0.5 - connector_sidewalk_width),
                         radial_point(start_angle, radius),
                         radial_point(start_angle, max(
                             0.0, radius - connector_sidewalk_width))),
                    )
                    if (arm_edge.median and next_edge.median
                            and abs(arm.width - nxt.width) > 1e-6):
                        # The legacy rounded corner intentionally retains its
                        # original 3.8 m footprint.  With unequal carriageway
                        # widths, however, the two 7.4 m straight extensions
                        # start at different stations and leave a small wedge
                        # behind that corner.  Close only that property-side
                        # wedge; the curved kerb and its road-side outline are
                        # left untouched.
                        arm_wide_start = point_from_node(
                            center, arm, trim_a,
                            arm.width * 0.5
                            + _sidewalk_footprint_for_edge(arm_edge))
                        next_wide_start = point_from_node(
                            center, nxt, trim_b,
                            -nxt.width * 0.5
                            - _sidewalk_footprint_for_edge(next_edge))
                        wide_joint = _line_intersection(
                            arm_wide_start, arm.outward,
                            next_wide_start, nxt.outward)
                        # Walk the complete boundary from the retained corner
                        # arc, along the second arm's standard and wide outer
                        # endpoints, around the property-side join, and back
                        # via the first arm.  Including both standard endpoints
                        # is essential: they bound the tiny 2x3 hole nearest
                        # the old rounded corner.
                        closure_outline = tuple(point for point in (
                            connector_specs[0][3],
                            connector_specs[1][1], next_wide_start,
                            wide_joint, arm_wide_start,
                            connector_specs[0][1]) if point is not None)
                        # The broad closure outline also contains pieces of
                        # both mature extension strips.  Tessellate it as a
                        # fan, then subtract those finite strips so every XY
                        # point is owned by exactly one pavement mesh.
                        reach = max(item.length for item in paths.values()) + 10.0
                        arm_extension = (
                            connector_specs[0][0],
                            add(connector_specs[0][0], mul(arm.outward, reach)),
                            add(arm_wide_start, mul(arm.outward, reach)),
                            arm_wide_start)
                        next_extension = (
                            connector_specs[1][0],
                            add(connector_specs[1][0], mul(nxt.outward, reach)),
                            add(next_wide_start, mul(nxt.outward, reach)),
                            next_wide_start)
                        closure_pieces = []
                        boundary_vectors = [Vector(point)
                                            for point in closure_outline]
                        triangles = tessellate_polygon([boundary_vectors])
                        for triangle in triangles:
                            pieces = [[(
                                boundary_vectors[point].x,
                                boundary_vectors[point].y)
                                if isinstance(point, int) else (point.x, point.y)
                                for point in triangle]]
                            for cutter in (arm_extension, next_extension):
                                pieces = [piece for candidate in pieces
                                          for piece in _subtract_convex_polygon(
                                              candidate, cutter)]
                            closure_pieces.extend(
                                piece for piece in pieces if len(piece) >= 3)
                        closure_name = (
                            f"{node.id} corner {index} unequal-width connector closure")
                        for piece_index, closure in enumerate(closure_pieces):
                            piece_name = f"{closure_name} {piece_index}"
                            _polygon(
                                piece_name, closure,
                                SIDEWALK_TOP_Z_M - (
                                    0.012 if sidewalk_bricks else 0.0),
                                sidewalk)
                            _sidewalk_brick_polygon(
                                piece_name + " brick paving", closure,
                                sidewalk_bricks)
                    for connector_index, (straight_road, straight_outer,
                                          arc_road, arc_outer) in enumerate(connector_specs):
                        connector_length = math.hypot(
                            straight_road[0] - arc_road[0],
                            straight_road[1] - arc_road[1])
                        if connector_length <= 1e-6:
                            continue
                        # Both adjoining mature sidewalks own the outward side
                        # of their exact trim lines. Clip the return against
                        # both inward half-planes: on a skew junction it can
                        # otherwise reach across and overlap the *other* arm,
                        # even after its own endpoint has been clipped.
                        connector_piece = list((
                            straight_road, arc_road, arc_outer, straight_outer))
                        for clip_arm, clip_trim in ((arm, trim_a), (nxt, trim_b)):
                            clip_origin = point_from_node(
                                center, clip_arm, clip_trim, 0.0)
                            connector_piece = _clip_polygon_half_plane(
                                connector_piece,
                                (clip_origin, mul(clip_arm.outward, -1.0)))
                            if len(connector_piece) < 3:
                                break
                        connector_pieces = ((connector_piece,)
                                            if len(connector_piece) >= 3 else ())
                        connector_name = (
                            f"{node.id} corner {index} connector "
                            f"{connector_index}")
                        for piece_index, connector_piece in enumerate(connector_pieces):
                            piece_name = f"{connector_name} sidewalk {piece_index}"
                            _polygon(
                                piece_name, connector_piece,
                                SIDEWALK_TOP_Z_M - (
                                    0.012 if sidewalk_bricks else 0.0),
                                sidewalk)
                            _sidewalk_brick_polygon(
                                f"{connector_name} brick paving {piece_index}",
                                connector_piece, sidewalk_bricks)
                        straight_center = (
                            straight_road[0] + (straight_outer[0] - straight_road[0])
                            * CURB_WIDTH_M * 0.5 / SIDEWALK_WIDTH_M,
                            straight_road[1] + (straight_outer[1] - straight_road[1])
                            * CURB_WIDTH_M * 0.5 / SIDEWALK_WIDTH_M)
                        arc_center = radial_point(
                            end_angle if connector_index == 0 else start_angle,
                            radius - CURB_WIDTH_M * 0.5)
                        connector_path = _PolylinePath((straight_center, arc_center))
                        _curb_blocks_along_path(
                            f"{node.id} corner {index} connector {connector_index} curb",
                            connector_path, 0.0, connector_path.length, 0.0,
                            curb, road_reference=center)
                    if planting is not None:
                        planting_instance(
                            planting.id, planting.start, planting.end,
                            planting.width, planting.density,
                            planting.maintenance, planting.health,
                            planting.seed, planting.elevation,
                            planting.curve_center, planting.curve_radius,
                            planting.curve_start_degrees,
                            planting.curve_sweep_degrees,
                            style=planting.style,
                        )
                    guard = corner_guardrails.get((node.id, label))
                    if node.kind == "priority_t_junction":
                        guard = None
                    if guard is not None:
                        guardrail_instance(
                            guard.id, fillet_center, fillet_center,
                            guard.exterior_color, guard.beam_side,
                            guard.elevation, fillet_center, radius - 0.22,
                            start_angle + sweep * 0.25, sweep * 0.5,
                        )
                    arm_tactile = (arm_edge.tactile_paving
                                   and arm_edge.sidewalks == "both")
                    next_tactile = (next_edge.tactile_paving
                                    and next_edge.sidewalks == "both")
                    if arm_tactile or next_tactile:
                        crossing_tactile_sides.setdefault(
                            (node.id, arm.edge_id), set()).add(1)
                        crossing_tactile_sides.setdefault(
                            (node.id, nxt.edge_id), set()).add(-1)
                        route_ends = (
                            radial_point(end_angle,
                                      radius - (SIDEWALK_WIDTH_M - 0.60)),
                            radial_point(start_angle,
                                      radius - (SIDEWALK_WIDTH_M - 0.60)),
                        )
                        straight_route_ends = (
                            point_from_node(
                                center, arm, trim_a,
                                arm.width * 0.5 + SIDEWALK_WIDTH_M - 0.60),
                            point_from_node(
                                center, nxt, trim_b,
                                -nxt.width * 0.5 - SIDEWALK_WIDTH_M + 0.60),
                        )
                        for connector_index, (straight_route, arc_route) in enumerate(
                                zip(straight_route_ends, route_ends)):
                            connector = _PolylinePath((straight_route, arc_route))
                            if connector.length > 1e-6:
                                _tactile_tiles_along_path(
                                    tactile_plans,
                                    f"{node.id} corner {index} tactile connector {connector_index}",
                                    connector, 0.0, connector.length, 0.0,
                                    "guidance", allow_empty=True)
                        route_corner = _line_intersection(
                            route_ends[0], arm.outward,
                            route_ends[1], nxt.outward)
                        if route_corner is not None:
                            # The two mature straight tactile routes must end
                            # at this corner warning field.  Record the actual
                            # half-plane in each road's outward direction;
                            # otherwise their first tile continues beyond the
                            # warning and survives clipping as an orphan sliver.
                            for terminal_arm, local_side, enabled in (
                                    (arm, 1, arm_tactile),
                                    (nxt, -1, next_tactile)):
                                if not enabled:
                                    continue
                                path_side = (local_side
                                             if terminal_arm.endpoint == "from"
                                             else -local_side)
                                terminal_outward = terminal_arm.outward
                                terminal_extent = 0.30 * (
                                    abs(terminal_outward[0] * arm.outward[0]
                                        + terminal_outward[1] * arm.outward[1])
                                    + abs(terminal_outward[0] * arm.left[0]
                                          + terminal_outward[1] * arm.left[1]))
                                tactile_route_terminals.append((
                                    f"{terminal_arm.edge_id} tactile route {path_side}_",
                                    route_corner, terminal_outward,
                                    terminal_extent))
                            # Stop each rigid run at the theoretical meeting
                            # point. At a non-right angle their square ends
                            # deliberately leave triangular wedges; they never
                            # overlap or deform a manufactured 300 mm tile.
                            def stop_before_corner(endpoint):
                                dx = endpoint[0] - route_corner[0]
                                dy = endpoint[1] - route_corner[1]
                                length = math.hypot(dx, dy)
                                ux, uy = dx / length, dy / length
                                # The warning field is a 0.6 m square oriented
                                # with arm.outward/arm.left.  Project its true
                                # half extents onto this leg instead of using a
                                # fixed cardinal clearance; the latter lets an
                                # oblique leg continue past the warning face.
                                warning_extent = 0.30 * (
                                    abs(ux * arm.outward[0] + uy * arm.outward[1])
                                    + abs(ux * arm.left[0] + uy * arm.left[1]))
                                clearance = min(length, warning_extent + 0.002)
                                return (route_corner[0] + dx / length * clearance,
                                        route_corner[1] + dy / length * clearance)

                            for leg_index, points in enumerate((
                                    (route_ends[0], stop_before_corner(route_ends[0])),
                                    (stop_before_corner(route_ends[1]), route_ends[1]))):
                                terminal_arm = arm if leg_index == 0 else nxt
                                route_end = route_ends[leg_index]
                                outward_separation = (
                                    (route_end[0] - route_corner[0])
                                    * terminal_arm.outward[0]
                                    + (route_end[1] - route_corner[1])
                                    * terminal_arm.outward[1])
                                # If the warning field has moved farther
                                # outward than the arc endpoint, this leg would
                                # reverse back toward the intersection and
                                # appear as an isolated strip beyond warning.
                                if outward_separation <= 0.0:
                                    continue
                                leg = _PolylinePath(points)
                                if leg.length <= 1e-6:
                                    continue
                                _tactile_tiles_along_path(
                                    tactile_plans,
                                    f"{node.id} corner {index} tactile leg {leg_index}",
                                    leg, 0.0, leg.length, 0.0, "guidance")

                            # If only one adjoining road carries a longitudinal
                            # route, the other branch must still continue from
                            # this corner warning field to its crosswalk.  This
                            # is the same one-sided rule used by the mature
                            # orthogonal planner.
                            for branch_index, (terminal_arm, local_side,
                                               enabled, straight_route) in enumerate((
                                    (arm, 1, arm_tactile, straight_route_ends[0]),
                                    (nxt, -1, next_tactile, straight_route_ends[1]))):
                                if enabled:
                                    continue
                                has_crosswalk = (
                                    node.kind != "priority_t_junction"
                                    or (terminal_arm.edge_id, node.id)
                                    in stop_controlled_approaches)
                                if not has_crosswalk:
                                    continue
                                crossing_station = _arm_crosswalk_distance(
                                    terminal_arm, arms)
                                crossing_route = point_from_node(
                                    center, terminal_arm, crossing_station,
                                    local_side * (
                                        terminal_arm.width * 0.5
                                        + SIDEWALK_WIDTH_M - 0.60))
                                extension = _PolylinePath((
                                    straight_route, crossing_route))
                                if extension.length > 1e-6:
                                    _tactile_tiles_along_path(
                                        tactile_plans,
                                        f"{node.id} corner {index} tactile crosswalk extension {branch_index}",
                                        extension, 0.0, extension.length, 0.0,
                                        "guidance", allow_empty=True)
                            corner_warning = _PolylinePath((
                                add(route_corner, mul(arm.outward, -0.30)),
                                add(route_corner, mul(arm.outward, 0.30)),
                            ))
                            _tactile_tiles_along_path(
                                tactile_plans,
                                f"{node.id} corner {index} tactile warning",
                                corner_warning, 0.0, corner_warning.length,
                                0.0, "warning", rows=2)
                    continue
            corner_planting = arm_edge.planting is not None and next_edge.planting is not None
            if corner_planting:
                outer_forward = tuple(reversed(outer))

                def inset_curve(distance):
                    result = []
                    for road_point, outer_point in zip(inner, outer_forward):
                        dx, dy = outer_point[0] - road_point[0], outer_point[1] - road_point[1]
                        length = math.hypot(dx, dy)
                        result.append((road_point[0] + dx / length * distance,
                                       road_point[1] + dy / length * distance))
                    return result

                bed_near = inset_curve(0.33)
                bed_center = inset_curve(0.33 + 0.85 * 0.5)
                bed_far = inset_curve(0.33 + 0.85)
                _polygon(f"{node.id} corner {index} inner sidewalk",
                         tuple(inner + list(reversed(bed_near))),
                         SIDEWALK_TOP_Z_M, sidewalk)
                _polygon(f"{node.id} corner {index} outer sidewalk",
                         tuple(bed_far + outer), SIDEWALK_TOP_Z_M, sidewalk)
                planting_path = _PolylinePath(bed_center)
                module_count = max(1, math.ceil(planting_path.length / 1.1))
                module_length = planting_path.length / module_count
                for module_index in range(module_count):
                    station_a = module_index * module_length
                    station_b = (module_index + 1) * module_length
                    planting_instance(
                        f"{node.id} corner {index} planting {module_index}",
                        planting_path.offset_point(station_a, 0.0),
                        planting_path.offset_point(station_b, 0.0), 0.85,
                        arm_edge.planting.density,
                        arm_edge.planting.maintenance,
                        arm_edge.planting.health,
                        (arm_edge.planting.seed or 1000) + index * 100 + module_index,
                        PLANTING_INSTANCE_Z_M,
                        style=("clipped_hedge"
                               if arm_edge.planting.style == "clipped_hedge"
                               and next_edge.planting.style == "clipped_hedge"
                               else "legacy"),
                    )
            else:
                _polygon(f"{node.id} corner sidewalk {index}",
                         tuple(inner + outer), SIDEWALK_TOP_Z_M, sidewalk)
            corner_curb = _PolylinePath(inner)
            _curb_blocks_along_path(
                f"{node.id} corner {index} curb", corner_curb,
                0.0, corner_curb.length, 0.0, curb)
            if arm_edge.guardrail is not None and next_edge.guardrail is not None:
                outer_forward = tuple(reversed(outer))
                guard_points = []
                for road_point, outer_point in zip(inner, outer_forward):
                    dx, dy = outer_point[0] - road_point[0], outer_point[1] - road_point[1]
                    length = math.hypot(dx, dy)
                    guard_points.append((road_point[0] + dx / length * 0.22,
                                         road_point[1] + dy / length * 0.22))
                guard_path = _PolylinePath(guard_points)
                module_count = max(1, math.ceil(guard_path.length / 1.1))
                module_length = guard_path.length / module_count
                for module_index in range(module_count):
                    guardrail_instance(
                        f"{node.id} corner {index} guardrail {module_index}",
                        guard_path.offset_point(module_index * module_length, 0.0),
                        guard_path.offset_point((module_index + 1) * module_length, 0.0),
                        arm_edge.guardrail.exterior_color, "right", SIDEWALK_TOP_Z_M)
        for arm in arms:
            arm_has_crosswalk = (
                node.kind != "priority_t_junction"
                or (arm.edge_id, node.id) in stop_controlled_approaches)
            if not arm_has_crosswalk:
                continue
            edge = next(item for item in network.edges if item.id == arm.edge_id)
            crosswalk_distance = _arm_crosswalk_distance(arm, arms)
            cross_center = point_from_node(center, arm, crosswalk_distance)
            heading = math.atan2(arm.outward[1], arm.outward[0])
            across = arm.left
            _rotated_crosswalk(f"{node.id} {arm.id} crosswalk", cross_center,
                               arm.outward,
                               max(0.5, arm.width - 2 * (
                                   CURB_ROAD_APRON_M + ROAD_MARKING_CURB_CLEARANCE_M)),
                               3.2, white)
            tactile_sides = crossing_tactile_sides.get(
                (node.id, arm.edge_id), set())
            if tactile_sides:
                for side in sorted(tactile_sides):
                    warning = point_from_node(center, arm, crosswalk_distance,
                                              side * (arm.width / 2 + 0.60))
                    warning_start = add(warning, mul(arm.outward, -1.65))
                    warning_end = add(warning, mul(arm.outward, 1.65))
                    warning_path = _PolylinePath((warning_start, warning_end))
                    _tactile_tiles_along_path(
                        tactile_plans, f"{node.id} {arm.id} tactile warning {side}",
                        warning_path, 0.0, warning_path.length, 0.0,
                        "warning", rows=2)
                    guide_a = point_from_node(
                        center, arm, crosswalk_distance,
                        side * (arm.width / 2 + 0.90))
                    guide_b = point_from_node(
                        center, arm, crosswalk_distance,
                        side * (arm.width / 2 + 2.70))
                    guide_path = _PolylinePath((guide_a, guide_b))
                    _tactile_tiles_along_path(
                        tactile_plans, f"{node.id} {arm.id} tactile guide {side}",
                        guide_path, 0.0, guide_path.length, 0.0,
                        "guidance", rows=2)
                    terminal_a = point_from_node(
                        center, arm, crosswalk_distance,
                        side * (arm.width / 2 + 2.70))
                    terminal_b = point_from_node(
                        center, arm, crosswalk_distance,
                        side * (arm.width / 2 + 3.30))
                    terminal_path = _PolylinePath((terminal_a, terminal_b))
                    _tactile_tiles_along_path(
                        tactile_plans, f"{node.id} {arm.id} tactile terminal {side}",
                        terminal_path, 0.0, terminal_path.length, 0.0,
                        "warning", rows=2)
            stop = point_from_node(center, arm, crosswalk_distance + 3.6)
            # Stop only the inbound (left-driving) half of the carriageway.
            extra_here = has_extra_inbound_lane(edge, arm.endpoint)
            carriageway_width = (edge.lanes_each_way
                                 + (1 if extra_here else 0)) * LANE_WIDTH_M
            inbound_center = -(arm.width * 0.5 - carriageway_width * 0.5)
            stop = add(stop, mul(arm.left, inbound_center))
            _rotated_stop_line(f"{node.id} {arm.id} stop line", stop,
                               arm.outward, carriageway_width
                               - 2 * (CURB_ROAD_APRON_M
                                      + ROAD_MARKING_CURB_CLEARANCE_M), white)

            is_unsignalized = node.kind in {
                "stop_cross", "stop_t_junction", "priority_t_junction"}
            is_stop_controlled = ((arm.edge_id, node.id)
                                  in stop_controlled_approaches)
            if is_stop_controlled:
                # Keep the ordinary crosswalk/stop-line layout unchanged. Stop
                # control only adds the inbound road text and roadside sign.
                inbound_heading = math.degrees(math.atan2(
                    -arm.outward[1], -arm.outward[0]))
                marking_center = add(stop, mul(arm.outward, 4.9))
                _stacked_stop_marking(marking_center, inbound_heading, white)
                # ``stop`` is centred on the inbound half carriageway. Move
                # another quarter road-width plus the shared road-edge offset
                # to sit just behind, but clear of, the guardrail.
                sign_location = add(
                    add(stop, mul(arm.outward, 1.3)),
                    mul(arm.left, -(carriageway_width * 0.5
                                    + STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M)))
            elif is_unsignalized and node.kind != "priority_t_junction":
                inbound_heading = math.degrees(math.atan2(
                    -arm.outward[1], -arm.outward[0]))
                sign_location = add(
                    add(stop, mul(arm.outward, 1.3)),
                    mul(arm.left, -(carriageway_width * 0.5
                                    + STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M)))

            if is_unsignalized:
                if is_stop_controlled:
                    if node.kind == "priority_t_junction":
                        sign_types = ("止まれ", "指定方向外進行禁止（左折）")
                    else:
                        sign_types = (("止まれ", "横断歩道")
                                      if stop_approach_has_crosswalk_sign(
                                          node.id, arm.edge_id)
                                      else ("止まれ",))
                else:
                    sign_types = ("横断歩道",)
                    stop_distance = crosswalk_distance + 3.6
                    try:
                        point_on_road_from_node(edge, node.id, 70.0, 0.0)
                    except ValueError:
                        pass
                    else:
                        for advance in (30.0, 50.0):
                            center_on_lane, outward_at_marking = point_on_road_from_node(
                                edge, node.id, stop_distance + advance,
                                inbound_center)
                            travel = (-outward_at_marking[0],
                                      -outward_at_marking[1])
                            diamond_heading = math.degrees(math.atan2(
                                travel[1], travel[0]))
                            _road_crosswalk_diamond(
                                f"{node.id} {arm.id} crosswalk diamond {int(advance)}m",
                                center_on_lane, diamond_heading, white)
                cached_asset_instance(
                    ("road_sign_stack", sign_types),
                    lambda sign_types=sign_types: create_road_sign_stack(
                        sign_types,
                        "Road Sign Stack Prototype " + " ".join(sign_types)),
                    f"{node.id} {arm.id} road sign",
                    (*sign_location, SIGNAL_BASE_Z_M), inbound_heading - 90.0,
                )
            if node.kind.startswith("signalized"):
                light = _arm_active(node, arm, groups)
                cardinal_angles = {"east": 0.0, "north": 90.0,
                                   "west": 180.0, "south": 270.0}
                approach = min(
                    cardinal_angles,
                    key=lambda name: abs((arm.angle - cardinal_angles[name]
                                          + 180.0) % 360.0 - 180.0),
                )
                delta = (arm.angle - cardinal_angles[approach] + 180.0) % 360.0 - 180.0

                # A vehicle head faces this incoming arm, while its pole is
                # physically on the continuation across the junction. When a
                # through road bends, those are deliberately different frames.
                support_arm = next(
                    (other for group in groups if arm in group
                     for other in group if other is not arm), None)
                if support_arm is None:
                    # A T stem has no opposite arm, but its pole stands on the
                    # uninterrupted through-road sidewalk. Follow that road's
                    # frame for XY while the head keeps the stem's own angle.
                    # At 0 degrees this is exactly the legacy location.
                    through_arm = next(
                        (candidate for group in groups if arm not in group
                         and len(group) > 1 for candidate in group),
                        None)
                    if through_arm is None:
                        support_delta = delta
                    else:
                        through_cardinal = min(
                            cardinal_angles,
                            key=lambda name: abs((through_arm.angle
                                                  - cardinal_angles[name]
                                                  + 180.0) % 360.0 - 180.0),
                        )
                        support_delta = (
                            through_arm.angle
                            - cardinal_angles[through_cardinal]
                            + 180.0) % 360.0 - 180.0
                else:
                    support_approach = cardinal_angles[
                        {"east": "west", "west": "east",
                         "north": "south", "south": "north"}[approach]]
                    support_delta = (
                        support_arm.angle - support_approach + 180.0) % 360.0 - 180.0

                def rotate_site(site, site_delta=delta):
                    angle_delta = math.radians(site_delta)
                    rx, ry = site.location[0] - center[0], site.location[1] - center[1]
                    return ((center[0] + rx * math.cos(angle_delta)
                             - ry * math.sin(angle_delta)),
                            (center[1] + rx * math.sin(angle_delta)
                             + ry * math.cos(angle_delta)),
                            site.location[2])

                vehicle_site = next(
                    site for site in compatibility_signals
                    if site.id == f"{node.id}_{approach}_vehicle")
                # Median plans and their signal sites are already authored in
                # the real edge frame. Rotating those world-space coordinates
                # again displaces an oblique island pole off its median.
                vehicle_location = (
                    vehicle_site.location
                    if vehicle_site.support_mode == "median_right"
                    else rotate_site(vehicle_site, support_delta)
                )
                if support_arm is None and through_arm is not None:
                    # The stem-facing pole belongs at the road-facing edge of
                    # the uninterrupted back sidewalk. Rotating its legacy XY
                    # vector preserves an obsolete longitudinal component and
                    # puts it at the property edge. Preserve only its station
                    # along the through road, then rebuild the normal offset
                    # from the standard roadside clearance encoded by the
                    # planner's smaller coordinate.
                    vehicle_location = t_stem_signal_support_location(
                        center, arm, through_arm, vehicle_location)
                vehicle_instance(f"{node.id} {arm.id} vehicle",
                                 vehicle_location,
                                 vehicle_site.rotation_degrees + delta, light,
                                 node.name, node.roman_name, node.exterior_color,
                                 effective_vehicle_arrow(network, node),
                                 bool(effective_vehicle_arrow(network, node) == "right"
                                      and node.signal_phase.endswith("right_arrow")
                                      and _arm_selected(node, arm, groups)),
                                 _vehicle_horizontal_extension(
                                     network, vehicle_site),
                                 "right" if vehicle_site.support_mode == "median_right"
                                 else "left")
                pedestrian_sites = sorted(
                    (site for site in compatibility_signals
                     if site.kind == "pedestrian"
                     and site.id.startswith(f"{node.id}_{approach}_")),
                    key=lambda site: site.id,
                )
                for site in pedestrian_sites:
                    pedestrian_light = (
                        "blue" if (not node.signal_phase.endswith("_right_arrow")
                                   and _pedestrian_arm_selected(
                                       node, site.rotation_degrees, arms, groups))
                        else "red")
                    countdown = countdown_by_node[node.id]
                    countdown_level = (countdown.blue_level
                                       if pedestrian_light == "blue"
                                       else countdown.red_level)
                    pedestrian_location = rotate_site(site)
                    pedestrian_rotation = site.rotation_degrees + delta
                    block = signal_block_by_pedestrian.get(site.id)
                    merge = False
                    merge_position = "inner"
                    if block is not None and site.pedestrian_position == merge_position \
                            and block.vehicle.support_mode == "roadside_left":
                        vehicle_approach = next(
                            name for name in cardinal_angles
                            if block.vehicle.id.startswith(f"{node.id}_{name}_"))
                        vehicle_arm = min(
                            arms,
                            key=lambda item: abs((item.angle
                                                  - cardinal_angles[vehicle_approach]
                                                  + 180.0) % 360.0 - 180.0))
                        vehicle_delta = ((vehicle_arm.angle
                                          - cardinal_angles[vehicle_approach]
                                          + 180.0) % 360.0 - 180.0)
                        vehicle_support_arm = next(
                            (other for group in groups if vehicle_arm in group
                             for other in group if other is not vehicle_arm),
                            None)
                        if vehicle_support_arm is None:
                            through_arm = next(
                                (candidate for group in groups
                                 if vehicle_arm not in group and len(group) > 1
                                 for candidate in group),
                                None)
                            if through_arm is None:
                                vehicle_support_delta = vehicle_delta
                            else:
                                through_cardinal = min(
                                    cardinal_angles,
                                    key=lambda name: abs((through_arm.angle
                                                          - cardinal_angles[name]
                                                          + 180.0) % 360.0 - 180.0),
                                )
                                vehicle_support_delta = (
                                    through_arm.angle
                                    - cardinal_angles[through_cardinal]
                                    + 180.0) % 360.0 - 180.0
                        else:
                            vehicle_support_approach = cardinal_angles[
                                {"east": "west", "west": "east",
                                 "north": "south", "south": "north"}[
                                     vehicle_approach]]
                            vehicle_support_delta = (
                                vehicle_support_arm.angle - vehicle_support_approach
                                + 180.0) % 360.0 - 180.0
                        vehicle_angle = math.radians(vehicle_support_delta)
                        vx = block.vehicle.location[0] - center[0]
                        vy = block.vehicle.location[1] - center[1]
                        transformed_vehicle = (
                            center[0] + vx * math.cos(vehicle_angle)
                            - vy * math.sin(vehicle_angle),
                            center[1] + vx * math.sin(vehicle_angle)
                            + vy * math.cos(vehicle_angle),
                            block.vehicle.location[2],
                        )
                        transformed_vehicle_rotation = (
                            block.vehicle.rotation_degrees + vehicle_delta)
                        merge = math.dist(
                            pedestrian_location[:2], transformed_vehicle[:2]) < 0.05
                        if merge:
                            vehicle_radians = math.radians(
                                transformed_vehicle_rotation)
                            pedestrian_radians = math.radians(
                                pedestrian_rotation)
                            pole_x = (transformed_vehicle[0]
                                      - math.sin(vehicle_radians) * 0.16)
                            pole_y = (transformed_vehicle[1]
                                      + math.cos(vehicle_radians) * 0.16)
                            pedestrian_location = (
                                pole_x + math.sin(pedestrian_radians) * 0.16,
                                pole_y - math.cos(pedestrian_radians) * 0.16,
                                transformed_vehicle[2],
                            )
                    pedestrian_instance(f"{site.id} general", pedestrian_location,
                                        pedestrian_rotation,
                                        pedestrian_light, countdown_level,
                                        site.pedestrian_support_side, not merge,
                                        node.exterior_color)

    profile("JUNCTIONS")
    # Preserve the mature 650 mm total-width profile, rounded noses and the
    # short junction-side islands. These semantic islands also support signals.
    rendered_medians = []
    for item in compatibility_medians:
        edge = next((candidate for candidate in network.edges
                     if candidate.id == item.edge_id), None)
        if edge is not None and item.id == f"{edge.id}_median":
            path = paths[edge.id]
            start, end = feature_interval(edge, path, 0.15)
            for endpoint, node_id in (("start", edge.start), ("end", edge.end)):
                node = network.nodes[node_id]
                if node.kind != "priority_t_junction":
                    continue
                same_road_arms = [candidate for candidate in network.edges
                                  if node_id in {candidate.start, candidate.end}
                                  and candidate.road_id == edge.road_id]
                if edge.road_id and len(same_road_arms) == 2:
                    if endpoint == "start":
                        start = 0.0
                    else:
                        end = path.length
            if end - start <= 0.5:
                continue
            rounded_start = start > 1e-6
            rounded_end = end < path.length - 1e-6
            render_start = start + (item.cap_depth if rounded_start else 0.0)
            render_end = end - (item.cap_depth if rounded_end else 0.0)
            if render_end <= render_start:
                continue
            if any(has_extra_inbound_section(edge, endpoint)
                   for endpoint in ("from", "to")):
                _raised_variable_median(
                    item.id, paths[edge.id], edge, render_start, render_end,
                    item.height, median_concrete, rounded_start, rounded_end,
                    item.cap_depth)
                rendered_medians.append(item)
                continue
            if edge.geometry is not None and edge.geometry.kind != "line":
                _raised_median_along_path(
                    item.id, path, render_start, render_end,
                    item.width, item.height, median_concrete,
                    rounded_start, rounded_end, item.cap_depth)
                rendered_medians.append(item)
                continue
            item = replace(
                item,
                start=path.point_at_distance(render_start),
                end=path.point_at_distance(render_end),
                rounded_start=rounded_start,
                rounded_end=rounded_end,
            )
        _raised_median(item, median_concrete)
        rendered_medians.append(item)
    for item in median_devices:
        if item.device_type == "keep_left_sign":
            key = ("median island device", "procedural_keep_left")
            builder = lambda: create_keep_left_sign("Procedural Keep Left Prototype")
        else:
            key = ("median island device", "dual_warning_lamp")
            builder = lambda: create_dual_warning_lamp("Dual Warning Lamp Prototype")
        cached_asset_instance(
            key, builder, item.id, item.location, item.rotation_degrees)
    profile("MEDIANS")

    for item in planned_bicycles:
        edge = next(edge for edge in network.edges if edge.id == item.edge_id)
        base_path = paths[edge.id]
        path = (_ApproachOffsetPath(base_path, edge)
                if any(has_extra_inbound_section(edge, endpoint)
                       for endpoint in ("from", "to")) else base_path)
        mapped, station = _map_chord_point_to_path(
            network, edge, base_path, item.location)
        tangent = base_path.tangent_at_distance(station)
        centre = base_path.point_at_distance(station)
        normal = (-tangent[1], tangent[0])
        lateral = ((mapped[0] - centre[0]) * normal[0]
                   + (mapped[1] - centre[1]) * normal[1])
        if (edge.geometry is not None and edge.geometry.kind != "line") or \
                any(has_extra_inbound_section(edge, endpoint)
                    for endpoint in ("from", "to")):
            bicycle_marking_deformed(
                item.id, path, station, lateral, item.direction,
                item.width, white, bicycle_blue)
            continue
        else:
            location = path.offset_point(station, lateral)
            rotation = item.rotation_degrees
        bicycle_marking_instance(item.id, location, rotation,
                                 item.width, white, bicycle_blue)
    for item in plan_bicycle_junction_chevrons(network):
        instance = bicycle_blue_chevron_instance(
            item.id, item.location, item.rotation_degrees,
            item.width, bicycle_blue,
        )
        instance["junction_id"] = item.node_id
        instance["road_id"] = item.road_id
        instance["junction_bicycle_priority"] = item.priority
    for guide in plan_right_turn_guides(network):
        for index, (start, end) in enumerate(guide.dash_segments):
            obj = strip(
                f"{guide.id} dash {index + 1}", start, end, 0.13,
                ROAD_PAINT_CENTER_Z_M, white,
                thickness=ROAD_PAINT_THICKNESS_M,
                bevel=ROAD_PAINT_BEVEL_M,
            )
            obj["right_turn_guide"] = guide.id
        stop_obj = strip(
            f"{guide.id} waiting stop line",
            guide.stop_line_start, guide.stop_line_end, 0.30,
            ROAD_PAINT_CENTER_Z_M, white,
            thickness=ROAD_PAINT_THICKNESS_M,
            bevel=ROAD_PAINT_BEVEL_M,
        )
        stop_obj["right_turn_guide"] = guide.id
        stop_obj["right_turn_waiting_stop_line"] = True
    profile("BICYCLES")
    for light_id, _edge_id, _side, kind, location, rotation, lit in general_street_lights:
        street_light_instance(light_id, location, kind, lit, rotation)
    profile("STREET_LIGHTS")
    pedestrian_lights = [item for item in general_street_lights
                         if item[3] == "pedestrian"]
    tree_clearance_sq = STREET_LIGHT_TREE_CLEARANCE_M ** 2
    for item in planned_trees:
        edge = next(edge for edge in network.edges if edge.id == item.edge_id)
        base_path = paths[edge.id]
        path = (_ApproachOffsetPath(base_path, edge)
                if any(has_extra_inbound_section(edge, endpoint)
                       for endpoint in ("from", "to")) else base_path)
        mapped, station = _map_chord_point_to_path(
            network, edge, base_path, item.location)
        tree_side = 1 if item.side == "left" else -1
        if interval_hits_driveway(
                edge.id, tree_side, station, station, clearance=3.0):
            continue
        tangent = base_path.tangent_at_distance(station)
        centre = base_path.point_at_distance(station)
        normal = (-tangent[1], tangent[0])
        lateral = ((mapped[0] - centre[0]) * normal[0]
                   + (mapped[1] - centre[1]) * normal[1])
        location = (*path.offset_point(station, lateral), item.location[2])
        if any(
            light_edge_id == item.edge_id and light_side == item.side
            and ((location[0] - light_location[0]) ** 2
                 + (location[1] - light_location[1]) ** 2) < tree_clearance_sq
            for (_light_id, light_edge_id, light_side, _kind, light_location,
                 _rotation, _lit) in pedestrian_lights
        ):
            continue
        street_tree_instance(item.id, location, item.species, item.seed,
                             item.rotation_degrees)
    profile("TREES")
    def before_route_terminal(tile):
        for prefix, terminal, outward, extent in tactile_route_terminals:
            if not tile.id.startswith(prefix):
                continue
            distance = ((tile.center[0] - terminal[0]) * outward[0]
                        + (tile.center[1] - terminal[1]) * outward[1])
            if distance < extent:
                return False
        return True

    tactile_plans = [tile for tile in tactile_plans
                     if tile.kind != "guidance" or before_route_terminal(tile)]
    profile("TACTILE_FILTER")
    tactile_plans = _trim_continuous_tactile_joints(tactile_plans)
    tactile_plans = _non_overlapping_tactile(tactile_plans)
    profile("TACTILE_OVERLAP")
    _tactile_paving_mesh(tactile_plans, tactile)
    # Detail placement uses the same longitudinal clearance solver as the
    # existing roadside equipment. No scene coordinates or extra UI controls.
    from .urban_details import utility, repair, SurfaceReservations
    bpy.context.view_layer.update()
    surface_reservations = SurfaceReservations(bpy.context.scene,(white,orange,bicycle_blue))
    cabinet_candidates = {}
    utility_positions = []
    for edge in network.edges:
        if edge.sidewalks != 'both':
            continue
        base_path = paths[edge.id]
        path = (_ApproachOffsetPath(base_path, edge)
                if any(has_extra_inbound_section(edge, endpoint)
                       for endpoint in ('from','to')) else base_path)
        frame = street_frames[edge.id]
        start, end = feature_interval(edge, path, 6.0)
        half = road_half_width_m(edge)
        for side in (-1,1):
            for station, index in frame.positions(start, end, 28.0,
                    seed_for(side,'drains'), .10):
                if interval_hits_driveway(edge.id, side, station-.3, station+.3, 1.0):
                    continue
                station=surface_reservations.choose(path,station,side*(half-.28),.55,.55,start,end,
                    lambda s:not interval_hits_driveway(edge.id,side,s-.3,s+.3,1.0))
                if station is None:continue
                point = path.offset_point(station,side*(half-.28))
                tangent = path.tangent_at_distance(station)
                heading = math.degrees(math.atan2(tangent[1],tangent[0]))
                utility('drain',f'{frame.identity} {side} drain {index}',(*point,0),heading)
                utility_positions.append(point)
            for station,index in frame.positions(start+2.5,end-2.5,63.0,
                    seed_for(side,'service covers'),.16):
                if interval_hits_driveway(edge.id,side,station-2,station+2,1.0):
                    continue
                lateral = side*(half-1.55)
                key=seed_for(frame.identity,index,side,'repair')
                repair_length=1.3+(key%5)*.32
                station=surface_reservations.choose(path,station,lateral,repair_length,1.12,start,end,
                    lambda s:not interval_hits_driveway(edge.id,side,s-2,s+2,1.0))
                if station is None:continue
                point = path.offset_point(station,lateral)
                if any(math.dist(point,p)<1.0 for p in utility_positions):
                    continue
                tangent = path.tangent_at_distance(station)
                heading=math.degrees(math.atan2(tangent[1],tangent[0]))
                key=seed_for(frame.identity,index,side,'repair')
                utility('cover',f'{frame.identity} {side} utility cover {index}',(*point,0),heading)
                utility_positions.append(point)
                repair(f'{frame.identity} {side} cover reinstatement {index}',
                       path,station,lateral,1.3+(key%5)*.32,1.12,key)
        # Put the cabinet in the furniture strip, between hedge and tactile
        # route. The 0.50 m deep foundation clears the 0.85 m planting bed by
        # 0.35 m; the door faces the walking side. Keep widened-road eligibility.
        cabinet_offset = 0.33 + 0.85 + 0.35 + 0.50 * 0.5
        if _sidewalk_width_for_edge(edge) >= 5.0 and end-start > 3.0:
            for endpoint in (edge.start,edge.end):
                nearest=nearest_road_junction(edge,endpoint)
                if nearest is None:continue
                _,arm,_arms=nearest
                node_id = arm.node_id
                if network.nodes[node_id].kind not in {'signalized_cross','signalized_t_junction'}:continue
                station=start+1.0 if endpoint==edge.start else end-1.0
                for side in (-1,1):
                    if interval_hits_driveway(edge.id,side,station-.5,station+.5,2.0):continue
                    point=path.offset_point(station,side*(half+cabinet_offset))
                    # Foundation half-diagonal .455 + tile half-diagonal .213
                    # + at least .30 m clearance, including transverse routes.
                    if any(math.dist(point,t.center)<1.0 for t in tactile_plans):continue
                    tangent=path.tangent_at_distance(station)
                    heading=math.degrees(math.atan2(tangent[1],tangent[0]))+(180 if side>0 else 0)
                    cabinet_candidates.setdefault(node_id,[]).append((math.dist(point,network.nodes[node_id].position),point,heading))
    for node_id,candidates in sorted(cabinet_candidates.items()):
        _,point,heading=min(candidates)
        utility('cabinet',node_id+' signal control cabinet',(*point,SIDEWALK_TOP_Z_M),heading)
    profile("URBAN_DETAILS")
    profile("FINAL_ASSETS")
    if os.environ.get("ROAD_GENERATOR_PROFILE") == "1":
        print(f"PROFILE_GENERAL_SCENE_SECONDS={time.perf_counter() - started:.6f}")
    from .subway import add_subway_entrances
    add_subway_entrances(network)
    return collection
