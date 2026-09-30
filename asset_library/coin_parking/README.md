# Surface parking

## Overview

A small urban parking lot whose bay count and layout are derived from width and depth.
It uses generic equipment, signs, and pricing rather than reproducing an operator's branding.

## Usage

```sh
blender -b --python asset_library/coin_parking/scripts/build_coin_parking.py -- --width 18 --depth 24 --output scenes/parking --render final --views overview,top
```

Dimensions are in metres; defaults are 13.2 × 17 m. Rendering modes are `none`, `preview`, and `final`.
Views are `overview`, `top`, `entrance`, `payment`, and `lock`.
Preview uses 1100 × 825 with 24 samples; final uses 1400 × 1050 with 64 samples, both in EEVEE.
Outputs are `blend/coin_parking.blend`, `renders/*.png`, and `metrics.json`.
No additional Python packages, MCP server, or runtime network access are needed.

```python
from asset_library.coin_parking.scripts.build_coin_parking import build_asset
asset_collection, layout = build_asset(width=18, depth=24)
```

The asset collection is `COIN PARKING | rectangular flap lot`.
Standalone context is a separate collection, `CONTEXT | sidewalk crossover and street`.

### Road connection

```python
from road_generator.blender.parking import attach_parking_to_driveway
root, layout = attach_parking_to_driveway(network, "driveway_1", 12, 18)
```

Position and rotation follow the driveway component's side/station and the road cross-section.
The entrance meets the outer sidewalk edge at Z = 0.02 m.
Curved frontage is set back as needed and joined with an 80 mm thick asphalt apron, sampled approximately every 0.25 m.
Straight frontage needs no extra setback or apron. Tight folds and sites extending past the road end raise errors.
The caller is responsible for collisions with neighboring sites and buildings.

## Specifications and placement

### Layout

Local X spans zero to width, Y spans zero to depth, and Z = 0 is the site surface. The road-facing side is -Y.
Entrance center is `(layout.entrance_x, 0, 0)` and width is `layout.entrance_width`; these are also stored as collection properties.
Standalone context places the site and sidewalk at Z = 0 and the carriageway at Z = -0.13 m.

`layout.py` plans without Blender. Bays are 2.5 × 5.0 m; aisles are at least 5.5 m wide.
It chooses the highest-capacity feasible rear row, single side row, or double side row, preferring a rear row on ties.
Longitudinal rows retain at least 1.5 m end clearance. Invalid rectangles raise errors rather than shrinking bays or aisles.
Some valid layouts start at 7.2 × 12.9 m or 11.3 × 6.0 m. These are scenery constraints, not vehicle swept-path certification.

| Dimensions | Bays | Layout |
|---|---:|---|
| 9 × 13 m | 3 | Rear row |
| 12 × 18 m | 5 | Single side row |
| 25 × 13 m | 9 | Rear row |
| 18 × 24 m | 16 | Double side row |

### Geometry and materials

- Each bay has a lowered locking flap with motor housing, axle, grip, sensor, and anchors, plus a concrete wheel stop.
- One payment machine has a keypad, display, coin/note slots, receipt and change outlets, instructions, door hardware, and conduit.
- Japanese text uses `CITY_FONT`; ASCII uses Blender's built-in font. Text receives a bevel of 0.8% of its size and is converted to meshes; font binaries are not packed.
- Orange tubular fences can replace adjacent pairs with two cones and a black/yellow bar at 15% probability, using a dimension-derived seed and nonoverlapping selection.
- Cones are 721 mm high, with 380 mm square weights, 236.34 mm body diameter at 90 mm height, 57 mm tips, 40 mm holes, and three white bands. Bars are about 2 m long, 34 mm in diameter, with 78 mm inner rings.
- The vehicle entrance is 4.2 m wide. A pedestrian opening remains in front of the payment machine.
- Shared metric asphalt, cracks, worn paint, bay numbers, and detector-loop cuts form the pavement.
- Flap motor housings are centered on each bay's left marking. The exit stop line is 2.6 × 0.20 m, offset to the right when viewed from the road.
- The double-sided parking sign is 1.18 × 1.25 m, opposite the payment machine, with its pole 0.30 m from the entrance edge and its face aligned with road travel. The rate board is 1.90 × 1.46 m.
- Equipment prototypes and materials are shared across bays; fences and signs have restrained streaking.

## Validation

```sh
python3 -m unittest discover -s asset_library/coin_parking/tests -v
```

[Back to asset library](../../README.md#asset-library)
