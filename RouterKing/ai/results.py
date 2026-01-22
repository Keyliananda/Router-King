"""Result models for RouterKing AI analysis."""

from dataclasses import dataclass, field


@dataclass
class AnalysisIssue:
    severity: str
    message: str
    suggestion: str = ""
    object_label: str = ""


@dataclass
class AnalysisResult:
    issues: list = field(default_factory=list)
    summary: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class OptimizationResult:
    issues: list = field(default_factory=list)
    summary: str = ""
    stats: dict = field(default_factory=dict)
    preview_objects: list = field(default_factory=list)
