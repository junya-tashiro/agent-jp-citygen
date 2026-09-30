"""Rectangle packing with a single shared entrance and unobstructed aisles.

Coordinates: [0,width] x [0,depth], front boundary y=0; metres.
"""
from dataclasses import dataclass, asdict
import math

BAY_WIDTH=2.5
BAY_DEPTH=5.0
AISLE_MIN=5.5
EDGE=.4
FRONT=2.0

@dataclass(frozen=True)
class Bay:
    number:int
    x:float
    y:float
    rotation:float

@dataclass(frozen=True)
class Layout:
    width:float
    depth:float
    kind:str
    bays:tuple
    entrance_x:float
    entrance_width:float
    aisle:tuple
    payment:tuple
    @property
    def capacity(self):return len(self.bays)
    def to_dict(self):return dict(asdict(self),capacity=self.capacity)

def plan(width,depth):
    if not all(math.isfinite(v) and v>0 for v in (width,depth)):
        raise ValueError('Width and depth must be finite positive metres.')
    options=[]
    # A transverse rear row with a generous full-width turning court.
    n=math.floor((width-2*EDGE+1e-8)/BAY_WIDTH)
    if width>=7.2 and depth>=FRONT+AISLE_MIN+BAY_DEPTH+EDGE and n:
        left=(width-n*BAY_WIDTH)/2
        bays=tuple(Bay(i+1,left+(i+.5)*BAY_WIDTH,depth-EDGE-BAY_DEPTH/2,0) for i in range(n))
        options.append(Layout(width,depth,'rear_row',bays,width/2,4.2,
                              (EDGE,FRONT,width-EDGE,depth-EDGE-BAY_DEPTH),(width-1.05,.85)))
    # Perpendicular rows facing one continuous access aisle from the entrance.
    n=math.floor((depth-FRONT-1.5+1e-8)/BAY_WIDTH)
    for rows in (1,2):
        if n<1 or width<2*EDGE+rows*BAY_DEPTH+AISLE_MIN:continue
        left=EDGE+BAY_DEPTH;right=width-EDGE-(BAY_DEPTH if rows==2 else 0)
        bays=[]
        for side in range(rows):
            for i in range(n):
                bays.append(Bay(len(bays)+1,EDGE+BAY_DEPTH/2 if side==0 else width-EDGE-BAY_DEPTH/2,
                                FRONT+(i+.5)*BAY_WIDTH,90 if side==0 else -90))
        options.append(Layout(width,depth,'double_row' if rows==2 else 'single_row',tuple(bays),
                              (left+right)/2,4.2,(left,FRONT,right,depth-EDGE),(1.5,.85)))
    if not options:
        raise ValueError('Rectangle cannot fit 2.5 x 5 m bays, a 5.5 m aisle and one entrance. '
                         'Try at least 7.2 x 12.9 m, or 11.3 x 6.0 m.')
    return max(options,key=lambda o:(o.capacity,o.kind=='rear_row'))

def bay_bounds(b):
    w,d=(BAY_WIDTH,BAY_DEPTH) if b.rotation==0 else (BAY_DEPTH,BAY_WIDTH)
    return (b.x-w/2,b.y-d/2,b.x+w/2,b.y+d/2)

def validate(layout):
    boxes=[bay_bounds(b) for b in layout.bays]
    def overlaps(a,b):return min(a[2],b[2])-max(a[0],b[0])>1e-6 and min(a[3],b[3])-max(a[1],b[1])>1e-6
    for i,a in enumerate(boxes):
        assert a[0]>=EDGE-1e-6 and a[1]>=FRONT-1e-6
        assert a[2]<=layout.width-EDGE+1e-6 and a[3]<=layout.depth-EDGE+1e-6
        assert not overlaps(a,layout.aisle)
        assert all(not overlaps(a,b) for b in boxes[i+1:])
    assert layout.aisle[2]-layout.aisle[0]>=AISLE_MIN or layout.kind=='rear_row'
    e=layout.entrance_x;half=layout.entrance_width/2
    assert e-half>0 and e+half<layout.width
    px,py=layout.payment
    assert abs(px-e)>half+.4
    return {'bay_overlap':False,'aisle_clear':True,'entrance_width_m':layout.entrance_width,'capacity':layout.capacity}
