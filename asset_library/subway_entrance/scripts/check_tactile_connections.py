"""Audit shared products, non-overlap, continuous branches and source replacement."""
import bpy,json,sys,math
from pathlib import Path
from dataclasses import replace
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from road_generator.core.planner import TactileTilePlan
from road_generator.blender.general_scene import _tile_corners,_tiles_overlap

def distance(a,b):
    def point_segment(p,x,y):
        d=y-x;t=max(0,min(1,(p-x).dot(d)/d.length_squared));return (p-x-d*t).length
    return min([point_segment(p,x,y) for p in a for x,y in zip(b,b[1:]+b[:1])]+[point_segment(p,x,y) for p in b for x,y in zip(a,a[1:]+a[:1])])

prototypes={kind:next(o for o in bpy.data.objects if o.name.startswith('Tactile '+kind+' prototype') and o.data.materials[0].name=='Tactile paving yellow') for kind in ('guidance','warning')}
for root in [o for o in bpy.context.scene.objects if o.get('asset_type')=='subway_entrance']:
    data=json.loads(root['tactile_connection']);assert data['shared_road_tiles']
    tiles=[TactileTilePlan(t['id'],t['kind'],t['center'],t['size'],'x',t['rotation_degrees']) for t in data['tile_plans']]
    physical=[replace(t,size=tuple(s*.296/.30 for s in t.size)) for t in tiles]
    polys=[[Vector(p) for p in _tile_corners(t)] for t in physical]
    for i,a in enumerate(physical):
        for b in physical[:i]:assert not _tiles_overlap(a,b,tolerance=1e-7),(a.id,b.id)
    # The graph must remain connected through normal tile joints, including the turn.
    reached={0}
    while True:
        extra={j for j in range(len(polys)) if j not in reached and any(distance(polys[i],polys[j])<.012 for i in reached)}
        if not extra:break
        reached.update(extra)
    assert len(reached)==len(polys),(root.name,[tiles[i].id for i in range(len(tiles)) if i not in reached])
    main=root.matrix_world@Vector(data['main_tile_local'])
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH' and obj.name.startswith('Tactile paving guidance instances'):
            assert all((obj.matrix_world@v.co-main).xy.length>.01 for v in obj.data.vertices)
    entry=[t for t in physical if t.id.startswith('branch_entry')]
    assert abs(max(p[1] for t in entry for p in _tile_corners(t))-data['end_y'])<.004
    parts=[o for o in root.children if o.get('subway_part') in ('tactile_connection','tactile_warning')]
    for part in parts:
        group=part.modifiers[0].node_group
        proto=next(n.inputs['Object'].default_value for n in group.nodes if n.bl_idname=='GeometryNodeObjectInfo')
        assert proto in prototypes.values()
    print('TACTILE_CONNECTION_OK',root['variant'],'tiles',len(tiles),'shared_instances',len(parts))
