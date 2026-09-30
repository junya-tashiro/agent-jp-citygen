# Dependencies and licensing

## Generated data

Geometry, materials, and textures are generated from code. External models, photographic textures, and font binaries are not bundled.
`asset_library/shared/fractures.py` and `asset_library/street_tree/scripts/procedural_textures.py` generate pixels that are saved in the Blend file.
Sign text is configurable; buildings are assembled from original prototypes.

## Fonts

Japanese lettering requires a user-supplied font. Set `CITY_FONT` to a TTF, OTF, or TTC file.
An installed Japanese system font can be used as a fallback on macOS.
Text is converted to meshes; the font file itself is not packed.

## License

The code uses the [MIT License](../LICENSE). Blender, Python, Node.js, and fonts retain their respective licenses.
Choose a font whose terms support your intended use and distribution of generated work.
The release script exports an allowlist of files and rejects bundled image, model, and font binaries.
