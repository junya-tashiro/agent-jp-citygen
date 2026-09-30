"""Pure-Python architectural recipes, independent of Blender and render detail.

Seeds select correlated massing, facade, base and crown decisions. District
sampling compares coarse *geometric* descriptors, not colors or random IDs.
"""
from dataclasses import dataclass,asdict,replace
import random,hashlib,json,math

PROFILES={
 'round_blade':('fins','curtain','dark_grid'),
 'soft_step':('stone_grid','fins','ribbon'),
 'offset_pair':('curtain','dark_grid','fins'),
 'terrace_tower':('dark_grid','stone_grid','curtain'),
 'round_ribbon':('ribbon','curtain','fins'),
 'folded_office':('folded',),
 'steel_loft':('exoskeleton','dark_grid'),
 'ceramic_screen':('ceramic','fins'),
 'arcade_office':('stone_grid','punched'),
 'garden_steps':('balcony','ribbon','stone_grid'),
}
@dataclass(frozen=True)
class Mass:
    width:float;depth:float;z:float;count:int;x:float;y:float;radius:float;facade:str;bay:float;shape:str="rectangle";notch:float=.18;tall_floor:int=-1;extra_height:float=0
@dataclass(frozen=True)
class Design:
    key:str;seed:int;width:float;depth:float;floors:int;floor_height:float;base_height:float;radius:float;base_style:str;roof_style:str;masses:tuple;base_floors:int;ground_height:float;base_program:str;terrace_depth:float;interior_program:str;parking:bool;site_height:float;parking_side:str;tower_form:str="straight";vertical_style:str="none";podium_radius:float=0;ground_mode:str="lobby";atrium:bool=False
    def payload(self):return asdict(self)
    def signature(self):
        p=self.payload();p.pop('seed');p.pop('key')
        return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:20]
    def descriptor(self):
        # Coarse bins ensure tiny dimensional jitter does not count as a new type.
        return (round(self.width/4),round(self.depth/4),round(self.floors/3),round(self.radius/2),self.base_style,self.roof_style,self.base_floors,self.base_program,round(self.terrace_depth),self.interior_program,self.parking,round(self.site_height,1),self.parking_side,self.tower_form,self.vertical_style,round(self.podium_radius/2),self.ground_mode,self.atrium,
                len(self.masses),len({round(m.z/self.floor_height) for m in self.masses}),
                tuple((round(m.width/self.width*8),round(m.depth/self.depth*8),round(m.x/2),round(m.y/2),round(m.count/3),round(m.z/self.floor_height/3),m.facade,m.shape,round(m.notch*10),m.tall_floor,round(m.extra_height)) for m in self.masses))

def derive_design(spec,seed=11,overrides=None):
    if spec.family not in PROFILES:raise ValueError('This family uses the authored legacy builder')
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError('seed must be an integer')
    rng=random.Random(int(hashlib.sha256(f'{spec.key}:{seed}:architecture-v1'.encode()).hexdigest()[:16],16))
    overrides=dict(overrides or {})
    allowed={'width','depth','floors','corner_radius','base_style','facade','roof_style','base_floors','base_program','terrace_depth','interior_program','parking','site_height','parking_side','tower_form','plan_shape','vertical_style','sky_floor','podium_radius','ground_mode','atrium'}
    if set(overrides)-allowed:raise ValueError('Unknown design overrides: '+str(set(overrides)-allowed))
    w=round(spec.width*rng.uniform(.90,1.12),1);d=round(spec.depth*rng.uniform(.90,1.10),1)
    floors=spec.floors+rng.randint(-3,4) if spec.floors>20 else spec.floors+rng.randint(-1,2)
    w=overrides.get('width',w);d=overrides.get('depth',d);floors=overrides.get('floors',floors)
    if isinstance(floors,bool) or not isinstance(floors,int) or not 6<=floors<=65:raise ValueError('floors must be an integer in 6..65')
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 6<=v<=100 for v in (w,d)):raise ValueError('width/depth must be finite metres in 6..100')
    family=spec.family;h=spec.floor_height;base=spec.base_height
    radius=round(min(w,d)*rng.uniform(.09,.19),2) if family in ('round_blade','soft_step','round_ribbon') else 0
    radius=overrides.get('corner_radius',radius)
    if not isinstance(radius,(int,float)) or not math.isfinite(radius) or not (radius==0 or .6<=radius<min(w,d)*.45):raise ValueError('corner_radius must fit the footprint')
    choices=('portico','lantern','arcade') if floors>20 else ('shopfront','deep_portal','arcade')
    default_base=rng.choice(choices)
    if family=='arcade_office':default_base='arcade'
    if seed==11:default_base={'round_blade':'portico','soft_step':'lantern','offset_pair':'portico','terrace_tower':'lantern','round_ribbon':'shopfront','folded_office':'deep_portal','steel_loft':'deep_portal','ceramic_screen':'shopfront','arcade_office':'arcade','garden_steps':'shopfront'}[family]
    base_style=overrides.get('base_style',default_base)
    roof_style=overrides.get('roof_style',rng.choice(('louver','stepped_cap','pergola')))
    if base_style not in ('portico','lantern','arcade','shopfront','deep_portal'):raise ValueError('Unknown base_style')
    if roof_style not in ('louver','stepped_cap','pergola'):raise ValueError('Unknown roof_style')
    facade=overrides.get('facade',PROFILES[family][0] if seed==11 else rng.choice(PROFILES[family]))
    if facade not in PROFILES[family]:raise ValueError('facade is incompatible with this family')
    # Independent stream preserves the established tower grammar.
    low=random.Random(f'{spec.key}:{seed}:podium-v1')
    defaults={'building_11':(3,'gallery'),'building_12':(4,'terrace'),'building_13':(3,'colonnade'),'building_14':(4,'terrace'),'building_21':(4,'gallery'),'building_22':(3,'terrace')}
    bf,program=(defaults if seed==11 else {}).get(spec.key,(low.choice((2,3,4)) if floors>20 else low.choice((1,2)),low.choice(('gallery','terrace','colonnade'))))
    if w<10:bf,program=1,'split_shop'
    bf=overrides.get('base_floors',bf);program=overrides.get('base_program',program)
    if isinstance(bf,bool) or not isinstance(bf,int) or not 1<=bf<=4:raise ValueError('base_floors must be 1..4')
    if program not in ('gallery','terrace','colonnade','split_shop'):raise ValueError('Unknown base_program')
    if program=='terrace' and bf<2:
        if 'base_floors' in overrides:
            if 'base_program' in overrides:raise ValueError('terrace requires at least two podium floors')
            program='gallery'
        else:bf=2
    ground=5.4 if floors>20 else 4.5
    terrace=overrides.get('terrace_depth',round(min(d*.18,5.5),2) if program=='terrace' else 0)
    if not isinstance(terrace,(int,float)) or not math.isfinite(terrace) or not 0<=terrace<=min(d*.3,8):raise ValueError('terrace_depth must fit the podium')
    if program=='terrace' and terrace<2:raise ValueError('A usable terrace needs at least 2 metres')
    if program!='terrace' and terrace:raise ValueError('terrace_depth requires terrace program')
    interior_rng=random.Random(f'{spec.key}:{seed}:interior-v1')
    interior=overrides.get('interior_program','convenience' if spec.key=='building_26' else interior_rng.choice(('business','hospitality','cafe','gallery')))
    parking=overrides.get('parking',spec.key=='building_25')
    if interior not in ('business','hospitality','cafe','gallery','convenience'):raise ValueError('Unknown interior_program')
    if not isinstance(parking,bool):raise ValueError('parking must be boolean')
    if parking and (w<30 or d<38 or radius):raise ValueError('Parking ramp requires a rectangular footprint at least 30 x 38 m')
    if interior=='convenience' and (w<12 or d<12):raise ValueError('Convenience store requires at least 12 x 12 m')
    site_height=overrides.get('site_height',1.8 if parking else 0)
    parking_side=overrides.get('parking_side','left')
    if not isinstance(site_height,(int,float)) or not math.isfinite(site_height) or not (1.2<=site_height<=2.4 if parking else site_height==0):raise ValueError('site_height must be 1.2..2.4 for parking, otherwise zero')
    if parking_side not in ('left','right'):raise ValueError('parking_side must be left or right')
    form_rng=random.Random(f'{spec.key}:{seed}:form-v2')
    high=floors>20
    form=overrides.get('tower_form',form_rng.choices(('straight','stepped','paired'),(80,15,5))[0] if high else 'straight')
    if form not in ('straight','stepped','paired'):raise ValueError('Unknown tower_form')
    shape=overrides.get('plan_shape','rectangle' if radius or not high else form_rng.choice(('rectangle','cross','chamfer','core_wing')))
    if shape not in ('rectangle','cross','chamfer','core_wing'):raise ValueError('Unknown plan_shape')
    if radius and shape!='rectangle':raise ValueError('Rounded towers require rectangle plan_shape')
    vertical=overrides.get('vertical_style',form_rng.choice(('piers','paired_fins','none')) if high else 'none')
    if vertical not in ('piers','paired_fins','none'):raise ValueError('Unknown vertical_style')
    podium_radius=overrides.get('podium_radius',round(min(w,d)*.18,2) if high and not radius and form_rng.random()<.3 else radius)
    if not isinstance(podium_radius,(int,float)) or not math.isfinite(podium_radius) or not 0<=podium_radius<min(w,d)*.4:raise ValueError('Invalid podium_radius')
    mode=overrides.get('ground_mode','continuous' if not high and interior!='convenience' and 'base_floors' not in overrides and 'base_program' not in overrides and ('interior_program' not in overrides or interior in ('business','hospitality')) and form_rng.random()<.7 else 'lobby')
    if mode not in ('continuous','lobby'):raise ValueError('Unknown ground_mode')
    if mode=='continuous' and (high or interior=='convenience'):raise ValueError('Continuous ground requires a non-store midrise')
    if mode=='continuous':
        bf=1;program='gallery';terrace=0;ground=h;interior='business';form='straight'
    atrium=overrides.get('atrium',high)
    if not isinstance(atrium,bool):raise ValueError('atrium must be boolean')
    base=ground+(bf-1)*h
    n=floors-bf;masses=[]
    def add(ww,dd,z,count,x=0,y=0,r=0,style=None):
        ww=min(ww,w-2*abs(x)-.02);dd=min(dd,d-2*abs(y)-.02)
        supports=[m for m in masses if abs(z-(m.z+m.count*h))<.002 and abs(x-m.x)+ww/2<=m.width/2+.03 and abs(y-m.y)+dd/2<=m.depth/2+.03]
        if supports:
            support=supports[0];ww=min(ww,support.width-2*abs(x-support.x)-.02);dd=min(dd,support.depth-2*abs(y-support.y)-.02)
        masses.append(Mass(round(ww,2),round(dd,2),round(z,3),count,round(x,2),round(y,2),round(min(r,ww*.42,dd*.42),2),style or facade,round(rng.uniform(1.7,2.4) if facade in ('curtain','fins') else rng.uniform(2.7,3.7),2)))
        return z+count*h
    if form=='straight':
        factor=.80 if podium_radius>radius else .96
        add(w*factor,d*factor,base,n,0,0,radius)
    elif form=='paired':
        gap=rng.uniform(1.2,2.3);left=w*rng.uniform(.40,.47);right=w-left-gap
        add(left,d*.83,base,n,-w/2+left/2,d*.04,0)
        add(right,d*.94,base,max(2,n-rng.randint(4,8)),w/2-right/2,-d*.01,0,rng.choice(('dark_grid','ribbon')))
    elif form=='stepped':
        tiers=3 if seed==11 else rng.choice((2,3,4))
        tiers=min(tiers,n);remaining=n;counts=[]
        for i in range(tiers-1):
            count=max(1,min(remaining-(tiers-i-1),round(remaining*rng.uniform(.35,.58))))
            counts.append(count);remaining-=count
        counts.append(remaining)
        z=base;ww=w*.93;dd=d*.92;x=y=0
        for i,count in enumerate(counts):
            z=add(ww,dd,z,count,x,y,radius,facade if i!=tiers-1 else rng.choice(PROFILES[family]))
            shrink=rng.uniform(.74,.87);nextw=ww*shrink;nextd=dd*shrink
            x+=(ww-nextw)*rng.uniform(-.35,.35);y+=(dd-nextd)*rng.uniform(.1,.4)
            ww=nextw;dd=nextd
    if podium_radius>radius and form!='straight':
        masses=[replace(m,width=m.width*.80,depth=m.depth*.80,x=m.x*.80,y=m.y*.80,radius=m.radius*.80) for m in masses]
    if terrace:
        # Affine setback of all tower sections retains nesting and support.
        factor=(d-terrace-.04)/d
        masses=[replace(m,depth=round(m.depth*factor,4),y=round(m.y*factor+terrace/2,4),radius=round(m.radius*factor,4)) for m in masses]
    sky=overrides.get('sky_floor',form_rng.randrange(max(1,n//3),max(2,n*2//3)) if high and form_rng.random()<.65 else -1)
    if isinstance(sky,bool) or not isinstance(sky,int) or not -1<=sky<n:raise ValueError('sky_floor must be -1 or an upper-floor index')
    sky_z=base+sky*h;extra=round(h*.8,2) if sky>=0 else 0
    if form=='stepped':shape='rectangle'
    notch=round(form_rng.uniform(.13,.23),2)
    masses=[replace(m,shape=shape,notch=notch) for m in masses]
    adjusted=[]
    for m in masses:
        index=round((sky_z-m.z)/h)
        active=sky>=0 and 0<=index<m.count
        adjusted.append(replace(m,z=m.z+(extra if sky>=0 and m.z>sky_z+.01 else 0),tall_floor=index if active else -1,extra_height=extra if active else 0))
    masses=adjusted
    return Design(spec.key,seed,w,d,floors,h,base,radius,base_style,roof_style,tuple(masses),bf,ground,program,terrace,interior,parking,site_height,parking_side,form,vertical,podium_radius,mode,atrium)

def design_distance(a,b):
    aa=a.descriptor();bb=b.descriptor()
    return sum(x!=y for x,y in zip(aa,bb))/len(aa)

def plan_district(count,seed=1,specs=None,rounded_fraction=None):
    """Balanced families; reject repeated coarse descriptors; maximize novelty.

    This limits repetition in a batch. It is not a claim that infinitely many
    visually unique buildings can be made from a finite vocabulary.
    """
    if not isinstance(count,int) or not 1<=count<=2000:raise ValueError('count must be 1..2000')
    if specs is None:
        from .catalog import CATALOG
        specs=[s for s in CATALOG if s.family in PROFILES]
    if rounded_fraction is not None and (isinstance(rounded_fraction,bool) or not isinstance(rounded_fraction,(int,float)) or not math.isfinite(rounded_fraction) or not 0<=rounded_fraction<=1):raise ValueError('rounded_fraction must be 0..1')
    round_families={'round_blade','soft_step','round_ribbon'}
    rng=random.Random(seed);result=[];seen=set();counts={s.key:0 for s in specs};descriptors={s.key:[] for s in specs}
    for _ in range(count):
        eligible=specs
        if rounded_fraction is not None:
            want_round=math.floor((len(result)+1)*rounded_fraction+1e-8)>sum(getattr(p,'radius',0)>0 for p in result)
            eligible=[s for s in specs if (s.family in round_families)==want_round]
            if not eligible:raise ValueError('Selected profiles cannot satisfy rounded_fraction')
        spec=min(eligible,key=lambda s:counts[s.key]);candidates=[]
        for _ in range(36):
            candidate_seed=rng.randrange(2**31)
            opts={}
            if spec.floors>20:
                hi=sum(p.floors>20 for p in result)
                opts['tower_form']='stepped' if hi%7==6 else 'paired' if hi%14==12 else 'straight'
            elif spec.key!='building_26':
                mid=sum(p.floors<=20 and p.interior_program!='convenience' for p in result)
                opts['ground_mode']='continuous' if mid%10<7 else 'lobby'
            design=derive_design(spec,candidate_seed,opts)
            descriptor=design.descriptor()
            if descriptor in seen:continue
            score=min((sum(a!=b for a,b in zip(descriptor,peer))/len(descriptor) for peer in descriptors[spec.key]),default=1)
            candidates.append((score,design))
        if not candidates:raise ValueError('Design vocabulary exhausted at requested diversity; widen profiles')
        design=max(candidates,key=lambda pair:pair[0])[1]
        seen.add(design.descriptor());descriptors[spec.key].append(design.descriptor());result.append(design);counts[spec.key]+=1
    return result


def floor_z(m,index,h):
    return m.z+index*h+(m.extra_height if m.tall_floor>=0 and index>m.tall_floor else 0)

def mass_top(m,h):
    return m.z+m.count*h+m.extra_height
