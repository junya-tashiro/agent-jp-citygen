# Tool interface and cost

The interface is a repository plus a small JSON CLI. Normal scene creation has a compact entry point, while the implementation remains available for feature development.

| Interface | Properties | Use |
|---|---|---|
| Read and modify all source for every scene | Flexible, but increases context, implementation work, and risk of breaking constraints | Not the normal workflow |
| JSON CLI and a short guide | Agent-independent, locally validated, usable by coding agents | Standard interface |
| MCP server | Structured tools, but requires server and client configuration | Could wrap the CLI |
| Dedicated LLM application | Unified UX, with model, authentication, billing, and UI maintenance | Outside the public scope |

## Cost sources

1. Natural language to request JSON uses the selected agent's token budget or subscription.
2. Planning and validation run locally in Python and Node.js. The LLM does not compute each building.
3. Blender generation and previews use local CPU, GPU, and memory, with no external rendering API charges.
4. Image review and iteration use agent inputs and conversation capacity.

Agent cost depends on the model, plan, and interaction volume and has not been measured here.
Blender execution time and agent interaction time are separate quantities.

## Efficiency

- Compiled road JavaScript is bundled; normal use needs no npm installation or repeated compilation.
- SVG maps provide layout feedback without rendering a 3D scene.
- Candidate comparison and placement search run locally without Blender.
- Plan, font, and output hashes allow matching Blend files and previews to be reused.
- Image-only previews load the existing Blend instead of rebuilding roads and buildings.
- Default previews use 640 px and EEVEE with eight samples; `--resolution` changes the size.
- JSON summaries are separate from detailed logs.
- Meshes, materials, foliage clusters, and evaluated bevel geometry are shared where possible.

See `docs/VALIDATION.md` for checks and each output's `build_report.json` for measurements.
Generation time depends on vegetation, excavation Booleans, and building structure as well as scene size.
