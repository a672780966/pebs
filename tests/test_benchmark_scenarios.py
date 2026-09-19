"""M6 §26/§27：scenario 案例（F 局部修改 / G 只出 PPT）的真实执行路径。

hermetic 版用 FakeLLM 验证机制：先完成并接受基线课程，再执行 scenario，
并断言 locality（F）与复用（G）的指标确实被计算与记录。
"""

from __future__ import annotations

from conftest import FakeLLM, FakeResearch

from pebs import config, engine as engine_mod
from pebs.benchmark import runner

# 基线课程只生产脚本（与 case C 的请求一致；FakeLLM 的默认语义层会附加 pptx）
SCRIPT_ONLY_ROUTE = {
    "task_intent": "课程脚本生产",
    "primary_outputs": ["script"],
    "secondary_outputs": [],
    "delivery_mode": "asynchronous_video",
    "learner_profile": {"level": "在职教师", "discipline": "托育", "prior_knowledge": "有"},
    "knowledge_types": ["concept", "case_analysis"],
    "research_need": "VERIFY",
    "media_need": "DIAGRAM",
    "assessment_need": True,
    "requested_outputs": ["script"],
    "risk_flags": [],
    "confidence": 0.8,
    "uncertainties": [],
}


def _patch_providers(monkeypatch):
    """engine.py 直接绑定了 get_llm/get_research，必须 patch engine 模块。"""
    monkeypatch.setattr(engine_mod, "get_llm", lambda: FakeLLM(route_payload=SCRIPT_ONLY_ROUTE))
    monkeypatch.setattr(engine_mod, "get_research", lambda: FakeResearch())


def _isolate(tmp_path, monkeypatch):
    """hermetic 测试不得把 run.json 写进仓库的 benchmarks/runs（会污染真实报告）。"""
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(runner.cases, "runs_dir", lambda: runs)
    _patch_providers(monkeypatch)


def test_plan_only_selection_experiment_swaps_the_producer(tmp_path, monkeypatch):
    """§46：零模型调用的 Builtin vs 显式外部 Skill 对照应显示产出者被替换。"""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    records = runner.plan_only_case("D")
    changed = runner.plan_only_case("D", extra_skills=["hinge-question-designer"])
    builtin_assessment = next(
        trace for trace in records["selection_trace"] if trace["artifact"] == "assessment"
    )
    external_assessment = next(
        trace for trace in changed["selection_trace"] if trace["artifact"] == "assessment"
    )
    assert builtin_assessment["selected"] == "assessment-designer"
    assert external_assessment["selected"] == "hinge-question-designer"
    assert "显式指定" in external_assessment["reason"] or "Explicit" in external_assessment["reason"]
    assert "assessment" in changed["terminal_outputs"]
    assert changed["metrics"]["model_calls"] == 0


def test_local_edit_scenario_reports_locality(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    record = runner.run_scenario("F", project_id="bench-f-scenario")
    assert record["base_run_status"] == "succeeded", record
    assert record["scenario"] == "local_edit"
    assert record["run_status"] == "succeeded", record
    locality = record["locality"]
    assert locality["preserve"], "必须声明 preserve 集合"
    assert locality["locality_preservation_rate"] == 1.0, locality
    assert record["metrics"]["unnecessary_regeneration"] == 0
    assert record["edit"]["affected_artifacts"]


def test_ppt_only_scenario_reuses_the_existing_course(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    record = runner.run_scenario("G", project_id="bench-g-scenario")
    assert record["base_run_status"] == "succeeded", record
    assert record["scenario"] == "ppt_only"
    assert record["run_status"] == "succeeded", record
    nodes = dict(record["plan_nodes"])
    assert nodes.get("presentation-planner") is False, record["plan_nodes"]
    assert nodes.get("script-writer") is True, "脚本必须复用而不是重写"
    assert record["metrics"]["reuse_rate"] > 0
    assert "pptx_deck" in record["artifact_hashes"]
