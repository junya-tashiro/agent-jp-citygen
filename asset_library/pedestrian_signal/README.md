# Pedestrian signals

## Overview

Vertical pedestrian signals with a standing red figure, a walking blue figure, and optional eight-step countdown bars beside the unlit aspect.
White and brown exterior finishes are supported. A separate pedestrian-phase sign is not included.

## Usage

```sh
blender -b --python asset_library/pedestrian_signal/scripts/build_pedestrian_signal.py -- --active-light red --countdown on --countdown-level 6 --exterior-color brown
```

| Argument | Values | Default | Meaning |
|---|---|---|---|
| `--active-light` | `red`, `blue` | `red` | Illuminated figure |
| `--countdown` | `on`, `off` | `on` | Bars beside the unlit aspect |
| `--countdown-level` | 0–8 | 8 | Remaining bars; decreasing the value removes bars from the top |
| `--exterior-color` | `white`, `brown` | `white` | Housing and support finish |
| `--support-side` | `left`, `right` | `left` | Side to which the head extends when viewed from the front |
| `--skip-render` | flag | off | Save without previews |

Countdown level has no visual effect when countdown is off.
Outputs go to `blend/` and `renders/`, with configuration-based names such as `pedestrian_signal_red_brown_countdown6.blend`.
The reusable `Pedestrian Signal Asset` and `Preview Environment` are separate.

## Specifications and placement

The origin is the pole center at ground level. Pole height is 4.8 m, with radius and finish shared with vehicle signals.
Two support pipes curve vertically behind the head. The front faces local -Y; front-view left is local +X.
Changing support side moves the head and pipe path without mirroring figures, door hardware, or visors.
White uses pale concrete and galvanized supports; brown paints the supports dark brown.

The housing is 380 mm wide, 700 mm high, and 140 mm deep; display windows are approximately 250 mm square.
Figures are generated as meshes from fixed row-and-interval masks in the script.

[Back to asset library](../../README.md#asset-library)
