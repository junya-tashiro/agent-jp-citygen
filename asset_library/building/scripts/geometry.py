"""Material batches and reusable floor meshes; no object per window."""
import bpy,math,hashlib
from mathutils import Vector
from .materials import material
class Geometry:
    def __init__(self):self.parts={};self.planting=[]
    def mesh(self,key,vertices,faces):
        vs,fs=self.parts.setdefault(key,([],[]));n=len(vs);vs.extend(vertices);fs.extend(tuple(n+i for i in face) for face in faces)
    def box(self,key,center,size,angle=0):
        if min(size)<=0:raise ValueError((key,size))
        cx,cy,cz=center;dx,dy,dz=[v/2 for v in size];c,s=math.cos(angle),math.sin(angle)
        verts=[(cx+x*c-y*s,cy+x*s+y*c,cz+z) for z in (-dz,dz) for y in (-dy,dy) for x in (-dx,dx)]
        self.mesh(key,verts,[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)])
    def prism(self,key,poly,z,height):
        n=len(poly);self.mesh(key,[(x,y,h) for h in (z,z+height) for x,y in poly],[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
    def tube(self,key,a,b,r=.025,n=8):
        a,b=Vector(a),Vector(b);axis=(b-a).normalized();u=axis.cross(Vector((0,0,1)))
        if u.length<.01:u=axis.cross(Vector((1,0,0)))
        u.normalize();v=axis.cross(u)
        self.mesh(key,[tuple(p+r*(math.cos(i*math.tau/n)*u+math.sin(i*math.tau/n)*v)) for p in (a,b) for i in range(n)], [tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
    def finish(self,col,parent,name,location=(0,0,0)):
        objects=[]
        for key,(vs,fs) in self.parts.items():
            digest=hashlib.sha256(repr((vs,fs)).encode()).hexdigest()[:16];meshname='Building module '+key+' '+digest
            mesh=bpy.data.meshes.get(meshname)
            if mesh is None:
                mesh=bpy.data.meshes.new(meshname);mesh.from_pydata(vs,[],fs);mesh.materials.append(material(key));mesh.update()
            obj=bpy.data.objects.new(name+' / '+key,mesh);col.objects.link(obj);obj.parent=parent;obj.location=location;obj['building_part']=key
            if key not in ('blue_glass','grey_glass','smoke_glass','clear','leaf','leaf_light','warm_light'):
                m=obj.modifiers.new('Edge highlights','BEVEL');m.width=.015 if key in ('concrete','limestone','pale_stone','granite') else .005;m.segments=1
                if key=='fabric':m.width=.035;m.segments=3
            objects.append(obj)
        if self.planting:
            from .landscape import populate
            objects.extend(populate(col,parent,self.planting,location))
        return objects

def footprint(w,d,chamfer=0):
    x=w/2;y=d/2;c=chamfer
    if c:return [(-x+c,-y),(x-c,-y),(x,-y+c),(x,y-c),(x-c,y),(-x+c,y),(-x,y-c),(-x,-y+c)]
    return [(-x,-y),(x,-y),(x,y),(-x,y)]

class Face:
    """u along wall, v positive outward, z up."""
    def __init__(self,g,a,b):
        self.g=g;self.a=a;dx,dy=b[0]-a[0],b[1]-a[1];self.length=math.hypot(dx,dy);self.tx,self.ty=dx/self.length,dy/self.length;self.nx,self.ny=self.ty,-self.tx;self.angle=math.atan2(dy,dx)
    def point(self,u,v,z):return (self.a[0]+self.tx*u+self.nx*v,self.a[1]+self.ty*u+self.ny*v,z)
    def box(self,key,u,v,z,width,depth,height):self.g.box(key,self.point(u,v,z),(width,depth,height),self.angle)
    def tube(self,key,a,b,r=.025,n=8):self.g.tube(key,self.point(*a),self.point(*b),r,n)


def rounded_footprint(w,d,radius=0,segments=8):
    """CCW rounded rectangle, with exact straight-to-arc tangent points."""
    if radius<=0:return footprint(w,d)
    r=min(radius,min(w,d)/2-.05);points=[]
    for cx,cy,start in ((w/2-r,-d/2+r,-90),(w/2-r,d/2-r,0),(-w/2+r,d/2-r,90),(-w/2+r,-d/2+r,180)):
        for i in range(segments+1):
            a=math.radians(start+i*90/segments);points.append((cx+r*math.cos(a),cy+r*math.sin(a)))
    return points

class EntranceGeometry(Geometry):
    """Clip individual facade solids around a doorway before material batching."""
    def __init__(self,bounds):
        super().__init__();self.opening=bounds
    def box(self,key,center,size,angle=0):
        # Ground entrances are on a straight cardinal facade.
        if abs(math.sin(angle*2))>1e-6:return super().box(key,center,size,angle)
        sx,sy,sz=size
        if abs(math.sin(angle))>.5:sx,sy=sy,sx
        c=center;lo=[c[i]-v/2 for i,v in enumerate((sx,sy,sz))];hi=[c[i]+v/2 for i,v in enumerate((sx,sy,sz))]
        cutlo=self.opening[:3];cuthi=self.opening[3:]
        if any(hi[i]<=cutlo[i] or lo[i]>=cuthi[i] for i in range(3)):return super().box(key,center,size,angle)
        for axis in range(3):
            for lower in (True,False):
                a=lo.copy();b=hi.copy()
                if lower:b[axis]=max(lo[axis],cutlo[axis])
                else:a[axis]=min(hi[axis],cuthi[axis])
                if all(b[i]-a[i]>1e-5 for i in range(3)):
                    super().box(key,tuple((a[i]+b[i])/2 for i in range(3)),tuple(b[i]-a[i] for i in range(3)))
            lo[axis]=max(lo[axis],cutlo[axis]);hi[axis]=min(hi[axis],cuthi[axis])
    def tube(self,key,a,b,r=.025,n=8):
        lo=self.opening[:3];hi=self.opening[3:]
        if all(max(a[i],b[i])+r>lo[i] and min(a[i],b[i])-r<hi[i] for i in range(3)):return
        super().tube(key,a,b,r,n)
