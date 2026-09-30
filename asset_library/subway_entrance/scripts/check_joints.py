import bpy
from mathutils import Vector
scene=bpy.context.scene;dg=bpy.context.evaluated_depsgraph_get()
count=0
for root in [o for o in scene.objects if o.get('asset_type')=='subway_entrance']:
    if root['variant']=='stairs':
        samples=[((x,6.8,2.55),(0,-1,0),'frame') for x in (-1.35,-.8,0,.8,1.35)]
    else:
        samples=[((0,3.3,z),(0,-1,0),'frame') for z in (.975,1,1.04,1.07)]
        # Start inside the enclosure to exclude the outdoor brick edge from door-frame rays.
        samples += [((x,.01,z),(0,1,0),None) for x in (-.73,-.655,0,.655,.73) for z in (.025,.5,1.5,2.24,2.33)]
    for point,direction,part in samples:
        hit,p,_,_,obj,_=scene.ray_cast(dg,root.matrix_world@Vector(point),root.matrix_world.to_3x3()@Vector(direction),distance=.8)
        assert hit and obj.parent==root,(root.name,point,obj.name if obj else None)
        if part:assert obj.get('subway_part')==part,(point,obj.name)
        count+=1
print('JOINT_RAYS_OK',count)
