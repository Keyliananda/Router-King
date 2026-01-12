"""G-code parsing helpers for preview and streaming."""

import math
import re

_WORD_RE = re.compile(r"([A-Za-z])([-+]?\d*\.?\d+)")
_COMMENT_RE = re.compile(r"\(.*?\)")


class GcodePath:
    def __init__(self):
        self.segments = []
        self._min_x = None
        self._min_y = None
        self._max_x = None
        self._max_y = None

    def add_segment(self, x0, y0, x1, y1, rapid=False):
        if x0 == x1 and y0 == y1:
            return
        self.segments.append((x0, y0, x1, y1, rapid))
        for x, y in ((x0, y0), (x1, y1)):
            if self._min_x is None:
                self._min_x = self._max_x = x
                self._min_y = self._max_y = y
                continue
            self._min_x = min(self._min_x, x)
            self._max_x = max(self._max_x, x)
            self._min_y = min(self._min_y, y)
            self._max_y = max(self._max_y, y)

    def bounds(self):
        if self._min_x is None:
            return None
        return (self._min_x, self._min_y, self._max_x, self._max_y)


def strip_comments(line):
    line = _COMMENT_RE.sub("", line)
    if ";" in line:
        line = line.split(";", 1)[0]
    return line.strip()


def iter_gcode_lines(text):
    for raw in text.splitlines():
        line = strip_comments(raw)
        if line:
            yield line


def parse_gcode(text):
    parser = _Parser()
    for line in iter_gcode_lines(text):
        parser.handle_line(line)
    return parser.path


class _Parser:
    def __init__(self):
        self.path = GcodePath()
        self.absolute = True
        self.units = 1.0
        self.motion = 0
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0

    def handle_line(self, line):
        words = _parse_words(line)
        if not words:
            return
        coords = {}
        for letter, value in words:
            if letter == "G":
                code = int(round(value))
                if code in (0, 1, 2, 3):
                    self.motion = code
                elif code == 90:
                    self.absolute = True
                elif code == 91:
                    self.absolute = False
                elif code == 20:
                    self.units = 25.4
                elif code == 21:
                    self.units = 1.0
            elif letter in ("X", "Y", "Z", "I", "J", "R"):
                coords[letter] = value

        x0, y0, z0 = self.x, self.y, self.z
        x1, y1, z1 = x0, y0, z0

        if "X" in coords:
            x_val = coords["X"] * self.units
            x1 = x_val if self.absolute else x1 + x_val
        if "Y" in coords:
            y_val = coords["Y"] * self.units
            y1 = y_val if self.absolute else y1 + y_val
        if "Z" in coords:
            z_val = coords["Z"] * self.units
            z1 = z_val if self.absolute else z1 + z_val

        if self.motion in (0, 1):
            if (x0, y0) != (x1, y1):
                self.path.add_segment(x0, y0, x1, y1, rapid=self.motion == 0)
        elif self.motion in (2, 3):
            if (x0, y0) != (x1, y1):
                self._add_arc(x0, y0, x1, y1, coords, cw=self.motion == 2)

        self.x, self.y, self.z = x1, y1, z1

    def _add_arc(self, x0, y0, x1, y1, coords, cw):
        center = None
        if "I" in coords or "J" in coords:
            center = self._center_from_ij(x0, y0, x1, y1, coords, cw)
        elif "R" in coords:
            center = self._center_from_r(x0, y0, x1, y1, coords["R"], cw)
        if center is None:
            self.path.add_segment(x0, y0, x1, y1, rapid=False)
            return
        cx, cy, delta = center
        radius = math.hypot(x0 - cx, y0 - cy)
        if radius == 0.0:
            return
        steps = max(8, int(abs(delta) / (math.pi / 16)))
        prev_x, prev_y = x0, y0
        for step in range(1, steps + 1):
            angle = math.atan2(y0 - cy, x0 - cx) + (delta * step / steps)
            nx = cx + math.cos(angle) * radius
            ny = cy + math.sin(angle) * radius
            self.path.add_segment(prev_x, prev_y, nx, ny, rapid=False)
            prev_x, prev_y = nx, ny

    def _center_from_ij(self, x0, y0, x1, y1, coords, cw):
        i_val = coords.get("I", 0.0) * self.units
        j_val = coords.get("J", 0.0) * self.units
        cx = x0 + i_val
        cy = y0 + j_val
        delta = _arc_delta(x0, y0, x1, y1, cx, cy, cw=cw)
        return (cx, cy, delta) if delta is not None else None

    def _center_from_r(self, x0, y0, x1, y1, r_value, cw):
        radius = abs(r_value) * self.units
        dx = x1 - x0
        dy = y1 - y0
        dist = math.hypot(dx, dy)
        if dist == 0 or dist > 2 * radius:
            return None
        mid_x = (x0 + x1) / 2.0
        mid_y = (y0 + y1) / 2.0
        h = math.sqrt(max(radius * radius - (dist / 2.0) ** 2, 0.0))
        ux = -dy / dist
        uy = dx / dist
        centers = [
            (mid_x + ux * h, mid_y + uy * h),
            (mid_x - ux * h, mid_y - uy * h),
        ]
        use_large = r_value < 0
        best = None
        for cx, cy in centers:
            delta = _arc_delta(x0, y0, x1, y1, cx, cy, cw=cw)
            if delta is None:
                continue
            if best is None:
                best = (cx, cy, delta)
                continue
            if use_large:
                if abs(delta) > abs(best[2]):
                    best = (cx, cy, delta)
            else:
                if abs(delta) < abs(best[2]):
                    best = (cx, cy, delta)
        return best


def _parse_words(line):
    return [(letter.upper(), float(number)) for letter, number in _WORD_RE.findall(line)]


def _arc_delta(x0, y0, x1, y1, cx, cy, cw=None):
    start = math.atan2(y0 - cy, x0 - cx)
    end = math.atan2(y1 - cy, x1 - cx)
    delta = end - start
    if cw is None:
        return delta
    if cw:
        if delta >= 0:
            delta -= 2 * math.pi
    else:
        if delta <= 0:
            delta += 2 * math.pi
    return delta
