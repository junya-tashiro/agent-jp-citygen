"""Conservative occupancy tests for convex site envelopes, in metres."""
import math

def transform(point, origin, angle):
    c,s=math.cos(angle),math.sin(angle);x,y=point
    return [origin[0]+c*x-s*y,origin[1]+s*x+c*y]

def rectangle(bounds, origin=(0,0), angle=0):
    x0,y0,x1,y1=bounds
    return [transform(p,origin,angle) for p in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]

def overlap(a,b,epsilon=.001):
    if any(max(p[k] for p in a)<=min(p[k] for p in b)+epsilon or max(p[k] for p in b)<=min(p[k] for p in a)+epsilon for k in (0,1)):return False
    for polygon in (a,b):
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            axis=(-(q[1]-p[1]),q[0]-p[0]);length=math.hypot(*axis)
            if length<1e-9:continue
            axis=(axis[0]/length,axis[1]/length)
            aa=[v[0]*axis[0]+v[1]*axis[1] for v in a];bb=[v[0]*axis[0]+v[1]*axis[1] for v in b]
            if max(aa)<=min(bb)+epsilon or max(bb)<=min(aa)+epsilon:return False
    return True

def inside(polygon,bounds):
    x0,y0,x1,y1=bounds
    return all(x0<=x<=x1 and y0<=y<=y1 for x,y in polygon)

def site_bounds(d):
    if d.parking:
        run=round(d.site_height/.15)*.34
        return [-d.width/2-6-run,-d.depth/2-22-run,d.width/2+6+run,d.depth/2+4+run]
    # Includes upper volumes, roof edges and projecting facade members.
    return [-d.width/2-.60,-d.depth/2-2.50,d.width/2+.60,d.depth/2+.60]


def area(poly):return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if len(poly)>2 else 0

def outside_convex(subject,clip):
    result=[];inside=list(subject)
    for a,b in zip(clip,clip[1:]+clip[:1]):
        def value(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        parts=[]
        for sign in (-1,1):
            out=[]
            for prev,cur in zip(inside[-1:]+inside[:-1],inside):
                u,v=sign*value(prev),sign*value(cur)
                if (u<0)!=(v<0):
                    t=u/(u-v);out.append((prev[0]+t*(cur[0]-prev[0]),prev[1]+t*(cur[1]-prev[1])))
                if v>=0:out.append(cur)
            parts.append(out)
        if area(parts[0])>.0001:result.append(parts[0])
        inside=parts[1]
        if len(inside)<3:break
    return result

