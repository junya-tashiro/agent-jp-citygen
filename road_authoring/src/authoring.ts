import type { CenterTreatment, Road, RoadEdge, RoadNetworkDocument, RoadNode } from "./model";

export type Point = [number, number];
export interface RoadStyle {
  road_class: string;
  speed_limit: number;
  lanes_each_way: number;
  sidewalks: "none" | "both";
  center_treatment: CenterTreatment;
  median_width: "narrow" | "wide";
  bicycle_lane: boolean;
  curb_parking_prohibition: boolean;
  tactile_paving: boolean;
  guardrail: false | { exterior_color: "white" | "brown" };
  planting: false | { random: true; style: "legacy" | "clipped_hedge"; seed?: number };
  street_trees: false | { random: boolean; species: "keyaki" | "ginkgo" | "cherry"; density: number; seed?: number };
  street_lights: boolean;
}
export interface AuthoredRoad { id: string; start: Point; end: Point; style: RoadStyle }
export interface JunctionStyle { exterior_color: "white" | "brown"; name?: string; roman_name?: string; sequence?: number; signal_control?: "signalized" | "unsignalized" | "unsignalized_n_by_1"; extra_inbound_lane?: boolean }
export interface EditorDocument { roads: AuthoredRoad[]; junctions?: Record<string, JunctionStyle>; scene?: { time_of_day: "day" | "night" } }

export const DEFAULT_STYLE: RoadStyle = {
  road_class: "local", speed_limit: 30, lanes_each_way: 1, sidewalks: "both",
  center_treatment: "orange_solid", median_width: "narrow", bicycle_lane: true, curb_parking_prohibition: true,
  tactile_paving: true,
  guardrail: { exterior_color: "brown" }, planting: { random: true, style: "clipped_hedge" },
  street_trees: { random: true, species: "keyaki", density: 1 },
  street_lights: true,
};
export const EMPTY_EDITOR_DOCUMENT: EditorDocument = { roads: [], junctions: {}, scene: { time_of_day: "day" } };

const key = ([x, y]: Point) => `${x},${y}`;
const pointOn = ([x, y]: Point, road: AuthoredRoad) => {
  if (road.start[1] === road.end[1]) return y === road.start[1] && x >= Math.min(road.start[0], road.end[0]) && x <= Math.max(road.start[0], road.end[0]);
  return x === road.start[0] && y >= Math.min(road.start[1], road.end[1]) && y <= Math.max(road.start[1], road.end[1]);
};
const isHorizontal = (road: AuthoredRoad) => road.start[1] === road.end[1];
const sanitize = (value: number) => String(value).replace("-", "m").replace(".", "p");
const nodeId = ([x, y]: Point) => `node_${sanitize(x)}_${sanitize(y)}`;

export function validateRoads(editor: EditorDocument): string[] {
  const errors: string[] = [];
  const ids = new Set<string>();
  for (const road of editor.roads) {
    if (!road.id || ids.has(road.id)) errors.push(`道路IDが空または重複しています: ${road.id || "(空)"}`); ids.add(road.id);
    if (road.start[0] !== road.end[0] && road.start[1] !== road.end[1]) errors.push(`${road.id}: 道路は水平または垂直である必要があります`);
    if (key(road.start) === key(road.end)) errors.push(`${road.id}: 道路の長さが0です`);
    if (!Number.isInteger(road.style.lanes_each_way) || road.style.lanes_each_way < 1) errors.push(`${road.id}: 車線数は1以上の整数です`);
    if (road.style.center_treatment === "median" && road.style.lanes_each_way < 2) errors.push(`${road.id}: 中央分離帯には片側2車線以上が必要です`);
    if (road.style.center_treatment === "white_dashed" && road.style.lanes_each_way !== 1) errors.push(`${road.id}: 白点線は片側1車線専用です`);
    if (road.style.center_treatment === "none" && road.style.lanes_each_way !== 1) errors.push(`${road.id}: 中央線なしは片側1車線専用です`);
    if ((road.style.planting || road.style.curb_parking_prohibition || road.style.tactile_paving) && road.style.sidewalks !== "both") errors.push(`${road.id}: 道路設備には歩道が必要です`);
    if (road.style.street_trees && !road.style.planting) errors.push(`${road.id}: 街路樹には植え込みが必要です`);
  }
  for (let i = 0; i < editor.roads.length; i++) for (let j = i + 1; j < editor.roads.length; j++) {
    const a = editor.roads[i], b = editor.roads[j];
    if (isHorizontal(a) !== isHorizontal(b)) continue;
    const sameLine = isHorizontal(a) ? a.start[1] === b.start[1] : a.start[0] === b.start[0]; if (!sameLine) continue;
    const [a0, a1] = isHorizontal(a) ? [Math.min(a.start[0], a.end[0]), Math.max(a.start[0], a.end[0])] : [Math.min(a.start[1], a.end[1]), Math.max(a.start[1], a.end[1])];
    const [b0, b1] = isHorizontal(b) ? [Math.min(b.start[0], b.end[0]), Math.max(b.start[0], b.end[0])] : [Math.min(b.start[1], b.end[1]), Math.max(b.start[1], b.end[1])];
    if (Math.min(a1, b1) > Math.max(a0, b0)) errors.push(`${a.id}と${b.id}: 同一直線上で道路が重複しています`);
  }
  return errors;
}

function splitPoints(editor: EditorDocument) {
  const result = new Map(editor.roads.map((road) => [road.id, new Map([[key(road.start), road.start], [key(road.end), road.end]])]));
  for (let i = 0; i < editor.roads.length; i++) for (let j = i + 1; j < editor.roads.length; j++) {
    const a = editor.roads[i], b = editor.roads[j];
    if (isHorizontal(a) === isHorizontal(b)) continue;
    const horizontal = isHorizontal(a) ? a : b, vertical = isHorizontal(a) ? b : a;
    const p: Point = [vertical.start[0], horizontal.start[1]];
    if (pointOn(p, horizontal) && pointOn(p, vertical)) { result.get(horizontal.id)!.set(key(p), p); result.get(vertical.id)!.set(key(p), p); }
  }
  return result;
}

function edgeFeatures(style: RoadStyle): Partial<RoadEdge> {
  return {
    median: style.center_treatment === "median",
    ...(style.center_treatment === "median" ? { median_width: style.median_width ?? "narrow" } : {}),
    ...(style.center_treatment === "median" ? {} : { center_marking: style.center_treatment }),
    bicycle_lane: style.bicycle_lane,
    curb_parking_prohibition: style.curb_parking_prohibition,
    tactile_paving: style.tactile_paving,
    street_lights: style.street_lights,
    ...(style.guardrail ? { guardrail: { sides: "both" as const, exterior_color: style.guardrail.exterior_color } } : {}),
    ...(style.planting ? { planting: { random: true, style: "clipped_hedge" as const, ...(style.planting.seed == null ? {} : { seed: style.planting.seed }) } } : {}),
    ...(style.street_trees ? { street_trees: { enabled: true, ...style.street_trees, ...(style.street_trees.random ? { species_pool: ["keyaki", "ginkgo"] as const } : {}) } } : {}),
  };
}

export function compileV1(editor: EditorDocument): RoadNetworkDocument {
  const errors = validateRoads(editor); if (errors.length) throw new Error(errors.join("\n"));
  const splits = splitPoints(editor); const edges: RoadEdge[] = []; const coordinates = new Map<string, Point>();
  for (const road of editor.roads) {
    const points = [...splits.get(road.id)!.values()].sort((a, b) => isHorizontal(road) ? a[0] - b[0] : a[1] - b[1]);
    points.forEach((p) => coordinates.set(key(p), p));
    for (let i = 0; i < points.length - 1; i++) edges.push({ id: `${road.id}_edge_${i + 1}`, road: road.id, from: nodeId(points[i]), to: nodeId(points[i + 1]), ...edgeFeatures(road.style) });
  }
  const degree = new Map<string, number>(); for (const edge of edges) { degree.set(edge.from, (degree.get(edge.from) ?? 0) + 1); degree.set(edge.to, (degree.get(edge.to) ?? 0) + 1); }
  const nodes: RoadNode[] = [...coordinates.values()].map((position) => {
    const id = nodeId(position), count = degree.get(id) ?? 0;
    if (count === 1) return { id, type: "boundary", position };
    const junction = editor.junctions?.[key(position)], exterior_color = junction?.exterior_color ?? "brown", name = junction?.name ?? "", roman_name = junction?.roman_name ?? "";
    if (count === 3) return { id, type: "signalized_t_junction", position, name, roman_name, crossings: ["east_west", "north_south"], signal_phase: (Math.abs(position[0] + position[1]) % 2 ? "north_south_green" : "east_west_green"), exterior_color, vehicle_arrow: "none" };
    if (count === 4) return { id, type: "signalized_cross", position, name, roman_name, crossings: ["east_west", "north_south"], signal_phase: (Math.abs(position[0] + position[1]) % 2 ? "north_south_green" : "east_west_green"), exterior_color, vehicle_arrow: "none" };
    throw new Error(`座標(${position.join(", ")})の接続数が${count}です。道路端同士の接続や三重交差は未対応です`);
  });
  const roads: Road[] = editor.roads.map(({ id, style }) => ({ id, road_class: style.road_class, speed_limit: style.speed_limit, lanes_each_way: style.lanes_each_way, sidewalks: style.sidewalks }));
  return { scene: { time_of_day: editor.scene?.time_of_day ?? "day" }, roads, nodes, edges };
}

// The editor intentionally normalizes every enabled planting to the tall hedge.
// Legacy density/style fields therefore do not make an imported road incompatible.
const comparablePlanting = (planting: RoadEdge["planting"]) => planting ? { ...(planting.seed == null ? {} : { seed: planting.seed }) } : false;
const comparableFeatures = (edge: RoadEdge) => JSON.stringify({ median: edge.median ?? false, median_width: edge.median ? edge.median_width ?? "narrow" : "narrow", center_marking: edge.center_marking ?? "orange_solid", bicycle_lane: edge.bicycle_lane ?? false, curb_parking_prohibition: edge.curb_parking_prohibition ?? false, tactile_paving: edge.tactile_paving ?? false, street_lights: edge.street_lights ?? true, guardrail: edge.guardrail ?? false, planting: comparablePlanting(edge.planting), street_trees: edge.street_trees ?? false });

export function importV1(document: RoadNetworkDocument): EditorDocument {
  if (!Array.isArray(document.roads) || !Array.isArray(document.nodes) || !Array.isArray(document.edges)) throw new Error("roads、nodes、edgesが必要です");
  const nodes = new Map(document.nodes.map((node) => [node.id, node])); const roads: AuthoredRoad[] = [];
  for (const road of document.roads) {
    const members = document.edges.filter((edge) => edge.road === road.id); if (!members.length) throw new Error(`${road.id}: 所属edgeがありません`);
    const points = members.flatMap((edge) => [nodes.get(edge.from)?.position, nodes.get(edge.to)?.position]).filter(Boolean) as Point[];
    const horizontal = points.every((point) => point[1] === points[0][1]), vertical = points.every((point) => point[0] === points[0][0]);
    if (!horizontal && !vertical) throw new Error(`${road.id}: 異なる直線上のedgeが混在しています`);
    const feature = comparableFeatures(members[0]); if (members.some((edge) => comparableFeatures(edge) !== feature)) throw new Error(`${road.id}: edgeごとの道路設備設定が一致していません`);
    const sorted = [...new Map(points.map((p) => [key(p), p])).values()].sort((a, b) => horizontal ? a[0] - b[0] : a[1] - b[1]);
    const first = members[0];
    roads.push({ id: road.id, start: sorted[0], end: sorted[sorted.length - 1], style: {
      road_class: road.road_class ?? "local", speed_limit: road.speed_limit ?? 30, lanes_each_way: road.lanes_each_way ?? 1, sidewalks: road.sidewalks ?? "none",
      center_treatment: first.median ? "median" : first.center_marking ?? "orange_solid", median_width: first.median_width ?? "narrow", bicycle_lane: first.bicycle_lane ?? false, curb_parking_prohibition: first.curb_parking_prohibition ?? false, tactile_paving: first.tactile_paving ?? false,
      guardrail: first.guardrail ? { exterior_color: first.guardrail.exterior_color ?? "white" } : false,
      planting: first.planting ? { random: true, style: "clipped_hedge", ...(first.planting.seed == null ? {} : { seed: first.planting.seed }) } : false,
      street_trees: first.street_trees ? { random: first.street_trees.random ?? false, species: first.street_trees.species ?? "keyaki", density: first.street_trees.density ?? 1, ...(first.street_trees.seed == null ? {} : { seed: first.street_trees.seed }) } : false,
      street_lights: first.street_lights ?? true,
    } });
  }
  let sequence = 0;
  const junctions = Object.fromEntries(document.nodes.filter((node) => ["signalized_cross", "signalized_t_junction", "stop_cross", "stop_t_junction", "priority_t_junction"].includes(node.type)).map((node) => [key(node.position), { exterior_color: node.exterior_color === "white" ? "white" as const : "brown" as const, name: node.name ?? "", roman_name: node.roman_name ?? "", sequence: ++sequence, signal_control: node.type === "priority_t_junction" ? "unsignalized_n_by_1" as const : node.type.startsWith("stop_") ? "unsignalized" as const : "signalized" as const }]));
  const editor: EditorDocument = { roads, junctions, scene: { time_of_day: document.scene?.time_of_day ?? "day" } }; compileV1(editor);
  const expected = compileV1(editor); if (expected.nodes.length !== document.nodes.length || expected.edges.length !== document.edges.length) throw new Error("道路の交点・分割edgeがこのエディタの規則と一致しません");
  const importedNodes = new Map(document.nodes.map((node) => [node.id, node]));
  for (const node of expected.nodes) {
    const actual = importedNodes.get(node.id);
    if (!actual || actual.type !== node.type || key(actual.position) !== key(node.position) || JSON.stringify(actual.crossings ?? []) !== JSON.stringify(node.crossings ?? []) || (actual.name ?? "") !== (node.name ?? "") || (actual.roman_name ?? "") !== (node.roman_name ?? "") || (actual.exterior_color ?? "brown") !== (node.exterior_color ?? "brown")) throw new Error(`${node.id}: 交差点の種類・位置・名称・信号色・横断歩道がこのエディタの規則と一致しません`);
  }
  const importedEdges = new Map(document.edges.map((edge) => [edge.id, edge]));
  for (const edge of expected.edges) {
    const actual = importedEdges.get(edge.id);
    if (!actual || actual.from !== edge.from || actual.to !== edge.to || actual.road !== edge.road || comparableFeatures(actual) !== comparableFeatures(edge)) throw new Error(`${edge.id}: edge分割または道路設備がこのエディタの規則と一致しません`);
  }
  return editor;
}
