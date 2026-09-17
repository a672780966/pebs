from __future__ import annotations

from typing import Any

from .. import gates as gate_mod
from .. import preconditions as precondition_mod
from .. import registry
from .contracts import KNOWN_GATES


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = plan.get("nodes", [])
    ids = [node.get("node_id") for node in nodes]
    if len(ids) != len(set(ids)):
        errors.append("节点 id 重复")
    by_id = {node.get("node_id"): node for node in nodes}
    terminals = set(plan.get("terminal_outputs") or [])
    producers = _artifact_producers(nodes)
    ancestors = _ancestors(nodes)
    reused_artifacts = set(plan.get("reused_artifacts") or [])
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
        # QA gate contract: known gate, real evaluator, compatible scope, and - only
        # for a gate this deliverable contract makes applicable - declaration ordering.
        for gate in list(node.get("gate_before", [])) + list(node.get("gate_after", [])):
            if gate not in KNOWN_GATES:
                errors.append(f"{node_id}: 未知 Gate {gate}")
                continue
            scope = gate_mod.GATE_SCOPE.get(gate)
            if scope is None or gate not in gate_mod.GATE_EVALUATOR_STEP:
                errors.append(f"{node_id}: Gate {gate} 缺少评估契约（scope / evaluator step）")
                continue
            if gate not in gate_mod.GATE_FUNCTIONS:
                errors.append(f"{node_id}: Gate {gate} 没有评估实现")
                continue
            if scope not in set(node.get("inputs") or []):
                errors.append(f"{node_id}: Gate {gate} 的目标范围 {scope} 不在该 skill 的输入中")
            if not _gate_applicable(gate, terminals):
                # Inapplicable to this deliverable contract: no evaluator is required.
                continue
            evaluators = _evaluator_nodes(nodes, gate)
            if not evaluators:
                errors.append(
                    f"{node_id}: Gate {gate} 适用但计划中没有可执行的评估方（步骤 "
                    f"{gate_mod.GATE_EVALUATOR_STEP[gate]}，且未被复用）"
                )
                continue
            for evaluator in evaluators:
                if gate in (node.get("gate_before") or []):
                    if evaluator["node_id"] not in ancestors.get(node_id, set()):
                        errors.append(f"{node_id}: Gate {gate} 的评估方必须先于该节点运行")
                if gate in (node.get("gate_after") or []):
                    if node_id not in ancestors.get(evaluator["node_id"], set()):
                        errors.append(f"{node_id}: Gate {gate} 的评估方必须晚于该节点运行")
        # Execution precondition contract: implemented kind, truthful + reachable +
        # checker-compatible declared input, resolvable scope.
        for precondition in node.get("preconditions") or []:
            errors.extend(_precondition_errors(node, precondition, producers, reused_artifacts))
    # Evaluator data ordering: for every applicable gate, a planned producer of an
    # artifact the gate observes must precede the evaluator. An artifact the evaluator
    # step itself produces and consumes (G8 on the export manifest) is exempt; absence
    # of an optional observed producer is not an error.
    for gate in gate_mod.ALL_GATES:
        if not _gate_applicable(gate, terminals):
            continue
        intra_step = set(gate_mod.GATE_CONTRACTS.get(gate, {}).get("produced_and_evaluated_in_same_step") or [])
        for evaluator in _evaluator_nodes(nodes, gate):
            for observed in gate_mod.GATE_OBSERVED_ARTIFACTS.get(gate, []):
                if observed in intra_step:
                    continue
                for producer_id in producers.get(observed, []):
                    if producer_id == evaluator["node_id"]:
                        errors.append(
                            f"Gate {gate}: 评估方 {evaluator['node_id']} 不能同时是 {observed} 的生产者"
                        )
                        continue
                    if producer_id not in ancestors.get(evaluator["node_id"], set()):
                        errors.append(
                            f"Gate {gate}: 评估方 {evaluator['node_id']} 必须晚于 {observed} 的生产者 {producer_id}"
                        )
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


def _artifact_producers(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    producers: dict[str, list[str]] = {}
    for node in nodes:
        for output in node.get("outputs") or []:
            producers.setdefault(str(output), []).append(str(node.get("node_id")))
    return producers


def _ancestors(nodes: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Transitive depends_on closure, bounded so a cyclic plan cannot recurse forever."""
    ancestors = {str(node.get("node_id")): set(node.get("depends_on") or []) for node in nodes}
    for _ in range(len(ancestors)):
        changed = False
        for node_id in ancestors:
            expanded = set(ancestors[node_id])
            for dep in list(ancestors[node_id]):
                expanded |= ancestors.get(dep, set())
            if expanded != ancestors[node_id]:
                ancestors[node_id] = expanded
                changed = True
        if not changed:
            break
    return ancestors


def _gate_applicable(gate_id: str, terminals: set[str]) -> bool:
    """Applicability comes from the deliverable contract only - never from artifact reuse."""
    scope = gate_mod.GATE_SCOPE.get(gate_id)
    return bool(scope) and scope in terminals


def _evaluator_nodes(nodes: list[dict[str, Any]], gate_id: str) -> list[dict[str, Any]]:
    """Nodes that actually execute the gate's evaluator step in this run.

    A reused node is not an executable evaluator for the current run.
    """
    step = gate_mod.GATE_EVALUATOR_STEP.get(gate_id)
    if not step:
        return []
    return [node for node in nodes if step in (node.get("steps") or []) and not node.get("reused")]


def _precondition_errors(
    node: dict[str, Any], precondition: dict[str, Any], producers: dict[str, list[str]], reused_artifacts: set[str]
) -> list[str]:
    node_id = node.get("node_id")
    kind = str(precondition.get("kind") or "")
    contract = precondition_mod.PRECONDITION_CONTRACTS.get(kind)
    if contract is None:
        return [f"{node_id}: 未实现的前置条件 {kind or '<empty>'}"]
    errors: list[str] = []
    declared = precondition.get("inputs")
    if not isinstance(declared, list) or not declared or any(not isinstance(item, str) or not item.strip() for item in declared):
        errors.append(f"{node_id}: 前置条件 {kind} 的作用域无法解析（inputs 必须是非空字符串列表）")
        declared = []
    usage_scope = precondition.get("usage_scope")
    if usage_scope is not None and (
        not isinstance(usage_scope, list)
        or not usage_scope
        or any(not isinstance(item, str) or not item.strip() for item in usage_scope)
    ):
        errors.append(f"{node_id}: 前置条件 {kind} 的 usage_scope 无法解析")
    required = list(contract.get("required_inputs") or [])
    for item in required:
        if item not in declared:
            errors.append(f"{node_id}: 前置条件 {kind} 必须声明输入 {item}")
    node_inputs = set(node.get("inputs") or [])
    for item in declared:
        if item not in required:
            errors.append(f"{node_id}: 前置条件 {kind} 声明的输入 {item} 与检查器契约不兼容（应为 {required}）")
            continue
        if item not in node_inputs:
            errors.append(f"{node_id}: 前置条件 {kind} 的输入 {item} 不在该 skill 的输入中")
            continue
        if not producers.get(item) and item not in reused_artifacts:
            errors.append(f"{node_id}: 前置条件 {kind} 的输入 {item} 不可达（既无生产者也未复用）")
    return errors
