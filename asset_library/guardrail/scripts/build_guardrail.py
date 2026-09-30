"""Procedural Japanese three-rail pedestrian guard fence."""

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
from asset_library.shared.surfaces import finish



EMBEDDED = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"
POST_DIAMETER = 0.0605
BEAM_DIAMETER = 0.0427
FENCE_HEIGHT = 0.80
BEAM_HEIGHTS = (0.265, 0.535, 0.80)
DEFAULT_POST_SPACING = 3.0


def _material(name, color, metallic=0.0, roughness=0.5, variation=0.0):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return finish(mat, 'coating' if 'coating' in name else
                  'metal' if metallic > .5 else 'optics')


def _cube(name, location, dimensions, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Pressed metal edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def _cylinder_between(name, start, end, radius, mat, vertices=28):
    start = Vector(start)
    end = Vector(end)
    delta = end - start
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=delta.length,
        location=(start + end) * 0.5,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    obj.rotation_mode = "XYZ"
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        if len(face.vertices) == 4:
            face.use_smooth = True
    return obj


def _post_cap(name, x, mat):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=POST_DIAMETER * 0.62, depth=0.024,
        location=(x, 0, FENCE_HEIGHT + 0.055),
    )
    cap = bpy.context.object
    cap.name = name
    cap.data.materials.append(mat)
    bevel = cap.modifiers.new("Rounded pressed cap", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 4
    return cap


def _linked_copy(source, name, location):
    """Place another identical manufactured part using shared mesh data."""
    obj = source.copy()
    obj.data = source.data
    obj.name = name
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def _apply_modifiers(obj):
    """Bake prototype-only bevels before linked copies share their mesh."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def _join_meshes(name, objects):
    """Collapse manufactured parts sharing one material into one render mesh."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    joined = objects[0]
    bpy.context.view_layer.objects.active = joined
    if len(objects) > 1:
        bpy.ops.object.join()
    joined.name = name
    return joined


def create_guardrail(name="Guardrail", length=6.0, exterior_color="white",
                     post_spacing=DEFAULT_POST_SPACING, reflector_bands=True,
                     beam_side="right", include_posts=True,
                     include_end_post=True, include_beams=True):
    """Create a local +X guard fence rooted at its first post on grade."""
    if length <= 0:
        raise ValueError("length must be positive")
    if post_spacing <= 0:
        raise ValueError("post_spacing must be positive")
    if exterior_color not in {"white", "brown"}:
        raise ValueError("exterior_color must be 'white' or 'brown'")
    if beam_side not in {"left", "right"}:
        raise ValueError("beam_side must be 'left' or 'right'")
    side = 1.0 if beam_side == "left" else -1.0

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root["asset_type"] = "Japanese three-rail pedestrian guard fence"
    root["exterior_color"] = exterior_color
    root["length_m"] = length
    root["nominal_height_m"] = FENCE_HEIGHT
    root["post_diameter_m"] = POST_DIAMETER
    root["beam_diameter_m"] = BEAM_DIAMETER
    root["beam_side"] = beam_side

    if exterior_color == "white":
        coating = _material("Guard fence off-white coating", (0.76, 0.77, 0.73),
                            metallic=0.12, roughness=0.48, variation=0.12)
    else:
        coating = _material("Guard fence dark brown coating", (0.070, 0.045, 0.030),
                            metallic=0.10, roughness=0.53, variation=0.10)
    hardware = _material("Guard fence stainless fasteners", (0.32, 0.35, 0.35),
                         metallic=0.78, roughness=0.34)
    reflector = _material("Guard fence amber reflector", (0.95, 0.48, 0.015),
                          metallic=0.0, roughness=0.31)

    segment_count = max(1, math.ceil(length / post_spacing))
    actual_spacing = length / segment_count
    post_positions = [actual_spacing * index for index in range(segment_count + 1)]
    created = []
    prototypes = {}

    for index, x in enumerate(post_positions if include_posts else ()):
        if not include_end_post and index == len(post_positions)-1:
            continue
        post_name = f"{name} post {index + 1:02d}"
        if "post" not in prototypes:
            prototypes["post"] = _cylinder_between(
                post_name, (x, 0, -0.12), (x, 0, FENCE_HEIGHT + 0.045),
                POST_DIAMETER * 0.5, coating, 32,
            )
            post = prototypes["post"]
        else:
            post = _linked_copy(prototypes["post"], post_name,
                                (x, 0, prototypes["post"].location.z))
        created.append(post)

        cap_name = f"{name} post cap {index + 1:02d}"
        if "cap" not in prototypes:
            prototypes["cap"] = _post_cap(cap_name, x, coating)
            _apply_modifiers(prototypes["cap"])
            cap = prototypes["cap"]
        else:
            cap = _linked_copy(prototypes["cap"], cap_name,
                               (x, 0, prototypes["cap"].location.z))
        created.append(cap)
        if reflector_bands:
            band_name = f"{name} amber band {index + 1:02d}"
            if "band" not in prototypes:
                prototypes["band"] = _cylinder_between(
                    band_name, (x, 0, 0.685), (x, 0, 0.720),
                    POST_DIAMETER * 0.515, reflector, 32,
                )
                band = prototypes["band"]
            else:
                band = _linked_copy(prototypes["band"], band_name,
                                    (x, 0, prototypes["band"].location.z))
            created.append(band)

        for rail_index, z in enumerate(BEAM_HEIGHTS, 1):
            bracket_name = f"{name} bracket {index + 1:02d}-{rail_index}"
            if "bracket" not in prototypes:
                prototypes["bracket"] = _cube(
                    bracket_name, (x, side * 0.043, z),
                    (0.085, 0.050, 0.064), coating, 0.008,
                )
                _apply_modifiers(prototypes["bracket"])
                bracket = prototypes["bracket"]
            else:
                bracket = _linked_copy(
                    prototypes["bracket"], bracket_name, (x, side * 0.043, z),
                )
            created.append(bracket)

            bolt_name = f"{name} bolt {index + 1:02d}-{rail_index}"
            if "bolt" not in prototypes:
                prototypes["bolt"] = _cylinder_between(
                    bolt_name, (x, side * 0.082, z), (x, -side * 0.012, z),
                    0.0062, hardware, 20,
                )
                bolt = prototypes["bolt"]
            else:
                bolt = _linked_copy(
                    prototypes["bolt"], bolt_name,
                    (x, prototypes["bolt"].location.y, z),
                )
            created.append(bolt)

    # Front-mounted beams are divided at posts like manufactured three-metre
    # sections. Their joints are hidden by the pressed brackets and bolts.
    beam_y = side * 0.075
    for span_index in range(segment_count if include_beams else 0):
        x0 = post_positions[span_index]
        x1 = post_positions[span_index + 1]
        for rail_index, z in enumerate(BEAM_HEIGHTS, 1):
            beam_name = f"{name} beam {span_index + 1:02d}-{rail_index}"
            if "beam" not in prototypes:
                prototypes["beam"] = _cylinder_between(
                    beam_name, (x0, beam_y, z), (x1, beam_y, z),
                    BEAM_DIAMETER * 0.5, coating, 32,
                )
                beam = prototypes["beam"]
            else:
                beam = _linked_copy(
                    prototypes["beam"], beam_name,
                    ((x0 + x1) * 0.5, beam_y, z),
                )
            created.append(beam)

    # The individual pieces remain explicit geometry, but Blender does not
    # need a separate dependency-graph object for every post, bolt and span.
    # Three material-grouped meshes preserve the exact baked surfaces while
    # making large networks cheap to instance and save.
    groups = {}
    for obj in created:
        mat = obj.data.materials[0]
        groups.setdefault(mat, []).append(obj)
    created = [
        _join_meshes(f"{name} {mat.name} parts", objects)
        for mat, objects in groups.items()
    ]

    for obj in created:
        obj.parent = root
    return root


def create_curved_guardrail(name="Curved Guardrail", radius=3.58,
                            start_degrees=4.0, sweep_degrees=82.0,
                            exterior_color="white", post_count=3):
    """Create a smooth three-rail arc with an explicit, sparse post count."""
    if radius <= 0 or sweep_degrees == 0:
        raise ValueError("radius and sweep_degrees must define a non-empty arc")
    if post_count < 2:
        raise ValueError("post_count must be at least 2")
    if exterior_color not in {"white", "brown"}:
        raise ValueError("exterior_color must be 'white' or 'brown'")
    coating = _material(
        "Guard fence off-white coating" if exterior_color == "white"
        else "Guard fence dark brown coating",
        (0.76, 0.77, 0.73) if exterior_color == "white"
        else (0.070, 0.045, 0.030),
        metallic=0.11, roughness=0.50, variation=0.10,
    )
    reflector = _material("Guard fence amber reflector", (0.95, 0.48, 0.015),
                          roughness=0.31)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root["asset_type"] = "Japanese curved three-rail pedestrian guard fence"
    root["curve_radius_m"] = radius
    root["post_count"] = post_count

    segment_count = max(16, math.ceil(abs(sweep_degrees) / 3.0))

    def arc_tube(part_name, arc_radius, z, tube_radius):
        curve = bpy.data.curves.new(part_name + " curve", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 1
        curve.bevel_depth = tube_radius
        curve.bevel_resolution = 3
        curve.resolution_u = 2
        spline = curve.splines.new("POLY")
        spline.points.add(segment_count)
        for index, point in enumerate(spline.points):
            angle = math.radians(start_degrees + sweep_degrees * index / segment_count)
            point.co = (math.cos(angle) * arc_radius,
                        math.sin(angle) * arc_radius, z, 1.0)
        obj = bpy.data.objects.new(part_name, curve)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(coating)
        obj.parent = root
        return obj

    # The rails sit 75mm toward the carriageway side of the post centreline.
    for rail_index, z in enumerate(BEAM_HEIGHTS, 1):
        arc_tube(f"{name} continuous curved rail {rail_index}",
                 radius + 0.075, z, BEAM_DIAMETER * 0.5)

    for index in range(post_count):
        fraction = index / (post_count - 1)
        angle = math.radians(start_degrees + sweep_degrees * fraction)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        post = _cylinder_between(
            f"{name} post {index + 1:02d}", (x, y, -0.12),
            (x, y, FENCE_HEIGHT + 0.045), POST_DIAMETER * 0.5, coating, 32,
        )
        post.parent = root
        cap = _cylinder_between(
            f"{name} post cap {index + 1:02d}",
            (x, y, FENCE_HEIGHT + 0.043), (x, y, FENCE_HEIGHT + 0.067),
            POST_DIAMETER * 0.62, coating, 32,
        )
        cap.parent = root
        band = _cylinder_between(
            f"{name} amber band {index + 1:02d}",
            (x, y, 0.685), (x, y, 0.720),
            POST_DIAMETER * 0.515, reflector, 32,
        )
        band.parent = root
    return root


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _parse_options():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--length", type=float, default=6.0)
    parser.add_argument("--exterior-color", choices=("white", "brown"), default="white")
    parser.add_argument("--post-spacing", type=float, default=3.0)
    parser.add_argument("--beam-side", choices=("left", "right"), default="right")
    parser.add_argument("--no-reflector-bands", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


def _standalone_main():
    options = _parse_options()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = create_guardrail(
        "Guardrail Asset", options.length, options.exterior_color,
        options.post_spacing, not options.no_reflector_bands, options.beam_side,
    )
    collection = bpy.data.collections.new("Guardrail Asset")
    bpy.context.scene.collection.children.link(collection)
    for obj in [root, *root.children_recursive]:
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)

    floor = _material("Preview asphalt", (0.055, 0.060, 0.061), roughness=0.92,
                      variation=0.18)
    _cube("Preview ground", (options.length * 0.5, 0, -0.08),
          (options.length + 3.0, 4.0, 0.16), floor)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("Guardrail preview world")
    scene.world.color = (0.055, 0.060, 0.070)

    sun_data = bpy.data.lights.new("Soft sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Soft sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(42), 0, math.radians(-28))
    area_data = bpy.data.lights.new("Large fill", "AREA")
    area_data.energy = 550
    area_data.shape = "RECTANGLE"
    area_data.size = 8.0
    area = bpy.data.objects.new("Large fill", area_data)
    bpy.context.scene.collection.objects.link(area)
    area.location = (options.length * 0.35, -4.0, 5.5)
    _look_at(area, (options.length * 0.5, 0, 0.4))

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (options.length * 0.34, -10.5, 1.62)
    camera_data.lens = 55
    _look_at(camera, (options.length * 0.50, -0.01, 0.43))
    scene.camera = camera

    asset_root = Path(__file__).resolve().parent.parent
    suffix = options.exterior_color
    blend_path = asset_root / "blend" / f"guardrail_{suffix}.blend"
    render_path = asset_root / "renders" / f"guardrail_{suffix}.png"
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    render_path.parent.mkdir(parents=True, exist_ok=True)
    if not options.skip_render:
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))


if __name__ == "__main__" and not EMBEDDED:
    _standalone_main()
