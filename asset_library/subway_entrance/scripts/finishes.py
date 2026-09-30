"""Procedural, metre-scaled finishes and modest maintenance variation."""

def refine_finish(mat,key,bs):
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    def node(kind):return nodes.new('ShaderNode'+kind)
    def math(op,a,b):
        n=node('Math');n.operation=op
        for i,value in enumerate((a,b)):
            if isinstance(value,(int,float)):n.inputs[i].default_value=value
            else:links.new(value,n.inputs[i])
        return n.outputs[0]
    if key in ('glass','car_glass'):
        mix=next(n for n in nodes if n.type=='MIX_SHADER')
        fresnel=node('Fresnel');fresnel.inputs['IOR'].default_value=1.45
        # A thin optical sheet with angle-dependent reflection; no doubled alpha shell.
        reflection=math('MULTIPLY_ADD',fresnel.outputs[0],.84)
        reflection.node.inputs[2].default_value=.045
        links.new(math('SUBTRACT',1,reflection),mix.inputs[0])
        coord=node('TexCoord');separate=node('SeparateXYZ');links.new(coord.outputs['Object'],separate.inputs[0])
        base=.9685 if key=='glass' else .185
        distance=math('ABSOLUTE',math('SUBTRACT',separate.outputs['Z'],base),0)
        film=math('MAXIMUM',0,math('SUBTRACT',1,math('MULTIPLY',distance,12)))
        amount=node('Attribute');amount.attribute_type='OBJECT';amount.attribute_name='weathering'
        links.new(math('ADD',.075,math('MULTIPLY',math('MULTIPLY',film,amount.outputs['Fac']),.28)),bs.inputs['Roughness'])
        return
    if key not in ('stone','tile','metal','porcelain','frame','interior','handrail','nosing'):return
    coord=node('TexCoord');noise=node('TexNoise');noise.inputs['Scale'].default_value=5
    links.new(coord.outputs['Object'],noise.inputs['Vector'])
    if key in ('metal','handrail','nosing'):
        scale=node('VectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(110,110,2)
        links.new(coord.outputs['Object'],scale.inputs[0])
        fine=next(n for n in nodes if n.type=='TEX_NOISE');links.new(scale.outputs[0],fine.inputs['Vector']);fine.inputs['Scale'].default_value=3
        bs.inputs['Anisotropic'].default_value=.45
    # Ground splash fades within 250mm; sparse vertical dust/rain runs remain subtle.
    separate=node('SeparateXYZ');links.new(coord.outputs['Object'],separate.inputs[0])
    ground=math('MAXIMUM',0,math('SUBTRACT',1,math('MULTIPLY',math('ABSOLUTE',separate.outputs['Z'],0),4)))
    if key=='stone':
        under_cap=math('MAXIMUM',0,math('SUBTRACT',1,math('MULTIPLY',math('ABSOLUTE',math('SUBTRACT',separate.outputs['Z'],.89),0),8)))
        ground=math('ADD',ground,math('MULTIPLY',under_cap,.22))
    stretch=node('VectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(24,24,.7)
    links.new(coord.outputs['Object'],stretch.inputs[0]);rain=node('TexNoise');rain.inputs['Scale'].default_value=2;links.new(stretch.outputs[0],rain.inputs[0])
    amount=node('Attribute');amount.attribute_type='OBJECT';amount.attribute_name='weathering'
    mask=math('MULTIPLY',amount.outputs['Fac'],math('ADD',math('MULTIPLY',ground,.28),math('MULTIPLY',rain.outputs['Fac'],.06)))
    color=node('MixRGB');color.blend_type='MULTIPLY';color.inputs[2].default_value=(.32,.30,.26,1)
    old=list(bs.inputs['Base Color'].links)
    if old:links.new(old[0].from_socket,color.inputs[1])
    else:color.inputs[1].default_value=bs.inputs['Base Color'].default_value
    links.new(mask,color.inputs[0]);links.new(color.outputs[0],bs.inputs['Base Color'])
    rough=math('ADD',bs.inputs['Roughness'].default_value,math('MULTIPLY',noise.outputs['Fac'],.06))
    if key in ('handrail','nosing'):
        if key=='handrail':
            geom=node('NewGeometry');normal=node('SeparateXYZ');links.new(geom.outputs['Normal'],normal.inputs[0])
            touch=math('MAXIMUM',0,normal.outputs['Z'])
        else:touch=math('MAXIMUM',0,math('SUBTRACT',1,math('ABSOLUTE',separate.outputs['X'],0)))
        rough=math('SUBTRACT',rough,math('MULTIPLY',math('MULTIPLY',touch,amount.outputs['Fac']),.12))
    links.new(rough,bs.inputs['Roughness'])
    if key=='stone':
        macro=node('MixRGB');macro.blend_type='MULTIPLY';macro.inputs[0].default_value=.13
        links.new(color.outputs[0],macro.inputs[1]);links.new(noise.outputs['Color'],macro.inputs[2]);links.new(macro.outputs[0],bs.inputs['Base Color'])
