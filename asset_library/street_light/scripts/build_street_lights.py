"""Procedural roadway and pedestrian street-light assets."""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ASSET_ROOT = Path(__file__).resolve().parents[1]
WARM_LIGHT = (1.0, 0.58, 0.22)


def material(name, color, metallic=0.0, roughness=0.5, emission=None,
             emission_strength=0.0, transmission=0.0):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def cube(name, location, dimensions, mat, bevel=0.0, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def cylinder(name, location, radius, depth, mat, vertices=48,
             rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                       depth=depth, location=location,
                                       rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def tapered(name, location, radius_bottom, radius_top, depth, mat, vertices=48):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius_bottom,
                                   radius2=radius_top, depth=depth,
                                   location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def _tube_between(name, start, end, radius, mat, vertices=32):
    start, end = Vector(start), Vector(end)
    delta = end - start
    obj = cylinder(name, (start + end) * 0.5, radius, delta.length, mat, vertices)
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def _square_bar_between(name, start, end, width, mat, bevel=0.0):
    start, end = Vector(start), Vector(end)
    delta = end - start
    obj = cube(name, (start + end) * 0.5,
               (width, width, delta.length), mat, bevel)
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def _square_frustum(name, z_bottom, z_top, half_bottom, half_top, mat):
    vertices = []
    for z, half in ((z_bottom, half_bottom), (z_top, half_top)):
        vertices.extend(((-half, -half, z), (half, -half, z),
                         (half, half, z), (-half, half, z)))
    faces = ((0, 1, 2, 3), (4, 7, 6, 5),
             (0, 4, 5, 1), (1, 5, 6, 2),
             (2, 6, 7, 3), (3, 7, 4, 0))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Lantern glass edge softness", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 2
    return obj


def _warm_area_light(name, location, energy, size, rotation=(0, 0, 0),
                     spread_degrees=180.0):
    data = bpy.data.lights.new(name, "AREA")
    data.color = WARM_LIGHT
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = size * 0.45
    if hasattr(data, "spread"):
        data.spread = math.radians(spread_degrees)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def create_roadway_streetlight(name="Roadway Street Light", location=(0, 0, 0),
                               rotation_degrees=0.0, lit=True):
    """Create a fixed-span, two-sided median street light.

    Local X is the road-crossing direction.  The arm length deliberately does
    not depend on lane count; future placement code only positions the root.
    """
    before = set(bpy.context.scene.objects)
    galvanized = material("Street light matte galvanized grey",
                          (0.34, 0.37, 0.38), 0.58, 0.64)
    dark_metal = material("Street light dark grey joints",
                          (0.095, 0.105, 0.108), 0.62, 0.48)
    lens = material(
        "Street light warm LED diffuser" if lit else "Street light unlit diffuser",
        (0.92, 0.78, 0.48) if lit else (0.34, 0.36, 0.34),
        roughness=0.32 if lit else 0.52,
        emission=WARM_LIGHT if lit else None,
        emission_strength=7.5 if lit else 0.0,
    )

    cylinder(name + " circular footing", (0, 0, 0.08), 0.28, 0.16,
             dark_metal, 56)
    cylinder(name + " base flange", (0, 0, 0.20), 0.22, 0.10,
             galvanized, 56)
    for angle in range(0, 360, 90):
        r = math.radians(angle)
        cylinder(name + " anchor bolt", (math.cos(r) * 0.16,
                 math.sin(r) * 0.16, 0.27), 0.014, 0.055, dark_metal, 20)
    tapered(name + " tapered median pole", (0, 0, 4.35),
            0.155, 0.082, 8.20, galvanized, 64)
    cube(name + " access hatch", (0, -0.151, 0.95),
         (0.19, 0.018, 0.42), dark_metal, 0.024)
    cylinder(name + " upper coupling", (0, 0, 8.48), 0.105, 0.28,
             dark_metal, 48)

    arm_root_height = 8.62
    arm_tip_height = 8.78
    for side, label in ((-1, "left"), (1, "right")):
        housing_tilt = -side * math.radians(3.5)
        housing_center = Vector((side * 2.62, 0, 8.80))

        def housing_point(local_x, local_y, local_z):
            """Map a luminaire-local point into asset coordinates."""
            return housing_center + Vector((
                math.cos(housing_tilt) * local_x
                + math.sin(housing_tilt) * local_z,
                local_y,
                -math.sin(housing_tilt) * local_x
                + math.cos(housing_tilt) * local_z,
            ))

        # Recess the diffuser by its full thickness: its outer face is exactly
        # coplanar with the housing underside instead of hanging below it.
        diffuser_center = housing_point(0, -0.005, -0.070)
        # One uninterrupted arm per side: deliberately no diagonal brace or
        # intermediate elbow.  Its tip rises slightly away from the pole.
        _tube_between(name + f" {label} outward arm", (0, 0, arm_root_height),
                      (side * 2.45, 0, arm_tip_height), 0.064, galvanized, 40)
        # Hollow housing: the lower face is open except for the flush diffuser.
        # Its four walls act as a real baffle around the recessed Area Light.
        for part, local, dimensions in (
            ("top", (0, 0, 0.060), (0.72, 0.34, 0.040)),
            ("front wall", (0, -0.155, 0), (0.72, 0.030, 0.120)),
            ("back wall", (0, 0.155, 0), (0.72, 0.030, 0.120)),
            ("inner end wall", (-side * 0.345, 0, 0),
             (0.030, 0.28, 0.120)),
            ("outer end wall", (side * 0.345, 0, 0),
             (0.030, 0.28, 0.120)),
        ):
            cube(name + f" {label} LED housing {part}",
                 housing_point(*local), dimensions, galvanized, 0.022,
                 (0, housing_tilt, 0))
        diffuser = cube(name + f" {label} warm diffuser", diffuser_center,
                        (0.58, 0.24, 0.020), lens, 0.018,
                        (0, housing_tilt, 0))
        # The frosted cover is visible but must transmit the internal lamp's
        # direct light; otherwise the flush cover becomes an opaque blocker.
        if hasattr(diffuser, "visible_shadow"):
            diffuser.visible_shadow = False
        cylinder(name + f" {label} arm collar", (side * 2.24, 0, 8.77),
                 0.083, 0.15, dark_metal, 32,
                 (0, math.radians(90) - side * math.radians(3.5), 0))
        if lit:
            # The emitting rectangle sits inside the hollow case.  The walls
            # baffle lateral rays while its underside remains physically flush.
            light_center = housing_point(0, 0, 0.018)
            light = _warm_area_light(
                name + f" {label} cast light",
                light_center,
                300, 0.56, (0, housing_tilt, 0))
            light.data.size_y = 0.23

    # Bake the final 70% design size into the reusable asset itself.  Keeping
    # the canonical collection at its real size avoids a placement-time parent
    # scale and the expensive scene-wide dependency-graph update it required.
    design_scale = 0.70
    created = set(bpy.context.scene.objects) - before
    for obj in created:
        obj.location = Vector(obj.location) * design_scale
        if obj.type == "MESH":
            obj.scale = tuple(value * design_scale for value in obj.scale)
        elif obj.type == "LIGHT":
            if hasattr(obj.data, "size"):
                obj.data.size *= design_scale
            if hasattr(obj.data, "size_y"):
                obj.data.size_y *= design_scale
            if hasattr(obj.data, "shadow_soft_size"):
                obj.data.shadow_soft_size *= design_scale

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["asset_type"] = "roadway_streetlight"
    root["lit"] = bool(lit)
    root["design_scale"] = 0.70
    root["nominal_height_m"] = 6.272
    root["fixed_total_span_m"] = 3.92
    return root


def _lantern_roof(name, z, frame, half_extent=0.17, rise=0.14):
    vertices = [(-half_extent, -half_extent, z),
                (half_extent, -half_extent, z),
                (half_extent, half_extent, z),
                (-half_extent, half_extent, z), (0, 0, z + rise)]
    faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(frame)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Soft cap edge radius", "BEVEL")
    bevel.width = 0.012
    bevel.segments = 3
    return obj


def create_pedestrian_streetlight(name="Pedestrian Street Light",
                                  location=(0, 0, 0), rotation_degrees=0.0,
                                  lit=True):
    """Create a compact dark-green gas-lamp-inspired footway light."""
    before = set(bpy.context.scene.objects)
    green = material("Street light deep green painted iron",
                     (0.018, 0.095, 0.065), 0.55, 0.48)
    green_dark = material("Street light deep green shadow metal",
                          (0.008, 0.035, 0.025), 0.62, 0.56)
    glass = material(
        "Street light warm frosted lantern glass" if lit else
        "Street light unlit frosted lantern glass",
        (0.94, 0.72, 0.38) if lit else (0.30, 0.34, 0.30),
        roughness=0.28 if lit else 0.42, transmission=0.16,
        emission=WARM_LIGHT if lit else None,
        emission_strength=5.5 if lit else 0.0,
    )

    cylinder(name + " buried base", (0, 0, 0.08), 0.25, 0.16, green_dark, 56)
    tapered(name + " flared lower pedestal", (0, 0, 0.42),
            0.22, 0.115, 0.68, green, 56)
    cylinder(name + " lower decorative collar", (0, 0, 0.77),
             0.17, 0.16, green_dark, 56)
    tapered(name + " slender footway post", (0, 0, 2.08),
            0.105, 0.074, 2.50, green, 48)
    for z, radius, depth in ((3.30, 0.13, 0.11), (3.39, 0.18, 0.09),
                             (3.48, 0.12, 0.10)):
        cylinder(name + " upper ornamental collar", (0, 0, z),
                 radius, depth, green_dark if radius > 0.15 else green, 48)
    cylinder(name + " lantern lower plate", (0, 0, 3.54), 0.18, 0.07,
             green_dark, 56)

    z_bottom, z_top = 3.55, 3.92
    half_bottom, half_top = 0.105, 0.155
    _square_frustum(name + " lantern luminous core", z_bottom, z_top,
                    half_bottom - 0.018, half_top - 0.018, glass)
    for sx in (-1, 1):
        for sy in (-1, 1):
            _square_bar_between(
                name + " lantern sloping corner frame",
                (sx * half_bottom, sy * half_bottom, z_bottom),
                (sx * half_top, sy * half_top, z_top),
                0.035, green, 0.007)
    for z, half in ((z_bottom, half_bottom), (z_top, half_top)):
        cube(name + " lantern square rail", (0, -half, z),
             (half * 2 + 0.035, 0.035, 0.035), green, 0.008)
        cube(name + " lantern square rail", (0, half, z),
             (half * 2 + 0.035, 0.035, 0.035), green, 0.008)
        cube(name + " lantern square rail", (-half, 0, z),
             (0.035, half * 2 + 0.035, 0.035), green, 0.008)
        cube(name + " lantern square rail", (half, 0, z),
             (0.035, half * 2 + 0.035, 0.035), green, 0.008)
    _lantern_roof(name + " pyramidal lantern cap", 3.95, green_dark)
    cylinder(name + " cap finial", (0, 0, 4.14), 0.035, 0.10, green, 32)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16,
                                        location=(0, 0, 4.215))
    finial = bpy.context.object
    finial.name = name + " rounded finial"
    finial.scale = (0.045, 0.045, 0.055)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    finial.data.materials.append(green_dark)
    if lit:
        point_data = bpy.data.lights.new(name + " warm pedestrian pool", "POINT")
        point_data.color = WARM_LIGHT
        point_data.energy = 650
        point_data.shadow_soft_size = 1.45
        point = bpy.data.objects.new(name + " warm pedestrian pool", point_data)
        bpy.context.collection.objects.link(point)
        point.location = (0, 0, 3.72)

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in set(bpy.context.scene.objects) - before:
        if obj is not root:
            obj.parent = root
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    root["asset_type"] = "pedestrian_streetlight"
    root["lit"] = bool(lit)
    root["nominal_height_m"] = 4.27
    return root


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _preview(asset, lit):
    scene = bpy.context.scene
    ground = material("Street light preview paving", (0.11, 0.12, 0.115),
                      roughness=0.88)
    cube("Preview ground", (0, 0, -0.06), (15, 12, 0.10), ground, 0.02)
    world = bpy.data.worlds.new("Street light preview dusk")
    world.use_nodes = True
    bg = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.035, 0.055, 0.085, 1.0)
    bg.inputs["Strength"].default_value = 0.20
    scene.world = world
    for label, position, energy, size, color in (
        ("Key", (-5, -5, 9), 1000, 5.0, (0.72, 0.82, 1.0)),
        ("Fill", (5, -2, 5), 360, 4.0, (0.78, 0.86, 1.0)),
    ):
        data = bpy.data.lights.new("Preview " + label, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new("Preview " + label, data)
        scene.collection.objects.link(obj)
        obj.location = position
        _look_at(obj, (0, 0, 3.5))
    camera_data = bpy.data.cameras.new("Street light preview camera")
    camera = bpy.data.objects.new("Street light preview camera", camera_data)
    scene.collection.objects.link(camera)
    if asset == "roadway":
        camera.location = (10.8, -13.0, 7.1)
        _look_at(camera, (0, 0, 4.6))
        camera_data.lens = 58
    else:
        camera.location = (6.1, -8.5, 4.1)
        _look_at(camera, (0, 0, 2.35))
        camera_data.lens = 62
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.25 if lit else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=("roadway", "pedestrian"), required=True)
    parser.add_argument("--lit", choices=("on", "off"), default="on")
    parser.add_argument("--render", choices=("none", "preview", "final"), default="preview")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lit = args.lit == "on"
    if args.asset == "roadway":
        root = create_roadway_streetlight(lit=lit)
    else:
        root = create_pedestrian_streetlight(lit=lit)
    _preview(args.asset, lit)
    suffix = "lit" if lit else "unlit"
    stem = f"street_light_{args.asset}_{suffix}"
    if args.render != "none":
        bpy.context.scene.render.resolution_x = 1200 if args.render == "final" else 900
        bpy.context.scene.render.resolution_y = 1200 if args.render == "final" else 900
        bpy.context.scene.render.filepath = str(ASSET_ROOT / "renders" / f"{stem}.png")
        bpy.ops.render.render(write_still=True)
    # Preview staging is intentionally excluded from the reusable asset file.
    # Keeping it would add cameras/lights/ground geometry every time the asset
    # is linked into a generated scene.
    bpy.context.scene.camera = None
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Preview") or obj.name == "Street light preview camera":
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSET_ROOT / "blend" / f"{stem}.blend"))
    print(f"STREET_LIGHT_ASSET={root['asset_type']} lit={root['lit']} objects={len(bpy.data.objects)}")


if __name__ == "__main__":
    main()
