"""Assembly of declarative masses, with continuous rounded facade boundaries."""
import bpy,math,json
from dataclasses import replace
from .geometry import Geometry,Face,rounded_footprint
from .facade import floor_module,pane
from .details import planter,roof,text
from .landscape import place_stock
from .design import derive_design,floor_z,mass_top
from .street_detail import entrance_hardware,column_finish,canopy_finish
from .tower_form import mass_outline,vertical_members

def edges(poly):return zip(poly,poly[1:]+poly[:1])

def railing(g,poly,z,frame):
    for a,b in edges(poly):
        f=Face(g,a,b);f.box(frame,f.length/2,-.10,z+1.12,f.length,.08,.065)
        f.box('clear',f.length/2,-.10,z+.61,f.length-.025,.018,.94)
        n=max(1,math.ceil(f.length/1.6))
        for i in range(n):f.box(frame,i*f.length/n,-.10,z+.59,.05,.08,1.13)

def base_assembly(g,col,root,spec,design,poly):
    h=design.base_height;mode=design.base_style
    g.prism('granite',poly,-.18,.18)
    if not design.atrium:g.prism('ceiling',poly,h-.30,.30)
    # A recessed central enclosure keeps the lobby transparent at its perimeter.
    for a,b in edges(poly):
        f=Face(g,a,b);long=f.length>5;front=f.ny<-.95 and long;back=f.ny>.95 and long
        n=max(1,round(f.length/4.8));bw=f.length/n;inset=1.3 if mode=='portico' and long else .38
        if front and design.interior_program=='convenience':
            from .tenant_front import store_front
            store_front(g,col,root,spec,design,f)
            continue
        if front and design.width<10:
            # Independent 1.25 m office entrance beside a small tenant frontage.
            office=f.length-1.05;shop=(f.length-2.0)/2
            pane(f,shop,1.55,f.length-2.3,3.1,spec.frame,'clear',-.42)
            pane(f,office,1.25,1.25,2.5,spec.frame,'clear',-.42)
            pane(f,office,2.86,1.25,.68,spec.frame,'clear',-.42)
            entrance_hardware(f,office,1.25,2.5,-.42,automatic=False)
            entrance_hardware(f,shop,f.length-2.3,3.1,-.42)
            f.tube('silver',(shop+.15,-.30,1),(shop+.15,-.30,1.65),.022)
            f.box(spec.wall,f.length-1.95,-.05,h/2,.27,.60,h)
            f.box(spec.wall,f.length/2,-.03,h-.65,f.length,.50,1.3)
            f.box(spec.frame,shop,.65,3.25,f.length-2.1,1.65,.16)
            f.box('silver',f.length-1.72,.28,1.6,.18,.05,.65)
            for j in range(4):f.box('black',f.length-1.72,.31,1.38+j*.14,.13,.018,.05)
            text(col,root,spec.title,f.point(shop,.24,3.85),.24,f.length-2.4,f.angle)
            f.tube('silver',(office,-.3,.9),(office,-.3,1.55),.022)
            continue
        if back:
            f.box(spec.wall,f.length/2,-.12,h/2,f.length,.30,h)
            for i in range(n):
                u=(i+.5)*bw;f.box('dark_metal',u,.05,1.55,bw*.65,.12,3.1)
                for j in range(17):f.box('black',u,.118,.2+j*.16,bw*.61,.015,.035)
            continue
        for i in range(n):
            u=(i+.5)*bw;door=front and (i==n//2 or (design.base_program=='gallery' and i%3==0))
            if long:
                f.box(spec.wall,i*bw,.02,h/2,.42,.62,h)
                column_finish(f,i*bw,h)
                f.box('warm_light',u,-.9,h-.35,max(.1,bw-.9),.16,.035)
            if door:
                pane(f,u,1.5,bw-.55,3,'silver','clear',-inset)
                entrance_hardware(f,u,bw-.55,3,-inset)
                for du in (-.14,.14):f.tube('silver',(u+du,-inset+.12,1),(u+du,-inset+.12,1.65),.022)
                pane(f,u,(h+3)/2-.15,bw-.55,h-3.3,spec.frame,'clear',-inset)
                f.box('black',u,-inset+.6,.013,bw-.55,1.2,.025)
                if mode!='arcade':
                    f.box(spec.frame,u,.9,3.26,bw+.15,2.1,.20)
                    canopy_finish(f,u,bw)
                    for du in (-bw*.35,bw*.35):f.tube(spec.frame,(u+du,.05,4.05),(u+du,1.80,3.36),.035)
                signz=3.75 if mode!='arcade' else h-.35
                signv=.62 if mode=='arcade' else .22
                f.box(spec.frame,u,signv,signz,bw-.65,.12,.36)
                text(col,root,spec.title,f.point(u,signv+.065,signz),.23,bw-.85,f.angle)
            else:
                pane(f,u,h/2,bw-(.48 if long else .025),h-.35,spec.frame,'clear',-inset)
            if mode=='arcade' and long:
                spring=2.7;rr=(bw-.5)/2;rise=min(1.55,h-3.1)
                # Stone spandrel with a true arch-shaped lower silhouette.
                for j in range(16):
                    aa=j*math.pi/16;bb=(j+1)*math.pi/16
                    p=(u+rr*math.cos(aa),spring+rise*math.sin(aa));q=(u+rr*math.cos(bb),spring+rise*math.sin(bb))
                    verts=[f.point(v,dep,z) for dep in (-.2,.55) for v,z in (p,q,(q[0],min(h-.22,5.05)),(p[0],min(h-.22,5.05)))]
                    g.mesh(spec.wall,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
                f.box(spec.wall,i*bw,.15,spring/2,.58,.8,spring)
                if h>8:f.box(spec.frame,u,.10,5.1,bw,.50,.20)
            elif mode=='lantern':
                f.box(spec.frame,u,.08,h*.48,bw,.23,.22)
                if long:
                    for j in range(1,5):f.box(spec.frame,i*bw+j*bw/5,.10,h*.73,.055,.20,h*.46)
            elif mode=='deep_portal' and door:
                for du in (-bw/2,bw/2):f.box(spec.wall,u+du,.38,h/2,.70,1.25,h)
                f.box(spec.wall,u,.38,h-.5,bw,1.25,1)
        if long:f.box(spec.wall,f.length,.02,h/2,.42,.62,h)
        f.box(spec.frame,f.length/2,.03,h-.13,f.length,.35,.26)
    # Front landscape is within the asset forecourt, away from the central door.
    if root.get('include_forecourt',True) and design.width>=12 and design.interior_program!='convenience':
        for side in (-1,1):planter(g,side*(design.width/2-3),-design.depth/2-.95,0,3.4,1.1)

def create_recipe(spec,seed,detail,name=None,overrides=None,include_forecourt=True):
    design=derive_design(spec,seed,overrides)
    col=bpy.data.collections.new(name or spec.key);bpy.context.scene.collection.children.link(col)
    root=bpy.data.objects.new(name or spec.title,None);col.objects.link(root)
    root['include_forecourt']=include_forecourt
    root['asset_type']='urban_building';root['detail']=detail;root['seed']=seed
    actual=replace(spec,width=design.width,depth=design.depth,floors=design.floors)
    from dataclasses import asdict
    root['spec_json']=json.dumps(asdict(actual));root['design_json']=json.dumps(design.payload());root['design_signature']=design.signature()
    poly=rounded_footprint(design.width,design.depth,design.radius);root['footprint_json']=json.dumps(poly)
    from .podium import assemble
    g=Geometry();top_poly=assemble(g,col,root,spec,design,base_assembly,railing)
    if design.ground_mode!='continuous':railing(g,top_poly,design.base_height,spec.frame)
    sections=[]
    for k,m in enumerate(design.masses):
        p=mass_outline(m)
        modules=[floor_module(p,design.floor_height,m.facade,spec.wall,spec.frame,spec.glass,seed+31*k,variant=v,bay=m.bay,detail=detail) for v in range(3 if detail=='high' else 1)]
        for i in range(m.count):
            module=modules[i%len(modules)]
            if i==m.tall_floor:
                module=floor_module(p,design.floor_height+m.extra_height,'curtain',spec.wall,spec.frame,spec.glass,seed,bay=m.bay,detail=detail)
                for a,b in edges(p):
                    f=Face(module,a,b)
                    for zz in (.22,design.floor_height+m.extra_height-.30):f.box(spec.frame,f.length/2,.15,zz,f.length,.44,.28)
            module.finish(col,root,'Floor module '+m.facade,(m.x,m.y,floor_z(m,i,design.floor_height)))
        sections.append(dict(width=m.width,depth=m.depth,z=m.z,count=m.count,style=m.facade,offset=(m.x,m.y),radius=m.radius,chamfer=0,shape=m.shape,floor_levels=[floor_z(m,i,design.floor_height) for i in range(m.count)]))
        top=mass_top(m,design.floor_height)
        r=Geometry()
        vertical_members(r,p,m.z,top,spec,design.vertical_style)
        upper=[u for u in design.masses if abs(u.z-top)<.002]
        terrace=bool(upper)
        if terrace:
            r.prism('roof',p,top,.12)
            railing(r,p,top,spec.frame)
            candidates=[(x,y,min(3.2,m.width*.20),.9) for x in (-m.width*.25,m.width*.25) for y in (-m.depth/2+.7,m.depth/2-.7)]
            candidates += [(x,y,.9,.9) for x in (-m.width/2+.7,m.width/2-.7) for y in (-m.depth*.20,m.depth*.20)]
            for x,y,pw,pd in candidates:
                inside=all(max(abs(cx)-(m.width/2-m.radius),0)**2+max(abs(cy)-(m.depth/2-m.radius),0)**2<=m.radius**2+.001 for cx in (x-pw/2,x+pw/2) for cy in (y-pd/2,y+pd/2)) if m.radius else True
                clear=all(abs(x+m.x-u.x)>(pw+u.width)/2+.12 or abs(y+m.y-u.y)>(pd+u.depth)/2+.12 for u in upper)
                if inside and clear:planter(r,x,y,top+.12,pw,pd)
        else:
            roof(r,p,top,m.width,m.depth,seed,spec.frame,occupied=False)
            if design.roof_style=='louver':
                for a,b in edges(rounded_footprint(m.width*.63,m.depth*.61,m.radius*.4)):
                    f=Face(r,a,b)
                    for j in range(16):f.box(spec.frame,f.length/2,0,top+.6+j*.20,f.length,.10,.09)
                    for u in (0,f.length/2):f.box(spec.frame,u,0,top+1.9,.09,.14,3.4)
            elif design.roof_style=='stepped_cap':
                for j in range(3):
                    pp=[(x*(1-j*.012),y*(1-j*.012)) for x,y in p]
                    for a,b in edges(pp):
                        f=Face(r,a,b);f.box(spec.frame,f.length/2,-.03,top+.8+j*.4,f.length,.55,.43)
            else:
                for x in (-m.width*.32,m.width*.32):
                    for y in (-m.depth*.28,-m.depth*.04):r.box(spec.frame,(x,y,top+1.5),(.12,.12,3))
                for j in range(10):r.box(spec.frame,(0,-m.depth*.28+j*m.depth*.24/9,top+3),(m.width*.65,.13,.15))
        r.finish(col,root,'Terrace and crown',(m.x,m.y,0))
    if design.tower_form=='paired':
        a,b=design.masses;level=design.base_height+int(min(a.count,b.count)*.55)*design.floor_height
        x1=a.x+a.width/2-.20;x2=b.x-b.width/2+.20;mid=(x1+x2)/2
        g.box(spec.frame,(mid,0,level+.12),(x2-x1,4,.24));g.box(spec.frame,(mid,0,level+3),(x2-x1,4,.20))
        for y in (-2,2):g.box('blue_glass',(mid,y,level+1.5),(x2-x1,.045,2.7))
    if spec.family=='round_blade' and not design.terrace_depth:
        # Deep front eaves with diagonal supports meet both slab and grade.
        yy=-design.depth/2
        g.box(spec.frame,(0,yy-.6,design.ground_height-.40),(design.width*.74,3.3,.28))
        for x in (-design.width*.31,design.width*.31):g.tube(spec.frame,(x*.80,yy+.30,0),(x,yy+.30,design.ground_height-.52),.22,12)
    g.finish(col,root,'Base and landscape')
    if include_forecourt and (design.width>25 or spec.family=='garden_steps'):
        for side in (-1,1):
            x=side*(design.width/2+2.4);y=-design.depth*.22
            tree=place_stock(col,root,'tree',0 if side<0 else 1,(x,y,0),angle=seed*.31+side)
            bed=Geometry();bed.box('soil',(x,y,-.04),(2.2,2.2,.06))
            for dx in (-1.16,1.16):bed.box('granite',(x+dx,y,.025),(.12,2.44,.12))
            for dy in (-1.16,1.16):bed.box('granite',(x,y+dy,.025),(2.20,.12,.12))
            bed.finish(col,root,'Tree soil bed')
    root['sections_json']=json.dumps(sections);root['height']=max(mass_top(m,design.floor_height) for m in design.masses)+5.6
    from .interiors import furnish
    furnish(col,root,spec,design)
    if design.parking:
        from .parking_plaza import raised_site
        raised_site(col,root,spec,design)
    root['module_instances']=sum(m.count for m in design.masses)
    return root
