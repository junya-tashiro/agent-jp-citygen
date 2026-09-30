"""Blender-independent 2D centreline geometry.

Road equipment is placed by arc length rather than Bezier parameter so spacing
is stable on both straight and gently curved roads.
"""

from dataclasses import dataclass
import bisect
import math


Point = tuple[float, float]


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def mul(a: Point, value: float) -> Point:
    return a[0] * value, a[1] * value


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Point) -> float:
    return math.hypot(*a)


def normalized(a: Point) -> Point:
    value = length(a)
    if value < 1e-9:
        raise ValueError("Cannot normalize a zero-length vector")
    return a[0] / value, a[1] / value


def left_normal(a: Point) -> Point:
    return -a[1], a[0]


def angle_degrees(a: Point) -> float:
    return math.degrees(math.atan2(a[1], a[0]))


def angle_between(a: Point, b: Point) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(normalized(a), normalized(b))))))


@dataclass(frozen=True)
class PathSample:
    s: float
    point: Point
    tangent: Point


class Centerline:
    """A line or cubic Bezier with an adaptive arc-length lookup table."""

    def __init__(self, start: Point, end: Point, control_from: Point | None = None,
                 control_to: Point | None = None, tolerance: float = 0.015):
        self.start = tuple(map(float, start))
        self.end = tuple(map(float, end))
        self.control_from = tuple(map(float, control_from)) if control_from else None
        self.control_to = tuple(map(float, control_to)) if control_to else None
        self.is_line = control_from is None and control_to is None
        if length(sub(self.end, self.start)) < 0.05:
            raise ValueError("Centreline endpoints must be at least 0.05 m apart")
        if (control_from is None) != (control_to is None):
            raise ValueError("A cubic Bezier requires both control points")
        pairs = [(0.0, self.start)]
        if self.is_line:
            pairs.append((1.0, self.end))
        else:
            self._subdivide(0.0, self.start, 1.0, self.end, pairs, tolerance, 0)
        self._ts = [item[0] for item in pairs]
        self._points = [item[1] for item in pairs]
        distances = [0.0]
        for a, b in zip(self._points, self._points[1:]):
            distances.append(distances[-1] + length(sub(b, a)))
        self._distances = distances
        self.length = distances[-1]
        if self.length < 0.05:
            raise ValueError("Centreline has negligible length")
        for t in (0.0, 1.0):
            if length(self._derivative(t)) < 1e-6:
                raise ValueError("Bezier endpoint handle produces a zero tangent")

    @classmethod
    def from_edge(cls, network, edge, tolerance=0.015):
        start = network.nodes[edge.start].position
        end = network.nodes[edge.end].position
        geometry = getattr(edge, "geometry", None)
        if geometry and geometry.kind == "cubic_bezier":
            return cls(start, end, geometry.control_from, geometry.control_to, tolerance)
        return cls(start, end, tolerance=tolerance)

    def _point(self, t: float) -> Point:
        if self.is_line:
            return add(self.start, mul(sub(self.end, self.start), t))
        p0, p1, p2, p3 = self.start, self.control_from, self.control_to, self.end
        u = 1.0 - t
        return (
            u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
        )

    def _derivative(self, t: float) -> Point:
        if self.is_line:
            return sub(self.end, self.start)
        p0, p1, p2, p3 = self.start, self.control_from, self.control_to, self.end
        u = 1.0 - t
        return (
            3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0]),
            3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1]),
        )

    def _subdivide(self, t0, p0, t1, p1, output, tolerance, depth):
        tm = (t0 + t1) * 0.5
        pm = self._point(tm)
        chord_mid = mul(add(p0, p1), 0.5)
        error = length(sub(pm, chord_mid))
        tangent_change = angle_between(self._derivative(t0), self._derivative(t1))
        if depth < 14 and (error > tolerance or tangent_change > 2.0
                           or length(sub(p1, p0)) > 2.0):
            self._subdivide(t0, p0, tm, pm, output, tolerance, depth + 1)
            self._subdivide(tm, pm, t1, p1, output, tolerance, depth + 1)
        else:
            output.append((t1, p1))

    def _t_at_distance(self, s: float) -> float:
        s = max(0.0, min(self.length, s))
        index = max(0, min(len(self._distances) - 2,
                           bisect.bisect_right(self._distances, s) - 1))
        a, b = self._distances[index:index + 2]
        fraction = 0.0 if b - a < 1e-9 else (s - a) / (b - a)
        return self._ts[index] + (self._ts[index + 1] - self._ts[index]) * fraction

    def point_at_distance(self, s: float) -> Point:
        return self._point(self._t_at_distance(s))

    def tangent_at_distance(self, s: float) -> Point:
        return normalized(self._derivative(self._t_at_distance(s)))

    def normal_at_distance(self, s: float) -> Point:
        return left_normal(self.tangent_at_distance(s))

    def offset_point(self, s: float, lateral: float) -> Point:
        return add(self.point_at_distance(s), mul(self.normal_at_distance(s), lateral))

    def sample_interval(self, s0=0.0, s1=None, max_segment=1.0) -> tuple[PathSample, ...]:
        s1 = self.length if s1 is None else s1
        count = max(1, math.ceil(abs(s1 - s0) / max_segment))
        return tuple(PathSample(s0 + (s1 - s0) * i / count,
                                self.point_at_distance(s0 + (s1 - s0) * i / count),
                                self.tangent_at_distance(s0 + (s1 - s0) * i / count))
                     for i in range(count + 1))

    def project_point(self, point: Point) -> tuple[float, float]:
        best_s, best_distance = 0.0, float("inf")
        for a, b, sa, sb in zip(self._points, self._points[1:],
                                self._distances, self._distances[1:]):
            ab = sub(b, a)
            denom = dot(ab, ab)
            t = 0.0 if denom < 1e-12 else max(0.0, min(1.0, dot(sub(point, a), ab) / denom))
            candidate = add(a, mul(ab, t))
            distance = length(sub(point, candidate))
            if distance < best_distance:
                best_distance = distance
                best_s = sa + (sb - sa) * t
        return best_s, best_distance

    def minimum_sampled_radius(self) -> float:
        """Conservative sampled horizontal radius; infinity for a line."""
        if self.is_line:
            return float("inf")
        samples = self.sample_interval(max_segment=0.5)
        result = float("inf")
        for before, current, after in zip(samples, samples[1:], samples[2:]):
            a = math.dist(before.point, current.point)
            b = math.dist(current.point, after.point)
            c = math.dist(before.point, after.point)
            area2 = abs(cross(sub(current.point, before.point), sub(after.point, before.point)))
            if area2 > 1e-8:
                result = min(result, a * b * c / (2.0 * area2))
        return result

    def has_self_intersection(self) -> bool:
        points = self._points

        def orientation(a, b, c):
            return cross(sub(b, a), sub(c, a))

        for i in range(len(points) - 1):
            for j in range(i + 2, len(points) - 1):
                if i == 0 and j == len(points) - 2:
                    continue
                a, b, c, d = points[i], points[i + 1], points[j], points[j + 1]
                o1, o2 = orientation(a, b, c), orientation(a, b, d)
                o3, o4 = orientation(c, d, a), orientation(c, d, b)
                if o1 * o2 < -1e-10 and o3 * o4 < -1e-10:
                    return True
        return False
