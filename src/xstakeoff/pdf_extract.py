import fitz
from typing import Dict, List, Tuple
from collections import defaultdict
import math

Point = Tuple[float, float]
Polyline = List[Point]

def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def _polyline_length(poly: Polyline) -> float:
    return sum(_dist(poly[i - 1], poly[i]) for i in range(1, len(poly)))

def _round_point(p: Point, tol: float) -> Point:
    return (round(p[0] / tol) * tol, round(p[1] / tol) * tol)

def extract_merged_polylines_in_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    endpoint_tol: float = 2.0,
    min_length: float = 80.0,
) -> List[Polyline]:
    """
    Extract vector segments that intersect `rect` and merge connected segments
    into longer polylines.
    """
    segments: List[Tuple[Point, Point]] = []

    drawings = page.get_drawings()
    for d in drawings:
        drect = d.get("rect")
        if not drect:
            continue
        drect = fitz.Rect(drect)
        if not drect.intersects(rect):
            continue

        for item in d.get("items", []):
            kind = item[0]
            if kind == "l":
                # Common formats:
                # ("l", x1, y1, x2, y2)
                # ("l", (x1, y1), (x2, y2))
                if len(item) == 5:
                    _, x1, y1, x2, y2 = item
                    segments.append(((float(x1), float(y1)), (float(x2), float(y2))))
                elif len(item) == 3:
                    _, p1, p2 = item
                    segments.append(((float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))))
                else:
                    continue

            elif kind == "c":
                # Curve endpoints only (MVP)
                # Common formats:
                # ("c", x1,y1,x2,y2,x3,y3,x4,y4)
                # ("c", (x1,y1),(x2,y2),(x3,y3),(x4,y4))
                if len(item) == 9:
                    _, x1, y1, x2, y2, x3, y3, x4, y4 = item
                    segments.append(((float(x1), float(y1)), (float(x4), float(y4))))
                elif len(item) == 5:
                    _, p1, p2, p3, p4 = item
                    segments.append(((float(p1[0]), float(p1[1])), (float(p4[0]), float(p4[1]))))
                else:
                    continue


    if not segments:
        return []

    endpoint_index: Dict[Point, List[int]] = defaultdict(list)
    for idx, (a, b) in enumerate(segments):
        endpoint_index[_round_point(a, endpoint_tol)].append(idx)
        endpoint_index[_round_point(b, endpoint_tol)].append(idx)

    unused = set(range(len(segments)))

    def next_connected(current: Point) -> int | None:
        bucket = _round_point(current, endpoint_tol)
        for cand in endpoint_index.get(bucket, []):
            if cand in unused:
                return cand
        return None

    polylines: List[Polyline] = []

    while unused:
        start_idx = next(iter(unused))
        unused.remove(start_idx)
        a0, b0 = segments[start_idx]

        chain = [a0, b0]

        # forward
        end = b0
        while True:
            nxt = next_connected(end)
            if nxt is None:
                break
            unused.remove(nxt)
            a, b = segments[nxt]
            if _dist(end, a) <= endpoint_tol:
                chain.append(b)
                end = b
            elif _dist(end, b) <= endpoint_tol:
                chain.append(a)
                end = a
            else:
                break

        # backward
        start = a0
        prepend = [a0]
        while True:
            nxt = next_connected(start)
            if nxt is None:
                break
            unused.remove(nxt)
            a, b = segments[nxt]
            if _dist(start, a) <= endpoint_tol:
                prepend.append(b)
                start = b
            elif _dist(start, b) <= endpoint_tol:
                prepend.append(a)
                start = a
            else:
                break

        prepend = list(reversed(prepend))[:-1]
        merged = prepend + chain

        if _polyline_length(merged) >= min_length:
            polylines.append(merged)

    polylines.sort(key=_polyline_length, reverse=True)
    return polylines

def polyline_length(poly: Polyline) -> float:
    return _polyline_length(poly)