"""Combined evaluated-scene regression checks for the detailed entrance model."""
import bpy,runpy,sys,json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
folder=Path(__file__).parent
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
out=Path(args[0]) if args else Path('/tmp/subway_realism_surfaces.json')
for name in ('check_joints.py','check_enclosure.py','check_tactile_connections.py','check_double_doors.py'):
    sys.argv=['blender','--'];runpy.run_path(str(folder/name),run_name='__main__')
sys.argv=['blender','--',str(out),'--strict'];runpy.run_path(str(folder/'check_surfaces.py'),run_name='__main__')
scene=bpy.context.scene;dg=bpy.context.evaluated_depsgraph_get();fixtures=0
for root in [o for o in scene.objects if o.get('asset_type')=='subway_entrance']:
    M=root.matrix_world;inv=M.inverted();spec=json.loads(root['spec_json'])
    for o in root.children:
        if o.type=='LIGHT':
            assert o.get('subway_part')=='fixture_light' and o.data.energy>0
            hit,p,_,_,surface,_=scene.ray_cast(dg,o.matrix_world.translation,M.to_3x3()@Vector((0,0,1)),distance=.06)
            assert hit and surface.parent==root,(o.name,'unattached light')
            fixtures+=1
    if root['variant']=='stairs':
        # The outer opaque roof declines towards the gutter; no beam pierces it.
        for side in (-1,1):
            heights=[]
            for x in (.60,spec['width']/2-.10):
                hit,p,_,_,o,_=scene.ray_cast(dg,M@Vector((side*x,3.30,3.1)),Vector((0,0,-1)),distance=.5)
                assert hit and o.parent==root
                heights.append((inv@p).z)
            assert heights[0]>heights[1]+.04,heights
print('REALISM_CHECKS_OK fixtures',fixtures)
