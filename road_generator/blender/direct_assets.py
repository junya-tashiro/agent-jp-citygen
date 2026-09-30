"""Fast direct-Python asset composition without intermediate .blend files."""

import math
import os
import random
import zlib

import bpy
from mathutils import Vector

os.environ["BLENDER_ASSET_EMBEDDED"] = "1"

from asset_library.guardrail.scripts import build_guardrail as guardrail  # noqa: E402
from asset_library.dual_warning_lamp.scripts.build_dual_warning_lamp import (  # noqa: E402
    create_dual_warning_lamp,
)
from asset_library.planting.scripts import build_planting as planting  # noqa: E402
from asset_library.planting.scripts import build_clipped_hedge as clipped_hedge  # noqa: E402
from asset_library.road_marking.scripts import build_bicycle_lane_marking as bicycle_marking  # noqa: E402
from asset_library.road_marking.scripts.build_lane_use_arrow import (  # noqa: E402
    create_lane_use_arrow,
)
from asset_library.reflector_pole.scripts.build_reflector_pole import (  # noqa: E402
    create_reflector_pole,
)
from asset_library.pedestrian_signal.scripts import build_pedestrian_signal as ped  # noqa: E402
from asset_library.road_sign.scripts.build_road_sign_samples import (  # noqa: E402
    create_keep_left_sign, create_road_sign, create_road_sign_stack,
)
from asset_library.fire_hydrant_sign.scripts.build_fire_hydrant_sign import (  # noqa: E402
    create_fire_hydrant_sign,
)
from asset_library.fire_hydrant_cover.scripts.build_fire_hydrant_cover import (  # noqa: E402
    create_fire_hydrant_cover,
)
from asset_library.street_tree.scripts import build_street_tree as street_tree  # noqa: E402
from asset_library.street_light.scripts import build_street_lights as street_light  # noqa: E402
from asset_library.traffic_signal.scripts import build_traffic_signal as vehicle  # noqa: E402


_CACHE = {}
_PEDESTRIAN_PARTS = {}
_VEHICLE_STRUCTURE = {}
_VEHICLE_HEAD_PARTS = {}
_VEHICLE_SUPPORT_PARTS = {}
_NAME_PLATE_STRUCTURE = None


def _collection(name):
    return bpy.data.collections.new(name)


def _move_to_collection(objects, collection):
    for obj in objects:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)


def _capture(builder):
    """Build operator-based prototypes in a small dependency graph.

    Resolve world transforms before leaving the temporary scene. Captured
    assets have always been flattened by their consumers; do it while parent
    matrices are still evaluated, rather than after removing their root.
    """
    window = bpy.context.window
    if window is None:
        before = set(bpy.context.scene.objects)
        builder()
        bpy.context.view_layer.update()
        return set(bpy.context.scene.objects) - before
    original = window.scene
    destination = bpy.context.collection
    scratch = bpy.data.scenes.new('Asset prototype workspace')
    try:
        window.scene = scratch
        builder()
        bpy.context.view_layer.update()
        objects = set(scratch.objects)
        transforms = {obj:obj.matrix_world.copy() for obj in objects}
        for obj, matrix in transforms.items():
            obj.parent = None
            obj.matrix_world = matrix
            destination.objects.link(obj)
        return objects
    finally:
        window.scene = original
        bpy.data.scenes.remove(scratch)


def _instance(collection, name, location=(0, 0, 0), rotation_degrees=0, scale=(1, 1, 1), owner=None):
    obj = bpy.data.objects.new(name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = collection
    obj.location = location
    obj.rotation_euler[2] = math.radians(rotation_degrees)
    obj.scale = scale
    (owner or bpy.context.collection).objects.link(obj)
    return obj


def _arc_chords(center, radius, start_degrees, sweep_degrees, target_length=0.9):
    arc_length = abs(math.radians(sweep_degrees) * radius)
    count = max(2, math.ceil(arc_length / target_length))
    points = []
    for index in range(count + 1):
        angle = math.radians(start_degrees + sweep_degrees * index / count)
        points.append((center[0] + math.cos(angle) * radius,
                       center[1] + math.sin(angle) * radius))
    return tuple(zip(points, points[1:]))


def sidewalk_brick_surface(name, center, length, width, rotation_radians,
                           elevation, materials, seed=None):
    """Create one batched 2:1 basket-weave paving surface with random colours."""
    if length <= 0.05 or width <= 0.05 or not materials:
        return None
    unit = 0.20
    cell = unit * 2.0
    # A narrow 3 mm joint keeps the pavement visually continuous while still
    # leaving enough separation for the rounded edge highlight to read.
    joint = 0.003
    columns = max(1, math.ceil(length / cell))
    rows = max(1, math.ceil(width / cell))
    origin_x, origin_y = -length * 0.5, -width * 0.5
    vertices, faces, material_indices = [], [], []
    stable_seed = (seed if seed is not None
                   else zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF)
    rng = random.Random(stable_seed)

    def brick(x0, x1, y0, y1):
        x0, x1 = max(origin_x, x0), min(-origin_x, x1)
        y0, y1 = max(origin_y, y0), min(-origin_y, y1)
        inset = joint * 0.5
        if x1 - x0 <= joint or y1 - y0 <= joint:
            return
        x0, x1, y0, y1 = x0 + inset, x1 - inset, y0 + inset, y1 - inset
        first = len(vertices)
        vertices.extend(((x0, y0, 0.0), (x1, y0, 0.0),
                         (x1, y1, 0.0), (x0, y1, 0.0)))
        faces.append((first, first + 1, first + 2, first + 3))
        material_indices.append(rng.randrange(len(materials)))

    for column in range(columns):
        x0 = origin_x + column * cell
        for row in range(rows):
            y0 = origin_y + row * cell
            # Alternating 400x200 and 200x400 pairs reproduce the reference's
            # repeated horizontal/vertical woven rhythm. Clipping is confined
            # to the property/end boundary; a 200x200 square is acceptable
            # there when only half a pair fits.
            if (column + row) % 2 == 0:
                brick(x0, x0 + cell, y0, y0 + unit)
                brick(x0, x0 + cell, y0 + unit, y0 + cell)
            else:
                brick(x0, x0 + unit, y0, y0 + cell)
                brick(x0 + unit, x0 + cell, y0, y0 + cell)

    mesh = bpy.data.meshes.new(f"{name} mesh")
    mesh.from_pydata(vertices, [], faces)
    for material in materials:
        mesh.materials.append(material)
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (*center[:2], elevation)
    obj.rotation_euler[2] = rotation_radians
    obj["asset_kind"] = "sidewalk_brick_surface"
    obj["brick_nominal_size_m"] = (unit, cell)
    obj["brick_count"] = len(faces)
    obj["colour_count"] = len(materials)
    obj["deterministic_random_seed"] = stable_seed
    solidify = obj.modifiers.new("Brick thickness", "SOLIDIFY")
    solidify.thickness = 0.012
    solidify.offset = -1.0
    bevel = obj.modifiers.new("Soft rounded brick edges", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    bevel.affect = "EDGES"
    return obj


def guardrail_instance(name, start, end, exterior_color="white", beam_side="right",
                       elevation=0.0, curve_center=None, curve_radius=0.0,
                       curve_start_degrees=0.0, curve_sweep_degrees=0.0):
    if curve_center is not None and curve_radius > 0.0 and curve_sweep_degrees:
        # Guardrails are rigid between posts even on the gentle curves this
        # generator supports. Place shared straight modules chord-by-chord;
        # this is visually faithful and avoids baking a unique heavy mesh for
        # every corner radius and angle.
        instances = []
        for index, (arc_start, arc_end) in enumerate(_arc_chords(
                curve_center, curve_radius, curve_start_degrees,
                curve_sweep_degrees, target_length=1.8)):
            segment_instances = guardrail_instance(
                f"{name} arc {index + 1:02d}", arc_start, arc_end,
                exterior_color, beam_side, elevation,
            )
            for instance in segment_instances:
                instance["curve_radius_m"] = curve_radius
                instance["curve_center"] = curve_center
            instances.extend(segment_instances)
        return tuple(instances)
    start = Vector((*start, 0.0))
    end = Vector((*end, 0.0))
    delta = end - start
    length = round(delta.length, 6)
    canonical_length = 1.0 if length < 2.0 else 5.0
    module_count = max(1, math.ceil(length / 5.5))
    module_length = length / module_count
    key = ("guardrail module", exterior_color, beam_side,
           round(canonical_length, 3))
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(
            f"Shared guardrail module {exterior_color} {beam_side}"
        )
        objects = _capture(lambda: guardrail.create_guardrail(
            "Canonical Guardrail", canonical_length, exterior_color=exterior_color,
            beam_side=beam_side,
        ))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    direction = delta.normalized()
    angle = math.degrees(math.atan2(delta.y, delta.x))
    instances = []
    for index in range(module_count):
        location = start + direction * (module_length * index)
        instance = _instance(
            collection, f"{name} module {index + 1}",
            (location.x, location.y, elevation), angle,
            (module_length / canonical_length, 1.0, 1.0),
        )
        instance["beam_side"] = beam_side
        instance["guardrail_edge_id"] = name
        instances.append(instance)
    return tuple(instances)


def guardrail_path_instance(name, path, start, end, lateral, exterior_color,
                            beam_side, elevation, frame, end_posts=(True,True)):
    """Separate shared posts and beams preserve spacing across split edges."""
    collections = {}
    for part in ('post','beams'):
        key = ('continuous guard fence',part,exterior_color,beam_side)
        collection = _CACHE.get(key)
        if collection is None:
            collection = _collection(f'Shared fence {part} {exterior_color} {beam_side}')
            objects = _capture(lambda:guardrail.create_guardrail(
                'Canonical fence '+part,3.0,exterior_color=exterior_color,
                beam_side=beam_side,include_posts=part=='post',
                include_end_post=False,include_beams=part=='beams'))
            _move_to_collection(objects,collection)
            _CACHE[key]=collection
        collections[part]=collection
    positions=[s for s,index in frame.positions(start,end,3.0)]
    if end_posts[0]:positions.append(start)
    if end_posts[1]:positions.append(end)
    for serial,s in enumerate(sorted(set(positions))):
        point=path.offset_point(s,lateral)
        # One physical post at shared endpoints, including adjoining corners.
        key=('fence post placed',round(point[0],3),round(point[1],3),round(elevation,3),exterior_color)
        if key in _CACHE:continue
        tangent=path.tangent_at_distance(s)
        heading=math.degrees(math.atan2(tangent[1],tangent[0]))
        obj=_instance(collections['post'],name+f' post {serial}',(*point,elevation),heading)
        _CACHE[key]=obj
    cuts=sorted({start,end,*positions})
    for serial,(a,b) in enumerate(zip(cuts,cuts[1:])):
        if b-a<.005:continue
        p,q=path.offset_point(a,lateral),path.offset_point(b,lateral)
        heading=math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))
        _instance(collections['beams'],name+f' beams {serial}',(*p,elevation),heading,
                  (math.dist(p,q)/3.0,1,1))


def reflector_pole_instance(name, location, rotation_degrees=0.0):
    key = ("reflector pole",)
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection("Shared red reflector pole")
        objects = _capture(lambda: create_reflector_pole("Canonical Reflector Pole"))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    instance = _instance(collection, name, location, rotation_degrees)
    instance["asset_type"] = "reflector_pole"
    return instance


def lane_use_arrow_instance(name, location, rotation_degrees, kind, material):
    key = ("lane-use arrow", kind, material.name)
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(f"Shared lane-use arrow {kind}")
        objects = _capture(lambda: create_lane_use_arrow(
            "Canonical lane-use arrow", kind, material))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    instance = _instance(collection, name, location, rotation_degrees)
    instance["asset_type"] = "lane_use_arrow"
    instance["arrow_kind"] = kind
    return instance


def prewarm_roadside_components(guardrail_plans=(), planting_plans=(),
                                reflector_pole=False):
    """Build costly shared roadside meshes before the dependency graph grows."""
    for item in guardrail_plans:
        instances = guardrail_instance(
            item.id, item.start, item.end, item.exterior_color, item.beam_side,
            item.elevation, item.curve_center, item.curve_radius,
            item.curve_start_degrees, item.curve_sweep_degrees,
        )
        for instance in instances:
            bpy.data.objects.remove(instance, do_unlink=True)
    for item in planting_plans:
        instances = planting_instance(
            item.id, item.start, item.end, item.width, item.density,
            item.maintenance, item.health, item.seed, item.elevation,
            item.curve_center, item.curve_radius,
            item.curve_start_degrees, item.curve_sweep_degrees,
            style=item.style,
        )
        for instance in instances:
            bpy.data.objects.remove(instance, do_unlink=True)
    if reflector_pole:
        instance = reflector_pole_instance("Reflector pole prewarm", (0, 0, -1000))
        bpy.data.objects.remove(instance, do_unlink=True)


def _curved_soil_instance(name, center, radius, width, start_degrees,
                          sweep_degrees, elevation):
    """Instance one continuous recessed annular soil bed beneath corner shrubs."""
    sweep = abs(sweep_degrees)
    key = ("curved planting soil", round(radius, 3), round(width, 3),
           round(sweep, 2))
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(
            f"Shared curved planting soil {radius:.3f}m {sweep:.1f} degrees"
        )
        segments = max(24, math.ceil(sweep / 2.5))
        inner = radius - width * 0.5
        outer = radius + width * 0.5
        top_z, bottom_z = 0.060, -0.085
        vertices = []
        for z in (top_z, bottom_z):
            for arc_radius in (inner, outer):
                for index in range(segments + 1):
                    angle = math.radians(-sweep * 0.5 + sweep * index / segments)
                    # Millimetre-scale undulation keeps the soil from reading as plastic.
                    variation = (math.sin(index * 1.73) * 0.0018
                                 if z == top_z else 0.0)
                    vertices.append((math.cos(angle) * arc_radius,
                                     math.sin(angle) * arc_radius,
                                     z + variation))
        ring = segments + 1
        top_inner, top_outer, bottom_inner, bottom_outer = 0, ring, ring * 2, ring * 3
        faces = []
        for index in range(segments):
            nxt = index + 1
            faces.extend((
                (top_inner + index, top_inner + nxt, top_outer + nxt, top_outer + index),
                (top_outer + index, top_outer + nxt, bottom_outer + nxt, bottom_outer + index),
                (bottom_inner + nxt, bottom_inner + index, bottom_outer + index, bottom_outer + nxt),
            ))
        faces.extend((
            (top_inner, top_outer, bottom_outer, bottom_inner),
            (top_inner + segments, bottom_inner + segments,
             bottom_outer + segments, top_outer + segments),
        ))
        mesh = bpy.data.meshes.new("Canonical curved planting soil mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(planting._soil_material())
        soil = bpy.data.objects.new("Canonical continuous curved soil bed", mesh)
        collection.objects.link(soil)
        _CACHE[key] = collection
    midpoint = start_degrees + sweep_degrees * 0.5
    instance = _instance(collection, name, (*center, elevation), midpoint,
                         (1.0, -1.0 if sweep_degrees < 0 else 1.0, 1.0))
    instance["curve_radius_m"] = radius
    instance["planting_width_m"] = width
    instance["continuous_corner_soil"] = True
    return instance


def planting_instance(name, start, end, width=0.85, density=0.82,
                      maintenance=0.70, health=0.88, seed=1234,
                      elevation=0.07, curve_center=None, curve_radius=0.0,
                      curve_start_degrees=0.0, curve_sweep_degrees=0.0,
                      include_soil=True, style="legacy"):
    if curve_center is not None and curve_radius > 0.0 and curve_sweep_degrees:
        instances = [_curved_soil_instance(
            name + " continuous soil", curve_center, curve_radius, width,
            curve_start_degrees, curve_sweep_degrees, elevation,
        )]
        for index, (arc_start, arc_end) in enumerate(_arc_chords(
                curve_center, curve_radius, curve_start_degrees,
                curve_sweep_degrees, target_length=1.1)):
            segment_seed = zlib.crc32(
                f"{name}:arc:{index}".encode("utf-8"), seed
            ) & 0x7FFFFFFF
            instances.extend(planting_instance(
                f"{name} arc {index + 1:02d}", arc_start, arc_end, width,
                density, maintenance, health, segment_seed, elevation,
                include_soil=False, style=style,
            ))
        for instance in instances:
            instance["curve_radius_m"] = curve_radius
            instance["curve_center"] = curve_center
        return tuple(instances)
    start = Vector((*start, 0.0))
    end = Vector((*end, 0.0))
    delta = end - start
    length = delta.length
    direction = delta.normalized()
    angle = math.degrees(math.atan2(delta.y, delta.x))
    # Keep the detailed leaf geometry, but use a finite canonical module pool.
    # Previously module length and three continuous appearance parameters were
    # all cache keys, so nearly every edge generated eight unique heavy meshes.
    # Two perceptually distinct tiers per parameter preserve the visible range;
    # exact edge values remain metadata while order, reversal and stretch add
    # local variation without duplicating geometry.
    module_count = max(1, math.ceil(length / 5.5))
    module_length = round(length / module_count, 6)
    # Straight modules are already kept near five metres by module_count.
    # Reusing one 5m source (and one 1m source for corner chords) avoids
    # embedding a new high-detail shrub mesh for every slightly different edge
    # length. The resulting longitudinal stretch stays small on ordinary roads.
    canonical_length = 1.0 if module_length < 2.0 else 5.0
    if style == "clipped_hedge":
        # Keep the authored high clipped envelope. Two stock arrangements
        # share their leafy clusters instead of duplicating every blade for
        # each continuous appearance parameter.
        density_profile = 0.90
        maintenance_profile = 0.82
        health_profile = 0.92
    else:
        density_profile = min((0.74, 0.90), key=lambda value: abs(value - density))
        maintenance_profile = min((0.62, 0.82), key=lambda value: abs(value - maintenance))
        health_profile = min((0.76, 0.92), key=lambda value: abs(value - health))
    # Two stock arrangements reuse the same leafy shrub-cluster library.
    variant_count = 2
    variants = list(range(variant_count))
    rng = random.Random(seed)
    rng.shuffle(variants)
    instances = []
    for index in range(module_count):
        variant = variants[index % variant_count]
        variant_seed = zlib.crc32(
            (f"planting:{width:.4f}:{density_profile:.2f}:"
             f"{maintenance_profile:.2f}:{health_profile:.2f}:{variant}").encode("utf-8")
        ) & 0x7FFFFFFF
        key = ("planting module", style, round(width, 4), density_profile,
               maintenance_profile, health_profile, variant,
               round(canonical_length, 3), include_soil)
        collection = _CACHE.get(key)
        if collection is None:
            collection = _collection(
                f"Shared planting profile {density_profile:.2f}-"
                f"{maintenance_profile:.2f}-{health_profile:.2f} variant {variant + 1}"
            )
            builder = (clipped_hedge.create_clipped_hedge
                       if style == "clipped_hedge" else planting.create_planting_strip)
            objects = _capture(lambda: builder(
                "Canonical Planting", canonical_length, width, density_profile,
                maintenance_profile, health_profile, variant_seed, lod="low"))
            if not include_soil:
                for obj in tuple(objects):
                    if "soil" in obj.name.lower():
                        objects.remove(obj)
                        bpy.data.objects.remove(obj, do_unlink=True)
            _move_to_collection(objects, collection)
            _CACHE[key] = collection
        tile_start = start + direction * (module_length * index)
        reverse = rng.random() < 0.5
        location = tile_start + direction * module_length if reverse else tile_start
        instance = _instance(
            collection, f"{name} module {index + 1}",
            (location.x, location.y, elevation), angle + (180 if reverse else 0),
            (module_length / canonical_length, 1.0, 1.0),
        )
        instance["planting_edge_id"] = name
        instance["planting_width_m"] = width
        instance["planting_seed"] = seed
        instance["planting_variant"] = variant + 1
        instance["planting_density"] = density
        instance["planting_maintenance"] = maintenance
        instance["planting_health"] = health
        instance["planting_style"] = style
        instances.append(instance)
    return tuple(instances)


def street_tree_instance(name, location, species, seed, rotation_degrees=0.0):
    """Instance one of several detailed low-LOD individuals with cheap extra variation."""
    # Five skeletons reuse the same twelve leafy branch clusters per species.
    variant_count = 5
    variant = seed % variant_count
    key = ("street tree", species, variant)
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(
            f"Shared street tree {species} variant {variant + 1}"
        )
        canonical_seed = zlib.crc32(
            f"street-tree:{species}:{variant}".encode("utf-8")
        ) & 0x7FFFFFFF
        objects = _capture(lambda: street_tree.create_street_tree(
            "Canonical Street Tree", species=species, seed=canonical_seed,
            lod="low", individual_variation=0.14,
        ))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection

    rng = random.Random(seed ^ 0x71EE5EED)
    horizontal_scale = rng.uniform(0.93, 1.07)
    vertical_scale = rng.uniform(0.94, 1.08)
    young = seed % 23 == 0
    if young:
        horizontal_scale *= .78
        vertical_scale *= .86
    instance = _instance(
        collection, name, location, rotation_degrees,
        (horizontal_scale, horizontal_scale, vertical_scale),
    )
    instance["street_tree_species"] = species
    instance["street_tree_seed"] = seed
    instance["street_tree_variant"] = variant + 1
    instance["street_tree_young_replacement"] = young
    return instance


def street_light_instance(name, location, kind, lit, rotation_degrees=0.0):
    """Instance one shared lit/unlit roadway or pedestrian light asset."""
    if kind not in {"roadway", "pedestrian"}:
        raise ValueError(f"Unsupported street light kind: {kind!r}")
    key = ("street light", kind, bool(lit))
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(
            f"Shared {kind} street light {'lit' if lit else 'unlit'}"
        )
        builder = (street_light.create_roadway_streetlight
                   if kind == "roadway"
                   else street_light.create_pedestrian_streetlight)
        def build_canonical():
            builder(f"Canonical {kind.title()} Street Light", lit=lit)
            # Resolve the asset's baked dimensions before its hierarchy is
            # flattened into the shared collection.  Prewarming now calls this
            # while the scene is still empty, so the update is inexpensive.
            bpy.context.view_layer.update()
        objects = _capture(build_canonical)
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    instance = _instance(collection, name, location, rotation_degrees)
    instance["street_light_kind"] = kind
    instance["street_light_lit"] = bool(lit)
    return instance


def prewarm_street_light_components(specifications):
    """Build each shared lamp before dense trees make dependency updates costly."""
    for kind, lit in sorted(set(specifications)):
        instance = street_light_instance(
            f"Prewarm {kind} street light", (0, 0, -1000), kind, lit)
        bpy.data.objects.remove(instance, do_unlink=True)


def bicycle_marking_instance(name, location, rotation_degrees, width=0.50,
                             white_material=None, blue_material=None):
    key = ("bicycle marking", round(width, 4),
           white_material.name if white_material else "default white",
           blue_material.name if blue_material else "default blue")
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(f"Shared bicycle marking {width:.3f}m")
        objects = _capture(lambda: bicycle_marking.create_bicycle_lane_marking(
            "Canonical Bicycle Marking", width, white_material, blue_material,
        ))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    instance = _instance(collection, name, (*location, 0.0), rotation_degrees)
    instance["marking_width_m"] = width
    instance["marking_length_m"] = (
        width * bicycle_marking.REFERENCE_LENGTH_WIDTH_RATIO
    )
    return instance


def bicycle_blue_chevron_instance(name, location, rotation_degrees, width=0.50,
                                   blue_material=None):
    """Instance the blue-only bicycle direction marking."""
    key = ("bicycle blue chevron", round(width, 4),
           blue_material.name if blue_material else "default blue")
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection(f"Shared bicycle blue chevron {width:.3f}m")
        objects = _capture(lambda: bicycle_marking.create_bicycle_blue_chevron(
            "Canonical Bicycle Blue Chevron", width, blue_material))
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    instance = _instance(collection, name, (*location, 0.0), rotation_degrees)
    instance["asset_type"] = "bicycle_junction_blue_chevron"
    instance["marking_width_m"] = width
    return instance


def bicycle_marking_deformed(name, path, station, lateral, direction,
                             width=0.50, white_material=None,
                             blue_material=None):
    """Create one marking whose paint polygons follow a curved centreline.

    Curved symbols cannot be collection instances because their individual
    vertices need different path frames.  The ordinary straight symbol stays
    cached; only genuinely curved markings pay for unique meshes.
    """
    root = bicycle_marking.create_bicycle_lane_marking(
        name, width, white_material, blue_material)
    travel_sign = -1.0 if direction == "reverse" else 1.0
    for obj in root.children:
        if obj.type != "MESH":
            continue
        for vertex in obj.data.vertices:
            local_x, local_y = vertex.co.x, vertex.co.y
            sample_station = max(
                0.0, min(path.length, station + travel_sign * local_y))
            point = path.offset_point(
                sample_station, lateral - travel_sign * local_x)
            vertex.co.x = point[0]
            vertex.co.y = point[1]
        obj.data.update()
    root["deformed_along_road_curve"] = True
    return root


def _pedestrian_parts(exterior_color):
    if exterior_color in _PEDESTRIAN_PARTS:
        return _PEDESTRIAN_PARTS[exterior_color]
    objects = _capture(lambda: ped.create_pedestrian_signal(
        "Pedestrian Canonical Root", active_light="red", countdown="on",
        countdown_level=0, exterior_color=exterior_color,
        support_side="left", include_support=True,
    ))
    root = next(obj for obj in objects if obj.name.startswith("Pedestrian Canonical Root"))
    objects.remove(root)
    bpy.data.objects.remove(root, do_unlink=True)
    displays, pole, arms, body = [], [], [], []
    pole_prefixes = ("Pedestrian signal support pole", "Support pole top cap",
                     "Support pole fixing band")
    support_prefixes = ("Upper bent pedestrian", "Lower bent pedestrian",
                        "Signal end mounting", "Signal mounting bolt",
                        "Pedestrian signal cable")
    for obj in objects:
        if obj.name.startswith(("Red standing person LEDs", "Blue walking person LEDs",
                                "Countdown bar")):
            displays.append(obj)
        elif obj.name.startswith(pole_prefixes):
            pole.append(obj)
        elif obj.name.startswith(support_prefixes):
            arms.append(obj)
        else:
            body.append(obj)
    parts = tuple(_collection(name) for name in (
        f"Pedestrian {exterior_color} shared body",
        f"Pedestrian {exterior_color} shared arms",
        f"Pedestrian {exterior_color} shared pole",
        f"Pedestrian {exterior_color} canonical displays",
    ))
    for items, collection in zip((body, arms, pole, displays), parts):
        _move_to_collection(items, collection)
    _PEDESTRIAN_PARTS[exterior_color] = parts
    return parts


def _pedestrian_display(active_light, level, exterior_color):
    key = ("pedestrian_display", active_light, level, exterior_color)
    if key in _CACHE:
        return _CACHE[key]
    _, _, _, canonical = _pedestrian_parts(exterior_color)
    collection = _collection(f"Pedestrian display {active_light} {level}")
    red_active = active_light == "red"
    red = (1.0, 0.025, 0.012)
    cyan = (0.005, 0.75, 0.48)
    dark_red = (0.018, 0.002, 0.001)
    dark_cyan = (0.001, 0.018, 0.011)
    mats = {
        "red_person": ped.material("Red standing person LED material",
                                   red if red_active else dark_red,
                                   roughness=0.28 if red_active else 0.68,
                                   emission=red if red_active else None,
                                   strength=7.0 if red_active else 0.0),
        "blue_person": ped.material("Blue walking person LED material",
                                    cyan if not red_active else dark_cyan,
                                    roughness=0.28 if not red_active else 0.68,
                                    emission=cyan if not red_active else None,
                                    strength=7.0 if not red_active else 0.0),
    }
    countdown_color = red if red_active else cyan
    countdown_dark = dark_red if red_active else dark_cyan
    mats["count_lit"] = ped.material("Countdown illuminated bars", countdown_color,
                                     roughness=0.25, emission=countdown_color, strength=7.0)
    mats["count_dark"] = ped.material("Countdown unlit bars", countdown_dark, roughness=0.72)
    for source in canonical.objects:
        obj = source.copy()
        if source.name.startswith("Red standing person LEDs"):
            mat = mats["red_person"]
        elif source.name.startswith("Blue walking person LEDs"):
            mat = mats["blue_person"]
        else:
            # Red-active countdown is in the lower window; blue-active is upper.
            active_window = obj.location.z < 3.35 if red_active else obj.location.z > 3.35
            window_center = 3.19 if obj.location.z < 3.35 else 3.51
            row = round((obj.location.z - (window_center - 0.086)) / 0.0245)
            mat = mats["count_lit"] if active_window and row < level else mats["count_dark"]
        # Geometry is identical across states. Override the material on the
        # object while retaining the shared (and dense) canonical LED mesh.
        for slot in obj.material_slots:
            slot.link = "OBJECT"
            slot.material = mat
        collection.objects.link(obj)
    _CACHE[key] = collection
    return collection


def pedestrian_instance(name, location, rotation_degrees, active_light, countdown_level,
                        support_side="left", include_support=True, exterior_color="white"):
    body, arms, pole, _ = _pedestrian_parts(exterior_color)
    key = ("pedestrian", active_light, countdown_level, support_side, include_support,
           exterior_color)
    variant = _CACHE.get(key)
    if variant is None:
        variant = _collection("Generated " + " ".join(map(str, key)))
        right = support_side == "right"
        shift = -1.46 if right else 0.0
        _instance(body, "Body", (shift, 0, 0), owner=variant)
        _instance(_pedestrian_display(active_light, countdown_level, exterior_color), "Display",
                  (shift, 0, 0), owner=variant)
        _instance(arms, "Arms", scale=(-1, 1, 1) if right else (1, 1, 1), owner=variant)
        if include_support:
            _instance(pole, "Pole", owner=variant)
        _CACHE[key] = variant
    return _instance(variant, name, location, rotation_degrees)


def _vehicle_head_parts(exterior_color, arrow_blocks):
    key = (exterior_color, arrow_blocks)
    if key in _VEHICLE_HEAD_PARTS:
        return _VEHICLE_HEAD_PARTS[key]
    def build():
        root = bpy.data.objects.new('Vehicle Head Canonical Root', None)
        bpy.context.collection.objects.link(root)
        housing, housing_dark, rubber, _ = vehicle.build_signal_head(
            root, active_light='red', exterior_color=exterior_color,
            horizontal_extension=0.0)
        vehicle.build_arrow_blocks(root,arrow_blocks,set(),housing,housing_dark,rubber,0.0)
    objects = _capture(build)
    root = next(o for o in objects if o.name.startswith('Vehicle Head Canonical Root'))
    objects.discard(root)
    displays = [obj for obj in objects
                if "coarse LEDs" in obj.name or obj.name.startswith("right arrow LED")]
    structure = [obj for obj in objects if obj not in displays]
    structure_collection = _collection(f"Vehicle {exterior_color} {arrow_blocks} shared head")
    display_collection = _collection(f"Vehicle {exterior_color} {arrow_blocks} canonical display")
    _move_to_collection(structure, structure_collection)
    _move_to_collection(displays, display_collection)
    bpy.data.objects.remove(root, do_unlink=True)
    _VEHICLE_HEAD_PARTS[key] = structure_collection, display_collection
    return _VEHICLE_HEAD_PARTS[key]


def _vehicle_support_parts(exterior_color, horizontal_extension):
    key = (exterior_color, horizontal_extension)
    if key in _VEHICLE_SUPPORT_PARTS:
        return _VEHICLE_SUPPORT_PARTS[key]
    def build():
        root = bpy.data.objects.new('Vehicle Support Canonical Root', None)
        bpy.context.collection.objects.link(root)
        housing, _, bolt = vehicle.exterior_materials(exterior_color)
        vehicle.build_support(root,housing,bolt,exterior_color,horizontal_extension)
    objects = _capture(build)
    root = next(o for o in objects if o.name.startswith('Vehicle Support Canonical Root'))
    objects.discard(root)
    collection = _collection(
        f"Vehicle {exterior_color} {horizontal_extension:.3f}m shared support"
    )
    _move_to_collection(objects, collection)
    bpy.data.objects.remove(root, do_unlink=True)
    _VEHICLE_SUPPORT_PARTS[key] = collection
    return collection


def _vehicle_structure(exterior_color, arrow_blocks, horizontal_extension, support_side):
    key = (exterior_color, arrow_blocks, horizontal_extension, support_side)
    if key in _VEHICLE_STRUCTURE:
        return _VEHICLE_STRUCTURE[key]
    head, canonical_display = _vehicle_head_parts(exterior_color, arrow_blocks)
    support = _vehicle_support_parts(exterior_color, horizontal_extension)
    structure_collection = _collection(f"Vehicle {exterior_color} shared structure")
    right = support_side == "right"
    # Moving, rather than mirroring, the head preserves the authored right-arrow
    # direction. Only the support hardware itself is mirrored.
    head_shift = (-2.0 * vehicle.HEAD_CENTER.x - horizontal_extension
                  if right else horizontal_extension)
    _instance(head, "Head structure", (head_shift, 0, 0), owner=structure_collection)
    _instance(support, "Support structure", scale=(-1, 1, 1) if right else (1, 1, 1),
              owner=structure_collection)
    _VEHICLE_STRUCTURE[key] = structure_collection, canonical_display, head_shift
    return _VEHICLE_STRUCTURE[key]


def _vehicle_display(active_light, exterior_color, arrow_blocks, active_arrow):
    key = ("vehicle_display", active_light, exterior_color, arrow_blocks, active_arrow)
    if key in _CACHE:
        return _CACHE[key]
    _, canonical = _vehicle_head_parts(exterior_color, arrow_blocks)
    collection = _collection(f"Vehicle display {active_light}")
    specs = {
        "Green blue": ((0.015, 0.72, 0.38), (0.003, 0.012, 0.009), "green"),
        "Amber": ((1.0, 0.48, 0.015), (0.014, 0.010, 0.003), "yellow"),
        "Red": ((1.0, 0.035, 0.018), (0.014, 0.003, 0.002), "red"),
    }
    for source in canonical.objects:
        if source.name.startswith("right arrow LED"):
            lit, dark = (0.010, 0.62, 0.38), (0.002, 0.014, 0.010)
            active = active_arrow
        else:
            label = next(label for label in specs if source.name.startswith(label))
            lit, dark, key_name = specs[label]
            active = active_light == key_name
        mat = vehicle.material(source.name + " material", lit if active else dark, 0.0,
                               0.28 if active else 0.62,
                               emission=lit if active else None,
                               strength=8.0 if active else 0.0)
        obj = source.copy()
        for slot in obj.material_slots:
            slot.link = "OBJECT"
            slot.material = mat
        collection.objects.link(obj)
    _CACHE[key] = collection
    return collection


def _name_plate(japanese, roman):
    global _NAME_PLATE_STRUCTURE
    key = ("name_plate", japanese, roman)
    if key in _CACHE:
        return _CACHE[key]
    collection = _collection(f"Name plate {japanese}")
    if japanese.strip() or roman.strip():
        if _NAME_PLATE_STRUCTURE is None:
            before = set(bpy.context.scene.objects)
            root = bpy.data.objects.new("Name Plate Canonical Root", None)
            bpy.context.collection.objects.link(root)
            bolt = vehicle.material("Stainless name plate hardware", (0.52, 0.56, 0.57), 0.62, 0.43)
            vehicle.build_intersection_sign(root, "一丁目", "1-chome", bolt)
            objects = set(bpy.context.scene.objects) - before
            objects.discard(root)
            bpy.data.objects.remove(root, do_unlink=True)
            text_objects = [obj for obj in objects if obj.name.startswith("Intersection Japanese")
                            or obj.name.startswith("Intersection romanized")]
            for obj in text_objects:
                objects.remove(obj)
                bpy.data.objects.remove(obj, do_unlink=True)
            _NAME_PLATE_STRUCTURE = _collection("Shared intersection name plate structure")
            _move_to_collection(objects, _NAME_PLATE_STRUCTURE)
        _instance(_NAME_PLATE_STRUCTURE, "Plate structure", owner=collection)
        blue = vehicle.material("Intersection sign blue text", (0.015, 0.16, 0.43), 0.0, 0.68)
        root = bpy.data.objects.new("Name Text Root", None)
        collection.objects.link(root)
        vehicle.text_object("Intersection Japanese name", japanese, (0.90, -0.009, 5.390),
                            0.270, blue, root, max_width=0.77, font_weight=5)
        vehicle.text_object("Intersection romanized name", roman, (0.90, -0.009, 5.260),
                            0.1125, blue, root, max_width=0.75, font_weight=7)
        for obj in list(root.children):
            # The temporary root is identity. Keep the authored local transform;
            # querying matrix_world here would require a dependency-graph update
            # and was also able to collapse text in an unlinked collection.
            obj.parent = None
            for owner in list(obj.users_collection):
                owner.objects.unlink(obj)
            collection.objects.link(obj)
        bpy.data.objects.remove(root, do_unlink=True)
    _CACHE[key] = collection
    return collection


def vehicle_instance(name, location, rotation_degrees, active_light,
                     intersection_name="", intersection_roman="", exterior_color="white",
                     arrow_blocks="none", active_arrow=False, horizontal_extension=1.5,
                     support_side="left"):
    key = ("vehicle", active_light, intersection_name, intersection_roman, exterior_color,
           arrow_blocks, active_arrow, horizontal_extension, support_side)
    variant = _CACHE.get(key)
    if variant is None:
        structure, _, head_shift = _vehicle_structure(
            exterior_color, arrow_blocks, horizontal_extension, support_side,
        )
        variant = _collection("Generated " + " ".join(map(str, key)))
        _instance(structure, "Structure", owner=variant)
        _instance(_vehicle_display(active_light, exterior_color, arrow_blocks, active_arrow),
                  "Display", (head_shift, 0, 0), owner=variant)
        plate = _name_plate(intersection_name, intersection_roman)
        if plate.objects:
            plate_shift = (horizontal_extension if support_side == "left"
                           else -1.8 - horizontal_extension)
            _instance(plate, "Name Plate", (plate_shift, 0, 0), owner=variant)
        _CACHE[key] = variant
    return _instance(variant, name, location, rotation_degrees)


def prewarm_signal_components(vehicle_specs, pedestrian_specs, name_specs):
    """Build expensive editable signal sources while the Blender scene is small."""
    for exterior_color, arrow_blocks, horizontal_extension, support_side, light, active_arrow in vehicle_specs:
        _vehicle_structure(exterior_color, arrow_blocks, horizontal_extension, support_side)
        _vehicle_display(light, exterior_color, arrow_blocks, active_arrow)
    for exterior_color, light, level in pedestrian_specs:
        _pedestrian_parts(exterior_color)
        _pedestrian_display(light, level, exterior_color)
    for japanese, roman in name_specs:
        _name_plate(japanese, roman)


def cached_asset_instance(key, builder, name, location, rotation_degrees):
    """Fallback cache for less frequent assets such as road signs."""
    collection = _CACHE.get(key)
    if collection is None:
        collection = _collection("Generated Asset " + " ".join(map(str, key)))
        objects = _capture(builder)
        _move_to_collection(objects, collection)
        _CACHE[key] = collection
    return _instance(collection, name, location, rotation_degrees)


def prewarm_cached_asset(key, builder):
    """Build a fallback cached source before the scene dependency graph grows."""
    if key in _CACHE:
        return
    collection = _collection("Generated Asset " + " ".join(map(str, key)))
    objects = _capture(builder)
    _move_to_collection(objects, collection)
    _CACHE[key] = collection


__all__ = ("bicycle_marking_instance", "cached_asset_instance", "create_dual_warning_lamp",
           "create_fire_hydrant_cover", "create_fire_hydrant_sign",
           "create_keep_left_sign",
           "create_road_sign",
           "create_road_sign_stack",
           "guardrail_instance", "pedestrian_instance", "planting_instance",
           "reflector_pole_instance",
           "prewarm_cached_asset", "prewarm_roadside_components",
           "vehicle_instance")
