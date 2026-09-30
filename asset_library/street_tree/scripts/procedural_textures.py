"""Structural bark and deterministic code-generated leaf PBR materials."""

import math

import bpy
import numpy as np


BARK_SIZE = (512, 1024)
LEAF_SIZE = (256, 256)


def _smoothstep(value):
    return value * value * (3.0 - 2.0 * value)


def _value_noise(height, width, cells_y, cells_x, seed):
    """Small periodic value-noise implementation using vectorized bilinear interpolation."""
    rng = np.random.default_rng(seed)
    grid = rng.random((cells_y + 1, cells_x + 1), dtype=np.float32)
    grid[-1, :] = grid[0, :]
    grid[:, -1] = grid[:, 0]
    yy = np.arange(height, dtype=np.float32)[:, None] * cells_y / height
    xx = np.arange(width, dtype=np.float32)[None, :] * cells_x / width
    y0 = np.floor(yy).astype(np.int32)
    x0 = np.floor(xx).astype(np.int32)
    fy = _smoothstep(yy - y0)
    fx = _smoothstep(xx - x0)
    a = grid[y0, x0]
    b = grid[y0, x0 + 1]
    c = grid[y0 + 1, x0]
    d = grid[y0 + 1, x0 + 1]
    return ((a * (1.0 - fx) + b * fx) * (1.0 - fy) +
            (c * (1.0 - fx) + d * fx) * fy)


def _fractal(height, width, seed, base_cells=(3, 4), octaves=5):
    total = np.zeros((height, width), dtype=np.float32)
    weight = 0.0
    amplitude = 1.0
    for octave in range(octaves):
        total += _value_noise(
            height, width, base_cells[0] * 2 ** octave,
            base_cells[1] * 2 ** octave, seed + octave * 977,
        ) * amplitude
        weight += amplitude
        amplitude *= 0.52
    return total / weight


def _rgba(rgb):
    alpha = np.ones((*rgb.shape[:2], 1), dtype=np.float32)
    return np.concatenate((np.clip(rgb, 0.0, 1.0).astype(np.float32), alpha), axis=2)


def _linear_to_srgb(value):
    value = np.clip(value, 0.0, 1.0)
    return np.where(value <= 0.0031308, value * 12.92,
                    1.055 * np.power(value, 1.0 / 2.4) - 0.055)


def _gray_rgba(value):
    rgb = np.repeat(np.clip(value, 0.0, 1.0)[..., None], 3, axis=2)
    return _rgba(rgb)


def _image(name, array, color_space):
    existing = bpy.data.images.get(name)
    if existing is not None:
        return existing
    height, width = array.shape[:2]
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = color_space
    image.pixels.foreach_set(array.ravel())
    image.update()
    image.pack()
    image["code_generated"] = True
    return image


def _leaf_maps(species, seed):
    width, height = LEAF_SIZE
    u = np.arange(width, dtype=np.float32)[None, :] / (width - 1)
    v = np.arange(height, dtype=np.float32)[:, None] / (height - 1)
    x = u - 0.5
    noise = _fractal(height, width, seed, (5, 5), 4)
    main_vein = np.exp(-((x / 0.014) ** 2))
    side_veins = np.zeros((height, width), dtype=np.float32)
    if species == "ginkgo":
        angle = np.arctan2(x, np.maximum(0.02, v - 0.02))
        side_veins = np.exp(-((np.sin(angle * 8.0) / 0.18) ** 2)) * np.clip(v * 1.4, 0, 1)
        main_vein = main_vein * np.clip(0.65 - v, 0.0, 1.0) * 1.6
    else:
        for level in np.linspace(0.18, 0.82, 7):
            line = np.abs(v - level - np.abs(x) * (0.58 if species == "cherry" else 0.72))
            side_veins = np.maximum(side_veins, np.exp(-((line / 0.010) ** 2)))
        side_veins *= np.clip(1.0 - np.abs(x) * 1.5, 0.0, 1.0)
    veins = np.clip(main_vein * 0.95 + side_veins * 0.48, 0.0, 1.0)
    edge_tone = np.clip(np.sqrt((x / 0.52) ** 2 + ((v - 0.5) / 0.58) ** 2), 0, 1)
    value = np.clip(0.72 + (noise - 0.5) * 0.22 - edge_tone * 0.12 + veins * 0.16,
                    0.30, 1.0)
    base = np.stack((value * 0.88, value, value * 0.72), axis=2)
    height_map = np.clip(0.42 + (noise - 0.5) * 0.10 + veins * 0.48, 0.05, 0.98)
    roughness = np.clip(0.40 + (noise - 0.5) * 0.20 + veins * 0.10, 0.30, 0.62)
    return _rgba(_linear_to_srgb(base)), _gray_rgba(height_map), _gray_rgba(roughness)


def _image_node(nodes, image, name):
    node = nodes.new("ShaderNodeTexImage")
    node.name = name
    node.image = image
    node.extension = "REPEAT"
    node.interpolation = "Linear"
    return node


def _leaf_material(species, tint, variant, images):
    name = f"Street tree {species} generated leaf {variant}"
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    base_image, height_image, roughness_image = images
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*tint, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    base = _image_node(nodes, base_image, "Generated leaf base")
    height = _image_node(nodes, height_image, "Generated leaf veins")
    rough = _image_node(nodes, roughness_image, "Generated leaf roughness")
    front = nodes.new("ShaderNodeMixRGB")
    front.blend_type = "MULTIPLY"
    front.inputs[0].default_value = 1.0
    front.inputs[2].default_value = (*tint, 1.0)
    links.new(base.outputs["Color"], front.inputs[1])
    geometry = nodes.new("ShaderNodeNewGeometry")
    underside = nodes.new("ShaderNodeMixRGB")
    underside.blend_type = "MIX"
    underside.inputs[2].default_value = (
        min(1.0, tint[0] * 1.22), min(1.0, tint[1] * 1.12),
        min(1.0, tint[2] * 0.94), 1.0,
    )
    back = nodes.new("ShaderNodeMixRGB")
    back.blend_type = "MULTIPLY"
    back.inputs[0].default_value = 1
    back.inputs[2].default_value = (tint[0]*1.3, tint[1]*1.18, tint[2]*1.08, 1)
    links.new(base.outputs["Color"], back.inputs[1])
    links.new(back.outputs[0], underside.inputs[2])
    links.new(geometry.outputs["Backfacing"], underside.inputs[0])
    links.new(front.outputs["Color"], underside.inputs[1])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.00012
    links.new(height.outputs["Color"], bump.inputs["Height"])
    links.new(underside.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.055
    output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
    for link in list(output.inputs["Surface"].links):
        links.remove(link)
    translucent = nodes.new("ShaderNodeBsdfTranslucent")
    translucent.inputs["Color"].default_value = (
        min(1.0, tint[0] * 1.30), min(1.0, tint[1] * 1.18),
        min(1.0, tint[2] * 0.96), 1.0,
    )
    mix_shader = nodes.new("ShaderNodeMixShader")
    mix_shader.inputs[0].default_value = 0.24
    links.new(bsdf.outputs["BSDF"], mix_shader.inputs[1])
    links.new(underside.outputs["Color"], translucent.inputs["Color"])
    links.new(translucent.outputs["BSDF"], mix_shader.inputs[2])
    links.new(mix_shader.outputs["Shader"], output.inputs["Surface"])
    mat["code_generated_pbr"] = True
    return mat


def ensure_tree_materials(species, bark_color, leaf_colors):
    seed = {"keyaki": 1741, "ginkgo": 2857, "cherry": 3911}[species]
    from asset_library.street_tree.scripts.bark import bark_material
    bark = bark_material(species)
    leaf_base, leaf_height, leaf_roughness = _leaf_maps(species, seed + 613)
    images = (
        _image(f"{species} leaf base color", leaf_base, "sRGB"),
        _image(f"{species} leaf height", leaf_height, "Non-Color"),
        _image(f"{species} leaf roughness", leaf_roughness, "Non-Color"),
    )
    leaves = tuple(
        _leaf_material(species, color, index + 1, images)
        for index, color in enumerate(leaf_colors)
    )
    return bark, leaves


__all__ = ("BARK_SIZE", "LEAF_SIZE", "ensure_tree_materials")


def shrub_leaf_material(name, tint):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    names = ("Shrub leaf albedo", "Shrub leaf veins", "Shrub leaf roughness")
    images = tuple(bpy.data.images.get(n) for n in names)
    if not all(images):
        maps = _leaf_maps("cherry", 7013)
        images = tuple(_image(n, a, "sRGB" if i == 0 else "Non-Color")
                       for i, (n, a) in enumerate(zip(names, maps)))
    mat = _leaf_material("shrub", tint, name, images)
    mat.name = name
    return mat
