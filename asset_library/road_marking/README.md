# Road markings

## Overview

Code-generated bicycle-lane markings and lane-direction arrows. No image textures are required.

## Usage

```python
create_bicycle_lane_marking(name="Bicycle Lane Marking", width=0.50)
```

Standalone bicycle-marking generation:

```sh
blender -b --python asset_library/road_marking/scripts/build_bicycle_lane_marking.py
```

In a road network, `bicycle_lane: true` enables automatic placement in both directions.
Lane-direction arrow generation is implemented in `scripts/build_lane_use_arrow.py`.

## Specifications and placement

For bicycle markings, local +Y is the direction of travel; the origin is the center of the rear end of the painted strip.
Default width is 0.50 m, and the painted extent has an aspect ratio of 14.579088:1.
The pattern includes two white chevrons, a white arrow, a front-facing bicycle pictogram, and four blue chevrons.
Outlines and proportions are numeric definitions in the script.
The paint is 1.5 mm thick and sits directly on the asphalt surface.

[Back to asset library](../../README.md#asset-library)
