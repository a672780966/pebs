from __future__ import annotations

from conftest import REQUEST_1, run_dynamic_build


def test_dynamic_build_runs_plan_with_human_titles(engine):
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    plan = engine.store.accepted_content("build_plan_dynamic")
    assert plan["mode"] == "dynamic"
    assert plan["nodes"]
    assert plan["terminal_outputs"]
    route = engine.store.accepted_content("router_result")
    assert route["source"] in ("hybrid", "deterministic_fallback")
    titles = [step["title"] for step in status["steps"]]
    assert any("脚本" in title or "要求" in title for title in titles)
    assert engine.store.revisions_of("script:sec1")
    engine.accept(start["changeset_id"])
    assert engine.store.accepted_rev_id("script:sec1")


def test_dynamic_plan_reuse_skips_existing_artifact(engine):
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    engine.accept(start["changeset_id"])
    design_rev = engine.store.accepted_rev_id("learning_design:sec1")
    design_revisions = len(engine.store.revisions_of("learning_design:sec1"))

    start2, status2 = run_dynamic_build(engine, REQUEST_1)
    steps = {step["step_id"]: step for step in status2["steps"]}
    assert steps["script-writer"]["status"] == "SUCCEEDED"
    assert "复用" in (steps["script-writer"]["note"] or "")
    assert steps["presentation-composer"] and "复用" in (steps["presentation-composer"]["note"] or "")
    assert engine.store.accepted_rev_id("learning_design:sec1") == design_rev
    assert len(engine.store.revisions_of("learning_design:sec1")) == design_revisions
    plan = engine.store.accepted_content("build_plan_dynamic")
    assert "script" in plan["reused_artifacts"]


def test_dynamic_case_replace_keeps_unrelated_revisions(engine):
    start, status = run_dynamic_build(engine, REQUEST_1)
    assert status["run"]["status"] == "succeeded"
    engine.accept(start["changeset_id"])
    design_before = engine.store.accepted_rev_id("learning_design:sec1")
    script_before = engine.store.accepted_rev_id("script:sec1")

    result = engine.case_replace("case:sec1:1", "换成大学宿舍情境的案例")
    engine.accept(result["changeset_id"])
    assert engine.store.accepted_rev_id("learning_design:sec1") == design_before
    assert engine.store.accepted_rev_id("script:sec1") != script_before


def test_dynamic_plan_is_recorded_and_valid(engine):
    from pebs.planner import validation

    start, status = run_dynamic_build(engine, REQUEST_1)
    plan = engine.store.accepted_content("build_plan_dynamic")
    assert validation.validate_plan(plan) == []
    node_ids = {node["node_id"] for node in plan["nodes"]}
    step_ids = {step["step_id"] for step in status["steps"]}
    assert step_ids == node_ids
