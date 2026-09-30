"""Public asset selection shared by packaging and generator fingerprints."""
from pathlib import PurePosixPath

# Development records and scene-specific review tools stay in the development tree.
_PRIVATE_SCRIPTS = {
    'showcase.py', 'district_100.py', 'check_district.py',
    'rerender_caution.py', 'check_bark_revision.py',
    'inspect_subway.py', 'render_gallery.py', 'check_revision.py',
}


def public_asset_file(relative):
    path = PurePosixPath(relative)
    if path.parts[0] != 'asset_library':
        return False
    if any(p in ('__pycache__', 'archive', 'blend', 'renders') for p in path.parts):
        return False
    if path.suffix == '.md':
        return path.name == 'README.md' and len(path.parts) == 3
    if path.suffix != '.py':
        return False
    return not (path.name.startswith('review_') or path.name in _PRIVATE_SCRIPTS)
