"""Shared sidewalk path including approach widening; no Blender dependency."""
from .planner import approach_existing_lateral_m

class ApproachOffsetPath:
    """Centreline facade that moves signed offsets through an approach taper."""
    def __init__(self, path, edge):
        self._path = path
        self._edge = edge
        self.length = path.length

    def __getattr__(self, name):
        return getattr(self._path, name)

    def offset_point(self, station, lateral):
        adjusted = approach_existing_lateral_m(
            self._edge, station, self.length, lateral)
        return self._path.offset_point(station, adjusted)

