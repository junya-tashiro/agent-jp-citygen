"""Check the public tree API with no bark image files or user add-ons."""
from pathlib import Path
import sys
import math
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from asset_library.street_tree.scripts.build_street_tree import create_street_tree

for species in ('keyaki', 'cherry', 'ginkgo'):
    material = None
    for lod in ('low', 'medium', 'high'):
        root = create_street_tree(species, species=species, seed=9187, lod=lod)
        branches = next(o for o in root.children if 'trunk and branches' in o.name)
        current = branches.data.materials[0]
        assert material is None or current == material
        material = current
        assert not any(n.type == 'TEX_IMAGE' for n in current.node_tree.nodes)
        for key in ('bark_position_m', 'bark_radius_m'):
            attr = branches.data.attributes[key]
            assert len(attr.data) == len(branches.data.vertices)
            assert attr.domain == 'POINT'
        assert all(math.isfinite(c) for p in branches.data.attributes['bark_position_m'].data for c in p.vector)
        assert all(p.value > 0 for p in branches.data.attributes['bark_radius_m'].data)
        print('BARK_OK', species, lod, len(branches.data.vertices))
assert not [im for im in bpy.data.images if im.source == 'FILE' and im.filepath]
print('NO_EXTERNAL_IMAGES_OK')
