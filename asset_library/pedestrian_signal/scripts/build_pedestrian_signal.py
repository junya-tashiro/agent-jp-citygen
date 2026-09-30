import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from asset_library.shared.surfaces import signal_finish, smooth_bevel



ASSET_ROOT = Path(__file__).resolve().parent.parent
POLE_HEIGHT = 4.8
STANDING_PERSON_LED_POINTS = (
    (-5, -20), (-4, -20), (-3, -20), (-2, -20), (-1, -20), (1, -20), (2, -20), (3, -20),
    (4, -20), (5, -20), (-5, -19), (-4, -19), (-3, -19), (-2, -19), (-1, -19), (1, -19),
    (2, -19), (3, -19), (4, -19), (5, -19), (-5, -18), (-4, -18), (-3, -18), (-2, -18),
    (-1, -18), (1, -18), (2, -18), (3, -18), (4, -18), (5, -18), (-4, -17), (-3, -17),
    (-2, -17), (-1, -17), (1, -17), (2, -17), (3, -17), (4, -17), (-4, -16), (-3, -16),
    (-2, -16), (-1, -16), (1, -16), (2, -16), (3, -16), (4, -16), (-4, -15), (-3, -15),
    (-2, -15), (-1, -15), (1, -15), (2, -15), (3, -15), (4, -15), (-4, -14), (-3, -14),
    (-2, -14), (-1, -14), (0, -14), (1, -14), (2, -14), (3, -14), (4, -14), (-4, -13),
    (-3, -13), (-2, -13), (-1, -13), (0, -13), (1, -13), (2, -13), (3, -13), (4, -13),
    (-4, -12), (-3, -12), (-2, -12), (-1, -12), (0, -12), (1, -12), (2, -12), (3, -12),
    (4, -12), (-4, -11), (-3, -11), (-2, -11), (-1, -11), (0, -11), (1, -11), (2, -11),
    (3, -11), (4, -11), (-4, -10), (-3, -10), (-2, -10), (-1, -10), (0, -10), (1, -10),
    (2, -10), (3, -10), (4, -10), (-4, -9), (-3, -9), (-2, -9), (-1, -9), (0, -9), (1, -9),
    (2, -9), (3, -9), (4, -9), (-4, -8), (-3, -8), (-2, -8), (-1, -8), (0, -8), (1, -8),
    (2, -8), (3, -8), (4, -8), (-4, -7), (-3, -7), (-2, -7), (-1, -7), (0, -7), (1, -7),
    (2, -7), (3, -7), (4, -7), (-4, -6), (-3, -6), (-2, -6), (-1, -6), (0, -6), (1, -6),
    (2, -6), (3, -6), (4, -6), (-4, -5), (-3, -5), (-2, -5), (-1, -5), (0, -5), (1, -5),
    (2, -5), (3, -5), (4, -5), (-4, -4), (-3, -4), (-2, -4), (-1, -4), (0, -4), (1, -4),
    (2, -4), (3, -4), (4, -4), (-4, -3), (-3, -3), (-2, -3), (-1, -3), (0, -3), (1, -3),
    (2, -3), (3, -3), (4, -3), (-5, -2), (-4, -2), (-3, -2), (-2, -2), (-1, -2), (0, -2),
    (1, -2), (2, -2), (3, -2), (4, -2), (-5, -1), (-4, -1), (-3, -1), (-2, -1), (-1, -1),
    (0, -1), (1, -1), (2, -1), (3, -1), (4, -1), (5, -1), (-6, 0), (-5, 0), (-4, 0), (-3, 0),
    (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (-6, 1), (-5, 1),
    (-4, 1), (-3, 1), (-2, 1), (-1, 1), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1),
    (-6, 2), (-5, 2), (-4, 2), (-3, 2), (-2, 2), (-1, 2), (0, 2), (1, 2), (2, 2), (3, 2),
    (4, 2), (5, 2), (6, 2), (-6, 3), (-5, 3), (-4, 3), (-3, 3), (-2, 3), (-1, 3), (0, 3),
    (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (-6, 4), (-5, 4), (-4, 4), (-3, 4),
    (-2, 4), (-1, 4), (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (-6, 5), (-5, 5),
    (-4, 5), (-3, 5), (-2, 5), (-1, 5), (0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (5, 5), (6, 5),
    (-6, 6), (-5, 6), (-4, 6), (-3, 6), (-2, 6), (-1, 6), (0, 6), (1, 6), (2, 6), (3, 6),
    (4, 6), (5, 6), (6, 6), (-6, 7), (-5, 7), (-4, 7), (-3, 7), (-2, 7), (-1, 7), (0, 7),
    (1, 7), (2, 7), (3, 7), (4, 7), (5, 7), (6, 7), (-6, 8), (-5, 8), (-4, 8), (-3, 8),
    (-2, 8), (-1, 8), (0, 8), (1, 8), (2, 8), (3, 8), (4, 8), (5, 8), (6, 8), (-6, 9), (-5, 9),
    (-4, 9), (-3, 9), (-2, 9), (-1, 9), (0, 9), (1, 9), (2, 9), (3, 9), (4, 9), (5, 9), (6, 9),
    (-6, 10), (-5, 10), (-4, 10), (-3, 10), (-2, 10), (-1, 10), (0, 10), (1, 10), (2, 10),
    (3, 10), (4, 10), (5, 10), (6, 10), (-6, 11), (-5, 11), (-4, 11), (-3, 11), (-2, 11),
    (-1, 11), (0, 11), (1, 11), (2, 11), (3, 11), (4, 11), (5, 11), (6, 11), (-5, 12),
    (-4, 12), (-3, 12), (-2, 12), (-1, 12), (0, 12), (1, 12), (2, 12), (3, 12), (4, 12),
    (5, 12), (-3, 13), (-2, 13), (-1, 13), (0, 13), (1, 13), (2, 13), (3, 13), (-1, 14),
    (0, 14), (1, 14), (-2, 15), (-1, 15), (0, 15), (1, 15), (2, 15), (-2, 16), (-1, 16),
    (0, 16), (1, 16), (2, 16), (-2, 17), (-1, 17), (0, 17), (1, 17), (2, 17), (-3, 18),
    (-2, 18), (-1, 18), (0, 18), (1, 18), (2, 18), (3, 18), (-3, 19), (-2, 19), (-1, 19),
    (0, 19), (1, 19), (2, 19), (3, 19), (-2, 20), (-1, 20), (0, 20), (1, 20), (2, 20),
)

WALKING_PERSON_LED_POINTS = (
    (-6, -20), (-5, -20), (-4, -20), (-3, -20), (-2, -20), (9, -20), (10, -20), (11, -20),
    (-6, -19), (-5, -19), (-4, -19), (-3, -19), (-2, -19), (10, -19), (11, -19), (12, -19),
    (-6, -18), (-5, -18), (-4, -18), (-3, -18), (-2, -18), (9, -18), (10, -18), (11, -18),
    (12, -18), (-5, -17), (-4, -17), (-3, -17), (-2, -17), (8, -17), (9, -17), (10, -17),
    (11, -17), (12, -17), (-5, -16), (-4, -16), (-3, -16), (-2, -16), (-1, -16), (7, -16),
    (8, -16), (9, -16), (10, -16), (11, -16), (12, -16), (-5, -15), (-4, -15), (-3, -15),
    (-2, -15), (-1, -15), (7, -15), (8, -15), (9, -15), (10, -15), (11, -15), (-5, -14),
    (-4, -14), (-3, -14), (-2, -14), (-1, -14), (6, -14), (7, -14), (8, -14), (9, -14),
    (10, -14), (11, -14), (-4, -13), (-3, -13), (-2, -13), (-1, -13), (0, -13), (6, -13),
    (7, -13), (8, -13), (9, -13), (10, -13), (-4, -12), (-3, -12), (-2, -12), (-1, -12),
    (0, -12), (5, -12), (6, -12), (7, -12), (8, -12), (9, -12), (10, -12), (-4, -11),
    (-3, -11), (-2, -11), (-1, -11), (0, -11), (5, -11), (6, -11), (7, -11), (8, -11),
    (9, -11), (-4, -10), (-3, -10), (-2, -10), (-1, -10), (0, -10), (5, -10), (6, -10),
    (7, -10), (8, -10), (9, -10), (-4, -9), (-3, -9), (-2, -9), (-1, -9), (0, -9), (1, -9),
    (4, -9), (5, -9), (6, -9), (7, -9), (8, -9), (-3, -8), (-2, -8), (-1, -8), (0, -8),
    (1, -8), (4, -8), (5, -8), (6, -8), (7, -8), (8, -8), (-3, -7), (-2, -7), (-1, -7),
    (0, -7), (1, -7), (2, -7), (4, -7), (5, -7), (6, -7), (7, -7), (8, -7), (-3, -6), (-2, -6),
    (-1, -6), (0, -6), (1, -6), (2, -6), (3, -6), (4, -6), (5, -6), (6, -6), (7, -6), (8, -6),
    (-2, -5), (-1, -5), (0, -5), (1, -5), (2, -5), (3, -5), (4, -5), (5, -5), (6, -5), (7, -5),
    (-2, -4), (-1, -4), (0, -4), (1, -4), (2, -4), (3, -4), (4, -4), (5, -4), (6, -4), (7, -4),
    (-2, -3), (-1, -3), (0, -3), (1, -3), (2, -3), (3, -3), (4, -3), (5, -3), (6, -3), (7, -3),
    (8, -3), (-1, -2), (0, -2), (1, -2), (2, -2), (3, -2), (4, -2), (5, -2), (6, -2), (7, -2),
    (8, -2), (11, -2), (12, -2), (-1, -1), (0, -1), (1, -1), (2, -1), (3, -1), (4, -1),
    (5, -1), (6, -1), (7, -1), (8, -1), (11, -1), (12, -1), (-8, 0), (-1, 0), (0, 0), (1, 0),
    (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (11, 0), (12, 0), (13, 0),
    (-13, 1), (-12, 1), (-11, 1), (-10, 1), (-9, 1), (-8, 1), (-7, 1), (-1, 1), (0, 1), (1, 1),
    (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (11, 1), (12, 1), (13, 1),
    (-11, 2), (-10, 2), (-9, 2), (-8, 2), (-7, 2), (-6, 2), (-2, 2), (-1, 2), (0, 2), (1, 2),
    (2, 2), (3, 2), (4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (11, 2), (12, 2), (13, 2), (-9, 3),
    (-8, 3), (-7, 3), (-6, 3), (-5, 3), (-4, 3), (-2, 3), (-1, 3), (0, 3), (1, 3), (2, 3),
    (3, 3), (4, 3), (5, 3), (6, 3), (7, 3), (10, 3), (11, 3), (12, 3), (13, 3), (-8, 4),
    (-7, 4), (-6, 4), (-5, 4), (-4, 4), (-3, 4), (-2, 4), (-1, 4), (0, 4), (1, 4), (2, 4),
    (3, 4), (4, 4), (5, 4), (6, 4), (7, 4), (10, 4), (11, 4), (12, 4), (-7, 5), (-6, 5),
    (-5, 5), (-4, 5), (-3, 5), (-2, 5), (-1, 5), (0, 5), (1, 5), (2, 5), (3, 5), (4, 5),
    (5, 5), (6, 5), (7, 5), (10, 5), (11, 5), (12, 5), (-5, 6), (-4, 6), (-3, 6), (-2, 6),
    (-1, 6), (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (7, 6), (8, 6), (9, 6),
    (10, 6), (11, 6), (12, 6), (-4, 7), (-3, 7), (-2, 7), (-1, 7), (0, 7), (1, 7), (2, 7),
    (3, 7), (4, 7), (5, 7), (6, 7), (7, 7), (8, 7), (9, 7), (10, 7), (11, 7), (12, 7), (-4, 8),
    (-3, 8), (-2, 8), (-1, 8), (0, 8), (1, 8), (2, 8), (3, 8), (4, 8), (5, 8), (6, 8), (7, 8),
    (8, 8), (9, 8), (10, 8), (11, 8), (-3, 9), (-2, 9), (-1, 9), (0, 9), (1, 9), (2, 9),
    (3, 9), (4, 9), (5, 9), (6, 9), (7, 9), (8, 9), (9, 9), (10, 9), (-3, 10), (-2, 10),
    (-1, 10), (0, 10), (1, 10), (2, 10), (3, 10), (4, 10), (5, 10), (6, 10), (7, 10), (8, 10),
    (-2, 11), (-1, 11), (0, 11), (1, 11), (2, 11), (3, 11), (4, 11), (5, 11), (6, 11),
    (-1, 12), (0, 12), (1, 12), (2, 12), (3, 12), (4, 12), (-1, 13), (0, 13), (1, 13), (2, 13),
    (-2, 14), (-1, 14), (0, 14), (1, 14), (2, 14), (-2, 15), (-1, 15), (0, 15), (1, 15),
    (2, 15), (-2, 16), (-1, 16), (0, 16), (1, 16), (2, 16), (-3, 17), (-2, 17), (-1, 17),
    (0, 17), (1, 17), (2, 17), (-4, 18), (-3, 18), (-2, 18), (-1, 18), (0, 18), (1, 18),
    (2, 18), (3, 18), (-3, 19), (-2, 19), (-1, 19), (0, 19), (1, 19), (2, 19), (3, 19),
    (-2, 20), (-1, 20), (0, 20), (1, 20),
)

def build_options(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-light", choices=("red", "blue"), default="red")
    parser.add_argument("--countdown", choices=("on", "off"), default="on")
    parser.add_argument("--countdown-level", type=int, choices=range(0, 9), default=8,
                        help="Remaining illuminated bars, 0..8; bars disappear from the top")
    parser.add_argument("--exterior-color", choices=("white", "brown"), default="white")
    parser.add_argument(
        "--support-side", choices=("left", "right"), default="left",
        help="Side on which the signal body emerges from the support pole",
    )
    parser.add_argument("--skip-render", action="store_true")
    args, _ = parser.parse_known_args(argv)
    return args


OPTIONS = build_options(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"
SUPPORT_SIGN = -1.0 if OPTIONS.support_side == "right" else 1.0
# Move the body without reflecting it. This keeps the asymmetric door hardware,
# rain hoods and person symbols in their authored orientation on either support side.
BODY_CENTER = Vector((SUPPORT_SIGN * 0.730, 0.0, 3.35))


def support_x(value):
    return SUPPORT_SIGN * value


def material(name, color, metallic=0.0, roughness=0.5, emission=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    return signal_finish(mat, name, metallic, emission)


def exterior_materials(color):
    if color == "brown":
        painted = material("Dark brown painted exterior", (0.070, 0.046, 0.036), 0.18, 0.62)
        trim = material("Dark brown housing trim", (0.022, 0.014, 0.011), 0.12, 0.70)
        hardware = material("Dark brown coated hardware", (0.050, 0.032, 0.025), 0.34, 0.52)
        return painted, trim, hardware
    painted = material("White painted aluminum", (0.84, 0.86, 0.83), 0.08, 0.58)
    trim = material("Dark housing trim", (0.040, 0.045, 0.043), 0.08, 0.70)
    hardware = material("Stainless hardware", (0.52, 0.56, 0.57), 0.62, 0.43)
    return painted, trim, hardware


def concrete_material():
    mat = material("Pale weathered concrete pole", (0.54, 0.55, 0.54), 0.0, 0.98)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Specular IOR Level"].default_value = 0.14
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 34.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.78
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.50, 0.51, 0.50, 1)
    ramp.color_ramp.elements[1].color = (0.57, 0.58, 0.57, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.075
    bump.inputs["Distance"].default_value = 0.010
    links.new(texcoord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def parent_to(obj, root):
    if root is not None:
        obj.parent = root
    return obj


def cube(name, location, scale, mat, root, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Rounded manufactured edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 5
        smooth_bevel(obj, modifier)
    return parent_to(obj, root)


def cylinder(name, location, radius, depth, mat, root, rotation=(0, 0, 0), vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return parent_to(obj, root)


def rectangular_frame(name, center, half_width, half_height, rail, half_depth,
                      mat, root, bevel):
    cube(name + " top", (center.x, center.y, center.z + half_height - rail / 2),
         (half_width, half_depth, rail / 2), mat, root, bevel)
    cube(name + " bottom", (center.x, center.y, center.z - half_height + rail / 2),
         (half_width, half_depth, rail / 2), mat, root, bevel)
    side_height = half_height - rail
    for side in (-1, 1):
        cube(name + " side", (center.x + side * (half_width - rail / 2), center.y, center.z),
             (rail / 2, half_depth, side_height), mat, root, bevel)


def rounded_panel(name, center, half_width, half_height, half_depth, radius,
                  mat, root, corner_segments=10):
    outline = []
    corners = (
        (half_width - radius, half_height - radius, 0.0),
        (-half_width + radius, half_height - radius, math.pi / 2),
        (-half_width + radius, -half_height + radius, math.pi),
        (half_width - radius, -half_height + radius, 3 * math.pi / 2),
    )
    for cx, cz, start_angle in corners:
        for index in range(corner_segments + 1):
            angle = start_angle + (math.pi / 2) * index / corner_segments
            outline.append((cx + math.cos(angle) * radius,
                            cz + math.sin(angle) * radius))
    count = len(outline)
    vertices = []
    for y in (-half_depth, half_depth):
        vertices.extend((center.x + x, center.y + y, center.z + z) for x, z in outline)
    faces = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, count + next_index, count + index))
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Soft panel edge", "BEVEL")
    bevel.width = 0.002
    bevel.segments = 2
    smooth_bevel(obj, bevel)
    return parent_to(obj, root)


def rounded_frame(name, center, half_width, half_height, rail, half_depth,
                  radius, mat, root, corner_segments=10):
    def outline(width, height, corner_radius):
        result = []
        corners = (
            (width - corner_radius, height - corner_radius, 0.0),
            (-width + corner_radius, height - corner_radius, math.pi / 2),
            (-width + corner_radius, -height + corner_radius, math.pi),
            (width - corner_radius, -height + corner_radius, 3 * math.pi / 2),
        )
        for cx, cz, start in corners:
            for index in range(corner_segments + 1):
                angle = start + (math.pi / 2) * index / corner_segments
                result.append((cx + math.cos(angle) * corner_radius,
                               cz + math.sin(angle) * corner_radius))
        return result

    outer = outline(half_width, half_height, radius)
    inner_radius = max(0.004, radius - rail)
    inner = outline(half_width - rail, half_height - rail, inner_radius)
    count = len(outer)
    vertices = []
    for y in (-half_depth, half_depth):
        vertices.extend((center.x + x, center.y + y, center.z + z) for x, z in outer)
        vertices.extend((center.x + x, center.y + y, center.z + z) for x, z in inner)
    faces = []
    outer_back, inner_back = 0, count
    outer_front, inner_front = count * 2, count * 3
    for index in range(count):
        nxt = (index + 1) % count
        faces.extend([
            (outer_front + index, outer_front + nxt, inner_front + nxt, inner_front + index),
            (outer_back + nxt, outer_back + index, inner_back + index, inner_back + nxt),
            (outer_back + index, outer_back + nxt, outer_front + nxt, outer_front + index),
            (inner_back + nxt, inner_back + index, inner_front + index, inner_front + nxt),
        ])
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    edge = obj.modifiers.new("Soft manufactured frame edge", "BEVEL")
    edge.width = 0.002
    edge.segments = 2
    smooth_bevel(obj, edge)
    return parent_to(obj, root)


def rounded_top_hood(name, center, half_width, half_height, side_drop, strip,
                     half_depth, radius, mat, root, corner_segments=12):
    """Thin inverted-U sheet following the rounded frame contour."""
    outer = [(-half_width, half_height - side_drop),
             (-half_width, half_height - radius)]
    left_center = (-half_width + radius, half_height - radius)
    for index in range(corner_segments + 1):
        angle = math.pi - (math.pi / 2) * index / corner_segments
        outer.append((left_center[0] + math.cos(angle) * radius,
                      left_center[1] + math.sin(angle) * radius))
    outer.append((half_width - radius, half_height))
    right_center = (half_width - radius, half_height - radius)
    for index in range(corner_segments + 1):
        angle = math.pi / 2 - (math.pi / 2) * index / corner_segments
        outer.append((right_center[0] + math.cos(angle) * radius,
                      right_center[1] + math.sin(angle) * radius))
    outer.append((half_width, half_height - side_drop))

    inner_radius = radius - strip
    inner = [(half_width - strip, half_height - side_drop),
             (half_width - strip, half_height - radius)]
    for index in range(corner_segments + 1):
        angle = (math.pi / 2) * index / corner_segments
        inner.append((right_center[0] + math.cos(angle) * inner_radius,
                      right_center[1] + math.sin(angle) * inner_radius))
    inner.append((-half_width + radius, half_height - strip))
    for index in range(corner_segments + 1):
        angle = math.pi / 2 + (math.pi / 2) * index / corner_segments
        inner.append((left_center[0] + math.cos(angle) * inner_radius,
                      left_center[1] + math.sin(angle) * inner_radius))
    inner.append((-half_width + strip, half_height - side_drop))
    inner.reverse()

    if len(outer) != len(inner):
        raise ValueError("Rain hood contour paths must have matching points")
    count = len(outer)
    vertices = []
    for y in (-half_depth, half_depth):
        vertices.extend((center.x + x, center.y + y, center.z + z) for x, z in outer)
        vertices.extend((center.x + x, center.y + y, center.z + z) for x, z in inner)
    outer_back, inner_back = 0, count
    outer_front, inner_front = count * 2, count * 3
    faces = []
    for index in range(count - 1):
        nxt = index + 1
        faces.extend([
            (outer_front + index, outer_front + nxt, inner_front + nxt, inner_front + index),
            (outer_back + nxt, outer_back + index, inner_back + index, inner_back + nxt),
            (outer_back + index, outer_back + nxt, outer_front + nxt, outer_front + index),
            (inner_back + nxt, inner_back + index, inner_front + index, inner_front + nxt),
        ])
    faces.extend([
        (outer_back, outer_front, inner_front, inner_back),
        (outer_back + count - 1, inner_back + count - 1,
         inner_front + count - 1, outer_front + count - 1),
    ])
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate()
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    edge = obj.modifiers.new("Rolled rain hood edge", "BEVEL")
    edge.width = 0.0015
    edge.segments = 2
    smooth_bevel(obj, edge)
    return parent_to(obj, root)


def pipe(name, points, radius, mat, root):
    curve = bpy.data.curves.new(name + " Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = radius
    curve.bevel_resolution = 5
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return parent_to(obj, root)


def straight_bent_pipe(name, points, radius, mat, root):
    """Pipe following explicit straight runs and a sampled elbow without spline bowing."""
    curve = bpy.data.curves.new(name + " Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 5
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return parent_to(obj, root)


def segment_distance(point, start, end):
    px, pz = point
    ax, az = start
    bx, bz = end
    dx, dz = bx - ax, bz - az
    length_sq = dx * dx + dz * dz
    if length_sq == 0:
        return math.hypot(px - ax, pz - az)
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length_sq))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def point_in_polygon(point, polygon):
    x, z = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, z1 = previous
        x2, z2 = current
        if (z1 > z) != (z2 > z):
            crossing_x = (x2 - x1) * (z - z1) / (z2 - z1) + x1
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def person_led_points(kind):
    step = 0.0055
    design_points = (STANDING_PERSON_LED_POINTS if kind == "red"
                     else WALKING_PERSON_LED_POINTS)
    return [(ix * step, iz * step) for ix, iz in design_points]


def add_person_leds(label, center, points, active, lit_color, dark_color, root):
    dot_material = material(
        label + " LED material",
        lit_color if active else dark_color,
        roughness=0.28 if active else 0.68,
        emission=lit_color if active else None,
        strength=7.0 if active else 0.0,
    )
    vertices, faces = [], []
    segments = 12
    radius, depth = 0.0025, 0.0025
    for px, pz in points:
        base = len(vertices)
        for y in (-depth * 0.5, depth * 0.5):
            vertices.extend((center.x + px + math.cos(math.tau * i / segments) * radius,
                             center.y + 0.010 + y,
                             center.z + pz + math.sin(math.tau * i / segments) * radius)
                            for i in range(segments))
        for i in range(segments):
            nxt = (i + 1) % segments
            faces.append((base + i, base + nxt, base + segments + nxt, base + segments + i))
        faces.append(tuple(base + i for i in reversed(range(segments))))
        faces.append(tuple(base + segments + i for i in range(segments)))
    mesh = bpy.data.meshes.new(label + " LEDs Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(dot_material)
    obj = bpy.data.objects.new(label + " LEDs", mesh)
    bpy.context.collection.objects.link(obj)
    parent_to(obj, root)


def add_countdown(center, color, dark_color, level, enabled, root):
    active_material = material("Countdown illuminated bars", color, roughness=0.25,
                               emission=color, strength=7.0)
    dark_material = material("Countdown unlit bars", dark_color, roughness=0.72)
    for side in (-1, 1):
        for row in range(8):
            # row zero is the lowest segment; reducing level extinguishes the top first.
            lit = enabled and row < level
            z = center.z - 0.086 + row * 0.0245
            cube("Countdown bar", (center.x + side * 0.106, center.y + 0.008, z),
                 (0.006, 0.003, 0.008), active_material if lit else dark_material,
                 root, bevel=0.003)


def build_signal(root):
    painted, trim, hardware = exterior_materials(OPTIONS.exterior_color)
    rubber = material("Lens sealing rubber", (0.008, 0.010, 0.009), roughness=0.80)
    dark_lens = material("Smoked pedestrian lens", (0.008, 0.012, 0.011), roughness=0.30)
    red = (1.0, 0.025, 0.012)
    cyan = (0.005, 0.75, 0.48)
    dark_red = (0.018, 0.002, 0.001)
    dark_cyan = (0.001, 0.018, 0.011)

    # Published full-size proportions: 380 x 700 x 140 mm.
    cube("Pedestrian signal rounded body", BODY_CENTER, (0.190, 0.070, 0.350),
         painted, root, bevel=0.055)
    cube("Pedestrian signal recessed body bed", BODY_CENTER + Vector((0, -0.068, 0)),
         (0.174, 0.006, 0.318), painted, root, bevel=0.040)

    hood_color = ((0.070, 0.046, 0.036) if OPTIONS.exterior_color == "brown"
                  else (0.84, 0.86, 0.83))
    hood_material = material("Matching painted thin metal rain hood", hood_color, 0.55, 0.32)

    upper = BODY_CENTER + Vector((0, -0.103, 0.160))
    lower = BODY_CENTER + Vector((0, -0.103, -0.160))
    for label, center in (("Red standing aspect", upper), ("Blue walking aspect", lower)):
        # Negative Y is forward. The coloured frame projects furthest; rubber and
        # smoked lens step progressively rearward into the body.
        rounded_frame(label + " rounded retaining frame", center,
                      0.142, 0.142, 0.014, 0.016, 0.038, painted, root)
        rounded_panel(label + " recessed rounded smoked lens",
                      center + Vector((0, 0.020, 0)),
                      0.125, 0.125, 0.006, 0.032, dark_lens, root)
        # One thin sheet follows the same rounded upper contour as the frame,
        # then continues vertically down both sides.
        rounded_top_hood(label + " frame-following thin rain hood",
                         center + Vector((0, -0.050, 0)),
                         0.146, 0.146, 0.052, 0.004, 0.060, 0.038,
                         hood_material, root)

    red_active = OPTIONS.active_light == "red"
    add_person_leds("Red standing person", upper, person_led_points("red"), red_active,
                    red, dark_red, root)
    add_person_leds("Blue walking person", lower, person_led_points("blue"), not red_active,
                    cyan, dark_cyan, root)

    countdown_color = red if red_active else cyan
    countdown_dark = dark_red if red_active else dark_cyan
    # Both aspects physically contain countdown elements. Only the aspect whose
    # person symbol is currently dark illuminates them; the other set remains
    # visible as unlit hardware.
    add_countdown(upper, countdown_color, countdown_dark,
                  OPTIONS.countdown_level,
                  OPTIONS.countdown == "on" and not red_active, root)
    add_countdown(lower, countdown_color, countdown_dark,
                  OPTIONS.countdown_level,
                  OPTIONS.countdown == "on" and red_active, root)

    # Hinges and latches follow the two-door construction of real Japanese units.
    for z in (BODY_CENTER.z - 0.160, BODY_CENTER.z + 0.160):
        for side in (-1, 1):
            # Compact hinge/latch blocks sit directly against the 380 mm body.
            x = BODY_CENTER.x + side * 0.190
            cube("Signal door side hardware", (x, -0.004, z), (0.010, 0.018, 0.026),
                 hardware, root, 0.004)
    return painted, hardware


def build_support(root, painted, hardware, include_pole=True):
    pole_radius = 0.082
    if OPTIONS.exterior_color == "brown":
        pole_material = painted
        arm_material = painted
    else:
        pole_material = concrete_material()
        arm_material = material("Matte galvanized support pipes", (0.62, 0.65, 0.64),
                                0.42, 0.56)
    if include_pole:
        cylinder("Pedestrian signal support pole", (0, 0.16, POLE_HEIGHT / 2), pole_radius,
                 POLE_HEIGHT, pole_material, root, vertices=64)
        cylinder("Support pole top cap", (0, 0.16, POLE_HEIGHT + 0.012), pole_radius + 0.004,
                 0.024, arm_material, root, vertices=64)

    # Two independent arms leave the pole horizontally, then turn vertically
    # at the signal to support the upper and lower ends of the body.
    straight_bent_pipe("Upper bent pedestrian signal arm",
                       [(support_x(0.02), 0.15, 3.76), (support_x(0.64), 0.12, 3.76),
                        (support_x(0.675), 0.115, 3.755), (support_x(0.705), 0.105, 3.735),
                        (support_x(0.725), 0.095, 3.705), (support_x(0.73), 0.09, 3.66),
                        (support_x(0.73), 0.09, 3.58), (support_x(0.80), 0.08, 3.58)],
                       0.027, arm_material, root)
    straight_bent_pipe("Lower bent pedestrian signal arm",
                       [(support_x(0.02), 0.15, 2.94), (support_x(0.64), 0.12, 2.94),
                        (support_x(0.675), 0.115, 2.945), (support_x(0.705), 0.105, 2.965),
                        (support_x(0.725), 0.095, 2.995), (support_x(0.73), 0.09, 3.04),
                        (support_x(0.73), 0.09, 3.12), (support_x(0.80), 0.08, 3.12)],
                       0.027, arm_material, root)
    for z in (3.12, 3.58):
        cube("Signal end mounting block", (support_x(0.730), 0.08, z), (0.055, 0.035, 0.040),
             arm_material, root, 0.012)
        cylinder("Signal mounting bolt", (support_x(0.730), 0.035, z), 0.012, 0.016, hardware, root,
                 rotation=(math.radians(90), 0, 0), vertices=6)

    cable = material("Black outdoor cable", (0.005, 0.006, 0.005), roughness=0.78)
    pipe("Pedestrian signal cable",
         [(support_x(0.02), 0.08, 2.70), (support_x(0.24), 0.02, 2.61),
          (support_x(0.52), 0.02, 2.64), (support_x(0.72), 0.04, 2.94)],
         0.009, cable, root)
    for z in ((2.73, 3.97) if include_pole else ()):
        bpy.ops.mesh.primitive_torus_add(major_radius=pole_radius + 0.006,
                                        minor_radius=0.006, major_segments=48,
                                        minor_segments=8, location=(0, 0.16, z))
        band = bpy.context.object
        band.name = "Support pole fixing band"
        band.data.materials.append(hardware)
        parent_to(band, root)


def create_pedestrian_signal(name="Pedestrian Signal", location=(0, 0, 0),
                             rotation_degrees=0, active_light="red", countdown="on",
                             countdown_level=8, exterior_color="white",
                             support_side="left", include_support=True):
    """Build one editable pedestrian signal directly in the current scene."""
    global OPTIONS, SUPPORT_SIGN, BODY_CENTER
    previous = OPTIONS, SUPPORT_SIGN, BODY_CENTER.copy()
    OPTIONS = argparse.Namespace(
        active_light=active_light, countdown=countdown,
        countdown_level=countdown_level, exterior_color=exterior_color,
        support_side=support_side, skip_render=True,
    )
    SUPPORT_SIGN = -1.0 if support_side == "right" else 1.0
    BODY_CENTER = Vector((SUPPORT_SIGN * 0.730, 0.0, 3.35))
    try:
        root = bpy.data.objects.new(name, None)
        bpy.context.collection.objects.link(root)
        painted, hardware = build_signal(root)
        build_support(root, painted, hardware, include_pole=include_support)
        root.location = location
        root.rotation_euler[2] = math.radians(rotation_degrees)
        return root
    finally:
        OPTIONS, SUPPORT_SIGN, BODY_CENTER = previous


def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


if not EMBEDDED_BUILD:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)

    asset_collection = bpy.data.collections.new("Pedestrian Signal Asset")
    bpy.context.scene.collection.children.link(asset_collection)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[asset_collection.name]
    root = bpy.data.objects.new("Pedestrian Signal Asset Root", None)
    asset_collection.objects.link(root)
    painted, hardware = build_signal(root)
    build_support(root, painted, hardware)

    preview = bpy.data.collections.new("Preview Environment")
    bpy.context.scene.collection.children.link(preview)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[preview.name]
    ground = material("Preview asphalt", (0.045, 0.050, 0.052), roughness=0.88)
    cube("Preview ground", (0.6, 0.7, -0.05), (2.2, 2.0, 0.05), ground, None)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 64
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 900
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Color"].default_value = (0.035, 0.050, 0.070, 1)
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"].default_value = 0.72

    sun_data = bpy.data.lights.new("Soft daylight", "SUN")
    sun_data.energy = 1.8
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Soft daylight", sun_data)
    preview.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-140))

    area_data = bpy.data.lights.new("Front fill", "AREA")
    area_data.energy = 360
    area_data.shape = "DISK"
    area_data.size = 4.0
    area = bpy.data.objects.new("Front fill", area_data)
    preview.objects.link(area)
    area.location = (2.2, -4.0, 5.0)
    look_at(area, BODY_CENTER)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    preview.objects.link(camera)
    camera.location = (SUPPORT_SIGN * 3.25, -7.8, 3.75)
    camera_data.lens = 72
    look_at(camera, (BODY_CENTER.x, 0.0, 2.75))
    scene.camera = camera

    color_suffix = "" if OPTIONS.exterior_color == "white" else "_brown"
    countdown_suffix = "" if OPTIONS.countdown == "off" else f"_countdown{OPTIONS.countdown_level}"
    support_suffix = "" if OPTIONS.support_side == "left" else "_right_support"
    variant = f"pedestrian_signal_{OPTIONS.active_light}{color_suffix}{countdown_suffix}{support_suffix}"
    scene.render.filepath = str(ASSET_ROOT / f"renders/{variant}.png")
    if not OPTIONS.skip_render and not EMBEDDED_BUILD:
        bpy.ops.render.render(write_still=True)
    if not EMBEDDED_BUILD:
        bpy.ops.wm.save_as_mainfile(filepath=str(ASSET_ROOT / f"blend/{variant}.blend"))
