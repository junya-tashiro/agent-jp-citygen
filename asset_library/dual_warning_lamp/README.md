# Warning lamps

## Overview

A vertical two-lamp amber warning fixture with a metal housing, deep semicircular visors, retaining rings, and rear mounting hardware.
The lenses are non-emissive and have no LED dot array. Housing and pole use a low-gloss brown finish.

## Usage

```python
from asset_library.dual_warning_lamp.scripts.build_dual_warning_lamp import create_dual_warning_lamp
create_dual_warning_lamp(name="Median warning lamp", location=(0, 0, 0), rotation_degrees=90)
```

Generate a standalone Blend without rendering:

```sh
blender -b --python asset_library/dual_warning_lamp/scripts/build_dual_warning_lamp.py
```

## Specifications and placement

The origin is the pole center at ground level; the front faces local -Y.
Default housing dimensions are 0.143 m wide, 0.328 m high, and 0.086 m deep.
The exposed pole is approximately 0.318 m long; total height is approximately 0.63 m.
The exterior color is brown. No external textures or assets are required.

[Back to asset library](../../README.md#asset-library)
