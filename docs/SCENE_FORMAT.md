# City requests and plans, version 1

Distances are in metres; the world is Z-up. See `examples/city/central_200.json`.

## Request

- `version: 1`, integer `seed`, and `bounds: [xmin,ymin,xmax,ymax]`.
- `roads: [{id, points:[[x,y],...], style:{...}}]`. Omitted style fields use the road-authoring defaults.
- Alternatively, provide a V2 road-authoring `document` for the full authoring representation.
- `junctions: [{at:[x,y],style:{...}}]` configures intersections in the simple `roads` input. A selector must match an intersection.
- `components` contains driveway cutouts in road-authoring format. When using `document`, include them inside it.
- `time_of_day: day | night`.
- `buildings: {count:20, rounded_fraction:0.1, gap:1, detail:"medium"}`.
- `placements` reserves explicit buildings and parking before automatic placement.
- `subways` specifies subway entrances, station labels, and multiple route codes and colors.

## Road style

`road_class`, `speed_limit`, `lanes_each_way` (1–3), `sidewalks` (none/both),
`center_treatment` (median/none/orange_solid/white_solid/white_dashed), `median_width` (narrow/wide),
`bicycle_lane`, `curb_parking_prohibition`, `tactile_paving`, `street_lights`,
`guardrail` (false/{exterior_color:white|brown}),
`planting` (false/{random:true,style:legacy|clipped_hedge,seed}),
`street_trees` (false/{random,species:keyaki|ginkgo|cherry,density,seed}).

The road validator checks combinations, curvature, intersection angles, and approach lanes.
Junction style includes `exterior_color`, `name`, `roman_name`, `sequence`,
`signal_control` (signalized/unsignalized/unsignalized_n_by_1), and `extra_inbound_lane`.
Unsignalized four-way intersections require one lane per direction on every connected road.
Unsignalized n-by-1 T intersections must satisfy the authoring validator's supported conditions.

## Explicit placement

```json
{"id":"office", "type":"building", "key":"building_22", "seed":17,
 "edge":"avenue_edge_1_1", "station":60, "side":"left",
 "design":{"width":38,"depth":28,"floors":30}}
```

`edge` is a split edge ID from the compiled network. `station` is distance from that edge's start; `side` is relative to its direction.
Position and rotation are derived from the outer sidewalk edge.
Prototypes 01–10 accept a seed; 11–26 also accept the `design` parameters in the building README.
Site envelopes include projections, stairs, and driveways. Curved frontage is set back to clear the sidewalk and connected with paving.
For underground parking buildings, station denotes the driveway center; otherwise it denotes the building's lateral center.

```json
{"id":"parking", "type":"coin_parking", "width":18,"depth":24,
 "edge":"avenue_edge_2_2", "station":80,"side":"left"}
```

Parking station denotes the entrance. Cutout validation rejects proximity to intersections and overlaps with other cutouts.

```json
{"id":"subway", "variant":"stairs", "station_name":"中央", "station_roman":"Chuo",
 "width":3, "position":[-110,-13.399], "rotation_degrees":90,
 "routes":[{"code":"M11","color":"#E53935"}]}
```

Subways use the supplied position and rotation. During the Blender build, sampled rays check the body and its 2 m approach zone for sidewalk support and obstacles; overlapping entrances are rejected.
The build cuts the underground opening and connects tactile paving. Choose a sidewalk section wide enough for the entrance.

## Plans and validation

A plan stores the request, authoring document, compiled roads, selected building designs, placements, occupancy, signatures, actual counts, and warnings.
Revise the request and replan when making changes. Automatic placement uses conservative rectangular envelopes, not interlocking concave footprints.
Rounded-building ratios apply to candidates and are not guaranteed after site-fit filtering.
Roadless cities, terrain elevation, and deforming buildings to irregular plots are outside automatic placement.
Building plan shapes, terraces, facades, and lower-floor programs remain configurable.

A same-name `.svg` shows roads and sites; orange dots mark unsignalized intersections.
Derived positions, site dimensions, and driveway connections are recomputed for validation.
Replan from the request when the generator source signature changes.

## Maps

`plan` writes an SVG map automatically. To export a saved plan:

```sh
python3 city.py map scenes/demo/plan.json --output scenes/demo/map.svg --title 'Demo city'
```

Use `--no-labels` to hide site labels. SVGs can be zoomed in a browser.
Maps show roads, sidewalks, building sites, floor counts, parking, driveways, subway entrances, and signal control.
Coordinates are in metres, with +Y up and +X right; this is not geographic north.
Building polygons represent reserved sites, not roof outlines. Medians, crosswalks, road markings, and street furniture are omitted from this schematic.
Saved plans from different generator versions can be viewed, but a mismatched fingerprint is rejected.
A successful `map` command does not certify build validity; use `validate` before regeneration.
Map output uses only Python's standard library, with no Blender, Node.js, external images, or network access.
