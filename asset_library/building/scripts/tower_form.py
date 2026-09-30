"""Continuous tower outlines and full-height facade articulation."""
import math
from .geometry import rounded_footprint,footprint,Face


def mass_outline(m):
    w,d=m.width,m.depth;x,y=w/2,d/2;c=min(w,d)*m.notch
    if m.shape=='cross':
        return [(-x+c,-y),(x-c,-y),(x-c,-y+c),(x,-y+c),(x,y-c),(x-c,y-c),(x-c,y),(-x+c,y),(-x+c,y-c),(-x,y-c),(-x,-y+c),(-x+c,-y+c)]
    if m.shape=='chamfer':return footprint(w,d,c)
    if m.shape=='core_wing':
        k=w*.17;shoulder=y-d*.18
        return [(-x,-y),(x,-y),(x,shoulder),(k,shoulder),(k,y),(-k,y),(-k,shoulder),(-x,shoulder)]
    return rounded_footprint(w,d,m.radius)


def vertical_members(g,p,z,top,spec,style):
    if style=='none':return
    for a,b in zip(p,p[1:]+p[:1]):
        f=Face(g,a,b)
        if f.length<5:continue
        n=max(1,round(f.length/9));pitch=f.length/n
        for i in range(1,n):
            u=i*pitch
            if style=='piers':
                f.box(spec.wall,u,.20,(z+top)/2,.58,.70,top-z)
                f.box(spec.frame,u,.565,(z+top)/2,.18,.05,top-z)
            else:
                for du in (-.22,.22):f.box(spec.frame,u+du,.27,(z+top)/2,.13,.78,top-z)
