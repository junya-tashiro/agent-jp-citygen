"""Validation for explicitly positioned, reusable subway context assets."""
import math
from asset_library.subway_entrance.scripts.sign_spec import normalize_routes
from asset_library.subway_entrance.scripts.design import entrance_spec


def parse_subway_entrances(items):
    if not isinstance(items,list):raise ValueError('context.subway_entrances must be an array')
    result=[];ids=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError('subway entrance must be an object')
        ident=item.get('id')
        if not isinstance(ident,str) or not ident or ident in ids:raise ValueError('subway entrance id must be unique and non-empty')
        ids.add(ident)
        spec=entrance_spec(item.get('variant','stairs'),item.get('width',3.0))
        pos=item.get('position')
        if not isinstance(pos,(list,tuple)) or len(pos)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in pos):
            raise ValueError('subway entrance position must contain two finite numbers')
        angle=item.get('rotation_degrees',0)
        if isinstance(angle,bool) or not isinstance(angle,(int,float)) or not math.isfinite(angle):raise ValueError('subway rotation must be finite')
        name=item.get('station_name')
        if not isinstance(name,str) or not name.strip():raise ValueError('subway station_name is required')
        weathering=item.get('weathering',.18)
        if isinstance(weathering,bool) or not isinstance(weathering,(int,float)) or not math.isfinite(weathering) or not 0<=weathering<=1:raise ValueError('subway weathering must be between 0 and 1')
        labels={k:item.get(k,'') for k in ('station_roman','exit_label')}
        if any(not isinstance(v,str) for v in labels.values()):raise ValueError('subway labels must be strings')
        result.append(dict(id=ident,variant=spec['variant'],width=spec['width'],position=tuple(pos),rotation_degrees=float(angle),station_name=name,weathering=float(weathering),routes=normalize_routes(item.get('routes')),**labels))
    return tuple(result)


def subway_context_bounds(network):
    points=[]
    for item in network.subway_entrances:
        s=entrance_spec(item['variant'],item['width'])
        a=math.radians(item['rotation_degrees']);c,d=math.cos(a),math.sin(a)
        for x,y in [(-s['width']/2,-2),(s['width']/2,-2),(-s['width']/2,8.5),(s['width']/2,8.5)]:
            points.append((item['position'][0]+c*x-d*y,item['position'][1]+d*x+c*y))
    return points
