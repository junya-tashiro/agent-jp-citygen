"""Shared opaque leafy shoots, instanced in one geometry node modifier.

Road LOD shares a small shoot library across all trees/shrubs. Detailed asset
LODs retain the original individual blades. No alpha cards or realised copies.
"""
import bpy
import math
import random
import numpy as np
from mathutils import Vector, Matrix


def shared_foliage(leaves, name, materials, species):
    from .foliage import Leaves
    data = np.asarray(leaves.sites, dtype=np.float32)
    bounds = leaves.groups + [len(data)]
    groups = [data[a:b] for a,b in zip(bounds,bounds[1:]) if b>a]
    clouds = leaves.mesh(name,materials,species,'low',_coordinates_only=True)
    clouds = [clouds[a:b].reshape(-1,3) for a,b in zip(bounds,bounds[1:]) if b>a]
    key = 'Shared leafy shoots '+species+' '+materials[0].name
    sources = bpy.data.collections.get(key)
    def frame(group,cloud):
        delta=group[-1,:3]-group[0,:3]
        yaw=math.atan2(float(delta[1]),float(delta[0])) if species != 'shrub' else 0.0
        basis=Matrix.Rotation(yaw,3,'Z')
        local=cloud @ np.asarray(basis)
        low,high=local.min(axis=0),local.max(axis=0)
        centre=np.asarray(basis) @ ((low+high)*.5)
        return centre,basis,np.maximum(high-low,.0001)
    if sources is None:
        # The reference is fixed, never whichever tree happened to build first.
        if species == 'shrub':
            from asset_library.planting.scripts.shrub_growth import create_shrubs
            reference=create_shrubs('Reference',1.0,.85,.9,.82,.92,78191,True,
                                    'low',_foliage_only=True)
        else:
            from asset_library.street_tree.scripts.growth import grow
            from asset_library.street_tree.scripts.build_street_tree import SPECIES
            _,reference=grow(species,dict(SPECIES[species]),random.Random(78191),'low')
        reference_data=np.asarray(reference.sites,dtype=np.float32)
        reference_clouds=reference.mesh(name,materials,species,'low',_coordinates_only=True)
        reference_bounds=reference.groups+[len(reference_data)]
        source_groups=[reference_data[a:b] for a,b in zip(reference_bounds,reference_bounds[1:]) if b>a]
        source_clouds=[reference_clouds[a:b].reshape(-1,3) for a,b in zip(reference_bounds,reference_bounds[1:]) if b>a]
        sources = bpy.data.collections.new(key)
        for i in range(12):
            sample_index=(i*37)%len(source_groups)
            group = source_groups[sample_index]
            centre,basis,size = frame(group,source_clouds[sample_index])
            inv = basis.transposed()
            sample = Leaves()
            for site in group:
                pos = inv @ Vector(site[:3]-centre)
                direction = inv @ Vector(site[3:6])
                sample.add(pos,direction,float(site[6]),float(site[7]),float(site[8]),int(site[9]))
            obj = sample.mesh(key+f' {i:02d}',materials,species,'low')
            for owner in list(obj.users_collection): owner.objects.unlink(obj)
            sources.objects.link(obj)
            obj["cluster_size"]=list(map(float,size))
    positions=[];rotations=[];scales=[];indices=[]
    sizes=np.asarray([o['cluster_size'] for o in sorted(sources.objects,key=lambda o:o.name)])
    for group,cloud in zip(groups,clouds):
        centre,basis,size = frame(group,cloud)
        costs=np.abs(np.log(size[None,:]/sizes)).sum(axis=1)
        index=int(np.argmin(costs))
        positions.append(centre)
        rotations.append(tuple(basis.to_euler()))
        scales.append(size/sizes[index]);indices.append(index)
    mesh = bpy.data.meshes.new(name+' shoot points')
    mesh.vertices.add(len(groups));mesh.vertices.foreach_set('co',np.asarray(positions,dtype=np.float32).ravel())
    attr = mesh.attributes.new('shoot_rotation','FLOAT_VECTOR','POINT')
    attr.data.foreach_set('vector',np.asarray(rotations,dtype=np.float32).ravel())
    attr = mesh.attributes.new('shoot_scale','FLOAT_VECTOR','POINT')
    attr.data.foreach_set('vector',np.asarray(scales,dtype=np.float32).ravel())
    attr = mesh.attributes.new('shoot_variant','INT','POINT')
    attr.data.foreach_set('value',np.asarray(indices,dtype=np.int32))
    mesh.update()
    obj = bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    group_name = key+' instances'
    tree = bpy.data.node_groups.get(group_name)
    if tree is None:
        tree = bpy.data.node_groups.new(group_name,'GeometryNodeTree')
        tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        n=tree.nodes;l=tree.links
        inp=n.new('NodeGroupInput');out=n.new('NodeGroupOutput')
        coll=n.new('GeometryNodeCollectionInfo');coll.inputs['Collection'].default_value=sources
        coll.inputs['Separate Children'].default_value=True
        coll.inputs['Reset Children'].default_value=True
        inst=n.new('GeometryNodeInstanceOnPoints');inst.inputs['Pick Instance'].default_value=True
        rot=n.new('GeometryNodeInputNamedAttribute');rot.data_type='FLOAT_VECTOR';rot.inputs['Name'].default_value='shoot_rotation'
        scale=n.new('GeometryNodeInputNamedAttribute');scale.data_type='FLOAT_VECTOR';scale.inputs['Name'].default_value='shoot_scale'
        l.new(scale.outputs['Attribute'],inst.inputs['Scale'])
        idx=n.new('GeometryNodeInputNamedAttribute');idx.data_type='INT';idx.inputs['Name'].default_value='shoot_variant'
        l.new(inp.outputs['Geometry'],inst.inputs['Points']);l.new(coll.outputs['Instances'],inst.inputs['Instance'])
        l.new(rot.outputs['Attribute'],inst.inputs['Rotation']);l.new(idx.outputs['Attribute'],inst.inputs['Instance Index'])
        l.new(inst.outputs['Instances'],out.inputs['Geometry'])
    obj.modifiers.new('Shared opaque leafy shoots','NODES').node_group=tree
    obj['leaf_count']=len(data);obj['shared_shoot_count']=len(groups)
    return obj
