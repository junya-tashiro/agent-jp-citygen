import math

import bpy

from .primitives import (
    ROAD_PAINT_BEVEL_M, ROAD_PAINT_CENTER_Z_M, ROAD_PAINT_THICKNESS_M,
    ROAD_PAINT_TOP_Z_M, cube, extruded_polygons, polygon, strip,
)


def crosswalk(center, across_axis, road_width, mat, span=4.0, stripe=0.45, gap=0.45):
    # Japanese zebra bars run perpendicular to the walking direction. They span
    # the crosswalk width and repeat along the direction in which people walk.
    count = max(4, round((road_width + gap) / (stripe + gap)))
    actual_gap = (road_width - count * stripe) / (count - 1)
    first = -road_width * 0.5 + stripe * 0.5
    polygons = []
    for index in range(count):
        offset = first + index * (stripe + actual_gap)
        if across_axis == "y":
            cx, cy = center[0], center[1] + offset
            hx, hy = span * 0.5, stripe * 0.5
        else:
            cx, cy = center[0] + offset, center[1]
            hx, hy = stripe * 0.5, span * 0.5
        polygons.append(((cx - hx, cy - hy), (cx + hx, cy - hy),
                         (cx + hx, cy + hy), (cx - hx, cy + hy)))
    obj = extruded_polygons(
        "Crosswalk stripes", polygons, 0.0, ROAD_PAINT_THICKNESS_M,
        mat, ROAD_PAINT_BEVEL_M)
    obj["stripe_count"] = count
    return obj


def stop_line(center, across_axis, width, mat):
    dimensions = ((width, 0.30, ROAD_PAINT_THICKNESS_M) if across_axis == "x"
                  else (0.30, width, ROAD_PAINT_THICKNESS_M))
    cube("Stop line", (center[0], center[1], ROAD_PAINT_CENTER_Z_M),
         dimensions, mat, ROAD_PAINT_BEVEL_M)


def zebra_zone(points, mat, spacing=0.75, stripe_width=0.18):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    polygon("Zebra zone dark base", points, 0.018, mat[0])
    for index in range(len(points)):
        strip(f"Zebra outline {index + 1}", points[index - 1], points[index],
              0.16, 0.029, mat[1])
    def clip_half_plane(vertices, value, keep_above):
        output = []
        for index, current in enumerate(vertices):
            previous = vertices[index - 1]
            current_value = current[1] - current[0]
            previous_value = previous[1] - previous[0]
            current_inside = current_value >= value if keep_above else current_value <= value
            previous_inside = previous_value >= value if keep_above else previous_value <= value
            if current_inside != previous_inside:
                denominator = current_value - previous_value
                factor = 0.0 if abs(denominator) < 1e-8 else (value - previous_value) / denominator
                output.append((previous[0] + (current[0] - previous[0]) * factor,
                               previous[1] + (current[1] - previous[1]) * factor))
            if current_inside:
                output.append(current)
        return output

    # Intersect each diagonal band with the exact exclusion-zone polygon. This
    # avoids the oversized slashes that an unclipped line approximation produces.
    values = [y - x for x, y in points]
    cursor = min(values) - spacing
    index = 0
    half_band = stripe_width * math.sqrt(2) * 0.5
    while cursor <= max(values) + spacing:
        clipped = clip_half_plane(list(points), cursor - half_band, True)
        clipped = clip_half_plane(clipped, cursor + half_band, False) if clipped else []
        if len(clipped) >= 3:
            polygon(f"Zebra diagonal {index:02d}", clipped, 0.028, mat[1])
        cursor += spacing
        index += 1


def direction_arrow(center, heading_degrees, kind, mat):
    # Slender road arrow assembled from code-native polygons.
    points = [(-0.11, -1.1), (0.11, -1.1), (0.11, 0.35),
              (0.42, 0.08), (0.42, 0.43), (0.0, 0.92),
              (-0.42, 0.43), (-0.42, 0.08), (-0.11, 0.35)]
    if kind == "right":
        points = [(-0.10, -1.15), (0.12, -1.15), (0.12, 0.25),
                  (0.43, 0.25), (0.43, -0.02), (0.88, 0.42),
                  (0.43, 0.86), (0.43, 0.58), (-0.10, 0.58)]
    angle = math.radians(heading_degrees)
    transformed = []
    for x, y in points:
        transformed.append((center[0] + x * math.cos(angle) - y * math.sin(angle),
                            center[1] + x * math.sin(angle) + y * math.cos(angle)))
    polygon(f"{kind.title()} direction arrow", transformed, ROAD_PAINT_TOP_Z_M, mat)


def stop_text(center, heading_degrees, mat):
    from asset_library.shared.fonts import japanese_font
    curve = bpy.data.curves.new("止まれ road marking", "FONT")
    curve.body = "止まれ"
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 1.05
    curve.space_character = 0.9
    curve.font = japanese_font()
    obj = bpy.data.objects.new("止まれ road marking", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.location = (center[0], center[1], ROAD_PAINT_TOP_Z_M)
    obj.rotation_euler = (0, 0, math.radians(heading_degrees))
    # Text lies in local XY only after rotating around X.
    obj.rotation_euler[0] = 0
    return obj
