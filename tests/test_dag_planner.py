from __future__ import annotations

from pebs import planner
from pebs.planner import validation


def _route(outputs, **constraints):
    base = {"no_animation": False, "audit_only": False, "required_components": []}
    base.update(constraints)
    return {
        "source": "hybrid",
        "requested_outputs": outputs,
        "media_need": "DIAGRAM",
        "assessment_need": True,
        "research_need": "VERIFY",
        "constraints": base,
    }


def test_lesson_plan_and_pptx_plan_excludes_script_chain():
    plan = planner.plan(route=_route(["lesson_plan", "pptx", "docx"]), goal="大一第一课")
    skills = {node["skill"] for node in plan["nodes"]}
    assert "script-writer" not in skills
    assert "storyboard-designer" not in skills
    assert "animation-gate" not in skills
    assert {
        "lesson-designer",
        "media-router",
        "diagram-designer",
        "evidence-indexer",
        "presentation-planner",
        "presentation-composer",
        "docx-exporter",
    } <= skills
    assert "pptx_deck" in plan["terminal_outputs"]
    assert "export_manifest" in plan["terminal_outputs"]
    assert validation.validate_plan(plan) == []


def test_no_ppt_removes_presentation_nodes():
    plan = planner.plan(route=_route(["script", "docx"], no_animation=True), goal="只要脚本")
    skills = {node["skill"] for node in plan["nodes"]}
    assert "presentation-composer" not in skills
    assert "presentation-planner" not in skills
    assert "animation-gate" not in skills


def test_audit_only_reuses_existing_script_and_runs_gates():
    existing = [
        {"artifact_id": "script", "artifact_type": "script", "accepted_rev": "script@r1", "stale": 0},
        {"artifact_id": "evidence_index", "artifact_type": "evidence_index", "accepted_rev": "evidence_index@r1", "stale": 0},
        {"artifact_id": "requirements", "artifact_type": "requirements", "accepted_rev": "requirements@r1", "stale": 0},
        {"artifact_id": "learning_design:sec1", "artifact_type": "learning_design", "accepted_rev": "learning_design:sec1@r1", "stale": 0},
    ]
    plan = planner.plan(route=_route([], audit_only=True), goal="审核课程", existing_artifacts=existing)
    skills = {node["skill"] for node in plan["nodes"]}
    assert "gate-runner" in skills
    script_node = next(node for node in plan["nodes"] if node["skill"] == "script-writer")
    assert script_node["reused"] is True
    assert "presentation-composer" not in skills
    assert "storyboard-designer" not in skills
    assert "script" in plan["reused_artifacts"]
    assert validation.validate_plan(plan) == []


def test_existing_artifact_reuse_marks_node_reused():
    existing = [
        {
            "artifact_id": "learning_design:sec1",
            "artifact_type": "learning_design",
            "accepted_rev": "learning_design:sec1@r1",
            "stale": 0,
        }
    ]
    plan = planner.plan(route=_route(["script", "docx"]), goal="复用", existing_artifacts=existing)
    node = next(item for item in plan["nodes"] if item["skill"] == "learning-designer")
    assert node["reused"] is True
    assert "learning_design" in plan["reused_artifacts"]
    route = _route(["script", "pptx", "docx", "worksheet"])
    plan = planner.plan(route=route, goal="预算受限", budgets={"model_calls": 4, "research_requests": 2})
    assert plan["degraded"] is True
    assert plan["degradation_reasons"]
    assert validation.validate_plan(plan) == []


def test_validation_detects_dependency_cycle():
    plan = planner.plan(route=_route(["script", "docx"]), goal="cycle")
    node = plan["nodes"][1]
    node["depends_on"].append(node["node_id"])
    errors = validation.validate_plan(plan)
    assert any("cycle" in error or "依赖" in error for error in errors)


def test_parallel_groups_assigned_by_dependency_level():
    plan = planner.plan(route=_route(["script", "docx"]), goal="groups")
    groups = {node["skill"]: node["parallel_group"] for node in plan["nodes"]}
    assert groups["template-parser"] == 0
    assert groups["learning-designer"] > groups["requirements-builder"]
    assert max(groups.values()) > 1


def test_acceptance_example_lesson_plan_and_pptx_plan():
    from conftest import MissingLLM

    from pebs import router_v2

    request = (
        "为大一学生设计第一节90分钟《大学生心理健康教育》，希望学生先理解心理学为什么有用，"
        "包含2个深度思考活动，不需要录课脚本，最后生成教案和PPT。"
    )
    route = router_v2.route(request, llm=MissingLLM())
    assert "lesson_plan" in route["requested_outputs"]
    assert "pptx" in route["requested_outputs"]
    assert "script" not in route["requested_outputs"]
    assert router_v2.validate(route) == []
    plan = planner.plan(route=route, goal=request)
    skills = {node["skill"] for node in plan["nodes"]}
    assert "script-writer" not in skills
    assert "storyboard-designer" not in skills
    assert "animation-gate" not in skills
    assert "media-router" in skills
    assert "presentation-planner" in skills
    assert "presentation-composer" in skills
    assert "lesson-designer" in skills
    assert validation.validate_plan(plan) == []


def test_unknown_artifact_raises_planner_error():
    import pytest

    from pebs.planner import graph
    from pebs.planner.contracts import PlannerError

    with pytest.raises(PlannerError):
        graph.expand_graph(
            terminals=["nonexistent_artifact"],
            choose=lambda *args, **kwargs: None,
            existing_satisfied=set(),
            include_optional=set(),
            exclude_artifacts=set(),
        )
