"""User-owned text font, never bundled. Geometry/textures remain procedural.

CITY_FONT may point to an appropriately licensed Japanese font. A local macOS
font remains a compatibility fallback; its license is not the project's MIT.
"""
import os
from pathlib import Path

def font_path():
    configured=os.environ.get('CITY_FONT') or os.environ.get('COIN_PARKING_FONT')
    if configured:
        path=Path(configured).expanduser()
        if not path.is_file():raise FileNotFoundError('CITY_FONT does not exist: '+str(path))
    else:
        candidates=sorted(Path('/System/Library/Fonts').glob('*丸*'))
        if not candidates:raise RuntimeError('Japanese labels need a user-installed font. Set CITY_FONT to a Japanese TTF/OTF/TTC; no font is bundled.')
        path=candidates[0]
    return path

def japanese_font():
    import bpy
    return bpy.data.fonts.load(str(font_path()),check_existing=True)

def font_signature():
    import hashlib
    return hashlib.sha256(font_path().read_bytes()).hexdigest()
