"""Rectangular urban flap-lock parking; Blender 4.5+, EEVEE, metre units."""
from pathlib import Path
import argparse,json,math,sys,time,random
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from asset_library.coin_parking.scripts import components as c
from asset_library.coin_parking.scripts.layout import plan,validate
from asset_library.coin_parking.scripts.details import rail,cone,cone_bar,payment,signs,weather


def palette():
    c.M.clear();c.JP=c.font_find();c.LATIN=c.JP
    c.M.update({m['coin_parking_material_key']:m for m in bpy.data.materials if m.get('coin_parking_material_key')})
    if len(c.M)==16:return c.M
    c.M.clear()
    c.asphalt();c.worn_paint()
    for name,color,rough,metal,grain in [
        ('concrete',(.40,.39,.36),.88,0,90),('zinc',(.48,.52,.53),.36,.8,180),
        ('steel',(.12,.14,.14),.45,.7,120),('orange',(.9,.19,.025),.4,0,0),
        ('yellow',(.96,.60,.025),.4,0,0),('navy',(.015,.055,.062),.45,0,0),
        ('white',(.87,.86,.80),.45,0,0),('black',(.008,.013,.014),.55,0,0),
        ('rubber',(.022,.025,.023),.88,0,150),('lcd',(.24,.42,.36),.3,0,0),
        ('red',(.62,.022,.012),.5,0,0),('bitumen',(.02,.02,.019),.9,0,0),
        ('paver',(.34,.35,.34),.88,0,130),('glass',(.035,.055,.06),.2,.45,0)]:
        c.mat(name,color,rough,metal,grain,.0004)
    for name in ('orange','yellow','navy','white'):
        weather(c.M[name],.20 if name=='orange' else .12)
    for key,material in c.M.items():material['coin_parking_material_key']=key
    return c.M


def lock():
    m=c.M
    c.prism_y('steel ramp base',0,0,1.08,[(-.24,.012),(.24,.012),(.24,.026),(.14,.048),(-.14,.048),(-.24,.026)],m['navy'])
    c.box('drive unit sealed motor housing',(-.445,0,.11),(.23,.42,.20),m['navy'],.023)
    c.box('drive unit removable lid',(-.445,0,.218),(.24,.44,.018),m['zinc'],.012)
    c.cyl('pivot shaft',(0,.13,.075),.028,.88,m['zinc'],32,(1,0,0))
    plate=c.box('hinged lock plate',(0,-.015,.064),(.78,.30,.026),m['yellow'],.009)
    # Every generated bay is vacant, so the hinged plate remains lowered.
    for x in (-.34,-.17,0,.17,.34):
        c.box('raised anti slip rib',(x,-.015,.079),(.012,.24,.004),m['zinc'],.002)
    for x in (-.48,.48):
        for y in (-.19,.19):c.bolt((x,y,.05))
    c.box('sensor window',(.43,0,.051),(.095,.12,.012),m['black'],.006)
    c.text('lock caution','乗越注意',(-.445,-.213,.135),.029,m['white'],width=.195)


def wheelstop():
    m=c.M
    c.prism_y('cast concrete wheel stop',0,0,.58,[(-.08,.008),(.08,.008),(.07,.095),(.045,.13),(-.045,.13),(-.08,.085)],m['concrete'])
    for x in (-.19,.19):
        c.box('amber reflector',(x,-.082,.074),(.11,.006,.035),m['yellow'],.004)
        c.cyl('fixing recess',(x,0,.13),.017,.005,m['black'])
        c.bolt((x,0,.13))


def prototype(name,builder):
    existing=bpy.data.collections.get(name)
    if existing is not None and existing.get('parking_equipment_version')==2:return existing
    old=c.ACTIVE;coll=bpy.data.collections.new(name);c.ACTIVE=coll;builder();c.ACTIVE=old;coll['parking_equipment_version']=2
    return coll


def instance(source,name,x,y,z=0,angle=0):
    o=bpy.data.objects.new(name,None);o.instance_type='COLLECTION';o.instance_collection=source
    c.ACTIVE.objects.link(o);o.location=(x,y,z);o.rotation_euler.z=math.radians(angle);return o


def perimeter(layout,rail_source,cone_source,bar_source):
    w,d=layout.width,layout.depth
    rng=random.Random(f"parking-perimeter-v2:{w:.4f}:{d:.4f}")
    pairs=0
    def run(a,b):
        nonlocal pairs
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        count=int(length/1.9)
        if not count:return
        step=length/count
        angle=math.degrees(math.atan2(dy,dx));ux,uy=dx/length,dy/length
        i=0
        while i<count:
            if i+1<count and rng.random()<.15:
                t=(i+1)/count;cx,cy=a[0]+dx*t,a[1]+dy*t
                for offset in (-.945,.945):
                    instance(cone_source,'replacement cone',cx+ux*offset,cy+uy*offset)
                instance(bar_source,'paired cone connecting bar',cx,cy,angle=angle)
                pairs+=1;i+=2
            else:
                t=(i+.5)/count
                instance(rail_source,'orange perimeter U rail',a[0]+dx*t,a[1]+dy*t,angle=angle)
                i+=1
    run((.22,.35),(.22,d-.22));run((w-.22,.35),(w-.22,d-.22));run((.22,d-.22),(w-.22,d-.22))
    a=layout.entrance_x-layout.entrance_width/2;b=layout.entrance_x+layout.entrance_width/2
    # A 1.4 m pedestrian opening at the payment face; only the 4.2 m
    # central driveway is vehicle-accessible.
    px,_=layout.payment
    for lo,hi in [(.3,a-.25),(b+.25,w-.3)]:
        for start,end in [(lo,min(hi,px-.70)),(max(lo,px+.70),hi)]:
            if end>start:run((start,.18),(end,.18))
    c.ACTIVE['cone_bar_replacements']=pairs
    c.ACTIVE['rail_pair_replacement_probability']=.15
    # Short guarded frontage portions use striped removable poles.
    for x in (.2,w-.2):
        c.cyl('frontage removable bollard',(x,.16,.40),.047,.80,c.M['orange'])
        for z in (.53,.68):c.cyl('bollard white band',(x,.16,z),.048,.06,c.M['white'])


def ground(layout):
    w,d=layout.width,layout.depth;m=c.M
    c.box('rectangular asphalt lot',(w/2,d/2,-.08),(w,d,.16),m['asphalt / weathered aggregate'])
    # Irregular fine cracks retain the original scanned surface quality.
    rng=random.Random(73)
    for i in range(max(2,int(w*d/65))):
        x=rng.uniform(.5,w-.5);y=rng.uniform(.5,d-.5);points=[]
        for j in range(8):
            points.append((x,y,.001));x=max(.1,min(w-.1,x+rng.uniform(-.19,.22)));y=max(.1,min(d-.1,y+rng.uniform(.04,.21)))
        c.tube('irregular asphalt hairline crack',points,.0014,m['bitumen'])


def build_asset(width=13.2,depth=17.0):
    layout=plan(width,depth);validate(layout);palette()
    asset=c.collection('COIN PARKING | rectangular flap lot');c.ACTIVE=asset
    asset['width_m']=width;asset['depth_m']=depth;asset['capacity']=layout.capacity
    asset['layout_kind']=layout.kind;asset['entrance_center']=[layout.entrance_x,0,0]
    asset['entrance_width_m']=layout.entrance_width;asset['front']='-Y; datum z=0'
    ground(layout)
    locks=prototype('SHARED | lowered empty-bay flap lock',lock)
    stops=prototype('SHARED | concrete wheel stop',wheelstop)
    rails=prototype('SHARED | orange U rail',lambda:rail('orange bent tube',1.55))
    cones=prototype('SHARED | cone',cone)
    bars=prototype('SHARED | standard cone bar',cone_bar)
    for bay in layout.bays:
        a=math.radians(bay.rotation)
        def xy(x,y):return bay.x+math.cos(a)*x-math.sin(a)*y,bay.y+math.sin(a)*x+math.cos(a)*y
        for xx in (-1.25,1.25):
            x,y=xy(xx,0);o=c.box('bay boundary white paint',(x,y,.002),( .10,5.0,.003),c.M['aged thermoplastic white']);o.rotation_euler.z=a
        x,y=xy(0,2.47);o=c.box('bay rear white paint',(x,y,.002),(2.5,.10,.003),c.M['aged thermoplastic white']);o.rotation_euler.z=a
        x,y=xy(0,-1.82);o=c.text('bay number',str(bay.number),(x,y,.005),.64,c.M['aged thermoplastic white'],ground=True);o.rotation_euler.z=a
        x,y=xy(-.805,-.25);o=instance(locks,f'Bay {bay.number:02d} flap lock',x,y,angle=bay.rotation);o['bay_number']=bay.number;o['flap_state']='lowered / vacant'
        for xx in (-.73,.73):
            x,y=xy(xx,1.75);instance(stops,'rear tire stop',x,y,angle=bay.rotation)
        # Visible sawcut around the vehicle detection loop, inside each bay.
        points=[(*xy(x,y),.001) for x,y in [(-.83,-1.12),(.83,-1.12),(.83,.65),(-.83,.65),(-.83,-1.12)]]
        c.tube('sealed induction loop sawcut',points,.004,c.M['bitumen'])
    payment(*layout.payment);signs(layout);perimeter(layout,rails,cones,bars)
    length=(layout.entrance_width-.30)*2/3
    right=layout.entrance_x+layout.entrance_width/2-.15
    c.box('exit stop line',(right-length/2,.5,.002),(length,.20,.003),c.M['aged thermoplastic white'])
    # Metadata connects the lot mouth to a street generator's driveway cutout.
    return asset,layout


def context(layout):
    c.ACTIVE=c.collection('CONTEXT | sidewalk crossover and street');m=c.M;w=layout.width
    a=layout.entrance_x-layout.entrance_width/2;b=layout.entrance_x+layout.entrance_width/2
    # Flat accessible pedestrian strip; the curb ramp is on its carriageway side.
    c.box('continuous sidewalk',(w/2,-1.65,-.075),(w+4,3.3,.15),m['paver'])
    for x in [i*.5-2 for i in range(int((w+4)/.5)+1)]:
        c.box('sidewalk paving joint',(x,-1.65,.0005),(.007,3.3,.001),m['concrete'])
    for y in (-.55,-1.1,-1.65,-2.2,-2.75):c.box('sidewalk course joint',(w/2,y,.0005),(w+4,.007,.001),m['concrete'])
    c.box('driveway across sidewalk',(layout.entrance_x,-1.25,.001),(layout.entrance_width,2.5,.002),m['concrete'])
    c.mesh_obj('lowered driveway curb ramp',[(a,-2.5,.002),(b,-2.5,.002),(b,-3.3,-.13),(a,-3.3,-.13)],[(0,1,2,3)],m['concrete'])
    for left,right in [(-2,a),(b,w+2)]:
        for i in range(math.ceil((right-left)/.6)):
            x0=left+i*.6;x1=min(right,x0+.592)
            if x1>x0:c.box('curb outside single cutout',((x0+x1)/2,-3.22,-.057),((x1-x0),.16,.14),m['concrete'],.008)
    c.box('street carriageway',(w/2,-6.3,-.23),(w+16,6,.20),m['asphalt / weathered aggregate'])
    c.box('street edge line',(w/2,-3.65,-.127),(w+12,.10,.003),m['aged thermoplastic white'])
    # Plain massing stays outside the reusable lot collection.
    c.ACTIVE=c.collection('CONTEXT | optional neighbouring buildings')
    for x in (-3.5,w+3.5):
        c.box('neighbouring urban building',(x,layout.depth*.58,6),(5,layout.depth+4,12),m['paver'],.03)
        for z in (2,5,8,11):
            for y in range(2,int(layout.depth),3):
                c.box('recessed dark office window',(x+(2.51 if x<0 else -2.51),y,z),(.02,1.6,1.8),m['glass'])


def camera(name,loc,target,lens=45,ortho=None):
    d=bpy.data.cameras.new(name);o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o)
    o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();d.lens=lens;d.clip_end=2000
    if ortho:d.type='ORTHO';d.ortho_scale=ortho
    return o


def presentation(layout):
    s=bpy.context.scene;s.render.engine='BLENDER_EEVEE_NEXT';s.eevee.taa_render_samples=32;s.eevee.use_raytracing=True
    s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast'
    s.world=bpy.data.worlds.new('bright daylight');s.world.use_nodes=True
    next(n for n in s.world.node_tree.nodes if n.type=='BACKGROUND').inputs[0].default_value=(.63,.72,.85,1)
    next(n for n in s.world.node_tree.nodes if n.type=='BACKGROUND').inputs[1].default_value=.55
    d=bpy.data.lights.new('afternoon sun','SUN');d.energy=2.5;d.angle=math.radians(12)
    o=bpy.data.objects.new(d.name,d);s.collection.objects.link(o);o.rotation_euler=(.45,-.55,-.5)
    w,h=layout.width,layout.depth;span=max(w,h)
    views={'overview':camera('overview',(w*.5+span*.85,-span*.95,span*.88),(w/2,h*.4,.6),42),
           'top':camera('top',(w/2,h/2,40),(w/2,h/2,0),ortho=max(w,h*4/3)*1.14),
           'entrance':camera('entrance',(layout.entrance_x+3,-7,2.4),(layout.entrance_x,3,1.1),35),
           'payment':camera('payment',(layout.payment[0]+1.8,layout.payment[1]-3.3,2.15),(*layout.payment,1.2),49)}
    bay=layout.bays[0];views['lock']=camera('lock',(bay.x+1.3,bay.y-2.1,1.5),(bay.x,bay.y,.07),52)
    bpy.data.collections['CONTEXT | optional neighbouring buildings'].hide_render=True
    s.camera=views['overview'];s.unit_settings.system='METRIC'
    return views


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--width',type=float,default=13.2);parser.add_argument('--depth',type=float,default=17)
    parser.add_argument('--output',type=Path,default=ROOT);parser.add_argument('--render',choices=['none','preview','final'],default='preview');parser.add_argument('--views',default='overview,top,entrance,payment,lock')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    # Validate before clearing any scene.
    plan(args.width,args.depth)
    bpy.ops.wm.read_factory_settings(use_empty=True);t=time.perf_counter()
    asset,layout=build_asset(args.width,args.depth);context(layout);views=presentation(layout)
    s=bpy.context.scene;s.render.image_settings.file_format='PNG';s.render.resolution_percentage=100
    s.render.resolution_x=1400 if args.render=='final' else 1100;s.render.resolution_y=1050 if args.render=='final' else 825;s.eevee.taa_render_samples=64 if args.render=='final' else 24
    bpy.ops.file.pack_all();args.output.mkdir(parents=True,exist_ok=True);(args.output/'blend').mkdir(exist_ok=True);(args.output/'renders').mkdir(exist_ok=True)
    path=args.output/'blend/coin_parking.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True)
    metrics={'build_save_seconds':time.perf_counter()-t,'blend_bytes':path.stat().st_size,'objects':len(bpy.data.objects),'meshes':len(bpy.data.meshes),'font':c.JP.filepath,'layout':layout.to_dict(),'checks':validate(layout),'render_seconds':{}}
    if args.render!='none':
        for key in args.views.split(','):
            bpy.data.collections['CONTEXT | optional neighbouring buildings'].hide_render=(key!='entrance')
            s.camera=views[key];s.render.filepath=str(args.output/'renders'/f'{key}.png');t=time.perf_counter();bpy.ops.render.render(write_still=True);metrics['render_seconds'][key]=time.perf_counter()-t
    (args.output/'metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False))
    print('PARKING_COMPLETE',json.dumps(metrics,ensure_ascii=False))

if __name__=='__main__':main()
