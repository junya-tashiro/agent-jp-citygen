# Hydrant signs

## Overview

A hydrant location sign with a red pole, circular steel frame, and two red sign faces with white borders.
Both faces display `FIRE HYDRANT` and `消火栓`. Four welded support brackets are visible on one side; an empty auxiliary frame sits below.

## Usage

```sh
blender -b --python asset_library/fire_hydrant_sign/scripts/build_fire_hydrant_sign.py
```

Use `--skip-render` after Blender's `--` separator to save without rendering.
Road generation can import `create_fire_hydrant_sign(...)` directly.

Outputs:

- `blend/fire_hydrant_sign.blend`
- `renders/fire_hydrant_sign_front.png`
- `renders/fire_hydrant_sign_rear.png`

## Specifications and placement

The origin is the pole center at ground level. The front faces local -Y; the opposite face points toward +Y.

[Back to asset library](../../README.md#asset-library)
