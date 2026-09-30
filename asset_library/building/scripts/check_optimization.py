"""Check that shared bevels preserve evaluated vertices, polygons and materials."""
import bpy,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from asset_library.building.scripts.build_buildings import create_building
from asset_library.building.scripts.optimize import share_evaluated_bevels
bpy.ops.wm.read_factory_settings(use_empty=True)
r=create_building('building_13',detail='medium');bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
checks={}
for o in r.children:
 if o.type!='MESH' or not o.name.startswith('Floor module'):continue
 m=o.evaluated_get(dg).to_mesh();v=np.empty(len(m.vertices)*3,dtype=np.float32);m.vertices.foreach_get('co',v)
 checks[o.name]=(v,tuple(tuple(p.vertices) for p in m.polygons),tuple(x.name for x in m.materials));o.evaluated_get(dg).to_mesh_clear()
report=share_evaluated_bevels(list(r.children));assert report['frozen_instances']>0
for name,(before,faces,mats) in checks.items():
 o=bpy.data.objects[name];m=o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh();v=np.empty(len(m.vertices)*3,dtype=np.float32);m.vertices.foreach_get('co',v)
 assert np.array_equal(before,v),name
 assert faces==tuple(tuple(p.vertices) for p in m.polygons),name
 assert mats==tuple(x.name for x in m.materials),name
 o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
print('OPTIMIZATION_GEOMETRY_EXACT',len(checks),report,flush=True)
