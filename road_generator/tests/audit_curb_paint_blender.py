"""Audit every parking-paint batch in a generated blend against its stone mesh.

Blender -b --python this_file -- /path/to/road_network.blend [--baseline]
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

args = sys.argv[sys.argv.index('--') + 1:]
blend = Path(args[0])
bpy.ops.wm.open_mainfile(filepath=str(blend))


def tops(obj):
    vs = obj.data.vertices
    matrix = obj.matrix_world
    return [(matrix @ ((vs[i+4].co + vs[i+7].co) * .5),
             matrix @ ((vs[i+5].co + vs[i+6].co) * .5))
            for i in range(0, len(vs), 8)]


reports = []
for paint in bpy.context.scene.objects:
    if 'parking curb' not in paint.name or not paint.name.endswith('painted blocks'):
        continue
    source = paint.get('source_curb')
    if source is None:
        prefix, side = paint.name.split(' parking curb ')
        source = (prefix + ' curb blocks' if side == 'painted blocks' else
                  prefix + (' right' if side.startswith('-1') else ' left') + ' curb blocks')
    curb = bpy.data.objects.get(source)
    assert curb is not None, (paint.name, source)
    stones = tops(curb)
    tree = KDTree(len(stones))
    for index, (a, b) in enumerate(stones):
        centre = (a+b)*.5
        tree.insert(Vector((centre.x, centre.y, 0)), index)
    tree.balance()
    errors, height_errors = [], []
    for a, b in tops(paint):
        centre = (a+b)*.5
        _, index, _ = tree.find(Vector((centre.x, centre.y, 0)))
        c, d = stones[index]
        if (a.xy-d.xy).length < (a.xy-c.xy).length:
            c, d = d, c
        errors.append(max((a.xy-c.xy).length, (b.xy-d.xy).length))
        height_errors.append(max(abs(a.z-c.z-.002), abs(b.z-d.z-.002)))
    reports.append(dict(paint=paint.name, source=source, blocks=len(errors),
                        misaligned=sum(e > 3e-5 or h > 2e-6
                                       for e,h in zip(errors,height_errors)),
                        max_endpoint_error_m=max(errors),
                        max_height_error_m=max(height_errors)))
result = dict(rows=len(reports), blocks=sum(r['blocks'] for r in reports),
              misaligned=sum(r['misaligned'] for r in reports), details=reports)
(blend.parent.parent/'curb_alignment_audit.json').write_text(json.dumps(result, indent=2))
print('CURB AUDIT', {k:v for k,v in result.items() if k!='details'}, flush=True)
for road in ('road_1', 'road_2', 'road_3', 'road_4'):
    subset=[r for r in reports if r['paint'].startswith(road+'_')]
    print(road, 'misaligned',sum(r['misaligned'] for r in subset),
          'max error', max((r['max_endpoint_error_m'] for r in subset), default=0), flush=True)
assert result['rows'] > 0
if '--baseline' not in args:
    assert result['misaligned'] == 0, result
