"""Check the lift's side envelope and floor against the evaluated scene."""
import bpy,json
from mathutils import Vector
scene=bpy.context.scene;scene.view_layers[0].update();dg=bpy.context.evaluated_depsgraph_get()
root=next(o for o in scene.objects if o.get('asset_type')=='subway_entrance' and o['variant']=='elevator')
w=json.loads(root['spec_json'])['width'];M=root.matrix_world;inv=M.inverted();glass_count=0;floor_count=0
for side in (-1,1):
    for y in (.12,.3,.55,.60,1.2,1.8,2.9):
        for z in (1.1,2.1,2.38,2.6,3.1):
            hit,p,_,_,obj,_=scene.ray_cast(dg,M@Vector((side*(w/2+.1),y,z)),M.to_3x3()@Vector((-side,0,0)),distance=.4)
            assert hit and obj.parent==root,(side,y,z,obj)
            expected='glass'
            assert obj.get('subway_part')==expected,(side,y,z,obj.name)
            assert abs((inv@p).x-side*(w/2-.12))<.002
            glass_count+=1
for y in (.12,.32,.54,.65,1.0,2.0,2.7,2.85):
    for x in ((-.6,0,.6) if y<.6 else (-1.1,-.6,0,.6,1.1)):
        hit,p,_,_,obj,_=scene.ray_cast(dg,M@Vector((x,y,.06)),Vector((0,0,-1)),distance=.15)
        assert hit and obj.parent==root,(x,y,obj.name if obj else None)
        assert -.001<=(inv@p).z<.03,(x,y,inv@p)
        floor_count+=1
assert json.loads(root['excavated_surfaces'])
print('ENCLOSURE_OK','side_samples',glass_count,'floor_samples',floor_count)
