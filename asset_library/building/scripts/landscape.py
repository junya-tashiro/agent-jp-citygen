"""Building planting uses the road assets' branched shrubs and botanical leaves.

Small source stocks are cached per Blender file. Copies keep both mesh and
Geometry Nodes shoot libraries shared; no expanded leaf geometry per planter.
"""
import bpy,math
from mathutils import Matrix,Vector

def _stock(kind,variant):
    key=f'Building botanical stock {kind} {variant}'
    source=bpy.data.collections.get(key)
    if source:return source
    if kind=='shrub':
        from asset_library.planting.scripts.shrub_growth import create_shrubs
        root=create_shrubs(key,.72,.62,.72,.65,.94,931+variant*47,False,'low')
    else:
        from asset_library.street_tree.scripts.build_street_tree import create_street_tree
        root=create_street_tree(key,'keyaki',seed=831+variant*137,lod='low',height=4.7,crown_width=3.0,crown_start_height=1.7,trunk_diameter=.13,individual_variation=0)
    source=bpy.data.collections.new(key)
    for obj in list(root.children):
        # Containers provide soil; reuse only woody structure and foliage.
        if kind=='shrub' and 'soil' in obj.name:
            bpy.data.objects.remove(obj,do_unlink=True);continue
        for owner in list(obj.users_collection):owner.objects.unlink(obj)
        source.objects.link(obj);obj.parent=None
    bpy.data.objects.remove(root,do_unlink=True)
    return source

def place_stock(col,parent,kind,variant,position,scale=(1,1,1),angle=0):
    matrix=Matrix.Translation(Vector(position)) @ Matrix.Rotation(angle,4,'Z') @ Matrix.Diagonal((*scale,1))
    out=[]
    for src in _stock(kind,variant).objects:
        obj=src.copy();obj.data=src.data;col.objects.link(obj);obj.parent=parent;obj.matrix_basis=matrix @ src.matrix_basis
        obj['building_part']='botanical '+kind;out.append(obj)
    return out

def populate(col,parent,requests,offset):
    out=[]
    for x,y,z,w,d in requests:
        nx=max(1,round((w-.18)/.68));ny=max(1,round((d-.16)/.68)) if d>1.2 else 1
        sx=(w-.18)/nx;sy=(d-.16)/ny
        for j in range(ny):
            for i in range(nx):
                variant=(i+j+int(abs(x*7+y*11)))%3
                out+=place_stock(col,parent,'shrub',variant,(x-w/2+.09+i*sx+offset[0],y-d/2+.08+(j+.5)*sy+offset[1],z+.50+offset[2]),(sx/.72,sy/.62,.75+.05*variant))
    return out
