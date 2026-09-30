import bpy,sys,json
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from asset_library.building.scripts.build_buildings import create_building,preview_environment
from asset_library.building.scripts.catalog import get_spec
for rise in (1.2,1.8,2.4):
 bpy.ops.wm.read_factory_settings(use_empty=True);r=create_building('building_25',design={'site_height':rise});preview_environment(r,get_spec('building_25'));bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 x=r['parking_center_x']+1;profile=json.loads(r['parking_profile_json'])
 for (y0,z0),(y1,z1) in zip(profile,profile[1:]):
  y=(y0+y1)/2;z=(z0+z1)/2
  hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((x,y,z+.35)),Vector((0,0,-1)),distance=.6)
  assert hit and abs(p.z-z)<.03,(rise,'ramp floor',p,z)
 y=profile[-1][0]-3;z=profile[-1][1]
 hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((x,y,z+.1)),Vector((0,0,1)),distance=5)
 assert hit and p.z-z>=2.9,(rise,'headroom',p,z)
 for x,y,z in json.loads(r['perimeter_stair_samples_json']):
  hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((x,y,z+.2)),Vector((0,0,-1)),distance=.4)
  assert hit and abs(p.z-z)<.025,(rise,'perimeter stair tread',x,y,p,z)
 assert all(segment['kind'] in ('ramp edge','vehicle edge','portal edge','vehicle stair edge','stair handrail') for segment in json.loads(r['site_guards_json']))
 print('PARKING_CHECK_OK',rise,flush=True)
