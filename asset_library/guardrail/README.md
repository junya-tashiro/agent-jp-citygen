# Pedestrian fences

## Overview

A tubular pedestrian guard fence with three horizontal rails, post caps, front brackets, bolts, and yellow reflective bands.

## Usage

```python
create_guardrail(
    name="Guardrail", length=6.0, exterior_color="white",
    post_spacing=3.0, reflector_bands=True, beam_side="right",
)
```

Standalone generation:

```sh
blender -b --python asset_library/guardrail/scripts/build_guardrail.py -- --length 6 --exterior-color white
```

Road generation calls this API directly without loading an intermediate Blend.

## Specifications and placement

- Height: 800 mm.
- Posts: 60.5 mm diameter.
- Rails: 42.7 mm diameter, centered at heights 265, 535, and 800 mm.
- Standard post spacing: 3,000 mm.
- Paint: `white` or `brown`.

`beam_side` selects the side of the posts carrying the rails and brackets, viewed from the start toward the end.
For roadside placement, face the rails toward the carriageway.

[Back to asset library](../../README.md#asset-library)
