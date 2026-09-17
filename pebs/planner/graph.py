from __future__ import annotations

from typing import Any, Callable

from .. import registry
from .contracts import PlannerError, PlanEdge, PlanNode, node_title

GATE_PROVIDING_SKILLS = {"gate-runner"}
MAX_NODES = 40


def expand_graph(
    *,
    terminals: list[str],
    choose: Callable[..., dict[str, Any] | None],
    existing_satisfied: set[str],
    include_optional: set[str],
    exclude_artifacts: set[str],
    prefer: list[str] | None = None,
    pinned: list[str] | None = None,
) -> tuple[list[PlanNode], list[PlanEdge], list[str]]:
    nodes: dict[str, PlanNode] = {}
    reuse: set[str] = set()
    edges: list[PlanEdge] = []
    queue: list[tuple[str, str | None, bool]] = [(artifact, None, False) for artifact in terminals]
    produced_outputs: set[str] = set()
    gates_enqueued = False

    while queue:
        if not gates_enqueued and "script" in produced_outputs:
            gates_enqueued = True
            queue.append(("gate_result", None, False))
        artifact, required_by, optional_chain = queue.pop(0)
        if artifact in exclude_artifacts:
            continue
        if artifact in existing_satisfied:
            reuse.add(artifact)
            chosen_existing = choose(artifact, prefer=prefer, pinned=pinned)
            if chosen_existing is not None:
                record = chosen_existing["record"]
                skill_name = chosen_existing["name"]
                node = nodes.get(skill_name)
                if node is None:
                    steps = list(record.get("handler", {}).get("steps", []))
                    node = PlanNode(
                        node_id=skill_name,
                        title=node_title(skill_name, steps)
                        if steps
                        else str(record.get("description") or skill_name)[:24],
                        skill=skill_name,
                        steps=steps,
                        inputs=list(record.get("requires", [])),
                        outputs=list(record.get("produces", [])),
                        reason=f"复用已接受产物：{artifact}",
                        reused=True,
                        optional=False,
                    )
                    nodes[skill_name] = node
            if required_by:
                edges.append(PlanEdge(from_artifact=artifact, to_node=required_by, input=True))
            continue
        chosen = choose(artifact, prefer=prefer, pinned=pinned)
        if chosen is None:
            if required_by and artifact in existing_satisfied:
                continue
            raise PlannerError(f"no runtime skill can produce artifact '{artifact}'")
        record = chosen["record"]
        skill_name = chosen["name"]
        node_id = skill_name
        node = nodes.get(node_id)
        if node is None:
            steps = list(record.get("handler", {}).get("steps", []))
            node = PlanNode(
                node_id=node_id,
                title=node_title(skill_name, steps)
                if steps
                else str(record.get("description") or skill_name)[:24],
                skill=skill_name,
                steps=steps,
                inputs=list(record.get("requires", [])) + list(record.get("optional_requires", [])),
                outputs=list(record.get("produces", [])),
                gate_before=list(record.get("gates_before", [])),
                gate_after=list(record.get("gates_after", [])),
                preconditions=[dict(item) for item in record.get("preconditions", [])],
                reason=f"为产出 {artifact}",
                optional=True,
            )
            nodes[node_id] = node
            if len(nodes) > MAX_NODES:
                raise PlannerError(f"plan exceeds {MAX_NODES} nodes")
        produced_outputs.update(node.outputs)
        if not optional_chain:
            node.optional = False
        if required_by:
            edges.append(PlanEdge(from_artifact=artifact, to_node=required_by, input=True))
        for required in record.get("requires", []):
            if required in exclude_artifacts:
                continue
            queue.append((required, node_id, optional_chain))
        for optional in record.get("optional_requires", []):
            if optional in exclude_artifacts:
                continue
            # M6 §27：已存在的可选输入直接复用（零成本，且保留 provenance）
            if optional in include_optional or optional in existing_satisfied:
                queue.append((optional, node_id, True))

    produced: dict[str, str] = {}
    for node in nodes.values():
        for output in node.outputs:
            produced[output] = node.node_id
    for node in nodes.values():
        deps: list[str] = []
        for input_artifact in node.inputs:
            producer = produced.get(input_artifact)
            if producer and producer != node.node_id:
                deps.append(producer)
        node.depends_on = sorted(set(deps))
        if node.depends_on and node.optional:
            node.optional = all(nodes[dep].optional for dep in node.depends_on)

    apply_gate_topology(nodes, terminals)
    ordered = topological_order(list(nodes.values()))
    levels = parallel_levels(ordered)
    for node in ordered:
        node.parallel_group = levels[node.node_id]
    ordered_edges = [edge for edge in edges if edge.to_node in nodes]
    return ordered, ordered_edges, sorted(reuse)


def apply_gate_topology(nodes: dict[str, PlanNode], terminals: list[str]) -> None:
    """Order every applicable gate evaluator after the data it observes.

    Applicability comes from the deliverable contract (terminal outputs) only -
    never from which artifacts happen to exist or be reused. Obligations:
      gate_before -> evaluator is an ancestor of the declaring node
      gate_after  -> evaluator is a descendant of the declaring node
      observed artifact -> evaluator is downstream of its planned producer
    A producer that the evaluator step itself creates and consumes (G8 on the
    export manifest) is exempt. Absence of an optional observed producer is not
    an error: the gate's runtime semantics decide the outcome. topological_order
    stays the authoritative cycle check, so an impossible obligation surfaces as a
    PlannerError rather than a silently misordered plan.
    """
    from .. import gates

    producers: dict[str, list[str]] = {}
    for node in nodes.values():
        for output in node.outputs:
            producers.setdefault(output, []).append(node.node_id)

    def evaluators(gate_id: str) -> list[PlanNode]:
        step = gates.GATE_EVALUATOR_STEP.get(gate_id)
        if not step:
            return []
        # A reused node is not an executable evaluator for the current run.
        return [node for node in nodes.values() if step in node.steps and not node.reused]

    def depend(target: PlanNode, source_id: str) -> None:
        if source_id and source_id != target.node_id and source_id in nodes:
            target.depends_on = sorted(set(target.depends_on) | {source_id})

    applicable = set(terminals)
    for gate_id, contract in gates.GATE_CONTRACTS.items():
        if contract["scope"] not in applicable:
            continue
        for evaluator in evaluators(gate_id):
            intra_step = set(contract.get("produced_and_evaluated_in_same_step") or [])
            for node in nodes.values():
                if gate_id in node.gate_after:
                    depend(evaluator, node.node_id)
                if gate_id in node.gate_before:
                    depend(node, evaluator.node_id)
            for observed in gates.GATE_OBSERVED_ARTIFACTS.get(gate_id, []):
                if observed in intra_step:
                    continue
                for producer_id in producers.get(observed, []):
                    depend(evaluator, producer_id)


def topological_order(nodes: list[PlanNode]) -> list[PlanNode]:
    by_id = {node.node_id: node for node in nodes}
    ordered: list[PlanNode] = []
    visited: dict[str, int] = {}

    def visit(node: PlanNode) -> None:
        state = visited.get(node.node_id, 0)
        if state == 1:
            raise PlannerError(f"dependency cycle detected at {node.node_id}")
        if state == 2:
            return
        visited[node.node_id] = 1
        for dep in node.depends_on:
            if dep in by_id:
                visit(by_id[dep])
        visited[node.node_id] = 2
        ordered.append(node)

    for node in sorted(nodes, key=lambda item: item.node_id):
        visit(node)
    return ordered


def parallel_levels(ordered: list[PlanNode]) -> dict[str, int]:
    levels: dict[str, int] = {}
    for node in ordered:
        level = 0
        for dep in node.depends_on:
            level = max(level, levels.get(dep, 0) + 1)
        levels[node.node_id] = level
    return levels
