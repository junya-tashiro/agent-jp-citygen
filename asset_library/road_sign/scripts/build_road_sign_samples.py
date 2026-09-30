import bpy
import json
import math
import os
import sys
from pathlib import Path
from mathutils import Vector

from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asset_library.shared.surfaces import finish

from asset_library.road_sign.scripts.road_sign_face_geometry import (
    CROSSWALK_FACE_SIZE_PX, CROSSWALK_LEFT_STRIPE, CROSSWALK_NEAR_STRIPE,
    CROSSWALK_PEDESTRIAN, CROSSWALK_PLATE_OUTLINE, CROSSWALK_RIGHT_STRIPE,
    CROSSWALK_WHITE_BORDER, STOP_FACE_SIZE_PX, STOP_GLYPH_MA, STOP_GLYPH_RE,
    STOP_GLYPH_STOP, STOP_PLATE_OUTLINE, STOP_WHITE_BORDER,
)


ASSET_ROOT = Path(__file__).resolve().parent.parent
POLE_HEIGHT = 3.0
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"

SIGN_SPECS = {
    "止まれ": {"shape": "triangle_down", "width": 0.42 * 247 / 219, "height": 0.42},
    "横断歩道": {"shape": "triangle_up", "width": 0.60 * 182 / 207, "height": 0.60},
    "指定方向外進行禁止（左折）": {"shape": "circle", "width": 0.45, "height": 0.45},
    "駐車禁止": {"shape": "circle", "width": 0.45, "height": 0.45},
}


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    key = name.lower()
    if 'reflective' in key:
        finish(mat, 'sheeting')
    elif 'galvanized' in key:
        finish(mat, 'galvanized')
    elif 'aluminum' in key:
        finish(mat, 'metal')
    return mat


def rounded_polygon(points, radius, steps=7):
    rounded = []
    for i, point in enumerate(points):
        p = Vector(point)
        prev = Vector(points[i-1])
        nxt = Vector(points[(i+1) % len(points)])
        incoming = prev - p
        outgoing = nxt - p
        corner_radius = radius[i] if isinstance(radius, (tuple, list)) else radius
        a = p + incoming.normalized() * min(corner_radius, incoming.length*0.22)
        b = p + outgoing.normalized() * min(corner_radius, outgoing.length*0.22)
        for step in range(steps):
            t = step / (steps - 1)
            q = (1-t)*(1-t)*a + 2*(1-t)*t*p + t*t*b
            rounded.append(tuple(q))
    return rounded


def shape_points(shape, width, height, segments=96):
    if shape == "circle":
        return [(math.cos(2*math.pi*i/segments)*width/2,
                 math.sin(2*math.pi*i/segments)*height/2) for i in range(segments)]
    if shape == "triangle_down":
        # Japanese stop signs use broad upper corners and a tighter lower tip.
        return rounded_polygon(
            [(-width/2, height/2), (width/2, height/2), (0, -height/2)],
            (0.052, 0.052, 0.038),
            steps=10,
        )
    if shape == "triangle_up":
        return rounded_polygon(
            [(0, height/2), (width/2, -height/2), (-width/2, -height/2)],
            (0.042, 0.036, 0.036), steps=10,
        )
    if shape == "diamond":
        return rounded_polygon([(0, height/2), (width/2, 0), (0, -height/2), (-width/2, 0)], 0.020)
    return rounded_polygon([(-width/2, -height/2), (width/2, -height/2),
                            (width/2, height/2), (-width/2, height/2)], 0.018)


def create_plate(name, shape, width, height, center, front_mat, rear_mat,
                 thickness=0.0012, outline_points=None):
    points = outline_points if outline_points is not None else shape_points(
        shape, width, height)
    count = len(points)
    cx, cy, cz = center
    verts = [(cx+x, cy-thickness/2, cz+z) for x, z in points]
    verts += [(cx+x, cy+thickness/2, cz+z) for x, z in points]
    faces = [tuple(range(count)), tuple(reversed(range(count, count*2)))]
    for i in range(count):
        ni = (i+1) % count
        faces.append((i, ni, count+ni, count+i))
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(front_mat)
    mesh.materials.append(rear_mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.polygons[0].material_index = 0
    for poly in mesh.polygons[1:]:
        poly.material_index = 1
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            x, _, z = mesh.vertices[vi].co
            uv.data[li].uv = ((x-cx)/width + 0.5, (z-cz)/height + 0.5)
    bevel = obj.modifiers.new("Rolled safe edge", "BEVEL")
    bevel.width = 0.002
    bevel.segments = 3
    return obj


def cube(name, location, scale, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Edge radius", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def add_mounting_hardware(name, shape, x, pole_y, sign_y, sign_z, width, rear_mat):
    # Two horizontal aluminum ribs spot-welded to the rear face.
    for dz in (-0.13, 0.13):
        rib_half_width = width * (0.10 if shape in {
            "triangle_down", "triangle_up", "diamond"} else 0.27)
        cube(f"{name} rear rib", (x, sign_y+0.018, sign_z+dz),
             (rib_half_width, 0.014, 0.018), rear_mat, 0.005)
        cube(f"{name} short standoff", (x, (sign_y+pole_y)/2, sign_z+dz),
             (0.035, abs(pole_y-sign_y)/2, 0.022), rear_mat, 0.005)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.037, minor_radius=0.006,
                                        major_segments=40, minor_segments=10,
                                        location=(x, pole_y, sign_z+dz),
                                        rotation=(math.radians(90), 0, 0))
        bpy.context.object.name = f"{name} U band"
        bpy.context.object.data.materials.append(rear_mat)


def build_sign_stack(collection_name, sign_types, x, pole_mat, rear_mat):
    """Build one pole carrying one or more procedural faces, top to bottom."""
    if not sign_types:
        raise ValueError("sign_types must contain at least one sign")
    unknown = [name for name in sign_types if name not in SIGN_SPECS]
    if unknown:
        raise ValueError(f"Unsupported procedural road sign(s): {unknown}")
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    before = set(bpy.context.scene.objects)
    pole_y = 0.10
    sign_y = 0.0
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.030, depth=POLE_HEIGHT,
                                       location=(x, pole_y, POLE_HEIGHT/2))
    pole = bpy.context.object
    pole.name = f"{collection_name} galvanized pole"
    pole.data.materials.append(pole_mat)
    next_top = POLE_HEIGHT - 0.07
    for index, sign_type in enumerate(sign_types):
        spec = SIGN_SPECS[sign_type]
        sign_z = next_top - spec["height"] * 0.5
        face_name = (sign_type if len(sign_types) == 1 else
                     f"{collection_name} {index + 1} {sign_type}")
        white = material(f"{face_name} white reflective graphic",
                         (0.96, 0.97, 0.95), 0.01, 0.20)
        if sign_type == "止まれ":
            field = material(f"{face_name} red reflective face",
                             (0.92, 0.006, 0.004), 0.02, 0.24)
            outline = stop_outline_points(spec["width"], spec["height"])
            create_plate(face_name, spec["shape"], spec["width"], spec["height"],
                         (x, sign_y, sign_z), field, rear_mat,
                         outline_points=outline)
            add_procedural_stop_face(face_name, x, sign_z, spec["width"],
                                     spec["height"], field, white, sign_y - 0.0013)
        elif sign_type == "横断歩道":
            field = material(f"{face_name} blue reflective face",
                             (0.0, 0.112, 0.32), 0.02, 0.24)
            outline = crosswalk_outline_points(spec["width"], spec["height"])
            create_plate(face_name, spec["shape"], spec["width"], spec["height"],
                         (x, sign_y, sign_z), field, rear_mat,
                         outline_points=outline)
            add_procedural_crosswalk_face(
                face_name, x, sign_z, spec["width"], spec["height"],
                white, sign_y - 0.0013)
        elif sign_type == "指定方向外進行禁止（左折）":
            field = material(f"{face_name} blue reflective face",
                             (0.0, 0.112, 0.32), 0.02, 0.24)
            create_plate(face_name, spec["shape"], spec["width"], spec["height"],
                         (x, sign_y, sign_z), field, rear_mat)
            add_mandatory_left_face(
                face_name, x, sign_z, spec["width"], field, white,
                sign_y - 0.0013)
        elif sign_type == "駐車禁止":
            field = material(f"{face_name} blue reflective face",
                             (0.0, 0.112, 0.32), 0.02, 0.24)
            red = material(f"{face_name} red reflective graphic",
                           (0.90, 0.008, 0.012), 0.02, 0.22)
            create_plate(face_name, spec["shape"], spec["width"], spec["height"],
                         (x, sign_y, sign_z), field, rear_mat)
            add_no_parking_face(
                face_name, x, sign_z, spec["width"], field, red, white,
                sign_y - 0.0013)
        add_mounting_hardware(face_name, spec["shape"], x, pole_y, sign_y,
                              sign_z, spec["width"], rear_mat)
        next_top = sign_z - spec["height"] * 0.5 - 0.045
    for obj in set(bpy.context.scene.objects) - before:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)


def build_road_sign(name, spec, x, pole_mat, rear_mat):
    """Backward-compatible single-face wrapper around the stack builder."""
    del spec
    return build_sign_stack(name, (name,), x, pole_mat, rear_mat)


def create_road_sign(sign_type, name="Road Sign", location=(0, 0, 0),
                     rotation_degrees=0):
    return create_road_sign_stack((sign_type,), name, location, rotation_degrees)


def create_road_sign_stack(sign_types, name="Road Sign Stack", location=(0, 0, 0),
                           rotation_degrees=0):
    """Build an editable multi-face sign on one shared pole."""
    pole_mat = material("Galvanized steel pole", (0.50, 0.53, 0.54), 0.82, 0.34)
    rear_mat = material("Aluminum sign back and fittings", (0.48, 0.51, 0.52), 0.82, 0.30)
    before = set(bpy.context.scene.objects)
    build_sign_stack(name, tuple(sign_types), 0.0, pole_mat, rear_mat)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["graphic_source"] = "procedural_geometry"
    root["sign_types"] = json.dumps(tuple(sign_types), ensure_ascii=False)
    return root


def _procedural_face(name, points, y, mat):
    """Create one code-defined reflective graphic in the local X/Z plane."""
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata([(x, y, z) for x, z in points], [], [tuple(range(len(points)))])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _cubic_points(start, control_a, control_b, end, segments=8):
    points = []
    for index in range(1, segments + 1):
        t = index / segments
        inverse = 1.0 - t
        points.append((
            inverse ** 3 * start[0]
            + 3 * inverse * inverse * t * control_a[0]
            + 3 * inverse * t * t * control_b[0]
            + t ** 3 * end[0],
            inverse ** 3 * start[1]
            + 3 * inverse * inverse * t * control_a[1]
            + 3 * inverse * t * t * control_b[1]
            + t ** 3 * end[1],
        ))
    return points


def left_turn_arrow_points(center_x, center_z, diameter):
    """Metric outline of the mandatory-left direction arrow."""
    scale = diameter / 236.0

    def metric(point):
        return (center_x + (point[0] - 118.0) * scale,
                center_z + (118.0 - point[1]) * scale)

    design = [(37, 78)]
    design += _cubic_points((37, 78), (31, 82), (33, 90), (39, 94), 4)
    design += [(107, 134)]
    design += _cubic_points((107, 134), (112, 137), (118, 132), (115, 126), 4)
    design += [(101, 100), (140, 100)]
    design += _cubic_points((140, 100), (150, 100), (157, 108), (157, 118), 8)
    design += [(157, 182), (185, 182), (185, 116)]
    design += _cubic_points((185, 116), (185, 91), (166, 71), (141, 71), 10)
    design += [(101, 71), (115, 44)]
    design += _cubic_points((115, 44), (118, 38), (111, 33), (106, 37), 4)
    design += [(37, 78)]
    return tuple(metric(point) for point in design)


def add_mandatory_left_face(name, center_x, center_z, diameter,
                            blue, white, front_y):
    """Build the white border and left-turn arrow on a blue circular field."""
    segments = 128

    def circle(radius):
        return tuple(
            (center_x + math.cos(math.tau * index / segments) * radius,
             center_z + math.sin(math.tau * index / segments) * radius)
            for index in range(segments)
        )

    _procedural_face(name + " white border", circle(diameter * 0.475), front_y, white)
    _procedural_face(name + " inset blue field", circle(diameter * 0.438),
                     front_y - 0.0002, blue)
    _procedural_face(name + " mandatory left arrow",
                     left_turn_arrow_points(center_x, center_z, diameter),
                     front_y - 0.0004, white)


def add_no_parking_face(name, center_x, center_z, diameter,
                        blue, red, white, front_y):
    """Build a blue disc with one red prohibition ring and diagonal slash."""
    segments = 128

    def circle(radius):
        return tuple(
            (center_x + math.cos(math.tau * index / segments) * radius,
             center_z + math.sin(math.tau * index / segments) * radius)
            for index in range(segments)
        )

    # A narrow white reflective perimeter surrounds the prohibition ring.
    _procedural_face(name + " thin white perimeter",
                     circle(diameter * 0.500), front_y, white)
    _procedural_face(name + " red prohibition ring",
                     circle(diameter * 0.487), front_y - 0.0002, red)
    _procedural_face(name + " blue ring centre",
                     circle(diameter * 0.374), front_y - 0.0004, blue)

    # Rounded capsule running from upper-left to lower-right.
    half_length = diameter * 0.401
    half_width = diameter * 0.0630
    angle = math.radians(-45.0)
    along = Vector((math.cos(angle), math.sin(angle)))
    across = Vector((-along.y, along.x))
    slash = []
    for endpoint_sign, start_angle in ((1.0, -90.0), (-1.0, 90.0)):
        endpoint = Vector((center_x, center_z)) + along * (
            endpoint_sign * half_length)
        for step in range(17):
            theta = math.radians(start_angle + step * 180.0 / 16.0)
            point = endpoint + along * (math.cos(theta) * half_width)
            point += across * (math.sin(theta) * half_width)
            slash.append(tuple(point))
    _procedural_face(name + " red prohibition slash", tuple(slash),
                     front_y - 0.0006, red)


def _scaled_outline(points, size_px, width, height):
    """Convert one face-design coordinate path to local metric X/Z."""
    design_width, design_height = size_px
    return tuple(
        ((x / (design_width - 1) - 0.5) * width,
         (0.5 - y / (design_height - 1)) * height)
        for x, y in points
    )


def stop_outline_points(width, height):
    return _scaled_outline(
        STOP_PLATE_OUTLINE[0], STOP_FACE_SIZE_PX, width, height)


def _coordinate_paths_face(name, paths, size_px, center_x, center_z,
                           width, height, front_y, mat):
    """Create one named graphic component from normalized polygon paths."""
    design_width, design_height = size_px
    curves = [
        [Vector((
            center_x + (x / design_width - 0.5) * width,
            center_z + (0.5 - y / design_height) * height,
        )) for x, y in path]
        for path in paths
    ]
    vertices = [(point.x, front_y, point.y)
                for path in curves for point in path]
    faces = tessellate_polygon(curves)
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_procedural_stop_face(name, center_x, center_z, width, height,
                             red, white, front_y):
    """Build the white border and three Japanese glyph components."""
    del red
    parts = (
        ("white border", STOP_WHITE_BORDER),
        ("glyph stop", STOP_GLYPH_STOP),
        ("glyph ma", STOP_GLYPH_MA),
        ("glyph re", STOP_GLYPH_RE),
    )
    for label, paths in parts:
        _coordinate_paths_face(
            f"{name} {label}", paths, STOP_FACE_SIZE_PX,
            center_x, center_z, width, height, front_y, white)


def crosswalk_outline_points(width, height):
    return _scaled_outline(
        CROSSWALK_PLATE_OUTLINE[0], CROSSWALK_FACE_SIZE_PX, width, height)


def add_procedural_crosswalk_face(name, center_x, center_z, width, height,
                                  white, front_y):
    """Build the border, pedestrian and three crossing-stripe components."""
    parts = (
        ("white border", CROSSWALK_WHITE_BORDER),
        ("pedestrian", CROSSWALK_PEDESTRIAN),
        ("near crossing stripe", CROSSWALK_NEAR_STRIPE),
        ("left crossing stripe", CROSSWALK_LEFT_STRIPE),
        ("right crossing stripe", CROSSWALK_RIGHT_STRIPE),
    )
    for label, paths in parts:
        _coordinate_paths_face(
            f"{name} {label}", paths, CROSSWALK_FACE_SIZE_PX,
            center_x, center_z, width, height, front_y, white)


def create_keep_left_sign(name="Keep Left Sign", location=(0, 0, 0),
                          rotation_degrees=0):
    """Create 指定方向外進行禁止（左下矢印）from metric geometry."""
    before = set(bpy.context.scene.objects)
    diameter = 0.45
    pole_height = 1.48
    sign_z = 1.22
    pole_y = 0.075
    pole_mat = material(name + " pale matte galvanized pole",
                        (0.70, 0.72, 0.71), 0.18, 0.78)
    rear_mat = material(name + " aluminum back", (0.48, 0.51, 0.52), 0.82, 0.30)
    blue = material(name + " traffic blue reflective", (0.012, 0.285, 0.585), 0.04, 0.25)
    white = material(name + " white reflective", (0.92, 0.94, 0.93), 0.02, 0.22)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40, radius=0.026, depth=pole_height,
        location=(0, pole_y, pole_height * 0.5),
    )
    pole = bpy.context.object
    pole.name = name + " pole"
    pole.data.materials.append(pole_mat)

    create_plate(name + " aluminum plate", "circle", diameter, diameter,
                 (0, 0, sign_z), blue, rear_mat, thickness=0.006)
    segments = 96
    circle = lambda radius: tuple(
        (math.cos(math.tau * i / segments) * radius,
         sign_z + math.sin(math.tau * i / segments) * radius)
        for i in range(segments)
    )
    _procedural_face(name + " white border", circle(0.216), -0.0032, white)
    _procedural_face(name + " blue field", circle(0.194), -0.0038, blue)

    # Broad diagonal shaft, compact neck and asymmetric softened arrowhead.
    arrow_scale = 0.78
    arrow = rounded_polygon(tuple((x * arrow_scale, z * arrow_scale) for x, z in (
        (-0.171, -0.148), (-0.101, 0.128), (-0.050, 0.047),
        (0.102, 0.198), (0.164, 0.137), (0.006, -0.021),
        (0.132, -0.057),
    )), 0.010, steps=5)
    _procedural_face(name + " white lower-left arrow",
                     tuple((x, sign_z + z) for x, z in arrow), -0.0044, white)
    add_mounting_hardware(name, "circle", 0.0, pole_y, 0.0,
                          sign_z, diameter, rear_mat)

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["graphic_source"] = "procedural_geometry"
    root["sign_code"] = "specified_direction_keep_left"
    return root


def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


if not EMBEDDED_BUILD:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
if not EMBEDDED_BUILD:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 64
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium Low Contrast"

    pole_mat = material("Galvanized steel pole", (0.50, 0.53, 0.54), 0.82, 0.34)
    rear_mat = material("Aluminum sign back and fittings", (0.48, 0.51, 0.52), 0.82, 0.30)
    ground_mat = material("Neutral ground", (0.08, 0.09, 0.10), 0.0, 0.82)

    build_sign_stack("横断歩道 単体", ("横断歩道",), -2.25, pole_mat, rear_mat)
    build_sign_stack("止まれ＋横断歩道", ("止まれ", "横断歩道"),
                     -0.75, pole_mat, rear_mat)
    build_sign_stack(
        "止まれ＋指定方向外進行禁止（左折）",
        ("止まれ", "指定方向外進行禁止（左折）"), 0.75,
        pole_mat, rear_mat)
    build_sign_stack("駐車禁止 単体", ("駐車禁止",), 2.25,
                     pole_mat, rear_mat)

    cube("Preview Ground", (0, 0.8, -0.04), (5.3, 3.2, 0.04), ground_mat)
    world = scene.world or bpy.data.worlds.new("Studio world")
    scene.world = world
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Color"].default_value = (0.025, 0.035, 0.055, 1)
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"].default_value = 0.35

    light_data = bpy.data.lights.new("Large softbox", "AREA")
    light_data.energy = 1350
    light_data.shape = "DISK"
    light_data.size = 6
    light = bpy.data.objects.new("Large softbox", light_data)
    bpy.context.collection.objects.link(light)
    light.location = (-3, -4, 7)
    look_at(light, (0, 0, 1.4))

    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0, -13.5, 2.25)
    cam_data.lens = 62
    look_at(cam, (0, 0, 1.50))
    scene.camera = cam

    scene.render.filepath = str(ASSET_ROOT / "renders" / "road_sign_samples.png")
    if not EMBEDDED_BUILD:
        bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(ASSET_ROOT / "blend" / "road_sign_samples.blend"))
