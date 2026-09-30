"""Attach a rectangular parking asset to an existing driveway cutout, including curved sidewalks."""
import math
import bpy
from mathutils import Matrix, Vector
from road_generator.core.geometry import Centerline
from road_generator.core.planner import road_half_width_m
from road_generator.core.streets import sidewalk_footprint
from road_generator.blender.general_scene import _ApproachOffsetPath
from road_generator.core.parking import curved_frontage
from asset_library.coin_parking.scripts import components as c
from asset_library.coin_parking.scripts.layout import plan
from asset_library.coin_parking.scripts.build_coin_parking import build_asset


def attach_parking_to_driveway(network, component_id, width, depth):
    """Front follows the actual sidewalk outer edge; local +Y faces away.

    An asphalt apron joins the rectangular lot to the curved sidewalk edge.
    The caller owns lot-to-lot/building clearance, like other context assets.
    """
    component=next((c for c in network.components if c.id==component_id),None)
    if component is None or component.kind!='driveway_cutout':
        raise ValueError('An existing driveway_cutout component is required')
    edge=next(e for e in network.edges if e.id==component.edge_id)
    if edge.sidewalks!='both':raise ValueError('Parking attachment requires a sidewalk')
    layout=plan(width,depth)
    raw=Centerline.from_edge(network,edge);path=_ApproachOffsetPath(raw,edge)
    side=1 if component.side=='left' else -1
    tangent=Vector((*raw.tangent_at_distance(component.station),0))*side
    lateral=side*(road_half_width_m(edge)+sidewalk_footprint(edge))
    frontage=curved_frontage(path,component.station,lateral,side,width,layout.entrance_x)
    mouth=Vector((*frontage['mouth'],.02));normal=Vector((*frontage['normal'],0))
    setback=frontage['setback'];lot_mouth=mouth+normal*setback
    angle=math.atan2(tangent.y,tangent.x)
    transform=Matrix.Translation(lot_mouth)@Matrix.Rotation(angle,4,'Z')@Matrix.Translation((-layout.entrance_x,0,0))
    collection,layout=build_asset(width,depth)
    if frontage['curved']:
        # The apron belongs to the parking asset, entirely outside the sidewalk.
        # The rectangle retreats to the furthest edge point to avoid overlap on
        # the inside of a bend. The opposite bend simply needs an infill wedge.
        points=frontage['points'];verts=[];faces=[]
        for x,y in points:verts.extend([(x,y-setback,0),(x,0,0),(x,y-setback,-.08),(x,0,-.08)])
        for i in range(len(points)-1):
            a=i*4;b=a+4
            faces.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)])
        faces.extend([(0,1,3,2),(len(verts)-4,len(verts)-2,len(verts)-1,len(verts)-3)])
        c.ACTIVE=collection
        apron=c.mesh_obj('curved asphalt parking apron',verts,faces,c.M['asphalt / weathered aggregate'])
        apron['max_depth_m']=max(setback-y for x,y in points)
        collection['frontage_setback_m']=setback
    for parent in [bpy.context.scene.collection,*bpy.data.collections]:
        if collection.name in parent.children:parent.children.unlink(collection)
    obj=bpy.data.objects.new('Parking at '+component_id,None)
    obj.instance_type='COLLECTION';obj.instance_collection=collection
    bpy.context.scene.collection.objects.link(obj);obj.matrix_world=transform
    obj['driveway_component']=component_id;obj['sidewalk_datum_m']=.02
    obj['entrance_world']=list(lot_mouth);obj['sidewalk_connection_world']=list(mouth);obj['frontage_setback_m']=setback;obj['capacity']=layout.capacity
    return obj,layout
