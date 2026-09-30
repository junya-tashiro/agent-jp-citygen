"""Small street infrastructure, selected only inside usable roadside runs."""
import math
import random
import bpy
from .direct_assets import cached_asset_instance
from asset_library.shared.surfaces import asphalt_repair_material
from asset_library.street_utilities.scripts.build_street_utilities import create_utility
from road_generator.core.streets import seed_for


def utility(kind,name,point,angle):
    obj=cached_asset_instance(('street utility',kind),lambda:create_utility(kind),
                              name,point,angle)
    obj['utility_kind']=kind
    return obj


def repair(name,path,station,lateral,length,width,seed):
    rng=random.Random(seed)
    mat=asphalt_repair_material()
    vertices=[]
    # A saw-cut rectangle with centimetre-scale imperfect reinstatement edges.
    for x,y in [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)]:
        point=path.offset_point(station+x*length+rng.uniform(-.018,.018),lateral+y*width+rng.uniform(-.012,.012))
        vertices.append((*point,.00018))
    mesh=bpy.data.meshes.new(name+' mesh');mesh.from_pydata(vertices,[],[(0,1,2,3)]);mesh.materials.append(mat)
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    obj['asset_type']='local_asphalt_repair';obj['repair_seed']=seed
    return obj


class SurfaceReservations:
    """Conservative, spatially indexed paint bounds; includes collection instances."""
    def __init__(self,scene,materials):
        from mathutils import Matrix, Vector
        self.cells={}
        material_ids={m.as_pointer() for m in materials}
        def walk(obj,parent):
            world=parent @ obj.matrix_world
            if obj.instance_type=='COLLECTION' and obj.instance_collection:
                local=world @ Matrix.Translation(-obj.instance_collection.instance_offset)
                for child in obj.instance_collection.objects:walk(child,local)
            if obj.type!='MESH':return
            slots=obj.data.materials
            selected={i for i,m in enumerate(slots) if m and m.as_pointer() in material_ids}
            if not selected:return
            for polygon in obj.data.polygons:
                if polygon.material_index not in selected:continue
                points=[world@obj.data.vertices[i].co for i in polygon.vertices]
                xs=[p.x for p in points];ys=[p.y for p in points]
                self.add((min(xs),min(ys),max(xs),max(ys)))
        for obj in scene.objects:walk(obj,Matrix.Identity(4))
    @staticmethod
    def keys(bounds):
        x0,y0,x1,y1=bounds
        for x in range(math.floor(x0/3),math.floor(x1/3)+1):
            for y in range(math.floor(y0/3),math.floor(y1/3)+1):yield x,y
    def add(self,bounds):
        for cell in self.keys(bounds):self.cells.setdefault(cell,[]).append(bounds)
    def free(self,bounds):
        a,b,c,d=bounds
        return not any(a<=z and c>=x and b<=w and d>=y
                       for cell in self.keys(bounds)
                       for x,y,z,w in self.cells.get(cell,()))
    def choose(self,path,station,lateral,length,width,start,end,allowed):
        for delta in (0,.75,-.75,1.5,-1.5,2.5,-2.5,4,-4):
            s=station+delta
            if s-length*.5<start or s+length*.5>end or not allowed(s):continue
            corners=[path.offset_point(s+x*length,lateral+y*width) for x,y in [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)]]
            # Extra 15 cm beyond the physical frame / reinstatement edge.
            bounds=(min(p[0] for p in corners)-.15,min(p[1] for p in corners)-.15,
                    max(p[0] for p in corners)+.15,max(p[1] for p in corners)+.15)
            if self.free(bounds):
                self.add(bounds)
                return s
        return None
