"""Logical street coordinates, independent of editor edge subdivision."""
from dataclasses import dataclass
import math
import random
import zlib
from .geometry import Centerline


def seed_for(*parts):
    return zlib.crc32(':'.join(map(str, parts)).encode('utf-8')) & 0x7fffffff


@dataclass(frozen=True)
class StreetStation:
    identity: str
    offset: float
    direction: int = 1

    def at(self, local):
        return self.offset + self.direction * local

    def positions(self, start, end, spacing, seed=0, jitter=0.0):
        """Fixed anchors; clipping a segment never recentres the pattern."""
        low, high = sorted((self.at(start), self.at(end)))
        result = []
        for index in range(math.floor(low / spacing)-1, math.ceil(high / spacing)+1):
            rng = random.Random(seed_for(self.identity, seed, index))
            station = (index + .5 + rng.uniform(-jitter, jitter)) * spacing
            local = (station-self.offset) * self.direction
            if start <= local < end-1e-7:
                result.append((local, index))
        return sorted(result)

    def spans(self, start, end, spacing):
        low,high=sorted((self.at(start),self.at(end)))
        pieces=[]
        for index in range(math.floor(low/spacing),math.ceil(high/spacing)):
            a,b=max(low,index*spacing),min(high,(index+1)*spacing)
            p,q=sorted(((a-self.offset)*self.direction,(b-self.offset)*self.direction))
            if q-p>.001:pieces.append((p,q,index))
        return sorted(pieces)


def street_stations(network, paths=None):
    paths = paths or {e.id: Centerline.from_edge(network, e) for e in network.edges}
    groups = {}
    for edge in network.edges:
        groups.setdefault(edge.road_id or edge.id, []).append(edge)
    result = {}
    for road, edges in sorted(groups.items()):
        adjacency = {}
        for edge in edges:
            for node in (edge.start, edge.end):
                adjacency.setdefault(node, []).append(edge)
        remaining = {e.id for e in edges}
        while remaining:
            nodes = {n for e in edges if e.id in remaining for n in (e.start,e.end)}
            terminals = [n for n in nodes if len(adjacency[n]) == 1]
            anchor = min(terminals or nodes, key=lambda n:(network.nodes[n].position,n))
            identity = road + ':' + anchor
            queue = [(anchor,0.0)]
            while queue:
                node, distance = queue.pop(0)
                for edge in sorted(adjacency[node], key=lambda e:e.id):
                    if edge.id not in remaining:
                        continue
                    remaining.remove(edge.id)
                    forward = edge.start == node
                    result[edge.id] = StreetStation(identity, distance if forward else distance+paths[edge.id].length,1 if forward else -1)
                    queue.append((edge.end if forward else edge.start,distance+paths[edge.id].length))
    return result


SIDEWALK_WIDTH_M = 3.6
SIDEWALK_CORNER_RADIUS_M = SIDEWALK_WIDTH_M + .2


def sidewalk_width(edge):
    return SIDEWALK_WIDTH_M * (2 if edge.median else 1)


def sidewalk_footprint(edge):
    return sidewalk_width(edge) + SIDEWALK_CORNER_RADIUS_M - SIDEWALK_WIDTH_M
