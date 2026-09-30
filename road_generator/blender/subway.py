"""Context entrance placement and explicit pavement excavation for both renderers."""
import json
import math
import bpy
from mathutils import Vector, Matrix
from asset_library.subway_entrance.scripts.design import entrance_spec


def cut_opening(root,surfaces):
    """Subtract an entrance-local prism from nominated pavement/ground meshes."""
    spec=json.loads(root['spec_json']);bounds=spec['pavement_cutout']
    if bounds is None:return []
    from asset_library.subway_entrance.scripts.build_subway_entrance import Geometry
    x0,y0,x1,y1=bounds
    # Seat the pavement cut behind the stair lining, never on its visible face.
    if spec['variant']=='stairs':
        x0-=.06; x1+=.06; y1+=.06
        center_z,depth=-1.4,3.8
    else:
        # Shallow pavement replacement beneath the lift's dedicated floor slab.
        center_z,depth=-.12,.40
    g=Geometry();g.box('stone',((x0+x1)/2,(y0+y1)/2,center_z),(x1-x0,y1-y0,depth))
    vs,fs=g.batches['stone'];mesh=bpy.data.meshes.new('Temporary subway excavation');mesh.from_pydata(vs,[],fs);mesh.update()
    import bmesh
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);bm.to_mesh(mesh);bm.free()
    cutter=bpy.data.objects.new(mesh.name,mesh);bpy.context.scene.collection.objects.link(cutter)
    bpy.context.view_layer.update();cutter.matrix_world=root.matrix_world.copy()
    bpy.context.view_layer.update();inverse=root.matrix_world.inverted();changed=[]
    try:
        for obj in surfaces:
            if obj.type!='MESH':continue
            corners=[inverse@obj.matrix_world@Vector(p) for p in obj.bound_box]
            if max(p.x for p in corners)<=x0 or min(p.x for p in corners)>=x1 or max(p.y for p in corners)<=y0 or min(p.y for p in corners)>=y1:continue
            if max(p.z for p in corners)<-3.3 or min(p.z for p in corners)>.5:continue
            # Data may be shared by unrelated pieces of pavement.
            if obj.data.users>1:obj.data=obj.data.copy()
            # Boolean subtraction needs closed brick solids. Cutting the open
            # top faces first creates spurious upright caps at the entrance.
            if obj.get('asset_kind')=='sidewalk_brick_surface':
                for existing in list(obj.modifiers):
                    if existing.type=='SOLIDIFY':
                        with bpy.context.temp_override(object=obj,active_object=obj):
                            bpy.ops.object.modifier_apply(modifier=existing.name)
            modifier=obj.modifiers.new('Subway pavement opening','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
            modifier.use_hole_tolerant=True
            obj.modifiers.move(len(obj.modifiers)-1,0)
            with bpy.context.temp_override(object=obj,active_object=obj):bpy.ops.object.modifier_apply(modifier=modifier.name)
            changed.append(obj.name)
    finally:
        bpy.data.objects.remove(cutter,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    root['excavated_surfaces']=json.dumps(changed)
    root['excavation_bounds']=json.dumps([x0,y0,x1,y1])
    return changed


def add_subway_entrances(network):
    if not network.subway_entrances:return
    from asset_library.subway_entrance.scripts.build_subway_entrance import create_subway_entrance
    from road_generator.core.planner import SIDEWALK_TOP_Z_M
    scene=bpy.context.scene;bpy.context.view_layer.update()
    surfaces=[o for o in scene.objects if o.type=='MESH' and any(m and (m.name.startswith('Sidewalk') or m.name=='Urban ground') for m in o.data.materials)]
    # Validate the full body and 2m approach on existing pavement before mutating it.
    plans=[]
    for item in network.subway_entrances:
        spec=entrance_spec(item['variant'],item['width']);angle=math.radians(item['rotation_degrees'])
        transform=Matrix.Translation(Vector((*item['position'],SIDEWALK_TOP_Z_M)))@Matrix.Rotation(angle,4,'Z')
        w=spec['width'];length=spec['length'];dg=bpy.context.evaluated_depsgraph_get()
        for i in range(7):
            for j in range(math.ceil((length+2)/.25)+1):
                x=-w/2+.03+i*(w-.06)/6;y=-1.97+j*(length+1.94)/math.ceil((length+2)/.25)
                pt=transform@Vector((x,y,0))
                hit,loc,normal,index,obj,_=scene.ray_cast(dg,pt+Vector((0,0,8)),Vector((0,0,-1)),distance=9)
                if not hit or abs(loc.z-SIDEWALK_TOP_Z_M)>.06 or not any(m and m.name.startswith('Sidewalk') for m in obj.data.materials):
                    raise ValueError(f"Subway {item['id']}: body/approach must be on clear sidewalk; obstruction or edge at {tuple(pt)}")
        # Convex rectangle overlap via separating axes, including approaches.
        polygon=[transform@Vector((x,y,0)) for x,y in [(-w/2,-2),(w/2,-2),(w/2,length),(-w/2,length)]]
        for _,_,other in plans:
            axes=[(p[(k+1)%4]-p[k]).cross(Vector((0,0,1))).normalized() for p in (polygon,other) for k in (0,1)]
            if all(max(v.dot(a) for v in polygon)>min(v.dot(a) for v in other)+1e-6 and max(v.dot(a) for v in other)>min(v.dot(a) for v in polygon)+1e-6 for a in axes):
                raise ValueError('Subway entrance body/approach envelopes overlap')
        plans.append((item,transform,polygon))
    for item,transform,_ in plans:
        root=create_subway_entrance(**{k:item[k] for k in ('variant','width','station_name','station_roman','exit_label','weathering','routes')},name='Subway '+item['id'])
        root.matrix_world=transform;bpy.context.view_layer.update();cut_opening(root,surfaces)
        connect_tactile(root)


def connect_tactile(root):
    """Branch perpendicular to the local main-line tangent, then turn to the entrance."""
    from road_generator.core.planner import TactileTilePlan, SIDEWALK_TOP_Z_M
    from road_generator.blender.general_scene import (_PolylinePath, _tactile_tiles_along_path,
        _non_overlapping_tactile, _trim_continuous_tactile_joints, _tile_corners)
    from road_generator.blender.scene import _tactile_paving_mesh
    spec=json.loads(root['spec_json']);inv=root.matrix_world.inverted();candidates=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH' or not obj.name.startswith('Tactile paving guidance instances'):continue
        rotations=obj.data.attributes.get('instance_rotation');scales=obj.data.attributes.get('instance_scale')
        if rotations is None or scales is None:continue
        for v in obj.data.vertices:
            p=inv@obj.matrix_world@v.co;p.z=0
            angle=rotations.data[v.index].vector.z
            tangent=inv.to_3x3()@obj.matrix_world.to_3x3()@Vector((math.cos(angle),math.sin(angle),0))
            tangent.z=0;tangent.normalize()
            if not (-2.3<p.y<-.9 and spec['width']/2+.3<abs(p.x)<4.5):continue
            if abs(tangent.x)>math.sin(math.radians(20)) or not all(abs(v-1)<.02 for v in scales.data[v.index].vector):continue
            direction=Vector((-tangent.y,tangent.x,0))
            if direction.x*p.x>0:direction=-direction
            corner=p+direction*(-p.x/direction.x);corner.x=0
            if not -1.85<corner.y<-1.05:continue
            candidates.append((abs(corner.y+1.35),obj,v.index,p.copy(),direction,corner))
    if not candidates:
        root['tactile_connection']='No compatible guidance tile near approach';return
    dg=bpy.context.evaluated_depsgraph_get()
    stop=.08 if spec['variant']=='stairs' else -.779
    for _,obj,index,p,d,q in sorted(candidates,key=lambda c:c[0]):
        plans=[]
        def angle(axis):return math.degrees(math.atan2(axis.y,axis.x))
        plans.append(TactileTilePlan('branch_main','warning',tuple(p.xy),(.30,.30),'x',angle(d)))
        plans.append(TactileTilePlan('branch_turn','warning',tuple(q.xy),(.30,.30),'x',90))
        # Keep rectangular products outside the turn's warning square; the
        # oblique edge leaves the same small triangular joint as a road corner.
        corner_clear=(.15+.15*abs(d.y))/abs(d.x)+.002
        for name,start,end in [('branch_cross',p,q-d*corner_clear),('branch_entry',q+Vector((0,.15,0)),Vector((0,stop,0)))]:
            path=_PolylinePath((tuple(start.xy),tuple(end.xy)))
            _tactile_tiles_along_path(plans,name,path,0,path.length,0,route_key=name)
        # Adjacent main-line products use the same warning-priority trimming rules.
        removed={index}
        rotations=obj.data.attributes['instance_rotation'];scales=obj.data.attributes['instance_scale']
        for v in obj.data.vertices:
            local=inv@obj.matrix_world@v.co;local.z=0
            if v.index==index or (local-p).length>.65:continue
            rotation=rotations.data[v.index].vector.z
            axis=inv.to_3x3()@obj.matrix_world.to_3x3()@Vector((math.cos(rotation),math.sin(rotation),0))
            scale=scales.data[v.index].vector
            plans.append(TactileTilePlan('main_neighbor_'+str(v.index),'guidance',tuple(local.xy),(.30*scale.x,.30*scale.y),'x',angle(axis),'main'))
            removed.add(v.index)
        plans=_non_overlapping_tactile(_trim_continuous_tactile_joints(plans))
        polygons=[[Vector((*v,0)) for v in _tile_corners(tile)] for tile in plans]
        # Check the complete width of both legs and the turning pad before editing the main run.
        valid=True
        for tile,poly in zip(plans,polygons):
            if tile.id.startswith(('branch_main','main_neighbor_')):continue
            points=[sum(poly,Vector())/len(poly)]+[a.lerp(b,t) for a,b in zip(poly,poly[1:]+poly[:1]) for t in (0,.5)]
            for local in points:
                height=8 if local.y<-.1 else .08
                world=root.matrix_world@local
                hit,loc,_,_,surface,_=bpy.context.scene.ray_cast(dg,world+Vector((0,0,height)),Vector((0,0,-1)),distance=height+.2)
                pavement=hit and any(m and m.name.startswith('Sidewalk') for m in surface.data.materials)
                own_entry=hit and surface.parent==root and local.y>=-.1
                if not hit or abs(loc.z-root.location.z)>.015 or not (pavement or own_entry):valid=False;break
            if not valid:break
        if not valid:continue
        old=obj.data;keep=[v.index for v in old.vertices if v.index not in removed]
        mesh=bpy.data.meshes.new(old.name+' connected');mesh.from_pydata([tuple(old.vertices[i].co) for i in keep],[],[])
        for attrname in ('instance_scale','instance_rotation'):
            attr=mesh.attributes.new(attrname,'FLOAT_VECTOR','POINT')
            for j,k in enumerate(keep):attr.data[j].vector=old.attributes[attrname].data[k].vector
        obj.data=mesh;obj['tile_count']=len(keep)
        if old.users==0:bpy.data.meshes.remove(old)
        material=bpy.data.materials['Tactile paving yellow']
        parts=_tactile_paving_mesh(plans,material)
        for part in parts:
            for collection in list(part.users_collection):collection.objects.unlink(part)
            root.users_collection[0].objects.link(part)
            part.parent=root;part.location.z=-SIDEWALK_TOP_Z_M
            part['subway_part']='tactile_connection'
            # These points are entrance-local; only original road runs are branch candidates.
            part.name='Subway tactile '+root.name+' '+part.name.split('paving ')[-1]
        root['tactile_connection']=json.dumps({'main_tile_local':list(p),'corner_local':list(q),'branch_direction_local':list(d),'end_y':stop,'shared_road_tiles':True,'tile_plans':[{'id':t.id,'kind':t.kind,'center':t.center,'size':t.size,'rotation_degrees':t.rotation_degrees} for t in plans]})
        return
    root['tactile_connection']='Approach pavement unavailable for compatible guidance tiles'
