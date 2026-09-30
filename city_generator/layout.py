"""Dependency-free schematic map of a saved plan, in world metres (+Y up)."""
import html
import math
from .planning import network_from, fingerprint
from .geometry import rectangle
from road_generator.core.geometry import Centerline
from road_generator.core.offset_path import ApproachOffsetPath
from road_generator.core.planner import road_half_width_m
from road_generator.core.streets import sidewalk_footprint


def svg(plan, title='City plan', labels=True):
    """Map stored geometry, including historical plans; do not certify build validity."""
    if plan.get('version') != 1:
        raise ValueError('Unsupported map plan version')
    if plan.get('fingerprint') != fingerprint({k: v for k, v in plan.items() if k != 'fingerprint'}):
        raise ValueError('Plan changed; regenerate the plan before mapping')
    x0, y0, x1, y1 = plan['bounds']
    if not all(math.isfinite(v) for v in (x0,y0,x1,y1)) or x1 <= x0 or y1 <= y0:
        raise ValueError('Invalid map bounds')
    w, h = x1-x0, y1-y0
    unit = max(w,h)/160
    margin = 7*unit
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0-margin} {-y1-13*unit} {w+2*margin} {h+40*unit}" role="img">',
             f'<title>{html.escape(title)}</title>',
             '<desc>Schematic plan. Building polygons are reserved sites, not roof outlines. Coordinates are metres; +Y is up, not geographic north.</desc>',
             '<style>text{font-family:Arial,sans-serif;fill:#243443} .label{paint-order:stroke;stroke:#fff;stroke-width:.5;stroke-linejoin:round}</style>',
             f'<rect x="{x0-margin}" y="{-y1-13*unit}" width="{w+2*margin}" height="{h+40*unit}" fill="#fff"/>']

    def text(x,y,value,size=1,anchor='start'):
        parts.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size*unit:.3f}" text-anchor="{anchor}">{html.escape(str(value))}</text>')

    def polygon(points, color, tooltip='', stroke=None):
        if not all(math.isfinite(v) for p in points for v in p):
            raise ValueError('Non-finite map coordinate')
        coordinates=' '.join(f'{x:.3f},{-y:.3f}' for x,y in points)
        border=f' stroke="{stroke}" stroke-width="{unit*.13}"' if stroke else ''
        parts.append(f'<polygon points="{coordinates}" fill="{color}"{border}><title>{html.escape(tooltip)}</title></polygon>')

    text(x0,-y1-7*unit,title,3)
    text(x0,-y1-3*unit,f'{w:g} x {h:g} m | {len(plan["placements"])} sites | seed {plan["seed"]}',1.4)
    parts.append(f'<defs><clipPath id="map-extent"><rect x="{x0}" y="{-y1}" width="{w}" height="{h}"/></clipPath></defs>')
    parts.append('<g id="map" clip-path="url(#map-extent)">')
    polygon(rectangle(plan['bounds']),'#f1eee7')
    network=network_from(plan['network'])
    paths={edge.id:ApproachOffsetPath(Centerline.from_edge(network,edge),edge) for edge in network.edges}
    # Continuous ribbons avoid hairline seams between independently drawn quads.
    def ribbon(path,width):
        n=max(1,math.ceil(path.length))
        stations=[path.length*i/n for i in range(n+1)]
        return [path.offset_point(t,-width) for t in stations]+[path.offset_point(t,width) for t in reversed(stations)]
    for layer,color,sidewalk in [('sidewalks','#d5d0c4',True),('carriageways','#8996a3',False)]:
        parts.append(f'<g id="{layer}">')
        for edge in network.edges:
            width=road_half_width_m(edge)+(sidewalk_footprint(edge) if sidewalk else 0)
            polygon(ribbon(paths[edge.id],width),color,edge.id)
        parts.append('</g>')
    parts.append('<g id="sites">')
    for row in plan['placements']:
        d=row.get('design') or {}
        floors=d.get('floors')
        parking=row['type']=='coin_parking'
        color='#c6b0d9' if parking else '#538c9c' if (floors or 0)>20 else '#9dc4c4'
        info=row['id']+(f' | {floors} floors' if floors else '')+(' | underground parking' if d.get('parking') else '')
        if row.get('apron'):polygon(row['apron'],'#d5d0c4')
        polygon(row['polygon'],color,info,'#435766')
        if labels:
            poly=row['polygon'];cx=sum(p[0] for p in poly)/len(poly);cy=sum(p[1] for p in poly)/len(poly)
            text(cx,-cy,'P' if parking else f'{floors}F' if floors else row['id'],1.7,'middle')
    parts.append('</g><g id="driveways">')
    for row in plan['placements']:
        if row.get('driveway'):
            x,y=row['connection']
            parts.append(f'<circle cx="{x}" cy="{-y}" r="{unit}" fill="#9c5d23"><title>{html.escape(row["id"])} driveway connection</title></circle>')
    parts.append('</g><g id="junctions">')
    for node in network.nodes.values():
        signal=node.kind.startswith('signalized_')
        if signal or node.kind in ('stop_cross','stop_t_junction','priority_t_junction'):
            x,y=node.position;color='#227651' if signal else '#d9912c'
            parts.append(f'<circle cx="{x}" cy="{-y}" r="{unit*1.3}" fill="{color}" stroke="white" stroke-width="{unit*.3}"><title>{html.escape(node.id)}: {node.kind}</title></circle>')
    parts.append('</g><g id="subways">')
    from asset_library.subway_entrance.scripts.design import entrance_spec
    for entry in plan['network'].get('context',{}).get('subway_entrances',[]):
        spec=entrance_spec(entry.get('variant','stairs'),entry.get('width',3))
        polygon(rectangle(spec['footprint'],entry['position'],math.radians(entry.get('rotation_degrees',0))),'#286bbe',entry.get('id','Subway'))
        if labels:
            x,y=entry['position'][:2];text(x,-y-2*unit,'SUB',1.2,'middle')
    parts.append('</g></g>')
    parts.append(f'<rect x="{x0}" y="{-y1}" width="{w}" height="{h}" fill="none" stroke="#8996a3" stroke-width="{unit*.2}"/>')
    legend=[('Road','#8996a3'),('Sidewalk','#d5d0c4'),('Building site','#9dc4c4'),('High-rise >20F','#538c9c'),('Parking','#c6b0d9'),('Subway','#286bbe'),('Signalized','#227651'),('Unsignalized','#d9912c'),('Driveway','#9c5d23')]
    for i,(label,color) in enumerate(legend):
        x=x0+(i%5)*w/5;y=-y0+(5+i//5*4)*unit
        parts.append(f'<rect x="{x}" y="{y-unit}" width="{unit*1.5}" height="{unit*1.5}" fill="{color}"/>')
        text(x+2*unit,y+.3*unit,label,1.25)
    target=w/5;base=10**math.floor(math.log10(target));scale=max(v*base for v in (1,2,5,10) if v*base<=target)
    y=-y0+15*unit
    parts.append(f'<path d="M{x0},{y-unit} v{unit} h{scale} v{-unit}" fill="none" stroke="#243443" stroke-width="{unit*.3}"/>')
    text(x0,y+2*unit,f'{scale:g} m',1.3)
    text(x1,y,'+Y up / +X right',1.3,'end')
    text(x0,y+6*unit,'Schematic: sites, not roof outlines. Hover for IDs. Street furniture and markings omitted.',1.15)
    parts.append('</svg>')
    return '\n'.join(parts)
