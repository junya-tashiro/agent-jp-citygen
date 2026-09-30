"""White station lightbox with an original portal emblem and route roundels."""
import math
ROUTE_COLORS={}
def route_material(color):
    key='route_'+color[1:]
    def linear(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    ROUTE_COLORS[key]=tuple(linear(int(color[i:i+2],16)/255) for i in (1,3,5))
    return key

def station_sign(g,col,root,width,z,face_y,name,roman,routes,lift=False,height=.51):
    from .build_subway_entrance import label
    from .symbol_geometry import add_lift_symbol
    scale=height/.51
    g.box('frame',(0,face_y+.046,z),(width+.06,.08,height+.06))
    g.box('white',(0,face_y+.004,z),(width,.008,height))
    y=face_y-.002
    left=-width/2+.06*scale;right=width/2-.06*scale
    emblem=.31*scale;cx=left+emblem/2
    g.box('sign_teal',(cx,y+.0005,z),(emblem,.001,emblem))
    # A squared station portal with two converging rails, not a letter monogram.
    outlines=[
        [(-.345,-.28),(-.345,.325),(.345,.325),(.345,-.28),(.295,-.28),(.295,.275),(-.295,.275),(-.295,-.28)],
        [(-.225,-.30),(-.105,-.035),(-.105,.13),(-.055,.13),(-.055,-.045),(-.175,-.32)],
        [(.225,-.30),(.105,-.035),(.105,.13),(.055,.13),(.055,-.045),(.175,-.32)],
    ]
    for outline in outlines:
        g.mesh('white',[(cx+x*emblem,y-.002,z+h*emblem) for x,h in outline],[tuple(range(len(outline)))])
    start=left+emblem+.09*scale
    diameter=min(.31*scale,.90*scale/max(1,len(routes)));gap=.035*scale
    for i,route in enumerate(routes):
        x=start+diameter/2+i*(diameter+gap);r=diameter/2;n=64
        verts=[(x+rad*math.cos(j*math.tau/n),y-.002,z+rad*math.sin(j*math.tau/n)) for rad in (r,r*.79) for j in range(n)]
        g.mesh(route_material(route['color']),verts,[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)])
        letters=route['code'][:-2];number=route['code'][-2:]
        for text,dz,size in ((letters,.066,.160),(number,-.066,.148)):
            o=label(col,root,text,(x,y-.004,z+dz*diameter/.31),size*diameter/.31,diameter*.73,'black',bold=True)
            o['sign_role']='route';o['route_code']=route['code']
    text_left=start+len(routes)*(diameter+gap)+.07*scale
    text_right=right-(.29*scale if lift else 0)
    text_width=text_right-text_left
    for text,dz,size in ((name,.055,.252),(roman,-.105,.09)):
        o=label(col,root,text,((text_left+text_right)/2,y-.004,z+dz*scale),size*scale,text_width,'black',bold=True)
        if o:o['sign_role']='station'
    if lift:
        x=right-.105*scale
        g.box('blue',(x,y+.0005,z),(.25*scale,.001,.34*scale))
        add_lift_symbol(g,(x,z),y-.003,height=.29*scale)
