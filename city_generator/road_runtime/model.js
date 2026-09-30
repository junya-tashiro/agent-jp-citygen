"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_DOCUMENT = exports.EMPTY_DOCUMENT = void 0;
exports.cloneDocument = cloneDocument;
exports.uniqueId = uniqueId;
exports.effectiveEdge = effectiveEdge;
exports.signalPhases = signalPhases;
exports.EMPTY_DOCUMENT = { roads: [], nodes: [], edges: [] };
exports.DEFAULT_DOCUMENT = {
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
function cloneDocument(doc) {
    return structuredClone(doc);
}
function uniqueId(prefix, existing) {
    let i = 1;
    while (existing.includes(`${prefix}_${i}`))
        i++;
    return `${prefix}_${i}`;
}
function effectiveEdge(edge, doc) {
    const road = doc.roads?.find((item) => item.id === edge.road);
    return {
        road_class: edge.road_class ?? road?.road_class ?? "local",
        speed_limit: edge.speed_limit ?? road?.speed_limit ?? 30,
        lanes_each_way: edge.lanes_each_way ?? road?.lanes_each_way ?? 1,
        sidewalks: edge.sidewalks ?? road?.sidewalks ?? "none",
    };
}
function signalPhases(type) {
    if (type === "signalized_cross")
        return ["east_west_green", "north_south_green", "east_west_right_arrow", "north_south_right_arrow", "east_west_yellow", "north_south_yellow", "all_red"];
    if (type === "signalized_t_junction")
        return ["east_west_green", "north_south_green", "east_west_yellow", "north_south_yellow", "all_red"];
    if (type === "signalized_pedestrian_crossing")
        return ["vehicle_green", "pedestrian_green", "all_red"];
    return [];
}
