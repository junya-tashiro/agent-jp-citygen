"""Detect positive-area, coplanar, co-oriented rigid faces in entrance meshes."""
import bpy
import json
import sys
from collections import defaultdict
from pathlib import Path
from mathutils import Vector
report=[]
for root in [o for o in bpy.context.scene.objects if o.get('asset_type')=='subway_entrance']:
    groups=defaultdict(list)
    for obj in root.children:
        if obj.type!='MESH' or obj.get('subway_part') in ('lettering','pictogram','tactile_connection'):continue
        matrix=root.matrix_world.inverted()@obj.matrix_world
        for face in obj.data.polygons:
            if len(face.vertices)!=4:continue
            points=[matrix@obj.data.vertices[i].co for i in face.vertices]
            for axis in range(3):
                if max(p[axis] for p in points)-min(p[axis] for p in points)>1e-6:continue
                other=[i for i in range(3) if i!=axis]
                a,b=other
                rect=(min(p[a] for p in points),min(p[b] for p in points),max(p[a] for p in points),max(p[b] for p in points))
                # Bounding-box overlap is exact only for axis-aligned rectangles.
                # Annular sectors and other oblique quads need polygon intersection.
                if any(min(abs(p[a]-rect[0]),abs(p[a]-rect[2]))>1e-6 or min(abs(p[b]-rect[1]),abs(p[b]-rect[3]))>1e-6 for p in points):continue
                normal=(points[1]-points[0]).cross(points[2]-points[0])
                groups[(axis,round(points[0][axis],5),normal[axis]>0)].append((obj.name,face.index,rect))
    conflicts=[]
    for plane,faces in groups.items():
        for i,(name,index,a) in enumerate(faces):
            for other,j,b in faces[i+1:]:
                dx=min(a[2],b[2])-max(a[0],b[0]);dy=min(a[3],b[3])-max(a[1],b[1])
                if dx>1e-6 and dy>1e-6:conflicts.append({'plane':plane,'objects':[name,other],'faces':[index,j],'area':dx*dy})
    report.append({'root':root.name,'coplanar_overlaps':len(conflicts),'largest':sorted(conflicts,key=lambda v:-v['area'])[:25]})
args=sys.argv[sys.argv.index('--')+1:]
Path(args[0]).write_text(json.dumps(report,indent=2))
print('SURFACE_REPORT',json.dumps(report))
if len(args)>1 and args[1]=='--strict':assert not any(x['coplanar_overlaps'] for x in report)
