"""Ground-floor assembly details in metres; independent of scene placement."""
import math
from .details import text


def entrance_hardware(f,u,width,height,depth,automatic=True,floor_z=0):
    """Head operator, jamb seals, threshold and accessible glazed door markings."""
    width=max(.8,width);z=floor_z
    f.box('silver',u,depth+.015,z+.016,width,.23,.032)
    for dv in (-.065,.025):f.box('black',u,depth+dv,z+.033,width-.07,.010,.002)
    for du in (-width/2+.04,width/2-.04):
        f.box('black',u+du,depth+.018,z+height/2,.018,.028,height-.07)
    f.box('dark_metal',u,depth+.07,z+height+.025,width+.10,.22,.13)
    if automatic:
        f.box('silver',u,depth+.12,z+height+.035,width+.07,.16,.105)
        f.box('black',u,depth+.22,z+height+.045,.21,.07,.06)
        f.box('smoke_glass',u,depth+.258,z+height+.035,.135,.009,.025)
    else:
        for du in (-width/2+.075,width/2-.075):
            for zz in (.32,height-.30):f.box('silver',u+du,depth+.075,z+zz,.075,.045,.13)
        f.box('silver',u+width*.20,depth-.09,z+height-.08,.28,.11,.07)
    # Discreet collision-visibility marks on both leaves, below eye height.
    for du in (-width*.22,width*.22):
        f.box('white',u+du,depth+.013,z+1.05,min(.32,width*.18),.002,.018)


def lobby_finish(g,col,root,d,left,right,front,near,core_y,z,h,mode):
    """Rear service volume, floor joints, skirting and fitted circulation details."""
    width=right-left;cx=(left+right)/2
    # The lobby remains a full-height atrium. The rear becomes enclosed rooms,
    # rather than a tiny isolated lift wall with sky visible on either side.
    back=core_y+.72
    g.box('interior',(cx,back+.18,z+(h-.35)/2),(width+.40,.30,h-.35))
    for side in (-1,1):
        x=left-.08 if side<0 else right+.08
        run=max(.5,back-near-2.0)
        g.box('cream',(x,back-run/2,z+(h-.35)/2),(.18,run,h-.35))
        g.box('dark_stone',(x-side*.10,back-run/2,z+.075),(.025,run,.15))
    g.box('dark_stone',(cx,back-.015,z+.075),(width,.035,.15))
    # Large stone/porcelain slabs: hairline joints on the existing structural floor.
    pitch=1.2 if width>16 else .6
    y0=front+.55;y1=core_y-.20
    for i in range(1,math.ceil(width/pitch)):
        x=left+i*pitch
        if x<right:g.box('grout',(x,(y0+y1)/2,z+.002),(.003,y1-y0,.003))
    for i in range(1,math.ceil((y1-y0)/pitch)):
        y=y0+i*pitch
        if y<y1:g.box('grout',(cx,y,z+.002),(width,.003,.003))
    # A flush entry mat and metal perimeter sit inside, off the sidewalk.
    mat_w=min(2.4,width*.40);my=front+1.20
    g.box('silver',(cx,my,z+.006),(mat_w+.06,1.15,.012))
    g.box('mat_rubber',(cx,my,z+.014),(mat_w,1.09,.008))
    for i in range(18):g.box('dark_metal',(cx,my-.50+i/17,z+.019),(mat_w-.03,.012,.002))
    # Suspended perimeter reveal and narrow linear air supply at ceiling level.
    ceiling=z+h-.42
    for x in (left+.22,right-.22):
        run=max(1,core_y-near)
        g.box('black',(x,(near+core_y)/2,ceiling),(.22,run,.035))
        for dx in (-.055,.055):g.box('silver',(x+dx,(near+core_y)/2,ceiling-.022),(.018,run,.012))
    if mode!='convenience' and width>4:
        x=right-.55;yy=near+.6
        # Stone-backed tenant directory, not floating lettering on glass.
        g.box('pale_stone',(x,yy,z+1.25),(.75,.20,2.50))
        g.box('dark_metal',(x,yy-.111,z+1.55),(.57,.024,1.12))
        text(col,root,'INFORMATION',(x,yy-.128,z+1.98),.058,.48,key='white')
        first={'cafe':'1F  CAFE','gallery':'1F  GALLERY','hospitality':'1F  LOUNGE'}.get(mode,'1F  LOBBY')
        for i,body in enumerate((first,'2F  OFFICE','3F  OFFICE')):
            text(col,root,body,(x,yy-.128,z+1.75-i*.19),.066,.48,key='white')
        if width<14:
            for i in range(6):
                xx=left+.28+(i%2)*.34;zz=z+.75+(i//2)*.24
                g.box('silver',(xx,back-.20,zz),(.32,.12,.22))
                g.box('black',(xx,back-.264,zz+.05),(.23,.008,.018))
                g.box('white',(xx-.03,back-.27,zz-.02),(.10,.008,.045))


def column_finish(f,u,height,width=.42,depth=.62):
    """Stone-panel joints and a harder plinth at the column's exposed face."""
    f.box('dark_stone',u,.02,.10,width+.016,depth+.016,.20)
    # Recess-dark hairlines sit on the front face, below the canopy only.
    for i in range(1,math.ceil(height/1.0)):
        z=i*1.0
        if z<height-.15:f.box('grout',u,.02+depth/2+.001,z,width-.018,.003,.004)


def canopy_finish(f,u,width,depth=2.1):
    # Thin perimeter drip edge and lamps fitted into the opaque underside.
    f.box('silver',u,1.95,3.185,width+.12,.028,.055)
    for du in (-width*.27,width*.27):
        f.box('black',u+du,.90,3.152,.38,.22,.014)
        f.box('warm_light',u+du,.90,3.143,.30,.14,.006)


def occupied_details(g,left,right,near,core_y,z,h,mode):
    width=right-left;cx=(left+right)/2
    if width<14:return
    # Human-scale joinery against the rear rooms, below the open atrium volume.
    for i in range(max(1,math.ceil(width/1.2))):
        x=left+(i+.5)*width/math.ceil(width/1.2)
        g.box('wood' if mode in ('cafe','hospitality') else 'pale_stone',(x,core_y+.735,z+1.6),(width/math.ceil(width/1.2)-.012,.026,3.05))
    g.box('dark_metal',(cx,core_y+.71,z+3.15),(width,.03,.018))
    if mode=='cafe':
        for x in (left+width*.48,left+width*.79):
            for yy in (near+1.2,near+4):
                if yy+1>core_y:continue
                top=min(3.1,h-.70);bottom=top-.22;radius=.24;n=16
                verts=[(x+r*math.cos(i*math.tau/n),yy+r*math.sin(i*math.tau/n),z+zz) for r,zz in ((radius,bottom),(.10,top)) for i in range(n)]
                g.mesh('dark_metal',verts,[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
                g.tube('warm_light',(x,yy,z+bottom+.005),(x,yy,z+bottom+.012),radius-.012,16)
                g.tube('dark_metal',(x,yy,z+top),(x,yy,z+h-.40),.006,6)
                g.tube('dark_metal',(x,yy,z+h-.44),(x,yy,z+h-.40),.07,12)
    elif mode in ('business','hospitality'):
        # Segmented timber screen defines seating without blocking circulation.
        span=min(4.8,width*.18);x=right-span/2-1.5;yy=near+5.2
        if yy+1<core_y:
            g.box('dark_metal',(x,yy,z+.045),(span,.22,.09))
            for i in range(math.ceil(span/.18)):
                xx=x-span/2+.08+i*.18
                g.box('wood',(xx,yy,z+1.12),(.055,.12,2.15))
            g.box('dark_metal',(x,yy,z+2.22),(span,.16,.045))
