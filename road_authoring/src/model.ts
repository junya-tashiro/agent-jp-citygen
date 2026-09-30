export type NodeType = "boundary" | "signalized_cross" | "signalized_t_junction" | "signalized_pedestrian_crossing" | "stop_cross" | "stop_t_junction" | "priority_t_junction";
export type ExteriorColor = "white" | "brown";
export type Axis = "east_west" | "north_south";
export type CenterTreatment = "median" | "none" | "orange_solid" | "white_solid" | "white_dashed";

export interface RoadNode {
  id: string;
  type: NodeType;
  position: [number, number];
  name?: string;
  roman_name?: string;
  crossings?: Axis[];
  signal_phase?: string;
  pedestrian_countdown_blue_level?: number;
  exterior_color?: ExteriorColor;
  vehicle_arrow?: "none" | "right";
  [key: string]: unknown;
}

export interface Road {
  id: string;
  road_class?: string;
  speed_limit?: number;
  lanes_each_way?: number;
  sidewalks?: "none" | "both";
  [key: string]: unknown;
}

export interface RoadEdge {
  id: string;
  road?: string;
  from: string;
  to: string;
  road_class?: string;
  speed_limit?: number;
  lanes_each_way?: number;
  sidewalks?: "none" | "both";
  approaches?: Record<string, { stop_control?: boolean; right_turn_lane?: boolean; extra_inbound_lane?: boolean; [key: string]: unknown }>;
  guardrail?: { sides: "none" | "left" | "right" | "both"; exterior_color?: ExteriorColor; [key: string]: unknown };
  planting?: { random?: boolean; style?: "legacy" | "clipped_hedge"; density?: number; maintenance?: number; health?: number; seed?: number; [key: string]: unknown };
  street_trees?: { enabled?: boolean; random?: boolean; species?: "keyaki" | "ginkgo" | "cherry"; species_pool?: ("keyaki" | "ginkgo" | "cherry")[]; density?: number; seed?: number; [key: string]: unknown };
  street_lights?: boolean;
  median?: boolean;
  median_width?: "narrow" | "wide";
  center_marking?: Exclude<CenterTreatment, "median">;
  bicycle_lane?: boolean;
  curb_parking_prohibition?: boolean;
  tactile_paving?: boolean;
  geometry?: { type: "line" } | { type: "cubic_bezier"; control_from: [number, number]; control_to: [number, number] };
  [key: string]: unknown;
}

export interface RoadComponent {
  id: string;
  type: "driveway_cutout";
  edge: string;
  side: "left" | "right";
  station: number;
}

export interface ContextBuilding {
  id: string;
  position: [number, number];
  size: [number, number];
  height: number;
  roof_tilt_degrees?: number;
  [key: string]: unknown;
}

export interface RoadNetworkDocument {
  scene?: { time_of_day?: "day" | "night"; [key: string]: unknown };
  roads?: Road[];
  nodes: RoadNode[];
  edges: RoadEdge[];
  components?: RoadComponent[];
  context?: { buildings?: ContextBuilding[]; [key: string]: unknown };
  [key: string]: unknown;
}

export type Selection = { kind: "node" | "edge" | "road" | "building"; id: string } | null;
export type Tool = "select" | "road" | "node" | "split" | "delete" | "pan";

export const EMPTY_DOCUMENT: RoadNetworkDocument = { roads: [], nodes: [], edges: [] };

export const DEFAULT_DOCUMENT: RoadNetworkDocument = {
  roads: [{ id: "road_1", road_class: "local", speed_limit: 30, lanes_each_way: 1, sidewalks: "both" }],
  nodes: [
    { id: "west", type: "boundary", position: [-20, 0] },
    { id: "cross", type: "signalized_cross", position: [0, 0], crossings: ["east_west", "north_south"], signal_phase: "east_west_green", exterior_color: "white", vehicle_arrow: "none" },
    { id: "east", type: "boundary", position: [20, 0] },
  ],
  edges: [
    { id: "edge_1", road: "road_1", from: "west", to: "cross" },
    { id: "edge_2", road: "road_1", from: "cross", to: "east" },
  ],
};

export function cloneDocument(doc: RoadNetworkDocument): RoadNetworkDocument {
  return structuredClone(doc);
}

export function uniqueId(prefix: string, existing: string[]): string {
  let i = 1;
  while (existing.includes(`${prefix}_${i}`)) i++;
  return `${prefix}_${i}`;
}

export function effectiveEdge(edge: RoadEdge, doc: RoadNetworkDocument) {
  const road = doc.roads?.find((item) => item.id === edge.road);
  return {
    road_class: edge.road_class ?? road?.road_class ?? "local",
    speed_limit: edge.speed_limit ?? road?.speed_limit ?? 30,
    lanes_each_way: edge.lanes_each_way ?? road?.lanes_each_way ?? 1,
    sidewalks: edge.sidewalks ?? road?.sidewalks ?? "none",
  };
}

export function signalPhases(type: NodeType): string[] {
  if (type === "signalized_cross") return ["east_west_green", "north_south_green", "east_west_right_arrow", "north_south_right_arrow", "east_west_yellow", "north_south_yellow", "all_red"];
  if (type === "signalized_t_junction") return ["east_west_green", "north_south_green", "east_west_yellow", "north_south_yellow", "all_red"];
  if (type === "signalized_pedestrian_crossing") return ["vehicle_green", "pedestrian_green", "all_red"];
  return [];
}
