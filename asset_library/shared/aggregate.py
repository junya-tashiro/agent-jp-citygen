"""Metric, image-free asphalt aggregate shared by road, paint and repairs."""
import bpy


def aggregate_group():
    name = 'Shared metric asphalt aggregate v1'
    existing = bpy.data.node_groups.get(name)
    if existing:
        return existing
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    for label, kind in [('Color', 'NodeSocketColor'), ('Roughness', 'NodeSocketFloat'), ('Height', 'NodeSocketFloat')]:
        group.interface.new_socket(name=label, in_out='OUTPUT', socket_type=kind)
    nodes, links = group.nodes, group.links

    def math(operation, a, b):
        node = nodes.new('ShaderNodeMath'); node.operation = operation
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                node.inputs[i].default_value = v
            else:
                links.new(v, node.inputs[i])
        return node.outputs[0]

    def vector(operation, a, b):
        node = nodes.new('ShaderNodeVectorMath'); node.operation = operation
        links.new(a, node.inputs[0])
        if isinstance(b, tuple):
            node.inputs[1].default_value = b
        else:
            links.new(b, node.inputs[1])
        return node.outputs[0]

    def noise(coords, scale, detail=2):
        node = nodes.new('ShaderNodeTexNoise')
        node.inputs['Scale'].default_value = scale
        node.inputs['Detail'].default_value = detail
        links.new(coords, node.inputs['Vector'])
        return node

    def ramp(value, low, high, positions=(0, 1)):
        node = nodes.new('ShaderNodeValToRGB')
        for element, color, pos in zip(node.color_ramp.elements, (low, high), positions):
            element.position = pos
            element.color = (*((color,)*3 if isinstance(color, (float, int)) else color), 1)
        links.new(value, node.inputs[0])
        return node.outputs[0]

    def mix(factor, a, b):
        node = nodes.new('ShaderNodeMixRGB')
        for i, v in enumerate((factor, a, b)):
            if isinstance(v, tuple):
                node.inputs[i].default_value = (*v, 1)
            elif isinstance(v, (int, float)):
                node.inputs[i].default_value = v
            else:
                links.new(v, node.inputs[i])
        return node.outputs[0]

    position = nodes.new('ShaderNodeNewGeometry').outputs['Position']
    # Project onto world XY: raised paint samples exactly the substrate beneath it.
    coords = vector('MULTIPLY', position, (1, 1, 0))
    distortion = noise(coords, 650, 2).outputs['Color']
    warped = vector('ADD', coords, vector('MULTIPLY', distortion, (.0015, .0015, 0)))
    binder_noise = noise(coords, 850, 2).outputs['Fac']
    color = ramp(binder_noise, (.025, .027, .028), (.046, .048, .048))
    height = math('MULTIPLY', binder_noise, .018)
    # Two size populations, with flat tops and irregular recessed boundaries.
    for scale, coverage, amplitude in ((240, .72, .035), (105, .64, .075)):
        grain = nodes.new('ShaderNodeTexVoronoi')
        grain.voronoi_dimensions = '2D'
        grain.inputs['Scale'].default_value = scale
        links.new(warped, grain.inputs['Vector'])
        edge = nodes.new('ShaderNodeTexVoronoi')
        edge.voronoi_dimensions = '2D'; edge.feature = 'DISTANCE_TO_EDGE'
        edge.inputs['Scale'].default_value = scale
        links.new(warped, edge.inputs['Vector'])
        margin = ramp(edge.outputs['Distance'], 0, 1, (.007, .045))
        footprint = ramp(grain.outputs['Distance'], 1, 0, (.30, coverage))
        occupied = math('MULTIPLY', margin, footprint)
        exposed = ramp(grain.outputs['Color'], .25, 1, (.20, .75))
        occupied = math('MULTIPLY', occupied, exposed)
        mineral = ramp(grain.outputs['Color'], (.035, .039, .041), (.115, .12, .115), (.15, .85))
        mineral = mix(.40, mineral, ramp(binder_noise, (.025, .027, .028), (.13, .135, .13)))
        color = mix(occupied, color, mineral)
        height = math('ADD', height, math('MULTIPLY', occupied, amplitude))
    roughness = math('SUBTRACT', .94, math('MULTIPLY', occupied, .13))
    out = nodes.new('NodeGroupOutput')
    links.new(color, out.inputs['Color'])
    links.new(roughness, out.inputs['Roughness'])
    links.new(height, out.inputs['Height'])
    group['code_generated'] = True
    group['nominal_cell_spacing_m'] = [1/240, 1/105]
    return group
