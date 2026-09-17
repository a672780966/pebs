from __future__ import annotations

import json

import pytest
from conftest import REQUEST_1, FakeLLM, run_build

from pebs import gates


def _mutate_accepted(engine, artifact_id, mutate):
    content = json.loads(json.dumps(engine.store.accepted_content(artifact_id)))
    mutate(content)
    info = engine.store.add_revision(
        artifact_id=artifact_id,
        artifact_type=engine.store.get_revision(engine.store.accepted_rev_id(artifact_id))["artifact_type"],
        content=content,
        produced_by="test-mutant",
    )
    engine.store.set_accepted(artifact_id, info["revision_id"])
    return content


@pytest.fixture
def accepted_build(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    return engine


def test_g2_fails_when_claim_not_supported(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine, "script:sec1", lambda c: c["units"][1].update({"claim_refs": ["clm_deadbeef00@v1"]})
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g2_evidence(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("未获支持的 Claim" in issue["reason"] for issue in result["issues"])


def test_g2_fails_on_pending_placeholder(accepted_build):
    engine = accepted_build

    def mutate(content):
        content["units"][1]["placeholder"] = True

    _mutate_accepted(engine, "script:sec1", mutate)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g2_evidence(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("待核验" in issue["reason"] for issue in result["issues"])


def test_g4_fails_on_diagnosis_and_labeling(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "script:sec1",
        lambda c: c["units"][1].update({"text": "该学生患有焦虑症，应建议转介。"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g4_safety(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    reasons = " ".join(issue["reason"] for issue in result["issues"])
    assert "诊断" in reasons or "转介" in reasons or "标签" in reasons


def test_g4_needs_review_for_individual_inference(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "script:sec1",
        lambda c: c["units"][1].update({"text": "该学生注意力不集中，需要调整活动。"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g4_safety(ctx, "script:sec1")
    assert result["status"] == "NEEDS_REVIEW"


def test_g3_fails_when_strategy_outside_allowed_set(accepted_build):
    engine = accepted_build
    _mutate_accepted(
        engine,
        "teaching_plan:sec1",
        lambda c: c["strategies"][0].update({"strategy": "pure-lecture"}),
    )
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g3_pedagogy(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("不在知识类型" in issue["reason"] for issue in result["issues"])


def test_g6_flags_animation_requirement_conflict(engine):
    engine.llm = FakeLLM(animation_rejected=True)
    run_id, changeset_id = run_build(engine, "任务1 观察记录。每节 10–9999 字，每节至少 1 个案例和 1 个动画。")
    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "NEEDS_REVIEW"
    assert any("未通过 Animation Gate" in issue["reason"] for issue in result["issues"])
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False


def test_g6_not_applicable_requires_reason(engine):
    engine.llm = FakeLLM(animation_item=False)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g6_multimedia(ctx, "script:sec1")
    assert result["status"] == "NOT_APPLICABLE"
    assert result.get("not_applicable_reason")


def test_gate_result_invalidates_when_script_changes(accepted_build):
    engine = accepted_build
    assert gates.export_readiness(engine.store)["ready"] is True
    _mutate_accepted(engine, "script:sec1", lambda c: c["units"][1].update({"text": "改写后的讲解。"}))
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    assert any("已过期" in item for item in readiness["blocking"])
