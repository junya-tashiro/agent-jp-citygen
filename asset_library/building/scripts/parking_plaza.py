"""Raised landscaped site with a detached trench leading below the plaza."""
import bpy,json,math
from .geometry import Geometry
from .details import planter,text


def subtract(col,targets,bounds,matrix=None):
    x0,y0,z0,x1,y1,z1=bounds
    g=Geometry();g.box('black',((x0+x1)/2,(y0+y1)/2,(z0+z1)/2),(x1-x0,y1-y0,z1-z0))
    cutter=g.finish(col,None,'Temporary void')[0]
    cutter.modifiers.clear()
    if matrix is not None:cutter.matrix_world=matrix@cutter.matrix_world
    for obj in targets:
        if obj.type!='MESH':continue
        # Preserve the immutable geometry cache even before another instance exists.
        obj.data=obj.data.copy()
        mod=obj.modifiers.new('Site excavation','BOOLEAN');obj.modifiers.move(len(obj.modifiers)-1,0);mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.context.view_layer.objects.active=obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    mesh=cutter.data;bpy.data.objects.remove(cutter,do_unlink=True)
    if mesh.users==0:bpy.data.meshes.remove(mesh)


def excavate_context(root,objects,kerbs=()):
    if 'site_cutouts_json' not in root:return
    bpy.context.view_layer.update()
    col=objects[0].users_collection[0] if objects else bpy.context.scene.collection
    for bounds in json.loads(root['site_cutouts_json']):
        subtract(col,objects,bounds,root.matrix_world)
        if kerbs:
            x0,y0,_,x1,_,_=bounds
            subtract(col,kerbs,(x0,y0-10,-.5,x1,y0,.5),root.matrix_world)


def strip(g,key,x,width,profile,thick=.16):
    for (ya,za),(yb,zb) in zip(profile,profile[1:]):
        verts=[(xx,yy,zz-dz) for dz in (0,thick) for xx,yy,zz in ((x-width/2,ya,za),(x+width/2,ya,za),(x+width/2,yb,zb),(x-width/2,yb,zb))]
        g.mesh(key,verts,[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])


def raised_site(col,root,spec,d):
    rise=d.site_height;side=-1 if d.parking_side=='left' else 1
    # Everything belonging to the building sits on the raised plaza.
    for obj in list(root.children):obj.location.z+=rise
    front=-d.depth/2-22;back=d.depth/2+4;left=-d.width/2-6;right=d.width/2+6
    x=side*d.width*.27;lane=6.4;bottom=rise-3.25;portal=front+16;end=front+37
    ground=Geometry();ground.box('concrete',((left+right)/2,(front+back)/2,(rise-3.5)/2),(right-left,back-front,rise+3.5))
    ground.box('paving',(0,(front+back)/2,rise-.055),(right-left,back-front,.11))
    objects=ground.finish(col,root,'Raised site')
    # Open air approach, then a tunnel under the raised landscape, away from the facade.
    cut1=(x-lane/2,front-.1,-3.6,x+lane/2,portal,rise+1)
    cut2=(x-lane/2,portal-.01,-3.6,x+lane/2,end,rise-.28)
    subtract(col,objects,cut1);subtract(col,objects,cut2)
    g=Geometry();profile=[(front,0),(front+2,0),(front+5,bottom*.13),(front+15,bottom),(end,bottom)]
    strip(g,'roof',x,lane,profile)
    # Road center and drain across the level apron.
    strip(g,'amber',x,.10,[(y,z+.012) for y,z in profile],.008)
    for j in range(33):g.box('dark_metal',(x-lane/2+.08+j*(lane-.16)/32,front+1.1,.007),(.045,.35,.018))
    for xx in (x-lane/2-.13,x+lane/2+.13):
        g.box('granite',(xx,(front+portal)/2,(rise+bottom)/2),(.24,portal-front,rise-bottom))
        g.box('pale_stone',(xx,(front+portal)/2,rise+.035),(.32,portal-front,.07))
    g.box('dark_metal',(x,portal-.025,rise-.12),(lane,.12,.24))
    g.box('white',(x,portal-.095,rise-.11),(lane-.2,.025,.19))
    text(col,root,'P   IN / OUT   2.6 m',(x,portal-.12,rise-.11),.16,lane-.4,key='dark_metal')
    # Ceiling luminaires continue visibly into the tunnel.
    for yy in (portal+1,portal+5,portal+9,portal+15):
        g.box('warm_light',(x,yy,rise-.34),(3.6,.18,.055))
    # Equipment is recessed behind the entrance; clear lanes on each side.
    for xx in (x-2,x+2):
        g.box('amber',(xx,portal+2,bottom+.62),(.42,.40,1.24))
        g.box('black',(xx,portal+1.78,bottom+.88),(.26,.035,.25))
    g.box('white',(x-1.5,portal+2,bottom+1.12),(2.6,.08,.08))
    for j in range(6):g.box('product_red',(x-2.55+j*.42,portal+1.95,bottom+1.12),(.18,.025,.08))
    # A continuous stepped plinth opens the entire site towards its surroundings.
    stair_x=-side*d.width*.22
    steps=round(rise/.15);tread=.34;run=steps*tread
    rx=-side*(d.width/2+4.2)
    stair_openings=sorted([(x-3.33,x+3.33),(rx-1.10,rx+1.10)])
    stair_samples=[]
    for i in range(steps):
        margin=run-i*tread;z=rise*(i+1)/steps
        xa,xb=left-margin,right+margin;ya,yb=front-margin,back+margin
        # Front strips stop at the level vehicle and accessible approaches.
        cursor=xa
        for lo,hi in stair_openings+[(xb,xb)]:
            if lo>cursor:g.box('granite',((cursor+lo)/2,ya+tread/2,z/2),(lo-cursor,tread,z))
            cursor=max(cursor,hi)
        g.box('granite',((xa+xb)/2,yb-tread/2,z/2),(xb-xa,tread,z))
        for xx in (xa+tread/2,xb-tread/2):g.box('granite',(xx,(ya+yb)/2,z/2),(tread,yb-ya-2*tread,z))
        stair_samples.extend([(0,ya+tread/2,z),(0,yb-tread/2,z),(xa+tread/2,0,z),(xb-tread/2,0,z)])
    strip(g,'roof',x,lane,[(front-run,0),(front,0)])
    strip(g,'paving',rx,2.1,[(front-run,0),(front,0)])
    root['perimeter_stair_samples_json']=json.dumps(stair_samples)
    root['perimeter_stair_run']=run
    # Gentle accessible route on the edge opposite the vehicle approach.
    rx=-side*(d.width/2+4.2);ramp_run=rise*15
    subtract(col,objects,(rx-1.05,front-.1,-.1,rx+1.05,front+ramp_run,rise+.1))
    strip(g,'paving',rx,2.1,[(front,0),(front+ramp_run,rise)])
    for xx in (rx-1,rx+1):
        g.tube(spec.frame,(xx,front,.95),(xx,front+ramp_run,rise+.95),.032)
        for i in range(13):g.tube(spec.frame,(xx,front+i*ramp_run/12,rise*i/12),(xx,front+i*ramp_run/12,rise*i/12+.95),.025)
    # Garden above the portal, and planting along the raised forecourt.
    planter(g,x,portal+2,rise,8.0,2.4)
    for px in (stair_x-5,stair_x+5):planter(g,px,front+9,rise,2.0,2.0)
    from .landscape import place_stock
    for j,px in enumerate((x-5.6,x+5.6)):
        planter(g,px,front+11,rise,2.6,6.2)
        place_stock(col,root,'tree',j,(px,front+11,rise+.55))
    sign_x=x-side*(lane/2+1)
    g.box('dark_metal',(sign_x,front+1.7,rise+1.2),(.65,.30,2.4))
    text(col,root,'P',(sign_x,front+1.53,rise+1.8),.52,.55)
    text(col,root,'IN',(sign_x,front+1.53,rise+1.17),.25,.50)
    g.finish(col,root,'Plaza stairs and parking approach')
    from .plaza_guard import create_guards
    create_guards(col,root,spec,d)
    root['site_cutouts_json']=json.dumps([(x-lane/2,front-run,-3.6,x+lane/2,end,.01)])
    root['site_bounds_json']=json.dumps([left-run,front-run,right+run,back+run]);root['site_height']=rise
    root['parking_profile_json']=json.dumps(profile);root['parking_center_x']=x
    root['height']+=rise
    sections=json.loads(root['sections_json'])
    for section in sections:
        section['z']+=rise
        if 'floor_levels' in section:section['floor_levels']=[z+rise for z in section['floor_levels']]
    root['sections_json']=json.dumps(sections)
