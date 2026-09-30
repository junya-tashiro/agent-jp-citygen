"""Recessed-path guards and spaced stair handrails."""
import math,json
from .geometry import Geometry


def guard_layout(d):
    side=-1 if d.parking_side=='left' else 1
    front=-d.depth/2-22;back=d.depth/2+4;left=-d.width/2-6;right=d.width/2+6
    car=side*d.width*.27;ramp=-side*(d.width/2+4.2)
    rise=d.site_height;segments=[]
    def add(kind,a,b,z=rise):
        if math.dist(a,b)>.01:segments.append(dict(kind=kind,a=(*a,z),b=(*b,z)))
    y0=front+.15
    openings=[(car-3.33,car+3.33),(ramp-1.10,ramp+1.10)]
    # Outer edges are continuous steps. Only recessed paths need guards.
    for xx in (ramp-1.10,ramp+1.10):add('ramp edge',(xx,y0),(xx,front+rise*15))
    run=round(rise/.15)*.34
    for xx in (car-3.40,car+3.40):segments.append(dict(kind='vehicle stair edge',a=(xx,front-run+.17,.15),b=(xx,front+.15,rise+.07)))
    # Three sides of the vehicle trench, leaving the street approach open.
    for xx in (car-3.33,car+3.33):add('vehicle edge',(xx,y0),(xx,front+16+.15),rise+.07)
    add('portal edge',(car-3.33,front+16+.15),(car+3.33,front+16+.15),rise+.07)
    # Repeated graspable rails run up the stairs, leaving the long frontage open.
    def flight(a,b):
        segments.append(dict(kind='stair handrail',a=(*a,.15),b=(*b,rise)))
    def stations(lo,hi):
        n=max(1,math.ceil(math.ceil((hi-lo)/8)/2))
        return [lo+(hi-lo)*(i+.5)/n for i in range(n)]
    for xx in stations(left+1,right-1):
        if all(not lo-1 < xx < hi+1 for lo,hi in openings):
            flight((xx,front-run+.17),(xx,front-.17))
        flight((xx,back+run-.17),(xx,back+.17))
    for yy in stations(front+1,back-1):
        flight((left-run+.17,yy),(left-.17,yy))
        flight((right+run-.17,yy),(right+.17,yy))
    return segments,openings


def create_guards(col,root,spec,d):
    segments,openings=guard_layout(d);g=Geometry();posts=set();height=1.20;run=round(d.site_height/.15)*.34
    for segment in segments:
        handrail=segment['kind']=='stair handrail'
        height=.90 if handrail else 1.20
        a,b=segment['a'],segment['b'];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);angle=math.atan2(dy,dx)
        cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2;z=a[2];dz=b[2]-a[2]
        for level,thick in (((.65,.04),(.90,.04)) if handrail else ((.12,.04),(height-.025,.05))):
            if dz:g.tube(spec.frame,(a[0],a[1],z+level),(b[0],b[1],b[2]+level),.027,8)
            else:g.box(spec.frame,(cx,cy,z+level),(length,.055,thick),angle)
        n=max(1,math.ceil(length/1.5))
        for i in range(n+1):
            x,y=a[0]+dx*i/n,a[1]+dy*i/n;key=(round(x,4),round(y,4),round(z,4))
            if key in posts:continue
            posts.add(key)
            base=z+dz*i/n
            if dz:base=min(d.site_height,max(.15,math.ceil((.17+length*i/n)/.34)*d.site_height/round(d.site_height/.15)))
            top=z+dz*i/n+height
            g.box(spec.frame,(x,y,(base+top)/2),(.07,.07,top-base))
            g.box(spec.frame,(x,y,base+.012),(.14,.14,.024))
        if handrail:continue
        n=max(1,math.ceil(length/.11))
        for i in range(1,n):
            x,y=a[0]+dx*i/n,a[1]+dy*i/n
            g.box(spec.frame,(x,y,z+dz*i/n+.65),(.018,.025,1.04),angle)
    objects=g.finish(col,root,'Recessed path guards')
    for obj in objects:obj['site_guard']=True
    root['site_guards_json']=json.dumps(segments);root['site_guard_openings_json']=json.dumps(openings)
    root['site_guard_height']=1.20;root['site_guard_version']=2
