"""Pure-Python placement around the compiled GUI road network.

The road compiler owns road legality. This module owns conservative site
occupancy and reproducible architectural recipes, never road shape repairs.
"""
import hashlib,json,math,random,tempfile
from pathlib import Path
from .roads import compile_roads
from .distribution import public_asset_file
from .geometry import rectangle,overlap,inside,transform,site_bounds
from road_generator.core.schema import load_network
from road_generator.core.geometry import Centerline
from road_generator.core.offset_path import ApproachOffsetPath
from road_generator.core.planner import road_half_width_m
from road_generator.core.streets import sidewalk_footprint
from road_generator.core.parking import curved_frontage
from asset_library.building.scripts.catalog import get_spec
from asset_library.building.scripts.design import derive_design,plan_district,PROFILES

VERSION=1

def source_signature():
    root=Path(__file__).resolve().parents[1]
    paths=[]
    for folder in ('asset_library','road_generator/core','road_generator/blender','city_generator'):
        paths.extend(p for p in (root/folder).rglob('*.py') if 'tests' not in p.parts and p.name not in ('release.py','audit_blend.py'))
    paths.extend((root/'road_authoring/src').glob('*.ts'))
    paths.extend((root/'city_generator').glob('*.mjs'))
    # Only the four shared GUI modules belong to the public runtime.
    paths=[p for p in paths if p.suffix!='.ts' or p.name in ('authoring.ts','authoringV2.ts','geometry.ts','model.ts')]
    paths=[p for p in paths if p.relative_to(root).parts[0]!='asset_library' or public_asset_file(p.relative_to(root).as_posix())]
    h=hashlib.sha256()
    for p in sorted(paths):h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
    return h.hexdigest()


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def network_from(data):
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'network.json';p.write_text(json.dumps(data));network=load_network(p)
        from road_generator.core.general import validate_general_network
        validate_general_network(network)
        return network

def paths_and_envelopes(network):
    paths={};envelopes=[]
    for edge in network.edges:
        path=ApproachOffsetPath(Centerline.from_edge(network,edge),edge);paths[edge.id]=path
        outer=road_half_width_m(edge)+sidewalk_footprint(edge)
        count=max(1,math.ceil(path.length/1.0))
        for i in range(count):
            a,b=path.length*i/count,path.length*(i+1)/count
            envelopes.append([path.offset_point(a,-outer),path.offset_point(b,-outer),path.offset_point(b,outer),path.offset_point(a,outer)])
    return paths,envelopes

def place(network,paths,edge_id,station,side,local_bounds,anchor_x=0):
    edge=next((e for e in network.edges if e.id==edge_id),None)
    if edge is None:raise ValueError('Unknown edge '+str(edge_id))
    if side not in ('left','right'):raise ValueError('side must be left or right')
    if edge.sidewalks!='both':raise ValueError('Building/parking frontage requires a sidewalk')
    path=paths[edge.id];sgn=1 if side=='left' else -1
    if not 0<=station<=path.length:raise ValueError('station is outside edge')
    outer=road_half_width_m(edge)+sidewalk_footprint(edge)
    x0,y0,x1,y1=local_bounds
    front=curved_frontage(path,station,sgn*outer,sgn,x1-x0,anchor_x-x0)
    angle=math.atan2(front['tangent'][1],front['tangent'][0])
    origin=transform((-anchor_x,front['setback']-y0),front['mouth'],angle)
    polygon=rectangle(local_bounds,origin,angle)
    apron=[transform((x+x0,y-front['setback']+y0),origin,angle) for x,y in front['points']]
    apron+= [transform((x1,y0),origin,angle),transform((x0,y0),origin,angle)]
    return dict(connection=list(front['mouth']),edge=edge_id,station=station,side=side,position=[*origin,.02],rotation_degrees=math.degrees(angle),polygon=polygon,apron=apron)

def check_occupancy(row,bounds,roads,occupied):
    if not inside(row['polygon'],bounds):raise ValueError('Site exceeds city bounds')
    if any(overlap(row['polygon'],p) for p in roads):raise ValueError('Site overlaps road or sidewalk')
    if any(overlap(row['polygon'],p) for p in occupied):raise ValueError('Site overlaps another site')

def plan_city(request):
    allowed={'version','seed','bounds','roads','document','junctions','components','time_of_day','buildings','placements','subways'}
    if set(request)-allowed:raise ValueError('Unknown city fields: '+str(set(request)-allowed))
    if request.get('version')!=VERSION:raise ValueError('version must be 1')
    bounds=request['bounds']
    if len(bounds)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError('Invalid bounds')
    seed=request.get('seed',42)
    if type(seed)!=int:raise ValueError('seed must be integer')
    compiled=compile_roads(request);network=network_from(compiled['network'])
    if not network.edges:raise ValueError('At least one road is required')
    paths,roads=paths_and_envelopes(network);occupied=[];rows=[];warnings=[]
    settings={'count':20,'rounded_fraction':.1,'gap':1,'detail':'medium',**request.get('buildings',{})}
    if set(settings)-{'count','rounded_fraction','gap','detail'}:raise ValueError('Unknown buildings setting')
    if type(settings['count'])!=int or not 0<=settings['count']<=10000:raise ValueError('count must be 0..10000')
    if settings['detail'] not in ('medium','high'):raise ValueError('Invalid detail')
    if not 0<=settings['gap']<=20:raise ValueError('gap must be 0..20 metres')
    def add(item,automatic=False):
        kind=item.get('type','building')
        if kind=='building':
            spec=get_spec(item['key']);legacy=spec.family not in PROFILES
            if legacy:
                if item.get('design'):raise ValueError('Legacy 01-10 accept seed, not architectural overrides')
                from types import SimpleNamespace
                d=SimpleNamespace(parking=False)
                bb=[-spec.width/2-1.5,-spec.depth/2-2,spec.width/2+1.5,spec.depth/2+1.5]
                extra=dict(key=spec.key,seed=item.get('seed',seed),overrides={},design=None,signature=None,legacy=True)
            else:
                d=derive_design(spec,item.get('seed',seed),item.get('design',{}));bb=site_bounds(d)
                extra=dict(key=d.key,seed=d.seed,overrides=item.get('design',{}),design=d.payload(),signature=d.signature(),legacy=False)
        elif kind=='coin_parking':
            from asset_library.coin_parking.scripts.layout import plan
            layout=plan(item['width'],item['depth']);bb=[0,0,item['width'],item['depth']]
            extra=dict(width=item['width'],depth=item['depth'],capacity=layout.capacity)
        else:raise ValueError('Unknown placement type '+kind)
        anchor_x=layout.entrance_x if kind=='coin_parking' else ((-1 if d.parking_side=='left' else 1)*d.width*.27 if d.parking else 0)
        row=place(network,paths,item['edge'],item['station'],item['side'],bb,anchor_x)
        check_occupancy(row,bounds,roads,occupied)
        row.update(id=item.get('id',f'site_{len(rows)+1:03d}'),type=kind,local_bounds=bb,**extra)
        if any(r['id']==row['id'] for r in rows):raise ValueError('Duplicate placement ID '+row['id'])
        if kind=='coin_parking' or d.parking:
            x=layout.entrance_x if kind=='coin_parking' else (-1 if d.parking_side=='left' else 1)*d.width*.27
            target=row['connection']
            updated=compile_roads({'document':compiled['document'],'driveways':[target]})
            row['driveway']=updated['document']['components'][-1]['id']
            compiled.update(updated)
        rows.append(row)
        gap=settings['gap'] if automatic else 0
        occupied.append(rectangle([bb[0]-gap/2,bb[1],bb[2]+gap/2,bb[3]+gap/2],row['position'],math.radians(row['rotation_degrees'])))
    for item in request.get('placements',[]):
        try:add(item)
        except (ValueError,KeyError) as e:raise ValueError(f"{item.get('id','placement')}: {e}") from e
    pool=plan_district(max(settings['count']*3,1),seed,rounded_fraction=settings['rounded_fraction'])
    slots=[]
    for edge in network.edges:
        if edge.sidewalks!='both':continue
        path=paths[edge.id]
        for side in ('left','right'):
            for s in range(5,int(path.length)-4,4):slots.append((edge.id,s,side))
    random.Random(seed).shuffle(slots)
    for d in pool:
        if sum(r['type']=='building' for r in rows)>=settings['count']:break
        for edge,s,side in slots:
            try:add(dict(key=d.key,seed=d.seed,design={'tower_form':d.tower_form,'ground_mode':d.ground_mode},edge=edge,station=s,side=side),True);break
            except ValueError:continue
    actual=sum(r['type']=='building' for r in rows)
    if actual<settings['count']:warnings.append(f'Building target {settings["count"]}, placed {actual}; remaining sites do not fit. Increase bounds, reduce count, or specify smaller designs.')
    # Subway context is passed unchanged to the established pavement/raycast validator.
    compiled['network'].setdefault('context',{})['subway_entrances']=request.get('subways',[])
    network_from(compiled['network'])
    result=dict(version=VERSION,source_signature=source_signature(),seed=seed,bounds=bounds,request=request,document=compiled['document'],network=compiled['network'],placements=rows,detail=settings['detail'],warnings=warnings,summary={'buildings':actual,'coin_parking':sum(r['type']=='coin_parking' for r in rows),'subways':len(request.get('subways',[])), 'highrise':sum(bool(r.get('design')) and r['design']['floors']>20 for r in rows), 'rounded':sum(bool(r.get('design')) and r['design']['radius']>0 for r in rows), 'garage_buildings':sum(bool(r.get('design')) and r['design']['parking'] for r in rows), 'road_count':len(compiled['document']['roads']), 'unsignalized_junctions':sum(n['type'] in ('stop_cross','stop_t_junction','priority_t_junction') for n in compiled['network']['nodes'])})
    result['fingerprint']=fingerprint(result)
    return result

def validate_plan(plan):
    if plan.get('source_signature')!=source_signature():raise ValueError('Generator source changed; re-plan required')
    content={k:v for k,v in plan.items() if k!='fingerprint'}
    if fingerprint(content)!=plan.get('fingerprint'):raise ValueError('Plan changed: edit the request and re-plan, do not edit derived placements')
    compiled=compile_roads({'document':plan['document']})
    if {k:v for k,v in plan['network'].items() if k!='context'}!={k:v for k,v in compiled['network'].items() if k!='context'}:raise ValueError('Compiled roads differ')
    network=network_from(plan['network']);paths,roads=paths_and_envelopes(network);occupied=[]
    ids=set()
    for row in plan['placements']:
        if row['id'] in ids:raise ValueError('Duplicate site ID')
        ids.add(row['id'])
        anchor=0
        if row['type']=='building':
            spec=get_spec(row['key'])
            if row.get('legacy'):
                if spec.family in PROFILES:raise ValueError('Recipe cannot be marked legacy')
                expected_bounds=[-spec.width/2-1.5,-spec.depth/2-2,spec.width/2+1.5,spec.depth/2+1.5]
            else:
                d=derive_design(spec,row['seed'],row['overrides'])
                if json.loads(json.dumps(d.payload()))!=json.loads(json.dumps(row['design'])) or d.signature()!=row['signature']:raise ValueError('Recipe changed; re-plan required')
                expected_bounds=site_bounds(d)
                if d.parking:anchor=(-1 if d.parking_side=='left' else 1)*d.width*.27
        elif row['type']=='coin_parking':
            from asset_library.coin_parking.scripts.layout import plan as parking_plan
            layout=parking_plan(row['width'],row['depth']);anchor=layout.entrance_x
            expected_bounds=[0,0,row['width'],row['depth']]
        else:raise ValueError('Unknown placement type')
        if row['local_bounds']!=expected_bounds:raise ValueError('Site bounds differ from architectural recipe')
        expected=place(network,paths,row['edge'],row['station'],row['side'],expected_bounds,anchor)
        for key in ('position','rotation_degrees','polygon','apron','connection'):
            if json.loads(json.dumps(expected[key]))!=row[key]:raise ValueError('Derived placement differs: '+row['id']+' '+key)
        check_occupancy(row,plan['bounds'],roads,occupied);occupied.append(row['polygon'])
        if row.get('driveway'):
            component=next((c for c in network.components if c.id==row['driveway']),None)
            if component is None or component.edge_id!=row['edge'] or component.side!=row['side']:raise ValueError('Driveway does not serve its site')
            edge=next(e for e in network.edges if e.id==component.edge_id)
            lateral=(1 if component.side=='left' else -1)*(road_half_width_m(edge)+sidewalk_footprint(edge))
            mouth=paths[edge.id].offset_point(component.station,lateral)
            if math.dist(mouth,row['connection'])>.10:raise ValueError('Driveway entrance misalignment')
    return {'valid':True,**plan['summary'],'warnings':plan['warnings']}
