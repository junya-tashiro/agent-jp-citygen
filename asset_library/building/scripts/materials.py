"""Shared procedural finishes, without bitmap textures."""
import bpy
COLORS={
 'context_grey':((.22,.235,.24),0,.85),
 'grout':((.13,.14,.13),0,.90),'mat_rubber':((.045,.048,.045),0,.96),
 'fabric':((.14,.21,.20),0,.92),'cream':((.72,.64,.49),0,.65),
 'product_red':((.55,.07,.035),0,.43),'product_blue':((.04,.19,.38),0,.4),
 'product_green':((.12,.32,.10),0,.5),'store_teal':((.015,.28,.27),0,.38),
 'amber':((.85,.43,.035),0,.40),
 'limestone':((.50,.45,.35),0,.68),'pale_stone':((.60,.59,.54),0,.63),
 'granite':((.27,.29,.28),0,.61),'dark_stone':((.12,.15,.15),0,.55),
 'concrete':((.48,.49,.46),0,.76),'tile':((.38,.33,.28),0,.48),
 'brick':((.27,.105,.052),0,.77),'mortar':((.20,.18,.15),0,.85),
 'bronze':((.16,.12,.075),.72,.28),'silver':((.40,.43,.44),.72,.28),
 'dark_metal':((.055,.070,.072),.65,.29),'black':((.015,.02,.023),0,.8),
 'blue_glass':((.105,.21,.25),.40,.15),'grey_glass':((.19,.24,.24),.32,.18),
 'smoke_glass':((.19,.15,.105),.40,.19),'clear':((.22,.30,.31),.25,.12),
 'spandrel':((.055,.085,.095),.32,.3),'interior':((.24,.24,.21),0,.7),
 'ceiling':((.68,.65,.56),0,.8),'blind':((.40,.43,.40),0,.75),
 'wood':((.19,.095,.043),0,.58),'roof':((.17,.18,.17),0,.86),
 'paving':((.40,.39,.35),0,.88),'soil':((.045,.031,.017),0,.97),
 'leaf':((.06,.12,.039),0,.88),'leaf_light':((.115,.18,.06),0,.87),
 'white':((.82,.82,.75),0,.5),'warm_light':((1,.76,.40),0,.35),
}
def material(key):
    name='Building / '+key
    if name in bpy.data.materials:return bpy.data.materials[name]
    color,metal,rough=COLORS[key]
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=rough
    if key in ('limestone','pale_stone','granite','dark_stone','concrete','tile','brick','paving','roof','soil'):
        tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=70 if key!='brick' else 95;tex.inputs['Detail'].default_value=2
        coords=nodes.new('ShaderNodeTexCoord');links.new(coords.outputs['Object'],tex.inputs['Vector'])
        ramp=nodes.new('ShaderNodeValToRGB')
        for element,factor in zip(ramp.color_ramp.elements,(.80,1.12)):element.color=(*(c*factor for c in color),1)
        links.new(tex.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],bs.inputs['Base Color'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.003
        links.new(tex.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],bs.inputs['Normal'])
    if key=='wood':
        coords=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(3,80,5)
        links.new(coords.outputs['Object'],scale.inputs[0])
        grain=nodes.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=1;grain.inputs['Detail'].default_value=2;links.new(scale.outputs[0],grain.inputs['Vector'])
        ramp=nodes.new('ShaderNodeValToRGB')
        for e,f in zip(ramp.color_ramp.elements,(.72,1.15)):e.color=(*(c*f for c in color),1)
        links.new(grain.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],bs.inputs['Base Color'])
    if key=='clear':
        transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.68
        links.new(bs.outputs[0],mix.inputs[1]);links.new(transparent.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],next(n for n in nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'])
        fresnel=nodes.new('ShaderNodeFresnel');fresnel.inputs['IOR'].default_value=1.46
        ramp=nodes.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=0;ramp.inputs['From Max'].default_value=1;ramp.inputs['To Min'].default_value=.78;ramp.inputs['To Max'].default_value=.12
        links.new(fresnel.outputs[0],ramp.inputs['Value']);links.new(ramp.outputs[0],mix.inputs[0])
        mat.surface_render_method='BLENDED'
    if key=='warm_light':
        bs.inputs['Emission Color'].default_value=(*color,1);bs.inputs['Emission Strength'].default_value=2.4
    return mat
