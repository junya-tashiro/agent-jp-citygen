"""Code-native Japanese lane-use arrows with measured five-metre outlines."""

import argparse
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from road_generator.blender.primitives import (
    ROAD_PAINT_TOP_Z_M, cube, polygon, road_marking_material,
    weathered_material,
)


STRAIGHT = (
    (-0.10, -5.00), (0.10, -5.00), (0.10, -2.50),
    (0.28, -2.50), (0.0, 0.0), (-0.28, -2.50),
    (-0.10, -2.50),
)

# Local +Y is forward. The 2.20 m dimension belongs to the arrowhead's
# longitudinal span, while its lateral tip projects 0.40 m beyond the base.
TURN_SHAFT = ((-0.09, -5.0), (0.09, -5.0),
              (0.09, -1.25), (-0.09, -1.25))
TURN_HEAD = ((0.26, 0.0), (0.66, -1.10), (0.26, -2.20))
TURN_SHOULDER = (
    (0.26, -0.90), (0.00, -0.90), (-0.04, -0.93),
    (-0.08, -0.99), (-0.09, -1.08), (-0.09, -1.25),
    (-0.07, -1.35), (-0.04, -1.42), (0.00, -1.45),
    (0.26, -1.45),
)
RIGHT_PARTS = (TURN_SHAFT, TURN_HEAD, TURN_SHOULDER)


def _mirror(points):
    return tuple((-x, y) for x, y in reversed(points))


def _shift(points, x=0.0, y=0.0):
    return tuple((px + x, py + y) for px, py in points)


COMBINED_BRANCH_SHIFT_Y = -2.65
RIGHT_BRANCH_PARTS = tuple(
    _shift(part, y=COMBINED_BRANCH_SHIFT_Y)
    for part in (TURN_HEAD, TURN_SHOULDER)
)


PARTS_BY_KIND = {
    "straight": (STRAIGHT,),
    "left": tuple(_mirror(part) for part in RIGHT_PARTS),
    "right": RIGHT_PARTS,
    "left_straight": (
        STRAIGHT, *(_mirror(part) for part in RIGHT_BRANCH_PARTS)),
    "straight_right": (STRAIGHT, *RIGHT_BRANCH_PARTS),
}


def create_lane_use_arrow(name="Lane-use arrow", kind="straight", material=None):
    """Create a shared arrow pointing local +Y with its front at the origin."""
    if kind not in PARTS_BY_KIND:
        raise ValueError(f"Unsupported lane-use arrow kind: {kind}")
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root["asset_type"] = "Japanese lane-use road marking"
    root["kind"] = kind
    root["length_m"] = 5.0
    root["travel_direction"] = "local +Y"
    root["front_anchor"] = "local origin"
    for index, points in enumerate(PARTS_BY_KIND[kind], 1):
        item = polygon(f"{name} part {index}", points,
                       ROAD_PAINT_TOP_Z_M, material)
        item.parent = root
    return root


def _standalone_main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--kind", choices=tuple(PARTS_BY_KIND), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    white = road_marking_material(
        "Lane-use arrow white thermoplastic",
        (0.56, 0.56, 0.50), (0.91, 0.89, 0.79), (0.16, 0.17, 0.16),
    )
    asphalt = weathered_material(
        "Arrow preview asphalt", (0.025, 0.030, 0.032),
        (0.075, 0.082, 0.084), 0.92, 5.0,
    )
    create_lane_use_arrow(f"{args.kind} lane-use arrow", args.kind, white)
    cube("Preview road", (0.0, -2.5, -0.05), (6.5, 6.5, 0.10), asphalt, 0.02)

    camera_data = bpy.data.cameras.new("Top camera")
    camera = bpy.data.objects.new("Top camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, -2.5, 10.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 6.4
    bpy.context.scene.camera = camera

    world = bpy.data.worlds.new("Arrow preview world")
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes
                      if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (
        0.08, 0.08, 0.08, 1.0)
    background.inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"

    render_dir = args.output_root / "renders"
    blend_dir = args.output_root / "blend"
    render_dir.mkdir(parents=True, exist_ok=True)
    blend_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(render_dir / f"lane_use_arrow_{args.kind}.png")
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(blend_dir / f"lane_use_arrow_{args.kind}.blend"))


if __name__ == "__main__":
    _standalone_main()
