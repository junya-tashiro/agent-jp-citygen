"""Material-batched geometry with hidden rectangular contact faces removed."""
import hashlib
import math
import bpy
from mathutils import Vector


def subtract_rectangle(rect, cutter):
    x0,y0,x1,y1=rect;a,b,c,d=cutter
    a,b,c,d=max(a,x0),max(b,y0),min(c,x1),min(d,y1)
    if c-a<=1e-9 or d-b<=1e-9:return [rect]
    pieces=[(x0,y0,a,y1),(c,y0,x1,y1),(a,y0,c,b),(a,d,c,y1)]
    return [p for p in pieces if p[2]-p[0]>1e-9 and p[3]-p[1]>1e-9]


class Geometry:
    def __init__(self):
        self._raw={};self._boxes=[];self._compiled=None
    def group(self,name):
        geometry=self
        class Assembly:
            def __getattr__(self,method):
                def emit(key,*args,**kwargs):return getattr(geometry,method)(name+'/'+key,*args,**kwargs)
                return emit
        return Assembly()
    def mesh(self,key,vertices,faces):
        self._compiled=None
        vs,fs=self._raw.setdefault(key,([],[]));n=len(vs)
        vs.extend(vertices);fs.extend(tuple(n+i for i in f) for f in faces)
    def box(self,key,center,size):
        if min(size)<=0:raise ValueError('Box dimensions must be positive')
        self._compiled=None
        lo=tuple(c-s/2 for c,s in zip(center,size));hi=tuple(c+s/2 for c,s in zip(center,size))
        self._boxes.append((key,lo,hi))
    @property
    def batches(self):
        if self._compiled is not None:return self._compiled
        result={k:(list(v),list(f)) for k,(v,f) in self._raw.items()}
        for index,(key,lo,hi) in enumerate(self._boxes):
            neighbours=[(j,a,b) for j,(_,a,b) in enumerate(self._boxes) if j!=index and all(b[k]>=lo[k]-1e-8 and a[k]<=hi[k]+1e-8 for k in range(3))]
            for axis in range(3):
                a,b=[i for i in range(3) if i!=axis]
                for sign in (-1,1):
                    plane=lo[axis] if sign<0 else hi[axis]
                    pieces=[(lo[a],lo[b],hi[a],hi[b])]
                    for other,clo,chi in neighbours:
                        inside=clo[axis]+1e-8<plane<chi[axis]-1e-8
                        lower=abs(plane-clo[axis])<1e-8
                        upper=abs(plane-chi[axis])<1e-8
                        # Contact interfaces disappear; coincident exterior faces
                        # retain only the last authored material at that location.
                        covered=inside or (lower and (sign>0 or other>index)) or (upper and (sign<0 or other>index))
                        if covered:
                            cut=(clo[a],clo[b],chi[a],chi[b])
                            pieces=[q for p in pieces for q in subtract_rectangle(p,cut)]
                        if not pieces:break
                    vs,fs=result.setdefault(key,([],[]))
                    for x0,y0,x1,y1 in pieces:
                        ring=[]
                        for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
                            p=[0.,0.,0.];p[axis]=plane;p[a]=x;p[b]=y;ring.append(tuple(p))
                        normal=(Vector(ring[1])-Vector(ring[0])).cross(Vector(ring[2])-Vector(ring[0]))
                        if normal[axis]*sign<0:ring.reverse()
                        n=len(vs);vs.extend(ring);fs.append(tuple(range(n,n+4)))
        self._compiled=result
        return result
    def tube(self,key,a,b,r=.021,n=12,caps=True):
        a,b=Vector(a),Vector(b);axis=(b-a).normalized()
        u=axis.cross(Vector((0,0,1)))
        if u.length<.01:u=axis.cross(Vector((0,1,0)))
        u.normalize();v=axis.cross(u)
        verts=[tuple(p+r*(math.cos(i*math.tau/n)*u+math.sin(i*math.tau/n)*v)) for p in (a,b) for i in range(n)]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))] if caps else []
        faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        self.mesh(key,verts,faces)
    def profile(self,key,section,start,end):
        """Closed X/Z section extruded along Y, in metres."""
        n=len(section)
        self.mesh(key,[(x,y,z) for y in (start,end) for x,z in section],
                  [tuple(reversed(range(n))),tuple(range(n,2*n))]+
                  [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
    def rail(self,key,points,r=.021,bend=.085,n=16,caps=True):
        """Continuous swept tube with tangent quadratic bends and closed ends."""
        points=[Vector(p) for p in points];path=[points[0]]
        for a,b,c in zip(points,points[1:],points[2:]):
            d=min(bend,(b-a).length*.35,(c-b).length*.35)
            p=b+(a-b).normalized()*d;q=b+(c-b).normalized()*d
            path.extend((1-t)**2*p+2*(1-t)*t*b+t*t*q for t in [i/8 for i in range(9)])
        path.append(points[-1]);verts=[];previous=None
        for i,p in enumerate(path):
            tangent=(path[min(i+1,len(path)-1)]-path[max(0,i-1)]).normalized()
            u=previous-tangent*previous.dot(tangent) if previous is not None else tangent.cross(Vector((1,0,0)))
            if u.length<.01:u=tangent.cross(Vector((0,1,0)))
            u.normalize();previous=u.copy();v=tangent.cross(u)
            verts.extend(tuple(p+r*(math.cos(j*math.tau/n)*u+math.sin(j*math.tau/n)*v)) for j in range(n))
        faces=[tuple(reversed(range(n))),tuple(range((len(path)-1)*n,len(path)*n))] if caps else []
        faces.extend((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j) for i in range(len(path)-1) for j in range(n))
        self.mesh(key,verts,faces)
    def pane(self,key,axis,position,u_range,z_range):
        # One optical surface per pane avoids doubling alpha at its front/back.
        u0,u1=u_range;z0,z1=z_range
        if axis=='x':verts=[(position,u0,z0),(position,u1,z0),(position,u1,z1),(position,u0,z1)]
        else:verts=[(u0,position,z0),(u1,position,z0),(u1,position,z1),(u0,position,z1)]
        self.mesh(key,verts,[(0,1,2,3)])
        # Arrised 8mm edge: slope into the optical centre without a coplanar
        # horizontal face against the sill or head gasket.
        for z,dz in ((z0,.0008),(z1,-.0008)):
            for side in (-1,1):
                edge=[(position+d,u,h) if axis=='x' else (u,position+d,h)
                      for d,u,h in ((side*.004,u0,z+dz),(side*.004,u1,z+dz),(0,u1,z),(0,u0,z))]
                self.mesh((key.rsplit('/',1)[0]+'/' if '/' in key else '')+'glass_edge',edge,[(0,1,2,3)])
    def finish(self,collection,parent):
        from .build_subway_entrance import palette
        mats=palette()
        for key,(vs,fs) in self.batches.items():
            if not fs:continue
            part=key.rsplit('/',1)[-1]
            mesh_name='Subway shared '+key+' '+hashlib.sha256(repr((vs,fs)).encode()).hexdigest()[:16]
            mesh=bpy.data.meshes.get(mesh_name)
            if mesh is None:
                mesh=bpy.data.meshes.new(mesh_name);mesh.from_pydata(vs,[],fs);mesh.materials.append(mats[part]);mesh.update()
                # Weld only coincident vertices; rectangular faces stay disjoint.
                import bmesh
                bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);bm.to_mesh(mesh);bm.free()
            if part=='handrail':
                for face in mesh.polygons:face.use_smooth=True
            obj=bpy.data.objects.new(mesh.name,mesh);collection.objects.link(obj);obj.parent=parent
            if part not in ('glass','car_glass','glass_edge','pictogram'):
                bevel=obj.modifiers.new('Manufactured edges','BEVEL');bevel.width={'stone':.003,'tile':.001,'metal':.0007,'rubber':.0004,'porcelain':.002,'frame':.001}.get(part,.0006);bevel.segments=2
                bevel.use_clamp_overlap=True
            obj['subway_part']=part
            obj['subway_assembly']=key.split('/')[0] if '/' in key else 'enclosure'
            obj['weathering']=parent.get('weathering',.18)
