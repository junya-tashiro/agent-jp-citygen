"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.lerp = exports.unit = exports.distance = exports.length = exports.cross = exports.dot = exports.mul = exports.sub = exports.add = void 0;
exports.cubicPoint = cubicPoint;
exports.cubicTangent = cubicTangent;
exports.cubicRadius = cubicRadius;
exports.interpolate = interpolate;
exports.sampleCubic = sampleCubic;
exports.curveIntersections = curveIntersections;
exports.curvePath = curvePath;
exports.minimumRadius = minimumRadius;
exports.splitCubic = splitCubic;
exports.subCubic = subCubic;
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
exports.add = add;
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
exports.sub = sub;
const mul = (a, n) => [a[0] * n, a[1] * n];
exports.mul = mul;
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
exports.dot = dot;
const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
exports.cross = cross;
const length = (a) => Math.hypot(a[0], a[1]);
exports.length = length;
const distance = (a, b) => (0, exports.length)((0, exports.sub)(a, b));
exports.distance = distance;
const unit = (a) => { const n = (0, exports.length)(a); return n > 1e-9 ? (0, exports.mul)(a, 1 / n) : [0, 0]; };
exports.unit = unit;
const lerp = (a, b, t) => (0, exports.add)(a, (0, exports.mul)((0, exports.sub)(b, a), t));
exports.lerp = lerp;
function cubicPoint(c, t) {
    const u = 1 - t;
    return [u ** 3 * c.p0[0] + 3 * u * u * t * c.p1[0] + 3 * u * t * t * c.p2[0] + t ** 3 * c.p3[0], u ** 3 * c.p0[1] + 3 * u * u * t * c.p1[1] + 3 * u * t * t * c.p2[1] + t ** 3 * c.p3[1]];
}
function cubicTangent(c, t) {
    const u = 1 - t;
    return (0, exports.unit)([3 * u * u * (c.p1[0] - c.p0[0]) + 6 * u * t * (c.p2[0] - c.p1[0]) + 3 * t * t * (c.p3[0] - c.p2[0]), 3 * u * u * (c.p1[1] - c.p0[1]) + 6 * u * t * (c.p2[1] - c.p1[1]) + 3 * t * t * (c.p3[1] - c.p2[1])]);
}
function cubicRadius(c, t) {
    const u = 1 - t;
    const d1 = [3 * u * u * (c.p1[0] - c.p0[0]) + 6 * u * t * (c.p2[0] - c.p1[0]) + 3 * t * t * (c.p3[0] - c.p2[0]), 3 * u * u * (c.p1[1] - c.p0[1]) + 6 * u * t * (c.p2[1] - c.p1[1]) + 3 * t * t * (c.p3[1] - c.p2[1])];
    const d2 = [6 * u * (c.p2[0] - 2 * c.p1[0] + c.p0[0]) + 6 * t * (c.p3[0] - 2 * c.p2[0] + c.p1[0]), 6 * u * (c.p2[1] - 2 * c.p1[1] + c.p0[1]) + 6 * t * (c.p3[1] - 2 * c.p2[1] + c.p1[1])];
    const numerator = Math.abs((0, exports.cross)(d1, d2));
    return numerator < 1e-9 ? Infinity : (0, exports.length)(d1) ** 3 / numerator;
}
// Centripetal Catmull-Rom converted to cubic Beziers. It interpolates every
// authored key point while avoiding the large loops of uniform Catmull-Rom.
function interpolate(points) {
    if (points.length < 2)
        return [];
    const result = [];
    const tj = (ti, a, b) => ti + Math.sqrt(Math.max((0, exports.distance)(a, b), 1e-9));
    for (let i = 0; i < points.length - 1; i++) {
        const p1 = points[i], p2 = points[i + 1];
        const p0 = i ? points[i - 1] : (0, exports.sub)((0, exports.mul)(p1, 2), p2);
        const p3 = i + 2 < points.length ? points[i + 2] : (0, exports.sub)((0, exports.mul)(p2, 2), p1);
        const t0 = 0, t1 = tj(t0, p0, p1), t2 = tj(t1, p1, p2), t3 = tj(t2, p2, p3);
        const m1 = (0, exports.mul)((0, exports.add)((0, exports.mul)((0, exports.sub)(p1, p0), 1 / (t1 - t0)), (0, exports.add)((0, exports.mul)((0, exports.sub)(p2, p0), -1 / (t2 - t0)), (0, exports.mul)((0, exports.sub)(p2, p1), 1 / (t2 - t1)))), t2 - t1);
        const m2 = (0, exports.mul)((0, exports.add)((0, exports.mul)((0, exports.sub)(p2, p1), 1 / (t2 - t1)), (0, exports.add)((0, exports.mul)((0, exports.sub)(p3, p1), -1 / (t3 - t1)), (0, exports.mul)((0, exports.sub)(p3, p2), 1 / (t3 - t2)))), t2 - t1);
        const cubic = { p0: p1, p1: (0, exports.add)(p1, (0, exports.mul)(m1, 1 / 3)), p2: (0, exports.sub)(p2, (0, exports.mul)(m2, 1 / 3)), p3: p2 };
        result.push({ cubic, index: i });
    }
    return result;
}
function sampleCubic(cubic, steps = 24) {
    return Array.from({ length: steps + 1 }, (_, i) => ({ point: cubicPoint(cubic, i / steps), t: i / steps }));
}
function lineHit(a, b, c, d) {
    const r = (0, exports.sub)(b, a), s = (0, exports.sub)(d, c), denominator = (0, exports.cross)(r, s);
    if (Math.abs(denominator) < 1e-8)
        return null;
    const u = (0, exports.cross)((0, exports.sub)(c, a), r) / denominator, t = (0, exports.cross)((0, exports.sub)(c, a), s) / denominator;
    if (t < -1e-8 || t > 1 + 1e-8 || u < -1e-8 || u > 1 + 1e-8)
        return null;
    return { t, u, point: (0, exports.add)(a, (0, exports.mul)(r, t)) };
}
function curveIntersections(a, b) {
    const hits = [];
    for (const as of a)
        for (const bs of b) {
            const ap = sampleCubic(as.cubic), bp = sampleCubic(bs.cubic);
            for (let i = 0; i < ap.length - 1; i++)
                for (let j = 0; j < bp.length - 1; j++) {
                    const hit = lineHit(ap[i].point, ap[i + 1].point, bp[j].point, bp[j + 1].point);
                    if (!hit)
                        continue;
                    const at = (i + hit.t) / (ap.length - 1), bt = (j + hit.u) / (bp.length - 1);
                    if (hits.some((item) => item.aSegment === as.index && item.bSegment === bs.index && (0, exports.distance)(item.point, hit.point) < .1))
                        continue;
                    const ta = cubicTangent(as.cubic, at), tb = cubicTangent(bs.cubic, bt);
                    const raw = Math.acos(Math.max(-1, Math.min(1, Math.abs((0, exports.dot)(ta, tb))))) * 180 / Math.PI;
                    hits.push({ aSegment: as.index, aT: at, bSegment: bs.index, bT: bt, point: hit.point, angle: raw });
                }
        }
    return hits;
}
function curvePath(segments, map = (p) => p) {
    if (!segments.length)
        return "";
    const first = map(segments[0].cubic.p0);
    return `M ${first[0]} ${first[1]} ` + segments.map(({ cubic }) => { const a = map(cubic.p1), b = map(cubic.p2), c = map(cubic.p3); return `C ${a[0]} ${a[1]} ${b[0]} ${b[1]} ${c[0]} ${c[1]}`; }).join(" ");
}
function minimumRadius(segments) {
    let radius = Infinity;
    for (const segment of segments)
        for (let i = 0; i <= 40; i++)
            radius = Math.min(radius, cubicRadius(segment.cubic, i / 40));
    return radius;
}
function splitCubic(c, t) {
    const a = (0, exports.lerp)(c.p0, c.p1, t), b = (0, exports.lerp)(c.p1, c.p2, t), d = (0, exports.lerp)(c.p2, c.p3, t);
    const e = (0, exports.lerp)(a, b, t), f = (0, exports.lerp)(b, d, t), p = (0, exports.lerp)(e, f, t);
    return [{ p0: c.p0, p1: a, p2: e, p3: p }, { p0: p, p1: f, p2: d, p3: c.p3 }];
}
function subCubic(c, from, to) {
    if (from <= 0 && to >= 1)
        return c;
    const [left] = splitCubic(c, Math.max(0, Math.min(1, to)));
    if (from <= 0)
        return left;
    const relative = from / Math.max(to, 1e-9);
    return splitCubic(left, Math.max(0, Math.min(1, relative)))[1];
}
