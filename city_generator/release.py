"""Produce a history-free source snapshot with generated README illustrations."""
import argparse,json,shutil
from pathlib import Path
from distribution import public_asset_file
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
if out.exists():raise SystemExit('Output exists; choose an empty new path')
files=[ROOT/'city.py',ROOT/'LICENSE',ROOT/'README.md',ROOT/'README.ja.md']
# Documentation illustrations are outputs, never scene-generation inputs.
readme_images={Path('media')/name for name in (
    'intersection_reverse.jpg','street_depth.jpg','building_store_detail.jpg',
    'parking.jpg','subway_elevator.jpg')}
files.extend(ROOT/path for path in sorted(readme_images))
for base in ('asset_library','road_generator/core','road_generator/blender','road_generator/tests','city_generator'):
    files.extend(f for f in (ROOT/base).rglob('*') if f.is_file() and f.suffix in ('.py','.js','.mjs','.json') and '__pycache__' not in f.parts)
files.append(ROOT/'road_generator/scripts/build_road_network.py')
files.extend((ROOT/'road_generator/examples').glob('*.json'))
files.extend((ROOT/'road_generator/examples/general_geometry').glob('*.json'))
files.extend((ROOT/'road_authoring/src'/f) for f in ('authoring.ts','authoringV2.ts','geometry.ts','model.ts'))
files.extend((ROOT/'examples/city').glob('*.json'))
files.extend((ROOT/'docs').glob('*.md'))
# Per-asset API references; no binary assets or legacy experiment outputs.
files.extend((ROOT/'asset_library').rglob('*.md'))
files=[f for f in files if f.relative_to(ROOT).parts[0]!='asset_library' or public_asset_file(f.relative_to(ROOT).as_posix())]
out.mkdir(parents=True)
for src in sorted(set(files)):
    dst=out/src.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
(out/'AGENTS.md').write_text('Read docs/AGENT_WORKFLOW.md before creating a scene. Normal scene work edits only scenes/<name>/. Keep the shared generator and validation rules unchanged unless explicitly developing a feature.\n')
(out/'.gitignore').write_text('scenes/\n__pycache__/\n*.pyc\n*.blend*\nnode_modules/\n.DS_Store\n')
for f in out.rglob('*'):
    if f.is_file() and f.suffix.lower() in ('.png','.jpg','.jpeg','.blend','.ttf','.otf','.ttc','.exr','.ply') and f.relative_to(out) not in readme_images:raise RuntimeError('Binary asset leaked: '+str(f))
exported=[f for f in out.rglob('*') if f.is_file()]
print(json.dumps({'output':str(out),'files':len(exported),'bytes':sum(f.stat().st_size for f in exported),'history_included':False}))
