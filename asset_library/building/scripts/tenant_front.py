"""Original convenience tenant frontage, independent office entrance."""
from .facade import pane
from .street_detail import entrance_hardware
from .details import text

def store_front(g,col,root,spec,d,f):
    w=f.length;h=d.base_height;office=w-1.15;end=w-2.45
    for a,b in ((.15,end),(end+.2,w-.15)):
        count=max(1,round((b-a)/1.8));bay=(b-a)/count
        for i in range(count):pane(f,a+(i+.5)*bay,1.52,bay-.06,3.0,'silver','clear',-.40)
    f.box(spec.wall,end+.1,-.1,h/2,.22,.65,h)
    f.box('white',end/2,.05,3.42,end,.30,.70)
    for zz in (3.18,3.67):f.box('store_teal',end/2,.215,zz,end,.035,.10)
    text(col,root,'CONVENIENCE',f.point(end/2,.24,3.44),.39,end-.8,key='store_teal')
    f.box('dark_metal',end/2,.20,3.03,end,.9,.10)
    for x in (end-.95,end-2.20):f.box('silver',x,-.30,1.5,.04,.07,2.9)
    entrance_hardware(f,end-1.55,2.2,2.90,-.40)
    entrance_hardware(f,office,1.30,3.0,-.40,automatic=False)
    f.box('black',end-1.55,-.15,.02,2.2,1.0,.04)
    text(col,root,'OFFICE',f.point(office,.10,3.26),.19,1.7,key='dark_metal')
    f.tube('silver',(office,-.28,1),(office,-.28,1.6),.022)
    f.box(spec.wall,w/2,-.10,(h+3.74)/2,w,.3,h-3.74)
