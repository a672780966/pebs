"""M6 §16/§43：显式 `/skill-name` 必须把该 Skill 的产出加入计划。

此前 `prefer` 只影响"同类候选之间选谁"：如果该产物类型不在 DAG 里（例如没有消费者、
也不是终端），显式调用形同虚设——外部 Skill 永远不会被 Planner 选中。
"""

from __future__ import annotations

from pebs import registry
from pebs.planner import planner


def _synthetic_record() -> dict:
    return {
        "name": "synthetic-worksheet-maker",
        "version": "0.1.0",
        "domain": "education",
        "agent": "pedagogy-agent",
        "description": "合成测试技能：产出学习单",
        "status": "APPROVED",
        "invocation": {"auto": True, "explicit": True},
        "requires": ["learning_design"],
        "produces": ["worksheet"],
        "emits": ["worksheet"],
        "optional_requires": [],
        "input_schema": None,
        "output_schema": None,
        "provider": [],
        "tools": [],
        "risk_level": "low",
        "network": False,
        "filesystem": "none",
        "external_side_effects": False,
        "runtime": "builtin",
        "handler": {"builtin_function": "pebs.pipeline:step_worksheets", "steps": ["worksheets"]},
        "gates_before": [],
        "gates_after": [],
        "parallelizable": True,
        "estimated_cost": {"model_calls": 1, "research_calls": 0},
        "versions": [],
        "pinned_version": None,
        "patches": [],
    }


def _route():
    return {
        "task_intent": "写一节课程脚本",
        "primary_outputs": ["script"],
        "secondary_outputs": [],
        "requested_outputs": ["script"],
        "knowledge_types": ["concept"],
        "research_need": "VERIFY",
        "media_need": "NONE",
        "assessment_need": False,
        "constraints": {},
        "risk_flags": [],
        "confidence": 0.8,
        "uncertainties": [],
        "source": "deterministic",
    }


def test_explicit_skill_adds_its_artifact_to_the_plan(monkeypatch):
    skills = dict(registry.load_skills())
    skills["synthetic-worksheet-maker"] = _synthetic_record()
    monkeypatch.setattr(registry, "load_skills", lambda: skills)

    plan = planner.plan(route=_route(), goal="显式调用合成技能", prefer=["synthetic-worksheet-maker"])
    assert "worksheet" in plan["terminal_outputs"], plan["terminal_outputs"]
    node = next((item for item in plan["nodes"] if item["skill"] == "synthetic-worksheet-maker"), None)
    assert node is not None, [item["skill"] for item in plan["nodes"]]
    assert plan["route_notes"]["explicit_skills"], plan["route_notes"]


def test_without_explicit_skill_the_artifact_is_not_planned(monkeypatch):
    skills = dict(registry.load_skills())
    skills["synthetic-worksheet-maker"] = _synthetic_record()
    monkeypatch.setattr(registry, "load_skills", lambda: skills)

    plan = planner.plan(route=_route(), goal="普通调用")
    assert "worksheet" not in plan["terminal_outputs"]
    assert all(item["skill"] != "synthetic-worksheet-maker" for item in plan["nodes"])
