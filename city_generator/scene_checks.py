"""Checks evaluated Blender geometry against planned site envelopes."""
import math

def check_buildings(plan,roots):
    import bpy
    from mathutils import Vector
    dg=bpy.context.evaluated_depsgraph_get();checks=[]
    for row,root in zip(plan['placements'],roots):
        if row['type']!='building':continue
        inv=root.matrix_world.inverted();points=[]
        for obj in root.children_recursive:
            if obj.type not in ('MESH','CURVE','FONT'):continue
            ev=obj.evaluated_get(dg)
            points.extend(inv@ev.matrix_world@Vector(v) for v in ev.bound_box)
        if not points or not all(math.isfinite(c) for p in points for c in p):raise ValueError('Invalid generated geometry: '+row['id'])
        actual=[min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points)]
        expected=row['local_bounds'];outside=max(expected[0]-actual[0],expected[1]-actual[1],actual[2]-expected[2],actual[3]-expected[3],0)
        if outside>.02:raise ValueError(f"{row['id']}: generated geometry exceeds planned envelope by {outside:.3f}m; actual={actual}, planned={expected}")
        checks.append({'id':row['id'],'bounds':actual,'outside_m':outside})
    return checks
