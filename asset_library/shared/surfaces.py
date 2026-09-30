"""Metric, EEVEE-compatible finishes shared by independently built assets.

All detail is shading: no subdivision, alpha layers or scene-specific masks.
"""
import bpy


def noise(nodes, links, vector, scale, detail=3):
    node = nodes.new('ShaderNodeTexNoise')
    node.inputs['Scale'].default_value = scale
    node.inputs['Detail'].default_value = detail
    links.new(vector, node.inputs['Vector'])
    return node.outputs['Fac']


def ramp(nodes, links, value, low, high, positions=(0, 1)):
    node = nodes.new('ShaderNodeValToRGB')
    for element, color, position in zip(node.color_ramp.elements, (low, high), positions):
        element.color = (*color, 1)
        element.position = position
    links.new(value, node.inputs[0])
    return node.outputs['Color']




def asphalt_shader_group(repaired=False):
    name = 'Shared reinstated asphalt fields' if repaired else 'Shared weathered asphalt fields'
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    for label, kind in [('Color','NodeSocketColor'), ('Roughness','NodeSocketFloat'), ('Height','NodeSocketFloat')]:
        group.interface.new_socket(name=label, in_out='OUTPUT', socket_type=kind)
    nodes, links = group.nodes, group.links
    output = nodes.new('NodeGroupOutput')
    from asset_library.shared.aggregate import aggregate_group
    aggregate = nodes.new('ShaderNodeGroup'); aggregate.node_tree = aggregate_group()
    color = aggregate.outputs['Color']
    tone = nodes.new('ShaderNodeHueSaturation')
    tone.inputs['Saturation'].default_value = .30
    links.new(color, tone.inputs['Color'])
    position = nodes.new('ShaderNodeNewGeometry').outputs['Position']
    age = noise(nodes, links, position, .75, 5)
    age_color = ramp(nodes, links, age, (.80,.79,.77), (1.10,1.09,1.07), (.23,.77))
    mix = nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1
    links.new(tone.outputs[0], mix.inputs[1]); links.new(age_color, mix.inputs[2])
    if repaired:
        # The same aggregate, world scale and dry roughness as the carriageway.
        # Reinstatement is slightly fresher, without the old fracture field.
        tint = nodes.new('ShaderNodeMixRGB'); tint.blend_type = 'MULTIPLY'
        tint.inputs[0].default_value = 1
        tint.inputs[2].default_value = (.88, .88, .88, 1)
        links.new(mix.outputs[0], tint.inputs[1])
        links.new(tint.outputs[0], output.inputs['Color'])
        rough = aggregate.outputs['Roughness']
        links.new(rough, output.inputs['Roughness'])
        links.new(aggregate.outputs['Height'], output.inputs['Height'])
        return group
    from asset_library.shared.fractures import fracture_field
    fractures = fracture_field(nodes, links)
    cracked = nodes.new('ShaderNodeMixRGB')
    cracked.inputs[2].default_value = (.009,.010,.011,1)
    links.new(fractures, cracked.inputs[0]); links.new(mix.outputs[0], cracked.inputs[1])
    links.new(cracked.outputs[0], output.inputs['Color'])
    # A dry street retains high roughness throughout repairs.
    rough = aggregate.outputs['Roughness']
    links.new(rough, output.inputs['Roughness'])
    trench = nodes.new('ShaderNodeMath'); trench.operation = 'MULTIPLY'
    trench.inputs[1].default_value = .32
    links.new(fractures, trench.inputs[0])
    height = nodes.new('ShaderNodeMath'); height.operation = 'SUBTRACT'
    links.new(aggregate.outputs['Height'], height.inputs[0])
    links.new(trench.outputs[0], height.inputs[1])
    links.new(height.outputs[0], output.inputs['Height'])
    return group


def asphalt_material():
    mat = bpy.data.materials.new('Generated asphalt aggregate')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    field = nodes.new('ShaderNodeGroup'); field.node_tree = asphalt_shader_group()
    links.new(field.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(field.outputs['Roughness'], bsdf.inputs['Roughness'])
    mat['surface_scale_m'] = '4-10 mm aggregate cells / warped irregular fracture field'
    mat['code_generated_pbr'] = True
    return mat


def asphalt_repair_material():
    name = 'Local excavated asphalt repair'
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    field = nodes.new('ShaderNodeGroup'); field.node_tree = asphalt_shader_group(repaired=True)
    links.new(field.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(field.outputs['Roughness'], bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .65
    bump.inputs['Distance'].default_value = .008
    links.new(field.outputs['Height'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    mat['surface_scale_m'] = '4-10 mm aggregate cells; same scale as carriageway'
    mat['code_generated_pbr'] = True
    return mat


def finish(mat, kind):
    """Refine a base-color material without changing its authored color/emission."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    color = tuple(bsdf.inputs['Base Color'].default_value[:3])
    position = nodes.new('ShaderNodeNewGeometry').outputs['Position']
    fine = noise(nodes, links, position, 1100 if kind == 'coating' else 650)
    if kind == 'coating':
        bsdf.inputs['Metallic'].default_value = 0.0  # opaque paint covers the metal
        bsdf.inputs['Coat Weight'].default_value = .22
        bsdf.inputs['Coat Roughness'].default_value = .28
        rough_range, depth = (.32, .46), .000055
    elif kind in ('galvanized', 'metal'):
        bsdf.inputs['Metallic'].default_value = .94
        rough_range, depth = (.28, .48), .000035
        cells = nodes.new('ShaderNodeTexVoronoi')
        cells.inputs['Scale'].default_value = 180 if kind == 'galvanized' else 480
        links.new(position, cells.inputs['Vector'])
        dark, light = (.70, 1.10) if kind == 'galvanized' else (.97, 1.02)
        shade = ramp(nodes, links, cells.outputs['Color'],
                     tuple(c * dark for c in color), tuple(c * light for c in color))
        links.new(shade, bsdf.inputs['Base Color'])
    elif kind == 'sheeting':
        bsdf.inputs['Metallic'].default_value = 0
        bsdf.inputs['Coat Weight'].default_value = .38
        bsdf.inputs['Coat Roughness'].default_value = .2
        rough_range, depth = (.30, .38), .000018
    elif kind == 'optics':
        bsdf.inputs['IOR'].default_value = 1.49
        bsdf.inputs['Coat Weight'].default_value = .55
        bsdf.inputs['Coat Roughness'].default_value = .13
        rough_range, depth = (.19, .26), .000008
    else:
        raise ValueError(kind)
    rough = ramp(nodes, links, fine, (rough_range[0],) * 3, (rough_range[1],) * 3)
    links.new(rough, bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = depth
    bump.inputs['Strength'].default_value = .32
    links.new(fine, bump.inputs['Height'])
    links.new(bump.outputs[0], bsdf.inputs['Normal'])
    mat['finish'] = kind
    return mat


def signal_finish(mat, name, metallic, emission):
    key = name.lower()
    if emission is not None or any(s in key for s in ('lens', 'led', 'reflector')):
        return finish(mat, 'optics')
    if 'stainless' in key:
        return finish(mat, 'metal')
    if any(s in key for s in ('painted', 'coated', 'housing', 'hood', 'exterior')):
        return finish(mat, 'coating')
    return mat


def smooth_bevel(obj, modifier):
    """Keep flat faces planar while interpolating the existing bevel segments."""
    modifier.harden_normals = True
    for face in obj.data.polygons:
        face.use_smooth = True
    normal = obj.modifiers.new('Manufactured face normals', 'WEIGHTED_NORMAL')
    normal.keep_sharp = True
    normal.weight = 50
