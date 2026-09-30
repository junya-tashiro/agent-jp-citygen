"""Independent saved-scene audit. Runs under Blender, no rendering."""
import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
plan=json.loads(bpy.context.scene['city_plan_json']);dg=bpy.context.evaluated_depsgraph_get();rows=[]
for row in plan['placements']:
 root=next(o for o in bpy.context.scene.objects if o.get('city_id')==row['id'])
 if row['type']!='building':continue
 inv=root.matrix_world.inverted();points=[]
 for obj in root.children_recursive:
  if obj.type not in ('MESH','CURVE','FONT'):continue
  ev=obj.evaluated_get(dg)
  points.extend(inv@ev.matrix_world@Vector(v) for v in ev.bound_box)
 if not points:raise ValueError('Empty building '+row['id'])
 if not all(math.isfinite(c) for p in points for c in p):raise ValueError('Non-finite building geometry '+row['id'])
 bb=[min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points)]
 planned=row['local_bounds'];outside=max(planned[0]-bb[0],planned[1]-bb[1],bb[2]-planned[2],bb[3]-planned[3],0)
 rows.append({'id':row['id'],'bounds':bb,'outside_m':outside})
report={'buildings':rows,'max_outside_m':max(r['outside_m'] for r in rows)}
Path(bpy.data.filepath).with_name('geometry_audit.json').write_text(json.dumps(report,indent=2));print('GEOMETRY_AUDIT',report['max_outside_m'])
