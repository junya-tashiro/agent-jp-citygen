"""Build a rectangular Japanese underground fire-hydrant cover."""

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"


def material(name, color, metallic=0.0, roughness=0.5, cast_noise=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if cast_noise:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 115.0
        noise.inputs["Detail"].default_value = 5.0
        noise.inputs["Roughness"].default_value = 0.82
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.18
        ramp.color_ramp.elements[0].color = (0.060, 0.055, 0.050, 1.0)
        ramp.color_ramp.elements[1].position = 0.82
        ramp.color_ramp.elements[1].color = (0.140, 0.122, 0.106, 1.0)
        roughness_map = nodes.new("ShaderNodeMapRange")
        roughness_map.inputs["From Min"].default_value = 0.0
        roughness_map.inputs["From Max"].default_value = 1.0
        roughness_map.inputs["To Min"].default_value = 0.52
        roughness_map.inputs["To Max"].default_value = 0.74
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.28
        bump.inputs["Distance"].default_value = 0.0008
        mat.node_tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        mat.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        mat.node_tree.links.new(noise.outputs["Fac"], roughness_map.inputs["Value"])
        mat.node_tree.links.new(roughness_map.outputs["Result"], bsdf.inputs["Roughness"])
        mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        mat.node_tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cube(name, location, dimensions, mat, bevel=0.0, rotation=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=(0, 0, rotation))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Cast edge radius", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cylinder(name, location, radius, depth, mat, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def rounded_loop(width, height, radius, z, corner_segments=8):
    points = []
    for cx, cy, start in (
        (width / 2 - radius, height / 2 - radius, 0),
        (-width / 2 + radius, height / 2 - radius, 90),
        (-width / 2 + radius, -height / 2 + radius, 180),
        (width / 2 - radius, -height / 2 + radius, 270),
    ):
        for index in range(corner_segments + 1):
            angle = math.radians(start + index * 90 / corner_segments)
            points.append((cx + math.cos(angle) * radius,
                           cy + math.sin(angle) * radius, z))
    return points


def rounded_prism(name, width, height, radius, bottom, top, mat):
    lower = rounded_loop(width, height, radius, bottom)
    upper = rounded_loop(width, height, radius, top)
    count = len(lower)
    vertices = lower + upper
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Soft cast perimeter", "BEVEL")
    bevel.width = 0.003
    bevel.segments = 2
    return obj


def rounded_ring(name, outer_size, inner_size, outer_radius, inner_radius,
                 bottom, top, mat):
    outer_bottom = rounded_loop(*outer_size, outer_radius, bottom)
    inner_bottom = rounded_loop(*inner_size, inner_radius, bottom)
    outer_top = rounded_loop(*outer_size, outer_radius, top)
    inner_top = rounded_loop(*inner_size, inner_radius, top)
    count = len(outer_bottom)
    vertices = outer_bottom + inner_bottom + outer_top + inner_top
    ob, ib, ot, it = 0, count, count * 2, count * 3
    faces = []
    for index in range(count):
        nxt = (index + 1) % count
        faces.extend(((ot + index, ot + nxt, it + nxt, it + index),
                      (ob + nxt, ob + index, ib + index, ib + nxt),
                      (ob + index, ob + nxt, ot + nxt, ot + index),
                      (ib + nxt, ib + index, it + index, it + nxt)))
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Rounded cast ring edges", "BEVEL")
    bevel.width = 0.002
    bevel.segments = 2
    return obj


def diagonal_ribs(name, angle_degrees, offsets, mat):
    angle = math.radians(angle_degrees)
    direction = Vector((math.cos(angle), math.sin(angle)))
    normal = Vector((-direction.y, direction.x))
    half_x, half_y = 0.218, 0.168
    for index, offset in enumerate(offsets, 1):
        centre = normal * offset
        limits = []
        if abs(direction.x) > 1e-8:
            limits += [(half_x - centre.x) / direction.x,
                       (-half_x - centre.x) / direction.x]
        if abs(direction.y) > 1e-8:
            limits += [(half_y - centre.y) / direction.y,
                       (-half_y - centre.y) / direction.y]
        valid = [value for value in limits
                 if abs((centre + direction * value).x) <= half_x + 1e-6
                 and abs((centre + direction * value).y) <= half_y + 1e-6]
        if len(valid) < 2:
            continue
        low, high = min(valid), max(valid)
        midpoint = centre + direction * ((low + high) * 0.5)
        cube(f"{name} {index:02d}", (midpoint.x, midpoint.y, 0.0025),
             (high - low, 0.008, 0.002), mat, 0.0007, angle)


def raised_text(name, body, location, size, depth, mat):
    curve = bpy.data.curves.new(name + " Curve", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = depth
    curve.offset = 0.0
    curve.bevel_depth = 0.0007
    curve.bevel_resolution = 2
    curve.resolution_u = 16
    curve.fill_mode = "BOTH"
    from asset_library.shared.fonts import japanese_font
    curve.font = japanese_font()
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    return obj


def fire_service_emblem(name, x, raised, dark):
    cylinder(name + " hexagonal cartouche", (x, 0.045, 0.0035), 0.052,
             0.003, dark, vertices=6)
    cylinder(name + " central boss", (x, 0.045, 0.0058), 0.012, 0.002, raised)
    for index in range(8):
        angle = index * math.tau / 8
        cube(name + f" radial ray {index + 1}",
             (x + math.cos(angle) * 0.026,
              0.045 + math.sin(angle) * 0.026, 0.0058),
             (0.036, 0.008, 0.002), raised, 0.0007, angle)


def create_fire_hydrant_cover(name="Rectangular Fire Hydrant Cover",
                               location=(0, 0, 0), rotation_degrees=0):
    """Create a 500 x 400 mm single-outlet hydrant cover and support frame."""
    before = set(bpy.context.scene.objects)
    iron = material(name + " cast iron", (0.095, 0.084, 0.074),
                    metallic=0.62, roughness=0.64, cast_noise=True)
    raised = recess = iron
    rounded_ring(name + " buried support frame", (0.560, 0.460),
                 (0.506, 0.406), 0.062, 0.047, -0.080, 0.001, iron)
    rounded_prism(name + " cover plate", 0.500, 0.400, 0.044,
                  -0.047, 0.0015, iron)
    offsets = [index * 0.030 for index in range(-10, 11)]
    diagonal_ribs(name + " northeast diagonal rib", 52, offsets, raised)
    diagonal_ribs(name + " northwest diagonal rib", -52, offsets, raised)
    rounded_ring(name + " cover perimeter band", (0.486, 0.386),
                 (0.446, 0.346), 0.040, 0.025, 0.0015, 0.004, raised)
    fire_service_emblem(name + " left fire emblem", -0.164, raised, recess)
    fire_service_emblem(name + " right fire emblem", 0.164, raised, recess)
    for index, (character, x) in enumerate(zip("消火栓", (-0.068, 0.0, 0.068)), 1):
        cylinder(name + f" hydrant character cartouche {index}",
                 (x, -0.092, 0.0035), 0.031, 0.003, recess, vertices=6)
        raised_text(name + f" hydrant cast character {character}", character,
                    (x, -0.092, 0.0062), 0.052, 0.00045, raised)
    for x, label in ((-0.207, "left"), (0.207, "right")):
        cube(name + f" {label} lifting recess", (x, -0.145, 0.003),
             (0.055, 0.026, 0.002), recess, 0.010)
        cube(name + f" {label} lifting lip", (x, -0.145, 0.0045),
             (0.047, 0.006, 0.002), raised, 0.0007)
    cube(name + " key slot", (0.0, -0.166, 0.0045),
         (0.013, 0.037, 0.002), recess, 0.004)
    cylinder(name + " key slot head", (0.0, -0.148, 0.0045),
             0.009, 0.002, recess, vertices=32)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["asset_type"] = "rectangular_fire_hydrant_cover"
    root["nominal_cover_size_mm"] = (500, 400)
    root["frame_size_mm"] = (560, 460)
    root["installation_surface_z"] = 0.0
    root["asset_material_count"] = 1
    return root


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def preview_environment():
    scene = bpy.context.scene
    asphalt = material("Preview asphalt", (0.018, 0.021, 0.020),
                       roughness=0.94, cast_noise=False)
    cube("Preview road surface", (0, 0, -0.052), (2.2, 1.8, 0.10), asphalt)
    world = scene.world or bpy.data.worlds.new("Preview world")
    scene.world = world
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.12, 0.14, 0.16, 1)
    background.inputs["Strength"].default_value = 0.45
    for label, position, energy, size in (
        ("key", (-1.4, -1.8, 2.6), 380, 2.0),
        ("fill", (1.2, 0.8, 1.8), 180, 1.6),
    ):
        data = bpy.data.lights.new("Preview " + label, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new("Preview " + label, data)
        bpy.context.collection.objects.link(light)
        light.location = position
        look_at(light, (0, 0, 0))
    camera_data = bpy.data.cameras.new("Preview Camera")
    camera = bpy.data.objects.new("Preview Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    return camera


def render_views(camera):
    output = ASSET_ROOT / "renders"
    output.mkdir(parents=True, exist_ok=True)
    for label, position, lens in (
        ("oblique", (0.74, -0.92, 0.86), 58),
        ("top", (0.0, 0.0, 1.35), 68),
    ):
        camera.location = position
        camera.data.lens = lens
        look_at(camera, (0, 0, 0))
        bpy.context.scene.render.filepath = str(output / f"fire_hydrant_cover_{label}.png")
        bpy.ops.render.render(write_still=True)


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ASSET_ROOT / "blend" / "fire_hydrant_cover.blend")
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


if not EMBEDDED_BUILD:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_fire_hydrant_cover()
    opts = options()
    camera = preview_environment()
    if not opts.skip_render:
        render_views(camera)
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(opts.output))
