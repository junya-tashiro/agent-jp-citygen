"""Procedural mixed low-shrub planting for Japanese urban roadsides."""

import argparse
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asset_library.guardrail.scripts import build_guardrail  # noqa: E402


def _material(name, color, roughness=0.6, variation=0.0, subsurface=0.0):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    if 'leaves' in name or 'fresh tips' in name:
        from asset_library.street_tree.scripts.procedural_textures import shrub_leaf_material
        return shrub_leaf_material(name, color)
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
    if variation:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 35.0
        noise.inputs["Detail"].default_value = 4.0
        noise.inputs["Roughness"].default_value = 0.72
        ramp = nodes.new("ShaderNodeValToRGB")
        darker = tuple(channel * (1.0 - variation) for channel in color)
        lighter = tuple(min(1.0, channel * (1.0 + variation * 0.55)) for channel in color)
        ramp.color_ramp.elements[0].color = (*darker, 1.0)
        ramp.color_ramp.elements[1].color = (*lighter, 1.0)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.0012
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _soil_material():
    existing = bpy.data.materials.get("Planting dark urban soil")
    if existing is not None:
        return existing
    mat = _material("Planting dark urban soil", (0.075, 0.052, 0.030), 0.96)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    coordinates = nodes.new("ShaderNodeTexCoord")
    patches = nodes.new("ShaderNodeTexNoise")
    patches.name = "Damp and dry soil patches"
    patches.inputs["Scale"].default_value = 3.2
    patches.inputs["Detail"].default_value = 6.0
    patches.inputs["Roughness"].default_value = 0.84
    links.new(coordinates.outputs["Object"], patches.inputs["Vector"])
    colour = nodes.new("ShaderNodeValToRGB")
    colour.color_ramp.elements[0].position = 0.22
    colour.color_ramp.elements[0].color = (0.027, 0.019, 0.012, 1.0)
    colour.color_ramp.elements[1].position = 0.80
    colour.color_ramp.elements[1].color = (0.145, 0.095, 0.045, 1.0)
    links.new(patches.outputs["Fac"], colour.inputs["Fac"])
    links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
    grains = nodes.new("ShaderNodeTexNoise")
    grains.name = "Fine soil grains"
    grains.inputs["Scale"].default_value = 145.0
    grains.inputs["Detail"].default_value = 4.0
    grains.inputs["Roughness"].default_value = 0.78
    links.new(coordinates.outputs["Object"], grains.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.34
    bump.inputs["Distance"].default_value = 0.0035
    links.new(grains.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _cube(name, location, dimensions, mat, bevel=0.0):
    hx, hy, hz = (value * 0.5 for value in dimensions)
    vertices = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    if bevel:
        modifier = obj.modifiers.new("Soft natural edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def _mesh_object(name, vertices, faces, materials, material_indices=None, smooth=False):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    if material_indices:
        for polygon, index in zip(mesh.polygons, material_indices):
            polygon.material_index = index
    if smooth:
        for polygon in mesh.polygons:
            if len(polygon.vertices) == 4:
                polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _soil_surface(name, length, width, mat, rng):
    columns = max(8, math.ceil(length / 0.13))
    rows = max(4, math.ceil(width / 0.12))
    phase_a = rng.uniform(0, math.tau)
    phase_b = rng.uniform(0, math.tau)
    vertices = []
    for row in range(rows + 1):
        y = -width * 0.5 + width * row / rows
        for column in range(columns + 1):
            x = length * column / columns
            broad = math.sin(x * 1.7 + phase_a) * 0.0045
            cross = math.sin(y * 8.0 + x * 0.45 + phase_b) * 0.0025
            granular = rng.uniform(-0.0025, 0.0025)
            edge_fall = min(row, rows - row) / max(1.0, rows * 0.22)
            z = 0.061 + broad + cross + granular - max(0.0, 1.0 - edge_fall) * 0.004
            vertices.append((x, y, z))
    faces = []
    stride = columns + 1
    for row in range(rows):
        for column in range(columns):
            a = row * stride + column
            b = a + 1
            c = a + stride + 1
            d = a + stride
            if (row + column) % 2:
                faces.extend(((a, b, d), (b, c, d)))
            else:
                faces.extend(((a, b, c), (a, c, d)))
    return _mesh_object(name, vertices, faces, (mat,))


def _add_tapered_path(vertices, faces, path, radii, sides=8):
    if len(path) < 2 or len(path) != len(radii):
        raise ValueError("path and radii must have matching lengths of at least two")
    offset = len(vertices)
    for index, (point, radius) in enumerate(zip(path, radii)):
        if index == 0:
            tangent = Vector(path[1]) - Vector(point)
        elif index == len(path) - 1:
            tangent = Vector(point) - Vector(path[index - 1])
        else:
            tangent = Vector(path[index + 1]) - Vector(path[index - 1])
        tangent.normalize()
        reference = Vector((0, 0, 1)) if abs(tangent.z) < 0.92 else Vector((0, 1, 0))
        across = tangent.cross(reference).normalized()
        normal = tangent.cross(across).normalized()
        for side_index in range(sides):
            angle = math.tau * side_index / sides
            radial = across * math.cos(angle) + normal * math.sin(angle)
            vertices.append(tuple(Vector(point) + radial * radius))
    faces.append(tuple(offset + index for index in reversed(range(sides))))
    last = offset + (len(path) - 1) * sides
    faces.append(tuple(last + index for index in range(sides)))
    for ring in range(len(path) - 1):
        current = offset + ring * sides
        following = current + sides
        for side_index in range(sides):
            nxt = (side_index + 1) % sides
            faces.append((current + side_index, current + nxt,
                          following + nxt, following + side_index))


def create_planting_strip(name="Roadside Planting", length=6.0, width=0.85,
                          density=0.82, maintenance=0.70, health=0.88, seed=1234, lod="medium"):
    from asset_library.planting.scripts.shrub_growth import create_shrubs
    return create_shrubs(name, length, width, density, maintenance, health, seed,
                         clipped=False, lod=lod)


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _options():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--length", type=float, default=6.0)
    parser.add_argument("--width", type=float, default=0.85)
    parser.add_argument("--density", type=float, default=0.82)
    parser.add_argument("--maintenance", type=float, default=0.70)
    parser.add_argument("--health", type=float, default=0.88)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


def _standalone_main():
    options = _options()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    planting = create_planting_strip(
        "Roadside Planting Asset", options.length, options.width, options.density,
        options.maintenance, options.health, options.seed,
    )
    # The generated soil surface is around local z=60 mm. Place it 50 mm below
    # the existing 180 mm sidewalk top, as a recess in that sidewalk.
    planting.location.z = 0.07

    guardrail = build_guardrail.create_guardrail(
        "Preview white guardrail", options.length, "white", beam_side="right",
    )
    road_edge_y = -0.72
    curb_width = 0.15
    bed_near_y = -options.width * 0.5
    bed_far_y = options.width * 0.5
    sidewalk_far_y = 1.85
    guardrail.location.y = bed_near_y - 0.11
    guardrail.location.z = 0.18

    asphalt = _material("Preview asphalt", (0.045, 0.050, 0.052), 0.92, 0.22)
    concrete = _material("Preview sidewalk concrete", (0.43, 0.44, 0.41), 0.86, 0.13)
    curb = _material("Preview curb concrete", (0.52, 0.53, 0.49), 0.82, 0.10)
    road_min_y = -3.75
    _cube("Preview road", (options.length * 0.5,
                           (road_min_y + road_edge_y) * 0.5, -0.07),
          (options.length + 2.0, road_edge_y - road_min_y, 0.14), asphalt)
    curb_center_y = road_edge_y + curb_width * 0.5
    _cube("Preview curb", (options.length * 0.5, curb_center_y, 0.085),
          (options.length + 2.0, curb_width, 0.17), curb, 0.018)

    # Preserve the continuous sidewalk foundation. Only its 180 mm top slab is
    # divided around the planting opening, eliminating any void between road,
    # curb, soil and footway.
    sidewalk_near_y = road_edge_y + curb_width
    sidewalk_span = sidewalk_far_y - sidewalk_near_y
    _cube("Preview continuous sidewalk foundation",
          (options.length * 0.5, (sidewalk_near_y + sidewalk_far_y) * 0.5, -0.035),
          (options.length + 2.0, sidewalk_span, 0.07), concrete)
    front_width = bed_near_y - sidewalk_near_y
    _cube("Preview sidewalk road-side planting margin",
          (options.length * 0.5, (sidewalk_near_y + bed_near_y) * 0.5, 0.09),
          (options.length, front_width, 0.18), concrete, 0.018)
    back_width = sidewalk_far_y - bed_far_y
    _cube("Preview main sidewalk behind planting",
          (options.length * 0.5, (bed_far_y + sidewalk_far_y) * 0.5, 0.09),
          (options.length, back_width, 0.18), concrete, 0.025)
    for label, x in (("west", -0.5), ("east", options.length + 0.5)):
        _cube(f"Preview sidewalk {label} end around planting",
              (x, (sidewalk_near_y + sidewalk_far_y) * 0.5, 0.09),
              (1.0, sidewalk_span, 0.18), concrete, 0.025)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world = bpy.data.worlds.new("Planting preview world")
    scene.world.use_nodes = True
    background = next(node for node in scene.world.node_tree.nodes
                      if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.18, 0.22, 0.28, 1.0)
    background.inputs["Strength"].default_value = 0.32

    sun_data = bpy.data.lights.new("Soft afternoon sun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(7.0)
    sun = bpy.data.objects.new("Soft afternoon sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38), math.radians(-18), math.radians(-32))
    area_data = bpy.data.lights.new("Planting fill", "AREA")
    area_data.energy = 520
    area_data.shape = "RECTANGLE"
    area_data.size = 7.0
    area = bpy.data.objects.new("Planting fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (options.length * 0.40, -3.8, 5.2)
    _look_at(area, (options.length * 0.52, 0, 0.35))

    camera_data = bpy.data.cameras.new("Planting street-view camera")
    camera = bpy.data.objects.new("Planting street-view camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (options.length * 0.12, -5.7, 1.38)
    camera_data.lens = 52
    _look_at(camera, (options.length * 0.56, -0.02, 0.34))
    scene.camera = camera

    asset_root = Path(__file__).resolve().parent.parent
    blend_path = asset_root / "blend/planting_mixed_low_shrub.blend"
    render_path = asset_root / "renders/planting_mixed_low_shrub.png"
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    render_path.parent.mkdir(parents=True, exist_ok=True)
    if not options.skip_render:
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
    scene.camera = camera
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(
        f"PLANTING_QA plants={planting['plant_count']} leaves={planting['leaf_count']} "
        f"grass={planting['grass_blade_count']} seed={options.seed}"
    )


if __name__ == "__main__":
    _standalone_main()
