"""Facade cross-sections: separate systems, not recolored window grids."""
import math,random
from .geometry import Geometry,Face,EntranceGeometry

def pane(f,u,z,w,h,frame,glass,depth=-.16,blinds=0):
    # Opaque upper-floor glass gives stable distant reflections. Frames and
    # recessed reveals are physical; lobby glazing below uses real transparency.
    f.box(glass,u,depth,z,w,.022,h)
    for x in (u-w/2,u+w/2):f.box(frame,x,depth+.026,z,.052,.105,h+.052)
    for zz in (z-h/2,z+h/2):f.box(frame,u,depth+.026,zz,w,.105,.052)
    if w>1.7:f.box(frame,u,depth+.024,z,.045,.08,h)
    if glass=='clear':
        for x in (u-w/2+.032,u+w/2-.032):f.box('black',x,depth+.018,z,.012,.018,h-.048)
        for zz in (z-h/2+.032,z+h/2-.032):f.box('black',u,depth+.018,zz,w-.048,.018,.012)
        f.box(frame,u,depth+.045,z-h/2-.015,w+.02,.16,.035)
    if blinds:
        # Closed and partly lowered blinds sit just ahead of the dark glazing,
        # leaving dark margins, not arbitrary colored window tiles.
        bh=h*(.32 if blinds==1 else .76)
        f.box('blind',u,depth+.014,z+h/2-bh/2-.045,w-.14,.009,bh-.07)
        count=max(2,int(bh/.12))
        for j in range(count):f.box(frame,u,depth+.020,z+h/2-.10-j*(bh-.12)/count,w-.16,.009,.009)

def floor_module(poly,height,style,wall,frame,glass,seed,variant=0,bay=3.0,rear_solid=False,detail='high',entrance=None):
    g=EntranceGeometry(entrance) if entrance else Geometry();rng=random.Random(seed+variant*997)
    g.prism('interior',poly,.02,.18)
    g.prism('ceiling',[(x*.995,y*.995) for x,y in poly],height-.22,.18)
    for index,a in enumerate(poly):
        b=poly[(index+1)%len(poly)];f=Face(g,a,b)
        n=max(1,round(f.length/bay));bw=f.length/n
        rear=(f.ny>.5)
        localstyle='punched' if rear_solid and rear else style
        if f.length<1.2 and localstyle in ('stone_grid','punched','brick','balcony'):
            localstyle='curtain'
        if localstyle in ('folded','exoskeleton','ceramic'):
            f.box('spandrel',f.length/2,-.15,.40,f.length,.18,.80)
            f.box(frame,f.length/2,.04,height-.12,f.length,.20,.24)
            for i in range(n):
                u=(i+.5)*bw
                if localstyle=='folded' and f.ny<.5:
                    a=f.point(i*bw,-.10,0);b=f.point((i+.65)*bw,.52,0);c=f.point((i+1)*bw,-.10,0)
                    triangle=[a[:2],b[:2],c[:2]]
                    g.prism('interior',triangle,.02,.18);g.prism('ceiling',triangle,height-.22,.18)
                    for start,end in ((a,b),(b,c)):
                        ff=Face(g,start[:2],end[:2]);pane(ff,ff.length/2,(height+.65)/2,ff.length-.045,height-.95,frame,glass,-.015,0)
                else:
                    pane(f,u,(height+.65)/2,bw-.18,height-.95,frame,glass,-.22,0)
                if localstyle=='ceramic':
                    for du in (-bw*.42,-bw*.14,bw*.14):f.box(wall,u+du,.18,height/2,.15,.68,height-.04)
                if localstyle=='exoskeleton':
                    f.box(frame,i*bw,.22,height/2,.18,.40,height)
                    f.box(frame,u,.22,.11,bw,.40,.22)
                    # Braces terminate on the bay frame at floor levels.
                    if (i+variant)%3==0:f.tube(frame,(i*bw,.22,.20),((i+1)*bw,.22,height-.20),.065)
            f.box(frame,f.length,.17,height/2,.12,.35,height)
        elif localstyle in ('curtain','fins','dark_grid'):
            f.box('spandrel',f.length/2,-.055,.44,f.length,.11,.88)
            f.box(frame,f.length/2,.005,height-.08,f.length,.15,.16)
            for i in range(n):
                u=(i+.5)*bw;pane(f,u,(height+.82)/2,bw-.04,height-.98,frame,glass,-.11,0)
                if detail=='high' and rng.random()<.12:
                    f.box('blind',u,-.092,height-.68,bw-.20,.012,.68)
                if localstyle=='fins':f.box(frame,i*bw,.19,height/2,.115,.48,height-.015)
                elif localstyle=='dark_grid' and i%2==0:f.box(frame,i*bw,.08,height/2,.22,.25,height)
            f.box(frame,f.length,.13,height/2,.095,.36,height)
        elif localstyle in ('punched','stone_grid','brick'):
            sill=.88 if localstyle!='brick' else .76;head=.47;col=.55 if localstyle=='stone_grid' else bw*.28
            f.box(wall,f.length/2,-.045,sill/2,f.length,.32,sill)
            f.box(wall,f.length/2,-.045,height-head/2,f.length,.32,head)
            for i in range(n):
                u=(i+.5)*bw;ww=bw-col
                pane(f,u,(sill+height-head)/2,ww,height-head-sill,frame,glass,-.24,rng.choice((0,0,0,1,2)) if detail=='high' else 0)
                f.box(wall,i*bw,-.04,height/2,col,.33,height)
                if localstyle=='stone_grid':
                    f.box(wall,i*bw,.17,height/2,.20,.23,height)
                    f.box(wall,u,.14,sill-.08,ww,.27,.14)
                if localstyle=='brick':
                    f.box('pale_stone',u,.10,sill-.07,ww+.16,.40,.14)
                    f.box('brick',u,.06,height-head+.07,ww+.16,.38,.14)
            f.box(wall,f.length,-.04,height/2,col,.33,height)
            # Thin recessed joints belong to the solid bands, not drawn across glass.
            if detail=='high':
                if wall=='brick':
                    for zz in (.16,.34,.52,height-.16,height-.34):f.box('mortar',f.length/2,.119,zz,f.length,.005,.012)
                    for j in range(int(f.length/.65)):
                        f.box('mortar',j*.65,.12,.39,.010,.006,.66)
                elif wall in ('tile','pale_stone','limestone'):
                    for i in range(n):f.box('mortar',(i+.5)*bw,.119,.40,.012,.005,.65)
        elif localstyle=='ribbon':
            f.box(wall,f.length/2,-.02,.52,f.length,.34,1.04)
            f.box(wall,f.length/2,-.02,height-.17,f.length,.34,.34)
            f.box(frame,f.length/2,.17,1.035,f.length,.13,.08)
            for i in range(n):
                pane(f,(i+.5)*bw,(1.04+height-.34)/2,bw-.085,height-1.38,frame,glass,-.20,rng.choice((0,0,1,2)) if detail=='high' else 0)
                f.box(frame,i*bw,-.075,(1.04+height-.34)/2,.07,.23,height-1.38)
        elif localstyle=='balcony':
            # Only the street face has galleries; side and rear walls retain windows.
            if f.ny<-.5:
                for i in range(n):
                    u=(i+.5)*bw
                    if i<n//2+1:
                        pane(f,u,height/2,bw-.26,height-.55,frame,glass,-1.30,0)
                        f.box('concrete',u,-.60,.10,bw,.0+1.50,.20)
                        f.box('concrete',i*bw,-.54,height/2,.20,1.40,height)
                        f.box('silver',u,.025,.72,bw-.22,.045,.81)
                        for zz in (.33,.45,.57,.69,.81,.93,1.05):f.box('dark_metal',u,.051,zz,bw-.32,.008,.013)
                        f.tube('silver',(i*bw+.1,.04,1.17),((i+1)*bw-.1,.04,1.17),.032)
                        f.box('concrete',u,.07,height-.11,bw,.27,.22)
                    else:pane(f,u,height/2,bw-.07,height-.17,frame,glass,-.12,0)
            else:
                f.box(wall,f.length/2,-.10,height/2,f.length,.24,height)
                # Raised glazed service windows against a solid side wall.
                for i in range(n):pane(f,(i+.5)*bw,height*.57,bw*.51,height*.53,frame,glass,.035,0)
        else:raise ValueError(localstyle)
    return g
