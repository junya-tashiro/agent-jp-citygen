"""General-angle and gentle-curve road planning primitives."""

from dataclasses import dataclass
import math

from .geometry import Centerline, add, angle_degrees, left_normal, mul, normalized
from .planner import (
    CROSSWALK_OFFSET_FROM_ROAD_EDGE_M, LANE_WIDTH_M, road_half_width_m,
    approach_road_half_width_m,
    SIDEWALK_CORNER_RADIUS_M, SIDEWALK_WIDTH_M,
    SIGNAL_ROADSIDE_EDGE_CLEARANCE_M,
)


JUNCTION_KINDS = {"signalized_cross", "signalized_t_junction",
                  "stop_cross", "stop_t_junction", "priority_t_junction"}
JUNCTION_TRIM_M = 9.75
CROSSWALK_DISTANCE_M = 6.6
CROSSWALK_HALF_WIDTH_M = 1.60
STRAIGHT_AFTER_CROSSWALK_M = 10.0


def requires_general_geometry(network):
    """Use one geometry-aware path for every explicitly authored centreline."""
    return (bool(network.components)
            or any(edge.geometry is not None for edge in network.edges)
            or any(edge.approaches.get(endpoint, {}).get(
                       "extra_inbound_lane", False)
                   for edge in network.edges for endpoint in ("from", "to"))
            or any(node.kind == "priority_t_junction"
                   for node in network.nodes.values()))


def corner_fillet_radius(gap_degrees, available_tangent,
                         preferred_radius=SIDEWALK_CORNER_RADIUS_M):
    """Return the largest preferred tangent fillet fitting two kerb runs."""
    half_angle = math.radians(gap_degrees * 0.5)
    return min(preferred_radius,
               max(0.0, available_tangent * math.tan(half_angle)))


@dataclass(frozen=True)
class JunctionArm:
    id: str
    node_id: str
    edge_id: str
    endpoint: str
    outward: tuple[float, float]
    left: tuple[float, float]
    angle: float
    width: float
    road_id: str


def centerlines(network):
    controls = {}
    for edge in network.edges:
        geometry = edge.geometry
        if geometry is not None and geometry.kind == "cubic_bezier":
            controls[edge.id] = [geometry.control_from, geometry.control_to]

    # The editor cuts a straight approach out of an existing cubic. Merely
    # sharing the cut point is C0-continuous: the two offset road/sidewalk
    # boundaries still overlap on one side and open a wedge on the other.
    # Align the cubic endpoint handle with the adjoining straight edge for
    # every same-road, degree-two, non-junction split node. This structural
    # rule also repairs already-exported editor JSON without an angle switch.
    incident = {}
    for edge in network.edges:
        incident.setdefault(edge.start, []).append(edge)
        incident.setdefault(edge.end, []).append(edge)
    for node_id, edges in incident.items():
        if network.nodes[node_id].kind in JUNCTION_KINDS or len(edges) != 2:
            continue
        if not edges[0].road_id or edges[0].road_id != edges[1].road_id:
            continue
        line = next((edge for edge in edges
                     if edge.geometry is None or edge.geometry.kind == "line"), None)
        cubic = next((edge for edge in edges
                      if edge.geometry is not None
                      and edge.geometry.kind == "cubic_bezier"), None)
        if line is None or cubic is None:
            continue
        node = network.nodes[node_id].position
        line_other_id = line.end if line.start == node_id else line.start
        line_other = network.nodes[line_other_id].position
        line_outward = normalized((line_other[0] - node[0], line_other[1] - node[1]))
        desired = (-line_outward[0], -line_outward[1])
        control_index = 0 if cubic.start == node_id else 1
        old_control = controls[cubic.id][control_index]
        handle_length = math.hypot(old_control[0] - node[0], old_control[1] - node[1])
        controls[cubic.id][control_index] = (
            node[0] + desired[0] * handle_length,
            node[1] + desired[1] * handle_length,
        )

    result = {}
    for edge in network.edges:
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        if edge.id in controls:
            result[edge.id] = Centerline(start, end, *controls[edge.id])
        else:
            result[edge.id] = Centerline(start, end)
    return result


def arm_for_edge(network, edge, node_id, paths=None):
    paths = paths or centerlines(network)
    path = paths[edge.id]
    if edge.start == node_id:
        outward = path.tangent_at_distance(0.0)
        endpoint = "from"
    else:
        outward = mul(path.tangent_at_distance(path.length), -1.0)
        endpoint = "to"
    outward = normalized(outward)
    return JunctionArm(
        f"{edge.id}:{endpoint}", node_id, edge.id, endpoint, outward,
        left_normal(outward), angle_degrees(outward) % 360.0,
        approach_road_half_width_m(edge, endpoint) * 2, edge.road_id,
    )


def junction_arms(network, node_id, paths=None):
    paths = paths or centerlines(network)
    arms = [arm_for_edge(network, edge, node_id, paths) for edge in network.edges
            if node_id in {edge.start, edge.end}]
    return tuple(sorted(arms, key=lambda item: item.angle))


def smallest_angle(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def required_straight_approach_length(arm, arms):
    """Distance from the junction to 10m beyond this arm's crosswalk."""
    crossing_widths = [other.width for other in arms
                       if other.road_id != arm.road_id]
    perpendicular_width = max(crossing_widths, default=arm.width)
    return (perpendicular_width * 0.5
            + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
            + CROSSWALK_HALF_WIDTH_M
            + STRAIGHT_AFTER_CROSSWALK_M)


def straight_run_from_junction(network, arm, paths):
    """Measure the collinear line run, including same-road split edges."""
    initial = arm.outward
    current_id = arm.node_id
    edge = next(item for item in network.edges if item.id == arm.edge_id)
    visited = set()
    total = 0.0
    while edge.id not in visited:
        visited.add(edge.id)
        geometry = edge.geometry
        if geometry is not None and geometry.kind != "line":
            break
        path = paths[edge.id]
        outward = (path.tangent_at_distance(0.0) if edge.start == current_id
                   else mul(path.tangent_at_distance(path.length), -1.0))
        if outward[0] * initial[0] + outward[1] * initial[1] < 1.0 - 1e-8:
            break
        total += path.length
        next_id = edge.end if edge.start == current_id else edge.start
        if network.nodes[next_id].kind in JUNCTION_KINDS:
            break
        candidates = [item for item in network.edges
                      if item.id != edge.id
                      and next_id in {item.start, item.end}
                      and item.road_id == arm.road_id]
        if len(candidates) != 1:
            break
        current_id, edge = next_id, candidates[0]
    return total


def validate_general_network(network):
    paths = centerlines(network)
    for node in network.nodes.values():
        if node.kind not in JUNCTION_KINDS:
            continue
        curved_incident = [
            edge.id for edge in network.edges
            if node.id in {edge.start, edge.end}
            and edge.geometry is not None and edge.geometry.kind != "line"
        ]
        if curved_incident:
            raise ValueError(
                f"Junction {node.id!r} requires straight incident edges; "
                f"curves cannot pass through a junction: {curved_incident}"
            )
        arms = junction_arms(network, node.id, paths)
        expected = 4 if node.kind in {"signalized_cross", "stop_cross"} else 3
        if len(arms) != expected:
            raise ValueError(f"Node {node.id!r} requires {expected} incident arms")
        eligible_extra_arms = [
            arm for arm in arms
            if (node.kind == "signalized_cross"
                or (node.kind == "signalized_t_junction" and arm.road_id
                    and sum(candidate.road_id == arm.road_id
                            for candidate in arms) == 2))
            and (edge := next(item for item in network.edges
                              if item.id == arm.edge_id)).lanes_each_way >= 2
            and (node.kind == "signalized_cross" or edge.median)
        ]
        enabled_extra_arms = [
            arm for arm in eligible_extra_arms
            if next(item for item in network.edges
                    if item.id == arm.edge_id).approaches.get(
                        arm.endpoint, {}).get("extra_inbound_lane", False)
        ]
        if node.kind == "signalized_cross":
            if (enabled_extra_arms
                    and len(enabled_extra_arms) != len(eligible_extra_arms)):
                raise ValueError(
                    f"Junction {node.id!r} extra_inbound_lane must be enabled "
                    "on every eligible cross-junction approach")
        elif node.kind == "signalized_t_junction" and enabled_extra_arms:
            through = eligible_extra_arms
            stem = next((arm for arm in arms if arm not in through), None)
            right_turn_arm = next((
                arm for arm in through
                if stem is not None
                and ((-arm.outward[0]) * stem.outward[1]
                     - (-arm.outward[1]) * stem.outward[0]) < -1e-6
            ), None)
            if right_turn_arm is None or enabled_extra_arms != [right_turn_arm]:
                raise ValueError(
                    f"Junction {node.id!r} extra_inbound_lane is allowed only "
                    "on the through-road approach whose right turn exists")
            blocked_arm = next(arm for arm in through if arm != right_turn_arm)
            blocked_edge = next(item for item in network.edges
                                if item.id == blocked_arm.edge_id)
            blocked_edge.approaches.setdefault(blocked_arm.endpoint, {})[
                "_extra_inbound_lane_reserve"] = True
            arms = junction_arms(network, node.id, paths)
        for arm in arms:
            edge = next(item for item in network.edges if item.id == arm.edge_id)
            if not edge.approaches.get(arm.endpoint, {}).get(
                    "extra_inbound_lane", False):
                continue
            if node.kind == "priority_t_junction":
                raise ValueError(
                    f"Edge {edge.id!r} extra_inbound_lane is not supported at "
                    "an unsignalized priority T junction")
            if node.kind in {"signalized_t_junction", "stop_t_junction"}:
                same_road = [candidate for candidate in arms
                             if candidate.road_id == arm.road_id]
                if not arm.road_id or len(same_road) != 2:
                    raise ValueError(
                        f"Edge {edge.id!r} extra_inbound_lane is allowed only "
                        "on the through road of a T junction")
            extra_endpoint_count = sum(
                edge.approaches.get(endpoint, {}).get(
                    "extra_inbound_lane", False)
                for endpoint in ("from", "to"))
            # Two nearby junctions share a continuous approach section rather
            # than requiring two independent 50m envelopes.  80m is the
            # supported lower bound for that linked configuration.
            required_length = 80.0 if extra_endpoint_count == 2 else 50.0
            if paths[edge.id].length + 1e-6 < required_length:
                raise ValueError(
                    f"Edge {edge.id!r} extra_inbound_lane requires "
                    f"{required_length:g}m for the fixed section and taper")
        for arm in arms:
            required = required_straight_approach_length(arm, arms)
            available = straight_run_from_junction(network, arm, paths)
            if available + 1e-6 < required:
                raise ValueError(
                    f"Junction {node.id!r} arm {arm.edge_id!r} requires "
                    f"{required:.2f}m of straight approach to keep 10m "
                    f"beyond the crosswalk; only {available:.2f}m is available"
                )
        gaps = [((arms[(i + 1) % len(arms)].angle - arms[i].angle) % 360.0)
                for i in range(len(arms))]
        # T junctions contain one approximately 180-degree empty sector.
        tested = [gap for gap in gaps if gap < 150.0]
        # JSON coordinates are commonly rounded to millimetres, which can
        # perturb an authored 80/100-degree boundary by a few thousandths of
        # a degree. This epsilon is numerical input precision only.
        angle_epsilon = 0.005
        if any(not 80.0 - angle_epsilon <= gap <= 100.0 + angle_epsilon
               for gap in tested):
            raise ValueError(f"Node {node.id!r} has unsupported intersection angle(s): {gaps}")
        groups = {}
        for arm in arms:
            if arm.road_id:
                groups.setdefault(arm.road_id, []).append(arm)
        if node.kind in {"signalized_t_junction", "stop_t_junction",
                         "priority_t_junction"}:
            through_roads = [
                (road_id, members) for road_id, members in groups.items()
                if len(members) == 2
            ]
            if len(through_roads) != 1:
                raise ValueError(
                    f"T junction {node.id!r} must have exactly two arms with "
                    "the same road id to identify its through road"
                )
            road_id, members = through_roads[0]
            first, second = members[0].outward, members[1].outward
            cross = first[0] * second[1] - first[1] * second[0]
            dot = first[0] * second[0] + first[1] * second[1]
            # This tolerance absorbs normalized floating-point arithmetic
            # only. It is not an authored-angle feature threshold: a T's
            # through road must be tangent-continuous at the node.
            if abs(cross) > 1e-8 or dot >= 0.0:
                opposition = smallest_angle(members[0].angle, members[1].angle)
                raise ValueError(
                    f"Road {road_id!r} must be straight through T junction "
                    f"{node.id!r}; its node tangents differ by "
                    f"{abs(180.0 - opposition):.6f} degrees"
                )
        for road_id, members in groups.items():
            if len(members) == 2:
                opposition = smallest_angle(members[0].angle, members[1].angle)
                if not 159.95 <= opposition <= 200.05:
                    raise ValueError(
                        f"Road {road_id!r} changes direction too sharply through {node.id!r}: "
                        f"{180.0 - opposition:.1f} degrees"
                    )
    return paths


def point_from_node(node_position, arm, along, lateral=0.0):
    return add(add(node_position, mul(arm.outward, along)), mul(arm.left, lateral))


def t_stem_signal_support_location(center, stem_arm, through_arm,
                                   planned_location):
    """Place a T stem's far-side support beside the actual through road."""
    tangent = through_arm.outward
    open_direction = (-stem_arm.outward[0], -stem_arm.outward[1])
    normal = (-tangent[1], tangent[0])
    if normal[0] * open_direction[0] + normal[1] * open_direction[1] < 0.0:
        normal = (-normal[0], -normal[1])
    relative = (planned_location[0] - center[0],
                planned_location[1] - center[1])
    station = relative[0] * tangent[0] + relative[1] * tangent[1]
    roadside_offset = (through_arm.width * 0.5
                       + SIGNAL_ROADSIDE_EDGE_CLEARANCE_M)
    return (
        center[0] + tangent[0] * station + normal[0] * roadside_offset,
        center[1] + tangent[1] * station + normal[1] * roadside_offset,
        planned_location[2],
    )


def arm_groups(arms):
    groups = {}
    for arm in arms:
        groups.setdefault(arm.road_id or arm.id, []).append(arm)
    return tuple(tuple(items) for _, items in sorted(groups.items()))
