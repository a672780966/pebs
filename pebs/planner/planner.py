from __future__ import annotations

from typing import Any

from .. import registry
from . import graph, resolver, validation
from .contracts import BuildPlan, PlannerError

OUTPUT_ARTIFACT = {
    "script": "script",
    "lesson_plan": "lesson_plan",
    "worksheet": "worksheet",
    "case": "case",
    "assessment": "assessment",
    "pptx": "pptx_deck",
    "diagram": "diagrams",
    "storyboard": "storyboard",
}

DROPPABLE_ORDER = [
    "worksheet-designer",
    "load-reviewer",
    "storyboard-designer",
    "animation-gate",
    "case-designer",
    "assessment-designer",
    "diagram-designer",
    "evidence-indexer",
    "preview-builder",
]


def _terminals(route: dict[str, Any]) -> list[str]:
    requested = route.get("requested_outputs", [])
    constraints = route.get("constraints", {}) or {}
    if constraints.get("audit_only"):
        return ["gate_result", "export_manifest"]
    terminals = {OUTPUT_ARTIFACT[item] for item in requested if item in OUTPUT_ARTIFACT}
    if any(item in ("docx", "markdown", "pptx") for item in requested):
        terminals.add("export_manifest")
    if not terminals:
        terminals.add("export_manifest")
    return sorted(terminals)


def _selection_trace(
    nodes: list[dict[str, Any]], *, prefer: list[str] | None, pinned: list[str] | None
) -> list[dict[str, Any]]:
    """§64 Resolver Explainability：记录每个节点为什么被选中、有哪些候选被拒。"""
    from . import resolver as resolver_mod

    trace: list[dict[str, Any]] = []
    for node in nodes:
        outputs = list(node.get("outputs") or [])
        if not outputs:
            continue
        ranked = resolver_mod.rank_report(outputs[0])
        if not ranked:
            continue
        selected = next((item for item in ranked if item["name"] == node["skill"]), None)
        selected_score = (selected or {}).get("score")
        rejected = [
            {
                "candidate": item["name"],
                "score": item["score"],
                "status": item["status"],
                # 并列时不能编造"它更低"：并列的决策依据是显式指定/registry 顺序
                "rejected_because": (
                    resolver_mod.rejection_reason(selected, item)
                    if selected_score is not None and item["score"] < selected_score
                    else "得分并列；由显式指定或 registry 顺序决定"
                ),
            }
            for item in ranked
            if item["name"] != node["skill"]
        ]
        reasons: list[str] = []
        if node["skill"] in list(prefer or []):
            reasons.append("用户显式指定（Explicit User Choice）")
        if node["skill"] in list(pinned or []):
            reasons.append("项目 pin")
        reasons.append(f"为产出 {outputs[0]}")
        if selected and rejected:
            runner_up = rejected[0]
            if selected_score is not None and runner_up["score"] < selected_score:
                reasons.append(f"综合分 {selected_score} 高于次优 {runner_up['candidate']}（{runner_up['score']}）")
            else:
                reasons.append(f"与次优 {runner_up['candidate']} 并列（{runner_up['score']}）")
        if selected:
            breakdown = selected.get("breakdown") or {}
            if breakdown:
                reasons.append(
                    "得分构成："
                    + "、".join(f"{key}={value:+.2f}" for key, value in breakdown.items())
                )
        trace.append(
            {
                "artifact": outputs[0],
                "selected": node["skill"],
                "selected_score": (selected or {}).get("score"),
                "reason": "；".join(reasons),
                "rejected_candidates": rejected[:5],
            }
        )
    return trace


def _estimate(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    model_calls = 0
    research_calls = 0
    for node in nodes:
        record = registry.get(node["skill"]) or {}
        cost = record.get("estimated_cost", {}) or {}
        model_calls += int(cost.get("model_calls", 0))
        research_calls += int(cost.get("research_calls", 0))
    cost_class = "low" if model_calls <= 5 else ("medium" if model_calls <= 12 else "high")
    return {"model_calls": model_calls, "research_calls": research_calls, "cost_class": cost_class}


def plan(
    *,
    route: dict[str, Any],
    goal: str,
    existing_artifacts: list[dict[str, Any]] | None = None,
    budgets: dict[str, int] | None = None,
    prefer: list[str] | None = None,
    pinned: list[str] | None = None,
) -> dict[str, Any]:
    existing_artifacts = existing_artifacts or []
    constraints = route.get("constraints", {}) or {}
    requested = route.get("requested_outputs", [])
    terminals = _terminals(route)

    # §16/§43：显式 `/skill-name` 必须把该 Skill 的产出加入计划（否则 prefer 只影响
    # "同类候选之间选谁"，而该产物类型根本不会进入 DAG，显式调用形同虚设）。
    explicit_produces: set[str] = set()
    explicit_notes: list[str] = []
    for name in prefer or []:
        canonical = registry.resolve_alias(name) or name
        record = registry.get(canonical) or {}
        produces = [str(item) for item in (record.get("produces") or []) + (record.get("emits") or [])]
        if not produces:
            continue
        explicit_produces.update(produces)
        explicit_notes.append(f"显式调用 /{name} → 加入 {produces}")
    if explicit_produces:
        terminals = sorted(set(terminals) | explicit_produces)

    include_optional: set[str] = set()
    if {"script", "case"} & set(requested) or "case" in constraints.get("required_components", []):
        include_optional.add("case")
    if {"script", "assessment", "worksheet"} & set(requested) or route.get("assessment_need"):
        include_optional.add("assessment")
    if "worksheet" in requested:
        include_optional.add("worksheet")
    if route.get("media_need") in ("DIAGRAM", "ANIMATION_CANDIDATE"):
        include_optional.add("diagrams")
    if constraints.get("audit_only"):
        include_optional |= {"gate_result", "claims_set"}

    exclude: set[str] = set()
    if constraints.get("no_animation"):
        exclude |= {"animation_decisions", "storyboard"}

    existing_satisfied = {
        item.get("artifact_type") or item.get("artifact_id")
        for item in existing_artifacts
        if item.get("accepted_rev") and not item.get("stale")
    }

    ordered, edges, reuse = graph.expand_graph(
        terminals=terminals,
        choose=resolver.choose,
        existing_satisfied=existing_satisfied,
        include_optional=include_optional,
        exclude_artifacts=exclude,
        prefer=prefer,
        pinned=pinned,
    )

    node_dicts = [node.to_dict() for node in ordered]
    estimated = _estimate(node_dicts)
    degraded = False
    reasons: list[str] = []
    route_notes: dict[str, Any] = {"research_need": route.get("research_need")}
    if explicit_notes:
        route_notes["explicit_skills"] = explicit_notes

    budget_calls = int((budgets or {}).get("model_calls", 0) or 0)
    if budget_calls and estimated["model_calls"] > budget_calls:
        for skill_name in DROPPABLE_ORDER:
            if estimated["model_calls"] <= budget_calls:
                break
            node = next((item for item in node_dicts if item["skill"] == skill_name and item["optional"]), None)
            if node is None:
                continue
            remaining = [item for item in node_dicts if item["node_id"] != node["node_id"]]
            if not _covers_terminal(terminals, remaining):
                continue
            node_dicts = remaining
            node["degraded"] = True
            degraded = True
            reasons.append(f"预算不足：省略可选能力 {node['title']}（{skill_name}）")
            estimated = _estimate(node_dicts)
        if estimated["model_calls"] > budget_calls:
            degraded = True
            reasons.append(
                f"预算 {budget_calls} 次模型调用低于必需估计 {estimated['model_calls']}；运行将在预算处暂停"
            )
    research_budget = int((budgets or {}).get("research_requests", 0) or 0)
    if research_budget and estimated["research_calls"] > research_budget:
        route_notes["research_need"] = "VERIFY"
        degraded = True
        reasons.append(
            f"研究预算不足（{research_budget} < {estimated['research_calls']}）：降级为仅核验关键 Claim"
        )

    node_ids = {item["node_id"] for item in node_dicts}
    filtered_edges = [edge.to_dict() for edge in edges if edge.to_node in node_ids] if edges else []
    plan_obj = BuildPlan(
        goal=goal,
        nodes=[],  # filled below via dicts for fidelity
        edges=[],
        terminal_outputs=terminals,
        estimated=estimated,
        route_source=str(route.get("source", "unknown")),
        degraded=degraded,
        degradation_reasons=reasons,
        route_notes=route_notes,
    )
    data = plan_obj.to_dict()
    data["nodes"] = node_dicts
    data["edges"] = filtered_edges
    data["reused_artifacts"] = reuse
    data["selection_trace"] = _selection_trace(node_dicts, prefer=prefer, pinned=pinned)

    errors = validation.validate_plan(data)
    if errors:
        raise PlannerError("; ".join(errors))
    return data


def _covers_terminal(terminals: list[str], nodes: list[dict[str, Any]]) -> bool:
    produced = {output for node in nodes for output in node.get("outputs", [])}
    return all(terminal in produced for terminal in terminals)
