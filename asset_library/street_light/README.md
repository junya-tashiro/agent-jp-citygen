# Street lights

## Overview

Code-generated roadway and pedestrian light fixtures.

## Usage

- `create_roadway_streetlight(..., lit=True)`: symmetric fixed-length arms for median placement.
- `create_pedestrian_streetlight(..., lit=True)`: dark green lantern-style fixtures near planting strips.

## Specifications and placement

`lit=False` disables emission and actual lights without changing geometry. Both variants use warm-white light.
Roadway lights use 35 m spacing on roads with medians; pedestrian lights use 23 m spacing near planting strips.
Placement is enabled per road and uses intersection trimming consistent with pedestrian fences, on straight or Bezier sections.
When a pedestrian light conflicts with a street tree, the light is retained and that tree is omitted.

[Back to asset library](../../README.md#asset-library)
