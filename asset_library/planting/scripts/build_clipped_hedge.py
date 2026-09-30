"""Dense, box-clipped Japanese roadside hedge asset."""

import argparse
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asset_library.guardrail.scripts import build_guardrail  # noqa: E402
from asset_library.planting.scripts import build_planting as base  # noqa: E402


def create_clipped_hedge(name="Dense Clipped Roadside Hedge", length=6.0,
                         width=0.85, density=0.94, maintenance=0.92,
                         health=0.90, seed=173304, lod="medium"):
    from asset_library.planting.scripts.shrub_growth import create_shrubs
    return create_shrubs(name, length, width, density, maintenance, health, seed,
                         clipped=True, lod=lod)


def _look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def _standalone_main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--length", type=float, default=6.0)
    parser.add_argument("--width", type=float, default=0.85)
    parser.add_argument("--seed", type=int, default=173304)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    hedge = create_clipped_hedge(length=args.length, width=args.width, seed=args.seed)
    hedge.location.z = 0.07
    guardrail = build_guardrail.create_guardrail(
        "Preview white guardrail", args.length, "white", beam_side="right")
    guardrail.location = (0, -args.width * 0.5 - 0.11, 0.18)

    ground = base._material("Preview neutral ground", (0.30, 0.31, 0.29), 0.90, 0.08)
    base._cube("Preview ground", (args.length * 0.5, 0.45, -0.035),
               (args.length + 1.5, 3.0, 0.07), ground)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world = bpy.data.worlds.new("Clipped hedge preview world")
    scene.world.use_nodes = True
    background = next(node for node in scene.world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.16, 0.19, 0.22, 1.0)
    background.inputs["Strength"].default_value = 0.42

    sun_data = bpy.data.lights.new("Soft sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Soft sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-28))
    area_data = bpy.data.lights.new("Hedge fill", "AREA")
    area_data.energy = 480
    area_data.size = 6.0
    area = bpy.data.objects.new("Hedge fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (args.length * 0.45, -3.5, 4.5)
    _look_at(area, (args.length * 0.5, 0, 0.45))

    camera_data = bpy.data.cameras.new("Clipped hedge camera")
    camera = bpy.data.objects.new("Clipped hedge camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (args.length * 0.08, -5.2, 1.65)
    camera_data.lens = 55
    _look_at(camera, (args.length * 0.54, 0.0, 0.48))
    scene.camera = camera

    asset_root = Path(__file__).resolve().parent.parent
    blend_path = asset_root / "blend/planting_dense_clipped_hedge.blend"
    render_path = asset_root / "renders/planting_dense_clipped_hedge.png"
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    render_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.skip_render:
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"CLIPPED_HEDGE_QA leaves={hedge['leaf_count']} branches={hedge['branch_count']} seed={args.seed}")


if __name__ == "__main__":
    _standalone_main()
