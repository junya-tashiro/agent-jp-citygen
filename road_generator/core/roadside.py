"""Road-edge-relative placement along a chain of authored road segments."""
from .planner import approach_existing_lateral_m, road_half_width_m


def roadside_site(chain, paths, station, side, setback):
    """Resolve chain distance and side before applying the local road profile.

    ``chain`` contains (edge, traversal_start_node) pairs. Return the point,
    traversal tangent, supporting edge and its local centreline station.
    """
    remaining = station
    for index, (edge, from_node) in enumerate(chain):
        path = paths[edge.id]
        if remaining <= path.length or index == len(chain) - 1:
            forward = edge.start == from_node
            distance = max(0.0, min(path.length, remaining))
            local = distance if forward else path.length - distance
            local_side = side if forward else -side
            lateral = approach_existing_lateral_m(
                edge, local, path.length,
                local_side * (road_half_width_m(edge) + setback))
            point = path.offset_point(local, lateral)
            tangent = path.tangent_at_distance(local)
            if not forward:
                tangent = (-tangent[0], -tangent[1])
            return point, tangent, edge, local
        remaining -= path.length
    raise ValueError('A roadside site requires a nonempty road chain')
