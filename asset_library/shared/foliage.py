"""Batched, folded botanical blades. No alpha cards or per-leaf objects."""
import math
import bpy
import numpy as np
from mathutils import Vector


class Leaves:
    def __init__(self):
        self.sites = []
        self.groups = []

    def begin_group(self):
        self.groups.append(len(self.sites))

    def add(self, anchor, direction, length, width, roll, material=0):
        self.sites.append((*anchor, *direction, length, width, roll, material))

    def mesh(self, name, materials, species='keyaki', lod='medium', _coordinates_only=False):
        if lod == 'low' and self.groups and not _coordinates_only:
            from .leaf_clusters import shared_foliage
            return shared_foliage(self, name, materials, species)
        data = np.asarray(self.sites, dtype=np.float32).reshape((-1, 10))
        count = len(data)
        # Five blade stations give a rounded obovate outline on shrubs. The
        # midrib is raised, edges recurved, and distal blade curls down.
        stations = (0.15, .32, .52, .73, .90)
        widths = (.35, .75, 1., .78, .34)
        if species == 'shrub':
            widths = (.32, .68, .94, 1., .76)
        points = [(0., 0., 0.)]
        uv = [(.5, 0.)]
        for t, w in zip(stations, widths):
            for side in (-1, 0, 1):
                points.append((t, side*w*.5, (0.045 if side == 0 else -.035)*math.sin(t*math.pi)-.10*t**3))
                uv.append((.5+side*w*.5, t))
        points.append((1., 0., -.10))
        uv.append((.5, 1.))
        faces = [(0,2,1),(0,3,2)]
        for row in range(4):
            a, b = 1+row*3, 4+row*3
            faces.extend([(a,a+1,b+1),(a,b+1,b),(a+1,a+2,b+2),(a+1,b+2,b+1)])
        faces.extend([(13,14,16),(14,15,16)])
        if lod == 'low' and species != 'ginkgo':
            points = [(0,0,0),(.34,-.38,-.025),(.34,0,.035),(.34,.38,-.025),
                      (.73,-.37,-.07),(.73,0,-.015),(.73,.37,-.07),(1,0,-.10)]
            uv = [(y+.5,x) for x,y,z in points]
            faces = [(0,2,1),(0,3,2),(1,2,5),(1,5,4),(2,3,6),(2,6,5),(4,5,7),(5,6,7)]
        if species == 'ginkgo':
            # Long petiole, radiating fan, shallow central cleft.
            points = [(0,0,0),(.30,-.045,0),(.63,-.47,-.01),(.88,-.50,-.04),
                      (1.,-.30,-.065),(.97,-.07,-.045),(.86,0,-.025),
                      (.98,.09,-.045),(1.,.32,-.065),(.87,.50,-.04),
                      (.62,.46,-.01),(.30,.045,0),(.65,0,.035)]
            uv = [(y+.5,x) for x,y,z in points]
            faces = [(12,i,(i+1)%12) for i in range(12)]
        points = np.asarray(points, dtype=np.float32)
        faces = np.asarray(faces, dtype=np.int32)
        uv = np.asarray(uv, dtype=np.float32)
        axis = data[:,3:6].copy()
        axis /= np.maximum(np.linalg.norm(axis,axis=1)[:,None],1e-8)
        side = np.cross(axis, np.array((0,0,1),dtype=np.float32))
        vertical = np.linalg.norm(side,axis=1) < .01
        side[vertical] = (1,0,0)
        side /= np.maximum(np.linalg.norm(side,axis=1)[:,None],1e-8)
        normal = np.cross(side,axis)
        angle = data[:,8,None]
        across = side*np.cos(angle)+normal*np.sin(angle)
        normal = normal*np.cos(angle)-side*np.sin(angle)
        coords = (data[:,:3,None].transpose(0,2,1) +
                  axis[:,None,:]*points[None,:,0,None]*data[:,None,6,None] +
                  across[:,None,:]*points[None,:,1,None]*data[:,None,7,None] +
                  normal[:,None,:]*points[None,:,2,None]*data[:,None,6,None])
        if _coordinates_only:
            return coords
        triangles = (faces[None,:,:]+np.arange(count,dtype=np.int32)[:,None,None]*len(points)).reshape(-1,3)
        mesh = bpy.data.meshes.new(name+' mesh')
        mesh.vertices.add(count*len(points))
        mesh.vertices.foreach_set('co', coords.reshape(-1))
        mesh.loops.add(triangles.size)
        mesh.loops.foreach_set('vertex_index',triangles.reshape(-1))
        mesh.polygons.add(len(triangles))
        mesh.polygons.foreach_set('loop_start',np.arange(len(triangles),dtype=np.int32)*3)
        mesh.polygons.foreach_set('loop_total',np.full(len(triangles),3,dtype=np.int32))
        mesh.polygons.foreach_set('use_smooth',np.ones(len(triangles),dtype=bool))
        for mat in materials:
            mesh.materials.append(mat)
        mesh.polygons.foreach_set('material_index',np.repeat(data[:,9].astype(np.int32),len(faces)))
        layer = mesh.uv_layers.new(name='Leaf UV')
        layer.data.foreach_set('uv',np.tile(uv[faces].reshape(-1),count))
        mesh.update()
        obj = bpy.data.objects.new(name,mesh)
        bpy.context.collection.objects.link(obj)
        obj['leaf_count'] = count
        return obj
