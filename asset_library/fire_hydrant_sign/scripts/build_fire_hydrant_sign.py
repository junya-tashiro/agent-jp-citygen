"""Procedural Japanese fire-hydrant location sign."""

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asset_library.fire_hydrant_sign.scripts.fire_hydrant_face_geometry import (
    HYDRANT_FACE_PATHS,
)


ASSET_ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def cube(name, location, dimensions, mat, bevel=0.0, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Soft manufactured edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def cylinder(name, location, radius, depth, mat, rotation=(0.0, 0.0, 0.0), vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth,
        location=location, rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def tube_path(name, points, radius, mat, cyclic=False):
    curve = bpy.data.curves.new(name + " Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 5
    curve.resolution_u = 12
    spline = curve.splines.new("NURBS" if cyclic else "POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1.0)
    spline.use_cyclic_u = cyclic
    if cyclic:
        spline.order_u = min(3, len(points))
        spline.use_endpoint_u = False
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def _radial_strap(name, center, angle, inner_radius, outer_radius, y, mat):
    midpoint_radius = (inner_radius + outer_radius) * 0.5
    length = outer_radius - inner_radius + 0.035
    x = center[0] + math.cos(angle) * midpoint_radius
    z = center[1] + math.sin(angle) * midpoint_radius
    return cube(
        name, (x, y, z), (length, 0.012, 0.045), mat, 0.004,
        rotation=(0.0, -angle, 0.0),
    )


def hydrant_face_graphic(name, center, y, mat, facing_front=True):
    paths = [
        [Vector((center[0] + (x if facing_front else -x),
                 center[1] + z)) for x, z in path]
        for path in HYDRANT_FACE_PATHS
    ]

    def signed_area(path):
        return sum(
            path[index].x * path[(index + 1) % len(path)].y
            - path[(index + 1) % len(path)].x * path[index].y
            for index in range(len(path))
        ) * 0.5

    def contains(path, point):
        inside = False
        previous = path[-1]
        for current in path:
            if ((current.y > point.y) != (previous.y > point.y)
                    and point.x < (previous.x - current.x)
                    * (point.y - current.y) / (previous.y - current.y)
                    + current.x):
                inside = not inside
            previous = current
        return inside

    winding = 1.0 if facing_front else -1.0
    outers = [path for path in paths
              if signed_area(path) * winding < -0.00025]
    holes = [path for path in paths
             if signed_area(path) * winding > 0.00004]
    objects = []
    for component_index, outer in enumerate(outers, start=1):
        component = [outer] + [hole for hole in holes if contains(outer, hole[0])]
        vertices = [(point.x, y, point.y)
                    for path in component for point in path]
        faces = tessellate_polygon(component)
        mesh = bpy.data.meshes.new(f"{name} component {component_index} Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(f"{name} component {component_index}", mesh)
        bpy.context.collection.objects.link(obj)
        objects.append(obj)
    return objects


def create_fire_hydrant_sign(name="Fire Hydrant Sign", location=(0, 0, 0),
                             rotation_degrees=0):
    """Create a double-sided hydrant sign facing local -Y and +Y."""
    before = set(bpy.context.scene.objects)
    red_paint = material(name + " vermilion painted steel",
                         (0.72, 0.012, 0.018), 0.16, 0.34)
    face_red = material(name + " red reflective face",
                        (0.66, 0.003, 0.008), 0.03, 0.25)
    reflective_white = material(name + " white reflective graphic",
                                (0.96, 0.97, 0.95), 0.02, 0.20)
    frame_white = material(name + " pale coated auxiliary frame",
                           (0.74, 0.76, 0.74), 0.34, 0.46)

    post_x = 0.0
    # The first road-context pass showed that the regulation-limit height and
    # 42 mm pipe read as unnaturally tall and slender beside normal sidewalks.
    # Keep the 600 mm sign face, but use a more typical street-scale silhouette.
    post_radius = 0.025
    post_height = 3.80
    cylinder(name + " red support post", (post_x, 0.0, post_height * 0.5),
             post_radius, post_height, red_paint, vertices=48)

    sign_center = (-0.370, 0.0, 3.80)
    hoop_radius = 0.370
    hoop_points = [
        (sign_center[0] + math.cos(math.tau * index / 128) * hoop_radius,
         0.0,
         sign_center[2] + math.sin(math.tau * index / 128) * hoop_radius)
        for index in range(128)
    ]
    tube_path(name + " circular red guard and support hoop", hoop_points,
              post_radius, red_paint, cyclic=True)

    plate_radius = 0.300
    cylinder(name + " double-sided aluminum disc", sign_center,
             plate_radius, 0.0012, reflective_white,
             rotation=(math.radians(90), 0.0, 0.0), vertices=128)

    for facing_front, y in ((True, -0.00075), (False, 0.00075)):
        side = "front" if facing_front else "rear"
        cylinder(name + f" {side} inset red field",
                 (sign_center[0], y, sign_center[2]), plate_radius - 0.021,
                 0.0002, face_red, rotation=(math.radians(90), 0.0, 0.0),
                 vertices=128)

    for facing_front, y_sign in ((True, -0.0010), (False, 0.0010)):
        side = "front" if facing_front else "rear"
        hydrant_face_graphic(
            name + f" {side} traced reflective lettering",
            (sign_center[0], sign_center[2]), y_sign,
            reflective_white, facing_front,
        )

    # Four flat tabs are welded between the hoop and one face of the disc.
    # They remain visible from that side while the graphic itself is duplicated.
    for index, degrees in enumerate((45, 135, 225, 315), start=1):
        _radial_strap(name + f" rear welded support tab {index}",
                      (sign_center[0], sign_center[2]), math.radians(degrees),
                      plate_radius - 0.008, hoop_radius - post_radius,
                      0.003, red_paint)

    # Empty auxiliary information frame, fixed only to the main support post.
    frame_left = post_x - 0.800
    frame_right = post_x - 0.015
    frame_top = 3.41
    frame_bottom = 3.01
    rail = 0.012
    cube(name + " auxiliary frame top",
         ((frame_left + frame_right) * 0.5, 0.0, frame_top),
         (frame_right - frame_left, 0.007, rail), frame_white, 0.002)
    cube(name + " auxiliary frame bottom",
         ((frame_left + frame_right) * 0.5, 0.0, frame_bottom),
         (frame_right - frame_left, 0.007, rail), frame_white, 0.002)
    for x, label in ((frame_left, "left"), (frame_right, "right")):
        cube(name + f" auxiliary frame {label} side",
             (x, 0.0, (frame_top + frame_bottom) * 0.5),
             (rail, 0.007, frame_top - frame_bottom), frame_white, 0.002)
    cube(name + " auxiliary frame post clamp", (post_x, 0.0, frame_top),
         (0.060, 0.050, 0.040), red_paint, 0.006)

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["asset_type"] = "fire_hydrant_sign"
    root["graphic_source"] = "procedural_geometry"
    root["double_sided"] = True
    root["auxiliary_frame_empty"] = True
    return root


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _preview_environment():
    scene = bpy.context.scene
    ground = material("Preview neutral ground", (0.075, 0.082, 0.084), 0.0, 0.88)
    cube("Preview ground", (0, 0, -0.045), (5.0, 5.0, 0.08), ground, 0.01)
    world = scene.world or bpy.data.worlds.new("Preview world")
    scene.world = world
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.045, 0.060, 0.075, 1.0)
    background.inputs["Strength"].default_value = 0.38
    for light_name, light_location, energy, size in (
        ("Preview key", (-2.8, -4.0, 5.1), 1050, 3.2),
        ("Preview fill", (2.5, 1.8, 3.8), 650, 2.8),
    ):
        data = bpy.data.lights.new(light_name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(light_name, data)
        bpy.context.collection.objects.link(light)
        light.location = light_location
        _look_at(light, (-0.35, 0.0, 2.35))
    camera_data = bpy.data.cameras.new("Preview Camera")
    camera = bpy.data.objects.new("Preview Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = 60
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 760
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    return camera


def _render_views(camera):
    scene = bpy.context.scene
    output_dir = ASSET_ROOT / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    for side, y in (("front", -6.8), ("rear", 6.8)):
        camera.location = (-0.38, math.copysign(11.0, y), 2.95)
        _look_at(camera, (-0.38, 0.0, 2.35))
        scene.render.filepath = str(output_dir / f"fire_hydrant_sign_{side}.png")
        bpy.ops.render.render(write_still=True)


def _options():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ASSET_ROOT / "blend" / "fire_hydrant_sign.blend")
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


if not EMBEDDED_BUILD:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_fire_hydrant_sign()
    options = _options()
    camera = _preview_environment()
    if not options.skip_render:
        _render_views(camera)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(options.output))
