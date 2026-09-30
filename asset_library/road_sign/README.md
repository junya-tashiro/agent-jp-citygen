# Road signs

## Overview

Reusable Japanese road signs with thin aluminium plates, reflective texture
faces, pale galvanized poles, rear ribs, standoffs and U-band fittings.

## Usage

### Standalone generation

From the project root:

```sh
/Applications/Blender.app/Contents/MacOS/blender -b \
  --python asset_library/road_sign/scripts/build_road_sign_samples.py
```

Outputs:

- `blend/road_sign_samples.blend`
- `renders/road_sign_samples.png`

To add another sign, define its named coordinate paths, add a procedural face builder,
and register its metric dimensions in `SIGN_SPECS`.

### Scene placement

Because this file is also a multi-sign sample, each collection retains the
`Source X` position listed below. Subtract that value when placing an instance:

```python
import bpy

blend_path = "asset_library/road_sign/blend/road_sign_samples.blend"
collection_name = "止まれ＋横断歩道"
source_center_x = -0.75
target = (-3.92, 11.8, 0.0)

with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
    dst.collections = [collection_name]

instance = bpy.data.objects.new(f"{collection_name} instance", None)
instance.instance_type = "COLLECTION"
instance.instance_collection = dst.collections[0]
instance.location = (target[0] - source_center_x, target[1], target[2])
bpy.context.scene.collection.objects.link(instance)
```

`target` represents the desired pole centre at ground level. Rotate the instance
around Z to change the direction the sign faces.

## Specifications and placement

The generated `blend/road_sign_samples.blend` contains one collection per asset:

| Collection | Faces | Source X | Notes |
|---|---:|---:|---|
| `横断歩道 単体` | Pedestrian crossing | -2.25 m | Separate plate, figure, and crossing-stripe vector parts |
| `止まれ＋横断歩道` | Stop and pedestrian crossing | -0.75 m | Two faces stacked on one pole |
| `止まれ＋指定方向外進行禁止（左折）` | Stop and mandatory left turn | 0.75 m | Shared pole with a circular sign |
| `駐車禁止 単体` | No parking | 2.25 m | Blue face, red ring and slash, narrow white border |

All poles are 3.0 m high. `止まれ` is 0.42 m high and `横断歩道` is 0.60 m high.
The no-parking and mandatory-left-turn signs are both 0.45 m in diameter.
Both faces are assembled from named coordinate paths. Plate outlines, borders,
Japanese glyphs, the pedestrian and individual crossing stripes remain independently
readable in Python and are converted directly into aluminium and reflective meshes.

`create_road_sign(sign_type, ...)` creates one face. To share one pole between several
faces, use `create_road_sign_stack(("止まれ", "横断歩道"), ...)`; the tuple is ordered
top-to-bottom. Each face retains its own rear ribs, standoffs and U-bands while the pole
is generated exactly once.

`create_keep_left_sign()` builds a median-mounted keep-left arrow from a blue circle, white border, and vector arrow.
The face is 0.45 m in diameter and the pole is 1.48 m high.
Face it toward the intersection, with blue space between the arrow and border. The pole uses a pale, low-gloss galvanized finish.

[Back to asset library](../../README.md#asset-library)
