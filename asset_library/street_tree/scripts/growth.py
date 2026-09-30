"""Hierarchical summer crowns with connected scaffold, twigs and leafy shoots."""
import math
from mathutils import Vector
from asset_library.shared.foliage import Leaves


def grow(species, config, rng, lod):
    height = config['height']
    start = config['crown_start_height']
    span = height-start
    radius = config['crown_width']*.5
    branches = []
    leaves = Leaves()

    def branch(a, b, thickness, end_radius, segments=4, uplift=.08):
        a, b = Vector(a), Vector(b)
        delta = b-a
        bend = Vector((rng.uniform(-.10,.10),rng.uniform(-.10,.10),uplift))*delta.length
        path = [a+delta*(i/segments)+bend*math.sin(math.pi*i/segments) for i in range(segments+1)]
        radii = [end_radius+(thickness-end_radius)*(1-i/segments)**1.25 for i in range(segments+1)]
        branches.append((path,radii))
        return path

    def at(path,t):
        t=max(0,min(t,1))*(len(path)-1)
        i=min(int(t),len(path)-2)
        return path[i].lerp(path[i+1],t-i)

    # Buttress flare and a slightly wandering trunk; species retain their
    # excurrent (ginkgo) versus spreading scaffold organization.
    trunk_top = height*.94 if species == 'ginkgo' else start+span*.24
    sway = rng.uniform(.045,.12)
    trunk = [Vector((sway*math.sin(i*.62),sway*.65*math.sin(i*.91),trunk_top*i/12)) for i in range(13)]
    r = config['trunk_diameter']*.5
    radii = [r*(1-.72*i/12)+(r*.35*math.exp(-i*1.9)) for i in range(13)]
    if species == 'ginkgo':
        radii = [r*(1-.98*i/12)+r*.32*math.exp(-i*1.9) for i in range(13)]
    branches.append((trunk,radii))
    count = 17 if species == 'ginkgo' else 7
    phase = rng.uniform(0,math.tau)
    pruning_yaw = rng.uniform(0,math.tau)
    crown_bias = rng.uniform(.06,.22)
    for i in range(count):
        yaw = phase+i*2.39996+rng.uniform(-.25,.25)
        radial = Vector((math.cos(yaw),math.sin(yaw),0))
        local_radius = radius*(1-crown_bias*(.5+.5*math.cos(yaw-pruning_yaw)))
        tangent = Vector((-radial.y,radial.x,0))
        if species == 'ginkgo':
            level = (i+.5)/count
            origin = at(trunk,(start+span*level*.87)/trunk_top)
            reach = local_radius*(.98-.65*level)*rng.uniform(.8,1.05)
            end = origin+radial*reach*.72+Vector((0,0,span*.12))
            main = branch(origin,end,r*(.28-.17*level),.009,6,.03)
            secondary_count = 6
        else:
            origin = at(trunk,rng.uniform(.58,.98))
            reach = local_radius*rng.uniform(.26,.43)
            end = radial*reach+Vector((0,0,start+span*rng.uniform(.69,.79)))
            if species == 'cherry':
                end.z -= span*.14
            main = branch(origin,end,r*rng.uniform(.35,.52),.017,7,.05)
            secondary_count = 12
        for j in range(secondary_count):
            t = .22+.77*(j+.5)/secondary_count
            a = at(main,t)
            side = (-1 if j%2 else 1)
            if species == 'ginkgo':
                end = a+radial*rng.uniform(.15,.40)*radius+tangent*side*rng.uniform(.16,.42)*radius
                end.z += rng.uniform(.12,.58)
            else:
                vertical = max(-.87, min(.89, -.80+1.63*(j+rng.uniform(-.8,.8))/(secondary_count-1)))
                reach = local_radius*.90*math.sqrt(1-vertical*vertical)*rng.uniform(.62,1.10)
                end = radial*reach+tangent*side*radius*rng.uniform(.12,.52)
                end.z = start+span*(.55+.39*vertical)+rng.uniform(-.17,.17)
                if species == 'cherry':
                    end.z -= span*.06
            secondary = branch(a,end,.015 if species=='ginkgo' else .023,.0038,4,.06)
            leaves.begin_group()
            for k in range(7):
                a = at(secondary,.24+.75*(k+.5)/7)
                angle = yaw+k*2.4+rng.uniform(-.3,.3)
                direction = Vector((math.cos(angle),math.sin(angle),rng.uniform(-.2,.8))).normalized()
                twig_length = rng.uniform(.35,.74)*(radius/2.7)**.5
                twig = branch(a,a+direction*twig_length,.0038,.0012,3,.08)
                for s in range(5):
                    a=at(twig,.15+.84*(s+.5)/5)
                    angle += 2.39996
                    direction = Vector((math.cos(angle),math.sin(angle),rng.uniform(-.35,.8))).normalized()
                    shoot_length=rng.uniform(.20,.39)
                    shoot=branch(a,a+direction*shoot_length,.0013,.00035,2,.08)
                    material = rng.choices((0,1,2),(2,6,2))[0]
                    leaf_count = 18 if species != 'ginkgo' else 15
                    # Same branch hierarchy and canopy extent in all LODs.
                    # Low reduces leaf samples, not entire crown limbs.
                    if lod=='low': leaf_count = round(leaf_count*.67)
                    if lod=='high': leaf_count = round(leaf_count*1.2)
                    for n in range(leaf_count):
                        along=.08+.9*(n+.5)/leaf_count
                        anchor=at(shoot,along)
                        leaf_yaw=angle+(-1 if n%2 else 1)*rng.uniform(.8,1.7)
                        if species=='ginkgo':
                            # Five fan leaves radiate from each short spur.
                            anchor=at(shoot,.2+.35*(n//5))
                            leaf_yaw=angle+(n%5)*math.tau/5+rng.uniform(-.2,.2)
                        axis=Vector((math.cos(leaf_yaw),math.sin(leaf_yaw),rng.uniform(-.50,.45))).normalized()
                        length = {'keyaki':.095,'cherry':.108,'ginkgo':.106}[species]*rng.uniform(.75,1.22)
                        if lod=='low': length*=1.13
                        width=length*{'keyaki':.49,'cherry':.49,'ginkgo':.92}[species]
                        leaves.add(anchor+axis*.009,axis,length,width,rng.uniform(-.95,.95),material)
    # Fit the authored envelope continuously, avoiding piles of leaves on a
    # hard clamp plane. The public dimensions and road placement stay intact.
    points=[p for path,radii in branches for p in path if p.z>start]
    extent=max(math.hypot(p.x,p.y) for p in points)+.12
    zmax=max(p.z for p in points)+.10
    xy_scale=radius/extent
    zscale=span/(zmax-start)
    for path,radii in branches:
        for p in path:
            p.x*=xy_scale; p.y*=xy_scale
            if p.z>start: p.z=start+(p.z-start)*zscale
    for index,site in enumerate(leaves.sites):
        values=list(site)
        values[0]*=xy_scale; values[1]*=xy_scale
        if values[2]>start: values[2]=start+(values[2]-start)*zscale
        leaves.sites[index]=tuple(values)
    return branches,leaves
