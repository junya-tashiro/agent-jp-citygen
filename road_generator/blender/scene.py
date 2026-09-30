import math
import os
import random
from pathlib import Path
import time
import zlib

import bpy
import bmesh
from mathutils import Vector

from .direct_assets import (
    bicycle_blue_chevron_instance, bicycle_marking_instance,
    cached_asset_instance, create_dual_warning_lamp,
    create_keep_left_sign, create_road_sign, create_road_sign_stack, guardrail_instance,
    pedestrian_instance, planting_instance, reflector_pole_instance,
    lane_use_arrow_instance, sidewalk_brick_surface, street_light_instance,
    street_tree_instance, vehicle_instance,
    prewarm_cached_asset, prewarm_roadside_components, prewarm_signal_components,
    prewarm_street_light_components,
)
from .markings import crosswalk, stop_line
from road_generator.core.planner import (
    CURB_BLOCK_JOINT_M, CURB_BLOCK_LENGTH_M, CURB_ROAD_APRON_M, CURB_WIDTH_M,
    CURB_TOP_Z_M, JUNCTION_CENTER_MARKING_WIDTH_M, LANE_WIDTH_M,
    PLANTING_SOIL_TOP_Z_M, ROAD_MARKING_CURB_CLEARANCE_M,
    SIDEWALK_CORNER_RADIUS_M,
    SIDEWALK_HEIGHT_DELTA_M, SIDEWALK_INTERSECTION_MARGIN_M, SIDEWALK_TOP_Z_M,
    SIDEWALK_WIDTH_M, SIGNAL_BASE_Z_M, STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M,
    approach_lane_arrow_kinds, compatibility_approach_map,
    connected_approaches, effective_vehicle_arrow,
    plan_bicycle_junction_chevrons, plan_right_turn_guides,
    longitudinal_marking_trims,
    lane_separator_solid_interval,
    road_widths_at_node, stop_approach_has_crosswalk_sign,
    carriageway_lateral_m, road_half_width_m, has_extra_inbound_lane,
)
from .primitives import (
    ORANGE_PAINT_CENTER_Z_M, ROAD_PAINT_BEVEL_M, ROAD_PAINT_CENTER_Z_M,
    ROAD_PAINT_THICKNESS_M,
    apply_surface_relief, cube, cylinder, dashed_line, extruded_polygons, look_at, material,
    polygon, polygon_batch, road_marking_material, strip, torus, weathered_material,
)


def _asphalt_material():
    from asset_library.shared.surfaces import asphalt_material
    mat = asphalt_material()
    apply_surface_relief(mat, "road")
    return mat


def _sidewalk_brick_palette():
    """Five fixed muted clay/concrete colours from Japanese woven paving."""
    if os.environ.get("ROAD_GENERATOR_SIDEWALK_FINISH", "brick").lower() == "concrete":
        return ()
    specs = (
        ("muted brick", (0.155, 0.112, 0.095), (0.315, 0.235, 0.205)),
        ("muted clay", (0.135, 0.100, 0.087), (0.275, 0.210, 0.185)),
        ("mushroom taupe", (0.125, 0.115, 0.108), (0.265, 0.245, 0.230)),
        ("deep brown grey", (0.085, 0.075, 0.070), (0.205, 0.185, 0.175)),
        ("pale grey clay", (0.185, 0.165, 0.150), (0.365, 0.325, 0.295)),
    )
    return tuple(weathered_material(
        f"Sidewalk brick {label}", dark, light, 0.86, 22.0, "paver")
        for label, dark, light in specs)


def _vehicle_horizontal_extension(network, site):
    """Return one canonical arm extension for prewarm and final placement."""
    node = network.nodes[site.node_id]
    if node.kind not in {"signalized_cross", "signalized_t_junction"}:
        return 1.5
    approach = next((key for key in ("west", "south", "east", "north")
                     if site.id.endswith(f"_{key}_vehicle")), None)
    mapped = compatibility_approach_map(network, node.id)
    edge = next((candidate for candidate in network.edges
                 if mapped.get(candidate.id) == approach), None)
    if edge is None:
        lanes_each_way = 1
    else:
        endpoint = "from" if edge.start == node.id else "to"
        lanes_each_way = edge.lanes_each_way + (
            1 if has_extra_inbound_lane(edge, endpoint) else 0)
    if site.support_mode == "median_right":
        return max(0.0, 3.25 * lanes_each_way * 0.5 - 2.05)
    roadside_pole_inward_shift = 2.15 - 0.42
    one_lane_extension = 1.5 - roadside_pole_inward_shift
    return max(one_lane_extension,
               one_lane_extension + 3.25 * (lanes_each_way - 1) / 2)


def _road_crosswalk_diamond(name, center, heading_degrees, mat):
    """Paint one 5.0 x 1.5 m advance-crosswalk diamond."""
    heading = math.radians(heading_degrees)
    forward = Vector((math.cos(heading), math.sin(heading)))
    left = Vector((-forward.y, forward.x))
    origin = Vector(center)
    half_length, half_width, stroke = 2.5, 0.75, 0.25
    outer = (origin + forward * half_length, origin + left * half_width,
             origin - forward * half_length, origin - left * half_width)
    # Offset every side inward by the stated paint width.  Four ring faces
    # meet exactly at their vertices, unlike overlapping rotated rectangles.
    inset_scale = 1.0 - stroke * math.hypot(
        1.0 / half_length, 1.0 / half_width)
    inner = tuple(origin + (point - origin) * inset_scale for point in outer)
    vertices = [(point.x, point.y, ROAD_PAINT_CENTER_Z_M)
                for point in outer + inner]
    faces = [(index, (index + 1) % 4, 4 + (index + 1) % 4, 4 + index)
             for index in range(4)]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj["marking_kind"] = "advance_crosswalk_diamond"
    obj["overall_length_m"] = 5.0
    obj["overall_width_m"] = 1.5
    obj["stroke_width_m"] = stroke
    solidify = obj.modifiers.new("Road paint thickness", "SOLIDIFY")
    solidify.thickness = ROAD_PAINT_THICKNESS_M
    solidify.offset = -0.5


def _road_rectangle(name, start, end, width, asphalt):
    a = Vector(start)
    b = Vector(end)
    delta = b - a
    center = (a + b) * 0.5
    obj = cube(name, (center.x, center.y, -0.045), (delta.length, width, 0.09), asphalt)
    obj.rotation_euler[2] = math.atan2(delta.y, delta.x)
    return obj


def _straight_curb_blocks(name, start, end, curb_material, roadward_sign=1.0,
                          lowered_crossing_distances=(),
                          lowered_driveway_distances=()):
    """Build a batched row of rounded 400mm kerb blocks and flush apron."""
    a = Vector(start)
    b = Vector(end)
    delta = b - a
    length = delta.length
    if length <= 0.01:
        return None
    direction = delta.normalized()
    normal = Vector((-direction.y, direction.x)) * roadward_sign
    count = max(1, round(length / CURB_BLOCK_LENGTH_M))
    pitch = length / count
    block_length = max(0.01, pitch - CURB_BLOCK_JOINT_M)
    vertices, faces = [], []
    apron_vertices, apron_faces = [], []
    foundation_vertices, foundation_faces = [], []

    def cuboid(center, along, across, z0, z1,
               target_vertices=vertices, target_faces=faces,
               top_start=None, top_end=None):
        first = len(target_vertices)
        u = direction * (along * 0.5)
        v = normal * (across * 0.5)
        corners = (center - u - v, center + u - v, center + u + v, center - u + v)
        target_vertices.extend((point.x, point.y, z0) for point in corners)
        start_z = z1 if top_start is None else top_start
        end_z = z1 if top_end is None else top_end
        target_vertices.extend((
            (corners[0].x, corners[0].y, start_z),
            (corners[1].x, corners[1].y, end_z),
            (corners[2].x, corners[2].y, end_z),
            (corners[3].x, corners[3].y, start_z),
        ))
        target_faces.extend(tuple(first + i for i in face) for face in (
            (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
            (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        ))

    foundation_center = (a + b) * 0.5 + normal * (CURB_ROAD_APRON_M * 0.5)
    cuboid(foundation_center, length, CURB_WIDTH_M + CURB_ROAD_APRON_M,
           -0.026, -0.002, foundation_vertices, foundation_faces)
    lowered_sections = (tuple((item, 3.2) for item in lowered_crossing_distances)
                        + tuple((item, 6.4) for item in lowered_driveway_distances))
    def height_at(station):
        height = CURB_TOP_Z_M
        for center, flat_width in lowered_sections:
            offset = abs(station - center)
            flat_half = flat_width * 0.5
            if offset <= flat_half:
                candidate = SIDEWALK_TOP_Z_M
            elif offset < flat_half + CURB_BLOCK_LENGTH_M:
                factor = (offset - flat_half) / CURB_BLOCK_LENGTH_M
                candidate = (SIDEWALK_TOP_Z_M
                             + (CURB_TOP_Z_M - SIDEWALK_TOP_Z_M) * factor)
            else:
                continue
            height = min(height, candidate)
        return height
    top_profiles = [(height_at(index * pitch),
                     height_at((index + 1) * pitch))
                    for index in range(count)]

    for index in range(count):
        center = a + direction * ((index + 0.5) * pitch)
        cuboid(center, block_length, CURB_WIDTH_M, 0.0, CURB_TOP_Z_M,
               top_start=top_profiles[index][0], top_end=top_profiles[index][1])
        apron_width = CURB_ROAD_APRON_M - CURB_BLOCK_JOINT_M
        apron_center = center + normal * (
            CURB_WIDTH_M * 0.5 + CURB_BLOCK_JOINT_M + apron_width * 0.5)
        cuboid(apron_center, block_length, apron_width, -0.025, 0.0005,
               apron_vertices, apron_faces)
    mesh = bpy.data.meshes.new(name + " block mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(curb_material)
    obj = bpy.data.objects.new(name + " blocks", mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Rounded stone block edges", "BEVEL")
    bevel.affect = "EDGES"
    # Ignore the shallow internal edges that tessellate each curved face;
    # beveling those edges produces a false continuous sheet over the top.
    # The approximately 90-degree external block edges remain selected.
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(20.0)
    bevel.width = 0.01
    bevel.segments = 3
    obj["block_nominal_length_m"] = CURB_BLOCK_LENGTH_M
    obj["road_apron_width_m"] = CURB_ROAD_APRON_M
    obj["curb_grid_start"] = (a.x, a.y)
    obj["curb_grid_end"] = (b.x, b.y)
    obj["curb_grid_count"] = count
    obj["curb_grid_pitch_m"] = pitch
    obj["lowered_crossing_count"] = len(lowered_crossing_distances)
    obj["lowered_driveway_count"] = len(lowered_driveway_distances)
    foundation_mesh = bpy.data.meshes.new(name + " buried foundation mesh")
    foundation_mesh.from_pydata(foundation_vertices, [], foundation_faces)
    foundation_mesh.materials.append(curb_material)
    foundation_obj = bpy.data.objects.new(name + " buried foundation", foundation_mesh)
    bpy.context.collection.objects.link(foundation_obj)
    foundation_obj["buried_below_road_surface"] = True
    apron_mesh = bpy.data.meshes.new(name + " flush road block mesh")
    apron_mesh.from_pydata(apron_vertices, [], apron_faces)
    apron_mesh.materials.append(curb_material)
    apron_obj = bpy.data.objects.new(name + " flush road-level blocks", apron_mesh)
    bpy.context.collection.objects.link(apron_obj)
    apron_bevel = apron_obj.modifiers.new("Subtle flush block edges", "BEVEL")
    apron_bevel.width = 0.00075
    apron_bevel.segments = 2
    apron_obj["block_nominal_length_m"] = CURB_BLOCK_LENGTH_M
    apron_obj["road_apron_width_m"] = CURB_ROAD_APRON_M
    return obj


def _sidewalk_pair(name, start, end, road_width, sidewalk_width, sidewalk, curb,
                   planting_by_side=None, curb_rows=None, crosswalks=(),
                   crossing_centers=None, brick_materials=(),
                   driveways_by_side=None):
    a = Vector(start)
    b = Vector(end)
    delta = b - a
    length = delta.length
    direction = delta.normalized()
    normal = Vector((-direction.y, direction.x))
    center = (a + b) * 0.5
    angle = math.atan2(delta.y, delta.x)
    planting_by_side = planting_by_side or {}
    driveways_by_side = driveways_by_side or {}
    # The rounded corner is centred one corner radius beyond the road edge.
    # Its pavement fan therefore reaches this far beyond the nominal straight
    # sidewalk outer edge. Extend only the property-side edge of straight runs
    # so both outlines meet without a visible step at the tangent point.
    outer_extension = SIDEWALK_CORNER_RADIUS_M - sidewalk_width

    lowered_crossing_distances = []
    # General geometry supplies actual world-space crossing centres.  The
    # legacy plans carry only cardinal x/y semantics and therefore cannot
    # identify a crossing after its approach has been rotated.
    candidates = (() if crossing_centers is None
                  else tuple(crossing_centers))
    if crossing_centers is None:
        expected_walking_axis = "y" if abs(direction.x) > 0.5 else "x"
        candidates = tuple(crossing.center for crossing in crosswalks
                           if crossing.walking_axis == expected_walking_axis)
    for crossing_center in candidates:
        relative = Vector(crossing_center) - a
        if abs(relative.dot(normal)) > 0.05:
            continue
        projection = relative.dot(direction)
        if -2.5 <= projection <= length + 2.5:
            lowered_crossing_distances.append(projection)

    def slab(label, longitudinal_start, longitudinal_end, side_sign,
             lateral_center, width,
             z=SIDEWALK_TOP_Z_M - 0.09, height=0.18, bevel=0.0):
        slab_length = longitudinal_end - longitudinal_start
        if slab_length <= 0.01 or width <= 0.01:
            return
        slab_center = (a + direction * ((longitudinal_start + longitudinal_end) * 0.5)
                       + normal * side_sign * lateral_center)
        has_brick_surface = (
            brick_materials
            and abs(z + height * 0.5 - SIDEWALK_TOP_Z_M) < 1e-5
            and "foundation" not in label
        )
        # The concrete is now the bedding layer, not a second visible finish.
        # Sink its top by the brick thickness; otherwise it fills the rounded
        # shoulders and makes the bevel entirely invisible.
        brick_thickness = 0.012 if has_brick_surface else 0.0
        obj = cube(label, (slab_center.x, slab_center.y, z - brick_thickness * 0.5),
                   (slab_length, width, height - brick_thickness), sidewalk, bevel)
        obj.rotation_euler[2] = angle
        if has_brick_surface:
            sidewalk_brick_surface(
                f"{label} brick paving", slab_center, slab_length, width,
                angle, SIDEWALK_TOP_Z_M + 0.0005, brick_materials)

    for side_name, side_sign in (("right", -1), ("left", 1)):
        curb_offset = normal * side_sign * (road_width * 0.5 + 0.07)
        curb_start = a + curb_offset
        curb_end = b + curb_offset
        curb_obj = _straight_curb_blocks(
            f"{name} {side_name} curb", curb_start, curb_end,
            curb, roadward_sign=-side_sign,
            lowered_crossing_distances=lowered_crossing_distances,
            lowered_driveway_distances=driveways_by_side.get(side_name, ()))
        if curb_rows is not None and curb_obj is not None:
            curb_rows.append(curb_obj)

        planting = planting_by_side.get(side_name)
        # The raised sidewalk starts behind the kerb instead of overlapping
        # it.  Its outside edge remains unchanged, making the 140 mm kerb a
        # visibly independent row of stone blocks.
        pavement_width = sidewalk_width - CURB_WIDTH_M + outer_extension
        sidewalk_center = (road_width * 0.5 + CURB_WIDTH_M
                           + pavement_width * 0.5)
        if planting is None:
            slab(f"{name} {side_name} sidewalk", 0.0, length, side_sign,
                 sidewalk_center, pavement_width)
            continue

        planting_start = max(0.0, min(length, (Vector(planting.start) - a).dot(direction)))
        planting_end = max(0.0, min(length, (Vector(planting.end) - a).dot(direction)))
        if planting_end < planting_start:
            planting_start, planting_end = planting_end, planting_start
        if planting_end - planting_start <= 0.01:
            slab(f"{name} {side_name} sidewalk", 0.0, length, side_sign,
                 sidewalk_center, pavement_width)
            continue

        slab(f"{name} {side_name} sidewalk before planting", 0.0, planting_start,
             side_sign, sidewalk_center, pavement_width)
        slab(f"{name} {side_name} sidewalk after planting", planting_end, length,
             side_sign, sidewalk_center, pavement_width)

        # Keep a continuous low concrete foundation below the recess. The
        # visible top surface is split into a road-side margin, a soil bed and
        # a remaining pedestrian strip; the original sidewalk footprint is intact.
        slab(f"{name} {side_name} planting foundation", planting_start, planting_end,
             side_sign, sidewalk_center, pavement_width,
             z=0.035 + SIDEWALK_HEIGHT_DELTA_M, height=0.07,
             bevel=0.012)
        near_margin = 0.33
        back_width = sidewalk_width + outer_extension - near_margin - planting.width
        visible_near_margin = near_margin - CURB_WIDTH_M
        slab(f"{name} {side_name} planting road margin", planting_start, planting_end,
             side_sign, road_width * 0.5 + CURB_WIDTH_M
             + visible_near_margin * 0.5, visible_near_margin)
        slab(f"{name} {side_name} planting pedestrian margin", planting_start,
             planting_end, side_sign,
             road_width * 0.5 + near_margin + planting.width + back_width * 0.5,
             back_width)
        # A driveway removes the planting bed but does not interrupt the
        # paving. Fill only the normally recessed soil-width strip; the two
        # existing pedestrian bands remain shared, so additional cutouts do
        # not duplicate the full sidewalk mesh.
        for driveway_index, driveway in enumerate(
                driveways_by_side.get(side_name, ())):
            fill_start = max(planting_start, driveway - 3.6)
            fill_end = min(planting_end, driveway + 3.6)
            if fill_end - fill_start <= 0.01:
                continue
            slab(f"{name} {side_name} driveway fill {driveway_index + 1}",
                 fill_start, fill_end, side_sign,
                 road_width * 0.5 + near_margin + planting.width * 0.5,
                 planting.width)


def _curb_parking_stripes(item, paint, curb_rows=()):
    """Paint alternating 1.2 m orange dashes on the curb top only."""
    stripe_length = 1.20
    gap_length = 1.20
    # Inset the paint onto the rounded top face of each block. A flat cuboid
    # bevel was thickness-limited and left square-looking corners floating
    # over the kerb chamfer, so use an explicit rounded plan outline instead.
    curb_width = CURB_WIDTH_M - 0.02
    visible_curb_top = CURB_TOP_Z_M
    if item.curve_center is not None:
        total_length = abs(math.radians(item.curve_sweep_degrees) * item.curve_radius)
        count = math.floor((total_length + gap_length) / (stripe_length + gap_length))
        if count < 1:
            return
        occupied = count * stripe_length + (count - 1) * gap_length
        margin = (total_length - occupied) * 0.5
        direction_sign = 1.0 if item.curve_sweep_degrees >= 0 else -1.0
        for index in range(count):
            stripe_start = margin + index * (stripe_length + gap_length)
            for piece in range(3):
                piece_start = stripe_start + piece * CURB_BLOCK_LENGTH_M + CURB_BLOCK_JOINT_M * 0.5
                piece_end = stripe_start + (piece + 1) * CURB_BLOCK_LENGTH_M - CURB_BLOCK_JOINT_M * 0.5
                angle0 = item.curve_start_degrees + direction_sign * math.degrees(piece_start / item.curve_radius)
                angle1 = item.curve_start_degrees + direction_sign * math.degrees(piece_end / item.curve_radius)
                _annular_sector(
                    f"{item.id} curved top {index + 1:02d}-{piece + 1}",
                    item.curve_center, item.curve_radius - curb_width * 0.5,
                    item.curve_radius + curb_width * 0.5, angle0, angle1,
                    visible_curb_top + ROAD_PAINT_CENTER_Z_M, paint, 4,
                )
        return
    a = Vector(item.start)
    b = Vector(item.end)
    delta = b - a
    length = delta.length
    direction = delta.normalized()
    # Locate the actual curb row. Paint plans can be trimmed further than the
    # curb itself (for example around a crossing), so recomputing a grid from
    # the shorter paint span changes both pitch and phase and accumulates drift.
    midpoint = (a + b) * 0.5
    best = None
    for row in curb_rows:
        row_a = Vector(row["curb_grid_start"])
        row_b = Vector(row["curb_grid_end"])
        row_delta = row_b - row_a
        row_length = row_delta.length
        if row_length <= 0.01:
            continue
        row_direction = row_delta.normalized()
        if abs(row_direction.dot(direction)) < 0.9999:
            continue
        projection = (midpoint - row_a).dot(row_direction)
        closest = row_a + row_direction * max(0.0, min(row_length, projection))
        distance = (midpoint - closest).length
        if best is None or distance < best[0]:
            best = (distance, row, row_a, row_direction)
    if best is None or best[0] > 0.03:
        return
    _, row, row_a, row_direction = best
    block_count = int(row["curb_grid_count"])
    pitch = float(row["curb_grid_pitch_m"])
    item_min = min((a - row_a).dot(row_direction),
                   (b - row_a).dot(row_direction))
    item_max = max((a - row_a).dot(row_direction),
                   (b - row_a).dot(row_direction))
    across = Vector((-direction.y, direction.x))

    def rounded_top_points(center, along, width, radius=0.01):
        points = []
        half_along, half_width = along * 0.5, width * 0.5
        for cx, cy, start_angle in (
                (half_along - radius, half_width - radius, 0.0),
                (-half_along + radius, half_width - radius, 90.0),
                (-half_along + radius, -half_width + radius, 180.0),
                (half_along - radius, -half_width + radius, 270.0)):
            for step in range(5):
                theta = math.radians(start_angle + step * 22.5)
                local = direction * (cx + math.cos(theta) * radius)
                local += across * (cy + math.sin(theta) * radius)
                points.append((center.x + local.x, center.y + local.y))
        return points

    painted_index = 0
    painted_polygons = []
    for block_index in range(block_count):
        center_distance = (block_index + 0.5) * pitch
        if center_distance < item_min or center_distance > item_max:
            continue
        if block_index % 6 >= 3:
            continue
        painted_index += 1
        piece_length = pitch - CURB_BLOCK_JOINT_M - 0.02
        center = row_a + row_direction * center_distance
        painted_polygons.append(
            rounded_top_points(center, piece_length, curb_width))
    if painted_polygons:
        obj = polygon_batch(
            f"{item.id} painted curb tops", painted_polygons,
            visible_curb_top + ROAD_PAINT_THICKNESS_M * 0.5, paint)
        obj["painted_curb_block_count"] = painted_index


def _raised_median(item, concrete):
    """Build one solid median with a top-only bevel and optional round nose."""
    start = Vector(item.start)
    end = Vector(item.end)
    axis = (end - start).normalized()
    across = Vector((-axis.y, axis.x))
    length = (end - start).length
    radius = item.width * 0.5
    cap_depth = item.cap_depth
    bevel = min(0.035, item.height * 0.25, radius * 0.25)

    def outline(r, start_x, end_x):
        points = [(start_x, r), (end_x, r)]
        segments = 16
        cap_x = cap_depth * r / radius
        if item.rounded_end:
            points.extend((end_x + math.cos(math.pi * 0.5 - math.pi * i / segments) * cap_x,
                           math.sin(math.pi * 0.5 - math.pi * i / segments) * r)
                          for i in range(1, segments + 1))
        else:
            points.append((end_x, -r))
        points.append((start_x, -r))
        if item.rounded_start:
            points.extend((start_x + math.cos(-math.pi * 0.5 - math.pi * i / segments) * cap_x,
                           math.sin(-math.pi * 0.5 - math.pi * i / segments) * r)
                          for i in range(1, segments + 1))
        return tuple(points)

    outer = outline(radius, 0.0, length)
    top = outline(radius - bevel,
                  0.0 if item.rounded_start else bevel,
                  length if item.rounded_end else length - bevel)
    vertices = []
    for z, shape in ((0.0, outer), (item.height - bevel, outer), (item.height, top)):
        vertices.extend(tuple(start + axis * x + across * y) + (z,) for x, y in shape)
    count = len(outer)
    faces = [tuple(range(count)), tuple(reversed(range(2 * count, 3 * count)))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
        faces.append((count + index, count + nxt,
                      2 * count + nxt, 2 * count + index))
    mesh = bpy.data.meshes.new(item.id + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(concrete)
    obj = bpy.data.objects.new(item.id, mesh)
    bpy.context.collection.objects.link(obj)
    obj["top_bevel_m"] = bevel
    obj["bottom_edge_beveled"] = False
    return obj


def _annular_sector(name, center, inner_radius, outer_radius, start_angle,
                    end_angle, z, mat, steps):
    """Create a flat annular sector without relying on a slow boolean cut."""
    vertices = []
    for index in range(steps + 1):
        angle = math.radians(start_angle + (end_angle - start_angle) * index / steps)
        direction = Vector((math.cos(angle), math.sin(angle)))
        inner = Vector(center) + direction * inner_radius
        outer = Vector(center) + direction * outer_radius
        vertices.extend(((inner.x, inner.y, z), (outer.x, outer.y, z)))
    faces = []
    for index in range(steps):
        base = index * 2
        faces.append((base, base + 1, base + 3, base + 2))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _planting_retaining_walls(item, sidewalk_material):
    """Close the exposed 50mm recess between sidewalk and planting soil."""
    wall_thickness = 0.025
    wall_height = SIDEWALK_TOP_Z_M - PLANTING_SOIL_TOP_Z_M
    wall_z = (SIDEWALK_TOP_Z_M + PLANTING_SOIL_TOP_Z_M) * 0.5
    if wall_height <= 0.0:
        return

    if item.curve_center is None:
        start = Vector(item.start)
        end = Vector(item.end)
        delta = end - start
        length = delta.length
        if length <= 0.01:
            return
        direction = delta.normalized()
        normal = Vector((-direction.y, direction.x))
        angle = math.atan2(direction.y, direction.x)
        midpoint = (start + end) * 0.5
        for side, sign in (("inner", -1.0), ("outer", 1.0)):
            center = midpoint + normal * sign * item.width * 0.5
            wall = cube(f"{item.id} {side} planting wall",
                        (center.x, center.y, wall_z),
                        (length, wall_thickness, wall_height), sidewalk_material)
            wall.rotation_euler[2] = angle
        for label, point in (("start", start), ("end", end)):
            wall = cube(f"{item.id} {label} planting wall",
                        (point.x, point.y, wall_z),
                        (wall_thickness, item.width, wall_height), sidewalk_material)
            wall.rotation_euler[2] = angle
        return

    center = Vector(item.curve_center)
    start_angle = item.curve_start_degrees
    end_angle = start_angle + item.curve_sweep_degrees
    steps = max(16, math.ceil(abs(item.curve_sweep_degrees) / 3.0))

    def curved_wall(label, radius):
        vertices = []
        for z in (PLANTING_SOIL_TOP_Z_M, SIDEWALK_TOP_Z_M):
            for current_radius in (radius - wall_thickness * 0.5,
                                   radius + wall_thickness * 0.5):
                for index in range(steps + 1):
                    angle = math.radians(
                        start_angle + (end_angle - start_angle) * index / steps)
                    point = center + Vector((math.cos(angle), math.sin(angle))) * current_radius
                    vertices.append((point.x, point.y, z))
        ring = steps + 1
        faces = []
        for index in range(steps):
            ti, to = index, ring + index
            bi, bo = ring * 2 + index, ring * 3 + index
            faces.extend(((ti, ti + 1, to + 1, to),
                          (bi, bo, bo + 1, bi + 1),
                          (ti, bi, bi + 1, ti + 1),
                          (to, to + 1, bo + 1, bo)))
        mesh = bpy.data.meshes.new(f"{item.id} {label} planting wall mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(sidewalk_material)
        obj = bpy.data.objects.new(f"{item.id} {label} planting wall", mesh)
        bpy.context.collection.objects.link(obj)

    curved_wall("inner", item.curve_radius - item.width * 0.5)
    curved_wall("outer", item.curve_radius + item.width * 0.5)
    for label, degrees in (("start", start_angle), ("end", end_angle)):
        angle = math.radians(degrees)
        point = center + Vector((math.cos(angle), math.sin(angle))) * item.curve_radius
        wall = cube(f"{item.id} {label} planting wall",
                    (point.x, point.y, wall_z),
                    (item.width, wall_thickness, wall_height), sidewalk_material)
        wall.rotation_euler[2] = angle


def _curved_curb_blocks(name, center, start_angle, end_angle, radius, curb_material):
    """Batched curved kerb blocks plus the 150mm flush road-side apron."""
    centerline_radius = radius - CURB_WIDTH_M * 0.5
    arc_length = abs(math.radians(end_angle - start_angle) * centerline_radius)
    count = max(1, round(arc_length / CURB_BLOCK_LENGTH_M))
    angle_pitch = (end_angle - start_angle) / count
    # Match the narrow 2 mm joints used by the straight kerb blocks.
    raised_curved_joint = CURB_BLOCK_JOINT_M
    apron_curved_joint = CURB_BLOCK_JOINT_M
    raised_gap_angle = math.degrees(raised_curved_joint / centerline_radius)
    apron_centerline_radius = radius + CURB_ROAD_APRON_M * 0.5
    apron_gap_angle = math.degrees(apron_curved_joint / apron_centerline_radius)
    vertices, faces = [], []
    apron_vertices, apron_faces = [], []
    foundation_vertices, foundation_faces = [], []

    def annular_volume(inner_radius, outer_radius, angle0, angle1, z0, z1,
                       target_vertices=vertices, target_faces=faces,
                       steps_override=None):
        steps = (steps_override if steps_override is not None
                 else max(2, round(abs(angle1 - angle0) / 4.0)))
        first = len(target_vertices)
        for z in (z0, z1):
            for index in range(steps + 1):
                angle = math.radians(angle0 + (angle1 - angle0) * index / steps)
                direction = Vector((math.cos(angle), math.sin(angle)))
                for current_radius in (inner_radius, outer_radius):
                    point = Vector(center) + direction * current_radius
                    target_vertices.append((point.x, point.y, z))
        ring = (steps + 1) * 2
        for level in (0, 1):
            base = first + level * ring
            for index in range(steps):
                offset = base + index * 2
                face = (offset, offset + 1, offset + 3, offset + 2)
                target_faces.append(face if level else tuple(reversed(face)))
        for index in range(steps):
            low = first + index * 2
            high = first + ring + index * 2
            nxt_low = low + 2
            nxt_high = high + 2
            target_faces.extend(((low, nxt_low, nxt_high, high),
                                 (low + 1, high + 1, nxt_high + 1, nxt_low + 1)))
        target_faces.extend(((first, first + ring, first + ring + 1, first + 1),
                             (first + steps * 2, first + steps * 2 + 1,
                              first + ring + steps * 2 + 1,
                              first + ring + steps * 2)))

    # On a convex sidewalk corner the carriageway is outside the arc (larger
    # radius), unlike the roadward normal of a straight kerb.  The foundation
    # therefore spans from the pavement-side edge of the raised kerb through
    # the flush apron outside it.
    annular_volume(radius - CURB_WIDTH_M, radius + CURB_ROAD_APRON_M,
                   start_angle, end_angle, -0.026, -0.002,
                   foundation_vertices, foundation_faces)
    for index in range(count):
        block_start = start_angle + index * angle_pitch
        block_end = start_angle + (index + 1) * angle_pitch
        raised_angle0 = block_start + math.copysign(
            raised_gap_angle * 0.5, angle_pitch)
        raised_angle1 = block_end - math.copysign(
            raised_gap_angle * 0.5, angle_pitch)
        apron_angle0 = block_start + math.copysign(
            apron_gap_angle * 0.5, angle_pitch)
        apron_angle1 = block_end - math.copysign(
            apron_gap_angle * 0.5, angle_pitch)
        annular_volume(radius - CURB_WIDTH_M, radius,
                       raised_angle0, raised_angle1, 0.0, CURB_TOP_Z_M,
                       steps_override=1)
        # Keep the flush road-side stone as an explicit segmented annular
        # block row.  Its top is lifted only by a rendering tolerance above
        # asphalt, avoiding z-fighting while remaining road-level in scale.
        annular_volume(radius + CURB_BLOCK_JOINT_M,
                       radius + CURB_ROAD_APRON_M,
                       apron_angle0, apron_angle1, -0.025, 0.0015,
                       apron_vertices, apron_faces, steps_override=1)
    mesh = bpy.data.meshes.new(name + " curved block mesh")
    mesh.from_pydata(vertices, [], faces)
    normal_mesh = bmesh.new()
    normal_mesh.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(normal_mesh, faces=normal_mesh.faces)
    normal_mesh.to_mesh(mesh)
    normal_mesh.free()
    mesh.materials.append(curb_material)
    obj = bpy.data.objects.new(name + " curved blocks", mesh)
    bpy.context.collection.objects.link(obj)
    # Each visible curved unit has one top face, like a straight cuboid. This
    # avoids beveling internal top tessellation into a false covering sheet.
    bevel = obj.modifiers.new("Rounded stone block edges", "BEVEL")
    bevel.affect = "EDGES"
    bevel.limit_method = "NONE"
    bevel.width = 0.01
    bevel.segments = 3
    obj["block_nominal_length_m"] = CURB_BLOCK_LENGTH_M
    obj["road_apron_width_m"] = CURB_ROAD_APRON_M
    foundation_mesh = bpy.data.meshes.new(name + " buried foundation mesh")
    foundation_mesh.from_pydata(foundation_vertices, [], foundation_faces)
    foundation_mesh.materials.append(curb_material)
    foundation_obj = bpy.data.objects.new(name + " buried foundation", foundation_mesh)
    bpy.context.collection.objects.link(foundation_obj)
    foundation_obj["buried_below_road_surface"] = True
    apron_mesh = bpy.data.meshes.new(name + " flush road block mesh")
    apron_mesh.from_pydata(apron_vertices, [], apron_faces)
    normal_mesh = bmesh.new()
    normal_mesh.from_mesh(apron_mesh)
    bmesh.ops.recalc_face_normals(normal_mesh, faces=normal_mesh.faces)
    normal_mesh.to_mesh(apron_mesh)
    normal_mesh.free()
    apron_mesh.materials.append(curb_material)
    apron_obj = bpy.data.objects.new(name + " flush road-level blocks", apron_mesh)
    bpy.context.collection.objects.link(apron_obj)
    apron_bevel = apron_obj.modifiers.new("Rounded flush stone block edges", "BEVEL")
    apron_bevel.width = 0.00075
    apron_bevel.segments = 2
    apron_obj["block_nominal_length_m"] = CURB_BLOCK_LENGTH_M
    apron_obj["road_apron_width_m"] = CURB_ROAD_APRON_M
    apron_obj["curved_road_apron"] = True
    apron_obj["road_apron_top_tolerance_m"] = 0.0015
    return obj


def _sidewalk_brick_polygon(name, boundary, materials):
    """Clip the ordinary Cartesian basket weave to an arbitrary footprint."""
    if not materials or len(boundary) < 3:
        return None
    from mathutils.geometry import tessellate_polygon
    boundary_vectors = [Vector(point) for point in boundary]
    raw_triangles = tessellate_polygon([boundary_vectors])
    triangles = [tuple((point.x, point.y) for point in
                       (boundary_vectors[p] if isinstance(p, int) else p
                        for p in triangle))
                 for triangle in raw_triangles]
    # Rounded-corner sectors tessellate into many narrow triangles. Most
    # lattice bricks cannot intersect most of those triangles, so retain an
    # exact bounding box and winding sign for a cheap rejection first.
    triangle_regions = []
    for triangle in triangles:
        area = sum(triangle[i][0] * triangle[(i + 1) % len(triangle)][1]
                   - triangle[(i + 1) % len(triangle)][0] * triangle[i][1]
                   for i in range(len(triangle)))
        triangle_regions.append((
            triangle,
            (min(p[0] for p in triangle), max(p[0] for p in triangle),
             min(p[1] for p in triangle), max(p[1] for p in triangle)),
            1.0 if area >= 0.0 else -1.0,
        ))

    def clip_convex(subject, clipper, sign):
        result = list(subject)
        for i, edge_a in enumerate(clipper):
            edge_b, previous, result = clipper[(i + 1) % len(clipper)], result, []
            if not previous:
                break
            def inside(p):
                return sign * ((edge_b[0] - edge_a[0]) * (p[1] - edge_a[1])
                               - (edge_b[1] - edge_a[1]) * (p[0] - edge_a[0])) >= -1e-9
            def crossing(a, b):
                ex, ey, dx, dy = edge_b[0] - edge_a[0], edge_b[1] - edge_a[1], b[0] - a[0], b[1] - a[1]
                denominator = dx * ey - dy * ex
                if abs(denominator) < 1e-12:
                    return b
                t = ((edge_a[0] - a[0]) * ey - (edge_a[1] - a[1]) * ex) / denominator
                return (a[0] + dx * t, a[1] + dy * t)
            for j, current in enumerate(previous):
                prior = previous[j - 1]
                if inside(current):
                    if not inside(prior): result.append(crossing(prior, current))
                    result.append(current)
                elif inside(prior): result.append(crossing(prior, current))
        return result

    seed = zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF
    rng = random.Random(seed)
    vertices, faces, material_indices = [], [], []
    unit, cell, inset = 0.20, 0.40, 0.0015
    for column in range(math.floor(min(p[0] for p in boundary) / cell), math.ceil(max(p[0] for p in boundary) / cell)):
        for row in range(math.floor(min(p[1] for p in boundary) / cell), math.ceil(max(p[1] for p in boundary) / cell)):
            x0, y0 = column * cell, row * cell
            bricks = (((x0, x0 + cell, y0, y0 + unit), (x0, x0 + cell, y0 + unit, y0 + cell))
                      if (column + row) % 2 == 0 else
                      ((x0, x0 + unit, y0, y0 + cell), (x0 + unit, x0 + cell, y0, y0 + cell)))
            for bx0, bx1, by0, by1 in bricks:
                brick = ((bx0 + inset, by0 + inset), (bx1 - inset, by0 + inset),
                         (bx1 - inset, by1 - inset), (bx0 + inset, by1 - inset))
                material_index = rng.randrange(len(materials))
                for triangle, bounds, sign in triangle_regions:
                    if (bx1 - inset < bounds[0] or bx0 + inset > bounds[1]
                            or by1 - inset < bounds[2] or by0 + inset > bounds[3]):
                        continue
                    clipped = clip_convex(brick, triangle, sign)
                    if len(clipped) < 3: continue
                    first = len(vertices)
                    vertices.extend((x, y, SIDEWALK_TOP_Z_M + 0.0005) for x, y in clipped)
                    faces.append(tuple(range(first, first + len(clipped))))
                    material_indices.append(material_index)
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    for face, material_index in zip(mesh.polygons, material_indices):
        face.material_index = material_index
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj["asset_kind"] = "sidewalk_brick_surface"
    obj["boundary_bricks_may_deform"] = True
    obj["deterministic_random_seed"] = seed
    solidify = obj.modifiers.new("Brick thickness", "SOLIDIFY")
    solidify.thickness = 0.012
    solidify.offset = -1.0
    bevel = obj.modifiers.new("Soft rounded brick edges", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    bevel.affect = "EDGES"
    return obj


def _sidewalk_brick_sector(name, center, inner_radius, outer_radius,
                           start_angle, end_angle, materials):
    """Clip the Cartesian basket weave to a rounded corner sector."""
    if not materials or outer_radius <= inner_radius + 1e-5:
        return None
    steps = 32
    def arc(radius):
        return [(center[0] + math.cos(math.radians(start_angle +
                 (end_angle - start_angle) * i / steps)) * radius,
                 center[1] + math.sin(math.radians(start_angle +
                 (end_angle - start_angle) * i / steps)) * radius)
                for i in range(steps + 1)]
    outer = arc(outer_radius)
    boundary = ([center, *outer] if inner_radius <= 1e-6
                else [*outer, *reversed(arc(inner_radius))])
    return _sidewalk_brick_polygon(name, boundary, materials)


def _rounded_corner(name, center, start_angle, end_angle, radius, sidewalk, curb,
                    planting=None, brick_materials=()):
    steps = 24
    arc = []
    for index in range(steps + 1):
        angle = math.radians(start_angle + (end_angle - start_angle) * index / steps)
        arc.append((center[0] + math.cos(angle) * radius,
                    center[1] + math.sin(angle) * radius))
    # Match the lowered top elevation of the adjoining sidewalk slabs. Where
    # the corner contains planting, split the pavement explicitly around its
    # annular bed so the recessed soil is not occluded by the sidewalk fan.
    pavement_radius = radius - CURB_WIDTH_M
    pavement_arc = []
    for index in range(steps + 1):
        angle = math.radians(start_angle + (end_angle - start_angle) * index / steps)
        pavement_arc.append((center[0] + math.cos(angle) * pavement_radius,
                             center[1] + math.sin(angle) * pavement_radius))
    bedding_z = SIDEWALK_TOP_Z_M - 0.012 if brick_materials else SIDEWALK_TOP_Z_M
    if planting is None:
        polygon(name + " sidewalk", [center, *pavement_arc], bedding_z, sidewalk)
        _sidewalk_brick_sector(name + " brick paving", center, 0.0,
                               pavement_radius, start_angle, end_angle,
                               brick_materials)
    else:
        bed_inner = planting.curve_radius - planting.width * 0.5
        bed_outer = planting.curve_radius + planting.width * 0.5
        inner_arc = []
        for index in range(steps + 1):
            angle = math.radians(start_angle +
                                 (end_angle - start_angle) * index / steps)
            inner_arc.append((center[0] + math.cos(angle) * bed_inner,
                              center[1] + math.sin(angle) * bed_inner))
        polygon(name + " inner sidewalk", [center, *inner_arc], bedding_z, sidewalk)
        _sidewalk_brick_sector(name + " inner brick paving", center, 0.0,
                               bed_inner, start_angle, end_angle,
                               brick_materials)
        _annular_sector(name + " outer sidewalk", center, bed_outer, pavement_radius,
                        start_angle, end_angle, bedding_z, sidewalk, steps)
        _sidewalk_brick_sector(name + " outer brick paving", center, bed_outer,
                               pavement_radius, start_angle, end_angle,
                               brick_materials)
        planting_start = planting.curve_start_degrees
        planting_end = planting_start + planting.curve_sweep_degrees
        low, high = sorted((planting_start, planting_end))
        if low > start_angle + 1e-4:
            cap_steps = max(1, round(steps * (low - start_angle) /
                                     (end_angle - start_angle)))
            _annular_sector(name + " start pavement return", center,
                            bed_inner, min(bed_outer, pavement_radius), start_angle, low,
                            bedding_z, sidewalk, cap_steps)
            _sidewalk_brick_sector(
                name + " start return brick paving", center, bed_inner,
                min(bed_outer, pavement_radius), start_angle, low,
                brick_materials)
        if high < end_angle - 1e-4:
            cap_steps = max(1, round(steps * (end_angle - high) /
                                     (end_angle - start_angle)))
            _annular_sector(name + " end pavement return", center,
                            bed_inner, min(bed_outer, pavement_radius), high, end_angle,
                            bedding_z, sidewalk, cap_steps)
            _sidewalk_brick_sector(
                name + " end return brick paving", center, bed_inner,
                min(bed_outer, pavement_radius), high, end_angle,
                brick_materials)

    _curved_curb_blocks(name + " curb", center, start_angle, end_angle, radius, curb)


def _intersection_corner_pavement(name, center, start_angle, end_angle,
                                  radius, asphalt, central_corner=None):
    """Fill the concave road corner up to, but never beneath, the curved kerb."""
    # The caller supplies world-space centres, so signs come from the arc's
    # quadrant rather than the absolute world coordinate.
    midpoint_angle = math.radians((start_angle + end_angle) * 0.5)
    sign_x = 1.0 if math.cos(midpoint_angle) >= 0.0 else -1.0
    sign_y = 1.0 if math.sin(midpoint_angle) >= 0.0 else -1.0
    if central_corner is None:
        central_corner = (center[0] + sign_x * radius,
                          center[1] + sign_y * radius)
    steps = 24
    arc = []
    for index in range(steps + 1):
        angle = math.radians(end_angle - (end_angle - start_angle) * index / steps)
        arc.append((center[0] + math.cos(angle) * radius,
                    center[1] + math.sin(angle) * radius))
    polygon(name, [central_corner, *arc], 0.0005, asphalt)


def _stacked_stop_marking(center, heading_degrees, marking):
    # Japanese road-marking glyphs are deliberately stretched in the direction
    # of travel.  The standard figure collection uses an approximately 3:1
    # length-to-width ratio so the text reads correctly from a driver's low,
    # oblique viewpoint rather than looking like ordinary square type.
    angle = math.radians(heading_degrees)
    forward = Vector((math.cos(angle), math.sin(angle)))
    across = Vector((math.sin(angle), -math.cos(angle)))
    glyph_width = 1.05
    glyph_length = glyph_width * 3.0
    glyph_gap = 0.45

    # Explicit road-marking outlines, normalized to a one-metre design square.
    # These intentionally use broad rectangular strokes, clipped diagonals and
    # angular joins instead of a typesetting font. The low oblique viewpoint of
    # a driver turns the 3:1 longitudinal stretch back into readable characters.
    glyphs = {
        "止": (
            # Long centre stem and the three square-ended branches shown in
            # the standard road-glyph drawing.
            ((-0.11, -0.50), (0.08, -0.50), (0.08, 0.50), (-0.11, 0.50)),
            ((0.07, 0.13), (0.48, 0.13), (0.48, 0.25), (0.07, 0.25)),
            ((-0.40, -0.38), (-0.22, -0.38), (-0.22, 0.17), (-0.40, 0.17)),
            ((-0.50, -0.50), (0.50, -0.50), (0.50, -0.37), (-0.50, -0.37)),
        ),
        "ま": (
            ((-0.10, -0.50), (0.09, -0.50), (0.09, 0.50), (-0.10, 0.50)),
            ((-0.50, 0.23), (0.50, 0.23), (0.50, 0.36), (-0.50, 0.36)),
            ((-0.50, 0.00), (0.50, 0.00), (0.50, 0.13), (-0.50, 0.13)),
            # C-shaped lower loop. The return path along the inside leaves the
            # asphalt opening visible without relying on a texture or font.
            ((-0.10, -0.13), (-0.25, -0.14), (-0.38, -0.17),
             (-0.47, -0.22), (-0.50, -0.28), (-0.50, -0.36),
             (-0.42, -0.43), (-0.28, -0.48), (-0.10, -0.50),
             (-0.10, -0.42), (-0.21, -0.41), (-0.30, -0.39),
             (-0.36, -0.35), (-0.36, -0.28), (-0.31, -0.23),
             (-0.20, -0.19), (-0.10, -0.18)),
            # Tapered right-hand sweep from the loop junction.
            ((0.08, -0.14), (0.24, -0.16), (0.50, -0.34),
             (0.50, -0.48), (0.08, -0.19)),
        ),
        "れ": (
            ((-0.09, -0.50), (0.09, -0.50), (0.09, 0.50), (-0.09, 0.50)),
            ((-0.50, 0.16), (-0.09, 0.16), (-0.09, 0.29), (-0.50, 0.29)),
            # Long lower-left diagonal branch. Keep this as a convex quad that
            # meets the centre stem at its edge; a concave overlapping face can
            # triangulate with a dark, apparently chipped wedge in Blender.
            ((-0.09, 0.16), (-0.09, -0.03),
             (-0.50, -0.40), (-0.50, -0.25)),
            # Upper diagonal joins the centre stem to the separate right stem.
            ((0.05, 0.18), (0.24, 0.33), (0.42, 0.33),
             (0.09, -0.02), (-0.04, -0.10)),
            # Right stem and its small kicked-out foot are a single angular
            # silhouette instead of reducing it to a generic hiragana font glyph.
            ((0.24, -0.50), (0.50, -0.47), (0.50, -0.31),
             (0.41, -0.33), (0.41, 0.33), (0.24, 0.33)),
        ),
    }

    for index, character in enumerate("止まれ"):
        point = Vector(center) - forward * index * (glyph_length + glyph_gap)
        world_polygons = []
        for component in glyphs[character]:
            world_polygons.append(tuple(
                (point.x + across.x * x * glyph_width + forward.x * y * glyph_length,
                 point.y + across.y * x * glyph_width + forward.y * y * glyph_length)
                for x, y in component
            ))
        obj = extruded_polygons(
            f"止まれ {index + 1} {character}", world_polygons, 0.0,
            ROAD_PAINT_THICKNESS_M, marking,
        )
        obj["marking_glyph_width_m"] = glyph_width
        obj["marking_glyph_length_m"] = glyph_length
        obj["marking_length_width_ratio"] = 3.0


def _tactile_paving_mesh(tiles, tactile_material):
    """Build all tactile tiles as one compact mesh with standard 5mm relief."""
    if not tiles:
        return None
    vertices, faces = [], []

    def box(cx, cy, sx, sy, z0, z1):
        first = len(vertices)
        vertices.extend((
            (cx - sx / 2, cy - sy / 2, z0), (cx + sx / 2, cy - sy / 2, z0),
            (cx + sx / 2, cy + sy / 2, z0), (cx - sx / 2, cy + sy / 2, z0),
            (cx - sx / 2, cy - sy / 2, z1), (cx + sx / 2, cy - sy / 2, z1),
            (cx + sx / 2, cy + sy / 2, z1), (cx - sx / 2, cy + sy / 2, z1),
        ))
        faces.extend(tuple(first + i for i in face) for face in (
            (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
            (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        ))

    def rounded_box(cx, cy, sx, sy, z0, z1, radius=0.01, corner_segments=4):
        radius = min(radius, sx * 0.25, sy * 0.25)
        ring = []
        for corner_x, corner_y, start_angle in (
            (cx + sx / 2 - radius, cy + sy / 2 - radius, 0),
            (cx - sx / 2 + radius, cy + sy / 2 - radius, 90),
            (cx - sx / 2 + radius, cy - sy / 2 + radius, 180),
            (cx + sx / 2 - radius, cy - sy / 2 + radius, 270),
        ):
            for step in range(corner_segments + 1):
                angle = math.radians(start_angle + step * 90 / corner_segments)
                ring.append((corner_x + math.cos(angle) * radius,
                             corner_y + math.sin(angle) * radius))
        first = len(vertices)
        count = len(ring)
        vertices.extend((x, y, z0) for x, y in ring)
        vertices.extend((x, y, z1) for x, y in ring)
        faces.append(tuple(first + i for i in reversed(range(count))))
        faces.append(tuple(first + count + i for i in range(count)))
        for i in range(count):
            j = (i + 1) % count
            faces.append((first + i, first + j, first + count + j, first + count + i))

    def truncated_cylinder(cx, cy, bottom_radius, top_radius, z0, z1, segments=12):
        first = len(vertices)
        for z, radius in ((z0, bottom_radius), (z1, top_radius)):
            vertices.extend((cx + math.cos(i * math.tau / segments) * radius,
                             cy + math.sin(i * math.tau / segments) * radius, z)
                            for i in range(segments))
        faces.append(tuple(first + i for i in reversed(range(segments))))
        faces.append(tuple(first + segments + i for i in range(segments)))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((first + i, first + j,
                          first + segments + j, first + segments + i))

    # Keep tactile bases positively above the rounded brick shoulders.
    base_z, relief_z = SIDEWALK_TOP_Z_M + 0.003, SIDEWALK_TOP_Z_M + 0.008

    def append_tile(kind):
        cx = cy = 0.0
        sx = sy = 0.30
        # A 1mm plate prevents z-fighting while retaining visible 300mm joints.
        rounded_box(cx, cy, max(0.002, sx - 0.004), max(0.002, sy - 0.004),
                    SIDEWALK_TOP_Z_M, base_z, radius=0.01)
        if kind == "warning":
            for ix in range(5):
                for iy in range(5):
                    truncated_cylinder(cx + (ix - 2) * sx / 5,
                                       cy + (iy - 2) * sy / 5,
                                       0.014, 0.0085, base_z, relief_z)
        else:
            # Four directional ribs, JIS-style. Short adjustment tiles retain
            # the same rib count and simply shorten the direction of travel.
            along = sx
            across = sy
            for index in range(4):
                offset = (index - 1.5) * across / 4
                rib_length = max(0.004, along - 0.028)
                box(cx, cy + offset, rib_length, 0.018, base_z, relief_z)

    prototype_collection = bpy.data.collections.get("Tactile paving shared prototypes")
    if prototype_collection is None:
        prototype_collection = bpy.data.collections.new("Tactile paving shared prototypes")
        bpy.context.scene.collection.children.link(prototype_collection)
        prototype_collection.hide_render = True
        prototype_collection.hide_viewport = True

    def prototype(kind):
        existing = next((o for o in prototype_collection.objects
                         if o.name.startswith(f"Tactile {kind} prototype")
                         and o.type == 'MESH' and o.data.materials
                         and o.data.materials[0] == tactile_material), None)
        if existing is not None:
            return existing
        vertices.clear()
        faces.clear()
        append_tile(kind)
        mesh = bpy.data.meshes.new(f"Tactile {kind} shared mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(tactile_material)
        obj = bpy.data.objects.new(f"Tactile {kind} prototype", mesh)
        prototype_collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
        return obj

    prototypes = {kind: prototype(kind) for kind in ("guidance", "warning")}

    def instanced_points(kind, kind_tiles):
        mesh = bpy.data.meshes.new(f"Tactile {kind} instance points")
        mesh.from_pydata([(item.center[0], item.center[1], 0.0) for item in kind_tiles], [], [])
        scale_attribute = mesh.attributes.new("instance_scale", "FLOAT_VECTOR", "POINT")
        rotation_attribute = mesh.attributes.new("instance_rotation", "FLOAT_VECTOR", "POINT")
        for index, item in enumerate(kind_tiles):
            if kind == "guidance":
                along = item.size[0] if item.guidance_axis == "x" else item.size[1]
                across = item.size[1] if item.guidance_axis == "x" else item.size[0]
                scale_attribute.data[index].vector = (along / 0.30, across / 0.30, 1.0)
                rotation_attribute.data[index].vector = (
                    0.0, 0.0,
                    math.radians(item.rotation_degrees)
                    + (0.0 if item.guidance_axis == "x" else math.pi / 2),
                )
            else:
                scale_attribute.data[index].vector = (1.0, 1.0, 1.0)
                rotation_attribute.data[index].vector = (
                    0.0, 0.0, math.radians(item.rotation_degrees),
                )
        obj = bpy.data.objects.new(f"Tactile paving {kind} instances", mesh)
        bpy.context.collection.objects.link(obj)
        tree = bpy.data.node_groups.new(f"Tactile {kind} instancing", "GeometryNodeTree")
        tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        group_input = tree.nodes.new("NodeGroupInput")
        group_output = tree.nodes.new("NodeGroupOutput")
        object_info = tree.nodes.new("GeometryNodeObjectInfo")
        object_info.inputs["Object"].default_value = prototypes[kind]
        object_info.inputs["As Instance"].default_value = True
        scale_input = tree.nodes.new("GeometryNodeInputNamedAttribute")
        scale_input.data_type = "FLOAT_VECTOR"
        scale_input.inputs["Name"].default_value = "instance_scale"
        rotation_input = tree.nodes.new("GeometryNodeInputNamedAttribute")
        rotation_input.data_type = "FLOAT_VECTOR"
        rotation_input.inputs["Name"].default_value = "instance_rotation"
        instances = tree.nodes.new("GeometryNodeInstanceOnPoints")
        tree.links.new(group_input.outputs["Geometry"], instances.inputs["Points"])
        tree.links.new(object_info.outputs["Geometry"], instances.inputs["Instance"])
        tree.links.new(scale_input.outputs["Attribute"], instances.inputs["Scale"])
        tree.links.new(rotation_input.outputs["Attribute"], instances.inputs["Rotation"])
        tree.links.new(instances.outputs["Instances"], group_output.inputs["Geometry"])
        modifier = obj.modifiers.new("Shared tactile tile instances", "NODES")
        modifier.node_group = tree
        obj["tile_count"] = len(kind_tiles)
        return obj

    objects = []
    for kind in ("guidance", "warning"):
        kind_tiles = tuple(item for item in tiles if item.kind == kind)
        if kind_tiles:
            objects.append(instanced_points(kind, kind_tiles))
    if objects:
        objects[0]["tile_standard_m"] = 0.30
        objects[0]["relief_height_m"] = 0.005
        objects[0]["guidance_ribs"] = 4
        objects[0]["warning_dots"] = "5x5"
    return tuple(objects)


def build_scene(root: Path, network, plan, crosswalks, stop_lines, signal_sites, signal_blocks,
                pedestrian_countdowns, guardrails, plantings=(), bicycle_markings=(),
                curb_parking_stripes=(), street_trees=(), medians=(),
                median_island_devices=(), corner_reflector_poles=(), tactile_tiles=(),
                street_lights=()):
    profile_enabled = os.environ.get("ROAD_GENERATOR_PROFILE") == "1"
    profile_checkpoint = time.perf_counter()

    def profile(label):
        nonlocal profile_checkpoint
        now = time.perf_counter()
        if profile_enabled:
            print(f"PROFILE_{label}_SECONDS={now - profile_checkpoint:.6f}")
        profile_checkpoint = now

    bpy.ops.wm.read_factory_settings(use_empty=True)
    roads_collection = bpy.data.collections.new("Generated Road Network")
    bpy.context.scene.collection.children.link(roads_collection)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[roads_collection.name]

    prewarm_roadside_components(
        guardrails, plantings,
        bool(corner_reflector_poles),
    )
    prewarm_street_light_components(
        (item.kind, item.lit) for item in street_lights
    )
    device_types = {item.device_type for item in median_island_devices}
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

    asphalt = _asphalt_material()
    marking = road_marking_material(
        "Road marking white thermoplastic",
        (0.56, 0.56, 0.50), (0.91, 0.89, 0.79), (0.16, 0.17, 0.16),
    )
    orange = road_marking_material(
        "Orange no-passing thermoplastic",
        (0.56, 0.20, 0.018), (0.95, 0.43, 0.035), (0.14, 0.10, 0.055), 0.70,
    )
    bicycle_blue = road_marking_material(
        "Bicycle lane blue thermoplastic",
        (0.035, 0.245, 0.390), (0.275, 0.694, 0.882),
        (0.035, 0.075, 0.090), 0.76,
    )
    curb_orange = road_marking_material(
        "Curb parking prohibition orange thermoplastic",
        (0.56, 0.19, 0.008), (1.0, 0.49, 0.025),
        (0.24, 0.12, 0.025), 0.78,
    )
    tactile_yellow = weathered_material(
        "Tactile paving yellow", (0.58, 0.39, 0.018),
        (0.98, 0.72, 0.055), 0.83, 18.0,
    )
    sidewalk = weathered_material("Sidewalk concrete", (0.28, 0.29, 0.27),
                                  (0.47, 0.48, 0.44), 0.88, 8.0, "concrete")
    sidewalk_bricks = _sidewalk_brick_palette()
    curb = weathered_material("Curb concrete", (0.36, 0.37, 0.34),
                              (0.58, 0.58, 0.53), 0.82, 12.0, "concrete")
    median_concrete = weathered_material(
        "Median concrete", (0.31, 0.32, 0.30), (0.53, 0.53, 0.49), 0.86, 14.0,
        "concrete",
    )
    ground = weathered_material("Urban ground", (0.12, 0.105, 0.075),
                                (0.20, 0.17, 0.12), 0.96, 3.0)
    shared_hardware = {
        "white": material("Shared signal galvanized hardware", (0.58, 0.62, 0.62), 0.62, 0.34),
        "brown": material("Shared signal brown coated hardware", (0.070, 0.046, 0.036), 0.18, 0.62),
    }
    cable_mat = material("Shared signal black cable", (0.006, 0.007, 0.006), 0.0, 0.78)

    vehicle_sites_for_prewarm = {
        site.id: site for site in signal_sites if site.kind == "vehicle"
    }
    countdown_for_prewarm = {item.node_id: item for item in pedestrian_countdowns}

    def prewarm_vehicle_light(site):
        node = network.nodes[site.node_id]
        axis = ("east_west" if any(key in site.id for key in
                                   ("_west_vehicle", "_east_vehicle"))
                else "north_south")
        if node.signal_phase == f"{axis}_green" or node.signal_phase == "vehicle_green":
            return "green"
        if node.signal_phase == f"{axis}_yellow":
            return "yellow"
        return "red"

    vehicle_specs = set()
    for site in vehicle_sites_for_prewarm.values():
        node = network.nodes[site.node_id]
        effective_arrow = effective_vehicle_arrow(network, node)
        axis = ("east_west" if any(key in site.id for key in
                                   ("_west_vehicle", "_east_vehicle"))
                else "north_south")
        active_arrow = (effective_arrow == "right"
                        and node.signal_phase == f"{axis}_right_arrow")
        vehicle_specs.add((
            node.exterior_color, effective_arrow,
            _vehicle_horizontal_extension(network, site),
            "right" if site.support_mode == "median_right" else "left",
            prewarm_vehicle_light(site), active_arrow,
        ))

    pedestrian_specs = set()
    for site in signal_sites:
        if site.kind != "pedestrian":
            continue
        node = network.nodes[site.node_id]
        rotation = round(site.rotation_degrees) % 180
        walking_axis = "east_west" if rotation == 90 else "north_south"
        if node.kind == "signalized_pedestrian_crossing":
            light = "blue" if node.signal_phase == "pedestrian_green" else "red"
        elif node.signal_phase.endswith("_right_arrow"):
            light = "red"
        else:
            light = "blue" if node.signal_phase == f"{walking_axis}_green" else "red"
        countdown = countdown_for_prewarm[site.node_id]
        if node.kind in {"signalized_cross", "signalized_t_junction"} and node.signal_phase.endswith("_yellow"):
            active_axis = node.signal_phase.removesuffix("_yellow")
            level = 8 if walking_axis == active_axis else 0
        else:
            level = countdown.blue_level if light == "blue" else countdown.red_level
        pedestrian_specs.add((node.exterior_color, light, level))

    name_specs = {
        (node.name, node.roman_name) for node in network.nodes.values()
        if node.name.strip() or node.roman_name.strip()
    }
    prewarm_signal_components(vehicle_specs, pedestrian_specs, name_specs)
    profile("SETUP")

    xs = [node.position[0] for node in network.nodes.values()]
    ys = [node.position[1] for node in network.nodes.values()]
    for item in network.buildings:
        xs.extend((item.position[0] - item.size[0] * 0.5,
                   item.position[0] + item.size[0] * 0.5))
        ys.extend((item.position[1] - item.size[1] * 0.5,
                   item.position[1] + item.size[1] * 0.5))
    from road_generator.core.subway import subway_context_bounds
    for x, y in subway_context_bounds(network):
        xs.append(x); ys.append(y)
    terrain_center = ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)
    cube("Surrounding terrain", (*terrain_center, -0.17),
         (max(xs) - min(xs) + 18, max(ys) - min(ys) + 18, 0.25), ground)

    # Base roads come directly from graph edges. Sidewalks are trimmed around
    # semantic nodes so they never run through an intersection mouth.
    planting_by_edge_side = {(item.edge_id, item.side): item for item in plantings}
    back_planting_by_node = {
        item.edge_id.removesuffix("_back_sidewalk"): item
        for item in plantings if item.side == "back"
    }
    corner_planting_by_id = {
        item.id: item for item in plantings if item.curve_center is not None
    }
    curb_rows = []
    for segment in plan.segments:
        _road_rectangle(segment.edge_id, segment.start, segment.end, segment.width, asphalt)
        if segment.sidewalks == "both":
            start = Vector(segment.start)
            end = Vector(segment.end)
            direction = (end - start).normalized()
            start_kind = network.nodes[next(e.start for e in network.edges if e.id == segment.edge_id)].kind
            end_kind = network.nodes[next(e.end for e in network.edges if e.id == segment.edge_id)].kind
            edge = next(e for e in network.edges if e.id == segment.edge_id)
            if start_kind in ("signalized_cross", "signalized_t_junction",
                              "stop_cross", "stop_t_junction"):
                widths = road_widths_at_node(network, edge.start)
                perpendicular = widths[1] if abs(direction.x) > 0.5 else widths[0]
                start += direction * (perpendicular * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M)
            if end_kind in ("signalized_cross", "signalized_t_junction",
                            "stop_cross", "stop_t_junction"):
                widths = road_widths_at_node(network, edge.end)
                perpendicular = widths[1] if abs(direction.x) > 0.5 else widths[0]
                end -= direction * (perpendicular * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M)
            if (end - start).length > 1.0:
                edge_plantings = {
                    side: planting_by_edge_side[(segment.edge_id, side)]
                    for side in ("left", "right")
                    if (segment.edge_id, side) in planting_by_edge_side
                }
                _sidewalk_pair(segment.edge_id, start, end, segment.width, SIDEWALK_WIDTH_M,
                               sidewalk, curb, edge_plantings, curb_rows, crosswalks,
                               brick_materials=sidewalk_bricks)
    profile("ROADS_SIDEWALKS")

    # Intersection geometry and markings are derived from semantic graph nodes.
    for node in network.nodes.values():
        if node.kind not in ("signalized_cross", "signalized_t_junction",
                             "stop_cross", "stop_t_junction"):
            continue
        x, y = node.position
        east_west_width, north_south_width = road_widths_at_node(network, node.id)
        corner_x = north_south_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
        corner_y = east_west_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
        corners = (
            ("southwest", (-corner_x, -corner_y), (0, 90)),
            ("northwest", (-corner_x, corner_y), (-90, 0)),
            ("southeast", (corner_x, -corner_y), (90, 180)),
            ("northeast", (corner_x, corner_y), (180, 270)),
        )
        if node.kind in {"stop_t_junction", "signalized_t_junction"}:
            # The two rounded corners sit beside the terminating stem. The
            # sidewalk opposite that stem remains a straight, continuous slab.
            stem = None
            if node.kind == "signalized_t_junction":
                connected = set(connected_approaches(network, node.id))
                missing = next(direction for direction in ("west", "east", "south", "north")
                               if direction not in connected)
                stem = {"west": (1, 0), "east": (-1, 0),
                        "south": (0, 1), "north": (0, -1)}[missing]
            else:
                for approach in plan.approaches:
                    if approach.node_id != node.id or not approach.stop_control:
                        continue
                    edge = next(item for item in network.edges if item.id == approach.edge_id)
                    other_id = edge.end if edge.start == node.id else edge.start
                    delta = (Vector(network.nodes[other_id].position) - Vector(node.position)).normalized()
                    stem = (round(delta.x), round(delta.y))
                    break
            horizontal_half_road = east_west_width * 0.5
            vertical_half_road = north_south_width * 0.5
            horizontal_sidewalk_offset = horizontal_half_road + SIDEWALK_WIDTH_M * 0.5
            vertical_sidewalk_offset = vertical_half_road + SIDEWALK_WIDTH_M * 0.5
            horizontal_span = 2 * (vertical_half_road + SIDEWALK_CORNER_RADIUS_M)
            vertical_span = 2 * (horizontal_half_road + SIDEWALK_CORNER_RADIUS_M)
            horizontal_curb_offset = horizontal_half_road + 0.07
            vertical_curb_offset = vertical_half_road + 0.07
            layouts = {
                (0, -1): ((corners[0], corners[2]), "north",
                          (x, y + horizontal_sidewalk_offset),
                          (horizontal_span, SIDEWALK_WIDTH_M),
                          ((x - horizontal_span * 0.5, y + horizontal_curb_offset),
                           (x + horizontal_span * 0.5, y + horizontal_curb_offset))),
                (0, 1): ((corners[1], corners[3]), "south",
                         (x, y - horizontal_sidewalk_offset),
                         (horizontal_span, SIDEWALK_WIDTH_M),
                         ((x - horizontal_span * 0.5, y - horizontal_curb_offset),
                          (x + horizontal_span * 0.5, y - horizontal_curb_offset))),
                (-1, 0): ((corners[0], corners[1]), "east",
                          (x + vertical_sidewalk_offset, y),
                          (SIDEWALK_WIDTH_M, vertical_span),
                          ((x + vertical_curb_offset, y - vertical_span * 0.5),
                           (x + vertical_curb_offset, y + vertical_span * 0.5))),
                (1, 0): ((corners[2], corners[3]), "west",
                         (x - vertical_sidewalk_offset, y),
                         (SIDEWALK_WIDTH_M, vertical_span),
                         ((x - vertical_curb_offset, y - vertical_span * 0.5),
                          (x - vertical_curb_offset, y + vertical_span * 0.5))),
            }
            if stem in layouts:
                corners, opposite, slab_center, slab_size, curb_points = layouts[stem]
                slab_center = list(slab_center)
                slab_size = list(slab_size)
                outer_extension = SIDEWALK_CORNER_RADIUS_M - SIDEWALK_WIDTH_M
                if opposite in {"north", "south"}:
                    sign = 1.0 if opposite == "north" else -1.0
                    slab_center[1] += sign * (
                        CURB_WIDTH_M * 0.5 + outer_extension * 0.5)
                    slab_size[1] += outer_extension - CURB_WIDTH_M
                else:
                    sign = 1.0 if opposite == "east" else -1.0
                    slab_center[0] += sign * (
                        CURB_WIDTH_M * 0.5 + outer_extension * 0.5)
                    slab_size[0] += outer_extension - CURB_WIDTH_M
                slab_center, slab_size = tuple(slab_center), tuple(slab_size)
                def back_sidewalk_slab(label, center_xy, size_xy):
                    brick_thickness = 0.012 if sidewalk_bricks else 0.0
                    cube(label,
                         (*center_xy, SIDEWALK_TOP_Z_M - 0.09
                          - brick_thickness * 0.5),
                         (*size_xy, 0.18 - brick_thickness), sidewalk)
                    sidewalk_brick_surface(
                        label + " brick paving", center_xy, size_xy[0], size_xy[1],
                        0.0, SIDEWALK_TOP_Z_M + 0.0005, sidewalk_bricks)
                back_planting = back_planting_by_node.get(node.id)
                if back_planting is None:
                    back_sidewalk_slab(
                        f"{node.id} continuous {opposite} sidewalk",
                        slab_center, slab_size)
                else:
                    # Match the recessed planting cross-section used along
                    # ordinary edges: 0.33m road margin, 0.85m soil bed and a
                    # 2.42m unobstructed pedestrian strip.
                    near, bed = 0.33, back_planting.width
                    visible_near = near - CURB_WIDTH_M
                    pedestrian = SIDEWALK_WIDTH_M + outer_extension - near - bed
                    cube(f"{node.id} back planting foundation",
                         (*slab_center, 0.035 + SIDEWALK_HEIGHT_DELTA_M),
                         (*slab_size, 0.07), sidewalk, 0.012)
                    if opposite in {"north", "south"}:
                        sign = 1.0 if opposite == "north" else -1.0
                        road_half = east_west_width * 0.5
                        back_sidewalk_slab(
                            f"{node.id} back planting road margin",
                            (x, y + sign * (road_half + CURB_WIDTH_M
                                           + visible_near * 0.5)),
                            (slab_size[0], visible_near))
                        back_sidewalk_slab(
                            f"{node.id} back planting pedestrian margin",
                            (x, y + sign * (road_half + near + bed
                                           + pedestrian * 0.5)),
                            (slab_size[0], pedestrian))
                    else:
                        sign = 1.0 if opposite == "east" else -1.0
                        road_half = north_south_width * 0.5
                        back_sidewalk_slab(
                            f"{node.id} back planting road margin",
                            (x + sign * (road_half + CURB_WIDTH_M
                                         + visible_near * 0.5), y),
                            (visible_near, slab_size[1]))
                        back_sidewalk_slab(
                            f"{node.id} back planting pedestrian margin",
                            (x + sign * (road_half + near + bed
                                         + pedestrian * 0.5), y),
                            (pedestrian, slab_size[1]))
                roadward_sign = {
                    "north": -1.0, "south": 1.0,
                    "east": 1.0, "west": -1.0,
                }[opposite]
                back_curb = _straight_curb_blocks(
                    f"{node.id} continuous {opposite} curb", *curb_points,
                    curb, roadward_sign=roadward_sign,
                )
                if back_curb is not None:
                    curb_rows.append(back_curb)
            else:
                corners = ()
        for label, offset, angles in corners:
            corner_center = (x + offset[0], y + offset[1])
            _intersection_corner_pavement(
                f"{node.id} {label} corner pavement", corner_center,
                *angles, SIDEWALK_CORNER_RADIUS_M, asphalt)
            _rounded_corner(f"{node.id} {label} corner", corner_center,
                            *angles, SIDEWALK_CORNER_RADIUS_M, sidewalk, curb,
                            corner_planting_by_id.get(
                                f"{node.id}_{label}_corner_planting"),
                            sidewalk_bricks)
        if node.kind in {"signalized_cross", "signalized_t_junction",
                         "stop_cross", "stop_t_junction"}:
            cube(f"{node.id} intersection pavement", (x, y, -0.043),
                 (north_south_width, east_west_width, 0.086), asphalt)
        if node.kind in {"stop_cross", "stop_t_junction"}:
            for edge in network.edges:
                if node.id not in {edge.start, edge.end}:
                    continue
                other_id = edge.end if edge.start == node.id else edge.start
                outward = (Vector(network.nodes[other_id].position)
                           - Vector(node.position)).normalized()
                endpoint = Vector(node.position) + outward * (LANE_WIDTH_M * 0.25)
                strip(
                    f"{node.id} {edge.id} center arm marking",
                    node.position, endpoint,
                    JUNCTION_CENTER_MARKING_WIDTH_M,
                    ROAD_PAINT_CENTER_Z_M, marking,
                    thickness=ROAD_PAINT_THICKNESS_M,
                    bevel=ROAD_PAINT_BEVEL_M,
                )
    for item in plantings:
        _planting_retaining_walls(item, sidewalk)
    profile("INTERSECTIONS")

    edge_by_id = {edge.id: edge for edge in network.edges}
    for segment in plan.segments:
        edge = edge_by_id[segment.edge_id]
        start = Vector(segment.start)
        end = Vector(segment.end)
        direction = (end - start).normalized()
        start_trim, end_trim = longitudinal_marking_trims(network, edge, crosswalks)
        segment_length = (end - start).length
        start_has_stop_line = start_trim > 1.0 + 1e-6
        end_has_stop_line = end_trim > 1.0 + 1e-6
        start += direction * start_trim
        end -= direction * end_trim
        if (end - start).length <= 0.5:
            continue
        normal = Vector((-direction.y, direction.x))
        if not edge.median and edge.center_marking != "none":
            if edge.center_marking == "white_dashed":
                dashed_line(
                    f"{segment.edge_id} white dashed centre line", start, end,
                    0.15, 5.0, 5.0, ROAD_PAINT_CENTER_Z_M, marking,
                    thickness=ROAD_PAINT_THICKNESS_M, bevel=ROAD_PAINT_BEVEL_M,
                )
            else:
                centre_material = (orange if edge.center_marking == "orange_solid"
                                   else marking)
                strip(f"{segment.edge_id} {edge.center_marking} centre line",
                      start, end, 0.15,
                      (ORANGE_PAINT_CENTER_Z_M
                       if edge.center_marking == "orange_solid"
                       else ROAD_PAINT_CENTER_Z_M), centre_material,
                      thickness=ROAD_PAINT_THICKNESS_M,
                      bevel=ROAD_PAINT_BEVEL_M)
        # White broken lane separators divide lanes travelling in the same
        # direction. The orange centre line continues to separate opposing flow.
        for lane_boundary in range(1, segment.lanes_each_way):
            offset = lane_boundary * 3.25
            for side in (-1, 1):
                shifted_offset = carriageway_lateral_m(edge, side * offset)
                solid = lane_separator_solid_interval(
                    0.0, segment_length, side,
                    (-start_trim if start_has_stop_line else None),
                    (-end_trim if end_has_stop_line else None),
                )
                # Work in the original edge station frame so the side/direction
                # relationship is identical to the arbitrary-angle renderer.
                dashed_start = start_trim
                dashed_end = segment_length - end_trim
                if solid is not None:
                    if side < 0:
                        dashed_start = solid[1]
                    else:
                        dashed_end = solid[0]
                if dashed_end - dashed_start > 0.05:
                    a = (Vector(segment.start) + direction * dashed_start
                         + normal * shifted_offset)
                    b = (Vector(segment.start) + direction * dashed_end
                         + normal * shifted_offset)
                    dashed_line(f"{segment.edge_id} lane divider", a, b,
                                0.13, 3.0, 3.0, ROAD_PAINT_CENTER_Z_M, marking,
                                thickness=ROAD_PAINT_THICKNESS_M,
                                bevel=ROAD_PAINT_BEVEL_M)
                if solid is not None and solid[1] - solid[0] > 0.05:
                    a = (Vector(segment.start) + direction * solid[0]
                         + normal * shifted_offset)
                    b = (Vector(segment.start) + direction * solid[1]
                         + normal * shifted_offset)
                    strip(f"{segment.edge_id} lane divider solid approach",
                          a, b, 0.13, ROAD_PAINT_CENTER_Z_M, marking,
                          thickness=ROAD_PAINT_THICKNESS_M,
                          bevel=ROAD_PAINT_BEVEL_M)

        arrow_kinds = approach_lane_arrow_kinds(segment.lanes_each_way)
        original_start = Vector(segment.start)
        for endpoint, trim, side, travel_sign in (
                (edge.start, start_trim, -1, -1.0),
                (edge.end, end_trim, 1, 1.0)):
            if trim <= 1.0 + 1e-6 or not arrow_kinds:
                continue
            stop_station = (trim if side < 0 else segment_length - trim)
            tip_station = stop_station - travel_sign * 2.0
            travel = direction * travel_sign
            rotation = math.degrees(math.atan2(travel.y, travel.x)) - 90.0
            for lane_index, kind in enumerate(arrow_kinds):
                lateral = carriageway_lateral_m(edge, side * (
                    segment.lanes_each_way - lane_index - 0.5) * LANE_WIDTH_M)
                location = (original_start + direction * tip_station
                            + normal * lateral)
                lane_use_arrow_instance(
                    f"{segment.edge_id} {endpoint} lane {lane_index + 1} {kind} arrow",
                    (location.x, location.y, 0.0), rotation, kind, marking,
                )

    for item in bicycle_markings:
        bicycle_marking_instance(
            item.id, item.location, item.rotation_degrees, item.width,
            marking, bicycle_blue,
        )

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
                ROAD_PAINT_CENTER_Z_M, marking,
                thickness=ROAD_PAINT_THICKNESS_M,
                bevel=ROAD_PAINT_BEVEL_M,
            )
            obj["right_turn_guide"] = guide.id
        stop_obj = strip(
            f"{guide.id} waiting stop line",
            guide.stop_line_start, guide.stop_line_end, 0.30,
            ROAD_PAINT_CENTER_Z_M, marking,
            thickness=ROAD_PAINT_THICKNESS_M,
            bevel=ROAD_PAINT_BEVEL_M,
        )
        stop_obj["right_turn_guide"] = guide.id
        stop_obj["right_turn_waiting_stop_line"] = True

    for item in curb_parking_stripes:
        _curb_parking_stripes(item, curb_orange, curb_rows)

    for item in medians:
        _raised_median(item, median_concrete)

    for item in median_island_devices:
        if item.device_type == "keep_left_sign":
            key = ("median island device", "procedural_keep_left")
            builder = lambda: create_keep_left_sign("Procedural Keep Left Prototype")
        else:
            key = ("median island device", "dual_warning_lamp")
            builder = lambda: create_dual_warning_lamp("Dual Warning Lamp Prototype")
        cached_asset_instance(key, builder, item.id, item.location, item.rotation_degrees)

    # Every marking is generated from the same crosswalk plan later used for
    # signals, so its physical extent and its control equipment cannot diverge.
    for crossing in crosswalks:
        crosswalk(crossing.center, crossing.walking_axis,
                  max(0.5, crossing.road_width - 2 * (
                      CURB_ROAD_APRON_M + ROAD_MARKING_CURB_CLEARANCE_M)),
                  marking, span=crossing.crosswalk_width)
    _tactile_paving_mesh(tactile_tiles, tactile_yellow)
    for line in stop_lines:
        stop_line(line.center, line.across_axis, line.width, marking)

    # Unsignalized-junction roadside control derives entirely from approach
    # attributes. Signalized nodes never enter this branch.
    stop_sign_sites = []
    unsignalized_approaches = []
    for node in network.nodes.values():
        if node.kind not in {"stop_cross", "stop_t_junction"}:
            continue
        for edge in network.edges:
            if node.id not in {edge.start, edge.end}:
                continue
            endpoint = "from" if edge.start == node.id else "to"
            unsignalized_approaches.append((
                node, edge,
                bool(edge.approaches.get(endpoint, {}).get("stop_control", False)),
            ))
    for node, edge, is_stop_controlled in unsignalized_approaches:
        other_id = edge.start if edge.end == node.id else edge.end
        outward = (Vector(network.nodes[other_id].position) - Vector(node.position)).normalized()
        travel = -outward
        left = Vector((-travel.y, travel.x))
        if abs(outward.x) > abs(outward.y):
            approach_name = "east" if outward.x > 0 else "west"
        else:
            approach_name = "north" if outward.y > 0 else "south"
        planned_line = next(
            (item for item in stop_lines
             if item.id == f"{node.id}_{approach_name}_{approach_name}_stop"),
            None,
        )
        # An unsignalized junction retains the exact crosswalk and stop-line
        # geometry of its signalized counterpart. Stop control only adds the
        # road text and roadside sign; it must not paint a second, nearer line.
        if planned_line is None:
            raise ValueError(
                f"Unsignalized approach {edge.id!r} at {node.id!r} "
                "requires a planned crosswalk stop line")
        line_center = Vector(planned_line.center)
        heading = math.degrees(math.atan2(travel.y, travel.x))
        if is_stop_controlled:
            _stacked_stop_marking(line_center + outward * 4.9, heading, marking)
        else:
            available = (Vector(network.nodes[other_id].position)
                         - Vector(node.position)).length
            if available >= 70.0:
                for distance in (30.0, 50.0):
                    _road_crosswalk_diamond(
                        f"{node.id} {edge.id} crosswalk diamond {int(distance)}m",
                        line_center + outward * distance, heading, marking,
                    )
        line_lateral_offset = road_half_width_m(edge) * 0.5
        sign_types = (("止まれ", "横断歩道")
                      if is_stop_controlled and stop_approach_has_crosswalk_sign(
                          node.id, edge.id)
                      else (("止まれ",) if is_stop_controlled
                            else ("横断歩道",)))
        stop_sign_sites.append((
            line_center + outward * 1.3 + left * (
                line_lateral_offset + STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M),
            heading - 90,
            sign_types,
        ))
    profile("MARKINGS_MEDIANS")

    # Context placement is definition data. This Blender layer only supplies
    # reusable rendering recipes for the objects explicitly listed in JSON.
    guardrail_started = time.perf_counter()
    for item in guardrails:
        guardrail_instance(
            item.id, item.start, item.end, item.exterior_color, item.beam_side,
            item.elevation, item.curve_center, item.curve_radius,
            item.curve_start_degrees, item.curve_sweep_degrees,
        )
    profile("GUARDRAILS")

    planting_started = time.perf_counter()
    for item in plantings:
        planting_instance(
            item.id, item.start, item.end, item.width, item.density,
            item.maintenance, item.health, item.seed, item.elevation,
            item.curve_center, item.curve_radius,
            item.curve_start_degrees, item.curve_sweep_degrees,
            style=item.style,
        )
    profile("PLANTINGS")

    for item in corner_reflector_poles:
        reflector_pole_instance(item.id, item.location, item.rotation_degrees)
    profile("CORNER_REFLECTOR_POLES")

    street_tree_started = time.perf_counter()
    for item in street_trees:
        street_tree_instance(
            item.id, item.location, item.species, item.seed, item.rotation_degrees,
        )
    profile("STREET_TREES")

    for item in street_lights:
        street_light_instance(
            item.id, item.location, item.kind, item.lit, item.rotation_degrees,
        )
    profile("STREET_LIGHTS")

    vehicle_sites = {site.id: site for site in signal_sites if site.kind == "vehicle"}
    countdown_by_node = {item.node_id: item for item in pedestrian_countdowns}

    def vehicle_light(site):
        node = network.nodes[site.node_id]
        if node.kind == "signalized_pedestrian_crossing":
            return "green" if node.signal_phase == "vehicle_green" else "red"
        axis = "east_west" if any(key in site.id for key in ("_west_vehicle", "_east_vehicle")) else "north_south"
        if node.signal_phase == f"{axis}_green":
            return "green"
        if node.signal_phase == f"{axis}_yellow":
            return "yellow"
        return "red"

    def vehicle_arrow_active(site):
        if effective_vehicle_arrow(network, network.nodes[site.node_id]) != "right":
            return False
        axis = ("east_west" if any(key in site.id for key in
                                  ("_west_vehicle", "_east_vehicle"))
                else "north_south")
        return network.nodes[site.node_id].signal_phase == f"{axis}_right_arrow"

    def pedestrian_light(site):
        node = network.nodes[site.node_id]
        if node.kind == "signalized_pedestrian_crossing":
            return "blue" if node.signal_phase == "pedestrian_green" else "red"
        rotation = round(site.rotation_degrees) % 180
        walking_axis = "east_west" if rotation == 90 else "north_south"
        if node.signal_phase.endswith("_right_arrow"):
            return "red"
        return "blue" if node.signal_phase == f"{walking_axis}_green" else "red"

    def pedestrian_countdown_level(site, light):
        countdown = countdown_by_node[site.node_id]
        node = network.nodes[site.node_id]
        if node.kind in {"signalized_cross", "signalized_t_junction"} and node.signal_phase.endswith("_yellow"):
            active_axis = node.signal_phase.removesuffix("_yellow")
            rotation = round(site.rotation_degrees) % 180
            walking_axis = "east_west" if rotation == 90 else "north_south"
            return 8 if walking_axis == active_axis else 0
        return countdown.blue_level if light == "blue" else countdown.red_level

    for site in vehicle_sites.values():
        node = network.nodes[site.node_id]
        light = vehicle_light(site)
        effective_arrow = effective_vehicle_arrow(network, node)
        vehicle_instance(
            site.id.replace("_", " "), site.location, site.rotation_degrees, light,
            node.name, node.roman_name, node.exterior_color, effective_arrow,
            vehicle_arrow_active(site), _vehicle_horizontal_extension(network, site),
            "right" if site.support_mode == "median_right" else "left",
        )
    profile("VEHICLE_SIGNALS")

    pole_parts = ("Pedestrian signal support pole", "Support pole top cap",
                  "Support pole fixing band")

    def shared_pole_root(vehicle_site, pedestrian_rotation):
        # Both source assets model their actual pole axis at local (0, 0.16),
        # not at the collection origin. Because the two signals can have
        # different headings, equal collection origins do not mean equal pole
        # axes. Solve the pedestrian root so its rotated arm root/pole axis lands
        # exactly on the rotated vehicle-pole axis.
        vehicle_angle = math.radians(vehicle_site.rotation_degrees)
        pedestrian_angle = math.radians(pedestrian_rotation)
        target_x = vehicle_site.location[0] - math.sin(vehicle_angle) * 0.16
        target_y = vehicle_site.location[1] + math.cos(vehicle_angle) * 0.16
        return (
            target_x + math.sin(pedestrian_angle) * 0.16,
            target_y - math.cos(pedestrian_angle) * 0.16,
            vehicle_site.location[2],
        )

    def shared_pole_axis(vehicle_site):
        angle = math.radians(vehicle_site.rotation_degrees)
        return Vector((vehicle_site.location[0] - math.sin(angle) * 0.16,
                       vehicle_site.location[1] + math.cos(angle) * 0.16,
                       vehicle_site.location[2]))

    def add_shared_mount_hardware(block, site, branch_left, level_offset, exterior_color):
        hardware = shared_hardware[exterior_color]
        axis = shared_pole_axis(block.vehicle)
        angle = math.radians(site.rotation_degrees)
        # In local coordinates +X is the viewer's left because the signal faces
        # -Y; the right-side asset therefore branches along local -X.
        branch_sign = 1.0 if branch_left else -1.0
        direction = Vector((math.cos(angle) * branch_sign, math.sin(angle) * branch_sign, 0))
        # The source arm levels are 2.94/3.76 m. A paired head moves 14 cm to
        # avoid superposed collars while retaining the published signal height.
        for z in (axis.z + 2.94 + level_offset,
                  axis.z + 3.76 + level_offset):
            torus("Shared pedestrian arm clamping band", (axis.x, axis.y, z),
                  0.092, 0.008, hardware)
            start = axis - direction * 0.025
            end = axis + direction * 0.145
            sleeve = cylinder("Shared pedestrian arm root sleeve",
                              ((start.x + end.x) * 0.5, (start.y + end.y) * 0.5, z),
                              0.034, (end - start).length, hardware,
                              rotation=(0, math.radians(90), math.atan2(direction.y, direction.x)),
                              vertices=32)
            sleeve.rotation_mode = "QUATERNION"
            sleeve.rotation_quaternion = direction.to_track_quat("Z", "Y")
        box_center = axis - direction * 0.12 + Vector((0, 0, 3.34 + level_offset))
        cube("Shared pedestrian cable junction box", box_center,
             (0.16, 0.10, 0.22), hardware, 0.018)
        cable_start = axis + Vector((0, 0, 3.05 + level_offset))
        cable_end = box_center - Vector((0, 0, 0.10))
        cable_direction = cable_end - cable_start
        cable = cylinder("Shared pedestrian connection cable",
                         (cable_start + cable_end) * 0.5, 0.010, cable_direction.length,
                         cable_mat, vertices=20)
        cable.rotation_mode = "QUATERNION"
        cable.rotation_quaternion = cable_direction.to_track_quat("Z", "Y")

    for block in signal_blocks:
        for site in block.pedestrians:
            node = network.nodes[site.node_id]
            # Moving the far-side vehicle pole to the junction side of its
            # crosswalk swaps the coincident pedestrian site from position 1
            # (outside) to position 2 (junction side). Median supports never merge.
            merge_position = "inner"
            merge = (site.pedestrian_position == merge_position
                     and block.vehicle.support_mode == "roadside_left"
                     and math.dist(site.location[:2], block.vehicle.location[:2]) < 0.05)
            if merge:
                root = shared_pole_root(block.vehicle, site.rotation_degrees)
                location = root
            else:
                location = site.location
            light = pedestrian_light(site)
            countdown_level = pedestrian_countdown_level(site, light)
            pedestrian_instance(
                f"{site.id.replace('_', ' ')} position {site.pedestrian_position}",
                location, site.rotation_degrees,
                light, countdown_level, site.pedestrian_support_side,
                not merge, node.exterior_color,
            )
            if merge:
                add_shared_mount_hardware(
                    block, site, site.pedestrian_support_side == "left", 0.0,
                                          node.exterior_color)

    # Mid-block pedestrian crossing is not a three-signal corner block.
    block_ids = {site.id for block in signal_blocks for site in block.pedestrians}
    for site in signal_sites:
        if site.kind == "pedestrian" and site.id not in block_ids:
            # The eastern standalone crosswalk explicitly uses a right-emerging
            # support while preserving the authored, unmirrored signal box.
            light = pedestrian_light(site)
            countdown_level = pedestrian_countdown_level(site, light)
            node = network.nodes[site.node_id]
            support_side = (site.pedestrian_support_side
                            if site.pedestrian_position else "right")
            pedestrian_instance(
                site.id.replace("_", " "), site.location, site.rotation_degrees,
                light, countdown_level, support_side,
                True, node.exterior_color,
            )
    profile("PEDESTRIAN_SIGNALS")

    # The stop-sign collection was authored at X=-3 m, so compensate its source origin.
    for index, (location, rotation, sign_types) in enumerate(stop_sign_sites):
        cached_asset_instance(
            ("road_sign_stack", sign_types),
            lambda sign_types=sign_types: create_road_sign_stack(
                sign_types, "Road Sign Stack Prototype " + " ".join(sign_types)),
            f"Road sign {index + 1}", (*location, SIGNAL_BASE_Z_M), rotation,
        )

    # Sparse context supplies scale without obscuring the road graph.
    building_mat = material("Muted building walls", (0.42, 0.40, 0.35), roughness=0.82)
    roof_mat = material("Dark roofs", (0.055, 0.062, 0.067), metallic=0.05, roughness=0.5)
    for item in network.buildings:
        x, y = item.position
        sx, sy = item.size
        cube(f"Context building {item.id}", (x, y, item.height * 0.5),
             (sx, sy, item.height), building_mat, 0.10)
        roof = cube(f"Context roof {item.id}", (x, y, item.height + 0.35),
                    (sx + 0.5, sy + 0.5, 0.38),
                    roof_mat, 0.08)
        roof.rotation_euler[1] = math.radians(item.roof_tilt_degrees)

    from .subway import add_subway_entrances
    add_subway_entrances(network)
    return roads_collection


def _setup_day_lighting(scene):
    """Preserve the established daylight rig exactly for legacy JSON."""
    world = bpy.data.worlds.new("Procedural city daylight")
    world.use_nodes = True
    world.node_tree.nodes.clear()
    output = world.node_tree.nodes.new("ShaderNodeOutputWorld")
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(135)
    background = world.node_tree.nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 0.25
    world.node_tree.links.new(sky.outputs["Color"], background.inputs["Color"])
    world.node_tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world

    sun_data = bpy.data.lights.new("Broad daylight sun", "SUN")
    sun_data.energy = 1.5
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Broad daylight sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-135))
    scene.view_settings.exposure = -0.8


def _setup_night_lighting(scene):
    world = bpy.data.worlds.new("Procedural city night")
    world.use_nodes = True
    world.node_tree.nodes.clear()
    output = world.node_tree.nodes.new("ShaderNodeOutputWorld")
    background = world.node_tree.nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.025, 0.045, 0.095, 1.0)
    background.inputs["Strength"].default_value = 0.25
    world.node_tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world

    moon_data = bpy.data.lights.new("Broad cool moonlight", "SUN")
    moon_data.color = (0.38, 0.52, 0.82)
    moon_data.energy = 0.48
    moon_data.angle = math.radians(12)
    moon = bpy.data.objects.new("Broad cool moonlight", moon_data)
    scene.collection.objects.link(moon)
    moon.rotation_euler = (math.radians(68), math.radians(-12), math.radians(42))
    scene.view_settings.exposure = 0.50


def setup_lighting_and_cameras(network):
    scene = bpy.context.scene
    if network.scene.time_of_day == "night":
        _setup_night_lighting(scene)
    else:
        _setup_day_lighting(scene)

    overview_data = bpy.data.cameras.new("Road network overview")
    overview = bpy.data.objects.new("Road network overview", overview_data)
    scene.collection.objects.link(overview)
    xs = [node.position[0] for node in network.nodes.values()]
    ys = [node.position[1] for node in network.nodes.values()]
    center = Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, 0))
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    overview_span = max(span_y + 16.0, (span_x + 16.0) / (1100 / 760))
    overview.location = (center.x, center.y, max(60, overview_span * 1.2))
    overview_data.type = "ORTHO"
    overview_data.ortho_scale = max(50, overview_span)
    overview.rotation_euler = (0, 0, 0)

    driver_data = bpy.data.cameras.new("Driver approach camera")
    driver = bpy.data.objects.new("Driver approach camera", driver_data)
    scene.collection.objects.link(driver)
    target_node = next((node for node in network.nodes.values()
                        if node.kind in {"signalized_cross", "signalized_t_junction",
                                         "stop_cross", "stop_t_junction"}),
                       next(iter(network.nodes.values())))
    driver.location = (min(xs) + 9.0, target_node.position[1] + 1.65, 1.55)
    driver_data.lens = 45
    look_at(driver, (target_node.position[0], target_node.position[1] + 3.7, 2.0))
    scene["time_of_day"] = network.scene.time_of_day
    return overview, driver
