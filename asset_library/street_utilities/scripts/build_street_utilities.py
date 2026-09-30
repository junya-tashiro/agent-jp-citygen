"""Metre-scale road hardware, built as material-batched shared meshes."""
import math
import bpy
from road_generator.blender.primitives import weathered_material


def palette():
    def mat(name,a,b,rough=.7):
        return bpy.data.materials.get(name) or weathered_material(name,a,b,rough,85)
    return [mat('Utility cast iron',(.025,.031,.030),(.105,.113,.105)),
            mat('Utility dark recess',(.009,.012,.011),(.02,.024,.021),.95),
            mat('Utility concrete foundation',(.23,.24,.22),(.42,.43,.39),.9),
            mat('Utility cabinet coating',(.24,.25,.22),(.36,.37,.33),.55),
            mat('Utility zinc fixings',(.32,.34,.32),(.58,.60,.56),.4)]


class Parts:
    def __init__(self):self.vertices=[];self.faces=[];self.materials=[]
    def face(self,verts,mat):
        n=len(self.vertices);self.vertices.extend(verts);self.faces.append(tuple(range(n,n+len(verts))));self.materials.append(mat)
    def box(self,centre,size,mat=0):
        x,y,z=centre;a,b,c=(v*.5 for v in size)
        verts=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        n=len(self.vertices);self.vertices.extend(verts)
        for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
            self.faces.append(tuple(n+i for i in f));self.materials.append(mat)
    def ring(self,outer,inner,z,mat=0):
        for i in range(64):
            a=i*math.tau/64;b=(i+1)*math.tau/64
            self.face([(r*math.cos(t),r*math.sin(t),z) for r,t in [(outer,a),(outer,b),(inner,b),(inner,a)]],mat)
    def finish(self,name):
        mesh=bpy.data.meshes.new(name+' mesh');mesh.from_pydata(self.vertices,[],self.faces)
        for m in palette():mesh.materials.append(m)
        for p,m in zip(mesh.polygons,self.materials):p.material_index=m
        mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o)
        bevel=o.modifiers.new('Small cast and folded edges','BEVEL');bevel.width=.0015;bevel.segments=2
        return o


def create_utility(kind):
    p=Parts()
    if kind=='drain':
        p.box((0,0,.001),(.55,.55,.002),2)
        p.box((0,0,.003),(.49,.49,.002),1)
        for sign in (-1,1):
            p.box((sign*.244,0,.008),(.018,.506,.010),0)
            p.box((0,sign*.244,.008),(.47,.018,.010),0)
        for i in range(19):p.box((-.216+i*.024,0,.008),(.008,.47,.009),0)
        for y in (-.15,0,.15):p.box((0,y,.006),(.47,.006,.005),0)
        for x in (-.23,.23):
            for y in (-.23,.23):p.box((x,y,.014),(.011,.011,.003),4)
    elif kind=='cover':
        p.ring(.345,.300,.001,2);p.ring(.312,.291,.003,0);p.ring(.292,0,.002,1)
        p.ring(.286,.274,.005,0)
        for i in range(-10,11):
            v=i*.025;span=2*math.sqrt(max(0,.269**2-v*v))
            p.box((v,0,.004),(.006,span,.003),0)
            p.box((0,v,.004),(span,.006,.003),0)
        for x in (-.21,.21):p.box((x,0,.006),(.028,.078,.004),1)
        p.ring(.05,0,.007,0)
    elif kind=='cabinet':
        p.box((0,0,.12),(.76,.50,.24),2)
        p.box((0,0,.90),(.65,.38,1.36),3)
        p.box((0,0,1.602),(.69,.42,.045),3)
        p.box((0,-.193,.92),(.596,.010,1.25),1)
        p.box((0,-.202,.92),(.581,.014,1.233),3)
        for z in (.43,1.35):p.box((-.283,-.216,z),(.021,.018,.085),4)
        p.box((.23,-.218,.91),(.018,.024,.12),4)
        p.box((0,-.214,1.38),(.15,.003,.045),4)
        for z in (.49,.505,.52,.535,.55,.565):p.box((.15,.193,z),(.20,.004,.004),1)
        for x in (-.24,.24):
            p.box((x,.10,.22),(.044,.044,.20),0)
            p.box((x,-.14,.258),(.035,.035,.015),4)
    else:raise ValueError(kind)
    obj=p.finish('Road utility '+kind);obj['asset_type']='street_utility';obj['utility_kind']=kind
    return obj
