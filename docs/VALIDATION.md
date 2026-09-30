# Validation

## Automated tests

Run from the project root:

```sh
python3 -m unittest discover -s city_generator/tests -v
python3 -m unittest discover -s road_generator/tests -v
python3 -m unittest discover -s asset_library/coin_parking/tests -v
python3 -m unittest discover -s asset_library/subway_entrance/tests -v
python3 asset_library/building/scripts/check_designs.py
```

Tests cover planning, reproducibility, road conditions, curvature, occupancy, inputs, tamper detection, and map output.
The building design check evaluates 1,000 plans for structural descriptors, support, ratios, and reproducibility.

## Build-time checks

- Compare evaluated building bounds with planned site envelopes.
- Check driveway and sidewalk connection positions.
- Check subway support surfaces, approach clearance, and tactile connections.
- Lock output directories against concurrent generation.
- Use plan, font, Blend, and image hashes to decide whether outputs can be reused.

Generation times, file sizes, and check results are saved in `build_report.json`; detailed logs are in `build.log`.
Previews use EEVEE. Runtime depends on building structure, vegetation, and underground openings.

## Environment and limits

Tested on macOS with Blender 4.5.6 LTS. Other operating systems and fonts have not been tested directly.
Automatic placement uses conservative rectangular envelopes. Site fit can change target counts and rounded-building ratios.
Subway support and obstacle checks use sampling and cannot guarantee detection of every thin obstacle.
A valid 2D plan does not certify collision-free final meshes, traffic safety, or legal compliance.
