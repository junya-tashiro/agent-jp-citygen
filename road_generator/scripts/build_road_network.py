"""Generic CLI for generating any supported road-network JSON definition."""

import argparse
import sys
import os
import time
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from road_generator.blender.scene import build_scene, setup_lighting_and_cameras
from road_generator.blender.general_scene import build_general_scene
from road_generator.core.planner import (
    plan_bicycle_markings, plan_crosswalks, plan_curb_parking_stripes,
    plan_corner_reflector_poles, plan_guardrails, plan_medians,
    plan_median_island_devices, plan_network,
    plan_pedestrian_countdowns, plan_plantings, plan_signal_blocks, plan_signal_sites,
    plan_stop_lines, plan_street_trees,
    plan_street_lights,
    plan_tactile_paving,
)
from road_generator.core.schema import load_network
from road_generator.core.general import requires_general_geometry


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", type=Path, required=True,
                        help="Road-network JSON, absolute or relative to the repository root")
    parser.add_argument("--output-root", type=Path, required=True,
                        help="Output directory, absolute or relative to the repository root")
    parser.add_argument("--output-name", default="road_network",
                        help="Stem used for the .blend and render filenames")
    parser.add_argument("--render", choices=("none", "preview", "final"), default="preview")
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(args)


def resolve_from_root(path):
    return path if path.is_absolute() else ROOT / path


opts = options()
profile = os.environ.get("ROAD_GENERATOR_PROFILE") == "1"
profile_started = time.perf_counter()
definition = resolve_from_root(opts.definition)
output_root = resolve_from_root(opts.output_root)

network = load_network(definition)
# An explicitly-authored straight segment is still the same geometry as the
# legacy axis-aligned segment.  Keep it on the mature renderer so adding
# ``geometry: {type: line}`` cannot silently replace detailed kerbs, tactile
# tiles or roadside placement with a second implementation.
general_geometry = requires_general_geometry(network)
if general_geometry:
    build_general_scene(ROOT, network)
else:
    plan = plan_network(network)
    crosswalks = plan_crosswalks(network)
    medians = plan_medians(network, crosswalks)
    signal_sites = plan_signal_sites(network, medians)
    signal_blocks = plan_signal_blocks(signal_sites)
    pedestrian_countdowns = plan_pedestrian_countdowns(network)
    stop_lines = plan_stop_lines(crosswalks)
    guardrails = plan_guardrails(network, crosswalks)
    plantings = plan_plantings(network, crosswalks)
    corner_reflector_poles = plan_corner_reflector_poles(network)
    street_trees = plan_street_trees(network, crosswalks)
    street_lights = plan_street_lights(network, crosswalks)
    bicycle_markings = plan_bicycle_markings(network)
    curb_parking_stripes = plan_curb_parking_stripes(network, crosswalks)
    tactile_tiles = plan_tactile_paving(network, crosswalks)
    median_island_devices = plan_median_island_devices(network, medians, signal_sites)
    build_scene(ROOT, network, plan, crosswalks, stop_lines, signal_sites, signal_blocks,
                pedestrian_countdowns, guardrails, plantings, bicycle_markings,
                curb_parking_stripes, street_trees, medians, median_island_devices,
                corner_reflector_poles, tactile_tiles, street_lights=street_lights)
overview, driver = setup_lighting_and_cameras(network)
if profile:
    print(f"PROFILE_SCENE_SECONDS={time.perf_counter() - profile_started:.6f}")

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_percentage = 100
scene.view_settings.look = "AgX - Medium High Contrast"

(output_root / "blend").mkdir(parents=True, exist_ok=True)
(output_root / "renders").mkdir(parents=True, exist_ok=True)

if opts.render != "none":
    if opts.render == "final":
        scene.render.resolution_x = 1600
        scene.render.resolution_y = 1000
        scene.render.image_settings.color_mode = "RGBA"
    else:
        scene.render.resolution_x = 1100
        scene.render.resolution_y = 760
    scene.camera = overview
    scene.render.filepath = str(output_root / f"renders/{opts.output_name}_overview.png")
    bpy.ops.render.render(write_still=True)
    scene.camera = driver
    scene.render.filepath = str(output_root / f"renders/{opts.output_name}_driver.png")
    bpy.ops.render.render(write_still=True)

scene.camera = driver
save_started = time.perf_counter()
bpy.ops.wm.save_as_mainfile(filepath=str(output_root / f"blend/{opts.output_name}.blend"), compress=True)
if profile:
    print(f"PROFILE_SAVE_SECONDS={time.perf_counter() - save_started:.6f}")
