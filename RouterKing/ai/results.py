"""Result models for RouterKing AI analysis."""

from dataclasses import dataclass, field


@dataclass
class AnalysisIssue:
    severity: str
    message: str
    suggestion: str = ""
    object_label: str = ""
    feedback_key: str = ""
    weight: float = 1.0


@dataclass
class AnalysisResult:
    issues: list = field(default_factory=list)
    summary: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class CamAnalysisResult:
    issues: list = field(default_factory=list)
    summary: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class OptimizationTarget:
    obj: object
    label: str
    shape: object
    optimized_edges: int


@dataclass
class OptimizationResult:
    issues: list = field(default_factory=list)
    summary: str = ""
    stats: dict = field(default_factory=dict)
    preview_objects: list = field(default_factory=list)
    optimized_targets: list = field(default_factory=list)
