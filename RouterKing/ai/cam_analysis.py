"""CAM risk analysis helpers for RouterKing."""

import math
import re

try:
    from .config import load_config
    from .results import AnalysisIssue, CamAnalysisResult
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from ai.config import load_config
    from ai.results import AnalysisIssue, CamAnalysisResult

try:
    from ..gcode.parser import iter_gcode_lines
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from gcode.parser import iter_gcode_lines


_WORD_RE = re.compile(r"([A-Za-z])([-+]?\d*\.?\d+)")


def analyze_gcode(text, config=None):
    if not text or not text.strip():
        result = CamAnalysisResult()
        result.issues.append(
            AnalysisIssue(
                severity="info",
                message="No G-code loaded.",
                suggestion="Load G-code in the G-Code tab and retry.",
                feedback_key="cam.no_gcode",
            )
        )
        result.summary = "No G-code loaded."
        return result

    if config is None:
        config = load_config()
    settings = config.get("cam", {})
    parser = _CamParser(settings)
    for line in iter_gcode_lines(text):
        parser.handle_line(line)
    return parser.result()


class _CamParser:
    def __init__(self, settings):
        self.units = 1.0
        self.absolute = True
        self.motion = None
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.feed = None
        self.safe_z = float(settings.get("safe_z_height", 3.0))
        self.min_arc_radius = float(settings.get("min_arc_radius", 0.5))
        self.tool_radius = float(settings.get("tool_radius", 1.0))
        self.max_plunge_step = float(settings.get("max_plunge_step", 2.0))
        self.max_issue_per_type = int(settings.get("max_issue_per_type", 5))
        self.stats = {
            "lines": 0,
            "rapid_moves": 0,
            "arcs": 0,
            "min_z": None,
            "min_arc_radius": None,
        }
        self.issues = []
        self._issue_counts = {}

    def handle_line(self, line):
        words = _parse_words(line)
        if not words:
            return
        self.stats["lines"] += 1

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
            elif letter == "F":
                self.feed = value
            elif letter in ("X", "Y", "Z", "I", "J", "R"):
                coords[letter] = value

        x0, y0, z0 = self.x, self.y, self.z
        x1, y1, z1 = x0, y0, z0

        if "X" in coords:
            value = coords["X"] * self.units
            x1 = value if self.absolute else x1 + value
        if "Y" in coords:
            value = coords["Y"] * self.units
            y1 = value if self.absolute else y1 + value
        if "Z" in coords:
            value = coords["Z"] * self.units
            z1 = value if self.absolute else z1 + value

        self._update_min_z(z1)

        if self.motion == 0:
            if (x0, y0) != (x1, y1):
                self.stats["rapid_moves"] += 1
                if max(z0, z1) <= self.safe_z:
                    self._add_issue(
                        "cam.rapid_low_z",
                        "warning",
                        f"Rapid move at low Z ({max(z0, z1):.2f}).",
                        "Raise Z before rapid XY moves.",
                    )
        elif self.motion in (2, 3):
            if (x0, y0) != (x1, y1):
                self.stats["arcs"] += 1
                radius = _arc_radius(coords, self.units)
                if radius is not None:
                    self._update_min_radius(radius)
                    if radius < self.min_arc_radius:
                        self._add_issue(
                            "cam.arc_radius",
                            "warning",
                            f"Arc radius is small ({radius:.3f}).",
                            "Increase arc radius or adjust toolpath smoothing.",
                        )
                    if self.tool_radius > 0 and radius < self.tool_radius:
                        self._add_issue(
                            "cam.overcut",
                            "warning",
                            f"Arc radius ({radius:.3f}) is smaller than tool radius.",
                            "Risk of overcut; reduce tool radius or adjust path.",
                        )

        if z1 < z0 and (z0 - z1) > self.max_plunge_step:
            self._add_issue(
                "cam.plunge_depth",
                "warning",
                f"Plunge step is large ({(z0 - z1):.2f}).",
                "Reduce Z step depth or add ramping.",
            )

        self.x, self.y, self.z = x1, y1, z1

    def result(self):
        result = CamAnalysisResult()
        result.issues = list(self.issues)
        result.stats = dict(self.stats)
        if not result.issues:
            result.issues.append(
                AnalysisIssue(
                    severity="info",
                    message="No CAM risks detected.",
                    suggestion="Toolpath looks clean with current thresholds.",
                    feedback_key="cam.no_issues",
                )
            )
        risk_count = len([issue for issue in result.issues if issue.severity != "info"])
        if risk_count:
            result.summary = f"CAM analysis finished. Risks: {risk_count}."
        else:
            result.summary = "CAM analysis finished. No risks detected."
        return result

    def _update_min_z(self, z_value):
        if z_value is None:
            return
        if self.stats["min_z"] is None or z_value < self.stats["min_z"]:
            self.stats["min_z"] = z_value

    def _update_min_radius(self, radius):
        if self.stats["min_arc_radius"] is None or radius < self.stats["min_arc_radius"]:
            self.stats["min_arc_radius"] = radius

    def _add_issue(self, key, severity, message, suggestion):
        count = self._issue_counts.get(key, 0)
        if count >= self.max_issue_per_type:
            return
        self._issue_counts[key] = count + 1
        self.issues.append(
            AnalysisIssue(
                severity=severity,
                message=message,
                suggestion=suggestion,
                feedback_key=key,
            )
        )


def _parse_words(line):
    return [(letter.upper(), float(number)) for letter, number in _WORD_RE.findall(line)]


def _arc_radius(coords, units):
    if "I" in coords or "J" in coords:
        i_val = coords.get("I", 0.0) * units
        j_val = coords.get("J", 0.0) * units
        radius = math.hypot(i_val, j_val)
        return radius if radius > 0 else None
    if "R" in coords:
        radius = abs(coords["R"]) * units
        return radius if radius > 0 else None
    return None
