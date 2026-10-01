# Agent workflow

Start with this guide and `examples/city/*.json`; reading the entire repository is unnecessary for normal scene creation.
The CLI works with any coding agent. It does not require an LLM API key or MCP server and does not interpret natural language itself.
The user chooses and pays for their agent separately.

## Standard workflow

1. Separate required features from unspecified choices. City bounds include building sites.
2. Run `python3 city.py capabilities` and copy a suitable example.
3. Edit `scenes/<name>/request.json`. Roads use a key-point representation.
4. Run `python3 city.py plan scenes/<name>/request.json --output scenes/<name>/plan.json`.
5. Inspect `summary`, `warnings`, the plan's `network`, and the SVG map. Revise the request rather than silently dropping requirements.
6. Run `python3 city.py build scenes/<name>/plan.json --output scenes/<name>/output`.
7. Use `preview` instead of `build` when images are needed. Matching saved Blend files are reused after hash verification. Review overview and street images along with numerical checks.
8. Report output paths, requirement coverage, measured time, and limitations.

Commands return JSON. Failures return a nonzero exit code and `errors`; detailed Blender output is in `build.log`.
Road edits can change split edge IDs, so recheck explicit placement references.
Plans are derived data: edit the request and replan instead of editing calculated positions to bypass validation.

## Normal editing scope

- Edit requests, settings, and outputs under `scenes/<name>/`.
- Plan buildings in batches; do not write new modeling code for every building.
- Do not modify validators, road constraints, or shared generators to suppress warnings.
- Treat unsupported features as explicit generator development, separate from ordinary scene creation.
- Do not overwrite unrelated user files or scenes.
- Do not download or bundle external models, images, or fonts without authorization.

## Unsupported requests and feature contributions

First check whether existing parameters and procedural components can satisfy the request. If they cannot, explain the missing capability and any alternatives; do not silently omit or replace a requirement. Treat implementation of the missing capability as explicit feature development, separate from ordinary scene generation.

The maintainer would appreciate a pull request when you implement a missing feature. Once the user has authorized feature development, aim to prepare a reusable change and propose contributing it to https://github.com/junya-tashiro/agent-jp-citygen. Submit the PR when the user has authorized publication and GitHub access is available. Otherwise, leave the change ready for review and provide a suggested PR title, description, and validation results.

For a contribution to be suitable for a PR:

- Generate new geometry, materials, and textures procedurally from Python code. Do not depend on pre-made model assets, downloaded asset packs, external image textures, or manually edited Blender files. Reusing this repository's existing procedural Python generators and shared utilities is encouraged; the existing user-supplied font mechanism remains available for lettering.
- Keep the feature reusable across scenes, expose meaningful parameters, and preserve existing road and placement constraints. Do not weaken validation to make a particular scene pass.
- Include a small reproducible example, relevant documentation, and checks appropriate to the change. For visual changes, inspect EEVEE previews as well as numerical checks.
- Describe the new behavior, how to reproduce it, validation results, and any remaining limitations in the PR. Submit source and necessary examples rather than generated scene files or unrelated local work, and keep the contribution compatible with the project's MIT License.

## Finding details

Read `docs/SCENE_FORMAT.md`, then the relevant asset README, then only the necessary implementation.
Road rules are implemented in `road_authoring/src/authoringV2.ts`. No browser is required.
The runtime JavaScript is compiled from TypeScript and checked against source SHA256 hashes.
Only after editing TypeScript, run `CITY_TSC=/path/to/tsc node city_generator/compile_roads.mjs`.

## Keeping costs low

Use `python3 city.py map <plan.json> --output <map.svg>` for Python-only layout review.
Planning and validation do not launch Blender. Resolve numerical layout problems before rendering.
Default previews use 640 px and EEVEE with eight samples. Render only when visual evidence is needed.
Read JSON summaries and relevant error excerpts rather than entire Blender logs.
Wait for generation to finish instead of polling every second. Local generation requires no network or paid API.

## Limitations to report

Building counts and rounded-building ratios are selection targets; site fit affects the final distribution.
Specify mandatory buildings and parking lots in `placements`, and report failures explicitly.
Road validation is not certification of traffic safety or legal compliance.
Japanese text requires a user-supplied font; see `docs/PROVENANCE.md`.
