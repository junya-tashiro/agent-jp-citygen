# Planting

## Overview

Shrub-based planting strips for the sidewalk side of roadside fences.
Soil, multi-stem bases, branching twigs, and curved leaves are generated in Python.
Leaf color, veins, and roughness images are also generated from code, with leaf-local UVs and thin-leaf transmission.
Randomness is structured at strip, plant, branch, and leaf levels. Identical seeds and arguments produce identical geometry.

## Usage

```python
create_planting_strip(
    name="Roadside Planting", length=6.0, width=0.85,
    density=0.82, maintenance=0.70, health=0.88, seed=1234,
)
```

- `density`: foliage density, 0–1.
- `maintenance`: uniformity of pruning, 0–1.
- `health`: absence of yellowing and dead foliage, 0–1.
- `seed`: reproducible random seed.

```sh
blender -b --python asset_library/planting/scripts/build_planting.py -- --length 6 --width 0.85 --density 0.82 --maintenance 0.70 --health 0.88 --seed 1234
blender -b --python asset_library/planting/scripts/build_clipped_hedge.py
```

The clipped-hedge script writes `blend/planting_dense_clipped_hedge.blend` and `renders/planting_dense_clipped_hedge.png`.
Use the `clipped_hedge` road style for this variant.
Standalone previews include a fence, road, and sidewalk; the asset returned by `create_planting_strip` does not.

## Specifications and placement

Road integration cuts a planting opening in the sidewalk. Soil is approximately 50 mm below the sidewalk surface.
Fence posts sit on the remaining concrete strip toward the carriageway.
Clipped hedges use branching plants and curved leaves, with twig tips confined to the strip width and an upper band around 0.90 m.

`shrub_growth.py` generates trunks, branches, and shoots, with leaves on and inside the pruning envelope.
Leaves are thick and obovate, with a folded midrib and a curved tip.
`lod="medium"` is the default for close views; `low` reduces leaf counts and subdivisions for road scenes.
Low LOD shares 12 foliage clusters and two plant arrangements while preserving the clipped envelope.
Medium/high assets batch individual curved leaves into meshes.

[Back to asset library](../../README.md#asset-library)
