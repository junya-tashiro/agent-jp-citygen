"""Branch-local bark structures, evaluated without external images."""
import bpy


def bark_material(species):
    version = 1 if species == 'ginkgo' else 2
    name = f'Street tree {species} structural bark v{version}'
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(node for node in n if node.type == 'BSDF_PRINCIPLED')

    def math(op, a, b):
        node = n.new('ShaderNodeMath'); node.operation = op
        for i, value in enumerate((a, b)):
            if isinstance(value, (int, float)):
                node.inputs[i].default_value = value
            else:
                l.new(value, node.inputs[i])
        return node.outputs[0]

    def vector(op, a, b):
        node = n.new('ShaderNodeVectorMath'); node.operation = op
        l.new(a, node.inputs[0])
        if isinstance(b, tuple):
            node.inputs[1].default_value = b
        else:
            l.new(b, node.inputs[1])
        return node.outputs[0]

    def noise(coords, scale, detail=3):
        node = n.new('ShaderNodeTexNoise')
        l.new(coords, node.inputs['Vector'])
        node.inputs['Scale'].default_value = scale
        node.inputs['Detail'].default_value = detail
        return node

    def ramp(value, stops):
        node = n.new('ShaderNodeValToRGB')
        for i, (pos, color) in enumerate(stops):
            element = node.color_ramp.elements[i] if i < 2 else node.color_ramp.elements.new(pos)
            element.position = pos
            element.color = (*((color,)*3 if isinstance(color, (int, float)) else color), 1)
        l.new(value, node.inputs[0])
        return node.outputs[0]

    def mix(factor, a, b):
        node = n.new('ShaderNodeMixRGB')
        for i, value in enumerate((factor, a, b)):
            if isinstance(value, tuple):
                node.inputs[i].default_value = (*value, 1)
            elif isinstance(value, (float, int)):
                node.inputs[i].default_value = value
            else:
                l.new(value, node.inputs[i])
        return node.outputs[0]

    attr = n.new('ShaderNodeAttribute'); attr.attribute_name = 'bark_position_m'
    coords = attr.outputs['Vector']
    radius = n.new('ShaderNodeAttribute'); radius.attribute_name = 'bark_radius_m'
    maturity = ramp(radius.outputs['Fac'], [(.008, 0), (.09, 1)])
    fine = noise(coords, 900, 3).outputs['Fac']
    grain_coords = vector('MULTIPLY', coords, (180, 180, 22))
    grain = noise(grain_coords, 1, 4).outputs['Fac']
    warp = noise(coords, 24, 3).outputs['Color']
    warped = vector('ADD', coords, vector('MULTIPLY', warp, (.022, .022, .015)))
    erosion = noise(coords, 145, 4).outputs['Color']
    warped = vector('ADD', warped, vector('MULTIPLY', erosion, (.010, .010, .010)))
    scales = {'keyaki': (23, 23, 15), 'ginkgo': (38, 38, 4), 'cherry': (16, 16, 125)}
    structured = vector('MULTIPLY', warped, scales[species])
    cells = n.new('ShaderNodeTexVoronoi')
    cells.feature = 'DISTANCE_TO_EDGE'
    cells.inputs['Scale'].default_value = 1
    l.new(structured, cells.inputs['Vector'])
    ids = n.new('ShaderNodeTexVoronoi')
    ids.inputs['Scale'].default_value = 1
    l.new(structured, ids.inputs['Vector'])
    edge = cells.outputs['Distance']
    variability = noise(coords, 65, 4).outputs['Fac']
    if species == 'keyaki':
        # Nested erosion fronts expose successive layers rather than tiled cells.
        erosion_coords = vector('MULTIPLY', warped, (19, 19, 13))
        erosion_field = noise(erosion_coords, 1, 5)
        erosion_field.inputs['Roughness'].default_value = .72
        erosion_value = erosion_field.outputs['Fac']
        underlayer = ramp(erosion_value, [(.395, 0), (.410, 1)])
        outerlayer = ramp(erosion_value, [(.510, 0), (.526, 1)])
        fresh = mix(variability, (.25, .185, .12), (.38, .30, .21))
        middle = mix(variability, (.21, .215, .195), (.35, .345, .30))
        old = mix(variability, (.14, .15, .14), (.27, .28, .25))
        color = mix(outerlayer, mix(underlayer, fresh, middle), old)
        flakes = noise(coords, 170, 4).outputs['Fac']
        pitted = ramp(flakes, [(.34, 0), (.48, .35), (.58, .85), (.70, 1)])
        color = mix(math('MULTIPLY', pitted, .13), color, (.31, .30, .26))
        height = math('ADD', math('MULTIPLY', underlayer, .32),
                      math('MULTIPLY', outerlayer, .48))
        height = math('ADD', height, math('MULTIPLY', pitted, .15))
        depth = .0022
    elif species == 'ginkgo':
        ridge = ramp(edge, [(0, 0), (.045, .20), (.18, .85), (.33, 1)])
        color = ramp(ridge, [(0, (.065, .053, .039)), (.15, (.14, .12, .09)),
                              (.75, (.28, .265, .22)), (1, (.32, .30, .25))])
        color = mix(.20, color, ramp(grain, [(0, (.10, .09, .075)), (1, (.36, .33, .27))]))
        height = math('ADD', ridge, math('MULTIPLY', grain, .16))
        depth = .006
    else:
        # Older rough strips interrupt the smooth skin and its lenticels.
        age_coords = vector('MULTIPLY', warped, (19, 19, 3))
        age = noise(age_coords, 1, 4).outputs['Fac']
        aged = ramp(age, [(.48, 0), (.61, 1)])
        fissure_coords = vector('MULTIPLY', warped, (70, 70, 8))
        fissures = n.new('ShaderNodeTexVoronoi')
        fissures.feature = 'DISTANCE_TO_EDGE'
        fissures.inputs['Scale'].default_value = 1
        l.new(fissure_coords, fissures.inputs['Vector'])
        trench = ramp(fissures.outputs['Distance'], [(.007, 1), (.045, 0)])
        trench = math('MULTIPLY', trench, aged)
        island = ramp(ids.outputs['Distance'], [(.15, 1), (.39, 0)])
        lenticel = math('MULTIPLY', island, ramp(variability, [(.32, 0), (.63, 1)]))
        lenticel = math('MULTIPLY', lenticel, math('SUBTRACT', 1, math('MULTIPLY', aged, .75)))
        skin = mix(grain, (.095, .063, .047), (.26, .19, .14))
        scales = noise(vector('MULTIPLY', warped, (170, 170, 65)), 1, 4).outputs['Fac']
        rough_skin = mix(scales, (.09, .08, .065), (.29, .255, .205))
        color = mix(aged, skin, rough_skin)
        color = mix(trench, color, (.045, .032, .021))
        color = mix(lenticel, color, (.32, .245, .17))
        rough_height = math('MULTIPLY', aged, math('MULTIPLY', scales, .38))
        height = math('ADD', rough_height, math('MULTIPLY', lenticel, .20))
        height = math('SUBTRACT', height, math('MULTIPLY', trench, .65))
        height = math('ADD', height, math('MULTIPLY', grain, .06))
        depth = .0035
    young = mix(grain, (.13, .12, .08), (.24, .22, .15))
    l.new(mix(maturity, young, color), bsdf.inputs['Base Color'])
    l.new(ramp(fine, [(0, .65), (1, .92)]), bsdf.inputs['Roughness'])
    micro = n.new('ShaderNodeBump')
    micro.inputs['Distance'].default_value = .00018
    micro.inputs['Strength'].default_value = .35
    l.new(fine, micro.inputs['Height'])
    bump = n.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = depth
    bump.inputs['Strength'].default_value = .7
    l.new(math('MULTIPLY', maturity, height), bump.inputs['Height'])
    l.new(micro.outputs['Normal'], bump.inputs['Normal'])
    l.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    mat['code_generated_pbr'] = True
    mat['bark_model'] = {
        'keyaki': 'nested erosion fronts exposing successive bark layers',
        'cherry': 'lenticels interrupted by aged skin and local fissures',
        'ginkgo': 'branch-local cellular plates / fissures / lenticel islands',
    }[species]
    return mat
