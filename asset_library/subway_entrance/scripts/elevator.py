"""Glazed lift enclosure, recessed landing doors and visible lift assembly."""


LANDING_DOOR_Y=.473
CAR_DOOR_Y=.563
FRONT_GLASS_Y=.0525


def door_leaf(g,x0,x1,y):
    # Actual glazed opening with separate rubber seating and recessed glass.
    mid=(x0+x1)/2;wx0,wx1=mid-.095,mid+.095;z0,z1=.035,2.235;wz0,wz1=.53,1.98
    def panel(a,b,c,d):g.box('metal',((a+b)/2,y,(c+d)/2),(b-a,.034,d-c))
    panel(x0,wx0,z0,z1);panel(wx1,x1,z0,z1)
    panel(wx0,wx1,z0,wz0);panel(wx0,wx1,wz1,z1)
    # Rubber surround remains on the edge, not a solid plate behind the glass.
    for x in (wx0+.006,wx1-.006):g.box('rubber',(x,y-.014,(wz0+wz1)/2),(.012,.015,wz1-wz0))
    for z in (wz0+.006,wz1-.006):g.box('rubber',(mid,y-.014,z),(wx1-wx0-.024,.015,.012))
    g.pane('car_glass','y',y-.008,(wx0+.013,wx1-.013),(wz0+.013,wz1-.013))
    for x in (mid-.102,mid+.102):g.box('metal',(x,y-.024,1.255),(.014,.018,1.478))
    for z in (.523,1.987):g.box('metal',(mid,y-.024,z),(.19,.018,.014))


def build_elevator(g,width,length):
    w=width;L=length;car=g.group('car')
    from .details import glazing_seat
    from .controls import CALL_PANEL_RISE
    g.box('stone',(0,L/2,-.105),(w-.04,L,.20))
    g.box('interior',(0,1.56,-.0025),(w-.50,3.12,.005))
    g.box('stone',(0,.155,-.006),(1.462,.31,.012))
    # Fixed shaft frame shares exactly the stair canopy material.
    for side in (-1,1):
        x=side*(w/2-.12)
        for y in (.0525,1.60,3.10):
            bottom=-.005 if y==.0525 else .945
            g.box('frame',(x,y,(bottom+3.485)/2),(.105,.105,3.485-bottom))
        for a,b in ((.105,1.5475),(1.6525,3.0475)):
            for lo,hi in ((.993,2.465),(2.515,3.375)):
                g.pane('glass','x',x,(a,b),(lo,hi))
                glazing_seat(g,'x',x,a,b,lo,hi,'frame')
        for z in (.968,2.490,3.40):g.box('frame',(x,L/2,z),(.095,L,.05))
    g.box('stone',(0,L-.15,.46),(w-.56,.25,.92))
    g.box('stone',(0,L-.15,.946),(w-.60,.29,.045))
    for z in (.968,2.49,3.40):g.box('frame',(0,L-.12,z),(w-.24,.095,.05))
    g.box('frame',(0,L-.12,2.1715),(.075,.095,2.407))
    for a,b in ((-w/2+.182,-.048),(.048,w/2-.182)):
        for lo,hi in ((.987,2.454),(2.526,3.365)):
            g.pane('glass','y',L-.12,(a,b),(lo,hi))
            glazing_seat(g,'y',L-.12,a,b,lo,hi,'frame')
    # Front glazing and glazed reveals belong to the stationary enclosure only.
    outer=w/2-.1725
    for a,b in ((-outer,-.735),(.735,outer)):
        g.box('stone',((a+b)/2,.2015,.46),(b-a,.403,.92))
        g.box('stone',((a+b)/2,.2015,.946),(b-a,.448,.045))
        g.pane('glass','y',FRONT_GLASS_Y,(a,b),(.9685,2.345))
        glazing_seat(g,'y',FRONT_GLASS_Y,a,b,.9685,2.345,'frame')
    g.pane('glass','y',FRONT_GLASS_Y,(-outer,outer),(2.345,2.875))
    glazing_seat(g,'y',FRONT_GLASS_Y,-outer,outer,2.345,2.875,'frame')
    for side in (-1,1):
        g.box('frame',(side*.735,FRONT_GLASS_Y,1.175),(.060,.105,2.36))
        g.pane('glass','x',side*.735,(FRONT_GLASS_Y,.403),(.9685,2.325))
        glazing_seat(g,'x',side*.735,FRONT_GLASS_Y,.403,.9685,2.325,'frame')
        g.box('frame',(side*.692,.468,1.1725),(.086,.13,2.345))
    g.box('frame',(0,FRONT_GLASS_Y,2.345),(w-.24,.105,.060))
    g.box('frame',(0,.468,2.289),(1.47,.13,.112))
    # Independently framed landing and car doors: 90mm between leaf centre planes.
    for y in (LANDING_DOOR_Y,CAR_DOOR_Y):
        layer=car if y==CAR_DOOR_Y else g
        door_leaf(layer,-.651,-.004,y);door_leaf(layer,.004,.651,y)
        layer.box('rubber',(0,y+.024,1.13),(.010,.013,2.20))
        for side in (-1,1):layer.box('rubber',(side*.650,y+.020,1.135),(.025,.018,2.25))
        for z in (.025,2.235):layer.box('rubber',(0,y+.020,z),(1.32,.018,.03))
    # Two separate sills and a recessed inter-sill clearance.
    g.box('frame',(0,.411,.007),(1.46,.198,.014))
    g.box('interior',(0,.533,.007),(1.46,.038,.014))
    g.box('rubber',(0,.512,.001),(1.34,.004,.002))
    car.box('porcelain',(0,.586,.007),(1.46,.064,.014))
    for y in (.382,.414,.446,.565,.591):(car if y>.55 else g).box('rubber',(0,y,.015),(1.32,.005,.002))
    # The call plate is mounted to its own slender stationary post.
    g.box('frame',(.899,.037,1.1675),(.105,.074,2.345))
    # Flush button plate, physical push surfaces and small tactile dots.
    g.box('metal',(.899,-.008,1.10+CALL_PANEL_RISE),(.155,.018,.31))
    g.box('rubber',(.899,-.019,1.12+CALL_PANEL_RISE),(.055,.004,.055))
    g.tube('white',(.899,-.023,1.12+CALL_PANEL_RISE),(.899,-.028,1.12+CALL_PANEL_RISE),.020,24)
    from asset_library.subway_entrance.scripts.controls import add_controls
    add_controls(g)
    for dx,dz in ((-.012,-.092),(0,-.080),(.012,-.092)):
        g.tube('metal',(.899+dx,-.019,1.12+CALL_PANEL_RISE+dz),(.899+dx,-.022,1.12+CALL_PANEL_RISE+dz),.002,10)
    # Landing downlights sit on a shallow fixed door-head transom.
    g.box('frame',(0,.295,2.3625),(1.47,.30,.075))
    for x in (-.52,.52):
        g.tube('frame',(x,.295,2.343),(x,.295,2.333),.070,28)
        g.tube('light',(x,.295,2.332),(x,.295,2.328),.049,28)
    g.box('frame',(0,1.60,3.535),(w,3.2,.25))
    g.box('porcelain',(0,1.60,3.668),(w-.06,3.14,.016))
    # Interior: car platform, glazed car shell, corner posts and handrails.
    car_half=min(.90,w/2-.42);front=.62;back=2.58
    # Car return panels and door head travel with the car, clear of the shaft facade.
    for side in (-1,1):
        car.box('porcelain',(side*(car_half+.675)/2,.6025,1.20),(car_half-.675,.07,2.37))
        car.box('porcelain',(side*.674,.6025,1.135),(.046,.07,2.23))
    car.box('porcelain',(0,.6025,2.3025),(car_half*2,.07,.185))
    car.box('interior',(0,.655,2.52),(1.58,.10,.10))
    for x in (-.48,.48):
        car.tube('interior',(x,.613,2.52),(x,.645,2.52),.034,24)
        car.box('porcelain',(x,.595,2.372),(.035,.05,.295))

    car.box('interior',(0,(front+back)/2,-.045),(car_half*2+.05,back-front+.055,.07))
    car.box('tile',(0,(front+back)/2,-.003),(car_half*2,back-front+.008,.014))
    for s in (-1,1):
        car.box('porcelain',(s*car_half,(front+back)/2,.073),(.055,back-front+.055,.146))
        for y in (front,back):car.box('porcelain',(s*car_half,y,1.22),(.055,.055,2.39))
        car.pane('car_glass','x',s*car_half,(front+.0275,back-.0275),(.185,2.355))
        for z in (.16,2.38):car.box('porcelain',(s*car_half,(front+back)/2,z),(.05,back-front,.05))
        for y in (front+.28,back-.28):car.tube('porcelain',(s*(car_half-.07),y,.93),(s*car_half,y,.90),.009)
    car.box('porcelain',(0,back,.073),(car_half*2+.055,.055,.146))
    car.pane('car_glass','y',back,(-car_half+.0275,car_half-.0275),(.185,2.355))
    for z in (.16,2.38):car.box('porcelain',(0,back,z),(car_half*2,.05,.05))
    car.rail('porcelain',[(-car_half,front+.12,.90),(-car_half+.07,front+.12,.93),(-car_half+.07,back-.06,.93),(car_half-.07,back-.06,.93),(car_half-.07,front+.12,.93),(car_half,front+.12,.90)],.019,.06)
    for x in (-.5,.5):car.tube('porcelain',(x,back-.06,.93),(x,back,.90),.009)
    car.box('porcelain',(0,(front+back)/2,2.44),(car_half*2+.055,back-front+.055,.09))
    car.box('light',(0,1.65,2.389),(1.15,.92,.01))
    # Guide rails and brackets stay distinct from the car and enclosure glazing.
    rail_x=car_half+.19
    for s in (-1,1):
        g.box('interior',(s*rail_x,1.66,1.70),(.08,.055,3.25))
        g.box('porcelain',(s*rail_x,1.625,1.70),(.035,.055,3.25))
        for z in (.38,1.34,2.70,3.25):
            g.box('porcelain',(s*(rail_x+.06),1.69,z),(.16,.15,.055))
        for z in (.28,2.44):car.box('interior',(s*(car_half+.08),1.64,z),(.14,.12,.10))
    # Overhead support frame and compact drive above the passenger car.
    for x in (-.67,.67):car.box('porcelain',(x,1.65,2.61),(.09,1.82,.11))
    for y in (.80,2.48):car.box('porcelain',(0,y,2.61),(1.43,.09,.11))
    drive_y=2.59
    for x in (-rail_x,rail_x):g.box('porcelain',(x,drive_y,3.17),(.09,.12,.50))
    g.box('porcelain',(0,drive_y,2.92),(rail_x*2+.09,.16,.09))
    g.box('porcelain',(.40,drive_y,2.970),(.58,.53,.03))
    g.box('interior',(.40,drive_y,3.10),(.41,.43,.25))
    g.tube('interior',(.13,drive_y,3.10),(.21,drive_y,3.10),.19,32)
    car.box('porcelain',(.167,2.40,2.68),(.20,.20,.05))
    import math
    for x in (.143,.159,.175,.191):
        points=[(x,2.40,2.71),(x,2.40,3.10)]
        points += [(x,drive_y+.195*math.cos(math.pi-i*math.pi/16),3.10+.195*math.sin(math.pi-i*math.pi/16)) for i in range(17)]
        points += [(x,2.785,2.64)]
        for a,b in zip(points,points[1:]):g.tube('rubber',a,b,.004,8)
    # Counterweight in its own narrow frame behind the car.
    for x in (-.50,.50):g.box('porcelain',(x,2.78,1.92),(.042,.06,1.42))
    for z in (1.22,2.62):g.box('porcelain',(0,2.78,z),(1.04,.06,.042))
    for i in range(10):g.box('interior',(0,2.78,1.32+i*.122),(.91,.12,.11))
