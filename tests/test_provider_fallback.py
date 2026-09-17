from __future__ import annotations

from conftest import REQUEST_1, MissingLLM, run_dynamic_build

from pebs import router_v2


def test_route_without_provider_uses_deterministic_fallback():
    result = router_v2.route("写一节观察记录课程脚本，每节 200–300 字。", llm=MissingLLM())
    assert result["source"] == "deterministic_fallback"
    assert result["constraints"]["word_min"] == 200
    assert result["constraints"]["word_max"] == 300
    assert router_v2.validate(result) == []


def test_dynamic_build_without_provider_blocks_without_fabrication(engine):
    engine.llm = MissingLLM()
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] in ("blocked", "failed")
    route = engine.store.accepted_content("router_result")
    assert route["source"] == "deterministic_fallback"
    assert engine.store.revisions_of("script:sec1") == []
    assert engine.store.revisions_of("learning_design:sec1") == []
    steps = {step["step_id"]: step["status"] for step in status["steps"]}
    assert "BLOCKED" in steps.values()


def test_plan_records_degraded_research_when_budget_tight(engine):
    start, status = run_dynamic_build(engine, REQUEST_1, budgets={"model_calls": 40, "research_requests": 0})
    plan = engine.store.accepted_content("build_plan_dynamic")
    assert plan["route_notes"].get("research_need") in ("VERIFY", "NONE", "LITERATURE", "DEEP")
    if plan["degraded"]:
        assert plan["degradation_reasons"]
