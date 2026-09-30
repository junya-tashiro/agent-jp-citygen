"""Geometry and generated finishes shared by the rectangular parking asset."""
from pathlib import Path
import os
import json
import math
import random
import sys
import unicodedata
import time

import bpy
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
RNG = random.Random(240905)
M = {}
ACTIVE = None


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def put(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    ACTIVE.objects.link(obj)
    return obj


def mat(name, color, rough=.6, metal=0, grain=0, bump=.001):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    p = next(v for v in n if v.type == 'BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    if grain:
        tex = n.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = grain
        tex.inputs['Detail'].default_value = 3
        tc = n.new('ShaderNodeTexCoord')
        l.new(tc.outputs['Object'], tex.inputs['Vector'])
        ramp = n.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = (*(v*.62 for v in color), 1)
        ramp.color_ramp.elements[1].color = (*(min(v*1.25, 1) for v in color), 1)
        l.new(tex.outputs['Fac'], ramp.inputs[0])
        l.new(ramp.outputs[0], p.inputs['Base Color'])
        b = n.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = .38
        b.inputs['Distance'].default_value = bump
        l.new(tex.outputs['Fac'], b.inputs['Height'])
        l.new(b.outputs['Normal'], p.inputs['Normal'])
    M[name] = m
    return m


def asphalt():
    # The shared generated aggregate has a continuous warped fracture field;
    # large rectangles must not reveal identical cracks every three metres.
    from asset_library.shared.surfaces import asphalt_shader_group
    m=mat('asphalt / weathered aggregate',(.09,.091,.089),.88)
    n,l=m.node_tree.nodes,m.node_tree.links
    p=next(v for v in n if v.type=='BSDF_PRINCIPLED')
    field=n.new('ShaderNodeGroup');field.node_tree=asphalt_shader_group()
    l.new(field.outputs['Color'],p.inputs['Base Color'])
    l.new(field.outputs['Roughness'],p.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.65;bump.inputs['Distance'].default_value=.008
    l.new(field.outputs['Height'],bump.inputs['Height']);l.new(bump.outputs[0],p.inputs['Normal'])
    return m


def footing_weather(material):
    """World-space damp accumulation fading over the bottom 50cm of masonry."""
    n,l=material.node_tree.nodes,material.node_tree.links
    p=next(v for v in n if v.type=='BSDF_PRINCIPLED')
    old=p.inputs['Base Color'].links[0].from_socket
    geom=n.new('ShaderNodeNewGeometry');sep=n.new('ShaderNodeSeparateXYZ')
    l.new(geom.outputs['Position'],sep.inputs[0])
    ramp=n.new('ShaderNodeMapRange');ramp.clamp=True
    ramp.inputs['From Min'].default_value=.03;ramp.inputs['From Max'].default_value=.65
    ramp.inputs['To Min'].default_value=.75;ramp.inputs['To Max'].default_value=0
    l.new(sep.outputs['Z'],ramp.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=7;noise.inputs['Detail'].default_value=4
    l.new(geom.outputs['Position'],noise.inputs['Vector'])
    mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY'
    l.new(noise.outputs['Fac'],mul.inputs[0]);l.new(ramp.outputs[0],mul.inputs[1])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[2].default_value=(.20,.23,.15,1)
    l.new(mul.outputs[0],mix.inputs[0]);l.new(old,mix.inputs[1]);l.new(mix.outputs[0],p.inputs['Base Color'])


def worn_paint():
    m = mat('aged thermoplastic white', (.74,.735,.66), .82, grain=160, bump=.0007)
    n, l = m.node_tree.nodes, m.node_tree.links
    p = next(v for v in n if v.type == 'BSDF_PRINCIPLED')
    tex = n.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = 120
    tex.inputs['Detail'].default_value = 2
    tc = n.new('ShaderNodeTexCoord')
    l.new(tc.outputs['Object'], tex.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .34
    ramp.color_ramp.elements[1].position = .46
    l.new(tex.outputs['Fac'], ramp.inputs[0])
    transparent = n.new('ShaderNodeBsdfTransparent')
    mix = n.new('ShaderNodeMixShader')
    l.new(ramp.outputs[0], mix.inputs[0])
    l.new(transparent.outputs[0], mix.inputs[1])
    l.new(p.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], next(v for v in n if v.type == 'OUTPUT_MATERIAL').inputs[0])
    return m


def box(name, loc, dims, material, bevel=0):
    # Direct mesh creation avoids context/depsgraph overhead in repeated pieces.
    x,y,z = (v/2 for v in dims)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),
                      (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)], [],
                     [(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)])
    mesh.materials.append(material)
    ob = bpy.data.objects.new(name, mesh)
    ACTIVE.objects.link(ob)
    ob.location = loc
    if bevel:
        b = ob.modifiers.new('manufactured edge', 'BEVEL')
        b.width, b.segments = bevel, 3
        b = ob.modifiers.new('weighted corner normals', 'WEIGHTED_NORMAL')
    return ob


def mesh_obj(name, verts, faces, material):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(material)
    ob = bpy.data.objects.new(name, me)
    ACTIVE.objects.link(ob)
    return ob


def tube(name, points, radius, material):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.resolution_u = 1
    c.bevel_depth, c.bevel_resolution = radius, 2
    s = c.splines.new('POLY')
    s.points.add(len(points)-1)
    for p, xyz in zip(s.points, points):
        p.co = (*xyz, 1)
    c.materials.append(material)
    ob = bpy.data.objects.new(name, c)
    ACTIVE.objects.link(ob)
    return ob


def cyl(name, loc, radius, depth, material, vertices=24, direction=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    ob = put(bpy.context.object)
    ob.name = name
    ob.data.materials.append(material)
    if direction:
        ob.rotation_euler = Vector(direction).to_track_quat('Z','Y').to_euler()
    for p in ob.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return ob


def font_find():
    from asset_library.shared.fonts import japanese_font
    return japanese_font()


def text(name, body, loc, size, material, width=None, ground=False, align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body, cu.size, cu.align_x, cu.align_y = body, size, align, 'CENTER'
    # Keep the default Bfont for ASCII. The alternate font slot selects Japanese
    # glyphs without splitting a line into separate objects.
    cu.font_bold = JP
    for char, style in zip(body, cu.body_format):
        style.use_bold = not char.isascii()
    cu.resolution_u = 12
    # Preserve the original fill: offsetting Japanese contours breaks tessellation.
    # A tiny round edge expands strokes without changing their fill boundaries.
    cu.bevel_depth = size * .008
    cu.bevel_resolution = 3
    cu.space_character = 1.03
    cu.materials.append(material)
    ob = bpy.data.objects.new(name, cu)
    ACTIVE.objects.link(ob)
    ob.location = loc
    if not ground:
        ob.rotation_euler.x = math.pi/2
    if width:
        bpy.context.view_layer.update()
        if ob.dimensions.x > width:
            ob.scale *= width / ob.dimensions.x
    return ob



def bolt(loc, face=False):
    cyl('M10 galvanized anchor / washer', loc, .014, .003, M['zinc'], 20, (0,-1,0) if face else None)
    xyz = (loc[0],loc[1]-.004,loc[2]) if face else (loc[0],loc[1],loc[2]+.005)
    cyl('hex head', xyz, .008, .008, M['zinc'], 6, (0,-1,0) if face else None)


def prism_y(name, cx, cy, width, section, material):
    verts = [(cx+side*width/2, cy+y,z) for side in [-1,1] for y,z in section]
    n = len(section)
    faces = [tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh_obj(name, verts, faces, material)
