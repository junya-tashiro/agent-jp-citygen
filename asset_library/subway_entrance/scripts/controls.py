"""Cabin operating panel and raised landing-button symbols."""


CALL_PANEL_RISE=.06

def add_controls(g):
    car=g.group('car')
    # Right of the doors when facing the exit from inside the cabin (-X).
    x=-.79
    car.box('porcelain',(x,.609,1.20),(.15,.038,.48))
    car.box('interior',(x,.633,1.20),(.12,.012,.44))
    for z in (1.35,1.25,1.15,1.05):
        car.box('rubber',(x,.642,z),(.055,.006,.055))
        car.box('white',(x,.649,z),(.046,.008,.046))
    # The inside face points +Y, so screen-right is local -X.
    for z,opening in ((1.15,True),(1.05,False)):
        for side in (-1,1):
            tip=side*(.017 if opening else .003)
            base=side*(.003 if opening else .017)
            points=[(tip,0),(base,-.013),(base,.013)]
            car.mesh('rubber',[(x-u,.655,z+v) for u,v in points],[(0,1,2)])
    arrow=[(-.0025,.013),(.0025,.013),(.0025,-.003),(.009,.003),(.012,-.001),(0,-.013),(-.012,-.001),(-.009,.003),(-.0025,-.003)]
    g.mesh('rubber',[(.899+u,-.029,1.12+CALL_PANEL_RISE+v) for u,v in arrow],[tuple(range(len(arrow)))])
