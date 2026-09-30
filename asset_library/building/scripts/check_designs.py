"""Checks meaningful large-batch variation without running Blender."""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from asset_library.building.scripts.catalog import CATALOG
from asset_library.building.scripts.design import derive_design,plan_district,design_distance,mass_top
plans=plan_district(1000,20260906)
assert len({d.descriptor() for d in plans})==1000
assert len({d.signature() for d in plans})==1000
assert [p.signature() for p in plans[:50]]==[p.signature() for p in plan_district(50,20260906)]
counts={s.key:sum(d.key==s.key for d in plans) for s in CATALOG[10:]}
assert max(counts.values())-min(counts.values())<=1
for d in plans:
    assert 1<=d.base_floors<=4
    assert abs(d.base_height-d.ground_height-(d.base_floors-1)*d.floor_height)<1e-6
    assert max(mass_top(m,d.floor_height) for m in d.masses)<=d.base_height+(d.floors-d.base_floors)*d.floor_height+max(m.extra_height for m in d.masses)+.001
    for m in d.masses:
        assert m.count>0 and m.width>0 and m.depth>0
        assert abs(m.x)+m.width/2<=d.width/2+.001
        assert abs(m.y)+m.depth/2<=d.depth/2+.001
    for upper in d.masses:
        if abs(upper.z-d.base_height)<.002:continue
        supports=[lower for lower in d.masses if abs(upper.z-(mass_top(lower,d.floor_height)))<.002]
        assert any(abs(upper.x-lower.x)+upper.width/2<=lower.width/2+.001 and abs(upper.y-lower.y)+upper.depth/2<=lower.depth/2+.001 for lower in supports)
for spec in CATALOG[10:]:
    for floors in (6,65):
        for bf in (1,2,3,4):
            for seed in (11,17,42):
                d=derive_design(spec,seed,{'floors':floors,'base_floors':bf})
                assert all(m.count>0 for m in d.masses),(spec.key,floors,bf,seed)
for overrides in ({'width':float('nan')},{'floors':6.5},{'corner_radius':.01},{'facade':'unknown'},{'colour':'red'},{'base_floors':0},{'base_program':'unknown'},{'terrace_depth':99}):
    try:derive_design(CATALOG[10],11,overrides)
    except ValueError:pass
    else:raise AssertionError(overrides)
summary={'count':1000,'unique_coarse_structural_descriptors':1000,'family_counts':counts,'deterministic_prefix':True,'supported_setbacks':True,'note':'Descriptor uniqueness is a numerical guard. See rendered seed variants for visual assessment.'}
p=ROOT/'asset_library/building/renders/design_checks.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))

limited=plan_district(100,20260907,rounded_fraction=.1)
assert sum(p.radius>0 for p in limited)==10
assert sum(p.parking for p in limited)>0
assert sum(p.interior_program=='convenience' for p in limited)>0
assert len({p.descriptor() for p in limited})==100
print('ROUND_QUOTA_10_PERCENT_OK')

from asset_library.building.scripts.catalog import get_spec
for d in limited:
    replay=derive_design(get_spec(d.key),d.seed,{'tower_form':d.tower_form,'ground_mode':d.ground_mode})
    assert replay.signature()==d.signature()
high=[d for d in limited if d.floors>20]
assert sum(d.tower_form=='stepped' for d in high)/len(high)<.20
mid=[d for d in limited if d.floors<=20 and d.interior_program!='convenience']
assert .65<=sum(d.ground_mode=='continuous' for d in mid)/len(mid)<=.80
assert all(d.atrium for d in high)
print('FORM_QUOTAS_AND_REPLAY_OK')
