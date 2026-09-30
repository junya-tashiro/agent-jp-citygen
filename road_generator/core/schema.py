from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import zlib


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    position: tuple[float, float]
    name: str = ""
    roman_name: str = ""
    crossings: tuple[str, ...] = ()
    signal_phase: str = ""
    pedestrian_countdown_blue_level: int | None = None
    exterior_color: str = "white"
    vehicle_arrow: str = "none"


@dataclass(frozen=True)
class Approach:
    edge_id: str
    node_id: str
    direction: str
    right_turn_lane: bool = False
    stop_control: bool = False


@dataclass(frozen=True)
class GuardrailConfig:
    sides: str
    exterior_color: str = "white"


@dataclass(frozen=True)
class PlantingConfig:
    density: float = 0.82
    maintenance: float = 0.70
    health: float = 0.88
    seed: int | None = None
    style: str = "legacy"


@dataclass(frozen=True)
class StreetTreeConfig:
    enabled: bool = True
    species: str = "keyaki"
    density: float = 1.0
    seed: int | None = None


@dataclass(frozen=True)
class Road:
    id: str
    road_class: str = "local"
    speed_limit: int = 30
    lanes_each_way: int = 1
    sidewalks: str = "none"


@dataclass(frozen=True)
class EdgeGeometry:
    kind: str = "line"
    control_from: tuple[float, float] | None = None
    control_to: tuple[float, float] | None = None


@dataclass(frozen=True)
class Edge:
    id: str
    start: str
    end: str
    road_class: str
    speed_limit: int
    lanes_each_way: int
    sidewalks: str
    approaches: dict[str, dict] = field(default_factory=dict)
    guardrail: GuardrailConfig | None = None
    planting: PlantingConfig | None = None
    street_trees: StreetTreeConfig | None = None
    street_lights: bool = True
    median: bool = False
    median_width: str = "narrow"
    center_marking: str = "orange_solid"
    bicycle_lane: bool = False
    curb_parking_prohibition: bool = False
    tactile_paving: bool = False
    road_id: str = ""
    geometry: EdgeGeometry | None = None


@dataclass(frozen=True)
class ContextBuilding:
    id: str
    position: tuple[float, float]
    size: tuple[float, float]
    height: float
    roof_tilt_degrees: float = 0.0


@dataclass(frozen=True)
class RoadComponent:
    id: str
    kind: str
    edge_id: str
    side: str
    station: float


@dataclass(frozen=True)
class SceneConfig:
    time_of_day: str = "day"


@dataclass(frozen=True)
class RoadNetwork:
    nodes: dict[str, Node]
    edges: tuple[Edge, ...]
    buildings: tuple[ContextBuilding, ...] = ()
    roads: dict[str, Road] = field(default_factory=dict)
    scene: SceneConfig = field(default_factory=SceneConfig)
    components: tuple[RoadComponent, ...] = ()
    subway_entrances: tuple[dict, ...] = ()


def load_network(path: Path) -> RoadNetwork:
    data = json.loads(path.read_text(encoding="utf-8"))
    scene_item = data.get("scene", {})
    if not isinstance(scene_item, dict):
        raise ValueError("scene must be an object")
    time_of_day = scene_item.get("time_of_day", "day")
    if time_of_day not in {"day", "night"}:
        raise ValueError("scene.time_of_day must be day or night")
    scene = SceneConfig(time_of_day=time_of_day)
    roads = {}
    for item in data.get("roads", ()):
        road = Road(
            id=item["id"],
            road_class=item.get("road_class", "local"),
            speed_limit=item.get("speed_limit", 30),
            lanes_each_way=item.get("lanes_each_way", 1),
            sidewalks=item.get("sidewalks", "none"),
        )
        if road.id in roads:
            raise ValueError(f"Duplicate road id: {road.id!r}")
        roads[road.id] = road
    nodes = {
        item["id"]: Node(
            id=item["id"],
            kind=item["type"],
            position=tuple(item["position"]),
            name=item.get("name", ""),
            roman_name=item.get("roman_name", ""),
            crossings=tuple(item.get("crossings", ())),
            signal_phase=item.get("signal_phase", ""),
            pedestrian_countdown_blue_level=item.get("pedestrian_countdown_blue_level"),
            exterior_color=item.get("exterior_color", "white"),
            vehicle_arrow=item.get("vehicle_arrow", "none"),
        )
        for item in data["nodes"]
    }
    edge_items = []
    for item in data["edges"]:
        road_id = item.get("road", "")
        if road_id and road_id not in roads:
            raise ValueError(f"Edge {item['id']!r} references unknown road {road_id!r}")
        road = roads.get(road_id)
        guardrail_item = item.get("guardrail")
        guardrail = None
        if guardrail_item is not None:
            if not isinstance(guardrail_item, dict):
                raise ValueError(f"Edge {item['id']!r} guardrail must be an object")
            sides = guardrail_item.get("sides", "none")
            exterior_color = guardrail_item.get("exterior_color", "white")
            if sides not in {"none", "left", "right", "both"}:
                raise ValueError(
                    f"Edge {item['id']!r} guardrail sides must be none/left/right/both"
                )
            if exterior_color not in {"white", "brown"}:
                raise ValueError(
                    f"Edge {item['id']!r} guardrail exterior_color must be white or brown"
                )
            guardrail = GuardrailConfig(sides, exterior_color)
        planting_item = item.get("planting")
        planting = None
        if planting_item is not None:
            if not isinstance(planting_item, dict):
                raise ValueError(f"Edge {item['id']!r} planting must be an object")
            randomize = planting_item.get("random", False)
            if not isinstance(randomize, bool):
                raise ValueError(
                    f"Edge {item['id']!r} planting random must be true or false"
                )
            seed = planting_item.get("seed")
            if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
                raise ValueError(f"Edge {item['id']!r} planting seed must be an integer")
            if randomize:
                random_seed = seed if seed is not None else (
                    zlib.crc32(f"{road_id or item['id']}:planting".encode("utf-8"))
                    & 0x7FFFFFFF
                )
                rng = random.Random(random_seed)
                planting_item = {
                    **planting_item,
                    "density": round(rng.uniform(0.74, 0.90), 2),
                    "maintenance": round(rng.uniform(0.62, 0.78), 2),
                    "health": round(rng.uniform(0.82, 0.95), 2),
                }
                seed = random_seed
            values = {
                key: planting_item.get(key, default)
                for key, default in (("density", 0.82), ("maintenance", 0.70),
                                     ("health", 0.88))
            }
            for key, value in values.items():
                if (not isinstance(value, (int, float)) or isinstance(value, bool)
                        or not 0.0 <= value <= 1.0):
                    raise ValueError(
                        f"Edge {item['id']!r} planting {key} must be a number from 0 to 1"
                    )
            style = planting_item.get("style", "legacy")
            if style not in {"legacy", "clipped_hedge"}:
                raise ValueError(
                    f"Edge {item['id']!r} planting style must be legacy or clipped_hedge"
                )
            planting = PlantingConfig(**values, seed=seed, style=style)
        street_tree_item = item.get("street_trees")
        street_trees = None
        if street_tree_item is not None:
            if not isinstance(street_tree_item, dict):
                raise ValueError(f"Edge {item['id']!r} street_trees must be an object")
            enabled = street_tree_item.get("enabled", True)
            randomize = street_tree_item.get("random", False)
            species = street_tree_item.get("species", "keyaki")
            species_pool = street_tree_item.get(
                "species_pool", ["keyaki", "ginkgo", "cherry"])
            density = street_tree_item.get("density", 1.0)
            seed = street_tree_item.get("seed")
            if not isinstance(enabled, bool):
                raise ValueError(
                    f"Edge {item['id']!r} street_trees enabled must be true or false"
                )
            if not isinstance(randomize, bool):
                raise ValueError(
                    f"Edge {item['id']!r} street_trees random must be true or false"
                )
            if (not isinstance(species_pool, list) or not species_pool
                    or any(item not in {"keyaki", "ginkgo", "cherry"}
                           for item in species_pool)
                    or len(set(species_pool)) != len(species_pool)):
                raise ValueError(
                    f"Edge {item['id']!r} street_trees species_pool must be a "
                    "non-empty unique list containing keyaki, ginkgo or cherry"
                )
            if randomize:
                random_seed = seed if seed is not None else (
                    zlib.crc32(f"{road_id or item['id']}:street_trees".encode("utf-8"))
                    & 0x7FFFFFFF
                )
                rng = random.Random(random_seed)
                species = rng.choice(tuple(species_pool))
                density = round(rng.uniform(0.85, 1.10), 2)
                seed = random_seed
            if species not in {"keyaki", "ginkgo", "cherry"}:
                raise ValueError(
                    f"Edge {item['id']!r} street_trees species must be "
                    "keyaki, ginkgo or cherry"
                )
            if (not isinstance(density, (int, float)) or isinstance(density, bool)
                    or not 0.1 <= density <= 2.5):
                raise ValueError(
                    f"Edge {item['id']!r} street_trees density must be a number "
                    "from 0.1 to 2.5 trees per 10m"
                )
            if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
                raise ValueError(f"Edge {item['id']!r} street_trees seed must be an integer")
            street_trees = StreetTreeConfig(enabled, species, float(density), seed)
        bicycle_lane = item.get("bicycle_lane", False)
        if not isinstance(bicycle_lane, bool):
            raise ValueError(f"Edge {item['id']!r} bicycle_lane must be true or false")
        median = item.get("median", False)
        if not isinstance(median, bool):
            raise ValueError(f"Edge {item['id']!r} median must be true or false")
        median_width = item.get("median_width", "narrow")
        if median_width not in {"narrow", "wide"}:
            raise ValueError(
                f"Edge {item['id']!r} median_width must be narrow or wide")
        center_marking = item.get("center_marking", "orange_solid")
        if center_marking not in {"none", "orange_solid", "white_solid", "white_dashed"}:
            raise ValueError(
                f"Edge {item['id']!r} center_marking must be orange_solid, "
                "white_solid, white_dashed or none"
            )
        curb_parking_prohibition = item.get("curb_parking_prohibition", False)
        if not isinstance(curb_parking_prohibition, bool):
            raise ValueError(
                f"Edge {item['id']!r} curb_parking_prohibition must be true or false"
            )
        tactile_paving = item.get("tactile_paving", False)
        if not isinstance(tactile_paving, bool):
            raise ValueError(f"Edge {item['id']!r} tactile_paving must be true or false")
        street_lights = item.get("street_lights", True)
        if not isinstance(street_lights, bool):
            raise ValueError(f"Edge {item['id']!r} street_lights must be true or false")
        geometry_item = item.get("geometry")
        geometry = None
        if geometry_item is not None:
            if not isinstance(geometry_item, dict):
                raise ValueError(f"Edge {item['id']!r} geometry must be an object")
            kind = geometry_item.get("type", "line")
            if kind not in {"line", "cubic_bezier"}:
                raise ValueError(f"Edge {item['id']!r} geometry type must be line or cubic_bezier")
            control_from = geometry_item.get("control_from")
            control_to = geometry_item.get("control_to")
            if kind == "cubic_bezier":
                for label, point in (("control_from", control_from), ("control_to", control_to)):
                    if (not isinstance(point, list) or len(point) != 2
                            or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                                   for v in point)):
                        raise ValueError(f"Edge {item['id']!r} {label} must be [x, y]")
                control_from, control_to = tuple(control_from), tuple(control_to)
            elif control_from is not None or control_to is not None:
                raise ValueError(f"Edge {item['id']!r} line geometry cannot have control points")
            geometry = EdgeGeometry(kind, control_from, control_to)
        edge_items.append(Edge(
            id=item["id"],
            start=item["from"],
            end=item["to"],
            road_class=item.get("road_class", road.road_class if road else "local"),
            speed_limit=item.get("speed_limit", road.speed_limit if road else 30),
            lanes_each_way=item.get("lanes_each_way", road.lanes_each_way if road else 1),
            sidewalks=item.get("sidewalks", road.sidewalks if road else "none"),
            approaches=item.get("approaches", {}),
            guardrail=guardrail,
            planting=planting,
            street_trees=street_trees,
            street_lights=street_lights,
            median=median,
            median_width=median_width,
            center_marking=center_marking,
            bicycle_lane=bicycle_lane,
            curb_parking_prohibition=curb_parking_prohibition,
            tactile_paving=tactile_paving,
            road_id=road_id,
            geometry=geometry,
        ))
    edges = tuple(edge_items)
    unknown = {endpoint for edge in edges for endpoint in (edge.start, edge.end)} - set(nodes)
    if unknown:
        raise ValueError(f"Unknown network nodes: {sorted(unknown)}")
    valid_node_kinds = {
        "boundary", "signalized_cross", "signalized_t_junction",
        "signalized_pedestrian_crossing", "stop_cross", "stop_t_junction",
        "priority_t_junction",
    }
    invalid_kinds = {node.kind for node in nodes.values()} - valid_node_kinds
    if invalid_kinds:
        raise ValueError(f"Unsupported node type(s): {sorted(invalid_kinds)}")
    phase_options = {
        "signalized_cross": {
            "east_west_green", "north_south_green",
            "east_west_right_arrow", "north_south_right_arrow", "all_red",
            "east_west_yellow", "north_south_yellow",
            "group_a_green", "group_b_green", "group_a_yellow", "group_b_yellow",
            "group_a_right_arrow", "group_b_right_arrow",
        },
        "signalized_t_junction": {
            "east_west_green", "north_south_green",
            "east_west_yellow", "north_south_yellow", "all_red",
            "group_a_green", "group_b_green", "group_a_yellow", "group_b_yellow",
        },
        "signalized_pedestrian_crossing": {"vehicle_green", "pedestrian_green", "all_red"},
    }
    for node in nodes.values():
        if node.exterior_color not in {"white", "brown"}:
            raise ValueError(
                f"Node {node.id!r} exterior_color must be 'white' or 'brown'"
            )
        if node.vehicle_arrow not in {"none", "right"}:
            raise ValueError(
                f"Node {node.id!r} vehicle_arrow must be 'none' or 'right'"
            )
        if node.kind in phase_options and node.signal_phase not in phase_options[node.kind]:
            raise ValueError(
                f"Node {node.id!r} requires signal_phase in {sorted(phase_options[node.kind])}"
            )
        if node.signal_phase.endswith("_right_arrow") and node.vehicle_arrow != "right":
            raise ValueError(
                f"Node {node.id!r} uses a right-arrow phase without vehicle_arrow='right'"
            )
        level = node.pedestrian_countdown_blue_level
        if level is not None and (not isinstance(level, int) or isinstance(level, bool)
                                  or not 0 <= level <= 8):
            raise ValueError(
                f"Node {node.id!r} pedestrian_countdown_blue_level must be an integer 0..8"
            )
        if node.kind in {"signalized_t_junction", "stop_t_junction",
                         "priority_t_junction"}:
            incident = [edge for edge in edges if node.id in {edge.start, edge.end}]
            if len(incident) != 3:
                raise ValueError(
                    f"Node {node.id!r} {node.kind} requires exactly 3 incident edges"
                )
        if node.kind == "stop_cross":
            incident = [edge for edge in edges if node.id in {edge.start, edge.end}]
            if len(incident) != 4:
                raise ValueError(
                    f"Node {node.id!r} stop_cross requires exactly 4 incident edges")
        if node.kind in {"stop_cross", "stop_t_junction"} and set(node.crossings) != {
                "east_west", "north_south"}:
            raise ValueError(
                f"Node {node.id!r} {node.kind} requires all connected crosswalks")
        if node.kind == "priority_t_junction":
            incident = [edge for edge in edges if node.id in {edge.start, edge.end}]
            controlled = [edge for edge in incident if edge.approaches.get(
                "from" if edge.start == node.id else "to", {}).get(
                    "stop_control", False)]
            through_groups = {}
            for edge in incident:
                if edge not in controlled:
                    through_groups.setdefault(edge.road_id, []).append(edge)
            through = next((items for road_id, items in through_groups.items()
                            if road_id and len(items) == 2), None)
            if len(controlled) != 1 or controlled[0].lanes_each_way != 1:
                raise ValueError(
                    f"Node {node.id!r} priority_t_junction requires exactly one "
                    "one-lane stop-controlled stem")
            if through is None or any(edge.lanes_each_way < 2 or not edge.median
                                      for edge in through):
                raise ValueError(
                    f"Node {node.id!r} priority_t_junction requires one continuous "
                    "2+-lane median through road")
    for road in roads.values():
        if (not isinstance(road.lanes_each_way, int)
                or isinstance(road.lanes_each_way, bool)
                or road.lanes_each_way < 1):
            raise ValueError(f"Road {road.id!r} lanes_each_way must be a positive integer")
        if road.sidewalks not in {"none", "both"}:
            raise ValueError(f"Road {road.id!r} has unsupported sidewalks={road.sidewalks!r}")
    for edge in edges:
        if (not isinstance(edge.lanes_each_way, int) or isinstance(edge.lanes_each_way, bool)
                or edge.lanes_each_way < 1):
            raise ValueError(f"Edge {edge.id!r} lanes_each_way must be a positive integer")
        start = nodes[edge.start].position
        end = nodes[edge.end].position
        from .geometry import Centerline
        centerline = Centerline.from_edge(RoadNetwork(nodes, edges, (), roads), edge)
        if centerline.has_self_intersection():
            raise ValueError(f"Edge {edge.id!r} centreline self-intersects")
        # Road Structure Ordinance guidance ties minimum horizontal radius to
        # design speed. These conservative urban-road values keep authored
        # curves in the deliberately gentle range supported by this generator.
        minimum_radius = 60.0 if edge.speed_limit >= 40 else 30.0
        if centerline.minimum_sampled_radius() < minimum_radius - 1e-6:
            raise ValueError(
                f"Edge {edge.id!r} curve radius is below {minimum_radius:g} m "
                f"for speed_limit={edge.speed_limit}"
            )
        # An edge must describe one graph segment, not cross intermediate nodes.
        # Otherwise its road, sidewalks and markings are drawn straight through
        # intersections that should have their own trimmed geometry.
        for node in nodes.values():
            if node.id in {edge.start, edge.end}:
                continue
            x, y = node.position
            along, distance = centerline.project_point((x, y))
            if distance < 1e-5 and 1e-4 < along < centerline.length - 1e-4:
                raise ValueError(
                    f"Edge {edge.id!r} passes through intermediate node {node.id!r}; "
                    "split the edge at that node"
                )
        if edge.sidewalks not in {"none", "both"}:
            raise ValueError(f"Edge {edge.id!r} has unsupported sidewalks={edge.sidewalks!r}")
        if edge.median and edge.lanes_each_way < 2:
            raise ValueError(
                f"Edge {edge.id!r} median requires lanes_each_way >= 2"
            )
        for endpoint, attrs in edge.approaches.items():
            if endpoint not in {"from", "to"} or not isinstance(attrs, dict):
                raise ValueError(
                    f"Edge {edge.id!r} approaches must contain from/to objects")
            extra_lane = attrs.get("extra_inbound_lane", False)
            if not isinstance(extra_lane, bool):
                raise ValueError(
                    f"Edge {edge.id!r} extra_inbound_lane must be true or false")
            if extra_lane and edge.lanes_each_way < 2:
                raise ValueError(
                    f"Edge {edge.id!r} extra_inbound_lane requires "
                    "lanes_each_way >= 2")
            if extra_lane:
                node_id = edge.start if endpoint == "from" else edge.end
                if nodes[node_id].kind not in {
                        "signalized_cross", "signalized_t_junction"}:
                    raise ValueError(
                        f"Edge {edge.id!r} extra_inbound_lane endpoint must "
                        "be a signalized cross or T junction")
                if (nodes[node_id].kind == "signalized_t_junction"
                        and not edge.median):
                    raise ValueError(
                        f"Edge {edge.id!r} extra_inbound_lane at a T junction "
                        "requires a median")
        if edge.center_marking == "white_dashed" and edge.lanes_each_way != 1:
            raise ValueError(
                f"Edge {edge.id!r} white_dashed center_marking requires "
                "lanes_each_way == 1"
            )
        if edge.center_marking == "white_solid" and edge.lanes_each_way != 1:
            raise ValueError(
                f"Edge {edge.id!r} white_solid center_marking requires "
                "lanes_each_way == 1"
            )
        if edge.center_marking == "none" and edge.lanes_each_way != 1:
            raise ValueError(
                f"Edge {edge.id!r} none center_marking requires "
                "lanes_each_way == 1"
            )
        if edge.planting is not None and edge.sidewalks != "both":
            raise ValueError(
                f"Edge {edge.id!r} planting requires sidewalks='both'"
            )
        if (edge.street_trees is not None and edge.street_trees.enabled
                and edge.planting is None):
            raise ValueError(
                f"Edge {edge.id!r} street_trees requires planting"
            )
        if edge.curb_parking_prohibition and edge.sidewalks != "both":
            raise ValueError(
                f"Edge {edge.id!r} curb_parking_prohibition requires sidewalks='both'"
            )
        if edge.tactile_paving and edge.sidewalks != "both":
            raise ValueError(
                f"Edge {edge.id!r} tactile_paving requires sidewalks='both'"
            )
    context = data.get("context", {})
    if context.get("guardrails"):
        raise ValueError("context.guardrails is unsupported; use edges[].guardrail")
    from .subway import parse_subway_entrances
    subway_entrances = parse_subway_entrances(context.get("subway_entrances", []))
    buildings = tuple(ContextBuilding(
        id=item["id"], position=tuple(item["position"]), size=tuple(item["size"]),
        height=item["height"], roof_tilt_degrees=item.get("roof_tilt_degrees", 0.0),
    ) for item in context.get("buildings", ()))
    component_items = data.get("components", [])
    if not isinstance(component_items, list):
        raise ValueError("components must be an array")
    component_ids = set()
    components = []
    edge_map = {edge.id: edge for edge in edges}
    for item in component_items:
        if not isinstance(item, dict):
            raise ValueError("components entries must be objects")
        component_id = item.get("id")
        kind = item.get("type")
        edge_id = item.get("edge")
        side = item.get("side")
        station = item.get("station")
        if not isinstance(component_id, str) or not component_id:
            raise ValueError("component id must be a non-empty string")
        if component_id in component_ids:
            raise ValueError(f"Duplicate component id: {component_id!r}")
        component_ids.add(component_id)
        if kind != "driveway_cutout":
            raise ValueError(f"Component {component_id!r} has unsupported type {kind!r}")
        if edge_id not in edge_map:
            raise ValueError(f"Component {component_id!r} references unknown edge {edge_id!r}")
        if side not in {"left", "right"}:
            raise ValueError(f"Component {component_id!r} side must be left or right")
        if not isinstance(station, (int, float)) or isinstance(station, bool):
            raise ValueError(f"Component {component_id!r} station must be a number")
        edge = edge_map[edge_id]
        if edge.sidewalks != "both":
            raise ValueError(f"Component {component_id!r} requires sidewalks='both'")
        components.append(RoadComponent(
            component_id, kind, edge_id, side, float(station)))
    return RoadNetwork(nodes=nodes, edges=edges, buildings=buildings,
                       roads=roads, scene=scene, components=tuple(components),
                       subway_entrances=subway_entrances)
