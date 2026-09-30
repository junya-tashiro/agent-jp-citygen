"""Blender-independent dimensions and placement envelopes, in metres."""
import math


def entrance_spec(variant='stairs', width=3.0):
    if variant not in ('stairs', 'elevator'):
        raise ValueError('variant must be stairs or elevator')
    if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or not 2.6 <= width <= 4.0:
        raise ValueError('width must be finite and between 2.6 and 4.0 metres')
    length = 6.6 if variant == 'stairs' else 3.2
    return dict(variant=variant, width=float(width), length=length,
                height=2.95 if variant == 'stairs' else 3.675,
                footprint=[-width/2, 0, width/2, length],
                approach=[-width/2, -2.0, width/2, 0],
                pavement_cutout=[-width/2+.23, 0, width/2-.23, 6.38] if variant == 'stairs' else [-width/2+.15, 0, width/2-.15, 3.12],
                opening=[-width/2+.23, .9, width/2-.23, 6.38] if variant == 'stairs' else None,
                underground_footprint=[-width/2, .9, width/2, 8.45] if variant == 'stairs' else None,
                stair_rise=.16, stair_run=.30, stair_count=15,
                depth=2.4 if variant == 'stairs' else 0)
