# Vehicle signals

## Overview

Reusable Japanese horizontal vehicle signal with three 250 mm LED aspects,
rounded pale housing, attached visors, concrete support pole, twin cantilever
pipes, mounting hardware, junction box and restrained cable runs.

## Usage

### Build options

```sh
/Applications/Blender.app/Contents/MacOS/blender -b \
  --python asset_library/traffic_signal/scripts/build_traffic_signal.py -- \
  --main-light red \
  --arrow-blocks right \
  --active-arrows right \
  --exterior-color brown \
  --intersection-name "中 央" \
  --intersection-roman "Chuo" \
  --horizontal-extension 3.25
```

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--main-light` | `green`, `yellow`, `red`, `none` | `red` | Illuminated main aspect |
| `--arrow-blocks` | `none`, `right`, `all` | `right` | Install no arrow blocks, only the right block, or all three blocks |
| `--active-arrows` | comma-separated `left,up,right`, or `none` | `right` | Arrow LEDs to illuminate |
| `--exterior-color` | `white`, `brown` | `white` | Exterior finish for the housing, pole, support arms and hardware |
| `--skip-render` | flag | off | Save the `.blend` without rendering previews |
| `--intersection-name` | any string | Specify explicitly | Japanese text, including spaces exactly as supplied |
| `--intersection-roman` | any string | Specify explicitly | Romanized text |
| `--horizontal-extension` | non-negative metres | `1.5` | Add reach between the support pole and the signal head; the name board moves with the head. The road generator uses `1.5m + lane_width × (lanes_each_way - 1) / 2` |
| `--support-side` | `left`, `right` | `left` | Pole side viewed by approaching traffic; right-side supports do not mirror the head, aspects, or lettering |

If both `--intersection-name ""` and `--intersection-roman ""` are empty, the entire name-board assembly is omitted, including its border, text, and rear clamps. Output names include `_no_name_plate`.

Examples:

```sh
# Right arrow block installed; red and right arrow illuminated
/Applications/Blender.app/Contents/MacOS/blender -b \
  --python asset_library/traffic_signal/scripts/build_traffic_signal.py -- \
  --main-light red --arrow-blocks right --active-arrows right

# All arrow blocks installed; left and up arrows illuminated
/Applications/Blender.app/Contents/MacOS/blender -b \
  --python asset_library/traffic_signal/scripts/build_traffic_signal.py -- \
  --main-light green --arrow-blocks all --active-arrows left,up
```

### Outputs

Right-block builds use the base filenames; all-block builds add `_arrows_all`:

- `blend/traffic_signal_vehicle_horizontal.blend`
- `blend/traffic_signal_vehicle_horizontal_arrows_all.blend`
- matching overall, detail and rear previews in `renders/`

Brown-finish builds add `_brown` before any arrow suffix, for example:

- `blend/traffic_signal_vehicle_horizontal_brown.blend`
- `blend/traffic_signal_vehicle_horizontal_brown_arrows_all.blend`

Builds without arrow blocks add `_no_arrows`:

- `blend/traffic_signal_vehicle_horizontal_no_arrows.blend`
- `blend/traffic_signal_vehicle_horizontal_no_arrows_no_name_plate.blend`

The `.blend` separates reusable and preview content:

- `Traffic Signal Asset` — collection to import into another scene
- `Traffic Signal Asset Root` — parent controlling the entire asset
- `Preview Environment` — camera, lighting and preview ground; do not import it

### Scene placement

```python
import bpy

blend_path = "asset_library/traffic_signal/blend/traffic_signal_vehicle_horizontal.blend"
collection_name = "Traffic Signal Asset"

with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
    if collection_name not in src.collections:
        raise ValueError(f"Missing collection: {collection_name}")
    dst.collections = [collection_name]

instance = bpy.data.objects.new("Vehicle traffic signal instance", None)
instance.instance_type = "COLLECTION"
instance.instance_collection = dst.collections[0]
instance.location = (-3.92, 6.4, 0.0)
instance.rotation_euler[2] = 0.0
bpy.context.scene.collection.objects.link(instance)
```

Move or rotate only the instance (or `Traffic Signal Asset Root` when working
inside the source file) to preserve all physical connections.

See the city examples in `examples/city/` for road-network integration.

## Specifications and placement

### Components

It can also include configurable arrow blocks and a bilingual intersection-name
board.

### Origin and orientation

The asset root is at the support-pole centre on ground level: `(0, 0, 0)`.
The cantilever pipes and signal head extend mainly along local `+X`. The front of
the signal faces local `-Y`.

`support_side="right"` moves the support pipes to local -X. Heads, arrows, and lettering keep their orientation and are translated rather than mirrored.

For a road running along Y, place the pole just outside the left road edge and
leave rotation at zero. The head will then project over the road and face traffic
approaching from negative Y.

[Back to asset library](../../README.md#asset-library)
