"""Ray checks for concave envelopes, tall floors and open atria."""
import bpy,sys,json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from asset_library.building.scripts.build_buildings import create_building
from asset_library.building.scripts.design import derive_design,floor_z
from asset_library.building.scripts.catalog import get_spec
from asset_library.building.scripts.tower_form import mass_outline
from asset_library.building.scripts.geometry import Face,Geometry
for shape in ('rectangle','cross','chamfer','core_wing'):
 bpy.ops.wm.read_factory_settings(use_empty=True)
 opts=dict(tower_form='straight',plan_shape=shape,sky_floor=12,podium_radius=5,base_floors=4,base_program='terrace')
 d=derive_design(get_spec('building_13'),11,opts);root=create_building(d.key,design=opts)
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();m=d.masses[0];poly=mass_outline(m)
 z=floor_z(m,12,d.floor_height)
 for a,b in zip(poly,poly[1:]+poly[:1]):
  f=Face(Geometry(),a,b);point=Vector(f.point(f.length/2,.9,z+2))+Vector((m.x,m.y,0))
  hit,p,*_=bpy.context.scene.ray_cast(dg,point,Vector((-f.nx,-f.ny,0)),distance=2)
  assert hit,(shape,'open envelope',a,b)
 hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((m.x,m.y,z+d.floor_height+.3)),Vector((0,0,-1)),distance=.6)
 assert not hit,(shape,'floor inside tall storey',p)
 for level in range(1,d.base_floors):
  zz=d.ground_height+(level-1)*d.floor_height
  hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((0,-d.depth*.10,zz+.6)),Vector((0,0,-1)),distance=.9)
  assert not hit,(shape,'floor in atrium',p)
 assert len(json.loads(root['interior_programs_json']))==1
 if shape in ('cross','core_wing'):
  hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((m.x+m.width/2-.5,m.y+m.depth/2-.5,floor_z(m,3,d.floor_height)+.7)),Vector((0,0,-1)),distance=.8)
  assert not hit,(shape,'floor across recess',p)
 print('FORM_CHECK_OK',shape,flush=True)
print('ALL_FORMS_CHECKED',flush=True)
