"""Freeze identical static bevel evaluations once, retaining evaluated geometry."""
import bpy,time


def share_evaluated_bevels(objects):
    start=time.perf_counter();groups={}
    for o in objects:
        if o.type!='MESH' or 'building_part' not in o or len(o.modifiers)!=1:continue
        m=o.modifiers[0]
        if m.type!='BEVEL' or m.name!='Edge highlights' or not m.show_render or not m.show_viewport:continue
        # Geometry.finish owns this exact static stack; never freeze user modifiers.
        if o.data.shape_keys or o.animation_data or m.vertex_group:continue
        settings=tuple((p.identifier,str(getattr(m,p.identifier))) for p in m.bl_rna.properties if not p.is_readonly and p.identifier!='name')
        groups.setdefault((o.data.as_pointer(),settings),[]).append(o)
    dg=bpy.context.evaluated_depsgraph_get();instances=0;sources=0
    for group in groups.values():
        if len(group)<2:continue
        first=group[0];old=first.data
        mesh=bpy.data.meshes.new_from_object(first.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
        mesh.name=old.name+' / shared bevel';mesh['shared_evaluated_bevel']=True
        for o in group:
            o.modifiers.clear();o.data=mesh;instances+=1
        if old.users==0:bpy.data.meshes.remove(old)
        sources+=1
    bpy.context.view_layer.update()
    return dict(frozen_instances=instances,shared_evaluations=sources,seconds=time.perf_counter()-start)
