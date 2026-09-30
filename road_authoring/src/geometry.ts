export type Point = [number, number];
export interface Cubic { p0: Point; p1: Point; p2: Point; p3: Point }
export interface CurveSegment { cubic: Cubic; index: number }
export interface CurveHit { aSegment: number; aT: number; bSegment: number; bT: number; point: Point; angle: number }

export const add = (a: Point, b: Point): Point => [a[0] + b[0], a[1] + b[1]];
export const sub = (a: Point, b: Point): Point => [a[0] - b[0], a[1] - b[1]];
export const mul = (a: Point, n: number): Point => [a[0] * n, a[1] * n];
export const dot = (a: Point, b: Point) => a[0] * b[0] + a[1] * b[1];
export const cross = (a: Point, b: Point) => a[0] * b[1] - a[1] * b[0];
export const length = (a: Point) => Math.hypot(a[0], a[1]);
export const distance = (a: Point, b: Point) => length(sub(a, b));
export const unit = (a: Point): Point => { const n = length(a); return n > 1e-9 ? mul(a, 1 / n) : [0, 0]; };
export const lerp = (a: Point, b: Point, t: number): Point => add(a, mul(sub(b, a), t));

export function cubicPoint(c: Cubic, t: number): Point {
  const u = 1 - t;
  return [u ** 3 * c.p0[0] + 3 * u * u * t * c.p1[0] + 3 * u * t * t * c.p2[0] + t ** 3 * c.p3[0], u ** 3 * c.p0[1] + 3 * u * u * t * c.p1[1] + 3 * u * t * t * c.p2[1] + t ** 3 * c.p3[1]];
}
export function cubicTangent(c: Cubic, t: number): Point {
  const u = 1 - t;
  return unit([3 * u * u * (c.p1[0] - c.p0[0]) + 6 * u * t * (c.p2[0] - c.p1[0]) + 3 * t * t * (c.p3[0] - c.p2[0]), 3 * u * u * (c.p1[1] - c.p0[1]) + 6 * u * t * (c.p2[1] - c.p1[1]) + 3 * t * t * (c.p3[1] - c.p2[1])]);
}
export function cubicRadius(c: Cubic, t: number): number {
  const u = 1 - t;
  const d1: Point = [3 * u * u * (c.p1[0] - c.p0[0]) + 6 * u * t * (c.p2[0] - c.p1[0]) + 3 * t * t * (c.p3[0] - c.p2[0]), 3 * u * u * (c.p1[1] - c.p0[1]) + 6 * u * t * (c.p2[1] - c.p1[1]) + 3 * t * t * (c.p3[1] - c.p2[1])];
  const d2: Point = [6 * u * (c.p2[0] - 2 * c.p1[0] + c.p0[0]) + 6 * t * (c.p3[0] - 2 * c.p2[0] + c.p1[0]), 6 * u * (c.p2[1] - 2 * c.p1[1] + c.p0[1]) + 6 * t * (c.p3[1] - 2 * c.p2[1] + c.p1[1])];
  const numerator = Math.abs(cross(d1, d2));
  return numerator < 1e-9 ? Infinity : length(d1) ** 3 / numerator;
}

// Centripetal Catmull-Rom converted to cubic Beziers. It interpolates every
// authored key point while avoiding the large loops of uniform Catmull-Rom.
export function interpolate(points: Point[]): CurveSegment[] {
  if (points.length < 2) return [];
  const result: CurveSegment[] = [];
  const tj = (ti: number, a: Point, b: Point) => ti + Math.sqrt(Math.max(distance(a, b), 1e-9));
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i], p2 = points[i + 1];
    const p0 = i ? points[i - 1] : sub(mul(p1, 2), p2);
    const p3 = i + 2 < points.length ? points[i + 2] : sub(mul(p2, 2), p1);
    const t0 = 0, t1 = tj(t0, p0, p1), t2 = tj(t1, p1, p2), t3 = tj(t2, p2, p3);
    const m1 = mul(add(mul(sub(p1, p0), 1 / (t1 - t0)), add(mul(sub(p2, p0), -1 / (t2 - t0)), mul(sub(p2, p1), 1 / (t2 - t1)))), t2 - t1);
    const m2 = mul(add(mul(sub(p2, p1), 1 / (t2 - t1)), add(mul(sub(p3, p1), -1 / (t3 - t1)), mul(sub(p3, p2), 1 / (t3 - t2)))), t2 - t1);
    const cubic = { p0: p1, p1: add(p1, mul(m1, 1 / 3)), p2: sub(p2, mul(m2, 1 / 3)), p3: p2 };
    result.push({ cubic, index: i });
  }
  return result;
}

export function sampleCubic(cubic: Cubic, steps = 24) {
  return Array.from({ length: steps + 1 }, (_, i) => ({ point: cubicPoint(cubic, i / steps), t: i / steps }));
}

function lineHit(a: Point, b: Point, c: Point, d: Point) {
  const r = sub(b, a), s = sub(d, c), denominator = cross(r, s);
  if (Math.abs(denominator) < 1e-8) return null;
  const u = cross(sub(c, a), r) / denominator, t = cross(sub(c, a), s) / denominator;
  if (t < -1e-8 || t > 1 + 1e-8 || u < -1e-8 || u > 1 + 1e-8) return null;
  return { t, u, point: add(a, mul(r, t)) };
}

export function curveIntersections(a: CurveSegment[], b: CurveSegment[]): CurveHit[] {
  const hits: CurveHit[] = [];
  for (const as of a) for (const bs of b) {
    const ap = sampleCubic(as.cubic), bp = sampleCubic(bs.cubic);
    for (let i = 0; i < ap.length - 1; i++) for (let j = 0; j < bp.length - 1; j++) {
      const hit = lineHit(ap[i].point, ap[i + 1].point, bp[j].point, bp[j + 1].point); if (!hit) continue;
      const at = (i + hit.t) / (ap.length - 1), bt = (j + hit.u) / (bp.length - 1);
      if (hits.some((item) => item.aSegment === as.index && item.bSegment === bs.index && distance(item.point, hit.point) < .1)) continue;
      const ta = cubicTangent(as.cubic, at), tb = cubicTangent(bs.cubic, bt);
      const raw = Math.acos(Math.max(-1, Math.min(1, Math.abs(dot(ta, tb))))) * 180 / Math.PI;
      hits.push({ aSegment: as.index, aT: at, bSegment: bs.index, bT: bt, point: hit.point, angle: raw });
    }
  }
  return hits;
}

export function curvePath(segments: CurveSegment[], map: (p: Point) => Point = (p) => p) {
  if (!segments.length) return "";
  const first = map(segments[0].cubic.p0);
  return `M ${first[0]} ${first[1]} ` + segments.map(({ cubic }) => { const a = map(cubic.p1), b = map(cubic.p2), c = map(cubic.p3); return `C ${a[0]} ${a[1]} ${b[0]} ${b[1]} ${c[0]} ${c[1]}`; }).join(" ");
}

export function minimumRadius(segments: CurveSegment[]) {
  let radius = Infinity;
  for (const segment of segments) for (let i = 0; i <= 40; i++) radius = Math.min(radius, cubicRadius(segment.cubic, i / 40));
  return radius;
}

export function splitCubic(c: Cubic, t: number): [Cubic, Cubic] {
  const a = lerp(c.p0, c.p1, t), b = lerp(c.p1, c.p2, t), d = lerp(c.p2, c.p3, t);
  const e = lerp(a, b, t), f = lerp(b, d, t), p = lerp(e, f, t);
  return [{ p0: c.p0, p1: a, p2: e, p3: p }, { p0: p, p1: f, p2: d, p3: c.p3 }];
}

export function subCubic(c: Cubic, from: number, to: number): Cubic {
  if (from <= 0 && to >= 1) return c;
  const [left] = splitCubic(c, Math.max(0, Math.min(1, to)));
  if (from <= 0) return left;
  const relative = from / Math.max(to, 1e-9);
  return splitCubic(left, Math.max(0, Math.min(1, relative)))[1];
}
