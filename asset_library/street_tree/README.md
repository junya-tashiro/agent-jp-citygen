# Street trees

## Overview

Procedural deciduous trees with generated bark and leaf materials.

- `keyaki`: upward-branching, spreading crown.
- `ginkgo`: narrow conical crown with a main trunk and short branches.
- `cherry`: broad lateral branches beginning lower on the trunk.

## Usage

```python
create_street_tree(name="Street Tree", species="keyaki", seed=1234,
                   lod="medium", individual_variation=0.10)
```

Optional dimensions: `height`, `crown_width`, `crown_start_height`, and `trunk_diameter`.
`lod` is `low`, `medium`, or `high`. `individual_variation` ranges from 0 to 0.30 and correlates changes in height, crown width, trunk diameter, and pruning height.
A value of zero uses the species' reference dimensions.

```sh
blender -b --python asset_library/street_tree/scripts/build_street_tree.py -- --render preview
blender -b --python asset_library/street_tree/scripts/build_street_tree.py -- --render none
blender -b --python asset_library/street_tree/scripts/build_street_tree.py -- --scene variation-row --species keyaki --count 10 --render preview
```

Road scenes call the Python API directly; generated Blend files are not required inputs.

## Specifications and placement

Trunks have low-frequency bends and noncircular cross-sections. Primary branches taper through secondary branches to leaf-bearing shoots.
`growth.py` distributes leaves inside the crown as well as on the surface. Trunks/branches and leaves are batched instead of creating one object per element.
Regular curved leaves use 17 vertices; road low-LOD leaves use eight. Ginkgo leaves are fan-shaped with a central notch.
Low LOD preserves primary branches while reducing leaf counts and subdivisions.

### Materials

`scripts/bark.py` creates peeling plates, lenticels, or longitudinal grooves according to species, without images.
Metric `bark_position_m` and `bark_radius_m` attributes allow thinner branches to transition to smoother bark.
Leaf color, veins, and roughness are generated at 256 × 256, shared, and packed in the Blend.
Leaves use local UVs, curved geometry, different front/back colors, and thin-leaf transmission.

### Sharing

Road low LOD combines five skeletons and 12 foliage clusters per species, with directional pruning variation and some young trees.
Clusters use Geometry Nodes instances without realization into separate per-tree meshes.
A seed's result does not depend on the order in which other trees are generated.

[Back to asset library](../../README.md#asset-library)
