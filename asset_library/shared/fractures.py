"""Seeded, seamless asphalt fracture field; independent of any road layout."""
import math
import random
import bpy
import numpy as np

TILE_METRES = 24.0


def fracture_image():
    name = 'Asphalt irregular branching fractures'
    existing = bpy.data.images.get(name)
    if existing is not None:
        return existing
    size = 2048
    pixels_per_metre = size/TILE_METRES
    mask = np.zeros((size,size),dtype=np.float32)
    rng = random.Random(0xA5FA17)

    def segment(a,b,width,strength):
        a=np.asarray(a)*pixels_per_metre
        b=np.asarray(b)*pixels_per_metre
        radius=width*pixels_per_metre*.5
        low=np.floor(np.minimum(a,b)-radius-1).astype(int)
        high=np.ceil(np.maximum(a,b)+radius+1).astype(int)
        xs=np.arange(low[0],high[0]+1);ys=np.arange(low[1],high[1]+1)
        xx,yy=np.meshgrid(xs+.5,ys+.5)
        delta=b-a
        along=np.clip(((xx-a[0])*delta[0]+(yy-a[1])*delta[1])/max(float(delta@delta),1e-10),0,1)
        distance=np.sqrt((xx-a[0]-along*delta[0])**2+(yy-a[1]-along*delta[1])**2)
        coverage=np.clip(radius+.60-distance,0,1)*strength
        iy,ix=np.meshgrid(ys%size,xs%size,indexing='ij')
        mask[iy,ix]=np.maximum(mask[iy,ix],coverage)

    def path(origin,angle,steps,width,branching=True):
        point=origin
        for i in range(steps):
            angle+=rng.uniform(-.39,.39)
            length=rng.uniform(.09,.28)
            end=(point[0]+math.cos(angle)*length,point[1]+math.sin(angle)*length)
            taper=min(1.,(i+1)/3,(steps-i)/4)
            # Short interruptions and fluctuating aperture avoid drawn lines.
            if rng.random()>.075:
                segment(point,end,width*rng.uniform(.65,1.30)*taper,rng.uniform(.70,1.0))
            if branching and i>3 and rng.random()<.075:
                path(point,angle+rng.choice((-1,1))*rng.uniform(.45,1.10),rng.randint(3,9),width*.53,False)
            point=end

    for _ in range(34):
        origin=(rng.uniform(0,TILE_METRES),rng.uniform(0,TILE_METRES))
        path(origin,rng.uniform(0,math.tau),rng.randint(8,32),rng.uniform(.006,.019))
    rgba=np.empty((size,size,4),dtype=np.float32)
    rgba[:,:,:3]=mask[:,:,None];rgba[:,:,3]=1
    image=bpy.data.images.new(name,width=size,height=size,alpha=False)
    image.colorspace_settings.name='Non-Color'
    image.pixels.foreach_set(rgba.reshape(-1))
    image.pack()
    image['physical_tile_m']=TILE_METRES
    image['generator']='Seeded random walks with branches, tapered aperture and gaps'
    return image


def fracture_field(nodes,links):
    position=nodes.new('ShaderNodeNewGeometry').outputs['Position']
    warp=nodes.new('ShaderNodeTexNoise')
    warp.inputs['Scale'].default_value=.075
    warp.inputs['Detail'].default_value=2
    links.new(position,warp.inputs['Vector'])
    amplitude=nodes.new('ShaderNodeVectorMath');amplitude.operation='SCALE'
    amplitude.inputs[3].default_value=6.0
    links.new(warp.outputs['Color'],amplitude.inputs[0])
    shifted=nodes.new('ShaderNodeVectorMath');shifted.operation='ADD'
    links.new(position,shifted.inputs[0]);links.new(amplitude.outputs[0],shifted.inputs[1])
    scale=nodes.new('ShaderNodeVectorMath');scale.operation='SCALE'
    scale.inputs[3].default_value=1/TILE_METRES
    links.new(shifted.outputs[0],scale.inputs[0])
    texture=nodes.new('ShaderNodeTexImage');texture.image=fracture_image()
    texture.label='Nonperiodic world warp / branching hairline fractures'
    links.new(scale.outputs[0],texture.inputs['Vector'])
    strength=nodes.new('ShaderNodeMath');strength.operation='MULTIPLY'
    strength.inputs[1].default_value=.62
    links.new(texture.outputs['Color'],strength.inputs[0])
    return strength.outputs[0]
