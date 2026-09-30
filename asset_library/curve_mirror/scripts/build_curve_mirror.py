import bpy
import argparse
import math
import random
import sys
from pathlib import Path
from mathutils import Matrix, Vector

random.seed(12)


def parse_build_options():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mirror-count", type=int, choices=(1, 2), default=1)
    parser.add_argument("--spread-degrees", type=float, default=24.0)
    parser.add_argument("--pole-length", type=float, default=2.5,
                        help="Visible pole length above ground in metres")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


BUILD_OPTIONS = parse_build_options()


def curve_mirror_layout(pole_location, pole_length=2.5, mirror_count=1, spread_degrees=24.0):
    """Return reusable pole-relative placement data, independent of any background."""
    if mirror_count not in (1, 2):
        raise ValueError("mirror_count must be 1 or 2")
    pole_x, pole_y = pole_location
    mirror_z = pole_length - 0.29
    sign_z = pole_length - 1.17
    if mirror_count == 1:
        centers = [(pole_x, pole_y - 0.18, mirror_z)]
        yaws = [0.0]
    else:
        centers = [
            (pole_x - 0.34, pole_y - 0.12, mirror_z),
            (pole_x + 0.34, pole_y - 0.12, mirror_z),
        ]
        yaws = [-spread_degrees * 0.5, spread_degrees * 0.5]
    return {"centers": centers, "yaws": yaws, "sign_z": sign_z, "pole_top": pole_length}


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def mat(name, color, metallic=0.0, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = roughness
    return m


def add_surface_variation(material, scale, strength, detail=4.0):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    p = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = 0.7
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.035
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], p.inputs["Normal"])


def cube(name, loc, scale, material, bevel=0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    if bevel:
        b = o.modifiers.new("Worn edges", "BEVEL")
        b.width = bevel
        b.segments = 2
    return o


def cylinder(name, loc, radius, depth, material, rotation=(0, 0, 0), vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    return o


def horizontal_beam(name, start, end, width, height, material):
    start, end = Vector(start), Vector(end)
    delta = end - start
    midpoint = (start + end) * 0.5
    o = cube(name, midpoint, (delta.length/2, width/2, height/2), material, min(width, height)*0.18)
    o.rotation_euler[2] = math.atan2(delta.y, delta.x)
    return o


def pipe(name, points, radius, material):
    c = bpy.data.curves.new(name, "CURVE")
    c.dimensions = "3D"
    c.resolution_u = 10
    c.bevel_depth = radius
    c.bevel_resolution = 5
    s = c.splines.new("BEZIER")
    s.bezier_points.add(len(points) - 1)
    for b, p in zip(s.bezier_points, points):
        b.co = p
        b.handle_left_type = "AUTO"
        b.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, c)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    return o


def convex_disc(name, center, aperture, sphere_radius, material, rings=42, segments=160):
    # True spherical cap; centre projects toward the camera (-Y).
    verts = []
    faces = []
    cx, edge_y, cz = center
    for j in range(1, rings + 1):
        r = aperture * j / rings
        sag = sphere_radius - math.sqrt(sphere_radius * sphere_radius - r * r)
        y = edge_y - (sphere_radius - math.sqrt(sphere_radius * sphere_radius - aperture * aperture)) + sag
        for i in range(segments):
            a = 2 * math.pi * i / segments
            verts.append((cx + r * math.cos(a), y, cz + r * math.sin(a)))
    # Close the tiny central ring with one smooth n-gon. This avoids the radial
    # triangle fan that created a visible pinched dot in the mirror centre.
    faces.append(tuple(reversed(range(segments))))
    for j in range(1, rings):
        a0 = (j - 1) * segments
        b0 = j * segments
        for i in range(segments):
            ni = (i + 1) % segments
            faces.append((a0 + i, b0 + i, b0 + ni, a0 + ni))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    for p in mesh.polygons:
        p.use_smooth = True
    return o


def hood_mesh(center, radius, material):
    # A real road-mirror hood is a thin visor growing forward from the rear shell.
    # Its broad surfaces are almost parallel to the viewing axis; from the front it
    # reads as a narrow lip, not as a horseshoe-shaped plate covering the mirror.
    cx, y, cz = center
    verts, faces = [], []
    angles = [math.radians(3 + i * 174 / 72) for i in range(73)]
    # The visor is deepest at the crown and gently fades toward both ends.
    for radial_offset in (-0.0024, 0.0096):
        for front_side in (False, True):
            for a in angles:
                crown = max(0.0, math.sin(a)) ** 0.55
                yy = y + 0.0144 if not front_side else y - (0.0144 + 0.048 * crown)
                rr = radius + radial_offset
                verts.append((cx + rr * math.cos(a), yy, cz + rr * math.sin(a)))
    n = len(angles)
    # Back/front narrow edges plus the inner underside and outer weather surface.
    for layer in (0, 2):
        for i in range(n - 1):
            faces.append((layer*n+i, layer*n+i+1, (layer+1)*n+i+1, (layer+1)*n+i))
    for radial in (0, 1):
        a0 = radial*n
        b0 = (2+radial)*n
        for i in range(n - 1):
            faces.append((a0+i, b0+i, b0+i+1, a0+i+1))
    mesh = bpy.data.meshes.new("Rain hood mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new("Pressed steel rain hood", mesh)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    bevel = o.modifiers.new("Rolled lip", "BEVEL")
    bevel.width = 0.0024
    bevel.segments = 3
    return o


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 128
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 10
scene.cycles.diffuse_bounces = 4
scene.cycles.glossy_bounces = 8
scene.cycles.transparent_max_bounces = 8
scene.render.image_settings.color_mode = "RGB"
scene.render.resolution_x = 768
scene.render.resolution_y = 1152
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "8"
scene.view_settings.look = "AgX - Medium Low Contrast"
scene.camera = None

# Overcast world with a restrained sun, like the reference photo.
world = scene.world or bpy.data.worlds.new("Overcast world")
scene.world = world
world.use_nodes = True
nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()
out = nodes.new("ShaderNodeOutputWorld")
bg = nodes.new("ShaderNodeBackground")
sky = nodes.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(13)
sky.sun_rotation = math.radians(220)
sky.air_density = 1.4
sky.dust_density = 3.2
sky.ozone_density = 1.2
bg.inputs["Strength"].default_value = 0.38
links.new(sky.outputs["Color"], bg.inputs["Color"])
links.new(bg.outputs["Background"], out.inputs["Surface"])

# Materials: subdued, slightly aged values.
orange = mat("Faded orange paint", (0.42, 0.105, 0.025), 0.18, 0.42)
hoodmat = mat("Brown orange weathered hood", (0.22, 0.055, 0.025), 0.5, 0.34)
rubber = mat("Old black gasket", (0.008, 0.009, 0.008), 0.0, 0.7)
steel = mat("Galvanized steel", (0.48, 0.50, 0.49), 0.82, 0.3)
asphalt = mat("Aged asphalt", (0.045, 0.052, 0.056), 0.0, 0.84)
concrete = mat("Weathered concrete", (0.37, 0.38, 0.35), 0.0, 0.9)
grass = mat("Dry roadside grass", (0.19, 0.20, 0.10), 0.0, 0.95)
white = mat("Aged white paint", (0.67, 0.68, 0.63), 0.05, 0.68)
black = mat("Printed black", (0.0, 0.0, 0.0), 0.0, 0.65)
red = mat("Printed safety red", (0.38, 0.002, 0.001), 0.0, 0.58)
wall = mat("Corrugated wall", (0.26, 0.28, 0.27), 0.25, 0.65)
roofmat = mat("Dark ceramic roof", (0.035, 0.04, 0.045), 0.28, 0.52)
wood = mat("Distant wood", (0.12, 0.075, 0.04), 0.0, 0.8)
add_surface_variation(orange, 28.0, 0.13, 5.0)
add_surface_variation(hoodmat, 17.0, 0.18, 5.0)
add_surface_variation(asphalt, 8.0, 0.32, 7.0)
add_surface_variation(concrete, 12.0, 0.22, 5.0)
add_surface_variation(wall, 22.0, 0.18, 4.0)

# Broad environment, with detail both visible and behind the camera for reflection.
cube("Road", (0, 0, -0.14), (12, 14, 0.14), asphalt)
cube("Sidewalk", (0, 4.25, 0.0), (12, 1.05, 0.13), concrete)
cube("Verge", (0, 6.2, -0.01), (12, 1.0, 0.11), grass)
for x in (-4.0, 4.0):
    cube("Faded edge marking", (x, -3.0, 0.015), (0.045, 9.0, 0.012), white)

# Visible old Japanese-style house.
cube("Old house", (-4.4, 8.5, 1.45), (3.1, 1.8, 1.45), wall)
roof = cube("Tiled roof", (-4.4, 8.45, 3.05), (3.55, 2.15, 0.18), roofmat, 0.04)
roof.rotation_euler[1] = math.radians(-8)
for x in [-6.7, -5.8, -4.9, -4.0, -3.1, -2.2]:
    cylinder("Roof tile ridge", (x, 6.85, 3.22), 0.045, 4.1, roofmat, (math.radians(90), 0, 0), 16)

# Objects positioned in front of the mirror become coherent convex reflections.
cube("Reflected house", (-4.6, -10.5, 1.7), (3.2, 1.7, 1.7), wall)
rroof = cube("Reflected roof", (-4.6, -10.5, 3.52), (3.7, 2.1, 0.2), roofmat, 0.06)
rroof.rotation_euler[1] = math.radians(10)
cube("Reflected road crossing", (0.0, -7.4, 0.025), (8.0, 0.15, 0.018), white)

# Roadside fence, repeated irregularly.
for y in (3.36, -5.8):
    for x in range(-10, 11, 2):
        cylinder("Fence upright", (x + random.uniform(-0.02, 0.02), y, 0.63), 0.037, 1.25, steel, vertices=20)
    for z in (0.33, 0.88):
        cylinder("Fence rail", (0, y, z), 0.036, 20.0, steel, (0, math.radians(90), 0), 24)

# Bare tree silhouettes and utility poles add non-uniform reflections/detail.
for base_x, base_y, height in [(-8, 7.0, 5.0), (6.5, 7.5, 4.5), (7, -9, 6.0), (-8, -8, 5.5)]:
    cylinder("Tree trunk", (base_x, base_y, height/2), 0.08, height, wood, vertices=12)
    for k in range(7):
        a = (k / 7) * math.pi * 2
        pipe("Bare branch", [(base_x, base_y, height*0.65),
             (base_x + math.cos(a)*0.7, base_y + math.sin(a)*0.7, height*0.84),
             (base_x + math.cos(a)*1.25, base_y + math.sin(a)*1.25, height)], 0.018, wood)

# Standard Japanese roadside installation: straight 76.3 mm OD steel pole.
# A 4,000 mm pole is normally embedded about 900 mm, leaving roughly 3.1 m
# above grade. The short exposed extension above the mirror supports its clamp.
pole_x = 0.48
pole_y = 4.72
pole_length = BUILD_OPTIONS.pole_length
if pole_length <= 1.5:
    raise ValueError("--pole-length must be greater than 1.5 metres")
pole_top = pole_length
asset_layout = curve_mirror_layout(
    (pole_x, pole_y), pole_length, BUILD_OPTIONS.mirror_count, BUILD_OPTIONS.spread_degrees
)
cylinder("Extra slim straight support pole", (pole_x, pole_y, pole_length/2), 0.0224, pole_length, orange, vertices=48)

# Mirror assembly. A single mirror sits directly in front of the pole on a short
# perpendicular stub. A double installation uses symmetric left/right branches.
mc = asset_layout["centers"][0]
mirror = mat("Real mirror", (0.86, 0.88, 0.90), 1.0, 0.012)
mp = next(n for n in mirror.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
mp.inputs["Coat Weight"].default_value = 0.3
mp.inputs["Coat Roughness"].default_value = 0.025
mirror_face = convex_disc("Scaled convex mirror surface", mc, 0.2048, 1.536, mirror)

# Very thin dark gasket only; no orange full-circumference frame.
bpy.ops.mesh.primitive_torus_add(major_radius=0.208, minor_radius=0.0045, major_segments=160, minor_segments=16,
                                location=(mc[0], mc[1]+0.005, mc[2]), rotation=(math.radians(90), 0, 0))
gasket = bpy.context.object
gasket.name = "Thin mirror gasket"
gasket.data.materials.append(rubber)

# Shallow rear housing, hidden behind the reflective cap.
back_shell = cylinder("Galvanized pressed backing shell", (mc[0], mc[1]+0.020, mc[2]), 0.211, 0.0105, steel,
                      (math.radians(90), 0, 0), 128)
hood = hood_mesh((mc[0], mc[1]-0.003, mc[2]), 0.213, hoodmat)

# Orange rolled perimeter belongs to the shell edge, not to the mirror face.
bpy.ops.mesh.primitive_torus_add(major_radius=0.212, minor_radius=0.0042, major_segments=160, minor_segments=14,
                                location=(mc[0], mc[1]+0.026, mc[2]), rotation=(math.radians(90), 0, 0))
rear_edge_flange = bpy.context.object
rear_edge_flange.name = "Thin orange rear perimeter flange"
rear_edge_flange.data.materials.append(hoodmat)

# Pressed reinforcement ribs on the galvanized rear shell, matching the
# characteristic star-like structure visible on real 800 mm road mirrors.
rib_mat = mat("Pressed galvanized rear ribs", (0.38, 0.42, 0.43), 0.86, 0.24)
# Assign after material creation because the shell is built immediately above.
back_shell.data.materials.clear()
back_shell.data.materials.append(rib_mat)
for i in range(6):
    angle = math.radians(i * 60 + 8)
    length = 0.130
    mid_r = 0.102
    rib = cube("Pressed radial reinforcement rib", (mc[0] + math.cos(angle)*mid_r,
               mc[1] + 0.054, mc[2] + math.sin(angle)*mid_r),
               (length/2, 0.0026, 0.017), rib_mat, 0.0038)
    rib.rotation_euler[1] = -angle

# Central embossed boss and four real-looking fixing bolts.
cylinder("Rear central boss", (mc[0], mc[1]+0.036, mc[2]), 0.047, 0.0065, rib_mat,
         (math.radians(90), 0, 0), 64)
for dx, dz in ((-0.028, -0.028), (-0.028, 0.028), (0.028, -0.028), (0.028, 0.028)):
    cylinder("Hex mounting bolt", (mc[0]+dx, mc[1]+0.075, mc[2]+dz), 0.010, 0.010, steel,
             (math.radians(90), 0, 0), 6)

# Mount branches are generated below after the one/two-mirror body transforms.
cube("Compact vertical pole saddle plate", (pole_x-0.014, pole_y-0.020, mc[2]),
     (0.030, 0.018, 0.090), steel, 0.007)

# Two saddle clamps wrap around the straight pole; paired ears and bolts lock
# the mirror arm to the pole without the impossible direct intersection used before.
for z in (mc[2]-0.06, mc[2]+0.06):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0255, minor_radius=0.0055, major_segments=40, minor_segments=10,
                                    location=(pole_x, pole_y, z))
    bpy.context.object.data.materials.append(steel)
    cube("Clamp saddle ear", (pole_x-0.055, pole_y-0.010, z), (0.038, 0.018, 0.026), steel, 0.006)
    cylinder("Clamp bolt", (pole_x-0.080, pole_y-0.034, z), 0.008, 0.040, steel,
             (math.radians(90), 0, 0), 6)

tilted_prefixes = (
    "Scaled convex mirror surface", "Thin mirror gasket",
    "Galvanized pressed backing shell", "Pressed steel rain hood",
    "Thin orange rear perimeter flange", "Pressed radial reinforcement rib",
    "Rear central boss", "Hex mounting bolt",
)


def transform_mirror_body(objects, center, downward_degrees, yaw_degrees):
    center = Vector(center)
    transform = (Matrix.Translation(center) @
                 Matrix.Rotation(math.radians(yaw_degrees), 4, "Z") @
                 Matrix.Rotation(math.radians(downward_degrees), 4, "X") @
                 Matrix.Translation(-center))
    for obj in objects:
        obj.matrix_world = transform @ obj.matrix_world


def duplicate_mirror_body(source_objects, source_center, target_center, yaw_delta):
    source_center, target_center = Vector(source_center), Vector(target_center)
    transform = (Matrix.Translation(target_center) @
                 Matrix.Rotation(math.radians(yaw_delta), 4, "Z") @
                 Matrix.Translation(-source_center))
    duplicates = []
    for source in source_objects:
        copy = source.copy()
        if source.data:
            copy.data = source.data.copy()
        copy.name = source.name + " Right"
        bpy.context.collection.objects.link(copy)
        copy.matrix_world = transform @ source.matrix_world
        duplicates.append(copy)
    return duplicates


def build_mount_branch(center, label, compact=False):
    center = Vector(center)
    if compact:
        # Short stub normal to the back of a single mirror, like sample_2.
        plate_center = (center.x, center.y + 0.045, center.z)
        cube(f"{label} angle plate", plate_center, (0.055, 0.008, 0.050), steel, 0.005)
        horizontal_beam(f"{label} short perpendicular stub",
                        (center.x, center.y + 0.055, center.z),
                        (pole_x, pole_y - 0.025, center.z), 0.042, 0.045, steel)
    else:
        toward = 1.0 if center.x < pole_x else -1.0
        plate_x = center.x + toward * 0.055
        cube(f"{label} angle plate", (plate_x, center.y + 0.055, center.z),
             (0.050, 0.008, 0.050), steel, 0.005)
        horizontal_beam(f"{label} symmetric branch",
                        (center.x + toward*0.070, center.y + 0.065, center.z),
                        (pole_x - toward*0.010, pole_y - 0.025, center.z),
                        0.042, 0.045, steel)
        horizontal_beam(f"{label} lower gusset",
                        (center.x + toward*0.085, center.y + 0.070, center.z-0.045),
                        (pole_x - toward*0.012, pole_y - 0.030, center.z-0.095),
                        0.024, 0.026, steel)


left_body = [obj for obj in bpy.context.scene.objects if obj.name.startswith(tilted_prefixes)]
if BUILD_OPTIONS.mirror_count == 1:
    transform_mirror_body(left_body, mc, 10.0, 0.0)
    build_mount_branch(mc, "Single mirror", compact=True)
else:
    transform_mirror_body(left_body, mc, 10.0, asset_layout["yaws"][0])
    right_mc = asset_layout["centers"][1]
    duplicate_mirror_body(left_body, mc, right_mc, BUILD_OPTIONS.spread_degrees)
    build_mount_branch(mc, "Left mirror", compact=False)
    build_mount_branch(right_mc, "Right mirror", compact=False)

# Warning sign with recognisable Japanese text using a system font if available.
sign_z = asset_layout["sign_z"]
sign = cube("Warning board 430x120", (pole_x, 4.675, sign_z), (0.06, 0.0125, 0.215), white, 0.012)
def text_obj(body, loc, size, material):
    c = bpy.data.curves.new(body, "FONT")
    c.body = body
    c.align_x = "CENTER"
    c.align_y = "CENTER"
    c.size = size
    c.extrude = 0.0
    from asset_library.shared.fonts import japanese_font
    c.font = japanese_font()
    o = bpy.data.objects.new(body, c)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (math.radians(90), 0, 0)
    o.data.materials.append(material)
    return o
text_obj("注", (pole_x, 4.6615, sign_z+0.015), 0.112, black)
text_obj("意", (pole_x, 4.6615, sign_z-0.115), 0.112, black)

# Red upward arrow from the reference: compact triangular head with a short,
# broad rectangular stem, centred in the upper white margin.
arrow_verts = [
    (pole_x-0.040, 4.6615, sign_z+0.120), (pole_x, 4.6615, sign_z+0.185), (pole_x+0.040, 4.6615, sign_z+0.120),
    (pole_x+0.017, 4.6615, sign_z+0.120), (pole_x+0.017, 4.6615, sign_z+0.085),
    (pole_x-0.017, 4.6615, sign_z+0.085), (pole_x-0.017, 4.6615, sign_z+0.120),
]
arrow_mesh = bpy.data.meshes.new("Caution arrow mesh")
arrow_mesh.from_pydata(arrow_verts, [], [(0, 1, 2, 3, 4, 5, 6)])
arrow_mesh.update()
arrow = bpy.data.objects.new("Red upward caution arrow", arrow_mesh)
bpy.context.collection.objects.link(arrow)
arrow.data.materials.append(red)

# Small paint wear spots on lower pole.
rust = mat("Rust spots", (0.15, 0.035, 0.012), 0.15, 0.78)
for i in range(16):
    z = random.uniform(0.25, pole_top-0.12)
    a = random.uniform(0, math.pi*2)
    cylinder("Paint chip", (pole_x + 0.023*math.cos(a), pole_y + 0.023*math.sin(a), z),
             random.uniform(0.005, 0.012), 0.004, rust, (math.pi/2, 0, a), 8)

# Soft overcast key and faint warm sun.
area_data = bpy.data.lights.new("Large cloudy sky", "AREA")
area_data.energy = 390
area_data.shape = "DISK"
area_data.size = 9
area_data.color = (0.67, 0.76, 1.0)
area = bpy.data.objects.new("Large cloudy sky", area_data)
bpy.context.collection.objects.link(area)
area.location = (-4, -1, 12)
look_at(area, mc)
sun_data = bpy.data.lights.new("Weak evening sun", "SUN")
sun_data.energy = 0.32
sun_data.angle = math.radians(12)
sun_data.color = (1.0, 0.65, 0.4)
sun = bpy.data.objects.new("Weak evening sun", sun_data)
bpy.context.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-120))

# Photo-like viewpoint: slight side angle exposes the convexity and hood depth.
cam_data = bpy.data.cameras.new("Camera")
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (3.4, -8.7, 2.25)
cam_data.lens = 72
cam_data.sensor_width = 36
cam_data.dof.use_dof = False
look_at(cam, (0.10, 4.65, 1.72))
scene.camera = cam

asset_root = Path(__file__).resolve().parent.parent
variant = f"{BUILD_OPTIONS.mirror_count}mirror"
if BUILD_OPTIONS.mirror_count == 2:
    variant += f"_spread{BUILD_OPTIONS.spread_degrees:g}"
variant += f"_pole{BUILD_OPTIONS.pole_length:g}m"
blend_path = asset_root / "blend" / f"curve_mirror_{variant}.blend"
render_path = asset_root / "renders" / f"curve_mirror_{variant}.png"
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

# Dedicated rear-detail image for validating the backing shell and hardware.
front_location = cam.location.copy()
front_rotation = cam.rotation_euler.copy()
front_x, front_y = scene.render.resolution_x, scene.render.resolution_y
cam.location = (2.05, 7.15, 3.48)
cam_data.lens = 78
look_at(cam, (0.18, 4.62, 2.88))
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.filepath = str(asset_root / "renders" / f"curve_mirror_{variant}_rear.png")
bpy.ops.render.render(write_still=True)

# Close-up used to validate caution-board typography and spacing.
cam.location = (1.15, 2.55, 2.16)
cam_data.lens = 92
look_at(cam, (pole_x, 4.66, sign_z))
scene.render.resolution_x = 600
scene.render.resolution_y = 900
scene.render.filepath = str(asset_root / "renders" / f"curve_mirror_{variant}_caution.png")
bpy.ops.render.render(write_still=True)

# Leave the editable file in its primary front-view state.
cam.location = front_location
cam.rotation_euler = front_rotation
cam_data.lens = 72
scene.render.resolution_x, scene.render.resolution_y = front_x, front_y
scene.render.filepath = str(render_path)

bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
