"""Run with Blender --background --python to check actual curb/paint meshes."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from road_generator.blender.general_scene import (
    _PolylinePath, _curb_blocks_along_path, _curb_paint_on_blocks,
)
from road_generator.blender.scene import _sidewalk_pair


def check(start, end, phase, direction, points, trimmed=False, straight=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = _PolylinePath(points)
    mat = bpy.data.materials.new('test')
    common = dict(logical_offset=phase, lowered_driveway_distances=(5.1,),
                  lowered_crossing_distances=(11.7,))
    curb = _curb_blocks_along_path('curb', path, start, end, .14, mat, **common)
    if straight:
        rows = []
        _sidewalk_pair('sidewalk', path.offset_point(start, 0), path.offset_point(end, 0),
                       6.5, 3.6, mat, mat, curb_rows=rows,
                       crossing_centers=(path.offset_point(11.7, 0),),
                       driveways_by_side={'left': (5.1-start,), 'right': (5.1-start,)})
        curb = rows[0 if direction < 0 else 1]
    _curb_paint_on_blocks('paint', curb, path,
                         start + (.7 if trimmed else 0), end - (.9 if trimmed else 0),
                         mat, logical_direction=direction, logical_offset=phase)
    paint = bpy.data.objects['paint painted blocks']
    # Endpoint centres of each box's top face: paint may narrow across the
    # block, but must use exactly its longitudinal ends and its height profile.
    def ends(obj):
        vs = obj.data.vertices
        return [tuple((vs[i+j].co + vs[i+k].co) * .5 for j,k in ((4,7),(5,6)))
                for i in range(0,len(vs),8)]
    stone_ends = ends(curb)
    for a,b in ends(paint):
        matches = [(c,d) for c,d in stone_ends
                   if (a.xy-c.xy).length < 2e-5 and (b.xy-d.xy).length < 2e-5]
        assert len(matches) == 1, (start,end,phase,a,b)
        c,d = matches[0]
        assert abs(a.z-c.z-.002) < 2e-6
        assert abs(b.z-d.z-.002) < 2e-6
    return len(ends(paint))


count = 0
for direction in (-1,1):
    for phase in (0, .173, -51.830786):
        for trimmed in (False,True):
            for points in (((0,0),(25,0)), ((0,0),(12,1),(25,3))):
                count += check(.137, 22.863, phase, direction, points, trimmed)
for direction in (-1,1):
    for phase in (0, .173, -51.830786):
        for trimmed in (False,True):
            for points in (((0,0),(25,0)), ((3,-2),(23,13))):
                count += check(.137, 22.863, phase, direction, points, trimmed, straight=True)
print(f'PASS: 48 curb cases; {count} painted blocks match actual curb ends and heights')
