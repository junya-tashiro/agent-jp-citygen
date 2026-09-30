"""Procedural Japanese roadside two-lamp warning unit (no image textures)."""

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"
DEFAULT_SCALE = 0.42
POST_LENGTH_SCALE = 0.70


def material(name, color, metallic=0.0, roughness=0.5, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    return mat


def cube(name, location, dimensions, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Small manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def cylinder(name, location, radius, depth, mat, vertices=40, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def _visor(name, center_z, outer_radius, depth, mat):
    """Upper semicircular sheet-metal hood, open below and projecting forward."""
    segments = 24
    inner_radius = outer_radius - 0.018
    rear_y, front_y = -0.116, -0.116 - depth
    vertices = []
    for y in (rear_y, front_y):
        for radius in (inner_radius, outer_radius):
            vertices.extend((math.cos(math.pi * i / segments) * radius, y,
                             center_z + math.sin(math.pi * i / segments) * radius)
                            for i in range(segments + 1))
    ring = segments + 1
    faces = []
    inner_rear, outer_rear, inner_front, outer_front = 0, ring, ring * 2, ring * 3
    for index in range(segments):
        nxt = index + 1
        faces.extend(((outer_rear + index, outer_rear + nxt,
                       outer_front + nxt, outer_front + index),
                      (inner_front + index, inner_front + nxt,
                       inner_rear + nxt, inner_rear + index),
                      (inner_front + index, outer_front + index,
                       outer_front + nxt, inner_front + nxt),
                      (outer_rear + index, inner_rear + index,
                       inner_rear + nxt, outer_rear + nxt)))
    faces.extend(((inner_rear, outer_rear, outer_front, inner_front),
                  (inner_rear + segments, inner_front + segments,
                   outer_front + segments, outer_rear + segments)))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _lamp(name, center_z, housing, bezel, amber):
    # One continuous large optic: intentionally no LED dots and no emission.
    cylinder(name + " recessed cup", (0, -0.108, center_z), 0.128, 0.055,
             bezel, 48, (math.radians(90), 0, 0))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24,
                                        location=(0, -0.151, center_z))
    lens = bpy.context.object
    lens.name = name + " single amber lens"
    lens.scale = (0.108, 0.050, 0.108)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lens.data.materials.append(amber)
    for polygon in lens.data.polygons:
        polygon.use_smooth = True
    bpy.ops.mesh.primitive_torus_add(major_radius=0.113, minor_radius=0.012,
                                    major_segments=48, minor_segments=10,
                                    location=(0, -0.181, center_z),
                                    rotation=(math.radians(90), 0, 0))
    bpy.context.object.name = name + " broad retaining ring"
    bpy.context.object.data.materials.append(bezel)
    _visor(name + " deep upper visor", center_z, 0.154, 0.145, housing)


def create_dual_warning_lamp(name="Dual Warning Lamp", location=(0, 0, 0),
                             rotation_degrees=0, scale=DEFAULT_SCALE):
    """Create an editable two-lamp roadside warning unit facing local -Y."""
    before = set(bpy.context.scene.objects)
    # This asset intentionally has one exterior variant. Match the established
    # brown roadside-equipment palette used by both signal assets.
    housing = material(name + " dark brown painted exterior",
                       (0.070, 0.046, 0.036), 0.18, 0.62)
    post_mat = material(name + " dark brown coated post and mounting",
                        (0.050, 0.032, 0.025), 0.22, 0.66)
    bezel = material(name + " dark brown lamp bezel",
                     (0.022, 0.014, 0.011), 0.12, 0.70)
    amber = material(name + " unlit amber glass", (0.46, 0.145, 0.020), 0.02, 0.28, 0.10)

    original_post_height = 1.08
    post_height = original_post_height * POST_LENGTH_SCALE
    top_shift = original_post_height - post_height
    cylinder(name + " support post", (0, 0.055, post_height * 0.5),
             0.068, post_height, post_mat, 40)
    cylinder(name + " post top sleeve", (0, 0.055, 1.035 - top_shift),
             0.086, 0.18, housing, 40)
    cube(name + " lamp cabinet", (0, 0, 1.425 - top_shift),
         (0.34, 0.205, 0.78), housing, 0.018)
    cube(name + " rear mounting spine", (0, 0.126, 1.425 - top_shift),
         (0.14, 0.060, 0.70), post_mat, 0.012)
    _lamp(name + " upper", 1.635 - top_shift, housing, bezel, amber)
    _lamp(name + " lower", 1.215 - top_shift, housing, bezel, amber)

    fastener = material(name + " dark brown coated fasteners",
                        (0.050, 0.032, 0.025), 0.34, 0.52)
    for z in (1.18, 1.67):
        for x in (-0.174, 0.174):
            cylinder(name + " side fastener", (x, 0.0, z - top_shift), 0.009, 0.010,
                     fastener, 20, (0, math.radians(90), 0))

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root.scale = (scale, scale, scale)
    root["asset_type"] = "dual_warning_lamp"
    root["lamp_emission"] = 0.0
    root["graphic_source"] = "procedural_geometry"
    root["asset_scale"] = scale
    root["post_length_scale"] = POST_LENGTH_SCALE
    return root


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _render_preview(output):
    scene = bpy.context.scene
    ground_mat = material("Preview neutral ground", (0.075, 0.082, 0.084), 0.0, 0.88)
    cube("Preview ground", (0, 0, -0.045), (4.0, 4.0, 0.08), ground_mat, 0.01)
    world = scene.world or bpy.data.worlds.new("Preview world")
    scene.world = world
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes
                      if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.055, 0.072, 0.090, 1.0)
    background.inputs["Strength"].default_value = 0.34

    for name, location, energy, size in (
        ("Preview key", (-2.7, -3.8, 4.7), 900, 3.0),
        ("Preview fill", (2.8, -1.8, 2.8), 420, 2.4),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        _look_at(light, (0, 0, 1.15))

    camera_data = bpy.data.cameras.new("Preview Camera")
    camera = bpy.data.objects.new("Preview Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (2.15, -4.8, 2.18)
    camera_data.lens = 66
    _look_at(camera, (0, 0, 1.03))
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 820
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.filepath = str(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


def _options():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ASSET_ROOT / "blend" / "dual_warning_lamp.blend")
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


if not EMBEDDED_BUILD:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_dual_warning_lamp()
    options = _options()
    output = options.output
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    if not options.skip_render:
        _render_preview(ASSET_ROOT / "renders" / "dual_warning_lamp.png")
