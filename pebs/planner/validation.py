from __future__ import annotations

from typing import Any

from .. import registry
from .contracts import KNOWN_GATES, KNOWN_GATES as _KNOWN


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = plan.get("nodes", [])
    ids = [node.get("node_id") for node in nodes]
    if len(ids) != len(set(ids)):
        errors.append("节点 id 重复")
    by_id = {node.get("node_id"): node for node in nodes}
    for node in nodes:
        node_id = node.get("node_id")
        steps = node.get("steps") or []
        skill = node.get("skill")
        record = registry.get(skill) if skill else None
        if record is None:
            errors.append(f"{node_id}: 未注册的 skill {skill}")
        else:
            runtime_kind = record.get("runtime", "builtin")
            if runtime_kind == "builtin":
                if not steps:
                    errors.append(f"{node_id}: 没有可执行步骤")
                elif set(steps) != set(record.get("handler", {}).get("steps", [])):
                    errors.append(f"{node_id}: steps 与注册表不一致")
            elif not (record.get("handler") or {}).get("skill_path"):
                errors.append(f"{node_id}: 外部 Skill 缺少 skill_path")
        for dep in node.get("depends_on", []):
            if dep not in by_id:
                errors.append(f"{node_id}: 依赖不存在 {dep}")
        for gate in list(node.get("gate_before", [])) + list(node.get("gate_after", [])):
            if gate not in KNOWN_GATES:
                errors.append(f"{node_id}: 未知 Gate {gate}")
    for artifact in plan.get("terminal_outputs", []):
        produced = any(artifact in (node.get("outputs") or []) for node in nodes)
        if not produced:
            errors.append(f"终产物缺少生产者：{artifact}")
    estimated = plan.get("estimated", {})
    if int(estimated.get("model_calls", 0)) < 0 or int(estimated.get("research_calls", 0)) < 0:
        errors.append("预算估计不能为负")
    try:
        from . import graph
        from .contracts import PlanNode

        graph.topological_order(
            [
                PlanNode(
                    node_id=node["node_id"],
                    title=node.get("title", ""),
                    skill=node.get("skill", ""),
                    depends_on=list(node.get("depends_on", [])),
                )
                for node in nodes
            ]
        )
    except Exception as exc:  # noqa: BLE001 - cycle or unknown dependency surfaces as validation error
        errors.append(str(exc))
    return errors


def gate_coverage(plan: dict[str, Any]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {}
    for node in plan.get("nodes", []):
        for gate in node.get("gate_after", []):
            coverage.setdefault(gate, []).append(node["node_id"])
    return coverage
