"""Code-native Japanese bicycle-lane road marking based on measured proportions."""

import argparse
import math
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from road_generator.blender.primitives import (  # noqa: E402
    ROAD_PAINT_TOP_Z_M, cube, polygon, road_marking_material, weathered_material,
)

REFERENCE_CENTER_X_PX = 446.5
REFERENCE_PAINT_WIDTH_PX = 373.0
REFERENCE_FRONT_Y_PX = 1753.0
REFERENCE_REAR_Y_PX = 7191.0
REFERENCE_LENGTH_WIDTH_RATIO = (
    (REFERENCE_REAR_Y_PX - REFERENCE_FRONT_Y_PX) / REFERENCE_PAINT_WIDTH_PX
)


WHITE_CHEVRON = (
    (432, 1753), (604, 1944), (604, 2083),
    (431, 1890), (260, 2086), (261, 1950),
)
WHITE_ARROW = (
    (440, 2399), (611, 2589), (611, 2729), (488, 2594),
    (488, 2774), (388, 2774), (388, 2595), (267, 2732),
    (267, 2599),
)
RIDER_HEAD = (
    (445, 2987), (473, 2991), (492, 3004), (508, 3028),
    (515, 3056), (513, 3087), (503, 3112), (484, 3133),
    (460, 3143), (438, 3142), (416, 3131), (400, 3112),
    (392, 3095), (388, 3076), (390, 3042), (400, 3018),
    (418, 2998),
)
RIDER_BODY_AND_ARMS = (
    (398, 3158), (502, 3158), (535, 3168), (611, 3378),
    (568, 3392), (510, 3234), (510, 3411), (493, 3414),
    (476, 3423), (461, 3438), (454, 3452), (440, 3433),
    (426, 3422), (411, 3415), (390, 3412), (390, 3225),
    (317, 3389), (275, 3372), (363, 3171),
)
LEFT_HANDLEBAR = ((272, 3377), (370, 3415), (371, 3418), (361, 3443), (262, 3405))
RIGHT_HANDLEBAR = ((621, 3377), (633, 3405), (534, 3445), (524, 3417))
BICYCLE_FORK = (
    (383, 3422), (401, 3429), (424, 3445), (443, 3465),
    (449, 3476), (473, 3448), (515, 3422), (533, 3450),
    (508, 3461), (482, 3484), (471, 3503), (466, 3528),
    (435, 3528), (432, 3526), (432, 3515), (427, 3499),
    (415, 3480), (390, 3459), (366, 3448),
)
CENTRE_HUB = (
    (445, 3549), (451, 3549), (458, 3554), (464, 3570),
    (462, 3591), (452, 3603), (442, 3602), (432, 3584),
    (434, 3561),
)
LEFT_CRANK = (
    (361, 3528), (376, 3531), (384, 3540), (387, 3549),
    (387, 3725), (381, 3738), (370, 3745), (360, 3745),
    (352, 3741), (343, 3725), (343, 3548), (347, 3538),
)
RIGHT_CRANK = (
    (527, 3528), (543, 3532), (553, 3549), (553, 3890),
    (548, 3902), (536, 3911), (520, 3909), (512, 3901),
    (508, 3891), (508, 3548), (512, 3538),
)
FRONT_WHEEL = (
    (444, 3617), (459, 3620), (470, 3638), (470, 4075),
    (466, 4086), (453, 4096), (443, 4096), (435, 4092),
    (426, 4076), (426, 3638), (431, 3626),
)
LEFT_PEDAL = (
    (357, 3760), (374, 3762), (387, 3773), (388, 3790),
    (375, 3803), (351, 3804), (345, 3801), (335, 3788),
    (338, 3771), (344, 3765),
)
RIGHT_PEDAL = (
    (530, 3927), (551, 3930), (562, 3942), (563, 3954),
    (560, 3960), (547, 3970), (525, 3970), (516, 3965),
    (510, 3957), (510, 3941), (518, 3932),
)
BLUE_CHEVRON = (
    (446, 4594), (611, 4817), (611, 4995),
    (447, 4772), (282, 4995), (282, 4814),
)
BLUE_CHEVRON_LENGTH_WIDTH_RATIO = (
    (4995.0 - 4594.0) / (611.0 - 282.0)
)


def create_bicycle_blue_chevron(name="Bicycle Lane Blue Chevron", width=0.50,
                                 blue_material=None):
    """Create only the blue directional chevron, centred and pointing local +Y."""
    if width <= 0:
        raise ValueError("width must be positive")
    if blue_material is None:
        _, blue_material = _paint_materials()
    source_center_x = (282.0 + 611.0) * 0.5
    source_center_y = (4594.0 + 4995.0) * 0.5
    scale = width / (611.0 - 282.0)
    points = tuple(
        ((x - source_center_x) * scale,
         (source_center_y - y) * scale)
        for x, y in BLUE_CHEVRON
    )
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    face = polygon(name + " face", points, ROAD_PAINT_TOP_Z_M, blue_material)
    face.parent = root
    root["asset_type"] = "Bicycle-lane blue directional chevron"
    root["marking_width_m"] = width
    root["marking_length_m"] = width * BLUE_CHEVRON_LENGTH_WIDTH_RATIO
    root["travel_direction"] = "local +Y"
    return root


def _paint_materials():
    white = bpy.data.materials.get("Bicycle lane white thermoplastic")
    if white is None:
        white = road_marking_material(
            "Bicycle lane white thermoplastic",
            (0.56, 0.56, 0.50), (0.91, 0.89, 0.79), (0.16, 0.17, 0.16),
        )
    blue = bpy.data.materials.get("Bicycle lane blue thermoplastic")
    if blue is None:
        # Source paint is #46B1E1. The range adds restrained real-world wear
        # while retaining that cyan-blue identity.
        blue = road_marking_material(
            "Bicycle lane blue thermoplastic",
            (0.035, 0.245, 0.390), (0.275, 0.694, 0.882), (0.035, 0.075, 0.090), 0.76,
        )
    return white, blue


def create_bicycle_lane_marking(name="Bicycle Lane Marking", width=0.50,
                                 white_material=None, blue_material=None):
    """Create the full marking on local XY, centred on X and pointing local +Y."""
    if width <= 0:
        raise ValueError("width must be positive")
    if white_material is None or blue_material is None:
        default_white, default_blue = _paint_materials()
        white_material = white_material or default_white
        blue_material = blue_material or default_blue
    scale = width / REFERENCE_PAINT_WIDTH_PX

    def transformed(points, y_shift=0.0):
        return tuple(
            ((x - REFERENCE_CENTER_X_PX) * scale,
             (REFERENCE_REAR_Y_PX - (y + y_shift)) * scale)
            for x, y in points
        )

    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root["asset_type"] = "Code-native Japanese bicycle-lane marking"
    root["marking_width_m"] = width
    root["marking_length_m"] = REFERENCE_LENGTH_WIDTH_RATIO * width
    root["length_width_ratio"] = REFERENCE_LENGTH_WIDTH_RATIO
    root["travel_direction"] = "local +Y"

    specifications = [
        ("white chevron 1", WHITE_CHEVRON, white_material, 0),
        ("white chevron 2", WHITE_CHEVRON, white_material, 322),
        ("white direction arrow", WHITE_ARROW, white_material, 0),
        ("rider head", RIDER_HEAD, white_material, 0),
        ("rider body and arms", RIDER_BODY_AND_ARMS, white_material, 0),
        ("left handlebar", LEFT_HANDLEBAR, white_material, 0),
        ("right handlebar", RIGHT_HANDLEBAR, white_material, 0),
        ("bicycle fork", BICYCLE_FORK, white_material, 0),
        ("centre hub", CENTRE_HUB, white_material, 0),
        ("left crank", LEFT_CRANK, white_material, 0),
        ("right crank", RIGHT_CRANK, white_material, 0),
        ("front wheel", FRONT_WHEEL, white_material, 0),
        ("left pedal", LEFT_PEDAL, white_material, 0),
        ("right pedal", RIGHT_PEDAL, white_material, 0),
    ]
    for index, shift in enumerate((0, 730, 1465, 2196), 1):
        specifications.append((f"blue chevron {index}", BLUE_CHEVRON, blue_material, shift))

    for label, points, mat, shift in specifications:
        obj = polygon(f"{name} {label}", transformed(points, shift), ROAD_PAINT_TOP_Z_M, mat)
        obj.parent = root
    return root


def _options():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--width", type=float, default=0.50)
    parser.add_argument("--skip-render", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


def _standalone_main():
    options = _options()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    marking = create_bicycle_lane_marking(width=options.width)
    length = marking["marking_length_m"]
    asphalt = weathered_material(
        "Bicycle marking preview asphalt", (0.025, 0.030, 0.032),
        (0.075, 0.082, 0.084), 0.92, 5.0,
    )
    panel_width = max(2.2, options.width * 1.75)
    cube("Preview asphalt lane", (0, length * 0.5, -0.045),
         (panel_width, length + 1.4, 0.09), asphalt)

    world = bpy.data.worlds.new("Bicycle marking preview world")
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.025, 0.03, 0.035, 1)
    background.inputs["Strength"].default_value = 0.28
    bpy.context.scene.world = world
    area_data = bpy.data.lights.new("Even overhead softbox", "AREA")
    area_data.energy = 1100
    area_data.shape = "RECTANGLE"
    area_data.size = length
    area_data.size_y = panel_width * 2
    area = bpy.data.objects.new("Even overhead softbox", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (0, length * 0.5, 8)

    camera_data = bpy.data.cameras.new("Bicycle marking orthographic camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = length + 1.2
    camera = bpy.data.objects.new("Bicycle marking orthographic camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0, length * 0.5, 20)
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 480
    scene.render.resolution_y = 1500
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    asset_root = Path(__file__).resolve().parent.parent
    blend_path = asset_root / "blend/bicycle_lane_marking.blend"
    render_path = asset_root / "renders/bicycle_lane_marking.png"
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    render_path.parent.mkdir(parents=True, exist_ok=True)
    if not options.skip_render:
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(
        f"BICYCLE_MARKING_QA width={options.width:.3f}m length={length:.3f}m "
        f"ratio={REFERENCE_LENGTH_WIDTH_RATIO:.6f} objects={len(marking.children)}"
    )


if __name__ == "__main__":
    _standalone_main()
