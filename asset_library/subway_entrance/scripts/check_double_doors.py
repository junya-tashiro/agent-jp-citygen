"""Verify separated shaft/car facade and both physical landing/car door layers."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from asset_library.subway_entrance.scripts.elevator import LANDING_DOOR_Y,CAR_DOOR_Y
scene=bpy.context.scene;scene.view_layers[0].update();dg=bpy.context.evaluated_depsgraph_get()
root=next(o for o in scene.objects if o.get('variant')=='elevator');M=root.matrix_world;inv=M.inverted()
def ray(p,d,distance=.2):
    hit,point,_,_,o,_=scene.ray_cast(dg,M@Vector(p),M.to_3x3()@Vector(d),distance=distance)
    assert hit and o.parent==root,(p,d,o)
    return inv@point,o
for x in (-.5,.5):
    for y in (LANDING_DOOR_Y,CAR_DOOR_Y):
        p,o=ray((x,y-.04,1),(0,1,0),.035)
        assert o.get('subway_part')=='metal' and abs(p.y-(y-.017))<.001,(p,o.name)
        p,o=ray((x,y+.04,1),(0,-1,0),.035)
        assert o.get('subway_part')=='metal' and abs(p.y-(y+.017))<.001,(p,o.name)
assert .04<CAR_DOOR_Y-LANDING_DOOR_Y-.034<.08
for x in (-1.1,1.1):
    p,o=ray((x,-.05,1.5),(0,1,0))
    assert o.get('subway_part')=='glass' and abs(p.y-.0525)<.001
# The car return and inside controls are behind the glass facade, not its wall.
p,o=ray((-.79,.80,1.8),(0,-1,0),.25)
assert o.get('subway_part')=='porcelain' and .61<p.y<.65
frame=next(o for o in root.children if o.get('subway_part')=='frame')
assert frame.data.materials[0].name=='Subway / frame'
print('DOUBLE_DOORS_OK centre_gap_m',CAR_DOOR_Y-LANDING_DOOR_Y,'leaf_clearance_m',CAR_DOOR_Y-LANDING_DOOR_Y-.034)

# Sample all six cabin surfaces from its occupied interior. Rays must hit the car,
# never the stationary enclosure behind a missing panel.
half=min(.90,json.loads(root['spec_json'])['width']/2-.42)
counts={}
for name,direction in [('left',(-1,0,0)),('right',(1,0,0)),('front',(0,-1,0)),('back',(0,1,0)),('floor',(0,0,-1)),('ceiling',(0,0,1))]:
    points=[]
    if name in ('left','right'):
        points=[(0,y,z) for y in (.65,.8,1.6,2.4,2.55) for z in (.03,.1,.2,1.2,2.35,2.39)]
    elif name in ('front','back'):
        points=[(x,1.5,z) for x in (-half+.05,-.69,-.5,0,.5,.69,half-.05) for z in (.04,.1,.3,1.2,2.22,2.30,2.39)]
    else:
        points=[(x,y,1.3) for x in (-half+.04,0,half-.04) for y in (.65,.8,1.6,2.4,2.55)]
    for point in points:
        hit,o=ray(point,direction,3)
        assert o.get('subway_assembly')=='car',(name,point,o.name,list(hit))
    counts[name]=len(points)
print('CAR_SIX_FACES_OK',counts)

for x in (-1.1,1.1):
    p,o=ray((x,-.1,.60),(0,1,0))
    assert o.get('subway_part')=='stone' and abs(p.y)<.002,(p,o.name)
from asset_library.subway_entrance.scripts.controls import CALL_PANEL_RISE
panel_bottom=1.10+CALL_PANEL_RISE-.155
assert panel_bottom-.9685>.03
p,o=ray((.899,-.10,panel_bottom+.015),(0,1,0),.2)
assert o.get('subway_part')=='metal'
print('FRONT_PLINTH_OK panel_clearance_m',panel_bottom-.9685)

# Front post shoes must cover the pavement datum. The approach must not
# acquire an upright brick cap when the pavement is excavated.
width=json.loads(root['spec_json'])['width']
for side in (-1,1):
    p,o=ray((side*(width/2-.12),-.1,.005),(0,1,0))
    assert o.get('subway_part')=='frame',(p,o.name)
for x in (-.735,.735,.899):
    p,o=ray((x,-.1,.005),(0,1,0))
    assert o.get('subway_part')=='frame',(p,o.name)
for i in range(25):
    for z in (.01,.03):
        origin=M@Vector((-1.2+i*.1,-.03,z))
        hit,p,_,_,o,_=scene.ray_cast(dg,origin,M.to_3x3()@Vector((0,1,0)),distance=.08)
        assert not hit or o.parent==root,('Front pavement cap',i,z,o.name)
print('FRONT_FEET_AND_PAVEMENT_OK')
