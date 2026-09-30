"""Reusable furnished lower floors: circulation, service cores and tenant uses."""
import bpy,math,random,json
from .geometry import Geometry
from .details import text,planter


def chair(g,x,y,z,angle=0):
    def box(key,dx,dy,dz,w,d,h):
        c,s=math.cos(angle),math.sin(angle)
        g.box(key,(x+dx*c-dy*s,y+dx*s+dy*c,z+dz),(w,d,h),angle)
    box('fabric',0,0,.47,.48,.48,.11);box('fabric',0,.21,.76,.48,.09,.49)
    for dx in (-.18,.18):
        for dy in (-.18,.18):box('dark_metal',dx,dy,.23,.035,.035,.46)


def table(g,x,y,z,w=1.2,d=.75):
    g.box('wood',(x,y,z+.76),(w,d,.065))
    for dx in (-w*.37,w*.37):
        for dy in (-d*.32,d*.32):g.box('dark_metal',(x+dx,y+dy,z+.37),(.045,.045,.74))


def sofa(g,x,y,z,w=2):
    g.box('fabric',(x,y,z+.30),(w,.80,.48))
    g.box('fabric',(x,y+.34,z+.65),(w,.16,.60))
    for side in (-1,1):g.box('fabric',(x+side*(w/2-.08),y,z+.55),(.16,.82,.43))
    for dx in (-w*.35,w*.35):g.box('dark_metal',(x+dx,y,z+.08),(.08,.60,.16))
    for i in range(3):g.box('fabric',(x+(i-1)*w*.29,y-.05,z+.57),(w*.28,.59,.12))


def shelves(g,x,y,z,w=1.0,length=3.4,detail='high'):
    g.box('white',(x,y,z+.12),(w,length,.24));g.box('white',(x,y,z+.90),(.08,length,1.6))
    for yy in (-length/2,length/2):g.box('silver',(x,y+yy,z+.85),(w,.06,1.7))
    for level in range(4):
        zz=z+.30+level*.38
        g.box('white',(x,y,zz),(w,length,.05))
        for side in (-1,1):
            g.box('amber',(x+side*(w/2-.015),y,zz+.03),(.025,length,.045))
            count=12 if detail=='high' else 6
            for j in range(count):
                color=('product_red','product_blue','cream','product_green')[(j+level)%4]
                g.box(color,(x+side*w*.29,y-length/2+.16+j*(length-.32)/(count-1),zz+.13),(.23,.17,.22))
                if detail=='high':g.box('white',(x+side*w*.415,y-length/2+.16+j*(length-.32)/(count-1),zz+.14),(.01,.09,.09))


def furnish(col,root,spec,d):
    from .street_detail import lobby_finish,occupied_details
    from dataclasses import replace
    if getattr(d,'ground_mode','')=='continuous':
        m=d.masses[0];d=replace(d,width=m.width,depth=m.depth)
    g=Geometry();programs=[];rng=random.Random(f'{d.key}:{d.seed}:rooms')
    for floor in range(1 if getattr(d,'atrium',False) else d.base_floors):
        z=(.205 if getattr(d,'ground_mode','')=='continuous' else .003) if floor==0 else d.ground_height+(floor-1)*d.floor_height+.21
        h=d.base_height if getattr(d,'atrium',False) else d.ground_height if floor==0 else d.floor_height
        front=-d.depth/2+(d.terrace_depth if floor else 0)
        inset=max(1.65,getattr(d,'podium_radius',d.radius)*.70+.7)
        left=-d.width/2+inset;right=d.width/2-inset
        if floor==0 and d.width<10:right=d.width/2-2.2
        width=right-left;cx=(right+left)/2;near=front+2.1;back=d.depth/2-1.0
        mode=d.interior_program if floor==0 else rng.choice(('business','hospitality','cafe','gallery'))
        programs.append(mode)
        # Service enclosure provides an actual back wall, with lift doors facing the lobby.
        core_y=min(back-2,near+max(5,(back-near)*.63));core_w=min(width*.65,9)
        if mode=='convenience':core_y=back-1.0
        g.box('cream',(cx,core_y+.65,z+(h-.35)/2),(core_w,1.3,h-.35))
        if mode!='convenience':
            count=2 if core_w>4.5 else 1
            for i in range(count):
                x=cx+(i-(count-1)/2)*2.1
                g.box('dark_metal',(x,core_y-.022,z+1.23),(1.60,.08,2.46))
                for side in (-1,1):g.box('silver',(x+side*.365,core_y-.072,z+1.18),(.71,.045,2.34))
                g.box('black',(x,core_y-.10,z+2.25),(.025,.015,.12))
                g.box('silver',(x+.9,core_y-.07,z+1.12),(.13,.05,.25))
                g.box('warm_light',(x+.9,core_y-.10,z+1.13),(.04,.012,.04))
            text(col,root,'LOBBY' if floor==0 else f'{floor+1}F', (cx,core_y-.08,z+2.85),.22,min(core_w-1,3),key='dark_metal')
        lobby_finish(g,col,root,d,left,right,front,near,core_y,z,h,mode)
        # Continuous ceiling with recessed lighting grids and HVAC slots.
        ceiling_z=z+h-(.45 if floor==0 else .5)
        for x in (left+width*.22,left+width*.78):
            for yy in (near+1.0,(near+core_y)/2,core_y-1):
                g.box('white',(x,yy,ceiling_z),(max(.5,min(width*.28,3.0)),.65,.08))
                g.box('warm_light',(x,yy,ceiling_z-.05),(max(.4,min(width*.28,3.0)-.12),.52,.025))
            g.box('black',(x,core_y-1,ceiling_z+.01),(max(.5,min(width*.25,2.6)),.12,.035))
        # Unshadowed fill lights supplement daylight within the transparent enclosure.
        light=bpy.data.lights.new('Interior ambient '+mode,'AREA');light.energy=max(180,width*25);light.shape='RECTANGLE';light.size=max(2,width*.75);light.size_y=max(3,core_y-near);light.use_shadow=False
        obj=bpy.data.objects.new(light.name,light);col.objects.link(obj);obj.parent=root;obj.location=(cx,(near+core_y)/2,ceiling_z-.12)
        if mode=='convenience':
            store_right=d.width/2-2.65;sw=store_right-left
            g.box('cream',(store_right+.3,(front+.4+back)/2,z+(h-.4)/2),(.18,back-front-.4,h-.4))
            office_x=(store_right+.45+d.width/2-.4)/2
            g.box('cream',(office_x,back-1.7,z+1.6),(1.9,.4,3.2))
            g.box('dark_metal',(office_x,back-1.93,z+1.2),(1.45,.08,2.4))
            for side in (-1,1):g.box('silver',(office_x+side*.34,back-1.98,z+1.17),(.65,.035,2.32))
            # Refrigerated drinks against the rear wall, lit cabinet interiors.
            for i in range(max(2,int(sw/1.05))):
                x=left+.55+i*1.02
                if x>store_right-.4:break
                g.box('dark_metal',(x,back-1.0,z+1.12),(.98,.75,2.24))
                for k in range(5):
                    zz=z+.24+k*.38;g.box('white',(x,back-1.44,zz),(.88,.45,.035))
                    for j in range(5):g.box(('product_green','product_blue','cream')[j%3],(x-.34+j*.17,back-1.46,zz+.14),(.12,.12,.25))
                g.box('clear',(x,back-1.71,z+1.16),(.89,.015,2.05))
                g.box('silver',(x+.35,back-1.74,z+1.1),(.025,.03,.6))
                g.box('warm_light',(x,back-1.55,z+2.10),(.8,.04,.035))
            length=min(4.2,max(2,back-near-5))
            for x in range(0,max(1,int((sw-2.4)/2.2))):shelves(g,left+2.1+x*2.2,near+3.1+length/2,z,length=length,detail=root['detail'])
            # Checkout, conveyor-free service counter and two tills.
            g.box('store_teal',(left+1.0,near+1.5,z+.5),(1.5,2.8,1.0))
            g.box('white',(left+1.0,near+1.5,z+1.03),(1.65,2.9,.08))
            for yy in (near+.65,near+2.25):
                g.box('black',(left+1.2,yy,z+1.14),(.36,.30,.18));g.box('dark_metal',(left+1.2,yy+.12,z+1.40),(.39,.08,.31))
            g.box('silver',(left+.85,near+3.2,z+1.28),(.48,.48,.48))
        elif mode=='business':
            desk_y=near+3;desk_x=left+min(width*.28,4)
            g.box('wood',(desk_x,desk_y,z+.5),(min(3.4,width*.46),.85,1))
            g.box('pale_stone',(desk_x,desk_y,z+1.04),(min(3.6,width*.48),.96,.09))
            g.box('black',(desk_x,desk_y+.15,z+1.22),(.46,.08,.30))
            if width>8:
                sofa(g,right-1.6,near+2.5,z,2.1);table(g,right-1.6,near+1.25,z,1.1,.55)
                for i in range(3):
                    x=cx+(i-1)*.95;g.box('silver',(x,core_y-2,z+.48),(.20,1.1,.96));g.box('clear',(x+.30,core_y-2,z+.74),(.42,.035,.54))
        elif mode=='hospitality':
            for x in (left+width*.24,left+width*.76):
                sofa(g,x,near+2.3,z,min(2.3,width*.36));table(g,x,near+.95,z,min(1.4,width*.25),.60)
                if core_y-near>6:chair(g,x,near+4.5,z,math.pi)
            g.box('wood',(cx,core_y-1.1,z+.55),(min(4,width*.55),.8,1.1))
            for i in range(8):g.box('bronze',(cx-min(4,width*.55)/2+.15+i*min(4,width*.55)/8,core_y-1.52,z+.52),(.045,.035,.9))
        elif mode=='cafe':
            g.box('wood',(left+.55,(near+core_y)/2,z+.52),(1.0,max(2,core_y-near-1),1.04))
            g.box('white',(left+.55,(near+core_y)/2,z+1.07),(1.10,max(2,core_y-near-1),.07))
            g.box('silver',(left+.55,near+2,z+1.30),(.50,.52,.42))
            for x in (left+width*.48,left+width*.79):
                for yy in (near+1.2,near+4):
                    if yy+1>core_y:continue
                    table(g,x,yy,z,.85,.75);chair(g,x,yy+.72,z);chair(g,x,yy-.72,z,math.pi)
                    g.tube('white',(x,yy,z+.80),(x,yy,z+.92),.05,10)
        else:
            for i in range(3):
                x=left+width*(i+1)/4;yy=near+2+(i%2)*2
                g.box('white',(x,yy,z+.48),(.7,.7,.96))
                g.tube('bronze',(x-.2,yy,z+.96),(x+.2,yy,z+1.7),.10,12)
            for side in (-1,1):
                x=cx+side*width*.34;g.box('wood',(x,core_y-.04,z+1.6),(min(1.6,width*.25),.06,1.2))
                g.box('product_blue',(x,core_y-.08,z+1.6),(min(1.45,width*.23),.02,1.05))
        if width>24 and mode!='convenience':
            for side in (-1,1):
                xx=cx+side*(width/2-3.2)
                for yy in (near+6,near+10):
                    if yy+1.6>=core_y:continue
                    table(g,xx,yy,z,1.8,.8)
                    for dx in (-.5,.5):chair(g,xx+dx,yy+.75,z)
                    g.box('wood',(xx,yy+1.25,z+.65),(2.4,.10,1.3))
                    for j in range(9):g.box('wood',(xx-1.1+j*.275,yy+1.25,z+1.8),(.06,.10,1.0))
        occupied_details(g,left,right,near,core_y,z,h,mode)
        # Compact corner planting does not occupy the center circulation route.
        if width>9 and mode!='convenience':planter(g,left+.5,core_y-1,z,.70,.70)
    g.finish(col,root,'Lower floor interiors')
    root['interior_programs_json']=json.dumps(programs)
