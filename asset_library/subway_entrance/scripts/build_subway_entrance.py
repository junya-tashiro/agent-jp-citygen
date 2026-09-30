"""Original Japanese subway entrances. Python geometry only; EEVEE preview."""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from asset_library.subway_entrance.scripts.design import entrance_spec


def palette():
    result = {}
    specs = {
        'stone': ((.43,.44,.41),0,.77), 'tile': ((.64,.65,.60),0,.58),
        'handrail': ((.36,.40,.41),.78,.24), 'nosing': ((.36,.40,.41),.78,.30), 'metal': ((.36,.40,.41),.78,.28), 'frame': ((.12,.16,.17),.7,.34),
        'blue': ((.016,.09,.19),.15,.36), 'white': ((.87,.90,.86),0,.4),
        'black': ((.012,.018,.021),.1,.48), 'yellow': ((.84,.53,.025),0,.7),
        'glass_edge': ((.13,.26,.21),0,.18), 'glass': ((.64,.77,.78),0,.06), 'car_glass': ((.71,.80,.78),0,.08),
        'porcelain': ((.74,.75,.70),0,.40), 'interior': ((.37,.40,.39),0,.48),
        'rubber': ((.025,.03,.032),0,.76), 'pictogram': ((.92,.94,.92),0,.38), 'light': ((.85,.90,1),0,.3),
    }
    from asset_library.subway_entrance.scripts.signage import ROUTE_COLORS
    specs['sign_teal']=((.015,.34,.40),0,.4)
    specs.update({k:(v,0,.4) for k,v in ROUTE_COLORS.items()})
    for key,(color,metal,rough) in specs.items():
        name='Subway / '+key
        mat=bpy.data.materials.get(name)
        if mat is None:
            mat=bpy.data.materials.new(name);mat.use_nodes=True
            bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
            bs.inputs['Base Color'].default_value=(*color,1)
            bs.inputs['Metallic'].default_value=metal
            bs.inputs['Roughness'].default_value=rough
            if key in ('glass','car_glass'):
                bs.inputs['Transmission Weight'].default_value=0
                mat.surface_render_method='BLENDED'
                bs.inputs['IOR'].default_value=1.45
                # Thin architectural glazing: stable transmission in EEVEE.
                nodes,links=mat.node_tree.nodes,mat.node_tree.links
                transparent=nodes.new('ShaderNodeBsdfTransparent')
                mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.90 if key=='glass' else .87
                links.new(bs.outputs[0],mix.inputs[1]);links.new(transparent.outputs[0],mix.inputs[2])
                links.new(mix.outputs[0],next(n for n in nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'])
            if key in ('light','white','blue','pictogram'):
                bs.inputs['Emission Color'].default_value=(*color,1)
                bs.inputs['Emission Strength'].default_value=2 if key=='light' else (.6 if key=='blue' else .65)
            if key in ('stone','tile','metal','handrail','nosing'):
                nodes,links=mat.node_tree.nodes,mat.node_tree.links
                tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=180 if key in ('stone','tile') else 330
                coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['Object'],tex.inputs['Vector'])
                bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22
                bump.inputs['Distance'].default_value=.0006 if key in ('stone','tile') else .00008
                links.new(tex.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])
            if key=='stone':
                nodes,links=mat.node_tree.nodes,mat.node_tree.links
                grain=nodes.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=270
                links.new(coord.outputs['Object'],grain.inputs['Vector'])
                ramp=nodes.new('ShaderNodeValToRGB')
                ramp.color_ramp.elements[0].position=.23;ramp.color_ramp.elements[0].color=(.27,.28,.26,1)
                ramp.color_ramp.elements[1].position=.77;ramp.color_ramp.elements[1].color=(.57,.58,.54,1)
                links.new(grain.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],bs.inputs['Base Color'])
            from asset_library.subway_entrance.scripts.finishes import refine_finish
            refine_finish(mat,key,bs)
        result[key]=mat
    return result


from asset_library.subway_entrance.scripts.geometry import Geometry


def font():
    from asset_library.shared.fonts import japanese_font
    return japanese_font()


def label(collection,parent,body,position,size,max_width,material='white',side=0,bold=False):
    if not body:return
    curve=bpy.data.curves.new('Subway lettering','FONT');curve.body=body;curve.font=font()
    curve.size=size;curve.align_x='CENTER';curve.align_y='CENTER';curve.space_character=1.1
    curve.extrude=.0004;curve.resolution_u=6
    if bold:
        curve.bevel_depth=size*.008
        curve.bevel_resolution=2
    obj=bpy.data.objects.new('Sign '+body,curve);collection.objects.link(obj);obj.parent=parent
    obj.location=position;obj.rotation_euler=(math.pi/2,0,side)
    curve.materials.append(palette()[material])
    bpy.context.view_layer.update()
    # Text local X is horizontal even on the side sign.
    span=max(v[0] for v in obj.bound_box)-min(v[0] for v in obj.bound_box)
    if span>max_width:obj.scale*=max_width/span
    # Store durable glyph geometry; packed TTC faces may not survive Blender reload.
    bpy.context.view_layer.update()
    mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    baked=bpy.data.objects.new('Sign '+body,mesh);collection.objects.link(baked);baked.parent=parent
    baked.matrix_basis=obj.matrix_basis.copy();baked['subway_part']='lettering';baked['label_text']=body
    bpy.data.objects.remove(obj,do_unlink=True)
    if curve.users==0:bpy.data.curves.remove(curve)
    return baked


def warning_tiles(g,width,y,z=0):
    # Defer placement to the same detailed products used by the road renderer.
    if not hasattr(g,'warning_fields'):g.warning_fields=[]
    g.warning_fields.append((width,y,z))


def finish_warning_tiles(g,col,root):
    from road_generator.core.planner import TactileTilePlan, SIDEWALK_TOP_Z_M
    from road_generator.blender.scene import _tactile_paving_mesh, weathered_material
    material=bpy.data.materials.get('Tactile paving yellow')
    if material is None:
        material=weathered_material('Tactile paving yellow',(.58,.39,.018),(.98,.72,.055),.83,18.0)
    for field,(width,y,z) in enumerate(g.warning_fields):
        count=int((width-.5)/.3+1e-6)
        plans=[TactileTilePlan(f'entrance_warning_{field}_{i}_{j}','warning',
                ((i-(count-1)/2)*.3,y+offset),(.3,.3),'x',0)
               for i in range(count) for j,offset in enumerate((-.15,.15))]
        for part in _tactile_paving_mesh(plans,material):
            for collection in list(part.users_collection):collection.objects.unlink(part)
            col.objects.link(part);part.parent=root;part.location.z=z-SIDEWALK_TOP_Z_M
            part.name='Subway entrance warning tiles';part['subway_part']='tactile_warning'


def create_subway_entrance(variant='stairs',station_name='中央',station_roman='Chuo',exit_label='A1',width=3.0,name=None,weathering=.18,routes=None):
    if isinstance(weathering,bool) or not isinstance(weathering,(int,float)) or not math.isfinite(weathering) or not 0<=weathering<=1:raise ValueError('weathering must be between 0 and 1')
    from asset_library.subway_entrance.scripts.sign_spec import normalize_routes
    from asset_library.subway_entrance.scripts.signage import station_sign
    routes=normalize_routes(routes)
    spec=entrance_spec(variant,width)
    if not isinstance(station_name,str) or not station_name.strip():raise ValueError('station_name must be non-empty')
    for value in (station_roman,exit_label):
        if not isinstance(value,str):raise ValueError('Sign labels must be strings')
    col=bpy.data.collections.new(name or 'Subway Entrance '+variant);bpy.context.scene.collection.children.link(col)
    root=bpy.data.objects.new(name or 'Subway '+variant,None);col.objects.link(root)
    root['routes_json']=json.dumps(routes)
    root['asset_type']='subway_entrance';root['variant']=variant;root['station_name']=station_name
    root['spec_json']=json.dumps(spec);root['coordinate_convention']='origin threshold; +Y inward; -Y front; Z up'
    root['weathering']=float(weathering)
    g=Geometry();w=width;L=spec['length'];inner=w-.46
    # Shared stone plinths and metal wall caps, all inside maximum width.
    for s in (-1,1):
        x=s*(w/2-.15)
        g.box('stone',(x,L/2,.46),(.25,L,.92))
        g.box('rubber',((1 if x>0 else -1)*(w/2-.018),L/2,.0015),(.014,L,.003))
        g.box('metal' if variant=='stairs' else 'stone',(x,L/2,.946),(.29,L,.045))
    if variant=='stairs':
        # 0.9m top landing; fifteen 160mm risers / 300mm treads; bottom landing.
        g.box('stone',(0,.35,-.09),(inner,.70,.18))
        g.box('stone',(0,.87,-.09),(inner,.06,.18))
        g.box('stone',(0,.77,-.11),(inner,.14,.14))
        warning_tiles(g,w,.38)
        for i in range(15):
            y=.9+(i+.5)*.3;top=-(i+1)*.16
            g.box('stone',(0,y,top-.09),(inner,.30,.18))
            g.box('nosing',(0,y-.138,top+.001),(inner,.023,.003))
            g.box('black',(0,y-.105,top+.002),(inner-.06,.036,.004))
            # Close each riser and the underside as a real solid stepped slab.
            if i<14:g.box('stone',(0,y+.15,top-.17),(inner,.04,.18))
        g.box('stone',(0,5.88,-2.49),(inner,.96,.18))
        warning_tiles(g,w,5.98,-2.4)
        for s in (-1,1):
            g.box('tile',(s*(w/2-.18),3.65,-.82),(.1,5.5,3.50))
            # Metric tile joints in stairwell, visible in the descent.
            for j in range(12):g.box('stone',(s*(w/2-.233),3.65,-2.35+j*.28),(.007,5.45,.005))
            for j in range(18):g.box('stone',(s*(w/2-.233),.96+j*.30,-.8),(.007,.004,3.2))
            x=s*(w/2-.34)
            for h in (.72,.92):
                points=[(x,.20,h),(x,.90,h),(x,5.4,h-2.4),(x,6.1,h-2.4)]
                points=[(s*(w/2-.235),.20,h)]+points+[(s*(w/2-.235),6.1,h-2.4)]
                g.rail('handrail',points)
                for y in (1.2,2.4,3.6,4.8,5.9):
                    z=h-min(2.4,max(0,y-.9)*.16/.30)
                    g.tube('metal',(x,y,z),(s*(w/2-.13),y,z-.07),.011)
            for y in (.10,1.70,3.30,4.90,6.48):
                g.box('frame',(s*(w/2-.12),y,1.87),(.09,.09,1.86))
                g.box('metal',(s*(w/2-.12),y,1.02),(.16,.16,.12))
            for a,b in ((.15,1.65),(1.75,3.25),(3.35,4.85),(4.95,6.43)):
                g.pane('glass','x',s*(w/2-.12),(a,b),(.9685,2.515))
            g.box('frame',(s*(w/2-.12),L/2,2.55),(.12,L,.12))
            # Roof gutter and downpipe.

        # Shallow pitched metal roof with translucent centre strip.

        g.mesh('glass',[(-.55,0,2.89),(.55,0,2.89),(.55,L,2.89),(-.55,L,2.89)],[(0,1,2,3)])
        for y in (.06,1.70,3.30,4.90,6.54):
            g.box('frame',(0,y,2.72),(w,.08,.13))
            g.box('frame',(0,y,2.829),(1.12,.08,.09))
        g.box('stone',(0,6.49,.35),(w-.04,.20,1.15))
        g.box('metal',(0,6.49,.946),(w-.02,.29,.045))
        # Recessed, closed far end represents the continuation beyond the asset.
        g.box('stone',(0,7.40,-2.49),(inner,2.0,.18))
        g.box('tile',(0,7.40,-.16),(inner,2.0,.16))
        for s in (-1,1):g.box('tile',(s*(w/2-.18),7.4,-1.3),(.10,2.0,2.2))
        g.box('black',(0,8.40,-1.30),(inner,.10,2.2))
        g.pane('glass','y',6.49,(-w/2+.14,w/2-.14),(.9685,2.52))
        g.box('frame',(0,6.49,2.55),(w-.12,.12,.12))
        # A dark lower turning passage, with ceiling over bottom landing.
        g.box('tile',(0,6.34,-.18),(inner,.30,.16))
        station_sign(g,col,root,inner-.10,-.43,6.355,station_name,station_roman,routes,height=.32)
        for side in (-1,1):
            for y in (1.7,3.3,4.9):
                x=side*(w/2+.55)/2
                g.box('frame',(x,y,2.6375),(.12,.85,.035))
                g.box('light',(x,y,2.6075),(.068,.76,.024))
        # Entry drainage channel: solid recess and raised bars.
        g.box('black',(0,.77,-.032),(inner,.132,.014))
        for i in range(int(inner/.04)):
            g.box('metal',(-inner/2+.02+i*.04,.77,-.006),(.011,.13,.012))
        for y in (.702,.838):g.box('metal',(0,y,-.006),(inner,.012,.012))
        sign_z=2.56
    else:
        from asset_library.subway_entrance.scripts.elevator import build_elevator
        build_elevator(g,w,L)
        for text,z in (('1',1.35),('B1',1.25)):
            button_label=label(col,root,text,(-.79,.655,z),.031,.039,'rubber',side=math.pi)
            button_label['subway_assembly']='car'
        warning_tiles(g,1.7,-.48)
        sign_z=3.16
    station_sign(g,col,root,w-.16,sign_z,-.030 if variant=='stairs' else -.008,station_name,station_roman,routes,lift=variant=='elevator')
    from asset_library.subway_entrance.scripts.details import stair_details,elevator_details,fixture_lights
    (stair_details if variant=='stairs' else elevator_details)(g,w,L)
    # Recessed panel perimeter and narrow weather seal.
    trim='frame'
    sy=-.032 if variant=='stairs' else -.010
    for z in (sign_z-.257,sign_z+.257):g.box(trim,(0,sy,z),(w-.15,.012,.012))
    for x in (-w/2+.077,w/2-.077):g.box(trim,(x,sy,sign_z),(.012,.012,.51))
    g.finish(col,root)
    fixture_lights(col,root,w,variant)
    finish_warning_tiles(g,col,root)
    return root


def setup_preview(root,output,render='preview'):
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT'
    scene.eevee.taa_render_samples=48 if render=='preview' else 96
    scene.eevee.use_raytracing=True
    scene.render.resolution_x=1300;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.world=bpy.data.worlds.new('Subway preview world');scene.world.use_nodes=True
    next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND').inputs[0].default_value=(.55,.65,.78,1)
    next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND').inputs[1].default_value=.45
    scene.view_settings.view_transform='AgX'
    for name,loc,energy,size in [('Key',(2,-4,9),1800,7),('Fill',(-5,2,6),1300,6)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size
        o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,2,0))-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('Entrance camera');camera=bpy.data.objects.new('Entrance camera',data);scene.collection.objects.link(camera)
    camera.location=(8,-10,6.5);target=Vector((0,2.6,1));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();data.lens=48
    scene.camera=camera
    output.mkdir(parents=True,exist_ok=True)
    return camera


def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=['stairs','elevator'],default='stairs')
    p.add_argument('--station-name',default='中央');p.add_argument('--station-roman',default='Chuo');p.add_argument('--exit-label',default='A1');p.add_argument('--width',type=float,default=3)
    from asset_library.subway_entrance.scripts.sign_spec import parse_route_argument
    p.add_argument('--route',action='append',type=parse_route_argument,help='Station code and color (M11=#E53935); repeat for multiple lines')
    p.add_argument('--weathering',type=float,default=.18)
    p.add_argument('--render',choices=['none','preview','final'],default='preview')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    start=time.perf_counter();bpy.ops.wm.read_factory_settings(use_empty=True)
    root=create_subway_entrance(args.variant,args.station_name,args.station_roman,args.exit_label,args.width,weathering=args.weathering,routes=args.route if args.route is not None else ['M15','H07','C08'])
    out=ROOT/'asset_library/subway_entrance';camera=setup_preview(root,out/'renders',args.render)
    # Preview support is intentionally separate and includes a real stair opening.
    from road_generator.blender.subway import cut_opening
    g=Geometry();g.box('tile',(0,2.7,-.14),(12,16,.28))
    col=bpy.data.collections.new('Preview Environment');bpy.context.scene.collection.children.link(col)
    parent=bpy.data.objects.new('Preview pavement',None);col.objects.link(parent);g.finish(col,parent)
    cut_opening(root,list(parent.children))
    for f in list(bpy.data.fonts):
        if f.users==0 and f.name!='Bfont':bpy.data.fonts.remove(f)
    bpy.ops.file.pack_all();(out/'blend').mkdir(exist_ok=True)
    path=out/'blend'/('subway_'+args.variant+'.blend');bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True)
    metrics={'build_save_seconds':time.perf_counter()-start,'blend_bytes':path.stat().st_size,'objects':len(bpy.data.objects),'vertices':sum(len(m.vertices) for m in bpy.data.meshes)}
    if args.render!='none':
        for view,loc,target in [('overview',(8,-10,6.5),(0,2.6,1)),('entrance',(2.7,-5,2.1),(0,1.7,.4)),('detail',(.4,-1.8,1.7),(0,3,-1) if args.variant=='stairs' else (0,.1,1.3))]:
            camera.location=loc;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
            bpy.context.scene.render.filepath=str(out/'renders'/f'{args.variant}_{view}.png');t=time.perf_counter();bpy.ops.render.render(write_still=True);metrics[view+'_render_seconds']=time.perf_counter()-t
    (out/'renders'/f'{args.variant}_metrics.json').write_text(json.dumps(metrics,indent=2))
    print('SUBWAY_METRICS',json.dumps(metrics))

if __name__=='__main__':main()
