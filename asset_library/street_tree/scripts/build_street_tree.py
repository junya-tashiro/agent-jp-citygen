"""Code-native, batched street trees with three distinct deciduous silhouettes."""

import argparse
import math
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asset_library.street_tree.scripts.procedural_textures import ensure_tree_materials  # noqa: E402


SPECIES = {
    "keyaki": {
        "label": "Keyaki vase crown",
        "height": 8.5,
        "crown_width": 5.8,
        "crown_start_height": 2.25,
        "trunk_diameter": 0.38,
        "bark": (0.24, 0.22, 0.17),
        "leaf_colors": ((0.070, 0.235, 0.055), (0.115, 0.315, 0.075),
                        (0.175, 0.370, 0.095)),
    },
    "ginkgo": {
        "label": "Ginkgo conical crown",
        "height": 9.2,
        "crown_width": 3.2,
        "crown_start_height": 2.15,
        "trunk_diameter": 0.34,
        "bark": (0.25, 0.235, 0.19),
        "leaf_colors": ((0.145, 0.300, 0.055), (0.215, 0.390, 0.070),
                        (0.310, 0.455, 0.080)),
    },
    "cherry": {
        "label": "Cherry spreading crown",
        "height": 6.7,
        "crown_width": 5.2,
        "crown_start_height": 1.85,
        "trunk_diameter": 0.42,
        "bark": (0.205, 0.125, 0.095),
        "leaf_colors": ((0.080, 0.230, 0.060), (0.135, 0.325, 0.085),
                        (0.205, 0.390, 0.115)),
    },
}


def _material(name, color, roughness=0.72, noise_scale=5.0, variation=0.16,
              bump_strength=0.12, texture_scale=(1.0, 1.0, 1.0),
              fine_bump_scale=None, bump_distance=None):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = roughness
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.76
    coordinates = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (*texture_scale,)
    links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (
        color[0] * (1.0 - variation), color[1] * (1.0 - variation),
        color[2] * (1.0 - variation), 1.0,
    )
    ramp.color_ramp.elements[1].color = (
        min(1.0, color[0] * (1.0 + variation)),
        min(1.0, color[1] * (1.0 + variation)),
        min(1.0, color[2] * (1.0 + variation)), 1.0,
    )
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = (
        bump_distance if bump_distance is not None else
        (0.018 if noise_scale < 10 else 0.001)
    )
    bump_source = noise.outputs["Fac"]
    if fine_bump_scale is not None:
        fine = nodes.new("ShaderNodeTexNoise")
        fine.name = "Fine longitudinal bark fissures"
        fine.inputs["Scale"].default_value = fine_bump_scale
        fine.inputs["Detail"].default_value = 4.5
        fine.inputs["Roughness"].default_value = 0.82
        links.new(mapping.outputs["Vector"], fine.inputs["Vector"])
        bump_source = fine.outputs["Fac"]
    links.new(bump_source, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _mesh_object(name, vertices, faces, materials, material_indices=None, smooth=False,
                 face_uvs=None):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    if material_indices is not None:
        for polygon, index in zip(mesh.polygons, material_indices):
            polygon.material_index = index
    if smooth:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    if face_uvs is not None:
        uv_layer = mesh.uv_layers.new(name="Procedural UV")
        import numpy as np
        uv_layer.data.foreach_set("uv", np.asarray(
            [uv for face in face_uvs for uv in face], dtype=np.float32).reshape(-1))
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _sweep_path(vertices, faces, face_uvs, path, radii, sides, rng,
                irregularity=0.055, cap_start=True, bark_repeat_m=0.72,
                bark_positions=None, bark_radii=None, bark_offset=0.0):
    """Append a tapered branch with subtly non-circular, longitudinally varied rings."""
    if len(path) < 2:
        return
    cumulative = [0.0]
    for index in range(1, len(path)):
        cumulative.append(cumulative[-1] + (Vector(path[index]) - Vector(path[index - 1])).length)
    offset = len(vertices)
    previous_across = None
    ridge_phase = rng.uniform(0, math.tau)
    ellipse_phase = rng.uniform(0, math.tau)
    for index, point in enumerate(path):
        if index == 0:
            tangent = Vector(path[1]) - Vector(point)
        elif index == len(path) - 1:
            tangent = Vector(point) - Vector(path[index - 1])
        else:
            tangent = Vector(path[index + 1]) - Vector(path[index - 1])
        tangent.normalize()
        if previous_across is None:
            reference = Vector((0, 0, 1)) if abs(tangent.z) < 0.92 else Vector((0, 1, 0))
            across = tangent.cross(reference).normalized()
        else:
            across = previous_across - tangent * previous_across.dot(tangent)
            if across.length < 1e-5:
                across = tangent.cross(Vector((0, 1, 0))).normalized()
            else:
                across.normalize()
        normal = tangent.cross(across).normalized()
        previous_across = across
        for side_index in range(sides):
            angle = math.tau * side_index / sides
            radial = across * math.cos(angle) + normal * math.sin(angle)
            ridges = (math.sin(angle * 3.0 + ridge_phase + index * 0.14) * 0.58 +
                      math.sin(angle * 7.0 - ridge_phase * 0.7 + index * 0.07) * 0.22)
            oval = math.cos(angle * 2.0 + ellipse_phase + index * 0.05) * 0.22
            ring_radius = radii[index] * (1.0 + irregularity * (ridges + oval))
            vertices.append(tuple(Vector(point) + radial * ring_radius))
            if bark_positions is not None:
                bark_positions.append((math.cos(angle)*radii[index],
                                       math.sin(angle)*radii[index],
                                       cumulative[index]+bark_offset))
                bark_radii.append(radii[index])
    if cap_start:
        faces.append(tuple(offset + i for i in reversed(range(sides))))
        face_uvs.append(tuple((0.5, 0.5) for _ in range(sides)))
    final = offset + (len(path) - 1) * sides
    faces.append(tuple(final + i for i in range(sides)))
    face_uvs.append(tuple((0.5, 0.5) for _ in range(sides)))
    for ring in range(len(path) - 1):
        current = offset + ring * sides
        following = current + sides
        for side_index in range(sides):
            nxt = (side_index + 1) % sides
            faces.append((current + side_index, current + nxt,
                          following + nxt, following + side_index))
            # Match bark grain in metres even on tapering branches.
            circumference = math.tau * radii[ring]
            next_circumference = math.tau * radii[ring + 1]
            u0 = side_index / sides * circumference / bark_repeat_m
            u1 = (side_index + 1) / sides * circumference / bark_repeat_m
            next_u0 = side_index / sides * next_circumference / bark_repeat_m
            next_u1 = (side_index + 1) / sides * next_circumference / bark_repeat_m
            v0 = cumulative[ring] / bark_repeat_m
            v1 = cumulative[ring + 1] / bark_repeat_m
            face_uvs.append(((u0, v0), (u1, v0), (next_u1, v1), (next_u0, v1)))


def create_street_tree(name="Street Tree", species="keyaki", seed=1234, lod="medium",
                       height=None, crown_width=None, crown_start_height=None,
                       trunk_diameter=None, individual_variation=0.10):
    if species not in SPECIES:
        raise ValueError(f"Unsupported species {species!r}; choose {sorted(SPECIES)}")
    if lod not in {"low", "medium", "high"}:
        raise ValueError("lod must be low, medium or high")
    if not 0.0 <= individual_variation <= 0.30:
        raise ValueError("individual_variation must be between 0.0 and 0.30")
    config = dict(SPECIES[species])
    overrides = {
        "height": height,
        "crown_width": crown_width,
        "crown_start_height": crown_start_height,
        "trunk_diameter": trunk_diameter,
    }
    for key, value in overrides.items():
        if value is not None:
            config[key] = float(value)

    variation_rng = random.Random(seed ^ 0x5EED71EE)
    clamp = lambda value, low, high: max(low, min(high, value))
    age = clamp(variation_rng.gauss(0.0, 0.72), -1.55, 1.55)
    vigor = clamp(variation_rng.gauss(0.0, 0.68), -1.55, 1.55)
    openness = clamp(variation_rng.gauss(0.0, 0.72), -1.55, 1.55)
    pruning = clamp(variation_rng.gauss(0.0, 0.60), -1.45, 1.45)
    height_factor = clamp(
        1.0 + individual_variation * (age * 0.55 + vigor * 0.45), 0.82, 1.18
    )
    crown_factor = clamp(
        1.0 + individual_variation *
        (age * 0.18 + vigor * 0.62 + openness * 0.20), 0.80, 1.20
    )
    trunk_factor = clamp(
        1.0 + individual_variation * (age * 0.78 + vigor * 0.22), 0.82, 1.20
    )
    if overrides["height"] is None:
        config["height"] *= height_factor
    if overrides["crown_width"] is None:
        config["crown_width"] *= crown_factor
    if overrides["trunk_diameter"] is None:
        config["trunk_diameter"] *= trunk_factor
    if overrides["crown_start_height"] is None:
        config["crown_start_height"] *= height_factor * clamp(
            1.0 + individual_variation * pruning * 0.18, 0.94, 1.06
        )
    if config["height"] <= 2.0 or config["crown_width"] <= 0.5:
        raise ValueError("height and crown_width are too small for a street tree")
    if not 0.5 < config["crown_start_height"] < config["height"] * 0.8:
        raise ValueError("crown_start_height must lie within the lower 80% of the tree")

    rng = random.Random(seed)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root["species"] = species
    root["seed"] = seed
    root["height_m"] = config["height"]
    root["crown_width_m"] = config["crown_width"]
    root["lod"] = lod
    root["individual_variation"] = individual_variation
    root["height_factor"] = height_factor
    root["crown_factor"] = crown_factor
    root["trunk_factor"] = trunk_factor

    bark, leaf_materials = ensure_tree_materials(
        species, config["bark"], config["leaf_colors"]
    )

    from asset_library.street_tree.scripts.growth import grow
    branches, foliage = grow(species, config, rng, lod)

    branch_vertices, branch_faces, branch_uvs = [], [], []
    bark_positions, bark_radii = [], []
    sides = {"low": 7, "medium": 12, "high": 16}[lod]
    for index, (path, radii) in enumerate(branches):
        path_sides = min(sides, 5) if radii[0] < 0.005 else sides
        _sweep_path(
            branch_vertices, branch_faces, branch_uvs, path, radii, path_sides, rng,
            irregularity=0.105 if index == 0 else 0.060,
            cap_start=index == 0,
            bark_repeat_m={"keyaki": 1.8, "cherry": 1.6, "ginkgo": 1.0}[species],
            bark_positions=bark_positions, bark_radii=bark_radii,
            bark_offset=index * 1.618,
        )
    branch_obj = _mesh_object(name + " trunk and branches", branch_vertices,
                              branch_faces, (bark,), smooth=True,
                              face_uvs=branch_uvs)
    branch_obj.parent = root
    attr = branch_obj.data.attributes.new('bark_position_m', 'FLOAT_VECTOR', 'POINT')
    attr.data.foreach_set('vector', [v for point in bark_positions for v in point])
    attr = branch_obj.data.attributes.new('bark_radius_m', 'FLOAT', 'POINT')
    attr.data.foreach_set('value', bark_radii)

    leaf_obj = foliage.mesh(name + " foliage", leaf_materials, species, lod)
    leaf_obj.parent = root
    root["branch_path_count"] = len(branches)
    root["leaf_count"] = len(foliage.sites)
    root["triangle_estimate"] = (sum(max(1, len(face)-2) for face in branch_faces)
                                 + len(leaf_obj.data.polygons))
    return root


def _cube(name, location, dimensions, material):
    x, y, z = (value * 0.5 for value in dimensions)
    vertices = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = _mesh_object(name, vertices, faces, (material,))
    obj.location = location
    return obj


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _setup_preview():
    # Context assets are preview-only.  Importing create_street_tree from another
    # generator remains independent of guardrails, planting and scene dressing.
    from asset_library.guardrail.scripts import build_guardrail
    from asset_library.planting.scripts import build_planting

    positions = (-6.3, 0.0, 6.3)
    bed_length = 5.0
    bed_width = 1.20
    road_edge_y = -1.0
    curb_width = 0.15
    sidewalk_near_y = road_edge_y + curb_width
    bed_near_y = -bed_width * 0.5
    bed_far_y = bed_width * 0.5
    sidewalk_far_y = 3.20
    scene_min_x, scene_max_x = -11.0, 11.0

    asphalt = _material("Street tree preview asphalt", (0.045, 0.050, 0.052),
                         0.94, noise_scale=38.0, variation=0.12,
                         bump_strength=0.16, bump_distance=0.0012)
    concrete = _material("Street tree preview sidewalk concrete", (0.43, 0.44, 0.41),
                          0.88, noise_scale=7.0, variation=0.10,
                          bump_strength=0.10, bump_distance=0.002)
    curb = _material("Street tree preview curb concrete", (0.52, 0.53, 0.49),
                      0.84, noise_scale=12.0, variation=0.09,
                      bump_strength=0.10, bump_distance=0.0015)
    scene_length = scene_max_x - scene_min_x
    _cube("Preview road", ((scene_min_x + scene_max_x) * 0.5, -3.0, -0.07),
          (scene_length + 2.0, 4.0, 0.14), asphalt)
    _cube("Preview curb", ((scene_min_x + scene_max_x) * 0.5,
                            road_edge_y + curb_width * 0.5, 0.085),
          (scene_length + 2.0, curb_width, 0.17), curb)
    _cube("Preview continuous sidewalk foundation",
          ((scene_min_x + scene_max_x) * 0.5,
           (sidewalk_near_y + sidewalk_far_y) * 0.5, -0.035),
          (scene_length, sidewalk_far_y - sidewalk_near_y, 0.07), concrete)
    _cube("Preview sidewalk road-side planting margin",
          ((scene_min_x + scene_max_x) * 0.5,
           (sidewalk_near_y + bed_near_y) * 0.5, 0.09),
          (scene_length, bed_near_y - sidewalk_near_y, 0.18), concrete)
    _cube("Preview main sidewalk behind planting",
          ((scene_min_x + scene_max_x) * 0.5,
           (bed_far_y + sidewalk_far_y) * 0.5, 0.09),
          (scene_length, sidewalk_far_y - bed_far_y, 0.18), concrete)

    bed_spans = [(x - bed_length * 0.5, x + bed_length * 0.5) for x in positions]
    paved_spans = []
    cursor = scene_min_x
    for start, end in bed_spans:
        if start > cursor:
            paved_spans.append((cursor, start))
        cursor = end
    if cursor < scene_max_x:
        paved_spans.append((cursor, scene_max_x))
    for index, (start, end) in enumerate(paved_spans, 1):
        _cube(
            f"Preview sidewalk infill {index:02d}",
            ((start + end) * 0.5, (bed_near_y + bed_far_y) * 0.5, 0.09),
            (end - start, bed_far_y - bed_near_y, 0.18), concrete,
        )

    roots = []
    for index, (species, x) in enumerate(zip(("keyaki", "ginkgo", "cherry"), positions)):
        planting = build_planting.create_planting_strip(
            f"{SPECIES[species]['label']} planting",
            length=bed_length, width=bed_width, density=0.88,
            maintenance=0.72, health=0.90,
            seed=(2851, 4769, 8191)[index],
        )
        planting.location = (x - bed_length * 0.5, 0.0, 0.07)
        guardrail = build_guardrail.create_guardrail(
            f"{SPECIES[species]['label']} white guardrail",
            length=bed_length, exterior_color="white", post_spacing=2.5,
            reflector_bands=True, beam_side="right",
        )
        guardrail.location = (x - bed_length * 0.5, bed_near_y - 0.11, 0.18)
        root = create_street_tree(
            SPECIES[species]["label"], species=species,
            seed=(1847, 3921, 7613)[index], lod="medium",
        )
        root.location = (x, 0.0, 0.13)
        roots.append(root)

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("Street tree preview world")
        bpy.context.scene.world = world
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.62, 0.70, 0.82, 1)
    background.inputs["Strength"].default_value = 0.35
    sun_data = bpy.data.lights.new("Street tree sun", "SUN")
    sun_data.energy = 2.7
    sun_data.angle = math.radians(18)
    sun = bpy.data.objects.new("Street tree sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-24), math.radians(-32))
    area_data = bpy.data.lights.new("Street tree fill", "AREA")
    area_data.energy = 900
    area_data.shape = "DISK"
    area_data.size = 8.0
    area = bpy.data.objects.new("Street tree fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (-7, -6, 11)
    _look_at(area, (0, 0, 4))
    camera_data = bpy.data.cameras.new("Street tree preview camera")
    camera = bpy.data.objects.new("Street tree preview camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, -27.5, 7.9)
    camera_data.lens = 47
    _look_at(camera, (0, 0.15, 4.25))
    bpy.context.scene.camera = camera
    details = {}
    detail_specs = {
        "keyaki_bark": ((-9.0, -7.2, 4.7), (-6.3, 0.0, 3.75), 68),
        "ginkgo_bark": ((-1.8, -6.2, 4.2), (0.0, 0.0, 3.45), 72),
        "cherry_bark": ((4.5, -6.2, 3.7), (6.3, 0.0, 3.05), 72),
        "leaf_detail": ((-7.5, -3.2, 7.2), (-6.3, 0.0, 6.75), 82),
    }
    for label, (location, target, lens) in detail_specs.items():
        detail_data = bpy.data.cameras.new(f"Street tree {label} camera")
        detail = bpy.data.objects.new(f"Street tree {label} camera", detail_data)
        bpy.context.collection.objects.link(detail)
        detail.location = location
        detail_data.lens = lens
        _look_at(detail, target)
        details[label] = detail
    return roots, camera, details


def _setup_variation_row(species="keyaki", count=10):
    """Build a long streetscape used to judge same-species individual variation."""
    from asset_library.guardrail.scripts import build_guardrail
    from asset_library.planting.scripts import build_planting

    spacing = 4.2
    positions = [(index - (count - 1) * 0.5) * spacing for index in range(count)]
    strip_start = positions[0] - 1.8
    strip_end = positions[-1] + 1.8
    strip_length = strip_end - strip_start
    bed_width = 1.20
    road_edge_y = -1.0
    curb_width = 0.15
    sidewalk_near_y = road_edge_y + curb_width
    bed_near_y = -bed_width * 0.5
    bed_far_y = bed_width * 0.5
    sidewalk_far_y = 3.20
    scene_min_x, scene_max_x = strip_start - 1.2, strip_end + 1.2
    scene_length = scene_max_x - scene_min_x

    asphalt = _material("Variation row asphalt", (0.045, 0.050, 0.052),
                         0.94, noise_scale=38.0, variation=0.12,
                         bump_strength=0.16, bump_distance=0.0012)
    concrete = _material("Variation row sidewalk concrete", (0.43, 0.44, 0.41),
                          0.88, noise_scale=7.0, variation=0.10,
                          bump_strength=0.10, bump_distance=0.002)
    curb = _material("Variation row curb concrete", (0.52, 0.53, 0.49),
                      0.84, noise_scale=12.0, variation=0.09,
                      bump_strength=0.10, bump_distance=0.0015)
    _cube("Variation row road", (0.0, -3.0, -0.07),
          (scene_length + 2.0, 4.0, 0.14), asphalt)
    _cube("Variation row curb", (0.0, road_edge_y + curb_width * 0.5, 0.085),
          (scene_length + 2.0, curb_width, 0.17), curb)
    _cube("Variation row sidewalk foundation",
          (0.0, (sidewalk_near_y + sidewalk_far_y) * 0.5, -0.035),
          (scene_length, sidewalk_far_y - sidewalk_near_y, 0.07), concrete)
    _cube("Variation row front sidewalk margin",
          (0.0, (sidewalk_near_y + bed_near_y) * 0.5, 0.09),
          (scene_length, bed_near_y - sidewalk_near_y, 0.18), concrete)
    _cube("Variation row main sidewalk",
          (0.0, (bed_far_y + sidewalk_far_y) * 0.5, 0.09),
          (scene_length, sidewalk_far_y - bed_far_y, 0.18), concrete)
    for label, start, end in (
        ("west", scene_min_x, strip_start),
        ("east", strip_end, scene_max_x),
    ):
        _cube(f"Variation row {label} sidewalk infill",
              ((start + end) * 0.5, 0.0, 0.09),
              (end - start, bed_width, 0.18), concrete)

    planting = build_planting.create_planting_strip(
        f"Ten {species} continuous planting",
        length=strip_length, width=bed_width, density=0.88,
        maintenance=0.72, health=0.90, seed=62831,
    )
    planting.location = (strip_start, 0.0, 0.07)
    guardrail = build_guardrail.create_guardrail(
        f"Ten {species} white guardrail",
        length=strip_length, exterior_color="white", post_spacing=2.8,
        reflector_bands=True, beam_side="right",
    )
    guardrail.location = (strip_start, bed_near_y - 0.11, 0.18)

    roots = []
    for index, x in enumerate(positions):
        root = create_street_tree(
            f"{SPECIES[species]['label']} individual {index + 1:02d}",
            species=species, seed=104729 + index * 7919, lod="medium",
            individual_variation=0.14,
        )
        root.location = (x, 0.0, 0.13)
        roots.append(root)

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("Street tree variation row world")
        bpy.context.scene.world = world
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.62, 0.70, 0.82, 1)
    background.inputs["Strength"].default_value = 0.35
    sun_data = bpy.data.lights.new("Variation row sun", "SUN")
    sun_data.energy = 2.7
    sun_data.angle = math.radians(18)
    sun = bpy.data.objects.new("Variation row sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-24), math.radians(-32))
    area_data = bpy.data.lights.new("Variation row fill", "AREA")
    area_data.energy = 1100
    area_data.shape = "RECTANGLE"
    area_data.size = 18.0
    area = bpy.data.objects.new("Variation row fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (-12, -18, 16)
    _look_at(area, (0, 0, 4.0))
    camera_data = bpy.data.cameras.new("Variation row camera")
    camera = bpy.data.objects.new("Variation row camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, -62.0, 10.0)
    camera_data.lens = 50
    _look_at(camera, (0, 0.1, 4.35))
    bpy.context.scene.camera = camera
    return roots, camera, {}


def _options():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", choices=("none", "preview", "final"), default="preview")
    parser.add_argument("--scene", choices=("three-species", "variation-row"),
                        default="three-species")
    parser.add_argument("--species", choices=tuple(SPECIES), default="keyaki")
    parser.add_argument("--count", type=int, default=10)
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


def main():
    opts = _options()
    if not 2 <= opts.count <= 20:
        raise ValueError("count must be between 2 and 20")
    started = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if opts.scene == "variation-row":
        roots, overview_camera, detail_cameras = _setup_variation_row(
            opts.species, opts.count
        )
        output_stem = f"street_tree_{opts.species}_variation_row"
    else:
        roots, overview_camera, detail_cameras = _setup_preview()
        output_stem = "street_tree_three_species"
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_percentage = 100
    if opts.scene == "variation-row":
        scene.render.resolution_x = 1800 if opts.render != "final" else 2400
        scene.render.resolution_y = 720 if opts.render != "final" else 960
    else:
        scene.render.resolution_x = 1200 if opts.render != "final" else 1800
        scene.render.resolution_y = 820 if opts.render != "final" else 1200
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.35
    output_root = ROOT / "asset_library/street_tree"
    (output_root / "blend").mkdir(parents=True, exist_ok=True)
    (output_root / "renders").mkdir(parents=True, exist_ok=True)
    if opts.render != "none":
        scene.camera = overview_camera
        scene.render.filepath = str(output_root / f"renders/{output_stem}.png")
        bpy.ops.render.render(write_still=True)
        scene.render.resolution_x = 1000 if opts.render != "final" else 1500
        scene.render.resolution_y = 820 if opts.render != "final" else 1200
        for label, detail_camera in detail_cameras.items():
            scene.camera = detail_camera
            scene.render.filepath = str(output_root / f"renders/street_tree_{label}.png")
            bpy.ops.render.render(write_still=True)
        scene.camera = overview_camera
    bpy.ops.wm.save_as_mainfile(
        filepath=str(output_root / f"blend/{output_stem}.blend")
    )
    print(f"STREET_TREE_SECONDS={time.perf_counter() - started:.4f}")
    for root in roots:
        print(f"STREET_TREE_QA={root['species']} branches={root['branch_path_count']} "
              f"leaves={root['leaf_count']} triangles={root['triangle_estimate']}")


if __name__ == "__main__":
    main()
