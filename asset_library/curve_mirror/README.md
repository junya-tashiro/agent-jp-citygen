# Traffic mirrors

## Overview

Procedurally generated convex roadside mirrors with mounting hardware, a pole, and a caution board.

## Usage

Generate one mirror:

```sh
blender -b --python asset_library/curve_mirror/scripts/build_curve_mirror.py
```

Generate two mirrors:

```sh
blender -b --python asset_library/curve_mirror/scripts/build_curve_mirror.py -- --mirror-count 2 --spread-degrees 24
```

| Option | Meaning |
|---|---|
| `--mirror-count 1\|2` | Number of mirrors |
| `--spread-degrees N` | Total outward angle of the double-mirror arrangement |
| `--pole-length N` | Visible pole length in metres; default 2.5 |

## Specifications and placement

Mirror and caution-board heights use fixed offsets from the pole top, so changing pole length moves both together.
The mirror and mounting components are separate from the preview environment.

Typical outputs include `blend/curve_mirror_1mirror_pole2.5m.blend`,
`blend/curve_mirror_2mirror_spread24_pole2.5m.blend`, and front, rear, and caution-board views in `renders/`.

[Back to asset library](../../README.md#asset-library)
