"""Pave narrow residual strips beside sites using the road's actual tiles."""
import math
from .geometry import rectangle,outside_convex,overlap,inside,area
from .planning import paths_and_envelopes

def add_infill(plan,network,palette):
    from road_generator.blender.scene import _sidewalk_brick_polygon
    _,roads=paths_and_envelopes(network)
    sites=[r['polygon'] for r in plan['placements']]
    done=[];objects=[]
    for row in plan['placements']:
        x0,y0,x1,y1=row['local_bounds']
        poly=rectangle([x0-1.1,y0,x1+1.1,y1],row['position'],math.radians(row['rotation_degrees']))
        if not inside(poly,plan['bounds']):continue
        pieces=[poly]
        for cutter in roads+sites+done:
            pieces=[part for piece in pieces for part in (outside_convex(piece,cutter) if overlap(piece,cutter) else [piece])]
            if not pieces:break
        for p in pieces:
            if area(p)<.01:continue
            objects.append(_sidewalk_brick_polygon('City residual paving '+str(len(objects)),p,palette));done.append(p)
    return objects
