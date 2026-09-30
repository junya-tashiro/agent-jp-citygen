import math

import bpy
from mathutils import Vector


ROAD_PAINT_THICKNESS_M = 0.0015
ROAD_PAINT_CENTER_Z_M = ROAD_PAINT_THICKNESS_M * 0.5
ROAD_PAINT_TOP_Z_M = ROAD_PAINT_THICKNESS_M
ROAD_PAINT_BEVEL_M = 0.00025
# Orange regulatory centre lines take visual precedence where their geometry
# meets white lane guidance.  Place the whole orange paint film just above the
# white film, with only a 0.1mm render tolerance between them.
ORANGE_PAINT_CENTER_Z_M = (ROAD_PAINT_CENTER_Z_M
                           + ROAD_PAINT_THICKNESS_M + 0.0001)


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def _surface_relief_group(kind):
    """One world-space height field shared by every material of a surface.

    In particular, asphalt and every road-paint material use the exact same
    ``road`` group, so paint does not look laminated over a different grain.
    """
    name = f"Shared {kind.title()} Surface Relief"
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group.interface.new_socket(name="Height", in_out="OUTPUT", socket_type="NodeSocketFloat")
    nodes, links = group.nodes, group.links
    if kind == "road":
        from asset_library.shared.surfaces import asphalt_shader_group
        output = nodes.new("NodeGroupOutput")
        field = nodes.new("ShaderNodeGroup"); field.node_tree = asphalt_shader_group()
        links.new(field.outputs["Height"], output.inputs["Height"])
        return group
    output = nodes.new("NodeGroupOutput")
    geometry = nodes.new("ShaderNodeNewGeometry")
    fine = nodes.new("ShaderNodeTexNoise")
    coarse = nodes.new("ShaderNodeTexNoise")
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    if kind == "paver":
        fine.inputs["Scale"].default_value = 380.0
        fine.inputs["Detail"].default_value = 4.0
        coarse.inputs["Scale"].default_value = 3.0
        coarse.inputs["Detail"].default_value = 4.0
        mix.inputs[0].default_value = 0.12
    else:  # cast concrete
        fine.inputs["Scale"].default_value = 460.0
        fine.inputs["Detail"].default_value = 5.0
        coarse.inputs["Scale"].default_value = 2.2
        coarse.inputs["Detail"].default_value = 5.0
        mix.inputs[0].default_value = 0.18
    links.new(geometry.outputs["Position"], fine.inputs["Vector"])
    links.new(geometry.outputs["Position"], coarse.inputs["Vector"])
    links.new(fine.outputs["Fac"], mix.inputs[1])
    links.new(coarse.outputs["Fac"], mix.inputs[2])
    links.new(mix.outputs["Color"], output.inputs["Height"])
    return group


def apply_surface_relief(mat, kind, strength=None, distance=None):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    relief = nodes.new("ShaderNodeGroup")
    relief.name = f"Shared {kind} relief"
    relief.node_tree = _surface_relief_group(kind)
    bump = nodes.new("ShaderNodeBump")
    bump.name = f"{kind.title()} surface relief"
    defaults = {
        "road": (0.65, 0.0080),
        "concrete": (0.42, 0.0015),
        "paver": (0.48, 0.0020),
    }
    default_strength, default_distance = defaults[kind]
    bump.inputs["Strength"].default_value = default_strength if strength is None else strength
    bump.inputs["Distance"].default_value = default_distance if distance is None else distance
    links.new(relief.outputs["Height"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return relief


def weathered_material(name, dark, light, roughness=0.8, scale=9.0,
                       relief_kind=None):
    mat = material(name, dark, roughness=roughness)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    noise = nodes.new("ShaderNodeTexNoise")
    position = nodes.new("ShaderNodeNewGeometry")
    links.new(position.outputs["Position"], noise.inputs["Vector"])
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.76
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    from asset_library.shared.surfaces import noise as surface_noise, ramp as surface_ramp
    grain = surface_noise(nodes, links, position.outputs["Position"], 360, 2)
    speckle = surface_ramp(nodes, links, grain, (.52, .49, .44), (1, 1, .98), (.20, .76))
    mineral = nodes.new("ShaderNodeMixRGB")
    mineral.blend_type = "MULTIPLY"
    mineral.inputs[0].default_value = .42
    links.new(ramp.outputs["Color"], mineral.inputs[1])
    links.new(speckle, mineral.inputs[2])
    links.new(mineral.outputs[0], bsdf.inputs["Base Color"])
    surface_roughness = surface_ramp(nodes, links, grain, (max(.35, roughness-.16),)*3, (min(.98, roughness+.06),)*3)
    links.new(surface_roughness, bsdf.inputs["Roughness"])
    if relief_kind is None:
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.16
        bump.inputs["Distance"].default_value = 0.0015
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        apply_surface_relief(mat, relief_kind)
    return mat


def road_marking_material(name, dark, light, worn, roughness=0.74):
    """Thermoplastic road paint with aggregate, wear and glass-bead sparkle.

    The texture uses object-space metres instead of Generated coordinates so
    long strips do not stretch the grain along their full length.  Dark worn
    patches are deliberately subtle: they suggest exposed aggregate without
    turning every marking into heavily damaged paint.
    """
    mat = material(name, light, roughness=roughness)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")

    coordinates = nodes.new("ShaderNodeTexCoord")

    aggregate = nodes.new("ShaderNodeTexNoise")
    aggregate.name = "Paint aggregate"
    aggregate.inputs["Scale"].default_value = 72.0
    aggregate.inputs["Detail"].default_value = 3.5
    aggregate.inputs["Roughness"].default_value = 0.72
    links.new(coordinates.outputs["Object"], aggregate.inputs["Vector"])

    paint_colour = nodes.new("ShaderNodeValToRGB")
    paint_colour.name = "Uneven paint colour"
    paint_colour.color_ramp.elements[0].position = 0.25
    paint_colour.color_ramp.elements[0].color = (*dark, 1.0)
    paint_colour.color_ramp.elements[1].position = 0.78
    paint_colour.color_ramp.elements[1].color = (*light, 1.0)
    links.new(aggregate.outputs["Fac"], paint_colour.inputs["Fac"])

    wear = nodes.new("ShaderNodeTexNoise")
    wear.name = "Tyre and weather wear"
    wear.inputs["Scale"].default_value = 2.8
    wear.inputs["Detail"].default_value = 7.0
    wear.inputs["Roughness"].default_value = 0.82
    wear.inputs["Distortion"].default_value = 0.18
    links.new(coordinates.outputs["Object"], wear.inputs["Vector"])

    wear_threshold = nodes.new("ShaderNodeValToRGB")
    wear_threshold.name = "Sparse worn patches"
    wear_threshold.color_ramp.elements[0].position = 0.57
    wear_threshold.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    wear_threshold.color_ramp.elements[1].position = 0.72
    wear_threshold.color_ramp.elements[1].color = (0.18, 0.18, 0.18, 1.0)
    links.new(wear.outputs["Fac"], wear_threshold.inputs["Fac"])

    worn_mix = nodes.new("ShaderNodeMixRGB")
    worn_mix.name = "Paint worn to road dust"
    worn_mix.blend_type = "MIX"
    worn_mix.inputs[2].default_value = (*worn, 1.0)
    links.new(wear_threshold.outputs["Color"], worn_mix.inputs[0])
    links.new(paint_colour.outputs["Color"], worn_mix.inputs[1])
    links.new(worn_mix.outputs["Color"], bsdf.inputs["Base Color"])

    roughness_ramp = nodes.new("ShaderNodeValToRGB")
    roughness_ramp.name = "Paint roughness variation"
    roughness_ramp.color_ramp.elements[0].color = (0.58, 0.58, 0.58, 1.0)
    roughness_ramp.color_ramp.elements[1].color = (0.86, 0.86, 0.86, 1.0)
    links.new(aggregate.outputs["Fac"], roughness_ramp.inputs["Fac"])
    links.new(roughness_ramp.outputs["Color"], bsdf.inputs["Roughness"])

    apply_surface_relief(mat, "road")

    # Thermoplastic markings contain glass beads.  A sparse Voronoi mask on the
    # clear-coat lobe gives small highlights under grazing or headlamp light.
    beads = nodes.new("ShaderNodeTexVoronoi")
    beads.name = "Retroreflective glass beads"
    beads.distance = "EUCLIDEAN"
    beads.inputs["Scale"].default_value = 190.0
    links.new(coordinates.outputs["Object"], beads.inputs["Vector"])
    bead_mask = nodes.new("ShaderNodeValToRGB")
    bead_mask.name = "Sparse bead mask"
    bead_mask.color_ramp.elements[0].position = 0.025
    bead_mask.color_ramp.elements[0].color = (0.32, 0.32, 0.32, 1.0)
    bead_mask.color_ramp.elements[1].position = 0.065
    bead_mask.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    links.new(beads.outputs["Distance"], bead_mask.inputs["Fac"])
    if "Coat Weight" in bsdf.inputs:
        links.new(bead_mask.outputs["Color"], bsdf.inputs["Coat Weight"])
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = 0.18
    # A centimetre-scale chipped edge field plus smaller aggregate pits,
    # sampled in world metres independently of marking dimensions.
    from asset_library.shared.surfaces import noise, ramp
    position = nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    flakes = noise(nodes, links, position, 38, 3.5)
    pits = noise(nodes, links, position, 120, 2)
    chip_mix = nodes.new("ShaderNodeMixRGB")
    chip_mix.inputs[0].default_value = .28
    links.new(flakes, chip_mix.inputs[1]); links.new(pits, chip_mix.inputs[2])
    coverage = ramp(nodes, links, chip_mix.outputs[0], (0,)*3, (1,)*3, (.405, .475))
    # At road viewing distances, expose the exact underlying asphalt field
    # within the coating surface instead of paying alpha overdraw for every
    # marking and every EEVEE shadow sample.
    from asset_library.shared.surfaces import asphalt_shader_group
    substrate = nodes.new("ShaderNodeGroup"); substrate.node_tree = asphalt_shader_group()
    chip_color = nodes.new("ShaderNodeMixRGB")
    chip_color.name = "Exposed asphalt through chipped paint"
    links.new(coverage, chip_color.inputs[0])
    links.new(substrate.outputs["Color"], chip_color.inputs[1])
    links.new(worn_mix.outputs[0], chip_color.inputs[2])
    links.new(chip_color.outputs[0], bsdf.inputs["Base Color"])
    chip_rough = nodes.new("ShaderNodeMixRGB")
    links.new(coverage, chip_rough.inputs[0])
    links.new(substrate.outputs["Roughness"], chip_rough.inputs[1])
    links.new(roughness_ramp.outputs[0], chip_rough.inputs[2])
    links.new(chip_rough.outputs[0], bsdf.inputs["Roughness"])
    return mat


def cube(name, location, dimensions, mat, bevel=0.0):
    hx, hy, hz = (value * 0.5 for value in dimensions)
    vertices = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.name = name
    obj.location = location
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Soft edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0), vertices=24):
    points = []
    half = depth * 0.5
    for z in (-half, half):
        points.extend((math.cos(math.tau * i / vertices) * radius,
                       math.sin(math.tau * i / vertices) * radius, z)
                      for i in range(vertices))
    faces = [tuple(reversed(range(vertices))), tuple(range(vertices, vertices * 2))]
    for i in range(vertices):
        nxt = (i + 1) % vertices
        faces.append((i, nxt, vertices + nxt, vertices + i))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(points, [], faces)
    for poly in mesh.polygons[2:]:
        poly.use_smooth = True
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def torus(name, location, major_radius, minor_radius, mat):
    major_segments, minor_segments = 40, 10
    vertices = []
    for major in range(major_segments):
        u = math.tau * major / major_segments
        for minor in range(minor_segments):
            v = math.tau * minor / minor_segments
            ring = major_radius + minor_radius * math.cos(v)
            vertices.append((ring * math.cos(u), ring * math.sin(u), minor_radius * math.sin(v)))
    faces = []
    for major in range(major_segments):
        for minor in range(minor_segments):
            nxt_major = (major + 1) % major_segments
            nxt_minor = (minor + 1) % minor_segments
            faces.append((major * minor_segments + minor,
                          nxt_major * minor_segments + minor,
                          nxt_major * minor_segments + nxt_minor,
                          major * minor_segments + nxt_minor))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    for poly in mesh.polygons:
        poly.use_smooth = True
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    return obj


def polygon(name, points, z, mat):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata([(x, y, z) for x, y in points], [], [list(range(len(points)))])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def polygon_batch(name, polygons, z, mat):
    """Create disconnected coplanar polygons in one mesh datablock."""
    vertices = []
    faces = []
    for points in polygons:
        if len(points) < 3:
            continue
        offset = len(vertices)
        vertices.extend((x, y, z) for x, y in points)
        faces.append(tuple(offset + index for index in range(len(points))))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def extruded_polygons(name, polygons, base_z, thickness, mat, bevel=0.0):
    """Create several independent flat prisms as one mesh object."""
    vertices = []
    faces = []
    for points in polygons:
        if len(points) < 3:
            continue
        offset = len(vertices)
        vertices.extend((x, y, base_z) for x, y in points)
        vertices.extend((x, y, base_z + thickness) for x, y in points)
        count = len(points)
        faces.append(tuple(offset + index for index in reversed(range(count))))
        faces.append(tuple(offset + count + index for index in range(count)))
        for index in range(count):
            nxt = (index + 1) % count
            faces.append((offset + index, offset + nxt,
                          offset + count + nxt, offset + count + index))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if bevel:
        modifier = obj.modifiers.new("Soft edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def strip(name, start, end, width, z, mat, thickness=0.012, bevel=0.01):
    a = Vector(start)
    b = Vector(end)
    delta = b - a
    length = delta.length
    center = (a + b) * 0.5
    obj = cube(name, (center.x, center.y, z), (length, width, thickness), mat, bevel)
    obj.rotation_euler[2] = math.atan2(delta.y, delta.x)
    return obj


def dashed_line(name, start, end, width, dash, gap, z, mat,
                thickness=0.012, bevel=0.01):
    a = Vector(start)
    b = Vector(end)
    delta = b - a
    length = delta.length
    direction = delta.normalized()
    across = Vector((-direction.y, direction.x)) * (width * 0.5)
    cursor = gap * 0.5
    vertices = []
    faces = []
    low = z - thickness * 0.5
    high = z + thickness * 0.5
    while cursor < length:
        piece = min(dash, length - cursor)
        if piece > 0.05:
            piece_start = a + direction * cursor
            piece_end = a + direction * (cursor + piece)
            offset = len(vertices)
            vertices.extend((
                (piece_start.x - across.x, piece_start.y - across.y, low),
                (piece_end.x - across.x, piece_end.y - across.y, low),
                (piece_end.x + across.x, piece_end.y + across.y, low),
                (piece_start.x + across.x, piece_start.y + across.y, low),
                (piece_start.x - across.x, piece_start.y - across.y, high),
                (piece_end.x - across.x, piece_end.y - across.y, high),
                (piece_end.x + across.x, piece_end.y + across.y, high),
                (piece_start.x + across.x, piece_start.y + across.y, high),
            ))
            faces.extend(tuple(offset + index for index in face) for face in (
                (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
            ))
        cursor += dash + gap
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if bevel:
        modifier = obj.modifiers.new("Soft painted edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()
