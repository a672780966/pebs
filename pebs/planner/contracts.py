from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


KNOWN_GATES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]


class PlannerError(Exception):
    pass


@dataclass
class PlanNode:
    node_id: str
    title: str
    skill: str
    steps: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    optional: bool = False
    parallel_group: int = 0
    gate_before: list[str] = field(default_factory=list)
    gate_after: list[str] = field(default_factory=list)
    preconditions: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    reused: bool = False
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "skill": self.skill,
            "steps": list(self.steps),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "depends_on": list(self.depends_on),
            "optional": self.optional,
            "parallel_group": self.parallel_group,
            "gate_before": list(self.gate_before),
            "gate_after": list(self.gate_after),
            "preconditions": [dict(item) for item in self.preconditions],
            "reason": self.reason,
            "reused": self.reused,
            "degraded": self.degraded,
        }


@dataclass
class PlanEdge:
    from_artifact: str
    to_node: str
    input: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"from_artifact": self.from_artifact, "to_node": self.to_node, "input": self.input}


@dataclass
class BuildPlan:
    goal: str
    nodes: list[PlanNode]
    edges: list[PlanEdge]
    terminal_outputs: list[str]
    estimated: dict[str, Any]
    route_source: str = "unknown"
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    route_notes: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id or ("plan_" + uuid.uuid4().hex[:10]),
            "goal": self.goal,
            "mode": "dynamic",
            "route_source": self.route_source,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "terminal_outputs": list(self.terminal_outputs),
            "estimated": self.estimated,
            "degraded": self.degraded,
            "degradation_reasons": list(self.degradation_reasons),
            "route_notes": self.route_notes,
            "created_at": now_iso(),
        }


def node_title(skill_name: str, steps: list[str]) -> str:
    from .. import pipeline

    titles = {step["step_id"]: step["title"] for step in pipeline.plan_steps()}
    for step in steps:
        if step in titles:
            return titles[step]
    return skill_name
