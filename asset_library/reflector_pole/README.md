# Reflector poles

## Overview

A flexible delineator with a red resin body, three white reflective bands, and a black base. Geometry and materials are generated from code.

## Usage

Call from Blender Python:

```python
from asset_library.reflector_pole.scripts.build_reflector_pole import create_reflector_pole
root = create_reflector_pole(name="Reflector Pole", location=(0, 0, 0), rotation_degrees=0.0)
```

## Specifications and placement

Height is approximately 0.80 m. Units are metres; the origin is the base center at ground level, with Z up.
`location` and `rotation_degrees` control placement and rotation around Z.

[Back to asset library](../../README.md#asset-library)
