"""Blender checks for label fitting, mesh reuse and width parameter endpoints."""
import bpy
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from asset_library.subway_entrance.scripts.build_subway_entrance import create_subway_entrance
bpy.ops.wm.read_factory_settings(use_empty=True)
a=create_subway_entrance(station_name='国際展示場正門前中央駅',width=2.6)
b=create_subway_entrance(station_name='中央',width=2.6,weathering=1)
c=create_subway_entrance('elevator',station_name='駅前',station_roman='Ekimae',exit_label='',width=4)
d=create_subway_entrance('elevator',station_name='中央',width=2.6)
e=create_subway_entrance('elevator',station_name='駅前',width=4,weathering=1)
mc={(o.get('subway_assembly'),o['subway_part']):o.data for o in c.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning')}
me={(o.get('subway_assembly'),o['subway_part']):o.data for o in e.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning')}
assert mc.keys()==me.keys() and all(mc[k]==me[k] for k in mc)
assert any(k[0]=='car' for k in mc) and any(k[0]=='enclosure' for k in mc)
ma={(o.get('subway_assembly'),o['subway_part']):o.data for o in a.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning')}
mb={(o.get('subway_assembly'),o['subway_part']):o.data for o in b.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning')}
assert all(o.get('weathering')==1 for o in b.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning'))
assert ma.keys()==mb.keys() and all(ma[k]==mb[k] for k in ma)
prototypes=[]
for root in (a,b):
    for o in root.children:
        if o.get('subway_part')=='tactile_warning':
            prototypes.append(next(n.inputs['Object'].default_value for n in o.modifiers[0].node_group.nodes if n.bl_idname=='GeometryNodeObjectInfo'))
assert len(set(prototypes))==1
for root,width in ((a,2.6),(b,2.6),(c,4),(d,2.6),(e,4)):
    for o in root.children:
        if o.get('subway_part')=='lettering':
            assert o.type=='MESH' and len(o.data.vertices)>0
            span=(max(v[0] for v in o.bound_box)-min(v[0] for v in o.bound_box))*o.scale.x
            assert span<=width+.01,(o.name,span)
    points=[v.co for o in root.children if o.type=='MESH' and o.get('subway_part') not in ('lettering','tactile_warning') for v in o.data.vertices]
    assert max(v.x for v in points)-min(v.x for v in points)<=width+.001
f=create_subway_entrance('elevator',station_name='四谷三丁目',routes=['M11'])
g=create_subway_entrance('stairs',station_name='中央',width=2.6,routes=['M15','H07','C08','G01','T01','N01'])
for root,count in ((f,1),(g,6)):
    route_labels=[o for o in root.children if o.get('sign_role')=='route']
    assert len(route_labels)==count*2*(2 if root['variant']=='stairs' else 1)
    assert all(o.get('label_text') not in ('A1','A2','改札方面') for o in root.children)
    for o in root.children:
        if o.get('sign_role'):
            import json
            half=json.loads(root['spec_json'])['width']/2-.08
            assert all(abs((o.matrix_basis@v.co).x)<half for v in o.data.vertices)
print('SUBWAY_API_OK shared meshes, long station name, 2.6m and 4m widths')
