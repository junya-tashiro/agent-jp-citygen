"""Blender worker; consumes a validated plan, never repairs its geometry."""
import argparse,json,math,runpy,sys,time,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--preview',action='store_true');p.add_argument('--resolution',type=int,default=640)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);started=time.perf_counter()
plan=json.loads(a.plan.read_text());out=a.output;out.mkdir(parents=True,exist_ok=True)
from city_generator.planning import validate_plan,network_from
validate_plan(plan)
(out/'road_network.json').write_text(json.dumps(plan['network'],ensure_ascii=False,indent=2))
sys.argv=['build_road_network.py','--','--definition',str(out/'road_network.json'),'--output-root',str(out),'--output-name','roads','--render','none']
runpy.run_path(str(ROOT/'road_generator/scripts/build_road_network.py'),run_name='__main__')
road_seconds=time.perf_counter()-started
from asset_library.building.scripts.build_buildings import create_building,set_camera
from asset_library.building.scripts.geometry import Geometry
from asset_library.building.scripts.parking_plaza import excavate_context
from road_generator.blender.parking import attach_parking_to_driveway
from road_generator.blender.scene import _sidewalk_brick_palette,_sidewalk_brick_polygon
from road_generator.blender.subway import cut_opening
network=network_from(plan['network']);col=bpy.data.collections.new('City context');bpy.context.scene.collection.children.link(col)
x0,y0,x1,y1=plan['bounds'];g=Geometry();g.box('paving',((x0+x1)/2,(y0+y1)/2,-.3),(x1-x0,y1-y0,.5));ground=g.finish(col,None,'City ground')
terrain=[o for o in bpy.context.scene.objects if o.name.startswith('Surrounding terrain')]+ground
palette=_sidewalk_brick_palette();built=[]
for row in plan['placements']:
    if row['type']=='building':
        root=create_building(row['key'],seed=row['seed'],detail=plan['detail'],name=row['id'],design=None if row.get('legacy') else row['overrides'],include_forecourt=row.get('legacy',False))
        if not row.get('legacy') and root['design_signature']!=row['signature']:raise ValueError('Generated building differs from planned recipe '+row['id'])
        root.location=row['position'];root.rotation_euler.z=math.radians(row['rotation_degrees']);bpy.context.view_layer.update()
        # Tile the complete reserved site; the asset floor covers its occupied portion.
        paving=_sidewalk_brick_polygon(row['id']+' site paving',row['polygon'],palette)
        paving['city_site']=row['id'];excavate_context(root,terrain+[paving])
        apron=row['apron']
        if abs(sum(p[0]*q[1]-p[1]*q[0] for p,q in zip(apron,apron[1:]+apron[:1])))>.002:
            _sidewalk_brick_polygon(row['id']+' frontage apron',apron,palette)
    else:
        root,layout=attach_parking_to_driveway(network,row['driveway'],row['width'],row['depth'])
    root['city_id']=row['id'];built.append(root);print('CITY_PLACED',row['id'],flush=True)
from city_generator.infill import add_infill
infill=add_infill(plan,network,palette)
for root in list(bpy.context.scene.objects):
    if root.get('asset_type')=='subway_entrance':cut_opening(root,ground+infill)
from asset_library.building.scripts.optimize import share_evaluated_bevels
optimization=share_evaluated_bevels(list(bpy.context.scene.objects))
bpy.context.view_layer.update()
from city_generator.scene_checks import check_buildings
geometry_checks=check_buildings(plan,built)
# Independent finite-coordinate and generated root checks.
for root in built:
    if not all(math.isfinite(v) for v in root.location):raise ValueError('Non-finite transform')
scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT';scene.eevee.taa_render_samples=8
scene.render.resolution_x=a.resolution;scene.render.resolution_y=round(a.resolution*.7);scene.render.resolution_percentage=100
cx,cy=(x0+x1)/2,(y0+y1)/2;size=max(x1-x0,y1-y0);cam=scene.camera;cam.data.clip_end=max(3000,size*10)
height=max([float(r.get('height',0)) for r in built]+[20])
set_camera(cam,(cx+size*1.2,cy-size*1.5,size*1.2+height*.5),(cx,cy,height*.45),ortho=max(size*1.65,height*2.1))
# Freeze generated lettering as mesh; never pack source font files.
for ob in list(scene.objects):
    if ob.type=='FONT':
        mesh=bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        replacement=bpy.data.objects.new(ob.name+' mesh',mesh);scene.collection.objects.link(replacement);replacement.matrix_world=ob.matrix_world.copy();bpy.data.objects.remove(ob,do_unlink=True)
scene['city_plan_json']=json.dumps(plan,ensure_ascii=False);scene['city_plan_fingerprint']=plan['fingerprint']
blend=out/'city.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
build_seconds=time.perf_counter()-started
renders=[]
if a.preview:
    scene.render.filepath=str(out/'overview.png');bpy.ops.render.render(write_still=True);renders.append('overview.png')
    edge=network.edges[len(network.edges)//2]
    from road_generator.core.geometry import Centerline
    path=Centerline.from_edge(network,edge)
    from road_generator.core.offset_path import ApproachOffsetPath
    from road_generator.core.planner import road_half_width_m
    from road_generator.core.streets import sidewalk_footprint
    path=ApproachOffsetPath(path,edge);lateral=road_half_width_m(edge)+sidewalk_footprint(edge)*.5 if edge.sidewalks=='both' else 1.625
    pos=path.offset_point(path.length*.3,lateral);target=path.offset_point(min(path.length,path.length*.3+30),lateral)
    set_camera(cam,(*pos,2),(*target,5),lens=28);scene.render.filepath=str(out/'street.png');bpy.ops.render.render(write_still=True);renders.append('street.png')
# Do not embed third-party system fonts into release scenes.
for font in bpy.data.fonts:
    if font.packed_file:font.unpack(method='REMOVE')
from asset_library.shared.fonts import font_signature
report={'valid':True,'font_signature':font_signature(),'plan_fingerprint':plan['fingerprint'],'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),'blend':str(blend),'summary':plan['summary'],'road_seconds':road_seconds,'build_seconds':build_seconds,'total_seconds':time.perf_counter()-started,'blend_bytes':blend.stat().st_size,'objects':len(scene.objects),'meshes':len(bpy.data.meshes),'optimization':optimization,'geometry_checks':geometry_checks,'renders':renders,'warnings':plan['warnings']}
if a.preview:
    report['preview_resolution']=a.resolution
    report['render_hashes']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in renders}
(out/'build_report.json').write_text(json.dumps(report,indent=2));print('CITY_COMPLETE',flush=True)
