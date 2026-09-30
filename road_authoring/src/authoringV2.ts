import { DEFAULT_STYLE, type EditorDocument, type JunctionStyle, type RoadStyle } from "./authoring";
import { curveIntersections, cubicPoint, cubicTangent, distance, interpolate, minimumRadius, sampleCubic, subCubic, type Point } from "./geometry";
import type { Road, RoadComponent, RoadEdge, RoadNetworkDocument, RoadNode } from "./model";

export type KeyPointKind = "anchor" | "junction";
export interface KeyPoint { id: string; position: Point; kind: KeyPointKind }
export interface AuthoredRoadV2 { id: string; keyPointIds: string[]; style: RoadStyle }
export interface AuthoredComponentV2 { id: string; type: "driveway_cutout"; roadId: string; side: "left" | "right"; stationM: number }
export interface EditorDocumentV2 { version: 2; scene?: { time_of_day: "day" | "night" }; keyPoints: Record<string, KeyPoint>; roads: AuthoredRoadV2[]; junctions: Record<string, JunctionStyle>; components: AuthoredComponentV2[] }
export interface ValidationResult { valid: boolean; errors: string[] }

export const EMPTY_EDITOR_V2: EditorDocumentV2 = { version: 2, scene: { time_of_day: "day" }, keyPoints: {}, roads: [], junctions: {}, components: [] };
export const DRIVEWAY_CUTOUT_HALF_EXTENT_M = 3.6;
export const DRIVEWAY_JUNCTION_CLEARANCE_M = 10;
export const STRAIGHT_AFTER_CROSSWALK_M = 10;
export const EXTRA_INBOUND_LANE_LENGTH_M = 50;
export const EXTRA_INBOUND_LANE_LINK_DISTANCE_M = 150;
export const EXTRA_INBOUND_LANE_MIN_JUNCTION_SPACING_M = 80;
const LANE_WIDTH_M = 3.25;
const roadWidth = (style: RoadStyle) => style.lanes_each_way * 2 * LANE_WIDTH_M
  + (style.center_treatment === "median" && style.median_width === "wide" ? LANE_WIDTH_M : 0);
const CROSSWALK_OFFSET_FROM_ROAD_EDGE_M = 5.75;
const CROSSWALK_HALF_WIDTH_M = 1.60;
const APPROACH_SPLIT_MARGIN_M = 0.50;
const clone = <T,>(v: T): T => structuredClone(v);
const near = (a: Point, b: Point, epsilon = .35) => distance(a, b) <= epsilon;
const clean = (s: string) => s.replace(/[^a-zA-Z0-9_]/g, "_");
const unique = (prefix: string, ids: Set<string>) => { let i = 1; while (ids.has(`${prefix}_${i}`)) i++; return `${prefix}_${i}`; };
export const roadPoints = (doc: EditorDocumentV2, road: AuthoredRoadV2) => road.keyPointIds.map((id) => doc.keyPoints[id].position);

type RoadProjection = { roadId: string; stationM: number; side: "left" | "right"; distanceM: number; point: Point; tangent: Point };
function sampledRoad(doc: EditorDocumentV2, road: AuthoredRoadV2, steps = 64) {
  const out: { point: Point; tangent: Point; stationM: number }[] = []; let stationM = 0;
  for (const [segmentIndex, { cubic }] of interpolate(roadPoints(doc, road)).entries()) for (let i = segmentIndex ? 1 : 0; i <= steps; i++) {
    const point = cubicPoint(cubic, i / steps); if (out.length) stationM += distance(out.at(-1)!.point, point);
    out.push({ point, tangent: cubicTangent(cubic, i / steps), stationM });
  }
  return out;
}
export function projectToRoad(doc: EditorDocumentV2, target: Point): RoadProjection | null {
  let best: RoadProjection | null = null;
  for (const road of doc.roads) {
    const samples = sampledRoad(doc, road);
    for (let i = 0; i < samples.length - 1; i++) {
      const a = samples[i], b = samples[i + 1], dx = b.point[0] - a.point[0], dy = b.point[1] - a.point[1], lengthSquared = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, ((target[0] - a.point[0]) * dx + (target[1] - a.point[1]) * dy) / Math.max(lengthSquared, 1e-9)));
      const point: Point = [a.point[0] + dx * t, a.point[1] + dy * t], candidate = distance(target, point);
      if (best && candidate >= best.distanceM) continue;
      const tangent: Point = [dx / Math.sqrt(lengthSquared), dy / Math.sqrt(lengthSquared)];
      const signed = tangent[0] * (target[1] - point[1]) - tangent[1] * (target[0] - point[0]);
      best = { roadId: road.id, stationM: a.stationM + Math.sqrt(lengthSquared) * t, side: signed >= 0 ? "left" : "right", distanceM: candidate, point, tangent };
    }
  }
  return best;
}
export function pointAtRoadStation(doc: EditorDocumentV2, road: AuthoredRoadV2, stationM: number) {
  const samples = sampledRoad(doc, road); if (!samples.length) return null;
  for (let i = 0; i < samples.length - 1; i++) if (stationM <= samples[i + 1].stationM) {
    const a = samples[i], b = samples[i + 1], t = (stationM - a.stationM) / Math.max(1e-9, b.stationM - a.stationM);
    return { point: [a.point[0] + (b.point[0] - a.point[0]) * t, a.point[1] + (b.point[1] - a.point[1]) * t] as Point, tangent: a.tangent };
  }
  return { point: samples.at(-1)!.point, tangent: samples.at(-1)!.tangent };
}

function componentErrors(doc: EditorDocumentV2, component: AuthoredComponentV2, peers = doc.components ?? []) {
  const errors: string[] = [], road = doc.roads.find((item) => item.id === component.roadId);
  if (!road) return [`${component.id}: 存在しない道路を参照しています`];
  if (road.style.sidewalks !== "both") errors.push(`${component.id}: 切り欠きには歩道が必要です`);
  const samples = sampledRoad(doc, road), length = samples.at(-1)?.stationM ?? 0;
  const junctionStations = road.keyPointIds
    .filter((id) => doc.keyPoints[id]?.kind === "junction")
    .map((id) => ({ id, station: samples.reduce((best, sample) => distance(sample.point, doc.keyPoints[id].position) < distance(best.point, doc.keyPoints[id].position) ? sample : best).stationM }));
  if (component.stationM < DRIVEWAY_CUTOUT_HALF_EXTENT_M || component.stationM > length - DRIVEWAY_CUTOUT_HALF_EXTENT_M || junctionStations.some(({ id, station }) => Math.abs(component.stationM - station) < approachLength(doc, id, road) + DRIVEWAY_CUTOUT_HALF_EXTENT_M)) errors.push(`${component.id}: 交差点・道路端から近すぎます`);
  if (peers.some((other) => other.id !== component.id && other.roadId === component.roadId && other.side === component.side && Math.abs(other.stationM - component.stationM) < DRIVEWAY_CUTOUT_HALF_EXTENT_M * 2)) errors.push(`${component.id}: 別の切り欠きと重なっています`);
  return errors;
}

export function pruneInvalidComponents(source: EditorDocumentV2) {
  const doc = clone(source), kept: AuthoredComponentV2[] = [], removed: string[] = [];
  for (const component of doc.components ?? []) {
    if (componentErrors(doc, component, kept).length) removed.push(component.id);
    else kept.push(component);
  }
  doc.components = kept;
  return { document: doc, removed };
}

function approachLength(doc: EditorDocumentV2, junctionId: string, road: AuthoredRoadV2) {
  const crossingWidths = doc.roads
    .filter((candidate) => candidate.id !== road.id && candidate.keyPointIds.includes(junctionId))
    .map((candidate) => roadWidth(candidate.style));
  // Invalid/incomplete junctions still need a deterministic preview. Once a
  // second road exists, its actual carriageway width controls the crosswalk
  // station for this arm rather than one junction-wide maximum lane count.
  const perpendicularWidth = crossingWidths.length
    ? Math.max(...crossingWidths)
    : roadWidth(road.style);
  const ordinary = perpendicularWidth * .5 + CROSSWALK_OFFSET_FROM_ROAD_EDGE_M
    + CROSSWALK_HALF_WIDTH_M + STRAIGHT_AFTER_CROSSWALK_M;
  return junctionHasAutomaticExtraInboundLane(doc, junctionId)
    ? Math.max(ordinary, EXTRA_INBOUND_LANE_LENGTH_M) : ordinary;
}

function compilationKeyPointIds(doc: EditorDocumentV2, road: AuthoredRoadV2) {
  const removed = new Set<string>();
  for (const junctionId of road.keyPointIds.filter((id) => doc.keyPoints[id]?.kind === "junction")) {
    const index = road.keyPointIds.indexOf(junctionId);
    const minimumRadius = road.style.speed_limit <= 30 ? 30 : 60;
    const required = approachLength(doc, junctionId, road) + APPROACH_SPLIT_MARGIN_M + minimumRadius * .5;
    for (const direction of [-1, 1]) {
      for (let cursor = index + direction; cursor >= 0 && cursor < road.keyPointIds.length; cursor += direction) {
        const id = road.keyPointIds[cursor];
        if (doc.keyPoints[id].kind === "junction") break;
        if (distance(doc.keyPoints[junctionId].position, doc.keyPoints[id].position) > required) break;
        if (cursor === 0 || cursor === road.keyPointIds.length - 1) break;
        removed.add(id);
      }
    }
  }
  return road.keyPointIds.filter((id) => !removed.has(id));
}

function snappedEndpoint(doc: EditorDocumentV2, point: Point, tolerance = 1.25): Point {
  let best = point, bestDistance = tolerance;
  for (const road of doc.roads) for (const { cubic } of interpolate(roadPoints(doc, road))) {
    const samples = sampleCubic(cubic, 32);
    for (let index = 0; index < samples.length - 1; index++) {
      const a = samples[index].point, b = samples[index + 1].point;
      const dx = b[0] - a[0], dy = b[1] - a[1], lengthSquared = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / Math.max(lengthSquared, 1e-9)));
      const projected: Point = [a[0] + dx * t, a[1] + dy * t], candidate = distance(point, projected);
      if (candidate < bestDistance) { bestDistance = candidate; best = projected; }
    }
  }
  return best;
}

function styleErrors(road: AuthoredRoadV2) {
  const s = road.style, out: string[] = [];
  if (!Number.isInteger(s.lanes_each_way) || s.lanes_each_way < 1 || s.lanes_each_way > 3) out.push(`${road.id}: 車線数は1〜3の整数です`);
  if (s.center_treatment === "median" && s.lanes_each_way < 2) out.push(`${road.id}: 中央分離帯には片側2車線以上が必要です`);
  if ((s.center_treatment === "none" || s.center_treatment === "white_solid" || s.center_treatment === "white_dashed") && s.lanes_each_way !== 1) out.push(`${road.id}: この中央線は片側1車線専用です`);
  if ((s.planting || s.street_trees || s.tactile_paving || s.curb_parking_prohibition) && s.sidewalks !== "both") out.push(`${road.id}: 道路設備には歩道が必要です`);
  if (s.street_trees && !s.planting) out.push(`${road.id}: 街路樹には植え込みが必要です`);
  return out;
}

export function validateEditorV2(doc: EditorDocumentV2): ValidationResult {
  const errors: string[] = [], ids = new Set<string>();
  for (const road of doc.roads) {
    if (!road.id || ids.has(road.id)) errors.push(`道路IDが空または重複しています: ${road.id || "(空)"}`); ids.add(road.id);
    if (road.keyPointIds.length < 2) errors.push(`${road.id}: キーポイントが2点未満です`);
    if (road.keyPointIds.some((id) => !doc.keyPoints[id])) { errors.push(`${road.id}: 存在しないキーポイントを参照しています`); continue; }
    const points = roadPoints(doc, road);
    if (points.some((p, i) => i > 0 && distance(points[i - 1], p) < 2)) errors.push(`${road.id}: キーポイント間は2m以上必要です`);
    const radius = minimumRadius(interpolate(points));
    const limit = road.style.speed_limit <= 30 ? 30 : 60;
    if (radius < limit - .05) errors.push(`${road.id}: カーブ半径${radius.toFixed(1)}mは最小${limit}m未満です`);
    errors.push(...styleErrors(road));
  }
  const componentIds = new Set<string>();
  for (const component of doc.components ?? []) {
    if (!component.id || componentIds.has(component.id)) errors.push(`コンポーネントIDが空または重複しています: ${component.id || "(空)"}`); componentIds.add(component.id);
    errors.push(...componentErrors(doc, component));
  }
  for (let i = 0; i < doc.roads.length; i++) for (let j = i + 1; j < doc.roads.length; j++) {
    const a = doc.roads[i], b = doc.roads[j];
    const shared = new Set(a.keyPointIds.filter((id) => b.keyPointIds.includes(id)));
    for (const hit of curveIntersections(interpolate(roadPoints(doc, a)), interpolate(roadPoints(doc, b)))) {
      if (hit.angle < 80 - .01) errors.push(`${a.id}と${b.id}: 交差角${hit.angle.toFixed(1)}°は許容範囲80〜100°外です`);
    }
  }
  const degrees = new Map(Object.keys(doc.keyPoints).map((id) => [id, armCount(doc, id)]));
  for (const [id, count] of degrees) if (doc.keyPoints[id].kind === "junction" && (count < 3 || count > 4)) errors.push(`${id}: 交差点の接続道路数${count}は未対応です`);
  for (const [id, style] of Object.entries(doc.junctions)) {
    if (style.signal_control === "unsignalized"
        && !junctionSupportsUnsignalized(doc, id)) {
      errors.push(`${id}: 信号なしは接続する全道路が片側1車線の十字路・丁字路専用です`);
    }
    if (style.signal_control === "unsignalized_n_by_1"
        && !junctionSupportsPriorityT(doc, id)) {
      errors.push(`${id}: 信号なし（n×1丁字路）は中央分離帯付き片側2車線以上の直線道路と片側1車線の突き当たり道路専用です`);
    }
  }
  for (const [id] of degrees) {
    if (doc.keyPoints[id].kind !== "junction") continue;
    for (const road of doc.roads) {
      const originalIndex = road.keyPointIds.indexOf(id);
      const ids = compilationKeyPointIds(doc, road), index = ids.indexOf(id);
      if (index < 0) continue;
      const required = approachLength(doc, id, road);
      for (const direction of [-1, 1]) {
        if (originalIndex + direction < 0 || originalIndex + direction >= road.keyPointIds.length) continue;
        const neighborIndex = index + direction;
        const available = neighborIndex < 0 || neighborIndex >= ids.length ? 0
          : distance(doc.keyPoints[id].position, doc.keyPoints[ids[neighborIndex]].position);
        if (available <= required + APPROACH_SPLIT_MARGIN_M) {
          errors.push(`${road.id}: ${id}の横断歩道外端から${STRAIGHT_AFTER_CROSSWALK_M}mの直線区間を確保できません（必要${required.toFixed(1)}m、利用可能${available.toFixed(1)}m）`);
        }
      }
    }
  }
  for (const road of doc.roads) {
    const ids = compilationKeyPointIds(doc, road);
    for (let index = 0; index < ids.length - 1; index++) {
      const from = ids[index], to = ids[index + 1];
      if (doc.keyPoints[from]?.kind !== "junction"
          || doc.keyPoints[to]?.kind !== "junction"
          || !junctionHasAutomaticExtraInboundLane(doc, from)
          || !junctionHasAutomaticExtraInboundLane(doc, to)) continue;
      const available = distance(doc.keyPoints[from].position, doc.keyPoints[to].position);
      if (available + 1e-6 < EXTRA_INBOUND_LANE_MIN_JUNCTION_SPACING_M) {
        errors.push(`${road.id}: 右折進入車線を連続させる交差点間隔は${EXTRA_INBOUND_LANE_MIN_JUNCTION_SPACING_M}m以上必要です（利用可能${available.toFixed(1)}m）`);
      }
    }
  }
  if (!errors.length) {
    const compiled = compileEditorV2Unchecked(doc), positions = new Map(compiled.nodes.map((node) => [node.id, node.position]));
    const roads = new Map((compiled.roads ?? []).map((road) => [road.id, road]));
    for (const edge of compiled.edges) {
      if (edge.geometry?.type !== "cubic_bezier") continue;
      const radius = minimumRadius([{ index: 0, cubic: {
        p0: positions.get(edge.from)!, p1: edge.geometry.control_from,
        p2: edge.geometry.control_to, p3: positions.get(edge.to)!,
      } }]);
      const speed = roads.get(edge.road ?? "")?.speed_limit ?? 40, limit = speed <= 30 ? 30 : 60;
      if (radius < limit - .05) errors.push(`${edge.id}: 交差点補正後のカーブ半径${radius.toFixed(1)}mは最小${limit}m未満です`);
    }
  }
  return { valid: !errors.length, errors: [...new Set(errors)] };
}

// Inserts one shared keypoint into both road splines at every geometric crossing.
// There is no angle/radius threshold shortcut: the same topology path is used at 0° and infinitesimal perturbations.
export function normalizeIntersections(source: EditorDocumentV2): EditorDocumentV2 {
  const doc = clone(source), kpIds = new Set(Object.keys(doc.keyPoints));
  const insertions = new Map<string, { segment: number; t: number; id: string }[]>();
  for (let i = 0; i < doc.roads.length; i++) for (let j = i + 1; j < doc.roads.length; j++) {
    const a = doc.roads[i], b = doc.roads[j], ac = interpolate(roadPoints(doc, a)), bc = interpolate(roadPoints(doc, b));
    for (const hit of curveIntersections(ac, bc)) {
      const existing = [...new Set([...a.keyPointIds, ...b.keyPointIds])].find((id) => near(doc.keyPoints[id].position, hit.point));
      const endpointA = hit.aT < .015 ? a.keyPointIds[hit.aSegment] : hit.aT > .985 ? a.keyPointIds[hit.aSegment + 1] : undefined;
      const endpointB = hit.bT < .015 ? b.keyPointIds[hit.bSegment] : hit.bT > .985 ? b.keyPointIds[hit.bSegment + 1] : undefined;
      let id = existing ?? (endpointA && endpointB && near(doc.keyPoints[endpointA].position, doc.keyPoints[endpointB].position) ? endpointA : undefined);
      if (!id) { id = unique("junction", kpIds); kpIds.add(id); doc.keyPoints[id] = { id, position: hit.point, kind: "junction" }; }
      else doc.keyPoints[id].kind = "junction";
      if (endpointA && endpointA !== id) { for (const road of doc.roads) road.keyPointIds = road.keyPointIds.map((x) => x === endpointA ? id! : x); delete doc.keyPoints[endpointA]; }
      else if (!a.keyPointIds.includes(id)) (insertions.get(a.id) ?? insertions.set(a.id, []).get(a.id)!).push({ segment: hit.aSegment, t: hit.aT, id });
      if (endpointB && endpointB !== id) { for (const road of doc.roads) road.keyPointIds = road.keyPointIds.map((x) => x === endpointB ? id! : x); delete doc.keyPoints[endpointB]; }
      else if (!b.keyPointIds.includes(id)) (insertions.get(b.id) ?? insertions.set(b.id, []).get(b.id)!).push({ segment: hit.bSegment, t: hit.bT, id });
    }
  }
  for (const road of doc.roads) {
    const bySegment = new Map<number, { t: number; id: string }[]>();
    for (const item of insertions.get(road.id) ?? []) (bySegment.get(item.segment) ?? bySegment.set(item.segment, []).get(item.segment)!).push(item);
    const next: string[] = [];
    for (let i = 0; i < road.keyPointIds.length - 1; i++) { next.push(road.keyPointIds[i]); next.push(...(bySegment.get(i) ?? []).sort((a, b) => a.t - b.t).map((x) => x.id)); }
    next.push(road.keyPointIds.at(-1)!); road.keyPointIds = next.filter((id, i) => i === 0 || id !== next[i - 1]);
  }
  return cleanupTopology(doc);
}

export function armCount(doc: EditorDocumentV2, id: string) {
  let count = 0;
  for (const road of doc.roads) {
    const index = road.keyPointIds.indexOf(id);
    if (index < 0) continue;
    if (index > 0) count++;
    if (index < road.keyPointIds.length - 1) count++;
  }
  return count;
}

export function junctionSupportsUnsignalized(doc: EditorDocumentV2, id: string) {
  const arms = armCount(doc, id);
  return (arms === 3 || arms === 4)
    && doc.roads.filter((road) => road.keyPointIds.includes(id))
      .every((road) => road.style.lanes_each_way === 1);
}

export function junctionSupportsPriorityT(doc: EditorDocumentV2, id: string) {
  if (armCount(doc, id) !== 3) return false;
  const incident = doc.roads.filter((road) => road.keyPointIds.includes(id));
  if (incident.length !== 2) return false;
  const through = incident.find((road) => {
    const index = road.keyPointIds.indexOf(id);
    return index > 0 && index < road.keyPointIds.length - 1;
  });
  const stem = incident.find((road) => road !== through);
  return Boolean(through && stem
    && through.style.lanes_each_way >= 2
    && through.style.center_treatment === "median"
    && stem.style.lanes_each_way === 1);
}

export function junctionSupportsExtraInboundLane(doc: EditorDocumentV2, id: string) {
  const arms = armCount(doc, id);
  if (arms !== 3 && arms !== 4) return false;
  const incident = doc.roads.filter((road) => road.keyPointIds.includes(id));
  const eligible = (road: AuthoredRoadV2) => road.style.lanes_each_way >= 2;
  if (arms === 4) return incident.length === 2 && incident.every(eligible);
  const through = incident.find((road) => {
    const index = road.keyPointIds.indexOf(id);
    return index > 0 && index < road.keyPointIds.length - 1;
  });
  return Boolean(through && eligible(through)
    && through.style.center_treatment === "median");
}

export function junctionHasAutomaticExtraInboundLane(doc: EditorDocumentV2, id: string) {
  if ((doc.junctions[id]?.signal_control ?? "signalized") !== "signalized"
      || !junctionSupportsExtraInboundLane(doc, id)) return false;
  return true;
}

export function enforceJunctionSignalEligibility(source: EditorDocumentV2) {
  const doc = clone(source);
  for (const [id, style] of Object.entries(doc.junctions)) {
    if (style.signal_control === "unsignalized"
        && !junctionSupportsUnsignalized(doc, id)) {
      style.signal_control = "signalized";
    }
    if (style.signal_control === "unsignalized_n_by_1"
        && !junctionSupportsPriorityT(doc, id)) {
      style.signal_control = "signalized";
    }
    // The extra approach lane is topology-derived. Discard the obsolete
    // short-lived manual setting when loading an older editor document.
    delete style.extra_inbound_lane;
  }
  return doc;
}

export function cleanupTopology(source: EditorDocumentV2): EditorDocumentV2 {
  const doc = clone(source), used = new Set(doc.roads.flatMap((road) => road.keyPointIds));
  for (const id of Object.keys(doc.keyPoints)) if (!used.has(id)) delete doc.keyPoints[id];
  for (const [id, point] of Object.entries(doc.keyPoints)) {
    if (point.kind !== "junction") continue;
    if (armCount(doc, id) < 3) {
      point.kind = "anchor";
      delete doc.junctions[id];
    }
  }
  for (const id of Object.keys(doc.junctions)) if (doc.keyPoints[id]?.kind !== "junction") delete doc.junctions[id];
  return doc;
}

export function removeRoad(doc: EditorDocumentV2, roadId: string) {
  const next = clone(doc);
  next.roads = next.roads.filter((road) => road.id !== roadId);
  next.components = (next.components ?? []).filter((component) => component.roadId !== roadId);
  return cleanupTopology(next);
}

export function addDrivewayCutout(doc: EditorDocumentV2, target: Point) {
  const projection = projectToRoad(doc, target), next = clone(doc);
  if (!projection) return { document: next, componentId: null, validation: { valid: false, errors: ["道路の歩道付近をクリックしてください"] } };
  const road = next.roads.find((item) => item.id === projection.roadId)!;
  if (road.style.sidewalks !== "both") return { document: next, componentId: null, validation: { valid: false, errors: ["歩道のある道路にのみ配置できます"] } };
  const roadHalf = road.style.lanes_each_way * LANE_WIDTH_M
    + (road.style.center_treatment === "median" && road.style.median_width === "wide" ? LANE_WIDTH_M * .5 : 0);
  const sidewalkWidth = road.style.center_treatment === "median" ? 7.2 : 3.6;
  if (projection.distanceM < roadHalf - 1 || projection.distanceM > roadHalf + sidewalkWidth + 2) return { document: next, componentId: null, validation: { valid: false, errors: ["道路の歩道付近をクリックしてください"] } };
  const ids = new Set((next.components ?? []).map((item) => item.id)), id = unique("driveway_cutout", ids);
  next.components ??= []; next.components.push({ id, type: "driveway_cutout", roadId: projection.roadId, side: projection.side, stationM: projection.stationM });
  const validation = validateEditorV2(next);
  return validation.valid
    ? { document: next, componentId: id, validation }
    : { document: clone(doc), componentId: null, validation };
}

export function removeComponent(doc: EditorDocumentV2, componentId: string) { const next = clone(doc); next.components = (next.components ?? []).filter((item) => item.id !== componentId); return next; }

export function addRoad(doc: EditorDocumentV2, points: Point[], style: RoadStyle = DEFAULT_STYLE) {
  const next = clone(doc), ids = new Set(Object.keys(next.keyPoints)), roadIds = new Set(next.roads.map((r) => r.id));
  const adjusted = points.map((point, index) => index === 0 || index === points.length - 1 ? snappedEndpoint(doc, point) : point);
  const keyPointIds = adjusted.map((position) => { const id = unique("point", ids); ids.add(id); next.keyPoints[id] = { id, position, kind: "anchor" }; return id; });
  const id = unique("road", roadIds); next.roads.push({ id, keyPointIds, style: clone(style) });
  const normalized = normalizeIntersections(next), pruned = pruneInvalidComponents(normalized), validation = validateEditorV2(pruned.document);
  return { document: pruned.document, roadId: id, validation, removedComponents: pruned.removed };
}

const features = (s: RoadStyle): Partial<RoadEdge> => ({ median: s.center_treatment === "median", ...(s.center_treatment === "median" ? { median_width: s.median_width ?? "narrow" } : { center_marking: s.center_treatment }), bicycle_lane: s.bicycle_lane, curb_parking_prohibition: s.curb_parking_prohibition, tactile_paving: s.tactile_paving, street_lights: s.street_lights, ...(s.guardrail ? { guardrail: { sides: "both" as const, exterior_color: s.guardrail.exterior_color } } : {}), ...(s.planting ? { planting: { random: true, style: "clipped_hedge" as const, ...(s.planting.seed == null ? {} : { seed: s.planting.seed }) } } : {}), ...(s.street_trees ? { street_trees: { enabled: true, ...s.street_trees, ...(s.street_trees.random ? { species_pool: ["keyaki", "ginkgo"] as const } : {}) } } : {}) });

function compileEditorV2Unchecked(doc: EditorDocumentV2): RoadNetworkDocument {
  const nodes = new Map<string, RoadNode>(), incident = new Map<string, number>(); let edges: RoadEdge[] = [];
  const ensure = (id: string, position: Point) => { if (!nodes.has(id)) nodes.set(id, { id: clean(id), type: "boundary", position }); };
  const approachParameter = (cubic: ReturnType<typeof interpolate>[number]["cubic"], target: number, fromStart: boolean) => {
    let low = 0, high = 1;
    for (let step = 0; step < 32; step++) { const middle = (low + high) / 2, measured = distance(cubicPoint(cubic, middle), fromStart ? cubic.p0 : cubic.p3); if (fromStart ? measured < target : measured >= target) low = middle; else high = middle; }
    return (low + high) / 2;
  };
  for (const road of doc.roads) {
    const compiledIds = compilationKeyPointIds(doc, road);
    const points = compiledIds.map((id) => doc.keyPoints[id].position), curves = interpolate(points);
    curves.forEach(({ cubic }, i) => {
      const fromId = compiledIds[i], toId = compiledIds[i + 1], fromJ = doc.keyPoints[fromId].kind === "junction", toJ = doc.keyPoints[toId].kind === "junction";
      ensure(fromId, cubic.p0); ensure(toId, cubic.p3);
      const pieces: { from: string; to: string; cubic?: typeof cubic }[] = [];
      const chord = distance(cubic.p0, cubic.p3), fromDistance = fromJ ? approachLength(doc, fromId, road) : 0, toDistance = toJ ? approachLength(doc, toId, road) : 0;
      if (fromJ && toJ && chord < EXTRA_INBOUND_LANE_LINK_DISTANCE_M
          && junctionHasAutomaticExtraInboundLane(doc, fromId)
          && junctionHasAutomaticExtraInboundLane(doc, toId)) {
        // A sub-150m pair is one shared, straight approach section. Splitting
        // two 50m envelopes would overlap below 100m and would unnecessarily
        // narrow then widen again above it.
        edges.push({ id: `${road.id}_edge_${i + 1}_1`, road: road.id,
          from: clean(fromId), to: clean(toId), geometry: { type: "line" },
          ...features(road.style) });
        incident.set(fromId, (incident.get(fromId) ?? 0) + 1);
        incident.set(toId, (incident.get(toId) ?? 0) + 1);
        return;
      }
      const fromFraction = Math.min(.48, approachParameter(cubic, fromDistance, true)), toFraction = Math.max(.52, approachParameter(cubic, toDistance, false));
      let lo = 0, hi = 1, current = fromId;
      if (fromJ && chord > fromDistance + .5) { lo = fromFraction; const id = `${road.id}_approach_${i}_from`, tangent = cubicTangent(cubic, 0); const p: Point = [cubic.p0[0] + tangent[0] * fromDistance, cubic.p0[1] + tangent[1] * fromDistance]; ensure(id, p); pieces.push({ from: current, to: id }); current = id; }
      let end = toId;
      if (toJ && chord > toDistance + .5) { hi = toFraction; end = `${road.id}_approach_${i}_to`; const tangent = cubicTangent(cubic, 1); ensure(end, [cubic.p3[0] - tangent[0] * toDistance, cubic.p3[1] - tangent[1] * toDistance]); }
      if (hi > lo + .001) {
        const middle = subCubic(cubic, lo, hi);
        // Refit the retained curve as a cubic Hermite span when an approach
        // endpoint moves onto the enforced tangent ray. Merely moving one
        // endpoint/handle can create a tiny-radius hook immediately after the
        // straight section; distributing the transition over the whole
        // retained span keeps it smooth and close to the original gentle arc.
        let refit = false;
        if (fromJ && current !== fromId) {
          middle.p0 = nodes.get(current)!.position;
          refit = true;
        }
        if (toJ && end !== toId) {
          middle.p3 = nodes.get(end)!.position;
          refit = true;
        }
        if (refit) {
          const chordLength = distance(middle.p0, middle.p3), handle = chordLength / 3;
          const startTangent = fromJ && current !== fromId
            ? cubicTangent(cubic, 0) : cubicTangent(cubic, lo);
          const endTangent = toJ && end !== toId
            ? cubicTangent(cubic, 1) : cubicTangent(cubic, hi);
          middle.p1 = [middle.p0[0] + startTangent[0] * handle, middle.p0[1] + startTangent[1] * handle];
          middle.p2 = [middle.p3[0] - endTangent[0] * handle, middle.p3[1] - endTangent[1] * handle];
        }
        pieces.push({ from: current, to: end, cubic: middle });
      }
      if (end !== toId) pieces.push({ from: end, to: toId });
      pieces.forEach((piece, p) => { const geometry: RoadEdge["geometry"] = piece.cubic && (distance(piece.cubic.p0, piece.cubic.p1) > .001 || distance(piece.cubic.p2, piece.cubic.p3) > .001) ? { type: "cubic_bezier", control_from: piece.cubic.p1, control_to: piece.cubic.p2 } : { type: "line" }; edges.push({ id: `${road.id}_edge_${i + 1}_${p + 1}`, road: road.id, from: clean(piece.from), to: clean(piece.to), geometry, ...features(road.style) }); incident.set(piece.from, (incident.get(piece.from) ?? 0) + 1); incident.set(piece.to, (incident.get(piece.to) ?? 0) + 1); });
    });
  }
  // Approach construction can place a helper node exactly on a following
  // edge when nearby junction envelopes meet. The generator requires
  // explicit topology at every such point, so split line and cubic edges
  // deterministically instead of rejecting the newly authored road.
  edges = edges.flatMap((edge) => {
    const a = nodes.get(edge.from)!.position, b = nodes.get(edge.to)!.position;
    const cubic = edge.geometry?.type === "cubic_bezier"
      ? { p0: a, p1: edge.geometry.control_from, p2: edge.geometry.control_to, p3: b }
      : null;
    const dx = b[0] - a[0], dy = b[1] - a[1], lengthSquared = dx * dx + dy * dy;
    if (!cubic && lengthSquared < 1e-9) return [edge];
    const interior = [...nodes.values()].flatMap((node) => {
      if (node.id === edge.from || node.id === edge.to) return [];
      let t: number, separation: number;
      if (!cubic) {
        t = ((node.position[0] - a[0]) * dx + (node.position[1] - a[1]) * dy) / lengthSquared;
        separation = distance(cubicPoint({ p0: a, p1: [a[0] + dx / 3, a[1] + dy / 3], p2: [a[0] + dx * 2 / 3, a[1] + dy * 2 / 3], p3: b }, t), node.position);
      } else {
        let bestT = 0, bestDistance = Infinity;
        for (let sample = 0; sample <= 256; sample++) { const candidateT = sample / 256, candidateDistance = distance(cubicPoint(cubic, candidateT), node.position); if (candidateDistance < bestDistance) { bestT = candidateT; bestDistance = candidateDistance; } }
        let low = Math.max(0, bestT - 1 / 256), high = Math.min(1, bestT + 1 / 256);
        for (let step = 0; step < 24; step++) { const left = low + (high - low) / 3, right = high - (high - low) / 3; if (distance(cubicPoint(cubic, left), node.position) <= distance(cubicPoint(cubic, right), node.position)) high = right; else low = left; }
        t = (low + high) * .5; separation = distance(cubicPoint(cubic, t), node.position);
      }
      if (t <= 1e-6 || t >= 1 - 1e-6) return [];
      return separation <= 1e-4 ? [{ id: node.id, t }] : [];
    }).sort((left, right) => left.t - right.t);
    if (!interior.length) return [edge];
    const ids = [edge.from, ...interior.map((item) => item.id), edge.to];
    return ids.slice(0, -1).map((from, index) => ({
      ...edge, id: index ? `${edge.id}_split_${index + 1}` : edge.id,
      from, to: ids[index + 1], geometry: cubic ? (() => { const piece = subCubic(cubic, index ? interior[index - 1].t : 0, index < interior.length ? interior[index].t : 1); return { type: "cubic_bezier" as const, control_from: piece.p1, control_to: piece.p2 }; })() : { type: "line" as const },
    }));
  });
  incident.clear();
  for (const edge of edges) {
    const rawFrom = [...nodes.entries()].find(([, node]) => node.id === edge.from)?.[0] ?? edge.from;
    const rawTo = [...nodes.entries()].find(([, node]) => node.id === edge.to)?.[0] ?? edge.to;
    incident.set(rawFrom, (incident.get(rawFrom) ?? 0) + 1);
    incident.set(rawTo, (incident.get(rawTo) ?? 0) + 1);
  }
  for (const [id, node] of nodes) {
    if (doc.keyPoints[id]?.kind !== "junction") continue;
    const count = incident.get(id) ?? 0, s = doc.junctions[id] ?? { exterior_color: "brown" };
    const unsignalized = s.signal_control === "unsignalized";
    const priorityT = s.signal_control === "unsignalized_n_by_1";
    node.type = count === 3
      ? (priorityT ? "priority_t_junction"
        : unsignalized ? "stop_t_junction" : "signalized_t_junction")
      : (unsignalized ? "stop_cross" : "signalized_cross");
    node.name = s.name ?? ""; node.roman_name = s.roman_name ?? ""; node.exterior_color = s.exterior_color; node.crossings = ["east_west", "north_south"];
    if (!unsignalized && !priorityT) {
      node.signal_phase = "group_a_green"; node.vehicle_arrow = "none";
      if (junctionHasAutomaticExtraInboundLane(doc, id)) {
        const touching = edges.filter((edge) => edge.from === node.id || edge.to === node.id);
        let selected = touching;
        if (count === 3) {
          const throughRoad = doc.roads.find((road) => {
            const index = road.keyPointIds.indexOf(id);
            return index > 0 && index < road.keyPointIds.length - 1;
          });
          const throughEdges = touching.filter((edge) => edge.road === throughRoad?.id);
          const stemEdge = touching.find((edge) => edge.road !== throughRoad?.id);
          const outward = (edge: RoadEdge): Point => {
            const other = nodes.get(edge.from === node.id ? edge.to : edge.from)!.position;
            const dx = other[0] - node.position[0], dy = other[1] - node.position[1], length = Math.hypot(dx, dy);
            return [dx / length, dy / length];
          };
          if (stemEdge) {
            const stem = outward(stemEdge);
            selected = throughEdges.filter((edge) => {
              const arm = outward(edge), inbound: Point = [-arm[0], -arm[1]];
              return inbound[0] * stem[1] - inbound[1] * stem[0] < -1e-6;
            });
          }
        }
        for (const edge of selected) {
          const endpoint = edge.from === node.id ? "from" : "to";
          edge.approaches = {
            ...edge.approaches,
            [endpoint]: { ...edge.approaches?.[endpoint], extra_inbound_lane: true },
          };
        }
      }
    }
    else {
      delete node.signal_phase; delete node.vehicle_arrow;
      const incidentRoads = doc.roads
        .filter((road) => road.keyPointIds.includes(id))
        .sort((a, b) => a.id.localeCompare(b.id));
      const stopRoad = count === 3
        ? incidentRoads.find((road) => {
            const index = road.keyPointIds.indexOf(id);
            return index === 0 || index === road.keyPointIds.length - 1;
          }) ?? incidentRoads[0]
        : incidentRoads[0];
      for (const edge of edges) {
        if (edge.road !== stopRoad?.id) continue;
        if (edge.from === node.id) edge.approaches = { ...edge.approaches, from: { stop_control: true } };
        if (edge.to === node.id) edge.approaches = { ...edge.approaches, to: { stop_control: true } };
      }
    }
  }
  const roads: Road[] = doc.roads.map((r) => ({ id: r.id, road_class: r.style.road_class, speed_limit: r.style.speed_limit, lanes_each_way: r.style.lanes_each_way, sidewalks: r.style.sidewalks }));
  const components: RoadComponent[] = [];
  for (const component of doc.components ?? []) {
    const road = doc.roads.find((item) => item.id === component.roadId), authored = road && pointAtRoadStation(doc, road, component.stationM); if (!road || !authored) continue;
    let best: { edge: RoadEdge; station: number; distance: number } | null = null;
    for (const edge of edges.filter((item) => item.road === road.id)) {
      const p0 = nodes.get(edge.from)!.position, p3 = nodes.get(edge.to)!.position, cubic = edge.geometry?.type === "cubic_bezier" ? { p0, p1: edge.geometry.control_from, p2: edge.geometry.control_to, p3 } : { p0, p1: [p0[0] + (p3[0] - p0[0]) / 3, p0[1] + (p3[1] - p0[1]) / 3] as Point, p2: [p0[0] + (p3[0] - p0[0]) * 2 / 3, p0[1] + (p3[1] - p0[1]) * 2 / 3] as Point, p3 };
      const samples = sampleCubic(cubic, 96); let station = 0;
      for (let i = 0; i < samples.length - 1; i++) { const a = samples[i].point, b = samples[i + 1].point, dx = b[0] - a[0], dy = b[1] - a[1], ls = dx * dx + dy * dy, t = Math.max(0, Math.min(1, ((authored.point[0] - a[0]) * dx + (authored.point[1] - a[1]) * dy) / Math.max(ls, 1e-9))), q: Point = [a[0] + dx * t, a[1] + dy * t], d = distance(authored.point, q); if (!best || d < best.distance) best = { edge, station: station + Math.sqrt(ls) * t, distance: d }; station += Math.sqrt(ls); }
    }
    if (best) components.push({ id: component.id, type: component.type, edge: best.edge.id, side: component.side, station: best.station });
  }
  return { scene: { time_of_day: doc.scene?.time_of_day ?? "day" }, roads, nodes: [...nodes.values()], edges, components };
}

export function compileEditorV2(doc: EditorDocumentV2): RoadNetworkDocument {
  const check = validateEditorV2(doc); if (!check.valid) throw new Error(check.errors.join("\n"));
  return compileEditorV2Unchecked(doc);
}

export function previewEditorV2(doc: EditorDocumentV2): RoadNetworkDocument {
  return compileEditorV2Unchecked(doc);
}

export function migrateLegacy(old: EditorDocument): EditorDocumentV2 {
  let doc = clone(EMPTY_EDITOR_V2); doc.scene = { time_of_day: old.scene?.time_of_day ?? "day" }; const ids = new Set<string>();
  for (const road of old.roads) { const a = unique("point", ids); ids.add(a); const b = unique("point", ids); ids.add(b); doc.keyPoints[a] = { id: a, position: road.start, kind: "anchor" }; doc.keyPoints[b] = { id: b, position: road.end, kind: "anchor" }; doc.roads.push({ id: road.id, keyPointIds: [a, b], style: clone(road.style) }); }
  doc = normalizeIntersections(doc);
  for (const [position, style] of Object.entries(old.junctions ?? {})) { const p = position.split(",").map(Number) as Point; const kp = Object.values(doc.keyPoints).find((x) => x.kind === "junction" && near(x.position, p)); if (kp) doc.junctions[kp.id] = style; }
  return doc;
}
