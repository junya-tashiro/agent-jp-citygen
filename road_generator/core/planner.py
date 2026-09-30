from dataclasses import dataclass
import math
import random
import zlib

from .schema import Approach, RoadNetwork


def stop_approach_has_crosswalk_sign(node_id: str, edge_id: str) -> bool:
    """Choose the 50% stacked-sign variant reproducibly per approach."""
    # Unlike hash(), crc32 is stable between Blender/Python processes.
    return zlib.crc32(f"{node_id}\0{edge_id}".encode("utf-8")) % 2 == 0


LANE_WIDTH_M = 3.25
MEDIAN_NARROW_WIDTH_M = 0.65
MEDIAN_WIDE_EXTRA_M = LANE_WIDTH_M
EXTRA_INBOUND_LANE_TAPER_M = 20.0
EXTRA_INBOUND_LANE_FULL_M = 30.0
EXTRA_INBOUND_LANE_LINK_M = 150.0
EXTRA_INBOUND_LANE_LINK_TRANSITION_M = 20.0


def median_extra_width_m(edge) -> float:
    """Extra total road width introduced by a wide median."""
    return (MEDIAN_WIDE_EXTRA_M
            if edge is not None and edge.median
            and edge.median_width == "wide" else 0.0)


def median_physical_width_m(edge) -> float:
    return MEDIAN_NARROW_WIDTH_M + median_extra_width_m(edge)


def road_half_width_m(edge) -> float:
    return edge.lanes_each_way * LANE_WIDTH_M + median_extra_width_m(edge) * 0.5


def carriageway_lateral_m(edge, lateral: float) -> float:
    """Move a signed lane-relative offset out by half the wide-median gain."""
    if abs(lateral) <= 1e-12:
        return lateral
    return lateral + math.copysign(median_extra_width_m(edge) * 0.5, lateral)


def has_extra_inbound_lane(edge, endpoint: str) -> bool:
    return bool(edge.approaches.get(endpoint, {}).get(
        "extra_inbound_lane", False))


def has_extra_inbound_reserve(edge, endpoint: str) -> bool:
    """Internal T-junction space replacing an impossible right turn."""
    return bool(edge.approaches.get(endpoint, {}).get(
        "_extra_inbound_lane_reserve", False))


def has_extra_inbound_section(edge, endpoint: str) -> bool:
    return (has_extra_inbound_lane(edge, endpoint)
            or has_extra_inbound_reserve(edge, endpoint))


def approach_road_half_width_m(edge, endpoint: str) -> float:
    if not has_extra_inbound_section(edge, endpoint):
        return road_half_width_m(edge)
    return edge.lanes_each_way * LANE_WIDTH_M + LANE_WIDTH_M * 0.5


def extra_lane_factor(edge, station: float, length: float) -> float:
    """Smoothstep blend from the ordinary section to either endpoint section."""
    # Closely spaced junctions share one continuous widened section.  Returning
    # to the ordinary cross-section only to widen again is visually noisy and,
    # below 100m, would make the two fixed+taper envelopes overlap.
    if (length < EXTRA_INBOUND_LANE_LINK_M
            and has_extra_inbound_section(edge, "from")
            and has_extra_inbound_section(edge, "to")):
        return 1.0
    def endpoint_factor(distance, endpoint):
        if not has_extra_inbound_section(edge, endpoint):
            return 0.0
        if distance <= EXTRA_INBOUND_LANE_FULL_M:
            return 1.0
        value = 1.0 - ((distance - EXTRA_INBOUND_LANE_FULL_M)
                       / EXTRA_INBOUND_LANE_TAPER_M)
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)
    return max(endpoint_factor(station, "from"),
               endpoint_factor(length - station, "to"))


def approach_outward_shift_m(edge, station: float, length: float) -> float:
    """Per-side outward shift of road-edge-relative objects."""
    return (0.0 if edge.median_width == "wide" else LANE_WIDTH_M * 0.5
            * extra_lane_factor(edge, station, length))


def approach_existing_lateral_m(edge, station: float, length: float,
                                lateral: float) -> float:
    if abs(lateral) <= 1e-12:
        return lateral
    return lateral + math.copysign(
        approach_outward_shift_m(edge, station, length), lateral)


def approach_median_section(edge, station: float, length: float,
                            endpoint: str | None = None) -> tuple[float, float]:
    """Return (centre lateral, width) in the edge centreline frame."""
    if endpoint is not None:
        factor = 1.0 if has_extra_inbound_section(edge, endpoint) else 0.0
        reserve = has_extra_inbound_reserve(edge, endpoint)
        # In the edge frame inbound is right at ``from`` and left at ``to``.
        outgoing_side = 1.0 if endpoint == "from" else -1.0
    elif (length < EXTRA_INBOUND_LANE_LINK_M
          and has_extra_inbound_section(edge, "from")
          and has_extra_inbound_section(edge, "to")):
        # Keep the divider narrowed throughout the linked section, while its
        # lateral bias changes continuously from the inbound side of the first
        # junction to that of the second.  This also drives an orange centre
        # line through the same smooth S transition.
        transition = min(EXTRA_INBOUND_LANE_LINK_TRANSITION_M, length)
        transition_start = (length - transition) * 0.5
        t = max(0.0, min(1.0,
            (station - transition_start) / max(transition, 1e-9)))
        t = t * t * (3.0 - 2.0 * t)
        from_reserve = has_extra_inbound_reserve(edge, "from")
        to_reserve = has_extra_inbound_reserve(edge, "to")
        from_width = (MEDIAN_NARROW_WIDTH_M + MEDIAN_WIDE_EXTRA_M
                      if from_reserve else MEDIAN_NARROW_WIDTH_M)
        to_width = (MEDIAN_NARROW_WIDTH_M + MEDIAN_WIDE_EXTRA_M
                    if to_reserve else MEDIAN_NARROW_WIDTH_M)
        from_lateral = 0.0 if from_reserve else LANE_WIDTH_M * 0.5
        to_lateral = 0.0 if to_reserve else -LANE_WIDTH_M * 0.5
        return (from_lateral + (to_lateral - from_lateral) * t,
                from_width + (to_width - from_width) * t)
    else:
        from_factor = extra_lane_factor(edge, station, length) if has_extra_inbound_section(edge, "from") else 0.0
        to_factor = extra_lane_factor(edge, station, length) if has_extra_inbound_section(edge, "to") else 0.0
        if from_factor >= to_factor:
            factor, outgoing_side = from_factor, 1.0
            reserve = has_extra_inbound_reserve(edge, "from")
        else:
            factor, outgoing_side = to_factor, -1.0
            reserve = has_extra_inbound_reserve(edge, "to")
    target_width = (MEDIAN_NARROW_WIDTH_M + MEDIAN_WIDE_EXTRA_M
                    if reserve else MEDIAN_NARROW_WIDTH_M)
    width = median_physical_width_m(edge) + (
        target_width - median_physical_width_m(edge)) * factor
    lateral = 0.0 if reserve else outgoing_side * LANE_WIDTH_M * 0.5 * factor
    return lateral, width


def approach_center_marking_lateral_m(edge, station: float, length: float) -> float:
    """Centre-line offset matching the displaced divider of an extra lane."""
    if edge.median or not (has_extra_inbound_section(edge, "from")
                           or has_extra_inbound_section(edge, "to")):
        return 0.0
    lateral, _width = approach_median_section(edge, station, length)
    return lateral
LANE_SEPARATOR_SOLID_APPROACH_M = 15.0
JUNCTION_CENTER_MARKING_WIDTH_M = 0.15
from .streets import SIDEWALK_WIDTH_M, SIDEWALK_CORNER_RADIUS_M
# Straight sidewalk/curb runs end at the tangent point of the rounded corner.
# Keeping these values identical prevents the straight geometry from extending
# into the first few centimetres of the curved geometry.
SIDEWALK_INTERSECTION_MARGIN_M = SIDEWALK_CORNER_RADIUS_M
BICYCLE_MARKING_WIDTH_M = 0.50
BICYCLE_MARKING_LENGTH_WIDTH_RATIO = 14.579088471849866
BICYCLE_MARKING_MIN_GAP_M = 2.5
BICYCLE_JUNCTION_CHEVRON_CROSSWALK_CLEARANCE_M = 0.08
CROSSWALK_OFFSET_FROM_ROAD_EDGE_M = 5.75
TACTILE_TILE_M = 0.30
TACTILE_ROUTE_BACK_EDGE_OFFSET_M = 0.60
TACTILE_CROSSING_EDGE_CLEARANCE_M = 0.30
CURB_BLOCK_LENGTH_M = 0.40
CURB_BLOCK_JOINT_M = 0.002
CURB_WIDTH_M = 0.14
CURB_ROAD_APRON_M = 0.15
ROAD_MARKING_CURB_CLEARANCE_M = 0.03
ROAD_TOP_Z_M = 0.0
SIDEWALK_TOP_Z_M = 0.02
CURB_TOP_Z_M = 0.17
SIDEWALK_HEIGHT_DELTA_M = SIDEWALK_TOP_Z_M - 0.18
GUARDRAIL_BASE_Z_M = SIDEWALK_TOP_Z_M
PLANTING_INSTANCE_Z_M = 0.07 + SIDEWALK_HEIGHT_DELTA_M
PLANTING_SOIL_TOP_Z_M = PLANTING_INSTANCE_Z_M + 0.06
SIGNAL_BASE_Z_M = SIDEWALK_HEIGHT_DELTA_M
SIGNAL_ROADSIDE_EDGE_CLEARANCE_M = 0.42
# The guardrail post centre is 0.22 m outside the carriageway. Its 60.5 mm
# post and the stop-sign's 60 mm pole leave about 20 mm clear when the sign
# centre is 0.30 m outside the road edge.
STOP_SIGN_OFFSET_FROM_ROAD_EDGE_M = 0.30
STREET_TREE_END_CLEARANCE_M = 0.50
PEDESTRIAN_STREET_LIGHT_SPACING_M = 23.0
PEDESTRIAN_STREET_LIGHT_CROSSWALK_CLEARANCE_M = 10.0
ROADWAY_STREET_LIGHT_SPACING_M = 35.0
STREET_LIGHT_TREE_CLEARANCE_M = 3.0
STREET_LIGHT_JUNCTION_ADVANCE_FRACTION = 0.70


def lane_separator_solid_interval(
        edge_start: float, edge_end: float, side: int,
        start_distance_to_stop_line: float | None,
        end_distance_to_stop_line: float | None,
) -> tuple[float, float] | None:
    """Return the solid lane-divider interval on an inbound approach.

    Road geometry is authored from ``start`` to ``end``.  In left-hand
    traffic, the negative-offset carriageway travels toward ``start`` and the
    positive-offset carriageway travels toward ``end``.  Only the divider on
    the corresponding inbound half becomes solid; the opposite, departing
    half remains dashed.

    Distances are measured from an edge endpoint toward its nearest junction;
    they are negative when that endpoint lies between the stop line and the
    junction.  This representation lets the interval continue across editor
    keypoint edges while remaining anchored to the actual stop line.
    """
    if edge_end <= edge_start:
        return None
    if side < 0 and start_distance_to_stop_line is not None:
        near = max(edge_start, edge_start - start_distance_to_stop_line)
        far = min(edge_end, edge_start + LANE_SEPARATOR_SOLID_APPROACH_M
                  - start_distance_to_stop_line)
        return (near, far) if far > near else None
    if side > 0 and end_distance_to_stop_line is not None:
        near_from_end = max(0.0, -end_distance_to_stop_line)
        far_from_end = min(edge_end - edge_start,
                           LANE_SEPARATOR_SOLID_APPROACH_M
                           - end_distance_to_stop_line)
        if far_from_end <= near_from_end:
            return None
        return (edge_end - far_from_end, edge_end - near_from_end)
    return None


def approach_lane_arrow_kinds(lanes_each_way: int) -> tuple[str, ...]:
    """Return lane-use arrows ordered from the driver's left to right."""
    if lanes_each_way < 2:
        return ()
    if lanes_each_way == 2:
        return ("left_straight", "straight_right")
    return ("left_straight", *("straight" for _ in range(lanes_each_way - 2)), "right")


def cross_lane_arrow_kinds(
        lanes_each_way: int, has_single_lane_road: bool) -> tuple[str, ...]:
    """Avoid a dedicated right-only lane in a cross containing a 1-lane road."""
    kinds = list(approach_lane_arrow_kinds(lanes_each_way))
    if has_single_lane_road and kinds and kinds[-1] == "right":
        kinds[-1] = "straight_right"
    return tuple(kinds)


def t_junction_lane_arrow_kinds(
        lanes_each_way: int, available_turn: str,
        dedicated_right_lane: bool = False) -> tuple[str, ...]:
    """Return arrows containing only movements that exist at a T junction."""
    if lanes_each_way < 2:
        return ()
    if available_turn == "stem":
        left_count = (lanes_each_way + 1) // 2
        return (*("left" for _ in range(left_count)),
                *("right" for _ in range(lanes_each_way - left_count)))
    if available_turn == "right":
        right = "right" if dedicated_right_lane else "straight_right"
        return (*("straight" for _ in range(lanes_each_way - 1)), right)
    if available_turn == "left":
        return ("left_straight",
                *("straight" for _ in range(lanes_each_way - 1)))
    raise ValueError(f"Unsupported T-junction movement: {available_turn!r}")


@dataclass(frozen=True)
class SegmentPlan:
    edge_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    sidewalks: str
    road_class: str
    speed_limit: int
    lanes_each_way: int


@dataclass(frozen=True)
class NetworkPlan:
    segments: tuple[SegmentPlan, ...]
    approaches: tuple[Approach, ...]


@dataclass(frozen=True)
class CrosswalkPlan:
    id: str
    node_id: str
    center: tuple[float, float]
    walking_axis: str
    road_width: float = 6.5
    crosswalk_width: float = 3.2
    controlled_approaches: tuple[str, ...] = ()
    median_extra_width: float = 0.0


@dataclass(frozen=True)
class TactileTilePlan:
    id: str
    kind: str
    center: tuple[float, float]
    size: tuple[float, float] = (TACTILE_TILE_M, TACTILE_TILE_M)
    guidance_axis: str = "x"
    rotation_degrees: float = 0.0
    route_key: str = ""


@dataclass(frozen=True)
class StopLinePlan:
    id: str
    center: tuple[float, float]
    across_axis: str
    width: float = 2.89


@dataclass(frozen=True)
class SignalSite:
    id: str
    kind: str
    location: tuple[float, float, float]
    rotation_degrees: float
    merge_candidate: bool = False
    node_id: str = ""
    support_mode: str = "roadside_left"
    support_median_id: str = ""
    pedestrian_support_side: str = "left"
    pedestrian_position: str = ""


@dataclass(frozen=True)
class SignalBlockPlan:
    corner: str
    vehicle: SignalSite
    pedestrians: tuple[SignalSite, SignalSite]
    pattern: int


@dataclass(frozen=True)
class PedestrianCountdownPlan:
    node_id: str
    blue_level: int
    red_level: int


@dataclass(frozen=True)
class GuardrailPlan:
    id: str
    edge_id: str
    side: str
    start: tuple[float, float]
    end: tuple[float, float]
    exterior_color: str
    beam_side: str
    elevation: float
    curve_center: tuple[float, float] | None = None
    curve_radius: float = 0.0
    curve_start_degrees: float = 0.0
    curve_sweep_degrees: float = 0.0


@dataclass(frozen=True)
class PlantingPlan:
    id: str
    edge_id: str
    side: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    density: float
    maintenance: float
    health: float
    seed: int
    elevation: float
    curve_center: tuple[float, float] | None = None
    curve_radius: float = 0.0
    curve_start_degrees: float = 0.0
    curve_sweep_degrees: float = 0.0
    style: str = "legacy"


@dataclass(frozen=True)
class StreetTreePlan:
    id: str
    edge_id: str
    side: str
    location: tuple[float, float, float]
    species: str
    seed: int
    rotation_degrees: float


@dataclass(frozen=True)
class StreetLightPlan:
    id: str
    edge_id: str
    kind: str
    side: str
    location: tuple[float, float, float]
    rotation_degrees: float
    lit: bool


@dataclass(frozen=True)
class ReflectorPolePlan:
    id: str
    node_id: str
    corner: str
    location: tuple[float, float, float]
    rotation_degrees: float


@dataclass(frozen=True)
class MedianPlan:
    id: str
    edge_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float = 0.65
    height: float = 0.24
    rounded_start: bool = False
    node_id: str = ""
    approach: str = ""
    rounded_end: bool = False
    cap_depth: float = MEDIAN_NARROW_WIDTH_M * 0.5


@dataclass(frozen=True)
class MedianIslandDevicePlan:
    id: str
    median_id: str
    device_type: str
    location: tuple[float, float, float]
    rotation_degrees: float


@dataclass(frozen=True)
class BicycleMarkingPlan:
    id: str
    edge_id: str
    direction: str
    location: tuple[float, float]
    rotation_degrees: float
    width: float


@dataclass(frozen=True)
class BicycleJunctionChevronPlan:
    id: str
    node_id: str
    road_id: str
    location: tuple[float, float]
    rotation_degrees: float
    width: float
    priority: bool


@dataclass(frozen=True)
class RightTurnGuidePlan:
    id: str
    node_id: str
    edge_id: str
    dash_segments: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    stop_line_start: tuple[float, float]
    stop_line_end: tuple[float, float]


@dataclass(frozen=True)
class CurbParkingStripePlan:
    id: str
    edge_id: str
    side: str
    start: tuple[float, float]
    end: tuple[float, float]
    curve_center: tuple[float, float] | None = None
    curve_radius: float = 0.0
    curve_start_degrees: float = 0.0
    curve_sweep_degrees: float = 0.0


CARDINALS = {
    (1, 0): "east",
    (-1, 0): "west",
    (0, 1): "north",
    (0, -1): "south",
}


def _cardinal(dx: float, dy: float) -> str:
    # Geographic labels remain useful compatibility metadata for the mature
    # planners.  Pick the nearest cardinal direction; actual geometry keeps
    # using the unmodified edge vector and therefore changes continuously.
    if abs(dx) >= abs(dy):
        key = (int(math.copysign(1, dx)), 0)
    else:
        key = (0, int(math.copysign(1, dy)))
    return CARDINALS[key]


def _compatibility_approach_map(network: RoadNetwork, node_id: str) -> dict[str, str]:
    """Assign rotated junction arms to one coherent cardinal frame."""
    node = network.nodes[node_id]
    records = []
    for edge in network.edges:
        if node_id not in {edge.start, edge.end}:
            continue
        other_id = edge.end if edge.start == node_id else edge.start
        other = network.nodes[other_id]
        records.append((edge, other.position[0] - node.position[0],
                        other.position[1] - node.position[1]))
    groups = {}
    for record in records:
        if record[0].road_id:
            groups.setdefault(record[0].road_id, []).append(record)
    if len(groups) != 2:
        return {edge.id: _cardinal(dx, dy) for edge, dx, dy in records}

    def horizontal_score(items):
        _, dx, dy = items[0]
        return abs(dx) / max(math.hypot(dx, dy), 1e-9)

    ordered = sorted(groups.values(), key=horizontal_score, reverse=True)
    result = {}
    for edge, dx, dy in ordered[0]:
        result[edge.id] = "east" if dx >= 0.0 else "west"
    for edge, dx, dy in ordered[1]:
        result[edge.id] = "north" if dy >= 0.0 else "south"
    return result


def compatibility_approach_map(network: RoadNetwork, node_id: str) -> dict[str, str]:
    """Public cardinal arm mapping shared by planners and Blender placement."""
    return _compatibility_approach_map(network, node_id)


def plan_network(network: RoadNetwork) -> NetworkPlan:
    segments = []
    approaches = []
    for edge in network.edges:
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        direction = _cardinal(end[0] - start[0], end[1] - start[1])
        segments.append(SegmentPlan(
            edge_id=edge.id,
            start=start,
            end=end,
            width=road_half_width_m(edge) * 2,
            sidewalks=edge.sidewalks,
            road_class=edge.road_class,
            speed_limit=edge.speed_limit,
            lanes_each_way=edge.lanes_each_way,
        ))
        for endpoint, node_id, facing in (
            ("from", edge.start, _cardinal(start[0] - end[0], start[1] - end[1])),
            ("to", edge.end, direction),
        ):
            attrs = edge.approaches.get(endpoint, {})
            if attrs:
                approaches.append(Approach(
                    edge_id=edge.id,
                    node_id=node_id,
                    direction=facing,
                    right_turn_lane=attrs.get("right_turn_lane", False),
                    stop_control=attrs.get("stop_control", False),
                ))
    return NetworkPlan(tuple(segments), tuple(approaches))


def road_widths_at_node(network: RoadNetwork, node_id: str) -> tuple[float, float]:
    """Return cardinal compatibility widths from junction-end tangents.

    General geometry may bend a nominal east-west road at the junction, so
    endpoint coordinate equality cannot identify its axis.  Classifying the
    actual junction tangent keeps the legacy cardinal planner useful while
    preserving the authored width of gently oblique and curved arms.
    """
    east_west, north_south = [], []
    approach_map = _compatibility_approach_map(network, node_id)
    for edge in network.edges:
        if node_id not in {edge.start, edge.end}:
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        geometry = edge.geometry
        if geometry is not None and geometry.kind == "cubic_bezier":
            tangent = (
                (geometry.control_from[0] - start[0],
                 geometry.control_from[1] - start[1])
                if edge.start == node_id else
                (end[0] - geometry.control_to[0],
                 end[1] - geometry.control_to[1])
            )
        else:
            tangent = (end[0] - start[0], end[1] - start[1])
        endpoint = "from" if edge.start == node_id else "to"
        width = approach_road_half_width_m(edge, endpoint) * 2
        target = (east_west if approach_map.get(edge.id) in {"east", "west"}
                  else north_south)
        target.append(width)
    return max(east_west, default=6.5), max(north_south, default=6.5)


def effective_vehicle_arrow(network: RoadNetwork, node) -> str:
    """Apply the shared right-arrow hardware rule for wide four-way roads."""
    if node.kind == "signalized_t_junction":
        return "none"
    if node.vehicle_arrow == "right":
        return "right"
    if node.kind != "signalized_cross":
        return "none"
    east_west_width, north_south_width = road_widths_at_node(network, node.id)
    two_by_two_width = 2 * 2 * LANE_WIDTH_M
    return ("right" if min(east_west_width, north_south_width)
            >= two_by_two_width - 1e-6 else "none")


def connected_approaches(network: RoadNetwork, node_id: str) -> tuple[str, ...]:
    """Return cardinal road arms connected to a semantic junction node."""
    return tuple(_compatibility_approach_map(network, node_id).values())


_CORNER_ARCS = (
    ("southwest", -1, -1, "west", "south", 4.0, 82.0),
    ("northwest", -1, 1, "west", "north", -86.0, 82.0),
    ("southeast", 1, -1, "east", "south", 94.0, 82.0),
    ("northeast", 1, 1, "east", "north", 184.0, 82.0),
)


def _edge_for_approach(network: RoadNetwork, node_id: str, approach: str):
    approach_map = _compatibility_approach_map(network, node_id)
    for edge in network.edges:
        if node_id not in {edge.start, edge.end}:
            continue
        if approach_map.get(edge.id) == approach:
            return edge
    return None


def _guardrail_side_toward_corner(network: RoadNetwork, edge, qx: int, qy: int) -> str:
    start = network.nodes[edge.start].position
    end = network.nodes[edge.end].position
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    left = (-dy / length, dx / length)
    return "left" if left[0] * qx + left[1] * qy > 0 else "right"


def _corner_sources(network: RoadNetwork, node_id: str, qx: int, qy: int,
                    first_approach: str, second_approach: str, feature: str):
    edges = tuple(_edge_for_approach(network, node_id, approach)
                  for approach in (first_approach, second_approach))
    if any(edge is None or edge.sidewalks != "both" for edge in edges):
        return None
    configs = tuple(getattr(edge, feature) for edge in edges)
    if any(config is None for config in configs):
        return None
    if feature == "guardrail":
        for edge, config in zip(edges, configs):
            required = _guardrail_side_toward_corner(network, edge, qx, qy)
            if config.sides not in {"both", required}:
                return None
    return edges, configs


def _corner_barrier_kind(node_id: str) -> str:
    """Use curved guardrails at every eligible corner."""
    return "guardrail"


def plan_crosswalks(network: RoadNetwork) -> tuple[CrosswalkPlan, ...]:
    crosswalks = []
    for node in network.nodes.values():
        x, y = node.position
        if node.kind in {"signalized_cross", "signalized_t_junction",
                         "stop_cross", "stop_t_junction",
                         "priority_t_junction"}:
            east_west_width, north_south_width = road_widths_at_node(network, node.id)
            connected = set(connected_approaches(network, node.id))
            east_west_crossing_offset = (
                north_south_width * 0.5 + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
            )
            north_south_crossing_offset = (
                east_west_width * 0.5 + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
            )
            stop_approaches = None
            if node.kind == "priority_t_junction":
                stop_approaches = {
                    _compatibility_approach_map(network, node.id)[edge.id]
                    for edge in network.edges
                    if node.id in {edge.start, edge.end}
                    and edge.approaches.get(
                        "from" if edge.start == node.id else "to", {}).get(
                            "stop_control", False)
                }
            if "north_south" in node.crossings:
                candidates = (
                    CrosswalkPlan(f"{node.id}_west", node.id,
                                  (x - east_west_crossing_offset, y), "y",
                                  east_west_width,
                                  controlled_approaches=("west",),
                                  median_extra_width=median_extra_width_m(
                                      _edge_for_approach(network, node.id, "west"))),
                    CrosswalkPlan(f"{node.id}_east", node.id,
                                  (x + east_west_crossing_offset, y), "y",
                                  east_west_width,
                                  controlled_approaches=("east",),
                                  median_extra_width=median_extra_width_m(
                                      _edge_for_approach(network, node.id, "east"))),
                )
                crosswalks.extend(item for item in candidates
                                  if item.controlled_approaches[0] in connected
                                  and (stop_approaches is None or
                                       item.controlled_approaches[0] in stop_approaches))
            if "east_west" in node.crossings:
                candidates = (
                    CrosswalkPlan(f"{node.id}_south", node.id,
                                  (x, y - north_south_crossing_offset), "x",
                                  north_south_width,
                                  controlled_approaches=("south",),
                                  median_extra_width=median_extra_width_m(
                                      _edge_for_approach(network, node.id, "south"))),
                    CrosswalkPlan(f"{node.id}_north", node.id,
                                  (x, y + north_south_crossing_offset), "x",
                                  north_south_width,
                                  controlled_approaches=("north",),
                                  median_extra_width=median_extra_width_m(
                                      _edge_for_approach(network, node.id, "north"))),
                )
                crosswalks.extend(item for item in candidates
                                  if item.controlled_approaches[0] in connected
                                  and (stop_approaches is None or
                                       item.controlled_approaches[0] in stop_approaches))
        elif node.kind == "signalized_pedestrian_crossing":
            walking_axis = "y" if "north_south" in node.crossings else "x"
            crosswalks.append(CrosswalkPlan(node.id, node.id, node.position, walking_axis, 6.5, 4.0,
                                            ("west", "east") if walking_axis == "y"
                                            else ("south", "north")))
    return tuple(crosswalks)


def _tactile_tile_run(plans, prefix, start, end, axis, kind="guidance", rows=1):
    """Tile a straight run exactly, using one short tile for the remainder."""
    sx, sy = start
    ex, ey = end
    length = abs((ex - sx) if axis == "x" else (ey - sy))
    if length < 0.005:
        return
    sign = 1.0 if ((ex - sx) if axis == "x" else (ey - sy)) >= 0 else -1.0
    full = int(length // TACTILE_TILE_M)
    remainder = length - full * TACTILE_TILE_M
    lengths = [TACTILE_TILE_M] * full
    if remainder >= 0.06:
        lengths.append(remainder)
    elif remainder > 1e-6 and lengths:
        # Never leave a hairline gap. Share a very short remainder with the
        # preceding full tile so both adjustment blocks remain manufacturable.
        shared = (lengths.pop() + remainder) * 0.5
        lengths.extend((shared, shared))
    elif remainder > 1e-6:
        lengths.append(remainder)
    cursor = 0.0
    for index, tile_length in enumerate(lengths):
        along = cursor + tile_length * 0.5
        for row in range(rows):
            across = (row - (rows - 1) * 0.5) * TACTILE_TILE_M
            if axis == "x":
                center = (sx + sign * along, sy + across)
                size = (tile_length, TACTILE_TILE_M)
            else:
                center = (sx + across, sy + sign * along)
                size = (TACTILE_TILE_M, tile_length)
            plans.append(TactileTilePlan(
                f"{prefix}_{index}_{row}", kind, center, size, axis,
            ))
        cursor += tile_length


def plan_tactile_paving(network: RoadNetwork,
                        crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[TactileTilePlan, ...]:
    """Plan JIS-style tactile routes from road-level opt-in settings."""
    plans = []
    junction_kinds = {"signalized_cross", "signalized_t_junction",
                      "stop_cross", "stop_t_junction", "priority_t_junction"}
    for edge in network.edges:
        if not edge.tactile_paving or edge.sidewalks != "both":
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        a = list(start)
        b = list(end)
        for node_id, sign in ((edge.start, 1.0), (edge.end, -1.0)):
            node = network.nodes[node_id]
            if node.kind not in junction_kinds:
                continue
            ew_width, ns_width = road_widths_at_node(network, node_id)
            perpendicular = ns_width if abs(ux) > 0.5 else ew_width
            trim = perpendicular * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M
            target = a if node_id == edge.start else b
            target[0] += ux * trim * sign
            target[1] += uy * trim * sign
        road_half = road_half_width_m(edge)
        offset = road_half + SIDEWALK_WIDTH_M - TACTILE_ROUTE_BACK_EDGE_OFFSET_M
        for side in (-1.0, 1.0):
            run_start = (a[0] + nx * offset * side, a[1] + ny * offset * side)
            run_end = (b[0] + nx * offset * side, b[1] + ny * offset * side)
            _tactile_tile_run(plans, f"{edge.id}_{'left' if side > 0 else 'right'}",
                              run_start, run_end, "x" if abs(ux) > 0.5 else "y")

    # When both roads carry a route, bridge their tangent points with the
    # square L-shaped corner shown in the standard intersection layout.
    for node in network.nodes.values():
        if node.kind not in junction_kinds:
            continue
        connected = set(connected_approaches(network, node.id))
        ew_width, ns_width = road_widths_at_node(network, node.id)
        for qx, qy, horizontal_approach, vertical_approach in (
            (-1, -1, "west", "south"), (-1, 1, "west", "north"),
            (1, -1, "east", "south"), (1, 1, "east", "north"),
        ):
            if horizontal_approach not in connected or vertical_approach not in connected:
                continue
            horizontal_edge = _edge_for_approach(network, node.id, horizontal_approach)
            vertical_edge = _edge_for_approach(network, node.id, vertical_approach)
            horizontal_enabled = bool(horizontal_edge and horizontal_edge.tactile_paving
                                      and horizontal_edge.sidewalks == "both")
            vertical_enabled = bool(vertical_edge and vertical_edge.tactile_paving
                                    and vertical_edge.sidewalks == "both")
            if not (horizontal_enabled or vertical_enabled):
                continue
            route_x = node.position[0] + qx * (
                ns_width * 0.5 + SIDEWALK_WIDTH_M - TACTILE_ROUTE_BACK_EDGE_OFFSET_M)
            route_y = node.position[1] + qy * (
                ew_width * 0.5 + SIDEWALK_WIDTH_M - TACTILE_ROUTE_BACK_EDGE_OFFSET_M)
            tangent_x = node.position[0] + qx * (
                ns_width * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M)
            tangent_y = node.position[1] + qy * (
                ew_width * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M)
            prefix = f"{node.id}_{qx:+d}_{qy:+d}_corner"
            for ix in (-0.5, 0.5):
                for iy in (-0.5, 0.5):
                    plans.append(TactileTilePlan(
                        f"{prefix}_warning_{ix:+g}_{iy:+g}", "warning",
                        (route_x + ix * TACTILE_TILE_M,
                         route_y + iy * TACTILE_TILE_M),
                    ))
            horizontal_end = (tangent_x if horizontal_enabled else
                              node.position[0] + qx * (
                                  ns_width * 0.5 + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
                                  - TACTILE_TILE_M))
            vertical_end = (tangent_y if vertical_enabled else
                            node.position[1] + qy * (
                                ew_width * 0.5 + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
                                - TACTILE_TILE_M))
            _tactile_tile_run(plans, f"{prefix}_horizontal",
                              (horizontal_end, route_y), (route_x, route_y), "x")
            _tactile_tile_run(plans, f"{prefix}_vertical",
                              (route_x, route_y), (route_x, vertical_end), "y")

        # A T-junction has one uninterrupted back sidewalk opposite its stem.
        # When the through road carries tactile paving, bridge its two split
        # edges across that back side. The stem-only case intentionally adds
        # nothing here.
        if node.kind in {"signalized_t_junction", "stop_t_junction",
                         "priority_t_junction"}:
            missing = next((direction for direction in ("west", "east", "south", "north")
                            if direction not in connected), None)
            if missing in {"north", "south"}:
                through_approaches = ("west", "east")
                through_edges = tuple(_edge_for_approach(network, node.id, item)
                                      for item in through_approaches)
                if all(edge and edge.tactile_paving and edge.sidewalks == "both"
                       for edge in through_edges):
                    side = 1 if missing == "north" else -1
                    route_y = node.position[1] + side * (
                        ew_width * 0.5 + SIDEWALK_WIDTH_M
                        - TACTILE_ROUTE_BACK_EDGE_OFFSET_M)
                    extent = ns_width * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M
                    _tactile_tile_run(
                        plans, f"{node.id}_back_connection",
                        (node.position[0] - extent, route_y),
                        (node.position[0] + extent, route_y), "x",
                    )
            elif missing in {"west", "east"}:
                through_approaches = ("south", "north")
                through_edges = tuple(_edge_for_approach(network, node.id, item)
                                      for item in through_approaches)
                if all(edge and edge.tactile_paving and edge.sidewalks == "both"
                       for edge in through_edges):
                    side = 1 if missing == "east" else -1
                    route_x = node.position[0] + side * (
                        ns_width * 0.5 + SIDEWALK_WIDTH_M
                        - TACTILE_ROUTE_BACK_EDGE_OFFSET_M)
                    extent = ew_width * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M
                    _tactile_tile_run(
                        plans, f"{node.id}_back_connection",
                        (route_x, node.position[1] - extent),
                        (route_x, node.position[1] + extent), "y",
                    )

    # Each corner served by either adjoining tactile road receives both
    # crossing branches: 11x2 warning, 2x6 guidance and a 2x2 warning junction.
    for crossing in crosswalks:
        approach = crossing.controlled_approaches[0] if crossing.controlled_approaches else ""
        axis = crossing.walking_axis
        across_axis = "y" if axis == "x" else "x"
        for endpoint_sign in (-1.0, 1.0):
            source = (_edge_for_approach(network, crossing.node_id, approach)
                      if approach else None)
            enabled = bool(source and source.tactile_paving and source.sidewalks == "both")
            node = network.nodes[crossing.node_id]
            if node.kind in junction_kinds and approach:
                perpendicular_approach = (
                    ("north" if endpoint_sign > 0 else "south")
                    if axis == "y" else
                    ("east" if endpoint_sign > 0 else "west")
                )
                perpendicular = _edge_for_approach(
                    network, crossing.node_id, perpendicular_approach,
                )
                enabled = enabled or bool(
                    perpendicular and perpendicular.tactile_paving
                    and perpendicular.sidewalks == "both"
                )
            if not enabled:
                continue
            for forward_index in range(2):
                forward = endpoint_sign * (
                    crossing.road_width * 0.5 + TACTILE_CROSSING_EDGE_CLEARANCE_M
                    + (forward_index + 0.5) * TACTILE_TILE_M)
                for across_index in range(11):
                    across = (across_index - 5) * TACTILE_TILE_M
                    center = ((crossing.center[0] + forward, crossing.center[1] + across)
                              if axis == "x" else
                              (crossing.center[0] + across, crossing.center[1] + forward))
                    plans.append(TactileTilePlan(
                        f"{crossing.id}_{endpoint_sign:+g}_warning_{forward_index}_{across_index}",
                        "warning", center,
                    ))
            guide_start_distance = (crossing.road_width * 0.5
                                    + TACTILE_CROSSING_EDGE_CLEARANCE_M
                                    + 2 * TACTILE_TILE_M)
            for row in range(2):
                lateral = (row - 0.5) * TACTILE_TILE_M
                start = ((crossing.center[0] + endpoint_sign * guide_start_distance,
                          crossing.center[1] + lateral)
                         if axis == "x" else
                         (crossing.center[0] + lateral,
                          crossing.center[1] + endpoint_sign * guide_start_distance))
                end = ((start[0] + endpoint_sign * 6 * TACTILE_TILE_M, start[1])
                       if axis == "x" else
                       (start[0], start[1] + endpoint_sign * 6 * TACTILE_TILE_M))
                _tactile_tile_run(plans, f"{crossing.id}_{endpoint_sign:+g}_guide_{row}",
                                  start, end, axis)
            terminal_distance = (crossing.road_width * 0.5
                                 + TACTILE_CROSSING_EDGE_CLEARANCE_M
                                 + 8 * TACTILE_TILE_M)
            for forward_index in range(2):
                for across_index in range(2):
                    forward = endpoint_sign * (terminal_distance + (forward_index + 0.5) * TACTILE_TILE_M)
                    across = (across_index - 0.5) * TACTILE_TILE_M
                    center = ((crossing.center[0] + forward, crossing.center[1] + across)
                              if axis == "x" else
                              (crossing.center[0] + across, crossing.center[1] + forward))
                    plans.append(TactileTilePlan(
                        f"{crossing.id}_{endpoint_sign:+g}_terminal_{forward_index}_{across_index}",
                        "warning", center, guidance_axis=across_axis,
                    ))
    # Warning surfaces replace, rather than cover, guidance ribs. Split any
    # intersecting guidance tile at warning boundaries so no overlap or gap is
    # introduced, including short adjustment blocks.
    warnings = tuple(item for item in plans if item.kind == "warning")
    resolved = [item for item in plans if item.kind == "warning"]
    for tile in (item for item in plans if item.kind == "guidance"):
        axis_index = 0 if tile.guidance_axis == "x" else 1
        across_index = 1 - axis_index
        along_size = tile.size[axis_index]
        across_size = tile.size[across_index]
        along_center = tile.center[axis_index]
        across_center = tile.center[across_index]
        intervals = [(along_center - along_size * 0.5,
                      along_center + along_size * 0.5)]
        for warning in warnings:
            warning_across_size = warning.size[across_index]
            if abs(across_center - warning.center[across_index]) >= (
                    across_size + warning_across_size) * 0.5 - 1e-6:
                continue
            cut_start = warning.center[axis_index] - warning.size[axis_index] * 0.5
            cut_end = warning.center[axis_index] + warning.size[axis_index] * 0.5
            next_intervals = []
            for start, end in intervals:
                if cut_end <= start + 1e-6 or cut_start >= end - 1e-6:
                    next_intervals.append((start, end))
                    continue
                if cut_start - start >= 0.01:
                    next_intervals.append((start, cut_start))
                if end - cut_end >= 0.01:
                    next_intervals.append((cut_end, end))
            intervals = next_intervals
        for part, (start, end) in enumerate(intervals):
            center = list(tile.center)
            size = list(tile.size)
            center[axis_index] = (start + end) * 0.5
            size[axis_index] = end - start
            resolved.append(TactileTilePlan(
                f"{tile.id}_part_{part}", tile.kind, tuple(center), tuple(size),
                tile.guidance_axis,
            ))
    return tuple(resolved)


def _roadside_feature_trims(network, edge, crosswalks, clearance=0.55):
    """Return the guardrail-derived longitudinal roadside envelope."""
    start = network.nodes[edge.start].position
    end = network.nodes[edge.end].position
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    left_x, left_y = -uy, ux
    horizontal = abs(ux) > 0.5

    def intersection_trim(node_id):
        node = network.nodes[node_id]
        if node.kind not in {"signalized_cross", "signalized_t_junction",
                             "stop_cross", "stop_t_junction",
                             "priority_t_junction"}:
            return 0.0
        east_west_width, north_south_width = road_widths_at_node(network, node_id)
        perpendicular_width = north_south_width if horizontal else east_west_width
        return perpendicular_width * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M

    start_trim, end_trim = intersection_trim(edge.start), intersection_trim(edge.end)
    for crossing in crosswalks:
        rel_x, rel_y = crossing.center[0] - start[0], crossing.center[1] - start[1]
        projection = rel_x * ux + rel_y * uy
        perpendicular = abs(rel_x * left_x + rel_y * left_y)
        half_span = crossing.crosswalk_width * 0.5
        if ((crossing.node_id not in {edge.start, edge.end} and perpendicular > 1e-5)
                or projection < -half_span or projection > length + half_span):
            continue
        trim = projection + half_span + clearance
        reverse_trim = length - projection + half_span + clearance
        if crossing.node_id == edge.start:
            start_trim = max(start_trim, trim)
        elif crossing.node_id == edge.end:
            end_trim = max(end_trim, reverse_trim)
        elif projection <= length * 0.5:
            start_trim = max(start_trim, trim)
        else:
            end_trim = max(end_trim, reverse_trim)
    return start_trim, end_trim


def plan_guardrails(network: RoadNetwork,
                    crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[GuardrailPlan, ...]:
    """Derive edge-side guard fences and trim them clear of crosswalks."""
    plans = []
    post_offset_from_road_edge = 0.22
    for edge in network.edges:
        config = edge.guardrail
        if config is None or config.sides == "none":
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        left_x, left_y = -uy, ux
        start_trim, end_trim = _roadside_feature_trims(network, edge, crosswalks)
        usable_length = length - start_trim - end_trim
        if usable_length <= 0.5:
            continue
        sides = ("left", "right") if config.sides == "both" else (config.sides,)
        road_half_width = road_half_width_m(edge)
        offset = road_half_width + post_offset_from_road_edge
        elevation = GUARDRAIL_BASE_Z_M if edge.sidewalks == "both" else ROAD_TOP_Z_M
        for side in sides:
            sign = 1.0 if side == "left" else -1.0
            a = (start[0] + ux * start_trim + left_x * sign * offset,
                 start[1] + uy * start_trim + left_y * sign * offset)
            b = (end[0] - ux * end_trim + left_x * sign * offset,
                 end[1] - uy * end_trim + left_y * sign * offset)
            # A fence on the left has the road on its right and vice versa.
            beam_side = "right" if side == "left" else "left"
            plans.append(GuardrailPlan(
                f"{edge.id}_{side}_guardrail", edge.id, side, a, b,
                config.exterior_color, beam_side, elevation,
            ))
    guardrail_radius = SIDEWALK_CORNER_RADIUS_M - post_offset_from_road_edge
    for node in network.nodes.values():
        if node.kind not in {"signalized_cross", "signalized_t_junction",
                             "stop_cross", "stop_t_junction",
                             "priority_t_junction"}:
            continue
        if _corner_barrier_kind(node.id) != "guardrail":
            continue
        east_west_width, north_south_width = road_widths_at_node(network, node.id)
        for label, qx, qy, first, second, start_angle, sweep in _CORNER_ARCS:
            sources = _corner_sources(network, node.id, qx, qy, first, second,
                                      "guardrail")
            if sources is None:
                continue
            edges, configs = sources
            center = (
                node.position[0] + qx * (north_south_width * 0.5
                                         + SIDEWALK_CORNER_RADIUS_M),
                node.position[1] + qy * (east_west_width * 0.5
                                         + SIDEWALK_CORNER_RADIUS_M),
            )
            plans.append(GuardrailPlan(
                f"{node.id}_{label}_corner_guardrail",
                "+".join(edge.id for edge in edges), label, center, center,
                configs[0].exterior_color, "right", GUARDRAIL_BASE_Z_M,
                center, guardrail_radius, start_angle + sweep * 0.25, sweep * 0.5,
            ))
    return tuple(plans)


def plan_plantings(network: RoadNetwork,
                   crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[PlantingPlan, ...]:
    """Derive identical planting beds on both sides of configured edges."""
    plans = []
    bed_width = 0.85
    bed_near_edge_offset = 0.33
    for edge in network.edges:
        config = edge.planting
        if config is None:
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        left_x, left_y = -uy, ux
        start_trim, end_trim = _roadside_feature_trims(network, edge, crosswalks)

        if length - start_trim - end_trim <= 0.5:
            continue
        road_half_width = road_half_width_m(edge)
        offset = road_half_width + bed_near_edge_offset + bed_width * 0.5
        for side in ("left", "right"):
            sign = 1.0 if side == "left" else -1.0
            a = (start[0] + ux * start_trim + left_x * sign * offset,
                 start[1] + uy * start_trim + left_y * sign * offset)
            b = (end[0] - ux * end_trim + left_x * sign * offset,
                 end[1] - uy * end_trim + left_y * sign * offset)
            base_seed = config.seed if config.seed is not None else 0
            # Blender custom integer properties are signed 32-bit values.
            seed = zlib.crc32(f"{edge.id}:{side}".encode("utf-8"), base_seed) & 0x7FFFFFFF
            plans.append(PlantingPlan(
                f"{edge.id}_{side}_planting", edge.id, side, a, b, bed_width,
                config.density, config.maintenance, config.health, seed,
                PLANTING_INSTANCE_Z_M, style=config.style,
            ))

    planting_radius = (SIDEWALK_CORNER_RADIUS_M - bed_near_edge_offset
                       - bed_width * 0.5)
    for node in network.nodes.values():
        if node.kind not in {"signalized_cross", "signalized_t_junction",
                             "stop_cross", "stop_t_junction",
                             "priority_t_junction"}:
            continue
        east_west_width, north_south_width = road_widths_at_node(network, node.id)
        for label, qx, qy, first, second, start_angle, sweep in _CORNER_ARCS:
            sources = _corner_sources(network, node.id, qx, qy, first, second,
                                      "planting")
            if sources is None:
                continue
            edges, configs = sources
            center = (
                node.position[0] + qx * (north_south_width * 0.5
                                         + SIDEWALK_CORNER_RADIUS_M),
                node.position[1] + qy * (east_west_width * 0.5
                                         + SIDEWALK_CORNER_RADIUS_M),
            )
            density = sum(item.density for item in configs) * 0.5
            maintenance = sum(item.maintenance for item in configs) * 0.5
            health = sum(item.health for item in configs) * 0.5
            source_seeds = ":".join(str(item.seed if item.seed is not None else 0)
                                    for item in configs)
            seed = zlib.crc32(
                f"{node.id}:{label}:corner:{source_seeds}".encode("utf-8")
            ) & 0x7FFFFFFF
            plans.append(PlantingPlan(
                f"{node.id}_{label}_corner_planting",
                "+".join(edge.id for edge in edges), label, center, center,
                bed_width, density, maintenance, health, seed,
                PLANTING_INSTANCE_Z_M,
                center, planting_radius, start_angle + sweep * 0.25, sweep * 0.5,
                "clipped_hedge" if all(item.style == "clipped_hedge" for item in configs)
                else "legacy",
            ))

    # A T-junction's missing road is a continuous sidewalk, not carriageway.
    # Bridge the two collinear planting beds across that back sidewalk when
    # both adjoining main-road edges opt into planting. A four-way junction
    # never enters this branch because there is no missing approach.
    opposite = {"west": "east", "east": "west", "south": "north", "north": "south"}
    for node in network.nodes.values():
        if node.kind not in {"signalized_t_junction", "stop_t_junction",
                             "priority_t_junction"}:
            continue
        connected = set(connected_approaches(network, node.id))
        missing = ({"west", "east", "south", "north"} - connected).pop()
        stem = opposite[missing]
        main_directions = connected - {stem}
        approach_map = _compatibility_approach_map(network, node.id)
        configs = []
        for direction in main_directions:
            edge = next((item for item in network.edges
                         if node.id in {item.start, item.end}
                         and approach_map.get(item.id) == direction), None)
            if edge is None or edge.planting is None:
                configs = []
                break
            configs.append(edge.planting)
        if len(configs) != 2:
            continue
        east_west_width, north_south_width = road_widths_at_node(network, node.id)
        x, y = node.position
        if missing in {"north", "south"}:
            sign = 1.0 if missing == "north" else -1.0
            span = north_south_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
            bed_y = y + sign * (east_west_width * 0.5
                                + bed_near_edge_offset + bed_width * 0.5)
            start, end = (x - span, bed_y), (x + span, bed_y)
        else:
            sign = 1.0 if missing == "east" else -1.0
            span = east_west_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
            bed_x = x + sign * (north_south_width * 0.5
                                + bed_near_edge_offset + bed_width * 0.5)
            start, end = (bed_x, y - span), (bed_x, y + span)
        density = sum(item.density for item in configs) * 0.5
        maintenance = sum(item.maintenance for item in configs) * 0.5
        health = sum(item.health for item in configs) * 0.5
        source_seeds = ":".join(str(item.seed if item.seed is not None else 0)
                                for item in configs)
        seed = zlib.crc32(f"{node.id}:back:{source_seeds}".encode("utf-8")) & 0x7FFFFFFF
        edge_id = f"{node.id}_back_sidewalk"
        plans.append(PlantingPlan(
            f"{edge_id}_planting", edge_id, "back", start, end, bed_width,
            density, maintenance, health, seed, PLANTING_INSTANCE_Z_M,
            style=("clipped_hedge" if all(item.style == "clipped_hedge" for item in configs)
                   else "legacy"),
        ))
    return tuple(plans)


def _fixed_spacing_positions(length: float, spacing: float,
                             fill_to_ends: bool = False) -> tuple[float, ...]:
    """Return exact-spacing stations, symmetrically inset from both ends."""
    count = int(length // spacing) + (1 if fill_to_ends else 0)
    if count < 1:
        return ()
    occupied = (count - 1) * spacing
    margin = (length - occupied) * 0.5
    return tuple(margin + index * spacing for index in range(count))


def _junction_biased_spacing_positions(length: float, spacing: float,
                                       near_start: bool,
                                       near_end: bool,
                                       fill_to_ends: bool = False) -> tuple[float, ...]:
    """Keep exact spacing while moving a one-ended run toward its junction."""
    positions = _fixed_spacing_positions(length, spacing, fill_to_ends)
    if not positions or near_start == near_end:
        return positions
    desired = spacing * STREET_LIGHT_JUNCTION_ADVANCE_FRACTION
    if near_start:
        shift = -min(desired, positions[0])
    else:
        shift = min(desired, length - positions[-1])
    return tuple(position + shift for position in positions)


def plan_street_lights(network: RoadNetwork,
                       crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[StreetLightPlan, ...]:
    """Place fixed-spacing road and footway lights inside guardrail trims."""
    plantings = {
        (item.edge_id, item.side): item
        for item in plan_plantings(network, crosswalks)
        if item.curve_center is None
    }
    lit = network.scene.time_of_day == "night"
    plans = []
    for edge in network.edges:
        if not edge.street_lights:
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        start_trim, end_trim = _roadside_feature_trims(network, edge, crosswalks)
        pedestrian_start_trim, pedestrian_end_trim = _roadside_feature_trims(
            network, edge, crosswalks,
            clearance=PEDESTRIAN_STREET_LIGHT_CROSSWALK_CLEARANCE_M)
        junction_kinds = {
            "signalized_cross", "signalized_t_junction", "stop_cross",
            "stop_t_junction", "priority_t_junction",
        }
        near_start = network.nodes[edge.start].kind in junction_kinds
        near_end = network.nodes[edge.end].kind in junction_kinds

        def priority_through(node_id):
            node = network.nodes[node_id]
            if node.kind != "priority_t_junction" or not edge.road_id:
                return False
            return sum(
                candidate.road_id == edge.road_id
                for candidate in network.edges
                if node_id in {candidate.start, candidate.end}
            ) == 2

        if priority_through(edge.start):
            start_trim, near_start = 0.0, False
        if priority_through(edge.end):
            end_trim, near_end = 0.0, False
        usable = length - start_trim - end_trim
        if usable <= 0:
            continue
        heading = math.degrees(math.atan2(uy, ux))
        if edge.median:
            for index, along in enumerate(_junction_biased_spacing_positions(
                    usable, ROADWAY_STREET_LIGHT_SPACING_M,
                    near_start, near_end), 1):
                station = start_trim + along
                plans.append(StreetLightPlan(
                    f"{edge.id}_roadway_street_light_{index:02d}", edge.id,
                    "roadway", "center",
                    (start[0] + ux * station, start[1] + uy * station, 0.24),
                    heading + 90.0, lit,
                ))
        if edge.sidewalks != "both":
            continue
        for side in ("left", "right"):
            planting = plantings.get((edge.id, side))
            side_sign = 1.0 if side == "left" else -1.0
            lateral = side_sign * (
                road_half_width_m(edge) + 0.33 + 0.85 * 0.5)
            if planting is None:
                normal = (-uy, ux)
                pedestrian_start = (
                    start[0] + ux * pedestrian_start_trim + normal[0] * lateral,
                    start[1] + uy * pedestrian_start_trim + normal[1] * lateral,
                )
                pedestrian_end = (
                    end[0] - ux * pedestrian_end_trim + normal[0] * lateral,
                    end[1] - uy * pedestrian_end_trim + normal[1] * lateral,
                )
                elevation = SIDEWALK_TOP_Z_M
            else:
                planting_start_station = ((planting.start[0] - start[0]) * ux
                                          + (planting.start[1] - start[1]) * uy)
                planting_end_station = ((planting.end[0] - start[0]) * ux
                                        + (planting.end[1] - start[1]) * uy)
                if planting_end_station < planting_start_station:
                    planting_start_station, planting_end_station = (
                        planting_end_station, planting_start_station)
                allowed_start = max(planting_start_station,
                                    pedestrian_start_trim)
                allowed_end = min(planting_end_station,
                                  length - pedestrian_end_trim)
                normal = (-uy, ux)
                pedestrian_start = (
                    start[0] + ux * allowed_start + normal[0] * lateral,
                    start[1] + uy * allowed_start + normal[1] * lateral,
                )
                pedestrian_end = (
                    start[0] + ux * allowed_end + normal[0] * lateral,
                    start[1] + uy * allowed_end + normal[1] * lateral,
                )
                elevation = planting.elevation + 0.06
            pdx = pedestrian_end[0] - pedestrian_start[0]
            pdy = pedestrian_end[1] - pedestrian_start[1]
            planting_length = math.hypot(pdx, pdy)
            if planting_length <= 1e-6:
                continue
            pux, puy = pdx / planting_length, pdy / planting_length
            for index, along in enumerate(_junction_biased_spacing_positions(
                    planting_length, PEDESTRIAN_STREET_LIGHT_SPACING_M,
                    near_start, near_end, fill_to_ends=True), 1):
                plans.append(StreetLightPlan(
                    f"{edge.id}_{side}_pedestrian_street_light_{index:02d}",
                    edge.id, "pedestrian", side,
                    (pedestrian_start[0] + pux * along,
                     pedestrian_start[1] + puy * along,
                     elevation),
                    heading, lit,
                ))
    return tuple(plans)


def plan_street_trees(network: RoadNetwork,
                      crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[StreetTreePlan, ...]:
    """Place reproducible trees along the planting centreline on both edge sides."""
    from .streets import street_stations, seed_for
    from .geometry import Centerline
    paths = {e.id: Centerline.from_edge(network, e) for e in network.edges}
    frames = street_stations(network, paths)
    planting_by_edge_side = {
        (item.edge_id, item.side): item
        for item in plan_plantings(network, crosswalks)
        if item.curve_center is None
    }
    plans = []
    for edge in network.edges:
        config = edge.street_trees
        if config is None or not config.enabled:
            continue
        for side in ("left", "right"):
            planting = planting_by_edge_side.get((edge.id, side))
            if planting is None:
                continue
            start = planting.start
            end = planting.end
            dx, dy = end[0] - start[0], end[1] - start[1]
            full_length = math.hypot(dx, dy)
            junction_kinds = {"signalized_cross", "signalized_t_junction",
                              "stop_cross", "stop_t_junction",
                              "priority_t_junction",
                              "signalized_pedestrian_crossing"}
            start_clearance = (STREET_TREE_END_CLEARANCE_M
                               if network.nodes[edge.start].kind in junction_kinds else 0.0)
            end_clearance = (STREET_TREE_END_CLEARANCE_M
                             if network.nodes[edge.end].kind in junction_kinds else 0.0)
            if full_length <= start_clearance + end_clearance:
                continue
            ux, uy = dx / full_length, dy / full_length
            start = (start[0] + ux * start_clearance,
                     start[1] + uy * start_clearance)
            end = (end[0] - ux * end_clearance,
                   end[1] - uy * end_clearance)
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            base_seed = config.seed if config.seed is not None else 0
            nominal_spacing = 10.0 / config.density
            frame = frames[edge.id]
            origin = network.nodes[edge.start].position
            tip = network.nodes[edge.end].position
            chord_length = math.dist(origin, tip)
            chord_axis = ((tip[0]-origin[0])/chord_length, (tip[1]-origin[1])/chord_length)
            start_station = ((start[0]-origin[0])*chord_axis[0] + (start[1]-origin[1])*chord_axis[1])
            ratio = paths[edge.id].length / chord_length
            canonical_side = side if frame.direction == 1 else ('right' if side == 'left' else 'left')
            for station, index in frame.positions(start_station*ratio,
                    (start_station+length)*ratio, nominal_spacing,
                    seed_for(base_seed, canonical_side), jitter=.11):
                fraction = (station/ratio-start_station)/length
                point = (start[0]+dx*fraction, start[1]+dy*fraction)
                seed = seed_for(frame.identity, canonical_side, index, base_seed, 'tree')
                rotation = seed_for(seed,'rotation') % 36000 / 100.0
                plans.append(StreetTreePlan(
                    f"{frame.identity}_{canonical_side}_street_tree_{index:04d}",
                    edge.id, side, (*point, planting.elevation + 0.06),
                    config.species, seed, rotation,
                ))
    pedestrian_lights = [item for item in plan_street_lights(network, crosswalks)
                         if item.kind == "pedestrian"]
    curved_edges = {edge.id for edge in network.edges
                    if edge.geometry is not None
                    and edge.geometry.kind == "cubic_bezier"}
    clearance_sq = STREET_LIGHT_TREE_CLEARANCE_M ** 2
    return tuple(item for item in plans if all(
        item.edge_id in curved_edges
        or item.edge_id != light.edge_id or item.side != light.side
        or ((item.location[0] - light.location[0]) ** 2
            + (item.location[1] - light.location[1]) ** 2) >= clearance_sq
        for light in pedestrian_lights
    ))


def plan_corner_reflector_poles(network: RoadNetwork) -> tuple[ReflectorPolePlan, ...]:
    """Reflector poles are disabled; eligible corners use guardrails."""
    return ()


def plan_medians(network: RoadNetwork,
                 crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[MedianPlan, ...]:
    """Plan narrow raised medians, deriving their ends from crosswalk extents."""
    plans = []
    crosswalk_clearance = 0.15
    for edge in network.edges:
        if not edge.median:
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        left_x, left_y = -uy, ux
        start_trim = 1.0 if network.nodes[edge.start].kind == "boundary" else 0.0
        end_trim = 1.0 if network.nodes[edge.end].kind == "boundary" else 0.0
        rounded_start = False
        rounded_end = False
        for crossing in crosswalks:
            if crossing.node_id in {edge.start, edge.end}:
                outward_approach = _compatibility_approach_map(
                    network, crossing.node_id).get(edge.id)
                if (outward_approach is not None
                        and outward_approach not in crossing.controlled_approaches):
                    continue
            rel_x = crossing.center[0] - start[0]
            rel_y = crossing.center[1] - start[1]
            projection = rel_x * ux + rel_y * uy
            perpendicular = abs(rel_x * left_x + rel_y * left_y)
            half_span = crossing.crosswalk_width * 0.5
            if ((crossing.node_id not in {edge.start, edge.end}
                 and perpendicular > 1e-5)
                    or projection < -half_span or projection > length + half_span):
                continue
            # Use the owning node rather than the segment midpoint. On a short
            # boundary segment, a wide junction's crosswalk can legitimately
            # lie beyond that midpoint.
            if crossing.node_id == edge.start:
                start_trim = max(start_trim, projection + half_span + crosswalk_clearance)
                rounded_start = True
            elif crossing.node_id == edge.end:
                end_trim = max(end_trim, length - projection + half_span + crosswalk_clearance)
                rounded_end = True
            elif projection <= length * 0.5:
                start_trim = max(start_trim, projection + half_span + crosswalk_clearance)
                rounded_start = True
            else:
                end_trim = max(end_trim, length - projection + half_span + crosswalk_clearance)
                rounded_end = True
        if length - start_trim - end_trim <= 0.5:
            continue
        median_width = median_physical_width_m(edge)
        cap_depth = MEDIAN_NARROW_WIDTH_M * 0.5
        median_start = start_trim + (cap_depth if rounded_start else 0.0)
        median_end = end_trim + (cap_depth if rounded_end else 0.0)
        plans.append(MedianPlan(
            f"{edge.id}_median", edge.id,
            (start[0] + ux * median_start, start[1] + uy * median_start),
            (end[0] - ux * median_end, end[1] - uy * median_end),
            median_width,
            rounded_start=rounded_start, rounded_end=rounded_end,
        ))

        # Add a separate island on the junction side of each crosswalk. Its
        # crosswalk-facing end is square; the nose facing the junction is round.
        for endpoint, node_id, outward_x, outward_y in (
            ("start", edge.start, ux, uy),
            ("end", edge.end, -ux, -uy),
        ):
            node = network.nodes[node_id]
            if node.kind not in {"signalized_cross", "signalized_t_junction"}:
                continue
            outward_approach = _compatibility_approach_map(
                network, node_id).get(edge.id, _cardinal(outward_x, outward_y))
            crossing = next((item for item in crosswalks
                             if item.node_id == node_id
                             and outward_approach in item.controlled_approaches), None)
            if crossing is None:
                continue
            endpoint_key = "from" if endpoint == "start" else "to"
            extra_here = has_extra_inbound_lane(edge, endpoint_key)
            reserve_here = has_extra_inbound_reserve(edge, endpoint_key)
            junction_median_width = (
                MEDIAN_NARROW_WIDTH_M + MEDIAN_WIDE_EXTRA_M
                if reserve_here else
                (MEDIAN_NARROW_WIDTH_M if extra_here else median_width))
            arm_left_x, arm_left_y = -outward_y, outward_x
            median_shift = LANE_WIDTH_M * 0.5 if extra_here else 0.0
            node_x, node_y = node.position
            east_west_width, north_south_width = road_widths_at_node(network, node_id)
            # Compatibility crosswalk plans store cardinal world coordinates.
            # Projecting those coordinates onto a rotated arm shortens the
            # semantic distance by cos(rotation), and can incorrectly erase
            # the junction-side island. Its station is defined in the arm
            # frame: perpendicular carriageway half-width + fixed offset.
            perpendicular_width = (
                north_south_width if outward_approach in {"east", "west"}
                else east_west_width
            )
            projection = (perpendicular_width * 0.5
                          + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M)
            square_end_distance = (
                projection - crossing.crosswalk_width * 0.5 - crosswalk_clearance
            )
            intersection_edge = (
                perpendicular_width * 0.5
            )
            # The rounded cap extends half its width toward the junction, so
            # place its centre half a width beyond the intersection boundary.
            full_rounded_center_distance = intersection_edge + cap_depth
            if square_end_distance - full_rounded_center_distance <= 0.5:
                continue
            rounded_center_distance = (
                square_end_distance
                - (square_end_distance - full_rounded_center_distance) * 0.5
            )
            plans.append(MedianPlan(
                f"{edge.id}_{endpoint}_intersection_median", edge.id,
                (node_x + outward_x * rounded_center_distance
                 + arm_left_x * median_shift,
                 node_y + outward_y * rounded_center_distance
                 + arm_left_y * median_shift),
                (node_x + outward_x * (square_end_distance - cap_depth)
                 + arm_left_x * median_shift,
                 node_y + outward_y * (square_end_distance - cap_depth)
                 + arm_left_y * median_shift),
                junction_median_width, 0.24, True, node_id, outward_approach,
                True,
            ))
    return tuple(plans)


def plan_median_island_devices(
        network: RoadNetwork, medians: tuple[MedianPlan, ...],
        signal_sites: tuple[SignalSite, ...] = (),
        seed: int = 20260819,
) -> tuple[MedianIslandDevicePlan, ...]:
    """Choose one consistent island device family per intersection."""
    plans = []
    multilane_device_by_node = {}
    for median in medians:
        if not median.node_id:
            continue
        start_x, start_y = median.start
        end_x, end_y = median.end
        dx, dy = end_x - start_x, end_y - start_y
        heading = math.degrees(math.atan2(dy, dx))
        east_west_width, north_south_width = road_widths_at_node(network, median.node_id)
        both_roads_multilane = (
            east_west_width >= 4 * LANE_WIDTH_M
            and north_south_width >= 4 * LANE_WIDTH_M
        )
        if both_roads_multilane:
            # This condition formerly forced a warning lamp. Choose once per
            # junction so all its islands agree, while additions elsewhere in
            # the graph cannot perturb the result.
            device_type = multilane_device_by_node.setdefault(
                median.node_id,
                "dual_warning_lamp" if random.Random(
                    f"{seed}:{median.node_id}:median-island-device"
                ).random() < 0.5 else "keep_left_sign",
            )
        else:
            device_type = "keep_left_sign"
        length = math.hypot(dx, dy)
        # Keep the sign/lamp close to the junction-facing nose. A vehicle
        # signal, when selected, stands near the opposite end of this short
        # island, leaving roughly 0.8--0.9 m between their support centres.
        device_distance = min(0.25, length * 0.25)
        factor = device_distance / length if length > 1e-9 else 0.0
        plans.append(MedianIslandDevicePlan(
            f"{median.id}_{device_type}", median.id, device_type,
            (start_x + dx * factor, start_y + dy * factor, median.height),
            heading - 90.0,
        ))
    return tuple(plans)


def longitudinal_marking_trims(
        network: RoadNetwork, edge,
        crosswalks: tuple[CrosswalkPlan, ...] | None = None,
) -> tuple[float, float]:
    """Derive centre/lane-line ends from crossing control, never JSON lengths."""
    if crosswalks is None:
        crosswalks = plan_crosswalks(network)
    start = network.nodes[edge.start].position
    end = network.nodes[edge.end].position
    horizontal = abs(end[0] - start[0]) > abs(end[1] - start[1])

    def trim(node_id, other_id):
        node = network.nodes[node_id]
        if node.kind == "boundary":
            return 1.0

        node_x, node_y = node.position
        other_x, other_y = network.nodes[other_id].position
        dx, dy = other_x - node_x, other_y - node_y
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        edge = next(item for item in network.edges
                    if {item.start, item.end} == {node_id, other_id})
        if node.kind == "priority_t_junction":
            same_road_arms = [item for item in network.edges
                              if node_id in {item.start, item.end}
                              and item.road_id == edge.road_id]
            if edge.road_id and len(same_road_arms) == 2:
                return 0.0
        outward_approach = _compatibility_approach_map(
            network, node_id).get(edge.id, _cardinal(dx, dy))
        # A centre/lane line terminates at the stop line belonging to traffic
        # arriving from this edge. Both the crossing displacement and its
        # painted width therefore remain single-source planner data.
        for crossing in crosswalks:
            if (crossing.node_id != node_id
                    or outward_approach not in crossing.controlled_approaches):
                continue
            projection = ((crossing.center[0] - node_x) * ux
                          + (crossing.center[1] - node_y) * uy)
            return projection + crossing.crosswalk_width * 0.5 + 2.0
        if node.kind in {"signalized_cross", "signalized_t_junction",
                         "stop_cross", "stop_t_junction",
                         "priority_t_junction"}:
            east_west_width, north_south_width = road_widths_at_node(network, node_id)
            perpendicular = north_south_width if horizontal else east_west_width
            return perpendicular * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M
        return 0.0

    return trim(edge.start, edge.end), trim(edge.end, edge.start)


def plan_bicycle_markings(network: RoadNetwork) -> tuple[BicycleMarkingPlan, ...]:
    """Place whole repeated symbols beside both outer carriageway edges."""
    plans = []
    pattern_length = BICYCLE_MARKING_WIDTH_M * BICYCLE_MARKING_LENGTH_WIDTH_RATIO
    crosswalks = plan_crosswalks(network)
    for edge in network.edges:
        if not edge.bicycle_lane:
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        left_x, left_y = -uy, ux
        start_trim, end_trim = longitudinal_marking_trims(network, edge, crosswalks)
        usable = length - start_trim - end_trim
        if usable < pattern_length:
            continue
        count = max(1, math.floor(
            (usable - BICYCLE_MARKING_MIN_GAP_M) /
            (pattern_length + BICYCLE_MARKING_MIN_GAP_M)
        ))
        # Reserve minimum clearance before/after and between every whole
        # symbol, then distribute all remaining length equally. This favours a
        # legible repeat without ever clipping the reference composition.
        gap = (usable - count * pattern_length) / (count + 1)
        road_half_width = road_half_width_m(edge)
        lateral_offset = road_half_width - BICYCLE_MARKING_WIDTH_M * 0.5 - 0.20
        for direction_name, travel_sign, side_sign in (
            ("forward", 1.0, 1.0), ("reverse", -1.0, -1.0),
        ):
            travel_x, travel_y = ux * travel_sign, uy * travel_sign
            heading = math.degrees(math.atan2(travel_y, travel_x))
            for index in range(count):
                distance = gap + index * (pattern_length + gap)
                if travel_sign > 0:
                    base_distance = start_trim + distance
                    base_x = start[0] + ux * base_distance
                    base_y = start[1] + uy * base_distance
                else:
                    base_distance = end_trim + distance
                    base_x = end[0] - ux * base_distance
                    base_y = end[1] - uy * base_distance
                location = (base_x + left_x * side_sign * lateral_offset,
                            base_y + left_y * side_sign * lateral_offset)
                plans.append(BicycleMarkingPlan(
                    f"{edge.id}_{direction_name}_bicycle_{index + 1}", edge.id,
                    direction_name, location, heading - 90.0,
                    BICYCLE_MARKING_WIDTH_M,
                ))
    return tuple(plans)


def plan_bicycle_junction_chevrons(
        network: RoadNetwork) -> tuple[BicycleJunctionChevronPlan, ...]:
    """Continue blue bicycle chevrons through straight four-arm junctions."""
    chevron_length = BICYCLE_MARKING_WIDTH_M * (401.0 / 329.0)
    # One arrow followed by a 1.5-arrow-length clear interval.
    pitch = chevron_length * 2.5
    plans = []

    for node in network.nodes.values():
        if node.kind != "signalized_cross":
            continue
        incident = [edge for edge in network.edges
                    if node.id in {edge.start, edge.end}]
        if (len(incident) != 4
                or any(edge.lanes_each_way < 2 for edge in incident)):
            continue
        groups = {}
        for edge in incident:
            if edge.road_id:
                groups.setdefault(edge.road_id, []).append(edge)
        if len(groups) != 2 or any(len(edges) != 2 for edges in groups.values()):
            continue

        road_specs = []
        for road_id, edges in sorted(groups.items()):
            if (not all(edge.bicycle_lane for edge in edges)
                    or len({edge.lanes_each_way for edge in edges}) != 1):
                continue
            directions = []
            valid = True
            for edge in edges:
                if edge.geometry is not None and edge.geometry.kind != "line":
                    valid = False
                    break
                other_id = edge.end if edge.start == node.id else edge.start
                other = network.nodes[other_id].position
                dx, dy = other[0] - node.position[0], other[1] - node.position[1]
                length = math.hypot(dx, dy)
                directions.append((dx / length, dy / length))
            if not valid:
                continue
            # A through road that changes direction at the junction is
            # intentionally outside this feature.
            dot = directions[0][0] * directions[1][0] + directions[0][1] * directions[1][1]
            cross = directions[0][0] * directions[1][1] - directions[0][1] * directions[1][0]
            if dot > -1.0 + 1e-8 or abs(cross) > 1e-6:
                continue
            axis = directions[0]
            if axis[0] < -1e-9 or (abs(axis[0]) <= 1e-9 and axis[1] < 0.0):
                axis = (-axis[0], -axis[1])
            junction_half = max(
                approach_road_half_width_m(
                    edge, "from" if edge.start == node.id else "to")
                for edge in edges)
            road_specs.append((road_id, edges[0], axis, junction_half))
        if not road_specs:
            continue

        eligible_ids = sorted(spec[0] for spec in road_specs)
        priority_id = eligible_ids[
            zlib.crc32(node.id.encode("utf-8")) % len(eligible_ids)
        ]
        # Generate the priority road first. Non-priority chevrons are removed
        # where their footprint crosses either continuous priority bike lane.
        road_specs.sort(key=lambda spec: spec[0] != priority_id)
        priority_spec = next((spec for spec in road_specs
                              if spec[0] == priority_id), None)
        priority_strips = []
        if priority_spec is not None:
            _, priority_edge, priority_axis, priority_half = priority_spec
            priority_normal = (-priority_axis[1], priority_axis[0])
            priority_lateral = (priority_half
                                - BICYCLE_MARKING_WIDTH_M * 0.5 - 0.20)
            priority_strips = [
                (priority_normal, priority_lateral),
                (priority_normal, -priority_lateral),
            ]

        for road_id, road_edge, axis, junction_half in road_specs:
            # This road's crosswalk position is determined by the width of the
            # road it crosses, not by the widest arm in the whole junction.
            perpendicular_half_width = max(
                approach_road_half_width_m(
                    edge, "from" if edge.start == node.id else "to")
                for other_road_id, edges in groups.items()
                if other_road_id != road_id
                for edge in edges
            )
            # Stay wholly on the junction side of each crosswalk. ``extent``
            # is a centre limit, hence subtracting half the chevron length.
            extent = (perpendicular_half_width + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
                      - 1.60 - BICYCLE_JUNCTION_CHEVRON_CROSSWALK_CLEARANCE_M
                      - chevron_length * 0.5)
            count = max(1, math.floor(2.0 * extent / pitch) + 1)
            occupied = (count - 1) * pitch
            first = -occupied * 0.5
            normal = (-axis[1], axis[0])
            lateral = (junction_half
                       - BICYCLE_MARKING_WIDTH_M * 0.5 - 0.20)
            is_priority = road_id == priority_id
            for travel_index, (travel_sign, side_sign) in enumerate(((1.0, 1.0), (-1.0, -1.0))):
                travel = (axis[0] * travel_sign, axis[1] * travel_sign)
                rotation = math.degrees(math.atan2(travel[1], travel[0])) - 90.0
                for index in range(count):
                    along = first + index * pitch
                    location = (
                        node.position[0] + axis[0] * along + normal[0] * side_sign * lateral,
                        node.position[1] + axis[1] * along + normal[1] * side_sign * lateral,
                    )
                    if not is_priority and priority_strips:
                        half_along = chevron_length * 0.5
                        half_across = BICYCLE_MARKING_WIDTH_M * 0.5
                        corners = [
                            (location[0] + axis[0] * a + normal[0] * b,
                             location[1] + axis[1] * a + normal[1] * b)
                            for a in (-half_along, half_along)
                            for b in (-half_across, half_across)
                        ]
                        # Reserve the whole crossing footprint rather than
                        # relying on a coincidental gap in the repeat pattern.
                        # This makes the selected priority visibly stable.
                        strip_clearance = half_across + half_along
                        crosses = any(
                            min((corner[0] - node.position[0]) * strip_normal[0]
                                + (corner[1] - node.position[1]) * strip_normal[1]
                                for corner in corners) <= strip_offset + strip_clearance
                            and max((corner[0] - node.position[0]) * strip_normal[0]
                                    + (corner[1] - node.position[1]) * strip_normal[1]
                                    for corner in corners) >= strip_offset - strip_clearance
                            for strip_normal, strip_offset in priority_strips
                        )
                        if crosses:
                            continue
                    plans.append(BicycleJunctionChevronPlan(
                        f"{node.id}_{road_id}_{travel_index}_{index}_junction_bicycle_chevron",
                        node.id, road_id, location, rotation,
                        BICYCLE_MARKING_WIDTH_M, is_priority,
                    ))
    return tuple(plans)


def plan_right_turn_guides(network: RoadNetwork) -> tuple[RightTurnGuidePlan, ...]:
    """Plan dotted in-junction extensions for right-turn-only approach lanes."""
    bicycle_chevrons = plan_bicycle_junction_chevrons(network)
    chevron_length = BICYCLE_MARKING_WIDTH_M * (401.0 / 329.0)
    dash_length = 3.0 / 5.0
    dash_gap = 3.0 / 5.0
    dash_width = 0.13
    median_plans = plan_medians(network, plan_crosswalks(network))

    def rectangle(center, along, length, width):
        across = (-along[1], along[0])
        return tuple(
            (center[0] + along[0] * a + across[0] * b,
             center[1] + along[1] * a + across[1] * b)
            for a, b in ((-length / 2, -width / 2),
                         (length / 2, -width / 2),
                         (length / 2, width / 2),
                         (-length / 2, width / 2))
        )

    def polygons_overlap(first, second):
        for polygon in (first, second):
            for index, point in enumerate(polygon):
                nxt = polygon[(index + 1) % len(polygon)]
                axis = (-(nxt[1] - point[1]), nxt[0] - point[0])
                first_projection = [p[0] * axis[0] + p[1] * axis[1] for p in first]
                second_projection = [p[0] * axis[0] + p[1] * axis[1] for p in second]
                if (max(first_projection) <= min(second_projection) + 1e-8
                        or max(second_projection) <= min(first_projection) + 1e-8):
                    return False
        return True

    plans = []
    for node in network.nodes.values():
        if node.kind not in {"signalized_cross", "signalized_t_junction"}:
            continue
        incident = [edge for edge in network.edges
                    if node.id in {edge.start, edge.end}]
        arms = []
        for edge in incident:
            other_id = edge.end if edge.start == node.id else edge.start
            other = network.nodes[other_id].position
            dx, dy = other[0] - node.position[0], other[1] - node.position[1]
            length = math.hypot(dx, dy)
            arms.append((edge, (dx / length, dy / length)))

        if (node.kind == "signalized_cross"
                and any(edge.lanes_each_way == 1 for edge, _outward in arms)):
            # A 1-lane crossing road means the multilane road has no added
            # right-turn-only approach, hence no in-junction guide either.
            continue

        node_chevrons = [item for item in bicycle_chevrons
                         if item.node_id == node.id]
        chevron_rectangles = []
        for item in node_chevrons:
            heading = math.radians(item.rotation_degrees + 90.0)
            along = (math.cos(heading), math.sin(heading))
            chevron_rectangles.append(rectangle(
                item.location, along, chevron_length, item.width))

        for edge, outward in arms:
            endpoint = "from" if edge.start == node.id else "to"
            if (node.kind == "signalized_t_junction"
                    and not has_extra_inbound_lane(edge, endpoint)):
                # A T junction receives an in-junction right-turn guide only
                # for its single explicitly added right-turn-only lane.
                continue
            if has_extra_inbound_reserve(edge, endpoint):
                # At the closed side of the asymmetric T junction this space
                # is a widened median, not a right-turn waiting lane.
                continue
            effective_lanes = edge.lanes_each_way + (
                1 if has_extra_inbound_lane(edge, endpoint) else 0)
            if "right" not in approach_lane_arrow_kinds(effective_lanes):
                continue
            perpendicular_half_widths = []
            for other_edge, other_outward in arms:
                if other_edge.id == edge.id:
                    continue
                dot = outward[0] * other_outward[0] + outward[1] * other_outward[1]
                angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
                if 60.0 <= angle <= 120.0:
                    perpendicular_half_widths.append(
                        road_half_width_m(other_edge))
            if not perpendicular_half_widths:
                continue
            crosswalk_inner = (
                max(perpendicular_half_widths)
                + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M - 1.60
                - BICYCLE_JUNCTION_CHEVRON_CROSSWALK_CLEARANCE_M
            )
            left = (-outward[1], outward[0])
            junction_median = next((
                item for item in median_plans
                if item.edge_id == edge.id and item.node_id == node.id
            ), None)
            inner_lateral = 0.0
            inner_outer_distance = crosswalk_inner
            if junction_median is not None:
                median_midpoint = (
                    (junction_median.start[0] + junction_median.end[0]) * 0.5,
                    (junction_median.start[1] + junction_median.end[1]) * 0.5,
                )
                median_center_lateral = (
                    (median_midpoint[0] - node.position[0]) * left[0]
                    + (median_midpoint[1] - node.position[1]) * left[1]
                )
                inner_lateral = (median_center_lateral
                                  - junction_median.width * 0.5)
                endpoint_distances = (
                    math.dist(node.position, junction_median.start),
                    math.dist(node.position, junction_median.end),
                )
                # The junction-side end is rounded; its physical nose extends
                # half the median width closer to the junction than its centre.
                inner_outer_distance = max(
                    0.0, min(endpoint_distances) - junction_median.width * 0.5)
            elif has_extra_inbound_lane(edge, endpoint):
                # Without a physical median, the displaced orange centre line
                # is the inner boundary of the added right-turn lane.
                inner_lateral = LANE_WIDTH_M * 0.5
            outer_lateral = (
                inner_lateral - (LANE_WIDTH_M - MEDIAN_NARROW_WIDTH_M * 0.5)
                if junction_median is not None
                else inner_lateral - LANE_WIDTH_M)
            effective_lane_width = inner_lateral - outer_lateral
            lane_center_lateral = (outer_lateral + inner_lateral) * 0.5
            stop_distance = LANE_WIDTH_M
            longitudinal_skew = (
                math.tan(math.radians(20.0)) * effective_lane_width * 0.5
            )
            lane_center = (
                node.position[0] + outward[0] * stop_distance
                + left[0] * lane_center_lateral,
                node.position[1] + outward[1] * stop_distance
                + left[1] * lane_center_lateral,
            )
            # Driver-left endpoint lies farther into the junction; driver-right
            # lies closer to the entry, making that dotted boundary shorter.
            stop_left = (
                lane_center[0] - left[0] * effective_lane_width * 0.5
                - outward[0] * longitudinal_skew,
                lane_center[1] - left[1] * effective_lane_width * 0.5
                - outward[1] * longitudinal_skew,
            )
            stop_right = (
                lane_center[0] + left[0] * effective_lane_width * 0.5
                + outward[0] * longitudinal_skew,
                lane_center[1] + left[1] * effective_lane_width * 0.5
                + outward[1] * longitudinal_skew,
            )
            dash_segments = []
            for lateral, inner_distance, outer_distance in (
                    (outer_lateral, stop_distance - longitudinal_skew,
                     crosswalk_inner),
                    (inner_lateral, stop_distance + longitudinal_skew,
                     inner_outer_distance)):
                available = outer_distance - inner_distance
                cursor = dash_gap * 0.5
                while cursor < available - 0.05:
                    piece = min(dash_length, available - cursor)
                    start_distance = inner_distance + cursor
                    end_distance = start_distance + piece
                    start = (
                        node.position[0] + outward[0] * start_distance + left[0] * lateral,
                        node.position[1] + outward[1] * start_distance + left[1] * lateral,
                    )
                    end = (
                        node.position[0] + outward[0] * end_distance + left[0] * lateral,
                        node.position[1] + outward[1] * end_distance + left[1] * lateral,
                    )
                    center = ((start[0] + end[0]) * 0.5,
                              (start[1] + end[1]) * 0.5)
                    dash_rectangle = rectangle(center, outward, piece, dash_width)
                    if not any(polygons_overlap(dash_rectangle, chevron)
                               for chevron in chevron_rectangles):
                        dash_segments.append((start, end))
                    cursor += dash_length + dash_gap
            plans.append(RightTurnGuidePlan(
                f"{node.id}_{edge.id}_right_turn_guide",
                node.id, edge.id, tuple(dash_segments), stop_left, stop_right,
            ))
    return tuple(plans)


def plan_curb_parking_stripes(
        network: RoadNetwork,
        crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[CurbParkingStripePlan, ...]:
    """Plan paired curb-warning segments, clear of crossings and corners."""
    plans = []
    crossing_clearance = 0.55
    for edge in network.edges:
        if not edge.curb_parking_prohibition:
            continue
        if edge.sidewalks != "both":
            continue
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        left_x, left_y = -uy, ux
        horizontal = abs(ux) > 0.5

        def corner_trim(node_id):
            node = network.nodes[node_id]
            if node.kind not in {"signalized_cross", "signalized_t_junction",
                                 "stop_cross", "stop_t_junction",
                                 "priority_t_junction"}:
                return 0.0
            east_west_width, north_south_width = road_widths_at_node(network, node_id)
            perpendicular = north_south_width if horizontal else east_west_width
            return perpendicular * 0.5 + SIDEWALK_INTERSECTION_MARGIN_M

        start_trim = corner_trim(edge.start)
        end_trim = corner_trim(edge.end)
        for crossing in crosswalks:
            rel_x = crossing.center[0] - start[0]
            rel_y = crossing.center[1] - start[1]
            projection = rel_x * ux + rel_y * uy
            perpendicular = abs(rel_x * left_x + rel_y * left_y)
            half_span = crossing.crosswalk_width * 0.5
            if ((crossing.node_id not in {edge.start, edge.end}
                 and perpendicular > 1e-5)
                    or projection < -half_span or projection > length + half_span):
                continue
            if projection <= length * 0.5:
                start_trim = max(start_trim, projection + half_span + crossing_clearance)
            else:
                end_trim = max(end_trim, length - projection + half_span + crossing_clearance)
        if length - start_trim - end_trim < 0.60:
            continue
        curb_offset = road_half_width_m(edge) + 0.07
        for side, sign in (("left", 1.0), ("right", -1.0)):
            a = (start[0] + ux * start_trim + left_x * sign * curb_offset,
                 start[1] + uy * start_trim + left_y * sign * curb_offset)
            b = (end[0] - ux * end_trim + left_x * sign * curb_offset,
                 end[1] - uy * end_trim + left_y * sign * curb_offset)
            plans.append(CurbParkingStripePlan(
                f"{edge.id}_{side}_curb_parking_stripes", edge.id, side, a, b,
            ))

    for node in network.nodes.values():
        if node.kind not in {"signalized_cross", "signalized_t_junction",
                             "stop_cross", "stop_t_junction",
                             "priority_t_junction"}:
            continue
        connected = set(connected_approaches(network, node.id))
        # Japanese curb parking-prohibition paint ends before a junction
        # corner; it does not continue around the rounded corner blocks.
        if node.kind in {"signalized_t_junction", "stop_t_junction",
                         "priority_t_junction"}:
            east_west_width, north_south_width = road_widths_at_node(network, node.id)
            missing = next((direction for direction in ("west", "east", "south", "north")
                            if direction not in connected), None)
            through = (("west", "east") if missing in {"north", "south"}
                       else ("south", "north"))
            through_edges = tuple(_edge_for_approach(network, node.id, item)
                                  for item in through)
            if all(edge and edge.sidewalks == "both"
                   and edge.curb_parking_prohibition for edge in through_edges):
                if missing in {"north", "south"}:
                    sign = 1.0 if missing == "north" else -1.0
                    y = node.position[1] + sign * (east_west_width * 0.5 + 0.07)
                    extent = north_south_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
                    start, end = ((node.position[0] - extent, y),
                                  (node.position[0] + extent, y))
                else:
                    sign = 1.0 if missing == "east" else -1.0
                    x = node.position[0] + sign * (north_south_width * 0.5 + 0.07)
                    extent = east_west_width * 0.5 + SIDEWALK_CORNER_RADIUS_M
                    start, end = ((x, node.position[1] - extent),
                                  (x, node.position[1] + extent))
                plans.append(CurbParkingStripePlan(
                    f"{node.id}_back_curb_parking_stripes",
                    "+".join(edge.id for edge in through_edges), "back", start, end,
                ))
    return tuple(plans)


def plan_stop_lines(crosswalks: tuple[CrosswalkPlan, ...]) -> tuple[StopLinePlan, ...]:
    plans = []
    clearance = 2.0
    for crossing in crosswalks:
        carriageway_width = crossing.road_width - crossing.median_extra_width
        lane_offset = round(
            crossing.median_extra_width * 0.5 + carriageway_width * 0.25, 2)
        distance = crossing.crosswalk_width * 0.5 + clearance
        x, y = crossing.center
        sites = {
            "west": ((x - distance, y + lane_offset), "y"),
            "east": ((x + distance, y - lane_offset), "y"),
            "south": ((x - lane_offset, y - distance), "x"),
            "north": ((x + lane_offset, y + distance), "x"),
        }
        for approach in crossing.controlled_approaches:
            center, axis = sites[approach]
            plans.append(StopLinePlan(f"{crossing.id}_{approach}_stop", center, axis,
                                      carriageway_width * 0.5 - 2 * (
                                          CURB_ROAD_APRON_M
                                          + ROAD_MARKING_CURB_CLEARANCE_M)))
    return tuple(plans)


def plan_signal_sites(
        network: RoadNetwork, medians: tuple[MedianPlan, ...] | None = None,
        support_seed: int = 20260816,
) -> tuple[SignalSite, ...]:
    if medians is None:
        medians = plan_medians(network, plan_crosswalks(network))
    median_by_node_approach = {
        (item.node_id, item.approach): item
        for item in medians if item.node_id
    }
    opposite_approach = {
        "west": "east", "east": "west",
        "south": "north", "north": "south",
    }
    sites = []
    for node in network.nodes.values():
        x, y = node.position
        if node.kind in {"signalized_cross", "signalized_t_junction"}:
            east_west_width, north_south_width = road_widths_at_node(network, node.id)
            connected = set(connected_approaches(network, node.id))
            missing = ({"west", "south", "east", "north"} - connected).pop() \
                if node.kind == "signalized_t_junction" else None
            # Define the west/eastbound approach once, then rotate it through
            # all four directions. Unless the schema later supplies an explicit
            # directional override, the junction is exactly fourfold symmetric.
            # The roadside pole remains across the intersection from
            # approaching traffic, but moves from beyond that far-side
            # crosswalk to its junction side. Laterally it sits at the road-facing edge
            # of the planting bed rather than deep inside the footway.
            crosswalk_half = 1.60
            support_clearance = 0.50
            longitudinal_clearance = (
                CROSSWALK_OFFSET_FROM_ROAD_EDGE_M - crosswalk_half
                - support_clearance)
            planting_road_edge_clearance = SIGNAL_ROADSIDE_EDGE_CLEARANCE_M
            approach_names = ("west", "south", "east", "north")
            for quarter, approach in enumerate(approach_names):
                if approach not in connected:
                    continue
                angle = quarter * math.pi / 2
                tx, ty = longitudinal_clearance, planting_road_edge_clearance
                rx = tx * math.cos(angle) - ty * math.sin(angle)
                ry = tx * math.sin(angle) + ty * math.cos(angle)
                rx = math.copysign(north_south_width * 0.5 + abs(rx), rx)
                ry = math.copysign(east_west_width * 0.5 + abs(ry), ry)
                location = (x + round(rx, 6), y + round(ry, 6), 0)
                support_mode = "roadside_left"
                support_median_id = ""
                # Like the roadside signal, a median-mounted signal remains
                # across the junction but moves onto the junction-side island
                # immediately before that far-side crosswalk.
                median = median_by_node_approach.get(
                    (node.id, opposite_approach[approach])
                )
                if median is not None:
                    # Give every node/approach its own deterministic random
                    # stream. CRC parity correlated visibly with sequential
                    # block IDs, whereas this avoids directional runs caused
                    # by the identifier's low bits and is order-independent.
                    choose_median = random.Random(
                        f"{support_seed}:{node.id}:{approach}:vehicle-support"
                    ).random() < 0.5
                    if choose_median:
                        # Use the junction-side island on the opposite arm,
                        # across the crosswalk from the long road-side median.
                        # Stand just inside the island's
                        # square (crosswalk-facing) end so the base cannot
                        # overhang the carriageway.
                        sx, sy = median.start
                        ex, ey = median.end
                        length = math.hypot(ex - sx, ey - sy)
                        if length > 1e-9:
                            inset = min(0.35, length * 0.25)
                            px = ex + (sx - ex) / length * inset
                            py = ey + (sy - ey) / length * inset
                            support_mode = "median_right"
                            support_median_id = median.id
                            location = (px, py, median.height)
                rotation = -90 + quarter * 90
                if support_mode == "roadside_left":
                    location = (location[0], location[1], SIGNAL_BASE_Z_M)
                sites.append(SignalSite(f"{node.id}_{approach}_vehicle", "vehicle",
                                        location, rotation, node_id=node.id,
                                        support_mode=support_mode,
                                        support_median_id=support_median_id))
            side_names = (
                ("west_south", "west_north"),
                ("south_east", "south_west"),
                ("east_north", "east_south"),
                ("north_west", "north_east"),
            )
            # Each pedestrian pole chooses side 1 (outside the crossing) or
            # side 2 (junction side).  Its unmirrored body then branches from
            # the pole toward the crossing centre.  A per-site RNG keeps the
            # choice random, reproducible and independent of iteration order.
            pedestrian_endpoint_clearance = 0.42
            for quarter in range(4):
                approach = approach_names[quarter]
                if approach not in connected:
                    continue
                angle = quarter * math.pi / 2
                perpendicular_half = (north_south_width * 0.5
                                      if approach in {"west", "east"}
                                      else east_west_width * 0.5)
                endpoint_half = (east_west_width * 0.5
                                 if approach in {"west", "east"}
                                 else north_south_width * 0.5)
                for item, endpoint_sign in enumerate((-1.0, 1.0)):
                    label = side_names[quarter][item]
                    outside = random.Random(
                        f"{support_seed}:{node.id}:{label}:pedestrian-position"
                    ).random() < 0.5
                    along = (perpendicular_half + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
                             + (crosswalk_half + support_clearance
                                if outside else -crosswalk_half - support_clearance))
                    across = endpoint_sign * (endpoint_half
                                              + pedestrian_endpoint_clearance)
                    tx, ty = -along, across
                    rx = tx * math.cos(angle) - ty * math.sin(angle)
                    ry = tx * math.sin(angle) + ty * math.cos(angle)
                    # Face along the pedestrian walking axis toward the other
                    # end of the crossing, never along the vehicle approach.
                    face = (across * math.sin(angle),
                            -across * math.cos(angle))
                    rotation = math.degrees(math.atan2(face[0], -face[1]))
                    local_x = (math.cos(math.radians(rotation)),
                               math.sin(math.radians(rotation)))
                    # The body branches from its pole toward the stripe area:
                    # junction-ward for position 1, outward for position 2.
                    side_outward = (-math.cos(angle), -math.sin(angle))
                    body_direction = ((-1.0 if outside else 1.0) * side_outward[0],
                                      (-1.0 if outside else 1.0) * side_outward[1])
                    support_side = ("left" if local_x[0] * body_direction[0]
                                    + local_x[1] * body_direction[1] > 0 else "right")
                    sites.append(SignalSite(
                        f"{node.id}_{label}_pedestrian", "pedestrian",
                        (x + round(rx, 6), y + round(ry, 6), SIGNAL_BASE_Z_M),
                        rotation,
                        not outside, node.id,
                        pedestrian_support_side=support_side,
                        pedestrian_position="outer" if outside else "inner",
                    ))
        elif node.kind == "signalized_pedestrian_crossing":
            if "north_south" in node.crossings:
                for label, kind, location, rotation in (
                    ("west_vehicle", "vehicle", (x - 5.8, y - 4.15, SIGNAL_BASE_Z_M), 90),
                    ("east_vehicle", "vehicle", (x + 5.8, y + 4.15, SIGNAL_BASE_Z_M), -90),
                    ("south_pedestrian", "pedestrian", (x - 2.7, y - 3.75, SIGNAL_BASE_Z_M), 180),
                    ("north_pedestrian", "pedestrian", (x + 2.7, y + 3.75, SIGNAL_BASE_Z_M), 0),
                ):
                    sites.append(SignalSite(f"{node.id}_{label}", kind, location, rotation,
                                            node_id=node.id))
    return tuple(sites)


def plan_pedestrian_countdowns(
        network: RoadNetwork, seed: int = 20260812, total: int = 8,
) -> tuple[PedestrianCountdownPlan, ...]:
    """Choose one reproducible countdown pair per signalized node.

    JSON controls only the blue remainder. The red remainder is always its
    complement, preserving blue_level + red_level == total.
    """
    plans = []
    for node in network.nodes.values():
        if node.kind not in ("signalized_cross", "signalized_t_junction",
                             "signalized_pedestrian_crossing"):
            continue
        blue_level = node.pedestrian_countdown_blue_level
        if blue_level is None:
            # A per-node RNG makes adding or reordering unrelated nodes unable to
            # change an existing intersection's value.
            blue_level = random.Random(f"{seed}:{node.id}").randint(0, total)
        plans.append(PedestrianCountdownPlan(node.id, blue_level, total - blue_level))
    return tuple(plans)


def plan_signal_blocks(signal_sites: tuple[SignalSite, ...], seed: int = 20260812) -> tuple[SignalBlockPlan, ...]:
    by_id = {site.id: site for site in signal_sites}
    membership = {
        "northwest": ("south", ("west_north", "north_west")),
        "northeast": ("west", ("east_north", "north_east")),
        "southeast": ("north", ("east_south", "south_east")),
        "southwest": ("east", ("west_south", "south_west")),
    }
    blocks = []
    # Discover signalized-cross prefixes from planned sites; the generic planner
    # must not know the sample's node id (for example, "kasumigaseki").
    node_ids = sorted({site.node_id for site in signal_sites
                       if site.kind == "vehicle" and site.node_id})
    for node_id in node_ids:
        for corner, (approach, pedestrian_labels) in membership.items():
            vehicle_id = f"{node_id}_{approach}_vehicle"
            pedestrian_ids = tuple(f"{node_id}_{label}_pedestrian" for label in pedestrian_labels)
            if vehicle_id in by_id and all(site_id in by_id for site_id in pedestrian_ids):
                vehicle = by_id[vehicle_id]
                blocks.append(SignalBlockPlan(
                    f"{node_id}_{corner}", vehicle,
                    tuple(by_id[site_id] for site_id in pedestrian_ids), 1,
                ))
    return tuple(blocks)
