import bpy
import argparse
import math
import os
import sys
from pathlib import Path
from mathutils import Vector

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from asset_library.shared.surfaces import signal_finish, smooth_bevel



ASSET_ROOT = Path(__file__).resolve().parent.parent
POLE_HEIGHT = 5.8
HEAD_CENTER = Vector((2.05, 0.0, 5.35))


def build_options(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-light", choices=("green", "yellow", "red", "none"), default="red")
    parser.add_argument("--arrow-blocks", choices=("none", "right", "all"), default="right")
    parser.add_argument("--active-arrows", default="right",
                        help="Comma-separated selection from left,up,right, or none")
    parser.add_argument("--exterior-color", choices=("white", "brown"), default="white",
                        help="Exterior finish for the housing, pole, arms and hardware")
    parser.add_argument("--skip-render", action="store_true",
                        help="Save the blend without producing preview renders")
    parser.add_argument("--intersection-name", default="中 央")
    parser.add_argument("--intersection-roman", default="Chuo")
    parser.add_argument("--horizontal-extension", type=float, default=1.5,
                        help="Additional horizontal reach in metres from pole to head")
    parser.add_argument("--support-side", choices=("left", "right"), default="left",
                        help="Pole side as seen by approaching traffic")
    args, _ = parser.parse_known_args(argv)
    active = set() if args.active_arrows == "none" else set(args.active_arrows.split(","))
    invalid = active - {"left", "up", "right"}
    if invalid:
        raise ValueError(f"Unsupported active arrow(s): {sorted(invalid)}")
    args.active_arrows = active
    if args.horizontal_extension < 0:
        raise ValueError("--horizontal-extension must be non-negative")
    return args


BUILD_OPTIONS = build_options(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
EMBEDDED_BUILD = os.environ.get("BLENDER_ASSET_EMBEDDED") == "1"


def material(name, color, metallic=0.0, roughness=0.5, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return signal_finish(m, name, metallic, emission)


def concrete_material():
    m = material("Pale weathered concrete pole", (0.54, 0.55, 0.54), 0.0, 0.98)
    nodes = m.node_tree.nodes
    links = m.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
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
    return m


def exterior_materials(color):
    if color == "brown":
        # A very dark, low-gloss brown commonly used to make roadside equipment
        # visually recede. Keep a slightly darker trim so the housing retains
        # readable edges in subdued light.
        painted = material("Dark brown painted exterior", (0.070, 0.046, 0.036),
                           0.18, 0.62)
        trim = material("Dark brown housing edge and hood", (0.022, 0.014, 0.011),
                        0.12, 0.70)
        hardware = material("Dark brown coated fasteners", (0.050, 0.032, 0.025),
                            0.34, 0.52)
        return painted, trim, hardware

    painted = material("White painted aluminum housing", (0.84, 0.86, 0.83),
                       0.08, 0.58)
    trim = material("Housing edge and hood", (0.055, 0.065, 0.063), 0.05, 0.67)
    hardware = material("Stainless fasteners", (0.52, 0.56, 0.57), 0.62, 0.43)
    return painted, trim, hardware


def parent_to(obj, root):
    obj.parent = root
    return obj


def cube(name, location, scale, mat, root, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new("Rounded manufactured edge", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        smooth_bevel(o, mod)
    return parent_to(o, root)


def cylinder(name, location, radius, depth, mat, root, rotation=(0, 0, 0), vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=location, rotation=rotation)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return parent_to(o, root)


def pipe(name, points, radius, mat, root):
    curve = bpy.data.curves.new(name + " Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 5
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, co in zip(spline.bezier_points, points):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return parent_to(o, root)


def text_object(name, body, location, size, mat, root, max_width, font_weight=6):
    curve = bpy.data.curves.new(name + " Text", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.00015
    from asset_library.shared.fonts import japanese_font
    if any(ord(ch)>127 for ch in body):curve.font=japanese_font()
    o = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(o)
    o.location = location
    o.rotation_euler = (math.radians(90), 0, 0)
    o.data.materials.append(mat)
    parent_to(o, root)
    # Updating the whole dependency graph for every short name dominates large
    # road-network builds. Only measure strings whose conservative nominal width
    # can exceed the board; short names are guaranteed to fit at authored scale.
    nominal_width = len(body) * size * 0.60
    if nominal_width > max_width:
        bpy.context.view_layer.update()
        if o.dimensions.x > max_width:
            scale = max_width / o.dimensions.x
            o.scale.x *= scale
    return o


def visor(name, center, inner_radius, depth, mat, root, segments=48):
    # An extruded upper semi-annulus, open below like a real signal hood.
    outer_radius = inner_radius + 0.012
    # The rear edge is seated directly on the housing face; only the front edge
    # projects outward. This avoids the visibly floating hood used previously.
    y_back = center.y + 0.025
    y_front = y_back - depth
    verts = []
    for y in (y_back, y_front):
        for radius in (inner_radius, outer_radius):
            for i in range(segments + 1):
                angle = math.pi * i / segments
                verts.append((center.x + math.cos(angle) * radius, y,
                              center.z + math.sin(angle) * radius))
    ring = segments + 1
    faces = []
    inner_back, outer_back, inner_front, outer_front = 0, ring, ring * 2, ring * 3
    for i in range(segments):
        ni = i + 1
        faces.extend([
            (inner_front+i, inner_front+ni, outer_front+ni, outer_front+i),
            (outer_back+i, outer_back+ni, outer_front+ni, outer_front+i),
            (inner_back+ni, inner_back+i, inner_front+i, inner_front+ni),
        ])
    faces.extend([
        (inner_back, outer_back, outer_front, inner_front),
        (inner_back+segments, inner_front+segments, outer_front+segments, outer_back+segments),
    ])
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    bevel = o.modifiers.new("Rolled visor edge", "BEVEL")
    bevel.width = 0.003
    bevel.segments = 2
    smooth_bevel(o, bevel)
    return parent_to(o, root)


def led_array(label, center, radius, active, lit_color, dark_color, root):
    dot_mat = material(
        label + " LED elements",
        lit_color if active else dark_color,
        0.0,
        0.28 if active else 0.62,
        emission=lit_color if active else None,
        strength=8.0 if active else 0.0,
    )
    # Concentric rings keep the coarse LED field visibly circular. The previous
    # clipped hexagonal grid passed a radius test, but its asymmetric candidate
    # bounds left a six-sided outer silhouette at this low dot density.
    dot_radius = 0.0068
    ring_spacing = 0.025
    points = [(0.0, 0.0)]
    ring_count = int((radius - dot_radius) // ring_spacing)
    for ring_index in range(1, ring_count + 1):
        ring_radius = ring_index * ring_spacing
        leds_on_ring = 6 * ring_index
        phase = math.pi / leds_on_ring
        for i in range(leds_on_ring):
            angle = math.tau * i / leds_on_ring + phase
            points.append((math.cos(angle) * ring_radius,
                           math.sin(angle) * ring_radius))

    add_led_mesh(label + " coarse LEDs", center, points, dot_radius, 0.0045,
                 dot_mat, root, y_offset=-0.030)


def add_led_mesh(name, center, points, radius, depth, mat, root, y_offset):
    vertices, faces = [], []
    segments = 12
    for px, pz in points:
        base = len(vertices)
        for y in (-depth * 0.5, depth * 0.5):
            vertices.extend((center.x + px + math.cos(math.tau * i / segments) * radius,
                             center.y + y_offset + y,
                             center.z + pz + math.sin(math.tau * i / segments) * radius)
                            for i in range(segments))
        for i in range(segments):
            nxt = (i + 1) % segments
            faces.append((base + i, base + nxt, base + segments + nxt, base + segments + i))
        faces.append(tuple(base + i for i in reversed(range(segments))))
        faces.append(tuple(base + segments + i for i in range(segments)))
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return parent_to(obj, root)


def arrow_points(direction):
    # Continuous centre stroke plus one-dot-wide diagonals, matching the clean
    # arrow pattern used by modern LED signal units.
    step = 0.025
    right = {(i * step, 0.0) for i in range(-4, 5)}
    for i in range(1, 4):
        right.add(((4 - i) * step, i * step))
        right.add(((4 - i) * step, -i * step))

    if direction == "right":
        points = right
    elif direction == "left":
        points = {(-x, z) for x, z in right}
    else:
        points = {(-z, x) for x, z in right}
    return sorted(points)


def build_arrow_blocks(root, block_mode, active_arrows, housing, housing_dark, rubber,
                       horizontal_extension=0.0):
    if block_mode == "none":
        return
    directions = ("right",) if block_mode == "right" else ("left", "up", "right")
    offsets = {"left": -0.305, "up": 0.0, "right": 0.305}
    arrow_z = 4.92
    cyan = (0.010, 0.62, 0.38)
    dark_cyan = (0.002, 0.014, 0.010)

    for direction in directions:
        center = Vector((HEAD_CENTER.x + horizontal_extension + offsets[direction], 0.0, arrow_z))
        cube(f"{direction} arrow rounded housing", center, (0.178, 0.090, 0.178),
             housing, root, 0.090)
        lens_center = center + Vector((0, -0.116, 0))
        cylinder(f"{direction} arrow white retaining ring", lens_center,
                 0.146, 0.020, housing, root,
                 rotation=(math.radians(90), 0, 0), vertices=96)
        cylinder(f"{direction} arrow bezel", lens_center,
                 0.137, 0.024, rubber, root,
                 rotation=(math.radians(90), 0, 0), vertices=96)
        lens_mat = material(f"{direction} arrow dark lens", dark_cyan, 0.02, 0.34)
        lens = cylinder(f"{direction} arrow lens", lens_center + Vector((0, -0.016, 0)),
                        0.125, 0.016, lens_mat, root,
                        rotation=(math.radians(90), 0, 0), vertices=128)
        bevel = lens.modifiers.new("Convex arrow lens edge", "BEVEL")
        bevel.width = 0.012
        bevel.segments = 5
        active = direction in active_arrows
        dot_mat = material(
            f"{direction} arrow LED elements",
            cyan if active else dark_cyan, 0.0, 0.28 if active else 0.65,
            emission=cyan if active else None, strength=8.0 if active else 0.0,
        )
        for x, z in arrow_points(direction):
            cylinder(f"{direction} arrow LED", (lens_center.x + x, lens_center.y - 0.030,
                                                 lens_center.z + z),
                     0.0070, 0.0045, dot_mat, root,
                     rotation=(math.radians(90), 0, 0), vertices=12)
        visor(f"{direction} arrow visor", lens_center, 0.139, 0.145, housing, root)
        # Twin rear brackets overlap both housings, making the block physically
        # continuous with the main signal when viewed from behind.
        for dx in (-0.070, 0.070):
            cube(f"{direction} arrow continuous rear bracket",
                 (center.x + dx, 0.115, 5.135), (0.020, 0.025, 0.060),
                 housing_dark, root, 0.005)


def build_intersection_sign(root, japanese_name, roman_name, bolt_mat,
                            horizontal_extension=0.0):
    # An unnamed intersection has no board at all—not a blank white plate.
    if not japanese_name.strip() and not roman_name.strip():
        return
    blue = material("Intersection sign blue", (0.015, 0.16, 0.43), 0.0, 0.68)
    sign_white = material("Intersection sign white", (0.84, 0.86, 0.83), 0.08, 0.58)
    sign_center = Vector((0.90 + horizontal_extension, 0.015, 5.35))
    half_width = 0.448
    half_height = 0.165
    cube("Intersection name white plate", sign_center,
         (half_width, 0.018, half_height), sign_white, root, 0.025)

    # Thin inset blue rule, leaving a visible white outer margin.
    face_y = sign_center.y - 0.020
    inset_x = half_width - 0.035
    inset_z = half_height - 0.030
    line = 0.006
    cube("Intersection sign blue upper rule", (sign_center.x, face_y, sign_center.z + inset_z),
         (inset_x, 0.002, line), blue, root, 0.002)
    cube("Intersection sign blue lower rule", (sign_center.x, face_y, sign_center.z - inset_z),
         (inset_x, 0.002, line), blue, root, 0.002)
    for dx in (-inset_x, inset_x):
        cube("Intersection sign blue side rule", (sign_center.x + dx, face_y, sign_center.z),
             (line, 0.002, inset_z), blue, root, 0.002)

    text_y = face_y - 0.004
    # Preserve the user-supplied name verbatim, including explicit spacing.
    text_object("Intersection Japanese name", japanese_name,
                (sign_center.x, text_y, sign_center.z + 0.040),
                0.270, blue, root, max_width=0.77, font_weight=5)
    text_object("Intersection romanized name", roman_name,
                (sign_center.x, text_y, sign_center.z - 0.090),
                0.1125, blue, root, max_width=0.75, font_weight=7)

    # The board sits directly in front of both horizontal pipes. Four shallow
    # rear clamps connect it without any dangling hanger rods.
    for x in (0.58 + horizontal_extension, 1.22 + horizontal_extension):
        for z in (5.29, 5.48):
            cube("Intersection sign direct rear clamp", (x, 0.085, z),
                 (0.026, 0.050, 0.032), bolt_mat, root, 0.007)
            cylinder("Intersection sign clamp bolt", (x, 0.142, z),
                     0.010, 0.016, bolt_mat, root,
                     rotation=(math.radians(90), 0, 0), vertices=6)


def build_signal_head(root, active_light="green", exterior_color="white",
                      horizontal_extension=0.0):
    housing, housing_dark, bolt_mat = exterior_materials(exterior_color)
    rubber = material("Lens sealing rubber", (0.012, 0.015, 0.014), 0.0, 0.78)

    # 250 mm three-aspect low-profile unit, slightly larger than the lenses.
    head_center = HEAD_CENTER + Vector((horizontal_extension, 0, 0))
    cube("Vehicle signal rounded housing", head_center, (0.485, 0.090, 0.180),
         housing, root, 0.178)

    aspects = [
        ("Green blue aspect", -0.305, (0.003, 0.012, 0.009), (0.015, 0.72, 0.38), "green"),
        ("Amber aspect", 0.0, (0.014, 0.010, 0.003), (1.0, 0.48, 0.015), "yellow"),
        ("Red aspect", 0.305, (0.014, 0.003, 0.002), (1.0, 0.035, 0.018), "red"),
    ]
    for label, dx, dark_color, lit_color, key in aspects:
        center = head_center + Vector((dx, -0.116, 0))
        cylinder(label + " white retaining ring", center, 0.146, 0.020, housing, root,
                 rotation=(math.radians(90), 0, 0), vertices=96)
        cylinder(label + " bezel", center, 0.137, 0.024, rubber, root,
                 rotation=(math.radians(90), 0, 0), vertices=96)
        lit = key == active_light
        lens_mat = material(label + " dark lens", dark_color, 0.02, 0.30)
        lens = cylinder(label + " 250mm lens", center + Vector((0, -0.016, 0)),
                        0.125, 0.016, lens_mat, root,
                        rotation=(math.radians(90), 0, 0), vertices=128)
        bevel = lens.modifiers.new("Convex lens edge", "BEVEL")
        bevel.width = 0.012
        bevel.segments = 5
        led_array(label, center, 0.108, lit, lit_color, dark_color, root)
        # The sheet-metal hood is painted as part of the exterior, rather than
        # being black trim. This also keeps brown units consistently brown.
        visor(label + " visor", center, 0.139, 0.145, housing, root)

    # Rear access door, hinge, latches, maker plate and perimeter seam.
    rear_y = head_center.y + 0.097
    cube("Rear access door", (head_center.x, rear_y, head_center.z),
         (0.445, 0.009, 0.145), housing, root, 0.022)
    cube("Rear door hinge", (head_center.x - 0.44, rear_y + 0.012, head_center.z),
         (0.012, 0.012, 0.092), bolt_mat, root, 0.004)
    for z in (head_center.z - 0.080, head_center.z + 0.080):
        cylinder("Rear door latch", (head_center.x + 0.42, rear_y + 0.018, z),
                 0.012, 0.010, bolt_mat, root,
                 rotation=(math.radians(90), 0, 0), vertices=6)
    cube("Manufacturer plate", (head_center.x, rear_y + 0.020, head_center.z - 0.105),
         (0.080, 0.003, 0.025), bolt_mat, root, 0.003)
    return housing, housing_dark, rubber, bolt_mat


def build_support(root, housing, bolt_mat, exterior_color="white", horizontal_extension=0.0):
    if exterior_color == "brown":
        support = housing
        pole = housing
    else:
        support = material("Matte galvanized support pipes", (0.62, 0.65, 0.64),
                           0.42, 0.56)
        pole = concrete_material()
    pole_radius = 0.082
    cylinder("Signal support pole", (0, 0.16, POLE_HEIGHT / 2), pole_radius,
             POLE_HEIGHT, pole, root, vertices=64)
    # Two slim pipes like common side-pole Japanese installations: a straight
    # upper tube and a bent lower brace, both terminating behind the housing.
    pipe("Upper slim signal support",
         [(0.02, 0.16, 5.48), (0.55, 0.15, 5.48),
          (1.35, 0.13, 5.48), (2.42 + horizontal_extension, 0.13, 5.48)],
         0.026, support, root)
    pipe("Lower bent signal brace",
         [(0.02, 0.16, 5.05), (0.14, 0.16, 5.23),
          (0.62, 0.15, 5.29), (1.35, 0.13, 5.29),
          (2.42 + horizontal_extension, 0.13, 5.29)],
         0.024, support, root)
    for x in (1.75 + horizontal_extension, 2.35 + horizontal_extension):
        for z in (5.29, 5.48):
            cube("Signal rear mounting cleat", (x, 0.115, z),
                 (0.038, 0.030, 0.050), support, root, 0.009)
            cylinder("Signal bracket bolt", (x, 0.148, z),
                     0.013, 0.020, bolt_mat, root,
                     rotation=(math.radians(90), 0, 0), vertices=6)
    cylinder("Pole top cap", (0, 0.16, POLE_HEIGHT + 0.012), pole_radius + 0.004,
             0.024, support, root, vertices=64)

    # Field wiring: rear entry, service loop, arm run and a junction box on pole.
    cable = material("Black outdoor signal cable", (0.008, 0.009, 0.008), 0.0, 0.76)
    pipe("Signal head service loop",
         [(2.20 + horizontal_extension, 0.16, 5.20),
          (2.20 + horizontal_extension, 0.22, 5.13),
          (2.10 + horizontal_extension, 0.24, 5.10),
          (1.99 + horizontal_extension, 0.21, 5.15)],
         0.009, cable, root)
    pipe("Signal power cable along brace",
         [(1.99 + horizontal_extension, 0.21, 5.15),
          (1.42 + horizontal_extension, 0.21, 5.18), (0.72, 0.21, 5.18),
          (0.18, 0.22, 5.02), (0.10, 0.12, 4.68), (0.08, 0.05, 4.58)],
         0.012, cable, root)
    pipe("Upper signal span cable",
         [(0.0, 0.18, 5.67), (0.55, 0.18, 5.61),
          (1.25, 0.17, 5.56), (1.72 + horizontal_extension, 0.16, 5.53)],
         0.006, cable, root)
    cube("Pole cable junction box", (0.0, -0.005, 4.58),
         (0.085, 0.045, 0.145), housing, root, 0.018)
    for z in (4.39, 4.77):
        bpy.ops.mesh.primitive_torus_add(major_radius=pole_radius + 0.006,
                                        minor_radius=0.006,
                                        major_segments=48, minor_segments=8,
                                        location=(0, 0.16, z))
        strap = bpy.context.object
        strap.name = "Pole cable fixing band"
        strap.data.materials.append(bolt_mat)
        parent_to(strap, root)


def create_traffic_signal(name="Traffic Signal", location=(0, 0, 0), rotation_degrees=0,
                          main_light="red", arrow_blocks="none", active_arrows=(),
                          exterior_color="white", intersection_name="",
                          intersection_roman="", include_support=True,
                          horizontal_extension=1.5, support_side="left"):
    """Build one editable signal directly in the current .blend scene."""
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    head_root = bpy.data.objects.new(name + " Head Assembly", None)
    support_root = bpy.data.objects.new(name + " Support Assembly", None)
    plate_root = bpy.data.objects.new(name + " Name Plate Assembly", None)
    for group in (head_root, support_root, plate_root):
        bpy.context.collection.objects.link(group)
        group.parent = root
    housing, housing_dark, rubber, bolts = build_signal_head(
        head_root, active_light=main_light, exterior_color=exterior_color,
        horizontal_extension=horizontal_extension,
    )
    build_arrow_blocks(head_root, arrow_blocks, set(active_arrows), housing, housing_dark, rubber,
                       horizontal_extension)
    if include_support:
        build_support(support_root, housing, bolts, exterior_color, horizontal_extension)
    build_intersection_sign(plate_root, intersection_name, intersection_roman, bolts,
                            horizontal_extension)
    if support_side == "right":
        head_center_x = HEAD_CENTER.x + horizontal_extension
        plate_center_x = 0.90 + horizontal_extension
        head_root.location.x = -2.0 * head_center_x
        support_root.scale.x = -1.0
        plate_root.location.x = -2.0 * plate_center_x
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["support_side"] = support_side
    return root


def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


if not EMBEDDED_BUILD:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)

    asset_collection = bpy.data.collections.new("Traffic Signal Asset")
    bpy.context.scene.collection.children.link(asset_collection)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[asset_collection.name]
    root = create_traffic_signal(
        "Traffic Signal Asset Root", main_light=BUILD_OPTIONS.main_light,
        arrow_blocks=BUILD_OPTIONS.arrow_blocks, active_arrows=BUILD_OPTIONS.active_arrows,
        exterior_color=BUILD_OPTIONS.exterior_color,
        intersection_name=BUILD_OPTIONS.intersection_name,
        intersection_roman=BUILD_OPTIONS.intersection_roman,
        horizontal_extension=BUILD_OPTIONS.horizontal_extension,
        support_side=BUILD_OPTIONS.support_side,
    )

    # Preview environment is separate from the reusable asset collection.
    preview = bpy.data.collections.new("Preview Environment")
    bpy.context.scene.collection.children.link(preview)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[preview.name]
    ground_mat = material("Preview asphalt", (0.045, 0.050, 0.052), 0.0, 0.88)
    cube("Preview ground", (0.8, 0.7, -0.05), (3.4, 2.8, 0.05), ground_mat, root=None, bevel=0.0).parent = None

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 64
    scene.cycles.samples = 160
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 1000
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
    area_data.energy = 420
    area_data.shape = "DISK"
    area_data.size = 5.0
    area = bpy.data.objects.new("Front fill", area_data)
    preview.objects.link(area)
    area.location = (2.5, -5.5, 7.5)
    look_at(area, HEAD_CENTER)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    preview.objects.link(camera)
    camera.location = (7.3, -12.5, 5.9)
    camera_data.lens = 62
    look_at(camera, (0.75, 0.0, 3.35))
    scene.camera = camera

    color_suffix = "" if BUILD_OPTIONS.exterior_color == "white" else "_brown"
    arrow_suffix = {"none": "_no_arrows", "right": "", "all": "_arrows_all"}[BUILD_OPTIONS.arrow_blocks]
    name_suffix = ("_no_name_plate" if not BUILD_OPTIONS.intersection_name.strip()
                   and not BUILD_OPTIONS.intersection_roman.strip() else "")
    variant_suffix = color_suffix + arrow_suffix + name_suffix
    scene.render.filepath = str(
        ASSET_ROOT / f"renders/traffic_signal_vehicle_horizontal{variant_suffix}.png"
    )
    if not BUILD_OPTIONS.skip_render and not EMBEDDED_BUILD:
        bpy.ops.render.render(write_still=True)

    # A second preview makes the hood, lens and housing construction easy to inspect.
    camera.location = (4.25, -7.2, 5.85)
    camera_data.lens = 78
    look_at(camera, HEAD_CENTER)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 720
    scene.render.filepath = str(
        ASSET_ROOT / f"renders/traffic_signal_vehicle_horizontal{variant_suffix}_detail.png"
    )
    if not BUILD_OPTIONS.skip_render and not EMBEDDED_BUILD:
        bpy.ops.render.render(write_still=True)

    camera.location = (4.2, 6.3, 5.9)
    camera_data.lens = 72
    look_at(camera, HEAD_CENTER)
    scene.render.filepath = str(
        ASSET_ROOT / f"renders/traffic_signal_vehicle_horizontal{variant_suffix}_rear.png"
    )
    if not BUILD_OPTIONS.skip_render and not EMBEDDED_BUILD:
        bpy.ops.render.render(write_still=True)
    if not EMBEDDED_BUILD:
        bpy.ops.wm.save_as_mainfile(filepath=str(
            ASSET_ROOT / f"blend/traffic_signal_vehicle_horizontal{variant_suffix}.blend"
        ))
