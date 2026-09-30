"""Numerical checks for catalog meshes, module reuse and enclosed floor levels."""
import bpy,sys,math,json,runpy
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from asset_library.building.scripts.catalog import CATALOG
from asset_library.building.scripts.build_buildings import create_building
report=[]
for spec in CATALOG:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root=create_building(spec.key);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    objects=[o for o in root.children if o.type=='MESH'];meshes=set(o.data for o in objects)
    assert len(meshes)<len(objects),(spec.key,'no shared meshes')
    assert all(all(math.isfinite(c) for c in v.co) for m in meshes for v in m.vertices)
    assert all((o.data.materials and o.data.materials[0]) or any(m.type=='NODES' for m in o.modifiers) for o in objects)
    assert all(o.parent==root for o in objects)
    sections=json.loads(root['sections_json']);checks=0
    for s in sections:
        for i in (0,s['count']-1):
            z=s.get('floor_levels',[s['z']+j*spec.floor_height for j in range(s['count'])])[i]
            x,y=s['offset']
            hit,p,n,idx,obj,m=bpy.context.scene.ray_cast(dg,Vector((x,y,z+.7)),Vector((0,0,-1)),distance=1)
            assert hit and obj.parent==root,(spec.key,'missing floor',s,i)
            assert abs(p.z-(z+.20))<.025,(spec.key,p.z,z)
            checks+=1
    if 'design_json' in root:
        d=json.loads(root['design_json'])
        for floor in range(1,d['base_floors']):
            z=d['ground_height']+(floor-1)*d['floor_height']+d.get('site_height',0)
            hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((d['width']*.28,0,z+.7)),Vector((0,0,-1)),distance=1)
            if d.get('atrium'):assert not hit,(spec.key,'slab remains in atrium',floor,p.z)
            else:assert hit and abs(p.z-z-.20)<.03,(spec.key,'podium floor',floor,p.z)
        if d['terrace_depth']:
            z=d['ground_height']+d.get('site_height',0);y=-d['depth']/2+d['terrace_depth']*.50
            hit,p,*_=bpy.context.scene.ray_cast(dg,Vector((0,y,z+.7)),Vector((0,0,-1)),distance=1)
            assert hit and abs(p.z-z-.09)<.03,(spec.key,'terrace floor',p.z)
    if spec.key=='building_06':
        for x,y,z,expected in ((4.30,-9.60,.575,.55),(4.44,-9.85,.63,.60)):
            hit,p,n,idx,obj,matrix=bpy.context.scene.ray_cast(dg,Vector((x,y,z)),Vector((0,0,-1)),distance=.2)
            assert hit and abs(p.z-expected)<.005,('planter rim/soil height',p.z,expected)
    if spec.key=='building_11':
        from asset_library.building.scripts.geometry import rounded_footprint,Face,Geometry
        m=json.loads(root['design_json'])['masses'][0]
        poly=rounded_footprint(m['width'],m['depth'],m['radius'])
        for a,b in zip(poly,poly[1:]+poly[:1]):
            f=Face(Geometry(),a,b);origin=Vector(f.point(f.length/2,1,m['z']+spec.floor_height*.6))+Vector((m['x'],m['y'],0))
            hit,p,n,idx,obj,matrix=bpy.context.scene.ray_cast(dg,origin,Vector((-f.nx,-f.ny,0)),distance=2)
            assert hit and obj.parent==root,('rounded glazing gap',a,b)
    if spec.key=='building_16':
        m=json.loads(root['design_json'])['masses'][0];n=max(1,round(m['width']/m['bay']));bw=m['width']/n
        for i in range(n):
            origin=Vector((-m['width']/2+(i+.65)*bw,-m['depth']/2-.40,m['z']+.7))
            hit,p,norm,idx,obj,matrix=bpy.context.scene.ray_cast(dg,origin,Vector((0,0,-1)),distance=1)
            assert hit and obj.parent==root,('folded facade missing projecting floor',i)
    # Instantiating the same building reuses every geometric floor prototype.
    before={o.data for o in objects if o.name.startswith('Floor module')}
    duplicate=create_building(spec.key,name='duplicate');after={o.data for o in duplicate.children if o.name.startswith('Floor module')}
    assert before==after,(spec.key,'duplicate floor geometry')
    report.append(dict(key=spec.key,objects=len(objects),unique_meshes=len(meshes),floor_rays=checks,shared_floor_meshes=len(before)))
    print('BUILDING_CHECK_OK',spec.key,flush=True)
# Medium detail must retain identical section outlines and height.
bpy.ops.wm.read_factory_settings(use_empty=True)
a=create_building('building_07',detail='high');b=create_building('building_07',detail='medium')
assert a['sections_json']==b['sections_json'] and a['height']==b['height']
assert sum(len(o.data.vertices) for o in a.children if o.type=='MESH')>sum(len(o.data.vertices) for o in b.children if o.type=='MESH')
out=ROOT/'asset_library/building/renders/checks.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(report,indent=2));print('ALL_BUILDINGS_CHECKED',flush=True)
