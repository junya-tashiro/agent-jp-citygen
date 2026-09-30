"""Occupied podium floors and accessible second-floor terraces."""
from dataclasses import replace
import math
from .geometry import Geometry,Face,rounded_footprint
from .facade import pane,floor_module
from .street_detail import entrance_hardware
from .details import planter,text


def assemble(g,col,root,spec,d,ground_builder,railing):
    if d.ground_mode=='continuous':
        from .tower_form import mass_outline
        m=d.masses[0];poly=mass_outline(m)
        front=-m.depth/2;door=min(1.8,m.width*.24);cx=0
        module=floor_module(poly,d.ground_height,m.facade,spec.wall,spec.frame,spec.glass,d.seed,bay=m.bay,detail=root['detail'],entrance=(cx-door/2,front-1.6,.21,cx+door/2,front+1.8,2.85))
        module.finish(col,root,'Office ground floor')
        f=Face(g,(-m.width/2,front),(m.width/2,front))
        pane(f,m.width/2,1.5,door,2.6,spec.frame,'clear',-.30)
        entrance_hardware(f,m.width/2,door,2.6,-.30,automatic=False,floor_z=.20)
        f.tube('silver',(m.width/2+.15,-.19,.95),(m.width/2+.15,-.19,1.65),.022)
        f.box(spec.frame,m.width/2,.38,2.98,door+.40,1.2,.12)
        g.box('granite',(0,front+.05,.10),(door,1.0,.20))
        root['podium_floors']=1;root['terrace_level']=0
        return poly
    poly=rounded_footprint(d.width,d.depth,d.podium_radius)
    style='portico' if d.base_program=='colonnade' else d.base_style
    ground_builder(g,col,root,spec,replace(d,base_height=d.ground_height,base_style=style),poly)
    td=d.terrace_depth
    upper=rounded_footprint(d.width,d.depth-td,min(d.podium_radius,(d.depth-td)*.3))
    upper=[(x,y+td/2) for x,y in upper]
    for floor in range(1,d.base_floors):
        z=d.ground_height+(floor-1)*d.floor_height;h=d.floor_height
        # Real slab and ceiling, rather than a single stretched lobby window.
        if not d.atrium:g.prism('granite',upper,z-.03,.23)
        if not d.atrium or floor==d.base_floors-1:g.prism('ceiling',upper,z+h-.22,.20)
        for a,b in zip(upper,upper[1:]+upper[:1]):
            f=Face(g,a,b);n=max(1,round(f.length/3.6));bw=f.length/n
            for i in range(n):
                u=(i+.5)*bw
                if td and floor==1 and f.ny<-.95 and i==n//2:
                    pane(f,u,z+1.6,bw-.08,2.8,spec.frame,'clear',-.16)
                    pane(f,u,z+(3+h)/2,bw-.08,h-3.2,spec.frame,'clear',-.16)
                    f.box(spec.frame,u,-.13,z+1.6,.055,.10,2.8)
                else:
                    pane(f,u,z+h/2,bw-.08,h-.42,spec.frame,'clear',-.16)
                if f.length>3:
                    f.box(spec.wall,i*bw,-.02,z+h/2,.25,.40,h)
                    # Interior sill and ceiling light give the transparent bays depth.
                    if not d.atrium or floor==d.base_floors-1:f.box('warm_light',u,-1.0,z+h-.27,max(.2,bw-.7),.15,.035)
                if td and floor==1 and f.ny<-.95 and i==n//2:
                    for du in (-.13,.13):f.tube('silver',(u+du,-.01,z+1),(u+du,-.01,z+1.65),.022)
            band=.65 if d.base_program=='gallery' else .30
            f.box(spec.wall,f.length/2,.04,z+h-.12,f.length,.42,band)
        # A shallow occupied interior with a central service core.
    if td:
        z=d.ground_height
        # Clip the terrace slab to the exterior strip; no slab across the atrium.
        boundary=-d.depth/2+td;strip=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if a[1]<=boundary:strip.append(a)
            if (a[1]<boundary<b[1]) or (b[1]<boundary<a[1]):
                t=(boundary-a[1])/(b[1]-a[1]);strip.append((a[0]+t*(b[0]-a[0]),boundary))
        g.prism('granite',strip,z-.03,.12)
        # Only the exterior edge; no railing across the doors into the terrace.
        segments=[(a,b) for a,b in zip(poly,poly[1:]+poly[:1]) if max(a[1],b[1])<=front_limit(d)]
        if td>d.podium_radius:
            for side in (-1,1):segments.append(((side*d.width/2,-d.depth/2+d.podium_radius),(side*d.width/2,-d.depth/2+td)))
        for a,b in segments:
            f=Face(g,a,b)
            f.box(spec.frame,f.length/2,-.10,z+1.12,f.length,.08,.065)
            f.box('clear',f.length/2,-.10,z+.61,f.length-.025,.018,.94)
            n=max(1,math.ceil(f.length/1.6))
            for i in range(n+1):f.box(spec.frame,i*f.length/n,-.10,z+.59,.05,.08,1.13)
        front=-d.depth/2
        xlimit=max(0,d.width/2-max(d.podium_radius,2)-2)
        for x in (-xlimit,xlimit):
            planter(g,x,front+td*.48,z+.10,min(3.4,d.width*.22),.9)
            g.box('wood',(x,front+td*.78,z+.53),(min(2.4,d.width*.18),.48,.12))
            for dx in (-.65,.65):g.box(spec.frame,(x+dx,front+td*.78,z+.28),(.10,.40,.44))
        # Two open pergolas, leaving a clear central circulation route.
        if d.width>20:
            for x in (-d.width*.27,d.width*.27):
                span=min(7,d.width*.22)
                for xx in (x-span/2,x+span/2):
                    for yy in (front+.55,front+td-.45):g.box(spec.frame,(xx,yy,z+1.6),(.13,.13,3.2))
                for yy in (front+.55,front+td-.45):g.box(spec.frame,(x,yy,z+3.13),(span+.13,.16,.18))
                for i in range(9):g.box(spec.frame,(x-span/2+i*span/8,front+td/2,z+3.22),(.12,td-.65,.18))
    if d.atrium and d.base_floors==1:g.prism('ceiling',poly,d.base_height-.22,.20)
    root['atrium']=d.atrium
    root['podium_floors']=d.base_floors
    root['terrace_level']=d.ground_height if td else 0
    return upper


def front_limit(d):
    return -d.depth/2+max(d.podium_radius,d.terrace_depth)+.001
