"""Preview an already generated scene without rebuilding roads/assets."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--resolution',type=int,default=640);p.add_argument('--preview',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);t=time.perf_counter()
plan=json.loads(a.plan.read_text());report=json.loads((a.output/'build_report.json').read_text());bpy.ops.wm.open_mainfile(filepath=str(a.output/'city.blend'))
from asset_library.building.scripts.build_buildings import set_camera
from city_generator.planning import network_from
from road_generator.core.geometry import Centerline
scene=bpy.context.scene;scene.render.resolution_x=a.resolution;scene.render.resolution_y=round(a.resolution*.7);scene.render.resolution_percentage=100;scene.eevee.taa_render_samples=8
scene.render.filepath=str(a.output/'overview.png');bpy.ops.render.render(write_still=True)
network=network_from(plan['network']);edge=network.edges[len(network.edges)//2];path=Centerline.from_edge(network,edge)
from road_generator.core.offset_path import ApproachOffsetPath
from road_generator.core.planner import road_half_width_m
from road_generator.core.streets import sidewalk_footprint
path=ApproachOffsetPath(path,edge);lateral=road_half_width_m(edge)+sidewalk_footprint(edge)*.5 if edge.sidewalks=='both' else 1.625
pos=path.offset_point(path.length*.3,lateral);target=path.offset_point(min(path.length,path.length*.3+30),lateral);set_camera(scene.camera,(*pos,2),(*target,5),lens=28)
scene.render.filepath=str(a.output/'street.png');bpy.ops.render.render(write_still=True)
report.update(preview_seconds=time.perf_counter()-t,preview_resolution=a.resolution,renders=['overview.png','street.png'])
report['render_hashes']={name:hashlib.sha256((a.output/name).read_bytes()).hexdigest() for name in report['renders']}
(a.output/'build_report.json').write_text(json.dumps(report,indent=2))
