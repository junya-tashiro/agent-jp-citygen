"""Twenty urban building families with shared, repeatable facade modules."""
import bpy,sys,math,json,time,argparse
from pathlib import Path
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from asset_library.building.scripts.catalog import CATALOG,get_spec
from asset_library.building.scripts.geometry import Geometry,Face,footprint
from asset_library.building.scripts.facade import floor_module
from asset_library.building.scripts.details import podium,roof,planter,text
from asset_library.building.scripts.materials import material
from mathutils import Vector


def create_building(kind='building_01',seed=11,detail='high',name=None,design=None,include_forecourt=True):
    """Origin is ground-level centre; front faces -Y. Returns one parent root.

    detail='medium' removes small joints and blind slats; silhouette, openings,
    floor plates and the complete street-level composition stay intact.
    """
    spec=get_spec(kind)
    if detail not in ('high','medium'):raise ValueError('detail must be high or medium')
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError('seed must be an integer')
    from asset_library.building.scripts.design import PROFILES
    if spec.family in PROFILES:
        from asset_library.building.scripts.recipe_builder import create_recipe
        return create_recipe(spec,seed,detail,name,design,include_forecourt=include_forecourt)
    if not include_forecourt:raise ValueError('Forecourt control is supported by recipe families 11–26')
    if design is not None:raise ValueError('Design overrides are supported by recipe families 11–26')
    col=bpy.data.collections.new(name or spec.key);bpy.context.scene.collection.children.link(col)
    root=bpy.data.objects.new(name or spec.title,None);col.objects.link(root);root['asset_type']='urban_building';root['spec_json']=json.dumps(asdict(spec));root['seed']=seed;root['detail']=detail
    w,d=spec.width,spec.depth;h=spec.floor_height;base=spec.base_height
    family=spec.family;g=Geometry();sections=[]
    ch=3.0 if family in ('chamfer_tower','ribbon') else 0
    poly=footprint(w,d,ch)
    podium(g,col,root,poly,base,spec.wall,spec.frame,spec.title,seed,portico=family in ('fin_tower','split_tower'),shops=family!='fin_tower',style=family)
    total_levels=spec.floors-(2 if base>8 else 1)
    def section(width,depth,z,count,style,offset=(0,0),chamfer=0,bay=3.0,rear=False):
        p=footprint(width,depth,chamfer);nvariants=3 if detail=='high' else 1
        modules=[floor_module(p,h,style,spec.wall,spec.frame,spec.glass,seed,variant=i,bay=bay,rear_solid=rear,detail=detail) for i in range(nvariants)]
        for i in range(count):modules[i%nvariants].finish(col,root,'Floor module '+style,(offset[0],offset[1],z+i*h))
        sections.append(dict(width=width,depth=depth,z=z,count=count,style=style,offset=offset,chamfer=chamfer))
        return z+count*h
    def crown(width,depth,z,offset=(0,0),chamfer=0,screen=True):
        r=Geometry();p=footprint(width,depth,chamfer);roof(r,p,z,width,depth,seed,spec.frame,occupied=width<25,layout=family)
        if screen and width>25:
            # Roof plant is hidden by a louver enclosure, distinct from office glazing.
            sw=width*.60;sd=depth*.60
            for a,b in zip(footprint(sw,sd),footprint(sw,sd)[1:]+footprint(sw,sd)[:1]):
                f=Face(r,a,b)
                for j in range(16):f.box(spec.frame,f.length/2,0,z+.65+j*.20,f.length,.07,.075)
                for i in range(max(2,int(f.length/2))):f.box(spec.frame,(i+.5)*f.length/max(2,int(f.length/2)),0,z+2.1,.07,.10,3.3)
        r.finish(col,root,'Roof assembly',(offset[0],offset[1],0))
    def terrace(width,depth,z,chamfer=0):
        # Continuous rooftop ground and perimeter without filling the upper tower.
        p=footprint(width,depth,chamfer);g.prism('paving',p,z-.06,.10)
        for a,b in zip(p,p[1:]+p[:1]):
            f=Face(g,a,b);f.box(spec.frame,f.length/2,-.06,z+1.20,f.length,.075,.075)
            for i in range(max(2,round(f.length/1.5))+1):
                u=i*f.length/max(2,round(f.length/1.5));f.box(spec.frame,u,-.06,z+.62,.055,.075,1.20)
            f.box('clear',f.length/2,-.08,z+.66,f.length-.08,.02,.98)
        for x in (-width*.36,width*.36):planter(g,x,-depth/2+1.0,z+.05,3,.85)
    if family=='fin_tower':
        terrace(w,d,base)
        top=section(35,25,base, total_levels,'fins',(0,2),bay=1.65)
        crown(35,25,top,(0,2))
        # Tall fins continue above the recessed crown for a legible skyline.
        for side in (-1,1):
            for i in range(22):g.box(spec.frame,(-17.5+i*35/21,side*12.5+2,top+1.3),(.115,.48,2.6))
    elif family=='stone_tower':
        z=section(w,d,base,5,'stone_grid',bay=3.7)
        terrace(w,d,z)
        z=section(w-8,d-6,z,17,'stone_grid',(0,2),bay=3.5)
        g.box('pale_stone',(0,2,z-.10),(w-7.5,d-5.5,.26))
        z=section(w-14,d-10,z,total_levels-22,'curtain',(0,3),bay=2.4)
        crown(w-14,d-10,z,(0,3));top=z
        for zc in (base,base+5*h):
            for a,b in zip(poly,poly[1:]+poly[:1]):
                f=Face(g,a,b)
                for dz,depth in ((-.15,.45),(.04,.60),(.16,.42)):f.box(spec.wall,f.length/2,.1,zc+dz,f.length,depth,.10)
    elif family=='split_tower':
        terrace(w,d,base)
        top=section(23,26,base,total_levels,'curtain',(-12,2),bay=1.6)
        top2=section(19,29,base,total_levels-7,'dark_grid',(12,1),bay=1.6)
        crown(23,26,top,(-12,2));crown(19,29,top2,(12,1))
        for zz in (base+9*h,base+21*h):
            g.box('silver',(-12,2,zz),(23.2,26.2,.48))
        # Narrow bridging spine stops below the taller roof.
        g.box('dark_metal',(.25,6,base+(top2-base)/2),(1.0,12,top2-base))
    elif family=='chamfer_tower':
        z=section(w,d,base,3,'dark_grid',chamfer=ch,bay=2.8)
        terrace(w,d,z,ch)
        top=section(w-6,d-4,z,total_levels-3,'dark_grid',(0,1),chamfer=2.5,bay=1.9)
        crown(w-6,d-4,top,(0,1),2.5)
        for zz in (base+3*h,top):
            p=footprint(w if zz<top else w-6,d if zz<top else d-4,ch if zz<top else 2.5)
            for a,b in zip(p,p[1:]+p[:1]):
                a=(a[0],a[1]+(1 if zz==top else 0));b=(b[0],b[1]+(1 if zz==top else 0))
                f=Face(g,a,b);f.box(spec.frame,f.length/2,.12,zz-.1,f.length,.35,.35)
    elif family=='wide_office':
        top=section(w,d,base,total_levels,'ribbon',bay=2.8)
        crown(w,d,top)
        # Three vertical stair/service zones break the long horizontal facade.
        for x in (-w*.33,0,w*.33):
            g.box('pale_stone',(x,-d/2-.05,base+(top-base)/2),(.72,.55,top-base))
            for z in (base+.5,top-.25):g.box('pale_stone',(x,-d/2-.1,z),(1.2,.65,.35))
        # Rooftop pavilion and a pergola, placed away from central plant.
        for i in range(10):g.box('bronze',(w*.28,-d*.16+i*.44,top+2.5),(9,.12,.14))
        for x in (w*.28-4.4,w*.28+4.4):
            for y in (-d*.16,-d*.16+3.96):g.box('bronze',(x,y,top+1.25),(.12,.12,2.5))
    elif family=='pencil':
        top=section(w-3,d,base,total_levels,'curtain',(1.5,0),bay=1.8,rear=True)
        g.box('dark_metal',(-w/2+1.48,0,(base+top)/2),(2.96,d,top-base))
        for j in range(int((top-base)/.27)):
            g.box('silver',(-w/2+1.48,-d/2-.02,base+.1+j*.27),(2.6,.14,.042))
        crown(w,d,top)
        g.box('silver',(-w/2+.10,-d/2,top+1.0),(.20,.25,2.0))
    elif family=='punched':
        z=section(w,d,base,total_levels-2,'punched',bay=3.3,rear=True)
        terrace(w,d,z)
        top=section(w-4,d-4,z,2,'punched',(1,1.5),bay=3.1)
        crown(w-4,d-4,top,(1,1.5))
        # A thin party wall and exposed rainwater pipe at the less public side.
        g.tube('dark_metal',(w/2+.18,d*.3,.25),(w/2+.18,d*.3,z+.3),.075)
        for zz in range(2,int(z),3):g.box('dark_metal',(w/2+.10,d*.3,zz),(.24,.12,.06))
    elif family=='ribbon':
        z=section(w,d,base,total_levels-1,'ribbon',chamfer=ch,bay=2.3)
        top=section(w-4,d-3,z,1,'ribbon',(0,1),chamfer=2,bay=2.3)
        terrace(w,d,z,ch);crown(w-4,d-3,top,(0,1),2)
        for zz in (base,base+4*h):
            for a,b in zip(poly,poly[1:]+poly[:1]):
                f=Face(g,a,b);f.box(spec.wall,f.length/2,.11,zz-.15,f.length,.38,.22)
    elif family=='balcony':
        top=section(w,d,base,total_levels,'balcony',bay=3.2)
        crown(w,d,top)
        for x in (-w/2,w/2):g.box('concrete',(x,-d/2-.04,(base+top)/2),(.18,.30,top-base))
    elif family=='brick':
        top=section(w,d,base,total_levels,'brick',bay=3.9)
        crown(w,d,top,screen=False)
        for x in (-w/2+.15,w/2-.15):
            g.box('dark_metal',(x,-d/2-.24,(base+top)/2),(.18,.25,top-base))
        # Bracing is anchored to continuous posts and floor-level beams.
        bw=w/round(w/3.9)
        for x in (-bw*1.5,-bw*.5,bw*.5,bw*1.5):
            g.box('dark_metal',(x,-d/2-.28,(base+top)/2),(.14,.22,top-base))
        for j in range(total_levels+1):
            z=base+j*h
            for x in (-bw,bw):g.box('dark_metal',(x,-d/2-.28,z),(bw+.14,.22,.18))
        for z in (base+h,base+3*h):
            for x in (-bw,bw):
                a=(x-bw/2,-d/2-.28,z+.13);b=(x+bw/2,-d/2-.28,z+h-.13)
                g.tube('dark_metal',a,b,.075,8)
                for pt in (a,b):
                    g.box('dark_metal',pt,(.35,.27,.35))
                    for dx in (-.10,.10):
                        for dz in (-.10,.10):g.tube('silver',(pt[0]+dx,pt[1]-.15,pt[2]+dz),(pt[0]+dx,pt[1]-.17,pt[2]+dz),.026,8)
        for z in (base,top):g.box('pale_stone',(0,-d/2-.10,z-.08),(w+.24,.50,.28))
    else:raise ValueError(family)
    g.finish(col,root,'Base and authored details')
    root['sections_json']=json.dumps(sections);root['height']=top+5.6;root['footprint_json']=json.dumps(poly)
    root['module_instances']=sum(s['count'] for s in sections)
    from types import SimpleNamespace
    from asset_library.building.scripts.interiors import furnish
    programs=('business','hospitality','cafe','gallery')
    furnish(col,root,spec,SimpleNamespace(key=spec.key,seed=seed,base_floors=1,ground_height=base,floor_height=h,width=w,depth=d,radius=ch,terrace_depth=0,parking=False,interior_program=programs[(int(spec.key.rsplit('_',1)[1])+seed)%4]))
    return root


def preview_environment(root,spec):
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT';scene.eevee.taa_render_samples=32;scene.eevee.use_raytracing=True
    scene.render.image_settings.file_format='PNG';scene.render.resolution_percentage=100;scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.35
    world=bpy.data.worlds.new('Urban soft daylight');scene.world=world;world.use_nodes=True
    next(n for n in world.node_tree.nodes if n.type=='BACKGROUND').inputs[0].default_value=(.55,.66,.76,1);next(n for n in world.node_tree.nodes if n.type=='BACKGROUND').inputs[1].default_value=.38
    sky=world.node_tree.nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_elevation=math.radians(38);sky.sun_rotation=math.radians(135);sky.sun_disc=False
    world.node_tree.links.new(sky.outputs[0],next(n for n in world.node_tree.nodes if n.type=='BACKGROUND').inputs[0])
    next(n for n in world.node_tree.nodes if n.type=='BACKGROUND').inputs[1].default_value=.18
    sun=bpy.data.lights.new('Afternoon sun','SUN');sun.energy=2.7;sun.angle=math.radians(12)
    o=bpy.data.objects.new('Afternoon sun',sun);scene.collection.objects.link(o);o.rotation_euler=(math.radians(28),math.radians(-24),math.radians(-28))
    col=bpy.data.collections.new('Preview Environment');scene.collection.children.link(col)
    ground=Geometry();ground.box('paving',(0,0,-.28),(2000,2000,.5))
    # Stone forecourt joint lines, kerb and carriageway establish scale.
    w,d=spec.width,spec.depth
    front=-d/2
    if 'site_bounds_json' in root:
        bounds=json.loads(root['site_bounds_json']);w=bounds[2]-bounds[0];front=bounds[1]
    ground.box('granite',(0,front-5.5,-.10),(w+20,.23,.30));ground.box('black',(0,front-11,-.08),(w+80,11,.14))
    for i in range(int((w+18)/1.5)):
        ground.box('mortar',(-w/2-9+i*1.5,front-2.7,-.021),(.009,5.3,.009))
    for j in range(4):ground.box('mortar',(0,front-.5-j*1.4,-.021),(w+18,.01,.009))
    for x in range(-int(w/2)-20,int(w/2)+20,7):ground.box('white',(x,front-11,.003),(3.2,.12,.012))
    for side in (-1,1):
        x=side*(w/2+2.8);y=front-4
        ground.tube('dark_metal',(x,y,0),(x,y,5.7),.07,10)
        ground.box('dark_metal',(x+.40,y,5.7),(1.05,.26,.13))
        ground.box('warm_light',(x+.40,y,5.622),(.82,.18,.025))
    context=ground.finish(col,None,'Preview streetscape')
    from asset_library.building.scripts.parking_plaza import excavate_context
    excavate_context(root,[o for o in context if o.get('building_part')=='paving'],[o for o in context if o.get('building_part')=='granite'])
    data=bpy.data.cameras.new('Building camera');cam=bpy.data.objects.new(data.name,data);scene.collection.objects.link(cam);scene.camera=cam
    return cam

def set_camera(cam,pos,target,lens=48,ortho=None):
    cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=lens
    if ortho:cam.data.type='ORTHO';cam.data.ortho_scale=ortho
    else:cam.data.type='PERSP'

def build_one(key,render=True):
    spec=get_spec(key);bpy.ops.wm.read_factory_settings(use_empty=True);start=time.perf_counter()
    root=create_building(key)
    from asset_library.building.scripts.catalog import BuildingSpec
    spec=BuildingSpec(**json.loads(root['spec_json']));cam=preview_environment(root,spec);height=root['height']
    out=ROOT/'asset_library/building';(out/'blend').mkdir(parents=True,exist_ok=True);(out/'renders').mkdir(exist_ok=True)
    scene=bpy.context.scene;scene.render.resolution_x=1100;scene.render.resolution_y=1300
    set_camera(cam,(spec.width*1.45,-spec.depth*1.9,height*.67),(0,0,height*.45),ortho=max(height*1.18,spec.width*1.8))
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'blend'/f'{key}.blend'),compress=True)
    objects=[o for o in root.children if o.type=='MESH'];meshes=set(o.data for o in objects)
    stats={'key':key,'height_m':height,'objects':len(objects),'unique_meshes':len(meshes),'mesh_instances':sum(m.users for m in meshes),'unique_vertices':sum(len(m.vertices) for m in meshes),'evaluated_base_vertices':sum(len(o.data.vertices) for o in objects),'blend_bytes':(out/'blend'/f'{key}.blend').stat().st_size,'build_save_seconds':time.perf_counter()-start,'views':{}}
    if render:
        for view in ('overview','street'):
            if view=='street':
                scene.render.resolution_x=1400;scene.render.resolution_y=1000
                if 'site_bounds_json' in root:
                    front=json.loads(root['site_bounds_json'])[1];set_camera(cam,(spec.width*.6,front-38,17),(0,front+12,3),lens=36)
                elif spec.width>30:set_camera(cam,(spec.width*.65,-spec.depth/2-27,7.5),(0,-spec.depth/2,6.6),lens=36)
                else:set_camera(cam,(spec.width*.80,-spec.depth/2-19,4.8),(0,-spec.depth/2,5.2),lens=36)
            scene.render.filepath=str(out/'renders'/f'{key}_{view}.png');t=time.perf_counter();bpy.ops.render.render(write_still=True);stats['views'][view]=time.perf_counter()-t
    (out/'renders'/f'{key}_metrics.json').write_text(json.dumps(stats,indent=2));print('BUILDING_COMPLETE',json.dumps(stats),flush=True)
    return stats

def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',default='all');p.add_argument('--no-render',action='store_true');args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    selected=CATALOG if args.kind=='all' else tuple(get_spec(key) for key in args.kind.split(','))
    for spec in dict.fromkeys(selected):build_one(spec.key,not args.no_render)
if __name__=='__main__':main()
