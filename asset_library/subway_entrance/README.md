# Subway entrances

## Overview

Freestanding stair and elevator entrances with stone-like lower walls, glazing, white station signs, and an original entrance symbol.
Geometry is generated from Python.

## Usage

```sh
blender -b --python asset_library/subway_entrance/scripts/build_subway_entrance.py -- --variant stairs --station-name '中央' --station-roman 'Chuo' --route 'M15=#E53935' --width 3 --render preview
```

Use `--variant elevator` for the lift. Rendering modes are `none`, `preview`, and `final`; EEVEE uses 48 preview samples or 96 final samples.
Outputs are `blend/subway_stairs.blend` or `blend/subway_elevator.blend`, plus three views and timing/size JSON in `renders/`.
Regenerating a variant updates its output files.

```python
from asset_library.subway_entrance.scripts.build_subway_entrance import create_subway_entrance
root = create_subway_entrance(
    variant="elevator", station_name="中央", station_roman="Chuo",
    routes=[{"code": "M11", "color": "#E53935"}], width=3.0,
)
root.location = (10, 20, 0.02)
```

Station names are displayed as supplied, without an automatic suffix. Romanized text may be empty.
Long labels are scaled to fit while preserving aspect ratio. Set `CITY_FONT` for Japanese text; lettering is saved as meshes without packing the font.
Identical non-text meshes and materials are shared within a Blender scene.

### Route signs

The front sign and rear stair sign share a white background, original entrance symbol, colored route circles, and bold station labels.
`routes` accepts zero to six codes, either strings such as `['M11']` or dictionaries with `code` and sRGB `#RRGGBB` color.
Omitting routes in the API gives no route labels. The CLI accepts repeated arguments such as `--route 'M15=#E53935' --route 'H07=#9CA5A9'`.
Codes are not inferred from station names. The default CLI sample uses three routes.
`exit_label` is accepted but is not displayed.

### Road integration

Use `context.subway_entrances` in the [road example](../../road_generator/examples/subway_entrances.json).
Position, rotation, and labels belong in input data.

```sh
blender -b --python road_generator/scripts/build_road_network.py -- --definition road_generator/examples/subway_entrances.json --output-root scenes/subway --render none
```

The build samples rays across the body and approach zone to check sidewalk support and obstacles, and rejects overlapping entrance envelopes.
Sampling is not a general collision solver; underground conflicts require separate review.
Stairs cut a Boolean opening only in relevant sidewalk/ground meshes. Change the JSON and regenerate to move an entrance; moving the root alone does not move the excavation.
Elevators replace shallow interior pavement with their own floor and finish, without an underground shaft opening.

Tactile branches leave the main strip at right angles and turn toward the entrance. Straight roads and gentle curves are supported when entrance/main-strip tangent deviation is within 20 degrees.
Selected main-strip tiles become warning tiles; surrounding tiles use the road system's overlap trimming and shared meshes/materials.
Rigid rectangular tiles retain triangular joints at bends. The full path width is checked on the sidewalk, with alternative candidates tried on failure.
If no valid connection exists, no branch is generated and the root's `tactile_connection` records the reason. Arbitrary obstacle-routing is not supported.

## Specifications and placement

Units are metres. The origin is the threshold center at sidewalk height; +Y points inward, -Y outward, and +Z upward.

| Property | Stairs | Elevator |
|---|---:|---:|
| Default width | 3.0 | 3.0 |
| Above-ground length | 6.6 | 3.2 |
| Above-ground height | About 2.9 | About 3.68 |
| Reserved approach length | 2.0 | 2.0 |
| Underground geometry | 15 steps, 0.16 rise, 0.30 run, 2.4 depth | None |
| Underground endpoint | Local Y = 8.45 | — |

Width range is 2.6–4.0 m, including walls and roof, not clear handrail spacing.
Elevator doors are approximately 1.3 m wide regardless of overall width. There are no side signs.
Stairs include continuous handrails, nosings, drainage, 300 mm tactile tiles, roof framing, glazing, gutters, downpipes, and lights.
The elevator is a static closed-door model.

`root['spec_json']` stores the body, approach, underground envelope, opening, and pavement replacement extents.
`pavement_cutout` begins ahead of `opening` to replace the upper landing as well.
The asset and `Preview Environment` are separate.

### Finishes

`weathering` ranges from 0 to 1, default 0.18; it is also available as `--weathering` and a road JSON field.
The model includes swept handrails, roof slope and drains, glazing beads and seals, stepped door frames, and lights.
The elevator enclosure and six-sided car are separate, with closely spaced landing and car doors.
Front glazing sits above a concrete-like lower wall. Exterior call buttons and interior controls are modeled independently.
Dimensions are model parameters, not certified construction specifications.

## Validation

`check_api.py` generates models to check label fitting, widths, and mesh sharing.
Run `check_realism.py` on a generated road scene containing both variants and tactile connections.
It invokes joint, enclosure, double-door, tactile-connection, and coplanar-surface checks.

[Back to asset library](../../README.md#asset-library)
