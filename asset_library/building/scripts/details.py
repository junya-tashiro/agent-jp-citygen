"""Street-level depth, shopfronts, service entries and roof machinery."""
import math,random,bpy
from pathlib import Path
from mathutils import Vector
from .geometry import Geometry,Face,footprint
from .materials import material

def text(col,root,body,position,size,max_width,angle=0,key='white'):
    c=bpy.data.curves.new('Building sign','FONT');c.body=body;c.align_x='CENTER';c.align_y='CENTER';c.size=size;c.space_character=1.15;c.extrude=.001;c.bevel_depth=.001;c.resolution_u=3
    from asset_library.shared.fonts import japanese_font
    if any(ord(ch)>127 for ch in body):c.font=japanese_font()
    o=bpy.data.objects.new(body,c);col.objects.link(o);o.parent=root;o.location=position;o.rotation_euler=(math.pi/2,0,angle);c.materials.append(material(key));bpy.context.view_layer.update()
    span=o.dimensions.x
    if span>max_width:o.scale*=max_width/span
    mesh=bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()));b=bpy.data.objects.new(body,mesh);col.objects.link(b);b.parent=root;b.matrix_basis=o.matrix_basis.copy();b['building_part']='lettering';b['label_text']=body
    bpy.data.objects.remove(o,do_unlink=True)
    if c.users==0:bpy.data.curves.remove(c)

def planter(g,x,y,z,w=2.5,d=1):
    # Hollow container: the soil sits below the rim, and stems begin in the bed.
    g.box('granite',(x,y,z+.01),(w,d,.10))
    for dx in (-w/2+.04,w/2-.04):g.box('granite',(x+dx,y,z+.28),(.08,d,.64))
    for dy in (-d/2+.04,d/2-.04):g.box('granite',(x,y+dy,z+.28),(w-.16,.08,.64))
    g.box('soil',(x,y,z+.53),(w-.16,d-.16,.04))
    g.planting.append((x,y,z,w,d))

def roof(g,poly,z,w,d,seed,frame='silver',occupied=False,layout='default'):
    g.prism('roof',poly,z,.12)
    for a,b in zip(poly,poly[1:]+poly[:1]):
        f=Face(g,a,b);f.box('concrete',f.length/2,-.12,z+.42,f.length,.25,.84);f.box(frame,f.length/2,-.12,z+.85,f.length+.03,.30,.07)
    # Stair/elevator overrun has its own roof edge, door and ventilation.
    mw=min(5,w*.28);md=min(5,d*.28)
    ox=-w/2+1.5 if layout=='pencil' else (w*.18 if layout=='brick' else 0)
    if layout=='pencil':mw=2.7;md=6
    g.box('concrete',(ox,d*.16,z+1.65),(mw,md,3.3));g.box(frame,(ox,d*.16,z+3.34),(mw+.15,md+.15,.13))
    g.box(frame,(ox,d*.16-md/2-.02,z+1.05),(.95,.07,2.1))
    for j in range(8):g.box('black',(ox,d*.16-md/2-.06,z+.45+j*.14),(.72,.015,.04))
    for i in range(2 if w<25 else 5):
        x=-w*.32+i*min(2.0,w*.12);y=-d*.07
        g.box('dark_metal',(x,y,z+.22),(1.5,2.1,.18));g.box('silver',(x,y,z+.82),(1.35,1.9,1.02))
        for j in range(9):g.box('black',(x,y-.958,z+.45+j*.105),(1.17,.016,.035))
        for xx in (-.35,.35):
            g.tube('dark_metal',(x+xx,y,z+1.335),(x+xx,y,z+1.37),.26,16)
            for k in range(6):g.box('silver',(x+xx,y+(k-1.5)*.10,z+1.38),(.46,.025,.025))
        g.tube('silver',(x+.6,y+.75,z+.5),(x+.6,d*.10,z+.5),.035)
    g.tube(frame,(ox+mw/2-.3,d*.16,z+3.40),(ox+mw/2-.3,d*.16,z+5.6),.035)
    for zz in (z+4.7,z+5.1):g.tube(frame,(ox+mw/2-.9,d*.16,zz),(ox+mw/2+.3,d*.16,zz),.012)
    if layout in ('punched','ribbon'):
        # An older small-office roof carries a panelled water tank on steel legs.
        tx=w*.28;ty=-d*.20
        for dx in (-.85,.85):
            for dy in (-.75,.75):g.box('dark_metal',(tx+dx,ty+dy,z+.64),(.10,.10,1.08))
        g.box('white',(tx,ty,z+1.92),(1.9,1.7,1.55))
        for dz in (-.77,0,.77):g.box('silver',(tx,ty,z+1.92+dz),(1.96,1.76,.035))
        for dx in (-.95,0,.95):g.box('silver',(tx+dx,ty-.866,z+1.92),(.035,.035,1.55))
        g.tube('silver',(tx+.6,ty,z+1.3),(tx+.6,ty,z+.18),.05)
    if layout=='brick':
        g.box('silver',(-w*.2,d*.1,z+.58),(1.0,d*.35,.65))
        for j in range(5):g.box('dark_metal',(-w*.2,d*.1-d*.175+j*d*.0875,z+.58),(1.04,.035,.69))
    if occupied:
        for x in (-w*.33,w*.33):planter(g,x,d*.30,z+.12,min(3,w*.2),.9)

def podium(g,col,root,poly,height,wall,frame,title,seed,portico=False,shops=True,style='curtain'):
    g.prism('granite',poly,-.18,.18);g.prism('ceiling',poly,height-.35,.35)
    for index,a in enumerate(poly):
        f=Face(g,a,poly[(index+1)%len(poly)])
        front=f.ny<-.5;back=f.ny>.5
        n=max(1,round(f.length/4.2));bw=f.length/n
        glassheight=height-.95;inset=1.7 if portico and front else .43
        if front and style=='stone_tower':
            for i in range(n+1):
                u=i*bw
                f.box('pale_stone',u,.18,height/2,.78,.90,height)
                f.box('pale_stone',u,.25,.20,1.02,1.02,.40)
                f.box('pale_stone',u,.22,height-.6,1.04,1.02,.26)
            for dz,dep in ((-.12,.95),(-.30,1.1),(-.48,.84)):
                f.box('pale_stone',f.length/2,.2,height+dz,f.length,dep,.15)
        if front and style=='brick':
            f.box('dark_metal',f.length/2,.72,3.25,f.length-.4,1.65,.15)
            for j in range(n+1):
                u=j*bw
                f.tube('dark_metal',(u,.12,4.15),(u,1.45,3.33),.035)
                f.box('dark_metal',u,.09,4.15,.20,.16,.30)
        if front and style in ('wide_office','punched'):
            for i in range(n+1):f.box('granite',i*bw,.10,1.10,.62,.73,2.20)
            f.box('granite',f.length/2,.16,height-.15,f.length,.84,.25)
        if front and style=='balcony':
            for u in (0,f.length):f.box('concrete',u,.3,height/2,.72,1.1,height)
            f.box('concrete',f.length/2,.3,height-.35,f.length,1.1,.70)
        # Recessed interior behind the glazing creates a real lobby volume.
        f.box('pale_stone',f.length/2,-1.9,.055,f.length,3.7,.11)
        if back:
            f.box(wall,f.length/2,-.12,height/2,f.length,.26,height)
            # Loading portal, fire exit and deep ventilation louvers.
            for i in range(n):
                u=(i+.5)*bw;ww=bw*.74;hh=min(3.5,height-.7)
                f.box(frame,u,.03,hh/2,ww,.12,hh)
                for j in range(int(hh/.16)):f.box('black',u,.096,.12+j*.16,ww-.12,.014,.034)
            continue
        for i in range(n):
            u=(i+.5)*bw;isdoor=(i==n//2 and front)
            f.box(wall,i*bw,.04,height/2,.48,.60,height)
            # Shop mullions, interior ceiling strip, rear wall with display panels.
            f.box(frame,u,-inset,glassheight+.23,bw-.48,.17,.19)
            if not isdoor:
                f.box('clear',u,-inset,glassheight/2+.15,bw-.55,.022,glassheight)
                f.box(frame,u,-inset+.035,glassheight/2+.15,.060,.11,glassheight)
                f.box('warm_light',u,-2.0,height-.45,bw*.72,.18,.045)
                # Art/display object on the console.
            else:
                dh=2.65;doorw=min(2.5,bw-.55)
                f.box('clear',u,-inset,dh/2,doorw,.03,dh)
                for du in (-doorw/2,0,doorw/2):f.box(frame,u+du,-inset+.025,dh/2,.055,.10,dh)
                for du in (-.18,.18):f.tube('silver',(u+du,-inset+.10,.9),(u+du,-inset+.10,1.55),.02)
                f.box(frame,u,-inset,dh+.03,doorw,.12,.08)
                if height>4:f.box('clear',u,-inset,(dh+height-.45)/2,bw-.55,.025,height-.45-dh)
                # Recessed mat, entrance canopy, supported brackets.
                f.box('black',u,-inset+.60,.014,doorw,1.2,.026)
                f.box(frame,u,.85,3.15,bw+.32,2.05,.18)
                f.box('warm_light',u,.68,3.049,bw*.65,.30,.025)
                for du in (-bw*.36,bw*.36):f.tube(frame,(u+du,0,3.85),(u+du,1.65,3.23),.032)
            for zz in (.12,):f.box(frame,u,-inset,zz,bw-.48,.12,.20)
            if height>6:
                f.box(frame,u,-inset,height*.52,bw-.48,.25,.30)
                f.box('ceiling',u,-2.2,height*.52,bw-.50,3.2,.18)
            if front and shops and i!=n//2 and (n<5 or i%3==0):
                pos=f.point(u,-inset+.10,2.65)
                text(col,root,(('COFFEE', 'ATELIER', 'BOOKS', 'BAKERY')[(i+seed)%4]),pos,.19,bw*.72,f.angle)
        f.box(wall,f.length,.04,height/2,.48,.60,height)
        f.box(wall,f.length/2,.04,height-.23,f.length,.65,.46)
        if front:
            # Building name, placed on an opaque fascia rather than floating in glass.
            u=(n//2+.5)*bw;z=min(4.0,height-1.0);namewidth=min(bw-.85,12)
            f.box(frame,u,-.12,z,namewidth+.5,.18,.40)
            text(col,root,title,f.point(u,-.022,z),.25,namewidth,f.angle)
    # Small planting beds hug the facade, keeping the central approach clear.
    xs=[p[0] for p in poly];ys=[p[1] for p in poly];w=max(xs)-min(xs);d=max(ys)-min(ys)
    for side in (-1,1):planter(g,side*(w/2-2),-d/2-.85,0,min(3.0,w*.20),.85)
