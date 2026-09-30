"""Procedural red-and-white Japanese flexible reflector pole."""

import math

import bpy


def _material(name, color, metallic=0.0, roughness=0.5, coat=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = next(node for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    return material


def _cylinder(name, radius, depth, z, material, vertices=48, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("Rounded moulded edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def create_reflector_pole(name="Reflector Pole", location=(0, 0, 0),
                          rotation_degrees=0.0):
    """Create an 0.80m flexible delineator with three retroreflective bands."""
    before = set(bpy.context.scene.objects)
    red = _material(name + " red flexible resin", (0.72, 0.018, 0.012),
                    roughness=0.28, coat=0.32)
    reflector = _material(name + " white retroreflective film",
                          (0.92, 0.94, 0.91), roughness=0.22, coat=0.45)
    rubber = _material(name + " black rubber base", (0.018, 0.020, 0.018),
                       roughness=0.76)
    hardware = _material(name + " recessed hardware", (0.045, 0.048, 0.046),
                         metallic=0.28, roughness=0.58)

    _cylinder(name + " weighted rubber base", 0.145, 0.038, 0.019,
              rubber, 64, 0.012)
    _cylinder(name + " lower moulded collar", 0.092, 0.030, 0.054,
              red, 56, 0.010)
    _cylinder(name + " flexible red body", 0.061, 0.716, 0.420,
              red, 56, 0.008)
    # Thin sleeves sit only 1.5mm proud of the resin, avoiding a toy-like stack.
    for index, center_z in enumerate((0.355, 0.535, 0.705), 1):
        band = _cylinder(name + f" reflective band {index}", 0.0625, 0.085,
                         center_z, reflector, 56, 0.003)
        band["retroreflective_band"] = True

    bpy.ops.mesh.primitive_uv_sphere_add(segments=56, ring_count=20,
                                        location=(0, 0, 0.778),
                                        scale=(0.061, 0.061, 0.030))
    cap = bpy.context.object
    cap.name = name + " rounded red cap"
    cap.data.materials.append(red)
    for polygon in cap.data.polygons:
        polygon.use_smooth = True

    # Three shallow recessed fasteners, matching the triangular base pattern.
    for index, angle in enumerate((90.0, 210.0, 330.0), 1):
        radians = math.radians(angle)
        bolt = _cylinder(name + f" base fastener {index}", 0.012, 0.004, 0.041,
                         hardware, 24, 0.002)
        bolt.location.x = math.cos(radians) * 0.103
        bolt.location.y = math.sin(radians) * 0.103

    created = set(bpy.context.scene.objects) - before
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = location
    root.rotation_euler[2] = math.radians(rotation_degrees)
    for obj in created:
        obj.parent = root
    root["asset_type"] = "reflector_pole"
    root["height_m"] = 0.80
    root["base_diameter_m"] = 0.29
    return root


__all__ = ("create_reflector_pole",)
