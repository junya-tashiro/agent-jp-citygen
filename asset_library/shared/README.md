# Shared components

## Overview

`surfaces.py` provides metric PBR asphalt, coated metal, galvanized metal,
aluminum, reflective sheeting and signal optics. It contains no placement or
scene logic. Shader detail adds no geometry; images are reused and packed once
per build. No runtime network access or add-on installation is required.

## Materials and textures

`aggregate.py` generates asphalt from two populations of irregular mineral
grains, binder and recessed boundaries. Color, roughness and height share the
same occupancy field. Nominal cell spacings are 4.2 and 9.5 mm; these are shader
parameters, not a certified pavement mix specification. No scanned images are
loaded. Japanese lettering uses the configured local font.

Road surfaces use world-space metres so painted marks share the underlying
aggregate. Tree bark is generated in `street_tree/scripts/bark.py` without images.
Coatings use an opaque
dielectric over metal; signal lenses use a distinct optical finish. Reflective
sheeting is an EEVEE surface approximation, not a measured retroreflection BSDF.

The road shader evaluates aggregate in world XY, so paint height does not shift
the underlying grains. `fractures.py` creates
a seamless field of seeded, branching and interrupted cracks, continuously warped
in world space so its 24 m source tile does not repeat regularly.
Marking chips expose the same asphalt color, roughness and height field in an
opaque shader: no alpha overdraw, and no separate geometric holes at 1.5 mm scale.
`foliage.py` batches folded leaf blades with leaf-local UVs using NumPy buffers.

## Vegetation sharing

Road vegetation uses `leaf_clusters.py` for low LOD: twelve deterministic,
opaque leafy branch/stock prototypes per species are instanced through a single
Geometry Nodes modifier per foliage object. Prototypes come from a fixed reference
seed, so generation order cannot change the result. Each cluster fits its original
blade envelope; vertical bounds are preserved. Medium/high LOD retain batched
individual blades. Instances are not realised in the delivered road scene.

`asphalt_repair_material()` uses the carriageway's generated aggregate at the same
world scale, roughness and bump depth. A restrained darker tint and omission of
old cracks distinguish reinstatement without introducing a smooth foreign patch.

[Back to asset library](../../README.md#asset-library)
