# Buildings

## Overview

Twenty-six original prototypes for Japanese-style urban scenery.
Use the root `city.py` CLI and [scene format](../../docs/SCENE_FORMAT.md) for complete cities.
This reference covers the standalone API, design parameters, and generation methods.

## Usage

### Standalone generation

```sh
blender -b --python asset_library/building/scripts/build_buildings.py -- --kind all
```

Use `--kind building_06` for one prototype, a comma-separated list for several, and `--no-render` to save without images.
Outputs go to `blend/` and `renders/`. Rendering uses EEVEE.

```python
from asset_library.building.scripts.build_buildings import create_building
root = create_building('building_06', seed=11, detail='high')
root.location = (10, 20, 0)
```

The origin is the site center at ground level; the front faces -Y. Asset geometry is parented to the returned root.
Preview ground, roads, and lighting are separate objects.

### Parametric designs

Prototypes 01–10 have authored compositions. Prototypes 11–26 are planned by `design.py` and assembled by `recipe_builder.py`.
Their seeds vary massing, setbacks, curvature, facades, lower floors, and roofs.

```python
root = create_building('building_11', seed=20260906, design={
    'width': 48, 'depth': 34, 'floors': 38, 'corner_radius': 4.5,
})
```

`design` overrides are supported by prototypes 11–26. Unspecified values are seeded; incompatible facades and invalid dimensions raise errors.
Plans are stored in `root['design_json']`, with structural signatures in `root['design_signature']`.
Medium detail preserves silhouettes and floor structure while reducing fine joints and blinds.
Typical floors share meshes by material; upper glass uses an opaque reflective approximation, while lower floors use transparent glass and interiors.

### Batch selection

```python
from asset_library.building.scripts.design import plan_district
for plan in plan_district(100, seed=42):
    root = create_building(plan.key, seed=plan.seed, detail='medium',
                           design={'tower_form': plan.tower_form,
                                   'ground_mode': plan.ground_mode})
    # Assign a site position to root.location.
```

This API selects buildings; road-aware site placement is handled separately by the city planner.

## Specifications and placement

### Prototypes

Keys are `building_01` through `building_26`. Descriptions below identify representative compositions; seeded families vary dimensions and floor counts.

| Key | Composition |
|---|---|
| `building_01` | 34-floor tower with vertical fins and a colonnaded base |
| `building_02` | 30-floor stone-grid tower with two setbacks |
| `building_03` | Two unequal towers, up to 38 floor equivalents, over a retail podium |
| `building_04` | 27-floor chamfered tower with large metal frames and two-level shops |
| `building_05` | Wide eight-floor office with a rooftop pergola |
| `building_06` | Narrow ten-floor glass frontage and vertical core |
| `building_07` | Nine-floor tiled facade with punched windows and upper setbacks |
| `building_08` | Nine-floor corner building with ribbon windows and a recessed top |
| `building_09` | Eight-floor building with deep balconies and vertical glazing |
| `building_10` | Seven-floor brick building with bracing and shop fronts |
| `building_11` | Rounded tower with an offset crown, bands, mullions, and a broad canopy |
| `building_12` | Rounded, stepped stone-and-glass tower |
| `building_13` | Offset paired masses, deep vertical gap, and connecting bridge |
| `building_14` | Asymmetric volumes with multiple elevated terraces |
| `building_15` | Rounded ribbon windows and recessed penthouse |
| `building_16` | Folded glass facade with recessed mullions |
| `building_17` | External columns, beams, and braces with large workshop windows |
| `building_18` | Vertical ceramic screens and upper setbacks |
| `building_19` | Deep stone arcades and recessed office windows |
| `building_20` | Three garden terraces, balconies, and shaded lower floors |
| `building_21` | Rounded tower over a wide retail podium; reference footprint 82 × 57 m |
| `building_22` | Large floor plates and a garden terrace; reference footprint 72 × 60 m |
| `building_23` | Narrow steel-frame tenant building; reference footprint 7.2 × 17 m |
| `building_24` | Narrow ceramic facade; reference footprint 6.8 × 15 m |
| `building_25` | Tower with a raised forecourt and underground parking entrance |
| `building_26` | Tenant building with a ground-floor convenience store |

### Design parameters

| Parameter | Meaning |
|---|---|
| `width`, `depth` | Building dimensions in metres, 6–100 |
| `floors` | Structural floor equivalents, including the height of atria |
| `corner_radius` | Tower corner radius |
| `base_style`, `facade`, `roof_style` | Compatible lower-floor, facade, and roof treatments |
| `base_floors` | Lower-floor height in floor equivalents, 1–4 |
| `base_program` | Lower-floor composition, including `gallery`, `colonnade`, `terrace`, or narrow `split_shop` |
| `terrace_depth` | Outdoor terrace depth in metres |
| `interior_program` | `business`, `hospitality`, `cafe`, `gallery`, or `convenience` |
| `tower_form` | `straight`, `stepped`, or `paired` |
| `plan_shape` | `rectangle`, `cross`, `chamfer`, or `core_wing` |
| `vertical_style` | `none`, `piers`, or `paired_fins` |
| `sky_floor` | Zero-based floor above the base with 1.8× normal height; -1 disables it |
| `podium_radius` | Podium corner radius, independent of the tower |
| `ground_mode` | `continuous` or `lobby` |
| `atrium` | Open lower-floor volume; default true for towers |
| `parking` | Underground parking entrance and raised site |
| `site_height` | Raised site height, 1.2–2.4 m |
| `parking_side` | `left` or `right` |

Tower podiums can span two to four floor equivalents without intermediate floors, ceilings, or upper-level furniture.
Only outdoor terraces retain their floors. Ground-floor height is 5.4 m for towers and 4.5 m for retail mid-rise bases; continuous facades use the normal floor height.
Terraces require at least two lower-floor equivalents and 2 m depth. Upper masses are transformed together to retain support.
Stepped masses use rectangular plans; rounded towers use rounded rectangles. Other supported plans share their outlines across walls, floors, and roofs.
`sections_json.floor_levels` records actual floor heights; `floor_z` and `mass_top` provide corresponding plan calculations.

### Interiors and parking

Interiors include reception desks and access gates (`business`), seating and screens (`hospitality`), counters and tables (`cafe`), display plinths (`gallery`), or stocked shelves, refrigerators, and registers (`convenience`).
Lighting, ventilation, service cores, and doors are modeled. Furniture is batched by material; product counts depend on detail level.
`root['interior_programs_json']` records programs per floor. Atria are furnished only at ground level.

```python
root = create_building('building_25', design={
    'parking': True, 'site_height': 1.8, 'parking_side': 'left',
    'interior_program': 'business',
})
```

Parking requires a nonrounded tower at least 30 m wide and 38 m deep.
The ground floor is raised above a forecourt with a 22 m approach area. Perimeter stairs use approximately 150 mm risers and 340 mm treads, with driveway and pedestrian-ramp cutouts.
Driveway edges have 1.2 m vertical-bar guards; stair handrails at 0.9/0.65 m are spaced roughly 16 m apart.
The root remains at road grade; child geometry is raised. `site_bounds_json` includes the forecourt, and `site_cutouts_json` records excavations.
For custom scenes, use `parking_plaza.excavate_context(root, paving_objects, curb_objects)` to remove ground and curbs from the driveway. The city CLI handles road connections.
The asset includes the entrance, approach, and gate, not an entire underground garage layout.

### Batch diversity and limits

`plan_district(count, seed, rounded_fraction=0.10)` runs without Blender.
It allocates rounded and nonrounded candidates, favors less-used prototypes, and compares 36 candidates per building.
Descriptors compare width/depth in 4 m bands, floors in groups of three, radius in 2 m bands, and structural features including plans, massing, facades, lower programs, and roofs.
Color, names, and tiny dimension changes do not count as structural diversity. The vocabulary is finite.

- Rounded ratio refers to the tower, not a rounded podium.
- Tower forms use a 14-building cycle: 11 straight, two stepped, one paired.
- Non-convenience-store mid-rise buildings use continuous ground floors in seven of every ten slots.
- Tower, parking, and convenience-store proportions depend on prototype selection rather than independent ratio arguments.
- Site-fit filtering can change target counts and ratios. Reproducibility requires the code version as well as the seed.

### Finishes and sharing

Lower floors include glazing seals, drips, door mechanisms, floor joints, skirtings, signs, furniture, and lighting.
Rear and side walls close off lobbies. Vegetation shares branches and foliage clusters; Japanese text uses `CITY_FONT`.
Typical floors share meshes and foliage uses Geometry Nodes instances.
`optimize.share_evaluated_bevels(objects)` shares evaluated geometry for identical static bevels; arbitrary modifiers and animation are outside its scope. Saved files can grow even when evaluation work decreases.
For prototypes 11–26, `include_forecourt=False` omits off-site forecourt planting and side trees while retaining terrace and parking-site planting.
Include canopies, stairs, and driveways in occupancy checks. Model dimensions do not certify structural or legal compliance.

## Validation

`python3 asset_library/building/scripts/check_designs.py` checks 1,000 plans for reproducibility and structural duplication.
These Blender scripts generate their own test models:

- `scripts/check_buildings.py`: floors, envelopes, finite coordinates, and mesh sharing.
- `scripts/check_forms.py`: concave plans, tall floors, and atria.
- `scripts/check_parking_plaza.py`: ramp floors and headroom.
- `scripts/check_optimization.py`: evaluated geometry and materials before and after bevel sharing.

```sh
blender -b --factory-startup --python asset_library/building/scripts/check_forms.py
```

[Back to asset library](../../README.md#asset-library)
