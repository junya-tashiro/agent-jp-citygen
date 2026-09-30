"""Multi-stem evergreen shrubs, clipped envelope and three-dimensional shoots."""
import math
import random
import bpy
from mathutils import Vector
from asset_library.shared.foliage import Leaves


def create_shrubs(name, length, width, density, maintenance, health, seed, clipped, lod="medium", _foliage_only=False):
    from asset_library.planting.scripts import build_planting as base
    if length <= 0 or width <= 0:
        raise ValueError('length and width must be positive')
    for label,value in [('density',density),('maintenance',maintenance),('health',health)]:
        if not 0 <= value <= 1:
            raise ValueError(f'{label} must be between 0 and 1')
    if lod not in ('low', 'medium', 'high'):
        raise ValueError('lod must be low, medium or high')
    rng=random.Random(seed)
    top=.9 if clipped else .73
    if not _foliage_only:
        root=bpy.data.objects.new(name,None)
        bpy.context.collection.objects.link(root)
        for key,value in dict(asset_type='Branched evergreen hedge' if clipped else 'Branched low evergreen shrubs',length_m=length,width_m=width,nominal_height_m=top,density=density,maintenance=maintenance,health=health,seed=seed,lod=lod).items():
            root[key]=value
        soil=base._soil_material()
        base._cube(name+' soil bed base',(length*.5,0,-.015),(length,width,.145),soil,.018).parent=root
        base._soil_surface(name+' uneven soil surface',length,width,soil,rng).parent=root
        woody=base._material('Evergreen shrub woody branches',(.12,.09,.052),.83,.22)
        materials=[base._material('Evergreen shrub '+label+' leaves',color,.40,.12,.035)
                   for label,color in [('shade',(.034,.105,.018)),('mature',(.068,.183,.027)),('new',(.13,.265,.044)),('old',(.18,.19,.025)),('dry',(.16,.085,.025))]]
    verts,faces=[],[]
    leaves=Leaves()
    branch_count=0
    def branch(a,b,radius,segments=3):
        nonlocal branch_count
        a,b=Vector(a),Vector(b)
        offset=Vector((rng.uniform(-.025,.025),rng.uniform(-.025,.025),.025))
        path=[a.lerp(b,i/segments)+offset*math.sin(math.pi*i/segments) for i in range(segments+1)]
        if not _foliage_only:
            base._add_tapered_path(verts,faces,path,[radius*(1-.85*i/segments) for i in range(segments+1)],sides=5 if radius<.006 else 7)
        branch_count+=1
        return path
    def clamp_target(p):
        p.x=min(length-.045,max(.045,p.x)) if length>.09 else length*.5
        p.y=min(width*.5-.04,max(-width*.5+.04,p.y)) if width>.08 else 0
        p.z=min(top-(.030 if clipped else .065),max(.15,p.z))
        return p
    nx=max(1,math.ceil(length/.42)); ny=max(1,math.ceil(width/.42))
    for ix in range(nx):
        for iy in range(ny):
            center=Vector(((ix+.5)*length/nx+rng.uniform(-.035,.035),((iy+.5)/ny-.5)*width,.055))
            shrub_top=top-(rng.uniform(0,.035) if clipped else rng.uniform(0,.13)*(1.2-maintenance))
            stem=branch(center,center+Vector((rng.uniform(-.03,.03),rng.uniform(-.03,.03),.20)),.022,4)
            phase=rng.uniform(0,math.tau)
            stock_tint=rng.choices((0,1,2),(2,7,1))[0]
            for m in range(4):
                yaw=phase+m*math.tau/4
                axis=Vector((math.cos(yaw),math.sin(yaw),0))
                tip=clamp_target(center+axis*.13+Vector((0,0,rng.uniform(.28,.44))))
                main=branch(stem[2],tip,.010,4)
                for j in range(6):
                    yaw+=2.39996
                    direction=Vector((math.cos(yaw),math.sin(yaw),0))
                    target=clamp_target(center+direction*rng.uniform(.12,.30)+Vector((0,0,rng.uniform(.34,shrub_top-.07))))
                    secondary=branch(main[2+j%3],target,.004,3)
                    shoots=max(1,round(2+4*density))
                    leaves.begin_group()
                    for k in range(shoots):
                        end=target+Vector((rng.uniform(-.13,.13),rng.uniform(-.13,.13),rng.uniform(-.08,.14)))
                        # Dense crown and side shell, with genuine interior foliage.
                        roll=rng.random()
                        if roll<.30:
                            end.z=shrub_top-rng.uniform(.025,.135) if clipped else shrub_top-rng.uniform(.06,.17)
                        elif roll<.84:
                            end.y=(1 if center.y>=0 else -1)*(width*.5-rng.uniform(.055,.15))
                            end.z=rng.uniform(.17,shrub_top-.08)
                        end=clamp_target(end)
                        shoot=branch(secondary[1+k%3],end,.0016,2)
                        mat=stock_tint if rng.random()<.72 else rng.choices((0,1,2,3,4),(3,10,2,(1-health)*1.3,(1-health)*.3))[0]
                        azimuth=rng.uniform(0,math.tau)
                        leaf_count = 7 if lod == 'low' else 10
                        for n in range(leaf_count):
                            t=.78+.21*(n/(leaf_count-1))
                            anchor=shoot[1].lerp(shoot[2],max(0,t*2-1)) if t>=.5 else shoot[0].lerp(shoot[1],t*2)
                            yaw=azimuth+n*2.39996
                            direction=Vector((math.cos(yaw),math.sin(yaw),rng.uniform(-.24,.78))).normalized()
                            blade=rng.uniform(.055,.082)*(1.15 if lod == 'low' else 1.0)
                            leaves.add(anchor,direction,blade,blade*rng.uniform(.46,.56),rng.uniform(-.65,.65),mat)
    if _foliage_only:return leaves
    base._mesh_object(name+' woody branching framework',verts,faces,(woody,),smooth=True).parent=root
    leaves.mesh(name+' batched evergreen foliage',materials,'shrub',lod).parent=root
    root['plant_count']=nx*ny
    root['branch_count']=branch_count
    root['leaf_count']=len(leaves.sites)
    root['grass_blade_count']=0
    return root
