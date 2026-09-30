"""Rectangular parking frontage against a sampled sidewalk outer boundary."""
import math


def curved_frontage(path, station, lateral, side, width, entrance_x, spacing=.25):
    mouth=path.offset_point(station,lateral)
    t=path.tangent_at_distance(station);tx,ty=t[0]*side,t[1]*side
    nx,ny=-ty,tx
    def project(s):
        p=path.offset_point(s,lateral);dx,dy=p[0]-mouth[0],p[1]-mouth[1]
        return entrance_x+dx*tx+dy*ty,dx*nx+dy*ny
    def boundary(target,direction):
        s=station;previous=project(s)[0]
        for _ in range(math.ceil(path.length/.5)+2):
            next_s=max(0,min(path.length,s+direction*side*.5));x=project(next_s)[0]
            if direction*(x-previous)<1e-8:
                raise ValueError('Parking frontage exceeds the edge or folds around the lot')
            if direction*(x-target)>=0:
                a,b=s,next_s
                for _ in range(35):
                    mid=(a+b)/2
                    if direction*(project(mid)[0]-target)<0:a=mid
                    else:b=mid
                return (a+b)/2
            s=next_s;previous=x
        raise ValueError('Cannot bracket parking frontage')
    start,end=boundary(0,-1),boundary(width,1)
    count=max(2,math.ceil(abs(end-start)/spacing))
    points=[project(start+(end-start)*i/count) for i in range(count+1)]
    points[0]=(0,points[0][1]);points[-1]=(width,points[-1][1])
    if any(b[0]<=a[0] for a,b in zip(points,points[1:])):
        raise ValueError('Sidewalk frontage must not fold back along parking frontage')
    curved=max(abs(y) for x,y in points)>.001
    setback=max(0,max(y for x,y in points))+.005 if curved else 0.0
    return {'mouth':mouth,'tangent':(tx,ty),'normal':(nx,ny),'points':points,
            'setback':setback,'stations':(start,end),'curved':curved}
