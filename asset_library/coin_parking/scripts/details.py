"""Reference-shaped parking equipment; dimensions in metres."""
import math
import bpy
from mathutils import Vector,Matrix
from . import components as c


def label(name,body,loc,size,material,width=None,bold=.008):
    o=c.text(name,body,loc,size,material,width=width)
    o['typeface']='Bfont + configured Japanese font';o['text']=body
    return o


def weather(material,amount=.18):
    n,l=material.node_tree.nodes,material.node_tree.links
    p=next(x for x in n if x.type=='BSDF_PRINCIPLED')
    base=p.inputs['Base Color'].links[0].from_socket if p.inputs['Base Color'].is_linked else None
    tc=n.new('ShaderNodeTexCoord');stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(32,32,2.4);l.new(tc.outputs['Object'],stretch.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=3
    l.new(stretch.outputs[0],noise.inputs['Vector'])
    mask=n.new('ShaderNodeMapRange');mask.clamp=True
    mask.inputs['From Min'].default_value=.49;mask.inputs['From Max'].default_value=.76
    mask.inputs['To Max'].default_value=amount;l.new(noise.outputs['Fac'],mask.inputs[0])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[2].default_value=(.26,.23,.18,1)
    if base:l.new(base,mix.inputs[1])
    else:mix.inputs[1].default_value=p.inputs['Base Color'].default_value
    l.new(mask.outputs[0],mix.inputs[0]);l.new(mix.outputs[0],p.inputs['Base Color'])


def rail(name,length):
    m=c.M;h=.68;r=.14;half=length/2
    points=[(-half,0,.04),(-half,0,h-r)]
    for i in range(9):
        a=math.pi-i*math.pi/16;points.append((-half+r+r*math.cos(a),0,h-r+r*math.sin(a)))
    points.append((half-r,0,h))
    for i in range(1,9):
        a=math.pi/2-i*math.pi/16;points.append((half-r+r*math.cos(a),0,h-r+r*math.sin(a)))
    points.append((half,0,.04));c.tube(name,points,.03025,m['orange'])
    for x in (-half,half):
        c.box('fence square footing',(x,0,.015),(.18,.18,.03),m['concrete'],.008)
        c.cyl('painted fence sleeve',(x,0,.08),.042,.11,m['orange'])


def cone():
    # Color-cone RG70045 manufacturer drawing: 721 high, 380 square x45 base,
    # diameter 236.34 at z90, 57 at neck, 40 bore. Integrated weighted base.
    m=c.M
    base=c.box('380 mm weighted moulded foot',(0,0,.0225),(.38,.38,.045),m['rubber'],.016)
    base['reference']='Color-cone RG70045 drawing';base['nominal_height_m']=.721
    def radius(z):return .11817+(.0285-.11817)*(z-.09)/(.716-.09)
    levels=[.09,.322,.428,.470,.625,.645,.68,.716]
    profile=[(.045,.137),(.058,.129),(.070,.121),(.09,.11817)]+[(z,radius(z)) for z in levels[1:]]+[(.721,.027)]
    n=64;verts=[(r*math.cos(j*math.tau/n),r*math.sin(j*math.tau/n),z) for z,r in profile for j in range(n)]
    faces=[];indices=[]
    for i in range(len(profile)-1):
        z=profile[i][0]
        for j in range(n):
            faces.append((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j))
            indices.append(0)
    ob=c.mesh_obj('continuous tapered cone shell',verts,faces,m['orange']);ob.data.materials.append(m['white'])
    for face,index in zip(ob.data.polygons,indices):face.material_index=index;face.use_smooth=True
    # User's Unknown.jpg: three reflective wraps with a shallow V at front/back.
    for low,high in ((.210,.278),(.355,.420),(.500,.560)):
        vertices=[]
        for level in (low,high):
            for j in range(n):
                angle=j*math.tau/n;z=level+.030*abs(math.cos(angle));r=radius(z)+.00035
                vertices.append((r*math.cos(angle),r*math.sin(angle),z))
        sheet=c.mesh_obj('three V edged reflective bands',vertices,[(j,(j+1)%n,n+(j+1)%n,n+j) for j in range(n)],m['white'])
        for face in sheet.data.polygons:face.use_smooth=True
    # The inside wall leaves the specified 40 mm opening visible.
    verts=[(r*math.cos(j*math.tau/n),r*math.sin(j*math.tau/n),z) for z,r in [(.721,.027),(.721,.020),(.65,.020)] for j in range(n)]
    faces=[(i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j) for i in (0,1) for j in range(n)]
    c.mesh_obj('cone neck lip and 40 mm bore',verts,faces,m['orange'])
    c.cyl('dark inside neck',(0,0,.647),.020,.002,m['black'],48)
    for z in (.661,.673,.685,.697,.708):
        r=radius(z)
        c.tube('moulded neck grip',[(r*math.cos(j*math.tau/48),r*math.sin(j*math.tau/48),z) for j in range(49)],.001,m['orange'])


def cone_bar():
    # Nominal 2 m x34 mm; 78 mm inner end-eye diameter. Eyes rest on taper.
    m=c.M;z=.643
    for i in range(10):
        a=-.915+i*.183;b=a+.183
        c.cyl('black yellow cone bar',((a+b)/2,0,z),.017,b-a,m['yellow'] if i%2==0 else m['black'],32,(1,0,0))
    for x in (-.945,.945):
        pts=[(x+.047*math.cos(j*math.tau/48),.047*math.sin(j*math.tau/48),z) for j in range(49)]
        c.tube('78 mm inner cone bar end eye',pts,.008,m['black'])



def payment(x,y):
    m=c.M
    c.box('payment concrete plinth',(x,y,.055),(.82,.70,.11),m['concrete'],.016)
    c.box('folded cabinet body',(x,y,.985),(.54,.42,1.75),m['yellow'],.014)
    c.box('lower service panel',(x,y-.215,.31),(.514,.013,.385),m['yellow'],.007)
    c.box('front door perimeter seal',(x,y-.216,1.16),(.505,.012,1.27),m['rubber'],.007)
    c.box('upper hinged cabinet door',(x,y-.225,1.16),(.486,.012,1.248),m['yellow'],.006)
    c.box('deep rain hood',(x,y-.015,1.884),(.585,.53,.075),m['yellow'],.007)
    c.box('hood shadow underside',(x,y-.043,1.842),(.53,.43,.008),m['black'])
    c.box('hood folded drip lip',(x,y-.275,1.861),(.585,.015,.035),m['yellow'],.003)
    c.box('control panel gasket',(x,y-.235,1.438),(.466,.006,.665),m['black'],.004)
    c.box('brushed stainless control panel',(x,y-.241,1.438),(.451,.006,.650),m['zinc'],.004)
    c.box('upper instrument black surround',(x,y-.25,1.635),(.435,.012,.228),m['black'],.008)
    c.box('display raised bezel',(x-.092,y-.264,1.636),(.224,.02,.160),m['steel'],.004)
    c.box('display protective glass',(x-.092,y-.276,1.636),(.201,.003,.138),m['lcd'],.003)
    label('display prompt','車室番号',(x-.092,y-.279,1.672),.028,m['navy'],.18,.002)
    label('display value','００１',(x-.092,y-.279,1.616),.043,m['navy'],.18,.003)
    c.box('keypad metal escutcheon',(x+.135,y-.266,1.641),(.167,.016,.19),m['zinc'],.004)
    for row in range(4):
        for col in range(3):
            xx=x+.079+col*.055;zz=1.703-row*.043
            c.box('key gasket',(xx,y-.278,zz),(.043,.006,.034),m['black'],.003)
            c.box('metal keypad key',(xx,y-.285,zz),(.036,.009,.028),m['yellow'] if row==3 and col==2 else m['zinc'],.003)
            text=str(row*3+col+1) if row<3 else ['消','0','確'][col]
            label('key engraving',text,(xx,y-.291,zz),.021,m['black'],.031,.002)
    # The reference has a compact left cash/service cluster and a projecting
    # right cashless terminal, instead of one featureless flat front panel.
    c.box('service card slot black recess',(x-.096,y-.258,1.487),(.22,.02,.048),m['black'],.004)
    c.box('service slot metal surround',(x-.096,y-.271,1.487),(.198,.008,.032),m['zinc'],.002)
    c.box('service ticket narrow throat',(x-.096,y-.277,1.487),(.178,.003,.008),m['black'])
    label('service ticket label','サービス券',(x-.096,y-.247,1.525),.022,m['black'],.19,.002)
    for xx,rad in [(x-.156,.040),(x-.058,.032)]:
        c.cyl('cash inlet ring',(xx,y-.265,1.393),rad,.025,m['zinc'],48,(0,-1,0))
    c.box('coin aperture',(x-.156,y-.281,1.393),(.005,.003,.052),m['black'])
    c.box('coin return slot',(x-.058,y-.281,1.393),(.041,.003,.006),m['black'])
    c.box('contactless reader thick body',(x+.134,y-.278,1.413),(.155,.078,.224),m['black'],.012)
    c.box('reader gloss screen',(x+.134,y-.320,1.428),(.117,.003,.166),m['lcd'],.005)
    label('reader screen','決済',(x+.134,y-.323,1.45),.031,m['navy'],.10,.002)
    label('reader touch mark',')))',(x+.134,y-.323,1.397),.033,m['navy'],.10,.002)
    c.box('reader bottom indicator',(x+.134,y-.324,1.309),(.104,.006,.008),m['yellow'],.003)
    c.box('bill reader projecting cassette',(x+.127,y-.273,1.195),(.178,.060,.149),m['black'],.012)
    c.box('bill mouth lower shelf',(x+.127,y-.310,1.15),(.152,.023,.026),m['steel'],.004)
    c.box('banknote throat',(x+.127,y-.306,1.24),(.142,.003,.012),m['black'])
    c.box('banknote yellow label',(x+.127,y-.307,1.198),(.137,.002,.047),m['yellow'],.001)
    label('banknote label','千円札',(x+.127,y-.309,1.20),.028,m['black'],.13,.002)
    # Three numbered yellow instruction labels follow the supplied photograph.
    for z,num,line1,line2 in [(1.30,'1','車室番号を入力','番号を確認してください'),(1.185,'2','料金をお支払い','硬貨・千円札が使えます')]:
        c.box('numbered yellow instruction',(x-.108,y-.246,z),(.225,.002,.102),m['yellow'],.001)
        label('instruction step',num,(x-.204,y-.249,z+.028),.030,m['black'],.025,.004)
        label('instruction line',line1,(x-.094,y-.249,z+.025),.026,m['black'],.18,.002)
        label('instruction detail',line2,(x-.107,y-.249,z-.021),.018,m['black'],.205,.001)
    c.box('exit instruction sticker',(x,y-.239,1.057),(.443,.002,.094),m['yellow'],.001)
    label('step three','3  ロック板が下がってから出庫',(x,y-.242,1.074),.023,m['black'],.415,.002)
    label('exit instruction detail','足元のロック板をご確認ください',(x,y-.242,1.036),.021,m['black'],.415,.001)
    # Deep return chute with internal angled baffle and a clear protective flap.
    c.box('return surround label',(x+.070,y-.235,.695),(.266,.006,.157),m['yellow'],.005)
    label('return label','4  おつり・領収書',(x+.07,y-.240,.750),.029,m['black'],.247,.003)
    c.box('return tray cavity',(x+.07,y-.245,.667),(.228,.020,.098),m['black'],.008)
    c.box('return tray lower lip',(x+.07,y-.286,.620),(.230,.064,.014),m['zinc'],.004)
    for dx in (-.108,.108):c.box('return tray side',(x+.07+dx,y-.267,.66),(.009,.06,.09),m['zinc'],.002)
    for dx in (-.064,0,.064):c.box('clear return curtain',(x+.07+dx,y-.279,.673),(.058,.004,.078),m['glass'],.002)
    for z in (.65,1.65):c.box('door hinge',(x-.254,y-.223,z),(.020,.02,.088),m['zinc'],.003)
    for z in (.59,1.49):
        c.cyl('service keyed lock',(x+.228,y-.237,z),.012,.008,m['zinc'],24,(0,-1,0))
        c.box('keyway',(x+.228,y-.243,z),(.002,.002,.012),m['black'])
    for xx in (-.21,.21):
        for zz in (1.135,1.738):c.bolt((x+xx,y-.248,zz),face=True)
    for zz in (.40,.425,.45,.475):c.box('side louvre',(x+.271,y+.08,zz),(.004,.16,.007),m['black'])
    c.tube('rear cable conduit',[(x+.19,y+.235,1.2),(x+.19,y+.235,.16),(x+.30,y+.24,.045)],.014,m['zinc'])


def signs(layout):
    sign_start=set(c.ACTIVE.objects)
    m=c.M;sx,_=layout.payment;sy=1.4
    for xx in (sx-.78,sx+.78):
        c.cyl('tariff board post',(xx,sy,1.77),.036,3.54,m['navy'])
        c.box('tariff board socket',(xx,sy,.04),(.22,.22,.08),m['concrete'],.012)
    c.box('tariff folded aluminum frame',(sx,sy,2.83),(1.90,.10,1.46),m['navy'],.012)
    c.box('tariff yellow panel',(sx,sy-.056,2.83),(1.84,.009,1.40),m['yellow'],.004)
    c.box('tariff header green band',(sx,sy-.062,3.40),(1.82,.003,.24),m['navy'])
    label('tariff header','24時間 コインパーキング',(sx,sy-.065,3.4),.154,m['white'],1.72,.011)
    label('daytime hours','8:00〜22:00',(sx,sy-.065,3.16),.164,m['navy'],1.68,.011)
    label('regular rate','20分 400円',(sx,sy-.065,2.94),.38,m['red'],1.70,.019)
    c.box('night maximum white field',(sx,sy-.063,2.505),(1.82,.004,.54),m['white'])
    label('night hours','夜間最大  22:00〜8:00',(sx,sy-.068,2.66),.134,m['navy'],1.70,.009)
    label('night maximum','1,200円',(sx,sy-.068,2.41),.38,m['red'],1.64,.020)
    label('repeat condition','繰り返し適用・全日同一料金',(sx,sy-.067,2.18),.080,m['navy'],1.7,.005)
    for dx in (-.85,.85):
        for z in (2.19,3.47):c.bolt((sx+dx,sy-.065,z),face=True)
    # Rotate the entire double-faced sign 90 degrees: both traffic approaches
    # see a face, instead of looking edge-on along the carriageway.
    # Place opposite the payment machine, 30 cm outside the clear mouth.
    side=1 if layout.payment[0]<layout.entrance_x else -1
    px=layout.entrance_x+side*(layout.entrance_width/2+.30);py=.64
    c.cyl('P sign post',(px,py,2.01),.052,4.02,m['navy'])
    before=set(c.ACTIVE.objects)
    c.box('large double faced P sign',(px,py,3.91),(1.18,.24,1.25),m['navy'],.025)
    label('large bold P','P',(px,py-.128,4.02),1.16,m['white'],1.00,.035)
    label('P hours','24時間',(px,py-.128,3.44),.18,m['yellow'],.98,.011)
    back=label('reverse bold P','P',(px,py+.128,4.02),1.16,m['white'],1.00,.035);back.rotation_euler.z=math.pi
    back=label('reverse P hours','24時間',(px,py+.128,3.44),.18,m['yellow'],.98,.011);back.rotation_euler.z=math.pi
    transform=Matrix.Translation((px,py,0))@Matrix.Rotation(math.pi/2,4,'Z')@Matrix.Translation((-px,-py,0))
    bpy.context.view_layer.update()
    for obj in set(c.ACTIVE.objects)-before:obj.matrix_world=transform@obj.matrix_world
    for obj in set(c.ACTIVE.objects)-sign_start:
        if 'text' in obj:obj.scale*=.80
