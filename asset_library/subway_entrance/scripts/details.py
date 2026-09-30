"""Manufactured sections and attachment details; dimensions are model design values."""
import math


def glazing_seat(g,axis,p,a,b,lo,hi,finish,left=True,right=True):
    # Narrow glazing beads flank one optical surface. A dark EPDM lip sits inside.
    def box(key,u,z,du,dz,depth,offset):
        center=(p+offset,u,z) if axis=='x' else (u,p+offset,z)
        size=(depth,du,dz) if axis=='x' else (du,depth,dz)
        g.box(key,center,size)
    for side in (-1,1):
        for u in ([a] if left else [])+([b] if right else []):
            box(finish,u,(lo+hi)/2,.018,hi-lo,.014,side*.016)
            box('rubber',u+( .009 if u==a else -.009),(lo+hi)/2,.006,hi-lo,.009,side*.007)
        for z in (lo,hi):
            box(finish,(a+b)/2,z,b-a,.018,.014,side*.016)
            box('rubber',(a+b)/2,z+(.009 if z==lo else -.009),b-a-.024,.006,.009,side*.007)


def stair_details(g,w,L):
    for side in (-1,1):
        x=side*(w/2-.12)
        for a,b in ((.15,1.65),(1.75,3.25),(3.35,4.85),(4.95,6.43)):
            glazing_seat(g,'x',x,a,b,.977,2.505,'frame')
        # Bent sheet gutter: open channel, folded lip, end closures.
        cx=side*(w/2-.055)
        section=[(cx-.043,2.765),(cx-.043,2.68),(cx+.043,2.68),(cx+.043,2.765),
                 (cx+.037,2.765),(cx+.037,2.686),(cx-.037,2.686),(cx-.037,2.765)]
        # A 48 x 60mm outlet in the channel floor connects to the open downpipe.
        for a,b in ((.015,6.42),(6.48,L-.015)):g.profile('metal',section,a,b)
        for x0,x1 in ((cx-.043,cx-.037),(cx+.037,cx+.043)):
            g.box('metal',((x0+x1)/2,6.45,2.7225),(x1-x0,.06,.085))
        for x0,x1 in ((cx-.037,cx-.024),(cx+.024,cx+.037)):
            g.box('metal',((x0+x1)/2,6.45,2.683),(x1-x0,.06,.006))
        for y in (.018,L-.018):g.box('metal',(cx,y,2.722),(.082,.006,.08))
        pipex=side*(w/2-.07)
        g.rail('metal',[(pipex,6.45,2.70),(pipex,6.45,.15),(pipex,6.30,.08)],.029,.06,caps=False)
        g.tube('metal',(pipex,6.45,2.63),(pipex,6.45,2.70),.025,24,caps=False)
        for z in (.45,1.45,2.40):
            g.tube('metal',(pipex,6.45,z-.012),(pipex,6.45,z+.012),.033,20)
            g.box('frame',(pipex,6.485,z),(.07,.055,.045))
        for z in (.27,2.56):g.tube('metal',(pipex,6.45,z-.026),(pipex,6.45,z+.026),.032,24)
        # Roof falls from the central glazing towards the lateral gutter.
        inner=side*.55;outer=side*(w/2-.055)
        section=[(inner,2.89),(outer,2.80),(outer,2.765),(outer-side*.008,2.765),
                 (outer-side*.008,2.792),(inner,2.882)]
        g.profile('metal',section,0,L)
        for y in (.014,L-.014):
            g.profile('frame',[(inner,2.878),(outer-side*.012,2.789),(outer-side*.012,2.757),(inner,2.847)],y-.012,y+.012)
        g.box('frame',(inner,L/2,2.883),(.035,L,.026))
        for y in (.10,1.70,3.30,4.90,6.48):
            # Cap covers and recessed fastener heads at column feet.
            for dx in (-.052,.052):
                for dy in (-.052,.052):
                    g.tube('frame',(x+dx,y+dy,1.08),(x+dx,y+dy,1.083),.008,6)
        for h in (.72,.92):
            for y in (1.2,2.4,3.6,4.8,5.9):
                z=h-min(2.4,max(0,y-.9)*.16/.30)-.07
                wall=side*(w/2-.232)
                g.tube('metal',(wall,y,z),(wall-side*.008,y,z),.036,24)
                for dz in (-.021,.021):g.tube('frame',(wall-side*.009,y,z+dz),(wall-side*.011,y,z+dz),.004,8)
        # Folded cap downstands terminate on the stone, no decorative wall grid.
        for dx in (-.139,.139):g.box('metal',(side*(w/2-.15)+dx,L/2,.916),(.008,L,.035))
    g.box('frame',(.75,6.5,-.251),(.16,.26,.024))
    g.box('light',(.75,6.5,-.267),(.12,.22,.012))
    glazing_seat(g,'y',6.49,-w/2+.14,w/2-.14,.977,2.505,'frame')
    for y in (6.355,6.625):g.box('metal',(0,y,.916),(w-.035,.008,.035))
    for side in (-1,1):
        for y in (1.7,3.3,4.9):
            x=side*(w/2+.55)/2
            for dy in (-.405,.405):g.box('porcelain',(x,y+dy,2.6095),(.084,.023,.032))
            for dx in (-.045,.045):g.box('frame',(x+dx,y,2.6095),(.008,.80,.035))


def elevator_details(g,w,L):
    from .controls import CALL_PANEL_RISE
    for side in (-1,1):
        x=side*(w/2-.12)
        for y in (.0525,1.60,3.10):
            z=.04875 if y==.0525 else 1.015
            height=.1075 if y==.0525 else .085
            g.box('frame',(x,y,z),(.127,.125,height))
        g.box('frame',(side*(w/2-.014),L/2,3.49),(.028,L-.04,.10))
        g.box('rubber',(side*(w/2-.040),L/2,3.405),(.007,L-.09,.006))
    # Concealed plate fixings and tactile raised button surround.
    for z in (.974+CALL_PANEL_RISE,1.226+CALL_PANEL_RISE):
        g.tube('metal',(.899,-.0175,z),(.899,-.019,z),.0045,16)
        g.box('rubber',(.899,-.0194,z),(.005,.0006,.0008))
    half=min(.90,w/2-.42);rail=half+.19;car=g.group('car')
    for side in (-1,1):glazing_seat(car,'x',side*half,.6475,2.5525,.185,2.355,'porcelain')
    glazing_seat(car,'y',2.58,-half+.0275,half-.0275,.185,2.355,'porcelain')
    for s in (-1,1):
        for z in (.28,2.44):
            car.box('porcelain',(s*(half+.095),1.64,z),(.09,.19,.16))
            for dy in (-.074,.074):car.tube('interior',(s*(half+.09),1.64+dy,z-.06),(s*(half+.09),1.64+dy,z+.06),.025,20)
        for z in (.38,1.34,2.70,3.25):
            for dy in (-.042,.042):g.tube('interior',(s*(rail+.065),1.69+dy,z+.028),(s*(rail+.065),1.69+dy,z+.034),.009,6)
        # Counterweight guide runners and fixed guides continue to the support beam.
        g.box('interior',(s*.55,2.78,1.73),(.035,.055,3.25))
        for z in (1.25,2.58):g.box('porcelain',(s*.525,2.78,z),(.075,.12,.095))
    # Motor cooling ribs, bearing collar and rope retention bridge.
    for x in (.27,.32,.37,.42,.47,.52):g.box('interior',(x,2.59,3.232),(.016,.38,.014))
    g.tube('porcelain',(.215,2.59,3.10),(.253,2.59,3.10),.065,24)
    for y in (2.40,2.78):g.box('porcelain',(.167,y,3.30),(.13,.025,.035))
    g.box('porcelain',(.167,2.59,3.325),(.13,.405,.015))
    # Cable termination rods and nuts at the moving crosshead.
    for x in (.143,.159,.175,.191):
        car.tube('interior',(x,2.40,2.68),(x,2.40,2.75),.006,10)
        car.tube('porcelain',(x,2.40,2.716),(x,2.40,2.725),.009,6)


def fixture_lights(col,root,w,variant):
    import bpy
    fixtures=[]
    if variant=='stairs':
        fixtures=[((s*(w/2+.55)/2,y,2.5805),16,.55) for s in (-1,1) for y in (1.7,3.3,4.9)]
        fixtures.append(((.75,6.5,-.281),12,.12))
    else:fixtures=[((x,.295,2.317),10,.085) for x in (-.52,.52)]+[((0,1.65,2.365),32,.80)]
    for i,(pos,energy,size) in enumerate(fixtures):
        data=bpy.data.lights.new('Subway fixture','AREA');data.energy=energy;data.shape='DISK';data.size=size;data.color=(1,.92,.80)
        obj=bpy.data.objects.new('Subway fixture '+str(i),data);col.objects.link(obj);obj.parent=root;obj.location=pos;obj['subway_part']='fixture_light';obj['subway_assembly']='car' if variant=='elevator' and i==2 else 'enclosure'
