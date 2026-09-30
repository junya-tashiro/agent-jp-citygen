"""Named geometric parts of a lift sign, in unit-width design coordinates."""
import math


def arc(cx,cy,r,start,end,count=10):
    return [(cx+r*math.cos(math.radians(start+(end-start)*i/count)),cy+r*math.sin(math.radians(start+(end-start)*i/count))) for i in range(count+1)]


def rounded_rect(x0,z0,x1,z1,r):
    return (arc(x1-r,z1-r,r,0,90)+arc(x0+r,z1-r,r,90,180)+
            arc(x0+r,z0+r,r,180,270)+arc(x1-r,z0+r,r,270,360))


def softened_outline(points,radius=.03):
    result=[]
    for i,p in enumerate(points):
        prev=points[i-1];nxt=points[(i+1)%len(points)]
        d0=math.dist(p,prev);d1=math.dist(p,nxt);r=min(radius,d0*.4,d1*.4)
        a=tuple(p[k]+(prev[k]-p[k])*r/d0 for k in (0,1))
        b=tuple(p[k]+(nxt[k]-p[k])*r/d1 for k in (0,1))
        for j in range(7):
            t=j/6;result.append(tuple((1-t)**2*a[k]+2*t*(1-t)*p[k]+t*t*b[k] for k in (0,1)))
    return result


def add_lift_symbol(g,center,y,height=.43):
    """Original two-door cabin diagram, dimensioned from simple primitives."""
    cx,cz=center;u=height
    def box(x,z,w,h):g.box('pictogram',(cx+x*u,y,cz+z*u),(w*u,.001,h*u))
    # Door frame and split leaves; arrows above indicate bidirectional travel.
    for x in (-.29,.29):box(x,-.09,.035,.66)
    box(0,.23,.615,.035);box(0,-.42,.615,.035);box(0,-.10,.018,.61)
    for x,sgn in ((-.14,1),(.14,-1)):
        box(x,.36,.025,.19)
        z=.46 if sgn==1 else .265
        shape=[(x-.07,z-sgn*.07),(x,z),(x+.07,z-sgn*.07)]
        g.mesh('pictogram',[(cx+a*u,y-.002,cz+b*u) for a,b in shape],[(0,1,2)])
